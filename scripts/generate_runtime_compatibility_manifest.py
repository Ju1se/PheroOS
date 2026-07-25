#!/usr/bin/env python3
"""Generate or verify the canonical runtime compatibility v1 artifact."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pheroos.conformance.runtime_compatibility import (  # noqa: E402
    build_runtime_compatibility_manifest_v1,
)


ARTIFACT = ROOT / "pheroos/conformance/abi/runtime-compatibility-v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    manifest = build_runtime_compatibility_manifest_v1()
    expected = manifest.canonical_bytes()
    if args.write:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_bytes(expected)
        print(
            "wrote pheroos/conformance/abi/runtime-compatibility-v1.json "
            f"root={manifest.manifest_root} digest={manifest.artifact_digest}"
        )
        return 0
    try:
        observed = ARTIFACT.read_bytes()
    except FileNotFoundError:
        print("missing pheroos/conformance/abi/runtime-compatibility-v1.json")
        return 1
    if observed != expected:
        print(
            "stale pheroos/conformance/abi/runtime-compatibility-v1.json; "
            "run scripts/generate_runtime_compatibility_manifest.py --write"
        )
        return 1
    print(
        "verified pheroos/conformance/abi/runtime-compatibility-v1.json "
        f"root={manifest.manifest_root} digest={manifest.artifact_digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
