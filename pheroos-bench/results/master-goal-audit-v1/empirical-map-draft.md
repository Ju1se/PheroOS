# Empirical map — draft, 2026-09-13

**The completed evidence supports a finite experimental runtime and several
bounded engineering gates. It does not establish a general coordination
advantage or complete the master goal.** This synthesis adds no observations,
tests, model calls or confirmatory evidence. The original R4 collection is
ABORT; its full audit, proposed replication and new R5 acceptance remain pending.

Engineering checks establish exercised implementation behavior. Measurement
checks establish coherent identities, denominators, receipts and costs.
Efficacy requires a supported task-quality/resource comparison; successful
serialization or publication alone does not establish it. Robustness evidence
applies only to the actual injected boundary, backend and failure model.

## Completed empirical findings

| Phase | Observation | Supported conclusion and limit |
| --- | --- | --- |
| [R1 coordination v2](../r1-coordination-pilot-v2/RESULTS.md) | 64 complete episodes across eight worlds and eight arms; every arm succeeds in 7/8 worlds. Candidate versus simple dedup+TTL delivers 8.78% fewer observations but uses 14.99% more logical operations and 19.99% more accounted bytes. | Engineering and seven paired measurement exports pass. Candidate is not promoted; flat quality intervals are `INSUFFICIENT_RESOLUTION`, not noninferiority. |
| R1 component ablations | Removing version reactivation delays four source corrections by 2–3 ticks; matched sparse sharing delays four by 2–7 ticks. Candidate and competent dedup baselines correct all eight updates within the update tick. | Components change finite behavior, but the candidate has no observed correction advantage over the dedup controls. Trusted provenance and synchronous toy delivery limit inference. |
| [R2 scheduling v1](../r2-pilot-v1/RESULTS.md) | All 480 episodes reproduce: eight pilot and 32 separate descriptive evaluation seeds, two regimes, six arms. Candidate and capability FIFO have identical execution traces and performance; pressure computation adds 3.75% operations in the bottleneck evaluation. | A bounded negative efficacy result: retain FIFO. Pressure activates without presenting a dispatch choice that distinguishes these treatments; this does not show backpressure can never help. |
| [R2 capacity addendum](../r2-capacity-audit-v1/RESULTS.md) | All 480 historical episodes/traces reproduce; available/busy/idle/unavailable capacity reconciles. Dedicated reserve is explicitly zero. | Measurement completeness improves with zero new independent observations. Idle time is not automatically deployable throughput; no reserve-policy benefit or real-runtime recovery is established. |
| [R3 framed v3](../r3-framed-pilot-v3/RESULTS.md) | 20 episodes, 120 main calls and 40 probes; 80,709 known tokens, including 45,504 on rejected actions. Every arm solves both code worlds and fails both evidence worlds. All 160 replies pass framing; 49 main and 20 probe actions pass the public checker. | Raw receipt/context/evaluator/authority reconciliation passes. Framing admission is distinct from action validity and hidden task success. No final-success advantage is observed. |
| R3 interaction | Seventeen probes have eligible current shared artifacts; zero pairs differ semantically with both actions valid. A [posthoc diagnostic](../r3-framed-pilot-v3/INTERACTION-DIAGNOSTIC.md) finds three actual-only immediate-prefix successes, all on one code world, with invalid withheld branches. | The frozen endpoint remains zero. The narrower effect is retained, but three policies on one world are not three independent replications; no downstream rollout or final-success benefit is established. |
| [Session/G5 diagnostic](../r3-session-capability-v1/RESULTS.md) | Sixteen episodes, 38,661 known tokens, 56 model and 76 tool calls; seven objectives succeed. Both 1.5B and 3B models solve autonomous code tasks and fail autonomous evidence tasks. Both fail evidence tasks even with supplied current inspections, choosing an invalid placeholder target. | [G5 passes bounded engineering](../r3-session-capability-v1/G5-gate-review.json): real model/tool Session execution, explicit larger-model control, verification and accounting are exercised. This establishes neither coordination superiority nor generally stronger 3B capability; free action choice does not isolate document-reasoning ability. |

Historical results remain separate. [R3 v1](../r3-pilot-v1/RESULTS.md) used 40,120
tokens in 80 real calls; nine shared-history raw-text changes were not nine
semantic improvements. R3 v2 recorded 20 failed episodes and 0/160 public-valid
actions, retaining 74,915 tokens. Its [offline format audit](../r3-format-audit-v1/GATE-REPORT.md)
found 160 sole JSON fences and 14 potential public-valid admissions under strict
unwrapping with original histories. Those posthoc admissions were never
propagated as successful historical rollouts. The common adapter was then
tested prospectively in a separately frozen v3; earlier outcomes were unchanged.

The [3B readiness journey](../session-model-readiness-v1/RESULTS.md) loaded and
generated successfully, but its one 63-token proposal failed the exact output
schema and published no final artifact. That is useful engineering evidence
with a retained task failure, not a success-rate estimate.

## Exact experiment identities

These config and freeze links identify the executed bytes, including source,
task/evaluator and dependency closure. Base commits and the shared development
package version alone are insufficient identities.

| Versioned method or schema | Config | Frozen source identity |
| --- | --- | --- |
| `r1_coordination_config_v2`; episodes `r1_coordination_episode_v2` | [R1 v2](../../r1-coordination-pilot-v2.json) | [Freeze](../r1-coordination-pilot-v2/freeze.json) |
| `r2_scheduling_pilot_v1` | [R2](../../r2-pilot-v1.json) | [Freeze](../r2-pilot-v1/freeze.json) |
| `r2_capacity_audit_v1` | [Capacity audit](../../r2-capacity-audit-v1.json) | [Freeze](../r2-capacity-audit-v1/freeze.json) |
| `r3_local_closed_loop_pilot_v1` | [R3 v1](../../r3-pilot-v1.json) | [Freeze](../r3-pilot-v1/freeze.json) |
| `r3_tool_loop_pilot_v2` | [R3 v2](../../r3-tool-pilot-v2.json) | [Freeze](../r3-tool-pilot-v2/freeze.json) |
| `r3_framed_action_pilot_v3` | [R3 v3](../../r3-framed-pilot-v3.json) | [Freeze](../r3-framed-pilot-v3/freeze.json) |
| `r3_session_capability_v1` | [G5 diagnostic](../../r3-session-capability-v1.json) | [Freeze](../r3-session-capability-v1/freeze.json) |

R3's small model is `Qwen/Qwen2.5-Coder-1.5B-Instruct` revision
`2e1fd397ee46e1388853d2af2c993145b0f1098a`. The G5 larger control is
`Qwen/Qwen2.5-Coder-3B-Instruct` revision
`488639f1ff808d1d3d0ba301aef8c11461451ec5`. Both are FP16 without quantization;
the freezes bind exact model manifests/files. All cited pilots/diagnostics are
non-confirmatory. R2's separate evaluation split remains descriptive. R1 paired
exports use unchanged `r_paired_world_mean_v1`; logical operation costs are not
tokens, money or physical network traffic.

## Finite OS architecture and robustness boundary

The [architecture review](architecture-review.md), its [identity manifest](architecture-review.json)
and [consumer inventory](../../EXPERIMENTAL-OS-CANDIDATE.md) place protocol
authority and canonical Trace in core; Session lifecycle, scheduling/execution,
SQLite state and adapters in the external runtime; and experimental attention,
tasks and statistics in bench. No protocol-core change was required.

One experimental `Session` owns declared finite DAG work, eligible agent/action
identities, leases, token/call reservations, receipts, cancellation/revocation
and recovery. `SessionDriver` executes replaceable model/tool adapters. Bounded
private checkpoints, verified artifacts, addressed reference mailboxes and
attention-selected history are distinct from current permission. A settled
late receipt accounts spend without restoring cancelled authority. New Session
calls never also charge the historical G1 Store or R3 PilotLedger. Wheel and
sdist acceptance each passed 131 tests; those receipts are engineering evidence,
not new experiments or production acceptance.

The [historical five-case fault run](../r5-runtime-faults-v1/RESULTS.md), method
`r5-runtime-faults-v1` ([config](../../r5-runtime-faults-v1.json),
[freeze](../r5-runtime-faults-v1/freeze.json)), passes its specific PilotLedger
SIGKILL, reordered-receipt and temporary-write-lock cases using fake inference.
Dispatched unknown calls stay unknown; committed receipts survive the tested
process boundary. These tests do not establish Session fault acceptance or
actual GPU crash recovery. The new 38-case Session study is still pending.

Unproven domains include general coordination efficacy, cross-family/model/task
generalization, learned escalation, physical GPU scaling, dynamic admission or
daemon supervision, long-soak retention, multi-host failover, hostile-host
authority custody, physical power-loss durability, arbitrary corruption repair
and external exactly-once effects. Current mailbox/checkpoint bounds do not
bound lifetime Trace growth. Trusted tool callbacks are not a general code
sandbox. Local cost/latency counters do not establish energy or dollar savings;
CPU activity overlapped some GPU runs, and timing remains diagnostic.

## Pending evidence and final decision

The [original R4 report](../r4-session-scaling-pilot-v1/RESULTS.md) retains all
264 rows: 204 complete, one `LeaseLost` abort and 59 unstarted rows. Its
`INVALID_SOURCE` disposition blocks every usable subset comparison. Known
started work retains 2,824,212 tokens, 5,891 model calls and 5,890 tool calls;
unstarted accounting remains null. The wall/monotonic discrepancy does not
establish the interruption's cause.

The full original-abort audit is pending at this draft. A [separately declared
replication](../../SCALING-replication-v1-contract.md) would attempt the unchanged
264-episode grid once with fresh ledgers, preserve all original costs, and never
pool repeated worlds as new independent units. It still requires the audited
original identity, its own freeze, collection and independent acceptance.
The new R5 Session study and final compatibility/default-policy decision remain
pending after the R4 gate. A negative efficacy result can complete a research
phase; a broken integrity or fault invariant cannot be excused as that kind of
negative result. No Stable, production or general swarm claim follows from
this draft, and historical E1/E2/E3 evidence and thresholds remain unchanged.
