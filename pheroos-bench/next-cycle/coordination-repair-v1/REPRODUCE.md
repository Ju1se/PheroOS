# Installation and reproduction

Use Python 3.12 and the repository's existing pinned validation environment. Core's retained full run used Python 3.14.7; bench/runtime used 3.12.3. All commands below are provider-free. Run from the PheroOS checkout unless stated otherwise.

## Verify retained bytes

The new publication manifest lists source, raw JSON/SQLite, logs, archives and packages directly stored in Git. Verification does not open SQLite or change WAL state:

```sh
python pheroos-bench/tools/restore_evidence_v1.py --manifest publication/coordination-repair-v1/manifest.json --root . --verify-only
```

Historical data remains in `publication/evidence-v1/`. Use its separate manifest and restoration instructions when reproducing the baseline audit. Never restore into an active database directory.

## Test both installed runtime cohorts

The tool requires installed build/pytest/numpy tooling. It installs only retained core/runtime wheels and a locally built bench wheel into a fresh temporary target, using `--no-deps`, and runs from an external directory. Missing Session integration is an error, not a skip.

```sh
python pheroos-bench/tools/verify_coordination_repair_install.py --runtime-cohort dev2 --output /tmp/repair-dev2-install.json
python pheroos-bench/tools/verify_coordination_repair_install.py --runtime-cohort dev3 --output /tmp/repair-dev3-install.json
```

Output paths must not exist. The new CI matrix runs both cohorts. Dev2 reproduces the collection environment; dev3 adds the metadata repair. The companion runtime contains complete installed wheel/sdist receipts and exact distributions under `results/coordination-repair-v1/` and `results/coordination-repair-v2/`. Its `tests/test_recorded_local_v2.py` reproduces the real authorization failure from the captured request without model weights or inference. Run the companion's `tools/verify_install.py` according to its CLI for an independent wheel/sdist rebuild check.

## Reproduce a public-tool reference episode

Install the three retained collection wheels into a fresh target. These are the actual dev2 collection bytes; no model dependency is needed:

```sh
python -m pip install --no-deps --ignore-installed --target /tmp/pheroos-repair-reference-site \
  pheroos-bench/next-cycle/coordination-repair-v1/artifacts/pheroos-0.1.0-py3-none-any.whl \
  pheroos-bench/next-cycle/coordination-repair-v1/artifacts/pheroos_runtime-0.1.0.dev2-py3-none-any.whl \
  pheroos-bench/next-cycle/coordination-repair-v1/artifacts/pheroos_bench-0.1.1.dev2-py3-none-any.whl
cd /tmp
PYTHONPATH=/tmp/pheroos-repair-reference-site python - <<'PY'
from pathlib import Path
from pheroos_bench.coordination_repair_v1 import run_episode
row = run_episode(world='interval_intersection/dev_a', arm='single', n=1,
                  condition='D2', steps=8, token_cap=10240, seed=2718,
                  model=None, output=Path('/tmp/pheroos-repair-reference-episode'))
assert row['status'] == 'VALID_KNOWN' and row['success'] is True
print(row['status'], row['success'])
PY
```

Use fresh installation/output directories; never overwrite a retained run. `provider-free/config.json` declares the full 61-episode reference design. Its original runner and nine exact source files are retained in `provider-free/frozen-source-v1.tar.xz`, with original paths and hashes in its manifest. The runner contains collection-host paths; exact campaign relocation requires an explicit isolated path mapping, preserving those original files. The example above is a new instrument replay, not another independent sample. Runtime IDs and timestamps need not be byte-identical across replays; compare declared outcomes, actions, versions and accounting semantics.

## Live collection is incomplete

Inspect `local-cycle-v1/actionability/` and the additive abort review. The only started episode has no model output; 27 others have null outcomes/costs. Do not interpret admission sentinels as a measured capability rate. The v1 pilot intentionally still names the failing v1 adapter. Do not run it as a repaired retry, patch frozen sources in place or replace model revisions silently.

A future retry needs a new runner/config/result directory that explicitly selects `recorded_local_v2`, references the original abort, preserves accounting and receives authorization for another campaign. Neither paid APIs nor new model downloads are part of this delivery. The local model identity is Qwen/Qwen2.5-Coder-3B-Instruct revision `488639f1ff808d1d3d0ba301aef8c11461451ec5`; exact tokenizer, generation, hardware and environment records remain in the frozen evidence. No credentials or model weights are distributed.
