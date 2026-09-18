"""Regressions for defects found by adversarial review of the finished layer.

Each test names the defect it locks out. They drive the real ledger, the real
runtime and the real offline audit; none asserts that a mock was called.
"""

import copy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile

import pytest

from pheroos_interaction.records import BudgetExceeded
from pheroos_interaction.runner import anthropic, audit, contracts, runtime, tools
from pheroos_interaction.runner.contracts import ContractError
from pheroos_interaction.runner.orchestration import CONTRACT, MODEL_KEY, OrchestrationSession

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "orchestration"


def spec_of(name):
    return contracts.workflow_spec(json.loads((EXAMPLES / name).read_text()))


def script_of(name):
    return anthropic.load_script(EXAMPLES / name)


def run(tmp_path, spec, script, *, session=None, name="s.sqlite"):
    session = session or OrchestrationSession.create(tmp_path / name, spec=spec)
    outcome = runtime.run_workflow(session, registry=tools.build_registry(spec, EXAMPLES),
                                   transports={"fake": anthropic.FakeTransport(script)})
    return session, outcome


def decisions(session, work_id):
    return [(row["decision"], row["reason"] or "") for row in session.decisions(work_id)]


# ---------------------------------------------------------------- admission refusals


@pytest.mark.parametrize("label, mutate, detail", [
    ("cyclic", lambda kids: kids[0].__setitem__("dependencies", [kids[1]["name"]])
     or kids[1].__setitem__("dependencies", [kids[0]["name"]]), "cyclic work dependencies"),
    ("duplicate-name", lambda kids: kids[1].__setitem__("name", kids[0]["name"]), "duplicate child name"),
    ("widened-tools", lambda kids: kids[0].__setitem__("tools", ["checker.category_totals"]),
     "does not conform"),   # the child schema's tool enum refuses it before admission
])
def test_a_refused_decomposition_is_a_recorded_rejection_and_never_wedges_the_run(
        tmp_path, label, mutate, detail):
    """The platform refuses these with a plain ValueError; it must not escape the step loop."""
    spec, script = spec_of("workflow-decomposition.json"), copy.deepcopy(script_of("script-decomposition.json"))
    mutate(script["responses"][0]["response"]["content"][0]["input"]["children"])
    session, outcome = run(tmp_path, spec, script)
    recorded = decisions(session, "totals")
    assert recorded[0][0] == "rejected" and detail in recorded[0][1]
    assert [row["work_id"] for row in session.tasks()] == ["totals", "review", "finalize"]
    assert outcome["status"] == "success" and outcome["tasks"]["totals"]["status"] == "published"
    assert audit.replay_run(session.path, spec_dir=EXAMPLES)["status"] == "PASS"


def test_a_resumed_run_does_not_repeat_a_refused_decomposition(tmp_path):
    spec, script = spec_of("workflow-decomposition.json"), copy.deepcopy(script_of("script-decomposition.json"))
    kids = script["responses"][0]["response"]["content"][0]["input"]["children"]
    kids[0]["dependencies"], kids[1]["dependencies"] = [kids[1]["name"]], [kids[0]["name"]]
    session, first = run(tmp_path, spec, script)
    before = contracts.wire(session.snapshot())
    reopened = OrchestrationSession(session.path)
    again = runtime.run_workflow(reopened, registry=tools.build_registry(spec, EXAMPLES),
                                 transports={"fake": anthropic.FakeTransport(script)})
    assert again["status"] == first["status"] == "success"
    assert contracts.wire(reopened.snapshot()) == before


def test_a_decomposition_that_would_consume_the_model_step_reserve_is_refused(tmp_path):
    raw = json.loads((EXAMPLES / "workflow-decomposition.json").read_text())
    raw["tasks"][0]["limits"]["model_steps"] = 2
    raw["tasks"][0]["decomposition"]["join_reserve"]["model_steps"] = 2
    spec = contracts.workflow_spec(raw)
    session, outcome = run(tmp_path, spec, script_of("script-decomposition.json"))
    recorded = decisions(session, "totals")
    assert recorded[0][0] == "rejected" and "join reserve of model steps" in recorded[0][1]
    assert [row["work_id"] for row in session.tasks()] == ["totals", "review", "finalize"]
    assert outcome["tasks"]["totals"]["status"] == "published"


def test_admit_children_refuses_the_step_reserve_atomically(tmp_path):
    raw = json.loads((EXAMPLES / "workflow-decomposition.json").read_text())
    raw["tasks"][0]["limits"]["model_steps"] = 2
    raw["tasks"][0]["decomposition"]["join_reserve"]["model_steps"] = 2
    spec = contracts.workflow_spec(raw)
    session = OrchestrationSession.create(tmp_path / "s.sqlite", spec=spec)
    engine = runtime.Runtime(session, registry=tools.build_registry(spec, EXAMPLES),
                             transports={"fake": anthropic.FakeTransport(script_of("script-decomposition.json"))})
    assert engine.step("totals")["status"] == "inferred"
    call_id = next(row["id"] for row in session.work_calls_of("totals"))
    lease = session.claim("producer", "totals")
    before = contracts.wire(session.snapshot())
    children = script_of("script-decomposition.json")["responses"][0]["response"]["content"][0]["input"]["children"]
    with pytest.raises(BudgetExceeded, match="join reserve of model steps"):
        session.admit_children(lease, call_id, children)
    assert contracts.wire(session.snapshot()) == before


# ---------------------------------------------------------------- tool scoping


def test_a_reader_cannot_reach_a_fixture_outside_its_declared_scope(tmp_path):
    """The reviewer's answer key: a producer must not be able to read the checker's fixture."""
    spec, script = spec_of("workflow-expected.json"), copy.deepcopy(script_of("script-expected.json"))
    assert spec["fixtures"]["expected"]["sha256"]
    reader = next(tool for tool in spec["tools"] if tool["name"] == "fixture.read")
    assert reader["config"] == {"fixtures": ["orders"]}
    script["responses"][0]["response"]["content"][0]["input"] = {"name": "expected"}
    session, outcome = run(tmp_path, spec, script)
    recorded = decisions(session, "draft")
    assert recorded[0][0] == "rejected" and "do not conform" in recorded[0][1]
    assert [row for row in session.work_calls_of("draft")
            if row["request"].get("binding", {}).get("kind") == "tool"] == []


def test_an_unscoped_reader_is_refused_at_registry_build(tmp_path):
    raw = json.loads((EXAMPLES / "workflow.json").read_text())
    for tool in raw["tools"]:
        if tool["name"] == "fixture.read":
            tool.pop("config")
    with pytest.raises(tools.ToolError, match="requires a config naming the fixtures"):
        tools.build_registry(contracts.workflow_spec(raw), EXAMPLES)


def test_no_shipped_example_lets_a_reader_reach_an_answer_key_fixture():
    """A checker that recomputes from the data may share it; an answer key may not be readable."""
    for name in ("workflow.json", "workflow-expected.json", "workflow-decomposition.json"):
        spec = spec_of(name)
        readable, checked = set(), set()
        for tool in spec["tools"]:
            readable |= set(tool["config"].get("fixtures", []))
            if "fixture" in tool["config"]:
                checked.add(tool["config"]["fixture"])
        assert readable == {"orders"}, f"{name} scopes its reader beyond the data fixture"
        assert "expected" not in readable, f"{name} lets a reader read the answer key"
        assert set(spec["fixtures"]) == readable | checked, f"{name} declares an unused fixture"


# ---------------------------------------------------------------- schema bounds


@pytest.mark.parametrize("schema", [
    {"type": "string"},
    {"type": "string", "minLength": 1},
    {"type": "object", "additionalProperties": False, "required": ["note"],
     "properties": {"note": {"type": "string"}}},
])
def test_an_unbounded_string_schema_is_refused_instead_of_narrowed_to_zero(schema):
    with pytest.raises(ContractError, match="explicit maxLength or an enum"):
        contracts.validate_schema(schema)


def test_a_bounded_or_enumerated_string_schema_still_validates():
    bounded = contracts.validate_schema({"type": "string", "maxLength": 8})
    assert contracts.conforms(bounded, "hello") is None
    enumerated = contracts.validate_schema({"type": "string", "enum": ["accept", "reject"]})
    assert enumerated["maxLength"] == 6 and contracts.conforms(enumerated, "accept") is None


# ---------------------------------------------------------------- accounting durability


def test_reported_usage_settles_in_the_receipt_transaction_so_a_crash_cannot_split_them(tmp_path):
    """A crash between settlement and a separate usage write made a clean run audit as FAIL."""
    spec, script = spec_of("workflow.json"), script_of("script.json")

    class Crash(OrchestrationSession):
        def _event(self, db, kind, work, payload):
            super()._event(db, kind, work, payload)
            if kind == "received" and not getattr(self, "fired", False):
                self.fired = True
                raise RuntimeError("process died immediately after settlement")

    session = Crash.create(tmp_path / "s.sqlite", spec=spec)
    engine = runtime.Runtime(session, registry=tools.build_registry(spec, EXAMPLES),
                             transports={"fake": anthropic.FakeTransport(script)})
    record = engine.step("produce")
    assert record["status"] in ("blocked_unknown", "error")
    reopened = OrchestrationSession(session.path)
    settled = [row for row in reopened.accounting() if row["reported"] is not None]
    for row in settled:
        call = reopened.call(row["call_id"])
        assert call["state"] == "received"
        assert row["reported"]["prompt_tokens"] == call["response"]["prompt_tokens"]
        assert row["reported"]["contract"] == CONTRACT
    assert all(row["reported"] is not None
               for row in reopened.accounting()
               if reopened.call(row["call_id"])["state"] == "received")


def test_a_completed_run_records_reported_usage_for_every_settled_model_call(tmp_path):
    session, outcome = run(tmp_path, spec_of("workflow.json"), script_of("script.json"))
    rows = session.accounting()
    assert rows and all(row["contract"] == CONTRACT and row["violation"] is None for row in rows)
    for row in rows:
        call = session.call(row["call_id"])
        usage = call["response"][MODEL_KEY]["usage"]
        assert row["reported"]["usage"] == usage
        assert row["reported"]["prompt_tokens"] <= row["prompt_bound"]
    assert audit.replay_run(session.path, spec_dir=EXAMPLES)["status"] == "PASS"


# ---------------------------------------------------------------- audit tamper detection


def tampered(session, tmp_path, mutate, name="tampered.sqlite"):
    target = tmp_path / name
    shutil.copy(session.path, target)
    database = sqlite3.connect(target)
    try:
        mutate(database)
        database.commit()
    finally:
        database.close()
    return target


def test_replay_detects_a_duplicate_decision_that_is_not_the_last_row_for_its_work(tmp_path):
    """Keying the uniqueness count by work id let a duplicate consumption audit clean."""
    session, _ = run(tmp_path, spec_of("workflow.json"), script_of("script.json"))

    def duplicate(database):
        row = database.execute(
            "SELECT work_id,version,call_id,receipt_digest,step,decision,reason,validator "
            "FROM orchestration_decisions_v1 WHERE work_id='produce' ORDER BY seq LIMIT 1").fetchone()
        database.execute("INSERT INTO orchestration_decisions_v1 VALUES (0,?,?,?,?,?,?,?,?)", row)

    report = audit.replay_run(tampered(session, tmp_path, duplicate), spec_dir=EXAMPLES)
    assert report["status"] == "FAIL"
    assert any(failure.startswith("decision_uniqueness:") for failure in report["failures"])
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)


def test_replay_accepts_a_rejection_recorded_for_a_well_formed_but_refused_proposal(tmp_path):
    spec, script = spec_of("workflow-decomposition.json"), copy.deepcopy(script_of("script-decomposition.json"))
    kids = script["responses"][0]["response"]["content"][0]["input"]["children"]
    kids[0]["dependencies"], kids[1]["dependencies"] = [kids[1]["name"]], [kids[0]["name"]]
    session, _ = run(tmp_path, spec, script)
    assert decisions(session, "totals")[0][0] == "rejected"
    assert audit.replay_run(session.path, spec_dir=EXAMPLES)["status"] == "PASS"


def test_replay_still_detects_a_decision_whose_receipt_no_longer_parses_to_it(tmp_path):
    session, _ = run(tmp_path, spec_of("workflow.json"), script_of("script.json"))

    def relabel(database):
        database.execute("UPDATE orchestration_decisions_v1 SET decision='abstain' WHERE decision='submit'")

    report = audit.replay_run(tampered(session, tmp_path, relabel), spec_dir=EXAMPLES)
    assert report["status"] == "FAIL"
    assert any(":proposal" in failure for failure in report["failures"])


# ---------------------------------------------------------------- provider usage detail


@pytest.mark.parametrize("extra, expected_prompt", [
    ({}, 10),
    ({"service_tier": "standard"}, 10),
    ({"server_tool_use": {"web_search_requests": 2}}, 10),
    ({"cache_creation": {"ephemeral_5m_input_tokens": 4}, "cache_creation_input_tokens": 4}, 14),
])
def test_documented_usage_detail_is_recorded_without_inflating_the_prompt_sum(extra, expected_prompt):
    raw = {"id": "msg", "type": "message", "role": "assistant", "model": "claude", "stop_reason": "end_turn",
           "content": [{"type": "text", "text": "hi"}],
           "usage": {"input_tokens": 10, "output_tokens": 3, **extra}}
    artifact, prompt, completion = anthropic.extract(raw)
    assert (prompt, completion) == (expected_prompt, 3)
    for key, value in extra.items():
        assert artifact["usage"][key] == value


def test_a_usage_member_that_is_neither_a_counter_nor_documented_detail_is_refused():
    raw = {"id": "msg", "type": "message", "role": "assistant", "model": "claude", "stop_reason": "end_turn",
           "content": [{"type": "text", "text": "hi"}],
           "usage": {"input_tokens": 1, "output_tokens": 1, "invented_tokens": 7}}
    with pytest.raises(ValueError, match="usage requires"):
        anthropic.extract(raw)


# ---------------------------------------------------------------- child read narrowing


def test_a_child_may_request_a_parent_read_whose_id_is_not_a_legal_child_name(tmp_path):
    """Deriving a sibling id first made a parent read named like `a.b` unrequestable."""
    raw = json.loads((EXAMPLES / "workflow-decomposition.json").read_text())
    upstream = json.loads(json.dumps(raw["tasks"][0]))
    upstream.update(id="orders.raw", instructions="Read the orders fixture and submit the totals.",
                    dependencies=[], reads=[], decomposition=None,
                    limits={"model_steps": 3, "tool_calls": 2, "rejections": 1, "calls": 4, "tokens": 60000})
    raw["tasks"][0]["dependencies"] = ["orders.raw"]
    raw["tasks"][0]["reads"] = ["orders.raw"]
    raw["tasks"] = [upstream] + raw["tasks"]
    spec = contracts.workflow_spec(raw)

    totals = {"totals": [{"category": "books", "cents": 2499}, {"category": "grocery", "cents": 600},
                         {"category": "tools", "cents": 3400}], "total_cents": 6499}

    def message(identifier, name, payload):
        return {"id": identifier, "type": "message", "role": "assistant", "model": "fake-model",
                "stop_reason": "tool_use", "usage": {"input_tokens": 900, "output_tokens": 40},
                "content": [{"type": "tool_use", "id": "toolu_" + identifier, "name": name, "input": payload}]}

    child = {"name": "books", "instructions": "Report the books total from the parent's read.",
             "tools": [], "reads": ["orders.raw"], "dependencies": [],
             "limits": {"model_steps": 2, "tool_calls": 0, "rejections": 1, "calls": 2, "tokens": 30000}}
    script = {"format": "fake-model-script-v1", "responses": [
        {"task": "orders.raw", "step": 0, "response": message("u0", "fixture.read", {"name": "orders"})},
        {"task": "orders.raw", "step": 1, "response": message("u1", "submit_output", totals)},
        {"task": "totals", "step": 0, "response": message("t0", "propose_children", {"children": [child]})},
        {"task": "totals.books", "step": 0, "response": message("b0", "submit_output", totals)},
        {"task": "totals", "step": 1, "response": message("t1", "submit_output", totals)},
        {"task": "review", "step": 0,
         "response": message("r0", "checker.category_totals", {"candidate_ref": "totals"})},
        {"task": "review", "step": 1,
         "response": message("r1", "submit_output", {"verdict": "accept", "note": "totals matched"})}]}

    session, outcome = run(tmp_path, spec, anthropic.validate_script(script))
    assert decisions(session, "totals")[0][0] == "decompose"
    admitted = session.task("totals.books")
    assert admitted["reads"] == ["orders.raw"] and "orders.raw" in admitted["dependencies"]
    assert outcome["tasks"]["totals.books"]["status"] == "published"
    assert audit.replay_run(session.path, spec_dir=EXAMPLES)["status"] == "PASS"


# ---------------------------------------------------------------- correctness defects


def test_an_admitted_decomposition_answers_its_propose_children_action(tmp_path):
    """An unanswered tool_use makes the parent's next request a malformed conversation."""
    session, outcome = run(tmp_path, spec_of("workflow-decomposition.json"),
                           script_of("script-decomposition.json"))
    assert outcome["status"] == "success"
    assert [row["decision"] for row in session.decisions("totals")] == ["decompose", "submit"]
    resumed = next(call for call in session.work_calls_of("totals")
                   if call["request"]["binding"]["kind"] == "model"
                   and call["request"]["binding"]["step"] == 1)
    messages = resumed["request"]["arguments"]["request"]["messages"]
    uses = {block["id"]: block["name"] for message in messages
            for block in message["content"] if block["type"] == "tool_use"}
    answered = {block["tool_use_id"] for message in messages
                for block in message["content"] if block["type"] == "tool_result"}
    assert set(uses) == answered, "an assistant tool_use went unanswered"
    assert set(uses.values()) == {"propose_children"}
    assert [message["role"] for message in messages] == ["user", "assistant", "user"]
    assert audit.replay_run(session.path, spec_dir=EXAMPLES)["status"] == "PASS"


def test_a_rejected_candidate_is_not_reported_as_a_successful_run(tmp_path):
    failing = copy.deepcopy(script_of("script.json"))
    failing["responses"][1]["response"]["content"][0]["input"]["total_cents"] = 1
    session, outcome = run(tmp_path, spec_of("workflow.json"), anthropic.validate_script(failing))
    assert outcome["status"] == "rejected"
    assert "finalize" in outcome["reason"]
    assert {name: task["status"] for name, task in outcome["tasks"].items()} == {
        "produce": "published", "review": "published", "finalize": "published"}
    assert json.loads(next(row["value"] for row in session.snapshot()["artifacts"]
                           if row["work_id"] == "finalize"))["accepted"] is False


def test_a_tool_call_must_be_bound_to_the_proposal_its_receipt_carries(tmp_path):
    """The digest alone is not enough: the receipt must propose this tool and these arguments."""
    from pheroos_interaction.records import StateError
    from pheroos_interaction.runner.orchestration import MODEL_KEY, call_identity
    spec = spec_of("workflow.json")
    session, _ = run(tmp_path, spec, script_of("script.json"))
    source = next(call for call in session.work_calls_of("produce")
                  if call["request"]["binding"]["kind"] == "model"
                  and call["request"]["binding"]["step"] == 0)
    assert source["response"][MODEL_KEY]["content"][0]["name"] == "fixture.read"
    other = OrchestrationSession(session.path)
    lease = other.claim("producer", "produce")
    assert lease is None    # the task is terminal; the binding rule is covered below

    fresh = OrchestrationSession.create(tmp_path / "fresh.sqlite", spec=spec)
    engine = runtime.Runtime(fresh, registry=tools.build_registry(spec, EXAMPLES),
                             transports={"fake": anthropic.FakeTransport(script_of("script.json"))})
    assert engine.step("produce")["status"] == "inferred"
    lease = fresh.claim("producer", "produce")
    model_call = call_identity(spec["run_id"], "produce", 1, "model", 0)
    receipt = fresh.call(model_call)
    substituted = {"name": "expected"}
    digest = contracts.digest(substituted)
    binding = {"kind": "tool", "step": 0, "attempt": 0,
               "spec_digest": fresh.snapshot()["orchestration"]["spec_digest"],
               "task_version": 1, "tool": "fixture.read", "tool_version": "fixture-read-v1",
               "schema_digest": contracts.digest(
                   tools.build_registry(spec, EXAMPLES).schema("fixture.read")),
               "arguments_digest": digest, "proposal_digest": digest,
               "model_call_id": model_call,
               "receipt_digest": contracts.digest(receipt["response"]), "inputs": []}
    before = contracts.wire(fresh.snapshot())
    # Same declared tool, consistent argument digest: only a check against the receipt
    # itself catches that the model never proposed these arguments.
    with pytest.raises(StateError, match="proposes different arguments"):
        fresh.reserve_tool_call(
            lease, call_identity(spec["run_id"], "produce", 1, "tool", 0),
            {"tool_ref": "fixture.read", "arguments": substituted, "binding": binding},
            source_call_id=model_call, step=0)
    assert contracts.wire(fresh.snapshot()) == before


def test_resume_refuses_a_frozen_record_that_describes_another_ledger(tmp_path):
    output = tmp_path / "run"
    runtime.start_run(EXAMPLES / "workflow.json", output,
                      script_path=EXAMPLES / "script.json")
    frozen = json.loads((output / "frozen.json").read_text())
    # Self-consistent but for a different workflow: only a check against the ledger
    # itself can catch this, since the frozen record agrees with its own digest.
    frozen["spec"] = contracts.workflow_spec(
        dict(json.loads((EXAMPLES / "workflow.json").read_text()), run_id="another-run"))
    frozen["spec_digest"] = contracts.digest(frozen["spec"])
    (output / "frozen.json").write_text(contracts.wire(frozen) + "\n")
    with pytest.raises(ValueError, match="does not describe this ledger"):
        runtime.resume_run(output, script_path=EXAMPLES / "script.json")
