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

The CLI surface is:

- `pheroos validate`
- `pheroos conformance`
- `pheroos schema export`

The ABI artifact surface is:

- checked-in JSON schemas under `schemas/`
- provider-free examples under `examples/`
- conformance checks under `pheroos.conformance`

Submodules may be imported by advanced users, but package `__all__` exports are the preferred public entry points.

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
- Conformance checks: Supported draft.
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

Schema changes should keep checked-in schema artifacts and `pheroos schema export` output aligned.

Version bumps should follow the release checklist in `docs/process/release-checklist.md`.

## Conformance Gate

Public API changes should pass:

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
