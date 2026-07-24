# Principal Verification, Membership, and Support v2

Status: Draft ABI

Public Python facade: `pheroos.governance.support_v2`

Conformance version: `pheroos-governance-support-conformance-v2`

## Scope

Support v2 is one durable, ordered authority chain:

```text
PrincipalVerificationSet v2
  -> Membership v2
    -> Support v2
      -> deterministic SupportEvaluation v2
```

The chain answers four different questions:

- Principal Verification records which principals have current, traceable
  external verification.
- Membership projects those records into Sybil-collapsed clusters.
- Support records evidence-bound lease issuance, revocation, switching, expiry,
  and eviction in one fixed ledger.
- SupportEvaluation derives current cluster support and equivocation exclusions.

It does not call a model provider, create evidence, grant authority to an
agent, or supply a database/server runtime.

## Authority rule

Portable records, snapshots, requests, evaluations, roots, and canonical bytes
are deterministic meaning only. They are not authority.

`Verified*SourceV2` objects prove deterministic preparation against exact
inputs. They are non-portable, final, caller-unconstructible, and still are not
authority.

`Verified*StateV2` objects are non-portable Store-bound handles. Rehydration
verifies the complete committed transition, inclusion proof, Trace batch, read
set, and observed position before issuing the handle. Later source/evaluation
uses revalidate the detached receipt anchor against the current Store head,
current state projection, and required transitive upstream heads; it does not
trust the cached portable payload as a currentness proof. A portable request
becomes authoritative only after the matching operation commits it atomically
through an exact scoped authority session.

The operation mapping is:

| Ledger | Authority operation | Commit entry point |
| --- | --- | --- |
| Principal Verification | `QUALIFY_EVIDENCE` | `advance_principal_verification_set_v2` |
| Membership | `EVALUATE_QUORUM` | `commit_membership_epoch_v2` |
| Support | `QUALIFY_EVIDENCE` | `advance_support_state_v2` |

Agents may propose records and observations. They cannot construct source/state
handles, choose the committed head, bypass current upstream state, or turn an
evaluation into publication authority.

## Fixed stream identity

Each ledger has one deterministic stream for an exact
scope/profile/assurance/manifest/policy/protocol/run/target binding.

Issuer identity and epoch are state, not stream selectors. Therefore issuer
rotation and epoch changes remain in one audit lineage. A mutation reference is
mapped deterministically to one transition ID; the same transition cannot be
reused for different content.

The public derivation functions are:

- `principal_verification_stream_ref_v2`
- `principal_verification_transition_id_v2`
- `membership_stream_ref_v2`
- `membership_transition_id_v2`
- `support_stream_ref_v2`
- `support_transition_id_v2`

## Principal Verification set

`PrincipalVerificationRecordV2` binds:

- principal, cluster, and failure-domain references;
- verification method and verification issuer;
- attestation and evidence roots;
- issuance and expiry steps;
- provenance and source Trace roots.

One `PrincipalVerificationSetSnapshotV2` is a complete replacement set, not a
patch. Records are canonically ordered by UTF-8 bytes. Principal, record, and
attestation reuse is rejected. The set snapshot binds its policy root, epoch,
parent revision/transition/root, expiry, issuer, record count, set root, and
snapshot root.

Preparation accepts a portable prior snapshot only to calculate the proposed
successor. Commit independently loads and verifies the actual Store parent.

## Membership

Membership can be prepared only from a Store-current
`VerifiedPrincipalVerificationSetStateV2`. It projects verified principals into
`MembershipClusterV2` records and collapses voting/support identity to one
cluster unit.

The Membership snapshot independently binds the complete Verification context:

- Verification stream and transition;
- Verification snapshot, set, and policy roots;
- Verification request reference;
- Verification current and expiry steps;
- Verification record count.

Membership cannot introduce a principal, cluster, method, issuer, or
verification root that is absent from the committed Verification set. Its
commit read set includes the exact current Verification head in addition to
its own parent, authority grant, and domain lifecycle.

## Support ledger

Support uses one ledger with four mutation kinds:

- `initialize`: creates the empty revision-one ledger;
- `issue`: creates a lease from current Membership, a proposal, and exact
  positive observations;
- `revoke`: removes one active lease and records the revocation lineage;
- `switch`: atomically revokes one lease and issues its declared replacement.

The active projection contains current leases only. Expired leases are
deterministically evicted by the next mutation. Durable history remains a
constant-space parent-bound accumulator:

```text
history[n] = H(history[n-1], transition_id[n], mutation_delta_root[n])
```

The mutation delta binds the mutation kind, observed epoch, current step,
issuer, provenance, Trace roots, parent identity, complete issued/revoked
records, evictions, and Membership precondition. A caller cannot retain a stale
lease by omitting it from an eviction list or reuse a pruned record under a new
transition.

Lease nonces are scoped by principal cluster. Collision checks do not turn an
unrelated cluster's nonce into global authority.

## Support preparation

The public preparation functions are:

- `prepare_support_initialize_v2`
- `prepare_support_issue_v2`
- `prepare_support_revoke_v2`
- `prepare_support_switch_v2`

Issue and switch require both a Store-current Support state handle and a
Store-current Membership state handle. Preparation rejects stale/future
observations, undeclared candidates, mismatched claim/epoch/context, invalid
principal membership, excessive TTL, incomplete observation roots, invalid
switch ancestry, and mutation lineage mismatches.

The commit path reads the Store again. A source prepared from a parent or
Membership head that is no longer current returns
`RETRY_REQUIRED/GOVERNANCE_READ_SET_STALE`; it is never silently rebased.

## Evaluation

`evaluate_support_v2` accepts Store-current Support and Membership handles. It:

- evaluates one exact candidate, claim, epoch, and step;
- derives active/revoked/expired/equivocated lease status;
- excludes every lease involved in same-context overlapping equivocation;
- counts unique verified clusters, not agents or observations;
- applies both the declared minimum cluster count and support ratio;
- returns a canonical `SupportEvaluationV2`.

An evaluation is portable evidence of deterministic calculation. It cannot
commit a candidate, authorize output, or create evidence/authority.

## Atomic read set and Trace

Every commit includes the exact write head, issuer-grant head, and domain
lifecycle head. Membership additionally includes the current Verification
head. Support issue/switch additionally include the current Membership head.

State and Trace publish in one StateStore v2 transaction. Event sequences are:

| Transition | Exact event sequence |
| --- | --- |
| Verification advance | `principal_verification_set_advanced` |
| Membership commit | `membership_epoch_committed` |
| Support initialize | `support_state_advanced` |
| Support issue | `support_state_advanced`, `support_lease_issued_v2` |
| Support revoke | `support_state_advanced`, `support_lease_revoked_v2` |
| Support switch | `support_state_advanced`, `support_lease_revoked_v2`, `support_lease_issued_v2` |

Trace validation independently recomputes stream, transition, parent,
source-context, read-set, policy, issuer, Verification/Membership, mutation,
delta, and record lineage. It does not trust roots repeated by the producer.

## Replay, restart, and finality

An exact retry first reconciles the previously committed transition. It returns
the same receipt even after restart, grant revocation, or domain seal. A
different request under a used transition ID is a conflict.

Rehydration accepts canonical portable request data plus an exact
`AuthorityDomainV2` and `GovernanceStateReaderV2`. It reconstructs no authority
from the payload; it reloads and verifies Store inclusion. Missing history,
unreliable finality, altered state, altered Trace, altered inclusion, or altered
position fails closed with a typed authority diagnostic.

After domain retirement:

- historical exact retries remain verifiable;
- new Verification, Membership, or Support transitions are denied with
  `GOVERNANCE_DOMAIN_SEALED`.

## Canonical and resource rules

Wire readers require exact dictionaries and lists, exact scalar types, complete
fields, canonical UTF-8 ordering, and supplied derived roots. Empty/self-healed
roots, tuples in JSON arrays, booleans in integer fields, duplicate identities,
reordered canonical arrays, cycles, and over-limit collections are rejected
before Store I/O.

Public bounds include text bytes, aggregate resource depth/nodes/text bytes,
Verification/Membership counts and snapshot bytes, Support observations,
Trace roots, leases, evictions, reason codes, and snapshot bytes. These bounds
are ABI constants exported from `pheroos.governance.support_v2`.

## Conformance

Run the public-only matrix against any StateStore v2 conformance adapter:

```python
from pheroos.conformance.checks.support_v2_contract import (
    run_governance_support_conformance_v2,
)

result = run_governance_support_conformance_v2(adapter)
assert result.ok, result.detail
```

The active matrix runs unchanged against the reference Store and the independent
stdlib Store. It covers the complete authority chain, initialize/issue/revoke/
switch, restart, rehydration, lost-response exact retry, stale parent and
Membership heads, issuer rotation, canonical/resource rejection, malicious
reader tampering, unavailable finality, seal behavior, and 32-worker identical
and conflicting races. The matrix imports no private Governance owner and uses
no adapter mutation/observation hook.

The deterministic example is `examples/support-v2-protocol`.

## Legacy boundary

The Draft facade imports no legacy `pheroos.governance.support` or
`pheroos.governance._support` owner. It exposes no v1-to-v2 authority projection
and no registry/sentinel compatibility lane. Existing v1 consumers must remain
on their declared ABI until they explicitly migrate to the complete v2 chain.
