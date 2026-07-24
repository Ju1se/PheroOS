#!/usr/bin/env python3
"""Generate or verify checked public ABI shape and lifecycle artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pheroos.conformance.public_api_inventory import (  # noqa: E402
    PUBLIC_API_INVENTORY_PATH,
    build_public_api_inventory,
    render_public_api_inventory,
)
from pheroos.conformance.public_api_lifecycle import (  # noqa: E402
    PUBLIC_API_LIFECYCLE_PATH,
    build_public_api_lifecycle,
    render_public_api_lifecycle,
)


ARTIFACT = ROOT / PUBLIC_API_INVENTORY_PATH
LIFECYCLE_ARTIFACT = ROOT / PUBLIC_API_LIFECYCLE_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help="replace the checked artifact with the current public ABI",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked artifact does not match the current public ABI",
    )
    args = parser.parse_args()

    rendered = render_public_api_inventory(build_public_api_inventory())
    lifecycle_rendered = render_public_api_lifecycle(build_public_api_lifecycle(ROOT))
    if args.write:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_bytes(rendered.encode("utf-8"))
        print(f"wrote {ARTIFACT.relative_to(ROOT)}")
        LIFECYCLE_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        LIFECYCLE_ARTIFACT.write_bytes(lifecycle_rendered.encode("utf-8"))
        print(f"wrote {LIFECYCLE_ARTIFACT.relative_to(ROOT)}")
        return 0

    stale = False
    for artifact, observed in (
        (ARTIFACT, rendered),
        (LIFECYCLE_ARTIFACT, lifecycle_rendered),
    ):
        try:
            checked = artifact.read_bytes().decode("utf-8")
        except FileNotFoundError:
            print(f"missing {artifact.relative_to(ROOT)}")
            stale = True
            continue
        if checked != observed:
            print(
                f"stale {artifact.relative_to(ROOT)}; "
                "run scripts/generate_public_api_inventory.py --write"
            )
            stale = True
            continue
        print(f"verified {artifact.relative_to(ROOT)}")
    return int(stale)


if __name__ == "__main__":
    raise SystemExit(main())
