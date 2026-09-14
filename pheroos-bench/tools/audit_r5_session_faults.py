"""Offline R5 evidence audit; never launches the harness, adapters, or recovery.

Requires a terminal study summary. Final state and hashes are independently
replayed; process injection and refusal observations remain trusted-host reports.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

METHOD = "r5_session_faults_v1"
CASES = """reserved_worker_kill:tool reserved_worker_kill:model
dispatched_worker_kill:tool dispatched_worker_kill:model receipt_before_commit:default
receipt_committed_before_ack:default publication_committed_before_ack:default
coordinator_restart_after_checkpoint:default transient_store_lock:reserve
transient_store_lock:receive transient_store_lock:publish cancellation_dispatch_order:cancel_first
cancellation_dispatch_order:dispatch_first revocation_after_receipt:default stale_lease_publication:default
reordered_duplicate_receipts:default mailbox:duplicate mailbox:reverse mailbox:count mailbox:bytes mailbox:expiry
provenance_substitution:unknown_reference provenance_substitution:foreign_reference
provenance_substitution:wrong_version provenance_substitution:mismatched_artifact
provenance_substitution:model_as_evidence provenance_substitution:boolean_objective
oversized_reply_known_usage:default transport:delayed_reply transport:lost_reply
transport:malformed_reply transport:wrong_correlation adapter_failure:tool_before_effect
adapter_failure:tool_after_effect adapter_failure:synthetic_provider stale_checkpoint:default
corrupted_signal:default corrupted_database_copy:default""".split()
BOUNDARIES = dict(reserved_worker_kill="after_reserve_commit", dispatched_worker_kill="after_dispatch_commit",
    receipt_before_commit="after_receipt_update_before_commit", receipt_committed_before_ack="after_receipt_commit_before_ack",
    publication_committed_before_ack="after_publication_commit_before_ack",
    coordinator_restart_after_checkpoint="after_checkpoint_and_mailbox_commit", transport="after_effect_before_reply")
LIMITS = dict(token_cap=64, max_calls=8, context_bytes=2048, artifact_bytes=1024, mailbox_messages=2, mailbox_bytes=1024)


def check(value, reason):
    if not value:
        raise ValueError(reason)


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def equal(left, right, reason):
    check(wire(left) == wire(right), reason)


def integer(value):
    check(type(value) is int and value >= 0, "exact nonnegative integer required")
    return value


def decode(text):
    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def read(path):
    return decode(Path(path).read_text())


def digest(value):
    return sha256(value.encode()).hexdigest()


def file_hash(path):
    result = sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def verify_inputs(inputs):
    check(type(inputs) is dict and inputs, "frozen input closure missing")
    for path, expected in inputs.items():
        check(type(expected) is str and len(expected) == 64 and file_hash(path) == expected, "frozen input changed: " + path)


def costs(calls):
    totals = dict(actual_tokens=0, reserved_tokens=0, unknown_tokens=0, unknown_calls=0)
    seen = set()
    for call in calls:
        key = call["id"]
        check(type(key) is str and key and key not in seen, "duplicate/invalid call identity")
        seen.add(key)
        prompt, maximum, reserved = [integer(call[k]) for k in ("prompt", "maximum", "reserved")]
        check(call["action"] in ("model.generate", "tool.evaluate"), "undeclared call action")
        equal([prompt, maximum], [2, 8] if call["action"] == "model.generate" else [0, 0], "synthetic allocation differs")
        check(reserved == prompt + maximum, "reservation components differ")
        state = call["state"]
        if state in ("received", "response_rejected"):
            response = decode(call["response"])
            incoming, outgoing = integer(response["prompt_tokens"]), integer(response["completion_tokens"])
            check(incoming == prompt and outgoing <= maximum and integer(call["actual"]) == incoming + outgoing, "receipt usage differs")
            check(outgoing == (1 if call["action"] == "model.generate" else 0), "declared synthetic completion count differs")
            totals["actual_tokens"] += call["actual"]
        else:
            check(state in ("reserved", "dispatched", "abandoned") and call["response"] is None, "invalid unreceived call")
            if state == "abandoned":
                check(integer(call["actual"]) == 0, "abandoned reservation charged")
            else:
                check(call["actual"] is None, "fabricated known usage")
                totals["reserved_tokens" if state == "reserved" else "unknown_tokens"] += reserved
                totals["unknown_calls"] += int(state == "dispatched")
    return totals


@contextmanager
def readonly_database(path):
    path = Path(path).resolve()
    check(path.is_file(), "missing database")
    for suffix in ("-wal", "-journal"):
        companion = Path(str(path) + suffix)
        check(not companion.exists() or companion.stat().st_size == 0, "unreconciled SQLite journal")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.row_factory = sqlite3.Row
        equal([r[0] for r in db.execute("PRAGMA integrity_check")], ["ok"], "SQLite integrity failure")
        yield db


def database(path):
    with readonly_database(path) as db:
        tables = {name: [dict(r) for r in db.execute(f"SELECT * FROM {name} ORDER BY rowid")]
                  for name in ("run", "work", "calls", "artifacts", "events", "checkpoints", "mailbox")}
    check(len(tables["run"]) == 1, "run identity count differs")
    snapshot = {k: tables[k] for k in ("work", "calls", "artifacts")}
    snapshot.update(run=tables["run"][0], events=[decode(e["value"]) for e in tables["events"]],
                    call_count=len(tables["calls"]), **costs(tables["calls"]))
    return snapshot, tables


def effect_rows(path):
    if not path.exists():
        return []
    with readonly_database(path) as db:
        return [dict(r) for r in db.execute("SELECT * FROM effects ORDER BY sequence")]


def verify_effects(rows, calls):
    counts = Counter(row["call_id"] for row in rows)
    check(all(n == 1 for n in counts.values()), "duplicate adapter invocation")
    for row in rows:
        call = calls[row["call_id"]]
        value = decode(row["value"])
        equal([row["work_id"], row["version"], row["kind"]],
              [call["work_id"], call["version"], "model" if call["action"] == "model.generate" else "tool"], "effect call binding differs")
        check(call["state"] in ("dispatched", "received", "response_rejected"), "effect without dispatch")
        inputs = dict(call_id=row["call_id"], work_id=row["work_id"], version=row["version"], kind=row["kind"], requested_value=value)
        fact = dict(kind="bounded_verified_fact", work_id=row["work_id"], version=row["version"], value=value)
        check(row["input_digest"] == digest(wire(inputs)) and row["output_digest"] == digest(wire(fact)), "effect digest differs")
        if call["state"] == "received":
            equal(decode(call["response"])["artifact"], fact, "receipt differs from actual sidecar effect")
    return dict(counts)


def authorization(run_id, work, action, payload):
    from pheroos.kernel import RuntimeScope
    from pheroos_runtime.session_driver_v1 import current_authorization
    return current_authorization(RuntimeScope("session-v1", run_id, work), work, 1, action, payload)


def ledger(snapshot, tables, authorize=authorization):
    """Replay recorded generations/epochs, dispatch/receipt/publication order."""
    run, calls = snapshot["run"], {c["id"]: c for c in snapshot["calls"]}
    artifacts = {a["ref"]: a for a in snapshot["artifacts"]}
    equal(decode(run["agents"]), ["a", "b"], "agent declaration differs")
    check(len(calls) <= 8, "call bound exceeded")
    state, owners, epochs, work_state, generation, enabled, messages = {}, {}, {}, {}, 0, True, {}
    authorities, published, checkpoint_events = 0, set(), {}
    limits = decode(run["limits"])
    check(snapshot["events"] and snapshot["events"][0]["reason"] == "created", "creation Trace missing")
    for work in snapshot["work"]:
        key = work["id"]
        check(key in ("inspect", "submit"), "undeclared work")
        equal(decode(work["declaration"]), dict(id=key, version=1, dependencies=[] if key == "inspect" else ["inspect"],
              agents=["a", "b"], actions=["model.generate", "tool.evaluate"]), "work declaration differs")
        epochs[key], work_state[key] = 0, "ready"
    equal(list(work_state), ["inspect", "submit"], "fixed work order differs")
    for index, event in enumerate(snapshot["events"]):
        check(set(event) == {"event_type", "protocol_id", "target", "reason", "lineage"}, "Trace shape differs")
        kind, work, data = event["reason"], event["target"], event["lineage"]
        check(event["event_type"] == "ext.session." + kind and event["protocol_id"] == "session.v1", "Trace contract differs")
        if kind == "created":
            check(index == 0 and work == "run", "duplicate/late creation")
            equal(data, dict(run_id=run["run_id"], limits=limits), "creation differs")
        elif kind == "claimed":
            check(enabled and work_state[work] == "ready", "claim after stop or unresolved work")
            check(work == "inspect" or any(artifacts[r]["work_id"] == "inspect" for r in published), "claim before dependency publication")
            epochs[work] += 1
            equal(data, dict(task_id=work, version=1, owner=data["owner"], epoch=epochs[work]), "claim epoch differs")
            check(data["owner"] in ("a", "b"), "undeclared lease owner")
            owners[work], work_state[work] = data["owner"], "leased"
        elif kind in ("reserved", "dispatched", "received", "response_rejected", "reservation_abandoned"):
            key = data["call_id"]
            call = calls[key]
            equal([call["work_id"], call["version"]], [work, 1], "call work/version differs")
            request = decode(call["request"])
            equal(request, dict(fixture="bounded_counter", call_id=key, task_id=work, version=1), "raw request binding differs")
            if kind == "reserved":
                check(enabled and work_state[work] == "leased" and key not in state and call["epoch"] == epochs[work], "invalid reservation authority")
                equal(data, dict(call_id=key, tokens=call["reserved"]), "reservation Trace differs")
                state[key] = "reserved"
            elif kind == "dispatched":
                check(enabled and work_state[work] == "leased" and state[key] == "reserved" and call["epoch"] == epochs[work], "dispatch without current authority")
                expected = authorize(run["run_id"], work, call["action"], request)
                equal(decode(call["authority"]), expected, "dispatch core authorization differs")
                equal(data, dict(call_id=key, authority=expected), "dispatch Trace differs")
                state[key], authorities = "dispatched", authorities + 1
            elif kind == "reservation_abandoned":
                check(state[key] == "reserved", "abandoning a dispatched call")
                equal(data, dict(call_id=key, released_tokens=call["reserved"]), "release differs")
                state[key] = "abandoned"
            else:
                check(state[key] == "dispatched", "duplicate or unsolicited receipt")
                response = decode(call["response"])
                response_digest = response["response_digest"] if kind == "response_rejected" else digest(call["response"])
                equal(data, dict(call_id=key, actual_tokens=call["actual"], response_digest=response_digest), "receipt Trace differs")
                check(len(call["response"].encode()) <= limits["artifact_bytes"], "unbounded retained receipt")
                state[key] = kind
        elif kind == "lease_expired":
            check(enabled and work_state[work] == "leased", "invalid expiry transition")
            expected = "uncertain" if any(state.get(k) == "dispatched" and c["work_id"] == work for k, c in calls.items()) else "ready"
            equal(data, dict(epoch=epochs[work], status=expected), "expiry discarded unknown work")
            work_state[work] = expected
        elif kind == "reconciled":
            check(enabled and work_state[work] == "uncertain" and not any(state.get(k) == "dispatched" and c["work_id"] == work for k, c in calls.items()), "invalid reconciliation")
            previous = snapshot["events"][index - 1]
            check(previous["reason"] in ("received", "response_rejected") and previous["target"] == work, "reconciliation lacks preceding receipt")
            equal(data, dict(call_id=previous["lineage"]["call_id"]), "reconciliation receipt binding differs")
            work_state[work] = "ready"
        elif kind == "published":
            artifact = artifacts[data["artifact_ref"]]
            call = calls[artifact["call_id"]]
            check(enabled and work_state[work] == "leased" and state[call["id"]] == "received" and call["action"] == "tool.evaluate", "publication lacks current lease/settled tool")
            value = decode(artifact["value"])
            equal(value, dict(kind="bounded_verified_fact", work_id=work, version=1, value=1), "published objective invalid")
            equal(value, decode(call["response"])["artifact"], "published artifact differs from receipt")
            check(artifact["work_id"] == work and artifact["version"] == 1 and artifact["publisher"] == owners[work], "publisher lineage differs")
            authority = decode(artifact["authority"])
            payload = dict(task_id=work, version=1, artifact=value, call_id=call["id"], response_digest=digest(call["response"]), scope_ref=authority["scope_ref"])
            expected = authorize(run["run_id"], work, "artifact.publish", payload)
            equal(authority, expected, "publication core authorization differs")
            check(artifact["ref"] == "sha256:" + digest(wire(payload)) and artifact["response_digest"] == payload["response_digest"], "artifact identity differs")
            equal(data, dict(artifact_ref=artifact["ref"], call_id=call["id"], version=1, response_digest=payload["response_digest"], authority=expected), "publication Trace differs")
            check(artifact["ref"] not in published, "duplicate publication")
            published.add(artifact["ref"])
            work_state[work], authorities = "done", authorities + 1
        elif kind in ("cancelled", "revoked"):
            check(enabled and work == "run", "duplicate/misbound stop")
            generation += 1
            equal(data, dict(generation=generation), "stop generation differs")
            enabled = False
            work_state = {k: "done" if v == "done" else kind for k, v in work_state.items()}
        elif kind == "checkpointed":
            check(enabled and work_state[work] == "leased" and data["agent"] == owners[work] and data["generation"] == generation, "checkpoint lacks current lease")
            integer(data["bytes"])
            checkpoint_events[data["agent"]] = (work, dict(data))
        elif kind == "message_sent":
            ref, recipient, key = data["artifact_ref"], data["recipient"], data["message_id"]
            check(enabled and ref in published and key not in messages and recipient in ("a", "b"), "mailbox reference lacks publication/permission")
            check(work == artifacts[ref]["work_id"], "message work lineage differs")
            check(integer(data["bytes"]) > 0, "empty message accounting")
            messages[key] = dict(data)
            selected = [m for m in messages.values() if m["recipient"] == recipient]
            check(len(selected) <= limits["mailbox_messages"] and sum(m["bytes"] for m in selected) <= limits["mailbox_bytes"], "mailbox capacity exceeded")
        elif kind in ("message_acknowledged", "message_expired"):
            check(work == "run", "message removal target differs")
            old = messages.pop(data["message_id"])
            equal(old["recipient"], data["recipient"], "message recipient changed")
        else:
            raise ValueError("undeclared Trace transition: " + kind)
    equal(state, {k: c["state"] for k, c in calls.items()}, "Trace/call states differ")
    check(published == set(artifacts), "Trace/artifact set differs")
    for work in snapshot["work"]:
        equal([work["status"], work["epoch"]], [work_state[work["id"]], epochs[work["id"]]], "final work authority state differs")
        equal([work["version"], work["generation"]], [1, 0], "work version/generation differs")
        equal(work["owner"], owners.get(work["id"]) if work["status"] == "leased" else None, "final lease owner differs")
    equal([run["generation"], run["enabled"]], [generation, int(enabled)], "final run authority differs")
    expected_status = "completed" if all(s == "done" for s in work_state.values()) else "running"
    if not enabled:
        expected_status = next(e["reason"] for e in reversed(snapshot["events"]) if e["reason"] in ("cancelled", "revoked"))
    equal(run["status"], expected_status, "final run disposition differs")
    check(set(checkpoint_events) == {p["agent"] for p in tables["checkpoints"]}, "checkpoint set differs")
    for saved in tables["checkpoints"]:
        work, event = checkpoint_events[saved["agent"]]
        equal([saved["work_id"], saved["version"], saved["generation"], len(saved["value"].encode())], [work, 1, event["generation"], event["bytes"]], "checkpoint binding differs")
        refs = [a["ref"] for a in artifacts.values() if work == "submit" and a["work_id"] == "inspect"]
        check(len(wire(dict(private=decode(saved["value"]), artifact_refs=refs)).encode()) <= limits["context_bytes"], "checkpoint exceeds context bound")
    check(set(messages) == {m["id"] for m in tables["mailbox"]}, "mailbox final state differs")
    for message in tables["mailbox"]:
        check(message["bytes"] == len(wire({k: v for k, v in message.items() if k != "bytes"}).encode()), "mailbox envelope bytes differ")
    return authorities


def expected_counts(case):
    """Literal independent oracle: calls, effects, artifacts, known, reserved, unknown tokens/calls."""
    group, variant = case.split(":")
    result = [1, 1, 0, 0, 0, 0, 0]
    if group == "reserved_worker_kill" or group == "stale_checkpoint" or case == "cancellation_dispatch_order:cancel_first":
        return [1, 0, 0, 0, 0, 0, 0]
    if group == "dispatched_worker_kill":
        return [1, 0, 0, 0, 0, 10 if variant == "model" else 0, 1]
    if case in ("receipt_before_commit:default", "transport:lost_reply", "transport:malformed_reply", "transport:wrong_correlation"):
        return [1, 1, 0, 0, 0, 10, 1]
    if group == "publication_committed_before_ack":
        return [3, 1, 1, 0, 0, 10, 1]
    if group == "coordinator_restart_after_checkpoint" or case == "mailbox:reverse":
        return [2, 2, 2, 0, 0, 0, 0]
    if case == "transient_store_lock:reserve":
        return [1, 0, 0, 0, 0, 0, 0]
    if group == "reordered_duplicate_receipts":
        return [2, 2, 0, 6, 0, 0, 0]
    if group == "adapter_failure":
        return [1, int(variant == "tool_after_effect"), 0, 0, 0, 10 if variant == "synthetic_provider" else 0, 1]
    if group in ("receipt_committed_before_ack", "oversized_reply_known_usage") or case in ("transport:delayed_reply", "provenance_substitution:model_as_evidence"):
        result[3] = 3
    if group in ("mailbox", "corrupted_signal", "stale_lease_publication") or case in ("transient_store_lock:publish", "provenance_substitution:unknown_reference", "provenance_substitution:foreign_reference"):
        result[2] = 1
    if case == "provenance_substitution:foreign_reference":
        result[1] = 2
    return result


def expected_call_states(case):
    group, variant = case.split(":")
    state, model = "received", False
    if group == "reserved_worker_kill":
        state, model = "abandoned", variant == "model"
    elif group == "dispatched_worker_kill":
        state, model = "dispatched", variant == "model"
    elif group == "publication_committed_before_ack":
        return [["one", "tool.evaluate", "received"], ["unused", "model.generate", "abandoned"], ["uncertain", "model.generate", "dispatched"]]
    elif group == "coordinator_restart_after_checkpoint" or case == "mailbox:reverse":
        return [[key, "tool.evaluate", "received"] for key in ("one", "two")]
    elif group == "reordered_duplicate_receipts":
        return [[key, "model.generate", "received"] for key in ("one", "two")]
    elif group == "receipt_before_commit" or group == "transport" and variant != "delayed_reply":
        state, model = "dispatched", True
    elif group == "oversized_reply_known_usage":
        state, model = "response_rejected", True
    elif group == "adapter_failure":
        state, model = "dispatched", variant == "synthetic_provider"
    elif group == "stale_checkpoint" or case == "cancellation_dispatch_order:cancel_first":
        state = "abandoned"
    elif case == "transient_store_lock:reserve":
        state = "reserved"
    elif group == "receipt_committed_before_ack" or case in ("transport:delayed_reply", "provenance_substitution:model_as_evidence"):
        model = True
    return [["one", "model.generate" if model else "tool.evaluate", state]]


def case_trace(case, snapshot):
    events = snapshot["events"]
    group, variant = case.split(":")
    sent = [e["lineage"] for e in events if e["reason"] == "message_sent"]
    removed = [e["reason"] for e in events if e["reason"] in ("message_acknowledged", "message_expired")]
    expected_sent = (2 if variant in ("duplicate", "reverse", "count") else 1 if variant == "expiry" else 0) if group == "mailbox" else int(group == "coordinator_restart_after_checkpoint")
    check(len(sent) == expected_sent, "declared mailbox injection missing")
    equal(removed, ["message_expired"] if case == "mailbox:expiry" else ["message_acknowledged"] * expected_sent, "message removal observations differ")
    if case in ("mailbox:duplicate", "mailbox:count"):
        check(sent[0]["artifact_ref"] == sent[1]["artifact_ref"] and sent[0]["message_id"] != sent[1]["message_id"], "duplicate reference injection differs")
    if case == "mailbox:reverse":
        equal([m["artifact_ref"] for m in sent], [a["ref"] for a in reversed(snapshot["artifacts"])], "reverse arrival injection differs")
    if group == "reordered_duplicate_receipts":
        equal([e["lineage"]["call_id"] for e in events if e["reason"] == "received"], ["two", "one"], "receipt reordering absent")
    if case in ("cancellation_dispatch_order:dispatch_first", "transport:delayed_reply"):
        equal([e["reason"] for e in events if e["reason"] in ("dispatched", "cancelled", "received")], ["dispatched", "cancelled", "received"], "late receipt did not follow committed cancellation")
    if group in ("coordinator_restart_after_checkpoint", "stale_checkpoint"):
        check(sum(e["reason"] == "checkpointed" for e in events) == 1, "checkpoint observation missing")
    epochs = [2 if group in ("reserved_worker_kill", "stale_lease_publication", "stale_checkpoint") else 1,
              2 if group == "coordinator_restart_after_checkpoint" else int(case == "mailbox:reverse")]
    equal([w["epoch"] for w in snapshot["work"]], epochs, "declared restart/reclaim epochs differ")
    stopped = ("cancelled" if group in ("mailbox", "corrupted_signal", "cancellation_dispatch_order", "adapter_failure")
               or case in ("transport:delayed_reply", "provenance_substitution:unknown_reference", "provenance_substitution:foreign_reference")
               else "revoked" if group in ("revocation_after_receipt", "stale_checkpoint") else None)
    expected_run = stopped or ("completed" if group == "coordinator_restart_after_checkpoint" else "running")
    equal(snapshot["run"]["status"], expected_run, "declared recovery disposition differs")
    done = {a["work_id"] for a in snapshot["artifacts"]}
    inspect = "uncertain" if group in ("dispatched_worker_kill", "receipt_before_commit") or case == "transport:lost_reply" else "leased"
    equal([w["status"] for w in snapshot["work"]], ["done" if key in done else stopped or (inspect if key == "inspect" else "ready") for key in ("inspect", "submit")], "declared final work disposition differs")


def observations(case, row, directory):
    integer(row["elapsed_ns"])
    integer(row["inspection_sequence_elapsed_ns"])
    check(type(row.get("before")) is dict, "retained before observation missing")
    raw = read(directory / "inspector-transport.json")
    inspector = decode(raw["stdout"])
    mandatory = {"status", "snapshot", "before", "refusals", "inspection_sequence_elapsed_ns", "effects", "effects_by_call", "accounting", "action_counts"}
    check(type(inspector) is dict and mandatory <= set(inspector), "raw inspector fields missing")
    parent_fields = {"method_version", "case", "counts_toward_verdict", "elapsed_ns", "boundary", "worker_exitcode",
                     "acknowledgment_received", "actual_sigkill", "transport_timeout_observed"}
    equal(inspector, {k: v for k, v in row.items() if k not in parent_fields}, "raw inspector/export differs")
    group, variant = case.split(":")
    crash = group in BOUNDARIES and (group != "transport" or variant in ("lost_reply", "delayed_reply"))
    if crash:
        marker = row["boundary"]
        check(set(marker) == {"boundary", "stage", "pid"}, "marker shape differs")
        check(integer(marker["pid"]) > 0, "missing observed worker PID")
        equal([marker["boundary"], marker["stage"]], [case, BOUNDARIES[group]], "wrong injection boundary")
        delayed = case == "transport:delayed_reply"
        equal([row["worker_exitcode"], row["actual_sigkill"], row["acknowledgment_received"]], [0, False, True] if delayed else [-9, True, False], "kill/ack observation differs")
        worker = read(directory / "worker-transport.json")
        check(type(worker["stdout"]) is str and type(worker["stderr"]) is str, "missing worker transport")
        if delayed:
            equal(read(directory / "delayed-packet.json")["raw_packet"], worker["stdout"], "delayed raw packet differs")
            packet = decode(worker["stdout"])
            equal(packet, dict(call_id="one", response=decode(row["snapshot"]["calls"][0]["response"])), "delayed correlation/settlement differs")
        else:
            equal(worker["stdout"], "", "acknowledgment contradicts kill marker")
        check(row["fresh_process_reopen"] is True, "missing reported fresh inspector")
        integer(row["recovery_elapsed_ns"])
        if case == "transport:lost_reply":
            check(row["transport_timeout_observed"] is True, "missing timeout observation")
    if group == "cancellation_dispatch_order":
        order = row["committed_order"]
        check(len(order) == 2, "missing committed order")
        if variant == "cancel_first":
            equal(order[0], {"committed": "cancel"}, "cancel order differs")
            check(set(order[1]) == {"refused"} and type(order[1]["refused"]) is str, "dispatch refusal missing")
        else:
            equal(order, [{"committed": "dispatch", "effect_executed": True}, {"committed": "cancel"}], "dispatch order differs")
            equal(read(directory / "delayed-response.json"), decode(row["snapshot"]["calls"][0]["response"]), "late raw receipt differs")
    if group == "transport" and variant in ("malformed_reply", "wrong_correlation"):
        packet = read(directory / "transport.json")["raw_packet"]
        if variant == "malformed_reply":
            equal(packet, "malformed JSON", "transport injection differs")
        else:
            equal(decode(packet), dict(call_id="other", response=dict(prompt_tokens=2, completion_tokens=1,
                text="synthetic proposal", artifact=dict(kind="bounded_verified_fact", work_id="inspect", version=1, value=1))), "wrong-correlation packet differs")
    expected_refusals = (["LeaseLost"] if crash else
        ["OperationalError"] if group == "transient_store_lock" else
        ["LeaseLost", "LeaseLost"] if group == "stale_lease_publication" else
        ["StateError", "StateError"] if group == "reordered_duplicate_receipts" else
        ["StateError", "StateError", "StateError", "ValueError", "StateError"] if group == "oversized_reply_known_usage" else
        ["LeaseLost"] * 3 if group == "stale_checkpoint" else
        ["DatabaseError"] * 2 if group == "corrupted_database_copy" else
        ["RuntimeError"] if group == "adapter_failure" else
        ["ValueError"] if group == "transport" else
        ["BudgetExceeded"] if case in ("mailbox:count", "mailbox:bytes") else
        ["LeaseLost"] if case in ("cancellation_dispatch_order:dispatch_first", "revocation_after_receipt:default", "provenance_substitution:wrong_version") else
        ["StateError"] if group in ("provenance_substitution", "corrupted_signal") else [])
    equal([value.split(":", 1)[0] for value in row["refusals"]], expected_refusals, "reported refusal observation differs")


def audit_case(case, row, directory):
    check(row["status"] in ("PASS", "FAIL", "INVALID_ABORT"), "unrecognized source disposition")
    if not directory.exists():
        check(row["status"] == "INVALID_ABORT" and row.get("accounting") is None, "missing case with invented accounting")
        return dict(case=case, source_status=row["status"], audit_status="UNAVAILABLE_RETAINED", accounting=None, runtime_disposition="UNAVAILABLE")
    equal(read(directory / "case.json"), row, "case/export row differs")
    if row["status"] == "PASS":
        observations(case, row, directory)
    corrupted = case == "corrupted_database_copy:default" and row["status"] == "PASS"
    snapshot, tables = database(directory / "session.sqlite")
    equal(snapshot, row["before"] if corrupted else row["snapshot"], "immutable SQLite/export differs")
    equal(decode(snapshot["run"]["limits"]), LIMITS | ({"mailbox_bytes": 1} if case == "mailbox:bytes" else {}), "stored runtime limits differ")
    equal(snapshot["run"]["run_id"], "r5-" + directory.name + "-session", "run identity differs")
    if row.get("before") is not None:
        before = row["before"]
        equal(before["events"], snapshot["events"][:len(before["events"])], "retained before Trace is not a prefix")
        equal({k: before[k] for k in costs(before["calls"])}, costs(before["calls"]), "before accounting differs")
    count = ledger(snapshot, tables)
    all_calls = {c["id"]: c for c in snapshot["calls"]}
    auxiliary = []
    if case == "provenance_substitution:foreign_reference" and row["status"] == "PASS":
        foreign, extra = database(directory / "foreign.sqlite")
        equal(foreign, row["auxiliary_sessions"][0]["snapshot"], "foreign SQLite/export differs")
        equal(foreign["run"]["run_id"], "r5-" + directory.name + "-foreign", "foreign run identity differs")
        equal(decode(foreign["run"]["limits"]), LIMITS, "foreign limits differ")
        count += ledger(foreign, extra)
        all_calls.update({c["id"]: c for c in foreign["calls"]})
        auxiliary.append(dict(ledger="foreign.sqlite", accounting=costs(foreign["calls"]),
            model_dispatches=sum(c["action"] == "model.generate" and c["state"] in ("dispatched", "received", "response_rejected") for c in foreign["calls"]),
            tool_dispatches=sum(c["action"] == "tool.evaluate" and c["state"] in ("dispatched", "received", "response_rejected") for c in foreign["calls"])))
        equal(auxiliary[0]["accounting"], row["auxiliary_sessions"][0]["accounting"], "auxiliary accounting differs")
        equal({k: auxiliary[0][k] for k in ("model_dispatches", "tool_dispatches")}, row["auxiliary_sessions"][0]["action_counts"], "auxiliary dispatch counts differ")
    invoked = effect_rows(directory / "effects.sqlite")
    equal(invoked, row["effects"], "effect sidecar/export differs")
    equal([r["sequence"] for r in invoked], list(range(1, len(invoked) + 1)), "effect sequence identity differs")
    if row["status"] == "PASS":
        for effect in invoked:
            equal(decode(effect["value"]), True if case == "provenance_substitution:boolean_objective" else 1, "declared effect input differs")
    effect_counts = verify_effects(invoked, all_calls)
    if "effects_by_call" in row:
        equal(effect_counts, row["effects_by_call"], "effect invocation count differs")
    if auxiliary:
        equal(invoked, row["auxiliary_sessions"][0]["effects"], "shared auxiliary sidecar export differs")
        equal(effect_counts, row["auxiliary_sessions"][0]["effects_by_call"], "shared auxiliary effect counts differ")
    check({k for k, c in all_calls.items() if c["state"] in ("received", "response_rejected")} <= set(effect_counts), "settled receipt without effect invocation")
    if case == "oversized_reply_known_usage:default" and row["status"] == "PASS":
        original = dict(prompt_tokens=2, completion_tokens=1, text="x" * 2048,
                        artifact=dict(kind="bounded_verified_fact", work_id="inspect", version=1, value=1))
        equal(decode(snapshot["calls"][0]["response"]), dict(response_rejected="response_bytes_exceeded",
              response_digest=digest(wire(original)), response_bytes=len(wire(original).encode()), prompt_tokens=2, completion_tokens=1), "oversized raw-response commitment differs")
    if case in ("coordinator_restart_after_checkpoint:default", "stale_checkpoint:default") and row["status"] == "PASS":
        checkpoint = tables["checkpoints"][0]
        old = dict(task_id="submit" if case.startswith("coordinator") else "inspect", version=1,
                   owner="b" if case.startswith("coordinator") else "a", epoch=1)
        expected = dict(artifact_ref=snapshot["artifacts"][0]["ref"], old_lease=old) if case.startswith("coordinator") else dict(old_lease=old, proposal={"value": 999})
        equal(decode(checkpoint["value"]), expected, "saved checkpoint data differs")
    totals = costs(snapshot["calls"])
    action_counts = {name: sum(c["action"] == action and c["state"] in ("dispatched", "received", "response_rejected") for c in snapshot["calls"])
                    for name, action in (("model_dispatches", "model.generate"), ("tool_dispatches", "tool.evaluate"))}
    if corrupted:
        check(row["snapshot"] is None and row["accounting"] is None and row["action_counts"] is None and row["runtime_disposition"] == "ABORT_UNAVAILABLE", "unavailable ledger was relabeled known")
        try:
            database(directory / "corrupted.sqlite")
        except sqlite3.DatabaseError:
            pass
        else:
            raise ValueError("corrupted copy remained readable")
        disposition = "ABORT_UNAVAILABLE"
    else:
        equal(totals, row["accounting"], "accounting/export differs")
        if "action_counts" in row:
            equal(action_counts, row["action_counts"], "dispatch counts differ")
        disposition = "UNRESOLVED" if totals["unknown_calls"] else snapshot["run"]["status"].upper()
    if row["status"] == "PASS":
        actual = [len(snapshot["calls"]), len(invoked), len(snapshot["artifacts"])] + [totals[k] for k in ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls")]
        equal(actual, expected_counts(case), "declared fault oracle counts differ")
        equal([[c["id"], c["action"], c["state"]] for c in snapshot["calls"]], expected_call_states(case), "declared final call states differ")
        case_trace(case, snapshot)
    return dict(case=case, source_status=row["status"], audit_status="INTEGRITY_PASS", runtime_disposition=disposition,
                accounting=None if corrupted else totals, intact_original_accounting=totals if corrupted else None,
                primary_action_counts=None if corrupted else action_counts, intact_original_action_counts=action_counts if corrupted else None,
                auxiliary_ledgers=auxiliary, physical_effect_log_count=1 if (directory / "effects.sqlite").exists() else 0,
                authority_checks=count, effect_invocations=len(invoked), causal_events=len(snapshot["events"]))


def matrix(summary, rows):
    check(summary["method_version"] == METHOD and summary["counts_toward_verdict"] is False, "summary identity differs")
    check(summary["status"] in ("PASS", "FAIL", "INVALID_ABORT"), "nonterminal source summary")
    check(type(summary["source_unchanged"]) is bool, "source identity status is not boolean")
    check(type(summary["finalization_errors"]) is list and (not summary["source_unchanged"] or not summary["finalization_errors"]), "finalization errors conflict with source identity")
    equal([r["case"] for r in rows], CASES, "missing/duplicate/reordered fault identities")
    for row in rows:
        check(row["method_version"] == METHOD and row["counts_toward_verdict"] is False and row["status"] in ("PASS", "FAIL", "INVALID_ABORT"), "source row metadata differs")
    equal(summary["cases"], 38, "declared count differs")
    equal(summary["outcomes"], {s: sum(r["status"] == s for r in rows) for s in ("PASS", "FAIL", "INVALID_ABORT")}, "source outcome counts differ")
    equal(summary["source_accounting"], [dict(case=r["case"], status=r["status"], accounting=r.get("accounting")) for r in rows], "retained source accounting differs")
    expected = "INVALID_ABORT" if not summary["source_unchanged"] or any(r["status"] == "INVALID_ABORT" for r in rows) else "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
    equal(summary["status"], expected, "source disposition conceals failures")
    check(integer(summary["gpu_calls"]) == 0 and integer(summary["paid_provider_calls"]) == 0, "unexpected provider activity declaration")


def diagnostic_accounting(case, directory):
    """A non-accounting invariant failure must not discard readable charges."""
    result = dict(accounting=None, primary_action_counts=None, intact_original_accounting=None,
                  intact_original_action_counts=None, auxiliary_ledgers=[], effect_invocations=None,
                  accounting_verified=False, accounting_errors=[])
    ledgers = [("primary", "session.sqlite")]
    if case == "corrupted_database_copy:default":
        ledgers = [("damaged_primary", "corrupted.sqlite"), ("intact_original", "session.sqlite")]
    elif case == "provenance_substitution:foreign_reference":
        ledgers.append(("auxiliary_foreign", "foreign.sqlite"))
    for role, name in ledgers:
        try:
            snapshot, _ = database(directory / name)
            accounting = costs(snapshot["calls"])
            actions = {key: sum(c["action"] == action and c["state"] in ("dispatched", "received", "response_rejected") for c in snapshot["calls"])
                       for key, action in (("model_dispatches", "model.generate"), ("tool_dispatches", "tool.evaluate"))}
            if role == "primary":
                result.update(accounting=accounting, primary_action_counts=actions)
            elif role == "intact_original":
                result.update(intact_original_accounting=accounting, intact_original_action_counts=actions)
            elif role == "auxiliary_foreign":
                result["auxiliary_ledgers"].append(dict(ledger=name, accounting=accounting, **actions))
            else:
                # An unexpectedly readable damaged copy is not a second charge.
                result["unexpectedly_readable_damaged_copy"] = dict(accounting=accounting, action_counts=actions)
            result["accounting_verified"] = True
        except Exception as error:
            result["accounting_errors"].append(dict(ledger=name, role=role, error=f"{type(error).__name__}: {error}"))
    return result


def accounting_export(checked):
    verified = [r for r in checked if r["audit_status"] == "INTEGRITY_PASS" or r.get("accounting_verified") is True]
    primary = [r for r in verified if r["accounting"] is not None]
    auxiliary = [a for r in verified for a in r["auxiliary_ledgers"]]
    intact = [r for r in verified if r["intact_original_accounting"] is not None]
    def summed(rows, keys):
        return {key: sum(row[key] for row in rows) for key in keys} if rows else None
    token_keys = ("actual_tokens", "reserved_tokens", "unknown_tokens", "unknown_calls")
    action_keys = ("model_dispatches", "tool_dispatches")
    unique_costs = [r["accounting"] for r in primary] + [a["accounting"] for a in auxiliary] + [r["intact_original_accounting"] for r in intact]
    unique_actions = [r["primary_action_counts"] for r in primary] + auxiliary + [r["intact_original_action_counts"] for r in intact]
    return dict(verified_primary_ledgers=len(primary), unavailable_primary_cases=[r["case"] for r in checked if r.get("accounting") is None],
        primary_known_components=summed([r["accounting"] for r in primary], token_keys),
        primary_dispatches=summed([r["primary_action_counts"] for r in primary], action_keys),
        auxiliary_ledgers=auxiliary,
        intact_originals=[dict(case=r["case"], accounting=r["intact_original_accounting"], action_counts=r["intact_original_action_counts"]) for r in intact],
        all_observed_unique_available_ledger_components=summed(unique_costs, token_keys),
        all_observed_unique_available_dispatches=summed(unique_actions, action_keys),
        sidecar_effect_invocations=sum(r["effect_invocations"] for r in verified if r["effect_invocations"] is not None) if any(r["effect_invocations"] is not None for r in verified) else None,
        unverified_effect_case_ids=[r["case"] for r in checked if r.get("effect_invocations") is None],
        coverage="Only verified available ledgers are summed. Auxiliary and intact-before-corruption work is separate; damaged or missing primary accounting stays unavailable. Shared sidecars are counted once.")


def audit(output):
    # This gate precedes imports, source hashing, and any database access.
    check((output / "summary.json").is_file(), "terminal study summary required; actual auditing remains gated")
    summary, rows = read(output / "summary.json"), read(output / "outcomes.json")
    matrix(summary, rows)
    paths = sorted(p for p in output.rglob("*") if p.is_file())
    evidence = {str(p): file_hash(p) for p in paths}
    frozen = read(output / "freeze.json")
    check(frozen["method_version"] == METHOD and frozen["frozen_before_cases"] is True and frozen["counts_toward_verdict"] is False, "missing pre-execution identity")
    config = frozen["configuration"]
    equal(config, dict(method_version=METHOD, phase="engineering_fault_pilot", counts_toward_verdict=False,
        cases=CASES, boundary_timeout_seconds=10, child_timeout_seconds=20, reply_timeout_ms=50,
        sqlite_busy_timeout_ms=50, max_child_output_bytes=4194304, runtime_limits=LIMITS,
        synthetic_model=dict(prompt_tokens=2, max_new_tokens=8, completion_tokens=1), gpu_calls=0, paid_provider_calls=0,
        prerequisite="root-reviewed G5 capability and R4 completion gates"), "frozen configuration differs")
    installed = frozen["installed"]
    inputs = dict(frozen["source_sha256"], **installed["file_sha256"])
    verify_inputs(inputs)
    runtime_root = Path(installed["runtime_root"])
    check(str(runtime_root / "session_v1.py") in inputs and str(runtime_root / "session_driver_v1.py") in inputs, "missing installed Session identity")
    sys.path.insert(0, str(runtime_root.parent))
    import pheroos_runtime.session_v1 as installed_session
    import pheroos
    check(Path(installed_session.__file__).resolve() == (runtime_root / "session_v1.py").resolve(), "audit imported another runtime")
    core_root = runtime_root.parent / "pheroos"
    check(Path(pheroos.__file__).resolve() == (core_root / "__init__.py").resolve(), "audit imported another core")
    expected_installed = [*runtime_root.glob("*.py"), *core_root.rglob("*.py"), *core_root.rglob("*.json"), Path(installed["interpreter"]).resolve()]
    check(set(installed["file_sha256"]) == {str(p) for p in expected_installed}, "installed source/contract/interpreter closure incomplete")
    check(len(frozen["source_sha256"]) == 4 and {Path(p).name for p in frozen["source_sha256"]} ==
          {"r5_session_faults.py", "r5-session-faults-v1.json", "R5-session-faults-v1-contract.md", "test_r5_session_faults.py"}, "study source closure incomplete")
    config_path = next(p for p in frozen["source_sha256"] if Path(p).name == "r5-session-faults-v1.json")
    equal(read(config_path), config, "source configuration differs from frozen configuration")
    checked = []
    for index, row in enumerate(rows):
        directory = output / "cases" / f"{index:02d}-{row['case'].replace(':', '-')}"
        try:
            checked.append(audit_case(row["case"], row, directory))
        except Exception as error:
            checked.append(dict(case=row["case"], source_status=row["status"], audit_status="AUDIT_MISMATCH",
                error=f"{type(error).__name__}: {error}", reported_accounting=row.get("accounting"),
                **diagnostic_accounting(row["case"], directory)))
    for path, expected in evidence.items():
        check(file_hash(path) == expected, "audit changed original evidence")
    verify_inputs(inputs)
    mismatches = sum(r["audit_status"] == "AUDIT_MISMATCH" for r in checked)
    return dict(audit_method="r5_session_faults_independent_audit_v1", audit_status="AUDIT_MISMATCH" if mismatches else "INTEGRITY_PASS",
        source_status=summary["status"], engineering_gate="ELIGIBLE_FOR_ROOT_REVIEW" if not mismatches and summary["status"] == "PASS" else "NOT_ACCEPTED",
        counts_toward_verdict=False, generated_model_calls=0, cases=checked, source_summary=summary,
        observed_accounting=accounting_export(checked),
        frozen_input_sha256=inputs, original_evidence_sha256=evidence, original_evidence_unchanged=True,
        audit_source_sha256={str(Path(__file__).resolve()): file_hash(__file__)},
        limitations=["Control markers, exit codes, committed process order and refusal messages are trusted harness observations; no independent OS transcript was retained.",
          "Trace generations/epochs and publication bindings replay, but no historical clock instants or rejected-operation events exist; exact failed lease predicates cannot be reconstructed.",
          "Before snapshots have case-specific capture points. Transient returned contexts/mailboxes and refused-action arguments were not separately retained. Logical clock injections do not establish wall-clock jump robustness.",
          "Cancel/dispatch cases are two serialized process orders, not concurrent-race sampling. Timeout duration is a declared boundary plus reported observation, not an independently timed interval.",
          "Sidecar rows count this bounded adapter's invocations; they do not establish exactly-once effects for arbitrary APIs.",
          "An unresolved dispatch remains UNRESOLVED, even when the declared safety invariant passes. The corrupt copy remains ABORT_UNAVAILABLE with null accounting.",
          "No real model/provider, GPU, power-loss, multi-host, soak, or long-run event-log bound is tested."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    check((args.output / "summary.json").is_file(), "terminal study summary required; do not audit an active collection")
    check(not args.audit_output.exists(), "new exclusive additive audit output required")
    try:
        result = audit(args.output.resolve())
    except Exception as error:
        result = dict(audit_method="r5_session_faults_independent_audit_v1", audit_status="AUDIT_ERROR", counts_toward_verdict=False,
                      error=f"{type(error).__name__}: {error}", source_summary=read(args.output / "summary.json"))
    with args.audit_output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["audit_status"])
    return 0 if result.get("engineering_gate") == "ELIGIBLE_FOR_ROOT_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
