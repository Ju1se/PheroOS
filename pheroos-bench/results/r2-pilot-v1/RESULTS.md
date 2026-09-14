# R2: frozen scheduling experiment, 2026-09-12

Congestion backpressure provided **no improvement over capability FIFO** in this
finite workload. Their complete execution traces, completion, deadlines, waits,
retries and byte costs match. Computing pressure adds **3.75% logical scheduler
operations** in the bottleneck regime. This is a negative result for the tested
intervention; it does not justify changing the default scheduler.

The experiment completed all **480 scheduled episodes**: eight pilot seeds and
32 separate evaluation seeds, each with two workload regimes and six arms. There
were no measurement errors. This is one bounded R2 research delivery with
deterministic program agents; no LLM calls, CUDA, paid API, persistent runtime,
core contract or production recovery claim is involved.

## Independent evaluation

Each regime has 32 paired seeds and 24 declared dependency tasks per episode.
The bottleneck regime has a single inspect tool slot, four capability-constrained
workers, worker outages at ticks 7 and 17, and a 36-tick horizon. All arms have
identical workload, resource limits, exclusive claims and fault recovery.

| Arm | Tasks completed / 768 | On-time tasks / 768 | Mean episode p95 wait | Mean scheduler operations | Mean accounted bytes |
|---|---:|---:|---:|---:|---:|
| Capability FIFO | 768 | 625 (81.38%) | 8.094 ticks | 1,584.84 | 166,129.38 |
| Own-queue work stealing | 767 | 603 (78.52%) | 9.125 ticks | 1,593.78 | 166,862.69 |
| Deadline priority | 768 | 620 (80.73%) | 8.125 ticks | 1,591.53 | 166,608.25 |
| Central scarcity/deadline manager | 767 | 632 (82.29%) | 7.563 ticks | 1,761.69 | 166,745.88 |
| Congestion backpressure | 768 | 625 (81.38%) | 8.094 ticks | 1,644.31 | 166,129.38 |
| No-backpressure ablation | 768 | 625 (81.38%) | 8.094 ticks | 1,584.84 | 166,129.38 |

Tasks are denominators for descriptive completion counts; they are **not**
independent statistical samples. Pairing is at the seed level within each
regime. The two regimes of a seed are not counted as independent replications.
The p95 column averages each episode's nearest-rank p95 ready-wait metric.

Candidate minus FIFO: all performance and accounted-byte differences are zero;
mean scheduler operations increase by 59.47. Candidate mean throughput is
24/36 = 0.667 completed tasks per tick. It retries 29 interrupted claims over
32 episodes, with 1.219 lost execution units per episode and 0.207 mean logical
ticks from revocation to reassignment. All revocations recover; no simultaneous
duplicate claims, capability violations or tool-slot excesses occurred. The
finite-horizon starvation proxy is zero across every evaluated arm, which does
not establish absence of starvation in arbitrary workloads.

The manager completes more tasks before deadline in this sample but leaves one
task unfinished at the horizon. These are paired descriptive results, not a
statistical winner declaration or a reason to select a new default.

In the no-contention/no-failure regime, every arm completes all 768 tasks before
their deadlines, with zero ready waiting, retries and recovery events. Pressure
never activates. Candidate and FIFO again have identical trajectories; merely
checking pressure adds 24 operations per episode (0.81%). The horizon is 90 ticks
for spaced arrivals, so throughput or byte costs should not be compared across
regimes as if they had the same timing conditions.

Pilot and evaluation remain separate in the [summary](summary.json). No result
was used to tune the frozen policy, thresholds, workload or reporting rules.

## What the null result means

Congestion occurs in the bottleneck worlds. However, the arrival/dependency
structure already causes FIFO to order producers and downstream work so that
deprioritizing producers does not change dispatch. All generated candidate
traces match FIFO, including pilot. A separate constructed invariant test proves
that the implemented pressure rule can change dispatch when the observable queue
presents the relevant choice. The null is a limitation of this workload's ability
to distinguish the intervention, not evidence that backpressure can never help.
Any alternative workload needs a new frozen version and independent seeds.

## Evidence and validation

- [Freeze](freeze.json): SHA-256 of source, configuration, tests and data contract,
  plus Python/platform, written before either split executes.
- [All episodes](episodes.jsonl): 96 pilot and 384 evaluation rows; incomplete and
  late tasks remain in every denominator and cost total.
- [Summary](summary.json): stratified means, paired candidate-minus-control
  differences, logical scheduler costs, communication/encoding/state-write bytes.
- [Representative traces](sample-traces.json): every arm and regime for the first
  seed in each cohort; all other traces reproduce from the recorded seeds.
- [Audit](audit.json): all 480 episodes reproduce exactly. Every regenerated trace
  independently checks capabilities, dependency completion, exclusive claims,
  lease generations, tool capacity and exact output values. Workload hashes match
  across arms, frozen hashes remain unchanged, and all model/token counts are zero.
- [Validation](validation.json): **144 tests passed**, including 21 R2 tests plus
  R1 and relevant R0/E3 measurement/statistics regression tests.

From `pheroos-bench`, reproduce into a new directory:

```bash
PYTHONPATH=src /tmp/pheroos-wsl2-bench-env/bin/python -m pheroos_bench.r2_scheduling \
  --config r2-pilot-v1.json --output results/r2-reproduction-new
```

The [data contract](../../R2-data-contract.md) defines the complete logical cost
model. These counts are not CPU time, monetary spend or measurements of a
distributed network. Work stealing is an own-queue-first selection rule within
the same deterministic dispatcher; every arm has equal snapshot access and
reasonable recovery. The experiment has no powered noninferiority/superiority
gate and makes no production OS, sustained-starvation or real-model claims.
