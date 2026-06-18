# Release Checklist

Use this checklist before publishing a PheroOS protocol-core release.

## Scope Check

- [ ] The release keeps protocol-core small, deterministic, domain-neutral, and provider-free by default.
- [ ] No app runtime, provider gateway, dashboard, database, queue, worker pool, or server infrastructure was added.
- [ ] New executable code lives under an allowed surface: protocol, kernel, governance, drivers, trace, conformance, CLI, examples, or tests.
- [ ] New abstractions are directly exercised by tests, examples, or conformance.
- [ ] Baseline protocols are not forced to opt into optional swarm behavior.

## API and ABI Check

- [ ] Public package exports are intentional.
- [ ] Schema helpers and checked-in schema artifacts match.
- [ ] CLI behavior remains thin and delegates to core packages.
- [ ] Manifest changes include validation and conformance impact notes.
- [ ] Compatibility aliases are documented when present.
- [ ] Breaking changes include migration notes.

## Documentation Check

- [ ] `README.md` reflects current examples, conformance checks, and trace events.
- [ ] `SPEC.md` reflects current protocol-core surfaces.
- [ ] `docs/process/api-lifecycle.md` reflects current stability and compatibility rules.
- [ ] `docs/protocol/extension-points.md` reflects current extension boundaries.
- [ ] `CHANGELOG.md` has an entry for the release.

## Validation

Run:

```bash
python -m pytest -q
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol
python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
python -m pheroos.cli.main conformance examples/e2e-protocol
python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
python -m pheroos.cli.main conformance examples/swarm-protocol
git diff --check
```

If the console script is installed, the `pheroos` command may be used instead of `python -m pheroos.cli.main`.

## Release Metadata

- [ ] `pyproject.toml` version is correct.
- [ ] `pheroos.__version__` matches the package version.
- [ ] License and project URLs are correct.
- [ ] GitHub Actions pass.
- [ ] The git worktree contains no accidental local files, secrets, caches, generated reports, or virtual environments.

## Publishing

- [ ] Create a release branch or tag.
- [ ] Include changelog notes.
- [ ] Include migration notes for any draft ABI changes.
- [ ] Confirm examples remain provider-free and network-free.
