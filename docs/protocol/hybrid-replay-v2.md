# Hybrid Replay v2 ABI

Status: **Draft WP-05 implementation contract; not Stable**

Hybrid Replay v2 makes Hybrid pheromone memory restart-safe without making a
portable object authoritative. It composes the existing scoped
[Authority Session v2](authority-session-v2.md), atomic
[StateStore v2](authority-store-v2.md), and canonical Trace ABI. The portable
wire and `hybrid_replay_advanced` Trace vocabulary are implemented as part of
WP-05. Its public facade and reference/independent StateStore Conformance
matrix are active Draft surfaces; this document does not claim Stable
promotion or a production database adapter.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, and **MAY** are
normative for this Draft slice.

## 1. Boundary and versions

The exact version identifiers are:

```text
snapshot schema   = pheroos-governance-hybrid-replay-snapshot-v2
request schema    = pheroos-governance-hybrid-replay-advance-request-v2
state schema      = pheroos-governance-hybrid-replay-state-v2
canonical version = pheroos-authority-canonical-v2
numeric wire      = pheroos-binary64-hex-v1
session operation = advance_replay
Trace event        = hybrid_replay_advanced
```

Exact version dispatch is fail-closed. Aliases, version ranges, unknown
fields, missing fields, implicit coercion, and v1 payload reinterpretation are
not accepted.

This ABI owns durable replay contracts and authority checks. It does not add a
model provider, agent colony, worker, server, queue, database, migration
system, or environment simulator. A runtime supplies a provider-neutral
`GovernanceStateStoreV2` adapter; protocol-core supplies only contracts and a
deterministic in-memory reference.

## 2. Data is not authority

`HybridReplaySnapshotV2` is a closed, immutable portable projection. Successful
construction or strict `from_dict()` proves only that its shape, bindings,
canonical encodings, and roots are internally consistent.

`HybridReplayAdvanceRequestV2` binds one fully prepared next snapshot to the
same domain, scope, run, target, epoch, stream, advance reference, and
transition identity. It is an idempotency input, not permission to commit.

`VerifiedHybridSourceStepV2` is a local, non-portable evaluation proof. It is
issued only by `evaluate_hybrid_collective_step_v2(...)`, which accepts the
exact `domain_root`, `scope_ref`, `run_ref`, and `observed_epoch` of this
evaluation, one exact `ScopedProtocolManifestV2`, one exact declared topology,
deterministic Hybrid inputs, and either genesis or a Store-current
`VerifiedHybridReplayStateV2`. The proof binds all four authority-context
fields plus the manifest root, protocol, target, candidate set, manifest base
policy, actual input policy, topology, current step, committed parent snapshot
(or genesis), source step, and one canonical context root. Callers cannot
replace any of those bindings while building the advance request.

The source proof is a single-call carrier rather than durable authority. It
cannot be directly constructed, serialized, pickled, copied into a portable
credential, or used as a replay parent. Before a new commit, Governance
requires the request builder's domain, scope, run, and epoch to match the proof
exactly. The advance boundary repeats that comparison while reconstructing the
request from the proof, then compares its parent with the exact historical
parent loaded from StateStore. A proof evaluated for one authority context
cannot be re-stamped into another context even when the caller separately holds
a valid capability there. StateStore inclusion and the atomic read-set remain
the authority source; the source proof still grants no write authority.

`VerifiedHybridReplayStateV2` is a local opaque result. Governance may issue it
only after the selected Store proves the exact transition's committed
inclusion and returns a position observation. Its authority is therefore the
combination of the selected Store, exact domain/scope bindings, committed
history, and observed position—not the Python object shape.

A verified wrapper may represent a `current`, `superseded`, or `sealed`
historical transition. Only `current` conveys parent currentness for another
advance, and every advance MUST recheck that currentness atomically. A
`superseded` or `sealed` wrapper remains useful for audit and recovery but MUST
NOT authorize a child transition.

Raw JSON, a pickle, a copied dataclass, a receipt string, a root digest, a
Trace event, or a same-shaped object has no replay authority. Serialization of
a snapshot preserves data only; restart requires Store-backed rehydration.

The authoritative evaluation-to-commit path is:

```text
exact domain/scope/run/epoch + scoped manifest + topology + deterministic inputs
  -> evaluate_hybrid_collective_step_v2
  -> context-bound, non-portable VerifiedHybridSourceStepV2
  -> exact-context HybridReplayAdvanceRequestV2
  -> run/request-bound ADVANCE_REPLAY session
  -> exact-context rebuild + Store parent/source/read-set verification
  -> atomic state + Trace commit
```

## 3. Scope, stream, and transition identity

One scope/protocol/run/target tuple has exactly one replay stream:

```text
stream_payload = UTF8(scope_ref) || 0x00 || UTF8(protocol_ref) || 0x00 ||
                 UTF8(run_ref)   || 0x00 || UTF8(target_ref)
stream_ref     = "authority:hybrid-replay-v2:" ||
                 lowercase_hex(SHA-256(stream_payload))
```

The tuple prevents cross-scope, cross-protocol, cross-run, and cross-target
substitution. `run_ref` does not replace scope isolation: the capability and
session remain bound to the exact scope and run.

Every text component used by this encoding MUST reject U+0000. This makes the
NUL separator unambiguous; accepting an embedded separator would allow two
different tuples to derive the same stream or transition identity. Runtime
contracts, JSON Schema, and Trace validation apply the same prohibition.

One advance reference has exactly one transition identity in that stream:

```text
transition_payload = UTF8(stream_ref) || 0x00 || UTF8(advance_ref)
transition_id      = "transition:hybrid-replay-v2:" ||
                     lowercase_hex(SHA-256(transition_payload))
```

The identity does not depend on request-root accidents. An exact retry uses the
same transition id and byte-identical batch. Reusing it with different bytes or
roots is substitution and returns
`invalid/governance_transition_conflict`.

StateStore v2 retains its hard limit of 127 non-lifecycle streams per scope;
the reserved lifecycle stream is excluded. A Hybrid stream consumes one of
those entries, as do grant and other authority streams. A deployment SHOULD
use a run-bounded scope (one run or an explicitly finite run cohort), budget
all declared streams before starting it, and allocate a new scope rather than
reuse an unbounded tenant scope. Hybrid Replay v2 MUST NOT raise or bypass the
127-stream ABI constant.

## 4. Canonical numeric wire

Every binary64 leaf is finite canonical hexadecimal text under
`pheroos-binary64-hex-v1`:

```text
encode = exact_python_float.hex()
decode = float.fromhex(text), accepted only when decode.hex() == text
```

The encoder accepts an exact `float`, not an integer, Boolean, subclass, or
coercible value. The decoder rejects whitespace, aliases, decimal spellings,
case variants, `NaN`, and infinities. Signed zero remains distinct. Raw JSON
numbers MUST NOT stand in for binary64 text. This rule applies to policy,
trail strength, diffusion, feedback, overlay, and budget values before their
canonical roots are computed.

## 5. Complete snapshot truth

The snapshot binds all state required to continue one Hybrid run:

- domain, scope, manifest, protocol, run, target, epoch, stream, advance, and
  transition identity;
- revision, current step, and exact parent revision/transition/snapshot root;
- declared candidate set and safe fallback, full Hybrid policy, and declared
  subject topology;
- active pheromone trails with candidate/subject/target, provenance, Trace,
  TTL, and diffusion lineage;
- replay receipts, last-round budget, cumulative policy overlay, reconstructed
  effective policy, and source step/Trace lineage; and
- individual component roots, `state_root`, and `snapshot_root`.

Collections are bounded, duplicate-free, and canonically ordered. The active
trail projection is the durable active memory after the step; it is not
evidence, quorum, permission, or commit authority.

Resource limits are aggregate, not only per item. A snapshot is rejected
before expensive freezing or hashing when its portable graph is cyclic,
deeper than 64 containers, larger than 262,144 visited nodes, or carries more
than 12 MiB of UTF-8 text. A canonical snapshot is capped at 16 MiB. Each
diffusion causal payload is capped at 256 KiB, all causal payloads together at
8 MiB, and all trail lineage text together at 4 MiB. Topology subjects and
edges are indexed once per snapshot validation; receipt validation MUST NOT
perform a full topology scan for every receipt. These limits are wire
invariants and fail closed rather than truncating memory or lineage.

The public Draft Conformance resource subcheck uses the real limits above and
the public `HybridReplaySnapshotV2` constructor; it does not reduce private
constants. Exact depth, node, aggregate-text, and aggregate-lineage vectors
intentionally include one unknown closed-shape field, so their assertion is
precise: resource preflight accepts the exact boundary and ordinary shape
validation rejects later. The exact 8 MiB causal vector reaches causal JSON
validation, while the one-byte-over vector fails aggregate causal preflight.
The exact 16 MiB vector is a fully valid canonical snapshot; the otherwise
identical one-byte-over snapshot is rejected. Every rejection leaves the
public Store head unchanged and performs no atomic commit. The single topology
index assertion remains a Governance implementation gate because index-build
count is not observable through the public ABI.

Replay receipts have exactly four kinds:

| Kind | Durable meaning |
| --- | --- |
| `deposit` | One provenance- and Trace-bound deposited trail was processed. |
| `diffusion` | One derived trail, edge attenuation, hop, and parent/root event lineage was processed. |
| `feedback` | One subject/candidate outcome and bounded reinforcement delta was processed. |
| `adjustment` | One non-reactive layer proposal within declared policy-adjustment bounds was processed. |

Receipt event ids are unique across all four kinds, ordered by `(kind,
event_id)`, and each exact payload has its own root. The receipts are the
durable processed-id source; an external set or sentinel cannot override them.

The child overlay is the cumulative effective adjustment map for the run. It
contains one canonical value per adjusted field plus canonical source and
Trace lineage accumulated through the parent. Its values MUST stay within the
declared adjustment bounds. `effective_policy_projection` MUST reconstruct
exactly by applying that overlay to `policy_projection`; it is not a second
independent policy truth. Overlay Trace roots MUST be present in the snapshot's
source Trace set.

`last_budget` binds round and per-source caps from the effective policy and the
latest round's exact usage. Per-source usage must reconstruct `round_used` and
remain within both caps. Its root and the source-step/source-Trace roots retain
the budget's causal lineage across restart.

## 6. Parent, stale, and fork semantics

Revision advances by exactly one. Snapshot genesis uses parent revision `0`,
parent transition `genesis`, and the exact Hybrid genesis snapshot root. For a
non-genesis child, the declared parent transition and snapshot root MUST match
the committed parent state at the preceding revision. The Trace projection
uses `null` parent fields at revision 1 and exact parent roots thereafter.

An advance is authorized with one complete canonical read-set containing:

1. the replay stream's current parent revision and head root;
2. the session's captured issuer-grant revision and head root; and
3. the session's captured `authority:domain-lifecycle` revision and head root.

The session is exact-store-, domain-, scope-, run-, request-, operation-, and
target-bound. Its operation is `advance_replay`, its sole target bound is the
snapshot target, it has no action bound, and `request_ref` equals
`advance_ref`. No preflight read, wrapper flag, or embedded grant root may
replace the three atomic preconditions.

StateStore reconciliation occurs before current-parent, grant-revocation, or
domain-seal rejection. Consequently, an exact committed retry returns the
original commit with a fresh position observation even after a successor,
revocation, or seal.

The recovery read path does not require the already-consumed, non-portable
source proof after StateStore has proved an exact committed request and
session binding. `advance_hybrid_replay_state_v2(..., source=None)` is valid
only for that reconciliation result and performs no new mutation. If no exact
commit exists, an exact `VerifiedHybridSourceStepV2` remains mandatory; `None`,
a raw v1 step, or a same-shaped object is rejected before any write.

The public adapter matrix injects unavailable reads and a lost response only
through a delegating `GovernanceStateStoreV2` proxy. It proves reconciliation,
historical-parent, and rehydration `finality_unavailable`; a published commit
whose response was lost is recovered by an exact retry without a second
atomic commit. Recovery compares the complete canonical committed transition,
not only its receipt root. Reusing the transition id with different canonical
content remains a conflict. Historical replay-state, grant, and lifecycle read-set
entries are each tested for missing, revision-substituted, and root-substituted
forms, plus an extra entry and a tampered Trace `read_set_root`; all fail
closed during Store-backed reconstruction.

If no identical commit exists:

- a legitimate parent that became historical in a race returns
  `retry_required/governance_read_set_stale`, with no partial publication;
- two concurrent children cannot fork: one may commit and the losing valid
  read-set is stale;
- rollback, a parent not present in committed lineage, cross-binding, root
  tampering, or structurally inconsistent lineage is `invalid`; and
- the same transition id with a different canonical batch is
  `invalid/governance_transition_conflict`, never a retry.

`observed_epoch` is a monotonic logical clock inside one immutable replay run.
It may advance by more than one and MUST NOT move backward. Manifest,
candidate, base-policy, topology, protocol, target, and stream bindings cannot
change under an epoch increment; changing any of them requires a new run and
therefore a new replay stream. Epoch is not an implicit configuration
activation mechanism. Each source evaluation binds the exact new observed
epoch; a later builder or advance cannot silently re-stamp that proof with a
different epoch.

## 7. Rehydration and restart

Rehydration MUST follow this order:

1. strict snapshot/request schema, version, field, numeric, and root checks;
2. exact domain/scope/protocol/run/target/stream/transition binding checks;
3. `load_commit_view_v2(...)` for the declared transition;
4. committed inclusion and dynamic position verification;
5. extraction of the historical snapshot from
   `committed_transition.batch.transition.state_records`;
6. exact request/snapshot/root and session-binding comparison; and
7. issuance of a fresh local verified wrapper carrying that observed position.

`load_state_v2()` is forbidden for step 5: it returns current stream state and
would silently substitute a legal successor for the requested historical
transition. Historical state records are the only restart source for the
declared transition. The wrapper itself is never persisted as authority.

Before a next advance, Governance again loads/verifies the wrapper's exact
commit view and requires `current`. Thus a wrapper that became stale after
rehydration cannot win a check-then-write race. A restored `superseded` or
`sealed` transition remains historically valid without becoming actionable.

## 8. Atomic Trace lineage

Every successful advance emits exactly one canonical
`TraceEvent(event_type="hybrid_replay_advanced")` in the same StateStore batch
as state, head, receipt, inclusion proof, and transition index. A failure emits
none of those durable artifacts.

The event binds the scoped session, protocol/manifest/candidate/policy/effective
policy/topology roots, revision and step, parent transition/snapshot/head,
snapshot/memory/receipt roots, source step/Trace roots, and complete read-set
root. This authority event uses an exact lineage field set: missing and unknown
fields are rejected identically by runtime validation and the published Trace
schema. Its stream and transition identities are independently re-derived by
the Trace validator. Trace projection or archive success cannot create replay
authority; the committed Store batch is the authority source.

## 9. v1 compatibility and non-downgrade

The v1 `HybridReplayState` and its process-local issuance sentinels remain
Draft compatibility surfaces only while WP-05 migration is active. They are
not a v2 credential, historical proof, or restart mechanism. The v2 evaluator
does not read or issue those tokens: after StateStore currentness verification,
it feeds a structurally validated replay projection into the shared pure Hybrid
engine and commits only the independently rooted v2 snapshot. Its local source
proof binds complete canonical evaluation content and contains no issuance
sentinel.

A v2 entrypoint MUST accept only its exact v2 records and a genuine v2
authority session. It MUST NOT accept a raw v1 `HybridCollectiveStep`, a v1
sentinel as a parent, reinterpret a v1 digest as Store inclusion, or fall back
to process-local currentness. The v2 evaluator may reuse the existing pure
Hybrid scoring implementation internally, but only through its token-free pure
entry after deriving every declaration from the exact scoped manifest and only
while producing the complete v2 source-context proof; this is implementation
reuse, not a version fallback.
Existing v1 callers continue through their explicit legacy surface until the
lifecycle removal gate is satisfied.

This preserves baseline and Hybrid compatibility without weakening the v2
trust boundary. It does not declare Hybrid Replay v2 Stable or activate a
provider/runtime profile. Its adapter Conformance matrix proves ABI behavior;
it does not certify an operator-selected production Store deployment.
