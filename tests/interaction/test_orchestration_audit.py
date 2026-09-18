"""Offline replay of recorded orchestration runs, and the commitment seams it protects.

Part 1 records the three example workflows for real, then replays each recorded ledger
offline: a clean record must PASS while executing nothing, and every tampered record
must FAIL with a named check rather than pass silently. Nothing here asserts that a
mock was called; every claim is made against durable rows, a copied-and-mutated ledger,
a reopened session or an injected fault.

Part 2 exercises the commitment boundary through the real ``PlatformSession.commit``
API: at a certified loss exactly equal to the ledger's abstention loss the optimal
stopping rule abstains terminally instead of driving the ledger into its
``rule cannot publish at or above abstention loss`` refusal, while the dynamic
programme's values, its recall branch and cross-inhibition are unchanged.
"""

from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from pheroos_interaction import commitment
from pheroos_interaction.records import StateError
from pheroos_interaction.runner import anthropic, audit, contracts, runtime, tools
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.orchestration import OrchestrationSession
from pheroos_interaction.runner.platform import PlatformSession

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "orchestration"
WORKFLOWS = {"base": ("workflow.json", "script.json"),
             "decomposition": ("workflow-decomposition.json", "script-decomposition.json"),
             "expected": ("workflow-expected.json", "script-expected.json")}
# The recorded shape of each example run, asserted once so the tamper tests below are
# known to operate on a real, complete record rather than on an empty ledger.
RECORDED = {"base": {"model_calls": 4, "tool_calls": 2, "artifacts": 3, "decisions": 4},
            "decomposition": {"model_calls": 8, "tool_calls": 3, "artifacts": 5, "decisions": 8},
            "expected": {"model_calls": 4, "tool_calls": 2, "artifacts": 3, "decisions": 4}}


# ---------------------------------------------------------------- recording helpers

def load_spec(workflow):
    return contracts.workflow_spec(json.loads((EXAMPLES / workflow).read_text()))


def run_recorded(path, workflow, script, *, session_class=OrchestrationSession):
    """Record one real run of an example workflow; ``sent`` collects every dispatched request."""
    spec = load_spec(workflow)
    session = session_class.create(path, spec=spec)
    sent = []
    transport = anthropic.FakeTransport(script if type(script) is dict
                                        else anthropic.load_script(EXAMPLES / script), calls=sent)
    outcome = runtime.run_workflow(session, registry=tools.build_registry(spec, EXAMPLES),
                                   transports={"fake": transport})
    return {"path": path, "spec": spec, "outcome": outcome, "sent": sent}


@pytest.fixture(scope="session")
def recorded(tmp_path_factory):
    """One real run per example workflow, recorded once and never mutated by a test."""
    root = tmp_path_factory.mktemp("recorded")
    runs = {}
    for name, (workflow, script) in WORKFLOWS.items():
        runs[name] = run_recorded(root / (name + ".sqlite"), workflow, script)
        assert runs[name]["outcome"]["status"] == "success"
    return runs


def copy_ledger(recorded, name, tmp_path):
    target = tmp_path / (name + "-copy.sqlite")
    shutil.copy(recorded[name]["path"], target)
    return target


def tamper(recorded, name, tmp_path, mutate):
    """Copy a recorded ledger and apply one destructive mutation to the copy."""
    target = copy_ledger(recorded, name, tmp_path)
    database = sqlite3.connect(target)
    database.row_factory = sqlite3.Row
    try:
        mutate(database)
        database.commit()
    finally:
        database.close()
    return target


def replay(path):
    return audit.replay_run(path, spec_dir=EXAMPLES)


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(text):
    return sha256(text.encode()).hexdigest()


def named(report, prefix):
    return [failure for failure in report["failures"] if failure.startswith(prefix)]


def assert_detected(report, *prefixes):
    """A tampered record fails loudly, names the checks it failed, and still executes nothing."""
    assert report["status"] == "FAIL"
    assert report["failures"], "tampering produced a silent pass"
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)
    for prefix in prefixes:
        assert named(report, prefix), (prefix, report["failures"])


def file_digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- part 1a: clean replay

@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_replay_of_a_real_recorded_run_passes_and_counts_zero_new_calls(recorded, name):
    report = replay(recorded[name]["path"])
    assert report["status"] == "PASS" and report["failures"] == []
    assert report["format"] == audit.AUDIT_FORMAT and report["mode"] == "offline replay"
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)
    assert report["checks"] > 0 and report["accounting_violations"] == []
    assert report["source_match"] is True, "a matching source identity is what separates PASS from LIMITED"


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_replay_counts_match_the_calls_the_run_actually_recorded(recorded, name):
    report = replay(recorded[name]["path"])
    counts = {key: report["counts"][key] for key in RECORDED[name]}
    assert counts == RECORDED[name]
    assert report["counts"]["unknown_calls"] == report["counts"]["outstanding_reservations"] == 0
    assert report["counts"]["model_calls"] == len(recorded[name]["sent"])
    assert report["run_status"] == "completed"
    assert report["run_id"] == recorded[name]["spec"]["run_id"]
    assert report["spec_digest"] == contracts.digest(recorded[name]["spec"])


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_replay_leaves_the_ledger_snapshot_and_file_bytes_identical(recorded, name, tmp_path):
    path = copy_ledger(recorded, name, tmp_path)
    before = wire(OrchestrationSession(path).snapshot())
    before_bytes = file_digest(path)
    assert replay(path)["status"] == "PASS"
    assert file_digest(path) == before_bytes
    assert wire(OrchestrationSession(path).snapshot()) == before


def test_read_only_connection_refuses_every_kind_of_write(recorded):
    connection = audit.read_only(recorded["base"]["path"])
    try:
        for statement, arguments in (
                ("UPDATE run SET status='cancelled'", ()),
                ("UPDATE calls SET response=NULL", ()),
                ("DELETE FROM orchestration_decisions_v1", ()),
                ("INSERT INTO events(value) VALUES (?)", ("{}",)),
                ("UPDATE orchestration_artifacts_v1 SET lineage='[]'", ()),
                ("DROP TABLE orchestration_accounting_v1", ())):
            with pytest.raises(sqlite3.OperationalError):
                connection.execute(statement, arguments)
        assert connection.execute("SELECT COUNT(*) FROM calls").fetchone()[0] > 0
    finally:
        connection.close()


def test_replay_executes_no_tool_and_sends_no_request(recorded, monkeypatch):
    """Replay rebuilds requests; a registry whose tools explode and a live transport prove it runs nothing."""
    def armed(spec, spec_dir):
        registry = tools.build_registry(spec, spec_dir)
        registry.execute = lambda *args, **options: pytest.fail("replay executed a tool")
        return registry

    monkeypatch.setattr(audit, "build_registry", armed)
    sent = recorded["base"]["sent"]
    before = len(sent)
    report = replay(recorded["base"]["path"])
    assert report["status"] == "PASS" and report["failures"] == []
    assert len(sent) == before == RECORDED["base"]["model_calls"]


def test_replay_of_a_run_left_with_an_unresolved_dispatch_passes_and_reports_it(tmp_path):
    script = anthropic.load_script(EXAMPLES / "script.json")
    trimmed = {"format": script["format"],
               "responses": [item for item in script["responses"]
                             if (item["task"], item["step"]) != ("review", 1)]}
    record = run_recorded(tmp_path / "unresolved.sqlite", "workflow.json", trimmed)
    assert record["outcome"]["status"] == "blocked_unknown"
    report = replay(record["path"])
    assert report["status"] == "PASS" and report["failures"] == []
    assert report["counts"]["unknown_calls"] == 1 and report["counts"]["artifacts"] == 1


def test_replay_of_a_run_that_crashed_before_recording_consumption_fabricates_nothing(tmp_path):
    """A fault between settlement and the admitted transition leaves a receipt and no artifact."""
    class Crashing(OrchestrationSession):
        def _event(self, db, kind, work, payload):
            if kind == "orchestration.decision" and payload.get("decision") == "submit":
                raise RuntimeError("injected crash before the submit decision is recorded")
            return super()._event(db, kind, work, payload)

    record = run_recorded(tmp_path / "crash.sqlite", "workflow.json", "script.json", session_class=Crashing)
    assert record["outcome"]["status"] == "error"
    reopened = OrchestrationSession(record["path"])
    assert reopened.snapshot()["artifacts"] == [] and len(reopened.decisions()) == 1
    report = replay(record["path"])
    assert report["status"] == "PASS" and report["failures"] == []
    assert report["counts"]["artifacts"] == 0 and report["counts"]["model_calls"] == 2


# ---------------------------------------------------------------- part 1b: tamper detection

def test_replay_detects_an_altered_request_body(recorded, tmp_path):
    def mutate(db):
        row = db.execute("SELECT id,request FROM calls ORDER BY rowid LIMIT 1").fetchone()
        request = json.loads(row["request"])
        request["arguments"]["request"]["messages"][0]["content"][0]["text"] += " (inserted later)"
        db.execute("UPDATE calls SET request=? WHERE id=?", (wire(request), row["id"]))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "request_rebuild:", "request_digest:")


def test_replay_detects_an_altered_stored_response(recorded, tmp_path):
    def mutate(db):
        row = db.execute("SELECT id,response FROM calls WHERE state='received' ORDER BY rowid LIMIT 1").fetchone()
        response = json.loads(row["response"])
        response["message"]["id"] = "msg_substituted"
        db.execute("UPDATE calls SET response=? WHERE id=?", (wire(response), row["id"]))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "decision:", "tool_receipt_binding:")


def test_replay_detects_an_altered_artifact_value(recorded, tmp_path):
    def mutate(db):
        row = db.execute("SELECT ref,value FROM artifacts WHERE work_id='produce'").fetchone()
        value = json.loads(row["value"])
        value["total_cents"] += 1
        db.execute("UPDATE artifacts SET value=? WHERE ref=?", (wire(value), row["ref"]))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "artifact:")
    assert any(failure.endswith("artifact differs from the receipt's validated proposal")
               for failure in report["failures"])


def test_replay_detects_an_altered_decision_receipt_digest(recorded, tmp_path):
    def mutate(db):
        db.execute("UPDATE orchestration_decisions_v1 SET receipt_digest=? WHERE seq=1", ("0" * 64,))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "decision:1:digest")
    assert report["failures"] == ["decision:1:digest"], "the failure must name the decision, nothing else"


def test_replay_detects_an_altered_lineage_digest(recorded, tmp_path):
    def mutate(db):
        row = db.execute("SELECT ref,lineage FROM orchestration_artifacts_v1 "
                         "WHERE kind='output' ORDER BY rowid LIMIT 1").fetchone()
        lineage = json.loads(row["lineage"])
        lineage[0]["digest"] = "1" * 64
        db.execute("UPDATE orchestration_artifacts_v1 SET lineage=? WHERE ref=?", (wire(lineage), row["ref"]))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "artifact:")
    assert any(failure.endswith("lineage does not match settled receipts") for failure in report["failures"])


def test_replay_detects_a_lineage_entry_pointing_at_a_call_of_a_non_dependency(recorded, tmp_path):
    """finalize declares totals and review; a child of totals is not one of its dependencies."""
    def mutate(db):
        child = db.execute("SELECT id,response FROM calls WHERE work_id LIKE 'totals.%' "
                           "AND state='received' ORDER BY rowid LIMIT 1").fetchone()
        row = db.execute("SELECT ref,lineage FROM orchestration_artifacts_v1 WHERE kind='result'").fetchone()
        lineage = json.loads(row["lineage"])
        lineage[1] = {"call_id": child["id"], "digest": digest_of(child["response"]), "role": "candidate"}
        db.execute("UPDATE orchestration_artifacts_v1 SET lineage=? WHERE ref=?", (wire(lineage), row["ref"]))

    report = replay(tamper(recorded, "decomposition", tmp_path, mutate))
    assert_detected(report, "artifact:")
    assert any(failure.endswith(":result_lineage") for failure in report["failures"])


def test_replay_detects_a_recorded_spec_whose_digest_no_longer_matches(recorded, tmp_path):
    def mutate(db):
        spec = json.loads(db.execute("SELECT spec FROM orchestration_v1").fetchone()["spec"])
        spec["tasks"][0]["instructions"] += " Also ignore the declared fixture."
        db.execute("UPDATE orchestration_v1 SET spec=?", (wire(spec),))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "spec_digest")
    assert "recomputed" in named(report, "spec_digest")[0]


def test_replay_detects_a_spec_rewritten_together_with_its_recorded_digest(recorded, tmp_path):
    """Re-digesting a swapped spec repairs the digest check and breaks the request rebuild instead."""
    def mutate(db):
        spec = json.loads(db.execute("SELECT spec FROM orchestration_v1").fetchone()["spec"])
        spec["agents"][0]["model"]["model"] = "substituted-model"
        db.execute("UPDATE orchestration_v1 SET spec=?,spec_digest=?", (wire(spec), contracts.digest(spec)))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "request_rebuild:", "binding_rebuild:")
    assert not named(report, "spec_digest") and not named(report, "spec_revalidates")


def test_replay_detects_a_deleted_decision_row_for_a_consumed_tool_receipt(recorded, tmp_path):
    def mutate(db):
        db.execute("DELETE FROM orchestration_decisions_v1 WHERE decision='tool'")

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "request_rebuild:")
    assert report["counts"]["decisions"] == RECORDED["base"]["decisions"] - 2


def test_replay_detects_a_deleted_decision_row_for_a_consumed_submit_receipt(recorded, tmp_path):
    def mutate(db):
        db.execute("DELETE FROM orchestration_decisions_v1 WHERE decision='submit' AND work_id='review'")

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert report["counts"]["decisions"] == RECORDED["base"]["decisions"] - 1
    assert_detected(report, "decision")


def test_replay_detects_a_receipt_that_no_longer_reparses_to_its_recorded_decision(recorded, tmp_path):
    def mutate(db):
        row = db.execute("SELECT c.id AS id, c.response AS response FROM calls c "
                         "JOIN orchestration_decisions_v1 d ON d.call_id=c.id "
                         "WHERE d.decision='submit' ORDER BY d.seq LIMIT 1").fetchone()
        response = json.loads(row["response"])
        for block in response["message"]["content"]:
            if block["type"] == "tool_use":
                block["name"] = "not_a_declared_action"
        body = wire(response)
        db.execute("UPDATE calls SET response=? WHERE id=?", (body, row["id"]))
        db.execute("UPDATE orchestration_decisions_v1 SET receipt_digest=? WHERE call_id=?",
                   (digest_of(body), row["id"]))

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "decision:")
    assert any("re-parses to rejected but the ledger recorded submit" in failure
               for failure in report["failures"])


def test_replay_detects_a_lineage_row_whose_artifact_was_deleted(recorded, tmp_path):
    def mutate(db):
        db.execute("DELETE FROM artifacts WHERE work_id='review'")

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "artifact:", "terminal:review")
    assert any(failure.endswith("lineage names an unpublished artifact") for failure in report["failures"])


def test_replay_detects_a_settled_call_whose_usage_exceeds_its_declared_prompt_bound(recorded, tmp_path):
    def mutate(db):
        db.execute("UPDATE orchestration_accounting_v1 SET prompt_bound=1")

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "accounting:")
    assert any(failure.endswith("settled prompt usage exceeds the declared bound")
               for failure in report["failures"])


def test_replay_detects_an_accounting_violation_recorded_against_a_settled_call(recorded, tmp_path):
    def mutate(db):
        call_id = db.execute("SELECT call_id FROM orchestration_accounting_v1 ORDER BY rowid LIMIT 1").fetchone()[0]
        db.execute("UPDATE orchestration_accounting_v1 SET violation=? WHERE call_id=?", ("{}", call_id))

    path = tamper(recorded, "base", tmp_path, mutate)
    report = replay(path)
    assert_detected(report, "accounting:")
    assert any(failure.endswith("a call with an accounting violation must stay dispatched")
               for failure in report["failures"])
    assert len(report["accounting_violations"]) == 1


def test_replay_detects_a_recorded_template_version_it_cannot_rebuild(recorded, tmp_path):
    def mutate(db):
        db.execute("UPDATE orchestration_v1 SET template_version='orchestration-context-v0'")

    report = replay(tamper(recorded, "base", tmp_path, mutate))
    assert_detected(report, "template_version")


# ---------------------------------------------------------------- part 1c: LIMITED

def test_a_differing_source_identity_yields_limited_and_not_fail(recorded, monkeypatch):
    monkeypatch.setattr(audit, "source_identity", lambda: {"runner/audit.py": "0" * 64})
    report = replay(recorded["base"]["path"])
    assert report["status"] == "LIMITED" != "FAIL"
    assert report["source_match"] is False and report["failures"] == []
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)
    assert report["counts"]["model_calls"] == RECORDED["base"]["model_calls"]


def test_a_differing_source_identity_never_downgrades_a_tampered_record_to_limited(recorded, tmp_path, monkeypatch):
    def mutate(db):
        db.execute("UPDATE orchestration_decisions_v1 SET receipt_digest=? WHERE seq=1", ("2" * 64,))

    path = tamper(recorded, "base", tmp_path, mutate)
    monkeypatch.setattr(audit, "source_identity", lambda: {"runner/audit.py": "0" * 64})
    report = replay(path)
    assert report["status"] == "FAIL" and report["source_match"] is False


# ---------------------------------------------------------------- part 2: commitment seams

MODEL_AT_DEADLINE = (1., .05, 0, .5, [.2, .8], [.5, .5])
MODEL_WITH_HORIZON = (1., .05, 3, .5, [.2, .8], [.5, .5])


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def verify_ok(task_id, artifact):
    return True


def platform_session(tmp_path, candidates):
    """A real PlatformSession carrying settled receipts with the declared certified losses."""
    session = PlatformSession.create(
        tmp_path / "commit.sqlite", "run-1", agents=["a", "b", "host"],
        work=[{"id": "w", "version": 1, "dependencies": [], "agents": ["a", "b"],
               "actions": ["tool.evaluate"]}],
        token_cap=10_000, max_calls=50, clock=Clock(), platform={"budgets": {}})
    for agent, call_id, loss in candidates:
        lease = session.claim(agent, "w")
        SessionDriver(session, tools={"mock": lambda arguments: {"value": arguments}}
                      ).evaluate(lease, call_id, "mock", {"k": 1})
        session.propose(lease, call_id, loss)
        session.release(lease)
    return session


def platform_events(session, kind):
    return [event["details"] for event in session.snapshot()["events"]
            if event["event_type"] == "interaction.session.platform." + kind]


def test_optimal_stopping_rule_abstains_terminally_at_a_loss_equal_to_the_abstention_loss(tmp_path):
    """The programme values publishing and abstaining alike here; the ledger publishes only on
    strict improvement, so the rule must abstain instead of driving commit into its refusal."""
    session = platform_session(tmp_path, [("a", "w:a", 1.0)])
    rule = commitment.optimal_stopping_rule(*MODEL_AT_DEADLINE, 0)
    result = session.commit("w", verify=verify_ok, abstain_loss=1., rule=rule)
    assert result["decision"] == "abstain" and result["candidates"] == 1
    snapshot = session.snapshot()
    assert snapshot["artifacts"] == [], "an abstention publishes no artifact"
    assert [row["work_id"] for row in snapshot["platform"]["decisions"]] == ["w"]
    assert platform_events(session, "waited") == []
    assert session.claim("b", "w") is None and session.ready_work("a") == []


def test_the_equality_abstention_is_terminal_and_idempotent(tmp_path):
    session = platform_session(tmp_path, [("a", "w:a", 1.0)])
    rule = commitment.optimal_stopping_rule(*MODEL_AT_DEADLINE, 0)
    result = session.commit("w", verify=verify_ok, abstain_loss=1., rule=rule)
    snapshot = session.snapshot()
    replayed = session.commit("w", verify=lambda *args: pytest.fail("verification replayed"),
                              abstain_loss=1., rule=lambda *args: pytest.fail("rule replayed"))
    assert replayed == result and session.snapshot() == snapshot


def test_the_same_programme_publishes_a_loss_strictly_below_the_abstention_loss(tmp_path):
    session = platform_session(tmp_path, [("a", "w:a", 0.999)])
    rule = commitment.optimal_stopping_rule(*MODEL_AT_DEADLINE, 0)
    result = session.commit("w", verify=verify_ok, abstain_loss=1., rule=rule)
    assert result["decision"] == "publish" and result["call_id"] == "w:a"
    assert [row["call_id"] for row in session.snapshot()["artifacts"]] == ["w:a"]


def test_the_ledger_still_refuses_a_rule_that_names_a_candidate_at_the_abstention_loss(tmp_path):
    """The fix belongs to the rule; the ledger guard that made the equality case raise is intact."""
    session = platform_session(tmp_path, [("a", "w:a", 1.0)])
    before = session.snapshot()
    with pytest.raises(StateError, match="rule cannot publish at or above abstention loss"):
        session.commit("w", verify=verify_ok, abstain_loss=1., rule=lambda rows, loss: rows[0]["call_id"])
    assert session.snapshot() == before


def test_optimal_stopping_rule_still_waits_on_a_real_session_above_the_abstention_loss(tmp_path):
    session = platform_session(tmp_path, [("a", "w:a", 1.5)])
    waiting = commitment.optimal_stopping_rule(*MODEL_WITH_HORIZON, 0)
    assert session.commit("w", verify=verify_ok, abstain_loss=1., rule=waiting) == {"decision": "wait",
                                                                                   "candidates": 1}
    assert [{k: v for k, v in e.items() if k != "at"} for e in platform_events(session, "waited")] \
        == [{"candidates": 1, "abstain_loss": 1.}]
    assert session.snapshot()["artifacts"] == []
    at_deadline = commitment.optimal_stopping_rule(*MODEL_WITH_HORIZON, 3)
    assert session.commit("w", verify=verify_ok, abstain_loss=1., rule=at_deadline)["decision"] == "abstain"
    assert session.snapshot()["artifacts"] == []


def test_optimal_stopping_rule_keeps_refusing_an_empty_field_and_a_disagreeing_ledger_loss():
    rule = commitment.optimal_stopping_rule(*MODEL_AT_DEADLINE, 0)
    assert rule([], 1.) is None
    with pytest.raises(ValueError, match="abstain_loss"):
        rule([{"call_id": "w:a", "certified_loss": .2}], 2.)
    assert rule([{"call_id": "w:a", "certified_loss": .2}], 1.) == "w:a"


def test_commit_value_states_and_values_are_unchanged_on_the_documented_distribution():
    decide = commitment.commit_value(*MODEL_WITH_HORIZON)
    assert decide(0, None) == {"state": "no_candidate", "value": .59375, "wait_value": .59375}
    assert decide(3, None) == {"state": "abstain", "value": 1, "wait_value": None}
    assert decide(0, .2)["state"] == "publish" and decide(0, .2)["value"] == .2
    assert decide(0, .5) == {"state": "wait", "value": .4421875, "wait_value": .4421875}
    assert decide(3, .5) == {"state": "publish", "value": .5, "wait_value": None}
    assert decide(3, 1.5) == {"state": "abstain", "value": 1, "wait_value": None}
    assert decide(7, .5) == decide(3, .5)


def test_commit_value_keeps_the_recall_branch_for_a_candidate_above_the_abstention_loss():
    """Waiting beats abstaining at 1.5 with three ticks left; the equality fix must not touch this."""
    decide = commitment.commit_value(*MODEL_WITH_HORIZON)
    assert decide(0, 1.5)["state"] == "wait"
    assert decide(0, 1.5)["wait_value"] < 1 and decide(0, 1.5)["value"] == .59375
    assert decide(2, 1.5)["state"] == "wait" and decide(3, 1.5)["state"] == "abstain"


def test_commit_value_at_the_deadline_is_still_the_minimum_of_candidate_and_abstention():
    decide = commitment.commit_value(*MODEL_AT_DEADLINE)
    assert decide(0, .6) == {"state": "publish", "value": .6, "wait_value": None}
    assert decide(0, 1.5) == {"state": "abstain", "value": 1, "wait_value": None}
    assert decide(0, None) == {"state": "abstain", "value": 1, "wait_value": None}
    assert decide(0, 1) == {"state": "publish", "value": 1, "wait_value": None}


def test_commit_value_wait_value_is_still_exact_for_an_off_support_candidate():
    decide = commitment.commit_value(1, .05, 1, .5, [.2, .8], [.5, .5])
    expected = .05 + .5 * .6 + .5 * (.5 * .2 + .5 * .6)
    assert decide(0, .6) == {"state": "wait", "value": expected, "wait_value": expected}
    assert expected == pytest.approx(.55, abs=1e-15)


def commitment_config(**changes):
    return commitment.CommitmentConfig(**({"abstain_loss": 1., "latency_cost": .25,
                                           "decision_time": 1.} | changes))


def test_cross_inhibition_gate_at_the_abstention_boundary_is_unchanged():
    config = commitment_config()
    assert commitment.cross_inhibition([1.0], ["only"], config)["reason"] == commitment.NO_ADMISSIBLE
    assert commitment.cross_inhibition([.75], ["only"], config)["reason"] == commitment.NO_ADMISSIBLE
    passing = commitment.cross_inhibition([.74], ["only"], config)
    assert passing["decision"] == "publish" and passing["index"] == 0


def test_cross_inhibition_rule_abstains_terminally_at_the_same_boundary_on_a_real_session(tmp_path):
    session = platform_session(tmp_path, [("a", "w:a", 1.0)])
    rule = commitment.cross_inhibition_rule(commitment_config())
    assert rule([{"call_id": "w:a", "certified_loss": 1.0}], 1.) is None
    result = session.commit("w", verify=verify_ok, abstain_loss=1., rule=rule)
    assert result["decision"] == "abstain"
    assert session.snapshot()["artifacts"] == [] and platform_events(session, "waited") == []
    assert session.claim("b", "w") is None


def test_cross_inhibition_rule_still_publishes_an_admissible_candidate_on_a_real_session(tmp_path):
    session = platform_session(tmp_path, [("a", "w:a", .4), ("b", "w:b", .2)])
    rule = commitment.cross_inhibition_rule(commitment_config())
    result = session.commit("w", verify=verify_ok, abstain_loss=1., rule=rule)
    assert result["decision"] == "publish" and result["call_id"] == "w:b" and result["publisher"] == "b"
    assert [row["call_id"] for row in session.snapshot()["artifacts"]] == ["w:b"]


# ---------------------------------------------------------------- part 1d: the executor's two records

class Interrupted(BaseException):
    """A simulated process death; not an Exception, so no runtime handler swallows it."""


def run_until_reserved(path):
    """A real run that died between reserving a call and dispatching it."""
    class Dying(OrchestrationSession):
        def _event(self, db, kind, work, payload):
            super()._event(db, kind, work, payload)
            if kind == "dispatched":
                raise Interrupted(kind)

    spec = load_spec("workflow.json")
    session = Dying.create(path, spec=spec)
    with pytest.raises(Interrupted):
        runtime.run_workflow(
            session, registry=tools.build_registry(spec, EXAMPLES),
            transports={"fake": anthropic.FakeTransport(anthropic.load_script(EXAMPLES / "script.json"))})
    return path


def rewrite_claim_owner(path, owner):
    """Rewrite the owner recorded in every ``claimed`` event of a ledger copy."""
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    try:
        for row in database.execute("SELECT seq, value FROM events").fetchall():
            value = json.loads(row["value"])
            if not value["event_type"].endswith(".claimed"):
                continue
            value["details"]["owner"] = owner
            database.execute("UPDATE events SET value=? WHERE seq=?",
                             (json.dumps(value, sort_keys=True, separators=(",", ":")), row["seq"]))
        database.commit()
    finally:
        database.close()


def test_a_call_that_reserved_but_never_dispatched_still_has_an_attested_executor(tmp_path):
    """Producing no external effect is not a reason to stop verifying who claimed.

    The call has no execution permission, but ``claim`` wrote a durable ``claimed``
    event at the same work, version and epoch, so the actor is reconstructed from the
    ledger and checked against the task's eligible set.
    """
    path = run_until_reserved(tmp_path / "reserved.sqlite")
    calls = {row["id"]: row for row in OrchestrationSession(path).snapshot()["calls"]}
    assert len(calls) == 1
    (call,) = calls.values()
    assert call["state"] in ("reserved", "abandoned") and call["permission"] is None
    report = replay(path)
    assert report["status"] == "PASS" and report["failures"] == []
    assert (report["new_model_calls"], report["new_tool_calls"]) == (0, 0)


def test_replay_detects_an_undispatched_call_claimed_by_an_ineligible_agent(tmp_path):
    """Proof the actor is reconstructed and CHECKED, not merely skipped.

    Without reconstruction this ledger replays clean, because the only record naming
    the executor is the claim event this test rewrites.
    """
    path = run_until_reserved(tmp_path / "reserved-tampered.sqlite")
    rewrite_claim_owner(path, "intruder")
    assert_detected(replay(path), "call_claimant:")


def test_replay_detects_a_permission_and_a_claim_event_that_disagree(recorded, tmp_path):
    """Two records of one authority that contradict each other is a failure, not a preference."""
    target = copy_ledger(recorded, "base", tmp_path)
    rewrite_claim_owner(target, "someone-else")
    assert_detected(replay(target), "call_authority_agrees:")


def test_replay_reads_the_previous_durable_task_schema(recorded, tmp_path):
    """Offline audit reads v1 and v2 task tables; the live runtime executes only v2.

    The repository holds no genuinely historical v1 orchestration ledger - the table
    was never released under that name - so this downgrades a real recorded ledger to
    the v1 shape (one executor per task, in a column named ``agent``) to exercise the
    reader. It demonstrates the compatibility path works, not that such a record exists.
    """
    target = copy_ledger(recorded, "base", tmp_path)
    database = sqlite3.connect(target)
    database.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in database.execute("SELECT * FROM orchestration_tasks_v2")]
        database.execute("ALTER TABLE orchestration_tasks_v2 RENAME TO orchestration_tasks_v1")
        database.execute("ALTER TABLE orchestration_tasks_v1 RENAME COLUMN agents TO agent")
        for row in rows:
            database.execute("UPDATE orchestration_tasks_v1 SET agent=? WHERE work_id=?",
                             (json.dumps(json.loads(row["agents"])[0]), row["work_id"]))
        database.commit()
    finally:
        database.close()
    ledger = audit.ReplayLedger(target)
    assert ledger.task_table == "orchestration_tasks_v1"
    assert all(json.loads(row["agents"]) for row in ledger.rows["orchestration_tasks"])
    report = replay(target)
    assert report["status"] == "PASS" and report["failures"] == []


def as_legacy(spec):
    """The same workload declared in the previous schema: exactly one executor per task."""
    document = json.loads(json.dumps(spec))
    document["format"] = contracts.LEGACY_SPEC_FORMAT
    document.pop("capacity", None)
    for task in document["tasks"]:
        task["agent"] = task.pop("agents")[0]
    return contracts.workflow_spec(document)


def test_a_v1_workflow_validates_and_audits_but_the_runtime_refuses_to_execute_it(tmp_path):
    """v1 is historical audit semantics; v2 is executable semantics.

    The refusal is at the execution boundary rather than at ``start_run`` alone, so a
    v1 declaration cannot reach a step through ``run_workflow`` either.
    """
    legacy = as_legacy(load_spec("workflow.json"))
    assert legacy["format"] == contracts.LEGACY_SPEC_FORMAT
    assert all("agent" in task and "agents" not in task for task in legacy["tasks"])
    session = OrchestrationSession.create(tmp_path / "legacy.sqlite", spec=legacy)
    engine = runtime.Runtime(session, registry=tools.build_registry(legacy, EXAMPLES),
                             transports={})
    assert engine.executable is False
    with pytest.raises(StateError, match="audited but not executed"):
        engine.run()
    with pytest.raises(StateError, match="audited but not executed"):
        engine.step(legacy["tasks"][0]["id"])
    # and the same refusal at the recorded-run entry point, before any ledger is made
    document = tmp_path / "legacy.json"
    document.write_text(json.dumps(legacy))
    with pytest.raises(ValueError, match="audited but not executed"):
        runtime.start_run(document, tmp_path / "legacy-run")
    assert not (tmp_path / "legacy-run").exists()
