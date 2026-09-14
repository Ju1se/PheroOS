"""Finite installed-Session fault harness; study execution requires prior gates.

No provider/model is imported. Child-only injections never edit runtime files.
The bounded effect log deliberately records duplicate invocations without
idempotency, so replay bugs cannot be hidden by an idempotent test adapter.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import sqlite3
import subprocess
import sys
import time

METHOD = "r5_session_faults_v1"
GROUPS = {
    "reserved_worker_kill": ("tool", "model"),
    "dispatched_worker_kill": ("tool", "model"),
    "receipt_before_commit": ("default",),
    "receipt_committed_before_ack": ("default",),
    "publication_committed_before_ack": ("default",),
    "coordinator_restart_after_checkpoint": ("default",),
    "transient_store_lock": ("reserve", "receive", "publish"),
    "cancellation_dispatch_order": ("cancel_first", "dispatch_first"),
    "revocation_after_receipt": ("default",),
    "stale_lease_publication": ("default",),
    "reordered_duplicate_receipts": ("default",),
    "mailbox": ("duplicate", "reverse", "count", "bytes", "expiry"),
    "provenance_substitution": ("unknown_reference", "foreign_reference", "wrong_version",
                               "mismatched_artifact", "model_as_evidence", "boolean_objective"),
    "oversized_reply_known_usage": ("default",),
    "transport": ("delayed_reply", "lost_reply", "malformed_reply", "wrong_correlation"),
    "adapter_failure": ("tool_before_effect", "tool_after_effect", "synthetic_provider"),
    "stale_checkpoint": ("default",),
    "corrupted_signal": ("default",),
    "corrupted_database_copy": ("default",),
}
CASES = tuple(f"{group}:{variant}" for group, variants in GROUPS.items() for variant in variants)
CRASH_GROUPS = frozenset(("reserved_worker_kill", "dispatched_worker_kill", "receipt_before_commit",
    "receipt_committed_before_ack", "publication_committed_before_ack", "coordinator_restart_after_checkpoint"))
BOUNDARIES = dict(reserved_worker_kill="after_reserve_commit", dispatched_worker_kill="after_dispatch_commit",
    receipt_before_commit="after_receipt_update_before_commit", receipt_committed_before_ack="after_receipt_commit_before_ack",
    publication_committed_before_ack="after_publication_commit_before_ack",
    coordinator_restart_after_checkpoint="after_checkpoint_and_mailbox_commit", transport="after_effect_before_reply")


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def save(path, value):
    with Path(path).open("x") as stream:
        stream.write(wire(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def configuration():
    return dict(method_version=METHOD, phase="engineering_fault_pilot", counts_toward_verdict=False,
                cases=list(CASES), boundary_timeout_seconds=10, child_timeout_seconds=20,
                reply_timeout_ms=50,
                sqlite_busy_timeout_ms=50, max_child_output_bytes=4 * 1024 * 1024,
                runtime_limits=dict(token_cap=64, max_calls=8, context_bytes=2048,
                                    artifact_bytes=1024, mailbox_messages=2, mailbox_bytes=1024),
                synthetic_model=dict(prompt_tokens=2, max_new_tokens=8, completion_tokens=1),
                gpu_calls=0, paid_provider_calls=0,
                prerequisite="root-reviewed G5 capability and R4 completion gates")


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def refused(error_type, action):
    try:
        action()
    except error_type as error:
        return f"{type(error).__name__}: {error}"
    raise AssertionError(f"expected {error_type.__name__}")


def runtime():
    from pheroos_runtime.session_v1 import Session
    from pheroos_runtime.session_driver_v1 import current_authorization
    from pheroos_runtime.store import BudgetExceeded, Lease, LeaseLost, StateError
    return Session, current_authorization, BudgetExceeded, Lease, LeaseLost, StateError


def probe(runtime_site):
    import pheroos
    import pheroos_runtime
    runtime()  # Assert this installation exposes the selected experimental consumer.
    root = Path(pheroos_runtime.__file__).resolve().parent
    if root.parent != Path(runtime_site).resolve():
        raise ValueError("Session must resolve to the explicitly installed runtime target")
    files = [*root.glob("*.py"), *Path(pheroos.__file__).parent.rglob("*.py"),
             *Path(pheroos.__file__).parent.rglob("*.json"), Path(sys.executable).resolve()]
    return dict(runtime_root=str(root), interpreter=sys.executable, python=sys.version,
                file_sha256={str(p): sha256(p.read_bytes()).hexdigest() for p in sorted(files)})


def new_session(directory, *, name="session", mailbox_bytes=None):
    Session, *_ = runtime()
    limits = configuration()["runtime_limits"]
    if mailbox_bytes is not None:
        limits["mailbox_bytes"] = mailbox_bytes
    work = [dict(id=key, version=1, dependencies=[] if key == "inspect" else ["inspect"],
                 agents=["a", "b"], actions=["model.generate", "tool.evaluate"])
            for key in ("inspect", "submit")]
    return Session(Path(directory) / f"{name}.sqlite", clock=lambda: 100) if (Path(directory) / f"{name}.sqlite").exists() else (
        Session.create(Path(directory) / f"{name}.sqlite", f"r5-{Path(directory).name}-{name}",
                       agents=["a", "b"], work=work, clock=lambda: 100, **limits))


def effect(directory, call_id, work, *, kind="tool", value=1):
    """One committed row per actual adapter invocation; duplicate IDs allowed."""
    fact = dict(kind="bounded_verified_fact", work_id=work, version=1, value=value)
    inputs = dict(call_id=call_id, work_id=work, version=1, kind=kind, requested_value=value)
    with sqlite3.connect(Path(directory) / "effects.sqlite") as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE IF NOT EXISTS effects (sequence INTEGER PRIMARY KEY, call_id TEXT, work_id TEXT, version INTEGER, kind TEXT, value TEXT, input_digest TEXT, output_digest TEXT)")
        db.execute("INSERT INTO effects(call_id,work_id,version,kind,value,input_digest,output_digest) VALUES (?,?,?,?,?,?,?)",
                   (call_id, work, 1, kind, wire(value), sha256(wire(inputs).encode()).hexdigest(), sha256(wire(fact).encode()).hexdigest()))
    return fact


def effects(directory):
    path = Path(directory) / "effects.sqlite"
    if not path.exists():
        return []
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM effects ORDER BY sequence")]


def reserve(session, lease, call_id="one", *, model=False):
    session.reserve(lease, call_id, "model.generate" if model else "tool.evaluate",
                    {"fixture": "bounded_counter", "call_id": call_id},
                    prompt_tokens=2 if model else 0, max_new_tokens=8 if model else 0)


def dispatch(session, lease, call_id="one"):
    session.dispatch(lease, call_id, runtime()[1])


def reply(directory, call_id="one", work="inspect", *, model=False, value=1):
    fact = effect(directory, call_id, work, kind="model" if model else "tool", value=value)
    return dict(prompt_tokens=2, completion_tokens=1, text="synthetic proposal", artifact=fact) if model else (
        dict(prompt_tokens=0, completion_tokens=0, artifact=fact))


def verified(work, fact):
    return (type(fact) is dict and set(fact) == {"kind", "work_id", "version", "value"}
            and fact["kind"] == "bounded_verified_fact" and fact["work_id"] == work
            and type(fact["version"]) is int and fact["version"] == 1
            and type(fact["value"]) is int and fact["value"] == 1)


def publish(session, lease, response, call_id="one"):
    return session.publish(lease, call_id, response["artifact"], verify=verified, authorize=runtime()[1])


def completed_inspection(session, directory, *, call_id="one"):
    lease = session.claim("a", "inspect", lease_seconds=1)
    reserve(session, lease, call_id)
    dispatch(session, lease, call_id)
    response = reply(directory, call_id)
    session.receive(call_id, response)
    return lease, response, publish(session, lease, response, call_id)


def pause(case, control_fd, *, stage, release=False):
    payload = wire(dict(boundary=case, stage=stage, pid=os.getpid())).encode() + b"\n"
    os.write(control_fd, payload)
    if release:
        require(sys.stdin.readline() == "release\n", "missing controlled release")
    else:
        signal.pause()
        raise AssertionError("crash boundary resumed without SIGKILL")


@contextmanager
def before_commit_pause(session, case, control_fd):
    """Proxy only this child's transaction after the actual receipt UPDATE."""
    original = sqlite3.connect
    class Connection:
        def __init__(self, inner):
            object.__setattr__(self, "inner", inner)
            object.__setattr__(self, "received_update", False)
        def __getattr__(self, key):
            return getattr(self.inner, key)
        def __setattr__(self, key, value):
            setattr(self.inner, key, value)
        def execute(self, sql, parameters=()):
            value = self.inner.execute(sql, parameters)
            if sql.startswith("UPDATE calls SET state=?,response=?,actual=?"):
                object.__setattr__(self, "received_update", True)
            return value
        def commit(self):
            if self.received_update:
                pause(case, control_fd, stage="after_receipt_update_before_commit")
            self.inner.commit()
    def connect(path, *args, **kwargs):
        connection = original(path, *args, **kwargs)
        return Connection(connection) if str(path) == session.path else connection
    sqlite3.connect = connect
    try:
        yield
    finally:
        sqlite3.connect = original


def crash_worker(case, directory, control_fd):
    group, variant = case.split(":")
    session = new_session(directory)
    if group == "coordinator_restart_after_checkpoint":
        _, _, reference = completed_inspection(session, directory)
        lease = session.claim("b", "submit", lease_seconds=1)
        session.checkpoint(lease, {"artifact_ref": reference, "old_lease": asdict(lease)})
        session.send("a", "b", reference, ttl_seconds=200)
        pause(case, control_fd, stage="after_checkpoint_and_mailbox_commit")
    lease = session.claim("a", "inspect", lease_seconds=1)
    model = variant == "model" or group in ("receipt_before_commit", "receipt_committed_before_ack", "transport")
    reserve(session, lease, model=model)
    if group == "reserved_worker_kill":
        pause(case, control_fd, stage="after_reserve_commit")
    dispatch(session, lease)
    if group == "dispatched_worker_kill":
        pause(case, control_fd, stage="after_dispatch_commit")
    response = reply(directory, model=model)
    if group == "transport":
        pause(case, control_fd, stage="after_effect_before_reply", release=variant == "delayed_reply")
        print(wire(dict(call_id="one", response=response)), flush=True)
        return
    if group == "receipt_before_commit":
        with before_commit_pause(session, case, control_fd):
            session.receive("one", response)
        raise RuntimeError("precommit receipt hook did not fire; injection is invalid")
    session.receive("one", response)
    if group == "publication_committed_before_ack":
        reserve(session, lease, "unused", model=True)
        reserve(session, lease, "uncertain", model=True)
        dispatch(session, lease, "uncertain")
        publish(session, lease, response)
        pause(case, control_fd, stage="after_publication_commit_before_ack")
    elif group == "receipt_committed_before_ack":
        pause(case, control_fd, stage="after_receipt_commit_before_ack")
    else:
        raise ValueError("undeclared crash boundary")


def inspect_crash(case, directory, delayed_packet=None):
    started = time.monotonic_ns()
    Session, _, _, Lease, LeaseLost, StateError = runtime()
    group, variant = case.split(":")
    session = Session(Path(directory) / "session.sqlite", clock=lambda: 200)
    before = session.snapshot()
    refusals = []
    old = Lease("inspect", 1, "a", 1)
    if group == "reserved_worker_kill":
        session.recover()
        after = session.snapshot()
        require(after["actual_tokens"] == after["reserved_tokens"] == after["unknown_tokens"] == 0,
                "undispatched reservation not released")
        require(after["calls"][0]["state"] == "abandoned", "reservation not abandoned")
        current = session.claim("b", "inspect")
        require(current and current.epoch == 2, "higher-epoch reclaim absent")
        refusals.append(refused(LeaseLost, lambda: dispatch(session, old)))
        require(effects(directory) == [], "undispatched adapter ran")
    elif group in ("dispatched_worker_kill", "receipt_before_commit") or case == "transport:lost_reply":
        session.recover()
        after = session.snapshot()
        expected = 0 if variant == "tool" else 10
        require(after["unknown_calls"] == 1 and after["unknown_tokens"] == expected,
                "unknown dispatch was discarded")
        require(after["actual_tokens"] == 0 and after["calls"][0]["state"] == "dispatched", "partial receipt committed")
        require(session.claim("b", "inspect") is None, "unresolved work was reclaimed")
        refusals.append(refused(LeaseLost, lambda: dispatch(session, old)))
        require(len(effects(directory)) == (0 if group == "dispatched_worker_kill" else 1), "unexpected effect execution")
    elif group == "receipt_committed_before_ack":
        require(before["actual_tokens"] == 3 and before["unknown_calls"] == 0, "committed usage lost")
        response = json.loads(before["calls"][0]["response"])
        session.receive("one", response)
        require(session.snapshot() == before, "duplicate receipt changed state/cost")
        from pheroos_runtime.session_driver_v1 import SessionDriver
        require(SessionDriver(session).replay("one") == response, "settled receipt not replayable")
        refusals.append(refused(LeaseLost, lambda: dispatch(session, old)))
    elif group == "publication_committed_before_ack":
        require(len(before["artifacts"]) == 1 and before["work"][0]["status"] == "done", "publication not durable")
        require(before["reserved_tokens"] == 0 and before["unknown_tokens"] == 10 and before["unknown_calls"] == 1,
                "publication released unknowns or stranded unused reservations")
        artifact = session.artifact(before["artifacts"][0]["ref"])
        require(verified("inspect", artifact["value"]), "committed artifact not retrievable")
        refusals.append(refused(LeaseLost, lambda: publish(session, old, {"artifact": artifact["value"]})))
    elif group == "coordinator_restart_after_checkpoint":
        old = Lease("submit", 1, "b", 1)
        session.recover()
        current = session.claim("b", "submit")
        require(current and current.epoch == 2, "checkpoint work not reclaimed")
        context = session.context(current)
        messages = session.mailbox("b")
        require(len(messages) == 1 and context["private"]["artifact_ref"] == messages[0]["artifact_ref"], "checkpoint/mailbox lost")
        require(session.artifact(messages[0]["artifact_ref"])["value"]["value"] == 1, "verified reference lost")
        refusals.append(refused(LeaseLost, lambda: session.checkpoint(old, {})))
        reserve(session, current, "two")
        dispatch(session, current, "two")
        response = reply(directory, "two", "submit")
        session.receive("two", response)
        publish(session, current, response, "two")
        session.ack("b", messages[0]["id"])
        require(session.snapshot()["run"]["status"] == "completed", "journey did not complete after restart")
    elif case == "transport:delayed_reply":
        packet = parse_packet(delayed_packet, "one")
        session.receive("one", packet)
        require(session.snapshot()["actual_tokens"] == 3 and session.snapshot()["run"]["status"] == "cancelled",
                "late receipt did not settle without revival")
        require(session.claim("a", "inspect") is None, "late receipt revived cancellation")
        refusals.append(refused(LeaseLost, lambda: publish(session, old, packet)))
    else:
        raise ValueError("undeclared crash inspector")
    observed = result(directory, session, before=before, refusals=refusals, fresh_process_reopen=True)
    observed["recovery_elapsed_ns"] = time.monotonic_ns() - started
    return observed


def json_object(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate transport key")
            value[key] = item
        return value
    if type(text) is not str:
        raise ValueError("JSON text required")
    value = json.loads(text, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite transport value")))
    if type(value) is not dict:
        raise ValueError("JSON object required")
    return value


def parse_packet(text, call_id):
    if type(text) is not str or len(text.encode()) > 4096:
        raise ValueError("bounded transport text required")
    value = json_object(text)
    if set(value) != {"call_id", "response"} or value["call_id"] != call_id or type(value["response"]) is not dict:
        raise ValueError("transport correlation or response mismatch")
    return value["response"]


def accounting(snapshot):
    def integer(value):
        if type(value) is not int or value < 0:
            raise ValueError("exact nonnegative accounting integer required")
        return value
    if type(snapshot) is not dict or type(snapshot.get("calls")) is not list:
        raise ValueError("call list unavailable")
    totals = dict(actual_tokens=0, reserved_tokens=0, unknown_tokens=0, unknown_calls=0)
    seen = set()
    for call in snapshot["calls"]:
        if type(call) is not dict or type(call.get("id")) is not str or call["id"] in seen:
            raise ValueError("invalid or duplicate call identity")
        seen.add(call["id"])
        prompt, maximum, allocation = [integer(call.get(key)) for key in ("prompt", "maximum", "reserved")]
        require(allocation == prompt + maximum, "reservation components differ")
        if call.get("action") not in ("model.generate", "tool.evaluate"):
            raise ValueError("undeclared accounting action")
        require((prompt, maximum) == ((2, 8) if call["action"] == "model.generate" else (0, 0)),
                "call allocation differs from declared synthetic model/tool contract")
        state = call.get("state")
        if state in ("received", "response_rejected"):
            response = json_object(call.get("response"))
            actual = integer(call.get("actual"))
            received_prompt, completion = [integer(response.get(key)) for key in ("prompt_tokens", "completion_tokens")]
            require(received_prompt == prompt and completion <= maximum and actual == received_prompt + completion,
                    "received usage components differ")
            totals["actual_tokens"] += actual
        elif state in ("reserved", "dispatched", "abandoned"):
            require(call.get("response") is None, "unreceived call has response")
            if state == "abandoned":
                require(integer(call.get("actual")) == 0, "abandoned reservation was charged")
            else:
                require(call.get("actual") is None, "unknown/reserved call has fabricated usage")
                totals["reserved_tokens" if state == "reserved" else "unknown_tokens"] += allocation
                totals["unknown_calls"] += int(state == "dispatched")
        else:
            raise ValueError("undeclared call state")
    require(integer(snapshot.get("call_count")) == len(seen), "call count differs")
    for key, value in totals.items():
        require(integer(snapshot.get(key)) == value, "snapshot accounting differs from call components")
    return totals


def result(directory, session, **observations):
    snapshot = session.snapshot() if session is not None else None
    invoked = effects(directory)
    counts = {call: sum(row["call_id"] == call for row in invoked) for call in {r["call_id"] for r in invoked}}
    require(all(count == 1 for count in counts.values()), "duplicate bounded effect invocation")
    for row in invoked:
        value = json.loads(row["value"])
        require(type(row["version"]) is int and row["version"] == 1, "effect version mismatch")
        inputs = dict(call_id=row["call_id"], work_id=row["work_id"], version=1, kind=row["kind"], requested_value=value)
        output = dict(kind="bounded_verified_fact", work_id=row["work_id"], version=1, value=value)
        require(row["input_digest"] == sha256(wire(inputs).encode()).hexdigest()
                and row["output_digest"] == sha256(wire(output).encode()).hexdigest(), "effect digest mismatch")
    costs = accounting(snapshot) if snapshot is not None else None
    if snapshot is not None:
        from pheroos.kernel import RuntimeScope
        from pheroos.trace import TraceEvent
        for event in snapshot["events"]:
            TraceEvent(**event).validate()
        traced = {event["lineage"]["artifact_ref"] for event in snapshot["events"] if event["event_type"] == "ext.session.published"}
        require(traced == {a["ref"] for a in snapshot["artifacts"]}, "publication Trace differs from stored artifacts")
        for artifact in snapshot["artifacts"]:
            call = next(c for c in snapshot["calls"] if c["id"] == artifact["call_id"])
            require(call["action"] == "tool.evaluate" and call["state"] == "received", "artifact lacks settled tool")
            require((artifact["work_id"], artifact["version"]) == (call["work_id"], call["version"]), "artifact work/version mismatch")
            require(artifact["response_digest"] == sha256(call["response"].encode()).hexdigest(), "artifact response digest mismatch")
            require(wire(json.loads(call["response"])["artifact"]) == artifact["value"], "artifact value mismatch")
            require(verified(artifact["work_id"], json.loads(artifact["value"])), "unverified objective published")
            authority = json.loads(artifact["authority"])
            scope = RuntimeScope("session-v1", snapshot["run"]["run_id"], artifact["work_id"])
            require(authority["scope_ref"] == scope.scope_ref and authority["task_id"] == artifact["work_id"]
                    and authority["version"] == artifact["version"] and authority["action"] == "artifact.publish"
                    and authority["reusable_authority"] is False, "publication authority lineage mismatch")
    action_counts = {kind: sum(c["action"] == action and c["state"] in ("dispatched", "received", "response_rejected")
                              for c in snapshot["calls"])
                     for kind, action in (("model_dispatches", "model.generate"), ("tool_dispatches", "tool.evaluate"))} if snapshot is not None else None
    return dict(snapshot=snapshot, effects=invoked, effects_by_call=counts, action_counts=action_counts,
                accounting=costs,
                **observations)


def diagnostic(directory):
    """Best-effort observations after failure; never manufacture missing costs."""
    value = {"snapshot": None, "accounting": None, "effects": None}
    try:
        Session, *_ = runtime()
        snapshot = Session(Path(directory) / "session.sqlite", clock=lambda: 200).snapshot()
        value["snapshot"] = snapshot
        value["accounting"] = accounting(snapshot)
    except Exception as error:
        value["snapshot_error"] = f"{type(error).__name__}: {error}"
    try:
        value["effects"] = effects(directory)
    except Exception as error:
        value["effects_error"] = f"{type(error).__name__}: {error}"
    return value


def operation(name, directory):
    Session, _, _, Lease, LeaseLost, _ = runtime()
    session = Session(Path(directory) / "session.sqlite", clock=lambda: 100)
    if name == "cancel":
        session.cancel()
        return {"committed": "cancel"}
    if name == "dispatch":
        try:
            dispatch(session, Lease("inspect", 1, "a", 1))
        except LeaseLost as error:
            return {"refused": str(error)}
        response = reply(directory)
        save(Path(directory) / "delayed-response.json", response)
        return {"committed": "dispatch", "effect_executed": True}
    raise ValueError("undeclared child operation")


def child_operation(name, directory):
    process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--operation", name,
                              "--case-directory", str(directory)], capture_output=True, text=True,
                             timeout=configuration()["child_timeout_seconds"], check=True)
    return json.loads(process.stdout)


def sequence(case, directory):
    Session, _, BudgetExceeded, Lease, LeaseLost, StateError = runtime()
    group, variant = case.split(":")
    session = new_session(directory, mailbox_bytes=1 if case == "mailbox:bytes" else None)
    refusals, observations, auxiliary, before = [], [], [], session.snapshot()
    if group == "mailbox" or case == "corrupted_signal:default" or variant in ("unknown_reference", "foreign_reference"):
        _, _, reference = completed_inspection(session, directory)
        if variant == "foreign_reference":
            foreign = new_session(directory, name="foreign")
            _, _, reference = completed_inspection(foreign, directory, call_id="foreign-one")
            auxiliary.append(result(directory, foreign))
        if variant == "unknown_reference" or group == "corrupted_signal":
            reference = "sha256:" + "0" * 64
        if group != "mailbox":
            refusals.append(refused(StateError, lambda: session.send("a", "b", reference)))
        elif variant == "bytes":
            refusals.append(refused(BudgetExceeded, lambda: session.send("a", "b", reference)))
        elif variant == "reverse":
            second_lease = session.claim("b", "submit")
            reserve(session, second_lease, "two")
            dispatch(session, second_lease, "two")
            second_reply = reply(directory, "two", "submit")
            session.receive("two", second_reply)
            second_ref = publish(session, second_lease, second_reply, "two")
            second_id = session.send("b", "a", second_ref)
            first_id = session.send("a", "a", reference)
            require([m["artifact_ref"] for m in session.mailbox("a")] == [second_ref, reference],
                    "reversed arrival altered artifact references")
            require(len(session.snapshot()["artifacts"]) == 2, "arrival created extra evidence")
            session.ack("a", first_id)
            session.ack("a", second_id)
        else:
            first = session.send("a", "b", reference, ttl_seconds=1)
            if variant == "expiry":
                session.clock = lambda: 101
                require(session.mailbox("b") == [], "expired mailbox entry survived")
            else:
                second = session.send("a", "b", reference, ttl_seconds=1)
                require(len(session.mailbox("b")) == 2 and len(session.snapshot()["artifacts"]) == 1,
                        "duplicate messages created evidence or disappeared")
                if variant == "count":
                    refusals.append(refused(BudgetExceeded, lambda: session.send("a", "b", reference)))
                    session.cancel()
                    require(session.snapshot()["run"]["status"] == "cancelled", "full mailbox blocked cancellation")
                for key in ([second, first] if variant == "reverse" else [first, second]):
                    session.ack("b", key)
                require(session.mailbox("b") == [], "acknowledged message survived")
        session.cancel()
        require(session.snapshot()["run"]["status"] == "cancelled", "mailbox blocked direct cancellation")
        return result(directory, session, before=before, refusals=refusals, auxiliary_sessions=auxiliary)
    lease = session.claim("a", "inspect", lease_seconds=1)
    if group == "cancellation_dispatch_order":
        reserve(session, lease)
        order = ("cancel", "dispatch") if variant == "cancel_first" else ("dispatch", "cancel")
        observations = [child_operation(name, directory) for name in order]
        if variant == "cancel_first":
            require(effects(directory) == [] and session.snapshot()["calls"][0]["state"] == "abandoned", "cancel-first allowed execution")
        else:
            response = json.loads((Path(directory) / "delayed-response.json").read_text())
            require(session.snapshot()["unknown_calls"] == 1, "zero-token unknown was hidden")
            session.receive("one", response)
            refusals.append(refused(LeaseLost, lambda: publish(session, lease, response)))
        require(session.claim("b", "inspect") is None, "cancelled work revived")
        return result(directory, session, before=before, committed_order=observations, refusals=refusals)
    if group == "stale_checkpoint":
        session.checkpoint(lease, {"old_lease": asdict(lease), "proposal": {"value": 999}})
        session = Session(session.path, clock=lambda: 200)
        session.recover()
        current = session.claim("a", "inspect")
        require(current.epoch == 2 and session.context(current)["private"]["old_lease"] == asdict(lease), "compatible checkpoint data lost")
        refusals.append(refused(LeaseLost, lambda: session.checkpoint(lease, {})))
        reserve(session, current)
        refusals.append(refused(LeaseLost, lambda: dispatch(session, lease)))
        session.revoke()
        require(session.claim("a", "inspect") is None, "revoked checkpoint restored authority")
        refusals.append(refused(LeaseLost, lambda: session.context(current)))
        return result(directory, session, before=before, refusals=refusals)
    if group == "transient_store_lock":
        original = sqlite3.connect
        if variant != "reserve":
            reserve(session, lease)
            dispatch(session, lease)
            response = reply(directory)
            if variant == "publish":
                session.receive("one", response)
        before_lock = session.snapshot()
        blocker = original(session.path, isolation_level=None)
        blocker.execute("BEGIN IMMEDIATE")
        def bounded_connect(*args, **kwargs):
            kwargs["timeout"] = configuration()["sqlite_busy_timeout_ms"] / 1000
            return original(*args, **kwargs)
        sqlite3.connect = bounded_connect
        action = (lambda: reserve(session, lease)) if variant == "reserve" else (
            (lambda: session.receive("one", response)) if variant == "receive" else lambda: publish(session, lease, response))
        try:
            refusals.append(refused(sqlite3.OperationalError, action))
        finally:
            sqlite3.connect = original
            blocker.rollback()
            blocker.close()
        require(session.snapshot() == before_lock, "failed transaction changed durable state")
        action()  # Retry only the storage transition, never the effect adapter.
        return result(directory, session, before=before_lock, refusals=refusals)
    model = group in ("receipt_before_commit", "oversized_reply_known_usage", "reordered_duplicate_receipts", "transport") or variant in ("model_as_evidence", "synthetic_provider")
    reserve(session, lease, model=model)
    dispatch(session, lease)
    if group == "adapter_failure":
        if variant == "tool_after_effect":
            reply(directory)
        def failed_adapter():
            raise RuntimeError("declared synthetic adapter failure after dispatch")
        refusals.append(refused(RuntimeError, failed_adapter))
        require(session.snapshot()["unknown_calls"] == 1, "failed adapter dispatch became free")
        session.cancel()
        require(session.snapshot()["unknown_calls"] == 1, "cancel released unknown adapter work")
        return result(directory, session, before=before, refusals=refusals)
    response = reply(directory, model=model, value=True if variant == "boolean_objective" else 1)
    if group == "transport":
        packet = "malformed JSON" if variant == "malformed_reply" else wire(dict(call_id="other", response=response))
        save(Path(directory) / "transport.json", {"raw_packet": packet})
        refusals.append(refused(ValueError, lambda: parse_packet(packet, "one")))
        require(session.snapshot()["unknown_calls"] == 1 and not session.snapshot()["artifacts"], "bad transport settled or published")
        return result(directory, session, before=before, refusals=refusals)
    if group == "oversized_reply_known_usage":
        response["text"] = "x" * 2048
        refusals.append(refused(StateError, lambda: session.receive("one", response)))
        settled = session.snapshot()
        require(settled["actual_tokens"] == 3 and settled["unknown_calls"] == 0, "oversized known usage lost")
        require(settled["calls"][0]["state"] == "response_rejected", "oversized payload retained as usable")
        metadata = json_object(settled["calls"][0]["response"])
        require(metadata["response_digest"] == sha256(wire(response).encode()).hexdigest()
                and metadata["response_bytes"] == len(wire(response).encode())
                and len(settled["calls"][0]["response"].encode()) <= configuration()["runtime_limits"]["artifact_bytes"]
                and "text" not in metadata, "oversized rejection metadata is not bounded or correctly bound")
        refusals.append(refused(StateError, lambda: session.receive("one", response)))
        refusals.append(refused(StateError, lambda: session.receive("one", response | {"text": "conflict"})))
        require(session.snapshot() == settled, "duplicate rejection charged twice")
        from pheroos_runtime.session_driver_v1 import SessionDriver
        refusals.append(refused(ValueError, lambda: SessionDriver(session).replay("one")))
        refusals.append(refused(StateError, lambda: publish(session, lease, response)))
        return result(directory, session, before=before, refusals=refusals)
    if group == "reordered_duplicate_receipts":
        reserve(session, lease, "two", model=True)
        dispatch(session, lease, "two")
        second = reply(directory, "two", model=True)
        for call_id, value in (("two", second), ("one", response)):
            session.receive(call_id, value)
            settled = session.snapshot()
            session.receive(call_id, dict(reversed(list(value.items()))))
            refusals.append(refused(StateError, lambda: session.receive(call_id, value | {"text": "conflict"})))
            require(session.snapshot() == settled, "duplicate/conflicting receipt changed ledger")
        require(session.snapshot()["actual_tokens"] == 6, "reordered costs did not settle exactly once")
        return result(directory, session, before=before, refusals=refusals)
    if group == "stale_lease_publication":
        session.clock = lambda: 200
        session.recover()
        require(session.snapshot()["unknown_calls"] == 1 and session.claim("b", "inspect") is None,
                "expired unresolved dispatch became reclaimable")
    session.receive("one", response)
    if group == "revocation_after_receipt":
        session.revoke()
        session = Session(session.path, clock=lambda: 100)
        require(session.claim("b", "inspect") is None, "revoke allowed implicit regrant")
        refusals.append(refused(LeaseLost, lambda: publish(session, lease, response)))
    elif group == "stale_lease_publication":
        current = session.claim("b", "inspect")
        require(current.epoch == 2, "higher epoch absent")
        refusals.append(refused(LeaseLost, lambda: publish(session, lease, response)))
        refusals.append(refused(LeaseLost, lambda: session.checkpoint(lease, {})))
        publish(session, current, response)
    elif group == "provenance_substitution":
        if variant == "wrong_version":
            refusals.append(refused(LeaseLost, lambda: publish(session, replace(lease, version=2), response)))
        elif variant == "mismatched_artifact":
            refusals.append(refused(StateError, lambda: publish(session, lease, response | {"artifact": response["artifact"] | {"value": 2}})))
        else:
            refusals.append(refused(StateError, lambda: publish(session, lease, response)))
        require(not session.snapshot()["artifacts"], "substituted provenance published")
    elif group == "corrupted_database_copy":
        before = session.snapshot()
        corrupted = Path(directory) / "corrupted.sqlite"
        shutil.copyfile(session.path, corrupted)
        with corrupted.open("r+b") as stream:
            stream.write(b"BROKEN SQLITE HEADER")
            stream.flush()
            os.fsync(stream.fileno())
        damaged = Session(corrupted, clock=lambda: 100)
        refusals.append(refused(sqlite3.DatabaseError, damaged.snapshot))
        refusals.append(refused(sqlite3.DatabaseError, lambda: damaged.claim("a", "inspect")))
        return result(directory, None, before=before, runtime_disposition="ABORT_UNAVAILABLE",
                      intact_original_retained=True, refusals=refusals)
    else:
        raise ValueError("undeclared sequence case")
    return result(directory, session, before=before, refusals=refusals)


def execute_case(case, directory, runtime_python, runtime_site):
    """One temporary harness test or one declared study case; no implicit study."""
    if case not in CASES or os.name != "posix":
        raise ValueError("declared case and POSIX process semantics required")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    config = configuration()
    environment = dict(os.environ, PYTHONPATH=str(Path(runtime_site).resolve()), PYTHONDONTWRITEBYTECODE="1")
    command = [str(Path(runtime_python).resolve()), str(Path(__file__).resolve())]
    base = ["--case-directory", str(directory)]
    started = time.monotonic_ns()
    row = dict(method_version=METHOD, case=case, counts_toward_verdict=False, status="INVALID_ABORT")
    try:
        group, variant = case.split(":")
        if group in CRASH_GROUPS or case in ("transport:lost_reply", "transport:delayed_reply"):
            read_fd, write_fd = os.pipe()
            process = subprocess.Popen(command + ["--crash-worker", case, "--control-fd", str(write_fd)] + base,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
                pass_fds=(write_fd,))
            os.close(write_fd)
            try:
                with selectors.DefaultSelector() as ready:
                    ready.register(read_fd, selectors.EVENT_READ)
                    require(bool(ready.select(config["boundary_timeout_seconds"])), "boundary marker timeout")
                    marker = os.read(read_fd, 4096)
                require(json.loads(marker) == {"boundary": case, "stage": BOUNDARIES[group], "pid": process.pid}, "wrong boundary marker")
                if case == "transport:delayed_reply":
                    subprocess.run(command + ["--operation", "cancel"] + base, env=environment,
                                   capture_output=True, timeout=config["child_timeout_seconds"], check=True)
                    stdout, stderr = process.communicate(b"release\n", timeout=config["child_timeout_seconds"])
                    require(process.returncode == 0, "delayed child failed")
                    save(directory / "delayed-packet.json", {"raw_packet": stdout.decode()})
                else:
                    if case == "transport:lost_reply":
                        with selectors.DefaultSelector() as transport:
                            transport.register(process.stdout, selectors.EVENT_READ)
                            require(not transport.select(config["reply_timeout_ms"] / 1000), "reply arrived before injected timeout")
                        require(process.poll() is None, "worker exited instead of timing out")
                        row["transport_timeout_observed"] = True
                    process.kill()
                    stdout, stderr = process.communicate(timeout=5)
                    require(process.returncode == -signal.SIGKILL and stdout == b"", "SIGKILL or missing-ack oracle failed")
                row.update(boundary=json.loads(marker), worker_exitcode=process.returncode,
                           acknowledgment_received=bool(stdout), actual_sigkill=case != "transport:delayed_reply")
                save(directory / "worker-transport.json", dict(stdout=stdout.decode(), stderr=stderr.decode()))
            finally:
                os.close(read_fd)
                if process.poll() is None:
                    process.kill()
                remaining_out, remaining_err = process.communicate(timeout=5)
                row.setdefault("worker_exitcode", process.returncode)
                if not (directory / "worker-transport.json").exists():
                    save(directory / "worker-transport.json", dict(stdout=remaining_out.decode(), stderr=remaining_err.decode()))
            mode = "--inspect-crash"
        else:
            mode = "--sequence"
        child = subprocess.run(command + [mode, case] + base, env=environment, capture_output=True,
                               text=True, timeout=config["child_timeout_seconds"], check=True)
        require(len(child.stdout.encode()) <= config["max_child_output_bytes"], "child output exceeds bound")
        row.update(json.loads(child.stdout))
        save(directory / "inspector-transport.json", dict(stdout=child.stdout, stderr=child.stderr))
    except Exception as error:
        row.update(status="INVALID_ABORT", error=f"{type(error).__name__}: {error}")
        if isinstance(error, subprocess.CalledProcessError):
            row.update(child_stdout=str(error.stdout), child_stderr=str(error.stderr))
        try:
            recovery = subprocess.run(command + ["--diagnostic"] + base, env=environment,
                capture_output=True, text=True, timeout=config["child_timeout_seconds"], check=True)
            row.update(json.loads(recovery.stdout))
        except Exception as unavailable:
            row.update(accounting=None, diagnostic_error=f"{type(unavailable).__name__}: {unavailable}")
    row["elapsed_ns"] = time.monotonic_ns() - started
    try:
        save(directory / "case.json", row)
    except Exception as error:
        row.update(status="INVALID_ABORT", persistence_error=f"{type(error).__name__}: {error}")
    return row


def validate_outcomes(rows):
    if type(rows) is not list or len(rows) != len(CASES):
        raise ValueError("incomplete fault matrix")
    for expected, row in zip(CASES, rows):
        if (type(row) is not dict or row.get("case") != expected or row.get("method_version") != METHOD
                or row.get("counts_toward_verdict") is not False or row.get("status") not in ("PASS", "FAIL", "INVALID_ABORT")):
            raise ValueError("invalid, missing, duplicate or misidentified fault result")


def study(config_path, output, runtime_python, runtime_site):
    config_path, output = Path(config_path).resolve(), Path(output).resolve()
    if wire(json.loads(config_path.read_text())) != wire(configuration()):
        raise ValueError("configuration differs from declared fault study")
    command = [str(Path(runtime_python).resolve()), str(Path(__file__).resolve()), "--probe", str(Path(runtime_site).resolve())]
    environment = dict(os.environ, PYTHONPATH=str(Path(runtime_site).resolve()), PYTHONDONTWRITEBYTECODE="1")
    def identity():
        return json.loads(subprocess.run(command, env=environment, capture_output=True, text=True,
                                        timeout=20, check=True).stdout)
    before = identity()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    files = [Path(__file__).resolve(), config_path, root / "R5-session-faults-v1-contract.md", root / "tests/test_r5_session_faults.py"]
    hashes, rows, finalization_errors = {}, [], []
    try:
        hashes = {str(p): sha256(p.read_bytes()).hexdigest() for p in files}
        save(output / "freeze.json", dict(method_version=METHOD, configuration=configuration(),
             installed=before, source_sha256=hashes, counts_toward_verdict=False, frozen_before_cases=True))
    except Exception as error:
        finalization_errors.append(f"freeze failed: {type(error).__name__}: {error}")
    halted = bool(finalization_errors)
    for index, case in enumerate(CASES):
        directory = output / "cases" / f"{index:02d}-{case.replace(':', '-')}"
        try:
            if halted:
                raise RuntimeError("not attempted after earlier harness failure")
            row = execute_case(case, directory, runtime_python, runtime_site)
            if (type(row) is not dict or row.get("case") != case or row.get("method_version") != METHOD
                    or row.get("counts_toward_verdict") is not False or row.get("status") not in ("PASS", "FAIL", "INVALID_ABORT")):
                reported = row
                row = dict(method_version=METHOD, case=case, counts_toward_verdict=False, status="INVALID_ABORT",
                           error="returned case identity or status is invalid", reported_row=reported, accounting=None)
                halted = True
        except Exception as error:
            row = dict(method_version=METHOD, case=case, counts_toward_verdict=False, status="INVALID_ABORT",
                       error=f"{type(error).__name__}: {error}", accounting=None, attempted=not halted)
            if not halted and directory.exists():
                try:
                    recovered = subprocess.run([str(Path(runtime_python).resolve()), str(Path(__file__).resolve()),
                        "--diagnostic", "--case-directory", str(directory)], env=environment,
                        capture_output=True, text=True, timeout=20, check=True)
                    row.update(json.loads(recovered.stdout))
                except Exception as missing:
                    row["diagnostic_error"] = f"{type(missing).__name__}: {missing}"
            halted = True
        rows.append(row)
        print(wire({"case": case, "status": row["status"]}), flush=True)
    try:
        validate_outcomes(rows)
        unchanged = not finalization_errors and identity() == before and all(sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in hashes.items())
    except Exception as error:
        unchanged = False
        finalization_errors.append(f"{type(error).__name__}: {error}")
    try:
        save(output / "outcomes.json", rows)
    except Exception as error:
        unchanged = False
        finalization_errors.append(f"outcomes persistence failed: {type(error).__name__}: {error}")
    summary = dict(method_version=METHOD, counts_toward_verdict=False, cases=len(rows),
        outcomes={status: sum(row["status"] == status for row in rows) for status in ("PASS", "FAIL", "INVALID_ABORT")},
        source_unchanged=unchanged, gpu_calls=0, paid_provider_calls=0, finalization_errors=finalization_errors,
        source_accounting=[dict(case=row["case"], status=row["status"], accounting=row.get("accounting")) for row in rows],
        status="INVALID_ABORT" if not unchanged or any(r["status"] == "INVALID_ABORT" for r in rows)
        else "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS",
        limits="finite single-host Session acceptance; no soak, production or arbitrary exactly-once claim")
    try:
        save(output / "summary.json", summary)
    except Exception as error:
        summary["status"] = "INVALID_ABORT"
        summary["finalization_errors"].append(f"summary persistence failed: {type(error).__name__}: {error}")
    print(wire(summary), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-python", "runtime-site", "config", "output", "case-directory"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--probe", type=Path, help=argparse.SUPPRESS)
    for name in ("crash-worker", "inspect-crash", "sequence"):
        parser.add_argument("--" + name, choices=CASES, help=argparse.SUPPRESS)
    parser.add_argument("--operation", choices=("cancel", "dispatch"), help=argparse.SUPPRESS)
    parser.add_argument("--control-fd", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--diagnostic", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        print(wire(probe(args.probe)))
    elif args.crash_worker:
        crash_worker(args.crash_worker, args.case_directory, args.control_fd)
    elif args.operation:
        print(wire(operation(args.operation, args.case_directory)))
    elif args.diagnostic:
        print(wire(diagnostic(args.case_directory)))
    elif args.inspect_crash or args.sequence:
        sequence_started = time.monotonic_ns()
        try:
            if args.inspect_crash:
                packet = args.case_directory / "delayed-packet.json"
                observed = inspect_crash(args.inspect_crash, args.case_directory,
                    json.loads(packet.read_text())["raw_packet"] if packet.exists() else None)
            else:
                observed = sequence(args.sequence, args.case_directory)
            value = dict(status="PASS", **observed)
        except AssertionError as error:
            value = dict(status="FAIL", error=str(error), **diagnostic(args.case_directory))
        except Exception as error:
            value = dict(status="INVALID_ABORT", error=f"{type(error).__name__}: {error}", **diagnostic(args.case_directory))
        value["inspection_sequence_elapsed_ns"] = time.monotonic_ns() - sequence_started
        print(wire(value))
    else:
        if not all((args.runtime_python, args.runtime_site, args.config, args.output)):
            parser.error("--runtime-python, --runtime-site, --config and --output required; prior G5/R4 gates required")
        return 0 if study(args.config, args.output, args.runtime_python, args.runtime_site)["status"] == "PASS" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
