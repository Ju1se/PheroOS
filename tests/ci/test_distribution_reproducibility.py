from __future__ import annotations

from io import BytesIO
import gzip
from pathlib import Path
import tarfile
import tempfile
import unittest

from scripts.check_distribution_reproducibility import (
    compare_distribution_directories,
)
from scripts.normalize_sdist import RELEASE_SOURCE_DATE_EPOCH, normalize_sdist


def _write_archive(path: Path, *, timestamp: int, reverse: bool = False) -> None:
    entries = [
        ("pheroos-0.1.0/", None),
        ("pheroos-0.1.0/README.md", b"PheroOS\n"),
        ("pheroos-0.1.0/pheroos/__init__.py", b'__version__ = "0.1.0"\n'),
    ]
    if reverse:
        entries.reverse()
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename=f"source-{timestamp}.tar",
            mode="wb",
            fileobj=raw,
            mtime=timestamp,
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, payload in entries:
                    member = tarfile.TarInfo(name)
                    member.mtime = timestamp
                    member.uid = timestamp % 1000
                    member.gid = timestamp % 500
                    member.uname = "builder"
                    member.gname = "runner"
                    if payload is None:
                        member.type = tarfile.DIRTYPE
                        member.mode = 0o755
                        archive.addfile(member)
                    else:
                        member.mode = 0o644
                        member.size = len(payload)
                        archive.addfile(member, BytesIO(payload))


class DistributionReproducibilityTests(unittest.TestCase):
    def test_normalized_sdists_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            _write_archive(first, timestamp=1_700_000_000)
            _write_archive(second, timestamp=1_800_000_000, reverse=True)

            first_digest = normalize_sdist(first)
            second_digest = normalize_sdist(second)

            self.assertEqual(first_digest, second_digest)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, mode="r:gz") as archive:
                members = archive.getmembers()
                self.assertEqual(
                    [member.name for member in members],
                    sorted(member.name for member in members),
                )
                for member in members:
                    self.assertEqual(member.mtime, RELEASE_SOURCE_DATE_EPOCH)
                    self.assertEqual((member.uid, member.gid), (0, 0))
                    self.assertEqual((member.uname, member.gname), ("", ""))

    def test_unsafe_member_fails_without_replacing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unsafe.tar.gz"
            with tarfile.open(path, mode="w:gz") as archive:
                member = tarfile.TarInfo("../escape")
                member.size = 1
                archive.addfile(member, BytesIO(b"x"))
            before = path.read_bytes()

            with self.assertRaisesRegex(ValueError, "unsafe sdist member path"):
                normalize_sdist(path)

            self.assertEqual(path.read_bytes(), before)

    def test_distribution_directory_comparison_binds_both_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            for directory in (first, second):
                (directory / "pheroos-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
                (directory / "pheroos-0.1.0.tar.gz").write_bytes(b"sdist")

            hashes = compare_distribution_directories(first, second)
            self.assertEqual(len(hashes), 2)

            (second / "pheroos-0.1.0.tar.gz").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "not reproducible"):
                compare_distribution_directories(first, second)


if __name__ == "__main__":
    unittest.main()
