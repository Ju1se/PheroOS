from __future__ import annotations

import random
from copy import deepcopy

import pytest

from pheroos_bench import r0_measurement


def _config(worlds: int = 4, repetitions: int = 1) -> dict:
    return {
        "method_version": r0_measurement.METHOD,
        "phase": "instrument_check",
        "arms": ["control", "candidate"],
        "world_ids": {"task": [f"world-{index:03}" for index in range(worlds)]},
        "repetitions": repetitions,
        "cost_unit": "call_units",
        "budget_cap": 100,
        "confidence": 0.95,
        "bootstrap_resamples": 499,
        "seed": 37,
    }


def _row(cell: str, world: str, repetition: int, arm: str, **changes) -> dict:
    row = {
        "record_version": "r_episode_v1",
        "phase": "instrument_check",
        "cell": cell,
        "world_id": world,
        "repetition": repetition,
        "arm": arm,
        "outcome": "failed",
        "cost": 3,
        "unknown_cost_units": 0,
    }
    row.update(changes)
    return row


def _rows(config: dict) -> list[dict]:
    return [
        _row(
            cell,
            world,
            repetition,
            arm,
            outcome="success" if arm == "candidate" and index < 3 else "failed",
        )
        for cell, worlds in config["world_ids"].items()
        for index, world in enumerate(worlds)
        for repetition in range(config["repetitions"])
        for arm in config["arms"]
    ]


def _assert_invalid(report: dict) -> None:
    assert report["status"] == "INVALID_ABORT"
    assert report["counts_toward_verdict"] is False
    assert "quality" not in report
    assert "cost" not in report


def test_known_binary_world_effect_matches_independent_diagnostic() -> None:
    config = _config(worlds=100)
    config["bootstrap_resamples"] = 10_000
    rows = []
    for index, world in enumerate(config["world_ids"]["task"]):
        rows.append(
            _row(
                "task",
                world,
                0,
                "candidate",
                outcome="success" if index < 30 else "failed",
            )
        )
        rows.append(
            _row(
                "task",
                world,
                0,
                "control",
                outcome="success" if 30 <= index < 35 else "failed",
            )
        )
    report = r0_measurement.analyze(rows, config)
    assert report["status"] == "VALID_MEASUREMENT"
    assert report["counts_toward_verdict"] is False
    assert report["n_worlds"] == 100
    assert report["n_episodes"] == 200
    assert report["quality"]["mean"] == pytest.approx(0.25)
    assert report["quality"]["ci_low"] == pytest.approx(0.15)
    assert report["quality"]["ci_high"] == pytest.approx(0.35)
    assert report["quality"]["ci_status"] == "OK"


def test_sparse_repeated_improvements_are_one_percentage_point_not_thirty_three() -> (
    None
):
    config = _config(worlds=60, repetitions=3)
    config["bootstrap_resamples"] = 10_000
    rows = []
    for index, world in enumerate(config["world_ids"]["task"]):
        baseline_correct = 1 if index < 31 else 2
        for arm, correct in (
            ("control", baseline_correct),
            ("candidate", baseline_correct + (index < 2)),
        ):
            for repetition in range(3):
                rows.append(
                    _row(
                        "task",
                        world,
                        repetition,
                        arm,
                        outcome="success" if repetition < correct else "failed",
                    )
                )
    report = r0_measurement.analyze(rows, config)
    assert report["status"] == "VALID_MEASUREMENT"
    assert report["quality"]["mean"] == pytest.approx(2 / 180)
    assert report["quality"]["n_worlds"] == 60
    assert report["n_episodes"] == 360
    assert report["quality"]["ci_low"] == 0
    assert report["quality"]["ci_high"] == pytest.approx(5 / 180)


def test_replicating_within_world_repetitions_does_not_inflate_sample_size() -> None:
    config = _config(worlds=8, repetitions=2)
    rows = _rows(config)
    for row in rows:
        if row["repetition"] == 1:
            row["outcome"] = "success" if row["arm"] == "control" else "failed"
    first = r0_measurement.analyze(rows, config)
    expanded_config = deepcopy(config)
    expanded_config["repetitions"] = 6
    expanded = [
        dict(row, repetition=row["repetition"] + offset)
        for offset in (0, 2, 4)
        for row in rows
    ]
    second = r0_measurement.analyze(expanded, expanded_config)
    assert first["quality"] == second["quality"]
    assert first["cost"] == second["cost"]
    assert first["n_worlds"] == second["n_worlds"] == 8
    assert second["n_episodes"] == 3 * first["n_episodes"]


def test_input_order_does_not_change_pairing_or_bootstrap() -> None:
    config = _config(worlds=12, repetitions=3)
    rows = _rows(config)
    expected = r0_measurement.analyze(rows, config)
    random.Random(179).shuffle(rows)
    assert r0_measurement.analyze(rows, config) == expected


@pytest.mark.parametrize("candidate_outcome", ["success", "failed"])
def test_ordinary_flat_cells_are_valid_measurements(candidate_outcome: str) -> None:
    config = _config()
    config["world_ids"]["another-task"] = list(config["world_ids"]["task"])
    rows = _rows(config)
    for row in rows:
        row["outcome"] = candidate_outcome if row["arm"] == "candidate" else "failed"
    report = r0_measurement.analyze(rows, config)
    assert report["status"] == "VALID_MEASUREMENT"
    assert report["counts_toward_verdict"] is False
    assert report["n_worlds"] == 8
    assert report["quality"]["mean"] == (candidate_outcome == "success")
    assert report["quality"]["ci_status"] == "INSUFFICIENT_RESOLUTION"
    assert report["cost"]["ci_status"] == "INSUFFICIENT_RESOLUTION"


def test_identical_policies_have_zero_measured_advantage() -> None:
    config = _config(worlds=12)
    rows = _rows(config)
    for row in rows:
        row["outcome"] = (
            "success" if int(row["world_id"].split("-")[1]) % 2 else "failed"
        )
    report = r0_measurement.analyze(rows, config)
    assert report["status"] == "VALID_MEASUREMENT"
    assert report["quality"]["mean"] == 0
    assert report["quality"]["ci_low"] == report["quality"]["ci_high"] == 0
    assert report["cost"]["mean"] == 0


def test_all_episode_outcomes_contribute_quality_and_spend() -> None:
    config = _config(worlds=5)
    outcomes = ["success", "failed", "timeout", "rejected", "cancelled"]
    rows = []
    for index, world in enumerate(config["world_ids"]["task"]):
        rows.append(_row("task", world, 0, "control", outcome="success", cost=2))
        rows.append(
            _row(
                "task", world, 0, "candidate", outcome=outcomes[index], cost=10 + index
            )
        )
    report = r0_measurement.analyze(rows, config)
    assert report["status"] == "VALID_MEASUREMENT"
    assert report["n_worlds"] == 5
    assert report["n_episodes"] == 10
    assert report["quality"]["mean"] == pytest.approx(-0.8)
    # All five candidate episodes cost money, including the four non-successes.
    assert report["cost"]["mean"] == pytest.approx(10)
    candidate = next(row for row in report["by_cell_arm"] if row["arm"] == "candidate")
    assert candidate["cost_total"] == 60
    assert candidate["outcomes"] == dict.fromkeys(outcomes, 1)


def test_known_budget_violation_remains_an_observed_bad_result() -> None:
    config = _config()
    rows = _rows(config)
    rows[0]["cost"] = config["budget_cap"] + 1
    report = r0_measurement.analyze(rows, config)
    assert report["status"] == "VALID_MEASUREMENT"
    control = next(row for row in report["by_cell_arm"] if row["arm"] == "control")
    assert control["budget_exceeded_episodes"] == 1
    assert control["cost_total"] == 110
    assert report["cost"]["mean"] == pytest.approx(-24.5)


@pytest.mark.parametrize(
    "defect",
    [
        "missing_episode",
        "missing_world",
        "duplicate_episode",
        "extra_world",
        "extra_arm",
        "wrong_cell",
        "wrong_repetition",
        "bool_repetition",
        "negative_repetition",
        "string_repetition",
        "unknown_outcome",
        "unknown_version",
        "wrong_phase",
        "missing_cost",
        "negative_cost",
        "fractional_cost",
        "bool_cost",
        "infinite_cost",
        "nan_cost",
        "missing_unknown",
        "negative_unknown",
        "fractional_unknown",
        "bool_unknown",
        "missing_world_id",
        "extra_quality",
    ],
)
def test_invalid_grid_and_measurements_abort_without_statistical_verdict(
    defect: str,
) -> None:
    config = _config()
    rows = _rows(config)
    if defect == "missing_episode":
        rows.pop()
    elif defect == "missing_world":
        rows = [row for row in rows if row["world_id"] != "world-000"]
    elif defect == "duplicate_episode":
        rows.append(dict(rows[0]))
    elif defect == "extra_world":
        rows[0]["world_id"] = "undeclared-world"
    elif defect == "extra_arm":
        rows[0]["arm"] = "undeclared-arm"
    elif defect == "wrong_cell":
        rows[0]["cell"] = "undeclared-cell"
    elif defect == "wrong_repetition":
        rows[0]["repetition"] = 1
    elif defect == "bool_repetition":
        rows[0]["repetition"] = False
    elif defect == "negative_repetition":
        rows[0]["repetition"] = -1
    elif defect == "string_repetition":
        rows[0]["repetition"] = "0"
    elif defect == "unknown_outcome":
        rows[0]["outcome"] = "pending"
    elif defect == "unknown_version":
        rows[0]["record_version"] = "future"
    elif defect == "wrong_phase":
        rows[0]["phase"] = "confirmatory"
    elif defect == "missing_cost":
        del rows[0]["cost"]
    elif defect == "negative_cost":
        rows[0]["cost"] = -1
    elif defect == "fractional_cost":
        rows[0]["cost"] = 1.5
    elif defect == "bool_cost":
        rows[0]["cost"] = True
    elif defect == "infinite_cost":
        rows[0]["cost"] = float("inf")
    elif defect == "nan_cost":
        rows[0]["cost"] = float("nan")
    elif defect == "missing_unknown":
        del rows[0]["unknown_cost_units"]
    elif defect == "negative_unknown":
        rows[0]["unknown_cost_units"] = -1
    elif defect == "fractional_unknown":
        rows[0]["unknown_cost_units"] = 0.5
    elif defect == "bool_unknown":
        rows[0]["unknown_cost_units"] = True
    elif defect == "missing_world_id":
        del rows[0]["world_id"]
    elif defect == "extra_quality":
        rows[0]["quality"] = 1
    _assert_invalid(r0_measurement.analyze(rows, config))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("method_version", "paired_item_mean_v1"),
        ("phase", "confirmatory"),
        ("arms", ["control", "control"]),
        ("arms", ["control"]),
        ("world_ids", {}),
        ("world_ids", {"task": ["same", "same"]}),
        ("world_ids", {"task": []}),
        ("repetitions", 0),
        ("repetitions", True),
        ("cost_unit", "dollars"),
        ("budget_cap", 0),
        ("budget_cap", True),
        ("confidence", 1),
        ("bootstrap_resamples", 0),
        ("bootstrap_resamples", True),
        ("seed", True),
    ],
)
def test_analysis_contract_requires_explicit_valid_method_and_grid(
    field: str, value
) -> None:
    config = _config()
    rows = _rows(config)
    config[field] = value
    _assert_invalid(r0_measurement.analyze(rows, config))


def test_unknown_cost_is_never_silently_counted_as_zero() -> None:
    config = _config()
    rows = _rows(config)
    rows[0]["outcome"] = "timeout"
    rows[0]["unknown_cost_units"] = 5
    report = r0_measurement.analyze(rows, config)
    _assert_invalid(report)
    assert "unknown_cost" in str(report).lower()
    assert sum(row["unknown_cost_units"] for row in report["accounting"]) == 5
    assert sum(row["cost_total"] for row in report["accounting"]) == 24


def test_existing_public_bootstrap_receives_world_means_and_cell_strata(
    monkeypatch,
) -> None:
    calls = []

    def ci(differences, **kwargs):
        calls.append((list(differences), kwargs))
        return -0.1, 0.1

    monkeypatch.setattr(r0_measurement, "paired_percentile_ci", ci)
    config = _config(worlds=4, repetitions=3)
    config["world_ids"]["other"] = list(config["world_ids"]["task"])
    report = r0_measurement.analyze(_rows(config), config)
    assert report["status"] == "VALID_MEASUREMENT"
    assert len(calls) >= 2
    for differences, kwargs in calls:
        assert len(differences) == 8
        assert kwargs["statistic"] == "mean"
        assert sorted(kwargs["strata"]) == ["other"] * 4 + ["task"] * 4
        assert kwargs["confidence"] == 0.95
        assert kwargs["resamples"] == 499
        assert kwargs["seed"] == 37
    assert report["quality"]["ci_low"] == -0.1
    assert report["quality"]["ci_high"] == 0.1
