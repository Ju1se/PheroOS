# API and ABI Lifecycle

Status: draft

This document defines how PheroOS manages public API and ABI surfaces while the project is still pre-stable.

## Goals

- Keep public interfaces easy to discover.
- Keep protocol-core internally cohesive and externally low-coupled.
- Make extensions possible without forcing applications, providers, servers, or domain workflows into core.
- Avoid unnecessary constraints that do not protect correctness, traceability, compatibility, or deterministic behavior.

## Public API Surfaces

The public Python surfaces are package-level imports from:

- `pheroos.protocol`
- `pheroos.kernel`
- `pheroos.governance`
- `pheroos.drivers`
- `pheroos.trace`
- `pheroos.conformance`

The CLI surface covers manifest validation, conformance evaluation, and ABI schema export.

The ABI artifact surface is:

- checked-in JSON schemas under `schemas/`
- full capability manifest schema under `schemas/capability.schema.json`
- strict Commit Wire schema under `schemas/commit.schema.json`
- implementation-neutral Commit TCK schema under
  `schemas/commit-tck.schema.json`
- packaged Commit TCK vectors under `pheroos/conformance/tck/`
- provider-free examples under `examples/`
- conformance checks under `pheroos.conformance`

Submodules may be imported by advanced users, but package `__all__` exports are the preferred public entry points.

Canonical public type ownership is part of the ABI. `CommitAssurance` and
`CommitAction` are owned by `pheroos.protocol.commit_models`, while
`TraceEvent` is owned by `pheroos.trace`. Governance compatibility exports must
remain type-identical aliases, not parallel representations. The package
`__all__` name sets are frozen by the public API snapshot test only after all
release surfaces have stopped changing.

For the Optimal Commit Draft, the governance package intentionally exports the
complete authority lifecycle: canonical records, issuance and verification,
payload/fingerprint helpers, replay/window transitions, certificates,
distributed finality, and the total evaluator. This is a deliberately broad
ABI surface so an external runtime or independent verifier is not forced to
depend on private helpers. Symbols prefixed with `_` remain implementation
details; removing or renaming an exported symbol requires the normal Draft ABI
migration and snapshot update.

## Internal Surfaces

Implementation details should stay inside their package unless they are intentionally exported.

Examples:

- protocol parsing helpers stay under `pheroos.protocol`
- driver lifecycle internals stay under `pheroos.drivers`
- kernel materialization details stay under `pheroos.kernel`
- governance reference-engine helpers stay under `pheroos.governance`
- conformance orchestration stays under `pheroos.conformance`

If an internal helper becomes part of the public API, it should be exported intentionally, documented, and covered by tests.

## Stability Levels

PheroOS uses these stability labels until the first stable ABI release:

- Draft: shape may change, but changes require tests and changelog notes.
- Supported: intended for external implementations, covered by docs and conformance.
- Deprecated: still available, but scheduled for removal or replacement.
- Internal: not guaranteed outside the package that owns it.

Current project status:

- Manifest schemas: Draft, conformance-backed.
- Public package exports: Draft, test-backed.
- CLI commands: Supported draft.
- Provider-free examples: Supported draft.
- Conformance checks and profile versions: Supported draft.
- Optimal Commit Wire and TCK artifacts: Draft, conformance-backed.
- Full runtime infrastructure: out of scope.

## Change Rules

API or ABI changes should include:

- motivation
- affected public surface
- compatibility impact
- schema impact if any
- conformance impact if any
- migration notes when behavior changes
- tests for new or changed behavior
- extension and secret-boundary impact when manifest shape changes

Breaking changes should be avoided unless they improve a declared protocol invariant or remove an unsafe ambiguity.

Do not add a new required field, validator, denial path, or conformance failure unless it protects at least one of:

- protocol correctness
- deterministic behavior
- traceability
- output authority boundaries
- provider-free compatibility
- package import boundaries

## Deprecation Policy

Before the first stable ABI release, deprecations may be documented in `CHANGELOG.md` and migration notes.

After the first stable ABI release, public API removals should provide:

- a replacement path
- migration notes
- a compatibility window when practical
- conformance or tests proving the replacement

Compatibility aliases are acceptable when they reduce migration cost without creating a second incompatible ABI object.

## Versioning

Package version is declared in `pyproject.toml` and `pheroos.__version__`.

Protocol manifests include their own `protocol_version`.

Schema changes should keep checked-in schema artifacts and schema export behavior aligned.

Conformance reports include a profile version. A profile version change is an ABI signal and should be documented in `CHANGELOG.md`.

Version bumps should follow the release checklist in `docs/process/release-checklist.md`.

## Conformance Gate

Public API changes should pass CI-backed validation for:

- deterministic tests
- baseline protocol compatibility
- governed e2e protocol compatibility
- swarm protocol compatibility when swarm behavior is declared
- checked-in schema artifact consistency
- formatting and whitespace hygiene
