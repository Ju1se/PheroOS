"""Crash, restart and termination semantics of the bounded orchestration runtime.

Every crash here is injected durably: a session subclass raises inside a chosen
``_event`` kind, so the enclosing transaction rolls back exactly as a process death
would leave it, and the assertions read the reopened ledger rather than a mock. The
injected clock is the only source of time, so lease expiry is explicit rather than
slept for. Transport sends and tool executions are counted across the restart, so
"never re-sent" and "never re-executed" are observations, not expectations.
"""

import json
from pathlib import Path

import pytest

from pheroos_interaction.commitment import optimal_stopping_rule
from pheroos_interaction.records import StateError
from pheroos_interaction.runner import anthropic, audit, contracts, runtime, tools
from pheroos_interaction.runner.orchestration import MODEL_KEY, OrchestrationSession, call_identity
from pheroos_interaction.runner.platform import PlatformSession
from pheroos_interaction.runner.session import Session
from pheroos_interaction.runner import runtime_policies as policy
from pheroos_interaction.runner.worker import waiting_rule

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "orchestration"
MODEL = {"provider": "fake", "model": "fake-model", "max_new_tokens": 256,
         "prompt_token_bound": 8192, "prompt_overhead_tokens": 400}
RUN_LIMITS = {"max_calls": 32, "token_cap": 200000, "context_bytes": 131072, "artifact_bytes": 16384,
              "max_work_items": 8, "max_children": 4, "max_depth": 2, "max_platform_operations": 256}
NOTE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["note"],
               "properties": {"note": {"type": "string", "maxLength": 64, "minLength": 1}}}
WAIT_CONFIG = {"abstain_loss": 1.0, "latency_cost": 0.001, "deadline": 3, "arrival_prob": 0.9,
               "loss_support": [0.05], "loss_probs": [1.0], "tick_seconds": 60.0}
EXAMPLE_CALLS = (("produce", "model", 0), ("produce", "tool", 0), ("produce", "model", 1),
                 ("review", "model", 0), ("review", "tool", 0), ("review", "model", 1))


class Crash(BaseException):
    """A simulated process death: not an Exception, so no handler in the runtime swallows it."""


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class CrashSession(OrchestrationSession):
    """An orchestration ledger that dies inside a chosen durable event."""

    def __init__(self, path, *, clock=None, crash=None):
        super().__init__(path, clock=clock)
        self.crash = crash or (lambda kind, work, count: False)
        self.counts = {}

    def _event(self, db, kind, work, payload):
        super()._event(db, kind, work, payload)
        self.counts[(kind, work)] = self.counts.get((kind, work), 0) + 1
        if self.crash(kind, work, self.counts[(kind, work)]):
            raise Crash("%s/%s#%d" % (kind, work, self.counts[(kind, work)]))


def on_event(kind, work=None, occurrence=None):
    """Die the first time (or on the nth occurrence of) one durable event is written."""
    def crash(written, task, count):
        return (written == kind and (work is None or task == work)
                and (occurrence is None or count == occurrence))
    return crash


def hard_crash(kind, work=None):
    """Die on an event and on the release that would otherwise tidy the lease away.

    A real process death performs no ``finally``: the work stays leased until the
    lease expires. Refusing the release too reproduces that ledger state exactly.
    """
    reached = []

    def crash(written, task, count):
        if written == kind and (work is None or task == work):
            reached.append(written)
            return True
        return bool(reached) and written in ("reservation_abandoned", "platform.released")
    return crash


class Harness:
    """A workflow ledger plus its registry, script and shared send/execute logs."""

    def __init__(self, tmp_path, spec, spec_dir, script, clock, name="session.sqlite"):
        self.path = tmp_path / name
        self.spec = spec
        self.clock = clock
        self.script = script
        self.sent = []
        self.executed = []
        self.registry = tools.build_registry(spec, spec_dir)
        original = self.registry.execute

        def execute(name, arguments, resolver):
            self.executed.append(name)
            return original(name, arguments, resolver)
        self.registry.execute = execute
        OrchestrationSession.create(self.path, spec=spec, clock=clock)

    def open(self, crash=None):
        if crash is None:
            return OrchestrationSession(self.path, clock=self.clock)
        return CrashSession(self.path, clock=self.clock, crash=crash)

    def run(self, session=None, **options):
        session = self.open() if session is None else session
        return runtime.run_workflow(
            session, registry=self.registry,
            transports={"fake": anthropic.FakeTransport(self.script, calls=self.sent)}, **options)

    def sweep(self, session, sweeps=1):
        return runtime.Runtime(
            session, registry=self.registry,
            transports={"fake": anthropic.FakeTransport(self.script, calls=self.sent)}).run(max_sweeps=sweeps)

    def key(self, task, kind, step, attempt=0, version=1):
        return call_identity(self.spec["run_id"], task, version, kind, step, attempt)

    def calls(self):
        return {row["id"]: row for row in self.open().snapshot()["calls"]}

    def headers(self):
        return [request["system"].split("\n", 1)[0] for request in self.sent]

    def scripted(self, task, step):
        raw = next(entry["response"] for entry in self.script["responses"]
                   if entry["task"] == task and entry["step"] == step)
        return anthropic.extract(raw)


def header(task, step, version=1):
    return anthropic.HEADER_PREFIX + "task=%s version=%d step=%d" % (task, version, step)


def load(name):
    return contracts.workflow_spec(json.loads((EXAMPLES / name).read_text()))


def task_spec(name, *, dependencies=(), reads=(), calls=8, model_steps=3):
    return {"id": name, "kind": "model", "agent": "solo", "instructions": "Answer with one action.",
            "dependencies": list(dependencies), "reads": list(reads), "tools": [],
            "output_schema": NOTE_SCHEMA,
            "limits": {"model_steps": model_steps, "tool_calls": 0, "rejections": 1,
                       "calls": calls, "tokens": 50000}}


def mini_spec(tasks, run_id="mini-run"):
    """A reduced workflow: one agent, no tools, no fixtures; small enough to reason about."""
    return contracts.workflow_spec({
        "format": contracts.SPEC_FORMAT, "run_id": run_id,
        "agents": [{"id": "solo", "model": MODEL, "capabilities": {"tools": []}}],
        "tools": [], "fixtures": {}, "tasks": tasks, "limits": RUN_LIMITS})


def response(identifier, name, arguments):
    return {"id": identifier, "type": "message", "role": "assistant", "model": "fake-model",
            "stop_reason": "tool_use", "usage": {"input_tokens": 100, "output_tokens": 10},
            "content": [{"type": "tool_use", "id": "toolu_" + identifier, "name": name, "input": arguments}]}


def script_of(*entries):
    return anthropic.validate_script({"format": "fake-model-script-v1", "responses": [
        {"task": task, "step": step, "response": body} for task, step, body in entries]})


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def example(tmp_path, clock):
    return Harness(tmp_path, load("workflow.json"), EXAMPLES,
                   anthropic.load_script(EXAMPLES / "script.json"), clock)


@pytest.fixture
def decomposed(tmp_path, clock):
    return Harness(tmp_path, load("workflow-decomposition.json"), EXAMPLES,
                   anthropic.load_script(EXAMPLES / "script-decomposition.json"), clock)


@pytest.fixture
def abstaining(tmp_path, clock):
    """produce abstains; consume declares it as a dependency it can never read."""
    spec = mini_spec([task_spec("produce"),
                      task_spec("consume", dependencies=["produce"], reads=["produce"])])
    script = script_of(("produce", 0, response("p0", "abstain", {"reason": "the evidence is insufficient"})))
    return Harness(tmp_path, spec, tmp_path, script, clock)


# ---------------------------------------------------------------- 1. crash before dispatch

def test_crash_before_dispatch_sends_nothing_and_leaves_one_reserved_call(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("dispatched")))
    calls = example.calls()
    assert example.sent == []
    assert list(calls) == [example.key("produce", "model", 0)]
    assert calls[example.key("produce", "model", 0)]["state"] == "reserved"
    assert calls[example.key("produce", "model", 0)]["response"] is None


def test_crash_before_dispatch_leaves_the_work_leased_until_the_lease_expires(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("dispatched")))
    work = {row["id"]: row for row in example.open().snapshot()["work"]}["produce"]
    assert (work["status"], work["owner"]) == ("leased", "producer")
    # The lease length is the L3 policy's, not a constant baked into the runtime.
    ttl = policy.RuntimePolicies.from_spec(example.open().spec()).lease_duration()
    assert ttl == 120.0 and work["expires"] == example.clock.now + ttl


def test_lease_expiry_abandons_the_reservation_and_keeps_the_abandoned_row(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("dispatched")))
    example.clock.now += 300
    reopened = example.open()
    reopened.recover()
    abandoned = reopened.call(example.key("produce", "model", 0))
    assert abandoned["state"] == "abandoned"
    assert abandoned["actual"] == 0
    assert {row["id"]: row["status"] for row in reopened.snapshot()["work"]}["produce"] == "ready"


def test_the_attempt_after_an_abandoned_reservation_uses_the_attempt_indexed_call_id(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("dispatched")))
    example.clock.now += 300
    outcome = example.run()
    assert outcome["status"] == "success"
    calls = example.calls()
    assert calls[example.key("produce", "model", 0)]["state"] == "abandoned"
    assert calls[example.key("produce", "model", 0, attempt=1)]["state"] == "received"
    assert example.headers().count(header("produce", 0)) == 1


def test_a_restart_after_a_pre_dispatch_crash_publishes_every_declared_artifact(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("dispatched")))
    example.clock.now += 300
    outcome = example.run()
    reopened = example.open()
    assert outcome["status"] == "success"
    assert len(example.sent) == 4
    assert {row["work_id"]: row["kind"] for row in reopened.artifact_records()} == {
        "produce": "output", "review": "output", "finalize": "result"}


def test_an_abandoned_reservation_releases_its_tokens_but_keeps_its_call_slot(example):
    model = next(agent["model"] for agent in example.spec["agents"] if agent["id"] == "producer")
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("dispatched")))
    example.clock.now += 300
    held = example.open().work_budget("produce")
    reopened = example.open()
    reopened.recover()
    after = reopened.work_budget("produce")
    assert held["tokens"] == held["tokens_cap"] - model["prompt_token_bound"] - model["max_new_tokens"]
    assert after["tokens"] == after["tokens_cap"]
    assert (held["calls"], after["calls"]) == (after["calls_cap"] - 1, after["calls_cap"] - 1)


def test_repeated_pre_dispatch_crashes_exhaust_the_declared_call_cap(tmp_path, clock):
    harness = Harness(tmp_path, mini_spec([task_spec("produce", calls=2)]), tmp_path,
                      script_of(("produce", 0, response("p0", "submit_output", {"note": "ok"}))), clock)
    for _ in range(2):
        with pytest.raises(Crash):
            harness.run(harness.open(hard_crash("dispatched")))
        clock.now += 300
    outcome = harness.run()
    assert harness.sent == []
    assert [row["state"] for row in harness.open().snapshot()["calls"]] == ["abandoned", "abandoned"]
    assert outcome["status"] == "budget_exhausted"
    assert outcome["tasks"]["produce"]["status"] == "budget_exhausted"
    assert harness.open().snapshot()["artifacts"] == []


def test_a_recovered_pre_dispatch_abandonment_replays_without_a_failure(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("dispatched")))
    example.clock.now += 300
    example.run()
    report = audit.replay_run(example.path, spec_dir=EXAMPLES)
    assert report["failures"] == []
    assert report["status"] in ("PASS", "LIMITED")
    assert report["counts"]["outstanding_reservations"] == 0
    assert report["new_model_calls"] == 0


# ---------------------------------------------------------------- 2. crash after dispatch

def test_crash_after_dispatch_sends_once_and_leaves_the_call_dispatched(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    calls = example.calls()
    assert example.headers() == [header("produce", 0)]
    assert calls[example.key("produce", "model", 0)]["state"] == "dispatched"
    assert {row["id"]: row["status"] for row in example.open().snapshot()["work"]}["produce"] == "uncertain"


def test_no_sweep_ever_re_sends_a_dispatched_call(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    outcomes = [example.run() for _ in range(3)]
    assert [outcome["status"] for outcome in outcomes] == ["blocked_unknown"] * 3
    assert len(example.sent) == 1
    assert example.calls()[example.key("produce", "model", 0)]["state"] == "dispatched"
    assert outcomes[-1]["metrics"]["unknown_calls"] == 1
    assert outcomes[-1]["tasks"]["produce"]["status"] == "blocked_unknown"


def test_a_legitimate_late_receipt_settles_the_unknown_call_and_reconciles_the_work(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    example.run()
    call_id = example.key("produce", "model", 0)
    artifact, prompt, completion = example.scripted("produce", 0)
    reopened = example.open()
    reopened.receive(call_id, {MODEL_KEY: artifact, "tool_ref": contracts.MODEL_TOOL_REF,
                               "prompt_tokens": prompt, "completion_tokens": completion})
    assert reopened.call(call_id)["state"] == "received"
    assert {row["id"]: row["status"] for row in reopened.snapshot()["work"]}["produce"] == "ready"
    assert any(event["event_type"] == "interaction.session.reconciled"
               for event in reopened.snapshot()["events"])


def test_a_sweep_after_a_late_receipt_consumes_it_without_another_model_call(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    example.run()
    call_id = example.key("produce", "model", 0)
    artifact, prompt, completion = example.scripted("produce", 0)
    reopened = example.open()
    reopened.receive(call_id, {MODEL_KEY: artifact, "tool_ref": contracts.MODEL_TOOL_REF,
                               "prompt_tokens": prompt, "completion_tokens": completion})
    example.sweep(reopened)
    assert len(example.sent) == 1
    assert example.executed == ["fixture.read"]
    assert [(row["call_id"], row["decision"]) for row in reopened.decisions("produce")] == [(call_id, "tool")]


def test_a_run_continued_from_a_late_receipt_never_repeats_the_unknown_step(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    example.run()
    call_id = example.key("produce", "model", 0)
    artifact, prompt, completion = example.scripted("produce", 0)
    example.open().receive(call_id, {MODEL_KEY: artifact, "tool_ref": contracts.MODEL_TOOL_REF,
                                     "prompt_tokens": prompt, "completion_tokens": completion})
    outcome = example.run()
    assert outcome["status"] == "success"
    assert example.headers().count(header("produce", 0)) == 1
    assert len(example.sent) == 4
    assert outcome["metrics"]["unknown_calls"] == 0


def test_explicit_recovery_reports_a_hard_crash_after_dispatch_as_blocked_unknown(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("received")))
    assert {row["id"]: row["status"] for row in example.open().snapshot()["work"]}["produce"] == "leased"
    example.clock.now += 300
    reopened = example.open()
    reopened.recover()
    assert {row["id"]: row["status"] for row in reopened.snapshot()["work"]}["produce"] == "uncertain"
    outcome = example.run(reopened)
    assert outcome["status"] == "blocked_unknown"
    assert len(example.sent) == 1


def test_a_restart_after_a_hard_crash_following_dispatch_reports_blocked_unknown(example):
    with pytest.raises(Crash):
        example.run(example.open(hard_crash("received")))
    example.clock.now += 300
    outcome = example.run()
    assert example.calls()[example.key("produce", "model", 0)]["state"] == "dispatched"
    assert len(example.sent) == 1
    assert outcome["status"] == "blocked_unknown"


# ---------------------------------------------------------------- 3. crash before consumption

def test_crash_before_consumption_leaves_a_settled_receipt_with_no_decision(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("orchestration.decision")))
    reopened = example.open()
    assert [row["state"] for row in reopened.snapshot()["calls"]] == ["received"]
    assert reopened.decisions() == []
    assert len(example.sent) == 1
    assert example.executed == []


def test_a_restart_consumes_an_unconsumed_receipt_without_new_inference(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("orchestration.decision")))
    example.clock.now += 300
    outcome = example.run()
    assert outcome["status"] == "success"
    assert len(example.sent) == 4
    assert example.headers().count(header("produce", 0)) == 1
    assert outcome["metrics"]["model_calls"] == 4


def test_a_consumed_receipt_carries_exactly_one_recorded_decision(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("orchestration.decision")))
    example.clock.now += 300
    example.run()
    reopened = example.open()
    recorded = [row["call_id"] for row in reopened.decisions()]
    assert len(recorded) == len(set(recorded)) == 4
    assert [row["decision"] for row in reopened.decisions("produce")] == ["tool", "submit"]


# ---------------------------------------------------------------- 4. crash after a tool ran

def test_crash_after_a_tool_result_settles_records_the_consumption_durably(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("reserved", work="produce", occurrence=3)))
    reopened = example.open()
    assert example.executed == ["fixture.read"]
    assert {row["id"]: row["state"] for row in reopened.snapshot()["calls"]} == {
        example.key("produce", "model", 0): "received", example.key("produce", "tool", 0): "received"}
    assert [(row["step"], row["decision"]) for row in reopened.decisions("produce")] == [(0, "tool")]


def test_a_restart_does_not_execute_an_already_settled_tool_call_again(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("reserved", work="produce", occurrence=3)))
    example.clock.now += 300
    outcome = example.run()
    assert outcome["status"] == "success"
    assert example.executed == ["fixture.read", "checker.category_totals"]
    assert outcome["metrics"]["tool_calls"] == 2
    assert example.calls()[example.key("produce", "tool", 0)]["state"] == "received"


def test_a_settled_tool_receipt_keeps_its_bound_model_receipt_across_a_restart(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("reserved", work="produce", occurrence=3)))
    before = example.calls()[example.key("produce", "tool", 0)]
    example.clock.now += 300
    example.run()
    after = example.calls()[example.key("produce", "tool", 0)]
    assert before["request"] == after["request"] and before["response"] == after["response"]
    assert json.loads(after["request"])["binding"]["model_call_id"] == example.key("produce", "model", 0)


# ---------------------------------------------------------------- 5. crash after decomposition

def test_crash_after_child_admission_records_the_children_and_one_decompose_decision(decomposed):
    with pytest.raises(Crash):
        decomposed.run(decomposed.open(on_event("claimed", work="totals.books")))
    reopened = decomposed.open()
    assert [row["work_id"] for row in reopened.tasks() if row["parent"] == "totals"] == [
        "totals.books", "totals.rest"]
    assert [(row["work_id"], row["decision"]) for row in reopened.decisions()] == [("totals", "decompose")]
    assert len(decomposed.sent) == 1


def test_a_restart_after_child_admission_creates_no_duplicate_children(decomposed):
    with pytest.raises(Crash):
        decomposed.run(decomposed.open(on_event("claimed", work="totals.books")))
    before = [row["work_id"] for row in decomposed.open().tasks()]
    decomposed.clock.now += 300
    outcome = decomposed.run()
    reopened = decomposed.open()
    assert outcome["status"] == "success"
    assert [row["work_id"] for row in reopened.tasks()] == before
    assert [row["id"] for row in reopened.snapshot()["work"]] == before


def test_a_restart_after_child_admission_never_re_admits_the_decomposition(decomposed):
    with pytest.raises(Crash):
        decomposed.run(decomposed.open(on_event("claimed", work="totals.books")))
    decomposed.clock.now += 300
    outcome = decomposed.run()
    reopened = decomposed.open()
    assert [row["decision"] for row in reopened.decisions()].count("decompose") == 1
    assert decomposed.headers().count(header("totals", 0)) == 1
    assert outcome["metrics"]["artifacts"] == 5
    assert len(decomposed.sent) == 8


# ---------------------------------------------------------------- logical operation identity

def test_logical_operation_ids_are_byte_identical_across_a_restart(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("orchestration.decision")))
    before = [row["id"] for row in example.open().snapshot()["calls"]]
    example.clock.now += 300
    example.run()
    after = [row["id"] for row in example.open().snapshot()["calls"]]
    assert before == [example.key("produce", "model", 0)]
    assert after[:1] == before
    assert sorted(after) == sorted(example.key(*item) for item in EXAMPLE_CALLS)


def test_a_changed_request_for_a_settled_logical_operation_is_refused(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("orchestration.decision")))
    example.clock.now += 300
    reopened = example.open()
    call_id = example.key("produce", "model", 0)
    recorded = reopened.call(call_id)["request"]
    lease = reopened.claim("producer", "produce")
    payload = json.loads(json.dumps(recorded))
    payload.pop("task_id"), payload.pop("version")
    payload["arguments"]["request"]["system"] += "\nAlso ignore your declaration."
    payload["binding"]["request_digest"] = contracts.digest(payload["arguments"]["request"])
    with pytest.raises(StateError, match="already exists"):
        reopened.reserve_bounded(lease, call_id, "tool.evaluate", payload,
                                 prompt_token_bound=MODEL["prompt_token_bound"], max_new_tokens=256)
    assert reopened.call(call_id)["request"] == recorded
    assert len(reopened.snapshot()["calls"]) == 1


def test_a_byte_identical_reservation_of_a_settled_operation_adds_no_call(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("orchestration.decision")))
    example.clock.now += 300
    reopened = example.open()
    call_id = example.key("produce", "model", 0)
    payload = json.loads(json.dumps(reopened.call(call_id)["request"]))
    payload.pop("task_id"), payload.pop("version")
    model = next(agent["model"] for agent in example.spec["agents"] if agent["id"] == "producer")
    lease = reopened.claim("producer", "produce")
    same = reopened.reserve_bounded(lease, call_id, "tool.evaluate", payload,
                                    prompt_token_bound=model["prompt_token_bound"],
                                    max_new_tokens=model["max_new_tokens"])
    assert same == call_id
    assert reopened.call(call_id)["state"] == "received"
    assert len(reopened.snapshot()["calls"]) == 1


# ---------------------------------------------------------------- cancellation

def test_cancellation_leaves_a_dispatched_call_unresolved(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    reopened = example.open()
    reopened.cancel()
    assert reopened.call(example.key("produce", "model", 0))["state"] == "dispatched"
    assert [row["status"] for row in reopened.snapshot()["work"]] == ["cancelled"] * 3


def test_cancellation_blocks_every_publication_path(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    call_id = example.key("produce", "model", 0)
    artifact, prompt, completion = example.scripted("produce", 0)
    reopened = example.open()
    reopened.cancel()
    reopened.receive(call_id, {MODEL_KEY: artifact, "tool_ref": contracts.MODEL_TOOL_REF,
                               "prompt_tokens": prompt, "completion_tokens": completion})
    with pytest.raises(StateError, match="cancelled"):
        reopened.publish_derived("producer", "produce", kind="output", value={"note": "x"},
                                 source_call_id=call_id,
                                 lineage=[{"call_id": call_id, "digest": "0" * 64, "role": "proposal"}])
    with pytest.raises(StateError):
        reopened.publish_received("producer", call_id, verify=lambda work, value: True)
    assert reopened.snapshot()["artifacts"] == []


def test_a_cancelled_run_yields_the_cancelled_outcome_and_sends_nothing_more(example):
    with pytest.raises(Crash):
        example.run(example.open(on_event("received")))
    example.open().cancel()
    outcome = example.run()
    assert outcome["status"] == "cancelled"
    assert outcome["reason"] == "the run was cancelled"
    assert set(item["status"] for item in outcome["tasks"].values()) == {"cancelled"}
    assert len(example.sent) == 1
    assert outcome["metrics"]["unknown_calls"] == 1
    assert outcome["metrics"]["artifacts"] == 0


# ---------------------------------------------------------------- terminal abstention

def test_an_abstained_dependency_is_reported_by_blocked_work(abstaining):
    abstaining.run()
    assert abstaining.open().blocked_work() == [
        {"work": "consume", "dependency": "produce", "status": "done"}]


def test_a_failed_dependency_terminates_the_run_instead_of_polling(abstaining):
    outcome = abstaining.run()
    assert outcome["status"] == "dependency_failed"
    assert outcome["tasks"]["produce"]["status"] == "abstained"
    assert outcome["tasks"]["consume"]["status"] == "dependency_failed"
    assert outcome["metrics"]["sweeps"] < outcome["metrics"]["max_sweeps"]
    assert outcome["metrics"]["blocked_dependencies"] == 1


def test_no_artifact_is_fabricated_for_a_failed_dependency_or_its_dependent(abstaining):
    abstaining.run()
    reopened = abstaining.open()
    assert reopened.snapshot()["artifacts"] == []
    assert reopened.artifact_records() == []
    assert reopened.readable_artifacts("consume", "solo") == []


def test_an_agent_abstention_is_terminal_and_a_restart_does_not_re_run_it(abstaining):
    first = abstaining.run()
    decisions = abstaining.open().decisions()
    second = abstaining.run()
    reopened = abstaining.open()
    assert [row["decision"] for row in decisions] == ["abstain"]
    assert reopened.decisions() == decisions
    assert len(abstaining.sent) == 1
    assert first["status"] == second["status"] == "dependency_failed"
    assert {row["id"]: row["status"] for row in reopened.snapshot()["work"]}["produce"] == "done"


# ---------------------------------------------------------------- bounded WAIT

def platform_work(tmp_path, clock=None, name="wait.sqlite"):
    return PlatformSession.create(
        tmp_path / name, "wait-run", agents=["a", "b"], token_cap=1000, max_calls=20, clock=clock,
        platform={}, work=[{"id": "w", "version": 1, "dependencies": [], "agents": ["a", "b"],
                            "actions": ["tool.evaluate"]}])


def candidate(session, agent, call_id, loss, lease_seconds=10_000):
    lease = session.claim(agent, "w", lease_seconds=lease_seconds)
    session.reserve(lease, call_id, "tool.evaluate", {"tool_ref": "t", "arguments": {}},
                    prompt_tokens=0, max_new_tokens=0)
    session.dispatch(lease, call_id)
    session.receive(call_id, {"artifact": {"value": 7}, "prompt_tokens": 0, "completion_tokens": 0})
    session.propose(lease, call_id, loss)
    return lease


def verify(_work, value):
    return value == {"value": 7}


def waits(session):
    return sum(event["event_type"] == "interaction.session.platform.waited"
               for event in session.snapshot()["events"])


@pytest.mark.parametrize("sources", [[], ["a", "a"], "a", None, [1]])
def test_waiting_refuses_a_configuration_without_declared_candidate_sources(tmp_path, sources):
    session = platform_work(tmp_path)
    candidate(session, "a", "receipt-a", 0.9)
    with pytest.raises(ValueError, match="distinct declared candidate sources"):
        waiting_rule(session, "w", **dict(WAIT_CONFIG, candidate_sources=sources))


def test_waiting_refuses_a_candidate_source_that_is_not_an_agent_of_the_work(tmp_path):
    session = platform_work(tmp_path)
    candidate(session, "a", "receipt-a", 0.9)
    with pytest.raises(ValueError, match="agents declared for the work"):
        waiting_rule(session, "w", **dict(WAIT_CONFIG, candidate_sources=["a", "outsider"]))


@pytest.mark.parametrize("deadline", [0, -1, 3.0, True])
def test_waiting_refuses_a_configuration_without_a_positive_integer_deadline(tmp_path, deadline):
    session = platform_work(tmp_path)
    candidate(session, "a", "receipt-a", 0.9)
    with pytest.raises(ValueError, match="deadline"):
        waiting_rule(session, "w", **dict(WAIT_CONFIG, candidate_sources=["a", "b"], deadline=deadline))


def test_waiting_returns_none_once_every_declared_source_has_proposed(tmp_path):
    session = platform_work(tmp_path)
    candidate(session, "a", "receipt-a", 0.9)
    assert waiting_rule(session, "w", **dict(WAIT_CONFIG, candidate_sources=["a"])) is None
    assert callable(waiting_rule(session, "w", **dict(WAIT_CONFIG, candidate_sources=["a", "b"])))


def test_the_default_minimum_loss_rule_publishes_when_waiting_returns_none(tmp_path):
    session = platform_work(tmp_path)
    candidate(session, "a", "receipt-a", 0.9)
    rule = waiting_rule(session, "w", **dict(WAIT_CONFIG, candidate_sources=["a"]))
    result = session.commit("w", "a", verify=verify, abstain_loss=1.0, rule=rule, lease_seconds=10_000)
    assert rule is None
    assert result["decision"] == "publish"
    assert waits(session) == 0


def sweep(session, sources=("a", "b")):
    rule = waiting_rule(session, "w", **dict(WAIT_CONFIG, candidate_sources=list(sources)))
    return session.commit("w", "a", verify=verify, abstain_loss=1.0, rule=rule,
                          lease_seconds=10_000)["decision"]


def test_a_tight_polling_loop_never_advances_the_decision_clock(tmp_path):
    """The tick is recorded ledger time, so sweeping without waiting manufactures no arrival."""
    clock = Clock()
    session = platform_work(tmp_path, clock=clock)
    candidate(session, "a", "receipt-a", 0.9)
    assert [sweep(session) for _ in range(WAIT_CONFIG["deadline"] + 4)] == \
        ["wait"] * (WAIT_CONFIG["deadline"] + 4)
    assert session.snapshot()["artifacts"] == []
    stamps = {event["details"]["at"] for event in session.snapshot()["events"]
              if event["event_type"] == "interaction.session.platform.waited"}
    assert stamps == {clock.now}


def test_repeated_commit_sweeps_wait_only_until_the_declared_deadline(tmp_path):
    """With real elapsed time the programme reaches its deadline and then publishes."""
    clock = Clock()
    session = platform_work(tmp_path, clock=clock)
    candidate(session, "a", "receipt-a", 0.9)
    decisions = []
    for _ in range(WAIT_CONFIG["deadline"] + 4):
        decisions.append(sweep(session))
        if decisions[-1] != "wait":
            break
        clock.now += WAIT_CONFIG["tick_seconds"]
    assert decisions == ["wait"] * WAIT_CONFIG["deadline"] + ["publish"]
    assert waits(session) == WAIT_CONFIG["deadline"]
    assert [row["work_id"] for row in session.snapshot()["artifacts"]] == ["w"]


def test_a_fixed_elapsed_tick_would_wait_forever_even_as_time_passes(tmp_path):
    clock = Clock()
    session = platform_work(tmp_path, clock=clock)
    candidate(session, "a", "receipt-a", 0.9)
    fixed = optimal_stopping_rule(**{k: v for k, v in WAIT_CONFIG.items() if k != "tick_seconds"},
                                  elapsed=0)
    decisions = []
    for _ in range(WAIT_CONFIG["deadline"] + 4):
        decisions.append(session.commit("w", "a", verify=verify, abstain_loss=1.0, rule=fixed,
                                        lease_seconds=10_000)["decision"])
        clock.now += WAIT_CONFIG["tick_seconds"]
    assert decisions == ["wait"] * (WAIT_CONFIG["deadline"] + 4)
    assert waits(session) == WAIT_CONFIG["deadline"] + 4
    assert session.snapshot()["artifacts"] == []


def test_waiting_refuses_a_ledger_without_platform_state_or_an_unknown_work(tmp_path):
    plain = Session.create(tmp_path / "plain.sqlite", "plain-run", agents=["a"], token_cap=10, max_calls=5,
                           work=[{"id": "w", "version": 1, "dependencies": [], "agents": ["a"],
                                  "actions": ["tool.evaluate"]}])
    with pytest.raises(StateError, match="platform ledger"):
        waiting_rule(plain, "w", **dict(WAIT_CONFIG, candidate_sources=["a"]))
    with pytest.raises(StateError, match="unknown work"):
        waiting_rule(platform_work(tmp_path), "absent", **dict(WAIT_CONFIG, candidate_sources=["a"]))
