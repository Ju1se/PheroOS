from copy import deepcopy

import pytest

from pheroos_bench import r0_measurement
from pheroos_bench.coordination_repair_v1_measurement import analyze_forks


def test_unchanged_r0_equal_world_not_equal_cell_weight_with_signed_cost():
    config = dict(method_version=r0_measurement.METHOD, phase="instrument_check",
                  arms=["control", "candidate"], world_ids={"small": [f"s{i}" for i in range(10)],
                  "large": [f"l{i}" for i in range(90)]}, repetitions=1,
                  cost_unit="call_units", budget_cap=100, confidence=0.95,
                  bootstrap_resamples=199, seed=47)
    rows = [dict(record_version="r_episode_v1", phase="instrument_check", cell=cell,
                 world_id=world, repetition=0, arm=arm,
                 outcome="success" if cell == "small" and arm == "candidate" else "failed",
                 cost=10 if arm == "control" else (5 if cell == "small" else 12),
                 unknown_cost_units=0)
            for cell, worlds in config["world_ids"].items() for world in worlds for arm in config["arms"]]
    report = r0_measurement.analyze(rows, config)
    assert report["quality"]["mean"] == pytest.approx(0.10)
    assert report["cost"]["mean"] == pytest.approx(1.30)
    reversed_report = r0_measurement.analyze(rows, config | {"arms": list(reversed(config["arms"]))})
    assert reversed_report["quality"]["mean"] == pytest.approx(-0.10)
    assert reversed_report["cost"]["mean"] == pytest.approx(-1.30)


def fork_fixture():
    prefixes, records = [], []
    for world, count in (("one", 1), ("many", 9)):
        for number in range(count):
            prefix = str(number)
            prefixes.append(dict(world_id=world, prefix_id=prefix, eligible=True, prefix_tokens=10))
            for branch in ("relevant", "withheld", "irrelevant"):
                records.append(dict(world_id=world, prefix_id=prefix, branch=branch,
                                    success=world == "one" and branch == "relevant",
                                    incremental_tokens=4 if branch == "relevant" else 8,
                                    status="VALID_KNOWN", unknown_calls=0, invalid_actions=3))
    return prefixes, records


def test_forks_are_nested_and_invalid_actions_remain_in_denominator():
    prefixes, records = fork_fixture()
    result = analyze_forks(prefixes, records)
    assert result["status"] == "VALID_KNOWN"
    assert result["independent_worlds"] == 2
    assert result["comparisons"]["withheld"]["mean_differences"] == {
        "success": 0.5, "incremental_tokens": -4}
    assert result["prefix_tokens_total"] == 100
    assert result["executed_branches"] == 30


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "invalid", "ineligible"])
def test_fork_integrity_explicitly_preserves_bad_and_unresolved_records(change):
    prefixes, records = fork_fixture()
    if change == "missing":
        records.pop()
    elif change == "duplicate":
        records.append(deepcopy(records[0]))
    elif change == "unknown":
        records[0]["unknown_calls"] = 1
    elif change == "invalid":
        records[0]["status"] = "INVALID_ABORT"
    else:
        prefixes[0]["eligible"] = False
    result = analyze_forks(prefixes, records)
    assert result["status"] == ("VALID_UNRESOLVED" if change == "unknown" else "INVALID_ABORT")
