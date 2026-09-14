# R2 capacity audit v1 — 2026-09-12

**480/480 frozen episodes and traces reproduced exactly.** Capacity reconciles
in every episode. The reserve policy is explicitly **none**: zero dedicated
reserve worker-ticks. This addendum preserves the existing R2 negative result
and adds zero independent experimental observations.

**Problem.** R2 v1 reported scheduling outcomes and costs without explicit
available, busy, idle and unavailable worker capacity.

**Hypothesis.** This is an accounting check: occupied worker-ticks must equal
recorded execution units, and available plus unavailable capacity must equal
four workers times the horizon. It introduces no performance hypothesis or gate.

**Mechanism and baselines.** The unchanged candidate deprioritizes producers
when at least two tool jobs are ready. Capability FIFO, own-queue work stealing,
deadline priority, the scarcity/deadline manager and no-backpressure ablation
retain the same tasks, resources, recovery, evaluator and budgets.

**Implementation.** The new [method](../../src/pheroos_bench/r2_capacity.py)
regenerates each frozen row and trace, requires their original identity and
hashes, and accounts each `execute_unit` over its worker's tick. It classifies
outages before execution and retains every original cost dictionary. Source
and output are frozen independently; no historical file was edited.

**Tests.** [Validation](validation.json) records 47 passing tests: 26 capacity
cases and the existing 21 R2 tests. Counterexamples cover outage boundaries,
same-tick recovery/failure, duplicate occupation, unavailable workers, corrupted
trace/episode identities, source hash mismatches, interruption and overwrite
refusal. Interrupted replay retains known source costs and reports INVALID_ABORT.

**Design.** Reanalysis of the original eight pilot seeds and 32 descriptive
evaluation seeds, two regimes and six arms. The two regimes of one seed are
not independent replications. There are no new seeds, thresholds, confidence
claims, model calls or paid calls. [Config](../../r2-capacity-audit-v1.json)
pins the seven historical portable artifacts; [freeze](freeze.json) also pins
the historical source freeze and all new implementation inputs.

**Results.** Mean worker-ticks per existing evaluation episode:

| Regime / arm | Total | Available | Busy | Idle | Unavailable | Dedicated reserve |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Bottleneck: FIFO, candidate, no-backpressure | 144 | 135 | 49.875 | 85.125 | 9 | 0 |
| Bottleneck: work stealing | 144 | 135 | 49.90625 | 85.09375 | 9 | 0 |
| Bottleneck: deadline priority | 144 | 135 | 50.0625 | 84.9375 | 9 | 0 |
| Bottleneck: central manager | 144 | 135 | 50.125 | 84.875 | 9 | 0 |
| No contention/failure: all arms | 360 | 360 | 48.65625 | 311.34375 | 0 | 0 |

[All rows](episodes.jsonl) retain per-tick counts and source costs;
[summary](summary.json) retains separate pilot/evaluation and regime groups.
`available + unavailable = total` and `busy + idle = available` throughout.
Unavailable capacity is five ticks for worker 0 plus four for worker 2.

**Negative findings.** The historical candidate/FIFO dispatch traces still
match exactly. The candidate's 3.75% extra logical scheduler operations in the
bottleneck evaluation remain an adverse result, with no throughput, deadline,
wait, recovery or byte advantage. See the unchanged [R2 report](../r2-pilot-v1/RESULTS.md).

**Confounds.** Idle capacity combines dependency, capability, tool and arrival
constraints; it is not automatically deployable spare throughput. Busy time
includes failed/repeated execution. The two regimes have different horizons,
so their capacity totals are not comparative treatment effects. Logical ticks
do not measure OS CPU utilization, physical network traffic, latency or energy.

**Not proven.** No exercised reserve-worker or adaptive recruitment policy,
new scheduler advantage, real-runtime recovery, long-soak reliability or general
absence of starvation is established. The old workload could activate pressure
without presenting a dispatch choice that differentiated candidate from FIFO.

**Next gate.** Retain R2 as a completed bounded negative research phase with
explicit capacity accounting. Continue external-runtime lifecycle and R5 fault
acceptance. If deliberately reserved workers or a different workload become
necessary, use a separate version, matched ablation and independent experiment;
do not tune this historical null into a positive result.

Provenance: base repository commit
`b154472becea561ac1f5fc442a7ccf372ab154f8`; source method
`r2_scheduling_pilot_v1`; addendum method `r2_capacity_audit_v1`. The source
implementation SHA-256 is
`c9c94622d20d165effc8139062f4fd0888205cb4ad4493afc14fe79912352d62`;
the historical freeze SHA-256 is
`79312141639c0548c731fd971281f93fb2bfa603b871f5d3ee73ca213fa3eb3c`.
The experimental files were uncommitted at the base revision; exact hashes in
the freezes, rather than that commit alone, identify the executed methods.
