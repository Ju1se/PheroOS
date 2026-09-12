# R0 measurement contract

Version: `r_paired_world_mean_v1`. Phase: `instrument_check` only.
R0 tests instrumentation and never returns a treatment PASS/FAIL verdict.
E1/E2/E3 records and rules remain under their own versions.

`r0_measurement.analyze(rows, config)` returns `VALID_MEASUREMENT` or
`INVALID_ABORT`. It reuses the existing public paired differences and bootstrap
arithmetic with `statistic="mean"`. It does not call the E3 admission/verdict
or E3's flat-cell rejection.

## Declared grid and sampling unit

Configuration has exactly these fields:

```json
{
  "method_version": "r_paired_world_mean_v1",
  "phase": "instrument_check",
  "arms": ["control", "candidate"],
  "world_ids": {"task-family": ["world-1", "world-2"]},
  "repetitions": 3,
  "cost_unit": "call_units",
  "budget_cap": 26,
  "confidence": 0.95,
  "bootstrap_resamples": 10000,
  "seed": 37
}
```

Every declared `(cell, world_id, repetition, arm)` must appear exactly once;
repetition is zero-based. World IDs are distinct within each cell. Pairing uses
both cell and world ID, never agent ID. Each record has exactly:

```json
{
  "record_version": "r_episode_v1",
  "phase": "instrument_check",
  "cell": "task-family",
  "world_id": "world-1",
  "repetition": 0,
  "arm": "candidate",
  "outcome": "success",
  "cost": 2,
  "unknown_cost_units": 0
}
```

Outcomes are `success`, `failed`, `timeout`, `rejected`, `cancelled`. Success
maps to quality 1 and every other terminal outcome to 0. All episodes contribute
their actual known costs. Missing or unfinished measurement is not a zero-cost
failure. Costs and unknown units are nonnegative integers; booleans are invalid.
Unknown units abort analysis while preserving known accounting diagnostics.
Observed budget overruns are retained and counted, not dropped from the sample.
The cap is descriptive here; G1's execution store enforces reservations.

The estimand is the mean of candidate-minus-control differences in per-world
means. Repetitions are averaged inside worlds before resampling. Bootstrap
samples worlds within each cell, retaining its declared number of worlds.
Thus worlds have equal weight; a cell with more worlds has proportionally more
weight. Merely repeating episodes cannot increase the number of independent
worlds. This is not a model-drift or full hierarchical power analysis.

Single-cell and flat-cell data are legal. A zero-width interval is reported as
`INSUFFICIENT_RESOLUTION`; this does not turn valid observations into malformed
data or establish efficacy. The interval is two-sided percentile bootstrap.
R0 contains no admission threshold, superiority rule or confirmatory gate.

## Execution ledger reconciliation

`r0_runtime.reconcile_snapshot` is a G1 mock snapshot consistency check.
It recomputes call costs and retained reservations against ordered events,
then compares them with reported totals. An unresolved dispatched call can
be a valid ledger state but cannot become a fully known episode cost.
It does not authenticate evidence, grant authority, or verify storage against
tampering by the trusted host.

```bash
pheroos-bench-r0 --config config.json --records episodes.ndjson --output report.json
python -m pheroos_bench.r0_self_check --output synthetic-checks.json
```

Invalid records or JSON produce a saved `INVALID_ABORT` report and exit 2.
Output creation is exclusive. Existing results are never overwritten.
The synthetic checks include 30 wins/5 losses/65 ties and the sparse 2/180
counterexample. All results explicitly have `counts_toward_verdict=false`.
Dollar pricing, live LLM sampling, R1–R5 experiments and confirmatory thresholds
remain outside this instrument contract.
