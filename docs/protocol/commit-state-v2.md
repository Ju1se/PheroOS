# Commit Replay State v2

Status: public Draft ABI. This document describes the WP-05 durable replay
bookkeeping slice only. It is not a Stable or production-complete Commit
authority profile.

## Boundary

Commit Replay v2 records which declared replay identities have already been
processed for one exact target. It does not evaluate a commit window, make a
liveness decision, qualify evidence, issue support or membership authority, or
authorize output.

`prepare_commit_replay_advance_v2` accepts portable receipts and returns an
integrity-checked request plus a non-portable, context-bound source proof. That
preparation step does **not** verify the upstream evidence, principal,
membership, support, risk, or certificate authority represented by a receipt.
Only an exact `ADVANCE_REPLAY` session plus an atomic StateStore v2 commit
attests the replay bookkeeping transition itself. Upstream Store heads will be
added to the authority read-set by the later WP-05 authority migrations; until
then this Draft slice must not be described as Stable or production-complete.

## Public records

- `CommitReplayReceiptV2` is portable and binds namespace, record id, nonce,
  payload fingerprint, target, candidate, epoch, and principal. It is data, not
  authority.
- `CommitReplaySnapshotV2` is a complete replacement state. It binds the exact
  domain, scope, manifest, commit policy, profile, assurance, protocol, run,
  target, epoch, parent, step, and canonical receipt set.
- `CommitReplayAdvanceRequestV2` binds an idempotency reference to exactly one
  snapshot and transition id.
- `VerifiedCommitReplaySourceV2` is final and non-portable. It binds the exact
  request, parent, current step, and receipt additions. It uses exact local
  type, detached request, and recomputed binding checks; v2 has no registry,
  sentinel, cursor, lock, or mutable module-global authority state.
- `VerifiedCommitReplayStateV2` is final and non-portable. Every observation is
  reverified against the selected StateStore's historical committed view.

Portable snapshots, dictionaries, digests, raw v1 states, and same-shape
objects never satisfy either verified type.

## Canonical identity

One target owns one stream:

```text
authority:commit-replay-v2:
  sha256(scope_ref \0 protocol_ref \0 run_ref \0 target_ref)
```

One request owns one transition:

```text
transition:commit-replay-v2:
  sha256(stream_ref \0 advance_ref)
```

U+0000 is forbidden in each text component, so the delimiter is unambiguous.
The genesis snapshot uses the reserved parent transition id `genesis` and a
versioned genesis snapshot root. An explicit zero-receipt genesis transition is valid
and corresponds to v1 `initialize_commit_replay_state`; a non-genesis transition must add at least one new receipt.

Receipt ordering is by the versioned receipt root. Exact duplicates collapse.
Three collision axes fail closed when values differ:

1. nonce;
2. `(namespace, record_id)`;
3. payload fingerprint.

The v2 roots are intentionally versioned and are not equal to v1 fingerprints.
The replay meaning and three-axis collision result are differential invariants;
the hash domains are not.

## Authority operation

`advance_commit_replay_state_v2` performs this order:

1. validate the exact request and request-bound session;
2. reconcile the exact transition before checking current grant, lifecycle, or
   ephemeral source proof;
3. require the current `ADVANCE_REPLAY` grant for a new transition;
4. load a non-genesis parent with `load_commit_view_v2`, including finality and
   historical position;
5. verify immutable bindings, complete replacement, monotonic epoch/step, and
   append-only receipts;
6. verify the exact source proof against the Store-loaded parent;
7. atomically compare the replay, issuer-grant, and domain-lifecycle heads;
8. publish state and one canonical `commit_replay_advanced` Trace event in the
   same StateStore batch.

An exact retry returns the original receipt even after a grant is revoked, a
domain is sealed, or the first response is lost. The same transition id with
different bytes is a typed conflict. A legal child prepared from a parent that
has since been superseded receives a typed stale-read retry; it never forks the
stream. A historical committed parent may be used for structural verification,
but only the current head can win the atomic compare-and-swap.

## Read-set and Trace

Every committed transition has exactly three read preconditions at this Draft
stage:

- the target-scoped replay stream head;
- the exact issuer-grant stream head;
- the domain-lifecycle stream head.

`commit_replay_advanced` binds the session, manifest and policy roots,
profile/assurance, target, parent, snapshot, full receipt-set root, receipt
addition root, source-context root, parent head, and complete read-set root.
State and Trace are atomic; either both publish or neither publishes.

## Bounds

- at most 4,096 receipts per complete snapshot;
- at most 4,096 UTF-8 bytes per text field;
- at most 8 MiB for one canonical complete snapshot;
- JSON-safe non-negative integers only;
- exact arrays/tuples and exact public record types only.

Count bounds are checked before tuple conversion, sorting, copying, or hashing.
No database, provider, network, worker, or server implementation is part of
this ABI.

## Conformance

`pheroos-governance-commit-replay-conformance-v2` runs the same public-only
matrix against the reference StateStore and the independent stdlib Store. It
covers explicit empty genesis, child advancement, canonical read-set and Trace,
restart/rehydration, reconciliation/parent/rehydration finality, canonical
lost-response recovery, exact-retry conflict, and zero-write failure paths. It
also covers every replay/grant/lifecycle read-set omission and root/revision
substitution, extra/duplicate/reordered entries, Trace `read_set_root` tamper,
State/request/receipt/Trace substitution or deletion, cross-context session and
source rejection, raw/digest/pickle/v1-object rejection, 32-way exact-request
and two-fork races, superseded/current state observations, and the exact/+1
receipt-count, UTF-8 text, and 8 MiB snapshot bounds including receipt-byte
preflight.

The adversarial checks use a delegating consumer-side Store proxy over the
public StateStore v2 surface. The proxy may withhold or alter a detached public
view, or deliberately lose one returned response; it does not use Conformance
adapter tamper/observation hooks, inspect a persistence image, or mutate the
underlying Store. The matrix checks declared bindings and fail-closed Store
outcomes; it does not copy an application evaluator or infer upstream evidence
authority from a replay receipt.

Stable promotion remains blocked until the later WP-05 upstream authority
heads and consumers are migrated and the complete project acceptance gates
pass.

## Legacy-exit status

The namespace vocabulary now lives in a dependency-leaf module shared by the
v1 compatibility owner and v2. The unreleased intermediate helper
`commit_replay_receipt_v2_from_v1` and the v1 issuance-token
dependency have been removed from the v2 public and owner surfaces. Callers construct explicit
portable `CommitReplayReceiptV2` data; authority is acquired only through the
StateStore-backed v2 path. Static source checks therefore show no
`_commit_state` or legacy-registry dependency inside `_commit_state_v2`.

This clears the Commit Replay bookkeeping slice's direct legacy dependency; it
does not make the full Commit authority production-complete. Upstream durable
membership, support, risk, window/liveness, certificate, and distributed heads
must still enter their owning v2 paths and read sets before Stable promotion.
