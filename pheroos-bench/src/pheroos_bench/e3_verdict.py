"""Pre-registered E3 admission and verdict calculations.

This module is deliberately provider-free.  The runner that produces raw LLM
records lives outside this statistical boundary; records only need an item,
arm, repetition, exact-match quality, and accounting fields.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable


def _as_float(value: Any) -> float:
    return float(value)


def _item_arm_means(
    rows: Iterable[dict[str, Any]],
    *,
    arm: str,
    metric: str = "quality",
) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if str(row["arm"]) == arm:
            grouped[str(row["item_id"])].append(_as_float(row[metric]))
    return {item_id: sum(values) / len(values) for item_id, values in grouped.items()}


def paired_item_differences(
    rows: Iterable[dict[str, Any]], arm_a: str, arm_b: str, metric: str = "quality"
) -> list[float]:
    """Return per-item mean(a) - mean(b), paired before bootstrap."""

    rows = list(rows)
    a = _item_arm_means(rows, arm=arm_a, metric=metric)
    b = _item_arm_means(rows, arm=arm_b, metric=metric)
    common = sorted(a.keys() & b.keys())
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
    differences: list[float], *, confidence: float = 0.95, resamples: int = 10_000, seed: int = 37
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


def _metric_variance_by_arm_across_cells(rows: list[dict[str, Any]], metric: str) -> dict[str, float]:
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


def assert_nonzero_cell_variance(rows: list[dict[str, Any]], metric: str = "quality") -> None:
    """Reject a flat arm/cell metric; flat controls are a broken instrument."""

    variances = _metric_variance_by_arm_across_cells(rows, metric)
    flat = sorted(arm for arm, variance in variances.items() if variance <= 0.0)
    if flat:
        raise ValueError("flat arm metric across cells detected: " + ", ".join(flat))


def _ci_payload(differences: list[float], *, seed: int, config: dict[str, Any]) -> dict[str, Any]:
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
    """Evaluate the frozen admission rule; raise SystemExit(1) on failure."""

    arms = config["admission"]["arms_run"]
    if tuple(arms[:1]) != ("single",) or len(arms) != 2:
        raise ValueError("E3 admission must run single and static_homog only")
    static_arm = str(arms[1]).replace(" at max N", "")
    differences = paired_item_differences(rows, static_arm, "single")
    ci = _ci_payload(differences, seed=10_301, config=config)
    static_quality = _item_arm_means(rows, arm=static_arm)
    single_quality = _item_arm_means(rows, arm="single")
    common = sorted(static_quality.keys() & single_quality.keys())
    static_median = median([static_quality[item_id] for item_id in common])
    single_median = median([single_quality[item_id] for item_id in common])
    median_gap = static_median - single_median
    passed = median_gap > 10.0 * ci["ci_halfwidth"]
    result = {
        "status": "PASS_ADMISSION" if passed else "FAIL_ADMISSION",
        "arms": ["single", static_arm],
        "endpoint": "quality(static_homog@maxN) - quality(single)",
        "rule": "median(diff) > 10 * ci_halfwidth",
        "paired": ci,
        "static_median": static_median,
        "single_median": single_median,
        "median_gap": median_gap,
        "treatment_executed": False,
    }
    if not passed:
        # This is executable preregistration semantics, not a warning path.
        raise SystemExit(1)
    return result


def verdict(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Evaluate E3 primary, co-primary, and quality-floor gates."""

    assert_nonzero_cell_variance(rows)
    treatment = {str(row["arm"]) for row in rows}
    required = {"adaptive_K", "adaptive_random"}
    if not required <= treatment:
        raise ValueError("treatment records must include adaptive_K and adaptive_random")
    primary_differences = paired_item_differences(rows, "adaptive_K", "adaptive_random")
    primary = _ci_payload(primary_differences, seed=10_401, config=config)

    static_arms = sorted(
        arm for arm in treatment if arm.startswith("static_")
    )
    co_primary: dict[str, Any] = {}
    for index, arm in enumerate(static_arms):
        co_primary[arm] = _ci_payload(
            paired_item_differences(rows, "adaptive_K", arm),
            seed=10_500 + index,
            config=config,
        )
    adaptive_quality = _item_arm_means(rows, arm="adaptive_K")
    floor = float(config["endpoints"]["quality_floor"])
    floor_pass = median(list(adaptive_quality.values())) >= floor
    primary_pass = primary["ci_low"] > 0.0
    co_primary_pass = bool(co_primary) and all(result["ci_low"] > 0.0 for result in co_primary.values())
    passed = primary_pass and co_primary_pass and floor_pass
    return {
        "status": "PASS" if passed else "FAIL",
        "primary": primary,
        "co_primary": co_primary,
        "quality_floor": {"median": median(list(adaptive_quality.values())), "floor": floor, "pass": floor_pass},
        "counts_toward_verdict": True,
        "single_confirmatory_run": True,
    }


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the preregistered E3 statistics")
    parser.add_argument("--phase", choices=("admission", "verdict"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    rows = _load_rows(args.input)
    result = admission(rows, config) if args.phase == "admission" else verdict(rows, config)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
