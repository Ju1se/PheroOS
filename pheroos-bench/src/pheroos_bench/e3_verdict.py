"""Pre-registered E3 admission and verdict calculations.

This module is deliberately provider-free.  The runner that produces raw LLM
records lives outside this statistical boundary; records only need an item,
arm, repetition, exact-match quality, and accounting fields.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable


def _as_float(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("measurement must be a finite number")
    return float(value)


def _positive_int(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("a calibrated positive integer is required")
    return value


def _static_arms(config: dict[str, Any], *, admission_only: bool = False) -> list[str]:
    sizes = config["arms"]["static_homog"]["N"]
    if not isinstance(sizes, list) or not sizes:
        raise ValueError("static_homog.N must be a calibrated nonempty list")
    sizes = [_positive_int(n) for n in sizes]
    if len(set(sizes)) != len(sizes):
        raise ValueError("static N values must be distinct")
    if admission_only:
        return [f"static_homog@{max(sizes)}"]
    diverse = config["arms"]["static_diverse"]["N"]
    if diverse != "same set as static_homog" and diverse != sizes:
        raise ValueError("static arms must use the same N values")
    return sorted(
        f"{arm}@{n}" for arm in ("static_homog", "static_diverse") for n in sizes
    )


def _has_pilot_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().startswith("PILOT")
    if isinstance(value, dict):
        return any(_has_pilot_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_pilot_placeholder(v) for v in value)
    return False


def _validate_records(
    rows: list[dict[str, Any]], config: dict[str, Any], *, phase: str
) -> list[str]:
    """Check the declared experiment grid before looking at any outcome."""
    confirmatory = phase == "confirmatory"
    if confirmatory and (
        config.get("status") != "frozen" or _has_pilot_placeholder(config)
    ):
        raise ValueError(
            "confirmatory config must be frozen with no PILOT placeholders"
        )
    try:
        static = _static_arms(config, admission_only=not confirmatory)
        arms = static + (
            ["adaptive_K", "adaptive_random"] if confirmatory else ["single"]
        )
        if confirmatory and "single" in config["arms"]:
            arms.append("single")
        items = config["task"]["item_ids"]
        repetitions = _positive_int(
            config["statistics"]["repetitions_per_item_per_arm"]
        )
        model = config["model"]["provider_model_string"]
        unit = config["budget"]["unit"]
        cap = _as_float(config["budget"]["cap_per_item"])
    except (KeyError, TypeError) as exc:
        raise ValueError("missing calibrated experiment/data-contract field") from exc
    if unit not in ("tokens", "dollars") or cap <= 0:
        raise ValueError("budget needs an explicit unit and positive cap")
    if not isinstance(model, str) or not model or model.startswith("PILOT"):
        raise ValueError("the exact model must be declared")
    if not isinstance(items, dict) or not items:
        raise ValueError("task.item_ids must declare the item IDs in each benchmark")
    item_keys: set[tuple[str, str]] = set()
    for cell, ids in items.items():
        if (
            not isinstance(cell, str)
            or not cell
            or not isinstance(ids, list)
            or not ids
        ):
            raise ValueError("benchmark and item lists must be nonempty")
        if any(not isinstance(item, str) or not item for item in ids) or len(
            set(ids)
        ) != len(ids):
            raise ValueError("item IDs must be distinct nonempty strings per benchmark")
        item_keys.update((cell, item) for item in ids)
    expected = {
        (cell, item, rep, arm)
        for cell, item in item_keys
        for rep in range(repetitions)
        for arm in arms
    }
    observed: set[tuple[str, str, int, str]] = set()
    for row in rows:
        try:
            key = (row["cell"], row["item_id"], row["repetition"], row["arm"])
            quality, spent = _as_float(row["quality"]), _as_float(row[unit])
            if type(key[2]) is not int or key not in expected or key in observed:
                raise ValueError(
                    "duplicate or undeclared benchmark/item/repetition/arm"
                )
            if not 0 <= quality <= 1 or not 0 <= spent <= cap:
                raise ValueError("quality is out of range or budget is exceeded")
            if unit == "tokens" and type(row[unit]) is not int:
                raise ValueError("token accounting must be a known nonnegative integer")
            if row["model"] != model:
                raise ValueError("model version drifted")
            if (
                row["phase"] != phase
                or row["counts_toward_verdict"] is not confirmatory
            ):
                raise ValueError(
                    "pilot/admission records cannot enter the confirmatory verdict"
                )
        except (KeyError, TypeError) as exc:
            raise ValueError("malformed or incomplete experiment record") from exc
        observed.add(key)
    if observed != expected:
        raise ValueError(
            f"incomplete experiment grid: missing {len(expected - observed)} records"
        )
    return static


def _item_arm_means(
    rows: Iterable[dict[str, Any]],
    *,
    arm: str,
    metric: str = "quality",
) -> dict[tuple[str, str], float]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if str(row["arm"]) == arm:
            grouped[(str(row["cell"]), str(row["item_id"]))].append(
                _as_float(row[metric])
            )
    return {item_id: sum(values) / len(values) for item_id, values in grouped.items()}


def paired_item_differences(
    rows: Iterable[dict[str, Any]], arm_a: str, arm_b: str, metric: str = "quality"
) -> list[float]:
    """Return per-item mean(a) - mean(b), paired before bootstrap."""

    rows = list(rows)
    a = _item_arm_means(rows, arm=arm_a, metric=metric)
    b = _item_arm_means(rows, arm=arm_b, metric=metric)
    if a.keys() != b.keys():
        raise ValueError("paired arms have different benchmark/item sets")
    common = sorted(a)
    if not common:
        raise ValueError(f"no paired items for {arm_a!r} and {arm_b!r}")
    return [a[item_id] - b[item_id] for item_id in common]


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot take a percentile of an empty sample")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    ordered = sorted(values)
    index = probability * (len(ordered) - 1)
    lo = int(index)
    hi = min(lo + 1, len(ordered) - 1)
    weight = index - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def paired_percentile_ci(
    differences: list[float],
    *,
    confidence: float = 0.95,
    resamples: int = 10_000,
    seed: int = 37,
) -> tuple[float, float]:
    """Percentile bootstrap CI over already-paired item differences."""

    if not differences:
        raise ValueError("cannot bootstrap an empty sample")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        draw = [differences[rng.randrange(len(differences))] for _ in differences]
        estimates.append(median(draw))
    alpha = (1.0 - confidence) / 2.0
    return percentile(estimates, alpha), percentile(estimates, 1.0 - alpha)


def _metric_variance_by_arm_across_cells(
    rows: list[dict[str, Any]], metric: str
) -> dict[str, float]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cell = str(row.get("cell", row.get("benchmark", "default")))
        grouped[str(row["arm"])][cell].append(_as_float(row[metric]))
    result: dict[str, float] = {}
    for arm, cells in grouped.items():
        cell_means = [sum(values) / len(values) for values in cells.values()]
        if len(cell_means) < 2:
            raise ValueError(f"insensitivity check needs at least two cells for {arm}")
        mean = sum(cell_means) / len(cell_means)
        result[arm] = sum((value - mean) ** 2 for value in cell_means) / len(cell_means)
    return result


def assert_nonzero_cell_variance(
    rows: list[dict[str, Any]], metric: str = "quality"
) -> None:
    """Reject a flat arm/cell metric; flat controls are a broken instrument."""

    variances = _metric_variance_by_arm_across_cells(rows, metric)
    flat = sorted(arm for arm, variance in variances.items() if variance <= 0.0)
    if flat:
        raise ValueError("flat arm metric across cells detected: " + ", ".join(flat))


def _ci_payload(
    differences: list[float], *, seed: int, config: dict[str, Any]
) -> dict[str, Any]:
    statistics = config.get("statistics", {})
    confidence = float(statistics.get("confidence", 0.95))
    resamples = int(statistics.get("bootstrap_resamples", 10_000))
    lo, hi = paired_percentile_ci(
        differences, confidence=confidence, resamples=resamples, seed=seed
    )
    return {
        "n_items": len(differences),
        "median": median(differences),
        "ci_low": lo,
        "ci_high": hi,
        "ci_halfwidth": (hi - lo) / 2.0,
    }


def admission(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Run the unchanged admission gate separately for every benchmark."""
    static_arm = _validate_records(rows, config, phase="admission")[0]
    if config["admission"]["arms_run"] not in (
        ["single", "static_homog at max N"],
        ["single", static_arm],
    ):
        raise ValueError("admission must run single and static_homog at max N")
    cells = {}
    for cell in sorted(config["task"]["item_ids"]):
        selected = [row for row in rows if row["cell"] == cell]
        differences = paired_item_differences(selected, static_arm, "single")
        ci = _ci_payload(differences, seed=10_301, config=config)
        static_median = median(_item_arm_means(selected, arm=static_arm).values())
        single_median = median(_item_arm_means(selected, arm="single").values())
        gap = static_median - single_median
        passed = gap > 10.0 * ci["ci_halfwidth"]
        cells[cell] = {
            "status": "PASS_ADMISSION" if passed else "FAIL_ADMISSION",
            "paired": ci,
            "static_median": static_median,
            "single_median": single_median,
            "median_gap": gap,
        }
    if any(cell["status"] != "PASS_ADMISSION" for cell in cells.values()):
        raise SystemExit(1)
    return {
        "status": "PASS_ADMISSION",
        "arms": ["single", static_arm],
        "cells": cells,
        "treatment_executed": False,
        "rule": "median(static_quality) - median(single_quality) > 10 * ci_halfwidth(paired_diff)",
    }


def verdict(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate E3 primary, co-primary, and quality-floor gates."""

    static_arms = _validate_records(rows, config, phase="confirmatory")
    assert_nonzero_cell_variance(rows)
    treatment = {str(row["arm"]) for row in rows}
    required = {"adaptive_K", "adaptive_random"}
    if not required <= treatment:
        raise ValueError(
            "treatment records must include adaptive_K and adaptive_random"
        )
    primary_differences = paired_item_differences(rows, "adaptive_K", "adaptive_random")
    primary = _ci_payload(primary_differences, seed=10_401, config=config)

    co_primary: dict[str, Any] = {}
    for index, arm in enumerate(static_arms):
        co_primary[arm] = _ci_payload(
            paired_item_differences(rows, "adaptive_K", arm),
            seed=10_500 + index,
            config=config,
        )
    adaptive_quality = _item_arm_means(rows, arm="adaptive_K")
    floor = _as_float(config["endpoints"]["quality_floor"])
    if not 0 <= floor <= 1:
        raise ValueError("quality floor must be in [0, 1]")
    floor_pass = median(list(adaptive_quality.values())) >= floor
    primary_pass = primary["ci_low"] > 0.0
    co_primary_pass = bool(co_primary) and all(
        result["ci_low"] > 0.0 for result in co_primary.values()
    )
    passed = primary_pass and co_primary_pass and floor_pass
    secondary = {}
    if "single" in config["arms"]:
        secondary["adaptive_K_vs_single"] = _ci_payload(
            paired_item_differences(rows, "adaptive_K", "single"),
            seed=10_601,
            config=config,
        )
    return {
        "status": "PASS" if passed else "FAIL",
        "primary": primary,
        "co_primary": co_primary,
        "secondary": secondary,
        "quality_floor": {
            "median": median(list(adaptive_quality.values())),
            "floor": floor,
            "pass": floor_pass,
        },
        "counts_toward_verdict": True,
    }


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the preregistered E3 statistics"
    )
    parser.add_argument("--phase", choices=("admission", "verdict"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    rows = _load_rows(args.input)
    result = (
        admission(rows, config) if args.phase == "admission" else verdict(rows, config)
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
