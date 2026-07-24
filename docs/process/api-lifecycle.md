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
- the closed `pheroos.conformance.schema_catalog` ownership registry that
  binds every checked schema to its factory, reader/validator, CLI names,
  frozen state, package-data decision, profiles, and TCKs
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

WP-03 adds 23 public Draft Governance names under the canonical
`pheroos.governance.authority_session_v2` owner and two public Draft
Conformance names for its exact-version matrix. Portable grants, verifications,
and requests have strict canonical wire shapes; capability and session types
are intentionally non-portable opaque handles with no public constructor. The
shape and lifecycle inventories cover all 25 additions. Their availability is
not profile activation: the complete scoped-authority selectors, verifier TCK,
Output v2, and source-v4 gates were still inactive at that milestone. WP-05
subsequently deprecates only the legacy authority slices for which a complete
public StateStore-backed owner and reusable v2 Conformance matrix now exist.
Other trusted-host v1 issuers remain Draft until the same per-symbol gate is
met. No v1 implementation is physically removed by lifecycle metadata.

### WP-05 durable-authority deprecation boundary

WP-05 records an exact 86-name Governance cohort as Deprecated. The cohort is
not selected by a name wildcard. It is the reviewed set of process-local state,
sentinel-issued records, issuers/transitions, and currentness/authority checks
covered by these public v2 matrices:

- `run_governance_hybrid_replay_conformance_v2`
- `run_governance_commit_replay_conformance_v2`
- `run_governance_commit_decision_conformance_v2`
- `run_governance_risk_conformance_v2`
- `run_governance_support_conformance_v2`
- `run_governance_commit_certificate_conformance_v2`
- `run_governance_distributed_commit_conformance_v2`

The exact migration anchors are:

| Legacy authority slice | Exact public v2 replacement |
| --- | --- |
| `HybridCollectiveStep`; `hybrid_collective_step_is_authoritative` | `VerifiedHybridSourceStepV2` issued only by `evaluate_hybrid_collective_step_v2` |
| `HybridReplayState`; `hybrid_replay_state_is_authoritative` | `VerifiedHybridReplayStateV2`; `hybrid_replay_state_is_current_v2` |
| `evaluate_hybrid_collective_step`; `replay_state_from_hybrid_step` | `evaluate_hybrid_collective_step_v2`; `advance_hybrid_replay_state_v2` |
| `CommitReplayState`; its initialize/record/currentness/authority entrypoints | `VerifiedCommitReplayStateV2`; `prepare_commit_replay_advance_v2`; `advance_commit_replay_state_v2`; `commit_replay_state_is_current_v2` |
| v1 window, seal, progress, and outcome authority records/checks | `VerifiedCommitDecisionStateV2`; `commit_decision_state_is_current_v2`; `require_current_commit_decision_state_v2` |
| v1 window initialize/advance/reset/restart and liveness issuance | `prepare_commit_decision_initialize_v2`; `prepare_commit_decision_successor_v2`; `advance_commit_decision_v2` |
| `CommitLivenessInput`; `reduce_commit_liveness` | `VerifiedCommitDecisionSourceV2`; `reduce_commit_decision_v2` |
| `CommitFinalityVerification`; its authority check | neutral opaque `VerifiedCommitFinalityInputV2` |
| v1 Risk chain, assessment, and threshold authority records/issuers/checks | `VerifiedRiskStateV2`; `prepare_risk_state_advance_v2`; `advance_risk_state_v2`; `risk_state_is_current_v2` |
| v1 eligible Membership snapshot/epoch authority and checks | `VerifiedMembershipStateV2`; `commit_membership_epoch_v2`; `membership_state_is_current_v2` |
| v1 Support lease/revocation/replay authority, issue/revoke/switch, and checks | `VerifiedSupportStateV2`; the four `prepare_support_*_v2` entrypoints; `advance_support_state_v2`; `support_state_is_current_v2` |
| v1 local-receipt issuance/currentness and local finality | the sealed `VerifiedCommitDecisionStateV2` journey through `prepare_commit_decision_successor_v2` and `advance_commit_decision_v2` |
| v1 evidence-certificate issuance and current certified finality | `prepare_commit_certificate_v2`; `advance_commit_certificate_v2`; `verified_commit_certificate_finality_input_v2` |
| v1 outcome-certificate issuance/currentness | terminal `VerifiedCommitDecisionStateV2` through `advance_commit_decision_v2` |
| v1 Distributed state/issuers/transitions/currentness/finality | `VerifiedDistributedStateV2`; the four `prepare_distributed_*_v2` lane entrypoints; `advance_distributed_commit_v2`; `distributed_state_is_current_v2`; `verified_distributed_commit_finality_input_v2` |

A preparation function is not authority by itself. Where the lifecycle points
to `prepare_*_v2`, migration still requires the exact authority session,
atomic `advance_*_v2` Store commit, verified receipt/inclusion, and rehydrated
current owner described by that v2 ABI. There is no v1-to-v2 authority
conversion helper and no fallback to the old issuer when v2 denies or races.

The following surfaces deliberately remain Draft rather than Deprecated:

- v1 payload, `from_payload`, fingerprint, signing-root, and body-root helpers;
- `EvidenceCommitCertificate`, `OutcomeCertificate`, `LocalCommitReceipt`, and
  their historical inspection codecs;
- `verify_evidence_commit_certificate` and `verify_outcome_certificate` when
  used to inspect retained portable proof;
- portable Distributed proposal, witness, certificate, finality-decision, and
  epoch-certificate records/codecs; and
- independent portable Distributed verification functions such as
  `verify_distributed_commit_certificate`,
  `verify_distributed_commit_proposal`,
  `verify_epoch_transition_certificate`, and
  `verify_portable_witness_verification`.

Those functions validate or describe data. They cannot issue, refresh, make
current, or authorize a Store-backed v2 state. Retaining them is necessary for
historical proof inspection and must not be described as retaining v1 runtime
authority.

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
- Public package exports: Draft or Deprecated, test-backed; no Stable entries
  are claimed by WP-05.
- CLI commands: Draft.
- Provider-free examples: Draft.
- Conformance checks and profile versions: Draft.
- Optimal Commit Wire and TCK artifacts: Draft, conformance-backed.
- Full runtime infrastructure: out of scope.

### Draft Stable promotion candidate

`pheroos/conformance/abi/stable-python-api-v1.json` is the reviewed WP-07A
promotion candidate. It is a type-closed projection of the six public facades,
not a Stable lifecycle claim. Its lifecycle remains exactly
`draft / promotion_candidate / formal_stable=false` until the separately
governed WP-07B release gate succeeds.

The package-facade boundary, aggregate write journey, external adapter rules,
and verification commands are collected in the
[Stable Core consumer contract](../protocol/stable-core-consumer.md).

External consumers can inspect and check this projection with:

```bash
pheroos abi show --stable-only
pheroos abi diff --stable-only
```

The candidate diff is a promotion-readiness drift gate. When given a complete
public ABI inventory, it compares only candidate closure bindings and their
declared constant dependencies; changes to unrelated Expert Draft exports are
ignored. Candidate drift can fail the command while `stable_breaking` remains
false. Only a later formally Stable, same-major artifact may report a Stable
breaking change.

The executable strict-type consumer lives at
`tests/typing/stable_consumer.py`. Wheel and sdist tests install each artifact
separately, run that same file from an isolated external working directory,
and require both `pheroos/py.typed` and the candidate JSON to be packaged. The
same consumer executes the Governance-owned aggregate write journey and proves
committed output, duplicate-free exact retry, same-root restart recovery,
currentness denial after a successor, revoked/expired grant denial, and blocked
publish denial.

The candidate includes the portable signal proposal-root helper because the
aggregate journey requires an exact signal/proposal binding. It includes
portable grant revocation because lifecycle denial is part of that executable
journey. Neither root exposes an opaque capability or session. This evidence
does not change `draft / promotion_candidate / formal_stable=false`.

WP-01 reserves scoped authority v2 as a new semantic/profile family rather
than mutating the current Draft surface. The exact IDs and state model are in
the [authority decision](../protocol/authority-v2-decision.md). A v1 issuer is
marked Deprecated only after its session-bound replacement exists, is
exported, has lifecycle metadata, and passes the v2 negative/conformance
matrix; WP-05 closes that gate for the 86-name cohort above and no broader
set. The
[migration contract](../protocol/authority-v2-migration.md) fixes `0.3.0` as
the earliest possible removal, not a promised removal date.

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
| 6 Hybrid process-local step/replay authority surfaces | Hybrid Replay v2 owner/evaluator/currentness/advance | `0.3.0` |
| 27 Commit replay/window/seal/liveness/finality authority surfaces | Commit Replay v2 and Commit Decision v2 owners | `0.3.0` |
| 11 Risk/threshold authority surfaces | Risk v2 owner | `0.3.0` |
| 17 Membership/Support/replay authority surfaces | Membership and Support v2 owners | `0.3.0` |
| 8 local-receipt/certificate/current-finality authority surfaces | Commit Decision and Commit Certificate v2 owners | `0.3.0` |
| 17 Distributed issuer/transition/current-finality authority surfaces | four-lane Distributed Commit v2 owner | `0.3.0` |

`run_conformance` itself is not deprecated. It remains the manifest
conformance entrypoint; only its ignored `root` compatibility parameter is
scheduled for removal.

The WP-05 counts above describe lifecycle entries, not files deleted. Their v1
implementations remain available for the declared Draft compatibility window,
and portable historical readers may remain beyond it. Actual removal is owned
by the non-skippable physical-removal Goal and requires release/consumer
evidence at or after the earliest removal version.

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
