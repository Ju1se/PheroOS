# Experimental installed Session fault study v1

Method: `r5_session_faults_v1`. Status: **IMPLEMENTED, STUDY NOT EXECUTED OR FROZEN**.
The G5 capability and R4 scaling
gates must be reviewed before this study runs. Preparing a harness or passing
its tests does not supply R5 study evidence. This plan does not authorize a
soak or change the frozen Session implementation.

The starting matrix is
`/tmp/pheroos-os-runtime-v1/validation/r5-session-matrix-proposal.json`:
14 case groups, 28 declared variants. The five historical
`r5-runtime-faults-v1` cases used PilotLedger and cannot establish Session
lease, permission, checkpoint, mailbox or publication behavior. Preserve those
sources, ledgers, results and hashes unchanged.

## Concrete question and consumer

Can the installed Session retain cost uncertainty and fence stale execution
across selected process, transport and store faults in the existing two-agent
inspect → verified artifact reference → submit journey?

Use one fixed two-agent declaration, the installed Session/SessionDriver,
current public-core authorization, bounded context/mailbox limits and a local
deterministic evaluator. No model download, GPU inference or paid provider is
needed. Synthetic model reservations are labeled as such: prompt 2, maximum
8, received completion 1. Tool calls reserve zero tokens, while unresolved tool
dispatches must still report `unknown_calls=1`.

## Harness implementation

The bench-owned `tools/r5_session_faults.py`, config and tests
do not modify or monkeypatch a stored runtime file. Runtime injection exists
only in the selected child process, and the exact injected boundary is recorded.

The parent launches the explicitly selected interpreter with an explicitly
installed runtime target. Before execution it records source, installed
runtime/core, interpreter, config, harness and task hashes. Imports must resolve
to that target. Each case gets an exclusive directory, Session database,
effect-counter database, child logs and result. Check the closure again after
execution. A harness test uses temporary output and is not copied into the
study's result directory.

Use a dedicated control pipe for a bounded JSON boundary marker, distinct from
model/tool response transport. The parent waits with a finite selector timeout,
checks the exact marker, sends real SIGKILL, verifies exit `-SIGKILL` and absence
of an acknowledgment, then launches a fresh inspector process. A missing or
wrong marker invalidates the case; it is not evidence that the runtime recovered.
Do not treat an in-process exception as a process-crash experiment.

For precommit interruption, a child-only connection proxy intercepts the
selected Session transaction's commit after the receipt UPDATE. It delegates
all other operations to the actual SQLite connection. Record the selected SQL
transition and marker before killing. For contention, another real connection
holds a write lock; a child-only bounded busy timeout gives a reproducible
transaction failure. Retrying reserve/receive/publication may retry that storage
operation after the lock clears; it must not call the model/tool adapter again.

The deterministic effect adapter appends one sidecar row per invocation with
logical call ID, work/version, input digest and output digest. It intentionally
does not suppress duplicate call IDs: a repeated adapter execution would produce
a second row and fail the oracle. This bounded local effect is an observable
stand-in, not a claim about exactly-once behavior of arbitrary external APIs.
The Session ledger remains the only token-accounting owner.

Reopen both Session and effect logs in a fresh process. Export before/after
snapshots, all call states and known/reserved/unknown token components,
`unknown_calls`, action counts, artifact bindings, scope/version/permission
lineage, effect invocations and canonical Trace events. Record recovery attempts,
elapsed recovery time and whether recovery completed or correctly remained
uncertain. No missing counter is replaced with zero.

## Fixed matrix

Retain all 28 proposed variants:

- SIGKILL after reserve or dispatch, each with a zero-token tool and synthetic
  10-token model reservation.
- SIGKILL before receipt commit, after receipt commit before acknowledgment,
  and after publication commit before acknowledgment.
- Coordinator restart after checkpoint and verified-reference mailbox send.
- Transient store locks during reserve, receive and publication.
- Both committed orders of cancellation versus dispatch, including late receipt.
- Revocation after receipt and stale-lease publication after reconciliation.
- Reversed receipt settlement, exact duplicates and conflicting duplicates.
- Mailbox duplicate references, reversed arrival, count limit, byte limit and
  expiry, with cancellation bypassing saturated mailboxes.
- Unknown/foreign references, wrong work version, mismatched artifact,
  model-receipt publication and boolean-as-integer objective substitution.
- Oversized response with known actual usage, bounded rejection metadata and
  no usable replay/publication.

The fixed configuration adds ten variants, for **38 cases**, covering these
additional fault surfaces:

| Addition | Injection and independent oracle |
| --- | --- |
| Delayed response | Hold a child reply until cancellation commits; settle its known usage without publication or revival. |
| Response timeout/loss | Observe no transport reply for 50 ms after the sidecar effect commits, then kill the still-live child; no redispatch, one effect, unresolved accounting remains explicit. |
| Malformed transport/correlation | Deliver malformed JSON or another call's ID; reject before settlement, retain the original unknown dispatch, create no artifact. |
| Tool failure | Raise after durable dispatch, both before and after the bounded effect; sidecar distinguishes zero versus one invocation. |
| Synthetic provider failure | Raise from the replaceable model adapter after dispatch; retained 10-token reservation is unknown, not an assumed zero charge. |
| Stale checkpoint | Restart/reclaim or revoke, then try the saved old lease/permission data; checkpoint contents cannot execute or restore authority. |
| Corrupted signal/proposal | Alter an artifact reference or the proposed objective while preserving well-formed transport; immutable artifact lookup or the independent evaluator rejects it. |
| Corrupted database copy | Corrupt a disposable copy after a known boundary; read/dispatch failure remains an explicit abort with unavailable ledger totals. Retain the intact original and sidecar; do not claim reconstruction or power-loss durability. |

A dropped response, malformed transport and a provider exception are different
observations. Keep them distinct rather than assigning all three to a generic
crash label. State separately which injected failures involve real processes,
real SQLite behavior, caller-level substitution or a synthetic adapter.

The two cancel/dispatch orders use separate real processes and observed committed
ordering. SQLite contention uses a second real connection. Malformed/correlation
packets and failing provider/tool callbacks are deterministic harness adapters;
they do not establish GPU or production-provider transport robustness. Repeated
source acknowledgments and references are not independent evidence. The mailbox
arrival case delivers two already verified artifacts in reverse publication order.

After the required gate review, the explicit study command is:

```text
python tools/r5_session_faults.py --runtime-python /path/to/python --runtime-site /path/to/installed-target --config r5-session-faults-v1.json --output results/r5-session-faults-v1
```

The output directory must not already exist. The command freezes inputs before
cases and checks them afterward. The prerequisite is a root-reviewed execution
decision, not an inferred permission from this file. Harness tests create only
temporary case directories and never invoke the study entrypoint.

## Result classification and next gate

`PASS` means the declared invariant was observed for that exact case and
injection boundary. `FAIL` means a witnessed violation, such as a second effect,
stale publication, resurrected cancellation, or incorrect known/unknown charge.
`INVALID_ABORT` means the injection, trace, identity or oracle observation was
insufficient. Preserve the runtime's own completed/cancelled/uncertain/aborted
disposition separately; a safely unresolved dispatch is not successful recovery.

Require one result for every predeclared case/variant, retain all failures and
aborts, and reject incomplete matrices. No retry or altered injection after
observing an outcome can silently replace a result. This is finite engineering
acceptance without policy comparisons, confidence intervals or independent
efficacy evidence.

Session bounds retained mailbox entries and bytes, checkpoints, and this
declared finite work/call sequence. Repeated trusted checkpoint/send/ack calls
can still append additional Trace events: the runtime does not currently bound
long-run event-log growth by work/call count. This study supplies neither a
production log-retention guarantee nor evidence of long-run memory boundedness.

These cases do not establish multi-host failover, physical power-loss durability,
GPU-driver recovery, hostile-host authentication, arbitrary external-effect
exactly-once execution or long-run reliability. Any 8-hour and then 24-hour soak
requires a separate runtime-maturity review, frozen workloads, interruption and
accounting rules, and its own execution decision.
