from __future__ import annotations

import pytest

from pheroos_bench.e3_verdict import admission, paired_percentile_ci, verdict


def _config() -> dict:
    return {
        "admission": {"arms_run": ["single", "static_homog at max N"]},
        "statistics": {"confidence": 0.95, "bootstrap_resamples": 500},
        "endpoints": {"quality_floor": 0.60},
    }


def _rows() -> list[dict]:
    rows = []
    for item_id in range(8):
        for repetition in range(3):
            rows.extend(
                [
                    {
                        "item_id": str(item_id), "cell": str(item_id % 2), "rep": repetition,
                        "arm": "single", "quality": 0.25 + (item_id % 2) * 0.02 + repetition * 0.01,
                    },
                    {
                        "item_id": str(item_id), "cell": str(item_id % 2), "rep": repetition,
                        "arm": "static_homog", "quality": 0.80 + (item_id % 2) * 0.02 + repetition * 0.01,
                    },
                    {
                        "item_id": str(item_id), "cell": str(item_id % 2), "rep": repetition,
                        "arm": "adaptive_K", "quality": 0.82 + (item_id % 2) * 0.02 + repetition * 0.01,
                    },
                    {
                        "item_id": str(item_id), "cell": str(item_id % 2), "rep": repetition,
                        "arm": "adaptive_random", "quality": 0.62 + (item_id % 2) * 0.01 + repetition * 0.01,
                    },
                    {
                        "item_id": str(item_id), "cell": str(item_id % 2), "rep": repetition,
                        "arm": "static_diverse", "quality": 0.70 + (item_id % 2) * 0.02 + repetition * 0.01,
                    },
                ]
            )
    return rows


def test_paired_percentile_ci_is_deterministic() -> None:
    values = [0.1, 0.2, 0.3, 0.4]
    assert paired_percentile_ci(values, resamples=100, seed=9) == paired_percentile_ci(values, resamples=100, seed=9)


def test_admission_passes_and_never_marks_treatment_executed() -> None:
    result = admission(_rows(), _config())
    assert result["status"] == "PASS_ADMISSION"
    assert result["treatment_executed"] is False
    assert result["paired"]["median"] > 0


def test_admission_abort_is_system_exit() -> None:
    rows = [
        {"item_id": str(i), "cell": str(i % 2), "rep": 0, "arm": arm, "quality": 0.5}
        for i in range(8)
        for arm in ("single", "static_homog")
    ]
    with pytest.raises(SystemExit) as exc_info:
        admission(rows, _config())
    assert exc_info.value.code == 1


def test_verdict_checks_primary_co_primary_and_floor() -> None:
    result = verdict(_rows(), _config())
    assert result["status"] == "PASS"
    assert result["primary"]["ci_low"] > 0
    assert set(result["co_primary"]) == {"static_diverse", "static_homog"}
    assert result["quality_floor"]["pass"] is True


def test_flat_arm_is_rejected_before_verdict() -> None:
    rows = _rows()
    for row in rows:
        if row["arm"] == "adaptive_random":
            row["quality"] = 0.5
    with pytest.raises(ValueError, match="flat arm metric"):
        verdict(rows, _config())
