# R2 capacity audit v1

Method `r2_capacity_audit_v1` adds explicit capacity accounting to the frozen
`r2_scheduling_pilot_v1` experiment. It is retrospective instrumentation, adds
zero independent worlds, and never counts toward an efficacy verdict. The
historical null result and all its source, config, tests, contract and artifacts
remain unchanged. The configured base commit is
`b154472becea561ac1f5fc442a7ccf372ab154f8`; uncommitted experimental source is
identified by content hashes, not by that commit alone.

The new config pins all seven historical portable artifacts. Before replay,
the audit verifies those hashes and every source hash in the historical freeze,
and validates the complete declared 480-episode grid. Every regenerated episode
must equal its stored row, and every regenerated trace must match its stored
SHA-256. The first disagreement writes an `INVALID_ABORT` row, retaining known
historical costs and identifying capacity measurement as unknown; analysis stops.
Invalid input and interruption produce an `INVALID_ABORT` summary, never a
performance failure or a valid surviving subset. Original costs are neither
replaced by replay instrumentation costs nor inferred to be zero.

One `execute_unit` occupies its worker over `[tick, tick + 1)`. For each tick,
the exact frozen semantics first remove outages whose recovery tick has arrived,
then apply failures, then schedule work. Failure and recovery trace events must
match that schedule. A failed worker is unavailable even when it had no running
task. Duplicate execution by one worker in one tick, execution outside the
horizon, and execution by an unavailable worker are invalid.

All four workers are classified at each tick:

```text
available + unavailable = 4
busy + idle = available
sum(busy) = recorded execution_units
sum(available + unavailable) = 4 * horizon
```

The bottleneck schedule makes worker 0 unavailable on ticks 7–11 and worker 2
on ticks 17–20: nine unavailable worker-ticks. The no-failure regime has zero.
Completed events carry the next tick's boundary; occupancy is therefore derived
from `execute_unit`, not inferred from naive event timestamp ordering.

The reserve policy is **none**, with zero dedicated reserve worker-ticks in
every arm. Idle capacity means available workers without an execution unit;
it can arise from dependencies, capability/tool limits or lack of arrived work.
It is not a deliberately reserved workforce, measured spare throughput, or proof
of an adaptive recruitment policy. Retries consume busy ticks just like useful
execution; existing duplicate/lost-execution costs remain separately available.

All six frozen policies, workloads, budgets, horizons, faults and evaluators are
reused unchanged. Source cost dictionaries and zero LLM/token usage are retained;
this audit makes zero provider or paid calls. Logical worker-ticks are not CPU,
wall-time or energy measurements. The two regimes for a seed are not additional
independent replications. Summaries preserve pilot/evaluation and regime strata;
they introduce no interval, threshold, winner selection or new efficacy claim.

Run from `pheroos-bench` into a new directory:

```bash
.venv/bin/python -m pheroos_bench.r2_capacity \
  --config r2-capacity-audit-v1.json --output results/r2-capacity-audit-v1
```

The CLI creates output exclusively, hashes the method, config, tests, contract
and bound historical inputs before replay, flushes each row, and verifies hashes
again before a `VALID_RETROSPECTIVE_AUDIT` summary. Later reproductions require
new output directories. A genuinely exercised reserve-worker intervention or
changed workload requires its own version, ablation and independent experiment;
this addendum does not provide one.
