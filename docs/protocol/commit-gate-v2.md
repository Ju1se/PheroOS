# Commit Gate v2 ABI

Commit Gate v2 is the durable authority boundary for the two facts immediately
upstream of a commit operation:

- whether a commit is stopped; and
- whether the `commit` action is permitted for the declared candidate set.

It does not select a candidate, evaluate a collective decision, create
evidence, or publish output. Commit Decision remains a separate authority
owner. This separation lets a runtime replace decision algorithms without
changing the final gate ledgers.

## Fixed ledgers

Each scoped run target has two independent append-only streams:

```text
authority:commit-stop-v2:<sha256(selector)>
authority:commit-permission-v2:<sha256(selector)>
```

The selector material is exactly:

```text
scope_ref, protocol_ref, run_ref, target_ref, "commit"
```

It deliberately excludes epoch, issuer, profile, policy root, candidate set,
grant head, lifecycle head, and every other mutable value. Stop and Permission
use different stream namespaces, so one can advance without rewriting or
serializing behind the other.

Transition identity is derived from the fixed stream plus `resolution_ref` for
Stop or `permission_ref` for Permission. Reusing a transition identity with a
different body is a conflict; retrying the exact body reconciles to the original
receipt.

## Portable contracts

The public surface is `pheroos.governance.commit_gate_v2`.

Portable values are:

- `CommitGateDependenciesV2`
- `CommitStopSnapshotV2` and `CommitStopRequestV2`
- `CommitPermissionSnapshotV2` and `CommitPermissionRequestV2`

They round-trip through canonical JSON-shaped dictionaries. Every supplied
derived root must equal the locally recomputed value; an alternative valid
SHA-256 string is not accepted merely because it has the right shape.

### Dependency commitment

Both snapshots commit to the same five current durable authority heads:

1. Commit Replay v2
2. Risk v2
3. Principal Verification v2
4. Membership v2
5. Support v2

Principal Verification is explicit even though Membership also binds the
verification snapshot. This closes the prepare-to-commit interval: a new
verification-set head cannot make the transitive Membership authority stale
while a Gate mutation still commits against the old head.

For each dependency the snapshot records its fixed stream, revision,
transition, snapshot root, and current head root. `dependency_root` binds the
complete set. The common evaluation context additionally binds domain, scope,
exact manifest, commit policy, profile, assurance, protocol, run, target,
observed epoch, current step, and dependency root.

Callers do not supply expected head roots or cursors. Preparation extracts them
from current non-portable state handles and commit reloads them from the
authority session's Store.

A dependency may have been issued in an earlier authority epoch than the Gate
mutation. Equality is intentionally not required: the Store head and atomic
read precondition establish currentness, while a future-issued dependency is
rejected. This permits long-lived current authority without weakening CAS.

### Stop snapshot

A Stop snapshot records:

- exact policy and evaluation context roots;
- contiguous parent lineage;
- mutation issuer;
- an exact `blocked` boolean;
- canonical reason codes and `reason_root`; and
- issue and expiry steps.

A blocked resolution requires at least one reason. An unblocked resolution may
carry canonical explanatory reasons. A current Stop blocks only during
`issued_at_step <= current_step < expires_at_step`.

### Permission snapshot

A Permission snapshot records:

- exact policy and evaluation context roots;
- contiguous parent lineage;
- mutation issuer;
- an exact `allowed` boolean;
- the complete canonical candidate set declared for the target;
- canonical claim roots; and
- issue and expiry steps.

An allowed Permission requires at least one claim root. A denied Permission may
have no claims. A current Permission allows only a candidate present in its
committed candidate set and only during
`issued_at_step <= current_step < expires_at_step`.

## Non-portable authority

Preparation returns an opaque source handle together with the portable request.
The source binds:

- the exact `ScopedProtocolManifestV2`;
- the exact request and evaluation context;
- the five durable dependency preconditions; and
- a source context root.

Source and verified-state handles cannot be directly constructed, serialized,
or forged into authority. Verified state is reloaded from an exact committed
view and rechecks the receipt, inclusion proof, position observation, read set,
Trace event, stored request, source context, and every historical parent.

Copying a verified state returns the same Store-anchored local handle; it does
not create a portable authority token. Currentness is checked against the Store
on each use.

Here, Gate currentness means that the Stop or Permission record is the current
head of its own fixed ledger. Its dependency read set proves a coherent
issuance snapshot; it is not a perpetual lease on unchanged upstream state.
Commit Decision therefore rechecks and atomically binds the then-current Risk,
Membership, Principal Verification, Evidence, Support, Replay, Stop, and
Permission heads before it can commit. The convenience Gate predicates are not
standalone output or publication authority.

## Authority sessions and mutation

Stop requires `GovernanceIssuerOperationV2.RESOLVE_STOP` and no action scope.
Permission requires `GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION` with
the sole action reference `commit`. Both require the target scope and require
the request's mutation issuer to equal the grant issuer.

After exact-retry reconciliation, every new mutation verifies the current grant
and domain lifecycle. This ordering preserves lost-response recovery after a
grant is revoked or a domain is sealed, while denying any previously
unpublished write.

The atomic read set has exactly eight streams:

1. the gate's own parent head;
2. Commit Replay v2;
3. Risk v2;
4. Principal Verification v2;
5. Membership v2;
6. Support v2;
7. the current issuer-grant head; and
8. the domain lifecycle head.

Any changed dependency or parent makes the operation retry-required. The Store
publishes the new head, state, receipt, inclusion proof, position, and one Trace
event as a single commit. There is no process-local issuance registry, mutable
cursor, singleton, or sentinel authority.

## Trace ABI

The two closed event types are:

- `commit_stop_resolved_v2`
- `commit_permission_issued_v2`

Trace validation is independently implemented under `pheroos.trace`; it does
not import Governance's root helpers or contracts. It recomputes fixed stream
and transition identity, dependency, policy, evaluation, decision, snapshot,
request, source-context, and eight-entry read-set roots. It also enforces exact
session bounds, issuer binding, profile/assurance compatibility, freshness,
canonical arrays, and closed lineage fields. It also recomputes the explicit
Principal Verification dependency and the eight-entry authority read set.

## Failure and concurrency semantics

- Exact retry returns the original committed receipt, including after restart,
  revocation, or seal.
- Same-transition/different-body input is invalid.
- Conflicting workers racing from one parent publish one successor; stale
  workers receive retry-required.
- Identical workers all reconcile to one receipt and one revision.
- A stale dependency produces retry-required without publishing a gate head.
- Missing finality or a malformed Store view fails closed.
- A sealed domain denies every new gate transition.

## Resource limits

Text is bounded by UTF-8 bytes, not character count. Counts must be exact
integers, so booleans are rejected. Candidate, claim, and reason collections are
bounded, unique, and UTF-8 sorted. Snapshot canonical bytes are bounded before
authority mutation. Noncanonical arrays, unknown fields, root substitution,
oversized Unicode values, and malformed nested wire objects fail before Store
write.

## Compatibility

Baseline protocols are not required to adopt Commit Gate v2. Existing v1 Stop
and Permission decision meaning is preserved (`blocked` and `allowed`), but v1
in-process issuance objects are never accepted as v2 authority. V2 authority is
established only through current StateStore-backed sessions, exact source
verification, atomic inclusion, and current committed state.
