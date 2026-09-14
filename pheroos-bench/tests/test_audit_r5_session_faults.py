"""Sensitivity checks for the offline auditor; no harness/study/runtime calls."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

PATH = Path(__file__).resolve().parents[1] / "tools/audit_r5_session_faults.py"
SPEC = importlib.util.spec_from_file_location("audit_r5_session_faults", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def authorize(run, work, action, payload):
    return dict(scope_ref="test-scope", task_id=work, version=1, action=action,
                reusable_authority=False, payload_digest=audit.digest(audit.wire(payload)))


def event(kind, work, data):
    return dict(event_type="ext.session." + kind, protocol_id="session.v1", target=work or "run", reason=kind, lineage=data)


def fixture(*, model=False, received=False):
    request = dict(fixture="bounded_counter", call_id="one", task_id="inspect", version=1)
    action = "model.generate" if model else "tool.evaluate"
    authority = authorize("r5-fixture-session", "inspect", action, request)
    response = dict(prompt_tokens=2 if model else 0, completion_tokens=1 if model else 0,
                    artifact=dict(kind="bounded_verified_fact", work_id="inspect", version=1, value=1))
    call = dict(id="one", work_id="inspect", version=1, epoch=1, action=action, request=audit.wire(request),
                state="received" if received else "dispatched", prompt=2 if model else 0, maximum=8 if model else 0,
                reserved=10 if model else 0, response=audit.wire(response) if received else None,
                actual=(3 if model else 0) if received else None, authority=audit.wire(authority))
    work = [dict(id=key, version=1, declaration=audit.wire(dict(id=key, version=1,
                    dependencies=[] if key == "inspect" else ["inspect"], agents=["a", "b"], actions=["model.generate", "tool.evaluate"])),
                 status="leased" if key == "inspect" else "ready", owner="a" if key == "inspect" else None,
                 epoch=1 if key == "inspect" else 0, expires=101.0 if key == "inspect" else None, generation=0)
            for key in ("inspect", "submit")]
    events = [event("created", "", dict(run_id="r5-fixture-session", limits=audit.LIMITS)),
              event("claimed", "inspect", dict(task_id="inspect", version=1, owner="a", epoch=1)),
              event("reserved", "inspect", dict(call_id="one", tokens=call["reserved"])),
              event("dispatched", "inspect", dict(call_id="one", authority=authority))]
    if received:
        events.append(event("received", "inspect", dict(call_id="one", actual_tokens=call["actual"], response_digest=audit.digest(call["response"]))))
    snapshot = dict(run=dict(id=1, run_id="r5-fixture-session", status="running", generation=0, enabled=1,
                            agents=audit.wire(["a", "b"]), limits=audit.wire(audit.LIMITS)),
                    work=work, calls=[call], artifacts=[], events=events, call_count=1, **audit.costs([call]))
    return snapshot, dict(checkpoints=[], mailbox=[])


def persist(path, snapshot):
    schemas = {
        "run": "id INTEGER, run_id TEXT, status TEXT, generation INTEGER, enabled INTEGER, agents TEXT, limits TEXT",
        "work": "id TEXT, version INTEGER, declaration TEXT, status TEXT, owner TEXT, epoch INTEGER, expires REAL, generation INTEGER",
        "calls": "id TEXT, work_id TEXT, version INTEGER, epoch INTEGER, action TEXT, request TEXT, state TEXT, prompt INTEGER, maximum INTEGER, reserved INTEGER, response TEXT, actual INTEGER, authority TEXT",
        "artifacts": "ref TEXT, work_id TEXT, version INTEGER, publisher TEXT, value TEXT, call_id TEXT, response_digest TEXT, authority TEXT",
        "events": "seq INTEGER, value TEXT", "checkpoints": "agent TEXT, work_id TEXT, version INTEGER, generation INTEGER, value TEXT",
        "mailbox": "id TEXT, sender TEXT, recipient TEXT, artifact_ref TEXT, expires REAL, bytes INTEGER"}
    rows = {k: snapshot[k] for k in ("work", "calls", "artifacts")}
    rows.update(run=[snapshot["run"]], events=[dict(seq=i + 1, value=audit.wire(e)) for i, e in enumerate(snapshot["events"])])
    with sqlite3.connect(path) as db:
        for table, schema in schemas.items():
            db.execute(f"CREATE TABLE {table} ({schema})")
            for row in rows.get(table, []):
                db.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", list(row.values()))


def test_unknown_zero_token_dispatch_remains_unknown():
    snapshot, tables = fixture()
    assert audit.costs(snapshot["calls"]) == dict(actual_tokens=0, reserved_tokens=0, unknown_tokens=0, unknown_calls=1)
    assert audit.ledger(snapshot, tables, authorize) == 1


@pytest.mark.parametrize("change", [
    dict(actual=True), dict(actual=-1), dict(actual=None), dict(actual=4), dict(prompt=True),
    dict(reserved=9), dict(state="completed"), dict(response='{"prompt_tokens":2,"completion_tokens":1,"completion_tokens":1}'),
    dict(response='{"prompt_tokens":2,"completion_tokens":NaN}'),
    dict(response='{"prompt_tokens":2,"completion_tokens":true}'),
])
def test_known_accounting_tampering_is_detected(change):
    snapshot, _ = fixture(model=True, received=True)
    snapshot["calls"][0].update(change)
    with pytest.raises((ValueError, TypeError)):
        audit.costs(snapshot["calls"])


def test_sqlite_is_independent_from_export_and_stays_unchanged(tmp_path):
    snapshot, _ = fixture(model=True, received=True)
    path = tmp_path / "session.sqlite"
    persist(path, snapshot)
    before = audit.file_hash(path)
    retained, tables = audit.database(path)
    audit.equal(retained, snapshot, "original fixture")
    assert audit.ledger(retained, tables, authorize) == 1
    assert audit.file_hash(path) == before
    altered = deepcopy(snapshot)
    altered["calls"][0]["request"] = '{}'
    with pytest.raises(ValueError, match="export"):
        audit.equal(retained, altered, "database/export differs")


def test_raw_database_accounting_tamper_cannot_hide_behind_snapshot(tmp_path):
    snapshot, _ = fixture(model=True, received=True)
    path = tmp_path / "session.sqlite"
    persist(path, snapshot)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE calls SET actual=-1")
    with pytest.raises(ValueError):
        audit.database(path)


def test_cancelled_authority_cannot_dispatch_in_replayed_trace():
    snapshot, tables = fixture()
    snapshot["events"].insert(3, event("cancelled", "", dict(generation=1)))
    with pytest.raises(ValueError, match="current authority"):
        audit.ledger(snapshot, tables, authorize)


def test_duplicate_receipt_is_not_a_second_settlement_event():
    snapshot, tables = fixture(model=True, received=True)
    snapshot["events"].append(deepcopy(snapshot["events"][-1]))
    with pytest.raises(ValueError, match="duplicate or unsolicited"):
        audit.ledger(snapshot, tables, authorize)


def test_authorization_payload_mismatch_is_detected():
    snapshot, tables = fixture()
    snapshot["calls"][0]["authority"] = audit.wire({"approved": True})
    with pytest.raises(ValueError, match="core authorization"):
        audit.ledger(snapshot, tables, authorize)


def test_mailbox_case_requires_actual_retained_send_events():
    snapshot, _ = fixture(received=True)
    with pytest.raises(ValueError, match="mailbox injection missing"):
        audit.case_trace("mailbox:duplicate", snapshot)


def test_late_receipt_case_requires_cancel_before_settlement():
    snapshot, _ = fixture(model=True, received=True)
    snapshot["events"].append(event("cancelled", "", dict(generation=1)))
    with pytest.raises(ValueError, match="committed cancellation"):
        audit.case_trace("transport:delayed_reply", snapshot)


def test_retained_known_receipt_does_not_mean_completed_recovery():
    snapshot, _ = fixture(model=True, received=True)
    audit.case_trace("receipt_committed_before_ack:default", snapshot)
    snapshot["run"]["status"] = "completed"
    with pytest.raises(ValueError, match="recovery disposition"):
        audit.case_trace("receipt_committed_before_ack:default", snapshot)


def test_no_free_transition_between_zero_token_reserved_and_abandoned():
    assert audit.expected_call_states("transient_store_lock:reserve") == [["one", "tool.evaluate", "reserved"]]
    assert audit.expected_call_states("cancellation_dispatch_order:cancel_first") == [["one", "tool.evaluate", "abandoned"]]


@pytest.mark.parametrize("mutation", [
    lambda row: row.update(worker_exitcode=0), lambda row: row.update(actual_sigkill=False),
    lambda row: row.update(acknowledgment_received=True), lambda row: row.update(fresh_process_reopen=False),
    lambda row: row["boundary"].update(stage="different_boundary"),
    lambda row: row["boundary"].update(pid=True), lambda row: row["boundary"].update(boundary="another_case"),
])
def test_synthetic_kill_marker_inconsistency_is_rejected(tmp_path, mutation):
    snapshot, _ = fixture(model=True, received=True)
    case = "receipt_committed_before_ack:default"
    inspector = dict(status="PASS", snapshot=snapshot, before=deepcopy(snapshot),
        inspection_sequence_elapsed_ns=1, recovery_elapsed_ns=1, fresh_process_reopen=True,
        refusals=["LeaseLost: synthetic observation"], effects=[], effects_by_call={},
        accounting=audit.costs(snapshot["calls"]), action_counts=dict(model_dispatches=1, tool_dispatches=0))
    row = dict(elapsed_ns=2, boundary=dict(boundary=case, stage="after_receipt_commit_before_ack", pid=123),
               worker_exitcode=-9, actual_sigkill=True, acknowledgment_received=False, **deepcopy(inspector))
    (tmp_path / "inspector-transport.json").write_text(audit.wire(dict(stdout=audit.wire(inspector), stderr="")))
    (tmp_path / "worker-transport.json").write_text(audit.wire(dict(stdout="", stderr="")))
    audit.observations(case, row, tmp_path)
    mutation(row)
    with pytest.raises(ValueError):
        audit.observations(case, row, tmp_path)


@pytest.mark.parametrize("stdout", ["{}", "[]", '{"status":"PASS"}'])
def test_raw_inspector_cannot_be_replaced_with_empty_or_partial_object(tmp_path, stdout):
    row = dict(elapsed_ns=1, inspection_sequence_elapsed_ns=1, before={})
    (tmp_path / "inspector-transport.json").write_text(audit.wire(dict(stdout=stdout, stderr="")))
    with pytest.raises(ValueError, match="raw inspector fields missing"):
        audit.observations("adapter_failure:tool_before_effect", row, tmp_path)


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_effect_counter_cannot_ignore_unreconciled_journal(tmp_path, suffix):
    path = tmp_path / "effects.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE effects (sequence INTEGER)")
    assert audit.effect_rows(path) == []
    Path(str(path) + suffix).write_bytes(b"unreconciled committed-state evidence")
    with pytest.raises(ValueError, match="unreconciled SQLite journal"):
        audit.effect_rows(path)


def test_rejected_payload_retains_known_usage_but_cannot_publish():
    snapshot, tables = fixture(model=True, received=True)
    call = snapshot["calls"][0]
    call["state"] = "response_rejected"
    call["response"] = audit.wire(dict(prompt_tokens=2, completion_tokens=1, response_rejected="response_bytes_exceeded",
                                      response_digest="a" * 64, response_bytes=2048))
    snapshot["events"][-1] = event("response_rejected", "inspect", dict(call_id="one", actual_tokens=3, response_digest="a" * 64))
    assert audit.costs([call]) == dict(actual_tokens=3, reserved_tokens=0, unknown_tokens=0, unknown_calls=0)
    assert audit.ledger(snapshot, tables, authorize) == 1
    snapshot["artifacts"] = [dict(ref="fake", call_id="one")]
    snapshot["events"].append(event("published", "inspect", dict(artifact_ref="fake")))
    with pytest.raises(ValueError, match="settled tool"):
        audit.ledger(snapshot, tables, authorize)


def test_model_receipt_cannot_become_artifact_evidence():
    snapshot, tables = fixture(model=True, received=True)
    snapshot["artifacts"] = [dict(ref="fake", call_id="one")]
    snapshot["events"].append(event("published", "inspect", dict(artifact_ref="fake")))
    with pytest.raises(ValueError, match="settled tool"):
        audit.ledger(snapshot, tables, authorize)


@pytest.mark.parametrize("mutation", [lambda artifact: artifact.update(publisher="b"),
                                      lambda artifact: artifact.update(response_digest="0" * 64),
                                      lambda artifact: artifact.update(value=audit.wire(dict(kind="bounded_verified_fact", work_id="inspect", version=1, value=True)))])
def test_valid_publication_and_lineage_substitution_sensitivity(mutation):
    snapshot, tables = fixture(received=True)
    call = snapshot["calls"][0]
    fact = audit.decode(call["response"])["artifact"]
    payload = dict(task_id="inspect", version=1, artifact=fact, call_id="one",
                   response_digest=audit.digest(call["response"]), scope_ref="test-scope")
    authority = authorize(snapshot["run"]["run_id"], "inspect", "artifact.publish", payload)
    reference = "sha256:" + audit.digest(audit.wire(payload))
    artifact = dict(ref=reference, work_id="inspect", version=1, publisher="a", value=audit.wire(fact),
                    call_id="one", response_digest=payload["response_digest"], authority=audit.wire(authority))
    snapshot["artifacts"] = [artifact]
    snapshot["work"][0].update(status="done", owner=None, expires=None)
    snapshot["events"].append(event("published", "inspect", dict(artifact_ref=reference, call_id="one", version=1,
        response_digest=payload["response_digest"], authority=authority)))
    assert audit.ledger(snapshot, tables, authorize) == 2
    audit.case_trace("transient_store_lock:publish", snapshot)
    mutation(artifact)
    with pytest.raises(ValueError):
        audit.ledger(snapshot, tables, authorize)


def test_duplicate_sidecar_invocation_is_not_deduplicated():
    with pytest.raises(ValueError, match="duplicate adapter"):
        audit.verify_effects([{"call_id": "one"}, {"call_id": "one"}], {})


def test_effect_is_bound_to_raw_receipt():
    snapshot, _ = fixture(received=True)
    inputs = dict(call_id="one", work_id="inspect", version=1, kind="tool", requested_value=1)
    output = dict(kind="bounded_verified_fact", work_id="inspect", version=1, value=1)
    row = dict(call_id="one", work_id="inspect", version=1, kind="tool", value="1",
               input_digest=audit.digest(audit.wire(inputs)), output_digest=audit.digest(audit.wire(output)))
    calls = {"one": snapshot["calls"][0]}
    assert audit.verify_effects([row], calls) == {"one": 1}
    response = audit.decode(calls["one"]["response"])
    response["artifact"]["value"] = 2
    calls["one"]["response"] = audit.wire(response)
    with pytest.raises(ValueError, match="actual sidecar"):
        audit.verify_effects([row], calls)


def source_matrix():
    rows = [dict(method_version=audit.METHOD, case=case, counts_toward_verdict=False, status="PASS", accounting=None) for case in audit.CASES]
    rows[0]["status"] = "FAIL"
    summary = dict(method_version=audit.METHOD, counts_toward_verdict=False, status="FAIL", cases=38,
                   outcomes=dict(PASS=37, FAIL=1, INVALID_ABORT=0), source_unchanged=True, gpu_calls=0, paid_provider_calls=0,
                   finalization_errors=[],
                   source_accounting=[dict(case=r["case"], status=r["status"], accounting=None) for r in rows])
    return summary, rows


def test_matrix_preserves_failures_and_rejects_relabeling():
    summary, rows = source_matrix()
    audit.matrix(summary, rows)
    summary["status"] = "PASS"
    with pytest.raises(ValueError, match="conceals failures"):
        audit.matrix(summary, rows)


@pytest.mark.parametrize("mutation", [lambda rows: rows.pop(), lambda rows: rows.append(deepcopy(rows[0])),
                                        lambda rows: rows[0].update(case=rows[1]["case"])])
def test_full_38_identity_requirement(mutation):
    summary, rows = source_matrix()
    mutation(rows)
    with pytest.raises(ValueError, match="fault identities"):
        audit.matrix(summary, rows)


def test_missing_case_keeps_unavailable_accounting(tmp_path):
    row = dict(status="INVALID_ABORT", accounting=None)
    result = audit.audit_case(audit.CASES[0], row, tmp_path / "missing")
    assert result["accounting"] is None and result["runtime_disposition"] == "UNAVAILABLE"
    row["status"] = "PASS"
    with pytest.raises(ValueError):
        audit.audit_case(audit.CASES[0], row, tmp_path / "missing")


def test_synthetic_case_pass_stays_unresolved_after_cancel(tmp_path, monkeypatch):
    directory = tmp_path / "fixture"
    directory.mkdir()
    snapshot, _ = fixture()
    before = deepcopy(snapshot)
    before.update(calls=[], call_count=0, events=before["events"][:1], actual_tokens=0, reserved_tokens=0, unknown_tokens=0, unknown_calls=0)
    before["work"][0].update(status="ready", owner=None, epoch=0, expires=None)
    snapshot["events"].append(event("cancelled", "", dict(generation=1)))
    snapshot["run"].update(status="cancelled", generation=1, enabled=0)
    for work in snapshot["work"]:
        work.update(status="cancelled", owner=None, expires=None)
    persist(directory / "session.sqlite", snapshot)
    observations = dict(status="PASS", snapshot=snapshot, before=before, effects=[], effects_by_call={},
        action_counts=dict(model_dispatches=0, tool_dispatches=1), accounting=audit.costs(snapshot["calls"]),
        refusals=["RuntimeError: synthetic fixture only"], inspection_sequence_elapsed_ns=1)
    row = dict(method_version=audit.METHOD, case="adapter_failure:tool_before_effect", counts_toward_verdict=False,
               elapsed_ns=2, **observations)
    (directory / "case.json").write_text(audit.wire(row))
    (directory / "inspector-transport.json").write_text(audit.wire(dict(stdout=audit.wire(observations), stderr="")))
    original = audit.ledger
    monkeypatch.setattr(audit, "ledger", lambda snapshot, tables: original(snapshot, tables, authorize))
    result = audit.audit_case(row["case"], row, directory)
    assert result["source_status"] == "PASS" and result["runtime_disposition"] == "UNRESOLVED"
    assert result["accounting"]["unknown_calls"] == 1 and result["accounting"]["unknown_tokens"] == 0


def test_no_available_ledgers_does_not_export_fabricated_zero_costs():
    result = audit.accounting_export([dict(case="missing", audit_status="UNAVAILABLE_RETAINED", accounting=None)])
    assert result["all_observed_unique_available_ledger_components"] is None
    assert result["primary_dispatches"] is None and result["sidecar_effect_invocations"] is None


def test_other_audit_failure_keeps_independently_readable_unknown_costs(tmp_path):
    snapshot, _ = fixture(model=True)
    persist(tmp_path / "session.sqlite", snapshot)
    retained = audit.diagnostic_accounting("adapter_failure:synthetic_provider", tmp_path)
    assert retained["accounting_verified"] is True
    assert retained["accounting"] == dict(actual_tokens=0, reserved_tokens=0, unknown_tokens=10, unknown_calls=1)
    result = audit.accounting_export([dict(case="failed", audit_status="AUDIT_MISMATCH", **retained)])
    assert result["all_observed_unique_available_ledger_components"]["unknown_tokens"] == 10
    assert result["sidecar_effect_invocations"] is None


def test_corrupt_copy_diagnostic_never_double_counts_intact_original(tmp_path):
    snapshot, _ = fixture(model=True, received=True)
    persist(tmp_path / "session.sqlite", snapshot)
    (tmp_path / "corrupted.sqlite").write_bytes(b"not a database")
    retained = audit.diagnostic_accounting("corrupted_database_copy:default", tmp_path)
    assert retained["accounting"] is None
    assert retained["intact_original_accounting"]["actual_tokens"] == 3
    result = audit.accounting_export([dict(case="damaged", audit_status="AUDIT_MISMATCH", **retained)])
    assert result["all_observed_unique_available_ledger_components"]["actual_tokens"] == 3
    assert result["primary_known_components"] is None


def test_foreign_and_intact_setup_costs_are_visible_without_copy_double_counting():
    zero = dict(actual_tokens=0, reserved_tokens=0, unknown_tokens=0, unknown_calls=0)
    actions = dict(model_dispatches=0, tool_dispatches=1)
    rows = [dict(case="foreign", audit_status="INTEGRITY_PASS", accounting=zero, primary_action_counts=actions,
                 auxiliary_ledgers=[dict(ledger="foreign.sqlite", accounting=zero, **actions)],
                 intact_original_accounting=None, effect_invocations=2),
            dict(case="corrupted", audit_status="INTEGRITY_PASS", accounting=None, primary_action_counts=None,
                 auxiliary_ledgers=[], intact_original_accounting=zero, intact_original_action_counts=actions, effect_invocations=1)]
    result = audit.accounting_export(rows)
    assert result["primary_dispatches"]["tool_dispatches"] == 1
    assert result["all_observed_unique_available_dispatches"]["tool_dispatches"] == 3
    assert result["sidecar_effect_invocations"] == 3
    assert result["unavailable_primary_cases"] == ["corrupted"]


def test_terminal_gate_runs_before_any_import_or_database_access(tmp_path):
    with pytest.raises(ValueError, match="terminal study summary required"):
        audit.audit(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_frozen_source_change_is_detected(tmp_path):
    path = tmp_path / "source.py"
    path.write_text("before\n")
    inputs = {str(path): audit.file_hash(path)}
    audit.verify_inputs(inputs)
    path.write_text("after\n")
    with pytest.raises(ValueError, match="frozen input changed"):
        audit.verify_inputs(inputs)


def test_corrupted_copy_is_unreadable_and_original_is_retained(tmp_path):
    snapshot, _ = fixture(received=True)
    original = tmp_path / "original.sqlite"
    persist(original, snapshot)
    damaged = tmp_path / "damaged.sqlite"
    damaged.write_bytes(b"BROKEN SQLITE HEADER" + original.read_bytes()[20:])
    with pytest.raises(sqlite3.DatabaseError):
        audit.database(damaged)
    assert audit.database(original)[0]["actual_tokens"] == 0
