# Commit Finality v2 ABI

Status: **Draft direct-module ABI; not aggregate-activated or Stable**

`pheroos.governance.commit_finality_v2` is the authority-neutral public ABI
shared by Commit Decision, Commit Certificate, and Distributed Commit v2. It
owns their finality contracts' canonical Python identity. It does not own a
finality authority stream and cannot issue authority.

## Public surface

The facade exposes exactly:

```text
COMMIT_FINALITY_INPUT_SCHEMA_V2
COMMIT_FINALITY_PROJECTION_SCHEMA_V2
CommitFinalityOwnerV2
CommitFinalityProjectionV2
CommitFinalityStatusV2
VerifiedCommitFinalityInputV2
commit_finality_owner_genesis_snapshot_root_v2
commit_finality_owner_stream_ref_v2
```

`CommitFinalityProjectionV2` is canonical portable data. It records one
Certificate or Distributed owner observation, including status, current owner
head and receipt, the historical Decision seal, frozen dependencies, the
verification step, and reason codes. A projection never grants authority.

`VerifiedCommitFinalityInputV2` is an opaque, non-portable bridge. It cannot be
constructed, subclassed, mutated, or serialized. Copy and deep-copy preserve
the same verified object. The neutral facade exposes the type for signatures
and exact-type checks, but exposes no constructor or issuer.

## Authority boundary

Certificate and Distributed remain the only producer facades. Their
owner-specific adapters revalidate current StateStore position, receipts,
inclusion, Decision seal lineage, and policy-specific dependencies before a
private neutral issuer creates the opaque handle. Decision consumes the
handle, copies only its portable projection into a request, and binds the
owner head in its atomic read set.

The public neutral facade does not expose private issuer, material, token, or
inspection helpers. Importing it does not import Decision, Certificate, or
Distributed facades. Owner facades may depend on this facade for public type
annotations; this facade must never depend on an owner facade.

## Identity and compatibility

All public finality classes and helpers have
`pheroos.governance.commit_finality_v2` as their canonical module identity,
independent of owner-facade import order.

The Draft Decision facade retains its eight former finality names as
compatibility aliases. Those aliases resolve to the exact canonical objects
and do not rewrite their module identity. This preserves direct imports and
legacy Python pickle globals while making new reflection and pickle output use
the neutral module. Wire payloads, roots, Store records, CAS behavior, and
authority semantics are unchanged.

Aggregate activation must register the neutral facade as the one canonical
owner of these names. Compatibility aliases must not be mistaken for a second
ABI owner.

## Composite conformance contract

`pheroos.conformance.checks.commit_finality_v2_contract` is the durable,
provider-free TCK for the shared finality bridge. Its exact version is
`pheroos-governance-commit-finality-conformance-v2`. The module exports only
that version constant and
`run_governance_commit_finality_conformance_v2`.

The same matrix runs against both the reference StateStore and the independent
standard-library StateStore. It uses only public Governance facades and
commits real authority transitions for the following paths:

- a `VERIFIED` Certificate owner handle produces Decision
  `EVIDENCE_COMMIT`;
- a durable Certificate `CONFLICT` owner handle produces Decision
  `SAFETY_VIOLATION`;
- a Certificate semantic owner successor makes a precomputed Decision
  transition stale and returns `RETRY_REQUIRED`;
- a verified Distributed certificate lane produces Decision
  `EVIDENCE_COMMIT`;
- a publicly submitted, verifier-authenticated Distributed witness conflict
  commits a freeze-only witness transition; the current `FROZEN` owner then
  produces an opaque verified finality input and Decision
  `SAFETY_VIOLATION`;
- a Distributed semantic owner successor makes a precomputed Decision
  transition stale and returns `RETRY_REQUIRED`;
- a missing opaque owner handle stays provisional until the declared finality
  deadline, then produces `FINALITY_UNAVAILABLE` with no publication or
  execution authorization; and
- neither a portable `CommitFinalityProjectionV2` nor its projection root can
  replace the exact opaque `VerifiedCommitFinalityInputV2` handle.

The CAS journeys prepare a Decision successor first, advance the relevant
owner stream second, and then submit the stale Decision transition. This
proves atomic currentness against an actual owner successor rather than merely
comparing detached values.

## Distributed conflict coverage

The composite TCK reaches Distributed conflict only through the public
freeze-only observation ABI. A portable conflict observation carries an
alternate proposal and a real witness attestation; the public owner validates
the current Membership principal, verification root, cluster and failure
domain, epoch, sealed authority bindings, lifetime, and provenance before a
non-portable source may commit. The resulting witness-lane transition is
durable and sticky `FROZEN`; it neither appends to the proposal lane nor grants
quorum support to the alternate value.

The TCK then supplies that current frozen witness state to the public
Distributed finality adapter. The adapter revalidates all owner dependencies
against the real StateStore and returns an exact opaque
`VerifiedCommitFinalityInputV2`. Decision consumes the handle and commits
`SAFETY_VIOLATION` with `finality:conflict`. No private reducer, detached state,
or legacy authority registry is used.
