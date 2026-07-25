# Commit Evidence v2 ABI

Commit Evidence v2 is the Store-backed evidence authority consumed by the
durable Commit Decision path. It qualifies proposal data into an append-only,
target-scoped evidence stream. It does not call models, tools, providers, or
external databases.

## Authority boundary

Portable attestations, snapshots, projections, and evaluations are data. They
do not authorize a decision. Evidence authority exists only when all of the
following are true:

1. the request is bound to an exact `QUALIFY_EVIDENCE` authority session;
2. the session is backed by the same StateStore v2 instance used for commit;
3. Principal Verification, Membership, and Commit Replay are current committed
   dependencies for the same scope, protocol, run, target, and epoch;
4. the complete Evidence replacement commits atomically with its closed Trace
   event; and
5. a consumer re-verifies the committed view and current dependency heads.

Digest possession, request serialization, a projection, an evaluation, or an
object with the same public attributes cannot satisfy this boundary.

## Fixed stream and subject identity

One Evidence stream is selected by:

```text
(scope_ref, protocol_ref, run_ref, target_ref)
```

Epoch, candidate, claim, issuer, and policy version are state, not stream
selectors. This keeps cross-epoch history in one bounded stream and prevents
unbounded StateStore stream growth.

An evaluation subject is the exact tuple:

```text
(candidate_ref, claim_root, epoch)
```

Evidence for another candidate or claim is never aggregated into that subject.
If one candidate has multiple active claim roots, the authoritative Decision
adapter returns a typed subject conflict instead of allowing the caller to pick
the favorable claim.

## Proposal records

`CommitEvidenceAttestationV2` declares one of three evidence kinds:

- `positive`: support from a verified principal and independence group;
- `counter`: contrary evidence with an explicit disposition proposal; or
- `challenge`: a deterministic required-category challenge result.

Each proposal binds candidate, claim, epoch, principal, payload, nonce,
observation window, provenance, and Trace roots. Counterevidence requires one
exact `CounterevidenceDispositionProposalV2`. Replay receipts are derived from
the complete proposal data before qualification.

Agents may propose these records. They cannot qualify them, manufacture
Membership or Principal Verification authority, create Replay authority, or
commit an Evidence head.

## Qualification transition

The public operation is:

```text
prepare_commit_evidence_advance_v2
  -> open_commit_evidence_authority_session_v2
  -> advance_commit_evidence_state_v2
  -> rehydrate_commit_evidence_state_v2
```

Preparation validates the manifest policy, current dependencies, replay
coverage, proposal types, provenance, challenge relations, TTL, and parent
history. It returns a portable complete-replacement request and an opaque,
non-serializable source proof.

The commit uses one exact six-entry read set:

1. Evidence parent head;
2. issuer-grant head;
3. domain-lifecycle head;
4. Membership head;
5. Principal Verification head; and
6. Commit Replay head.

Every head is checked again by StateStore CAS. A dependency advance between
source validation and atomic publication returns
`GOVERNANCE_READ_SET_STALE`; it cannot publish a partially valid Evidence
state. Lost-response retry of the same committed transition returns the same
receipt without requiring the original opaque source again.

## Complete replacement and history

Every revision contains the complete bounded record set and exact mutation
roots. Historical records cannot disappear. A record may change only through a
declared revocation replacement that preserves immutable qualification fields
and adds exact revocation lineage.

The snapshot binds:

- parent revision, epoch, transition, snapshot, and history roots;
- manifest, authority, commit, and evidence policy roots;
- Membership, Principal Verification, and Replay committed heads;
- complete record, active-record, mutation, removal, and revocation roots; and
- deterministic history count and root.

Policy changes inside one epoch fail closed. A policy rotation requires a new
epoch while preserving the fixed stream lineage.

## Deterministic evaluation

`evaluate_commit_evidence_projection_v2` is a pure, portable calculation. It
is useful for interoperability and testing, but is not an authority grant.

Positive and counter caps are applied by `independence_ref`, not by cluster.
Cluster and failure-domain identities are used separately for diversity. Every
counted `(failure_domain_ref, cluster_ref)` contribution must satisfy the
declared contribution floor before it can participate in the diversity
matching calculation.

The evaluator checks:

- Replay coverage;
- positive and weighted-counter totals;
- counter ratio and critical blockers;
- required challenge categories;
- source diversity; and
- all declared evidence gates.

All authority integers use exact integer types. Boolean-as-integer values and
values outside the canonical range are rejected. Addition, scaling, weighting,
and signed net calculations saturate at the declared authority bounds before
canonical output, so large valid inputs cannot produce a non-serializable
result.

## Time and Decision totalization

Record freshness uses the half-open interval:

```text
observed_at_step <= current_step < expires_at_step
```

At the exact expiration step, the record contributes no positive,
counterevidence, challenge coverage, net value, or diversity.

Evidence, Membership, and Principal Verification freshness are also evaluated
at the Decision request's explicit `current_step`; wall-clock time is never
used. A Store head can remain current after its declared TTL. In that case the
opaque Decision context still returns the exact Evidence, Replay, Membership,
and Principal Verification receipts and read preconditions so Decision can
atomically commit a typed terminal outcome. The context marks freshness false,
removes all stale records and active subjects, and refuses authoritative
assessment with `GOVERNANCE_READ_SET_STALE`.

This distinction is intentional:

```text
current Store head != fresh positive authority
```

It preserves liveness at deadlines without allowing expired evidence to pass a
gate.

## Trace ABI

Each committed Evidence revision emits exactly one
`commit_evidence_qualified_v2` event in the same atomic batch. The closed Trace
contract independently derives and validates:

- canonical stream and transition identity;
- parent and history lineage;
- mutation delta root;
- source-context root;
- the six-entry read-set root; and
- Membership, Principal Verification, and Replay bindings.

Unknown fields, reordered or duplicated root arrays, boolean counters, invalid
nullable epochs, detached dependency roots, and forged derived roots fail
closed.

## Conformance and example

The public-only matrix is
`pheroos.conformance.checks.commit_evidence_v2_contract`. The same matrix runs
against the reference StateStore and the independent stdlib specification
adapter. It covers vertical commit, exact retry, restart, source imitation,
canonical input order, candidate/claim isolation, and conflicting forks. Its
positive path uses two independently verified principals in distinct clusters
and failure domains and proves that all evidence gates pass. A separate
single-principal path proves that one source remains insufficient.

Run the provider-free executable proof with:

```bash
python3 examples/commit-evidence-v2-protocol/run.py
```

The example uses no API key, model provider, network, database, daemon, worker,
or agent framework.

## Non-goals

Commit Evidence v2 is not an evidence database, retrieval service, vector
store, analytics system, agent memory framework, model verifier, provider
gateway, or workflow engine. Production persistence is supplied by an external
StateStore v2 implementation that passes Conformance.
