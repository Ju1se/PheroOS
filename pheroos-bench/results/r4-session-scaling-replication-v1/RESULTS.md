# R4 full-grid replication: pilot results

**The single replication completed all 264 episodes and the whole-grid
descriptive measurement check passes. Independent audit and the R4 gate remain
pending.** No policy promotion, confirmatory result or general coordination
advantage follows. The original collection remains `INVALID_ABORT`.

## Problem, hypothesis and mechanism

The [unchanged R4 design](../../R4-session-scaling-v1-contract.md) asks how fixed
work allocation, shared history, provenance deduplication, current-version
filtering and model size affect quality and redundant interaction as logical
agent count increases. More agents or sharing may help, have no effect, or harm
performance. The [replication contract](../../SCALING-replication-v1-contract.md)
authorizes one fresh full grid after the original abort, with no outcome-based
changes, selective replacement rows or automatic retry.

One experimental Session owns work, leases, durable permission state and
accounting. Fresh public-core authorization gates execution and publication.
Models propose actions; the common pure task tool checks them before publication.
Public-valid evaluation facts and hidden final
task success remain separate. Policies select bounded histories and create no
evidence or permission.

## Baselines, implementation and experimental design

Four constructed worlds—two integer code repairs and two evidence-revision
tasks—cross 66 conditions. The small-model cohort compares `private`,
`blackboard`, simple `dedup_ttl`, and `versioned` at N=1,2,4,8,16,32. Medium and
mixed cohorts compare private/blackboard at N=1,4,16,32. Mixed execution assigns
slots 0–27 to 1.5B and slots 28–31 to 3B. This is fixed escalation.

Every episode permits at most 32 global model turns, 64 runtime calls,
256 output tokens per generation and 2,048 prompt-plus-output tokens. The
40 `fixed_calls` conditions use a nonbinding 65,536-token ceiling; 13
`fixed_tokens` conditions use 8,192 tokens; 13 `fixed_deadline` conditions use
30 seconds with the larger ceiling. Token/deadline conditions cover small
private/blackboard at every N and medium private at N=1. All comparisons within
a regime use the same resource limits, task environment, accounting and checker.
Success always requires the final task version; hidden prefix scoring occurs
after execution. Seed is `3109 + world_index * 100 + step`; order seed is `3137`.

## Validation and measurement

The [outer campaign](campaign-summary.json) records exactly one attempt, no
errors and `REPLICATION_COLLECTED_PENDING_INDEPENDENT_AUDIT`. The
[inner summary](collection/summary.json) is `PILOT_COMPLETE` / `VALID_COMPLETE`:
160 call-limit, 52 budget and 52 deadline stops, with no invalid episodes.

The reviewed [analysis](analysis/analysis.json) validates the entire immutable
grid through the frozen measurement module, reproduces the stored summary and
checks exact equality with a representative frozen public export. All
[56 declared matched policy contrasts](analysis/paired-index.json) retain four
worlds and eight records each, with the unchanged `r_paired_world_mean_v1`
mapping, phase `instrument_check` and `counts_toward_verdict=false`. No contrast
was selected based on outcomes. All 61 stored output hashes match. The reviewed
14 synthetic analysis checks pass; commands, identities and output checks are
recorded in [analysis-execution.json](analysis-execution.json). The independent
SQLite/authority/full-checkpoint audit is a separate pending gate.

Across the 56 descriptive contrasts, quality differences are zero in 31,
+0.25 in 22 and −0.25 in three. Every quality interval includes zero. The flat
intervals are `INSUFFICIENT_RESOLUTION`; they do not prove equivalence. The four
constructed worlds are the pairing and aggregation units; conditions, agents
and turns add no independent units, and these fixtures are not a random sample
of a task population. Original and replication observations repeat the same
worlds and do not create eight independent worlds. These pilot intervals do not establish efficacy or powered
noninferiority. The additive descriptive formulas are not new confirmatory
endpoints.

## Quality, allocation and negative findings

There are 51 successful condition/world rows and 213 task failures. All 132
evidence-world rows fail. Aggregate condition counts describe the collected
grid, not independent task-success trials.

The fixed-call results below give successes out of the same four worlds.
Token totals and logical operations are per four-world condition; ranges cover
its declared N values. Every fixed-call episode dispatched all 32 model turns
and exercised all declared agents, including N=32.

| Cohort / policy | Successes at increasing declared N | Tokens per condition | Logical operations per condition |
| --- | --- | ---: | ---: |
| Small private, N=1,2,4,8,16,32 | 0, 1, 0, 0, 0, 0 | 47,799–63,378 | 4,048–4,520 |
| Small blackboard, same N | 0, 0, 0, 0, 0, 0 | 63,378 | 4,520 |
| Small dedup+TTL, same N | 1, 1, 1, 1, 1, 1 | 64,362 | 4,462 |
| Small versioned, same N | 1, 1, 1, 1, 1, 1 | 63,312 | 4,441 |
| Medium private, N=1,4,16,32 | 2, 2, 2, 2 | 46,327–70,889 | 4,048–4,520 |
| Medium blackboard, same N | 2, 2, 2, 2 | 70,889 | 4,520 |
| Mixed private, N=1,4,16,32 | 2, 2, 2, 2 | 47,618–64,429 | 4,048–4,520 |
| Mixed blackboard, same N | 2, 2, 2, 2 | 64,429 | 4,520 |

The dedup+TTL and versioned arms solve `bounded_increment` with the
small model where blackboard fails. Version filtering removes stale selected
receipts and slightly reduces cost relative to dedup+TTL, but adds no observed
quality gain. Both fail `cyclic_offset` and both evidence worlds. Higher N gives
no improvement in any shared-history fixed-call arm. Small private N=2 solves
one code world; larger private N loses that success in this sample. At N=2,
blackboard loses the same code-world success relative to private in all three
resource regimes. These are retained adverse observations, not a universal
ranking or a newly selected threshold.

Under the binding token cap, small private N=32 dispatches 20–22 agents per
episode and blackboard N=32 dispatches 15–17. Under the deadline, these ranges
are 19–28 and 15–28. Undispatched declared agents remain in the allocation data.
Medium private N=1 solves both code tasks in all three regimes; small private
N=2 solves only `bounded_increment`, and the other small private/blackboard
token/deadline conditions solve none. Context trimming is zero. The predeclared
private evidence-information bound at N≥8 is structural; failure at lower N
and with the medium model prevents treating it as an empirical capability floor.

## Sharing, repeated work and larger-model attribution

All [104 expected-null comparisons](analysis/expected-null-controls.json)—84
blackboard comparisons across N and 20 private/blackboard N=1 comparisons—have
identical common-prefix prompts, model IDs, seeds, response text and response
token counts across 2,685 paired steps. All 2,662 mutually available tool results
also match; 23 final tool comparisons are unavailable. Twelve deadline controls
have unequal lengths, retained explicitly. Thus increasing logical N under
blackboard changed attribution and foreign-record accounting, not common-prefix
model behavior. Small blackboard foreign-record bytes rise from zero at N=1
to 219,262 per four-world fixed-call condition at N=32, without a quality gain.

Per four-world fixed-call condition, small blackboard has 148 within-prompt
duplicate-provenance occurrences and 20 stale selected receipts. Dedup+TTL has
zero duplicate occurrences but 23 stale selections; versioned has neither.
Repeated published inspection origins are two, four and three respectively:
deduplicated context does not itself eliminate repeated inspection actions.
Across the full grid, 173 of 398 published valid inspections repeat a prior
origin, retaining 78,732 model tokens; 14,051 selections reuse a prior record
and 17,845 reuse prior provenance. Public-valid counters include submissions
that fail hidden scoring and do not establish independently true facts.

No one of 3,428 dispatched evidence prompts contains all three current required
sources. Even pooled within each evidence episode, final-version inspection
coverage reaches at most two sources: 78 episodes inspect none, 33 inspect one,
and 21 inspect two. No successful evidence convergence is observed. Public
semantic-action diversity is small: each of the 48 small-model dedup/versioned
fixed-call episodes has exactly one distinct valid signature, across all four
worlds and six N values. These signatures are a
descriptive proxy, not program equivalence or independent solution diversity.

The mixed cohort charges 896 small-model calls / 413,350 tokens and 128
medium-model calls / 65,612 tokens. All 16 first successful final-version
prefixes in that cohort occur in medium slots. At N=1, mixed first succeeds on
the code worlds at global turns 29 and 30; all-medium first succeeds at turns
1 and 4. Small dedup/versioned first succeeds on its one solved code world at
turn 7. Seven prefixes elsewhere later regress, so first success and stable
observed success remain separate in [episode metrics](analysis/episode-metrics.jsonl).
Unsuccessful convergence is censored/null. These slot attributions do not
isolate a causal contribution from the preceding small-model history or
establish generally superior model capability.

## Complete retained accounting and timing

| Replication quantity | Known total |
| --- | ---: |
| Actual tokens: prompt / completion | 3,402,842: 3,030,343 / 372,499 |
| Small-model calls / tokens | 5,843 / 2,747,026 |
| Medium-model calls / tokens | 1,291 / 655,816 |
| Model / tool calls | 7,134 / 7,085 |
| Control operations | 220,957 |
| Logical call units: model + tool + control | 235,176 |
| Reserved tokens / unknown tokens / unknown calls | 0 / 0 / 0 |
| Request / response bytes | 35,397,409 / 5,787,706 |
| Event / communication bytes | 26,551,624 / 5,075,330 |
| Processing bytes | 170,999,431 |

All 6,268 publicly rejected actions retain 2,970,028 tokens. Terminal failed
episodes retain 2,620,849 tokens; these cost slices overlap. Fourteen public-valid
but hidden-failing submissions retain 8,225 tokens. Deadline handling retains
49 known model replies without a tool receipt, charging 24,111 tokens; 51 known
model replies remain unpublished, charging 24,924 tokens. Late known work is
charged without publishing, and one abandoned reservation is not miscounted as
model dispatch. Every control stage remains visible, including policy selection,
context/tokenization, receipt binding, tool verification and Session boundaries.
Logical operations are neither model calls nor machine instruction counts.

Total episode elapsed time is 10,702.054243972 seconds, model execution is
8,006.867440636 seconds, in-episode model-get time is 585.568483713 seconds and
offline hidden evaluation is 6.043114770 seconds. The separate global log has
70 weight-load events totalling 690.731890106 seconds. It overlaps in-episode
model-get time; neither timing nor overlapping byte counters may be summed as
independent physical costs.

| Regime | Episode elapsed p50 / p95, seconds | Model execution p50 / p95, seconds |
| --- | ---: | ---: |
| Fixed calls, 160 rows | 52.423 / 70.948 | 37.103 / 50.739 |
| Fixed tokens, 52 rows | 24.875 / 31.514 | 18.932 / 26.582 |
| Fixed deadline, 52 rows | 30.473 / 31.660 | 24.576 / 27.175 |

Quantiles use linear interpolation over these descriptive rows, not independent
timing replications. Deadline elapsed time may exceed 30 seconds while a
dispatched reply settles; late publication remains fenced. One GPU serves one
resident checkpoint sequentially: logical N is not physical concurrency. Peak
adapter tensor allocations are 3,162,399,744 bytes for small and 6,387,716,608 for
medium, excluding other device/process memory. The bounded clock observer joins
successfully after 2,164 samples / 462,702 bytes, reported separately from inner
call units. Its largest sampled realtime-minus-monotonic interval difference is
3,822,289 ns; this does not establish an isolated timing benchmark or explain the
original interruption. Money and energy remain unmeasured/null.

The [original abort audit](../r4-session-scaling-pilot-v1/ABORT-AUDIT-ADDENDUM.md)
preserves **2,824,212 original known tokens** separately. Together with this
replication, the known subtotal is **6,227,054 tokens**. The original 59 unstarted
rows still have null accounting and outcomes; a successful replication does not
erase them or repair the original INVALID grid. No original row enters these
56 paired exports.

## Identity, limitations and next gate

Outer method is `r4_full_grid_replication_v1`; inner method is unchanged
`r4_session_scaling_pilot_v1`; task environment is `r4_task_fixtures_v1`.
Both are non-confirmatory pilots. The common models are Qwen2.5-Coder
1.5B-Instruct revision `2e1fd397ee46e1388853d2af2c993145b0f1098a` and
3B-Instruct revision `488639f1ff808d1d3d0ba301aef8c11461451ec5`, FP16 without
quantization, on the RTX 5070 Laptop GPU with Python 3.12.3, PyTorch
2.11.0+cu128 and Transformers 4.57.3. The freezes bind complete model and source
identities, rather than relying on package-version or base-commit labels alone.

| Artifact | SHA256 |
| --- | --- |
| Campaign config | `df9f3cea01a69c0718779c6086cbd644d3b9f80bc30ee9141d19e267eebca00e` |
| [Campaign freeze](campaign-freeze.json) | `aa759c38385bdb3f8852b38e02b5eed5e4de222b983353a63037fad4bd9ba709` |
| [Inner freeze](collection/freeze.json), identical to original | `fc535ea621a7d26582fd2888cac088b1f3f0604efdb98a4b54d0bdf147714e1c` |
| Inner config | `fa2618d606b2bd03c826d651f33a292a384bda03cef8b91a956b510804ec22ff` |
| [Raw episode stream](collection/episodes.jsonl) | `b4160e71a66a0977ad39995de1c5481eecfbb1baed7f20a4e590f35d00d9675c` |
| [Analysis](analysis/analysis.json) | `ccb2beaf0fa91acdd17b67da42fdaa42acd472400f7af93ef79975d3637adabc` |
| Analysis tool | `37df3d0b482d6c7016cc63e4b2ec88ac93f4e46ac5ab66481cde8bc50e6eb22e` |

The four finite development worlds and one model family/seed schedule do not
establish generalization, a capability threshold, learned recruitment, hardware
scaling or a general swarm benefit. Equal-weight logical operation accounting
is an instrumentation convention. Sequential host activity, model loading and
the added observer limit timing comparisons. Tokenizer/receipt audits cannot
reconstruct generated token IDs that were not saved. Trusted-host authority,
bounded retained context and finite loops do not establish hostile-host custody,
unbounded retention, physical power-loss recovery or external exactly-once
effects. Historical E1/E2/E3 evidence and thresholds remain unchanged.

**Next gate: complete independent full-grid raw/SQLite/authority/accounting and
campaign-identity review, then let root decide bounded R4 acceptance and whether
the separately frozen R5 Session study may proceed.** This phase report does not
complete that gate, authorize R5 execution or promote a default policy.
