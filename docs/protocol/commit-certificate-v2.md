# Commit Certificate v2 Draft ABI

Commit Certificate v2 is the portable finality owner for certified and
distributed Commit Decision v2 streams. It records independently checkable
decision, seal, evidence, authority-head, and output commitments while keeping
authority inside Governance and the atomic StateStore.

Portable certificate bytes are data, not authority. A certificate becomes a
governance fact only after a trusted issuer adapter accepts its attestations
and the complete replacement is atomically committed against the closed read
set described below.

## Boundary

The Draft facade is `pheroos.governance.commit_certificate_v2`. Its public
surface contains portable contracts, deterministic root helpers, the trusted
attestation adapter protocol, preparation and commit operations, and opaque
rehydrated state handles.

The ABI does not provide:

- key storage, certificate authorities, PKI, signature algorithms, or trust
  policy;
- a model provider, agent runtime, network service, database implementation,
  queue, or background verifier;
- authority from raw JSON, a portable dataclass, a caller-supplied boolean, or
  a replayed Trace event.

The runtime supplies a provider-neutral
`CommitCertificateIssuerAttestationVerifierV2`. The verifier decides whether
an issuer/attestation/body-root tuple is trusted. The protocol requires an
exact boolean result and re-runs the verifier immediately before commit. A raw
mapping is not a verifier.

## Fixed authority stream

The certificate stream is fixed by:

```text
scope_ref + protocol_ref + run_ref + target_ref
```

Certificate IDs, issuers, attestation references, envelope nonces, candidates,
claims, seal roots, and mutable Decision revisions do not select the stream.
Each mutation transition is fixed by the stream and `mutation_ref`.

This gives one ordered certificate history for one target in one protocol run.
Every committed snapshot is a complete replacement; there is no patch merge,
partial update, or process-local registry.

## Portable certificate

`PortableCommitCertificateV2` has two independently rooted layers:

1. `CommitCertificateBodyV2` is semantic truth. It binds policy identity,
   Decision current inclusion, the actual seal inclusion, the chosen subject,
   evidence and output roots, and the closed authority-leaf set.
2. The envelope binds certificate ID, issuer, issuance step, provenance,
   nonce, body, and canonical attestation references.

Changing any body field changes `body_root`. Changing any envelope field
changes `envelope_root`. Decoding requires exact fields, exact scalar types,
canonical UTF-8 ordering, bounded arrays, lowercase SHA-256 roots, supported
versions, and complete root reconstruction. Booleans cannot substitute for
integer revisions or epochs.

`verify_portable_commit_certificate_v2` reconstructs both layers and then
consults the explicitly supplied trusted verifier. Optional expected subject
and epoch arguments bind verification to the caller's context. Verification
does not create Store authority.

## Decision and seal lineage

Certificate preparation consumes only the opaque, current
`VerifiedCommitDecisionStateV2` adapter. It never accepts a raw Decision
snapshot or a caller-created inclusion claim.

The body distinguishes two observations:

- `decision_*` identifies the current, non-terminal Decision revision used for
  issuance, including its Store receipt and inclusion proof;
- `seal_*` identifies the actual historical `SEALED` transition, including its
  revision, snapshot, Store receipt, head, and inclusion proof.

A current Decision may be a later heartbeat. The implementation walks and
validates the parent chain until it reaches the actual `SEALED` transition and
requires the seal root to remain unchanged. It never substitutes the current
heartbeat receipt for the seal receipt.

The body additionally binds:

- manifest and commit-policy roots, profile, assurance, protocol, run, target,
  and epoch;
- window, frozen-dependency, assessment, candidate, and claim roots;
- evidence, challenge, support-lease, output-contract, and output-payload
  roots;
- exactly eight authority leaves.

## Closed authority-leaf set

The eight required leaves are:

```text
Replay
Risk
Membership
Principal Verification
Evidence
Support
Stop
Permission
```

Each leaf commits role, stream, revision, transition, snapshot, head, and
receipt. Roles and streams are unique and ordered canonically. Missing,
duplicated, unknown, historical-at-observation, or genesis-placeholder leaves
fail closed.

Principal Verification is an explicit leaf. It is not inferred from
Membership and must not be omitted under an older seven-dependency model.

## Atomic issuance

Issuance reuses the frozen
`GovernanceIssuerOperationV2.EVALUATE_QUORUM` operation. No new issuer
operation or mutable authority registry is introduced.

The atomic read set contains exactly twelve streams:

```text
1 certificate parent
1 current Commit Decision
8 authority leaves
1 issuer grant
1 domain lifecycle
```

Preparation and commit both revalidate the opaque Decision state, actual seal,
manifest policy, trusted attestation adapter, exact certificate body, and
parent replacement. Immediately before atomic commit the operation reloads all
nine upstream heads (Decision plus eight leaves). The StateStore CAS then
closes the race across the parent, upstreams, grant, and lifecycle.

No global lock is required. Concurrent writers race through StateStore CAS;
only a replacement whose complete read set remains current can commit.

## Retry, restart, and history

The transition ID is deterministic. An exact retry first reconciles the
already committed transition and returns the original receipt. Reconciliation
happens before current grant-revocation and domain-lifecycle checks, so a
caller that lost a response can recover committed truth even if the grant or
domain changed afterward.

This exception applies only to the exact committed request and session
binding. A new mutation after revocation or retirement is denied.

Opaque `VerifiedCommitCertificateStateV2` handles retain only the request,
receipt anchor, domain, and StateReader. Every property observation reloads
and validates committed state, receipt, Trace, read-set shape, Decision and
seal inclusions, all eight historical authority receipts, and parent history.
Handles cannot be constructed, subclassed, mutated, or pickled.

## Semantic retry and conflicts

The reducer separates semantic truth from transport re-attestation:

- the first accepted body is `verified`;
- the same body in a different valid envelope is `semantic_retry` and adds the
  new envelope/identity lineage without changing semantic truth;
- one certificate ID naming two bodies is a conflict;
- one seal naming two bodies is a conflict;
- a different seal that does not advance the epoch is a conflict;
- after conflict, conflict status is sticky.

A future epoch may replace an earlier verified body only when it carries a
different seal and a strictly advancing epoch. The reducer never guesses a
merge between two bodies.

## Finality adapter

Certificate authority is exposed to Commit Decision through the Draft owner
adapter
`pheroos.governance.commit_certificate_v2.verified_commit_certificate_finality_input_v2`.
Portable certificate data does not implement the adapter, and the adapter is
not a neutral finality issuer.

The adapter revalidates both Store-backed handles and requires:

- the certificate transition is still current;
- the supplied current Decision heartbeat is still current and non-terminal;
- the actual `SEALED` transition remains present in verified Decision history;
- the verification step is exactly the next Decision heartbeat and precedes
  the finality deadline;
- current Decision, actual seal, subject, evidence, output, and all eight leaf
  commitments exactly match the certificate;
- every authority-leaf head remains current.

After revalidation, the adapter returns an opaque, non-portable
`VerifiedCommitFinalityInputV2` whose canonical public type is owned by
`pheroos.governance.commit_finality_v2`. Issuance remains inside the neutral
private contract. The Certificate facade neither exposes the private issuer
nor re-exports the neutral handle type; it references the canonical type only
in the adapter's return annotation. This keeps module identity stable and
avoids a Certificate-to-Decision public facade dependency. The handle contains a
`CommitFinalityProjectionV2` owned by `CERTIFICATE`, plus the certificate CAS
precondition and receipt/inclusion roots. The projection is `VERIFIED` or
`CONFLICT`; it never directly commits a Decision outcome. Decision revalidates
the exact owner dependency before committing `EVIDENCE_COMMIT` or
`SAFETY_VIOLATION`.

The adapter accepts only an opaque current
`VerifiedCommitCertificateStateV2`, an opaque current sealed Decision state,
and the exact next heartbeat step. Direct construction, subclassing,
mutation, incomplete object fabrication, and serialization of the returned
handle fail closed. Copy and deep-copy preserve the same verified opaque
handle rather than manufacturing new authority.

## Trace

Each successful Store transition emits exactly one atomic event:

- `commit_certificate_verified_v2` for verified and semantic-retry snapshots;
- `commit_certificate_conflict_v2` for conflicting snapshots.

The private Trace contract is independent of Governance implementation
helpers. It validates exact lineage fields, session scope, stream and
transition identity, profile/assurance, status/mutation consistency, all eight
leaf roots and the leaf-set root, source-context root, and the exact twelve
entry read-set root.

Trace records explain a committed fact. They cannot be replayed to create
authority.

## Conformance and activation status

The currently published Commit Certificate v2 Conformance matrix covers only
the portable contract: canonical reconstruction, two independent trusted
attestation-verifier adapters, mutation rejection, expected-context binding,
and rejection of portable data as authority. It does **not** claim durable
owner portability across StateStore implementations.

The owner test matrix exercises the public finality entrypoint against real
current Store commits, the exact
twelve-stream CAS set, restart rehydration, exact retries, dependency races,
concurrent forks, Trace validation, and both `VERIFIED` and `CONFLICT`
Decision finality paths. A public dual-StateStore owner matrix is intentionally
held behind the shared Decision + Certificate + Distributed activation gate.
It will be registered only when the public Commit Decision Draft facade and
the Distributed finality owner are activated together. Production Conformance
must not import private Decision modules to bypass that gate.

## Failure model

Portable decoding and trusted verification use exceptions or `False` because
they do not mutate authority. Store operations return typed
`GovernanceCommitAttemptV2` failures with diagnostic code, path, and stage.

Representative fail-closed cases include:

- wrong scope, run, target, issuer, profile, assurance, manifest, or policy;
- stale parent, Decision, authority leaf, issuer grant, or lifecycle head;
- missing or forged Decision/seal receipt or inclusion proof;
- missing Principal Verification or any other required role;
- altered certificate/body/envelope root, unknown field, wrong scalar type, or
  over-limit resource;
- an untrusted or non-boolean attestation result;
- current-step, heartbeat, or finality-deadline mismatch;
- unavailable historical finality.

## Compatibility and runtime responsibilities

Commit Certificate v2 is Draft and applies only to certified or distributed
Commit Decision v2 policies with the matching portable/distributed certificate
mode and both issuer-attestation and independent-verification requirements.
Baseline, advisory, and evidence-bound protocols remain unchanged.

An external runtime is responsible for selecting a StateStore implementation,
maintaining trust material, implementing the attestation verifier, retaining
history required by the Store ABI, and coordinating the next Decision
heartbeat. Those responsibilities do not expand protocol-core into a server,
provider gateway, database, or certificate-management product.
