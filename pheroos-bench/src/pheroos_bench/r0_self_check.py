"""Declared synthetic R0 checks. No mechanism, provider or confirmatory verdict."""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import random

from .r0_measurement import METHOD, _load, analyze


def fixture(pairs, repetitions=1, cells=("synthetic",)):
    config = {
        "method_version": METHOD,
        "phase": "instrument_check",
        "arms": ["control", "candidate"],
        # Fixed width preserves the independent diagnostic's numerical order
        # under the analyzer's canonical lexical world ordering.
        "world_ids": {cell: [f"w{i:04d}" for i in range(len(pairs))] for cell in cells},
        "repetitions": repetitions,
        "cost_unit": "call_units",
        "budget_cap": 26,
        "confidence": 0.95,
        "bootstrap_resamples": 10000,
        "seed": 37,
    }
    rows = [
        {
            "record_version": "r_episode_v1",
            "phase": "instrument_check",
            "cell": cell,
            "world_id": f"w{i:04d}",
            "repetition": rep,
            "arm": arm,
            "outcome": "success" if pair[j] else "failed",
            "cost": 1,
            "unknown_cost_units": 0,
        }
        for cell in cells
        for i, pair in enumerate(pairs)
        for rep in range(repetitions)
        for j, arm in enumerate(config["arms"])
    ]
    return config, rows


def self_check() -> dict:
    config, rows = fixture([(0, 1)] * 30 + [(1, 0)] * 5 + [(0, 0)] * 65)
    positive = analyze(rows, config)
    identical_config, identical_rows = fixture([(i % 2, i % 2) for i in range(20)])
    sparse_config, sparse_rows = fixture([(0, 0)] * 60, repetitions=3)
    for row in sparse_rows:
        if (
            row["arm"] == "candidate"
            and row["world_id"] in ("w0000", "w0001")
            and row["repetition"] == 0
        ):
            row["outcome"] = "success"
    flat_config, flat_rows = fixture([(0, 0), (1, 1)] * 10, cells=("a", "b"))
    shuffled = deepcopy(rows)
    random.Random(19).shuffle(shuffled)
    unknown = deepcopy(rows)
    unknown[0]["unknown_cost_units"] = 1
    constant_config, constant_rows = fixture([(0, 1)] * 20)
    negative_config, negative_rows = fixture(
        [(1, 0)] * 30 + [(0, 1)] * 5 + [(0, 0)] * 65
    )
    checks = {
        "known_positive": positive,
        "known_negative": analyze(negative_rows, negative_config),
        "identical_arms": analyze(identical_rows, identical_config),
        "sparse_two_of_180": analyze(sparse_rows, sparse_config),
        "legal_flat_cells": analyze(flat_rows, flat_config),
        "constant_positive_difference": analyze(constant_rows, constant_config),
        "missing_episode": analyze(rows[:-1], config),
        "duplicate_episode": analyze(rows + rows[:1], config),
        "unknown_cost": analyze(unknown, config),
    }
    # Independent counterexample values, not thresholds fitted to outcomes.
    invariants = {
        "known_mean": positive["quality"]["mean"] == 0.25,
        "known_interval": (
            positive["quality"]["ci_low"],
            positive["quality"]["ci_high"],
        )
        == (0.15, 0.35),
        "negative_control": checks["known_negative"]["quality"]["mean"] == -0.25
        and checks["known_negative"]["quality"]["ci_high"] < 0,
        "identical_no_advantage": checks["identical_arms"]["quality"]["mean"] == 0,
        # Per-world averaging and the exact rational reference can differ by
        # one floating-point ULP. This numerical tolerance is not an effect gate.
        "sparse_mean": math.isclose(
            checks["sparse_two_of_180"]["quality"]["mean"],
            2 / 180,
            rel_tol=0,
            abs_tol=1e-15,
        ),
        "worlds_not_episodes": checks["sparse_two_of_180"]["n_worlds"] == 60,
        "flat_cells_valid": checks["legal_flat_cells"]["status"] == "VALID_MEASUREMENT",
        "zero_width_disclosed": checks["constant_positive_difference"]["quality"][
            "ci_status"
        ]
        == "INSUFFICIENT_RESOLUTION",
        "shuffle_invariant": analyze(shuffled, config) == positive,
        "invalid_inputs_abort": all(
            checks[k]["status"] == "INVALID_ABORT"
            for k in ("missing_episode", "duplicate_episode", "unknown_cost")
        ),
    }
    return {
        "status": "R0_INSTRUMENT_CHECKS_PASSED"
        if all(invariants.values())
        else "R0_INSTRUMENT_CHECKS_FAILED",
        "counts_toward_verdict": False,
        "invariants": invariants,
        "checks": checks,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-snapshot", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    report = self_check()
    from .r0_runtime import reconcile_snapshot

    report["runtime_snapshots"] = []
    for path in args.runtime_snapshot:
        raw = None
        try:
            raw = path.read_bytes()
            reconciled = reconcile_snapshot(_load(raw.decode("utf-8")))
        except (ValueError, OSError, UnicodeError) as exc:
            reconciled = {
                "validation_status": "INVALID_ABORT",
                "diagnostics": [str(exc)],
            }
        report["runtime_snapshots"].append(
            {
                "input_name": path.name,
                "sha256": sha256(raw).hexdigest() if raw is not None else None,
                "reconciliation": reconciled,
            }
        )
        if reconciled["validation_status"] != "VALID":
            report["status"] = "R0_INSTRUMENT_CHECKS_FAILED"
    package = Path(__file__).parent
    report["implementation_sha256"] = {
        name: sha256((package / name).read_bytes()).hexdigest()
        for name in (
            "e3_verdict.py",
            "r0_measurement.py",
            "r0_runtime.py",
            "r0_self_check.py",
        )
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
        output.write("\n")
    print(
        json.dumps({"status": report["status"], "output": str(args.output)}, indent=2)
    )
    return 0 if report["status"] == "R0_INSTRUMENT_CHECKS_PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
