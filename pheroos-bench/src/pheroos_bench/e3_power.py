"""Reproducible offline sensitivity diagnostic for the E3 primary CI gate.

This is not a full E3 power calculation: no LLM calls, admission, quality floor,
static-arm comparisons, budget constraints, or model drift are simulated.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

from .e3_verdict import paired_percentile_ci


SCENARIOS = (
    (100, 3, 0.0),
    (100, 3, 0.1),
    (100, 3, 0.2),
    (100, 5, 0.05),
    (100, 10, 0.1),
    (400, 1, 0.1),
)
BASELINE = 0.5
CONFIDENCE = 0.95


def _integer(value: int, name: str, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def simulate(
    *, trials: int = 200, resamples: int = 499, seed: int = 20260912
) -> dict[str, Any]:
    """Compare historical median and revised mean gates on identical item pairs.

    A single data RNG advances through scenarios, trials, arms, items, then
    repetitions. Separate bootstrap seeds are the master seed plus a trial's
    zero-based global index; both statistics use the same bootstrap seed.
    """

    _integer(trials, "trials", 1)
    _integer(resamples, "resamples", 2)
    _integer(seed, "seed", 0)
    data_rng = random.Random(seed)
    scenarios = []
    for scenario_index, (items, repetitions, effect) in enumerate(SCENARIOS):
        counts = {
            statistic: {"detections": 0, "zero_width_intervals": 0}
            for statistic in ("median", "mean")
        }
        for trial_index in range(trials):
            control = [
                sum(data_rng.random() < BASELINE for _ in range(repetitions))
                / repetitions
                for _ in range(items)
            ]
            treatment = [
                sum(data_rng.random() < BASELINE + effect for _ in range(repetitions))
                / repetitions
                for _ in range(items)
            ]
            differences = [a - b for a, b in zip(treatment, control, strict=True)]
            bootstrap_seed = seed + scenario_index * trials + trial_index
            for statistic in counts:
                lo, hi = paired_percentile_ci(
                    differences,
                    confidence=CONFIDENCE,
                    resamples=resamples,
                    seed=bootstrap_seed,
                    statistic=statistic,
                )
                zero_width = math.isclose(lo, hi, rel_tol=0.0, abs_tol=1e-12)
                counts[statistic]["zero_width_intervals"] += int(zero_width)
                # The old primary gate lacked the new nonzero-width guard.
                passed = lo > 0.0 and (statistic == "median" or not zero_width)
                counts[statistic]["detections"] += int(passed)
        methods = {}
        for statistic, count in counts.items():
            rate = count["detections"] / trials
            methods[statistic] = {
                **count,
                "detection_rate": rate,
                "monte_carlo_standard_error": math.sqrt(rate * (1 - rate) / trials),
            }
        scenarios.append(
            {
                "items": items,
                "repetitions": repetitions,
                "true_mean_quality_difference": effect,
                "control_probability": BASELINE,
                "treatment_probability": BASELINE + effect,
                "methods": methods,
            }
        )
    return {
        "schema": "e3_offline_primary_sensitivity_v1",
        "status": "synthetic_diagnostic_not_confirmatory_evidence",
        "llm_calls": 0,
        "trials_per_scenario": trials,
        "bootstrap_resamples": resamples,
        "seed": seed,
        "generation": {
            "rng": "Python random.Random (MT19937), random() < probability",
            "data_rng": "one Random(seed) stream across all scenarios",
            "order": "scenario, trial, arm (control then treatment), item, repetition",
            "independence": "all Bernoulli calls, arms, items and trials independent",
            "pairing": "mean(treatment repeats) - mean(control repeats) for each item",
            "bootstrap_seed": "seed + scenario_index * trials + trial_index (zero-based)",
            "paired_comparison": "both methods receive identical differences and bootstrap seed",
        },
        "inference": {
            "implementation": "pheroos_bench.e3_verdict.paired_percentile_ci",
            "confidence": CONFIDENCE,
            "interval": "two-sided percentile bootstrap, resampling paired items",
            "nominal_one_sided_alpha": 0.025,
            "alpha_caveat": "nominal only; finite discrete bootstrap need not attain this rate",
            "median_gate": "lower CI > 0 (historical primary gate)",
            "mean_gate": "lower CI > 0 and not math.isclose(lower, upper, rel_tol=0, abs_tol=1e-12) (revised primary gate)",
            "zero_width_intervals": "math.isclose(lower, upper, rel_tol=0, abs_tol=1e-12), matching the verdict guard",
            "monte_carlo_standard_error": "sqrt(rate * (1 - rate) / trials)",
            "se_caveat": "plug-in Monte Carlo SE; zero at rate 0 or 1 is not certainty",
        },
        "scope": {
            "included": "single primary superiority CI gate only",
            "excluded": [
                "admission",
                "co-primary comparisons with every static arm",
                "quality floors and cell-variance checks",
                "adaptive stopping and K* estimation",
                "budget, token usage and dollar costs",
                "item difficulty, correlated calls and model drift",
            ],
            "interpretation": "sensitivity under declared synthetic assumptions, not full E3 power or an R minimum",
        },
        "scenarios": scenarios,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--resamples", type=int, default=499)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = simulate(trials=args.trials, resamples=args.resamples, seed=args.seed)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
