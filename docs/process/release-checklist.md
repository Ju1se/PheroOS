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
- [ ] The static Schema Catalog has no missing/orphan artifact, duplicate
  path/`$id`/CLI alias, factory-byte drift, or incomplete reader/validator
  declaration.
- [ ] Frozen Capability/Protocol v1 and v2, Driver/Kernel v1, and scoped-Trace
  v1 roots are unchanged; new semantics use versioned IDs and exact dispatch.
- [ ] Authority v2 and scoped-authority TCK v2 use their new IDs; portable
  records do not grant StateStore currentness or Governance authority.
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
- [ ] `python scripts/check_engineering_baseline.py --check` passes; Ruff,
  Mypy, C901, runtime-dependency, and test-floor metrics did not regress, and
  public/schema/TCK/performance roots changed only through an audited refresh.
- [ ] `python scripts/check_legacy_authority_inventory.py --check` passes; the
  recursive legacy registry importer, namespace, cursor, and sentinel
  inventories have not expanded, and any removal was recorded with the
  shrink-only writer.
- [ ] Baseline protocol compatibility is checked.
- [ ] Governed e2e protocol compatibility is checked.
- [ ] Swarm protocol compatibility is checked when swarm behavior is declared.
- [ ] All 21 checked-in schema artifacts match their factory, typed-reader,
  semantic-validation, and CLI ownership declarations.
- [ ] `python scripts/generate_schema_artifacts.py --check` verifies Catalog
  closure and all seven frozen roots; two consecutive `--write` runs produce no
  byte changes and never rewrite a frozen artifact.
- [ ] Every one of the 25 `schema export` CLI names emits its checked artifact
  bytes exactly, including from an external working directory.
- [ ] The schema parity corpus covers required-field removal, unknown critical
  input, wrong discriminator/container, bool-as-int, non-finite values,
  duplicate keys, root/fingerprint mutation, and critical/noncritical
  extensions with the documented validation-layer owner.
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
- [ ] `requirements/ci-constraints.txt` contains exact, sorted, SHA-256-locked
  CI-only wheels for all three supported CPython versions, and
  `requirements/ci-constraints.sha256` matches it. Core runtime dependencies
  remain empty.
- [ ] `python scripts/check_ci_supply_chain.py --check` and the offline
  workflow-policy tests pass. The reviewed workflow header and every complete
  job block match their SHA-256 execution-context contract, so triggers,
  environments, runners, matrices, action inputs, shell controls, and ordered
  steps cannot drift independently of the policy review.
- [ ] Every network-capable CI install uses
  `--require-hashes --only-binary=:all:` against the checked Ubuntu x86_64
  CPython 3.12–3.14 wheel lock; every editable install is
  `--no-deps --no-build-isolation`, and every checkout uses
  `persist-credentials: false`.
- [ ] The fixed `quality-gate` aggregates every classified validation job;
  fork pull requests skip only provenance, while trusted `main` provenance is
  required to succeed.
- [ ] The checked repository policy remains `proposed` until the authorized
  release/merge Goal activates it; activation preserves PR-only main changes,
  required `quality-gate`, deletion/force-push denial, and zero mandatory
  approvals for the single-maintainer repository.
- [ ] `.github/immutable-releases-proposed.json` remains an inert, owner-neutral
  proposal until explicit WP-13 authorization. Its exact `PUT` activation and
  read-only `GET` verification contract use GitHub REST API version
  `2026-03-10` through `X-GitHub-Api-Version`; no checked-in payload contains a
  repository identity, credential, or disable path. The proposal's
  `authorization` field records the human remote-write gate, not API
  authentication: `GET` requires an external authenticated principal with
  repository `Administration: read`, and `PUT` requires
  `Administration: write`. The `PUT` has no request body; `desired_state` is
  proposal metadata and must not be serialized as one.
- [ ] Before activation, re-resolve the official GitHub Actions App integration
  id and verify it remains `15368`; the required `quality-gate` must reject a
  same-name check from any other integration.
- [ ] Treat workflow and policy-evaluator code from a pull-request checkout as
  maintainer-reviewed repository code, not an immutable external trust root.
  WP-00 prevents tested skip/masking paths but does not claim an organization
  required-workflow service or protection against a maintainer who can merge a
  self-modifying gate.
- [ ] Release output contains both CycloneDX 1.6 and SPDX 2.3 SBOMs, and every
  wheel/sdist entry contains the exact SHA-256 of the uploaded artifact. SBOM
  identity/version is read from exactly one `Name` and one `Version` in the one
  wheel and one sdist metadata pair; filenames and archive metadata roots bind
  that same identity/version and never read it from the mutable checkout.
- [ ] Reproducible release timestamps use the ZIP-safe 1980 epoch
  (`SOURCE_DATE_EPOCH=315532800`), never a pre-1980 value.
- [ ] A trusted push to `main` produces GitHub build provenance plus CycloneDX
  and SPDX attestations bound to the exact distribution bytes downloaded from
  the read-only `supply-chain` job; the provenance job must not rebuild its own
  subjects. A pull request, including a fork PR, skips only attestation and
  still runs all read-only validation jobs.

## Release Candidate Dry-Run

- [ ] From a clean candidate commit, run
  `python scripts/release_candidate.py --tag v<exact-version> --staging-dir <outside-checkout>`;
  the tag, `pyproject.toml`, source `pheroos.__version__`, wheel metadata, sdist
  metadata, and installed package version must be identical.
- [ ] Both builds, source verification, ABI diff, and migration notes read only
  from a snapshot materialized directly from the captured tree with
  `git ls-tree` and verified `git cat-file blob` bytes. Git attributes,
  export substitutions, checkout filters, replace refs, and mutable worktree
  bytes cannot rewrite the snapshot; the manifest binds both the full commit
  and full tree id, and the caller checkout remains clean at both pre-assembly
  and post-assembly checks.
- [ ] The first locked build is the only release subject. The second locked
  build is marked `comparison_only`, is byte-identical by filename and SHA-256,
  and is never installed, staged, attested, uploaded, signed, or published.
- [ ] Source, wheel, and sdist produce identical semantic transcripts from an
  external CWD for the strict Stable candidate consumer, every Schema CLI
  export, Commit TCK v1/v2, maintained Conformance examples, and the independent
  Runtime Integration adapter.
- [ ] `python scripts/release_candidate.py --verify-staging <staging-dir>` passes.
  The staging allowlist contains only the subject wheel/sdist, CycloneDX 1.6,
  SPDX 2.3, `ABI-DIFF.json`, `MIGRATION-NOTES.md`, `release-manifest.json`, and
  `SHA256SUMS`; no comparison-build path or undeclared asset is present.
- [ ] `release-manifest.json` records a clean full candidate commit, exact
  subject hashes, equal comparison hashes, transcript roots, Draft
  `promotion_candidate` lifecycle, `publication_allowed=false`, and the fixed
  reproducible epoch. `SHA256SUMS` binds every other staged byte.
- [ ] `ABI-DIFF.json` reports candidate drift zero, breaking differences zero,
  and closure missing zero. Migration notes embed the Unreleased changelog and
  bind each versioned migration source by SHA-256.
- [ ] `.github/workflows/release-candidate.yml` remains read-only and dry-run
  only. It may preserve the allowlisted staging set as CI evidence, but it must
  not create a commit, tag, Release, attestation, PyPI upload, or write token.
- [ ] `.github/rulesets/tags-v-proposed.json` remains disabled until WP-13
  authorization; its exact `refs/tags/v*` proposal denies both tag update and
  deletion with no bypass actor.
- [ ] `.github/repository-settings-proposed.json` remains a local proposal until
  WP-13 authorization; when applied, it enables only automatic deletion of
  merged branches.
- [ ] `.github/immutable-releases-proposed.json` passes the offline repository
  policy audit. Before the first RC or GA GitHub Release is created, a read-only
  `GET /repos/{owner}/{repo}/immutable-releases` must return HTTP `200` with
  `enabled=true`; `200` with `enabled=false`, HTTP `404`, or any indeterminate
  response means the repository is not proven protected and blocks publication.
  A contents-only default workflow token is not sufficient for this
  administrative check. An authorized, externally authenticated `PUT` must
  happen before any Release because the setting protects only future releases.

## Release Metadata

- [ ] `pyproject.toml` version is correct.
- [ ] `pheroos.__version__` matches the package version.
- [ ] License and project URLs are correct.
- [ ] GitHub Actions pass.
- [ ] The git worktree contains no accidental local files, secrets, caches, generated reports, or virtual environments.

## Publishing

- [ ] Obtain explicit WP-13 authorization before activating either proposed
  ruleset, enabling immutable releases, or creating a release branch, tag,
  GitHub Release, or PyPI upload.
- [ ] Enable and verify immutable releases before creating the first GitHub
  Release. Create the Release as a draft, attach the complete allowlisted asset
  set, and publish the draft only after hashes and attestations match; after
  publication, verify the Release reports `immutable=true`.
- [ ] Include changelog notes.
- [ ] Include migration notes for any draft ABI changes.
- [ ] Confirm examples remain provider-free and network-free.
- [ ] Download the CI release artifact, verify both SBOMs, and verify GitHub
  attestations before publishing the exact attested wheel and sdist.
- [ ] Never update/delete a published `v*` tag or replace a Release asset. On a
  post-publication failure, preserve the immutable Release, tag, assets, and
  prerelease/latest status; edit only its title or notes to mark it
  withdrawn/known-bad, then issue a new RC or patch with a newly attested
  immutable asset set. Only a newly qualified GA may become the new latest
  release.
