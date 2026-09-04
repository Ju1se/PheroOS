from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable

import numpy as np


def _bootstrap_median(values: Iterable[float], *, seed: int, samples: int) -> tuple[float, float]:
    values_array = np.asarray(list(values), dtype=np.float64)
    if values_array.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values_array.size, size=(samples, values_array.size))
    estimates = np.median(values_array[indices], axis=1)
    return tuple(float(x) for x in np.percentile(estimates, [2.5, 97.5]))


def _pairs(rows: list[dict[str, Any]], arm_a: str, arm_b: str, population: int, fraction: float, key: str) -> list[float]:
    a = {
        int(row["seed"]): row
        for row in rows
        if row["arm"] == arm_a and int(row["N"]) == population and float(row["informed_fraction"]) == fraction
    }
    b = {
        int(row["seed"]): row
        for row in rows
        if row["arm"] == arm_b and int(row["N"]) == population and float(row["informed_fraction"]) == fraction
    }
    return [float(a[seed][key]) - float(b[seed][key]) for seed in sorted(a.keys() & b.keys())]


def summarize_admission(rows: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    populations = [int(value) for value in config["scan"]["N"]]
    fractions = [float(value) for value in config["scan"]["informed_fraction"]]
    samples = int(config["seeds"]["bootstrap_resamples"])
    summary: list[dict[str, Any]] = []
    cells: dict[str, dict[str, Any]] = {}
    all_passed = True
    for population in populations:
        for fraction_index, fraction in enumerate(fractions):
            differences = _pairs(rows, "solitary", "oracle", population, fraction, "global_regret")
            lo, hi = _bootstrap_median(differences, seed=31_000 + population + fraction_index, samples=samples)
            gap = float(median(differences)) if differences else float("nan")
            halfwidth = (hi - lo) / 2.0
            passed = bool(differences) and gap > 10.0 * halfwidth
            all_passed = all_passed and passed
            key = f"N{population}_p{fraction:.2f}"
            cells[key] = {
                "N": population,
                "informed_fraction": fraction,
                "paired_count": len(differences),
                "median_solitary_minus_oracle": gap,
                "ci_low": lo,
                "ci_high": hi,
                "ci_halfwidth": halfwidth,
                "passed": passed,
            }
            for arm in ("solitary", "oracle"):
                arm_rows = [
                    row
                    for row in rows
                    if row["arm"] == arm
                    and int(row["N"]) == population
                    and float(row["informed_fraction"]) == fraction
                ]
                summary.append(
                    {
                        "N": population,
                        "informed_fraction": fraction,
                        "arm": arm,
                        "n": len(arm_rows),
                        "median_global_regret": median([float(row["global_regret"]) for row in arm_rows]) if arm_rows else float("nan"),
                        "median_steps_to_first_r_star_adoption": median(
                            [
                                float(row["steps_to_first_r_star_adoption"])
                                for row in arm_rows
                                if row["steps_to_first_r_star_adoption"] is not None
                            ]
                            or [float(config["timing"]["steps"])]
                        ),
                        "median_messages": median([float(row["messages"]) for row in arm_rows]) if arm_rows else 0.0,
                        "median_bytes": median([float(row["bytes"]) for row in arm_rows]) if arm_rows else 0.0,
                        "admission_pass_at_cell": passed,
                    }
                )
    return summary, {
        "experiment": config["experiment"],
        "status": "PASS_ADMISSION" if all_passed else "ADMISSION_FAILED",
        "all_cells_passed": all_passed,
        "cells": cells,
        "treatment_executed": False,
        "abort_on_failure": "sys.exit(1)",
    }


def admission_or_abort(rows: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary, admission = summarize_admission(rows, config)
    if admission["status"] != "PASS_ADMISSION":
        # This is deliberately a real process-level abort. It is not a warning
        # and it must prevent any treatment arm from being scheduled.
        raise SystemExit(1)
    return summary, admission


def summarize_treatment(rows: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    populations = [int(value) for value in config["scan"]["N"]]
    fractions = [float(value) for value in config["scan"]["informed_fraction"]]
    samples = int(config["seeds"]["bootstrap_resamples"])
    summary: list[dict[str, Any]] = []
    cells: dict[str, dict[str, Any]] = {}
    for population in populations:
        for fraction_index, fraction in enumerate(fractions):
            primary = _pairs(rows, "couzin", "naive_gossip", population, fraction, "global_regret")
            secondary = _pairs(rows, "couzin", "solitary", population, fraction, "global_regret")
            lo, primary_hi = _bootstrap_median(primary, seed=41_000 + population + fraction_index, samples=samples)
            sec_lo, sec_hi = _bootstrap_median(secondary, seed=42_000 + population + fraction_index, samples=samples)
            key = f"N{population}_p{fraction:.2f}"
            cells[key] = {
                "N": population,
                "informed_fraction": fraction,
                "paired_count": len(primary),
                "primary_median_couzin_minus_gossip": float(median(primary)) if primary else float("nan"),
                "primary_ci_low": lo,
                "primary_ci_high": primary_hi,
                "primary_pass": bool(primary) and primary_hi < 0.0,
                "secondary_median_couzin_minus_solitary": float(median(secondary)) if secondary else float("nan"),
                "secondary_ci_low": sec_lo,
                "secondary_ci_high": sec_hi,
            }
            for arm in ("solitary", "naive_gossip", "couzin"):
                arm_rows = [
                    row
                    for row in rows
                    if row["arm"] == arm
                    and int(row["N"]) == population
                    and float(row["informed_fraction"]) == fraction
                ]
                summary.append(
                    {
                        "N": population,
                        "informed_fraction": fraction,
                        "arm": arm,
                        "n": len(arm_rows),
                        "median_global_regret": median([float(row["global_regret"]) for row in arm_rows]) if arm_rows else float("nan"),
                        "median_steps_to_first_r_star_adoption": median(
                            [
                                float(row["steps_to_first_r_star_adoption"])
                                for row in arm_rows
                                if row["steps_to_first_r_star_adoption"] is not None
                            ]
                            or [float(config["timing"]["steps"])]
                        ),
                        "median_messages": median([float(row["messages"]) for row in arm_rows]) if arm_rows else 0.0,
                        "median_bytes": median([float(row["bytes"]) for row in arm_rows]) if arm_rows else 0.0,
                        "primary_pass_at_cell": cells[key]["primary_pass"] if arm == "couzin" else False,
                    }
                )

    passing_by_population: dict[str, list[float]] = {}
    adjacent_pairs: dict[str, list[list[float]]] = {}
    for population in populations:
        passing = [fraction for fraction in fractions if cells[f"N{population}_p{fraction:.2f}"]["primary_pass"]]
        passing_by_population[str(population)] = passing
        adjacent_pairs[str(population)] = [
            [left, right]
            for left, right in zip(passing, passing[1:])
            if fractions.index(right) == fractions.index(left) + 1
        ]
    primary_gate = any(adjacent_pairs[str(population)] for population in populations)
    smallest = {
        key: (values[0] if values else None)
        for key, values in passing_by_population.items()
    }
    comparable = [value for value in smallest.values() if value is not None]
    scale_prediction = all(left >= right for left, right in zip(comparable, comparable[1:])) if len(comparable) > 1 else None
    verdict = {
        "experiment": config["experiment"],
        "status": "PASS" if primary_gate else "FAIL",
        "primary_gate": primary_gate,
        "passing_cells": [key for key, value in cells.items() if value["primary_pass"]],
        "adjacent_passing_pairs_by_N": adjacent_pairs,
        "smallest_passing_fraction_by_N": smallest,
        "scale_prediction_non_increasing": scale_prediction,
        "treatment_executed": True,
        "admission_required": True,
        "thresholds_changed": False,
        "rerun": False,
        "cells": cells,
    }
    return summary, verdict
