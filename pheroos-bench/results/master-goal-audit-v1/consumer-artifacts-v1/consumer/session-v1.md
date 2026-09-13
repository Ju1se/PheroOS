# Experimental session v1

`pheroos_runtime.session_v1.Session` is a staged, single-host execution slice
for a concrete inspector → verified artifact reference → submitter journey.
It uses a new SQLite schema and the installed public PheroOS contracts. It
does not migrate G1 stores or the separate legacy `PilotLedger`; those remain
available for compatibility and reproduction. No session call is charged to
two ledgers. This module imports no provider, model or numerical package.

The trusted caller declares agents, work IDs/versions, dependency IDs, eligible
agents and allowed `model.generate`/`tool.evaluate` actions before creation.
Declarations must form a DAG. One verified artifact completes each work item.
The database and trusted authority/verifier callbacks are the host boundary;
agent messages and model outputs cannot issue authority or create artifacts.

```python
from pheroos_runtime.session_v1 import Session
from pheroos_runtime.session_driver_v1 import SessionDriver, current_authorization

session = Session.create(
    "new-session.sqlite", "inspect-submit",
    agents=["inspector", "submitter"],
    work=[
        {"id": "inspect", "version": 1, "dependencies": [],
         "agents": ["inspector"], "actions": ["tool.evaluate"]},
        {"id": "submit", "version": 1, "dependencies": ["inspect"],
         "agents": ["submitter"], "actions": ["tool.evaluate"]},
    ],
    token_cap=0, max_calls=2,
)
driver = SessionDriver(session, tools={"inspect": lambda _: {"evidence": 4}})
lease = session.claim("inspector", "inspect")
reply = driver.evaluate(lease, "inspect-call", "inspect", {})
ref = session.publish(
    lease, "inspect-call", reply["artifact"],
    verify=lambda task, value: task == "inspect" and value == {"evidence": 4},
    authorize=current_authorization,
)
message_id = session.send("inspector", "submitter", ref)
next_lease = session.claim("submitter", "submit")
assert session.context(next_lease)["artifact_refs"] == [ref]
assert session.artifact(ref)["value"] == {"evidence": 4}
session.ack("submitter", message_id)
```

`Session(path)` reopens an existing session. `claim` returns the existing
`Lease` dataclass; an ineligible agent, unfinished dependency or uncertain
dispatch cannot be bypassed with mailbox data. `checkpoint(lease, dict)` keeps
one private checkpoint per declared agent. `context(lease)` checks current
work/version/permission and returns only that agent's compatible checkpoint
and dependency artifact references. A recovered lease may reuse compatible
checkpoint data; the old lease itself remains fenced. Restored data is never
an executable permission.

`reserve(lease, call_id, action, payload, prompt_tokens=..., max_new_tokens=...)`
atomically binds the declared action, work/version, current lease and current
permission generation to the reservation. Caller-supplied task/version fields
must match; otherwise Session adds them. Calls count against `max_calls` even
when zero tokens are used. Nonnegative token quantities must be exact integers.
`dispatch(lease, call_id, authorize)` invokes current authorization while its
SQLite transaction serializes dispatch with cancellation/revocation. The
callback must return matching public Baseline Output v2 audit evidence with
`reusable_authority=False`; a cached root or an `authorized=True` dictionary
is not the callback contract. Session checks lease expiry again after the
callback. Trusted callbacks must actually perform the current public-core
check and must not recursively acquire this execution database.

The caller/driver executes the model or tool after dispatch commits, outside
the transaction, then calls `receive`. Committed dispatch can continue after
cancellation; remote work/charging cannot be undone. An exception without
valid usage leaves the entire reservation unresolved. There is no automatic
retry of a dispatched call. `call(id)` exposes committed receipt data after
restart without executing, authorizing or charging again. The driver provides
explicit replay only for accepted, settled receipts.

`receive(id, response)` requires the reserved prompt-token count and a
completion count no greater than the reserved maximum. Valid late usage
settles even after lease expiry, cancellation or revocation. Exact repeated
receipts are idempotent; different payload/usage cannot change a settled call.
A response exceeding the payload byte limit has its valid usage committed,
but stores only a bounded diagnostic containing its digest, byte count and
usage under `state="response_rejected"`. Session then raises a rejection
error. Repeating that rejected receipt preserves the same charge and error;
its payload cannot be replayed or published. Missing/malformed usage remains
unknown. Token-zero tool calls still expose `unknown_calls` while unresolved.

`publish(lease, call_id, artifact, verify=..., authorize=...)` requires a
settled `tool.evaluate` receipt on the current work/version whose `artifact`
exactly matches the proposed bytes. The independent verifier must return
exactly `True`, and current public-core publication authorization is mandatory.
A model response containing an `artifact` field is still a proposal and cannot
publish. Immutable artifact identity binds scope, work/version, call ID,
response digest and value; its record retains publisher and authority evidence.
Publication releases other never-dispatched reservations for that work and
retains any truly dispatched unknown calls. Completed work does not imply
fully known accounting when such calls remain; inspect both status and costs.

`recover` and `claim` detect expired leases. Never-dispatched reservations are
released; known receipts can be reused. Unresolved dispatched work becomes
`uncertain`, retaining its token reservation until valid usage arrives. A late
receipt can make uncertain work eligible for a new, higher lease epoch; it
cannot revive cancelled/revoked work. `cancel()` and `revoke()` bypass mailboxes,
disable further permission, increment its generation, fence old leases and
release only unspent reservations. Revocation is terminal in this slice:
claiming again cannot recreate a grant; there is no implicit regrant API.

Default limits are 4,096 bytes for each request and materialized private
context, 8,192 bytes for each response/artifact payload, and 16 messages/4,096
serialized message bytes per recipient. Rejection diagnostics have fixed
metadata overhead outside the rejected payload limit. Artifacts are bounded
by declared work count, calls by `max_calls`, and checkpoints by agent count.
These are logical JSON byte limits, not physical SQLite-file size guarantees.
Input returned by a trusted adapter necessarily exists before its receipt is
validated. Context overflow is explicit; critical dependency references are
not silently truncated.

`send(sender, recipient, artifact_ref, ttl_seconds=...)` accepts only references
to artifacts verified in this session and published by that sender. `mailbox`
returns addressed, unexpired references; `ack` removes only that recipient's
message. Expiry frees capacity at the boundary, and both expiry and acknowledgment
are observable. Repeated messages do not create new evidence, independence or
authority. Mailbox byte accounting covers the serialized message envelope
including message ID and expiry, excluding its byte-count diagnostic itself.

All durable transitions emit canonical `pheroos.trace.TraceEvent` records,
including reservation, dispatch, settlement/rejection, lease expiry,
reconciliation, publication, reservation abandonment and direct controls.
Snapshots expose those events, work/calls/artifacts, actual/reserved/unknown
tokens and unknown call count. Traces and artifact history are append-only
and bounded only by the finite declared work/call run, not a daemon log policy.

Validation includes a deterministic two-agent journey, current authorization,
lease/cancel/revoke fencing, known receipt reuse, bounded context/mailboxes,
wrong-source messages, proposal/evidence separation, accounting rejection
counterexamples and a real subprocess SIGKILL immediately after durable
dispatch. It exercises no GPU. The optional `clock` callable exists for
deterministic boundary tests; normal sessions use wall time, so host clock
changes can delay expiry or fence early.

This is not a production guarantee, arbitrary side-effect executor, general
exactly-once guarantee, multi-host store, complete authority custody system,
or completed R5/long-soak acceptance. Only pure/tool-verifiable actions are
within this slice. Backups, host power loss, database corruption and hostile
host substitution remain outside its guarantees. The next acceptance step is
the independent installed consumer journey and explicit runtime fault matrix.
