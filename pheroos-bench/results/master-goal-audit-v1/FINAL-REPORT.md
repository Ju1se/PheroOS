# Master empirical and architecture report

**Status: master research goal completed for the documented experimental OS
candidate.** The [final root acceptance](MASTER-ACCEPTANCE-v1.json) covers R1–R5,
the consumer/architecture decision, exact package retention and a fresh offline
consumer installation on 2026-09-13. This report synthesizes those records; it
adds no independent experiment or confirmatory observation. General efficacy,
production readiness and long-soak maturity remain unproven.

## Research question and evidence standard

Can provenance-aware deduplication, local relevance and version-triggered
reactivation reduce redundant multi-agent interaction without degrading task
success, and can the mechanism operate within a coherent finite runtime?
The completed evidence separates those questions. Engineering checks establish
exercised behavior; measurement checks establish identity, pairing and cost
reconciliation. Neither proves efficacy. Fault observations support only the
injected boundaries and backend, rather than production robustness.

Historical E1/E2/E3 evidence and thresholds remain unchanged. R1 and the later
development pilots do not count toward confirmatory evidence. R2's separate
evaluation split is descriptive. Constructed worlds are pairing/aggregation
units; agents, conditions, calls and repeated worlds add no independent units.
These fixtures are not a random sample of a task population. Flat quality
intervals and repeated successful implementation checks do not establish
noninferiority, equivalence or a general swarm advantage.

## Empirical findings

| Phase | Observed result | Decision supported |
| --- | --- | --- |
| [R1 coordination v2](../r1-coordination-pilot-v2/RESULTS.md) | 64 complete episodes, eight worlds and eight arms, including strong sharing/dedup controls and three component ablations. Candidate delivers 8.78% less than simple dedup+TTL but uses 14.99% more logical operations and 19.99% more accounted bytes. Every arm succeeds in 7/8 worlds. | Engineering and measurement pass. No candidate promotion or task-success noninferiority claim. |
| R1 ablations | Removing reactivation delays four source corrections by 2–3 ticks; matched sparse sharing delays four by 2–7 ticks. Candidate and both dedup baselines correct all eight update events within the update tick. | Components have observable effects, but the candidate has no observed correction advantage over competent dedup baselines. |
| [R2 scheduling](../r2-pilot-v1/RESULTS.md) | All 480 episodes/traces reproduce. Congestion candidate and capability FIFO dispatch and perform identically; candidate adds 3.75% scheduler operations in the bottleneck evaluation. | Retain conventional FIFO for this workload. The workload activates pressure without exposing a distinguishing dispatch choice; the negative result is bounded. |
| [R2 capacity audit](../r2-capacity-audit-v1/RESULTS.md) | Available/busy/idle/unavailable capacity reconciles in all historical episodes. Dedicated reserve is zero. | Accounting is complete for the declared model; no new sample or reserve-policy efficacy is introduced. |
| [R3 framed v3](../r3-framed-pilot-v3/RESULTS.md) | Twenty episodes, 160 main/probe calls and 80,709 known tokens. All five policies solve both code worlds and fail both evidence worlds. Seventeen probes have eligible shared artifacts; zero pairs show a semantic change with both actions valid. | Common framing, real inference, receipt/authority and evaluator paths reconcile. No final-success advantage or declared semantic-interaction benefit is established. |
| [R3 posthoc interaction](../r3-framed-pilot-v3/INTERACTION-DIAGNOSTIC.md) | Three actual-only immediate-prefix successes occur on one code world when invalid withheld branches are included. | Retain the narrower finding without changing the frozen endpoint, counting three policies as independent tasks, or claiming a downstream rollout effect. |
| [Session/G5](../r3-session-capability-v1/RESULTS.md) | Sixteen audited episodes; 38,661 tokens, 56 model calls and 76 tools. Both model sizes solve autonomous code tasks and fail evidence tasks, including with supplied current inspections. | [Bounded G5 engineering passes](../r3-session-capability-v1/G5-gate-review.json). Larger-model control and a real Session consumer are exercised; general model superiority and isolated document-reasoning capability remain unproven. |
| [R4 full-grid replication](../r4-session-scaling-replication-v1/RESULTS.md) | All 264 condition/world episodes complete; 51 succeed and 213 fail. Every evidence-world episode fails. All 56 matched policy exports validate, but every quality interval includes zero. | [Bounded R4 engineering/measurement passes](../r4-session-scaling-replication-v1/GATE-ADDENDUM.md). No coordination or model promotion follows. |
| [R5 Session faults](../r5-session-faults-v1/RESULTS.md) | One 38-case finite study; all source invariants and corrected offline audit checks pass. Available ledgers retain 18 known synthetic tokens and 70 unknown tokens in ten calls; one damaged primary ledger is unavailable. | [Bounded R5 engineering passes](../r5-session-faults-v1/GATE-ADDENDUM.md). Passing includes unresolved, cancelled, revoked and unavailable dispositions, rather than universal recovery. |

R3's failed admission history remains intact. [V1](../r3-pilot-v1/RESULTS.md)
used 40,120 known tokens and demonstrated transport rather than useful shared
semantic improvement. V2 retained 20 failed episodes, 0/160 public-valid actions
and 74,915 tokens. Its [offline format audit](../r3-format-audit-v1/GATE-REPORT.md)
found 14 potential admissions after sole-JSON-fence unwrapping against original
histories. It did not propagate normalized artifacts or change historical
outcomes. The common rule was then tested in separately frozen v3. The
[3B readiness journey](../session-model-readiness-v1/RESULTS.md) likewise retains
its schema-failing 63-token proposal and absence of final publication.

## R4: observed benefit, harm and overhead regions

The fixed-call study executes all 32 global turns and every declared identity
at N=1,2,4,8,16,32. Small blackboard solves 0/4 worlds at every N; dedup+TTL and
versioned each solve 1/4. Versioned removes stale selected receipts and slightly
reduces cost relative to dedup+TTL without improving quality. Medium and mixed
private/blackboard solve both code worlds at every declared N. These task-bound
observations favor examining model capability before adding coordination, but
do not establish a generally stronger model or a new default.

All 104 declared expected-null comparisons match common-prefix prompts,
model/seed, response text and token counts across 2,685 paired steps. Blackboard
does not gain quality with N; small blackboard foreign-record accounting grows
from zero at N=1 to 219,262 bytes per four-world fixed-call condition at N=32.
Logical N changes ownership and communication accounting while preserving the
observed common-input behavior. Under deadline conditions, unequal run lengths
are retained rather than hidden by prefix comparison.

There are adverse cases: small private N=2 solves `bounded_increment`, while
blackboard N=2 loses that success in each of the three resource regimes. Larger
private N loses the small model's fixed-call success in this sample. Increasing
N therefore does not provide a monotonic quality improvement. Binding tokens
and deadlines also leave declared agents unused; the allocation export retains
actual dispatched identities instead of treating idle N as exercised capacity.

Deduplication removes duplicate selected provenance without eliminating repeated
work: 173 of 398 published valid inspections repeat an earlier origin, charging
78,732 tokens across the grid. No one of 3,428 dispatched evidence prompts has
all three current sources, and no evidence episode globally inspects all three
final-version sources. The high-N private-information lower bound is a design
constraint, not an observed intelligence threshold; evidence failures at low N
and with medium models leave a broader capability/action-selection limitation.

Mixed execution charges 896 small calls / 413,350 tokens and 128 medium calls /
65,612 tokens. All 16 first successful prefixes in that cohort occur in medium
slots. At N=1, mixed first succeeds on code at turns 29 and 30; all-medium first
succeeds at turns 1 and 4. This is attribution to a scheduled slot, not an
isolated causal contribution or adaptive escalation finding. All conditions
continue until their declared resource stop rather than hidden success.

## Retained accounting and measurement limits

| R4 recorded quantity | Original known subtotal | Replication | Combined known subtotal |
| --- | ---: | ---: | ---: |
| Tokens | 2,824,212 | 3,402,842 | 6,227,054 |
| Model calls | 5,891 | 7,134 | 13,025 |
| Tool calls | 5,890 | 7,085 | 12,975 |
| Control operations | 186,609 | 220,957 | 407,566 |

The original 264-row collection remains `INVALID_ABORT`: 204 complete rows,
one `LeaseLost` abort and 59 unstarted rows. Its [full abort audit](../r4-session-scaling-pilot-v1/ABORT-AUDIT-ADDENDUM.md)
passes integrity/accounting without repairing that disposition or establishing
the interruption's cause. Unstarted accounting/outcomes remain null. The
replication uses new ledgers and an unchanged full grid, never borrows original
rows and never pools repeated worlds as new units. Combined figures are known
subtotals, not complete totals when original rows are missing.

The replication retains 2,970,028 tokens on 6,268 publicly rejected actions and
2,620,849 tokens in terminal failed episodes; these slices overlap. Late known
model replies without tool receipts retain 24,111 tokens. Reserved and unknown
usage are zero for the completed replication; the general accounting path
preserves unresolved usage rather than replacing it with zero. The original
aborted episode retains its final settled, unevaluated model receipt.

The unchanged `r_paired_world_mean_v1` adapter maps call units to dispatched
model calls + tool calls + declared control operations. Tokens, logical bytes,
loading and timing remain separate. Replication transport, event, communication
and processing measures overlap and are not physical I/O. Its 70 model loads,
in-episode model-get time and bounded clock-observer overhead are explicitly
reported, without double-counting overlapping stages. Logical N runs on one
GPU with sequential concurrency one. CPU activity, loading and sampling limit
timing inference; no hardware scaling, energy or monetary advantage is shown.

## Current finite architecture and compatibility boundary

The [source/installed architecture audit](architecture-review.md) and
[consumer inventory](../../EXPERIMENTAL-OS-CANDIDATE.md) identify a coherent
experimental path. Core owns protocol authority and canonical Trace. The
external Session owns finite declared DAG work, eligible agents/actions, leases,
durable permission state, reservations, receipts, cancellation/revocation and
recovery. Fresh public-core authorization gates execution/publication.
SessionDriver runs replaceable model and trusted tool adapters. Bench owns
tasks, attention/history policies, hidden evaluation and statistics.

Private checkpoints, verified artifacts, bounded addressed reference mailboxes,
attention and current authority remain distinct. Known late receipt settlement
does not revive cancelled permission. New Session calls have one accounting
owner and never also bill G1 Store or R3 PilotLedger. Historical runtime modules
remain available for their frozen consumers; migration/removal is an explicit
compatibility decision. Source/wheel/installed hashes identify the experimental
cohort; `0.1.0.dev1` alone does not. No core contract change or Stable export was
required. Wheel/sdist acceptance each passed 131 tests; [post-replication bench
regressions](bench-post-replication-validation-v1.json) record 1,171 passes and
17 explicit absent-Session skips, without treating skips as passes.
The R5 v2 audit correction also has [12 focused passing tests on Python 3.12](r5-audit-python312-validation.json),
recorded separately from that earlier full bench suite. The interrupted full core suite is not
claimed as passing; installed/runtime and focused checks do not replace it.

## Exact experiment identity index

| Method or schema | Config | Executed source identity |
| --- | --- | --- |
| `r1_coordination_config_v2` / `r1_coordination_episode_v2` | [R1](../../r1-coordination-pilot-v2.json) | [Freeze](../r1-coordination-pilot-v2/freeze.json) |
| `r2_scheduling_pilot_v1` / `r2_capacity_audit_v1` | [R2](../../r2-pilot-v1.json), [addendum](../../r2-capacity-audit-v1.json) | [R2 freeze](../r2-pilot-v1/freeze.json), [addendum freeze](../r2-capacity-audit-v1/freeze.json) |
| `r3_local_closed_loop_pilot_v1` / `r3_tool_loop_pilot_v2` | [V1](../../r3-pilot-v1.json), [v2](../../r3-tool-pilot-v2.json) | [V1 freeze](../r3-pilot-v1/freeze.json), [v2 freeze](../r3-tool-pilot-v2/freeze.json) |
| `r3_framed_action_pilot_v3` | [V3](../../r3-framed-pilot-v3.json) | [Freeze](../r3-framed-pilot-v3/freeze.json) |
| `r3_session_capability_v1` | [G5](../../r3-session-capability-v1.json) | [Freeze](../r3-session-capability-v1/freeze.json) |
| `r4_session_scaling_pilot_v1` / `r4_full_grid_replication_v1` | [Inner config](../../r4-session-scaling-pilot-v1.json), [campaign](../../scaling-full-grid-replication-v1.json) | [Identical inner freeze](../r4-session-scaling-replication-v1/collection/freeze.json), [campaign freeze](../r4-session-scaling-replication-v1/campaign-freeze.json) |
| `r5_session_faults_v1` | [R5 config](../../r5-session-faults-v1.json) | [Freeze](../r5-session-faults-v1/freeze.json), [audit v2](../r5-session-faults-v1/independent-audit-v2.json) |

The 1.5B model is `Qwen/Qwen2.5-Coder-1.5B-Instruct` revision
`2e1fd397ee46e1388853d2af2c993145b0f1098a`; the 3B control is
`Qwen/Qwen2.5-Coder-3B-Instruct` revision
`488639f1ff808d1d3d0ba301aef8c11461451ec5`. Both use FP16 without quantization.
The freezes bind model manifests/files, source, task/evaluator and dependencies.
The accepted R4 [full audit](../r4-session-scaling-replication-v1/independent-audit-v1.json)
SHA256 is `ad8424ed1eedd6ba04773e7e4b2893cb75b70ac63971cce0ffb6aaa38a0d6b49`;
the [root gate](../r4-session-scaling-replication-v1/R4-gate-review.json) pins its
phase report, outer audit and all primary measurement identities.

## Finite robustness evidence and final exit

The [historical five-case R5 run](../r5-runtime-faults-v1/RESULTS.md) passes its
specific PilotLedger SIGKILL, receipt-order and temporary-write-lock boundaries
with fake inference. This is not Session fault acceptance or GPU crash recovery.
The [new 38-case Session study](../../R5-session-faults-v1-contract.md) ran once
against the installed runtime. All 38 source invariants passed, with no study
`FAIL` or `INVALID_ABORT`. This is distinct from runtime disposition: 13
`RUNNING`, ten `UNRESOLVED`, one `COMPLETED`, 11 `CANCELLED`, two `REVOKED`, and
one `ABORT_UNAVAILABLE`. Only the checkpoint-restart case ends with the run
status `COMPLETED`; `mailbox:reverse` also publishes both work items before
explicit cancellation. The finite safe-disposition checks do not imply all
work recovered or finished.

The first offline audit retained one `AUDIT_MISMATCH`: its expected literal
`ValueError` label disagreed with the actual `JSONDecodeError` subclass for the
exact malformed packet. The separately identified v2 adapter retains all v1
checks and pins the packet, refusal text and unresolved state while correcting
that one expectation. No study case was rerun or historical outcome changed.
The [v2 audit/receipt](../r5-session-faults-v1/independent-audit-execution-v2.json)
records 38 `INTEGRITY_PASS`, all 628 frozen input identities and all 163 original
study files preserved, plus the unchanged initial failed audit and receipt.
This is a checker correction, not evidence of a repaired runtime defect.

Across unique available ledgers, R5 records 13 synthetic-model and 25 tool
dispatches, including one foreign-session auxiliary tool and one intact-original
tool before copy corruption. It retains **18 known synthetic tokens, 70 unknown
tokens, ten unknown calls and zero reserved tokens**. The damaged copy remains
null/unavailable and is not counted as another execution. Sidecars contain 33
invocations, with shared physical sidecars counted once. These bookkeeping
fixtures involve no actual model generation and are not added to the R4 real
model-token subtotal. Unknown zero-token tools remain unknown calls, and
dispatched work is not automatically repeated to obtain a cleaner outcome.

Nine cases use collector-observed SIGKILL markers and fresh-process inspection;
other cases cover committed state, selected lock/order/transport failures,
provenance substitution and bounded mailbox/checkpoint behavior. Markers,
timeouts and refusal strings are trusted collector observations. Missing raw
control-pipe bytes, failed-operation arguments and historical clock instants
limit independent reconstruction of injection details. The source report and
[root R5 gate](../r5-session-faults-v1/R5-gate-review.json) retain these limitations.
That gate is `PASS_BOUNDED_R5_ENGINEERING`, SHA256
`6915a05192451dfa008356b54a0cb11bc2695e10085f86d8f7bdc1f7c3af7e4f`.

The [consumer/compatibility decision](consumer-exit-decision-v1.md) is
`ACCEPTED_FINITE_CANDIDATE_PENDING_MASTER_REVIEW`: retain the source-identified
Session v1 cohort and its historical consumers, using fresh databases without
G1/PilotLedger migration. The final root decision resolves that retained pending
qualification. The [persistent archive and installation instructions](consumer-artifacts-v1/INSTALL.md)
retain exact accepted wheel, sdist and core packages with their acceptance and
consumer receipts. The [final preservation check](final-integrity-v1.json)
passes 3,588 unique retained file identities without rerunning a study. Root also
rechecked all 1,313 consumer-review inputs and all archive checksums. The
[fresh offline archive installation](consumer-install-check-v1.json) passes;
its [provider-free journey](consumer-install-check-v1/journey/report.json)
completes with two tool calls, zero model calls/tokens and zero reserved/unknown
usage. Rereading the committed receipt preserves the response and accounting.
This installation check is not another efficacy sample or fault study.

The closed loop returns independently verified tool results to later model
context; it does not train model weights or establish learned reinforcement.
Conventional dynamic allocation and negative efficacy results satisfy their
finite engineering/research criteria without promoting an adaptive policy.
Keep the simplest explicit single-agent/simple-sharing path; no experimental
candidate is promoted by this report. A scientifically negative efficacy result can complete a
research phase; a failed integrity invariant cannot be excused as that kind of
negative result.

No eight-hour or 24-hour soak was performed. Unproven domains include general coordination efficacy, task/model-family
generalization, learned recruitment/escalation, GPU replica scaling, dynamic
admission or service supervision, long-soak retention, multi-host failover,
hostile-host authority custody, physical power-loss durability, arbitrary
corruption repair and external exactly-once effects. Current mailbox/checkpoint
bounds do not bound lifetime Trace growth; trusted tool callbacks are not a
general sandbox. These limits remain explicit in the completed candidate and
its final acceptance. The work is retained locally with exact source/artifact
identities; no release, push or Stable API promotion was performed.
