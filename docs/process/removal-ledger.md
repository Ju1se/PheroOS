# Architecture Removal Ledger

Status: active Draft migration record

This ledger records the disposition of D-01 through D-18 from the project
architecture hardening audit. “Deferred” means the old public shape remains
available for a declared compatibility reason; it does not mean that the old
path may acquire new authority or features.

The `Status` column is closed to `removed`, `retained-with-reason`, and
`versioned-deferred`. Deprecation kind, compatibility form, replacement, and
remove-after version remain explicit in the explanatory columns.

| ID | Status | Replacement / isolation | Consumer proof and removal condition |
| --- | --- | --- | --- |
| D-01 | removed | `InMemoryTraceStore.records`; private storage is name-mangled and indexed | Trace store compatibility, snapshot, append, and mutation tests pass; `_records` is not exported. |
| D-02 | removed | dependency-free `pheroos._immutable` ABI container helpers | Kernel/Driver mutation and import-boundary tests pass; the two package-local copies are deleted. |
| D-03 | removed | `pheroos.protocol._immutable` owns protocol snapshot/deep-freeze behavior | Manifest and Commit model mutation/serialization tests preserve public bytes and shapes. |
| D-04 | removed | `pheroos.governance._commit_validation` is the single primitive text/step/bool/assurance/profile/fingerprint/label validator owner | Commit negative tests preserve exact errors and bounded integer behavior; 17 governance modules consume the shared owner. |
| D-05 | removed | generated static lazy Governance facade and checked-in public shape inventory | Export identity/signature/default/alias tests, cold-import budget, star import, `dir()`, pickle, and generator drift checks pass. |
| D-06 | versioned-deferred | new authority uses `GovernanceStateStore`, CAS heads, atomic state+trace batches, receipts, rehydration, retire, and tombstones; all v1 process state is quarantined in `_legacy.authority_registry` | New authority modules cannot import the legacy adapter. The adapter remains private for pre-0.2.0 issuer compatibility and exposes cardinality/reset only for conformance. Remove after every v1 issuer has a StateStore-backed profile and the legacy profile is retired; the non-skippable [physical-removal Goal](legacy-authority-physical-removal-goal.md) owns that deletion. |
| D-07 | retained-with-reason | Deprecated compatibility subtypes normalize to canonical `DriverDescriptor` plus capabilities/extensions. | Lifecycle registry marks the five specialized descriptors deprecated; remove no earlier than 0.3.0 after external usage audit and migration fixtures. |
| D-08 | retained-with-reason | Deprecated compatibility type `DriverHealth` is replaced by `DriverProbeResult` / identity alias `DriverProbeSnapshot`. | Driver lifecycle/readiness tests cover the replacement; remove `DriverHealth` no earlier than 0.3.0. |
| D-09 | retained-with-reason | Deprecated compatibility type `CanonicalTarget` is replaced by Protocol `TargetSpec` and validated target identifiers. | Lifecycle metadata points consumers to Protocol ownership; remove `CanonicalTarget` no earlier than 0.3.0. |
| D-10 | retained-with-reason | Deprecated compatibility type `RecoveryTrace` is replaced by canonical `TraceEvent(event_type="recovery")` and its static lineage contract. | Trace mutation/conformance tests cover the replacement; remove `RecoveryTrace` no earlier than 0.3.0 after migration. |
| D-11 | retained-with-reason | Deprecated alias `evaluate_hybrid_commit_evaluation` delegates to the sole total engine entry `evaluate_hybrid_commit_step(request=...)`. | The alias emits `DeprecationWarning`; payload-equivalence consumer tests pass. Remove no earlier than 0.3.0. |
| D-12 | retained-with-reason | Deprecated `root=` parameter remains on `run_conformance(path)` for call compatibility; source proof uses `run_source_conformance(root)`. | The parameter remains ignored and lifecycle-recorded. Remove the parameter, not `run_conformance`, no earlier than 0.3.0. |
| D-13 | versioned-deferred | canonical `pheroos.trace.TraceEvent` | Governance export is type-identical and `governance.trace` is a thin compatibility module. Remove module alias no earlier than 0.3.0. |
| D-14 | retained-with-reason | Deprecated compatibility wrappers translate the legacy exception contract while Protocol owns the canonical Commit codecs. | Lifecycle registry records all three replacements. Remove after consumer exception migration, no earlier than 0.3.0. |
| D-15 | versioned-deferred | Graph v2 decision required | `EvidenceEdge` remains frozen for Draft ABI compatibility and gains no authority. Graph v2 must either add endpoint/relation/provenance/trace semantics with conformance, or remove edges; v1 shape is not silently repurposed. |
| D-16 | versioned-deferred | `normalize_legacy_pheromone_trail(...)` binds the legacy constructor to explicit subject, target, source, provenance, and trace | The factory fails closed on missing/conflicting/ambiguous bindings and never creates evidence or authority. Remove the two-field constructor only in a new profile/schema after migration and TCK coverage. |
| D-17 | versioned-deferred | `canonical_pheromone_kind_profiles(...)` produces `pheroos-pheromone-kind-profile-map-v1` | Explicit per-kind profiles win in full; scalar weights only synthesize missing built-in kinds. Runtime scoring uses the single map and preserves legacy projections. Remove scalar fields only in a new manifest/schema profile after migration. |
| D-18 | retained-with-reason | Frozen `_legacy/hybrid_v1.py` selector receives only validated score/scout/fallback projections and cannot issue authority. | Modern atomic/certificate/output/Trace surfaces are excluded by source tests. Delete only when the baseline blended-score profile is formally retired. |

### WP-05 durable-authority lifecycle closure

WP-05 marks 86 public Governance names Deprecated only after their public,
StateStore-backed v2 owners and reusable Conformance matrices exist. The
machine-checked cohort is split as follows:

| Legacy authority family | Deprecated entries | Replacement owner and proof |
| --- | ---: | --- |
| Hybrid step/replay | 6 | Hybrid Replay v2; `run_governance_hybrid_replay_conformance_v2` |
| Commit replay/window/seal/liveness/finality | 27 | Commit Replay v2 and Commit Decision v2; their two v2 Conformance runners |
| Risk/threshold | 11 | Risk v2; `run_governance_risk_conformance_v2` |
| Membership/Support/replay | 17 | Membership and Support v2; `run_governance_support_conformance_v2` |
| local receipt/certificate/current finality | 8 | Commit Decision v2 and Commit Certificate v2; their two v2 Conformance runners |
| Distributed issuer/transition/current finality | 17 | four-lane Distributed Commit v2; `run_governance_distributed_commit_conformance_v2` |

Every entry has a fully qualified public replacement, a retained compatibility
reason, and `remove_after: 0.3.0`. The exact name-to-replacement map is locked
by `tests/conformance/test_public_api_lifecycle.py` and summarized in
[api-lifecycle.md](api-lifecycle.md). `0.3.0` is an earliest possible removal
version, not a removal promise.

This is lifecycle closure, not physical cleanup. The v1 implementations,
private registry, namespaces, cursors, and sentinels remain under D-06 until
the separate physical-removal Goal passes. Stable-candidate and production
paths must use v2 and must not fall back to these retained functions.

Portable data is not classified as authority merely because a v1 issuer once
produced it. Payload/`from_payload`/fingerprint/body-root helpers, historical
certificate readers, and independent portable certificate/proposal/witness/
epoch verifiers remain Draft. They may inspect retained bytes but cannot issue,
refresh, make current, or authorize a v2 StateStore owner.

### WP-05 pre-activation withdrawal

`commit_replay_receipt_v2_from_v1` was present only in an intermediate,
unreleased WP-05 Draft inventory and is withdrawn before the v2 surface is
activated. It had no released compatibility commitment and is not restored as
a deprecated alias: converting a v1 receipt into portable v2 data could be
misread as transferring authority. The explicit replacement is
`CommitReplayReceiptV2(...)` followed by the StateStore-backed Commit Replay v2
prepare, session, commit, and rehydration path. Frozen v1 receipt inspection and
the v1 issuer compatibility window are unchanged.

## Scoped Authority v2 Decision Set

WP-01 froze the rule that an export cannot become Deprecated before its exact
replacement exists. WP-05 now closes that gate only for the reviewed 86-name
cohort above; all other v1 issuers remain Draft until they independently meet
the same rule. This prevents a family-level label from hiding a missing
replacement inside the existing Draft v1 profile:

| Legacy family | Current status | Required replacement before deprecation | Earliest removal |
| --- | --- | --- | --- |
| Public issuers accepting caller-supplied `authority: AuthorityLevel` | Reviewed WP-05 authority subset Deprecated; unmatched and data-only helpers remain Draft trusted-host compatibility | Exact session-bound replacements under `pheroos-scoped-authority-local-v2` or `pheroos-scoped-authority-authenticated-v2`; lifecycle inventory lists every affected symbol | `0.3.0`, only after replacement shipment, migration fixtures, external-consumer audit, and zero Stable/example/TCK references |
| `GovernanceStateStore.atomic_commit`, current-head receipt verification, and destructive retirement read behavior | Draft v1 | `GovernanceStateStoreV2`, total typed commit attempt, historical inclusion lookup, position inspection, full atomic read-set, and seal-preserved proof | `0.3.0`, after v2 store Conformance and an independent adapter pass |
| Baseline output authorization with caller-provided publication boolean | Draft v1 | session-, action-, payload-, currentness-, and read-set-bound output v2 commit | `0.3.0`, after WP-04 migration and negative tests |
| Process-local replay/window authority used by a future Stable path | Deprecated compatibility only; physically retained | StateStore-backed append-only replay with restart-safe CAS and exact v2 profile binding | `0.3.0`, after consumer/removal gates; WP-05 deprecation alone is insufficient |

Portable v1 historical codecs and proof readers may outlive v1 issuance. A
deployment must retain the ability to inspect old committed bytes even after
new v1 issuance is disabled. The original 36-symbol issuer family and its
per-symbol gates are in the
[authority v2 migration contract](../protocol/authority-v2-migration.md); the
WP-05 lifecycle test is authoritative for which of those and which additional
process-local currentness surfaces have now passed the replacement gate.

## Enforcement

- The public lifecycle artifact records every exported Draft, compatibility,
  deprecated, replacement, and remove-after decision.
- Source conformance rejects orphan lifecycle entries, public-shape drift,
  forbidden package imports, and new durable-authority imports of `_legacy`.
- A deferred surface may receive compatibility fixes, but no new protocol
  authority, runtime infrastructure, or feature semantics.
- Actual removal requires a changelog entry, migration note, consumer fixture,
  ABI/profile version decision, and all release gates.
