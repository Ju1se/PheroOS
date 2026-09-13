# R1 coordination v2 — experimental pilot

Research question: can provenance-aware deduplication, local relevance, and
version-triggered reactivation reduce redundant multi-agent interaction without
degrading task success? This provider-free bench simulation tests mechanisms;
it adds no core API, external-runtime strategy, or default policy.

R1 v1 source, tests, contract, configuration and evidence remain frozen. Its
candidate tied source/version + TTL on success and deliveries and cost more
accounted bytes. V2 is a separately versioned implementation with new pilot
seeds 1000–1007, component ablations, delivery acknowledgments and R0 exports.
The v1 runner remains solely for reproducing v1 records. V2 neither migrates
those records nor turns their descriptive evaluation into confirmation.

## Deterministic environment and shared runtime

V2 reuses v1's immutable Signal and deterministic world generator. Each world
has four binary tasks, eight task-bound receivers, three independent sources
per task, 16 ticks, and 24 replicas per tick. Source accuracy is 0.9; old and
current observations may recur. Seed modulo four selects no update, source
update at tick 6, constraint update at tick 8, or both. Task 0 receives stop,
cancel and denial at ticks 12–14. Each agent subscribes to exactly one task in
scope `r1`. Observations are generated before any policy executes; truth is
available only to the common post-execution scorer.

All arms use one synchronous runner, receiver, scorer, control path, accounting
implementation and data delivery cap. Controls always reach their addressed
recipients before data and bypass attention and data caps. This is a simulated
reliable control path, not an implementation of G1 cancellation or authority.
No model or external runtime is invoked by R1. External G1/R0 are regression
checks, not treatment arms. Environment generation and external scoring are
outside policy cost for every arm.

Admission is followed immediately by delivery and cache acknowledgment. Only
actually delivered claims enter suppression state; cap-deferred observations
remain eligible on a later exposure. No queue or retry infrastructure is added.
The cap retains deterministic event/recipient ordering; it can produce starvation
under repeated irrelevant traffic, which remains a failed task rather than an
excluded episode. The pilot uses a four-tick TTL, exercising expiry within the
16-tick horizon. TTL expires at `tick - delivered_at >= ttl`; suppressed reads
do not extend it. Evidence validity includes its `expires_at` tick, and the
receiver checks validity again when answering without requiring new messages.

## Policies and ablations

| Arm | Behavior |
| --- | --- |
| `full_relevant` | Deliver all task-relevant evidence under the common cap. |
| `dedup_ttl` | Simple recipient/scope/task/origin deduplication plus TTL. |
| `source_version_ttl` | Origin deduplication plus task/source versions and TTL. |
| `matched_sparse_random` | Seeded random relevant edges, matching candidate data delivery counts each tick; the full selection index and quota are accounted. |
| `candidate` | Local relevance, canonical source-claim/version deduplication, TTL, and rejection of versions older than delivered source state. |
| `no_dedup` | Candidate with the TTL deduplication check removed; relevance and stale-version rejection remain. |
| `no_relevance` | Candidate with the evidence relevance filter removed; addressed controls and receiver bindings remain. |
| `no_reactivation` | Candidate with task/source versions removed only from the suppression key; TTL and stale-version rejection remain. |

The canonical source claim is `(recipient, scope, task, subject, source,
dependence_group)`. Candidate cache keys add `(task_version, source_version)`;
new versions reopen delivery before TTL expiry. Task versions define epochs;
source versions order changes within an epoch. Trusted fixture metadata declares
one immutable binary claim per source/subject/version. Replica/relay IDs and
identical payload values do not create independence. Different declared source
groups with identical values remain separate evidence. Multiple conflicting
facts under one source/subject/version, forged ancestry, and unknown dependence
are outside this fixture contract. A new fact needs a distinct subject or version.

Receivers count at most one current belief per subject/dependence group. They
reject other tasks/scopes and stale versions, invalidate old task evidence on
constraint updates, and answer by majority; missing support, a tie, expiration,
or a blocking control yields no answer. All policies share these semantics.
Origin IDs already encode versions in this world, so even the simple origin
baseline reactivates on updates. Candidate necessity must be assessed against
both competent baselines. Beating full sharing or an ablation alone is insufficient.

## Records, failure accounting and export

Run from `pheroos-bench` with a fresh output directory:

```bash
.venv/bin/python -m pheroos_bench.r1_coordination \
  --config r1-coordination-pilot-v2.json --output results/r1-coordination-pilot-v2
```

The CLI exclusively creates output and freezes source dependencies, tests,
contract, config and environment metadata before running all eight arms. Each
episode is flushed to `episodes.jsonl`. The authoritative `summary.json` must
be `PILOT_COMPLETE` with unchanged hashes before reading descriptive comparisons.
All metadata says `counts_toward_verdict=false`; only pilot configuration is
accepted. No confirmatory phase, gate, threshold, or best-arm selection exists.

Completed task failures retain `success=0` and every incurred cost. Success
requires every agent on tasks 1–3 correct and task 0 blocked. Correction delays
count ticks until all receivers of an updated task first answer correctly;
unrecovered updates are null and counted as missed. An already-correct noisy
belief can give delay zero; this is output recovery, not causal attribution.

Meter categories are input encoding, every recipient routing decision, delivered
envelopes, state reads and state writes. Each category records logical operations
and canonical JSON bytes. Total bytes sum all stages, including repeated movement
of a payload. They are not physical network traffic, RAM, runtime, GPU use or
money. LLM calls and input/output tokens are explicitly zero.

An execution exception or interruption records `INVALID_ABORT`, null success,
known partial meter costs, and one unknown-cost marker (not an estimated amount).
Malformed configs, duplicate/missing rows, inconsistent accounting or frozen-input
changes invalidate the run. Failed candidate execution cannot provide quotas to
the matched control; that control is explicitly invalid too. An interrupted grid
is incomplete and aborts. Measurement errors never become zero-cost failures or
valid comparisons of a surviving subset.

Each candidate/control directory contains exact R0 `config.json`,
`records.jsonl`, and a descriptive report from `r_paired_world_mean_v1`.
The export uses `phase=instrument_check`, one repetition, and equal independent
world weighting with the four cases as strata. Its `call_units` are explicitly
one logical metered stage operation per unit, including internal operations;
these are not model calls or G1 invocation costs. Source JSONL retains bytes,
deliveries, duplicate counts, correction delays and task outcomes. The declared
`retained_source_slots` diagnostic counts stored groups, including obsolete or
expired entries; it is not a count of currently valid independent support. The
declared
100,000-operation budget is an R0 descriptive overrun reference, not an enforced
total-cost cap; every arm has the same enforced per-tick delivery cap.

R0 reports quality and operation differences with paired-world intervals; flat
intervals remain `INSUFFICIENT_RESOLUTION`. The wrapper labels the source phase
as pilot and the unit mapping explicitly. Reports remain non-confirmatory,
including when the exact R0 files are passed separately to its CLI. E1/E2/E3
thresholds, measurement versions, and historical evidence are unchanged.

## Limitations

This is eight paired synthetic worlds, not evidence of task-success
noninferiority or real multi-agent/LLM efficacy. Repeated deterministic episodes
do not add independent worlds. Binary tasks, trusted source identities and
version metadata, fixed subscriptions, reliable transport, a synchronous schedule,
immediate complete source updates, fixed TTL and a short horizon restrict
generalization. Logical operation totals weight unlike operations equally;
byte totals are a different descriptive proxy. Fewer deliveries may coexist
with more internal work or worse recovery. All null and adverse outcomes remain
in the pilot. Confirmatory design, richer tasks, lossy transport, adversarial
provenance and real-runtime integration require separate scoped experiments.
