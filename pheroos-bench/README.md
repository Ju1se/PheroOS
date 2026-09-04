# PheroOS governed authority/commit protocol benchmark

This sibling repository is the executable experiment harness for PheroOS
governed authority and commit protocol experiments. It is intentionally small,
provider-free, and independent of protocol-core. E1 records a negative result
for one historical candidate-field implementation; it makes no claim of
emergent or swarm intelligence.

The dependency is pinned to the exact PheroOS commit recorded in
`experiment.json`. For local development against the checkout used to create
the lock, run with `PYTHONPATH=/Users/scottxie/Desktop/multi-agent`.

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

The current PheroOS Hybrid profile is not presented as a sixth arm: protocol-core
has no local `sense()` ABI, and this harness does not invent one or substitute a
batch evaluator. The field arm was an explicit candidate implementation under
test, and its negative result is recorded in `results/E1-negative-result.md`.
The repository's public positioning is governed authority/commit protocol, not
collective-intelligence capability.

## E2 Couzin preregistration

The independent Couzin experiment is frozen in `experiment-e2.json` with its
pre-run prediction at `results/e2/prediction.md`. It must be run in two phases:

```bash
PYTHONPATH=/Users/scottxie/Desktop/multi-agent \
  python -m pheroos_bench.e2_run --phase admission --output results/e2/admission --workers 4
PYTHONPATH=/Users/scottxie/Desktop/multi-agent \
  python -m pheroos_bench.e2_run --phase treatment --output results/e2/treatment --workers 4
```

Treatment refuses to run unless every admission cell passed and the frozen
config and source fingerprint are unchanged. The admission phase aborts with
`sys.exit(1)` on any failed cell and produces no treatment verdict.
