"""Real installed Session checks for the v2 additive consumer. No missing-runtime skips.

The deterministic adapter is an accounting probe, not a learned model.
"""
from hashlib import sha256
import json

import pytest

from pheroos_bench import coordination_repair_v1 as original
from pheroos_bench import coordination_repair_v2 as repaired

class PermissionProbe:
    def __init__(self, *, before_dispatch):
        self.identity = {"adapter": "permission_probe", "live_model": False}
        if before_dispatch:
            self.identity["fractional_identity"] = 0.7
        self.calls = 0

    def count_tokens(self, messages):
        return 32

    def generate(self, messages, max_new_tokens, seed):
        self.calls += 1
        raise PermissionError("synthetic post-dispatch permission denial")


def arguments(tmp_path, name="episode", **extra):
    return dict(world="interval_intersection/dev_a", arm="single", n=1,
                output=tmp_path / name, condition="D0", steps=1,
                token_cap=2048, **extra)


def test_preparation_progress_is_reported_without_rewriting_raw_v1(tmp_path):
    params = arguments(tmp_path)
    row = repaired.run_episode(**params)
    data = (params["output"] / "episode.json").read_bytes()
    raw = json.loads(data)
    assert raw["method_version"] == original.METHOD
    assert raw["metrics"]["first_verified_progress_turn"] is None
    assert row["raw_record"] == {"file": "episode.json", "sha256": sha256(data).hexdigest()}
    assert row["success"] is raw["success"] is True
    assert row["metrics"]["tool_calls"] == raw["metrics"]["tool_calls"] == 4
    progress = row["metrics"]["first_verified_progress"]
    assert progress["phase"] == "preparation"
    assert progress["preparation_index"] == 0 and progress["decision_turn"] is None
    assert progress["source_id"] == "lower_bounds"
    assert row["diagnostics"]["message_measurement_status"] == "CHANNEL_NOT_USED"
    assert row["metrics"]["message_duplicate_count"] == 0
    assert row["metrics"]["message_duplicate_rate"] is None
    assert row["metrics"]["prompt_message_exposures"] == 0
    assert row["complete_rollout"] is True
    assert json.loads((params["output"] / "episode-v2.json").read_text()) == row
    with pytest.raises(FileExistsError):
        repaired.run_episode(**params)
    assert (params["output"] / "episode.json").read_bytes() == data


@pytest.mark.parametrize("before_dispatch", [True, False])
def test_permission_error_stage_and_unknown_spending_use_real_session(tmp_path, before_dispatch):
    from pheroos_runtime.campaign_v1 import CampaignBudget
    campaign = CampaignBudget.create(tmp_path / "campaign.sqlite", token_cap=2048,
                                     dispatch_cap=2, config_digest="5" * 64)
    probe = PermissionProbe(before_dispatch=before_dispatch)
    params = arguments(tmp_path, model=probe, campaign=campaign, allocation_id="permission")
    row = repaired.run_episode(**params)
    raw = json.loads((params["output"] / "episode.json").read_text())
    assert raw["status"] == row["status"] == "INVALID_ABORT"
    assert raw["primary_failure_stage"] == row["raw_primary_failure_stage"] == "transport_format"
    assert row["primary_failure_stage"] == row["stop"] == "capability_permission"
    assert row["errors"][0]["raw_stage"] == "transport_format"
    assert row["metrics"]["tokens"] == raw["metrics"]["tokens"] == 0
    assert row["metrics"]["tool_calls"] == 3
    assert row["metrics"]["configured_inference_concurrency"] == 1
    assert row["metrics"]["actual_inference_concurrency"] == int(not before_dispatch)
    assert row["metrics"]["unknown_tokens"] == raw["metrics"]["unknown_tokens"] == (0 if before_dispatch else 288)
    assert row["metrics"]["unknown_calls"] == int(not before_dispatch)
    assert probe.calls == int(not before_dispatch)
    assert row["metrics"]["prompt_message_exposures"] == (0 if before_dispatch else 2)
    assert row["metrics"]["first_verified_progress"]["phase"] == "preparation"
    assert row["complete_rollout"] is False
    assert campaign.snapshot()["allotments"][0]["unknown_tokens"] == (0 if before_dispatch else 288)


def test_real_reference_forks_write_additive_raw_records_and_new_branch_scopes(tmp_path):
    parent = repaired.run_episode(world="interval_intersection/dev_a", arm="candidate", n=2,
        output=tmp_path / "parent", condition="D2", steps=8, token_cap=2048, capture_step=1)
    raw_parent = (tmp_path / "parent/episode.json").read_bytes()
    prefix, records, episodes = repaired.full_rollouts(parent, output=tmp_path / "forks")
    assert prefix["eligible"] and len(episodes) == len(records) == 3
    assert all(r["complete_rollout"] and r["success"] for r in records)
    scopes = {parent["scope_id"]} | {r["branch_scope"] for r in records}
    assert len(scopes) == 4
    for episode, record in zip(episodes, records):
        assert record["branch_setup_tool_calls"] == 2
        assert episode["metrics"]["first_verified_progress"]["source_id"] == "preference"
        branch = tmp_path / "forks" / record["branch"]
        raw = (branch / "episode.json").read_bytes()
        assert sha256(raw).hexdigest() == episode["raw_record"]["sha256"]
        assert json.loads(raw)["method_version"] == original.METHOD
    assert (tmp_path / "parent/episode.json").read_bytes() == raw_parent
