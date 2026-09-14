"""Behavior checks for the new public-task/hidden-objective boundary."""
from copy import deepcopy
import json

import pytest

from pheroos_bench import coordination_repair_v1_tasks as tasks


def _current(world, step=2):
    view = tasks.public_world(world, step)
    receipts = [tasks.inspect(world, step, s["source_id"]) for s in view["sources"] if s["required"]]
    return view, receipts


def test_split_and_public_interfaces_are_declared_without_answer_leak():
    development, pilot = tasks.worlds(), tasks.worlds("pilot")
    assert len(development) == 8 and len(pilot) == 4
    assert not set(development) & set(pilot)
    for world in development + pilot:
        public = tasks.public_world(world, 0)
        assert "content" not in json.dumps(public)
        assert "index_entry" not in json.dumps(public)
        assert "function_name" not in json.dumps(public)
        required = [s for s in public["sources"] if s["required"]]
        assert 1 <= len(required) <= 3
        assert public["work_dag"][-1]["dependencies"] == ["inspect:" + s["source_id"] for s in required]
        for action in public["legal_inspections"]:
            result = tasks.execute(world, 0, json.dumps(action), [])
            assert result["valid"]
            assert tasks.verify_artifact(world, result["artifact"])


@pytest.mark.parametrize("n", [1, 2, 4])
@pytest.mark.parametrize("world", tasks.worlds() + tasks.worlds("pilot"))
@pytest.mark.parametrize("starting_step", [0, 2])
def test_reference_completes_through_public_tools_under_twelve_total_actions(world, n, starting_step):
    receipts, assignments, final = [], [], None
    for offset in range(12):
        step = starting_step + offset
        public = tasks.public_world(world, step)
        action = tasks.reference_action(public, receipts)
        # Logical owners share exactly these metered receipts. N grants no extra
        # model/tool opportunities or hidden information to this instrument.
        assignments.append(offset % n)
        result = tasks.execute(world, step, json.dumps(action), receipts)
        assert result["valid"], result
        if action["action"] == "inspect":
            receipts.append(result["artifact"])
        else:
            final = result["artifact"]
            if public["update_step"] is None or step >= public["update_step"]:
                break
    assert len(assignments) <= 12
    assert tasks.score(world, step, final)
    assert len(receipts) >= len([s for s in public["sources"] if s["required"]])


def test_reference_is_public_argument_only_and_does_not_read_hidden_tables(monkeypatch):
    world = "inventory_reconciliation/dev_a"
    public, receipts = _current(world)
    expected = tasks.reference_action(public, receipts)
    monkeypatch.setattr(tasks, "_INPUTS", {})
    monkeypatch.setattr(tasks, "_EXPECTED", {})
    for name in ("inspect", "verify_artifact", "score"):
        monkeypatch.setattr(tasks, name, lambda *args: pytest.fail("hidden fixture/tool access"))
    assert tasks.reference_action(public, receipts) == expected


def test_wrong_semantic_answer_passes_public_and_fails_hidden():
    world = "interval_intersection/dev_a"
    public, receipts = _current(world)
    action = tasks.reference_action(public, receipts)
    action["answer"]["selection"] = 777
    result = tasks.execute(world, 2, json.dumps(action), receipts)
    assert result["valid"] and result["stage"] == "accepted"
    assert not tasks.score(world, 2, result["artifact"])


def test_execute_never_uses_hidden_evaluator(monkeypatch):
    world = "dependency_readiness/dev_a"
    public, receipts = _current(world)
    action = tasks.reference_action(public, receipts)
    monkeypatch.setattr(tasks, "_EXPECTED", {})
    monkeypatch.setattr(tasks, "score", lambda *args: pytest.fail("hidden evaluation"))
    assert tasks.execute(world, 2, json.dumps(action), receipts)["valid"]


def test_sources_update_and_historical_receipts_remain_verifiable_not_current():
    world = "version_correction/dev_a"
    old = tasks.inspect(world, 0, "current_values")
    new = tasks.inspect(world, 2, "current_values")
    assert old["source_version"] == 1 and new["source_version"] == 2
    assert old["content"] != new["content"]
    assert old["receipt_identity"] != new["receipt_identity"]
    assert tasks.verify_artifact(world, old) and tasks.verify_artifact(world, new)
    old_action = tasks.reference_action(tasks.public_world(world, 0), [old])
    result = tasks.execute(world, 2, json.dumps(old_action), [old])
    assert result["stage"] == "missing_or_stale_evidence"
    assert tasks.reference_action(tasks.public_world(world, 2), [old]) == {"action": "inspect", "target": "current_values"}


def test_duplicate_or_reordered_receipts_do_not_create_extra_required_support():
    world = "inventory_reconciliation/dev_a"
    public, receipts = _current(world)
    action = tasks.reference_action(public, receipts)
    shuffled = list(reversed(receipts)) + [receipts[0], receipts[0]]
    result = tasks.execute(world, 2, json.dumps(action), shuffled)
    assert result["valid"]
    assert len(result["artifact"]["citations"]) == 3
    action["citations"].append(action["citations"][0])
    assert tasks.execute(world, 2, json.dumps(action), shuffled)["stage"] == "missing_or_stale_evidence"


def test_forged_stale_cross_world_and_irrelevant_evidence_are_not_authority():
    world = "version_correction/dev_a"
    public, receipts = _current(world)
    action = tasks.reference_action(public, receipts)
    forged = deepcopy(receipts)
    forged[0]["content"]["values"]["north"] = 999
    assert not tasks.verify_artifact(world, forged[0])
    assert tasks.execute(world, 2, json.dumps(action), forged)["stage"] == "missing_or_stale_evidence"
    cross_world = tasks.inspect("version_correction/dev_b", 2, "current_values")
    assert not tasks.verify_artifact(world, cross_world)
    assert tasks.execute(world, 2, json.dumps(action), [cross_world])["stage"] == "missing_or_stale_evidence"
    irrelevant = tasks.inspect(world, 2, "unrelated_notice")
    assert tasks.verify_artifact(world, irrelevant)
    assert tasks.execute(world, 2, json.dumps(action), [irrelevant])["stage"] == "missing_or_stale_evidence"
    action["citations"][0]["source_version"] = 1
    assert tasks.execute(world, 2, json.dumps(action), receipts)["stage"] == "missing_or_stale_evidence"


def test_parse_action_never_executes_inspection(monkeypatch):
    monkeypatch.setattr(tasks, "inspect", lambda *args: pytest.fail("parse executed a source inspection"))
    result = tasks.parse_action("interval_intersection/dev_a", 0, '{"action":"inspect","target":"preference"}')
    assert result["valid"] and result["artifact"] is None
    assert result["normalized_action"] == {"action": "inspect", "target": "preference"}


@pytest.mark.parametrize("raw,stage", [
    ('{"action":"inspect","action":"submit","target":"preference"}', "transport_format"),
    ('{"action":"inspect","target":"preference","x":NaN}', "transport_format"),
    ('[]', "action_schema"),
    ('{"action":"inspect","target":{}}', "action_schema"),
    ('{"action":"inspect","target":"index_entry"}', "undeclared_target"),
    ('{"action":"inspect","target":"preference","extra":0}', "action_schema"),
    ('{"action":"execute","target":"preference"}', "action_schema"),
])
def test_failure_taxonomy_retains_invalid_actions(raw, stage):
    result = tasks.execute("interval_intersection/dev_a", 0, raw, [])
    assert not result["valid"] and result["artifact"] is None
    assert result["stage"] == stage


def test_single_fence_is_disclosed_syntax_only_and_extra_prose_rejected():
    raw = '{"action":"inspect","target":"preference"}'
    plain = tasks.execute("interval_intersection/dev_a", 0, raw, [])
    fenced = tasks.execute("interval_intersection/dev_a", 0, "```json\n" + raw + "\n```", [])
    assert plain["artifact"] == fenced["artifact"]
    assert fenced["framing"] == "single_json_fence"
    assert fenced["normalized_action"] == json.loads(raw)
    assert not tasks.execute("interval_intersection/dev_a", 0, "Answer: " + raw, [])["valid"]


def test_mutation_does_not_change_future_public_tools_and_materialization_is_bounded():
    world = "version_correction/dev_a"
    public, receipts = _current(world)
    receipts[0]["content"]["values"]["north"] = 888
    assert tasks.inspect(world, 2, "current_values")["content"]["values"]["north"] == 11
    public, receipts = _current(world)
    action = tasks.reference_action(public, receipts)
    assert tasks.execute(world, 2, json.dumps(action), receipts * 17)["stage"] == "missing_or_stale_evidence"
    assert not tasks.execute(world, 2, " " * (tasks.ACTION_BYTES + 1), [])["valid"]
