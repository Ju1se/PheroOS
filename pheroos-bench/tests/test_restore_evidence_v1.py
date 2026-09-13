"""Byte-level publication checks, independent of any experiment evaluator."""

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest


TOOL = Path(__file__).parents[1] / "tools" / "restore_evidence_v1.py"
SPEC = importlib.util.spec_from_file_location("restore_evidence_v1", TOOL)
restore_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore_tool)


def digest(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


class RestoreEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive_name = "publication/evidence-v1/data.tar.xz"
        self.archive_path = self.root / self.archive_name
        self.archive_path.parent.mkdir(parents=True)
        self.original = bytes(range(256)) * 8193 + b"\x00\xff\n\r\nSQLite format 3\x00"
        self.file_name = "results/world 1/ledger.sqlite"
        self.direct_name = "docs/contract.md"
        direct = self.root / self.direct_name
        direct.parent.mkdir()
        direct.write_bytes(b"Frozen contract\r\n\xff")
        self.manifest = {
            "version": "publication_evidence_v1",
            "repository": "https://github.com/example/research",
            "base_commit": "a" * 40,
            "counts_toward_verdict": False,
            "archives": [],
            "files": [
                {"path": self.direct_name, "storage": "direct", **digest(direct.read_bytes())},
                {"path": self.file_name, "storage": "archive", "archive": self.archive_name,
                 "member": self.file_name, "mode": "100644", **digest(self.original)},
            ],
        }
        self.manifest_path = self.root / "publication/evidence-v1/manifest.json"
        self.make_archive([(self.file_name, self.original)])

    def make_archive(self, entries):
        with tarfile.open(self.archive_path, "w:xz") as archive:
            for name, data in entries:
                if isinstance(name, tarfile.TarInfo):
                    entry = name
                else:
                    entry = tarfile.TarInfo(name)
                    entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        self.manifest["archives"] = [{"path": self.archive_name, **digest(self.archive_path.read_bytes())}]
        self.save()

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def run_restore(self, verify_only=False):
        self.save()
        return restore_tool.restore(self.manifest_path, self.root, verify_only=verify_only)

    def assert_invalid(self):
        with self.assertRaises((restore_tool.EvidenceError, tarfile.TarError, OSError)):
            self.run_restore()

    def test_verify_then_lossless_restore_and_matching_existing_unchanged(self):
        target = self.root / self.file_name
        before = digest(self.archive_path.read_bytes())
        report = self.run_restore(verify_only=True)
        self.assertEqual(report["status"], "VERIFIED")
        self.assertEqual(report["files_verified"], 2)
        self.assertFalse(target.exists())
        self.assertFalse(target.parent.exists())
        report = self.run_restore()
        self.assertEqual(report["files_restored"], 1)
        self.assertEqual(target.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
        target.chmod(0o600)
        os.utime(target, ns=(1_000_000_001, 1_000_000_002))
        before_stat = target.stat()
        report = self.run_restore()
        after_stat = target.stat()
        self.assertEqual(report["files_restored"], 0)
        self.assertEqual((before_stat.st_ino, before_stat.st_mtime_ns, before_stat.st_mode),
                         (after_stat.st_ino, after_stat.st_mtime_ns, after_stat.st_mode))
        self.assertEqual(before, digest(self.archive_path.read_bytes()))
        self.assertFalse(list(target.parent.glob(".restore-evidence-*")))

    def test_archive_corruption_rejected_without_restoration(self):
        data = bytearray(self.archive_path.read_bytes())
        data[len(data) // 2] ^= 1
        self.archive_path.write_bytes(data)
        self.assert_invalid()
        self.assertFalse((self.root / self.file_name).exists())

    def test_member_corruption_rejected_even_with_valid_archive_digest(self):
        self.make_archive([(self.file_name, self.original[:-1] + b"x")])
        self.assert_invalid()
        self.assertFalse((self.root / self.file_name).exists())

    def test_member_size_mismatch_rejected(self):
        self.manifest["files"][1]["size_bytes"] += 1
        self.assert_invalid()

    def test_archive_size_mismatch_rejected(self):
        self.manifest["archives"][0]["size_bytes"] += 1
        self.assert_invalid()

    def test_unsafe_manifest_paths_rejected(self):
        for name in ("../escape", "/escape", "C:/escape", "results/../escape", "results//file", "./file", "file/", "a\\b"):
            with self.subTest(name=name):
                self.manifest["files"][1]["path"] = name
                self.manifest["files"][1]["member"] = name
                self.assert_invalid()

    def test_symlink_directory_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / "results").symlink_to(outside, target_is_directory=True)
            self.assert_invalid()
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_symlink_file_rejected_even_when_matching_bytes(self):
        target = self.root / self.file_name
        target.parent.mkdir(parents=True)
        other = self.root / "other"
        other.write_bytes(self.original)
        target.symlink_to(other)
        self.assert_invalid()

    def test_symlink_archive_rejected(self):
        other = self.root / "other.tar.xz"
        self.archive_path.rename(other)
        self.archive_path.symlink_to(other)
        self.assert_invalid()

    def test_nonregular_tar_members_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                entry = tarfile.TarInfo(self.file_name)
                entry.type = kind
                entry.linkname = "../../outside"
                self.make_archive([(entry, b"")])
                self.assert_invalid()

    def test_extra_tar_member_rejected(self):
        self.make_archive([(self.file_name, self.original), ("unexpected", b"extra")])
        self.assert_invalid()

    def test_missing_tar_member_rejected(self):
        self.make_archive([])
        self.assert_invalid()

    def test_duplicate_tar_member_rejected(self):
        self.make_archive([(self.file_name, self.original), (self.file_name, self.original)])
        self.assert_invalid()

    def test_duplicate_manifest_file_rejected(self):
        self.manifest["files"].append(dict(self.manifest["files"][1]))
        self.assert_invalid()

    def test_duplicate_manifest_archive_rejected(self):
        self.manifest["archives"].append(dict(self.manifest["archives"][0]))
        self.assert_invalid()

    def test_archive_member_must_equal_original_path(self):
        self.manifest["files"][1]["member"] = "another/path"
        self.assert_invalid()

    def test_existing_mismatched_file_never_overwritten(self):
        target = self.root / self.file_name
        target.parent.mkdir(parents=True)
        target.write_bytes(b"keep my different bytes")
        before_stat = target.stat()
        for verify_only in (False, True):
            with self.assertRaises(restore_tool.EvidenceError):
                self.run_restore(verify_only=verify_only)
        self.assertEqual(target.read_bytes(), b"keep my different bytes")
        self.assertEqual(target.stat().st_mtime_ns, before_stat.st_mtime_ns)

    def test_missing_or_changed_direct_file_rejected(self):
        direct = self.root / self.direct_name
        direct.write_bytes(b"changed")
        self.assert_invalid()
        direct.unlink()
        self.assert_invalid()

    def test_all_members_verified_before_any_materialization(self):
        second = "results/second.bin"
        self.manifest["files"].append({"path": second, "storage": "archive",
            "archive": self.archive_name, "member": second, **digest(b"expected")})
        self.make_archive([(self.file_name, self.original), (second, b"modified")])
        self.assert_invalid()
        self.assertFalse((self.root / self.file_name).exists())

    def test_counts_toward_verdict_cannot_be_promoted(self):
        self.manifest["counts_toward_verdict"] = True
        self.assert_invalid()

    def test_duplicate_json_key_rejected(self):
        self.manifest_path.write_text('{"version":"publication_evidence_v1","version":"other"}')
        with self.assertRaises(restore_tool.EvidenceError):
            restore_tool.restore(self.manifest_path, self.root)

    def test_cli_success_and_explicit_invalid_exit(self):
        command = [sys.executable, str(TOOL), "--manifest", str(self.manifest_path), "--root", str(self.root), "--verify-only"]
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "VERIFIED")
        self.archive_path.write_bytes(b"corrupted")
        result = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "INVALID_PUBLICATION")


if __name__ == "__main__":
    unittest.main()
