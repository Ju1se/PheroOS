#!/usr/bin/env python3
"""Generate strict v2 schemas and verify all frozen v1 schema roots."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pheroos.drivers.schema import driver_schema, driver_schema_v2  # noqa: E402
from pheroos.kernel.schema import kernel_schema, kernel_schema_v2  # noqa: E402
from pheroos.protocol.schema import (  # noqa: E402
    capability_schema,
    capability_schema_v2,
    protocol_schema,
    protocol_schema_v2,
)


_FROZEN_V1_ROOTS = {
    "schemas/capability.schema.json": (
        "5d3a88ed54d9acf83813713abec493ebb85e245cd6766de9fffa03351cdb62cf"
    ),
    "schemas/protocol.schema.json": (
        "1abc0b228c72fc05f8ec6272d327d9c06ca3e3a7e37ea2487ccfeff60c86cdb6"
    ),
    "schemas/driver.schema.json": (
        "44171e85e1076231d9120f67abafcf521748ccbb8932a805df12c43823587fbd"
    ),
    "schemas/kernel.schema.json": (
        "da2e2001a61c19d2726bc96ef05392e1acb8618c6bb6a3dfb233bcc0398e0822"
    ),
}
_SCHEMAS: tuple[tuple[str, Callable[[], dict[str, Any]], bool], ...] = (
    ("schemas/capability.schema.json", capability_schema, True),
    ("schemas/capability-v2.schema.json", capability_schema_v2, False),
    ("schemas/protocol.schema.json", protocol_schema, True),
    ("schemas/protocol-v2.schema.json", protocol_schema_v2, False),
    ("schemas/driver.schema.json", driver_schema, True),
    ("schemas/driver-v2.schema.json", driver_schema_v2, False),
    ("schemas/kernel.schema.json", kernel_schema, True),
    ("schemas/kernel-v2.schema.json", kernel_schema_v2, False),
)


def _render(factory: Callable[[], dict[str, Any]]) -> bytes:
    return (json.dumps(factory(), indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help="write v2 artifacts; frozen v1 artifacts are verification-only",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify generator parity and immutable v1 roots",
    )
    args = parser.parse_args()

    failed = False
    for relative, factory, frozen in _SCHEMAS:
        path = ROOT / relative
        expected = _render(factory)
        if frozen:
            expected_root = _FROZEN_V1_ROOTS[relative]
            if sha256(expected).hexdigest() != expected_root:
                print(f"generator drifted from frozen v1 root: {relative}")
                failed = True
                continue
        if args.write and not frozen:
            path.write_bytes(expected)
            print(f"wrote {relative}")
            continue
        try:
            observed = path.read_bytes()
        except FileNotFoundError:
            print(f"missing {relative}")
            failed = True
            continue
        if observed != expected:
            print(f"stale {relative}")
            failed = True
            continue
        if frozen and sha256(observed).hexdigest() != _FROZEN_V1_ROOTS[relative]:
            print(f"frozen v1 root changed: {relative}")
            failed = True
            continue
        print(f"verified {relative}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
