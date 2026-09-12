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
