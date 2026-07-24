#!/usr/bin/env python3
"""Generate or verify the Draft Stable Python API promotion candidate."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pheroos.conformance.stable_api_candidate import (  # noqa: E402
    STABLE_API_CANDIDATE_PATH,
    build_stable_api_candidate,
    render_stable_api_candidate,
    stable_api_candidate_problems,
)


ARTIFACT = ROOT / STABLE_API_CANDIDATE_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help="replace the checked Draft promotion candidate",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="fail when the checked candidate differs from the public facades",
    )
    args = parser.parse_args()

    candidate = build_stable_api_candidate(ROOT)
    problems = stable_api_candidate_problems(candidate)
    if problems:
        for problem in problems:
            print(f"invalid Stable API candidate: {problem}")
        return 1
    rendered = render_stable_api_candidate(candidate)
    if args.write:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(rendered, encoding="utf-8")
        print(f"wrote {ARTIFACT.relative_to(ROOT)}")
        return 0
    try:
        checked = ARTIFACT.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"missing {ARTIFACT.relative_to(ROOT)}")
        return 1
    if checked != rendered:
        print(
            f"stale {ARTIFACT.relative_to(ROOT)}; "
            "run scripts/generate_stable_api_candidate.py --write"
        )
        return 1
    print(f"verified {ARTIFACT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
