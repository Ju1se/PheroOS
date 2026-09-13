# G1 WSL2 replication — 2026-09-11

The frozen mock runtime `b3c0d4977c466c02a200d4fe63857682de53ddfd` and core
`b4845e5972e74425af55ad9f306b17535957c68d` pass on WSL2 with Python **3.14.7**.
No implementation or original macOS result was changed.

- Installed runtime tests: **43 passed in 27.84s**.
- Independent wheel installation: **43 passed in 27.82s**.
- Independent sdist installation: **43 passed in 28.56s**.
- Four-worker blackboard CLI: **13 completed tasks, result 204, actual/reserved/unknown units 26/0/0**, all worker exit codes zero.

`g1-install-acceptance.json` comes from the unchanged frozen
`tools/verify_install.py`; `g1-semantic-comparison.json` checks the common
semantic fields against the published macOS acceptance. `demo-snapshot.json`
preserves a separate fresh CLI run. Runtime/bench have separate environments;
the runtime environment contains only installed frozen core/runtime wheels and
the recorded development tools.

`commands.jsonl` records argv, cwd, selected environment overrides, elapsed time,
and exit status for every acceptance command. Corresponding stdout/stderr logs
are retained. `sources.json` contains fixed Git archive revisions and hashes.
`python.stdout.log`, `packages.stdout.log`, `kernel.stdout.log`,
`os-release.stdout.log`, `cpu.stdout.log`, and `installed-paths.stdout.log`
record the new environment, including SQLite 3.53.1.

Dependencies were copied offline from the existing Python 3.14.7 development
environment's distribution inventories into an isolated venv, as detailed in
`offline-bootstrap.json`. No editable installs or inherited system packages
are used. `pip-check.stdout.log` reports no broken requirements. The historical
macOS patch version and full development dependency lock are unavailable; this
is the new environment's provenance.

`artifacts/` and `artifact-hashes.json` retain the exact core wheel and runtime
wheel/sdist used by the final installation acceptance. The unchanged install
verifier rebuilds runtime distributions, so the initial bootstrap-installed
wheel digest in `packages.stdout.log` differs from the later acceptance wheel
digest. Both builds use the same frozen source. `verify-build-artifacts/`
records an intermediate copy of the verifier's build artifacts, with its own
hash report.

The local driver was run as:

```bash
/home/scott/projects/PheroOS/.venv/bin/python replication/wsl2-20260911/run_g1_replication.py bootstrap
/home/scott/projects/PheroOS/.venv/bin/python replication/wsl2-20260911/run_g1_replication.py acceptance
```

It refuses existing frozen source/output paths. Use new paths for a new run.
These checks use no models or CUDA. Agreement supports only the tested mock
configurations and failure boundaries; timing differences and new artifact
hashes are expected and do not establish universal hardware independence.
