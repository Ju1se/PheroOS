from __future__ import annotations

import random
from collections import defaultdict
from statistics import fmean, median
from typing import Any, Iterable


def _finite_values(values: Iterable[float | int | None], fallback: float) -> list[float]:
    result = [float(value) for value in values if value is not None]
    return result or [fallback]


def bootstrap_ci(values: list[float], *, seed: int, confidence: float = 0.95, samples: int = 2000) -> tuple[float, float]:
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(median(draw))
    estimates.sort()
    alpha = (1.0 - confidence) / 2
    lo = estimates[max(0, int(alpha * samples))]
    hi = estimates[min(samples - 1, int((1.0 - alpha) * samples))]
    return lo, hi


def _paired_values(rows: list[dict[str, Any]], arm_a: str, arm_b: str, density: float, key: str, fallback: float) -> list[float]:
    a = {int(row["seed"]): row for row in rows if row["arm"] == arm_a and float(row["density"]) == density}
    b = {int(row["seed"]): row for row in rows if row["arm"] == arm_b and float(row["density"]) == density}
    return [float(a[seed][key]) - float(b[seed][key]) for seed in sorted(a.keys() & b.keys())]


def summarize(rows: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    arms = tuple(config["arms"])
    densities = tuple(float(value) for value in config["density"]["values"])
    summary: list[dict[str, Any]] = []
    density_results: dict[str, dict[str, Any]] = {}
    for density_index, density in enumerate(densities):
        grouped = {arm: [row for row in rows if row["arm"] == arm and float(row["density"]) == density] for arm in arms}
        central = grouped.get("centralized_online", [])
        field = grouped.get("field_local", [])
        stateless = grouped.get("stateless_local_aggregate", [])
        central_regret = median(_finite_values((row["final_regret"] for row in central), 1.0))
        central_bytes = median(_finite_values((row["bytes"] for row in central), 1.0))
        central_recovery = median(_finite_values((row["spof_recovery_steps"] for row in central), float(config["environment"]["steps"])))
        field_regret = median(_finite_values((row["final_regret"] for row in field), 1.0))
        field_bytes = median(_finite_values((row["bytes"] for row in field), float(config["environment"]["steps"])))
        field_recovery = median(_finite_values((row["spof_recovery_steps"] for row in field), float(config["environment"]["steps"])))
        primary_differences = _paired_values(rows, "stateless_local_aggregate", "field_local", density, "final_regret", 1.0)
        quality_differences = _paired_values(rows, "field_local", "centralized_online", density, "final_regret", 1.0)
        byte_ratios = []
        recovery_ratios = []
        field_by_seed = {int(row["seed"]): row for row in field}
        central_by_seed = {int(row["seed"]): row for row in central}
        for seed in sorted(field_by_seed.keys() & central_by_seed.keys()):
            central_row = central_by_seed[seed]
            field_row = field_by_seed[seed]
            byte_ratios.append(float(field_row["bytes"]) / max(1.0, float(central_row["bytes"])))
            c_recovery = central_row["spof_recovery_steps"]
            f_recovery = field_row["spof_recovery_steps"]
            c_value = float(config["environment"]["steps"] if c_recovery is None else c_recovery)
            f_value = float(config["environment"]["steps"] if f_recovery is None else f_recovery)
            recovery_ratios.append(f_value / max(1.0, c_value))
        _, quality_hi = bootstrap_ci(quality_differences, seed=10_000 + density_index)
        _, byte_hi = bootstrap_ci(byte_ratios, seed=20_000 + density_index)
        _, recovery_hi = bootstrap_ci(recovery_ratios, seed=30_000 + density_index)
        primary_improvement_lo, _ = bootstrap_ci(primary_differences, seed=40_000 + density_index)
        # ``primary_differences`` is stateless - field, so a positive number
        # means the field lowers regret.
        rule = config["decision_rule"]
        checks = {
            "quality_additive": quality_hi <= float(rule["quality_additive_floor_vs_centralized"]),
            "quality_absolute": field_regret <= float(rule["quality_absolute_floor"]),
            "communication": byte_hi <= float(rule["communication_ratio_max_vs_centralized"]),
            "recovery": recovery_hi <= float(rule["recovery_ratio_max_vs_centralized"]),
            "primary_field_vs_stateless": primary_improvement_lo > 0.0,
        }
        passed = all(checks.values())
        density_results[f"{density:.2f}"] = {
            "checks": checks,
            "passed": passed,
            "quality_field_median": field_regret,
            "quality_central_median": central_regret,
            "quality_additive_gap_median": field_regret - central_regret,
            "quality_additive_gap_ci_high": quality_hi,
            "quality_absolute_floor": float(rule["quality_absolute_floor"]),
            "communication_ratio_median": field_bytes / max(1.0, central_bytes),
            "communication_ratio_ci_high": byte_hi,
            "recovery_ratio_median": field_recovery / max(1.0, central_recovery),
            "recovery_ratio_ci_high": recovery_hi,
            "primary_improvement_ci_low": primary_improvement_lo,
        }
        for arm in arms:
            values = grouped[arm]
            summary.append({
                "density": density,
                "arm": arm,
                "n": len(values),
                "median_final_regret": median(_finite_values((row["final_regret"] for row in values), 1.0)),
                "median_shock_recovery_steps": median(_finite_values((row["shock_recovery_steps"] for row in values), float(config["environment"]["steps"]))),
                "median_spof_recovery_steps": median(_finite_values((row["spof_recovery_steps"] for row in values), float(config["environment"]["steps"]))),
                "median_bytes": median(_finite_values((row["bytes"] for row in values), 0.0)),
                "median_messages": median(_finite_values((row["messages"] for row in values), 0.0)),
                "median_final_best_share": median(_finite_values((row["final_best_share"] for row in values), 0.0)),
                "gate_pass_at_density": passed if arm == "field_local" else False,
            })
    passed_keys = [density for density in densities if density_results[f"{density:.2f}"]["passed"]]
    adjacent = any(b - a <= 0.050001 for a, b in zip(passed_keys, passed_keys[1:]))
    verdict = {
        "experiment_id": config["experiment_id"],
        "status": "PASS_SWARM_CLAIM" if adjacent else "FAIL_RENAME_REQUIRED",
        "counts_toward_verdict": True,
        "confirmatory_only": True,
        "passing_density_points": passed_keys,
        "adjacent_density_gate": adjacent,
        "density_results": density_results,
        "rename_required_if_no_adjacent_pair": True,
        "pilot_is_excluded": True,
    }
    return summary, verdict
