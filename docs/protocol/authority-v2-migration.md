# Scoped Authority v2 Migration Contract

Status: **accepted migration; Draft local rollout active, authenticated
production and Stable promotion gated**

This document fixes the compatibility and rollout contract for moving from the
trusted-host Authority ABI to scoped authority v2. The exact local profile now
composes StateStore, Authority Session, Baseline Output, schema/reader, Trace,
Runtime Integration, and Conformance as an active Draft selection. This is not
a production-runtime or Stable guarantee. Authenticated selection requires a
host-provided verifier and cannot claim production compatibility until the
external verifier and promotion gates below close.

The governing security invariants are defined by the
[authority trust model](authority-trust-model-v2.md), and the exact version
decisions are recorded in [authority-v2-decision.md](authority-v2-decision.md).
The central migration rule is:

> A v1 record can remain valid historical data, but it never becomes scoped v2
> authority by parsing, relabeling, adding a digest, or selecting an authority
> v2 schema/profile reader.

Agents remain proposal sources. `AuthorityLevel`, a Boolean, a digest, a
dataclass, a receipt identifier, or a Trace event is not a credential.

## 1. Frozen identifiers

The migration uses these exact identifiers. They are separate version axes and
must not be shortened, aliased, inferred from document shape, or substituted by
package versions.

| Axis | Exact identifier |
| --- | --- |
| Protocol semantic profile | `pheroos.protocol.v2` |
| Capability schema selector | `pheroos-capability-schema-v3` |
| Capability schema file / `$id` | `capability-v3.schema.json` / `https://pheroos.dev/schemas/capability-v3.schema.json` |
| Protocol schema selector | `pheroos-protocol-schema-v3` |
| Protocol schema file / `$id` | `protocol-v3.schema.json` / `https://pheroos.dev/schemas/protocol-v3.schema.json` |
| Authority policy | `pheroos-scoped-authority-policy-v2` |
| Local trusted-host profile | `pheroos-scoped-authority-local-v2` |
| Authenticated profile | `pheroos-scoped-authority-authenticated-v2` |
| Authority wire | `pheroos-authority-wire-v2` |
| Canonical encoding | `pheroos-authority-canonical-v2` |
| Authority schema selector | `pheroos-authority-schema-v2` |
| Authority schema file / `$id` | `authority-v2.schema.json` / `https://pheroos.dev/schemas/authority-v2.schema.json` |
| Authority ledger | `pheroos-governance-authority-ledger-v2` |
| StateStore ABI | `pheroos-governance-state-store-v2` |
| Atomic Trace batch | `pheroos-governance-trace-batch-v2` |
| Canonical authority read-set | `pheroos-governance-authority-read-set-v2` |
| StateStore Conformance | `pheroos-governance-state-store-conformance-v2` |
| Issuer verifier Conformance | `pheroos-issuer-grant-verifier-conformance-v2` |
| Authority TCK / TCK schema | `pheroos-scoped-authority-tck-v2` / `scoped-authority-tck-v2.schema.json` / `https://pheroos.dev/schemas/scoped-authority-tck-v2.schema.json` |
| Source profile | `pheroos-source-v4` |

The already published `pheroos-capability-schema-v2` and
`pheroos-protocol-schema-v2` selectors are strict schema-document revisions for
payloads whose semantic version is still `pheroos.protocol.v1`. They are not
authority v2 and their files, `$id` values, bytes, and meaning remain frozen.

## 2. Exact manifest selection

### 2.1 Legacy v1 stays explicit

This is a complete legacy PheroOS baseline profile. Omitting
`authority_policy` is intentional. It remains on current Draft v1 semantics and
must not receive v2 authority fields, authority v2 schema/profile readers, v2
diagnostics, or stronger security claims implicitly.

```json
{
  "id": "legacy-review-protocol",
  "name": "Legacy Review Protocol",
  "version": "0.1.0",
  "permissions": [],
  "required_connections": [],
  "drivers": [],
  "protocol": {
    "protocol_version": "pheroos.protocol.v1",
    "id": "review.legacy",
    "targets": [
      {
        "id": "decision:review",
        "description": "A legacy trusted-host review target."
      }
    ],
    "signals": [
      {
        "type": "proposal",
        "target": "decision:review",
        "authority_required": "governance"
      }
    ],
    "candidates": [
      {
        "id": "candidate:accept",
        "target": "decision:review",
        "label": "Accept"
      },
      {
        "id": "candidate:safe_fallback",
        "target": "decision:review",
        "label": "Insufficient evidence",
        "safe_fallback": true
      }
    ],
    "quorum_policy": {
      "target": "decision:review",
      "fallback_candidate": "candidate:safe_fallback",
      "commit_threshold": 1
    },
    "recovery_protocols": [],
    "evidence_policy": {
      "require_provenance": true,
      "allow_agent_fact_creation": false
    },
    "output_policy": {
      "writer_may_create_facts": false,
      "requires_committed_candidate": true,
      "requires_evidence_contract": true,
      "requires_stop_resolution": true,
      "requires_publication_permission": true
    },
    "trace_policy": {
      "required_events": ["block", "commit", "recovery", "output"]
    }
  }
}
```

The string `authority_required: governance` remains a declaration about the
required classification. It is not a credential and does not opt into scoped
authority.

### 2.2 Scoped v2 is an exact opt-in

This is the exact implemented Draft local-profile manifest shape. The
`authority_policy` object is closed: every listed field is required and no
additional critical field is accepted. The checked v3 manifest schemas and
their profile-selecting readers are active. This payload is valid only through
the exact Capability/Protocol v3 selection; readers still must not infer the
profile from shape. Selecting the authenticated profile additionally requires
the host-provided verifier described below.

```json
{
  "id": "scoped-review-protocol",
  "name": "Scoped Review Protocol",
  "version": "0.2.0rc1",
  "permissions": [],
  "required_connections": [],
  "drivers": [],
  "protocol": {
    "protocol_version": "pheroos.protocol.v2",
    "id": "review.scoped",
    "targets": [
      {
        "id": "decision:review",
        "description": "A scoped-authority review target."
      }
    ],
    "signals": [
      {
        "type": "proposal",
        "target": "decision:review",
        "authority_required": "governance"
      }
    ],
    "candidates": [
      {
        "id": "candidate:accept",
        "target": "decision:review",
        "label": "Accept"
      },
      {
        "id": "candidate:safe_fallback",
        "target": "decision:review",
        "label": "Insufficient evidence",
        "safe_fallback": true
      }
    ],
    "quorum_policy": {
      "target": "decision:review",
      "fallback_candidate": "candidate:safe_fallback",
      "commit_threshold": 1
    },
    "authority_policy": {
      "policy_version": "pheroos-scoped-authority-policy-v2",
      "profile": "pheroos-scoped-authority-local-v2",
      "wire_version": "pheroos-authority-wire-v2",
      "canonical_version": "pheroos-authority-canonical-v2",
      "ledger_version": "pheroos-governance-authority-ledger-v2",
      "state_store_version": "pheroos-governance-state-store-v2",
      "trace_batch_version": "pheroos-governance-trace-batch-v2",
      "read_set_version": "pheroos-governance-authority-read-set-v2"
    },
    "recovery_protocols": [],
    "evidence_policy": {
      "require_provenance": true,
      "allow_agent_fact_creation": false
    },
    "output_policy": {
      "writer_may_create_facts": false,
      "requires_committed_candidate": true,
      "requires_evidence_contract": true,
      "requires_stop_resolution": true,
      "requires_publication_permission": true
    },
    "trace_policy": {
      "required_events": ["block", "commit", "recovery", "output"]
    }
  }
}
```

The authenticated profile changes exactly one manifest value:

```json
{
  "profile": "pheroos-scoped-authority-authenticated-v2"
}
```

The external `IssuerGrantVerifier`, identity material, keys, endpoints, and
credentials must be selected by trusted deployment configuration. They are
never selected by this manifest, a request, an agent, or provider output. An
authenticated-profile reader may validate the declaration, but session binding
must fail until the host supplies a verifier that passes
`pheroos-issuer-grant-verifier-conformance-v2`.

### 2.3 Reader and selector matrix

| Capability selector | Protocol selector | Payload semantic | `authority_policy` | Reader result |
| --- | --- | --- | --- | --- |
| `pheroos-capability-schema-v1` | `pheroos-protocol-schema-v1` | `pheroos.protocol.v1` | absent | Legacy v1 object; trusted-host compatibility only |
| `pheroos-capability-schema-v2` | `pheroos-protocol-schema-v2` | `pheroos.protocol.v1` | absent | Current strict v1 object; no scoped authority |
| `pheroos-capability-schema-v3` | `pheroos-protocol-schema-v3` | `pheroos.protocol.v2` | exact closed v2 object and one exact profile | Scoped v2 object only after the activation checklist in section 9 closes |
| v1 or schema v2 | v1 or schema v2 | `pheroos.protocol.v2` | any | Reject cross-version selection |
| schema v3 | schema v3 | `pheroos.protocol.v1` | any | Reject semantic downgrade/cross-version selection |
| schema v3 | schema v3 | `pheroos.protocol.v2` | missing | Reject missing authority policy |
| schema v3 | schema v3 | `pheroos.protocol.v2` | unknown/missing field, profile, or exact identifier | Reject unsupported authority profile/version |
| any Capability selector | a different-surface or mismatched Protocol selector | any | any | Reject selector mismatch |
| missing or inferred selector | missing or inferred selector | any | any | Reject; authoritative readers never infer from shape |

The CLI compatibility aliases `capability` and `protocol` remain pinned to the
v1 schema files; `capability-v1` and `protocol-v1` select those same frozen
documents explicitly. None of these names may be repointed to schema v3.

The authority wire reader separately requires
`pheroos-authority-schema-v2` and `pheroos-authority-wire-v2`. A manifest reader
does not make an arbitrary authority envelope valid. The envelope must also
bind its profile, canonical version, ledger, scope, operation, grant, complete
read-set, and required Trace lineage.

### 2.4 Strict no-fallback rule

Once any v2 selector, semantic version, profile, or wire identifier is present,
the operation is v2-or-fail:

- no v2 payload is sent to a v1 reader;
- no missing v2 field is synthesized from a v1 default;
- no unknown v2 profile selects the local profile;
- no unavailable authenticated verifier selects the local profile;
- no StateStore conflict or unavailability invokes a v1 issuer or process-local registry;
- no missing certificate, grant, read-set head, or current action authority lowers assurance;
- no v1 decision, receipt, publication Boolean, replay sentinel, or
  `AuthorityLevel.GOVERNANCE` satisfies a v2 gate; and
- no failure after a v2 prepare or commit is retried as a legacy write.

The same runtime may serve separate v1 and v2 scopes during migration, but each
scope has exactly one selected semantic/profile path. Dual read for inspection
is allowed. Dual authoritative write, shadow authority, and per-request
downgrade are forbidden.

## 3. Profile guarantees

| Property | `pheroos-scoped-authority-local-v2` | `pheroos-scoped-authority-authenticated-v2` |
| --- | --- | --- |
| Durable trust root | Selected conforming StateStore plus local issuer capability custody | Selected conforming StateStore, local issuer capability custody, and host-selected external issuer/grant attestation verifier |
| Issuer identity guarantee | Trusted-host selection only; no independent identity or cryptographic authentication claim | Exact envelope/grant is verified under the selected external attestation policy |
| Verifier required | No | Yes; absence/unavailability fails closed |
| Scope/operation/target/action/payload binding | Required | Required |
| Expiry/revocation binding | Required local grant state | Required local grant state plus authenticated grant evidence |
| Atomic read-set, state, receipt, and critical Trace | Required | Required |
| Portable issuer capability | Forbidden | Forbidden; portable attestation is data until locally verified |
| Production claim | Reference and trusted-host deployment profile; not an external-authentication credential | Production-candidate identity profile only after external verifier and StateStore adapter pass Conformance |
| Malicious arbitrary Python in coordinator process | Outside guarantee | Outside guarantee |

Promotion of the authenticated production path to Stable requires at least one
independent external verifier adapter to pass
`pheroos-issuer-grant-verifier-conformance-v2`. Passing only the local
in-memory reference profile cannot satisfy that gate. This does not prevent a
future local trusted-host ABI from reaching its accurately named stability
level; it prevents local possession from being marketed as authenticated
production identity.

Neither profile implements keys, KMS, identity providers, network
authentication, databases, or action executors in protocol-core. A deployment
running untrusted Python must isolate it from the coordinator and StateStore
writer with a process or stronger boundary.

## 4. The 36-symbol `authority: AuthorityLevel` cohort

The checked-in public Python shape inventory currently contains exactly 36
Governance functions with a public parameter named `authority` annotated as
`AuthorityLevel`. WP-01 treats the complete set below as one trusted-host v1
migration cohort:

```text
assemble_portable_distributed_commit_certificate
assess_optimal_commit
bind_evidence
epoch_transition_certificate_body_root
evidence_commit_certificate_body_root
initialize_commit_replay_state
initialize_commit_window_state
initialize_distributed_commit_state
initialize_risk_assessment_chain
initialize_support_lease_replay_state
issue_action_permission
issue_commit_evaluation_context
issue_commit_liveness_input
issue_commit_threshold_snapshot
issue_counterevidence_disposition
issue_distributed_commit_certificate
issue_eligible_principal_snapshot
issue_epoch_transition_certificate
issue_evidence_commit_certificate
issue_local_commit_receipt
issue_outcome_certificate
issue_risk_assessment
issue_support_lease
outcome_certificate_body_root
revoke_support_lease
switch_support_lease
transition_distributed_commit_epoch
verify_challenge_attestation
verify_distributed_commit_finality
verify_evidence_commit_finality
verify_local_commit_finality
verify_observation_attestation
verify_principal_attestation
verify_quorum_witness
verify_signal_input
verify_stop_resolution
```

### 4.1 Deprecation decision

These functions remain Draft trusted-host compatibility in WP-01. They are not
Stable credentials, are not accepted by v2 consumers, and are not marked
Deprecated before a usable replacement exists.

For the `0.2.0rc1` replacement milestone, every one of the 36 lifecycle entries
must be reviewed individually:

1. export a v2 counterpart that accepts a live, scope-bound authority session
   (or, for a pure historical proof reader/root helper, accepts explicit
   non-authoritative classification data and independently verifies inclusion);
2. give that counterpart a canonical public owner, public shape entry,
   lifecycle entry, typed reader/validator where applicable, and negative tests;
3. record its exact fully-qualified replacement in the old symbol's lifecycle
   entry;
4. only then change the old symbol from `draft` to `deprecated`, with
   `remove_after: 0.3.0`; and
5. emit a `DeprecationWarning` on legacy invocation without changing v1 result
   bytes, diagnostic codes, or historical proof meaning.

There is no family-level wildcard replacement. A missing per-symbol
replacement keeps that legacy symbol Draft and blocks removal of the cohort; it
does not justify inventing an alias or routing it through a v2 entrypoint.

`0.3.0` is the earliest possible removal, not a promised removal release. A
symbol may be removed only when all of these gates pass:

- its replacement shipped no later than `0.2.0rc1` and the lifecycle registry
  has a non-null exact replacement plus `remove_after: 0.3.0`;
- all Stable candidates, provider-free examples, source-v4 checks, v2 schemas,
  Authority TCK vectors, reference adapter, and independent adapter use no v1
  issuance path;
- restart, concurrent CAS, tamper, cross-scope, revocation, retirement,
  authenticated-verifier, and no-fallback negative matrices pass;
- built wheel and sdist external-CWD consumers pass migration fixtures;
- the external-consumer audit finds no undeclared dependency, or an explicit
  later removal window is chosen;
- the changelog, migration note, removal ledger, public inventory, and package
  version all agree; and
- historical v1 proof readers/codecs required by retention remain available,
  even when their old issuance entrypoint is removed.

### 4.2 No compatibility upgrade

A v1 return value from this cohort can be inspected and archived. It cannot be
upgraded to v2 authority by copying fields into a new dataclass. Migration must
re-establish the scope/session, verify StateStore inclusion, bind the current
grant and complete read-set, and issue/commit a new v2 transition when a new
action is required.

## 5. Staged data and call migration

The stages are cumulative. A later stage cannot activate while an earlier
authority dependency remains a process-local or caller-asserted shortcut.

### Stage A — Freeze compatibility and selectors (WP-01)

- keep legacy manifests on `pheroos.protocol.v1`;
- reserve the exact v2 identifiers and closed manifest object;
- characterize v1 issuer, output Boolean, and finalize/head behavior;
- inventory all 36 public signatures and reserve their lifecycle decisions;
- publish the threat model, denial codes, negative gates, and no-fallback rule;
- keep the reserved v2 manifest/profile/wire readers unsupported until their
  implementation is complete; this stage predates the additive WP-02
  `GovernanceStateReaderV2` storage/finality slice.

### Stage B — StateStore and historical finality (WP-02)

Introduce the exact `pheroos-governance-state-store-v2` contract and total
typed commit result. The store must atomically validate the finite canonical
`pheroos-governance-authority-read-set-v2`, append state, authority-critical
Trace, and receipt, and return one typed disposition.

The closed `GovernanceCommitDispositionV2` wire set is exactly
`COMMITTED`, `DENIED`, `RETRY_REQUIRED`, `FINALITY_UNAVAILABLE`, and `INVALID`.
Only `COMMITTED` carries a committed transition, receipt, and position. The
closed `GovernanceCommitPositionV2` wire set is exactly `CURRENT`,
`SUPERSEDED`, and `SEALED`. Conflict/stale, unavailable, and malformed are
reason categories in the threat-model matrix; at the StateStore commit ABI they
map respectively to `RETRY_REQUIRED`, `FINALITY_UNAVAILABLE`, and `INVALID`.
They are not extra disposition or position wire values.

Migration of commit/finalize is:

```text
v1: prepare -> atomic_commit -> require receipt == current head -> finalize

v2: prepare
    -> atomic_commit_v2(full read-set)
    -> load and verify historical inclusion
    -> inspect CURRENT / SUPERSEDED / SEALED position
    -> finalize delivery and current actionability independently
```

A legal successor changes position to `SUPERSEDED`; it never changes the
historical committed disposition to `INVALID`. Unknown commit outcome after a
crash or unavailable response is reconciled by transition id before retry.

### Stage C — Issuer session (WP-03)

Bind a non-portable, least-privilege session to the selected StateStore,
authority domain, exact scope, allowed operation set, optional target/action
bounds, issued epoch/revision, expiry, and revocation generation. The local
profile uses trusted-host capability custody. The authenticated profile also
requires its host-selected verifier. V2 issuers accept the session; they do not
accept `AuthorityLevel` as credential.

The 36 legacy symbols remain isolated in v1 and cannot be called by an
authority v2 profile reader, consumer, reference adapter, or path intended for
later Stable promotion.

### Stage D — Baseline output (WP-04)

Replace caller-provided publication truth with one aggregate v2 journey that:

- recomputes the declared decision and safe fallback;
- binds evidence, provenance, stop resolution, manifest/policy, exact output
  payload, issuer grant/revocation, and current action permission;
- validates all authority heads in the same atomic read-set as the output
  authorization commit; and
- exposes publish/execute authority only from a verified durable commit.

Every Governance terminal outcome remains deliverable. Delivery, publication,
and execution are distinct statuses; a publication denial cannot hide the
final output or create an unbounded pending loop.

### Stage E — Replay, rehydration, and retirement (WP-05)

Move replay/window/certificate currentness needed by a path intended for later
Stable promotion from process-local registries into append-only StateStore
streams. Replay advance is CAS-bound to scope, target/action, epoch, payload,
grant, ledger, and prior root. Restart creates a new local capability handle
but cannot change canonical record roots.

Portable bytes rehydrate as detached data. They regain historical authority
only after exact inclusion verification, and regain current actionability only
after all current heads, grant, domain, and replay predicates pass. Retirement
is an atomic seal: it denies new writes and new action authority while
preserving historical proofs and delivery reconciliation.

### Stage F — Trace and delivery projections (WP-06/WP-07)

Authority-critical Trace is part of the StateStore atomic batch. Scoped
TraceStore and delivery outbox state are idempotent projections keyed by stable
identity and can be rebuilt from committed inclusion. Projection success,
delivery receipts, and Trace presence never create or upgrade authority.

### Stage G — Schema/profile readers, profile Conformance, and TCK (WP-08/WP-09)

Add new files for the reserved v3/v2 schema IDs without changing any existing
schema bytes. Activate exact profile dispatch and source-v4; consume the
already implemented Draft diagnostic registry, its lifecycle records, and
StateStore Conformance without redefining them; then add verifier Conformance
and the implementation-neutral authority TCK. Active v2 checks return PASS or
FAIL; they do not skip or report N/A.

Only after the reference implementation and an independent adapter pass the
same exact-version TCK may an authority v2 schema/profile reader return
authority-bearing typed objects.

### Stage H — Release lanes (WP-10 through WP-13)

Run the full regression, property/mutation/performance, package-consumer,
runtime-adapter, and release-candidate matrices. Activate repository protection
before merging implementation. Publish the replacement lifecycle entries no
later than `0.2.0rc1`; do not remove the v1 cohort before all `0.3.0` gates pass.

## 6. Portable and historical proof preservation

Migration is append-only with respect to proof meaning:

- existing schema `$id` values and checked-in bytes are immutable;
- v1 wire/codecs/readers continue to parse the exact v1 historical form;
- an authority v2 schema/profile reader never guesses that a v1 record is v2
  from matching fields;
- no migrator rewrites a v1 receipt, transition, certificate, Trace event, or
  canonical root in place;
- historical verification reports both inclusion and current position; it does
  not require the historical receipt to equal the current head;
- legal successors and domain retirement preserve earlier inclusion proofs;
- removed issuance APIs do not imply removal of retained proof readers;
- a detached portable payload is data until the deployment-selected StateStore
  verifies inclusion under the matching ledger/profile version; and
- current publish/execute always requires fresh currentness, grant, replay, and
  action checks, even when historical validity succeeds.

The registry-free `pheroos.governance.historical_certificate` leaf retains the
exact Draft v1 portable certificate codec, fingerprint, and attestation reader
for archived `pheroos-evidence-commit-certificate-v1` bytes. It exposes the
same function objects as the legacy certificate facade, but it cannot issue a
certificate, verify current finality, consult process-local issuance identity,
or upgrade a v1 payload into StateStore authority. Commit TCK v2 uses this
historical reader only for its frozen certificate-leaf integrity vector. Its
deadline vector similarly uses the pure registry-free
`pheroos.governance.commit_semantics` selector; neither operation is an
authority-v2 credential check.

If retention policy permits compaction, the adapter must retain a checkpoint or
inclusion proof sufficient to reproduce the same verification result and seal
root. Compaction may change storage layout, not authority truth.

## 7. Reserved diagnostics and negative-test gates

The codes in this section are implemented exact Draft v2 identifiers. WP-02
adds them to the Protocol-owned closed registry, records their Draft lifecycle,
and exercises their StateStore disposition mapping in Conformance. WP-08 must
consume, not recreate, that registry when it adds schema/profile dispatch and
profile-level Conformance artifacts. Until the complete profile activates,
current v1 code must not emit these codes or imply that authority v2 is
available.

### 7.1 Exact Draft diagnostic registry

The implementation-facing registry has exactly 17 diagnostics. The AH labels
in the threat model group security invariants; they are not a second 14-code
wire registry. One invariant may exercise multiple concrete diagnostics, and
one concrete diagnostic may protect multiple invariants.

The single canonical enum owner is
`pheroos.protocol.authority_v2.AuthorityDiagnosticCodeV2`. Governance imports
and consumes that same enum and owns its commit-disposition mapping; it may
re-export the same object but must not define a second registry. This placement
preserves the Protocol import boundary because the Protocol reader owns profile
dispatch and cannot import Governance. An input rejected before authority-v2
dispatch keeps the existing generic Protocol schema/version diagnostic.

| Test ID | Exact Draft diagnostic | Commit disposition | Required negative gate |
| --- | --- | --- | --- |
| `AUTH-V2-DIAG-001` | `authority_profile_unsupported` | `INVALID` | Missing, blank, unknown, case-mutated, cross-version, or internally inconsistent v2 profile selection rejects before typed authority construction; no v1 fallback |
| `AUTH-V2-DIAG-002` | `authority_session_required` | `DENIED` | Public constructor, proposal, `AuthorityLevel`, Boolean, digest, or same-shaped object without a live session creates no authority |
| `AUTH-V2-DIAG-003` | `authority_session_store_mismatch` | `INVALID` | Session bound to store/ledger/domain A is rejected by B, including after copy, pickle, restart, or reader-for-writer substitution |
| `AUTH-V2-DIAG-004` | `authority_scope_mismatch` | `INVALID` | Mutate tenant/run `scope_ref`; no issuance, recovery, replay advance, commit, or action escapes the original scope |
| `AUTH-V2-DIAG-005` | `authority_operation_denied` | `DENIED` | A valid session used outside its closed operation set or target/action bounds is denied without expanding the grant |
| `AUTH-V2-DIAG-006` | `authority_binding_mismatch` | `INVALID` | Mutate target, candidate/outcome, action, payload, epoch, ledger, transition, replay, or grant binding independently |
| `AUTH-V2-DIAG-007` | `authority_grant_unverified` | `DENIED` | Authenticated profile with absent, unknown, failing, request-selected, or downgraded verifier evidence cannot bind a session |
| `AUTH-V2-DIAG-008` | `authority_grant_expired` | `DENIED` | Expired grant denies new issuance/current action but does not rewrite historical inclusion |
| `AUTH-V2-DIAG-009` | `authority_grant_revoked` | `DENIED` | Revoked generation denies new issuance/current action while earlier committed proof remains verifiable |
| `AUTH-V2-DIAG-010` | `governance_read_set_invalid` | `INVALID` | Empty/oversized, duplicate, unsorted, noncanonical, malformed-root, or incomplete read-set commits nothing |
| `AUTH-V2-DIAG-011` | `governance_read_set_stale` | `RETRY_REQUIRED` | Advance each expected revision/root after prepare; the entire state/Trace/receipt batch remains unchanged |
| `AUTH-V2-DIAG-012` | `governance_transition_conflict` | `INVALID` | Reuse one transition id with different canonical bytes; exact retry remains idempotent but substitution is invalid |
| `AUTH-V2-DIAG-013` | `governance_domain_sealed` | `DENIED` | Post-seal issue/commit/replay/recover-current fails; pre-seal proof and permitted delivery remain readable |
| `AUTH-V2-DIAG-014` | `governance_finality_unavailable` | `FINALITY_UNAVAILABLE` | Inject unknown commit outcome/store unavailability; reconcile by transition id and perform no external effect or downgrade |
| `AUTH-V2-DIAG-015` | `governance_committed_transition_invalid` | `INVALID` | Missing/tampered/cross-ledger transition, receipt, batch, state root, or inclusion proof is invalid; a legal successor is not |
| `AUTH-V2-DIAG-016` | `governance_action_not_authorized` | `DENIED` | Delivery remains reachable while missing/stale/wrong-action/wrong-payload publish or execute authority is denied |
| `AUTH-V2-DIAG-017` | `governance_trace_lineage_invalid` | `INVALID` | Missing, reordered, duplicated, substituted, cross-scope, or noncanonical required Trace lineage prevents commit/recovery |

The registry uses only the five ADR commit dispositions. In particular,
read-set races are `RETRY_REQUIRED`, unknown finality is
`FINALITY_UNAVAILABLE`, and structural/conflicting proof is `INVALID`;
`CONFLICT`, `STALE`, `UNAVAILABLE`, and `MALFORMED` are not additional commit
wire values.

### 7.2 AH-to-diagnostic and negative-test coverage

| Threat test | Invariant | Required concrete diagnostics | Required negative case |
| --- | --- | --- | --- |
| `AUTH-V2-AH-001` | AH-001 | `authority_session_required`, `authority_operation_denied`, `governance_action_not_authorized` | Agent/model/tool authority-shaped proposal cannot issue, commit, or authorize; all authority-write counters remain zero |
| `AUTH-V2-AH-002` | AH-002 | `authority_session_required` | `AuthorityLevel.GOVERNANCE` without a live session is denied |
| `AUTH-V2-AH-003` | AH-003 | `authority_profile_unsupported`, `authority_scope_mismatch`, `authority_binding_mismatch`, `governance_trace_lineage_invalid` | Mutate profile, scope, operation/grant, target/action/payload/epoch/ledger, and Trace bindings one leaf at a time |
| `AUTH-V2-AH-004` | AH-004 | `governance_committed_transition_invalid` | Detached payload, copied receipt, or correct digest absent from selected StateStore history remains data |
| `AUTH-V2-AH-005` | AH-005 | `governance_action_not_authorized` | Included superseded transition stays historically valid but cannot publish/execute; delivery remains reachable |
| `AUTH-V2-AH-006` | AH-006 | `governance_committed_transition_invalid` | A legal successor yields `COMMITTED` plus `SUPERSEDED` with no diagnostic; only tampered/missing inclusion is invalid |
| `AUTH-V2-AH-007` | AH-007 | `governance_action_not_authorized` | Every declared terminal outcome delivers while publish and execute independently deny without exact current grants |
| `AUTH-V2-AH-008` | AH-008 | `authority_session_store_mismatch`, `authority_scope_mismatch`, `authority_binding_mismatch` | Replay across store, scope, target, action, payload, epoch, operation, or ledger fails independently |
| `AUTH-V2-AH-009` | AH-009 | `authority_session_required`, `authority_session_store_mismatch`, `authority_operation_denied`, `authority_grant_unverified`, `authority_grant_expired`, `authority_grant_revoked` | Copy/serialize/reconstruct, reader-for-writer, wrong store/operation, unverifiable, expired, and revoked capability cases all fail |
| `AUTH-V2-AH-010` | AH-010 | `governance_domain_sealed` | Seal rejects new authority writes/replay/current recovery while retaining historical proof and delivery |
| `AUTH-V2-AH-011` | AH-011 | `authority_session_required`, `governance_committed_transition_invalid`, `governance_action_not_authorized` | Boolean, digest, dataclass, enum, receipt/Trace id, outbox row, and delivery success each fail as authority |
| `AUTH-V2-AH-012` | AH-012 | `governance_read_set_stale` | Race 32 replay consumers, restart the winner, assert one durable advance and typed losers without partial Trace |
| `AUTH-V2-AH-013` | AH-013 | all 17, including `governance_finality_unavailable` | Vary exception text and every normal refusal/failure stage; exact diagnostic and five-value disposition remain unchanged |
| `AUTH-V2-AH-014` | AH-014 | `governance_read_set_invalid`, `governance_read_set_stale`, `governance_transition_conflict`, `governance_trace_lineage_invalid` | Omit/mutate every authority head and race each after evaluation; no output authority or partial state/Trace/receipt escapes |

Reader/selector negative cases remain mandatory: missing selectors, all v1/v2
semantic and schema-v2/v3 cross-products, missing `authority_policy`, mutation
of each of its eight exact fields, unknown critical fields, authenticated
verifier absence, and attempted legacy fallback must fail before authority is
returned. When the input has selected authority v2 far enough to use this
registry, the diagnostic is `authority_profile_unsupported`. Inputs rejected
before authority-v2 dispatch retain the existing Protocol schema-version
diagnostic and are never relabeled as successful v2 selection.

`DENIED` never creates an authority receipt, inclusion proof, committed
transition, or position. After a scope/session exists and where policy requires
auditing, the implementation must make one idempotent append attempt for a
deterministic canonical denial `TraceEvent` and expose the append outcome as
separate non-authority audit telemetry. It is not a
`pheroos-governance-trace-batch-v2` authority commit, cannot be loaded as
committed authority, and its success or failure does not change the denial.
Pre-auth malformed input cannot establish a scope or grant and therefore must
not be allowed to force StateStore or canonical Trace writes.

All diagnostic payloads must carry a stable code and canonical path without
secret values. Normal denial, retry-required, finality-unavailable, and invalid
outcomes are total typed results; exception message text is never a protocol
branch.

## 8. Failure and rollback policy

### 8.1 Before v2 activation

The Draft `GovernanceStateReaderV2` StateStore contract and reference reader are
implemented and Conformance-backed for the WP-02 storage/finality slice. The
authority v2 manifest/schema/wire readers that select and materialize a complete
profile remain unsupported. A deployment may continue serving explicit v1
scopes. Rolling back documentation or feature flags must not mutate frozen
schema/TCK/public inventory bytes. No component may advertise a v2 profile as
PASS, Stable, or production-ready.

### 8.2 During dual-version rollout

- route by exact manifest selector before constructing authority objects;
- maintain separate v1 and v2 authority domains and idempotency namespaces;
- permit comparison/shadow evaluation only when the shadow result cannot write,
  authorize, publish, execute, or affect the live result;
- never write both profiles for one operation;
- on v2 denial or unavailability, return its typed result and preserve terminal
  delivery; do not invoke v1;
- when the authenticated verifier is unavailable or inconclusive, deny session
  binding; do not switch to local; and
- when StateStore commit disposition is unknown, reconcile the exact transition
  id and inclusion before retrying or performing an external effect.

### 8.3 After the first v2 commit in a domain

That authority domain cannot be downgraded to v1. A rollback may stop new v2
traffic, keep the v2 reader/verifier available, reconcile in-flight
transitions, and seal the domain. If service must resume on legacy behavior, it
must use a newly declared legacy scope/domain with no claim of continuity or
inheritance from v2 authority. V2 history, receipts, Trace batches, and proof
readers remain retained.

### 8.4 Release abort criteria

Abort v2 activation, without falling back in-place, if any of these occurs:

- schema/profile dispatch is ambiguous or any selector silently falls back;
- a 36-cohort v1 issuer is reachable from a v2 consumer;
- a historical commit becomes invalid after a legal successor;
- any read-set race yields a partial state, Trace, receipt, or action result;
- a restart loses replay, seal, revocation, or historical inclusion state;
- local and authenticated guarantees are reported as equivalent;
- a terminal outcome becomes undeliverable because publication/execution is denied;
- reference and independent adapters disagree on a TCK vector; or
- a release artifact cannot verify retained v1 historical proof.

Rollback success means authority truth remains explainable and recoverable. It
does not mean silently obtaining a result through a weaker profile.

## 9. Activation and promotion checklist

The exact local profile reached Draft activation through these completed gates:

- [x] Capability/Protocol v3 and Authority/TCK v2 use new checked artifacts,
      exact selectors, strict readers, and the static Schema Catalog;
- [x] StateStore v2 proves atomic read-set, state, critical Trace, receipt,
      restart, historical inclusion, seal, and independent-adapter behavior;
- [x] local sessions are non-portable, least-privilege, scope/store/operation
      bound, revocable, and absent from agent/Driver/Trace/wire payloads;
- [x] Baseline Output v2 has no caller publication Boolean or read-then-commit
      TOCTOU;
- [x] production-path replay/currentness is StateStore-backed and restart-safe;
- [x] authority diagnostics and their negative tests are registered;
- [x] StateStore, Authority Session, and Baseline Output exact matrices pass
      reference and independent adapters, and their expected-free scoped TCK
      vocabulary is closed;
- [x] the reviewed 86-name legacy authority cohort has exported, tested,
      lifecycle-recorded v2 replacements or an explicit data-only retention;
- [x] Runtime Integration v1 proves exact local selection, recovery, current
      action gates, and v1 baseline non-upgrade; and
- [x] v1 manifests/examples/conformance remain available without implicit
      migration.

The following gates remain mandatory for authenticated production or Stable
promotion and are not implied by local Draft activation:

- [ ] a host-selected independent issuer-grant verifier passes its exact
      external Conformance profile with no authenticated-to-local fallback;
- [ ] the final Stable candidate, external adapter, and reference runtime pass
      the exact RC artifacts;
- [ ] wheel/sdist/RC supply-chain evidence and release notes state the real
      guarantee and arbitrary same-process Python limitation; and
- [ ] lifecycle promotion completes through the protected-main release gate.

`pheroos.protocol.v2` with the exact local profile is therefore active Draft.
Unknown, aliased, cross-version, or incomplete selections still fail with a
typed rejection; no path performs compatibility conversion or lower-assurance
fallback.
