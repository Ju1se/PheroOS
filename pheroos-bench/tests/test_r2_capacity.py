from copy import deepcopy
import json
from pathlib import Path

import pytest

from pheroos_bench import r2_capacity as audit
from pheroos_bench import r2_scheduling as r2


ROOT = Path(__file__).parents[1]


def example():
    spec = {"jobs": [{"id": "a"}], "horizon": 4, "failures": [(1, 0, 3)]}
    trace = [{"kind": "execute_unit", "tick": 0, "worker": 0, "task": "a"},
             {"kind": "worker_failed", "tick": 1, "worker": 0, "recover_at": 3},
             {"kind": "execute_unit", "tick": 1, "worker": 1, "task": "a"},
             {"kind": "worker_recovered", "tick": 3, "worker": 0},
             {"kind": "execute_unit", "tick": 3, "worker": 0, "task": "a"}]
    return spec, trace


def test_outage_end_is_available_and_idle_is_not_dedicated_reserve():
    spec, trace = example()
    result = audit.capacity(spec, trace)
    assert result["total_worker_ticks"] == 16
    assert result["unavailable_worker_ticks"] == 2
    assert result["available_worker_ticks"] == 14
    assert result["busy_worker_ticks"] == 3
    assert result["idle_worker_ticks"] == 11
    assert result["ticks"][2]["available"] == 3
    assert result["ticks"][3]["available"] == 4
    assert result["reserve_policy"] == "none"
    assert result["dedicated_reserve_worker_ticks"] == 0


def test_recovery_then_failure_at_same_tick_does_not_count_worker_available():
    spec, trace = example()
    spec["failures"].append((3, 0, 6))
    trace.pop()  # The worker remains offline and cannot execute at tick 3.
    trace.append({"kind": "worker_failed", "tick": 3, "worker": 0, "recover_at": 6})
    result = audit.capacity(spec, trace)
    assert result["unavailable_worker_ticks"] == 3
    assert result["ticks"][3]["available"] == 3


@pytest.mark.parametrize("defect", ["duplicate", "offline", "late", "unknown_worker", "unknown_task", "missing_failure", "missing_recovery"])
def test_bad_capacity_observations_are_rejected(defect):
    spec, trace = example()
    if defect == "duplicate":
        trace.append(dict(trace[0]))
    elif defect in ("offline", "late", "unknown_worker", "unknown_task"):
        trace[0].update({"offline": {"tick": 2}, "late": {"tick": 4},
                         "unknown_worker": {"worker": 4}, "unknown_task": {"task": "x"}}[defect])
    else:
        trace = [event for event in trace if event["kind"] != {
            "missing_failure": "worker_failed", "missing_recovery": "worker_recovered"}[defect]]
    with pytest.raises(ValueError):
        audit.capacity(spec, trace)


@pytest.mark.parametrize("world,unavailable", [(r2.WORLDS[0], 9), (r2.WORLDS[1], 0)])
@pytest.mark.parametrize("arm", r2.ARMS)
def test_real_frozen_semantics_reconcile_capacity_and_preserve_costs(world, unavailable, arm):
    source = r2.run_episode(937, arm, world) | {"cohort": "development"}
    before = deepcopy(source)
    result = audit.audit_episode(source)
    assert source == before
    assert result["capacity"]["unavailable_worker_ticks"] == unavailable
    assert result["capacity"]["busy_worker_ticks"] == source["costs"]["execution_units"]
    assert result["source_costs"] == source["costs"]
    assert result["additional_independent_worlds"] == 0
    assert result["paid_calls"] == result["llm_calls"] == 0


@pytest.mark.parametrize("field,value", [("trace_sha256", "changed"), ("completed_tasks", 0)])
def test_changed_historical_episode_is_not_reinterpreted(field, value):
    row = r2.run_episode(937, "capability_fifo") | {"cohort": "development"}
    row[field] = value
    with pytest.raises(ValueError, match="does not reproduce"):
        audit.audit_episode(row)


def test_source_artifact_hash_mismatch_writes_abort_and_refuses_overwrite(tmp_path):
    config = json.loads((ROOT / "r2-capacity-audit-v1.json").read_text())
    config["source_artifact_sha256"]["episodes.jsonl"] = "0" * 64
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "audit"
    arguments = ["--config", str(path), "--output", str(output)]
    assert audit.main(arguments) == 2
    summary = json.loads((output / "summary.json").read_text())
    assert summary["status"] == "INVALID_ABORT"
    assert summary["audited_episodes"] == 0
    assert not (output / "episodes.jsonl").exists()
    with pytest.raises(FileExistsError):
        audit.main(arguments)


def test_interrupted_audit_preserves_known_cost_and_never_marks_complete(tmp_path, monkeypatch):
    original = r2.run_episode(937, "capability_fifo") | {"cohort": "pilot"}
    monkeypatch.setattr(audit, "_inputs", lambda *_: (
        [original], {"pilot_seeds": [937], "evaluation_seeds": []}, {}))
    def interrupt(_):
        raise KeyboardInterrupt()
    monkeypatch.setattr(audit, "audit_episode", interrupt)
    output = tmp_path / "audit"
    assert audit.main(["--config", str(ROOT / "r2-capacity-audit-v1.json"), "--output", str(output)]) == 2
    summary = json.loads((output / "summary.json").read_text())
    row = json.loads((output / "episodes.jsonl").read_text())
    assert summary["status"] == row["status"] == "INVALID_ABORT"
    assert row["source_costs"] == original["costs"]
    assert row["capacity_measurement_unknown"] is True


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        audit._load('{"method": "one", "method": "two"}')
