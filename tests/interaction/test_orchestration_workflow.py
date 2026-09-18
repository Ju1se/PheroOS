"""End-to-end orchestration behaviour: what a whole recorded run binds together.

Every run here is driven by the scripted fake transport over the declared example
workflows, so nothing reaches a provider. The assertions are about durable rows:
which artifacts exist, which receipts they name, which digests bind a candidate to
the checker that examined it and to the result that reports the verdict, and what a
restart may not repeat. A published result is never read as a claim of semantic
correctness: one test deliberately breaks the candidate and shows the run still
publishes, marked not accepted.
"""

import ast
import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

import pheroos_interaction
import pheroos_interaction.runner
from pheroos_interaction.records import StateError
from pheroos_interaction.runner import anthropic, audit, cli, contracts, runtime, tools
from pheroos_interaction.runner.orchestration import OrchestrationSession, call_identity

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "orchestration"


class Clock:
    """An injected clock: time moves only when a test says so."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def load_spec(name="workflow.json"):
    return contracts.workflow_spec(json.loads((EXAMPLES / name).read_text()))


def load_script(name="script.json"):
    return json.loads((EXAMPLES / name).read_text())


def scripted(script, task, step):
    """The scripted tool_use block for one (task, step), as the fake provider returns it."""
    for entry in script["responses"]:
        if entry["task"] == task and entry["step"] == step:
            return entry["response"]["content"][0]
    raise AssertionError("the script has no response for %s step %d" % (task, step))


def make_runtime(session, spec, script, **options):
    return runtime.Runtime(session, registry=tools.build_registry(spec, EXAMPLES),
                           transports={"fake": anthropic.FakeTransport(script)}, **options)


class Run:
    """One finished workflow run plus the accessors the assertions need."""

    def __init__(self, spec, session, outcome, engine):
        self.spec, self.session, self.outcome, self.engine = spec, session, outcome, engine

    @property
    def statuses(self):
        return {work: record["status"] for work, record in self.outcome["tasks"].items()}

    @property
    def metrics(self):
        return self.outcome["metrics"]

    def artifacts(self):
        return {row["work_id"]: {**row, "value": json.loads(row["value"])}
                for row in self.session.snapshot()["artifacts"]}

    def value(self, work_id):
        return self.artifacts()[work_id]["value"]

    def calls(self):
        out = []
        for row in self.session.snapshot()["calls"]:
            request = json.loads(row["request"])
            out.append({**row, "request": request, "binding": request.get("binding") or {},
                        "response": json.loads(row["response"]) if row["response"] else None})
        return out

    def call(self, work_id, kind, step):
        found = [call for call in self.calls()
                 if call["work_id"] == work_id and call["binding"].get("kind") == kind
                 and call["binding"].get("step") == step]
        assert len(found) == 1, "expected one %s call at step %d of %s" % (kind, step, work_id)
        return found[0]


def start(tmp_path, *, workflow="workflow.json", script="script.json", mutate=None,
          clock=None, cls=OrchestrationSession, name="session.sqlite", run=True):
    spec = load_spec(workflow)
    body = load_script(script)
    if mutate is not None:
        mutate(body)
    session = cls.create(tmp_path / name, spec=spec, clock=clock)
    engine = make_runtime(session, spec, body)
    return Run(spec, session, engine.run() if run else None, engine)


def reopen(run, *, clock=None, script="script.json", mutate=None):
    """Continue the same ledger from a fresh session object, as a new process would."""
    body = load_script(script)
    if mutate is not None:
        mutate(body)
    session = OrchestrationSession(run.session.path, clock=clock)
    engine = make_runtime(session, run.spec, body)
    return Run(run.spec, session, engine.run(), engine)


def receipt_digest(response):
    return sha256(contracts.wire(response).encode()).hexdigest()


def raw_counts(path):
    """Count the ledger directly, read-only, without going through the session object."""
    database = audit.read_only(path)
    try:
        return {"calls": database.execute("SELECT COUNT(*) FROM calls").fetchone()[0],
                "artifacts": database.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0],
                "decisions": database.execute(
                    "SELECT COUNT(*) FROM orchestration_decisions_v1").fetchone()[0],
                "dispatched": database.execute(
                    "SELECT COUNT(*) FROM calls WHERE state='dispatched'").fetchone()[0],
                "reserved": database.execute(
                    "SELECT COUNT(*) FROM calls WHERE state='reserved'").fetchone()[0],
                "actual": database.execute("SELECT COALESCE(SUM(actual),0) FROM calls").fetchone()[0]}
    finally:
        database.close()


def drop_step(task, step):
    def mutate(script):
        script["responses"] = [entry for entry in script["responses"]
                               if (entry["task"], entry["step"]) != (task, step)]
    return mutate


def break_candidate(script):
    """Change exactly one field of the scripted candidate, leaving the review script alone."""
    scripted(script, "produce", 1)["input"]["total_cents"] = 6500


@pytest.fixture
def completed(tmp_path):
    return start(tmp_path)


@pytest.fixture
def broken(tmp_path):
    return start(tmp_path, mutate=break_candidate)


# ---------------------------------------------------------------- the two-agent example

def test_two_agent_example_completes_with_success_and_every_task_published(completed):
    assert completed.outcome["format"] == contracts.OUTCOME_FORMAT
    assert completed.outcome["status"] == "success"
    assert completed.statuses == {"produce": "published", "review": "published",
                                 "finalize": "published"}
    assert all(record["ref"] for record in completed.outcome["tasks"].values())


def test_two_agent_example_makes_four_model_calls_two_tool_calls_and_three_artifacts(completed):
    assert (completed.metrics["model_calls"], completed.metrics["tool_calls"]) == (4, 2)
    assert completed.metrics["artifacts"] == 3
    assert set(completed.artifacts()) == {"produce", "review", "finalize"}
    kinds = {row["work_id"]: row["kind"] for row in completed.session.artifact_records()}
    assert kinds == {"produce": "output", "review": "output", "finalize": "result"}
    assert completed.metrics["proposal_rejections"] == 0
    assert (completed.metrics["unknown_calls"], completed.metrics["outstanding_reservations"]) == (0, 0)


def test_produce_artifact_equals_the_scripted_submit_output_payload(completed):
    proposed = scripted(load_script(), "produce", 1)
    assert proposed["name"] == "submit_output"
    assert completed.value("produce") == proposed["input"]
    assert completed.value("review") == scripted(load_script(), "review", 1)["input"]


def test_each_model_receipt_reserves_the_declared_bound_and_settles_the_reported_usage(completed):
    bounds = {agent["id"]: agent["model"] for agent in completed.spec["agents"]}
    accounting = {row["call_id"]: row for row in completed.session.accounting()}
    agents = {task["id"]: task["agents"][0] for task in completed.spec["tasks"]}
    models = [call for call in completed.calls() if call["binding"].get("kind") == "model"]
    assert len(models) == 4
    for call in models:
        model = bounds[agents[call["work_id"]]]
        assert (call["prompt"], call["maximum"]) == (model["prompt_token_bound"],
                                                     model["max_new_tokens"])
        assert call["reserved"] == model["prompt_token_bound"] + model["max_new_tokens"]
        assert call["actual"] == call["response"]["prompt_tokens"] + call["response"]["completion_tokens"]
        row = accounting[call["id"]]
        assert (row["contract"], row["prompt_bound"]) == ("bounded_v2", model["prompt_token_bound"])
        assert row["violation"] is None
        assert 0 < row["reported"]["prompt_tokens"] <= row["prompt_bound"]


def test_call_ids_are_the_logical_operation_keys_of_their_bindings(completed):
    for call in completed.calls():
        binding = call["binding"]
        assert call["id"] == call_identity(completed.spec["run_id"], call["work_id"],
                                           call["version"], binding["kind"], binding["step"],
                                           binding.get("attempt", 0))
        assert call["id"].startswith("orch:")


def test_every_model_request_header_names_its_own_task_version_and_step(completed):
    for call in completed.calls():
        if call["binding"].get("kind") != "model":
            continue
        header = call["request"]["arguments"]["request"]["system"].split("\n")[0]
        assert header == "pheroos-orchestration task=%s version=%d step=%d" % (
            call["work_id"], call["version"], call["binding"]["step"])
        assert anthropic.HEADER.match(header)


def test_model_receipts_carry_message_and_tool_receipts_carry_result_without_an_artifact_key(completed):
    for call in completed.calls():
        assert "artifact" not in call["response"]
        if call["binding"]["kind"] == "model":
            assert set(call["response"]) == {"message", "tool_ref", "prompt_tokens",
                                             "completion_tokens"}
            assert call["response"]["message"]["content"]
        else:
            assert set(call["response"]) == {"result", "tool_ref", "prompt_tokens",
                                             "completion_tokens"}
            assert call["response"]["result"]["ok"] is True


def test_legacy_publication_paths_refuse_orchestration_receipts(completed):
    receipt = completed.call("produce", "model", 1)["id"]
    with pytest.raises(StateError, match="derived transition"):
        completed.session.publish_received("producer", receipt, verify=lambda work, value: True)
    with pytest.raises(StateError, match="does not use candidate arbitration"):
        completed.session.commit("produce", "producer", verify=lambda work, value: True,
                                 abstain_loss=1.0)


def test_each_settled_model_receipt_has_exactly_one_decision_row(completed):
    decisions = completed.session.decisions()
    by_call = [row["call_id"] for row in decisions]
    models = [call for call in completed.calls() if call["binding"]["kind"] == "model"]
    assert sorted(by_call) == sorted(call["id"] for call in models)
    assert len(set(by_call)) == len(by_call)
    assert [(row["work_id"], row["step"], row["decision"]) for row in decisions] == [
        ("produce", 0, "tool"), ("produce", 1, "submit"),
        ("review", 0, "tool"), ("review", 1, "submit")]
    for row in decisions:
        assert row["receipt_digest"] == receipt_digest(
            next(call["response"] for call in models if call["id"] == row["call_id"]))


# ---------------------------------------------------------------- the digest chain

def test_checker_receipt_records_the_digest_of_the_produce_artifact_value(completed):
    checker = completed.call("review", "tool", 0)
    result = checker["response"]["result"]
    assert result["ok"] is True
    assert checker["binding"]["tool"] == "checker.category_totals"
    assert result["value"]["candidate_digest"] == contracts.digest(completed.value("produce"))
    assert result["value"]["candidate_ref"] == "produce"
    assert result["value"]["pass"] is True
    assert result["value"]["detail"]["mismatches"] == []


def test_finalize_result_binds_the_candidate_digest_checker_call_and_decision_provenance(completed):
    candidate = completed.artifacts()["produce"]
    checker = completed.call("review", "tool", 0)
    result = completed.value("finalize")
    assert result["format"] == runtime.RESULT_FORMAT
    assert result["accepted"] is True
    assert result["rule"] == "checker_pass"
    assert result["candidate"] == {"ref": candidate["ref"], "digest": contracts.digest(candidate["value"]),
                                   "work": "produce", "value": candidate["value"]}
    assert result["checker"]["call_id"] == checker["id"]
    assert result["checker"]["tool"] == "checker.category_totals"
    assert result["checker"]["version"] == "category-totals-v1"
    assert result["checker"]["result"] == checker["response"]["result"]["value"]
    assert result["decision"] == {"by": "host", "reason": "checker pass",
                                  "spec_digest": completed.session.snapshot()["orchestration"]["spec_digest"]}
    assert completed.artifacts()["finalize"]["call_id"] == checker["id"]
    assert completed.artifacts()["finalize"]["publisher"] == "host"


def test_candidate_checker_and_result_share_one_unbroken_digest(completed):
    digest = contracts.digest(completed.value("produce"))
    assert completed.call("review", "tool", 0)["response"]["result"]["value"]["candidate_digest"] == digest
    assert completed.value("finalize")["candidate"]["digest"] == digest
    assert completed.value("finalize")["candidate"]["value"] == completed.value("produce")


def test_every_artifact_lineage_row_names_a_settled_receipt(completed):
    calls = {call["id"]: call for call in completed.calls()}
    records = completed.session.artifact_records()
    assert len(records) == 3
    for record in records:
        assert record["lineage"]
        for item in record["lineage"]:
            source = calls[item["call_id"]]
            assert source["state"] == "received"
            assert item["digest"] == receipt_digest(source["response"])
            assert item["role"] in ("proposal", "checker", "candidate")


def test_output_lineage_is_exactly_the_proposal_receipt_of_its_own_task(completed):
    records = {row["work_id"]: row for row in completed.session.artifact_records()}
    for work in ("produce", "review"):
        receipt = completed.call(work, "model", 1)
        assert records[work]["lineage"] == [{"call_id": receipt["id"],
                                             "digest": receipt_digest(receipt["response"]),
                                             "role": "proposal"}]
    lineage = records["finalize"]["lineage"]
    assert [item["role"] for item in lineage] == ["checker", "candidate"]
    assert lineage[0]["call_id"] == completed.call("review", "tool", 0)["id"]
    assert lineage[1]["call_id"] == completed.call("produce", "model", 1)["id"]


# ---------------------------------------------------------------- publication is not acceptance

def test_one_field_change_in_the_candidate_makes_the_checker_report_pass_false(broken):
    result = broken.call("review", "tool", 0)["response"]["result"]
    assert result["ok"] is True
    assert result["value"]["pass"] is False
    assert result["value"]["detail"]["mismatches"] == ["total_cents: expected 6499, got 6500"]
    assert broken.value("produce")["total_cents"] == 6500


def test_a_failed_checker_publishes_a_rejection_and_is_not_reported_as_success(broken):
    # Every task is terminal and every artifact published, but the acceptance rule
    # rejected the candidate: reporting that as success would be a false success.
    assert broken.outcome["status"] == "rejected"
    assert "finalize" in broken.outcome["reason"]
    assert broken.statuses == {"produce": "published", "review": "published",
                               "finalize": "published"}
    assert broken.metrics["artifacts"] == 3
    result = broken.value("finalize")
    assert result["accepted"] is False
    assert result["decision"]["reason"] == "checker fail"
    assert result["review"]["value"]["verdict"] == "accept"


def test_the_refused_result_still_carries_the_mutated_candidate_digest_chain(broken):
    digest = contracts.digest(broken.value("produce"))
    assert broken.call("review", "tool", 0)["response"]["result"]["value"]["candidate_digest"] == digest
    assert broken.value("finalize")["candidate"]["digest"] == digest
    assert broken.value("finalize")["checker"]["call_id"] == broken.call("review", "tool", 0)["id"]


# ---------------------------------------------------------------- decomposition

@pytest.fixture
def decomposed(tmp_path):
    return start(tmp_path, workflow="workflow-decomposition.json",
                 script="script-decomposition.json")


def test_decomposition_example_admits_exactly_the_two_declared_children(decomposed):
    rows = {row["work_id"]: row for row in decomposed.session.tasks()}
    children = {key: row for key, row in rows.items() if row["origin"] == "decomposition"}
    assert set(children) == {"totals.books", "totals.rest"}
    assert all(row["parent"] == "totals" for row in children.values())
    assert all(row["agents"] == ["producer"] for row in children.values())
    assert set(rows) - set(children) == {"totals", "review", "finalize"}


def test_admitted_children_narrow_the_parent_tools_reads_and_limits(decomposed):
    parent = decomposed.session.task("totals")
    for key in ("totals.books", "totals.rest"):
        child = decomposed.session.task(key)
        assert set(child["tools"]) <= set(parent["tools"])
        assert set(child["reads"]) <= set(parent["reads"]) | {"totals.books", "totals.rest"}
        for field in ("model_steps", "tool_calls", "rejections"):
            assert child["limits"][field] <= parent["limits"][field]
        assert child["output_schema"] == parent["decomposition"]["child_output_schema"]
        assert child["decomposition"] is None


def test_parent_caps_fall_by_exactly_the_transferred_child_budgets(decomposed):
    declared = next(task for task in decomposed.spec["tasks"] if task["id"] == "totals")["limits"]
    children = [decomposed.session.work_budget(key) for key in ("totals.books", "totals.rest")]
    parent = decomposed.session.work_budget("totals")
    assert parent["calls_cap"] == declared["calls"] - sum(row["calls_cap"] for row in children)
    assert parent["tokens_cap"] == declared["tokens"] - sum(row["tokens_cap"] for row in children)


def test_parent_keeps_its_declared_join_reserve_after_admitting_children(decomposed):
    reserve = next(task for task in decomposed.spec["tasks"]
                   if task["id"] == "totals")["decomposition"]["join_reserve"]
    budget = decomposed.session.work_budget("totals")
    assert budget["calls"] >= reserve["calls"]
    assert budget["tokens"] >= reserve["tokens"]


def test_children_are_admitted_once_as_a_single_decompose_decision(decomposed):
    decisions = decomposed.session.decisions("totals")
    assert [row["decision"] for row in decisions] == ["decompose", "submit"]
    assert decisions[0]["step"] == 0
    assert decisions[0]["reason"] == "children admitted: totals.books, totals.rest"
    assert decisions[0]["call_id"] == decomposed.call("totals", "model", 0)["id"]


def test_the_parent_reads_both_child_artifacts_in_its_later_step(decomposed):
    binding = decomposed.call("totals", "model", 1)["binding"]
    assert [item["producer"] for item in binding["inputs"]] == ["totals.books", "totals.rest"]
    published = decomposed.artifacts()
    for item in binding["inputs"]:
        assert item["digest"] == contracts.digest(published[item["producer"]]["value"])
    assert decomposed.session.task("totals")["reads"] == [], "the declaration itself never widens"
    assert decomposed.call("totals", "model", 0)["binding"]["inputs"] == []


def test_decomposition_example_publishes_five_artifacts_from_eight_model_calls(decomposed):
    assert decomposed.outcome["status"] == "success"
    assert decomposed.statuses == {"totals": "published", "totals.books": "published",
                                   "totals.rest": "published", "review": "published",
                                   "finalize": "published"}
    assert decomposed.metrics["model_calls"] == 8
    assert decomposed.metrics["artifacts"] == 5
    assert decomposed.value("totals")["total_cents"] == (
        decomposed.value("totals.books")["total_cents"] + decomposed.value("totals.rest")["total_cents"])
    assert decomposed.value("finalize")["accepted"] is True


# ---------------------------------------------------------------- no hardcoded names

@pytest.fixture
def reused(tmp_path):
    return start(tmp_path, workflow="workflow-expected.json", script="script-expected.json")


def test_a_workflow_with_different_agent_and_task_names_completes_the_same_way(reused):
    assert {agent["id"] for agent in reused.spec["agents"]} == {"author", "auditor"}
    assert reused.outcome["status"] == "success"
    assert reused.statuses == {"draft": "published", "audit": "published", "decide": "published"}
    assert (reused.metrics["model_calls"], reused.metrics["tool_calls"]) == (4, 2)
    assert reused.metrics["artifacts"] == 3


def test_the_reused_workflow_result_names_its_own_checker_candidate_and_review(reused):
    result = reused.value("decide")
    assert result["candidate"]["work"] == "draft"
    assert result["candidate"]["digest"] == contracts.digest(reused.value("draft"))
    assert result["checker"]["tool"] == "checker.expected_json"
    assert result["checker"]["call_id"] == reused.call("audit", "tool", 0)["id"]
    assert result["review"]["value"] == reused.value("audit")
    assert result["accepted"] is True


# ---------------------------------------------------------------- one step at a time

class CountingRuntime(runtime.Runtime):
    """Record how many durable calls each step of each sweep added to the ledger."""

    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.added, self.sweep = [], 0

    def _count(self, work_id):
        return sum(row["work_id"] == work_id for row in self.session.snapshot()["calls"])

    def _select_work(self, stalled=()):
        self.sweep += 1
        return super()._select_work(stalled)

    def step(self, work_id, agent=None):
        before = self._count(work_id)
        record = super().step(work_id, agent)
        self.added.append((self.sweep, work_id, self._count(work_id) - before))
        return record


@pytest.mark.parametrize("workflow,script,calls", [
    ("workflow.json", "script.json", 6),
    ("workflow-decomposition.json", "script-decomposition.json", 11),
])
def test_a_sweep_performs_at_most_one_call_of_one_task(tmp_path, workflow, script, calls):
    spec = load_spec(workflow)
    session = OrchestrationSession.create(tmp_path / "session.sqlite", spec=spec)
    engine = CountingRuntime(session, registry=tools.build_registry(spec, EXAMPLES),
                             transports={"fake": anthropic.FakeTransport(load_script(script))})
    outcome = engine.run()
    assert outcome["status"] == "success"
    assert engine.added, "the run performed no step at all"
    assert max(added for _, _, added in engine.added) == 1
    # The L2 allocation policy hands back one task per sweep, so a sweep performs at
    # most one durable call in total, of exactly one task.
    for sweep in {number for number, _, _ in engine.added}:
        in_sweep = [work for number, work, added in engine.added if number == sweep and added]
        assert len(in_sweep) <= 1
    assert len({number for number, _, _ in engine.added}) == len(engine.added)
    assert sum(added for _, _, added in engine.added) == len(session.snapshot()["calls"]) == calls


def test_one_step_of_one_task_adds_at_most_one_call(tmp_path):
    spec = load_spec()
    session = OrchestrationSession.create(tmp_path / "session.sqlite", spec=spec)
    engine = make_runtime(session, spec, load_script())
    statuses, counts = [], []
    for _ in range(5):
        before = len(session.snapshot()["calls"])
        record = engine.step("produce")
        statuses.append(record["status"])
        counts.append(len(session.snapshot()["calls"]) - before)
    assert statuses == ["inferred", "tool", "inferred", "published", "unavailable"]
    assert counts == [1, 1, 1, 0, 0]


# ---------------------------------------------------------------- metrics

def test_metrics_match_the_ledger_rows(completed):
    counts = raw_counts(completed.session.path)
    metrics = completed.engine.metrics()
    assert metrics["model_calls"] + metrics["tool_calls"] == counts["calls"]
    # Commitment is reported as an available capability, never as an arm that ran:
    # the runtime has no entry point for it and the ledger recorded no arbitration.
    assert metrics["policies"] == {
        "runtime_policies": {"allocation": "fifo", "lease": "evaporation"},
        "platform_capabilities": {"commitment": {"name": "min_loss", "active_decisions": 0}}}
    assert metrics["artifacts"] == counts["artifacts"]
    assert metrics["decisions"] == counts["decisions"]
    assert metrics["known_tokens"] == counts["actual"]
    assert metrics["unknown_calls"] == counts["dispatched"] == 0
    assert metrics["outstanding_reservations"] == counts["reserved"] == 0
    assert metrics["blocked_dependencies"] == len(completed.session.blocked_work()) == 0
    assert {key: completed.metrics[key] for key in metrics} == metrics


# ---------------------------------------------------------------- restart and recovery

def test_a_crash_before_publication_publishes_from_the_settled_receipt_without_new_inference(tmp_path):
    class FailPublication(OrchestrationSession):
        def _event(self, db, kind, work, payload):
            super()._event(db, kind, work, payload)
            if kind == "published" and work == "produce":
                raise RuntimeError("simulated process boundary failure")

    crashed = start(tmp_path, cls=FailPublication)
    assert crashed.outcome["status"] == "error"
    assert crashed.statuses["produce"] == "error"
    assert crashed.metrics["model_calls"] == 2 and crashed.metrics["artifacts"] == 0
    receipt = crashed.call("produce", "model", 1)
    assert receipt["state"] == "received"

    resumed = reopen(crashed)
    assert resumed.outcome["status"] == "success"
    assert resumed.metrics["model_calls"] == 4, "the settled proposal was consumed, not repeated"
    assert resumed.artifacts()["produce"]["call_id"] == receipt["id"]
    assert resumed.value("produce") == scripted(load_script(), "produce", 1)["input"]


def test_a_lease_held_by_a_dead_process_recovers_and_consumes_the_pending_proposal(tmp_path):
    class FailRelease(OrchestrationSession):
        def _event(self, db, kind, work, payload):
            super()._event(db, kind, work, payload)
            if kind == "platform.released":
                raise RuntimeError("simulated process death before release")

    clock = Clock()
    spec = load_spec()
    session = FailRelease.create(tmp_path / "session.sqlite", spec=spec, clock=clock)
    engine = make_runtime(session, spec, load_script())
    with pytest.raises(RuntimeError, match="process death"):
        engine.run()
    work = {row["id"]: row["status"] for row in session.snapshot()["work"]}
    assert work["produce"] == "leased"
    dead = Run(spec, session, None, engine)
    receipt = dead.call("produce", "model", 0)
    assert receipt["state"] == "received"

    clock.now += 600
    resumed = reopen(dead, clock=clock)
    assert resumed.outcome["status"] == "success"
    assert resumed.metrics["model_calls"] == 4, "the settled step-0 receipt was not re-inferred"
    assert resumed.call("produce", "model", 0)["id"] == receipt["id"]
    assert resumed.call("produce", "tool", 0)["binding"]["model_call_id"] == receipt["id"]


def test_an_unscripted_step_leaves_its_call_dispatched_and_is_never_retried(tmp_path):
    blocked = start(tmp_path, mutate=drop_step("produce", 1))
    assert blocked.outcome["status"] == "blocked_unknown"
    assert blocked.statuses["produce"] == "blocked_unknown"
    assert blocked.metrics["unknown_calls"] == 1
    dispatched = [call for call in blocked.calls() if call["state"] == "dispatched"]
    assert [call["binding"]["step"] for call in dispatched] == [1]
    before = raw_counts(blocked.session.path)

    again = reopen(blocked, mutate=drop_step("produce", 1))
    assert again.outcome["status"] == "blocked_unknown"
    assert raw_counts(again.session.path) == before, "an unresolved call is never redispatched"
    assert again.metrics["artifacts"] == 0


# ---------------------------------------------------------------- the command line

def read_report(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_cli_orchestrate_freezes_the_run_and_returns_zero(tmp_path, capsys):
    output = tmp_path / "run"
    code = cli.main(["orchestrate", "--workflow", str(EXAMPLES / "workflow.json"),
                     "--output", str(output), "--script", str(EXAMPLES / "script.json")])
    assert code == 0
    report = read_report(capsys)
    assert report["status"] == "success"
    assert sorted(path.name for path in output.iterdir()) == ["frozen.json", "outcome.json",
                                                              "session.sqlite"]
    frozen = json.loads((output / "frozen.json").read_text())
    assert frozen["spec_digest"] == contracts.digest(load_spec())
    assert frozen["spec_dir"] == str(EXAMPLES.resolve())
    assert json.loads((output / "outcome.json").read_text()) == report
    assert raw_counts(output / "session.sqlite")["calls"] == 6


def test_cli_orchestrate_refuses_to_reuse_an_output_directory(tmp_path):
    output = tmp_path / "run"
    output.mkdir()
    with pytest.raises(FileExistsError):
        cli.main(["orchestrate", "--workflow", str(EXAMPLES / "workflow.json"),
                  "--output", str(output), "--script", str(EXAMPLES / "script.json")])


def test_cli_orchestrate_resume_of_a_finished_run_adds_no_calls(tmp_path, capsys):
    output = tmp_path / "run"
    cli.main(["orchestrate", "--workflow", str(EXAMPLES / "workflow.json"),
              "--output", str(output), "--script", str(EXAMPLES / "script.json")])
    capsys.readouterr()
    before = raw_counts(output / "session.sqlite")
    code = cli.main(["orchestrate-resume", "--run", str(output),
                     "--script", str(EXAMPLES / "script.json")])
    assert code == 0
    report = read_report(capsys)
    assert report["status"] == "success"
    assert report["metrics"]["sweeps"] == 1
    assert raw_counts(output / "session.sqlite") == before
    assert (output / "outcome-resume-1.json").exists()


def test_cli_orchestrate_resume_refuses_a_different_script(tmp_path, capsys):
    output = tmp_path / "run"
    cli.main(["orchestrate", "--workflow", str(EXAMPLES / "workflow.json"),
              "--output", str(output), "--script", str(EXAMPLES / "script.json")])
    capsys.readouterr()
    other = tmp_path / "other-script.json"
    other.write_text(json.dumps(load_script("script-expected.json")))
    with pytest.raises(ValueError, match="different model script"):
        cli.main(["orchestrate-resume", "--run", str(output), "--script", str(other)])
    assert raw_counts(output / "session.sqlite")["calls"] == 6


def test_cli_orchestrate_replay_verifies_the_recorded_run(tmp_path, capsys):
    output = tmp_path / "run"
    cli.main(["orchestrate", "--workflow", str(EXAMPLES / "workflow.json"),
              "--output", str(output), "--script", str(EXAMPLES / "script.json")])
    capsys.readouterr()
    code = cli.main(["orchestrate-replay", "--run", str(output)])
    report = read_report(capsys)
    assert (code, report["status"]) == (0, "PASS")
    assert report["failures"] == []
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)
    assert report["counts"]["model_calls"] == 4
    assert report["counts"]["tool_calls"] == 2
    assert report["counts"]["artifacts"] == 3
    assert raw_counts(output / "session.sqlite")["calls"] == 6, "replay writes nothing"


def test_replay_verifies_the_decomposed_run_including_the_children_requests(decomposed):
    report = audit.replay_run(decomposed.session.path, spec_dir=EXAMPLES)
    assert (report["status"], report["failures"]) == ("PASS", [])
    assert report["counts"]["model_calls"] == 8
    assert report["counts"]["tool_calls"] == 3
    assert report["counts"]["artifacts"] == 5
    assert report["checks"] > report["counts"]["model_calls"]


def test_a_resumed_outcome_reports_the_artifact_references_it_calls_published(tmp_path):
    finished = start(tmp_path)
    resumed = reopen(finished)
    assert resumed.outcome["status"] == "success"
    published = resumed.artifacts()
    assert set(published) == set(resumed.outcome["tasks"])
    for work, record in resumed.outcome["tasks"].items():
        assert record["status"] == "published"
        assert record["ref"] == published[work]["ref"]


def test_cli_returns_two_when_the_workflow_did_not_succeed(tmp_path, capsys):
    script = tmp_path / "short-script.json"
    body = load_script()
    drop_step("produce", 1)(body)
    script.write_text(json.dumps(body))
    output = tmp_path / "run"
    code = cli.main(["orchestrate", "--workflow", str(EXAMPLES / "workflow.json"),
                     "--output", str(output), "--script", str(script)])
    assert code == 2
    assert read_report(capsys)["status"] == "blocked_unknown"
    assert raw_counts(output / "session.sqlite")["dispatched"] == 1


# ---------------------------------------------------------------- dependency boundary

def module_files(package):
    root = Path(package.__file__).resolve().parent
    files = sorted(path for path in root.glob("*.py"))
    assert files, "no source files were scanned for %s" % package.__name__
    return files


def imported_targets(path):
    """Every dotted name an import statement of this module names, relative ones included."""
    out = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            out.append(prefix)
            out.extend(prefix + ("." if node.module else "") + alias.name for alias in node.names)
    return out


def test_pure_policy_modules_import_no_runner_module():
    files = module_files(pheroos_interaction)
    assert {path.name for path in files} >= {"commitment.py", "records.py", "sequential.py"}
    for path in files:
        for target in imported_targets(path):
            parts = [part for part in target.lstrip(".").split(".") if part]
            assert "runner" not in parts, "%s imports %s" % (path.name, target)


def test_runner_modules_import_only_the_standard_library_and_the_pure_package():
    allowed = set(sys.stdlib_module_names) | {"pheroos_interaction"}
    files = module_files(pheroos_interaction.runner)
    assert len(files) >= 18
    for path in files:
        for target in imported_targets(path):
            if target.startswith("."):
                continue
            root = target.split(".")[0]
            assert root in allowed, "%s imports third-party %s" % (path.name, target)
