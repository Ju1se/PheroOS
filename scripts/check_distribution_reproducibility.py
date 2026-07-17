#!/usr/bin/env python3
"""Compare two wheel/sdist directories by filename and SHA-256."""

from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path


def distribution_hashes(directory: Path) -> dict[str, str]:
    artifacts = sorted(
        path
        for path in directory.iterdir()
        if path.is_file()
        and (path.suffix == ".whl" or path.name.endswith(".tar.gz"))
    )
    kinds = {
        "wheel": [path for path in artifacts if path.suffix == ".whl"],
        "sdist": [path for path in artifacts if path.name.endswith(".tar.gz")],
    }
    for kind, paths in kinds.items():
        if len(paths) != 1:
            raise ValueError(
                f"expected exactly one {kind} in {directory}, found {len(paths)}"
            )
    return {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in artifacts
    }


def compare_distribution_directories(first: Path, second: Path) -> dict[str, str]:
    first_hashes = distribution_hashes(first)
    second_hashes = distribution_hashes(second)
    if first_hashes != second_hashes:
        names = sorted(set(first_hashes) | set(second_hashes))
        differences = [
            f"{name}: {first_hashes.get(name, '<missing>')} != "
            f"{second_hashes.get(name, '<missing>')}"
            for name in names
            if first_hashes.get(name) != second_hashes.get(name)
        ]
        raise ValueError("distribution bytes are not reproducible: " + "; ".join(differences))
    return first_hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    try:
        hashes = compare_distribution_directories(args.first, args.second)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    for name, digest in hashes.items():
        print(f"{digest}  {name}")
    print("wheel and sdist bytes are reproducible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
