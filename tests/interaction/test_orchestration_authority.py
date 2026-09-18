"""Authority, validation and accounting boundaries of the bounded orchestration ledger.

Every check here goes through the real ledger. Workflows are created from validated
specs, steps are driven by the reference runtime over a scripted transport, and each
refusal is observed in durable rows - decisions, calls, artifacts, accounting and the
whole snapshot - never in a call count on a mock. A model proposal is data: it is
parsed, checked against the task's declared schemas, and then either consumed by one
admitted transition or recorded as a rejection that costs a step and a rejection slot.
"""

from hashlib import sha256
import json
import sqlite3

import pytest

from pheroos_interaction.records import BudgetExceeded, StateError
from pheroos_interaction.runner import anthropic, audit, contracts, runtime, tools
from pheroos_interaction.runner.contracts import ContractError
from pheroos_interaction.runner.orchestration import (MODEL_KEY, TOOL_KEY, OrchestrationSession,
                                                      call_identity)

RUN_ID = "authority"
ORDERS = {"orders": [{"id": "a", "category": "books", "amount_cents": 1000},
                     {"id": "b", "category": "apples", "amount_cents": 250}]}
OUTPUT = {"total_cents": 1250, "totals": [{"category": "apples", "cents": 250},
                                          {"category": "books", "cents": 1000}]}
VERDICT = {"verdict": "accept", "note": "the checker reported pass for the bound digest"}
TOTALS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["totals", "total_cents"],
    "properties": {"totals": {"type": "array", "maxItems": 64, "minItems": 0,
                              "items": {"type": "object", "additionalProperties": False,
                                        "required": ["category", "cents"],
                                        "properties": {"category": {"type": "string", "maxLength": 64,
                                                                    "minLength": 1},
                                                       "cents": {"type": "integer", "minimum": 0}}}},
                   "total_cents": {"type": "integer", "minimum": 0}}}
VERDICT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["verdict", "note"],
                  "properties": {"verdict": {"type": "string", "enum": ["accept", "reject"]},
                                 "note": {"type": "string", "maxLength": 512, "minLength": 1}}}
MODEL = {"provider": "fake", "model": "fake-model", "max_new_tokens": 1024,
         "prompt_token_bound": 16384, "prompt_overhead_tokens": 800}
TASK_LIMITS = {"model_steps": 4, "tool_calls": 2, "rejections": 2, "calls": 8, "tokens": 80000}
RUN_LIMITS = {"max_calls": 64, "token_cap": 400000, "context_bytes": 131072, "artifact_bytes": 32768,
              "max_work_items": 8, "max_children": 4, "max_depth": 2, "max_platform_operations": 512}
DECOMPOSITION = {"max_children": 3, "child_output_schema": TOTALS_SCHEMA,
                 "join_reserve": {"model_steps": 1, "calls": 2, "tokens": 40000}}
CHILD_LIMITS = {"model_steps": 3, "tool_calls": 2, "rejections": 1, "calls": 2, "tokens": 20000}


# ---------------------------------------------------------------- declarations


def fixtures(root):
    """Write the declared fixture and return its host declaration."""
    raw = contracts.wire(ORDERS).encode()
    (root / "fixtures").mkdir(parents=True, exist_ok=True)
    (root / "fixtures" / "orders.json").write_bytes(raw)
    return {"orders": {"path": "fixtures/orders.json", "sha256": sha256(raw).hexdigest(),
                       "bytes": len(raw)}}


def produce_task(**overrides):
    task = {"id": "produce", "kind": "model", "agent": "producer", "dependencies": [], "reads": [],
            "instructions": "Read the declared fixture and submit the totals per category.",
            "tools": ["fixture.read"], "output_schema": TOTALS_SCHEMA, "limits": dict(TASK_LIMITS)}
    task.update(overrides)
    return task


def review_task(**overrides):
    task = {"id": "review", "kind": "model", "agent": "reviewer", "dependencies": ["produce"],
            "reads": ["produce"], "instructions": "Check the candidate totals, then submit a verdict.",
            "tools": ["checker.category_totals"], "output_schema": VERDICT_SCHEMA,
            "limits": dict(TASK_LIMITS)}
    task.update(overrides)
    return task


def finalize_task():
    return {"id": "finalize", "kind": "host", "agent": "host", "dependencies": ["produce", "review"],
            "reads": ["produce", "review"],
            "rule": {"type": "checker_pass", "candidate": "produce", "review": "review",
                     "checker": "checker.category_totals"}}


def totals_task(**overrides):
    task = produce_task(id="totals", limits=dict(TASK_LIMITS, calls=14, tokens=200000),
                        instructions="Split the work with propose_children, then merge and submit.",
                        decomposition=dict(DECOMPOSITION))
    task.update(overrides)
    return task


def child(name, **overrides):
    proposal = {"name": name, "instructions": "Submit the " + name + " total.",
                "tools": ["fixture.read"], "reads": [], "dependencies": [],
                "limits": dict(CHILD_LIMITS)}
    proposal.update(overrides)
    return proposal


def workflow(root, *, tasks=None, run_limits=None, agent_tools=None):
    capabilities = agent_tools or {"producer": ["fixture.read"], "reviewer": ["checker.category_totals"]}
    return {"format": contracts.SPEC_FORMAT, "run_id": RUN_ID, "fixtures": fixtures(root),
            "agents": [{"id": name, "model": dict(MODEL), "capabilities": {"tools": list(names)}}
                       for name, names in capabilities.items()],
            "tools": [{"name": "fixture.read", "version": "fixture-read-v1", "config": {"fixtures": ["orders"]}},
                      {"name": "checker.category_totals", "version": "category-totals-v1",
                       "config": {"fixture": "orders"}}],
            "tasks": tasks or [produce_task()], "limits": dict(RUN_LIMITS, **(run_limits or {}))}


# ---------------------------------------------------------------- scripted provider


def use(name, arguments, identifier="toolu_0"):
    return {"type": "tool_use", "id": identifier, "name": name, "input": arguments}


def text(body):
    return {"type": "text", "text": body}


def response(*blocks, stop="tool_use", usage=None, identifier="msg"):
    return {"id": identifier, "type": "message", "role": "assistant", "model": "fake-model",
            "stop_reason": stop, "content": list(blocks),
            "usage": dict({"input_tokens": 900, "output_tokens": 40}, **(usage or {}))}


def script(*entries):
    return {"format": anthropic.SCRIPT_FORMAT,
            "responses": [{"task": task, "step": step, "response": body} for task, step, body in entries]}


SUBMIT_TOTALS = ("produce", 0, response(use("submit_output", OUTPUT)))
READ_FIXTURE = ("produce", 0, response(use("fixture.read", {"name": "orders"})))
SUBMIT_AFTER_TOOL = ("produce", 1, response(use("submit_output", OUTPUT), identifier="msg1"))
REVIEW_CHECK = ("review", 0, response(use("checker.category_totals", {"candidate_ref": "produce"})))
REVIEW_SUBMIT = ("review", 1, response(use("submit_output", VERDICT), identifier="msg1"))


class Clock:
    """An injected clock; time only moves when a test moves it."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def build(root, entries, *, tasks=None, run_limits=None, clock=None, sent=None):
    """Create a ledger from an inline spec and a runtime over the scripted transport."""
    spec = contracts.workflow_spec(workflow(root, tasks=tasks, run_limits=run_limits))
    session = OrchestrationSession.create(root / "session.sqlite", spec=spec, clock=clock)
    registry = tools.build_registry(spec, root)
    engine = runtime.Runtime(session, registry=registry,
                             transports={"fake": anthropic.FakeTransport(script(*entries), calls=sent)})
    return session, engine, spec


def reopen(session, engine, entries, *, clock=None, sent=None):
    """Reopen the same ledger in a fresh session and runtime, as a restart would."""
    reopened = OrchestrationSession(session.path, clock=clock)
    return reopened, runtime.Runtime(reopened, registry=engine.registry,
                                     transports={"fake": anthropic.FakeTransport(script(*entries),
                                                                                 calls=sent)})


def drive(engine, *work_ids):
    return [engine.step(work_id) for work_id in work_ids]


def copy(value):
    return json.loads(contracts.wire(value))


def call_rows(session, kind=None):
    rows = []
    for row in session.snapshot()["calls"]:
        binding = json.loads(row["request"]).get("binding", {})
        if kind is None or binding.get("kind") == kind:
            rows.append({**dict(row), "binding": binding})
    return rows


def model_payload(engine, session, lease, *, step=0, attempt=0):
    """Build exactly the payload the runtime would reserve for one model step."""
    declaration = session.task(lease.task_id)
    history = session.work_calls(lease)
    decisions = [row for row in session.decisions(lease.task_id) if row["version"] == lease.version]
    state = engine._state(declaration, history, decisions)
    inputs = session.readable_artifacts(lease.task_id, declaration["agents"][0], step)
    request, binding = engine.frozen_model_request(
        declaration, lease.task_id, lease.version, history, decisions, inputs,
        state["remaining"], step, attempt,
        session.snapshot()["orchestration"]["spec_digest"], declaration["agents"][0])
    return {"tool_ref": contracts.MODEL_TOOL_REF, "arguments": {"request": request}, "binding": binding}


def reserve_model(session, lease, call_id, payload):
    return session.reserve_bounded(lease, call_id, "tool.evaluate", payload,
                                   prompt_token_bound=MODEL["prompt_token_bound"],
                                   max_new_tokens=MODEL["max_new_tokens"])


def tool_payload(engine, session, lease, model_call_id, step=0):
    """Build exactly the payload the runtime would reserve for the proposed tool call."""
    declaration = session.task(lease.task_id)
    call = session.call(model_call_id)
    proposal = contracts.parse_proposal(call["response"][MODEL_KEY],
                                        tools=engine._tool_schemas(declaration),
                                        output_schema=declaration["output_schema"])
    binding = {"kind": "tool", "step": step, "attempt": 0,
               "spec_digest": session.snapshot()["orchestration"]["spec_digest"],
               "task_version": lease.version, "tool": proposal["tool"],
               "tool_version": engine.registry.version(proposal["tool"]),
               "schema_digest": contracts.digest(engine.registry.schema(proposal["tool"])),
               "arguments_digest": contracts.digest(proposal["arguments"]),
               "proposal_digest": contracts.proposal_digest(proposal),
               "model_call_id": model_call_id,
               "receipt_digest": sha256(contracts.wire(call["response"]).encode()).hexdigest(),
               "inputs": []}
    return {"tool_ref": proposal["tool"], "arguments": proposal["arguments"], "binding": binding}


def settled_proposal(tmp_path, entries=(SUBMIT_TOTALS,), **options):
    """Drive one inference so the task holds a settled, unconsumed model receipt."""
    session, engine, spec = build(tmp_path, entries, **options)
    record = engine.step("produce")
    assert record["status"] == "inferred"
    return session, engine, spec, record["call_id"]


# ---------------------------------------------------------------- proposal validation


def test_a_proposal_naming_a_tool_the_task_does_not_declare_records_no_tool_call_and_no_artifact(tmp_path):
    session, engine, _ = build(tmp_path, [
        ("produce", 0, response(use("checker.category_totals", {"candidate_ref": "produce"}))),
        SUBMIT_AFTER_TOOL])
    outcome = engine.run()
    decisions = session.decisions("produce")
    assert outcome["status"] == "success"
    assert [row["decision"] for row in decisions] == ["rejected", "submit"]
    assert "is not permitted for this task" in decisions[0]["reason"]
    assert call_rows(session, "tool") == []
    assert [row["work_id"] for row in session.artifact_records()] == ["produce"]


def test_a_rejected_proposal_consumes_one_model_step_and_one_rejection_slot(tmp_path):
    session, engine, _ = build(tmp_path, [
        ("produce", 0, response(use("submit_output", {"total_cents": 1250}))), SUBMIT_AFTER_TOOL])
    engine.run()
    declaration = session.task("produce")
    history = session.work_calls_of("produce")
    state = engine._state(declaration, history, session.decisions("produce"))
    assert [row["binding"]["step"] for row in call_rows(session, "model")] == [0, 1]
    assert state["rejections"] == 1
    assert state["remaining"] == {"model_steps": TASK_LIMITS["model_steps"] - 2,
                                 "tool_calls": TASK_LIMITS["tool_calls"],
                                 "rejections": TASK_LIMITS["rejections"] - 1}


@pytest.mark.parametrize("arguments, detail", [
    ({"name": "orders", "budget": 9}, "undeclared fields"),
    ({"name": 7}, "string required"),
    ({}, "required"),
])
def test_tool_arguments_that_break_the_declared_schema_are_rejected_before_the_tool_runs(
        tmp_path, arguments, detail):
    session, engine, _ = build(tmp_path, [("produce", 0, response(use("fixture.read", arguments))),
                                          SUBMIT_AFTER_TOOL])
    engine.run()
    decisions = session.decisions("produce")
    assert decisions[0]["decision"] == "rejected"
    assert "arguments for fixture.read do not conform" in decisions[0]["reason"]
    assert detail in decisions[0]["reason"]
    assert call_rows(session, "tool") == []


@pytest.mark.parametrize("output, detail", [
    ({"total_cents": "1250", "totals": []}, "exact integer required"),
    ({"total_cents": -1, "totals": []}, "minimum 0"),
    ({"total_cents": 1250, "totals": [{"category": "books", "cents": 1, "note": "x"}]},
     "undeclared fields"),
])
def test_a_submitted_output_that_breaks_the_declared_schema_is_rejected_and_publishes_nothing(
        tmp_path, output, detail):
    session, engine, _ = build(tmp_path, [("produce", 0, response(use("submit_output", output))),
                                          SUBMIT_AFTER_TOOL])
    engine.run()
    decisions = session.decisions("produce")
    assert decisions[0]["decision"] == "rejected"
    assert detail in decisions[0]["reason"]
    assert [row["kind"] for row in session.artifact_records()] == ["output"]
    assert json.loads(session.snapshot()["artifacts"][0]["value"]) == OUTPUT


def test_a_non_finite_number_never_reaches_a_proposal_or_the_ledger(tmp_path):
    raw = response(use("submit_output", {"total_cents": float("inf"), "totals": []}))
    with pytest.raises(ContractError, match="finite JSON numbers required"):
        contracts.parse_proposal(raw, tools={}, output_schema=TOTALS_SCHEMA)
    with pytest.raises(ContractError, match="finite JSON numbers required"):
        anthropic.extract(raw)
    with pytest.raises(ContractError, match="finite JSON numbers required"):
        anthropic.validate_script(script(("produce", 0, raw)))
    session, _, _ = build(tmp_path, [SUBMIT_TOTALS])
    with pytest.raises(ValueError):
        session.receive("orch:none", {MODEL_KEY: {"content": [], "usage": {"x": float("nan")}},
                                      "prompt_tokens": 0, "completion_tokens": 0})
    assert session.snapshot()["calls"] == []


@pytest.mark.parametrize("blocks, stop, detail", [
    ([text("I will not act right now.")], "end_turn", "got 0"),
    ([use("fixture.read", {"name": "orders"}, "a"), use("submit_output", OUTPUT, "b")], "tool_use",
     "got 2"),
    ([use("submit_output", OUTPUT)], "max_tokens", "truncated at max_tokens"),
])
def test_a_response_that_is_not_exactly_one_untruncated_action_is_rejected(tmp_path, blocks, stop, detail):
    session, engine, _ = build(tmp_path, [("produce", 0, response(*blocks, stop=stop)),
                                          SUBMIT_AFTER_TOOL])
    engine.run()
    decisions = session.decisions("produce")
    assert decisions[0]["decision"] == "rejected"
    assert detail in decisions[0]["reason"]
    assert call_rows(session, "tool") == []


def test_propose_children_is_rejected_when_the_task_is_not_in_decomposition_mode(tmp_path):
    session, engine, _ = build(tmp_path, [
        ("produce", 0, response(use("propose_children", {"children": [child("books")]}))),
        SUBMIT_AFTER_TOOL])
    engine.run()
    decisions = session.decisions("produce")
    assert decisions[0]["decision"] == "rejected"
    assert "propose_children is not available for this task" in decisions[0]["reason"]
    assert [row["work_id"] for row in session.tasks()] == ["produce"]
    assert [row["id"] for row in session.snapshot()["work"]] == ["produce"]


# ---------------------------------------------------------------- authority widening


@pytest.mark.parametrize("label, action, arguments", [
    ("another-agent-field", "submit_output", dict(OUTPUT, agent="reviewer")),
    ("another-task-ref-field", "submit_output", dict(OUTPUT, artifact_ref="sha256:" + "0" * 64)),
    ("larger-budget-field", "submit_output", dict(OUTPUT, limits={"calls": 999, "tokens": 999999})),
    ("other-model-field", "submit_output", dict(OUTPUT, model="some-other-model")),
    ("filesystem-path-field", "submit_output", dict(OUTPUT, path="/etc/passwd")),
    ("action-named-after-an-agent", "reviewer", {"candidate_ref": "produce"}),
    ("reserved-action-name", "propose_children", {"children": []}),
])
def test_a_proposal_that_tries_to_widen_authority_is_refused_and_changes_nothing_durable(
        tmp_path, label, action, arguments):
    session, engine, spec = build(tmp_path, [("produce", 0, response(use(action, arguments))),
                                             SUBMIT_AFTER_TOOL])
    declared = copy(session.task("produce"))
    budget = session.work_budget("produce")
    engine.run()
    decisions = session.decisions("produce")
    assert decisions[0]["decision"] == "rejected"
    assert session.task("produce") == declared
    assert [agent["id"] for agent in session.spec()["agents"]] == ["producer", "reviewer"]
    assert session.work_budget("produce")["calls_cap"] == budget["calls_cap"]
    assert session.work_budget("produce")["tokens_cap"] == budget["tokens_cap"]
    assert call_rows(session, "tool") == []
    assert [row["work_id"] for row in session.tasks()] == ["produce"]


def test_a_tool_argument_naming_an_unauthorized_artifact_resolves_to_nothing(tmp_path):
    session, engine, _ = build(
        tmp_path, [SUBMIT_TOTALS,
                   ("review", 0, response(use("checker.category_totals",
                                              {"candidate_ref": "sha256:" + "f" * 64})))],
        tasks=[produce_task(), review_task()])
    drive(engine, "produce", "produce", "review", "review")
    published = session.snapshot()["artifacts"]
    receipt = next(row for row in call_rows(session, "tool") if row["work_id"] == "review")
    assert json.loads(receipt["response"])[TOOL_KEY] == {"ok": False, "error": "candidate not visible"}
    assert [row["work_id"] for row in published] == ["produce"]
    assert json.loads(published[0]["value"]) == OUTPUT


def test_a_tool_argument_naming_a_filesystem_path_reads_nothing_outside_the_declared_fixtures(tmp_path):
    (tmp_path / "secret.json").write_text('{"orders": []}')
    session, engine, _ = build(tmp_path, [
        ("produce", 0, response(use("fixture.read", {"name": "../secret.json"})))])
    drive(engine, "produce", "produce")
    # The reader is scoped to its declared fixtures, so a path is refused by the schema
    # before any call is reserved: there is no tool row at all, only a recorded rejection.
    assert call_rows(session, "tool") == []
    decisions = session.decisions("produce")
    assert [row["decision"] for row in decisions] == ["rejected"]
    assert "do not conform" in decisions[0]["reason"]
    assert session.snapshot()["artifacts"] == []
    assert not (tmp_path / "secret.json").read_text() == ""


def test_a_task_declaration_naming_a_reserved_action_never_reaches_a_ledger(tmp_path):
    invalid = workflow(tmp_path, tasks=[produce_task(tools=["submit_output"])])
    with pytest.raises(ContractError, match="reserved action"):
        contracts.workflow_spec(invalid)
    with pytest.raises(ContractError):
        OrchestrationSession.create(tmp_path / "session.sqlite", spec=invalid)
    assert not (tmp_path / "session.sqlite").exists()


# ---------------------------------------------------------------- declared limits


def test_exhausting_max_rejections_ends_the_task_abstained_with_no_artifact(tmp_path):
    bad = response(use("submit_output", {"total_cents": "nope"}))
    session, engine, _ = build(tmp_path, [("produce", 0, bad), ("produce", 1, bad)],
                               tasks=[produce_task(limits=dict(TASK_LIMITS, rejections=1))])
    outcome = engine.run()
    assert outcome["status"] == "abstained"
    assert outcome["tasks"]["produce"] == {"status": "abstained", "reason": "rejection_limit", "ref": None}
    assert [row["decision"] for row in session.decisions("produce")] == ["rejected"]
    assert session.snapshot()["artifacts"] == []
    assert session.snapshot()["platform"]["decisions"][0]["work_id"] == "produce"


@pytest.mark.parametrize("limits, label", [({"calls": 2}, "calls"), ({"tokens": 18000}, "tokens")])
def test_a_task_that_cannot_admit_another_model_step_ends_budget_exhausted_with_no_reservation(
        tmp_path, limits, label):
    session, engine, _ = build(tmp_path, [READ_FIXTURE, SUBMIT_AFTER_TOOL],
                               tasks=[produce_task(limits=dict(TASK_LIMITS, **limits))])
    outcome = engine.run()
    assert outcome["status"] == "budget_exhausted"
    assert outcome["tasks"]["produce"]["status"] == "budget_exhausted"
    assert outcome["metrics"]["outstanding_reservations"] == 0
    assert all(row["state"] == "received" for row in session.snapshot()["calls"])
    assert session.snapshot()["artifacts"] == []


def test_a_reopened_ledger_derives_the_spent_rejection_from_durable_rows(tmp_path):
    session, engine, _ = build(tmp_path, [
        ("produce", 0, response(use("submit_output", {"total_cents": "nope"})))],
        tasks=[produce_task(limits=dict(TASK_LIMITS, rejections=1))])
    drive(engine, "produce", "produce")
    reopened, engine2 = reopen(session, engine, [])
    declaration = reopened.task("produce")
    state = engine2._state(declaration, reopened.work_calls_of("produce"), reopened.decisions("produce"))
    assert state["rejections"] == 1
    assert state["remaining"]["rejections"] == 0
    assert reopened.work_budget("produce")["calls"] == TASK_LIMITS["calls"] - 1


# ---------------------------------------------------------------- reservation admission


@pytest.mark.parametrize("label, call_id, mutation, detail", [
    ("not-the-logical-key", "orch:" + "0" * 64, None, "not the logical operation key"),
    ("foreign-spec-digest", None, {"spec_digest": "0" * 64}, "current workflow digest"),
    ("wrong-task-version", None, {"task_version": 2}, "current task version"),
    ("wrong-step-in-binding", None, {"step": 3}, "not the logical operation key"),
    ("undeclared-offered-tool", None, {"tools": [{"name": "checker.category_totals",
                                                  "version": "v1", "schema_digest": "d"}]},
     "offered tools exceed the task declaration"),
])
def test_a_model_reservation_whose_binding_does_not_match_the_ledger_is_refused(
        tmp_path, label, call_id, mutation, detail):
    session, engine, spec = build(tmp_path, [SUBMIT_TOTALS])
    lease = session.claim("producer", "produce")
    payload = copy(model_payload(engine, session, lease))
    if mutation:
        payload["binding"].update(mutation)
    identity = call_id or call_identity(RUN_ID, "produce", lease.version, "model", 0)
    with pytest.raises(StateError, match=detail):
        reserve_model(session, lease, identity, payload)
    assert session.snapshot()["calls"] == []


def test_a_model_reservation_that_is_refused_writes_no_call_row_and_spends_no_budget(tmp_path):
    session, engine, _ = build(tmp_path, [SUBMIT_TOTALS])
    lease = session.claim("producer", "produce")
    before = session.snapshot()
    payload = copy(model_payload(engine, session, lease))
    payload["binding"]["spec_digest"] = "0" * 64
    with pytest.raises(StateError):
        reserve_model(session, lease, call_identity(RUN_ID, "produce", 1, "model", 0), payload)
    after = session.snapshot()
    assert after["calls"] == [] and after["events"] == before["events"]
    assert session.work_budget("produce") == {"calls": TASK_LIMITS["calls"],
                                              "tokens": TASK_LIMITS["tokens"],
                                              "calls_cap": TASK_LIMITS["calls"],
                                              "tokens_cap": TASK_LIMITS["tokens"]}
    # The same payload with its own binding intact is admitted: the refusal above was
    # the binding check, not an unbuildable request.
    call_id = call_identity(RUN_ID, "produce", 1, "model", 0)
    reserve_model(session, lease, call_id, model_payload(engine, session, lease))
    assert [row["id"] for row in session.snapshot()["calls"]] == [call_id]


@pytest.mark.parametrize("label, binding, arguments, tool_ref, detail", [
    ("arguments-digest", {"arguments_digest": "0" * 64}, None, None, "differ from the bound digest"),
    ("changed-arguments", None, {"name": "elsewhere"}, None, "differ from the bound digest"),
    ("receipt-digest", {"receipt_digest": "0" * 64}, None, None, "does not match its model receipt"),
    ("undeclared-tool", {"tool": "checker.category_totals"}, None, "checker.category_totals",
     "outside the task declaration"),
])
def test_a_tool_reservation_whose_binding_does_not_match_its_proposal_is_refused(
        tmp_path, label, binding, arguments, tool_ref, detail):
    session, engine, _, _ = settled_proposal(tmp_path, [READ_FIXTURE])
    model_call = call_identity(RUN_ID, "produce", 1, "model", 0)
    lease = session.claim("producer", "produce")
    payload = copy(tool_payload(engine, session, lease, model_call))
    if binding:
        payload["binding"].update(binding)
    if arguments:
        payload["arguments"] = arguments
    if tool_ref:
        payload["tool_ref"] = tool_ref
    tool_call = call_identity(RUN_ID, "produce", 1, "tool", 0)
    with pytest.raises(StateError, match=detail):
        session.reserve_tool_call(lease, tool_call, payload, source_call_id=model_call, step=0)
    assert call_rows(session, "tool") == []
    assert session.decisions("produce") == []
    # The unmutated binding is admitted and consumes the receipt, so the refusals above
    # are the digest and declaration checks rather than an unbuildable tool call.
    session.reserve_tool_call(lease, tool_call, tool_payload(engine, session, lease, model_call),
                              source_call_id=model_call, step=0)
    assert [row["decision"] for row in session.decisions("produce")] == ["tool"]


@pytest.mark.parametrize("statement, parameters", [
    ("UPDATE artifacts SET value=? WHERE work_id='produce'", (contracts.wire({"total_cents": 0,
                                                                              "totals": []}),)),
    ("UPDATE work SET status='superseded',version=version+1 WHERE id='produce'", ()),
])
def test_dispatch_re_runs_admission_so_a_reservation_bound_to_a_changed_artifact_is_refused(
        tmp_path, statement, parameters):
    session, engine, _ = build(tmp_path, [SUBMIT_TOTALS, REVIEW_CHECK, REVIEW_SUBMIT],
                               tasks=[produce_task(), review_task()])
    drive(engine, "produce", "produce")
    lease = session.claim("reviewer", "review")
    payload = model_payload(engine, session, lease)
    assert [item["producer"] for item in payload["binding"]["inputs"]] == ["produce"]
    call_id = call_identity(RUN_ID, "review", lease.version, "model", 0)
    reserve_model(session, lease, call_id, payload)
    side = sqlite3.connect(session.path, isolation_level=None)
    try:
        side.execute(statement, parameters)
    finally:
        side.close()
    with pytest.raises(StateError, match="no longer authorized or has changed"):
        session.dispatch(lease, call_id)
    assert session.call(call_id)["state"] == "reserved"


def test_a_host_task_cannot_reserve_any_call(tmp_path):
    session, engine, _ = build(tmp_path, [SUBMIT_TOTALS, REVIEW_CHECK, REVIEW_SUBMIT],
                               tasks=[produce_task(), review_task(), finalize_task()])
    drive(engine, "produce", "produce", "review", "review", "review", "review")
    assert {row["id"]: row["status"] for row in session.snapshot()["work"]}["finalize"] == "ready"
    lease = session.claim("host", "finalize")
    payload = {"tool_ref": contracts.MODEL_TOOL_REF, "arguments": {"request": {}},
               "binding": {"kind": "model", "step": 0, "attempt": 0}}
    with pytest.raises(StateError, match="a host task performs no calls"):
        reserve_model(session, lease, call_identity(RUN_ID, "finalize", 1, "model", 0), payload)
    assert session.work_calls_of("finalize") == []


# ---------------------------------------------------------------- derived publication


def test_publish_derived_refuses_a_value_that_differs_from_the_receipts_validated_proposal(tmp_path):
    session, _, _, call_id = settled_proposal(tmp_path)
    lineage = [{"call_id": call_id, "role": "proposal",
                "digest": sha256(contracts.wire(session.call(call_id)["response"]).encode()).hexdigest()}]
    before = session.snapshot()
    with pytest.raises(StateError, match="value differs from the receipt's validated proposal"):
        session.publish_derived("producer", "produce", kind="output",
                                value=dict(OUTPUT, total_cents=9999),
                                source_call_id=call_id, lineage=lineage)
    assert session.snapshot() == before


@pytest.mark.parametrize("label, kind, lineage_of, detail", [
    ("extra-entry", "output", lambda good: good * 2, "lineage is exactly its proposal receipt"),
    ("wrong-digest", "output", lambda good: [dict(good[0], digest="0" * 64)],
     "lineage is exactly its proposal receipt"),
    ("non-dependency", "result", lambda good: good, "settled receipts of declared dependencies"),
    ("unknown-call", "result", lambda good: [dict(good[0], call_id="orch:" + "0" * 64)],
     "settled receipts of declared dependencies"),
])
def test_publish_derived_refuses_a_lineage_that_is_not_the_admitted_derivation(
        tmp_path, label, kind, lineage_of, detail):
    session, _, _, call_id = settled_proposal(tmp_path)
    good = [{"call_id": call_id, "role": "proposal",
             "digest": sha256(contracts.wire(session.call(call_id)["response"]).encode()).hexdigest()}]
    before = session.snapshot()
    with pytest.raises(StateError, match=detail):
        session.publish_derived("producer", "produce", kind=kind, value=OUTPUT,
                                source_call_id=call_id, lineage=lineage_of(good))
    assert session.snapshot() == before
    assert session.artifact_records() == []


def test_publish_derived_refuses_while_a_call_of_the_work_is_reserved(tmp_path):
    session, engine, _, call_id = settled_proposal(tmp_path)
    lease = session.claim("producer", "produce")
    reserve_model(session, lease, call_identity(RUN_ID, "produce", 1, "model", 1),
                  model_payload(engine, session, lease, step=1))
    lineage = [{"call_id": call_id, "role": "proposal",
                "digest": sha256(contracts.wire(session.call(call_id)["response"]).encode()).hexdigest()}]
    with pytest.raises(StateError, match="open reservation or unresolved dispatch"):
        session.publish_derived("producer", "produce", kind="output", value=OUTPUT,
                                source_call_id=call_id, lineage=lineage)
    assert session.snapshot()["artifacts"] == []
    assert [row["state"] for row in session.snapshot()["calls"]] == ["received", "reserved"]


def test_a_model_receipt_can_neither_be_published_nor_become_a_candidate(tmp_path):
    """Structural, not a special case: an orchestration receipt carries no artifact key."""
    session, _, _, call_id = settled_proposal(tmp_path)
    with pytest.raises(StateError, match="only through the derived transition"):
        session.publish_received("producer", call_id, verify=lambda work, value: True)
    lease = session.claim("producer", "produce")
    with pytest.raises(StateError, match="receipt lacks artifact"):
        session.propose(lease, call_id, 0.1)
    with pytest.raises(StateError, match="does not use candidate arbitration"):
        session.commit("produce", verify=lambda work, value: True, abstain_loss=1.0)
    assert session.snapshot()["artifacts"] == []


def test_model_and_tool_receipts_carry_no_artifact_key(tmp_path):
    session, engine, _ = build(tmp_path, [READ_FIXTURE, SUBMIT_AFTER_TOOL])
    engine.run()
    receipts = [json.loads(row["response"]) for row in session.snapshot()["calls"]]
    assert all("artifact" not in receipt for receipt in receipts)
    assert [sorted(set(receipt) & {MODEL_KEY, TOOL_KEY}) for receipt in receipts] == [
        [MODEL_KEY], [TOOL_KEY], [MODEL_KEY]]
    assert [row["kind"] for row in session.artifact_records()] == ["output"]


# ---------------------------------------------------------------- decomposition


def decomposing(tmp_path, entries=None, **options):
    entries = entries or [("totals", 0, response(use("propose_children",
                                                     {"children": [child("books"), child("rest")]})))]
    session, engine, spec = build(tmp_path, entries, tasks=[totals_task()], **options)
    record = engine.step("totals")
    assert record["status"] == "inferred"
    return session, engine, record["call_id"]


@pytest.mark.parametrize("label, children, error, detail", [
    ("cyclic", [child("books", dependencies=["rest"]), child("rest", dependencies=["books"])],
     ValueError, "cyclic work dependencies"),
    ("duplicate-name", [child("books"), child("books")], ContractError, "duplicate child name"),
    ("widened-tools", [child("books", tools=["checker.category_totals"])], ContractError,
     "cannot widen the parent's tools"),
    ("widened-reads", [child("books", reads=["elsewhere"])], ContractError,
     "may read only the parent's reads and its siblings"),
    ("widened-steps", [child("books", limits=dict(CHILD_LIMITS, model_steps=99))], ContractError,
     "cannot widen the parent's model_steps"),
    ("malformed-name", [child("Books")], ContractError, "child name must match"),
    ("join-reserve", [child("books", limits=dict(CHILD_LIMITS, calls=13, tokens=199000))],
     BudgetExceeded, "consume the parent's join reserve"),
    ("task-child-capacity", [child(name) for name in ("a", "b", "c", "d", "e")], BudgetExceeded,
     "exceed the task's declared decomposition bound"),
])
def test_a_refused_decomposition_leaves_the_snapshot_byte_identical(
        tmp_path, label, children, error, detail):
    session, engine, call_id = decomposing(tmp_path)
    lease = session.claim("producer", "totals")
    before = contracts.wire(session.snapshot())
    with pytest.raises(error, match=detail):
        session.admit_children(lease, call_id, children)
    assert contracts.wire(session.snapshot()) == before
    assert [row["work_id"] for row in session.tasks()] == ["totals"]


def test_a_task_cannot_declare_more_children_than_the_run_allows(tmp_path):
    """The run bound is enforced at spec validation, so a task bound can never exceed it.

    With that guard in place the per-parent run-level count inside ``_decompose`` is
    unreachable through ``admit_children``; it stays covered by the platform suite.
    """
    cap = RUN_LIMITS["max_children"]
    task = totals_task(decomposition=dict(DECOMPOSITION, max_children=cap + 1))
    with pytest.raises(ContractError, match="decomposition exceeds max_children"):
        contracts.workflow_spec(workflow(tmp_path, tasks=[task]))
    allowed = totals_task(decomposition=dict(DECOMPOSITION, max_children=cap))
    spec = contracts.workflow_spec(workflow(tmp_path, tasks=[allowed]))
    assert spec["tasks"][0]["decomposition"]["max_children"] == cap


def test_a_decomposition_naming_an_existing_work_id_is_refused(tmp_path):
    decoy = produce_task(id="totals.books", tools=[], instructions="A task whose id collides.",
                         limits=dict(TASK_LIMITS, calls=1, tokens=20000))
    session, engine, spec = build(tmp_path, [("totals", 0, response(use("propose_children",
                                                                        {"children": [child("books")]})))],
                                  tasks=[totals_task(), decoy])
    engine.step("totals")
    lease = session.claim("producer", "totals")
    before = contracts.wire(session.snapshot())
    with pytest.raises(ValueError, match="duplicate or existing child id"):
        session.admit_children(lease, call_identity(RUN_ID, "totals", 1, "model", 0), [child("books")])
    assert contracts.wire(session.snapshot()) == before


def test_the_runtime_records_a_rejection_for_a_refused_decomposition(tmp_path):
    session, engine, _ = build(tmp_path, [
        ("totals", 0, response(use("propose_children",
                                   {"children": [child("books", reads=["elsewhere"])]}))),
        ("totals", 1, response(use("submit_output", OUTPUT), identifier="msg1"))],
        tasks=[totals_task()])
    drive(engine, "totals", "totals")
    decisions = session.decisions("totals")
    assert [row["decision"] for row in decisions] == ["rejected"]
    assert "decomposition refused" in decisions[0]["reason"]
    assert [row["work_id"] for row in session.tasks()] == ["totals"]
    assert session.work_budget("totals")["calls_cap"] == 14


def test_a_children_proposal_above_the_declared_max_children_is_rejected_by_the_schema(tmp_path):
    session, engine, _ = build(tmp_path, [
        ("totals", 0, response(use("propose_children",
                                   {"children": [child(name) for name in ("a", "b", "c", "d")]}))),
        ("totals", 1, response(use("submit_output", OUTPUT), identifier="msg1"))],
        tasks=[totals_task()])
    drive(engine, "totals", "totals")
    decisions = session.decisions("totals")
    assert decisions[0]["decision"] == "rejected"
    assert "propose_children does not conform" in decisions[0]["reason"]
    assert [row["work_id"] for row in session.tasks()] == ["totals"]


def test_admit_children_refuses_more_children_than_the_task_declares(tmp_path):
    session, engine, call_id = decomposing(tmp_path)
    assert session.task("totals")["decomposition"]["max_children"] == 3
    lease = session.claim("producer", "totals")
    with pytest.raises((BudgetExceeded, ContractError)):
        session.admit_children(lease, call_id, [child(name) for name in ("a", "b", "c", "d")])


def test_a_second_decomposition_for_the_same_task_version_is_refused(tmp_path):
    submit = {"total_cents": 1000, "totals": [{"category": "books", "cents": 1000}]}
    session, engine, _ = decomposing(tmp_path, [
        ("totals", 0, response(use("propose_children", {"children": [child("books")]}))),
        ("totals.books", 0, response(use("submit_output", submit), identifier="b0")),
        ("totals", 1, response(use("submit_output", OUTPUT), identifier="msg1"))])
    drive(engine, "totals", "totals.books", "totals.books", "totals")
    second = call_identity(RUN_ID, "totals", 1, "model", 1)
    assert session.call(second)["state"] == "received"
    lease = session.claim("producer", "totals")
    before = contracts.wire(session.snapshot())
    with pytest.raises(StateError, match="already admitted a decomposition"):
        session.admit_children(lease, second, [child("more")])
    assert contracts.wire(session.snapshot()) == before
    assert [row["decision"] for row in session.decisions("totals")] == ["decompose"]


# ---------------------------------------------------------------- accounting


@pytest.mark.parametrize("usage, label", [
    ({"input_tokens": 99999}, "prompt-above-bound"),
    ({"input_tokens": 8000, "cache_creation_input_tokens": 8000, "cache_read_input_tokens": 1000},
     "cache-tokens-above-bound"),
    ({"output_tokens": 99999}, "completion-above-max-new-tokens"),
])
def test_a_usage_report_outside_the_declared_contract_records_a_violation_and_stays_dispatched(
        tmp_path, usage, label):
    session, engine, _ = build(tmp_path, [("produce", 0, response(use("submit_output", OUTPUT),
                                                                  usage=usage))])
    record = engine.step("produce")
    call_id = call_identity(RUN_ID, "produce", 1, "model", 0)
    accounting = session.accounting()[0]
    events = [event for event in session.snapshot()["events"]
              if event["event_type"] == "interaction.session.orchestration.accounting_violation"]
    assert record == {"work": "produce", "status": "blocked_unknown", "call_id": call_id,
                      "reason": "accounting_violation"}
    assert session.call(call_id)["state"] == "dispatched"
    assert accounting["contract"] == "bounded_v2"
    assert accounting["prompt_bound"] == MODEL["prompt_token_bound"]
    assert accounting["violation"]["prompt_bound"] == MODEL["prompt_token_bound"]
    assert accounting["violation"]["max_new_tokens"] == MODEL["max_new_tokens"]
    assert accounting["violation"]["reported"]["usage"] == dict(
        {"input_tokens": 900, "output_tokens": 40, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0}, **usage)
    assert len(events) == 1 and events[0]["details"]["call_id"] == call_id
    assert session.decisions("produce") == [] and session.snapshot()["artifacts"] == []


def test_recording_the_same_accounting_violation_twice_is_idempotent(tmp_path):
    session, engine, _ = build(tmp_path, [("produce", 0, response(use("submit_output", OUTPUT),
                                                                  usage={"input_tokens": 99999}))])
    engine.step("produce")
    call_id = call_identity(RUN_ID, "produce", 1, "model", 0)
    record = session.accounting()[0]["violation"]
    assert session.record_accounting_violation(call_id, record["reported"],
                                               record["response_digest"]) == record
    events = [event for event in session.snapshot()["events"]
              if event["event_type"] == "interaction.session.orchestration.accounting_violation"]
    assert len(events) == 1
    assert session.call(call_id)["state"] == "dispatched"


@pytest.mark.parametrize("label, mutation", [
    ("bad-usage-type", {"usage": {"input_tokens": "900", "output_tokens": 40}}),
    ("unknown-usage-field", {"usage": {"input_tokens": 900, "output_tokens": 40, "extra": 1}}),
    ("unknown-stop-reason", {"stop_reason": "refusal"}),
    ("unknown-block-type", {"content": [{"type": "thinking", "thinking": "unrecorded"}]}),
])
def test_a_malformed_provider_response_leaves_the_call_dispatched_and_records_nothing(
        tmp_path, label, mutation):
    raw = dict(response(use("submit_output", OUTPUT)), **mutation)
    session, engine, _ = build(tmp_path, [("produce", 0, raw)])
    record = engine.step("produce")
    call_id = call_identity(RUN_ID, "produce", 1, "model", 0)
    assert record["status"] == "blocked_unknown" and record["call_id"] == call_id
    assert session.call(call_id)["state"] == "dispatched"
    assert session.accounting()[0]["reported"] is None
    assert session.accounting()[0]["violation"] is None
    assert session.decisions("produce") == [] and session.snapshot()["artifacts"] == []


def test_a_byte_oversized_response_settles_with_its_valid_usage_and_is_consumed_as_a_rejection(tmp_path):
    entries = [("produce", 0, response(text("x" * 5000), use("submit_output", OUTPUT))),
               SUBMIT_AFTER_TOOL]
    session, engine, _ = build(tmp_path, entries, run_limits={"artifact_bytes": 4096})
    first = engine.step("produce")
    call_id = call_identity(RUN_ID, "produce", 1, "model", 0)
    settled = session.call(call_id)
    assert first == {"work": "produce", "status": "response_rejected", "call_id": call_id, "step": 0}
    assert settled["state"] == "response_rejected"
    assert settled["actual"] == 940
    assert settled["response"]["prompt_tokens"] == 900 and settled["response"]["completion_tokens"] == 40
    assert settled["response"]["response_rejected"] == "response_bytes_exceeded"
    assert session.snapshot()["unknown_calls"] == 0
    reopened, engine2 = reopen(session, engine, entries)
    outcome = engine2.run()
    assert outcome["status"] == "success"
    assert [row["decision"] for row in reopened.decisions("produce")] == ["rejected", "submit"]
    assert reopened.decisions("produce")[0]["reason"] == "response exceeded the recorded byte bound"
    assert outcome["metrics"]["unknown_calls"] == 0 and outcome["metrics"]["proposal_rejections"] == 1


def test_reported_prompt_usage_at_the_declared_bound_settles_under_the_bounded_contract(tmp_path):
    usage = {"input_tokens": 8000, "cache_creation_input_tokens": 8000,
             "cache_read_input_tokens": 384, "output_tokens": MODEL["max_new_tokens"]}
    session, engine, _ = build(tmp_path, [("produce", 0, response(use("submit_output", OUTPUT),
                                                                  usage=usage))])
    assert engine.step("produce")["status"] == "inferred"
    call_id = call_identity(RUN_ID, "produce", 1, "model", 0)
    settled, accounting = session.call(call_id), session.accounting()[0]
    assert settled["state"] == "received"
    assert settled["response"]["prompt_tokens"] == MODEL["prompt_token_bound"]
    assert settled["actual"] == MODEL["prompt_token_bound"] + MODEL["max_new_tokens"]
    assert accounting["violation"] is None
    assert accounting["reported"]["usage"] == usage


# ---------------------------------------------------------------- consumption and identity


def test_every_validated_model_receipt_has_exactly_one_decision_row(tmp_path):
    session, engine, _ = build(tmp_path, [READ_FIXTURE, SUBMIT_AFTER_TOOL, REVIEW_CHECK, REVIEW_SUBMIT],
                               tasks=[produce_task(), review_task(), finalize_task()])
    outcome = engine.run()
    decisions = session.decisions()
    model_calls = [row["id"] for row in call_rows(session, "model")]
    assert outcome["status"] == "success"
    assert sorted(row["call_id"] for row in decisions) == sorted(model_calls)
    assert [row["decision"] for row in decisions] == ["tool", "submit", "tool", "submit"]
    assert all(row["validator"] == "orchestration-validator-v1" for row in decisions)
    assert outcome["metrics"]["artifacts"] == 3


def test_reopening_between_settlement_and_consumption_repeats_no_inference_and_no_tool_execution(tmp_path):
    executed, sent = [], []
    entries = [READ_FIXTURE, SUBMIT_AFTER_TOOL]
    session, engine, _ = build(tmp_path, entries, sent=sent)
    original = engine.registry.execute
    engine.registry.execute = lambda name, arguments, resolver: (
        executed.append(name) or original(name, arguments, resolver))
    assert engine.step("produce")["status"] == "inferred"
    assert (len(sent), executed) == (1, [])
    reopened, engine2 = reopen(session, engine, entries, sent=sent)
    assert engine2.step("produce")["status"] == "tool"
    assert (len(sent), executed) == (1, ["fixture.read"])
    reopened2, engine3 = reopen(reopened, engine2, entries, sent=sent)
    assert engine3.step("produce")["status"] == "inferred"
    assert (len(sent), executed) == (2, ["fixture.read"])
    assert [row["binding"]["kind"] for row in call_rows(reopened2)] == ["model", "tool", "model"]
    assert len(call_rows(reopened2, "tool")) == 1


def test_offline_replay_confirms_a_recorded_rejection_without_executing_anything(tmp_path):
    session, engine, _ = build(tmp_path, [
        ("produce", 0, response(use("submit_output", {"total_cents": "1250"}))), SUBMIT_AFTER_TOOL])
    assert engine.run()["status"] == "success"
    report = audit.replay_run(session.path, spec_dir=tmp_path)
    assert report["failures"] == [] and report["status"] == "PASS"
    assert report["counts"]["rejections"] == 1 and report["counts"]["decisions"] == 2
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)
    assert report["accounting_violations"] == []


def test_offline_replay_reports_an_accounting_violation_and_its_unresolved_call(tmp_path):
    session, engine, _ = build(tmp_path, [("produce", 0, response(use("submit_output", OUTPUT),
                                                                  usage={"input_tokens": 99999}))])
    engine.step("produce")
    report = audit.replay_run(session.path, spec_dir=tmp_path)
    assert report["failures"] == [] and report["status"] == "PASS"
    assert report["accounting_violations"] == [call_identity(RUN_ID, "produce", 1, "model", 0)]
    assert report["counts"]["unknown_calls"] == 1 and report["counts"]["known_tokens"] == 0


def test_call_ids_are_the_logical_key_and_an_abandoned_attempt_takes_the_next_attempt_id(tmp_path):
    clock = Clock()
    session, engine, _ = build(tmp_path, [SUBMIT_TOTALS], clock=clock)
    lease = session.claim("producer", "produce", lease_seconds=30)
    first = call_identity(RUN_ID, "produce", 1, "model", 0)
    reserve_model(session, lease, first, model_payload(engine, session, lease))
    clock.now += 100
    session.recover()
    assert session.call(first)["state"] == "abandoned"
    reopened, engine2 = reopen(session, engine, [SUBMIT_TOTALS], clock=clock)
    record = engine2.step("produce")
    assert record["status"] == "inferred"
    assert record["call_id"] == call_identity(RUN_ID, "produce", 1, "model", 0, 1)
    assert [row["id"] for row in reopened.snapshot()["calls"]] == [
        first, call_identity(RUN_ID, "produce", 1, "model", 0, 1)]
    assert reopened.work_budget("produce")["calls"] == TASK_LIMITS["calls"] - 2
