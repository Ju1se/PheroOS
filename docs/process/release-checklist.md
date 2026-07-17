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
- [ ] Public facades remain cohesive; private engine dependencies are one-way,
  acyclic, free of aggregate-facade back-imports and hidden runtime registries,
  and preserve canonical public identity.
- [ ] Schema helpers and checked-in schema artifacts match.
- [ ] Frozen Capability, Protocol, Driver, and Kernel v1 schema roots are
  unchanged; new semantics use versioned IDs and exact reader dispatch.
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
- [ ] `README.md` and `README.zh-CN.md` describe the same maintained entry
  points and current ABI behavior.
- [ ] `SPEC.md` reflects current protocol-core surfaces.
- [ ] `docs/process/api-lifecycle.md` reflects current stability and compatibility rules.
- [ ] `docs/protocol/extension-points.md` reflects current extension boundaries.
- [ ] `CHANGELOG.md` has an entry for the release.
- [ ] Optimal Commit invariants, bounded liveness, output semantics, and
  migration requirements are documented when the feature is present.

## Validation

- [ ] Deterministic tests pass in CI.
- [ ] Python 3.12, 3.13, and 3.14 matrix jobs pass without version-specific
  exclusions or downgraded conformance behavior.
- [ ] Critical Ruff checks (`E9`, `F63`, `F7`, `F82`) and incremental Mypy
  checks pass for the stable scope, Driver, Kernel, and report boundaries.
- [ ] Baseline protocol compatibility is checked.
- [ ] Governed e2e protocol compatibility is checked.
- [ ] Swarm protocol compatibility is checked when swarm behavior is declared.
- [ ] Checked-in schema artifacts match exported ABI schema behavior.
- [ ] `python scripts/generate_schema_artifacts.py --check` verifies all four
  frozen v1 roots and all four generated v2 artifacts.
- [ ] The complete 38-case Commit TCK and all declared variants pass from source.
- [ ] Commit TCK, schemas, conformance, and provider-free examples pass from an
  isolated wheel and an external working directory.
- [ ] The wheel and sdist are both built without an unpinned isolated resolver,
  installed into separate environments, exercised outside the source working
  directory, and pass `pip check`; those exact validated bytes are the only
  inputs accepted by the SBOM and provenance jobs.
- [ ] A second build with the same locked toolchain and `SOURCE_DATE_EPOCH`
  produces byte-identical wheel and normalized sdist artifacts; CI compares
  exact filenames and SHA-256 digests before external installation.
- [ ] TCK v2 passes through both the public reference adapter and independent
  JSONL spec model; echo, constant, malformed, out-of-order, timeout, and
  cross-request-state adapters all fail closed.
- [ ] Scope isolation, concurrent idempotency, authority restart/rehydration,
  CAS conflict, failure injection, atomic state-plus-Trace, and retirement
  cardinality gates pass.
- [ ] `python scripts/check_reference_performance.py --check --quick` passes;
  a baseline refresh has not raised a hard-coded ceiling.
- [ ] Every terminal Commit outcome is deliverable; publication/execution and
  distributed conflict gates have negative coverage.
- [ ] Formatting and whitespace checks pass.
- [ ] `python -m pytest -q tests/test_documentation_links.py` passes.

## Supply Chain and Provenance

- [ ] Every GitHub Action `uses:` reference is a reviewed full 40-character
  commit SHA; mutable tags are comments only and never execution references.
- [ ] Workflow default permissions remain `contents: read`; only the trusted
  main-branch provenance job receives `id-token: write` and
  `attestations: write` plus the required `artifact-metadata: write`.
- [ ] `requirements/ci-constraints.txt` contains exact, sorted CI-only tool
  pins, and `requirements/ci-constraints.sha256` matches it. Core runtime
  dependencies remain empty.
- [ ] `python scripts/check_ci_supply_chain.py --check` and the offline
  workflow-policy tests pass.
- [ ] Release output contains both CycloneDX 1.6 and SPDX 2.3 SBOMs, and every
  wheel/sdist entry contains the exact SHA-256 of the uploaded artifact.
- [ ] Reproducible release timestamps use the ZIP-safe 1980 epoch
  (`SOURCE_DATE_EPOCH=315532800`), never a pre-1980 value.
- [ ] A trusted push to `main` produces GitHub build provenance plus CycloneDX
  and SPDX attestations bound to the exact distribution bytes downloaded from
  the read-only `supply-chain` job; the provenance job must not rebuild its own
  subjects. A pull request, including a fork PR, skips only attestation and
  still runs all read-only validation jobs.

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
- [ ] Download the CI release artifact, verify both SBOMs, and verify GitHub
  attestations before publishing the exact attested wheel and sdist.
