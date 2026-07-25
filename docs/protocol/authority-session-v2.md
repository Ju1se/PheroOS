# Authority Session v2 Normative Contract

Status: **Draft public ABI with provider-free Conformance; active local profile,
authenticated production promotion still gated**

Decision date: 2026-07-21

This document is the normative description of the public Authority Session v2
vertical slice exposed by `pheroos.governance.authority_session_v2` and the
`pheroos.governance` facade. Its single implementation owner remains the
private `pheroos.governance._authority_session_v2` package. The slice aligns
portable contracts, opaque handles, StateStore operations, Trace lineage,
failure boundaries, and a reusable public Conformance matrix. Public Draft
availability now participates in the exact local `pheroos.protocol.v2` path;
it does not make the ABI Stable or satisfy the authenticated external-verifier
gate.

If older design prose differs from the exact fields, signatures, event names,
or request flow below, this document controls for this Draft slice. The
accepted [authority v2 decision](authority-v2-decision.md),
[trust model](authority-trust-model-v2.md),
[migration contract](authority-v2-migration.md), and
[StateStore v2 contract](authority-store-v2.md) still control their broader
surfaces.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are normative for an implementation claiming this Draft ABI.

This remains protocol-core. It defines deterministic, provider-neutral records
and governance transitions. It does not implement authentication, identity
providers, a key service, network transport, a database, a server, an agent
runtime, model routing, or external effects.

## 1. Ownership, identifiers, and activation status

Protocol owns the closed diagnostic enum and Authority v2 canonical/version
rules. Governance owns the grant, verification, request, handle, session, and
commit semantics. StateStore owns atomic read-set validation, durable inclusion,
reconciliation, finality, and domain sealing. Trace remains the provider-neutral
event ABI. Conformance may compose those surfaces but creates no authority.

The following identifiers are exact and case-sensitive:

| Surface | Identifier | Status in this slice |
| --- | --- | --- |
| Issuer operation registry | `pheroos-governance-issuer-operation-v2` | Closed semantic enum |
| Portable issuer grant | `pheroos-governance-issuer-grant-v2` | Public Draft record |
| Portable grant verification | `pheroos-issuer-grant-verification-v2` | Public Draft record |
| Verifier ABI label | `pheroos-issuer-grant-verifier-v2` | Public Draft structural Protocol; external evidence pending |
| Durable grant state | `pheroos-governance-issuer-grant-state-v2` | Public Draft schema identifier; internally produced snapshot |
| Opaque issuer capability | `pheroos-governance-issuer-capability-v2` | Public Draft local handle; never a wire discriminator |
| Opaque authority session | `pheroos-governance-authority-session-v2` | Public Draft local handle; never a wire discriminator |
| Verified-signal request | `pheroos-governance-verified-signal-request-v2` | Public Draft record |
| Verified-signal state | `pheroos-governance-verified-signal-state-v2` | Public Draft schema identifier; internally produced snapshot |
| Domain-retirement request | `pheroos-governance-domain-retirement-request-v2` | Public Draft record |
| Authority-session Conformance | `pheroos-governance-authority-session-conformance-v2` | Public Draft reusable matrix |
| Grant-verifier Conformance | `pheroos-issuer-grant-verifier-conformance-v2` | Reserved inactive profile |

The machine-audit projection is:

<!-- authority-session-v2-registry:start -->
```json
{
  "format_version": 1,
  "status": "draft-active-local",
  "identifiers": {
    "authority_session": "pheroos-governance-authority-session-v2",
    "authority_session_conformance": "pheroos-governance-authority-session-conformance-v2",
    "domain_retirement_request": "pheroos-governance-domain-retirement-request-v2",
    "issuer_capability": "pheroos-governance-issuer-capability-v2",
    "issuer_grant": "pheroos-governance-issuer-grant-v2",
    "issuer_grant_state": "pheroos-governance-issuer-grant-state-v2",
    "issuer_grant_verification": "pheroos-issuer-grant-verification-v2",
    "issuer_grant_verifier": "pheroos-issuer-grant-verifier-v2",
    "issuer_operation": "pheroos-governance-issuer-operation-v2",
    "verified_signal_request": "pheroos-governance-verified-signal-request-v2",
    "verified_signal_state": "pheroos-governance-verified-signal-state-v2",
    "verifier_conformance": "pheroos-issuer-grant-verifier-conformance-v2"
  },
  "operations": [
    {"label": "VERIFY_SIGNAL", "wire": "verify_signal"},
    {"label": "EVALUATE_QUORUM", "wire": "evaluate_quorum"},
    {"label": "QUALIFY_EVIDENCE", "wire": "qualify_evidence"},
    {"label": "RESOLVE_STOP", "wire": "resolve_stop"},
    {"label": "ADVANCE_REPLAY", "wire": "advance_replay"},
    {"label": "ISSUE_ACTION_PERMISSION", "wire": "issue_action_permission"},
    {"label": "AUTHORIZE_OUTPUT", "wire": "authorize_output"},
    {"label": "RETIRE_DOMAIN", "wire": "retire_domain"}
  ],
  "stream_prefixes": {
    "issuer_grant": "authority:issuer-grant:",
    "verified_signal": "authority:verified-signal:"
  }
}
```
<!-- authority-session-v2-registry:end -->

Exact manifest/schema dispatch, Baseline Output v2, Runtime Integration, the
Authority schema, and the scoped TCK vocabulary now compose this public slice.
The local profile is active Draft. Authenticated production compatibility still
requires external verifier evidence and the later aggregate/promotion gates:

```text
pheroos.protocol.v2 + local profile -> active Draft exact dispatch
pheroos.protocol.v2 + authenticated profile -> Draft, host-selected verifier required
authenticated production/Stable claim -> gated on external verifier and promotion evidence
legacy v1 behavior -> unchanged
```

## 2. Closed `GovernanceIssuerOperationV2`

`GovernanceIssuerOperationV2` has exactly eight members in canonical order:

<!-- authority-session-v2-operations:start -->
```text
VERIFY_SIGNAL=verify_signal
EVALUATE_QUORUM=evaluate_quorum
QUALIFY_EVIDENCE=qualify_evidence
RESOLVE_STOP=resolve_stop
ADVANCE_REPLAY=advance_replay
ISSUE_ACTION_PERMISSION=issue_action_permission
AUTHORIZE_OUTPUT=authorize_output
RETIRE_DOMAIN=retire_domain
```
<!-- authority-session-v2-operations:end -->

A grant's `operations` is a non-empty exact tuple, contains only exact enum
members, has no duplicates, and follows that enum order. Arbitrary strings,
aliases, dynamic registrations, or implicit operations are invalid.

Only `VERIFY_SIGNAL` and `RETIRE_DOMAIN` have request/session commit paths in
this vertical slice. The other six members reserve least-privilege vocabulary;
their presence in the enum is not an implemented entrypoint. Grant activation
and revocation are trusted-host lifecycle operations and are not hidden ninth
or tenth enum values.

`target_refs` and `action_refs` are exact reference sets, represented as
UTF-8-sorted tuples. An empty tuple grants no implicit target or action. No
operation interprets an empty tuple, prefix, glob, or regular expression as a
wildcard. The two implemented session paths bind one exact signal target or no
target, respectively; neither path binds an action.

## 3. Shared canonical-value rules

Every portable record below is a frozen, slotted dataclass. It snapshots its
tuple inputs and provides `to_dict()`, strict `from_dict()`,
`canonical_bytes()`, and `root()`.

The canonical encoding uses UTF-8 JSON with keys sorted, no insignificant
whitespace, `ensure_ascii=False`, and `allow_nan=False`. Roots have the exact
form `sha256:` plus 64 lowercase hexadecimal characters. For record kind
`K`, the computation is:

```text
root = "sha256:" || lowercase_hex(SHA-256(
  UTF8("pheroos-governance-authority-v2:" || K) || 0x00 ||
  canonical_json(record_body_without_root)
))
```

Text values required as references are exact non-empty `str`, already NFC,
UTF-8 encodable, and have no surrounding whitespace. Epochs are exact `int`
values, not `bool`, in `0..9007199254740991`. Reference collections are exact
tuples in unsigned UTF-8 order with no duplicates. Their wire representation is
a JSON array. `from_dict()` accepts an exact built-in dictionary and rejects
missing or extension fields.

Every caller-selected `transition_id` is canonical text and MUST NOT equal the
reserved StateStore value `genesis`. Both portable request constructors and
their strict readers reject that value before a capability can open a session.

These checks establish deterministic bytes only. Portable bytes, a root, or a
reconstructed dataclass never becomes an opaque capability or authority
session.

## 4. Portable `GovernanceIssuerGrantV2`

`GovernanceIssuerGrantV2` is proposal/configuration data. It is not a bearer
credential, live permission, capability, session, or proof of current grant
state. Its constructor fields, in exact declaration order, are:

<!-- authority-session-v2-grant-fields:start -->
```text
domain_root
scope_ref
issuer_ref
grant_ref
grant_binding_ref
operations
target_refs
action_refs
issued_epoch
not_before_epoch
expires_at_epoch
revocation_generation
schema
canonical_version
grant_root
```
<!-- authority-session-v2-grant-fields:end -->

`schema` is exactly `pheroos-governance-issuer-grant-v2` and
`canonical_version` is exactly `pheroos-authority-canonical-v2`.
`domain_root` and `grant_binding_ref` are lowercase SHA-256 roots. The contract
requires the selected host/profile to provide `grant_binding_ref`; this class
does not invent a binding-policy evaluator or derive that reference from other
grant fields. It is included in `grant_root` and must remain stable for the
exact grant binding.

The grant body contains every field above except `grant_root`. Its root kind is
`issuer-grant`. Construction requires:

```text
issued_epoch <= not_before_epoch <= expires_at_epoch
```

Use additionally requires:

```text
not_before_epoch <= observed_epoch <= expires_at_epoch
```

`revocation_generation` is the generation activated with the grant. A normal
active state preserves it. Revocation advances the durable state generation by
exactly one and makes that grant stream terminal. A new portable object with
the old `grant_ref` does not bypass committed state.

## 5. Portable `IssuerGrantVerificationV2`

`IssuerGrantVerificationV2` is a detached, portable result returned by a
host-selected verifier for the authenticated profile. Its exact constructor
fields are:

<!-- authority-session-v2-verification-fields:start -->
```text
grant_root
grant_binding_ref
verifier_ref
accepted
verified_epoch
schema
canonical_version
verification_root
```
<!-- authority-session-v2-verification-fields:end -->

`schema` is exactly `pheroos-issuer-grant-verification-v2` and
`canonical_version` is `pheroos-authority-canonical-v2`. `accepted` is an exact
Boolean, not a truthy substitute. The root kind is
`issuer-grant-verification` and covers every field except
`verification_root`.

An accepted result is usable only when all of these hold:

- it is the exact `IssuerGrantVerificationV2` type after strict wire
  round-trip;
- `accepted is True`;
- `grant_root` and `grant_binding_ref` match the exact grant; and
- `verified_epoch` equals the operation's `observed_epoch`.

The provider-neutral verifier Protocol is exactly:

```python
class IssuerGrantVerifierV2(Protocol):
    def verify_issuer_grant_v2(
        self,
        grant: GovernanceIssuerGrantV2,
        *,
        observed_epoch: int,
    ) -> IssuerGrantVerificationV2: ...
```

There is no `verifier_version` property, request-selected verification policy,
diagnostic field, verification-expiry field, or evidence field on this ABI.
Trusted host configuration selects the verifier object; portable input cannot
select it.

For `pheroos-scoped-authority-local-v2`, the verifier argument MUST be `None`
and durable verification is `null`. Supplying a verifier fails with
`authority_profile_unsupported`. This profile expresses trusted host custody of
the selected writer, not authentication of a person, workload, model, agent,
tenant, or network peer.

For `pheroos-scoped-authority-authenticated-v2`, a conforming host verifier is
required for a new activation and for each capability bind. Missing verifiers,
exceptions, wrong result types, rejected results, or mismatched roots/epochs
fail as `authority_grant_unverified`. The accepted activation result is stored
with the grant and must match the activation epoch. A later capability bind may
use a fresh accepted result for its later observed epoch. Exact reconciliation
of an already committed activation happens before new verification, so the
same transition retry may recover the committed result without calling the
verifier again.

## 6. Deterministic streams and durable grant lifecycle

Stream references use a bare 64-hex suffix, not a `sha256:` suffix. The grant
stream is:

```text
grant_payload = UTF8(scope_ref) || 0x00 || UTF8(grant_ref)
grant_stream_ref = "authority:issuer-grant:" ||
                   lowercase_hex(SHA-256(grant_payload))
```

The active/revoked grant snapshot has exactly these keys:

```text
schema
profile
domain_root
scope_ref
grant_ref
grant_root
grant_binding_ref
grant
verification
status
activated_epoch
revoked_epoch
revocation_generation
```

`schema` is `pheroos-governance-issuer-grant-state-v2`; `status` is exactly
`active` or `revoked`. Active state has `revoked_epoch=null` and the grant's
generation. Revoked state preserves the exact grant and activation
verification, sets a valid `revoked_epoch`, and stores grant generation plus
one. State deletion, rollback, in-place mutation, and reactivation of a used
grant stream are forbidden.

Activation writes from the grant stream's genesis head and atomically observes
the current `authority:domain-lifecycle` head. It publishes the state snapshot
and exactly one Trace event named `issuer_grant_activated` in the same batch.

Revocation writes from the exact active grant head and atomically observes the
current lifecycle head. It publishes terminal state and exactly one Trace event
named `issuer_grant_revoked` in the same batch.

The four exact authority event names in this slice are:

<!-- authority-session-v2-events:start -->
```text
issuer_grant_activated
issuer_grant_revoked
signal_verified
domain_retired
```
<!-- authority-session-v2-events:end -->

Exact transition-id retry reconciles to the original committed result only
when the durable view matches the operation inputs. Reusing an id for different
semantics fails with `governance_transition_conflict`. Grant/lifecycle races
are resolved by StateStore read-set validation; no operation may publish a
partial state/Trace result.

## 7. Opaque capability and session handles

### 7.1 `GovernanceIssuerCapabilityV2`

The capability is a final, slotted, non-dataclass local object. It has no
public constructor, wire schema, `to_dict()`, `from_dict()`, pickle reducer, or
JSON representation. Its private snapshot retains:

- the exact selected `GovernanceStateStoreV2` writer object;
- the exact selected `AuthorityDomainV2` object and its canonical bytes;
- a detached exact grant and its canonical bytes;
- the accepted verification, if the profile requires one;
- one exact `run_ref`; and
- the bind `observed_epoch` and private ownership marker.

The exact domain object is retained so profile cannot be reconstructed or
substituted from grant state later. Store binding is object custody: the handle
retains the object itself. It does not substitute `id(store)`, a caller string,
database URL, fingerprint, global registry, weak-reference registry, or
same-shaped writer.

The selected writer MUST structurally implement `GovernanceStateStoreV2` and
its `state_store_version` MUST equal
`pheroos-governance-state-store-v2`. Shape compatibility is not version
compatibility. Activation, revocation, bind, session open, and every
session-authorized commit fail closed on a missing, mismatched, or drifting
version; no wrong-version operation may publish state or Trace.

The public read-only properties expose non-secret semantics including profile,
domain/scope/issuer/grant refs and roots, run, operation/target/action bounds,
grant epochs/generation, observed epoch, and optional verifier/root. They do
not expose the writer, domain object, verification object, or private marker.

Required local behavior is:

```text
GovernanceIssuerCapabilityV2(...) raises TypeError
subclassing GovernanceIssuerCapabilityV2 raises TypeError
copy.copy(capability) is capability
copy.deepcopy(capability) is capability
pickle.dumps(capability) raises TypeError
capability.__reduce__() raises TypeError
capability.__reduce_ex__(protocol) raises TypeError
capability.__getstate__() raises TypeError
hasattr(capability, "to_dict") is False
hasattr(capability, "from_dict") is False
repr(capability) is redacted
```

Reflection, `object.__new__`, copied slots, an uninitialized exact-class object,
or a same-shaped class fails private ownership/snapshot validation.

### 7.2 `GovernanceAuthoritySessionV2`

The session is also final, slotted, immutable, non-dataclass, non-pickleable,
non-serializable, and redacted. Copy and deepcopy return the identical object.
It privately retains the exact capability and writer. Its semantic bindings are:

<!-- authority-session-v2-session-bindings:start -->
```text
domain_root
scope_ref
run_ref
request_ref
request_root
operation
observed_epoch
grant_ref
grant_root
grant_binding_ref
grant_expected_revision
grant_expected_root
lifecycle_expected_revision
lifecycle_expected_root
target_refs
action_refs
```
<!-- authority-session-v2-session-bindings:end -->

The session is valid for one canonical request in the capability's exact run.
The portable `request_root` already binds `transition_id` and every other
request field; the session does not carry an independently replaceable
transition id. For verified signals, `target_refs` is the one exact request
target and must be included in the grant's explicit `target_refs`. For domain
retirement, both bound-ref tuples are empty. Empty grant bounds are not
wildcards.

Opening a session reloads the exact grant and lifecycle state, rejects a sealed
domain or inactive/mismatched/expired grant, and captures grant and lifecycle
heads as immutable preconditions. A session is not a durable permission cache:
later revocation or sealing makes the commit stale or denied.

## 8. Exact operation entrypoints

The public Draft entrypoint signatures are exactly:

<!-- authority-session-v2-entrypoints:start -->
```python
def activate_governance_issuer_grant_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    transition_id: str,
    observed_epoch: int,
    verifier: IssuerGrantVerifierV2 | None = None,
) -> GovernanceCommitAttemptV2: ...

def revoke_governance_issuer_grant_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant_ref: str,
    transition_id: str,
    observed_epoch: int,
) -> GovernanceCommitAttemptV2: ...

def bind_governance_issuer_capability_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    run_ref: str,
    observed_epoch: int,
    verifier: IssuerGrantVerifierV2 | None = None,
) -> GovernanceIssuerCapabilityV2: ...

def open_governance_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: GovernanceVerifiedSignalRequestV2
    | GovernanceDomainRetirementRequestV2,
) -> GovernanceAuthoritySessionV2: ...

def commit_verified_signal_v2(
    request: GovernanceVerifiedSignalRequestV2,
    *,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2: ...

def retire_governance_domain_v2(
    request: GovernanceDomainRetirementRequestV2,
    *,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2: ...
```
<!-- authority-session-v2-entrypoints:end -->

`bind_governance_issuer_capability_v2` receives the exact selected writer,
domain, grant, run, epoch, and optional host verifier. It returns an opaque
capability or raises `GovernanceAuthorityBindingErrorV2` for a well-formed
authority binding failure.

`open_governance_authority_session_v2` accepts the capability and the complete
portable request, not a loose list of request fields. It returns an opaque
session or raises the same typed binding exception.

The two commit entrypoints deliberately have no `state_store`/writer argument.
The genuine session privately owns the exact writer binding, and the operation
uses only that object. This makes passing a same-shaped Store B alongside a
Store-A session impossible at the API boundary.

## 9. Atomic session authorization read-set

Opening a session captures exact `GovernanceReadPreconditionV2` values for:

1. the active grant stream revision and head root; and
2. the `authority:domain-lifecycle` stream revision and head root.

Every authorized signal transition includes those captured preconditions plus
the signal write stream's current head in one canonical
`GovernanceAuthorityReadSetV2`. Every authorized retirement includes the same
captured grant/lifecycle preconditions plus the declared non-lifecycle stream
heads required for the seal.

The grant and lifecycle entries are unconditional. A session marker, embedded
grant root, external Trace event, preflight read, or process flag cannot replace
them. StateStore validates the complete read-set in the same atomic boundary as
state or seal, Trace batch, receipt, inclusion proof, and transition identity.
The authority-critical event lineage `domain_root`, when carried by a
`GovernanceTraceBatchV2`, MUST equal the batch's exact `domain_root`; matching
scope, stream, and transition alone is insufficient.

Governance also checks the current durable grant before preparing a commit so
obvious revoked, expired, unverified, or mismatched state returns its typed
diagnostic. That check is not the race boundary; the captured atomic
preconditions remain authoritative. A concurrent change yields
`governance_read_set_stale` or `governance_domain_sealed` with no partial
publication.

## 10. `VERIFY_SIGNAL` vertical slice

### 10.1 Portable request

`GovernanceVerifiedSignalRequestV2` has these exact constructor fields:

<!-- authority-session-v2-signal-request-fields:start -->
```text
domain_root
scope_ref
run_ref
request_ref
transition_id
signal_ref
target_ref
signal_root
evidence_root
status
observed_epoch
stream_ref
schema
canonical_version
request_root
```
<!-- authority-session-v2-signal-request-fields:end -->

`schema` is `pheroos-governance-verified-signal-request-v2` and the root kind is
`verified-signal-request`. `request_root` covers the complete body, including
`request_ref`, `transition_id`, status, roots, epoch, and derived stream.

`status` is exactly `verified` or `rejected`. This record is portable request
data; its status is not authority by possession. An authorized
`VERIFY_SIGNAL` session, issued from the trusted host's active exact grant and
bound to this complete request root, is the issuance trust root for this slice.
There is no additional signal-policy evaluator in this ABI. The commit path
accepts only `status == "verified"`; `rejected` returns
`governance_action_not_authorized` and commits nothing.

The derived stream is exact:

```text
signal_payload = UTF8(scope_ref) || 0x00 || UTF8(signal_ref) || 0x00 ||
                 UTF8(target_ref)
stream_ref = "authority:verified-signal:" ||
             lowercase_hex(SHA-256(signal_payload))
```

The constructor fills an empty `stream_ref` with that value or rejects a
non-empty mismatch. `transition_id` is taken directly from the request during
commit; it is not derived from `request_root`.

### 10.2 Session and commit

The exact commit call is:

```python
commit_verified_signal_v2(
    request,
    authority_session=authority_session,
)
```

The session must be genuine and bind the same operation, domain, scope, run,
request ref/root, observed epoch, and singleton target tuple. The operation uses
the session's private writer and checks that the grant still matches.

The durable state snapshot contains:

```text
schema
domain_root
scope_ref
stream_ref
request
request_root
operation
grant_ref
grant_root
grant_binding_ref
run_ref
signal_ref
target_ref
signal_root
evidence_root
status
observed_epoch
session_binding
```

`schema` is `pheroos-governance-verified-signal-state-v2`.
`session_binding` includes the exact request/grant/head/bound-ref semantics but
never the handle, writer, private marker, or verification object.

The same batch emits exactly one `signal_verified` Trace event. Its lineage
binds domain/scope/stream/transition, run/request, signal/target/evidence roots,
grant refs/roots, operation, observed epoch, and portable session binding.
Only a `COMMITTED` Store result plus valid inclusion creates the durable
verified-signal fact. Exact retry reconciles only when both request and session
binding match the committed view.

## 11. `RETIRE_DOMAIN` vertical slice

### 11.1 Portable request and complete stream declaration

`GovernanceDomainRetirementRequestV2` has these exact constructor fields:

<!-- authority-session-v2-retirement-request-fields:start -->
```text
domain_root
scope_ref
run_ref
request_ref
transition_id
stream_refs
reason_ref
observed_epoch
schema
canonical_version
request_root
```
<!-- authority-session-v2-retirement-request-fields:end -->

`schema` is `pheroos-governance-domain-retirement-request-v2`; the root kind is
`domain-retirement-request`. The complete body, including `request_ref`,
`transition_id`, sorted `stream_refs`, reason, and epoch, is bound by
`request_root`.

`stream_refs` is an exact UTF-8-sorted, duplicate-free tuple with at most 127
entries. It MUST declare the complete current set of non-lifecycle streams in
the domain. It MUST include the session grant stream exactly once and MUST NOT
include `authority:domain-lifecycle`.

The public `GovernanceStateStoreV2` surface intentionally has no stream
enumeration API. Therefore `retire_governance_domain_v2` does not discover or
guess the domain's stream set. The trusted coordinator that constructs the
portable request must supply the complete set. The operation loads the declared
heads, and the existing StateStore seal-closure validation rejects omissions,
unexpected additions, or stale heads without sealing.

Opening a retirement session binds the complete request root but does not
pretend to enumerate or validate closure. An omitted grant stream or included
lifecycle stream is returned by the retirement commit as typed
`governance_read_set_invalid` at `/stream_refs`.
An otherwise well-formed declaration that omits or adds a current
non-lifecycle stream is detected only by the Store's atomic closure comparison
and returns `governance_read_set_stale/RETRY_REQUIRED`, with no partial seal.

### 11.2 Existing seal composition

The exact call is:

```python
retire_governance_domain_v2(
    request,
    authority_session=authority_session,
)
```

The session must be genuine and bind `RETIRE_DOMAIN`, the same domain/scope/run,
request ref/root, epoch, and empty target/action tuples. The operation does not
invent another retirement state record. It builds the existing
`GovernanceDomainSealV2` on `authority:domain-lifecycle`.

The seal read-set contains the captured lifecycle precondition, captured exact
grant precondition, and current heads of every other declared stream.
`final_heads` is the same complete sorted non-lifecycle set. The request's exact
`transition_id` becomes the seal transition id.

The same batch emits exactly one `domain_retired` Trace event. Its lineage
binds run/request/reason, grant refs/roots, operation, epoch, final-heads root,
seal root, and portable session binding.

If revocation commits first, the captured grant precondition cannot authorize
the seal. If the seal commits first, later grant and ordinary writes are denied
by the lifecycle state. If another stream advances first, closure/read-set
validation returns stale. There is no check-then-seal gap. Retirement preserves
all prior state, Trace, receipts, and inclusion proofs; it does not delete a
database or revoke an external credential.

## 12. Python errors, typed bindings, and commit outcomes

The public Draft slice distinguishes construction/programmer failures from total
commit outcomes:

| Boundary | Result |
| --- | --- |
| Wrong exact Python type, direct opaque construction, subclassing, pickle, or malformed function call | `TypeError` or `ValueError` |
| Invalid portable fields, root, version, ordering, epoch, or closed value | `TypeError` or `ValueError` during strict construction/decoding |
| Well-formed capability/session bind or open fails authority binding | `GovernanceAuthorityBindingErrorV2` |
| Exact signal/retirement request reaches a commit entrypoint with missing, fake, or mismatched session | `GovernanceCommitAttemptV2` with typed failure |
| StateStore race, conflict, denial, or unavailable finality | `GovernanceCommitAttemptV2` with the Store/Governance disposition |

`GovernanceAuthorityBindingErrorV2` is a `ValueError` subclass with two typed
attributes: Protocol-owned `AuthorityDiagnosticCodeV2 code` and canonical JSON
Pointer `path`. Its text is not a wire protocol and MUST NOT be parsed.

The commit entrypoints accept `authority_session: object = None` so absence and
forgery are mapped to a total attempt, normally `authority_session_required`.
Binding drift maps to `authority_binding_mismatch`; an unusable private writer
maps to `authority_session_store_mismatch`. Grant/profile/lifecycle failures use
the existing exact diagnostics, including:

```text
authority_profile_unsupported
authority_scope_mismatch
authority_operation_denied
authority_binding_mismatch
authority_grant_unverified
authority_grant_expired
authority_grant_revoked
governance_action_not_authorized
governance_read_set_invalid
governance_read_set_stale
governance_transition_conflict
governance_domain_sealed
governance_finality_unavailable
governance_trace_lineage_invalid
```

No new free-form diagnostic namespace is defined here. A wrong request Python
type still raises `TypeError`; the total-result promise begins after the exact
portable request type is established.

## 13. Trace, secrecy, restart, and custody

Successful activation, revocation, signal commit, and retirement include their
one exact authority-critical event in the same Store batch. A failed attempt
does not publish durable state, a receipt, an inclusion proof, a committed
transition/index entry, or that critical Trace event.

Portable Trace lineage may include declared refs, roots, epochs, event type,
operation, and session-binding values. It MUST NOT include opaque handles, the
writer object, exact domain object, ownership markers, credentials, verifier
objects, secret verifier material, or ephemeral object identity.

Grant, verification, requests, committed states, transitions, receipts, and
proofs may cross restart as portable data. Capability and session handles may
not. After restart, trusted host configuration must select the new exact writer
object, load the committed active grant and lifecycle state, bind a new
run-specific capability (with a fresh authenticated verification when
required), and open a new request-specific session.

No pickle, object id, hidden portable nonce, process-global registry, or copied
slot state bridges restart. The local profile's guarantee is limited to trusted
host/coordinator custody. Opaque Python handles are least-privilege API objects,
not a sandbox against arbitrary malicious Python in the same process.

## 14. Conformance obligations and non-goals

To retain Draft activation and become eligible for later Stable promotion,
deterministic provider-free evidence MUST prove at least:

- the exact field sets, roots, strict wire round-trips, and closed enum/status
  values above;
- local and authenticated verification behavior, including no local fallback;
- exact Store/domain/run/request/operation/target binding and forged-handle
  rejection;
- direct construction, subclassing, serialization, pickle, reflection, copy,
  deepcopy, and restart behavior;
- activation/revocation lifecycle, exact reconciliation, and terminal
  revocation;
- captured grant/lifecycle preconditions on every session-authorized commit;
- exact StateStore version rejection at activation, bind, open, and commit;
- direct committed-batch proof of the captured grant/lifecycle read-set;
- `verified` versus `rejected` signal behavior with no invented policy layer;
- caller-declared retirement closure because Store has no enumeration API;
- exact event names and portable lineage with no handle/writer leakage;
- adversarial Store/grant/lifecycle/read-set/finality races with zero partial
  publication; and
- unchanged v1 behavior without implicit migration.

The public
`run_governance_authority_session_conformance_v2(...)` matrix applies the same
session behavior to the private reference StateStore and an independent stdlib
StateStore model. An independent external verifier adapter and production
StateStore adapter remain separate Conformance evidence. Passing the bundled
matrix alone does not establish authenticated production compatibility.

This contract does not add a generic capability/security/policy manager,
identity service, credential store, provider gateway, database schema, endpoint,
worker, queue, dashboard, plugin marketplace, agent framework, action executor,
or model client. It does not expose the StateStore writer to agents or Drivers.

The public ABI and local profile remain Draft. Exact dispatch, negative paths,
provider-free examples, source boundaries, Output v2, schema/TCK artifacts, and
Runtime Integration are implemented; external grant-verifier Conformance and
formal lifecycle promotion remain required before an authenticated production
or Stable claim. Its private implementation owner and bundled matrix are
necessary evidence, not self-certification.
