"""R0 instrument-only measurements; no treatment verdict or E3 reinterpretation.

The independent unit is a declared (cell, world), with repetitions averaged
within that world. Existing E3 arithmetic is reused with an explicit mean;
E3's record validator, gates and flat-cell rejection are not invoked.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
from statistics import fmean

from .e3_verdict import paired_item_differences, paired_percentile_ci

METHOD = "r_paired_world_mean_v1"
CONFIG_FIELDS = {
    "method_version",
    "phase",
    "arms",
    "world_ids",
    "repetitions",
    "cost_unit",
    "budget_cap",
    "confidence",
    "bootstrap_resamples",
    "seed",
}
ROW_FIELDS = {
    "record_version",
    "phase",
    "cell",
    "world_id",
    "repetition",
    "arm",
    "outcome",
    "cost",
    "unknown_cost_units",
}
OUTCOMES = {"success", "failed", "timeout", "rejected", "cancelled"}


def _require(condition: bool, reason: str):
    if not condition:
        raise ValueError(reason)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _identities(values):
    return (
        isinstance(values, list)
        and bool(values)
        and all(type(x) is str and bool(x.strip()) for x in values)
        and len(set(values)) == len(values)
    )


def _validate(rows, config):
    _require(
        type(config) is dict and set(config) == CONFIG_FIELDS, "invalid_config_fields"
    )
    _require(config["method_version"] == METHOD, "unsupported_method_version")
    _require(config["phase"] == "instrument_check", "unsupported_phase")
    _require(
        _identities(config["arms"]) and len(config["arms"]) == 2,
        "two_distinct_arms_required",
    )
    _require(config["cost_unit"] == "call_units", "unsupported_cost_unit")
    for field in ("repetitions", "budget_cap", "bootstrap_resamples"):
        _require(_integer(config[field], 1), f"invalid_{field}")
    _require(_integer(config["seed"]), "invalid_seed")
    confidence = config["confidence"]
    _require(
        type(confidence) in (int, float)
        and math.isfinite(confidence)
        and 0 < confidence < 1,
        "invalid_confidence",
    )
    cells = config["world_ids"]
    _require(type(cells) is dict and bool(cells), "invalid_world_ids")
    for cell, worlds in cells.items():
        _require(
            type(cell) is str and bool(cell.strip()) and _identities(worlds),
            "invalid_world_ids",
        )
    expected = {
        (cell, world, repetition, arm)
        for cell, worlds in cells.items()
        for world in worlds
        for repetition in range(config["repetitions"])
        for arm in config["arms"]
    }
    _require(type(rows) is list, "records_must_be_list")
    observed = set()
    normalized = []
    for row in rows:
        _require(type(row) is dict and set(row) == ROW_FIELDS, "invalid_record_fields")
        _require(
            row["record_version"] == "r_episode_v1" and row["phase"] == config["phase"],
            "record_version_or_phase_mismatch",
        )
        _require(
            all(type(row[k]) is str for k in ("cell", "world_id", "arm", "outcome")),
            "invalid_record_identity",
        )
        _require(_integer(row["repetition"]), "invalid_repetition")
        key = (row["cell"], row["world_id"], row["repetition"], row["arm"])
        _require(key in expected, "undeclared_episode")
        _require(key not in observed, "duplicate_episode")
        _require(row["outcome"] in OUTCOMES, "invalid_outcome")
        _require(
            _integer(row["cost"]) and _integer(row["unknown_cost_units"]),
            "invalid_accounting",
        )
        observed.add(key)
        normalized.append(
            {
                **row,
                "item_id": row["world_id"],
                "quality": int(row["outcome"] == "success"),
            }
        )
    _require(observed == expected, "incomplete_episode_grid")
    return sorted(
        normalized, key=lambda r: (r["cell"], r["world_id"], r["repetition"], r["arm"])
    )


def _paired(rows, config, metric):
    control, candidate = config["arms"]
    differences = paired_item_differences(rows, candidate, control, metric=metric)
    strata = [cell for cell, _ in sorted({(r["cell"], r["world_id"]) for r in rows})]
    low, high = paired_percentile_ci(
        differences,
        statistic="mean",
        confidence=config["confidence"],
        resamples=config["bootstrap_resamples"],
        seed=config["seed"],
        strata=strata,
    )
    return {
        "mean": fmean(differences),
        "ci_low": low,
        "ci_high": high,
        "ci_status": "INSUFFICIENT_RESOLUTION"
        if math.isclose(low, high, abs_tol=1e-12, rel_tol=0)
        else "OK",
        "n_worlds": len(differences),
    }


def analyze(rows, config) -> dict:
    """Return valid diagnostics or INVALID_ABORT; never infer treatment efficacy."""
    base = {"method_version": METHOD, "counts_toward_verdict": False}
    try:
        selected = _validate(rows, config)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {**base, "status": "INVALID_ABORT", "reason": str(exc)}
    groups = defaultdict(list)
    for row in selected:
        groups[(row["cell"], row["arm"])].append(row)
    totals = [
        {
            "cell": cell,
            "arm": arm,
            "n_episodes": len(values),
            "quality_mean": fmean(r["quality"] for r in values),
            "cost_total": sum(r["cost"] for r in values),
            "unknown_cost_units": sum(r["unknown_cost_units"] for r in values),
            "budget_exceeded_episodes": sum(
                r["cost"] > config["budget_cap"] for r in values
            ),
            "outcomes": {
                status: sum(r["outcome"] == status for r in values)
                for status in sorted(OUTCOMES)
            },
        }
        for (cell, arm), values in sorted(groups.items())
    ]
    if any(r["unknown_cost_units"] for r in selected):
        return {
            **base,
            "status": "INVALID_ABORT",
            "reason": "unknown_cost",
            "accounting": totals,
        }
    try:
        quality = _paired(selected, config, "quality")
        cost = _paired(selected, config, "cost")
    except (ValueError, OverflowError) as exc:
        return {
            **base,
            "status": "INVALID_ABORT",
            "reason": f"unrepresentable_measurement:{exc}",
            "accounting": totals,
        }
    return {
        **base,
        "status": "VALID_MEASUREMENT",
        "phase": "instrument_check",
        "contrast": {"candidate": config["arms"][1], "control": config["arms"][0]},
        "n_worlds": sum(len(worlds) for worlds in config["world_ids"].values()),
        "n_episodes": len(selected),
        "confidence": config["confidence"],
        "bootstrap_resamples": config["bootstrap_resamples"],
        "seed": config["seed"],
        "repetitions": config["repetitions"],
        "weighting": "equal_world; repetitions averaged; cells stratified with declared world counts",
        "interval": "two_sided_paired_world_percentile",
        "cost_unit": config["cost_unit"],
        "quality": quality,
        "cost": cost,
        "by_cell_arm": totals,
    }


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _load(value: str):
    return json.loads(value, object_pairs_hook=_strict_object)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="R0 instrument-only paired-world measurements"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = _load(args.config.read_text(encoding="utf-8"))
        rows = [
            _load(line)
            for line in args.records.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        result = analyze(rows, config)
    except (ValueError, OSError, TypeError) as exc:
        result = {
            "method_version": METHOD,
            "status": "INVALID_ABORT",
            "counts_toward_verdict": False,
            "reason": str(exc),
        }
    # Exclusive creation preserves previous diagnostics, including failed runs.
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 2 if result["status"] == "INVALID_ABORT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
