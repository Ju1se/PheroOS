# PheroOS governed authority/commit protocol benchmark

This separately packaged harness is maintained under `pheroos-bench/` in the
PheroOS repository. It is not part of the protocol-core distribution. E1/E2
are deterministic, provider-free simulations; the opt-in E3 runner makes
model API calls and belongs only to this research package. E1 records a negative result
for one historical candidate-field implementation; it makes no claim of
emergent or swarm intelligence.

The dependency is pinned to the exact PheroOS commit recorded in
`experiment.json`; it is not an instruction to substitute the latest core.
The wheel and sdist include byte-identical copies of the frozen E1/E2 configs.
The original files and historical results remain unchanged.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m pheroos_bench.run --mode pilot --output results/pilot
python -m pheroos_bench.run --mode confirmatory --output results/confirmatory
```

Pilot output is explicitly void and never enters the verdict. Confirmatory
output contains one canonical JSON record per seed/arm/density, a CSV summary,
an SVG density curve, and `verdict.json`. All arms use the same canonical JSON
codec, the same route/value wire granularity, and count encoded observations,
actions, reads, writes, and coordinator messages. Exploration is frozen at
`epsilon=0.0` for every arm. Field writes and reads are not free communication.

The first benchmark is a weighted route-cell environment. Agents see only
their local ring of route cells. The field arm uses a four-shard logical
environmental store and local sensing; the stateless arm sees the same local
observations without persistent memory, diffusion, or evaporation. Every arm
loses 25% of its agents for the resource fault. In the second 30-step window,
the centralized arm loses its coordinator, the field arm loses shard 0, and the
matched local controls lose the same agent quarter; failed field writes remain
counted. No replication is assumed.

The historical PheroOS Hybrid scoring path is not presented as a sixth arm: protocol-core
has no local `sense()` ABI, and this harness does not invent one or substitute a
batch evaluator. The field arm was an explicit candidate implementation under
test, and its negative result is recorded in `results/E1-negative-result.md`.
The repository's public positioning is governed authority/commit protocol, not
collective-intelligence capability.

## E2 Couzin preregistration

The independent Couzin experiment is frozen in `experiment-e2.json` with its
pre-run prediction at `results/e2/prediction.md`. It must be run in two phases:

```bash
python -m pheroos_bench.e2_run --phase admission --output results/e2/admission --workers 4
python -m pheroos_bench.e2_run --phase treatment --output results/e2/treatment --workers 4
```

Treatment refuses to run unless every admission cell passed and the frozen
config and source fingerprint are unchanged. The admission phase aborts with
`sys.exit(1)` on any failed cell and produces no treatment verdict.

Packaging fixes change the E2 source fingerprint, not its frozen config or
historical results. The current runner must not resume treatment against a
historical admission fingerprint; reproduce historical runs at their recorded
tag instead. These commands describe the phases, not authorization to rerun a
closed experiment or overwrite its evidence.

## E3 records and validation

See [E3 data contract](E3-data-contract.md) before collecting or evaluating
records. The current runner implements **admission and void pilot only**; it
does not implement adaptive treatment or establish a confirmatory result.
Tests use synthetic records and mocked HTTP calls, never paid provider calls.

New analyses explicitly declare `statistics.estimand="paired_item_mean_v1"`.
Admission and superiority intervals use paired item means; zero-width
intervals cannot automatically pass. Existing median-based results must retain
their original method. The [prediction draft](results/e3/prediction.md) is
**not frozen** and lists the remaining design decisions.

Use `pheroos-bench-e3-llm --items items.jsonl --dry-run` to preview one arm
without provider calls. Live collection requires `--output` and `--max-calls`.
This is a call-count limit, not a dollar limit; actual usage is retained when
collection aborts.

## R0 instrument checks

The [R0 data contract](R0-data-contract.md) adds a separate
`r_paired_world_mean_v1` instrument-only entry. It pairs independent worlds,
averages repetitions within worlds, retains legitimate flat cells, and aborts
on missing/duplicate records or unknown costs. It reuses the existing mean
bootstrap arithmetic; E3's historical gates are unchanged.

```bash
pheroos-bench-r0 --config config.json --records episodes.ndjson --output report.json
python -m pheroos_bench.r0_self_check --output synthetic-checks.json
```

`r0_runtime.reconcile_snapshot` independently reconciles G1's per-call and
event accounting. An optional external-runtime capture tool is under
`tools/capture_r0_runtime.py`; it requires the separately installed mock runtime.
Neither R0 entry invokes a paid provider or produces a treatment verdict.

The [WSL2 replication record](results/r0-replication/wsl2-20260911/RESULTS.md)
compares the frozen Mac evidence with fresh execution on the RTX 5070 laptop.
`tools/compare_r0_replication.py` checks the fixed G1 DAG, receipt bindings,
causal ordering and cancellation semantics before normalizing execution IDs.
It is an acceptance tool, not a new measurement method or treatment gate.

## R1–R5 finite experiments

The [Session capability diagnostic](R3-session-capability-v1-contract.md) adds
two pinned local model sizes through the separately installed experimental
runtime. The [R4 scaling design](R4-session-scaling-v1-contract.md) separates
logical agent count, model capability, token scarcity and deadlines. These are
pilot mechanisms and measurement infrastructure; their results do not promote
coordination policies into protocol-core or establish swarm efficacy.

The [original R4 collection](results/r4-session-scaling-pilot-v1/RESULTS.md)
remains `INVALID_ABORT`: 204 complete episodes, one LeaseLost episode and
59 unstarted rows. Its [independent abort audit passed](results/r4-session-scaling-pilot-v1/ABORT-AUDIT-ADDENDUM.md),
preserving 2,824,212 known tokens and the original null/INVALID accounting;
the interruption cause remains undetermined. The single
[separately frozen replication](results/r4-session-scaling-replication-v1/RESULTS.md)
completed the unchanged 264-episode grid and passed the
[R4 engineering/measurement gate](results/r4-session-scaling-replication-v1/GATE-ADDENDUM.md).
It retains 3,402,842 tokens, giving 6,227,054 known tokens across both attempts;
the original null rows remain explicit. All 56 policy exports are descriptive,
every quality interval includes zero, and no general coordination advantage is
demonstrated. Original rows are neither repaired nor pooled as new worlds.

The [38-case Session fault study](results/r5-session-faults-v1/RESULTS.md) also
passed its [bounded R5 gate](results/r5-session-faults-v1/GATE-ADDENDUM.md).
It retains 18 known synthetic tokens and 70 unknown tokens in ten calls, plus
unavailable accounting for a damaged copy. Passing includes unresolved and
fenced outcomes; it does not mean universal recovery or production robustness.
The original failed audit and narrow offline correction remain preserved.

The [master-goal phase map](MASTER-GOAL-status.md) tracks the evidence-driven
OS research target separately from current supported interfaces. The
[initial gate audit](results/master-goal-audit-v1/report.json) binds current
starting evidence. The [master report](results/master-goal-audit-v1/FINAL-REPORT.md)
now records the completed finite phases and [accepted finite consumer](results/master-goal-audit-v1/consumer-exit-decision-v1.md).
Its exact packages and installation instructions are [persistently archived](results/master-goal-audit-v1/consumer-artifacts-v1/INSTALL.md);
the [final preservation check](results/master-goal-audit-v1/final-integrity-v1.json)
passes 3,588 unique retained file identities. The [final root acceptance](results/master-goal-audit-v1/MASTER-ACCEPTANCE-v1.json)
completes the experimental candidate, including a fresh offline archive install
and provider-free two-agent journey. No model or coordination policy is promoted.

[R1 coordination v2](R1-coordination-v2-contract.md) adds a separate experimental,
pilot-only runner with dedup+TTL and version-aware baselines, component ablations,
delivery-aware suppression, and pairwise `r_paired_world_mean_v1` exports. Run
`python -m pheroos_bench.r1_coordination --config r1-coordination-pilot-v2.json
--output results/r1-coordination-pilot-v2` from this directory. The v1 freeze
and evidence remain unchanged; no pilot result counts toward confirmation.

The separately frozen [R1 signal experiment](results/r1-pilot-v1/RESULTS.md)
and [R2 scheduling experiment](results/r2-pilot-v1/RESULTS.md) retain all paired
worlds and negative results. Their candidates do not improve on the competent
simple baselines in these workloads, so neither becomes a default policy.
The [R2 capacity addendum](results/r2-capacity-audit-v1/RESULTS.md) reconciles
worker occupancy without adding independent observations. The
[R3 format audit](results/r3-format-audit-v1/GATE-REPORT.md) diagnoses the
frozen tool pilot's action-format failures without changing its outcomes.

The [R3 contract](R3-data-contract.md) defines a small real-model pilot with
closed task fixtures, public/hidden verification, five context-sharing controls,
and one total token cap per episode. Run `python -m pheroos_bench.r3_pilot --help`
for its explicit external-runtime interpreter and local-model inputs. Model
dependencies, GPU execution and token reservations belong to the independent
runtime. The [first GPU pilot](results/r3-pilot-v1/RESULTS.md) completed all 80
calls with known costs, but did not demonstrate useful semantic improvement
from shared work. These finite experiments do not establish swarm efficacy
or replace the existing E-series contracts.

## Package checks

From this directory:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

CI installs hash-locked test dependencies separately from the core. Tests build
both distributions in clean temporary trees, install them outside the source
directory, load both default configs, and compare the installed E2 fingerprint
with the source fingerprint. They do not run a full experiment.
