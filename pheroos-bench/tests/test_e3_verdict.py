from __future__ import annotations

import json
from copy import deepcopy
from statistics import median

import pytest

from pheroos_bench.e3_verdict import (
    ESTIMAND,
    AdmissionRejected,
    admission,
    main,
    paired_item_differences,
    paired_percentile_ci,
    verdict,
)


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
            "estimand": ESTIMAND,
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
            # Item-level gains vary: constant treatment differences cannot
            # establish uncertainty and must no longer serve as PASS fixtures.
            "quality": quality
            - 0.02 * (cell == "hard")
            + 0.01
            * int(item)
            * (arm == ("static_homog@8" if phase == "admission" else "adaptive_K")),
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
    assert result["estimand"] == ESTIMAND
    assert all(cell["paired"]["ci_status"] == "OK" for cell in result["cells"].values())


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
    assert result["primary"]["mean"] == pytest.approx(0.605)
    assert result["primary"]["confidence"] == 0.95
    assert result["primary"]["nominal_directional_alpha"] == pytest.approx(0.025)
    assert result["primary"]["median_robustness"]["used_for_success"] is False


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


def test_sparse_binary_improvements_cannot_pass_admission_via_median_jump() -> None:
    config = _config()
    config["task"]["item_ids"] = {"sparse": [str(i) for i in range(60)]}
    config["statistics"]["bootstrap_resamples"] = 10_000
    rows = []
    single_means, static_means = [], []
    for item in range(60):
        # Two additional correct answers move both middle order statistics,
        # despite improving only 2 of the 180 paired calls.
        baseline = 1 if item < 31 else 2
        improved = baseline + (item < 2)
        single_means.append(baseline / 3)
        static_means.append(improved / 3)
        for arm, correct in (("single", baseline), ("static_homog@8", improved)):
            for repetition in range(3):
                rows.append(
                    {
                        "item_id": str(item),
                        "cell": "sparse",
                        "repetition": repetition,
                        "arm": arm,
                        "quality": int(repetition < correct),
                        "tokens": 100,
                        "model": "test-model-v1",
                        "phase": "admission",
                        "counts_toward_verdict": False,
                    }
                )
    assert median(static_means) - median(single_means) == pytest.approx(1 / 3)
    with pytest.raises(AdmissionRejected) as rejected:
        admission(rows, config)
    cell = rejected.value.report["cells"]["sparse"]
    assert rejected.value.code == 1
    assert cell["status"] == "FAIL_ADMISSION"
    assert cell["mean_gap"] == pytest.approx(2 / 180)
    assert cell["paired"]["mean"] == pytest.approx(2 / 180)
    assert cell["paired"]["n_items"] == 60
    assert cell["paired"]["ci_low"] == 0
    assert cell["paired"]["ci_high"] == pytest.approx(5 / 180)
    assert cell["paired"]["median_robustness"]["median"] == 0


def test_primary_mean_can_detect_a_gain_when_median_is_zero() -> None:
    config = _config()
    config["task"]["item_ids"] = {
        cell: [str(i) for i in range(20)] for cell in ("easy", "hard")
    }
    rows = [
        dict(row, item_id=str(item))
        for row in _rows()
        if row["item_id"] == "0"
        for item in range(20)
    ]
    for row in rows:
        if row["arm"] in ("adaptive_K", "adaptive_random"):
            row["quality"] = (
                0.9 - 0.02 * (row["cell"] == "hard") + 0.01 * (int(row["item_id"]) % 2)
            )
            if row["arm"] == "adaptive_random" and int(row["item_id"]) < 3:
                row["quality"] -= 0.6
    result = verdict(rows, config)
    assert result["status"] == "PASS"
    assert result["primary"]["n_items"] == 40
    assert result["primary"]["mean"] == pytest.approx(6 * 0.6 / 40)
    assert result["primary"]["ci_low"] > 0
    assert result["primary"]["median_robustness"] == {
        "median": 0.0,
        "ci_low": 0.0,
        "ci_high": 0.0,
        "used_for_success": False,
    }


def test_repetitions_are_averaged_before_pairing_items_within_benchmarks() -> None:
    observations = {
        ("easy", "a"): [1, 1, 0],
        ("easy", "b"): [0, 0, 0],
        ("hard", "a"): [0, 0, 0],
        ("hard", "b"): [1, 0, 0],
    }
    rows = [
        {"cell": cell, "item_id": "shared-id", "arm": arm, "quality": quality}
        for (cell, arm), values in observations.items()
        for quality in values
    ]
    assert paired_item_differences(reversed(rows), "a", "b") == pytest.approx(
        [2 / 3, -1 / 3]
    )


def test_stratified_bootstrap_preserves_benchmark_sample_counts() -> None:
    # Fixed zero and one strata have a fixed weighted mean. Resampling across
    # them instead would introduce uncertainty in the benchmark composition.
    differences = [0.0, 1.0, 0.0, 1.0]
    stratified = paired_percentile_ci(
        differences,
        statistic="mean",
        strata=["easy", "hard", "easy", "hard"],
        resamples=500,
        seed=9,
    )
    unstratified = paired_percentile_ci(
        differences, statistic="mean", resamples=500, seed=9
    )
    assert stratified == (0.5, 0.5)
    assert unstratified[0] < 0.5 < unstratified[1]


@pytest.mark.parametrize("comparison", ["adaptive_random", "static_homog@4"])
def test_degenerate_primary_or_co_primary_interval_is_inconclusive(
    comparison: str,
) -> None:
    rows = _rows()
    treatment = {
        (row["cell"], row["item_id"], row["repetition"]): row["quality"]
        for row in rows
        if row["arm"] == "adaptive_K"
    }
    for row in rows:
        if row["arm"] == comparison:
            row["quality"] = (
                treatment[(row["cell"], row["item_id"], row["repetition"])] - 0.2
            )
    result = verdict(rows, _config())
    assert result["status"] == "INCONCLUSIVE"
    paired = (
        result["primary"]
        if comparison == "adaptive_random"
        else result["co_primary"][comparison]
    )
    assert paired["mean"] == pytest.approx(0.2)
    assert paired["ci_status"] == "INSUFFICIENT_RESOLUTION"


def test_rejected_admission_cli_writes_diagnostics_and_returns_nonzero(
    tmp_path, capsys
) -> None:
    rows = _rows("admission")
    for row in rows:
        row["quality"] = (0.8 if row["arm"] == "static_homog@8" else 0.2) - 0.02 * (
            row["cell"] == "hard"
        )
    records_path = tmp_path / "records.jsonl"
    config_path = tmp_path / "config.json"
    output_path = tmp_path / "admission.json"
    records_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    config_path.write_text(json.dumps(_config()))
    exit_code = main(
        [
            "--phase",
            "admission",
            "--input",
            str(records_path),
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 1
    report = json.loads(output_path.read_text())
    assert json.loads(capsys.readouterr().out) == report
    assert report["status"] == "FAIL_ADMISSION"
    assert report["treatment_executed"] is False
    assert all(
        cell["status"] == "INSUFFICIENT_RESOLUTION" for cell in report["cells"].values()
    )


@pytest.mark.parametrize("phase", ["admission", "confirmatory"])
@pytest.mark.parametrize("version", [None, "paired_item_median_v0"])
def test_legacy_config_requires_an_explicit_new_estimand(phase: str, version) -> None:
    config = _config()
    if version is None:
        del config["statistics"]["estimand"]
    else:
        config["statistics"]["estimand"] = version
    evaluate = admission if phase == "admission" else verdict
    with pytest.raises(ValueError, match="statistics.estimand must explicitly declare"):
        evaluate(_rows(phase), config)


def test_quality_floor_uses_the_mean_rather_than_the_median() -> None:
    rows, config = _rows(), _config()
    for row in rows:
        if row["arm"] == "adaptive_K":
            row["quality"] = (
                0.1 if (row["cell"], row["item_id"]) == ("easy", "0") else 0.8
            )
    config["endpoints"]["quality_floor"] = 0.7
    result = verdict(rows, config)
    assert result["quality_floor"]["mean"] == pytest.approx(0.625)
    assert result["quality_floor"]["median"] == pytest.approx(0.8)
    assert result["quality_floor"]["statistic"] == "mean"
    assert result["quality_floor"]["pass"] is False
    assert result["status"] == "FAIL"


@pytest.mark.parametrize("phase", ["admission", "confirmatory"])
def test_realized_costs_are_reported_separately_from_shared_caps(phase: str) -> None:
    rows = _rows(phase)
    for row in rows:
        row["tokens"] = 200 if row["arm"] == "single" else 100
    evaluate = admission if phase == "admission" else verdict
    report = evaluate(rows, _config())["descriptive"]
    assert report["budget_unit"] == "tokens"
    assert report["cap_per_item_arm_repetition"] == 1000
    for cell_arm in report["by_cell_arm"]:
        per_record = 200 if cell_arm["arm"] == "single" else 100
        assert cell_arm["n_records"] == 6
        assert cell_arm["spend_total"] == 6 * per_record
        assert cell_arm["spend_mean"] == per_record
