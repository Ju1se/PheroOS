# Full-grid R4 replication campaign v1

Method `r4_full_grid_replication_v1` owns this new campaign only. The inner
method remains `r4_session_scaling_pilot_v1`, with byte-identical runner,
configuration, task fixtures, policies, evaluator, runtime and model identities.
This contract prepares one attempt; it does not itself launch a model study.

## Reason and preserved evidence

The original 264-row campaign ended `INVALID_ABORT`: 204 complete episodes,
one interrupted episode and 59 unstarted placeholders. At step 7 of
`fixed_tokens-small-private-n1` / `evidence_revision/ready_window`, the model
receipt settled but a new tool reservation encountered `LeaseLost`. That
episode retains 4,248 known tokens, eight model calls and seven tool calls,
with no unknown spend or eighth tool execution/publication.

The failed episode reports 22.333854420 monotonic seconds, while the adjacent
episode file timestamps are 07:58:19.185279 and 17:14:43.407305 UTC. Session
leases use realtime; the runner measures duration and deadline with monotonic
time. This supports a clock-discontinuity or environmental-interruption
hypothesis. It does not prove suspend: per-event wall times and the expired
lease timestamp were not retained after cancellation. Denying new work after
expiry while settling the known receipt is consistent with the runtime contract.

The original freeze, config, episode stream, terminal summary, order, model-load
log and failed row are pinned by the new config. They remain unchanged and
invalid under the original whole-grid rule. No successful subset is relabeled
as a usable full grid, no failed row is replaced, and no historical cost is
discarded. Original source-accounting rows, including missing/null values,
are retained in the campaign report.

Preflight additionally requires the separately pinned independent abort audit:
`r4_session_scaling_abort_audit_v1` with
`ACCOUNTING_AND_ABORT_INTEGRITY_PASS`, source `INVALID_ABORT`, and
`FULL_GRID_INVALID_NO_USABLE_PAIRED_EXPORT`. Its config, retained accounting,
original evidence hashes and pilot/unchanged flags must match. A pending,
failed, partial, foreign or unpinned audit cannot launch the runner. Until the
full audit completes, the campaign config deliberately has no audit file hash.

## One unchanged full-grid attempt

`tools/run_scaling_replication.py` calls the original `runner.run` once, using
the original config path, original model paths and a fresh `collection/`
directory beneath `results/r4-session-scaling-replication-v1`. All 66 conditions
cross all four worlds in the original seeded order. Each episode creates a new
Session database. No original receipt, checkpoint, outcome or database supplies
work to the replication. No automatic retry follows another abort.

The wrapper requires exact equality between the original freeze and a newly
computed inner freeze before launch and after completion. That includes the
original interpreter/Python build, package identities, source closure and
fully hashed model manifests/files. The new wrapper, campaign config, contract
and `tests/test_scaling_replication.py` are frozen separately. The new test name
deliberately does not enter the original `test_r4_*.py` source glob.

Hypotheses, thresholds, tasks, policies, budgets, leases, cancellation behavior,
deadline handling, generation seeds and inner measurement mapping do not change.
This replication is selected because the original whole-grid attempt aborted,
not because a quality endpoint crossed an unfavorable threshold. It remains
exploratory; repeating the same four worlds does not create four new independent
worlds or additional confirmatory evidence. Reports must retain both campaigns
and their costs. The wrapper produces no paired efficacy export.

## Bounded clock observations

A diagnostic thread samples realtime, UTC, monotonic and, where available,
Linux boottime at startup, every five seconds and at finish. At most 20,000
samples are retained, including startup/finish. A stop event interrupts its
wait and cleanup joins it with a two-second bound. Sampling failure, exhaustion
or failed join is an explicit campaign error; the known collection and costs
remain available. There is no daemon service beyond this process.

The observer records interval differences without classifying them using a new
threshold. It never changes a clock, lease, deadline, authority, task action or
the runner's error handling, and never reissues an execution. Its thread and
small periodic file writes are extra host activity shared across conditions;
they are recorded campaign overhead, not zero-cost work or an isolated timing
benchmark. Observation does not prevent suspend or establish its cause. Failure
to collect diagnostics cannot silently produce a successful campaign label.
Sample count, serialized bytes and outer realtime/monotonic/boottime durations
are reported as separate campaign control overhead. They are not inserted into
the unchanged episode `call_units` and are not GPU-time or monetary estimates.

## Accounting, finalization and next gate

The outer report preserves the original and replication `source_accounting`
separately. A cross-attempt known subtotal sums only exact nonnegative counters
actually reported; missing rows/campaigns remain explicit. A partial subtotal
is not a complete total, a missing value is not zero, and original tokens are
not charged to the new Session ledger. Monetary cost remains null.

The original runner retains responsibility for raw episode/receipt accounting
and explicit interrupted/unstarted rows. The wrapper retains exceptions,
cleanup failures, source drift and unavailable summaries as `INVALID_ABORT`.
If the inner summary cannot be saved, reported counters from available raw
episode lines are retained diagnostically; malformed/unexported rows stay
missing. This recovery does not validate or repair a grid.
Successful collection is labeled
`REPLICATION_COLLECTED_PENDING_INDEPENDENT_AUDIT`, never engineering acceptance.
The clock thread is stopped in `finally`. Final write failures invalidate the
outer report and retain a best-effort diagnostic; a persistent storage failure
may make that report unavailable, so the CLI also returns the result and a
nonzero status. No inner evidence file is rewritten during outer cleanup.

Require both the campaign checks and an independent full-grid raw-receipt,
SQLite, authority, identity, accounting and frozen-export audit before a new R4
gate decision. The original invalid run cannot be repaired by a later complete
run, and an inner complete summary does not override an invalid outer campaign.
R5 remains gated on that decision. Neither attempt establishes long-soak,
production, multi-host, clock-fault repair, or general coordination efficacy.

After separate review, the explicit invocation is:

```text
PYTHONPATH=/tmp/pheroos-session-site:/home/scott/projects/PheroOS/pheroos-bench/src \
/home/scott/projects/PheroOS-runtime/.local/venv312/bin/python \
tools/run_scaling_replication.py --config scaling-full-grid-replication-v1.json \
--output results/r4-session-scaling-replication-v1
```

Provider-free tests use synthetic runners and temporary directories. They do
not invoke the original GPU runner or create a replication result directory.
