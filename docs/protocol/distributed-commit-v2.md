# Distributed Commit v2 ABI

Status: durable protocol-core ABI with verified and external Byzantine
conflict-observation TCK paths.

Distributed Commit v2 turns distributed finality into four fixed,
StateStore-backed governance streams. Portable proposals, witnesses,
certificates, and epoch certificates are data, never authority. Authority
comes only from an exact issuer session, an atomic full read set, and an opaque
state handle revalidated against the current Store.

This package is protocol core. It contains no provider client, network service,
database, worker, agent colony, model router, or consensus daemon. A host
runtime transports signed records and supplies durable StateStore and trusted
attestation-verifier implementations.

## Fixed lanes

For one `(scope, protocol, run, target)` tuple, the ABI derives exactly four
distinct stream references:

| Lane | Durable value | Authorized state |
| --- | --- | --- |
| `epoch` | static Membership epoch and certified transition | active epoch or sticky recovery history |
| `proposal` | declared proposal envelopes and semantic values | active proposal set |
| `witness` | trusted principal attestations and equivocation findings | active or sticky frozen |
| `certificate` | quorum certificates and conflicting certificate roots | verified or sticky frozen |

Stream and transition identifiers are deterministic. Genesis snapshot and
history roots are lane-specific. Every committed snapshot binds its parent,
dependency set, mutation, source context, history count/root, lane state root,
and canonical request root.

## Static-epoch policy

The declared eligible Membership set is exact and bounded to 4,096 principals.
For membership size `n`, maximum Byzantine faults `f`, and witness quorum `q`,
validation enforces all three equations:

```text
n >= 3f + 1
q <= n - f
2q - n > f
```

The minimum failure-domain diversity is positive, cannot exceed `q`, and must
be reachable by the exact current Membership. Principal references,
verification roots, clusters, and failure domains are explicit. A Membership
snapshot must be current at the logical evaluation step.

## Proposal and witness semantics

A proposal value binds the current sealed Decision, the verified central
Certificate, Membership and principal-verification truth, manifest/policy,
candidate, claim, seal, scope, run, target, and epoch. Its semantic value root
is separate from its proposal-envelope digest. A different nonce or provenance
may therefore be a semantic retry without inventing a second truth.

A witness binds the proposal digest and semantic value root, its principal and
verification root, cluster and failure domain, epoch, candidate and claim,
Membership and verification-set roots, provenance, trace roots, and an exact
logical validity interval. The trusted verifier receives the canonical signing
root. A witness is usable only when:

```text
witnessed_at_step <= current_step < expires_at_step
expires_at_step - witnessed_at_step == declared witness_ttl_steps
```

Repeated envelopes for the same semantic value are retries. Two trusted
witnesses from one principal in one epoch for different semantic values create
an equivocation finding and make the witness lane sticky `FROZEN`.

## Certificates and recovery

A distributed certificate contains canonical proposal digests and trusted
witnesses for one semantic value. Issuance rechecks exact Membership size,
quorum, principal uniqueness, and failure-domain diversity. Certificate
feedback cannot create evidence or authority. Two distinct certified semantic
values make the certificate lane sticky `FROZEN`.

Epoch transition certificates bind the prior epoch snapshot, current
Membership and verification roots, transition provenance, source traces, and
the exact action set. Normal transitions require `epoch_transition`. Recovery
from recorded witness or certificate conflicts additionally requires
`recovery`; conflict-history roots cannot later be erased. Epochs advance by
exactly one and cannot roll back or skip.

## Atomic authority and retry

Every lane commit performs one StateStore CAS over:

- the exact parent head;
- every declared cross-lane and upstream dependency head;
- the issuer-grant head; and
- the domain-lifecycle head.

An already committed identical transition returns its original receipt before
revocation or lifecycle checks. A different request against a stale parent or
dependency returns the typed `GOVERNANCE_READ_SET_STALE` retry result. No
process-local registry, portable source token, or deserialized state object can
replace current Store verification.

The four opaque `VerifiedDistributed*StateV2` handles are nonconstructible,
nonserializable, and exact-reader-bound. The neutral finality adapter emits a
`CommitFinalityProjectionV2` owned by `DISTRIBUTED`, using the certificate lane
as the canonical owner stream. A verified projection may authorize the sealed
Decision; pending, unavailable, and conflict projections remain typed facts for
Decision governance.

## Trace and conformance

The closed Trace contract validates six event types independently of
Governance implementation imports:

- `distributed_epoch_advanced_v2`
- `distributed_proposal_advanced_v2`
- `distributed_witness_advanced_v2`
- `distributed_certificate_advanced_v2`
- `distributed_witness_conflict_v2`
- `distributed_certificate_conflict_v2`

Trace validation recomputes stream, transition, request, dependency-set,
read-set, state, history, snapshot, session, grant, and lifecycle bindings. The
same six real event payloads pass the closed JSON Schema.

`run_governance_distributed_commit_conformance_v2` runs the verified four-lane
journey against any public StateStore v2 conformance adapter. The repository
runs it against both the reference Store and the independent standard-library
model, including fresh-reader restart, currentness, finality-handle creation,
closed Trace coverage, portable-request tamper rejection, external witness
conflict freeze, exact retry, conflict restart, and Decision safety
composition.

## External Byzantine conflict observation

The rule that a non-`VERIFIED` central Certificate cannot authorize a new
distributed proposal is a required safety invariant and must not be weakened.
It prevents a conflicting central authority value from becoming distributed
truth.

`DistributedWitnessConflictObservationV2` closes the audited conflict-ingress
gap without opening a second proposal or certificate authority path. It is a
portable record containing the complete externally observed proposal and
witness, observation time, provenance, trace roots, and a canonical
`observation_root`. Like every portable record, it has no authority.

`prepare_distributed_witness_conflict_observation_v2` accepts that record only
through an opaque, nonportable source recipe. Preparation and commit recheck:

1. the normal current Decision and central Certificate still satisfy the
   central `VERIFIED` gate;
2. the epoch, proposal, Membership, and principal-verification states are exact
   current Store-verified handles;
3. the external value retains the exact sealed authority, target, candidate,
   claim, central Certificate, Membership, policy, and verification bindings;
   only its explicitly observed current-Decision coordinates may differ;
4. the external witness names an eligible current principal, cluster,
   failure domain, and verification root, has exact policy TTL, and passes the
   supplied trusted attestation verifier over its canonical signing root;
5. the witness parent already contains the same principal's witness for the
   current local semantic value; and
6. parent, proposal, epoch, Decision, central Certificate, Membership,
   principal verification, issuer grant, and lifecycle heads all remain equal
   in one atomic CAS.

The only legal result is `EQUIVOCATION_FROZEN` on the existing witness lane.
The external proposal is never inserted into the proposal lane, never counted
as quorum support, never used to issue a certificate, and never authorized as
an alternate value. The full observation is embedded in the durable
equivocation finding; the finding root therefore binds it into witness state,
snapshot history, restart records, and the existing
`distributed_witness_conflict_v2` Trace event without defining a duplicate
event type.

Exact retries return the original receipt. Same-shaped sources, pickled source
handles, string verifier claims, bad attestations, changed sealed bindings,
stale parents, dependency races, and retired domains fail closed. A frozen
witness lane projects `CONFLICT` through the distributed finality adapter; the
next sealed Decision successor deterministically terminates as
`SAFETY_VIOLATION` and cannot publish the external value.
