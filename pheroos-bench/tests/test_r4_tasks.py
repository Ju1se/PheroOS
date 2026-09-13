"""Behavior counterexamples for the new finite R4 environment, without models."""

from copy import deepcopy
import json

import pytest

from pheroos_bench import r4_tasks as tasks
from pheroos_bench.r3_framed_pilot import frame


CODE_A, CODE_B, EVIDENCE_A, EVIDENCE_B = tasks.world_ids()
SOLUTIONS = {
    CODE_A: ["def bounded_increment(value, increment, ceiling):", "    return min(value + increment, ceiling)"],
    CODE_B: ["def cyclic_offset(start, distance, size):", "    return (start + distance) % size"],
}
TARGETS = {EVIDENCE_A: ["route_policy", "route_capacity", "route_ceiling"],
           EVIDENCE_B: ["ready_policy", "ready_state", "ready_limits"]}


def record(world, step, request, memory=None, agent="agent0"):
    result = tasks.apply(world, step, memory or [], json.dumps(request))
    return dict(result, step=step, agent=agent)


def inspect(world, step, target, *, agent="agent0", memory=None):
    return record(world, step, dict(action="inspect", target=target), memory, agent)


def inspected(world, start):
    return [inspect(world, start + i, target, agent=f"agent{i}") for i, target in enumerate(TARGETS[world])]


def submit_evidence(world, step, memory, lane, units):
    return record(world, step, dict(action="submit", candidate=dict(
        answer=dict(lane=lane, max_units=units),
        citations=[dict(source_id=target, version=tasks.task_version(world, step)) for target in TARGETS[world]])), memory)


@pytest.mark.parametrize("world", tasks.world_ids())
def test_fixed_32_global_turns_and_version_boundary(world):
    assert tasks.STEPS == 32
    assert [tasks.task_version(world, step) for step in range(32)] == (
        [1] * 32 if world.startswith("code_repair/") else [1] * 16 + [2] * 16)
    for invalid in (-1, 32, True, 1.0, "1"):
        with pytest.raises(ValueError):
            tasks.task_version(world, invalid)
    with pytest.raises(ValueError):
        tasks.task_version("code_repair/clamp", 0)


@pytest.mark.parametrize("n", [1, 2, 4, 8, 16, 32])
def test_all_declared_identities_act_under_same_global_task_schedule(n):
    agents = [f"agent{step % n}" for step in range(tasks.STEPS)]
    assert len(set(agents)) == n
    assert all(agents.count(agent) == 32 // n for agent in set(agents))
    for world in tasks.world_ids():
        for step in (0, 15, 16, 31):
            task = json.loads(tasks.messages_for(world, step, [])[1]["content"])["task"]
            assert task["turn"] == step + 1 and task["total_turns"] == 32
            assert "agent" not in json.dumps(task) and "agent_count" not in task
            if world in TARGETS:
                assert task["source_update_turn"] == 17
                assert [doc["source_id"] for doc in task["source_index"]] == TARGETS[world]
                assert all(doc["version"] == tasks.task_version(world, step) for doc in task["source_index"])


@pytest.mark.parametrize("world", [CODE_A, CODE_B])
def test_correct_code_passes_public_and_independent_hidden_grid(world):
    submitted = record(world, 0, dict(action="submit", candidate=dict(code_lines=SOLUTIONS[world])))
    assert submitted["valid"] is True
    assert tasks.score(world, 0, [submitted]) is True
    assert tasks.score(world, 31, [submitted]) is True


def test_public_test_overfit_does_not_pass_hidden_score_or_leak_checks(monkeypatch):
    lines = ["def bounded_increment(value, increment, ceiling):", "    if value == 2:",
             "        return 5", "    if value == 7:", "        return 8", "    return 4"]
    submitted = record(CODE_A, 0, dict(action="submit", candidate=dict(code_lines=lines)))
    assert submitted["valid"] is True
    assert tasks.score(CODE_A, 0, [submitted]) is False
    artifact = submitted["artifact"]["receipt"]
    assert set(artifact) == {"candidate", "public_test_outputs"}
    assert artifact["public_test_outputs"] == [5, 8, 4]
    monkeypatch.setattr(tasks, "score", lambda *args: pytest.fail("public action consulted hidden scorer"))
    assert record(CODE_A, 0, dict(action="submit", candidate=dict(code_lines=lines))) == submitted


def test_inspection_checks_actual_visible_workspace_and_changes_provenance():
    before = inspect(CODE_A, 0, "cross_ceiling")
    assert before["valid"] and before["artifact"]["receipt"]["passed"] is False
    patch = record(CODE_A, 1, dict(action="submit", candidate=dict(code_lines=SOLUTIONS[CODE_A])))
    after = inspect(CODE_A, 2, "cross_ceiling", memory=[patch])
    assert after["artifact"]["receipt"]["passed"] is True
    assert before["origin_identity"] != after["origin_identity"]
    detached = inspect(CODE_A, 3, "cross_ceiling")
    assert detached["artifact"]["receipt"]["passed"] is False
    assert detached["origin_identity"] == before["origin_identity"]


@pytest.mark.parametrize("world,version,lane,units", [
    (EVIDENCE_A, 1, "amber", 6), (EVIDENCE_A, 2, "amber", 3),
    (EVIDENCE_B, 1, "cedar", 4), (EVIDENCE_B, 2, "delta", 5),
])
def test_three_actual_current_inspections_then_answer(world, version, lane, units):
    start = 0 if version == 1 else 16
    memory = inspected(world, start)
    submitted = submit_evidence(world, start + 3, memory, lane, units)
    assert submitted["valid"] is True
    assert tasks.score(world, start + 3, memory + [submitted]) is True
    assert len(submitted["artifact"]["receipt"]["source_origins"]) == 3
    assert len(set(submitted["artifact"]["receipt"]["source_origins"])) == 3


def test_public_provenance_acceptance_is_not_answer_truth():
    memory = inspected(EVIDENCE_A, 0)
    wrong = submit_evidence(EVIDENCE_A, 3, memory, "invented_lane", 999)
    assert wrong["valid"] is True
    assert tasks.score(EVIDENCE_A, 3, memory + [wrong]) is False
    assert "hidden correctness was not checked" in wrong["feedback"]


@pytest.mark.parametrize("world,start,lane,units", [
    (EVIDENCE_A, 0, "amber", 6), (EVIDENCE_A, 16, "amber", 3),
    (EVIDENCE_B, 0, "cedar", 4), (EVIDENCE_B, 16, "delta", 5),
])
def test_submit_example_has_exact_current_citations_and_is_usable_after_inspection(world, start, lane, units):
    memory = inspected(world, start)
    task = json.loads(tasks.messages_for(world, start + 3, memory)[1]["content"])["task"]
    example = task["submit_example"]
    assert example["candidate"]["citations"] == task["source_index"]
    assert len(example["candidate"]["citations"]) == 3
    example["candidate"]["answer"] = dict(lane=lane, max_units=units)
    submitted = record(world, start + 3, example, memory)
    assert submitted["valid"] is True
    assert tasks.score(world, start + 3, memory + [submitted]) is True


def test_citations_alone_are_not_evidence_and_missing_source_cannot_be_invented():
    assert submit_evidence(EVIDENCE_A, 3, [], "amber", 6)["valid"] is False
    memory = inspected(EVIDENCE_A, 0)
    assert submit_evidence(EVIDENCE_A, 3, memory[:2], "amber", 6)["valid"] is False
    corrupt = deepcopy(memory)
    corrupt[1]["artifact"]["receipt"]["content"]["amber"] = 999
    assert submit_evidence(EVIDENCE_A, 3, corrupt, "amber", 6)["valid"] is False


def test_revision_rejects_old_receipts_and_old_submission_without_resurrecting_it():
    old = inspected(EVIDENCE_A, 0)
    submitted = submit_evidence(EVIDENCE_A, 3, old, "amber", 6)
    assert tasks.score(EVIDENCE_A, 15, old + [submitted]) is True
    assert tasks.score(EVIDENCE_A, 16, old + [submitted]) is False
    assert submit_evidence(EVIDENCE_A, 16, old, "amber", 3)["valid"] is False
    new = inspected(EVIDENCE_A, 16)
    assert all(a["origin_identity"] != b["origin_identity"] for a, b in zip(old, new))
    current = submit_evidence(EVIDENCE_A, 19, new, "amber", 3)
    assert tasks.score(EVIDENCE_A, 31, old + [submitted] + new + [current]) is True


def test_pre_revision_success_is_only_snapshot_success_under_common_final_objective():
    memory = inspected(EVIDENCE_A, 0)
    memory.append(submit_evidence(EVIDENCE_A, 3, memory, "amber", 6))
    assert tasks.score(EVIDENCE_A, 3, memory) is True
    # A slower deadline arm must not win by stopping before the common revision.
    assert tasks.score(EVIDENCE_A, 31, memory) is False


@pytest.mark.parametrize("mutation", [
    lambda c: c["citations"].pop(),
    lambda c: c["citations"].append(c["citations"][0]),
    lambda c: c["citations"][0].update(source_id="route_capacity"),
    lambda c: c["citations"][0].update(version=True),
    lambda c: c["citations"][0].update(version=2),
    lambda c: c["citations"][0].update(extra=1),
    lambda c: c["answer"].update(max_units=True),
    lambda c: c["answer"].update(max_units=-1),
    lambda c: c["answer"].update(extra=1),
])
def test_exact_evidence_schema_and_current_citation_versions(mutation):
    memory = inspected(EVIDENCE_A, 0)
    candidate = submit_evidence(EVIDENCE_A, 3, memory, "amber", 6)["artifact"]["receipt"]["candidate"]
    mutation(candidate)
    result = record(EVIDENCE_A, 3, dict(action="submit", candidate=candidate), memory)
    assert result["valid"] is False and result["artifact"] is None


def test_latest_publicly_valid_submission_is_selected_without_hidden_oracle():
    memory = inspected(EVIDENCE_A, 0)
    correct = submit_evidence(EVIDENCE_A, 3, memory, "amber", 6)
    wrong = submit_evidence(EVIDENCE_A, 4, memory, "amber", 2)
    assert tasks.score(EVIDENCE_A, 4, memory + [correct, wrong]) is False
    invalid = record(EVIDENCE_A, 5, {"action": "invent"})
    assert tasks.score(EVIDENCE_A, 5, memory + [correct, invalid]) is True


def test_private_visibility_and_anonymized_complete_shared_n_invariance():
    baseline = [inspect(EVIDENCE_A, step, TARGETS[EVIDENCE_A][step % 3]) for step in range(7)]
    for n in (1, 2, 4, 8, 16, 32):
        records = [dict(r, agent=f"agent{r['step'] % n}", id=f"N{n}:{r['step']}") for r in baseline]
        for policy in ("blackboard", "dedup_ttl", "versioned"):
            original_selected = tasks.select(policy, baseline, "agent0", 7, 1)
            selected = tasks.select(policy, records, f"agent{7 % n}", 7, 1)
            assert [r["origin_identity"] for r in selected] == [r["origin_identity"] for r in original_selected]
            expected = tasks.messages_for(EVIDENCE_A, 7, original_selected)
            actual = tasks.messages_for(EVIDENCE_A, 7, selected)
            assert actual == expected
        private = tasks.select("private", records, f"agent{7 % n}", 7, 1)
        assert all(r["agent"] == f"agent{7 % n}" for r in private)
        if n >= 8:
            assert private == []
    assert len(tasks.select("private", baseline, "agent0", 7, 1)) == 4


def test_provenance_dedup_keeps_latest_copy_and_ttl_boundary_is_explicit():
    records = [inspect(EVIDENCE_A, step, "route_policy", agent=f"agent{step}") for step in (0, 7)]
    assert records[0]["origin_identity"] == records[1]["origin_identity"]
    assert len(tasks.select("blackboard", records, "agent9", 8, 1)) == 2
    assert [r["step"] for r in tasks.select("dedup_ttl", records, "agent9", 8, 1)] == [7]
    assert [r["step"] for r in tasks.select("dedup_ttl", records, "agent9", 14, 1)] == [7]
    assert tasks.select("dedup_ttl", records, "agent9", 15, 1) == []
    assert tasks.select("versioned", records, "agent9", 15, 1) == []
    assert tasks.select("versioned", records, "agent9", 16, 2) == []


def test_version_selection_reopens_new_source_and_does_not_purge_baseline_stale_context():
    old = inspect(EVIDENCE_A, 15, "route_policy")
    new = inspect(EVIDENCE_A, 16, "route_policy")
    assert len(tasks.select("dedup_ttl", [old, new], "agent0", 17, 2)) == 2
    assert tasks.select("versioned", [old, new], "agent0", 17, 2) == [new]
    assert tasks.select("blackboard", [old, new], "agent0", 17, 2) == [old, new]


@pytest.mark.parametrize("n", [8, 16, 32])
def test_private_evidence_has_predeclared_four_turn_lower_bound(n):
    # Each source must be inspected in its own turn, followed by a submission.
    # Sixteen final-version slots provide <=2 turns per identity at these N.
    # This structural impossibility is not a measured model capability limit.
    history = []
    for step in range(16, 32):
        agent = f"agent{step % n}"
        memory = tasks.select("private", history, agent, step, 2)
        assert len(memory) < 3
        attempt = submit_evidence(EVIDENCE_A, step, memory, "amber", 3)
        assert attempt["valid"] is False
        own_turn = len(memory)
        history.append(inspect(EVIDENCE_A, step, TARGETS[EVIDENCE_A][own_turn], agent=agent))
    assert all(sum(r["agent"] == agent for r in history) <= 2 for agent in {r["agent"] for r in history})


def test_four_private_turns_per_version_are_sufficient_without_model_assistance():
    history = []
    for step in range(16, 32):
        agent = f"agent{step % 4}"
        memory = tasks.select("private", history, agent, step, 2)
        if len(memory) == 3:
            result = submit_evidence(EVIDENCE_A, step, memory, "amber", 3)
            result["agent"] = agent
        else:
            result = inspect(EVIDENCE_A, step, TARGETS[EVIDENCE_A][len(memory)], agent=agent)
        assert result["valid"] is True
        history.append(result)
    assert tasks.score(EVIDENCE_A, 31, history) is True


def test_four_selected_records_hold_three_sources_and_submission():
    memory = inspected(EVIDENCE_A, 16)
    submitted = submit_evidence(EVIDENCE_A, 19, memory, "amber", 3)
    for policy in ("blackboard", "dedup_ttl", "versioned"):
        selected = tasks.select(policy, memory + [submitted], "agent9", 20, 2)
        assert len(selected) == 4
        assert submit_evidence(EVIDENCE_A, 20, selected, "amber", 3)["valid"] is True


def test_all_policies_share_history_and_context_caps_and_return_detached_values():
    history = [record(CODE_A, step, {"action": "invent", "value": step}) for step in range(31)]
    for policy in tasks.POLICIES:
        selected = tasks.select(policy, history, "agent0", 31, 1)
        assert len(selected) == 4
        assert [r["step"] for r in selected] == [27, 28, 29, 30]
        selected[0]["feedback"] = "mutated"
        assert history[27]["feedback"] != "mutated"
        with pytest.raises(ValueError, match="32-record cap"):
            tasks.select(policy, history + history[:2], "agent0", 31, 1)
    with pytest.raises(ValueError, match="at most four"):
        tasks.messages_for(CODE_A, 31, history[-5:])


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(step=True), lambda r: r.update(step=31),
    lambda r: r.update(task_version=True), lambda r: r.update(task_version=2),
    lambda r: r.update(valid=1), lambda r: r.update(agent=""),
    lambda r: r.update(origin_identity="fabricated"),
    lambda r: r["artifact"].update(task_version=True),
    lambda r: r["artifact"].update(world_id=EVIDENCE_B),
    lambda r: r["artifact"]["receipt"].pop("source_id"),
])
def test_history_validation_rejects_stale_lineage_or_noncausal_metadata(mutation):
    item = inspect(EVIDENCE_A, 0, "route_policy")
    mutation(item)
    with pytest.raises(ValueError):
        tasks.select("versioned", [item], "agent0", 3, 1)


def test_cross_world_duplicate_and_unordered_histories_fail_closed():
    first = inspect(EVIDENCE_A, 0, "route_policy")
    second = inspect(EVIDENCE_A, 1, "route_capacity")
    foreign = inspect(EVIDENCE_B, 2, "ready_policy")
    for bad in ([first, foreign], [second, first], [first, first]):
        with pytest.raises(ValueError):
            tasks.select("blackboard", bad, "agent0", 3, 1)
    with pytest.raises(ValueError):
        tasks.messages_for(EVIDENCE_B, 3, [first])
    with pytest.raises(ValueError):
        tasks.score(EVIDENCE_B, 3, [first])
    with pytest.raises(ValueError):
        tasks.select("versioned", [first], "agent0", 16, 1)


@pytest.mark.parametrize("text", [
    '{"action":"inspect","action":"submit","target":"route_policy"}',
    '{"action":"inspect","target":"route_policy","extra":0}',
    '{"action":"inspect","target":true}', '{"action":"inspect","target":"missing"}',
    '{"action":NaN}', '[]', 'null', 'prose', 'x' * 16_385,
])
def test_invalid_actions_remain_ordinary_charged_results_without_artifacts(text):
    result = tasks.apply(EVIDENCE_A, 0, [], text)
    assert result["valid"] is False
    assert result["artifact"] is None and result["origin_identity"]


@pytest.mark.parametrize("line", ["    import os", "    return __import__('os')", "    while True:",
                                   "    return value.__class__", "    return 1 / 0"])
def test_model_code_cannot_escape_bounded_interpreter(line):
    request = dict(action="submit", candidate=dict(code_lines=["def bounded_increment(value, increment, ceiling):", line]))
    assert record(CODE_A, 0, request)["valid"] is False


def test_only_frozen_framing_adapter_removes_single_json_fence():
    text = '{"action":"inspect","target":"route_policy"}'
    fenced = "```json\n" + text + "\n```"
    assert tasks.apply(EVIDENCE_A, 0, [], fenced)["valid"] is False
    normalized, diagnostic = frame(fenced)
    assert diagnostic["admitted"] is True
    assert tasks.apply(EVIDENCE_A, 0, [], normalized)["valid"] is True


def test_citation_order_is_not_semantic_action_diversity():
    memory = inspected(EVIDENCE_A, 0)
    first = submit_evidence(EVIDENCE_A, 3, memory, "amber", 6)
    candidate = deepcopy(first["artifact"]["receipt"]["candidate"])
    candidate["citations"].reverse()
    second = record(EVIDENCE_A, 3, dict(action="submit", candidate=candidate), memory)
    assert first["semantic_action"] == second["semantic_action"]
