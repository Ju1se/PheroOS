from copy import deepcopy
import json
from pathlib import Path

import pytest

from pheroos_bench.r2_scheduling import ARMS, WORLDS, check_results, main, run_episode, simulate, summarize, workload


@pytest.mark.parametrize("arm", ARMS)
def test_dependency_order_exclusive_work_and_tool_capacity(arm):
    row = run_episode(937, arm, include_trace=True)
    jobs = {job["id"]: job for job in workload(937, WORLDS[0])["jobs"]}
    live, done = {}, set()
    for event in row["trace"]:
        if event["kind"] == "dispatch":
            assert event["task"] not in live.values()
            assert event["worker"] not in live
            assert all(dep in done for dep in jobs[event["task"]]["dependencies"])
            live[event["worker"]] = event["task"]
            assert sum(jobs[key]["tool"] for key in live.values()) <= 1
        elif event["kind"] in ("completed", "lease_revoked"):
            assert live.pop(event["worker"]) == event["task"]
            if event["kind"] == "completed":
                done.add(event["task"])
    assert row["concurrent_duplicate_work"] == 0
    assert check_results(list(jobs.values()), row["results"])


def test_worker_failure_revokes_lease_and_reclaims_without_losing_cost():
    job = {"id": "j0", "arrival": 0, "deadline": 10, "capability": "compute",
           "tool": False, "duration": 3, "dependencies": [], "value": 7, "feeds_tool": False}
    spec = {"jobs": [job], "horizon": 8, "tool_capacity": 1, "failures": [(1, 0, 5)]}
    for arm in ARMS:
        row = simulate(spec, arm, include_trace=True)
        assert row["results"] == {"j0": 7}
        assert row["duplicate_attempts"] == 1
        assert row["costs"]["duplicate_execution_units"] == 1
        assert row["costs"]["execution_units"] == 4
        assert row["recovery_delay_ticks"] == [0]
        dispatched = [event for event in row["trace"] if event["kind"] == "dispatch"]
        assert len(dispatched) == 2
        assert dispatched[1]["lease"] > dispatched[0]["lease"]
        assert dispatched[1]["worker"] != dispatched[0]["worker"]


@pytest.mark.parametrize("seed", [903, 911, 937])
def test_no_failure_no_contention_is_a_matched_negative_control(seed):
    rows = [run_episode(seed, arm, WORLDS[1]) for arm in ARMS]
    for row in rows:
        assert row["completion_fraction"] == 1
        assert row["deadline_completion_fraction"] == 1
        assert row["p95_wait_ticks"] == 0
        assert row["duplicate_attempts"] == 0
        assert row["costs"]["duplicate_execution_units"] == 0
        assert row["recovery_delay_ticks"] == []
        assert row["pressure_ticks"] == 0
        assert row["results"] == rows[0]["results"]
    # Backpressure still incurs observation-processing cost when it has no gain.
    candidate = rows[ARMS.index("congestion_backpressure")]
    ablation = rows[ARMS.index("no_backpressure")]
    assert candidate["costs"]["pressure_inspections"] > ablation["costs"]["pressure_inspections"]


def test_fifo_and_no_pressure_ablation_have_identical_trajectories():
    fifo = run_episode(937, "capability_fifo")
    ablation = run_episode(937, "no_backpressure")
    assert fifo["trace_sha256"] == ablation["trace_sha256"]
    assert fifo["costs"] == ablation["costs"]


def test_pressure_changes_priorities_only_when_public_tool_queue_is_congested():
    spec = workload(937, WORLDS[0])
    candidate = simulate(spec, "congestion_backpressure")
    assert candidate["pressure_ticks"] > 0
    assert candidate["workload_sha256"] == simulate(spec, "no_backpressure")["workload_sha256"]
    assert candidate["costs"]["pressure_inspections"] > 0


def test_work_conservation_skips_a_blocked_tool_job_to_run_compatible_work():
    base = {"arrival": 0, "deadline": 9, "capability": "compute", "duration": 3,
            "dependencies": [], "value": 1, "feeds_tool": False}
    spec = {"jobs": [base | {"id": "a", "tool": True}, base | {"id": "b", "tool": True},
                     base | {"id": "c", "tool": False}], "horizon": 1,
            "tool_capacity": 1, "failures": []}
    for arm in ARMS:
        row = simulate(spec, arm, include_trace=True)
        dispatched = [event["task"] for event in row["trace"] if event["kind"] == "dispatch"]
        assert "c" in dispatched
        assert len(dispatched) == 2


def test_deadline_failure_and_unfinished_work_are_not_dropped():
    spec = workload(937, WORLDS[0])
    spec["horizon"] = 2
    row = simulate(spec, "capability_fifo")
    assert row["declared_tasks"] == 24
    assert row["completion_fraction"] == row["completed_tasks"] / 24
    assert row["deadline_completion_fraction"] < 1
    assert row["blocked_or_unarrived_tasks"] > 0
    assert row["costs"]["execution_units"] > 0


def test_result_checker_rejects_wrong_values_and_missing_dependencies():
    jobs = [
        {"id": "a", "value": 2, "dependencies": []},
        {"id": "b", "value": 3, "dependencies": ["a"]},
    ]
    assert check_results(jobs, {"a": 2, "b": 5})
    assert not check_results(jobs, {"a": 2, "b": 3})
    assert not check_results(jobs, {"b": 5})
    assert not check_results(jobs, {"a": True})
    assert not check_results(jobs, {"unknown": 1})


def test_episode_is_reproducible_and_does_not_mutate_workload():
    spec = workload(937, WORLDS[0])
    original = deepcopy(spec)
    assert simulate(spec, "work_stealing") == simulate(spec, "work_stealing")
    assert spec == original


def test_logical_cost_totals_include_all_declared_categories():
    row = run_episode(937, "congestion_backpressure")
    costs = row["costs"]
    assert costs["total_communication_bytes"] == costs["message_bytes"] + costs["observation_bytes"]
    assert costs["total_logical_scheduler_units"] == sum(costs[key] for key in (
        "state_record_reads", "eligibility_inspections", "policy_evaluations", "pressure_inspections",
        "capability_inspections", "messages", "observation_messages", "state_record_writes",
    ))
    assert costs["total_accounted_bytes"] == costs["total_communication_bytes"] + costs["state_write_bytes"] + costs["encoding_bytes"]


def test_undeclared_arms_and_worlds_are_rejected():
    with pytest.raises(ValueError):
        run_episode(937, "unknown")
    with pytest.raises(ValueError):
        workload(937, "unknown")
    with pytest.raises(ValueError):
        workload(True, WORLDS[0])


def test_pressure_changes_a_dispatch_using_only_current_observable_queue():
    base = {"arrival": 0, "deadline": 9, "duration": 2, "dependencies": [], "value": 1}
    spec = {"jobs": [base | {"id": "a", "tool": False, "capability": "compute", "feeds_tool": True},
                     base | {"id": "z", "tool": False, "capability": "compute", "feeds_tool": False},
                     *[base | {"id": f"i{i}", "tool": True, "capability": "inspect", "feeds_tool": False} for i in range(2)]],
            "horizon": 1, "tool_capacity": 1, "failures": []}
    def first(arm):
        return next(e["task"] for e in simulate(spec, arm, include_trace=True)["trace"] if e["kind"] == "dispatch")
    assert first("no_backpressure") == "a"
    assert first("congestion_backpressure") == "i0"


def test_values_do_not_influence_policy_decisions():
    spec = workload(937, WORLDS[0])
    changed = deepcopy(spec)
    for job in changed["jobs"]:
        job["value"] += 1000
    for arm in ARMS:
        traces = [simulate(s, arm, include_trace=True)["trace"] for s in (spec, changed)]
        assert [e for e in traces[0] if e["kind"] == "dispatch"] == [e for e in traces[1] if e["kind"] == "dispatch"]


def test_invalid_measurements_and_existing_output_are_rejected(tmp_path):
    path = Path(__file__).parents[1] / "r2-pilot-v1.json"
    config = json.loads(path.read_text())
    row = {"cohort": "pilot", "seed": 0, "world": WORLDS[0], "arm": ARMS[0], "status": "ERROR"}
    assert summarize([row])["status"] == "INVALID"
    assert summarize([row, row])["status"] == "INVALID"
    assert summarize([], config)["status"] == "INVALID"
    with pytest.raises(FileExistsError):
        main(["--config", str(path), "--output", str(tmp_path)])
