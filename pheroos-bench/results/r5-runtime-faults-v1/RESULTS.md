# R5 local fault acceptance v1

**PASS for these five cases; R5 as a whole and G5 remain incomplete.**
The frozen run on 2026-09-12 exercised the installed external runtime on
WSL2 / Python 3.12.3. It made no GPU, paid-model or network calls. The script,
configuration and all eight installed runtime Python modules were hashed in
`freeze.json` before fault execution; the runtime hashes were unchanged after
execution. No production runtime source or earlier experiment was modified.

This is a separate engineering fault method, not an R3 quality experiment.
Fake inference reports two prompt tokens and one completion token against a
ten-token reservation. Those values test accounting arithmetic; they do not
represent actual model consumption.

| Case | Injection and observed result |
| --- | --- |
| Before receipt | Actual `r3_local.handle` generated its fake response; SIGKILL immediately before `PilotLedger.received`. Fresh-process reopening found one dispatched call, no response, actual 0 and unknown 10. |
| Receipt before commit | A child-only connection wrapper paused `commit` after the receipt UPDATE, before SQLite committed. SIGKILL rolled that transaction back: one dispatched call, no response, actual 0 and unknown 10 after reopening. |
| Receipt committed before acknowledgment | SIGKILL after actual `handle` returned and closed its ledger, before the test JSONL driver could emit its response. Reopening recovered the committed response, actual 3 and unknown 0. Repeating the identical receipt made no change. |
| Reordered receipts | Reserved and dispatched calls `one`, then `two`; settled `two`, then `one`. Actual/unknown moved 0/20 → 3/10 → 6/0. Exact duplicate receipts were idempotent; conflicting response text was rejected without changing either call. |
| Temporary SQLite writer lock | Another connection held `BEGIN IMMEDIATE`. With a test-only 100 ms busy timeout, reserve and receive each refused with `database is locked`. Failed reserve created no call; failed receive retained actual 0 / unknown 10. Releasing the lock allowed settlement to actual 3 / unknown 0, with only one call. |

All three killed children exited **-9 (`SIGKILL`)** and emitted **no stdout
acknowledgment**. The parent waited for a dedicated stderr boundary marker,
used a bounded wait and cleaned up any surviving child on failure. Each crash
case was inspected by another newly started process. Redispatching the call
or reserving its ID again was rejected in all three cases; the unknown cases
also refused another call that would exceed their retained budget.

`summary.json` records 5/5 PASS. The five named case JSON files retain
boundary stderr, process exit status, refusal messages and portable ledger
snapshots; the two sequence cases also retain intermediate snapshots.
The SQLite databases remain local evidence. `artifact-hashes.json` records
portable artifact hashes separately from local SQLite hashes.

## Scope and remaining gaps

The crash cases use the installed R3 handler and its actual public-core
authorization with fake inference. The test substitutes a ledger subclass
only to select a crash boundary; it does not edit installed source. The last
case pauses a test JSONL driver after `handle`, rather than loading the GPU
model through the production command's `main`. It verifies ledger durability
and absence of an acknowledgment, not GPU-driver recovery.

The writer-lock case tests temporary transaction acquisition failure, not
disk-full, I/O or commit failure, power loss, corruption or storage failover.
The reorder case covers two trusted local calls, not a distributed message
transport, source authentication or adversarial receipt substitution.

G1 separately has prior tests for lease expiry, cancellation, late receipts
and process death at four durable boundaries. R3 does not acquire those G1
lifecycle guarantees automatically: it has no in-flight cancellation or lease
recovery SDK. A committed result is readable from its ledger, but resubmitting
the same `generate` request is refused rather than transparently returning it.
Unknown dispatches require reconciliation and are never retried automatically.

Coordinator death/restart, untrusted source pollution, real GPU termination,
multiple hosts and arbitrary external side effects remain unverified here.
There is no general exactly-once-effects claim, policy comparison or change to
the default scheduler. G5 still requires its remaining fault matrix, explicit
backend guarantees and recoverable consumer lifecycle.

## Reproduce

Run from `pheroos-bench`, selecting an explicit external interpreter and a new
output directory. The installed runtime must match `freeze.json` for exact
replication; output directories cannot be overwritten.

```bash
python tools/r5_runtime_faults.py \
  --runtime-python /home/scott/projects/PheroOS-runtime/.local/venv312/bin/python \
  --config r5-runtime-faults-v1.json \
  --output results/r5-runtime-faults-v1-replication
```
