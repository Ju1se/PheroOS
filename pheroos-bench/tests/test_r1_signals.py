from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pheroos_bench import r1_signals as r1


@pytest.fixture
def config():
    return json.loads((Path(__file__).parents[1] / "r1-pilot-v1.json").read_text())


def test_clones_cannot_create_independent_support(config):
    signal = r1.world(900, config)[0][0][0]
    receiver = r1.Receiver(r1.Meter())
    for clone in range(100):
        receiver.receive(replace(signal, signal_id=f"clone-{clone}"), 0)
    assert len(receiver.sources) == 1
    assert receiver.answer() == signal.value


@pytest.mark.parametrize("arm", ["candidate", "source_version_ttl"])
@pytest.mark.parametrize("version_field", ["source_version", "task_version"])
def test_competent_policies_reactivate_valid_versions(config, arm, version_field):
    event = r1.world(900, config)[0][0][0]
    policy = r1.Policy(arm, 32, r1.Meter())
    assert policy.admit(event, 0, 0, 4)
    assert not policy.admit(replace(event, signal_id="clone"), 0, 1, 4)
    updated = replace(event, **{version_field: 2, "origin_event_id": "updated"})
    assert policy.admit(updated, 0, 2, 4)


def test_ablation_cannot_reactivate_within_window(config):
    event = r1.world(900, config)[0][0][0]
    policy = r1.Policy("no_reactivation", 32, r1.Meter())
    assert policy.admit(event, 0, 0, 4)
    assert not policy.admit(replace(event, source_version=2), 0, 6, 4)


def test_stale_replay_cannot_reverse_receiver_correction(config):
    event = r1.world(900, config)[0][0][0]
    receiver = r1.Receiver(r1.Meter())
    receiver.receive(event, 0)
    receiver.receive(replace(event, source_version=2, value=1 - event.value), 1)
    receiver.receive(event, 2)
    assert receiver.answer() == 1 - event.value


@pytest.mark.parametrize("arm", r1.ARMS)
def test_reliable_controls_bypass_exhausted_data_cap(config, arm):
    config["data_delivery_cap_per_step"] = 0
    row = r1.episode(900, arm, config, [0] * config["steps"])
    assert row["controls_delivered"] == 6
    assert row["final_answers"][0] is None
    assert row["final_answers"][4] is None
    assert sum(row["data_deliveries_per_step"]) == 0


def test_no_update_negative_has_no_candidate_quality_gain(config):
    rows = [r1.episode(900, arm, config) for arm in
            ("candidate", "source_version_ttl", "no_reactivation")]
    assert all(r["final_answers"] == rows[0]["final_answers"] for r in rows)
    assert all(r["data_deliveries_per_step"] == rows[0]["data_deliveries_per_step"] for r in rows)
    assert all(not r["correction_delays"] for r in rows)


def test_sparse_random_matches_candidate_budget_and_scoring_truth_is_private(config, monkeypatch):
    candidate = r1.episode(903, "candidate", config)
    sparse = r1.episode(903, "matched_sparse_random", config, candidate["data_deliveries_per_step"])
    assert sparse["data_deliveries_per_step"] == candidate["data_deliveries_per_step"]
    timeline, truth, meta = r1.world(903, config)
    monkeypatch.setattr(r1, "world", lambda *_: (timeline, [[1 - x for x in t] for t in truth], meta))
    changed = r1.episode(903, "candidate", config)
    assert changed["final_answers"] == candidate["final_answers"]
    assert changed["cost"] == candidate["cost"]


def test_every_stage_is_accounted_and_deterministic(config):
    row = r1.episode(903, "candidate", config)
    assert row == r1.episode(903, "candidate", config)
    cost = row["cost"]
    assert cost["total_accounted_bytes"] == sum(v for k, v in cost.items() if k.endswith("_bytes") and k != "total_accounted_bytes")
    assert all(v > 0 for v in cost.values())
    assert cost["delivered_operations"] == sum(row["data_deliveries_per_step"]) + row["controls_delivered"]
    assert row["llm_calls"] == row["input_tokens"] == row["output_tokens"] == 0


def test_output_directory_is_never_overwritten(config, tmp_path):
    path = Path(__file__).parents[1] / "r1-pilot-v1.json"
    with pytest.raises(FileExistsError):
        r1.main(["--config", str(path), "--output", str(tmp_path)])


def test_missing_duplicate_and_failed_measurements_are_invalid(config):
    row = {"split": "pilot", "seed": 0, "arm": "candidate", "status": "error"}
    assert r1.analyze([row], config)["status"] == "INVALID"
    assert r1.analyze([row, row])["status"] == "INVALID"
    assert r1.analyze([row])["status"] == "INVALID"


def test_no_signal_cannot_succeed_from_truth_access(config, monkeypatch):
    timeline, truth, meta = r1.world(903, config)
    empty = [[e for e in events if e.kind != "evidence"] for events in timeline]
    monkeypatch.setattr(r1, "world", lambda *_: (empty, truth, meta))
    row = r1.episode(903, "candidate", config)
    assert row["success"] == 0
    assert row["final_answers"] == [None] * config["agents"]
    assert row["missed_corrections"] == 2
