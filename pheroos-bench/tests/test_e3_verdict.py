from __future__ import annotations

from copy import deepcopy

import pytest

from pheroos_bench.e3_verdict import admission, paired_percentile_ci, verdict


def _config() -> dict:
    return {
        "status": "frozen",
        "admission": {"arms_run": ["single", "static_homog at max N"]},
        "arms": {
            "single": {"role": "admission + secondary comparator"},
            "static_homog": {"N": [4, 8]},
            "static_diverse": {"N": [4, 8]},
        },
        "task": {"item_ids": {"easy": ["0", "1"], "hard": ["0", "1"]}},
        "model": {"provider_model_string": "test-model-v1"},
        "budget": {"unit": "tokens", "cap_per_item": 1000},
        "statistics": {
            "confidence": 0.95,
            "bootstrap_resamples": 500,
            "repetitions_per_item_per_arm": 3,
        },
        "endpoints": {"quality_floor": 0.60},
    }


def _rows(phase: str = "confirmatory") -> list[dict]:
    qualities = {
        "adaptive_K": 0.90,
        "adaptive_random": 0.30,
        "static_homog@4": 0.40,
        "static_homog@8": 0.50,
        "static_diverse@4": 0.55,
        "static_diverse@8": 0.60,
        "single": 0.20,
    }
    if phase == "admission":
        qualities = {"single": 0.20, "static_homog@8": 0.80}
    return [
        {
            "item_id": item,
            "cell": cell,
            "repetition": repetition,
            "arm": arm,
            "quality": quality - 0.02 * (cell == "hard"),
            "tokens": 100,
            "model": "test-model-v1",
            "phase": phase,
            "counts_toward_verdict": phase == "confirmatory",
        }
        for cell, items in _config()["task"]["item_ids"].items()
        for item in items
        for repetition in range(3)
        for arm, quality in qualities.items()
    ]


def test_paired_percentile_ci_is_deterministic() -> None:
    values = [0.1, 0.2, 0.3, 0.4]
    assert paired_percentile_ci(values, resamples=100, seed=9) == paired_percentile_ci(
        values, resamples=100, seed=9
    )


def test_admission_checks_each_benchmark_with_runner_arm_names() -> None:
    result = admission(_rows("admission"), _config())
    assert result["status"] == "PASS_ADMISSION"
    assert result["treatment_executed"] is False
    assert set(result["cells"]) == {"easy", "hard"}
    assert result["arms"] == ["single", "static_homog@8"]


def test_one_failed_benchmark_aborts_admission() -> None:
    rows = _rows("admission")
    for row in rows:
        if row["cell"] == "hard":
            row["quality"] = 0.5
    with pytest.raises(SystemExit) as exc_info:
        admission(rows, _config())
    assert exc_info.value.code == 1


def test_verdict_checks_all_configured_static_arms() -> None:
    result = verdict(_rows(), _config())
    assert result["status"] == "PASS"
    assert result["primary"]["n_items"] == 4  # IDs are scoped by benchmark.
    assert set(result["co_primary"]) == {
        "static_homog@4",
        "static_homog@8",
        "static_diverse@4",
        "static_diverse@8",
    }
    assert result["quality_floor"]["pass"] is True


def test_one_superior_static_arm_causes_fail() -> None:
    rows = _rows()
    for row in rows:
        if row["arm"] == "static_diverse@8":
            row["quality"] += 0.35
    assert verdict(rows, _config())["status"] == "FAIL"


def test_single_is_reported_as_secondary_not_a_gate() -> None:
    rows = _rows()
    for row in rows:
        if row["arm"] == "single":
            row["quality"] += 0.75
    result = verdict(rows, _config())
    assert result["status"] == "PASS"
    assert result["secondary"]["adaptive_K_vs_single"]["ci_high"] < 0
    assert "single" not in result["co_primary"]


@pytest.mark.parametrize(
    "defect",
    [
        "missing_arm",
        "missing_single",
        "missing_item",
        "missing_all_arms_item",
        "duplicate",
        "missing_repetition",
        "extra_arm",
        "over_budget",
        "unknown_usage",
        "negative_cost",
        "nan_quality",
        "out_of_range_quality",
        "model_drift",
        "pilot",
        "wrong_cell",
        "unfrozen",
        "unresolved_pilot",
        "unknown_unit",
    ],
)
def test_invalid_evidence_cannot_produce_a_verdict(defect: str) -> None:
    rows, config = _rows(), deepcopy(_config())
    if defect == "missing_arm":
        rows = [r for r in rows if r["arm"] != "static_diverse@8"]
    elif defect == "missing_single":
        rows = [r for r in rows if r["arm"] != "single"]
    elif defect == "missing_item":
        rows = [
            r
            for r in rows
            if not (r["arm"] == "adaptive_random" and r["item_id"] == "0")
        ]
    elif defect == "missing_all_arms_item":
        rows = [r for r in rows if r["item_id"] != "0"]
    elif defect == "duplicate":
        rows.append(dict(rows[0]))
    elif defect == "missing_repetition":
        rows.pop()
    elif defect == "extra_arm":
        rows[0]["arm"] = "static_weak_unregistered"
    elif defect == "over_budget":
        rows[0]["tokens"] = 1001
    elif defect == "unknown_usage":
        rows[0]["tokens"] = None
    elif defect == "negative_cost":
        rows[0]["tokens"] = -1
    elif defect == "nan_quality":
        rows[0]["quality"] = float("nan")
    elif defect == "out_of_range_quality":
        rows[0]["quality"] = 2
    elif defect == "model_drift":
        rows[0]["model"] = "different-model"
    elif defect == "pilot":
        rows[0].update(phase="pilot", counts_toward_verdict=False)
    elif defect == "wrong_cell":
        rows[0]["cell"] = "gsm8k"
    elif defect == "unfrozen":
        config["status"] = "skeleton"
    elif defect == "unresolved_pilot":
        config["k_star"] = {"threshold": "PILOT"}
    elif defect == "unknown_unit":
        config["budget"]["unit"] = "unspecified"
    with pytest.raises(ValueError):
        verdict(rows, config)


def test_flat_arm_is_rejected_before_verdict() -> None:
    rows = _rows()
    for row in rows:
        if row["arm"] == "adaptive_random":
            row["quality"] = 0.5
    with pytest.raises(ValueError, match="flat arm metric"):
        verdict(rows, _config())
