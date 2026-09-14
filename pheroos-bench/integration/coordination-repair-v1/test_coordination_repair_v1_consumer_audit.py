"""Independent behavior checks using the real Session authorization boundary.

The adapter is a metered deterministic test double, never a live model study.
These tests require an installed/importable experimental coordination Session;
missing runtime support is a failure, not a skipped integration pass.
"""
from collections import Counter
import json

import pytest

from pheroos_runtime.campaign_v1 import CampaignBudget
from pheroos_bench import coordination_repair_v1 as consumer
from pheroos_bench import coordination_repair_v1_tasks as tasks
from pheroos_bench.coordination_repair_v1_measurement import analyze_forks


class PublicModel:
    identity = {"adapter": "test_public_rule_model_v1", "live_model": False}

    def __init__(self, behavior="reference"):
        self.behavior = behavior
        self.calls = 0

    def count_tokens(self, messages):
        # Synthetic token units are explicit; only accounting behavior is tested.
        return 32

    def generate(self, messages, max_new_tokens, seed):
        self.calls += 1
        prompt = json.loads(messages[-1]["content"])
        public, receipts = prompt["task"], prompt["tool_receipts"]
        if self.behavior == "repeat":
            action = {"action": "inspect", "target": "preference"}
        elif self.behavior == "reject_first" and self.calls == 1:
            action = {"action": "inspect", "target": "not_a_public_source"}
        else:
            action = tasks.reference_action(public, receipts)
            if action["action"] == "inspect":
                action["target"] = prompt["suggested_work"]
            if self.behavior == "wrong_answer" and action["action"] == "submit":
                action["answer"] = {"selection": 777}
            if self.behavior == "inspect_in_D0":
                action = {"action": "inspect", "target": "preference"}
        return {"text": "x" * 70000 if self.behavior == "oversized" else json.dumps(action), "prompt_tokens": 32, "completion_tokens": 16,
                "elapsed_ns": 1}


def run(tmp_path, name, *, arm="single", n=1, behavior="reference", condition="D2", steps=6, capture_step=None):
    campaign = CampaignBudget.create(tmp_path / (name + "-campaign.sqlite"),
        token_cap=20000, dispatch_cap=20, config_digest="3" * 64)
    episode = consumer.run_episode(world="interval_intersection/dev_a", arm=arm, n=n,
        output=tmp_path / name, model=PublicModel(behavior), campaign=campaign,
        allocation_id=name, condition=condition, steps=steps, token_cap=16384, capture_step=capture_step)
    snapshot = json.loads((tmp_path / name / "session-snapshot.json").read_text())
    return episode, snapshot, campaign.snapshot()


def test_D0_preparation_is_charged_and_hidden_failure_does_not_extend_run(tmp_path):
    episode, snapshot, campaign = run(tmp_path, "wrong", condition="D0", behavior="wrong_answer")
    assert episode["status"] == "VALID_KNOWN"
    assert episode["success"] is False
    assert episode["stop"] == "public_accepted_submission"
    assert len(episode["turns"]) == 1
    assert len(episode["preparations"]) == 3
    inspections = [c for c in snapshot["calls"] if c["action"] == "tool.evaluate"
                   and json.loads(c["request"])["tool_ref"] == "inspect_source"]
    assert len(inspections) == 3
    assert episode["metrics"]["tool_calls"] >= 4
    assert episode["metrics"]["tokens"] == 48
    assert campaign["known_tokens"] == 48
    assert not campaign["violation"]


def test_D0_rejection_is_in_actual_settled_validation_receipt(tmp_path):
    episode, snapshot, _ = run(tmp_path, "D0inspect", condition="D0", behavior="inspect_in_D0")
    row = episode["turns"][0]
    assert not row["validation"]["valid"]
    call = next(c for c in snapshot["calls"] if c["id"] == "validate-0")
    settled = json.loads(call["response"])["artifact"]
    assert settled == row["validation"]
    assert settled["stage"] == "action_schema"
    assert episode["metrics"]["inspection_dispatches"] == 3


def test_candidate_reuse_reduces_tool_execution_not_only_prompt_duplicates(tmp_path):
    candidate, c_snapshot, _ = run(tmp_path, "reuse", arm="candidate", n=2, behavior="repeat", steps=3)
    baseline, b_snapshot, _ = run(tmp_path, "baseline", arm="blackboard", n=2, behavior="repeat", steps=3)
    assert candidate["status"] == baseline["status"] == "VALID_KNOWN"
    assert candidate["metrics"]["model_calls"] == baseline["metrics"]["model_calls"] == 3
    assert candidate["metrics"]["inspection_dispatches"] == 1
    assert candidate["metrics"]["artifact_reuse"] == 2
    assert baseline["metrics"]["inspection_dispatches"] == 3
    assert candidate["metrics"]["tokens"] == baseline["metrics"]["tokens"] == 144
    for snapshot, expected in ((c_snapshot, 1), (b_snapshot, 3)):
        assert sum(c["action"] == "tool.evaluate" and json.loads(c["request"])["tool_ref"] == "inspect_source"
                   for c in snapshot["calls"]) == expected
    assert candidate["success"] is baseline["success"] is False


def test_failure_pressure_changes_actual_next_source_without_hiding_rejection(tmp_path):
    candidate, _, _ = run(tmp_path, "candidatefailure", arm="candidate", n=2, behavior="reject_first")
    baseline, _, _ = run(tmp_path, "baselinefailure", arm="blackboard", n=2, behavior="reject_first")
    assert candidate["success"] is baseline["success"] is True
    assert candidate["metrics"]["invalid_actions"] == baseline["metrics"]["invalid_actions"] == 1
    assert candidate["turns"][0]["validation"]["stage"] == "undeclared_target"
    assert candidate["turns"][1]["validation"]["normalized_action"]["target"] != baseline["turns"][1]["validation"]["normalized_action"]["target"]
    assert candidate["metrics"]["failure_stages"] == {"undeclared_target": 1}


def test_owner_pressure_reassignment_is_not_just_agent_relabeling():
    public = tasks.public_world("interval_intersection/dev_a", 0)
    agents = ["agent0", "agent1"]
    manifests = {a: [] for a in agents}
    fresh = consumer.choose_work("candidate", agents, public, manifests, 0, Counter())
    control = consumer.choose_work("blackboard", agents, public, manifests, 0, Counter())
    assert fresh == control  # Public FIFO tie order is shared until feedback differs.
    failed = Counter({fresh: 1})
    after = consumer.choose_work("candidate", agents, public, manifests, 1, failed)
    baseline = consumer.choose_work("blackboard", agents, public, manifests, 1, failed)
    assert after[1] != baseline[1]


def test_rejected_response_bytes_retain_known_usage_without_task_success(tmp_path):
    episode, snapshot, campaign = run(tmp_path, "oversized", behavior="oversized", steps=2)
    assert episode["status"] == "INVALID_ABORT"
    assert episode["success"] is None
    call = next(c for c in snapshot["calls"] if c["action"] == "model.generate")
    assert call["state"] == "response_rejected"
    assert call["actual"] == 48
    assert episode["metrics"]["input_tokens"] == 32
    assert episode["metrics"]["output_tokens"] == 16
    assert episode["metrics"]["unknown_calls"] == 0
    assert campaign["known_tokens"] == 48


def test_prefix_knowledge_unions_all_duplicate_receipt_publishers(tmp_path):
    episode, _, _ = run(tmp_path, "duplicateprefix", arm="blackboard", n=2,
                        behavior="repeat", steps=2, capture_step=1)
    prefix = episode["captured_prefix"]
    assert len(prefix["history"]) == 2
    identity = prefix["history"][0]["value"]["receipt_identity"]
    assert identity == prefix["history"][1]["value"]["receipt_identity"]
    assert set(prefix["knowledge_readers"][identity]) == {"agent0", "agent1"}


@pytest.mark.parametrize("status,unknown", [("UNDECLARED_STATUS", 0), ("VALID_KNOWN", -1)])
def test_nested_measurement_rejects_undeclared_or_negative_accounting(status, unknown):
    prefixes = [dict(world_id="w", prefix_id="p", eligible=True, prefix_tokens=7)]
    records = [dict(world_id="w", prefix_id="p", branch=b, status=status, success=False,
                    incremental_tokens=9, unknown_calls=unknown)
               for b in ("relevant", "withheld", "irrelevant")]
    assert analyze_forks(prefixes, records)["status"] == "INVALID_ABORT"


def prefix_parent():
    world = "interval_intersection/dev_a"
    lower, upper = [tasks.inspect(world, 0, s) for s in ("lower_bounds", "upper_bounds")]
    history = [dict(value=value, publisher=agent, turn=turn, ref="ref-" + str(turn),
                    origin=dict(session="/test/parent.sqlite", artifact_ref="ref-" + str(turn)))
               for turn, (value, agent) in enumerate(((lower, "agent0"), (upper, "agent1")))]
    return dict(world_id=world, scope_id="parent-scope", arm="candidate", n=2, token_cap=16384,
        metrics={"tokens": 240},
        captured_prefix=dict(world_id=world, prefix_id="step-1", next_step=2, next_scheduler_turn=2,
            remaining_steps=4, history=history, private_feedback={"agent0": [], "agent1": []},
            prefix_tokens=96, prefix_hash="a" * 64, submission=None, model_seed=2720,
            knowledge_readers={lower["receipt_identity"]: ["agent0", "agent1"],
                               upper["receipt_identity"]: ["agent1"]},
            failure_pressure=[dict(agent="agent0", target="lower_bounds", count=2)]))


def test_forks_preserve_prior_private_knowledge_and_scheduler_state(tmp_path, monkeypatch):
    from pheroos_bench import coordination_repair_v1_forks as forks
    parent, invocations = prefix_parent(), []

    def record_rollout(**arguments):
        invocations.append(arguments)
        return dict(scope_id=str(arguments["output"]), status="VALID_KNOWN", success=False,
                    metrics=dict(tokens=48, unknown_calls=0, invalid_actions=1), turns=[], stop="budget_deadline_stop")

    monkeypatch.setattr(forks, "run_episode", record_rollout)
    prefix, records, _ = forks.full_rollouts(parent, output=tmp_path / "forks")
    assert prefix["eligible"]
    assert len(invocations) == len(records) == 3
    for branch, invocation in zip(forks.BRANCHES, invocations):
        values = {i["value"]["source_id"]: i for i in invocation["imports"]}
        # agent1 already read lower_bounds before the fork, so withholding cannot
        # erase it. Upper_bounds was only known to its publisher at that prefix.
        assert set(values["lower_bounds"]["readers"]) == {"agent0", "agent1"}
        assert set(values["upper_bounds"]["readers"]) == ({"agent0", "agent1"} if branch == "relevant" else {"agent1"})
        assert invocation["scheduler_offset"] == 2
        assert invocation["initial_failures"] == parent["captured_prefix"]["failure_pressure"]
        assert invocation["seed"] == 2720
        assert invocation["steps"] == 4
        assert invocation["token_cap"] == 16384 - 96


def test_fork_eligibility_excludes_already_shared_sources_without_using_success():
    from pheroos_bench import coordination_repair_v1_forks as forks
    parent = prefix_parent()
    parent["success"] = True  # Eligibility is a public knowledge condition.
    assert forks.prepare_prefix(parent)["eligible"]
    parent["success"] = False
    for readers in parent["captured_prefix"]["knowledge_readers"].values():
        readers[:] = ["agent0", "agent1"]
    assert not forks.prepare_prefix(parent)["eligible"]
