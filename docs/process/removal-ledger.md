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
| D-06 | versioned-deferred | new authority uses `GovernanceStateStore`, CAS heads, atomic state+trace batches, receipts, rehydration, retire, and tombstones; all v1 process state is quarantined in `_legacy.authority_registry` | New authority modules cannot import the legacy adapter. The adapter remains private for pre-0.2.0 issuer compatibility and exposes cardinality/reset only for conformance. Remove after every v1 issuer has a StateStore-backed profile and the legacy profile is retired. |
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

## Enforcement

- The public lifecycle artifact records every exported Draft, compatibility,
  deprecated, replacement, and remove-after decision.
- Source conformance rejects orphan lifecycle entries, public-shape drift,
  forbidden package imports, and new durable-authority imports of `_legacy`.
- A deferred surface may receive compatibility fixes, but no new protocol
  authority, runtime infrastructure, or feature semantics.
- Actual removal requires a changelog entry, migration note, consumer fixture,
  ABI/profile version decision, and all release gates.
