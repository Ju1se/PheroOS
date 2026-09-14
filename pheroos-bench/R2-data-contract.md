# R2 deterministic scheduling pilot

Version: `r2_scheduling_pilot_v1`. Descriptive simulation only; no efficacy gate,
no live models, no new core ABI, and no production runtime recovery claim.

Each seed declares eight three-stage dependency chains (24 tasks), arrivals,
capability requirements, service durations, deadlines, and a single scarce tool
slot. Worker capabilities are compute+inspect, compute, inspect, compute: the
manager can observe that inspect has fewer capable workers. The bottleneck world stops worker
0 at tick 7 until 12 and worker 2 at tick 17 until 21. The negative-control world
spaces arrivals apart and has no failures. All six arms receive identical jobs,
resources, observations, checking, and fault recovery for a paired world/seed.

The arms are capability FIFO, own-queue-first work stealing, earliest-deadline
priority, a deterministic manager that prefers tasks with fewer capable workers,
FIFO with tool-queue backpressure, and the same candidate without backpressure.
Backpressure only lowers producer priority when at least two tool tasks are
ready. It uses observable queue state, not future outcomes or checker answers.
All arms scan past blocked jobs and remain work conserving. The no-pressure
ablation intentionally equals capability FIFO and must reproduce its trace.

Tasks are claimed exclusively. Dependencies must complete before dispatch.
Failures revoke the current lease, preserve consumed work cost, reset remaining
service, and permit immediate reassignment to another compatible worker. Lease
generations increase on revocation/reassignment. Retry waste is reported
separately from forbidden simultaneous duplicate execution. This is a logical
simulator; it does not test OS processes, persistent stores, or external effects.

At each tick, completion is recorded at the following boundary. Every declared
task contributes to completion and deadline fractions, including unfinished
tasks. Throughput is verified completions divided by the fixed world horizon.
p95 wait is nearest-rank cumulative ready-but-not-running ticks among tasks that
became ready; unfinished waits are right-censored at the horizon and retained.
Pending dependency-blocked/unarrived counts are separate. The starvation proxy
counts tasks that became ready but never started by the horizon; it cannot prove
infinite starvation. Recovery delay measures revoked-task-to-next-dispatch ticks,
including zero when another worker can immediately reclaim; unresolved failures
are retained. Completed output values are recomputed by an independent checker.

The complete **declared logical cost model** charges one scheduling snapshot per
tick, one unit per task/worker state record, eligibility inspection, policy score,
pressure inspection, manager capability inspection, event message, snapshot
message, and mutable state record write. State writes serialize task records,
running/offline maps and completed results after their transitions. Communication
bytes are actual canonical JSON UTF-8 sizes of snapshots
and all events, including declarations, execution units and recovery. Execution
and lost/repeated units are separate. Encoding bytes include every serialized
snapshot, message and state write. Total accounted bytes sum communication,
state writes and encoding; repeated stage traffic is intentionally counted.
Zero model calls/input tokens/output tokens are recorded explicitly. These units do not estimate CPU instruction
counts, network architectures, or real scheduler latency. All policies run in one
deterministic dispatcher; work stealing names a selection rule, not a distributed
deployment. Common snapshot delivery costs are charged equally.

Code, tests, configuration and this contract are hashed before pilot seeds 0–7
or separate evaluation seeds 100–131 execute. Final development checks use seeds
903/911/937; the inherited draft had included seed 3 in a test, so no claim is
made that every pilot seed is unseen. Evaluation seeds remain untouched before
freezing. Each seed runs both regimes; reports stratify by regime and never treat
tasks or the two versions of a seed as extra independent samples.
No policy changes or selection occur between pilot and evaluation. Evaluation
remains descriptive; no superiority/noninferiority threshold or promotion rule
is defined. The independent unit is the seed within a world, never a task or
worker. Summaries report means across whole episodes, paired candidate-minus-arm
differences, and pooled descriptive recovery delays; they are not inferential
confidence claims.

Raw episodes preserve exact workload/trace hashes, outputs, all metrics and
costs. Full traces for each arm/world at the first seed of each cohort are kept;
the remaining traces are reproducible from the frozen source and seed. Output
directories and files are created exclusively and prior results are not overwritten.
Each scheduled episode is appended and flushed to `episodes.jsonl`; an exception
produces an explicit error row and invalidates performance analysis. Missing or
duplicate episode identities are invalid. Partial task completion and late tasks
remain valid measured outcomes in the complete episode denominator and costs.

```bash
python -m pheroos_bench.r2_scheduling --config r2-pilot-v1.json --output results/r2-pilot-v1
```

The runner writes `freeze.json` with source/config/test/contract SHA-256 hashes
and Python/platform before either split runs, then verifies hashes after execution.
No R0, R1, E1, E2 or E3 outcome is rewritten by this experiment.
