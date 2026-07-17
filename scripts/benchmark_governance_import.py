#!/usr/bin/env python3
"""Measure the cold import cost of the Governance public facade."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_COUNT = 9
GOVERNANCE_IMPORT_BUDGET_MS = 120.0
_CHILD = """
import json
import sys
from time import perf_counter_ns

started = perf_counter_ns()
import pheroos.governance as governance
elapsed_ms = (perf_counter_ns() - started) / 1_000_000

print(json.dumps({
    "elapsed_ms": elapsed_ms,
    "loaded_pheroos_modules": sorted(
        name
        for name in sys.modules
        if name == "pheroos" or name.startswith("pheroos.")
    ),
    "cached_public_exports": sorted(
        name for name in governance.__all__ if name in governance.__dict__
    ),
    "public_export_count": len(governance.__all__),
}))
"""


def benchmark_governance_import(
    *,
    samples: int = DEFAULT_SAMPLE_COUNT,
    python: str = sys.executable,
) -> dict[str, Any]:
    """Return cold-process import observations and aggregate timings."""

    if samples < 1:
        raise ValueError("samples must be positive")
    observations: list[dict[str, Any]] = []
    for _ in range(samples):
        completed = subprocess.run(
            [python, "-c", _CHILD],
            check=True,
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        observation = json.loads(completed.stdout)
        if not isinstance(observation, dict):
            raise ValueError("benchmark child returned a malformed observation")
        observations.append(observation)

    elapsed = [float(item["elapsed_ms"]) for item in observations]
    return {
        "budget_ms": GOVERNANCE_IMPORT_BUDGET_MS,
        "max_ms": max(elapsed),
        "median_ms": statistics.median(elapsed),
        "min_ms": min(elapsed),
        "observations": observations,
        "python": python,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLE_COUNT)
    parser.add_argument(
        "--budget-ms",
        type=float,
        default=GOVERNANCE_IMPORT_BUDGET_MS,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the median cold import exceeds the budget",
    )
    args = parser.parse_args()

    result = benchmark_governance_import(samples=args.samples)
    result["budget_ms"] = args.budget_ms
    result["within_budget"] = result["median_ms"] <= args.budget_ms
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.check and not result["within_budget"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
