from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from pheroos_bench import r1_coordination as r1


ROOT = Path(__file__).parents[1]


@pytest.fixture
def config():
    return json.loads((ROOT / "r1-coordination-pilot-v2.json").read_text())


@pytest.fixture
def event(config):
    return r1.world(1000, config)[0][0][0]


def consume(policy, event, agent=0, tick=0):
    admitted = policy.admit(event, agent, tick, 4)
    if admitted:
        policy.delivered(event, agent, tick)
    return admitted


def test_provenance_dedup_is_recipient_local_not_value_matching(event):
    policy = r1.Policy("candidate", 32, r1.Meter())
    assert consume(policy, event)
    clone = replace(event, signal_id="relay", causal_parent_ids=(event.origin_event_id,))
    assert not consume(policy, clone)
    assert consume(policy, clone, agent=4)
    independent = replace(event, source_ref="independent", dependence_group="independent",
                          origin_event_id="independent-origin")
    assert consume(policy, independent)


@pytest.mark.parametrize("field", ["source_version", "task_version"])
def test_reactivation_is_a_version_only_ablation(event, field):
    event = replace(event, expires_at=64)
    candidate = r1.Policy("candidate", 32, r1.Meter())
    ablation = r1.Policy("no_reactivation", 32, r1.Meter())
    assert consume(candidate, event)
    assert consume(ablation, event)
    # Hold origin and payload constant to isolate the version dimension.
    changed = replace(event, **{field: 2})
    assert consume(candidate, changed, tick=1)
    assert not consume(ablation, changed, tick=1)
    assert consume(ablation, changed, tick=32)


@pytest.mark.parametrize("arm", ["dedup_ttl", "source_version_ttl", "candidate", "no_reactivation"])
def test_ttl_boundary_reopens_without_sliding_on_suppressed_reads(event, arm):
    policy = r1.Policy(arm, 4, r1.Meter())
    assert consume(policy, event)
    assert not consume(policy, event, tick=3)
    assert consume(policy, event, tick=4)


def test_newly_named_stale_claim_is_suppressed_and_cannot_reverse_answer(event):
    policy = r1.Policy("candidate", 4, r1.Meter())
    receiver = r1.Receiver(0, r1.Meter())
    fresh = replace(event, source_version=2, value=1 - event.value)
    assert consume(policy, fresh)
    receiver.receive(fresh, 0)
    stale = replace(event, origin_event_id="late-old-origin")
    assert not consume(policy, stale, tick=8)
    receiver.receive(stale, 8)
    assert receiver.answer(8) == fresh.value


def test_receiver_expires_evidence_without_another_message(event):
    receiver = r1.Receiver(0, r1.Meter())
    receiver.receive(replace(event, expires_at=2), 0)
    assert receiver.answer(2) == event.value
    assert receiver.answer(3) is None


def test_receiver_never_treats_replicas_as_independent_support(event):
    receiver = r1.Receiver(0, r1.Meter())
    receiver.receive(event, 0)
    for i in range(100):
        receiver.receive(replace(event, signal_id=f"replica:{i}"), 0)
    assert len(receiver.sources) == 1
    receiver.receive(replace(event, source_ref="independent", dependence_group="independent",
                             value=1-event.value), 0)
    assert len(receiver.sources) == 2
    assert receiver.answer(0) is None  # Clones cannot outvote an independent tie.


@pytest.mark.parametrize("kind", ["evidence", "constraint", "stop", "cancel", "denied"])
@pytest.mark.parametrize("field,value", [("task_ref", 1), ("scope_ref", "other")])
def test_receiver_binding_applies_even_without_relevance(event, kind, field, value):
    receiver = r1.Receiver(0, r1.Meter())
    receiver.receive(event, 0)
    receiver.receive(replace(event, kind=kind, value=1-event.value, task_version=2,
                             **{field: value}), 1)
    assert receiver.answer(1) == event.value
    assert not receiver.blocked
    assert receiver.task_version == 1


@pytest.mark.parametrize("arm", r1.ARMS)
def test_controls_share_reliable_addressed_path_at_zero_data_cap(config, arm):
    config["data_delivery_cap_per_step"] = 0
    row = r1.episode(1003, arm, config, [0] * config["steps"])
    assert row["status"] == "complete"
    assert row["controls_delivered"] == 8  # Two recipients x (constraint + three terminal controls).
    assert sum(row["data_deliveries_per_step"]) == 0
    assert row["success"] == 0
    assert row["cost"]["delivered_operations"] == 8


def set_timeline(monkeypatch, config, ticks):
    timeline = ticks + [[] for _ in range(config["steps"] - len(ticks))]
    truth = [[0] * config["tasks"] for _ in timeline]
    monkeypatch.setattr(r1, "world", lambda *_: (timeline, truth, {"updates": {}}))


def test_same_tick_clones_use_one_slot_and_independent_source_gets_next(config, event, monkeypatch):
    config.update(agents=4, data_delivery_cap_per_step=2)
    independent = replace(event, source_ref="independent", dependence_group="independent",
                          origin_event_id="independent-origin")
    set_timeline(monkeypatch, config, [[event, replace(event, signal_id="clone"), independent]])
    row = r1.episode(1000, "candidate", config)
    assert row["data_deliveries_per_step"][0] == 2
    assert row["duplicate_deliveries"] == 0
    assert row["retained_source_slots"][0] == 2


def test_cap_deferred_claim_can_deliver_when_exposed_again(config, event, monkeypatch):
    config.update(agents=4, data_delivery_cap_per_step=1)
    independent = replace(event, source_ref="independent", dependence_group="independent",
                          origin_event_id="independent-origin")
    set_timeline(monkeypatch, config, [[event, independent], [independent]])
    row = r1.episode(1000, "candidate", config)
    assert row["data_deliveries_per_step"][:2] == [1, 1]
    assert row["deferred_data_edges"] == 1
    assert row["retained_source_slots"][0] == 2


def test_ablations_change_communication_behavior_without_changing_receiver(config, event, monkeypatch):
    config.update(agents=4, data_delivery_cap_per_step=96)
    set_timeline(monkeypatch, config, [[event, replace(event, signal_id="clone")]])
    rows = {arm: r1.episode(1000, arm, config) for arm in ("candidate", "no_dedup", "no_relevance")}
    assert [rows[arm]["data_deliveries_per_step"][0] for arm in rows] == [1, 2, 4]
    assert all(row["final_answers"] == rows["candidate"]["final_answers"] for row in rows.values())


def test_shared_environment_is_deterministic_and_truth_is_scorer_only(config, monkeypatch):
    row = r1.episode(1003, "candidate", config)
    assert row == r1.episode(1003, "candidate", config)
    timeline, truth, meta = r1.world(1003, config)
    monkeypatch.setattr(r1, "world", lambda *_: (timeline, [[1-v for v in t] for t in truth], meta))
    changed = r1.episode(1003, "candidate", config)
    assert changed["cost"] == row["cost"]
    assert changed["final_answers"] == row["final_answers"]
    assert changed["success"] != row["success"]


def test_matched_random_uses_candidate_counts_and_accounts_selector(config):
    candidate = r1.episode(1003, "candidate", config)
    row = r1.episode(1003, "matched_sparse_random", config, candidate["data_deliveries_per_step"])
    assert row["data_deliveries_per_step"] == candidate["data_deliveries_per_step"]
    assert row["cost"]["routing_operations"] > candidate["cost"]["routing_operations"]


def test_missing_evidence_and_controls_cannot_satisfy_blocked_task(config, monkeypatch):
    config["source_accuracy"] = 1
    timeline, truth, meta = r1.world(1000, config)
    timeline = [[event for event in events if event.task_ref != 0] for events in timeline]
    monkeypatch.setattr(r1, "world", lambda *_: (timeline, truth, meta))
    row = r1.episode(1000, "candidate", config)
    assert row["final_answers"][0] is None
    assert row["controls_delivered"] == 0
    assert row["agent_accuracy"] == 0.75  # The other six receivers are correct.
    assert row["success"] == 0


def test_no_evidence_is_retained_as_known_cost_task_failure(config, monkeypatch):
    timeline, truth, meta = r1.world(1003, config)
    timeline = [[event for event in events if event.kind != "evidence"] for events in timeline]
    monkeypatch.setattr(r1, "world", lambda *_: (timeline, truth, meta))
    row = r1.episode(1003, "candidate", config)
    assert row["status"] == "complete"
    assert row["success"] == 0
    assert row["final_answers"] == [None] * config["agents"]
    assert row["missed_corrections"] == 2
    assert row["cost"]["total_accounted_operations"] > 0
    assert row["unknown_cost_units"] == 0


def test_all_stages_and_no_provider_costs_are_explicit(config):
    row = r1.episode(1003, "candidate", config)
    cost = row["cost"]
    for suffix in ("bytes", "operations"):
        assert cost[f"total_accounted_{suffix}"] == sum(
            cost[f"{stage}_{suffix}"] for stage in ("delivered", "routing", "encoding", "state_read", "state_write"))
    assert cost["delivered_operations"] == sum(row["data_deliveries_per_step"]) + row["controls_delivered"]
    assert row["llm_calls"] == row["input_tokens"] == row["output_tokens"] == row["unknown_cost_units"] == 0


@pytest.mark.parametrize("error", [RuntimeError("receive failed"), KeyboardInterrupt()])
def test_execution_error_retains_partial_cost_and_aborts(config, monkeypatch, error):
    def fail(*_):
        raise error
    monkeypatch.setattr(r1.Receiver, "receive", fail)
    row = r1.episode(1000, "candidate", config)
    assert row["status"] == "INVALID_ABORT"
    assert row["success"] is None
    assert row["unknown_cost_units"] > 0
    assert row["cost"]["delivered_operations"] == 1
    assert row["cost"]["total_accounted_operations"] > 1


def test_cli_produces_pilot_only_exports_and_refuses_overwrite(config, tmp_path):
    config.update(pilot_seeds=[1000], replicas_per_step=0)
    config["measurement"]["bootstrap_resamples"] = 10
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "output"
    args = ["--config", str(path), "--output", str(output)]
    assert r1.main(args) == 0
    summary = json.loads((output / "summary.json").read_text())
    assert summary["status"] == "PILOT_COMPLETE"
    assert summary["counts_toward_verdict"] is False
    assert summary["episodes"] == len(r1.ARMS)
    assert summary["freeze_hashes_unchanged"]
    for control in r1.ARMS:
        if control != "candidate":
            report = json.loads((output / control / "report.json").read_text())
            assert report["status"] == "VALID_MEASUREMENT"
            assert report["counts_toward_verdict"] is False
    with pytest.raises(FileExistsError):
        r1.main(args)


@pytest.mark.parametrize("change", [{"phase": "confirmatory"}, {"pilot_seeds": [1, 1]},
                                   {"ttl": 0}, {"source_accuracy": float("nan")},
                                   {"agents": 1}, {"data_delivery_cap_per_step": True}])
def test_invalid_configuration_writes_abort(config, tmp_path, change):
    config.update(change)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "output"
    assert r1.main(["--config", str(path), "--output", str(output)]) == 2
    report = json.loads((output / "summary.json").read_text())
    assert report["status"] == "INVALID_ABORT"
    assert report["counts_toward_verdict"] is False


def test_cli_execution_error_never_exports_valid_subset(config, tmp_path, monkeypatch):
    config.update(pilot_seeds=[1000], replicas_per_step=0)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    def fail(*_):
        raise RuntimeError("broken transport")
    monkeypatch.setattr(r1.Receiver, "receive", fail)
    output = tmp_path / "output"
    assert r1.main(["--config", str(path), "--output", str(output)]) == 2
    report = json.loads((output / "summary.json").read_text())
    assert report["invalid_episodes"] == len(r1.ARMS)
    assert report["known_accounted_operations"] > 0
    assert report["unknown_cost_units"] == len(r1.ARMS)
    assert all(r["status"] == "INVALID_ABORT" for r in report["comparisons"].values())


def test_changed_freeze_blocks_pair_exports(config, tmp_path, monkeypatch):
    config.update(pilot_seeds=[1000], replicas_per_step=0)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    original = r1.episode
    def changed(*args, **kwargs):
        row = original(*args, **kwargs)
        path.write_text(path.read_text() + "\n")
        return row
    monkeypatch.setattr(r1, "episode", changed)
    output = tmp_path / "output"
    assert r1.main(["--config", str(path), "--output", str(output)]) == 2
    report = json.loads((output / "summary.json").read_text())
    assert report["status"] == "INVALID_ABORT"
    assert report["freeze_hashes_unchanged"] is False
    assert not (output / "dedup_ttl").exists()


def test_interrupt_during_summary_cannot_report_pilot_complete(config, tmp_path, monkeypatch):
    config.update(pilot_seeds=[1000], replicas_per_step=0)
    config["measurement"]["bootstrap_resamples"] = 10
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    original = r1.episode
    def prepared(*args, **kwargs):
        row = original(*args, **kwargs)
        if args[1] == r1.ARMS[-1]:
            def interrupt(*_):
                raise KeyboardInterrupt()
            monkeypatch.setattr(r1, "fmean", interrupt)
        return row
    monkeypatch.setattr(r1, "episode", prepared)
    output = tmp_path / "output"
    assert r1.main(["--config", str(path), "--output", str(output)]) == 2
    report = json.loads((output / "summary.json").read_text())
    assert report["status"] == "INVALID_ABORT"
    assert "KeyboardInterrupt" in report["reason"]
