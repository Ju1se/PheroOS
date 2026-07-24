#!/usr/bin/env python3
"""Generate writeable schemas and verify the closed artifact catalog."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pheroos.conformance.schema_catalog import (  # noqa: E402
    SCHEMA_ARTIFACT_SPECS,
    render_schema_artifact,
    schema_catalog_problems,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help="write only catalog entries explicitly marked writeable",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify catalog closure, exact bytes, IDs, aliases, and frozen roots",
    )
    args = parser.parse_args()

    if args.write:
        blockers = _write_blockers(schema_catalog_problems(ROOT))
        if blockers:
            for problem in blockers:
                print(problem)
            print("refusing to write while the schema catalog is structurally invalid")
            return 1
        for spec in SCHEMA_ARTIFACT_SPECS:
            path = ROOT / spec.path
            expected = render_schema_artifact(spec)
            observed = path.read_bytes() if path.is_file() else None
            if spec.frozen:
                print(f"verified frozen {spec.path}")
                continue
            if observed == expected:
                print(f"verified {spec.path}")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
            print(f"wrote {spec.path}")

    problems = schema_catalog_problems(ROOT)
    if problems:
        for problem in problems:
            print(problem)
        if not args.write:
            print("run scripts/generate_schema_artifacts.py --write")
        return 1
    print(f"verified {len(SCHEMA_ARTIFACT_SPECS)} cataloged schema artifacts")
    return 0


def _write_blockers(problems: tuple[str, ...]) -> tuple[str, ...]:
    writeable = {
        spec.surface: spec for spec in SCHEMA_ARTIFACT_SPECS if not spec.frozen
    }
    writeable_paths = {spec.path for spec in writeable.values()}
    allowed = {
        *(f"bytes:{surface}" for surface in writeable),
        *(f"missing:{path}" for path in writeable_paths),
    }
    return tuple(problem for problem in problems if problem not in allowed)


if __name__ == "__main__":
    raise SystemExit(main())
