#!/usr/bin/env python3
"""Verify and restore byte-preserved publication_evidence_v1 tar.xz archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import tarfile


class EvidenceError(ValueError):
    """The manifest, stored bytes, or destination failed verification."""


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise EvidenceError(f"Invalid relative path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or any(part in (".", "..") or ":" in part for part in path.parts)
        or value == "."
    ):
        raise EvidenceError(f"Unsafe or noncanonical relative path: {value!r}")
    return value


def _safe_path(root: Path, relative: str) -> Path:
    current = root
    for part in PurePosixPath(_relative(relative)).parts:
        current = current / part
        if current.is_symlink():
            raise EvidenceError(f"Symlink destination is forbidden: {relative}")
    if not current.resolve().is_relative_to(root):
        raise EvidenceError(f"Path escapes root: {relative}")
    return current


def _digest_record(record: dict) -> None:
    if not isinstance(record.get("sha256"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", record["sha256"]
    ):
        raise EvidenceError(f"Invalid SHA-256 for {record.get('path')!r}")
    if type(record.get("size_bytes")) is not int or record["size_bytes"] < 0:
        raise EvidenceError(f"Invalid size_bytes for {record.get('path')!r}")


def _check_stream(stream, record: dict, output=None) -> None:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        if size > record["size_bytes"]:
            raise EvidenceError(f"Size exceeds manifest: {record['path']}")
        digest.update(chunk)
        if output is not None:
            output.write(chunk)
    if size != record["size_bytes"] or digest.hexdigest() != record["sha256"]:
        raise EvidenceError(f"Hash or size mismatch: {record['path']}")


def _check_file(root: Path, record: dict) -> bool:
    path = _safe_path(root, record["path"])
    if not path.exists():
        return False
    if not path.is_file():
        raise EvidenceError(f"Expected a regular file: {record['path']}")
    with path.open("rb") as stream:
        _check_stream(stream, record)
    return True


def _load_manifest(path: Path) -> tuple[list[dict], dict[str, dict]]:
    # Reject duplicate JSON keys so no parser-dependent declaration can hide.
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    manifest = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(manifest, dict) or manifest.get("version") != "publication_evidence_v1":
        raise EvidenceError("Expected publication_evidence_v1 manifest")
    if manifest.get("counts_toward_verdict") is not False:
        raise EvidenceError("Publication packaging must not count toward a verdict")
    if not isinstance(manifest.get("repository"), str) or not manifest["repository"]:
        raise EvidenceError("Missing repository identity")
    if not isinstance(manifest.get("base_commit"), str) or not re.fullmatch(
        r"[0-9a-f]{40}", manifest["base_commit"]
    ):
        raise EvidenceError("Invalid base_commit")
    archives = manifest.get("archives")
    files = manifest.get("files")
    if not isinstance(archives, list) or not isinstance(files, list):
        raise EvidenceError("archives and files must be lists")
    archive_map = {}
    for archive in archives:
        if not isinstance(archive, dict):
            raise EvidenceError("Invalid archive record")
        name = _relative(archive.get("path"))
        _digest_record(archive)
        if name in archive_map:
            raise EvidenceError(f"Duplicate archive declaration: {name}")
        archive_map[name] = archive
    seen = set()
    for record in files:
        if not isinstance(record, dict):
            raise EvidenceError("Invalid file record")
        name = _relative(record.get("path"))
        _digest_record(record)
        if name in seen or name in archive_map:
            raise EvidenceError(f"Duplicate or overlapping file declaration: {name}")
        seen.add(name)
        if record.get("mode", "100644") not in ("100644", "100755"):
            raise EvidenceError(f"Invalid file mode: {name}")
        if record.get("storage") == "archive":
            if record.get("archive") not in archive_map or record.get("member") != name:
                raise EvidenceError(f"Invalid archive/member reference: {name}")
        elif record.get("storage") != "direct" or "archive" in record or "member" in record:
            raise EvidenceError(f"Invalid storage declaration: {name}")
    return files, archive_map


def _members(archive: tarfile.TarFile, expected: dict[str, dict]) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    names = [entry.name for entry in members]
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise EvidenceError("Tar members differ from exact manifest declaration")
    for entry in members:
        _relative(entry.name)
        if not entry.isfile() or entry.sparse is not None:
            raise EvidenceError(f"Nonregular tar member: {entry.name}")
        if entry.size != expected[entry.name]["size_bytes"]:
            raise EvidenceError(f"Tar member size mismatch: {entry.name}")
    return members


def _restore_member(root: Path, record: dict, archive: tarfile.TarFile) -> bool:
    if _check_file(root, record):
        return False
    target = _safe_path(root, record["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _safe_path(root, record["path"])
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".restore-evidence-", dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            with archive.extractfile(record["member"]) as source:
                _check_stream(source, record, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o755 if record.get("mode") == "100755" else 0o644)
        try:
            # Atomic creation without overwriting a file created after validation.
            os.link(temporary, target)
        except FileExistsError:
            if _check_file(root, record):
                return False
            raise EvidenceError(f"Destination changed during restoration: {record['path']}")
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore(manifest_path: Path, root: Path, *, verify_only: bool = False) -> dict:
    """Validate every declared byte before restoring any missing archived file."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise EvidenceError("Root must be an existing directory")
    files, archives = _load_manifest(manifest_path)
    archived = {name: {} for name in archives}
    existing = 0
    direct = 0
    for record in files:
        present = _check_file(root, record)
        existing += int(present)
        if record["storage"] == "direct":
            direct += 1
            if not present:
                raise EvidenceError(f"Missing direct file: {record['path']}")
        else:
            archived[record["archive"]][record["member"]] = record
    for name, record in archives.items():
        if not _check_file(root, record):
            raise EvidenceError(f"Missing archive: {name}")
        with tarfile.open(_safe_path(root, name), mode="r:xz") as archive:
            for member in _members(archive, archived[name]):
                with archive.extractfile(member) as source:
                    _check_stream(source, archived[name][member.name])
    restored = 0
    if not verify_only:
        for name, archive_record in archives.items():
            if not _check_file(root, archive_record):
                raise EvidenceError(f"Archive disappeared during restoration: {name}")
            with tarfile.open(_safe_path(root, name), mode="r:xz") as archive:
                for member in _members(archive, archived[name]):
                    restored += int(_restore_member(root, archived[name][member.name], archive))
    return {
        "version": "publication_evidence_v1",
        "status": "VERIFIED" if verify_only else "RESTORED",
        "counts_toward_verdict": False,
        "archives_verified": len(archives),
        "files_verified": len(files),
        "direct_files": direct,
        "archived_files": len(files) - direct,
        "existing_matching_files": existing,
        "files_restored": restored,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        result = restore(args.manifest, args.root, verify_only=args.verify_only)
    except (EvidenceError, OSError, ValueError, TypeError, KeyError, RuntimeError, EOFError, lzma.LZMAError, tarfile.TarError) as error:
        print(json.dumps({"status": "INVALID_PUBLICATION", "error": str(error), "counts_toward_verdict": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
