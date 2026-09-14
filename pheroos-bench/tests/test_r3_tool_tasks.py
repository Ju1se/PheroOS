from copy import deepcopy
from hashlib import sha256
import json

import pytest

from pheroos_bench import r3_tool_tasks as tasks


CLAMP = "code_repair/clamp"
CHUNKS = "code_repair/chunk_count"
DISPATCH = "evidence_revision/dispatch_limit"
ROUTE = "evidence_revision/channel_route"
CLAMP_PATCH = ["def clamp(value, lower, upper):", "    return max(lower, min(value, upper))"]
CHUNKS_PATCH = ["def chunk_count(total, width):", "    return (total + width - 1) // width"]


def submit(lines):
    return json.dumps({"action": "submit", "candidate": {"code_lines": lines}})


def inspect(target):
    return json.dumps({"action": "inspect", "target": target})


def evidence(lane, units, version):
    return json.dumps({"action": "submit", "candidate": {
        "answer": {"lane": lane, "max_units": units},
        "citations": [{"source_id": "policy", "version": 1},
                      {"source_id": "capacity", "version": version}],
    }})


def record(world, step, result, arm="blackboard"):
    return dict(result, id=f"receipt-{step}", step=step, agent=tasks.agent_for(arm, step),
                task_version=tasks.version(world, step), receipt_digest=sha256(
                    json.dumps(result["artifact"], sort_keys=True).encode()).hexdigest())


def public_task(world, step=0, memory=()):
    return json.loads(tasks.messages_for(world, step, memory)[1]["content"])["task"]


def test_fixed_worlds_and_update_schedule_do_not_depend_on_arm():
    assert tasks.world_ids() == [CLAMP, CHUNKS, DISPATCH, ROUTE]
    tasks.world_ids().clear()
    assert len(tasks.world_ids()) == 4
    for world in tasks.world_ids():
        assert [tasks.version(world, step) for step in range(6)] == (
            [1] * 6 if world.startswith("code_") else [1, 1, 1, 2, 2, 2]
        )


@pytest.mark.parametrize("step", [-1, 6, True, 1.0, "0"])
def test_six_turn_bound_is_explicit(step):
    with pytest.raises(ValueError):
        tasks.version(CLAMP, step)
    with pytest.raises(ValueError):
        tasks.agent_for("single", step)


def test_unknown_world_and_arm_are_rejected():
    with pytest.raises(ValueError):
        tasks.version("unknown", 0)
    with pytest.raises(ValueError):
        tasks.agent_for("unknown", 0)


@pytest.mark.parametrize("world", [DISPATCH, ROUTE])
def test_documents_are_not_disclosed_before_inspection(world):
    task = public_task(world)
    assert task["source_index"] == [{"source_id": "policy", "version": 1},
                                    {"source_id": "capacity", "version": 1}]
    assert "documents" not in task
    encoded = json.dumps(tasks.messages_for(world, 0, []))
    assert '"content": {' not in encoded
    assert "blue" not in encoded and "alpha" not in encoded and "beta" not in encoded
    assert "request_limit\": 6" not in encoded
    assert public_task(world, 3)["source_index"][1]["version"] == 2


@pytest.mark.parametrize("world,index", [(CLAMP, ["below_lower", "inside_bounds", "above_upper"]),
                                         (CHUNKS, ["empty", "full_chunks", "partial_chunk"])])
def test_tests_are_indexed_without_arguments_or_expected_values(world, index):
    task = public_task(world)
    assert task["test_index"] == index
    assert "visible_tests" not in task
    assert "arguments" not in task and "expected" not in task
    assert task["workspace_code_lines"] == task["original_source"].splitlines()
    assert "hidden" not in json.dumps(task)
    task["test_index"].clear()
    assert public_task(world)["test_index"] == index


@pytest.mark.parametrize("world,target,arguments,expected,actual", [
    (CLAMP, "above_upper", [9, 0, 5], 5, 4),
    (CHUNKS, "partial_chunk", [9, 4], 3, 2),
])
def test_inspection_runs_actual_buggy_code(world, target, arguments, expected, actual):
    result = tasks.apply(world, 0, [], inspect(target))
    assert result["valid"]  # A failing test is a valid tool receipt.
    assert result["action"] == "inspect"
    assert result["semantic_action"] == {"action": "inspect", "target": target}
    artifact = result["artifact"]
    assert artifact["world_id"] == world and artifact["task_version"] == 1
    assert artifact["kind"] == "test_receipt"
    receipt = artifact["receipt"]
    assert receipt["arguments"] == arguments
    assert receipt["expected"] == expected and receipt["actual"] == actual
    assert receipt["passed"] is False
    assert "failed" in result["feedback"]


@pytest.mark.parametrize("world,lines,target,expected", [
    (CLAMP, CLAMP_PATCH, "above_upper", 5),
    (CHUNKS, CHUNKS_PATCH, "partial_chunk", 3),
])
def test_verified_patch_changes_receipt_derived_workspace(world, lines, target, expected):
    submitted = tasks.apply(world, 0, [], submit(lines))
    assert submitted["valid"]
    assert submitted["artifact"]["receipt"]["candidate"] == {"code_lines": lines}
    memory = [record(world, 0, submitted)]
    assert public_task(world, 1, memory)["workspace_code_lines"] == lines
    test = tasks.apply(world, 1, memory, inspect(target))
    assert test["artifact"]["receipt"]["actual"] == expected
    assert test["artifact"]["receipt"]["passed"]
    original = tasks.apply(world, 1, [], inspect(target))
    assert not original["artifact"]["receipt"]["passed"]
    assert test["artifact"]["receipt"]["workspace_digest"] != original["artifact"]["receipt"]["workspace_digest"]
    assert tasks.score(world, 5, memory)


def test_only_one_line_per_code_lines_item_is_accepted():
    accepted = tasks.apply(CLAMP, 0, [], submit(CLAMP_PATCH))
    assert accepted["valid"]
    for lines in [[], "\n".join(CLAMP_PATCH), [1], ["\n".join(CLAMP_PATCH)], ["x\ry"]]:
        result = tasks.apply(CLAMP, 0, [], submit(lines))
        assert not result["valid"]
        assert result["artifact"] is None
    alternate = json.dumps({"action": "submit", "candidate": {"code": "\n".join(CLAMP_PATCH)}})
    assert not tasks.apply(CLAMP, 0, [], alternate)["valid"]


def test_final_hidden_failure_is_not_model_feedback_or_artifact_selection_oracle():
    # Passes all visible cases, but violates the contract for other bounds.
    overfit = ["def clamp(value, lower, upper):", "    return max(0, min(value, 5))"]
    accepted = tasks.apply(CLAMP, 0, [], submit(overfit))
    assert accepted["valid"]
    memory = [record(CLAMP, 0, accepted)]
    before = tasks.messages_for(CLAMP, 1, memory)
    assert not tasks.score(CLAMP, 5, memory)
    assert tasks.messages_for(CLAMP, 1, memory) == before
    assert "Final verification" not in json.dumps(before)
    assert accepted["artifact"]["receipt"]["verification"] == "visible_checks_only"
    good = record(CLAMP, 0, tasks.apply(CLAMP, 0, [], submit(CLAMP_PATCH)))
    bad = record(CLAMP, 1, tasks.apply(CLAMP, 1, [], submit(overfit)))
    assert not tasks.score(CLAMP, 5, [good, bad])  # Latest public-valid candidate wins.


def test_inspection_never_replaces_latest_submission_in_scorer():
    patch = record(CHUNKS, 0, tasks.apply(CHUNKS, 0, [], submit(CHUNKS_PATCH)))
    receipt = record(CHUNKS, 1, tasks.apply(CHUNKS, 1, [patch], inspect("partial_chunk")))
    assert tasks.score(CHUNKS, 5, [patch, receipt])
    assert not tasks.score(CHUNKS, 5, [receipt])


def test_source_inspection_returns_exact_current_closed_document():
    before = tasks.apply(DISPATCH, 2, [], inspect("capacity"))
    after = tasks.apply(DISPATCH, 3, [], inspect("capacity"))
    assert before["artifact"]["receipt"] == {"source_id": "capacity", "version": 1,
                                             "content": {"blue": 9, "green": 4}}
    assert after["artifact"]["receipt"] == {"source_id": "capacity", "version": 2,
                                            "content": {"blue": 3, "green": 8}}
    assert before["artifact"]["task_version"] == 1
    assert after["artifact"]["task_version"] == 2
    before["artifact"]["receipt"]["content"]["blue"] = 999
    assert tasks.apply(DISPATCH, 2, [], inspect("capacity"))["artifact"]["receipt"]["content"]["blue"] == 9


@pytest.mark.parametrize("world,before,after", [
    (DISPATCH, ("blue", 6), ("blue", 3)), (ROUTE, ("alpha", 2), ("beta", 4)),
])
def test_stale_evidence_is_rejected_and_not_selected(world, before, after):
    old = tasks.apply(world, 2, [], evidence(*before, 1))
    assert old["valid"]
    records = [record(world, 2, old)]
    assert not tasks.score(world, 5, records)
    stale = tasks.apply(world, 3, records, evidence(*before, 1))
    assert not stale["valid"]
    assert stale["semantic_action"]["invalid"]
    current = tasks.apply(world, 3, records, evidence(*after, 2))
    assert current["valid"]
    assert current["semantic_action"]["answer"] == {"lane": after[0], "max_units": after[1]}
    assert tasks.score(world, 5, records + [record(world, 3, current)])


def test_declared_agent_allocation_and_independent_memory():
    assert [tasks.agent_for("single", i) for i in range(6)] == ["agent0"] * 6
    assert [tasks.agent_for("independent", i) for i in range(6)] == ["agent0"] * 3 + ["agent1"] * 3
    assert [tasks.agent_for("manager_graph", i) for i in range(6)] == ["agent0", "agent0", "agent1", "agent1", "agent2", "agent2"]
    records = [record(DISPATCH, i, tasks.apply(DISPATCH, i, [], inspect("policy")), "independent")
               for i in range(5)]
    assert tasks.memory_for("independent", records, 3, 2) == []
    assert [r["step"] for r in tasks.memory_for("independent", records, 5, 2)] == [3, 4]
    assert [r["step"] for r in tasks.memory_for("single", records, 5, 2)] == list(range(5))
    assert [r["step"] for r in tasks.memory_for("manager_graph", records, 5, 2)] == [3, 4]
    assert [r["step"] for r in tasks.memory_for("blackboard", records, 5, 2)] == [2, 3, 4]
    selected = tasks.memory_for("single", records, 5, 2)
    selected[0]["feedback"] = "mutated"
    assert records[0]["feedback"] != "mutated"


def test_versioned_memory_discards_old_receipts_and_deduplicates_clones():
    old = record(DISPATCH, 2, tasks.apply(DISPATCH, 2, [], inspect("capacity")))
    current = record(DISPATCH, 3, tasks.apply(DISPATCH, 3, [], inspect("capacity")))
    clone = deepcopy(current)
    clone.update(id="clone", agent="clone-agent", step=4)
    selected = tasks.memory_for("versioned_blackboard", [old, current, clone], 5, 2)
    assert selected == [clone]
    assert tasks.memory_for("blackboard", [old, current, clone], 5, 2) == [old, current, clone]


def test_action_semantics_ignore_code_serialization_and_evidence_citation_order():
    left = tasks.apply(CLAMP, 0, [], submit(CLAMP_PATCH))
    right = tasks.apply(CLAMP, 0, [], submit([
        "def clamp(value, lower, upper):", "    result = min(upper, max(lower, value))", "    return result"
    ]))
    assert left["semantic_action"] == right["semantic_action"]
    assert left["semantic_action"]["probe_outputs"] == [-1, 0, 1, 1]
    request = json.loads(evidence("blue", 3, 2))
    first = tasks.apply(DISPATCH, 3, [], json.dumps(request))
    request["candidate"]["citations"].reverse()
    second = tasks.apply(DISPATCH, 3, [], json.dumps(request))
    assert first["semantic_action"] == second["semantic_action"]


@pytest.mark.parametrize("text", [
    "null", "[]", "garbage", '{"action":"inspect","target":"unknown"}',
    '{"action":"reuse"}', '{"action":"finish"}',
    '{"action":"inspect","target":"capacity","extra":1}',
    '{"action":"inspect","target":null}',
    '{"action":"submit"}', '{"action":"submit","candidate":[]}',
    '{"action":"inspect","action":"submit","target":"capacity"}',
    '{"action":"submit","candidate":{"answer":NaN}}',
    '```json\n{"action":"inspect","target":"capacity"}\n```',
    '{"action":"submit","candidate":{"code_lines":["```python","x","```"]}}',
])
def test_malformed_or_undeclared_actions_are_explicit_failures(text):
    result = tasks.apply(DISPATCH, 0, [], text)
    assert result["valid"] is False
    assert result["artifact"] is None
    assert result["semantic_action"]["invalid"] is True
    assert result["feedback"]


def test_nested_code_fences_and_unknown_code_inspection_fail():
    assert not tasks.apply(CLAMP, 0, [], submit(["```python", *CLAMP_PATCH, "```"]))["valid"]
    assert not tasks.apply(CLAMP, 0, [], inspect("capacity"))["valid"]
    assert not tasks.apply(DISPATCH, 0, [], inspect("above_upper"))["valid"]


def test_wrong_world_or_invalid_receipt_cannot_patch_workspace():
    patch = record(CLAMP, 0, tasks.apply(CLAMP, 0, [], submit(CLAMP_PATCH)))
    invalid = deepcopy(patch)
    invalid["valid"] = False
    wrong_world = deepcopy(patch)
    wrong_world["artifact"]["world_id"] = CHUNKS
    for entry in [invalid, wrong_world]:
        result = tasks.apply(CLAMP, 1, [entry], inspect("above_upper"))
        assert not result["artifact"]["receipt"]["passed"]
        assert not tasks.score(CLAMP, 5, [entry])


def test_receipts_from_current_or_future_turn_cannot_change_prior_workspace():
    patch = record(CLAMP, 3, tasks.apply(CLAMP, 3, [], submit(CLAMP_PATCH)))
    for step in (1, 3):
        receipt = tasks.apply(CLAMP, step, [patch], inspect("above_upper"))
        assert not receipt["artifact"]["receipt"]["passed"]
    assert not tasks.score(CLAMP, 2, [patch])
    assert tasks.score(CLAMP, 3, [patch])
