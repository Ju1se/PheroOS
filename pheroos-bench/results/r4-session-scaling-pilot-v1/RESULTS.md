# R4 original pilot: ABORT phase report

**The original collection is `INVALID_ABORT`, with `source_status=INVALID_SOURCE`
and `reason=source_abort`. It cannot support policy comparisons or an R4 efficacy
verdict.** This development pilot has `counts_toward_verdict=false`.

## Problem, hypothesis and mechanism

The [frozen contract](../../R4-session-scaling-v1-contract.md) asks whether
sharing, provenance deduplication and current-version filtering improve task
completion or reduce repeated work as a fixed allocation is divided among more
agents. Benefits, null effects and harm are all admissible outcomes. Model text
remains a proposal: one experimental Session owns accounting and lease/permission
state. Fresh public-core authorization gates execution and publication, and an
independently executed task checker supplies publication facts.

## Baselines, implementation and design

The declared grid contains four worlds × 66 conditions = **264 episodes**.
Policies are `private`, shared `blackboard`, simple `dedup_ttl`, and `versioned`.
Logical N is 1, 2, 4, 8, 16 or 32. Small, medium and fixed-escalation mixed cohorts
share the runtime, tools, task/evaluator, framing, accounting and measurement.
Mixed execution assigns the last four of 32 global slots to the medium model.

The common bounds are 64 runtime calls, 256 output tokens per generation and
2,048 prompt-plus-output tokens. `fixed_calls` allows 32 model turns with a
nonbinding 65,536-token ceiling; `fixed_tokens` uses 8,192 tokens; `fixed_deadline`
uses 30 seconds and the larger ceiling. The generation seed schedule is
`3109 + world_index * 100 + step`; order seed is `3137`. Every final objective
requires the final task version. The four worlds, not turns, N values, policies
or repeated seeds, are the independent units.

Models are `Qwen/Qwen2.5-Coder-1.5B-Instruct` revision
`2e1fd397ee46e1388853d2af2c993145b0f1098a` and
`Qwen/Qwen2.5-Coder-3B-Instruct` revision
`488639f1ff808d1d3d0ba301aef8c11461451ec5`, FP16 without quantization.
The [freeze](freeze.json) records Python 3.12.3, PyTorch 2.11.0+cu128,
Transformers 4.57.3 and the installed experimental runtime/core closure.
The [environment](environment.json) records an RTX 5070 Laptop GPU under WSL2.
One resident checkpoint serves calls sequentially; model execution concurrency is one.

## Tests and checks

Frozen precollection tests cover task/evaluator separation, real agent
allocation, shared-prompt invariance, provenance/version/TTL behavior, receipt
binding, exact accounting types and explicit deadline/budget/abort outcomes.
For this report, direct JSON checks confirmed all 264 distinct declared
world/condition identities and the exact stored execution order, summed the
retained source-accounting rows and model receipts, and matched all 641
`freeze.source_sha256` entries to the current files. These checks do not replace
the separate SQLite, authority, evaluator and full checkpoint-file audit, which
is in progress. No valid-grid analyzer, subset export or new generation was run
for this report.

## Results, negative finding and retained costs

The [terminal summary](summary.json) retains **204 complete episodes, one started
`INVALID_ABORT` episode and 59 `INVALID_ABORT` / `not_started` rows**. Completed
episodes comprise 160 `call_limit` and 44 `budget` stops. No deadline episode
started. The declared grid is present, but collection validity failed; retaining
all row identities does not turn the completed subset into a valid comparison.
No usable `r_paired_world_mean_v1` comparisons are issued.

At zero-based row 204, `fixed_tokens-small-private-n1` on
`evidence_revision/ready_window` ended with `LeaseLost`:
“expired, cancelled, revoked or superseded work lease.” Its
[episode](episodes/fixed_tokens-small-private-n1/evidence_revision/ready_window/episode.json)
retains 4,248 tokens, eight model calls and seven tool calls. The last generation
receipt (`generate-7`) settled 554 tokens: 442 prompt and 112 completion. It was
framing-admitted but not evaluated or published; the run was cancelled. This
episode retains `success=null`, rather than being reclassified as task failure.

Known totals below cover all **205 started episodes**, including the abort.
The 59 unstarted rows retain null accounting. Zero unresolved usage among
recorded started work is not a zero-cost completed outcome for those rows.

| Recorded quantity | Known total |
| --- | ---: |
| Actual model tokens | 2,824,212 |
| Prompt / completion tokens | 2,514,597 / 309,615 |
| Small-model calls / tokens | 4,739 / 2,244,119 |
| Medium-model calls / tokens | 1,152 / 580,093 |
| Model / tool calls | 5,891 / 5,890 |
| Control operations | 186,609 |
| Logical operations: model + tool + control | 198,390 |
| Reserved tokens / unknown tokens / unknown calls | 0 / 0 / 0 |
| Request / response bytes | 29,468,791 / 4,821,424 |
| Event / communication bytes | 22,006,096 / 4,453,115 |
| Processing bytes | 144,023,853 |
| Episode elapsed nanoseconds | 9,990,389,279,252 |
| Model execution nanoseconds | 7,560,848,975,610 |
| In-episode model-get nanoseconds | 623,249,709,044 |
| Offline evaluator nanoseconds | 5,915,783,523 |

The separate [model-load log](model-loads.json) contains 67 successful load
events, totalling 690,361,078,150 nanoseconds. That log overlaps in-episode
model-get timing; the two values must not be added. Byte counters likewise
describe overlapping logical stages, not physical I/O. The original summary
reports `event_bytes_verified=false` because source validation aborted. Reported
event bytes are retained here without upgrading that verification status.
Monetary cost and energy are unmeasured/null. All failed and aborted work remains
charged; none of these costs is discarded if a later collection succeeds.

## Confounds and what was not proven

The preceding episode file has UTC mtime `2026-09-13T07:58:19.185279+00:00`;
the aborted episode file has `2026-09-13T17:14:43.407305+00:00`. This approximately
9-hour-16-minute filesystem wall-time gap contrasts with the failed episode's
22.333854420 seconds of recorded monotonic elapsed time. A host pause or clock
discontinuity is plausible, but file mtimes and the final ledger do not establish
the cause of `LeaseLost` or reconstruct historical lease expiry. The failure
must not be relabelled as a proven infrastructure-only exclusion.

This incomplete, sequential, single-host pilot establishes no coordination
benefit, noninferiority, scaling law, model superiority, capability floor or
timing advantage. The original four constructed worlds, private-history
information limits and one seed schedule remain design limitations. No policy,
runtime authority contract or threshold is promoted. Historical E1/E2/E3 and
earlier R-series evidence remain unchanged.

## Immutable identities

Method: `r4_session_scaling_pilot_v1`; phase: `pilot`. The freeze binds the full
source/config/model declaration. SHA256 values identify the original evidence:

| File | SHA256 |
| --- | --- |
| `freeze.json` | `fc535ea621a7d26582fd2888cac088b1f3f0604efdb98a4b54d0bdf147714e1c` |
| `summary.json` | `f28d0da3e63a2c56941c710318ad7b5cea195e31f966b2604ff25ef29d160f91` |
| `episodes.jsonl` | `8e32f12dd47767741080d89450979021c894f9cd1b69f1f54f934342993c75a4` |
| `order.json` | `e42ddfbfd9c0979ca0111041ada6bfe53bd0af30346c947d063826778332fe9d` |
| `model-loads.json` | `f3764c1308af55e2feaa7b691dbf45dd00075a25ff54f90946a634f23c9142d5` |
| Failed episode `episode.json` | `782632996d12df46560296852dec172f9373ce6721f648e8ecafa3cba7ba812e` |
| Failed episode `snapshot.json` | `ee5eef59f94d0bf808d592b61c5f72de27a4a9f5d545c18416dedb3b3eb05707` |
| Failed episode `session.sqlite` | `8a71de7a2184beb137eb95693358542d3da6b154f66ef9c0ec529194bbdb2a2e` |
| Config `r4-session-scaling-pilot-v1.json` | `fa2618d606b2bd03c826d651f33a292a384bda03cef8b91a956b510804ec22ff` |

## Decision and next gate

**Retain this original collection as ABORT; do not export its completed subset.**
The proposed next step, subject to root review, is a separately frozen,
complete-grid replication in a new exclusive result directory with the original
264-episode design, source, policies, tasks, evaluator, models, seed schedule,
order and resource bounds unchanged. Document host/clock observations and
revalidate the exact frozen input closure before generation. This is recovery
of the declared experiment, without outcome-based tuning or selective reruns.

The original raw records and costs remain permanent, separate evidence. A
replication would remain a non-confirmatory pilot and would not be pooled with
these repeated worlds as new independent units. Root must decide the replication
and subsequent R4/R5 gates after the independent abort audit; this report does
not complete those gates or authorize a policy promotion.
