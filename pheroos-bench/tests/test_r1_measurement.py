from __future__ import annotations

from copy import deepcopy
import random

import pytest

from pheroos_bench import r0_measurement, r1_measurement


def _config() -> dict:
    return {
        "phase": "pilot",
        "counts_toward_verdict": False,
        "pilot_seeds": list(range(8)),
        "arms": ["broadcast", "dedup_ttl", "candidate", "no_reactivation"],
        "repeats": 1,
        "measurement": {
            "confidence": 0.95,
            "bootstrap_resamples": 199,
            "seed": 37,
            "budget_cap": 100,
        },
    }


def _cost(operations: int = 3) -> dict:
    return {
        **{
            f"{stage}_{unit}": operations if unit == "operations" else 100
            for stage in r1_measurement.STAGES
            for unit in ("operations", "bytes")
        },
        "total_accounted_operations": 5 * operations,
        "total_accounted_bytes": 500,
    }


def _rows(config: dict) -> list[dict]:
    return [
        {
            "record_version": r1_measurement.RECORD_VERSION,
            "phase": "pilot",
            "counts_toward_verdict": False,
            "seed": seed,
            "arm": arm,
            "case": r1_measurement.CASES[seed % 4],
            "status": "complete",
            "success": int(arm != "no_reactivation"),
            "cost": _cost(2 if arm == "candidate" else 3),
            "unknown_cost_units": 0,
            "trajectory": [],
        }
        for seed in config["pilot_seeds"]
        for arm in config["arms"]
    ]


def _assert_invalid(result: dict) -> None:
    assert result["records"] == []
    report = result["report"]
    assert report["status"] == "INVALID_ABORT"
    assert report["counts_toward_verdict"] is False
    assert report["source_phase"] == "pilot"
    assert "quality" not in report
    assert "cost" not in report


def test_export_uses_exact_r0_contract_and_preserves_pilot_metadata() -> None:
    config = _config()
    rows = _rows(config)
    result = r1_measurement.export_pair(rows, config, "dedup_ttl")
    assert set(result) == {"config", "records", "report"}
    assert set(result["config"]) == r0_measurement.CONFIG_FIELDS
    assert all(set(row) == r0_measurement.ROW_FIELDS for row in result["records"])
    assert result["config"]["arms"] == ["dedup_ttl", "candidate"]
    assert result["config"]["world_ids"] == {
        "no_update": ["seed:0", "seed:4"],
        "source_update": ["seed:1", "seed:5"],
        "constraint_update": ["seed:2", "seed:6"],
        "mixed": ["seed:3", "seed:7"],
    }
    report = result["report"]
    assert report["status"] == "VALID_MEASUREMENT"
    assert report["n_worlds"] == 8
    assert report["n_episodes"] == 16
    assert report["phase"] == result["config"]["phase"] == "instrument_check"
    assert report["source_phase"] == "pilot"
    assert report["counts_toward_verdict"] is False
    assert report["experimental"] is True
    assert report["source_record_version"] == r1_measurement.RECORD_VERSION
    assert "logical metered stage operations" in report["mapping"]["call_units"]
    direct = r0_measurement.analyze(result["records"], result["config"])
    assert all(report[key] == value for key, value in direct.items())
    assert report["quality"]["mean"] == 0
    assert report["cost"]["mean"] == -5


def test_failed_completed_tasks_retain_all_cost_and_binary_failure() -> None:
    config = _config()
    rows = _rows(config)
    for row in rows:
        if row["arm"] == "candidate":
            row["success"] = 0
            row["cost"] = _cost(30)
    result = r1_measurement.export_pair(rows, config, "broadcast")
    report = result["report"]
    assert report["status"] == "VALID_MEASUREMENT"
    assert report["quality"]["mean"] == -1
    assert report["cost"]["mean"] == 135
    exported = [row for row in result["records"] if row["arm"] == "candidate"]
    assert len(exported) == 8
    assert all(row["outcome"] == "failed" and row["cost"] == 150 for row in exported)
    assert sum(
        group["budget_exceeded_episodes"]
        for group in report["by_cell_arm"]
        if group["arm"] == "candidate"
    ) == 8


def test_pairing_is_order_independent_and_never_inflates_independent_units() -> None:
    config = _config()
    rows = _rows(config)
    expected = r1_measurement.export_pair(rows, config, "broadcast")
    random.Random(71).shuffle(rows)
    config["pilot_seeds"].reverse()
    config["arms"].reverse()
    actual = r1_measurement.export_pair(rows, config, "broadcast")
    # The diagnostic comparison is invariant; source accounting intentionally
    # preserves source row order and indices for corruption investigations.
    for result in (actual, expected):
        result["report"].pop("source_accounting")
    assert actual == expected
    assert actual["report"]["n_worlds"] == 8


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("record_version", "r1_signals_v1"),
        ("phase", "evaluation"),
        ("counts_toward_verdict", True),
        ("counts_toward_verdict", 0),
        ("seed", False),
        ("seed", -1),
        ("seed", []),
        ("seed", "0"),
        ("seed", 1000),
        ("arm", "undeclared"),
        ("arm", []),
        ("case", "mixed"),
        ("case", []),
        ("status", "pending"),
        ("status", []),
        ("success", None),
        ("success", True),
        ("success", 1.0),
        ("success", 2),
        ("cost", None),
        ("cost", {}),
        ("cost", []),
        ("unknown_cost_units", 1),
        ("unknown_cost_units", None),
        ("unknown_cost_units", False),
        ("unknown_cost_units", -1),
        ("unknown_cost_units", 0.5),
    ],
)
def test_corrupted_rows_never_export_usable_subset(field: str, value) -> None:
    config = _config()
    rows = _rows(config)
    # Corrupt a nonselected ablation: validating only the chosen pair would
    # silently discard this defect and misrepresent the experiment as valid.
    row = next(row for row in rows if row["arm"] == "no_reactivation")
    row[field] = value
    _assert_invalid(r1_measurement.export_pair(rows, config, "broadcast"))


@pytest.mark.parametrize("defect", ["missing", "missing_arm", "duplicate", "non_dict"])
def test_full_declared_grid_required_for_every_pair(defect: str) -> None:
    config = _config()
    rows = _rows(config)
    if defect == "missing":
        rows.pop()
    elif defect == "missing_arm":
        rows = [row for row in rows if row["arm"] != "no_reactivation"]
    elif defect == "duplicate":
        rows.append(deepcopy(rows[-1]))
    else:
        rows[-1] = []
    result = r1_measurement.export_pair(rows, config, "broadcast")
    _assert_invalid(result)
    assert len(result["report"]["source_accounting"]) == len(rows)


@pytest.mark.parametrize("field", sorted(r1_measurement.COST_FIELDS))
@pytest.mark.parametrize("bad_value", [True, -1, 0.5, "3", float("nan"), float("inf"), None])
def test_all_stage_and_total_counters_require_nonnegative_integers(field, bad_value) -> None:
    config = _config()
    rows = _rows(config)
    rows[-1]["cost"][field] = bad_value
    result = r1_measurement.export_pair(rows, config, "broadcast")
    _assert_invalid(result)
    assert field not in result["report"]["source_accounting"][-1]["known_cost"]


@pytest.mark.parametrize("unit", ["operations", "bytes"])
def test_totals_are_verified_against_stage_counts(unit: str) -> None:
    config = _config()
    rows = _rows(config)
    rows[-1]["cost"][f"total_accounted_{unit}"] += 1
    result = r1_measurement.export_pair(rows, config, "broadcast")
    _assert_invalid(result)
    assert result["report"]["reason"] == f"accounted_{unit}_mismatch"


def test_abort_keeps_known_cost_and_unknown_units_without_creating_failure() -> None:
    config = _config()
    rows = _rows(config)
    rows[-1].update(status="INVALID_ABORT", success=None, unknown_cost_units=1)
    result = r1_measurement.export_pair(rows, config, "broadcast")
    _assert_invalid(result)
    assert result["report"]["reason"] == "source_INVALID_ABORT"
    accounting = result["report"]["source_accounting"]
    assert accounting[-1]["status"] == "INVALID_ABORT"
    assert accounting[-1]["known_cost"] == rows[-1]["cost"]
    assert accounting[-1]["unknown_cost_units"] == 1
    assert sum(row["known_cost"]["total_accounted_operations"] for row in accounting) == 440


def test_missing_or_unknown_cost_does_not_erase_other_known_stage_counters() -> None:
    config = _config()
    rows = _rows(config)
    del rows[-1]["cost"]["total_accounted_operations"]
    rows[-1]["unknown_cost_units"] = 1
    result = r1_measurement.export_pair(rows, config, "broadcast")
    _assert_invalid(result)
    accounting = result["report"]["source_accounting"][-1]
    assert accounting["known_cost"] == rows[-1]["cost"]
    assert accounting["unknown_cost_units"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase", "confirmatory"),
        ("counts_toward_verdict", True),
        ("pilot_seeds", []),
        ("pilot_seeds", [0, 0]),
        ("pilot_seeds", [True]),
        ("pilot_seeds", [0, []]),
        ("arms", []),
        ("arms", ["broadcast", "candidate", "broadcast"]),
        ("arms", ["broadcast", []]),
        ("arms", ["broadcast", "dedup_ttl"]),
        ("repeats", 2),
        ("repeats", True),
        ("measurement", {}),
        ("measurement", None),
    ],
)
def test_invalid_config_does_not_create_wire_records(field: str, value) -> None:
    config = _config()
    rows = _rows(config)
    config[field] = value
    result = r1_measurement.export_pair(rows, config, "broadcast")
    _assert_invalid(result)
    assert result["config"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("budget_cap", 0),
        ("budget_cap", True),
        ("bootstrap_resamples", 0),
        ("bootstrap_resamples", 3.5),
        ("seed", -1),
        ("seed", True),
        ("confidence", 0),
        ("confidence", 1),
        ("confidence", True),
        ("confidence", float("inf")),
        ("confidence", float("nan")),
    ],
)
def test_invalid_measurement_settings_abort(field: str, value) -> None:
    config = _config()
    rows = _rows(config)
    config["measurement"][field] = value
    _assert_invalid(r1_measurement.export_pair(rows, config, "broadcast"))


@pytest.mark.parametrize("control", ["candidate", "undeclared", [], None])
def test_control_must_be_a_declared_non_candidate_arm(control) -> None:
    config = _config()
    _assert_invalid(r1_measurement.export_pair(_rows(config), config, control))


@pytest.mark.parametrize("rows", [None, {}, "bad records", 3])
def test_malformed_record_containers_return_abort(rows) -> None:
    _assert_invalid(r1_measurement.export_pair(rows, _config(), "broadcast"))


def test_input_data_is_not_mutated() -> None:
    config = _config()
    rows = _rows(config)
    original = deepcopy((rows, config))
    r1_measurement.export_pair(rows, config, "broadcast")
    assert (rows, config) == original
