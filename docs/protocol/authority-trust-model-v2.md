# Authority v2 Trust Model

Status: **accepted and implemented trust boundary for the Draft local profile;
authenticated production promotion remains gated**

Acceptance freezes the design boundary. The Draft StateStore, Authority
Session, Baseline Output, schema/reader, Runtime Integration, reference Store,
and independent adapter contracts now implement the local scoped-authority
path. This makes the exact local manifest selection active as Draft; it does
not make the ABI Stable, authenticate arbitrary callers, or provide a
production runtime. The authenticated path retains its external-verifier and
promotion gates.

This document freezes the security boundary that the scoped authority work must
implement before any authority v2 profile can be promoted. It uses the accepted
exact identifiers:

- policy: `pheroos-scoped-authority-policy-v2`;
- local profile: `pheroos-scoped-authority-local-v2`;
- authenticated profile: `pheroos-scoped-authority-authenticated-v2`;
- StateStore ABI: `pheroos-governance-state-store-v2`;
- atomic Trace batch: `pheroos-governance-trace-batch-v2`; and
- canonical read-set: `pheroos-governance-authority-read-set-v2`.

The accepted [authority version decision](authority-v2-decision.md) freezes the
exact semantic, schema, wire, canonicalization, ledger, verifier, TCK, and
Conformance identifiers. The identifiers above MUST NOT be renamed or
reinterpreted without an explicit migration decision. Draft local activation
does not waive any requirement for authenticated or Stable promotion.

In the remainder of this document, “StateStore” means an implementation of
`pheroos-governance-state-store-v2`, “atomic Trace batch” means
`pheroos-governance-trace-batch-v2`, and “authority read-set” means
`pheroos-governance-authority-read-set-v2`. A v2 manifest opts in only by
declaring `pheroos-scoped-authority-policy-v2` and selecting exactly
`pheroos-scoped-authority-local-v2` or
`pheroos-scoped-authority-authenticated-v2`; aliases and version ranges fail
closed.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are to be interpreted as normative requirements for the selected
authority v2 profile.

This is a protocol-core trust model. It does not define an application runtime,
identity provider, database, key manager, network service, or generic security
manager.

## 1. Security objective

Authority v2 makes four questions unambiguous:

1. **Who issues?** A trusted authority coordinator may request issuance only
   while holding a local, scope-bound, operation-limited issuer capability. A
   `pheroos-scoped-authority-authenticated-v2` profile additionally uses a
   host-selected external `IssuerGrantVerifier` for the declared grant.
2. **Who commits?** Only the deployment-selected
   `pheroos-governance-state-store-v2` writer commits an authority transition
   after Governance has validated its complete canonical read-set, bindings,
   grant, and required Trace lineage.
3. **Who recovers?** A trusted coordinator may rehydrate portable bytes as data,
   but only the selected StateStore can prove committed inclusion. Recovery
   returns local authority only after inclusion, currentness when required, and
   the current local grant are all revalidated.
4. **Who executes?** Governance authorizes a particular action; it never
   performs the action. An external runtime executor may publish or execute only
   from an independently current, action-scoped authorization. Returning or
   transporting a Governance terminal outcome to the requesting runtime is
   always delivery-eligible and is not an external authority action; publish or
   execute denial cannot suppress it.

The trust root is therefore not an agent, enum, Boolean, digest, dataclass,
receipt identifier, Trace record, or model response. For the local reference
`pheroos-scoped-authority-local-v2` profile, the trust root is the combination
of the trusted coordinator's local issuer capability and the selected
`pheroos-governance-state-store-v2` implementation's atomic committed history.
The `pheroos-scoped-authority-authenticated-v2` profile also includes its
host-selected external issuer-grant verifier.

## 2. Protected assets

| Asset | Required property | Consequence of compromise |
| --- | --- | --- |
| Authority history | Append-only inclusion and immutable historical validity | A transition can be invented, removed, or rewritten |
| Current heads | Scope-local currentness with atomic compare-and-swap | Stale authority can be used as current authority |
| Issuer grants | Least privilege, scope and operation binding, expiry/revocation | An untrusted caller can issue authoritative envelopes |
| Canonical read-set | Complete, deterministic, atomically checked | Output or another authority commit can pass a TOCTOU window |
| Action authorization | Exact target, action, outcome/payload, epoch, and replay binding | A valid decision can be reused for a different external effect |
| Replay ledger | Durable monotonic advance across restart | One-shot authority can be replayed or a valid retry can be lost |
| Domain lifecycle | Active/sealed/retired state and terminal root | New authority can be written after retirement |
| Authority-critical Trace | Same atomic truth as its state transition | A commit cannot be reconstructed or audited |
| Terminal outcome delivery | Every issued terminal outcome remains deliverable | Strict authorization can suppress the final protocol result |
| Profile and schema dispatch | Exact, fail-closed version selection | Legacy bytes can be reinterpreted as stronger authority |

Confidentiality of model prompts, business data, signing keys, and provider
credentials is an external deployment concern. Protocol-core protects their
references and authority bindings, not their secret material.

## 3. Actors and authority

| Actor | Trust level | May do | Must never be treated as |
| --- | --- | --- | --- |
| Agent, scout, model, or planner | Untrusted proposal source | Produce reports, candidates, evidence references, and requested actions | Issuer, committer, verifier, or executor authority |
| Tool/provider adapter | Untrusted result source at the Governance boundary | Return result data and provenance | Proof that a result is true or that an action is allowed |
| External runtime | Mixed-trust orchestration boundary | Establish a request, transport records, schedule work, and deliver results | Authority merely because it called a core function |
| Trusted authority coordinator | Trusted capability custodian | Hold a local issuer capability, establish an authenticated scope/session, prepare requests, and call Governance/StateStore | Durable history or permission to exceed its grant |
| Governance Core | Trusted deterministic decision owner | Validate declarations, bindings, grants, read-sets, and decide authority semantics | Secret manager, executor, database, or network authenticator |
| StateStore adapter | Deployment-selected durable trust root | Atomically verify preconditions and append state, receipt, and authority-critical Trace | Identity issuer, policy engine, or external action executor |
| Host-selected external `IssuerGrantVerifier` | Authenticated-profile identity trust input | Verify an issuer-grant assertion for the exact envelope root | Request-selected, required by the local profile, or implemented inside core |
| Projector/reconciler | Trusted for availability, not authority | Rebuild query Trace and outbox records from committed inclusion | Issuer or source of committed truth |
| Scoped TraceStore | Query/archive projection | Store idempotently projected canonical Trace | Authority ledger, commit proof, event bus, or identity proof |
| Delivery outbox | Runtime transport coordination | Reconcile stable delivery identities and delivery status without gating result eligibility | Publication/execution authority or a prerequisite for returning the outcome |
| External action executor | Trusted effect boundary | Publish or execute an exact authorized action | Governance decision maker or issuer |
| Deployment operator | Administrative trust boundary | Select adapters, grants, verifier, and domain lifecycle policy | Implicit authority without a committed administrative grant |

### 3.1 Operation ownership matrix

| Operation | Authorized actor | Required basis | Forbidden shortcut |
| --- | --- | --- | --- |
| Produce a proposal | Any declared source | Declared source and provenance | Label the proposal `GOVERNANCE` and treat it as verified |
| Establish a scope/session | Trusted coordinator | Deployment authentication outside core and canonical `scope_ref` | Derive trust from caller-controlled tenant/run text alone |
| Issue an authority envelope | Governance issuance function called by the coordinator | Live local issuer capability, exact grant, exact envelope bindings, and authenticated-profile host-selected verifier result | Public constructor, enum, Boolean, digest, copied dataclass, or receipt id |
| Prepare a transition | Governance | Valid current snapshot and complete canonical authority read-set | Read current heads, discard them, and submit an unconditioned write |
| Commit a transition | StateStore writer | Atomic validation of every precondition plus state and critical Trace batch | Commit state and Trace in separate truth stores |
| Verify historical inclusion | StateStore reader/verifier | Exact transition/receipt root included in committed history | Check only receipt shape, hash equality, or current head equality |
| Recover local authority | Trusted coordinator plus Governance and StateStore | Parsed payload, verified inclusion, matching profile/bindings, local live grant, and currentness if an action is requested | Deserialize a portable capability or trust a portable issuer object |
| Advance replay | StateStore writer | Atomic CAS over the replay head in the same scope/epoch/action binding | Process-global sentinel or check-then-write |
| Seal/retire a domain | StateStore writer after Governance authorization | Administrative issuer grant and atomic terminal seal transition | Delete history or set a caller-owned Boolean |
| Return/transport a terminal outcome | Runtime delivery path | Governance-issued terminal outcome; a stable delivery identity MAY coordinate retries but is not a gate | Require a current head, issuer grant, `ActionPermission`, outbox success, or action authorization |
| Publish an output | External executor | Current `publish` authorization for exact target/output/action/epoch and replay state | Reuse delivery success, a publication Boolean, or a prior authorization |
| Execute an external action | External executor | Current `execute` authorization for exact target/action/payload/epoch and replay state | Treat publication or outcome commit as execution permission |
| Project Trace/outbox state | Projector/reconciler | Verified committed inclusion and idempotent projection identity | Let projection success create or upgrade authority |

## 4. Trust zones

```text
Z0  Untrusted sources
    agents, models, scouts, provider/tool results
             |
Z1  Pre-auth transport and parsing
    bytes are structurally checked; no scope/session authority exists yet
             |
Z2  Trusted coordinator boundary
    authenticated deployment session + local issuer capability custody
             |
Z3  Governance Core
    pure contract validation, deterministic decision, transition preparation
             |
Z4  StateStore authority boundary
    atomic read-set validation + state + receipt + critical Trace history
             |
Z5  Derived persistence
    idempotent Scoped TraceStore and delivery/outbox projections
             |
Z6  External effects
    publication, tool or provider execution
```

Crossing from Z0 or Z1 into Z2 does not itself create authority. Crossing from
Z3 into Z4 creates durable authority only after the StateStore returns a
verified committed result. Z5 is reconstructable from Z4 and cannot strengthen
or revoke Z4 truth. Crossing into Z6 requires an exact current publish/execute
authorization. Returning or transporting a terminal outcome to the requesting
runtime is not a Z6 external effect and is not equivalent to publication or
execution.

## 5. Attacker model and assumptions

The selected authority v2 profile MUST resist an attacker that can:

- fully control agent/model/scout outputs and requested actions;
- control or tamper with tool/provider result payloads and provenance claims;
- submit malformed, oversized-at-the-runtime-boundary, unknown-version, or
  semantically inconsistent portable records;
- copy, reconstruct, mutate, or serialize public Python dataclasses;
- supply valid-looking `AuthorityLevel` values, booleans, identifiers, and
  canonical SHA-256 digests;
- replay a valid record in another scope, target, action, epoch, ledger, or
  payload context;
- reorder, duplicate, delay, or retry requests;
- race concurrent coordinators against the same StateStore heads;
- crash a coordinator, projector, or executor between prepare, commit,
  projection, delivery, and action completion;
- present a historical receipt after legal successor transitions;
- cause TraceStore/outbox projection failure or temporary StateStore
  unavailability;
- attempt check-then-commit TOCTOU by changing any authority head after
  evaluation; and
- try to write or recover current action authority after a domain is sealed or
  retired.

The model assumes the deployment-selected StateStore correctly implements the
v2 conformance contract: atomicity, append-only inclusion, CAS, isolation,
durability, scope separation, and restart recovery. A malicious StateStore can
forge the local reference profile's trust root. Detecting or tolerating that
requires an authenticated or distributed profile with external attestation or
witness guarantees; a digest alone does not solve it.

The model also assumes the trusted coordinator protects its local issuer
capability and that the action executor enforces Governance decisions. A
compromised executor can perform external effects outside the protocol; PheroOS
can make that violation observable, but cannot physically prevent it.

### 5.1 Explicit process-isolation limit

Arbitrary untrusted Python running in the same process as the coordinator or
StateStore writer is **outside the isolation guarantee**. Python reflection,
`monkeypatch`, debugger access, native extensions, and direct memory access can
bypass ordinary object-capability encapsulation. A deployment that executes
untrusted Python MUST isolate it from the coordinator and StateStore writer by
a process or stronger security boundary. The protocol capability design limits
authorized API use; it is not a same-process malicious-code sandbox.

## 6. Record classification

The implementation MUST preserve these semantic classes. Public type names and
exact identifiers frozen by the accepted ADR cannot vary; private helper names
may differ without changing these classes:

| Class | Examples | Authority semantics | Portable |
| --- | --- | --- | --- |
| Declaration | Manifest policy, candidate/target declarations, profile selection | Constrains later decisions; not a credential | Yes |
| Proposal data | Agent report, model output, signal, evidence reference, requested action | Never authoritative by itself | Yes |
| Classification label | `AuthorityLevel`, status enum, assurance label | Describes a record; never proves issuer identity or possession | Yes |
| Local issuer capability | Opaque scope/operation grant handle held by coordinator | Permits a bounded issuance request while live | **No** |
| Portable issuer/grant reference | Issuer id, grant id, attestation envelope | Data until verified by the selected verifier and local grant policy | Yes |
| Prepared transition | Canonical write batch and read preconditions | Proposed state change; no durable authority | Yes as data |
| Commit receipt | Exact inclusion coordinates and roots | Evidence input; not authority until verified against selected StateStore history | Yes |
| Committed transition | StateStore-verified state + receipt + critical Trace inclusion | Historically authoritative | Yes with inclusion verification |
| Current action authorization | Committed action record plus current heads, live grant, replay state, and domain status | Authorizes exactly one declared `publish` or `execute` external effect | Yes as proof input; revalidation required |
| Domain seal/retirement record | Terminal scope root and lifecycle disposition | Closes new authority writes while retaining history | Yes with inclusion verification |
| Typed denial/result | `COMMITTED`, `DENIED`, `RETRY_REQUIRED`, `FINALITY_UNAVAILABLE`, or `INVALID` disposition | Observable protocol result; denial does not grant authority | Yes |
| Trace event/projection | Authority lineage copied to a scoped query store | Explains authority; never creates it | Yes |
| Delivery/outbox record | Stable delivery id and sink status | Transport coordination only; never a result-eligibility gate or publish/execute authority | Runtime-defined |

Public constructors MAY construct portable data. They MUST NOT manufacture the
local issuer capability or mark an unverified record as committed/current. A
hash proves that bytes match a digest; it does not prove who produced the bytes,
whether they were committed, or whether they remain actionable.

## 7. Required envelope and read-set bindings

Every v2 envelope capable of proposing an authority commit, changing replay
currentness, or authorizing an external action MUST bind, directly or through a
canonical root, all fields relevant to that operation:

- exact profile, schema, wire, and ledger versions;
- `scope_ref` and operation kind;
- issuer and grant references plus the selected attestation policy;
- target and candidate/outcome reference when the operation concerns a
  decision;
- action class (`publish` or `execute`), action reference, and exact
  output/payload root when the operation concerns an effect;
- epoch and replay stream/reference;
- authority ledger reference and transition identifier;
- complete canonical authority read-set root;
- required authority-critical Trace lineage root; and
- canonical validity bounds and revocation generation declared by the profile.

Terminal outcome delivery is not an action class or external authority effect.
Its stable delivery identity is runtime transport metadata: it MUST NOT appear
as an authority precondition or authority read-set head. Missing delivery
identity, outbox state, or transport acknowledgement cannot make a
Governance-issued terminal outcome ineligible for return to the requesting
runtime.

An operation MUST fail closed when a required binding is absent, unknown,
duplicated, non-canonical, or mismatched. Optional extension fields are
non-authoritative unless a later exact profile version promotes them into the
canonical root.

Canonical roots MUST be acyclic: an envelope/read-set binds required predecessor
lineage, `pheroos-governance-trace-batch-v2` binds the newly prepared transition
and its new critical Trace records, and the store receipt binds that completed
batch. An implementation MUST NOT solve a transition/Trace hash cycle by
omitting either side from committed truth.

The authority read-set contains 1 through 128
`(stream_ref, expected_revision, expected_root)` entries. Its exact canonical
encoding is frozen by the authority version decision and MUST:

1. reject duplicate `stream_ref` entries;
2. require NFC `stream_ref` values and sort them by unsigned UTF-8 bytes;
3. use JSON integer revisions in `0..9007199254740991`, never booleans, and
   lowercase canonical SHA-256 roots;
4. include every head used to authorize the result, including output,
   permission, stop, replay, membership, evidence, risk, policy, and domain
   lifecycle heads when applicable; and
5. be checked in the same StateStore atomic commit that writes the authority
   result and authority-critical Trace.

The 128-entry limit is an ABI bound. Extension fields, nested read-sets, and a
second precondition channel MUST NOT bypass it.

A reference store MAY internally serialize these heads through one authority
stream. An external adapter MAY implement a multi-head transaction. Both MUST
provide the same all-or-nothing read-set semantics at the ABI boundary.

## 8. Historical validity, currentness, and sealing

Historical validity and current actionability are independent facts. A legal
successor transition MUST change position, not rewrite inclusion.

### 8.1 Commit position model

`GovernanceCommitPositionV2` is a closed wire enum with exactly `CURRENT`,
`SUPERSEDED`, and `SEALED`. Position exists only after committed inclusion has
been verified. `PREPARED`, `NOT_INCLUDED`, `UNKNOWN`, and `RETIRED` are not wire
positions.

| Position/result | Included historically | Current for new authority | New writes | Delivery | New publish/execute |
| --- | --- | --- | --- | --- | --- |
| Prepared, no position | No | No | Not applicable | Diagnostic only | `INVALID` or `DENIED` |
| `CURRENT` | Yes | Yes, subject to all live heads/grants | Allowed by policy and CAS | Required for terminal outcomes | Requires exact current action authorization |
| `SUPERSEDED` | Yes | No | Successor already exists | Terminal outcome remains deliverable | `DENIED`; prepare against fresh heads |
| `SEALED` | Yes | No new authority currentness can be created | Denied | Previously committed delivery remains reconcilable | No new action authorization; only an effect already atomically committed before sealing may be reconciled |
| `INVALID`, no position | No verified inclusion | No | Not applicable | Typed invalid result only | Denied |
| `FINALITY_UNAVAILABLE`, no position | Unproven | Unproven | No assumed write | Typed unavailable result | Denied without downgrade; reconcile first |

`SEALED` in this section is a domain/authority-ledger lifecycle position. It is
not the existing Optimal Commit `CommitWindowSeal`, which is a liveness record
and does not seal an authority domain. Domain retirement is implemented as a
terminal seal reason; it MUST NOT add a fourth `RETIRED` wire position.

### 8.2 State transitions

```text
PREPARED --atomic commit--> CURRENT
CURRENT --legal successor--> SUPERSEDED (predecessor) + CURRENT (successor)
CURRENT/SUPERSEDED --terminal domain seal or retirement--> SEALED
```

No legal arrow leads from an included commit to `INVALID`. Tampered or absent
proof input can receive disposition `INVALID` with no position, but it does not
invalidate the original committed history.

A seal MUST itself be an atomic committed transition bound to the exact final
revision/root. After sealing, new issuance, replay advance, recovery as current
action authority, and policy mutation are denied. Projection, proof inspection,
terminal result delivery, and reconciliation of an effect already included in
the atomic committed batch remain possible. A retirement seal MUST NOT delete
the historical proof required by the declared retention/conformance policy.

### 8.3 Current actionability predicate

An included transition is actionable only when all applicable predicates are
true at one atomic snapshot:

- historical inclusion is verified;
- its scope, profile, operation, issuer/grant, target, action, payload, epoch,
  and ledger bindings match the request;
- every read-set head remains current;
- the issuer/grant has not expired or been revoked under the profile's declared
  validity basis;
- replay permission is current and can be atomically advanced when required;
- the domain lifecycle permits the action; and
- the terminal outcome's policy independently permits the requested action
  class.

Failure of current actionability never erases historical validity and never
suppresses delivery of the terminal Governance result.

## 9. Total results and exact denial registry

Expected denial, conflict, stale, unavailable, and malformed conditions MUST be
returned as total typed results. Callers MUST NOT distinguish them by parsing
exception messages. Programmer defects and impossible internal invariant
violations MAY raise a documented exception, but no normal adversarial input
path depends on its text.

`GovernanceCommitDispositionV2` is a closed wire enum with exactly:

- `COMMITTED`: the exact operation has verified durable inclusion;
- `DENIED`: a well-formed request was authoritatively refused; it carries no
  authority receipt, committed inclusion, commit position, or committed
  transition;
- `RETRY_REQUIRED`: a valid preparation lost a CAS/read-set race or used a
  known stale parent;
- `FINALITY_UNAVAILABLE`: the store cannot currently prove whether the
  transition committed, so reconciliation by transition identity is required;
  and
- `INVALID`: the input, identity, scope, batch, receipt, inclusion, or proof is
  malformed, conflicting, cross-boundary, or tampered.

There is no `CONFLICT`, `STALE`, `UNAVAILABLE`, or `MALFORMED` wire disposition.
Those conditions map to the closed dispositions above and to one or more exact
diagnostics. Human-readable detail MAY add context but MUST NOT be the dispatch
key.

The implementation-oriented stable diagnostic registry is exactly:

| Diagnostic identifier | Primary failure boundary |
| --- | --- |
| `authority_profile_unsupported` | Unknown, absent, aliased, or case-mutated authority profile |
| `authority_session_required` | Operation requires a live local authority session |
| `authority_session_store_mismatch` | Session/capability is bound to another StateStore |
| `authority_scope_mismatch` | Record or request crosses `scope_ref` |
| `authority_operation_denied` | Live grant does not permit the requested operation |
| `authority_binding_mismatch` | Target/action/payload/epoch/ledger binding differs |
| `authority_grant_unverified` | Authenticated grant cannot be verified |
| `authority_grant_expired` | Grant validity bound has elapsed |
| `authority_grant_revoked` | Current revocation state denies the grant |
| `governance_read_set_invalid` | Read-set shape, bound, order, entry, or root is invalid |
| `governance_read_set_stale` | A known current head differs from the expected revision/root |
| `governance_transition_conflict` | One transition identity is reused with different canonical bytes |
| `governance_domain_sealed` | Authority domain accepts no new write |
| `governance_finality_unavailable` | Store cannot establish commit/non-commit finality |
| `governance_committed_transition_invalid` | Receipt/batch/inclusion proof is absent, mismatched, or tampered |
| `governance_action_not_authorized` | Publish or execute effect lacks exact current action authority |
| `governance_trace_lineage_invalid` | Required canonical authority Trace lineage is missing or mismatched |

These 17 identifiers are closed for the selected v2 profiles. Their only enum
owner is
`pheroos.protocol.authority_v2.AuthorityDiagnosticCodeV2`. Governance consumes
that type and MAY re-export the identical object; it MUST NOT define a second
enum or competing spelling. Governance owns the mapping from its typed result
to these authority diagnostics. Generic schema/selector diagnostics emitted
before authority v2 dispatch retain their existing Protocol owner and MUST NOT
be relabeled as an authority v2 diagnostic. An AH-level typed label groups
related failures for review; it is not a substitute for the exact diagnostic
emitted by an implementation.

The following JSON block is the canonical machine-audit projection of the
invariant/diagnostic/negative-test mapping. Documentation checks MUST parse the
content between the markers, reject duplicate or missing `AH-001` through
`AH-014`, and compare it with the diagnostic table above and detailed registry
in section 11.

<!-- authority-v2-negative-matrix:start -->
```json
{
  "format_version": 1,
  "policy": "pheroos-scoped-authority-policy-v2",
  "profiles": [
    "pheroos-scoped-authority-local-v2",
    "pheroos-scoped-authority-authenticated-v2"
  ],
  "diagnostic_dispositions": {
    "authority_profile_unsupported": "INVALID",
    "authority_session_required": "DENIED",
    "authority_session_store_mismatch": "INVALID",
    "authority_scope_mismatch": "INVALID",
    "authority_operation_denied": "DENIED",
    "authority_binding_mismatch": "INVALID",
    "authority_grant_unverified": "DENIED",
    "authority_grant_expired": "DENIED",
    "authority_grant_revoked": "DENIED",
    "governance_read_set_invalid": "INVALID",
    "governance_read_set_stale": "RETRY_REQUIRED",
    "governance_transition_conflict": "INVALID",
    "governance_domain_sealed": "DENIED",
    "governance_finality_unavailable": "FINALITY_UNAVAILABLE",
    "governance_committed_transition_invalid": "INVALID",
    "governance_action_not_authorized": "DENIED",
    "governance_trace_lineage_invalid": "INVALID"
  },
  "cases": [
    {
      "invariant_id": "AH-001",
      "owner": "governance",
      "expected_dispositions": ["DENIED"],
      "denial_code": "PROPOSAL_CANNOT_AUTHORIZE",
      "diagnostics": [
        "authority_session_required",
        "authority_operation_denied",
        "governance_action_not_authorized"
      ],
      "trace_rules": ["TR-0", "TR-1"],
      "negative_test_id": "AUTH-V2-AH-001"
    },
    {
      "invariant_id": "AH-002",
      "owner": "governance",
      "expected_dispositions": ["DENIED"],
      "denial_code": "AUTHORITY_CREDENTIAL_MISSING",
      "diagnostics": ["authority_session_required"],
      "trace_rules": ["TR-0", "TR-1"],
      "negative_test_id": "AUTH-V2-AH-002"
    },
    {
      "invariant_id": "AH-003",
      "owner": "protocol+governance",
      "expected_dispositions": ["INVALID"],
      "denial_code": "ENVELOPE_BINDING_MISMATCH",
      "diagnostics": [
        "authority_profile_unsupported",
        "authority_scope_mismatch",
        "authority_binding_mismatch",
        "governance_trace_lineage_invalid"
      ],
      "trace_rules": ["TR-0", "TR-1", "TR-2"],
      "negative_test_id": "AUTH-V2-AH-003"
    },
    {
      "invariant_id": "AH-004",
      "owner": "governance+state-store",
      "expected_dispositions": ["INVALID"],
      "denial_code": "INCLUSION_NOT_VERIFIED",
      "diagnostics": ["governance_committed_transition_invalid"],
      "trace_rules": ["TR-0", "TR-1", "TR-2"],
      "negative_test_id": "AUTH-V2-AH-004"
    },
    {
      "invariant_id": "AH-005",
      "owner": "governance",
      "expected_dispositions": ["DENIED"],
      "denial_code": "CURRENT_ACTION_REQUIRED",
      "diagnostics": ["governance_action_not_authorized"],
      "trace_rules": ["TR-1", "TR-3"],
      "negative_test_id": "AUTH-V2-AH-005"
    },
    {
      "invariant_id": "AH-006",
      "owner": "state-store",
      "expected_dispositions": ["COMMITTED", "INVALID"],
      "denial_code": "HISTORICAL_INCLUSION_INVALID",
      "diagnostics": ["governance_committed_transition_invalid"],
      "trace_rules": ["TR-3"],
      "negative_test_id": "AUTH-V2-AH-006"
    },
    {
      "invariant_id": "AH-007",
      "owner": "governance-output",
      "expected_dispositions": ["DENIED"],
      "denial_code": "ACTION_AUTHORITY_REQUIRED",
      "diagnostics": ["governance_action_not_authorized"],
      "trace_rules": ["TR-1", "TR-2"],
      "negative_test_id": "AUTH-V2-AH-007"
    },
    {
      "invariant_id": "AH-008",
      "owner": "governance",
      "expected_dispositions": ["INVALID"],
      "denial_code": "AUTHORITY_BINDING_REUSE",
      "diagnostics": [
        "authority_session_store_mismatch",
        "authority_scope_mismatch",
        "authority_binding_mismatch"
      ],
      "trace_rules": ["TR-1"],
      "negative_test_id": "AUTH-V2-AH-008"
    },
    {
      "invariant_id": "AH-009",
      "owner": "coordinator+governance",
      "expected_dispositions": ["DENIED", "INVALID"],
      "denial_code": "ISSUER_CAPABILITY_INVALID",
      "diagnostics": [
        "authority_session_required",
        "authority_session_store_mismatch",
        "authority_operation_denied",
        "authority_grant_unverified",
        "authority_grant_expired",
        "authority_grant_revoked"
      ],
      "trace_rules": ["TR-0", "TR-1", "TR-2"],
      "negative_test_id": "AUTH-V2-AH-009"
    },
    {
      "invariant_id": "AH-010",
      "owner": "state-store",
      "expected_dispositions": ["DENIED"],
      "denial_code": "DOMAIN_SEALED",
      "diagnostics": ["governance_domain_sealed"],
      "trace_rules": ["TR-1", "TR-2", "TR-3"],
      "negative_test_id": "AUTH-V2-AH-010"
    },
    {
      "invariant_id": "AH-011",
      "owner": "governance",
      "expected_dispositions": ["DENIED", "INVALID"],
      "denial_code": "NON_AUTHORITY_VALUE",
      "diagnostics": [
        "authority_session_required",
        "governance_committed_transition_invalid",
        "governance_action_not_authorized"
      ],
      "trace_rules": ["TR-0", "TR-1"],
      "negative_test_id": "AUTH-V2-AH-011"
    },
    {
      "invariant_id": "AH-012",
      "owner": "state-store",
      "expected_dispositions": ["RETRY_REQUIRED"],
      "denial_code": "REPLAY_PRECONDITION_STALE",
      "diagnostics": ["governance_read_set_stale"],
      "trace_rules": ["TR-1", "TR-2"],
      "negative_test_id": "AUTH-V2-AH-012"
    },
    {
      "invariant_id": "AH-013",
      "owner": "governance+state-store-abi",
      "expected_dispositions": [
        "DENIED",
        "RETRY_REQUIRED",
        "FINALITY_UNAVAILABLE",
        "INVALID"
      ],
      "denial_code": "STORE_UNAVAILABLE",
      "diagnostics": [
        "authority_profile_unsupported",
        "authority_session_required",
        "authority_session_store_mismatch",
        "authority_scope_mismatch",
        "authority_operation_denied",
        "authority_binding_mismatch",
        "authority_grant_unverified",
        "authority_grant_expired",
        "authority_grant_revoked",
        "governance_read_set_invalid",
        "governance_read_set_stale",
        "governance_transition_conflict",
        "governance_domain_sealed",
        "governance_finality_unavailable",
        "governance_committed_transition_invalid",
        "governance_action_not_authorized",
        "governance_trace_lineage_invalid"
      ],
      "trace_rules": ["TR-1", "TR-4"],
      "negative_test_id": "AUTH-V2-AH-013"
    },
    {
      "invariant_id": "AH-014",
      "owner": "governance+state-store",
      "expected_dispositions": ["INVALID", "RETRY_REQUIRED"],
      "denial_code": "READ_SET_CONFLICT",
      "diagnostics": [
        "governance_read_set_invalid",
        "governance_read_set_stale",
        "governance_transition_conflict",
        "governance_trace_lineage_invalid"
      ],
      "trace_rules": ["TR-1", "TR-2"],
      "negative_test_id": "AUTH-V2-AH-014"
    }
  ]
}
```
<!-- authority-v2-negative-matrix:end -->

`governance_read_set_stale` maps to `RETRY_REQUIRED`, while
`governance_transition_conflict` is an identity/payload substitution and maps
only to `INVALID`; it MUST NOT be treated as a replay-race retry.
`governance_finality_unavailable` maps to `FINALITY_UNAVAILABLE`, invalid
read-set shape maps to `INVALID`, and a well-formed policy refusal maps to
`DENIED`. A pre-auth structural reader returns an exact reader diagnostic and
`INVALID` without requiring a StateStore or Trace write.

## 10. Trace and audit rules

Authority state and authority-critical Trace share one truth boundary:

- **TR-0 — pre-auth no-write:** malformed or unsupported input rejected before
  a trusted scope/session exists MUST NOT require a StateStore or TraceStore
  write. It MAY be recorded in deployment-local security telemetry, which is
  not canonical protocol Trace.
- **TR-1 — scoped denial audit:** after a scope/session exists, `DENIED` is
  returned independently of audit availability and carries no authority
  receipt, committed inclusion, position, or committed transition. If policy
  requires an audit record, the implementation MUST make one idempotent append
  attempt to a scoped audit sink and expose its outcome separately as
  non-authority audit telemetry. The canonical `TraceEvent` append MUST NOT use
  `pheroos-governance-trace-batch-v2` or the StateStore authority atomic batch;
  it cannot be loaded or recovered as authority. Audit success or failure MUST
  NOT change, suppress, upgrade, or turn the denial into pending/retry.
- **TR-2 — atomic authority change:** every successful issuance commit, replay
  advance, action authorization, recovery-as-current, revocation, or domain
  seal MUST include its complete canonical authority-critical Trace in the same
  StateStore atomic batch.
- **TR-3 — projection only:** an independent Scoped TraceStore receives
  idempotent projections from committed StateStore history. Projection failure
  cannot roll back, upgrade, revoke, or create authority. Projection records
  MUST carry their committed inclusion reference.
- **TR-4 — unavailable truth:** when StateStore truth is unavailable, the
  implementation returns `FINALITY_UNAVAILABLE` with
  `governance_finality_unavailable` and emits no fabricated canonical success
  or denial Trace. Reconciliation MAY project a later event only after
  committed history establishes what happened.

The StateStore is the atomic authority truth root. `TraceStore` is a query and
archive projection only; it is not a database substitute for authority, a
queue, an event bus, or an issuer.

## 11. AH invariant and negative-test registry

Each invariant has exactly one primary semantic owner. Collaborating surfaces
may encode or prove it, but MUST NOT implement a competing authority decision.
The listed negative test is a required Conformance/TCK case, not merely a unit
test suggestion.

| ID | Normative invariant | Primary owner | Typed denial | Trace rule | Required negative test |
| --- | --- | --- | --- | --- | --- |
| **AH-001** | Agent/model/tool data is always proposal data and MUST NOT directly issue, verify, commit, or authorize an action. | Governance | `PROPOSAL_CANNOT_AUTHORIZE` | TR-0 before session; otherwise TR-1 when declared | `AUTH-V2-AH-001`: submit a byte-identical agent-produced authority-shaped envelope; assert denial and no state/head advance. |
| **AH-002** | `AuthorityLevel` is a classification label, not a credential or proof of issuer possession. | Governance | `AUTHORITY_CREDENTIAL_MISSING` | TR-0 or TR-1 | `AUTH-V2-AH-002`: pass `AuthorityLevel.GOVERNANCE` without a live issuer capability; assert `DENIED` plus `authority_session_required` and no issued record. |
| **AH-003** | Every authority-capable envelope MUST bind its exact scope, operation, issuer/grant, relevant target/action/payload/epoch, ledger, read-set, and required Trace lineage. | Protocol contract; Governance enforces | `ENVELOPE_BINDING_MISMATCH` | TR-0 for malformed fields; TR-1 for an authenticated mismatch; TR-2 on success | `AUTH-V2-AH-003`: mutate profile, scope, target/action/payload/epoch/ledger, and Trace bindings one leaf at a time; assert the corresponding profile/scope/binding/Trace diagnostic, zero commit, and no partial Trace. |
| **AH-004** | Portable payload is data until the selected StateStore verifies exact committed inclusion; only then may a local live grant re-establish authority. | Governance + StateStore inclusion verifier | `INCLUSION_NOT_VERIFIED` | TR-0/1 on rejection; TR-2 only if recovery changes current state | `AUTH-V2-AH-004`: deserialize a structurally valid receipt/envelope absent from store history; assert `INVALID` plus `governance_committed_transition_invalid` even when all roots are canonical. |
| **AH-005** | Historical validity and current actionability MUST be represented and checked separately. | Governance | `CURRENT_ACTION_REQUIRED` | TR-1 for audited use denial; no rewrite of historical Trace | `AUTH-V2-AH-005`: verify an included transition at position `SUPERSEDED`; assert its historical disposition remains `COMMITTED`, while a new action is `DENIED` with `governance_action_not_authorized`, never historical `INVALID`. |
| **AH-006** | A legal successor MUST NOT turn an already committed receipt into `INVALID`; inclusion remains immutable and its position becomes `SUPERSEDED` or `SEALED`. | StateStore | `HISTORICAL_INCLUSION_INVALID` only for a proof that is not included or is tampered | TR-3 projects the successor; original atomic Trace remains | `AUTH-V2-AH-006`: commit A then legal successor B; verify A by transition/receipt root and assert `COMMITTED`/`SUPERSEDED`. Mutate A and assert `INVALID` with `governance_committed_transition_invalid`. |
| **AH-007** | Every Governance-issued terminal outcome from an active profile is unconditionally delivery-eligible for return/transport to the requesting runtime. Delivery is not an authority action; only `publish` and `execute` are external effects requiring separate current action authorization. | Governance Output contract | `ACTION_AUTHORITY_REQUIRED` applies only to publish/execute | Terminal outcome return is never gated; denied publish/execute follows TR-1 without suppressing delivery | `AUTH-V2-AH-007`: produce every declared terminal outcome with publish/execute denied; assert each outcome is still returned/transportable, no current head/grant/`ActionPermission` is consulted for delivery, and each requested external effect returns `governance_action_not_authorized`. |
| **AH-008** | A capability or authority record MUST NOT be reused across scope, target, action, epoch, payload, operation, or ledger bindings. | Governance | `AUTHORITY_BINDING_REUSE` | TR-1; no state advance | `AUTH-V2-AH-008`: replay one valid committed proof across every binding dimension independently; assert fail-closed exact denial for each case. |
| **AH-009** | An issuer capability is local, non-portable, least-privilege, operation/scope bounded, and subject to declared expiry and revocation. | Trusted coordinator custody; Governance verifies | `ISSUER_CAPABILITY_INVALID` | TR-0/1 on invalid capability; revocation uses TR-2 | `AUTH-V2-AH-009`: copy/serialize, expire, revoke, cross-scope, and exceed-operation grant; all issuance attempts must fail without commit. |
| **AH-010** | Domain seal/retirement MUST reject new authority writes and replay advances while preserving historical inclusion and unconditional terminal result delivery eligibility. | StateStore lifecycle contract | `DOMAIN_SEALED` | Seal itself TR-2; later denials TR-1; history TR-3 | `AUTH-V2-AH-010`: seal a domain, then attempt issue/commit/replay/recover-current; assert denial, unchanged seal root, and successful historical proof/result return. |
| **AH-011** | A Boolean, digest, same-shaped dataclass, enum, receipt id, Trace event, outbox row, or delivery success is never sufficient authority. | Governance | `NON_AUTHORITY_VALUE` | TR-0/1; no commit | `AUTH-V2-AH-011`: substitute each listed value; assert the applicable `authority_session_required`, `governance_committed_transition_invalid`, or `governance_action_not_authorized` diagnostic and no authority creation. |
| **AH-012** | Replay advance MUST be durable, append-only, atomic CAS, isolated by scope/action/epoch, and recoverable across restart. | StateStore | `REPLAY_PRECONDITION_STALE` | Successful advance TR-2; race loser TR-1 if declared, never a success Trace | `AUTH-V2-AH-012`: race 32 consumers, restart the winning store, and assert exactly one advance, stable retry identity, and `RETRY_REQUIRED` losers with `governance_read_set_stale`; transition-id payload substitution is not this retry case. |
| **AH-013** | Expected denial, conflict, stale, and unavailable paths MUST return total typed results; callers MUST NOT parse exception strings or silently downgrade. | Public Governance/StateStore ABI | `STORE_UNAVAILABLE` is one case in the total-result invariant; all 17 diagnostics map to the four non-committed dispositions | TR-4 for unavailable; TR-1 for auditable denial/stale/conflict | `AUTH-V2-AH-013`: vary exception text and exercise every one of the 17 diagnostic gates; assert its frozen `DENIED`, `RETRY_REQUIRED`, `FINALITY_UNAVAILABLE`, or `INVALID` mapping and no authority exposure. |
| **AH-014** | Output authorization and every other authority commit MUST atomically validate the complete canonical authority read-set in the same commit; check-then-write is forbidden. | Governance prepares; StateStore atomically enforces | `READ_SET_CONFLICT` | Winner TR-2; conflict has no success Trace and uses TR-1 only when auditable | `AUTH-V2-AH-014`: assert incomplete/noncanonical read-set is `INVALID`, stale heads are `RETRY_REQUIRED`, and transition-id reuse with different canonical bytes is `INVALID` with `governance_transition_conflict`; no output authority or partial state/Trace/receipt escapes. |

All negative tests MUST additionally assert scope isolation, unchanged frozen v1
artifacts, and absence of silent assurance downgrade where applicable. Active
profile checks return PASS or FAIL; skip, N/A, or no-op PASS is not Conformance.

## 12. Profile guarantees

### 12.1 Legacy v1

Legacy v1 remains explicit compatibility behavior. Passing
`AuthorityLevel.GOVERNANCE`, a caller publication Boolean, or a v1 process-local
issuer is a trusted-host assertion, not a production credential. This document
MUST NOT be retroactively applied to v1 bytes, schema identifiers, TCK roots, or
diagnostic meanings.

### 12.2 `pheroos-scoped-authority-local-v2`

The `pheroos-scoped-authority-local-v2` profile may trust deployment isolation,
coordinator capability custody, and the selected conforming StateStore. It MUST
still implement every scope, binding, atomic read-set, historical/current,
replay, sealing, typed result, and Trace rule in this document. It MUST describe
issuer identity as local trusted-host identity and MUST NOT claim portable or
cross-host authentication.

### 12.3 `pheroos-scoped-authority-authenticated-v2`

The `pheroos-scoped-authority-authenticated-v2` profile may claim an
authenticated issuer-grant binding only when trusted host configuration selects
an exact external `IssuerGrantVerifier` contract and the transition binds its
verified result into the envelope and committed history. A portable grant or
authority record remains data until local verification, and the issuer
capability itself is never portable. Core defines the provider-neutral verifier
ABI and Conformance semantics only; it does not own keys, certificates, KMS,
OAuth, or network identity lifecycle. An absent, unknown, expired, revoked, or
downgraded verifier result fails closed.

The authenticated production profile may be promoted to Stable only after at
least one independent external issuer-grant verifier adapter passes
`pheroos-issuer-grant-verifier-conformance-v2`. A local-only reference
implementation cannot satisfy that promotion gate. Until this evidence exists,
only the local trusted-host guarantee may be claimed.

## 13. Availability and final-output rule

Strict authority MUST NOT make the multi-agent protocol incapable of returning
its final result. Governance has two separate responsibilities:

1. terminate with a declared, typed outcome, including safe fallback, blocked,
   `INVALID`, `RETRY_REQUIRED`, or `FINALITY_UNAVAILABLE` when the selected
   profile permits that terminal outcome; and
2. independently authorize publication or execution.

Every Governance-issued terminal outcome is unconditionally delivery-eligible
for return or transport to the requesting runtime. Eligibility does not depend
on the current head, issuer grant, `ActionPermission`, outbox state, or
`governance_action_not_authorized`; that diagnostic applies only to publish or
execute. A missing publish/execute grant changes external-effect authorization,
not the outcome into indefinite `pending` and not the historical decision into
`INVALID`. A transport may retry using a stable delivery identity derived from
`scope_ref + transition_id + outcome ref`, but the identity and outbox are
coordination aids, never result gates and never authority. Physical transport
may fail and retry; such availability failure does not change protocol delivery
eligibility. Projection failure cannot reverse the commit or suppress return of
the outcome.

StateStore uncertainty returns `FINALITY_UNAVAILABLE` without pretending a
commit or non-commit was proved; the runtime reconciles by transition identity
before any external effect. A policy-declared fallback may still be delivered,
but it does not become a fallback commit. No profile may silently lower its
assurance level, manufacture evidence, or convert an unverified result into
authority in order to produce output.

## 14. Explicit non-goals

Authority v2 does **not** provide:

- a same-process sandbox for arbitrary or malicious Python;
- a generic capability, policy, authentication, or security manager;
- model-provider routing, agent orchestration, tool execution, queues, workers,
  schedulers, daemons, HTTP APIs, or dashboards;
- database engines, migrations, replication, backup, or connection lifecycle;
- a TraceStore, outbox, or event bus as a second authority ledger;
- secret storage, key generation, KMS, OAuth, certificate issuance, or network
  transport security;
- confidentiality for payloads or protection from traffic analysis;
- Byzantine tolerance for a malicious local StateStore unless an exact
  distributed/attested profile declares and proves it;
- protection from a deliberately non-conforming action executor;
- exactly-once external effects when the sink provides neither an idempotency
  key nor a shared transaction boundary;
- unlimited denial-of-service resistance or resource admission control;
- authority derived from hashes, blockchain terminology, pheromone strength,
  consensus score, or model confidence; or
- automatic upgrade of legacy manifests or reinterpretation of existing
  `PROTOCOL_SCHEMA_V2`/`CAPABILITY_SCHEMA_V2` document versions as authority
  semantic v2.

## 15. Implementation shape and review gate

Implementation MUST use small explicit contracts owned by existing surfaces:

- Protocol owns exact declarations, schema dispatch, canonical encoding, and
  validation diagnostics;
- Governance owns deterministic authority decisions, typed results, historical
  versus current semantics, and output/action separation;
- Trace owns canonical provider-neutral event shape, not authority truth;
- Conformance composes Protocol, Governance, StateStore adapters, and Trace to
  prove every AH negative case; and
- the external runtime owns authentication integration, capability custody,
  StateStore/database adapters, projection, outbox, and external execution.

No `SecurityManager`, `CapabilityManager`, generic policy engine, service
registry, provider gateway, background worker, or database implementation may
be introduced into protocol-core to satisfy this document. A new object is
acceptable only when it directly represents an invariant, typed outcome,
canonical binding, Trace lineage, or Conformance fixture described here.

During the WP-02 closure audit and before WP-03 implementation begins, review
must confirm:

- implementation consumes every exact identifier and closed enum in the
  accepted authority version decision without changing frozen v1 bytes;
- migration explicitly keeps legacy manifests on v1 and makes v2 opt-in;
- every diagnostic above has an owner, AH mapping, and negative TCK vector;
- local and authenticated profile guarantees are not conflated;
- the full read-set can be atomically implemented by both the reference store
  and external adapters;
- StateStore history is authoritative and Scoped TraceStore remains projection
  only; and
- no same-process isolation or external-action prevention claim exceeds the
  stated threat model.

Related current Draft documents:

- [Governance overview](../governance/overview.md)
- [Runtime integration](runtime-integration.md)
- [Optimal Commit ABI](optimal-commit-abi.md)
- [Optimal Commit v1 migration](optimal-commit-v1-migration.md)
- [Production readiness hardening plan](../process/production-readiness-hardening-goal-plan.md)
