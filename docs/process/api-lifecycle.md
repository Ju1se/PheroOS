# API and ABI Lifecycle

Status: draft

This document defines how PheroOS manages public API and ABI surfaces while the project is still pre-stable.

## Goals

- Keep public interfaces easy to discover and cohesive at package facades.
- Keep private implementation domains low-coupled, one-way, and independently
  replaceable without creating a second ABI.
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

The CLI surface covers version/profile inspection, manifest validation,
conformance, schema list/show/export, typed wire validation, TCK v1/v2, and
public ABI show/diff. It is a local management surface, not a network API.

The ABI artifact surface is:

- the packaged public Python shape inventory under
  `pheroos/conformance/abi/public-python-api-v1.json`
- the packaged public Python lifecycle registry under
  `pheroos/conformance/abi/public-python-api-lifecycle-v1.json`
- checked-in JSON schemas under `schemas/`
- full capability manifest schema under `schemas/capability.schema.json`
- strict Commit Wire schema under `schemas/commit.schema.json`
- implementation-neutral Commit TCK v1/v2 and v2 request/response schemas
- versioned conformance-report and scoped-Trace envelope schemas
- packaged Commit TCK vectors under `pheroos/conformance/tck/`
- provider-free examples under `examples/`
- conformance checks under `pheroos.conformance`

Submodules may be imported by advanced users, but package `__all__` exports are the preferred public entry points.

Canonical public type ownership is part of the ABI. `CommitAssurance` and
`CommitAction` are owned by `pheroos.protocol.commit_models`, while
`TraceEvent` is owned by `pheroos.trace`. Governance compatibility exports must
remain type-identical aliases, not parallel representations. The six package
`__all__` name sets, signatures, dataclass fields/defaults, enums, constants,
aliases, error types, and public method/property shapes are checked by the
shape inventory. The lifecycle registry covers every export and records its
`group`, `stability`, `since`, `replacement`, and `remove_after`. It also
covers Governance and Conformance compatibility-module attributes and the
closed Protocol, Kernel, Hybrid Commit, and atomic-transition diagnostic-code
registries.
Source conformance rejects missing entries, orphans, invalid replacements, and
unchecked drift in either artifact.

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

### Facade and dependency rules

- External consumers use the six package facades; private module paths are not
  compatibility promises.
- Moving an implementation behind a facade must preserve canonical object
  identity, signature, dataclass/default/enum shape, aliases, and pickle/module
  ownership recorded by the public inventory.
- A facade re-exports or delegates to one owner. It does not copy an algorithm,
  wrap a canonical type in a substitute subclass, or install a service
  locator.
- Private engines depend one way, never import the aggregate facade, and must
  remain free of cycles and hidden module-global runtime authority.
- Immutable static ABI contract registries may drive schema and validation;
  dynamic registration of authority-relevant branches is not an extension
  mechanism.

## Stability Levels

PheroOS uses these machine-checked stability labels until the first stable ABI
release:

- Draft: shape may change, but changes require tests and changelog notes.
- Stable: intended for external implementations, covered by docs and conformance.
- Deprecated: still available, but scheduled for removal or replacement.

Internal names are not lifecycle entries and are not guaranteed outside the
package that owns them.

Current project status:

- Manifest schemas: Draft, conformance-backed.
- Public package exports: Draft, test-backed.
- CLI commands: Draft.
- Provider-free examples: Draft.
- Conformance checks and profile versions: Draft.
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

The current Draft public removal ledger is machine-readable in the lifecycle
artifact. The complete D-01 through D-18 architecture disposition and
non-public migration gates are recorded in
[removal-ledger.md](removal-ledger.md):

| Compatibility surface | Replacement | Earliest removal |
| --- | --- | --- |
| five specialized Driver descriptor subclasses | `pheroos.drivers.DriverDescriptor` | `0.3.0` |
| `pheroos.drivers.DriverHealth` | `pheroos.drivers.DriverProbeResult` | `0.3.0` |
| `pheroos.governance.CanonicalTarget` | `pheroos.protocol.TargetSpec` | `0.3.0` |
| `pheroos.governance.RecoveryTrace` | `pheroos.trace.TraceEvent(event_type="recovery")` | `0.3.0` |
| `pheroos.governance.evaluate_hybrid_commit_evaluation` | `pheroos.governance.evaluate_hybrid_commit_step` | `0.3.0` |
| `run_conformance(..., root=...)` parameter only | `run_source_conformance(core_root)` for source proof | `0.3.0` |
| `pheroos.governance.trace` module alias | `pheroos.trace` | `0.3.0` |
| three Governance commit-codec wrappers | the same names under `pheroos.protocol` | `0.3.0` |

`run_conformance` itself is not deprecated. It remains the manifest
conformance entrypoint; only its ignored `root` compatibility parameter is
scheduled for removal.

## Versioning

Package version is declared in `pyproject.toml`, owned by the dependency-free
`pheroos._version` foundation, and re-exported as `pheroos.__version__`.

Protocol manifests include their own `protocol_version`.

Once a schema `$id` is exposed, its document bytes and meaning do not change in
place, including during Draft development. The original unversioned Capability,
Protocol, Driver, and Kernel IDs are frozen as legacy v1 artifacts. New
validation semantics use versioned IDs and exact version selection; CLI legacy
aliases remain pinned to v1. The roots and migration rules are recorded in
[schema-v1-v2-migration.md](schema-v1-v2-migration.md).

Schema changes should keep checked-in schema artifacts, generated schema
behavior, typed readers, and CLI exports aligned.

Conformance reports include a profile version. A profile version change is an ABI signal and should be documented in `CHANGELOG.md`.

Version bumps should follow the release checklist in `docs/process/release-checklist.md`.

## Conformance Gate

Public API changes should pass CI-backed validation for:

- deterministic tests
- Python 3.12 through 3.14
- baseline protocol compatibility
- governed e2e protocol compatibility
- swarm protocol compatibility when swarm behavior is declared
- checked-in schema artifact consistency
- public shape/lifecycle and static-contract consistency
- source-v3 scope, Driver, reusable StateStore/TraceStore adapter, and
  import-boundary checks
- TCK v1/v2 through reference and independent adapters
- separate external-CWD wheel and sdist consumers
- documentation links and bilingual README link parity
- formatting and whitespace hygiene
