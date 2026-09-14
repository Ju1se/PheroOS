"""Installed runtime boundaries, with a scripted model and no model libraries."""

import json
from pathlib import Path

import pytest

from pheroos_runtime.campaign_v1 import CampaignBudget
from pheroos_bench import model_interface_v1 as diagnostic


class Instrument:
    identity = {"adapter": "scripted_interface_test", "model_calls_are_live_inference": False}

    def __init__(self, text, *, prompt_tokens=100, fail=False):
        self.text, self.prompt_tokens, self.fail = text, prompt_tokens, fail
        self.requests = []

    def count_tokens(self, messages):
        return self.prompt_tokens

    def generate(self, messages, max_new_tokens, seed):
        self.requests.append((messages, max_new_tokens, seed))
        if self.fail:
            raise RuntimeError("scripted loss after dispatch")
        return dict(text=self.text, prompt_tokens=self.prompt_tokens, completion_tokens=1,
                    generated_token_ids=[7], token_counting_basis="scripted_test_only")


def run(tmp_path, arm, instrument):
    budget = CampaignBudget.create(tmp_path / "campaign.sqlite", token_cap=2048,
                                   dispatch_cap=1, config_digest="a" * 64)
    row = diagnostic.run_episode(world="version_correction/dev_a", arm=arm, seed=1729,
        output=tmp_path / "episode", model=instrument, campaign=budget, allocation_id="diagnostic",
        instrument_only=True)
    return row, budget.snapshot(), json.loads((tmp_path / "episode/session-snapshot.json").read_text())


@pytest.mark.parametrize("arm", list(diagnostic.ARMS))
def test_every_interface_uses_real_charged_preparation_and_one_driver_call(tmp_path, arm):
    raw = '{"value":11}' if arm == "direct_json_256" else '{"action":"submit","answer":{"value":11},"citations":[{"source_id":"current_values","source_version":2}]}'
    model = Instrument(raw)
    row, account, snapshot = run(tmp_path, arm, model)
    assert row["status"] == "VALID_KNOWN" and row["complete"]
    assert row["public_accepted"] and row["objective_success"] and row["instrument_only"]
    assert len(model.requests) == 1 and model.requests[0][1] == diagnostic.ARMS[arm]["max_new_tokens"]
    assert row["metrics"]["preparation_tools"] == 1
    assert row["metrics"]["tool_calls"] == 2 and row["metrics"]["model_calls"] == 1
    assert account["held_token_upper_bound"] == account["known_tokens"] == 101
    assert account["held_call_slots"] == 1 and account["allotments"][0]["state"] == "terminal"
    call = next(c for c in snapshot["calls"] if c["action"] == "model.generate")
    assert call["reserved"] == 100 + diagnostic.ARMS[arm]["max_new_tokens"]
    assert call["state"] == "received" and call["actual"] == 101
    preparation = json.loads(snapshot["calls"][0]["request"])["arguments"]
    assert preparation == {"world": "version_correction/dev_a", "source_id": "current_values", "source_version": 2}
    assert row["citations_origin"] == ("runtime_supplied" if arm == "direct_json_256" else "model_supplied")


def test_failed_response_is_a_known_task_failure_and_is_not_retried(tmp_path):
    model = Instrument('{"value":0}')
    row, account, snapshot = run(tmp_path, "direct_json_256", model)
    assert row["public_accepted"] and row["objective_success"] is False
    assert row["status"] == "VALID_KNOWN" and len(model.requests) == 1
    assert account["known_tokens_complete"] and snapshot["unknown_calls"] == 0


def test_context_refusal_preserves_charged_preparation_without_dispatch(tmp_path):
    model = Instrument("unused", prompt_tokens=1025)
    row, account, snapshot = run(tmp_path, "envelope_1024", model)
    assert row["status"] == "INVALID_ABORT" and row["objective_success"] is None
    assert row["error"]["stage"] == "context_preflight" and model.requests == []
    assert row["metrics"]["tool_calls"] == 1 and row["metrics"]["preparation_tools"] == 1
    assert account["held_call_slots"] == 0 and snapshot["unknown_calls"] == 0


def test_unknown_post_dispatch_spending_retains_invalid_status_and_upper_bound(tmp_path):
    model = Instrument("unused", prompt_tokens=1024, fail=True)
    row, account, snapshot = run(tmp_path, "envelope_1024", model)
    assert row["status"] == "INVALID_ABORT" and row["complete"] is False
    assert row["objective_success"] is None and row["public_accepted"] is None
    assert len(model.requests) == 1
    assert row["error"]["stage"] == "model_dispatch"
    assert snapshot["run"]["status"] == "cancelled" and snapshot["unknown_calls"] == 1
    assert account["held_token_upper_bound"] == account["allotments"][0]["unknown_tokens"] == 2048
    assert account["known_tokens"] == 0 and account["held_call_slots"] == 1
    model_call = next(c for c in snapshot["calls"] if c["action"] == "model.generate")
    assert model_call["actual"] is None and model_call["state"] == "dispatched"
