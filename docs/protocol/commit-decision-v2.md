# Commit Decision v2 ABI

Status: **Draft direct-module ABI; not aggregate-activated or Stable**

Commit Decision v2 replaces process-local Commit window, seal, liveness, and
terminal authority with one StateStore-backed lineage. It consumes current
Commit Replay v2, Risk v2, Membership v2, Support v2, COMMIT Stop v2, and
COMMIT Permission v2 state. It does not add a clock, scheduler, worker, model
provider, database, server, or workflow engine.

The Draft direct facade is `pheroos.governance.commit_decision_v2`. Aggregate
activation and Stable promotion remain gated on the shared Decision +
Certificate + Distributed finality journey and composite TCK. A partial
dataclass surface is not a valid fallback implementation.

## 1. One fixed decision stream

One scoped protocol/run/target has exactly one decision lineage:

```text
material = UTF8(scope_ref) || 0x00 || UTF8(protocol_ref) || 0x00 ||
           UTF8(run_ref)   || 0x00 || UTF8(target_ref)

stream_ref = "authority:commit-decision-v2:" ||
             lowercase_hex(SHA-256(material))

transition_id = "transition:commit-decision-v2:" ||
                lowercase_hex(SHA-256(UTF8(stream_ref) || 0x00 ||
                                      UTF8(mutation_ref)))
```

The selector excludes epoch, issuer, grant, profile, assurance, manifest and
policy roots, mutable dependency heads, candidate, and leader. Changes to
those values are explicit successors or resets on the same linear history;
they MUST NOT create parallel current decision heads.

Every text component rejects U+0000 and is bounded by 4,096 UTF-8 bytes.
Exact version dispatch, exact object fields, canonical UTF-8 ordering,
bool-as-integer rejection, bounded graph depth/nodes/text, and complete
canonical roots apply to every portable record.

## 2. Data and authority

Portable requests, snapshots, assessments, progress, outcomes, roots,
receipts, Trace events, JSON, and pickles are data. They are not authority.

`VerifiedCommitDecisionSourceV2` is a final, non-portable proof that Governance
derived one complete replacement from exact current upstream state. It cannot
be directly constructed or serialized. Its private token alone grants no
authority: commit independently rebuilds the replacement, reloads every
dependency head, and binds the grant and lifecycle in the atomic read-set.
Same-shaped objects, copied payloads, and exact-class objects carrying a forged
token fail closed before any write.

The authority-neutral contracts have their canonical public identity in
`pheroos.governance.commit_finality_v2`. The Decision facade retains its eight
former finality names as exact compatibility aliases, but it does not rewrite
their module identity. Certificate and Distributed reference the same neutral
type without importing the Decision facade.

`VerifiedCommitFinalityInputV2` is the authority-neutral, non-portable bridge
from a finality owner to Decision. Certificate and Distributed owners may issue
it only after proving their own current Store position, receipt, and inclusion.
Decision consumes only this opaque handle, then copies its portable projection
into the request and binds the handle anchor in the source-context root. A raw
projection, dictionary, or same-shaped object is never finality authority.

Omitting that handle does not mean the finality owner is absent. For certified
or distributed assurance, Decision reads the canonical owner stream from the
same StateReader as its parent and binds the current owner head in its CAS. A
non-genesis observation is verified through the exact current generic commit
view and contributes only its receipt, head, transition, revision, and the
top-level/nested-consistent `snapshot_root`. Decision does not decode owner
status, issue a projection, or turn stored bytes into finality authority.

`VerifiedCommitDecisionStateV2` is issued only after StateStore proves exact
committed inclusion and position. A historical wrapper may remain verifiable,
but only a dynamically `current` wrapper may parent another mutation.

Write authority requires an exact request-bound `EVALUATE_QUORUM` authority
session, current issuer grant, open domain lifecycle, complete current-head
read-set, and one successful atomic StateStore commit. Reconciliation of an
exact prior transition always occurs before grant, lifecycle, source, or
currentness rejection.

## 3. Dependency records and read-set

`CommitDecisionDependencyV2` binds:

- role;
- stream reference;
- revision;
- transition id;
- snapshot root;
- head root;
- receipt root; and
- observed position.

Roles are exact and unique. The dependency set is sorted by role and rooted as
one closed projection, preventing Risk, Membership, Support, Replay, Stop,
Permission, or finality roots from being substituted for each other. An
uninitialized dependency uses its declared canonical genesis transition and
root; empty strings never mean “not read.”

Ordinary assess, reset, seal, heartbeat, finalize, and deadline mutations bind
the current heads of:

1. the decision parent;
2. Commit Replay v2;
3. Risk v2;
4. Membership v2;
5. Principal Verification v2;
6. Support v2;
7. Commit Evidence v2;
8. COMMIT Stop v2;
9. COMMIT Permission v2;
10. the assurance-required certificate/distributed owner head, whether or not
    an opaque finality handle was consumed;
11. the issuer grant; and
12. the domain lifecycle.

Initialization binds only decision genesis, grant, and lifecycle. This lets a
run establish absolute deadlines before evidence dependencies exist. Every
later missing-input heartbeat discovers all eight upstream owner streams from
the parent-bound Store: each committed head is rehydrated through its exact
owner verifier and each absent head is bound to its canonical genesis. Thus
any causally valid partial upstream combination produces durable progress or a
deadline outcome with one complete CAS read-set; it never assumes that all
upstreams are simultaneously genesis. The progress record names the exact
roles still missing.

Membership and Support prove historical transitive verification lineage, but
that history alone cannot prove that Principal Verification remains current at
the Decision CAS. Decision therefore binds the one current Principal
Verification stream returned by the verified Evidence owner. Replay and
Membership preconditions returned by that owner must exactly equal Decision's
independently loaded heads; they are de-duplicated, never caller supplied.
Other transitive internal streams remain outside the read-set.

For a genesis finality owner, Decision binds the byte-identical canonical owner
genesis snapshot root. For a non-genesis owner without a verified finality
handle, Decision loads the exact current commit view, cross-checks
view/position/receipt/head identity, and extracts only the restricted generic
`snapshot_root`. Corrupt, cross-stream, stale, or unavailable owner views fail
typed validation. A concurrent owner successor invalidates the prepared
Decision read-set and returns `retry_required`; it cannot be silently ignored.

## 4. Complete replacement snapshot

`CommitDecisionSnapshotV2` contains all truth needed after restart:

- domain, scope, protocol, run, target, profile, assurance, manifest, policy,
  epoch, stream, mutation, transition, revision, and exact parent lineage;
- initialization step, current logical step, absolute evidence deadline, and
  absolute finality deadline;
- rolling decision-history root and count;
- exact dependency projections and dependency-set root;
- optional current assessment;
- current stability window;
- optional frozen window seal;
- exactly one current non-terminal progress or terminal outcome;
- source-context root; and
- state and snapshot roots.

Every successor is a full replacement. Terminal state is sticky: no valid
transition can return from a terminal outcome to progress, assessment, reset,
seal, or another terminal kind.

### 4.1 Assessment projection

The assessment stores deterministic candidate metrics, leader/ties, all gate
results, blocker/equivocation/replay-conflict references, reason codes,
evaluation context, dependency set, evidence/challenge/claim/lease roots, and
whether the candidate is ready for stability. Callers cannot supply `ready`, a
terminal kind, or reason classification.

### 4.2 Stability window

The window stores required stability steps, streak count/start, leader, last
readiness and assessment root, rolling streak/history roots, reset reason, and
remaining reset/restart budgets. It does not carry an unbounded assessment
array; StateStore transition history owns the complete audit trail.

Within one uninterrupted epoch, the required stability threshold cannot
decrease. A formal policy change or epoch restart resets the window and uses
the maximum of the current protocol minimum and current Risk v2 threshold. A
hidden maximum from an earlier epoch is not carried forever unless a future
Protocol ABI explicitly declares that rule.

Window continuity is semantic rather than “every dependency root is frozen.”
Risk, Membership, Principal Verification, leader identity, claim identity, and
logical step continuity are hard boundaries. Append-only Evidence, Replay,
Support, Stop, and Permission advances may preserve a streak only after the
new assessment proves the same leader and claim, current clear gates, and no
conflict or equivocation. A step gap, claim substitution, hard dependency
change, or readiness loss resets the window. Reset exhaustion is sticky: using
the last remaining reset changes the counter to zero; the next required reset
marks exhaustion and no later ready assessment silently clears it.

### 4.3 Window seal

The seal freezes the parent transition and snapshot, window and dependency
roots, seal step, leader/candidate, claim, output contract, and output payload.
It does not include the receipt for its own transition, which would create a
hash cycle. A later finalization verifies the seal transition receipt from
committed StateStore history.

Sealing is a same-logical-step transition from the stable parent and re-runs
the assessment and every gate at that exact step. A future-step seal request,
expired gate, changed hard dependency, or different leader resets rather than
reusing stale readiness. Certified/distributed heartbeats may advance the
Decision head after sealing; finality still binds the historical transition
that actually created the seal, not a later heartbeat transition.

### 4.4 Progress and outcome

Progress records phase, step, deadlines, assessment/window/seal/dependency
roots, heartbeat lineage, budgets, leader/streak, next required inputs, and
unmet gates. It is explicitly non-terminal.

An outcome records exact kind, candidate/claim/output/finality bindings,
epistemic commitment, delivery eligibility, reason codes, step/deadlines, and
the frozen window/seal/dependency roots. Publication and execution eligibility
remain false here; separate output authorization owns those actions.

## 5. Commands and derived mutations

A portable request carries command intent only:

- `initialize`;
- `evaluate`;
- `seal`;
- `explicit_unseal`; or
- `epoch_restart`.

It may carry logical step, declared candidate/evidence proposals, proposed
output, and a portable finality projection copied from an opaque verified
finality input. Callers cannot submit a raw projection through the preparation
path. The request cannot carry a derived mutation
kind, authoritative assessment, window count, readiness, progress, outcome,
or reason priority.

The pure reducer derives one of:

- `initialized`;
- `assessed`;
- `window_reset`;
- `epoch_restarted`;
- `sealed`;
- `heartbeat`;
- `finalized`; or
- `deadline_terminated`.

Every operation follows the same order:

1. decode exact canonical request;
2. reconcile the exact transition;
3. validate the current grant;
4. validate domain lifecycle;
5. load and verify the parent;
6. load current dependency heads;
7. verify source and complete replacement semantics;
8. independently rebuild read-set and Trace;
9. make one atomic commit; and
10. reconstruct the result and verified handle from the committed view.

Issuer rotation does not change stream identity. Each transition binds its own
issuer/grant/session. A revoked issuer cannot make a new successor, while its
already committed exact retry remains recoverable after revocation or domain
seal.

An epoch restart is the only transition that may change `epoch`. Its request
must observe the current parent epoch and declare exactly `parent.epoch + 1`.
Rollback, reuse, skipping, bool-as-integer, and restart beyond the canonical
maximum are rejected both by the request contract and again by the reducer.
The restart budget is durable and decremented only by the committed successor.

## 6. Total liveness

Terminal priority is fixed:

```text
INVALID
> SAFETY_VIOLATION
> BLOCKED
> EVIDENCE_COMMIT
> FINALITY_UNAVAILABLE
> declared SAFE_FALLBACK or ADVISORY
```

The deadline path reads current dependency heads. It does not require them to
equal a prior assessment. A legal upstream successor is re-evaluated; only
rollback, cross-selector substitution, corrupt committed state, or an
impossible fork is invalid/safety failure.

At or after the applicable deadline, a valid evaluation MUST return a terminal
outcome or a typed non-authoritative finality diagnostic. It MUST NOT return
progress. CAS loss may return `retry_required`, but carries no progress; the
winner’s terminal state is then observed and reconciled.

Rules:

- evidence-bound finality is same-step only;
- certified/distributed finality may arrive later only through exact `+1`
  heartbeats bound to the same seal and frozen dependencies;
- finality at the deadline is too late for evidence commit;
- any frozen dependency or gate change invalidates the old seal;
- an unresolved/expired Stop or Permission gate is progress before deadline
  and `BLOCKED` at deadline;
- missing Replay/Risk/Membership/Support before deadline is progress and at
  deadline becomes the manifest-declared safe fallback/advisory;
- a stable sealed decision with unavailable required proof becomes
  `FINALITY_UNAVAILABLE` at deadline; an observed owner without its opaque
  verified handle uses the explicit
  `finality:verified_owner_handle_missing_at_deadline` reason and can never
  become `EVIDENCE_COMMIT`; and
- a domain sealed before any terminal commit yields a non-authoritative
  `FINALITY_UNAVAILABLE/governance_domain_sealed` diagnostic, never a forged
  committed fallback.

Logical `current_step` is a runtime claim until the exact mutation commits. The
core does not schedule or poll. Ordinary crash recovery may skip steps;
late-finality heartbeats alone require exact `+1` continuity.

Initialization deadlines use explicit saturating canonical addition:

```text
deadline = min(MAX_AUTHORITY_REVISION_V2, current_step + positive_distance)
```

This makes `near-MAX + MAX` deterministic without constructing an out-of-range
snapshot. Initialization at the terminal maximum has no representable future
deadline and is rejected explicitly before source issuance. Bool and invalid
policy distances are rejected before reducer state construction. Saturation
does not permit progress at or beyond a committed deadline.

## 7. Trace and Conformance

Successful transitions atomically emit only the events applicable to their
derived mutation:

- `commit_decision_initialized_v2`;
- `commit_assessment_evaluated_v2`;
- `commit_window_advanced_v2`;
- `commit_window_reset_v2`;
- `commit_epoch_restarted_v2`;
- `commit_window_sealed_v2`;
- `commit_decision_progressed_v2`; and
- `commit_decision_outcome_committed_v2`.

Each event binds scope/stream/transition/request, revision/parent, issuer/grant
session, read-set, source context, dependency set, current step/deadlines, and
the applicable assessment/window/seal/progress/outcome roots. Trace validation
independently re-derives identities and roots. Trace explains a StateStore
commit; it cannot create authority.

The public Decision Conformance matrix runs unchanged against the reference
Store and an independent stdlib adapter. Its real durable journeys cover
initialization, bounded missing-input progress, deadline safe fallback, closed
ready assessment, stability, same-step seal, evidence-bound terminal commit,
restart rehydration, lost-response exact retry, parent CAS races, and atomic
Trace lineage. Production Conformance imports only public Governance facades;
it never imports tests or private Governance implementations.

`examples/commit-decision-v2-protocol` executes both Store implementations with
no provider, API key, network, database, worker, or app runtime. Aggregate
activation additionally requires the shared Certificate/Distributed finality
wrapper and composite three-owner race/TCK; the Decision-only matrix does not
claim those external-owner guarantees by itself.

## 8. Legacy exit

The v2 owner MUST NOT import or consult process-local Commit window/replay,
context, assessment, permission, stop, liveness, certificate, or receipt
issuance registries, sentinels, cursors, locks, or singleton maps. Shared pure
scoring may be migrated only after all authority inputs are reconstructed from
the v2 verified owners.

Internal consumers, examples, and TCK move to v2 before Stable promotion. The
legacy Draft facade may remain only under an explicit compatibility window;
the Stable/production path has no fallback to it.
