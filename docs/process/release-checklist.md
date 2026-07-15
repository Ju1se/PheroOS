# Release Checklist

Use this checklist before publishing a PheroOS protocol-core release.

## Scope Check

- [ ] The release keeps protocol-core small, deterministic, domain-neutral, and provider-free by default.
- [ ] No app runtime, provider gateway, dashboard, database, queue, worker pool, or server infrastructure was added.
- [ ] New executable code lives under an allowed surface: protocol, kernel, governance, drivers, trace, conformance, CLI, examples, or tests.
- [ ] New abstractions are directly exercised by tests, examples, or conformance.
- [ ] Baseline protocols are not forced to opt into optional swarm behavior.
- [ ] Baseline and Hybrid v1 protocols are not forced to opt into Optimal Commit.

## API and ABI Check

- [ ] Public package exports are intentional.
- [ ] Schema helpers and checked-in schema artifacts match.
- [ ] `schemas/capability.schema.json` reflects the full manifest loader contract.
- [ ] CLI behavior remains thin and delegates to core packages.
- [ ] Manifest changes include validation and conformance impact notes.
- [ ] Conformance profile version changes are documented.
- [ ] Manifest extensions preserve metadata without allowing secrets or authority bypass.
- [ ] Compatibility aliases are documented when present.
- [ ] Breaking changes include migration notes.
- [ ] Commit Wire covers every public record branch and the checked-in artifact
  matches the runtime schema exactly.
- [ ] Active Commit profiles have every required check registered; skip/N/A and
  implicit assurance downgrade paths are zero.
- [ ] Public `CommitAssurance`, `CommitAction`, and `TraceEvent` have one
  canonical owning type.

## Documentation Check

- [ ] `README.md` reflects current examples, conformance checks, and trace events.
- [ ] `SPEC.md` reflects current protocol-core surfaces.
- [ ] `docs/process/api-lifecycle.md` reflects current stability and compatibility rules.
- [ ] `docs/protocol/extension-points.md` reflects current extension boundaries.
- [ ] `CHANGELOG.md` has an entry for the release.
- [ ] Optimal Commit invariants, bounded liveness, output semantics, and
  migration requirements are documented when the feature is present.

## Validation

- [ ] Deterministic tests pass in CI.
- [ ] Baseline protocol compatibility is checked.
- [ ] Governed e2e protocol compatibility is checked.
- [ ] Swarm protocol compatibility is checked when swarm behavior is declared.
- [ ] Checked-in schema artifacts match exported ABI schema behavior.
- [ ] The complete 38-case Commit TCK and all declared variants pass from source.
- [ ] Commit TCK, schemas, conformance, and provider-free examples pass from an
  isolated wheel and an external working directory.
- [ ] Every terminal Commit outcome is deliverable; publication/execution and
  distributed conflict gates have negative coverage.
- [ ] Formatting and whitespace checks pass.

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
