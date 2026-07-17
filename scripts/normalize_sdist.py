#!/usr/bin/env python3
"""Rewrite a Python sdist with deterministic archive metadata."""

from __future__ import annotations

import argparse
from copy import copy
import gzip
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile


RELEASE_SOURCE_DATE_EPOCH = 315532800


def _validate_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe sdist member path: {member.name!r}")
    if not (member.isfile() or member.isdir()):
        raise ValueError(
            f"unsupported sdist member type for deterministic release: {member.name!r}"
        )


def normalize_sdist(
    path: Path,
    *,
    source_date_epoch: int = RELEASE_SOURCE_DATE_EPOCH,
) -> str:
    """Normalize one ``.tar.gz`` in place and return its SHA-256 digest."""

    if source_date_epoch < 0:
        raise ValueError("source_date_epoch must be non-negative")
    if not path.name.endswith(".tar.gz"):
        raise ValueError(f"expected a .tar.gz sdist: {path}")

    temporary_name: str | None = None
    try:
        with tarfile.open(path, mode="r:gz") as source:
            members = source.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise ValueError("sdist contains duplicate member paths")
            for member in members:
                _validate_member(member)

            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as raw_output:
                temporary_name = raw_output.name
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    compresslevel=9,
                    fileobj=raw_output,
                    mtime=source_date_epoch,
                ) as compressed:
                    with tarfile.open(
                        fileobj=compressed,
                        mode="w",
                        format=tarfile.PAX_FORMAT,
                    ) as output:
                        for original in sorted(members, key=lambda item: item.name):
                            member = copy(original)
                            member.uid = 0
                            member.gid = 0
                            member.uname = ""
                            member.gname = ""
                            member.mtime = source_date_epoch
                            member.pax_headers = {
                                key: value
                                for key, value in member.pax_headers.items()
                                if key
                                not in {
                                    "atime",
                                    "ctime",
                                    "gid",
                                    "gname",
                                    "mtime",
                                    "uid",
                                    "uname",
                                }
                            }
                            payload = (
                                source.extractfile(original)
                                if original.isfile()
                                else None
                            )
                            if original.isfile() and payload is None:
                                raise ValueError(
                                    f"cannot read sdist member: {original.name!r}"
                                )
                            try:
                                output.addfile(member, payload)
                            finally:
                                if payload is not None:
                                    payload.close()

        if temporary_name is None:
            raise RuntimeError("normalizer did not create an output archive")
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
        temporary_name = None
        return sha256(path.read_bytes()).hexdigest()
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sdists", nargs="+", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=RELEASE_SOURCE_DATE_EPOCH,
    )
    args = parser.parse_args()
    for sdist in args.sdists:
        digest = normalize_sdist(
            sdist,
            source_date_epoch=args.source_date_epoch,
        )
        print(f"{digest}  {sdist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
