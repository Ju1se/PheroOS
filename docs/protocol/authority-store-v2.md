# Authority StateStore v2 Normative Contract

Status: **Draft, independently audited, Conformance-backed, and used by the
active local scoped-authority profile**

Decision date: 2026-07-21

This document freezes the provider-neutral StateStore contract required by
WP-02. It refines the accepted
[authority v2 decision](authority-v2-decision.md),
[trust model](authority-trust-model-v2.md), and
[migration contract](authority-v2-migration.md). If prose elsewhere is less
specific, this document controls the StateStore v2 object shapes, roots,
atomic behavior, total results, historical-finality behavior, and seal
semantics. StateStore conformance alone does not activate a profile or grant
authority; the active local path also requires exact manifest dispatch,
Authority Session, Baseline Output, currentness, Trace, and Conformance.

The exact public contracts, serialized provider-free reference store, and
independent adapter Conformance implement this storage/finality slice. The
WP-02 closure audit found no remaining P0/P1 after its restart and historical
cross-stream replay regressions were converted into required tests. Authority
sessions, profile/schema dispatch, Output v2, and Runtime Integration were added
in later vertical slices. Using this Draft StateStore ABI alone still cannot
select `pheroos.protocol.v2` or authorize an action.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**,
and **MAY** are normative for an implementation that selects
`pheroos-governance-state-store-v2`.

This is a protocol-core ABI. It does not prescribe a database, server,
process manager, queue, worker, provider, identity system, or external
runtime. A serialized in-memory reference store and an independent adapter
must expose the same observable contract.

## 1. Frozen identifiers and ownership

These identifiers are exact, case-sensitive, and do not accept aliases,
version ranges, shape inference, or fallback:

| Surface | Exact identifier |
| --- | --- |
| Protocol semantics | `pheroos.protocol.v2` |
| Authority policy | `pheroos-scoped-authority-policy-v2` |
| Local profile | `pheroos-scoped-authority-local-v2` |
| Authenticated profile | `pheroos-scoped-authority-authenticated-v2` |
| Wire | `pheroos-authority-wire-v2` |
| Canonicalization | `pheroos-authority-canonical-v2` |
| Read-set | `pheroos-governance-authority-read-set-v2` |
| Ledger | `pheroos-governance-authority-ledger-v2` |
| StateStore | `pheroos-governance-state-store-v2` |
| Atomic Trace batch | `pheroos-governance-trace-batch-v2` |

`pheroos.protocol.authority_v2` owns:

- `AuthorityV2ProtocolError` for strict Python construction and decoding;
- `AuthorityDiagnosticCodeV2`, the single 17-code diagnostic enum;
- `GovernanceReadPreconditionV2`;
- `GovernanceAuthorityReadSetV2`;
- `AUTHORITY_CANONICAL_VERSION_V2`;
- `GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2`;
- `MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2`;
- `MAX_AUTHORITY_REVISION_V2`; and
- `loads_governance_authority_read_set_v2()`.

Governance imports the exact Protocol enum object. It may re-export that
object as a facade alias, but MUST NOT define a second diagnostic enum or copy
the strings into another registry. Governance owns the mapping from those
codes to `GovernanceCommitDispositionV2`.

`AuthorityV2ProtocolError` is a strict construction/decode error. It is not a
StateStore failure protocol. A caller MUST NOT catch it and parse its message
to infer a Governance disposition.

## 2. Closed outcome axes

### 2.1 Commit disposition

`GovernanceCommitDispositionV2` has exactly five lowercase wire values:

| Python label | Wire value | Meaning |
| --- | --- | --- |
| `COMMITTED` | `committed` | The exact transition has verified durable inclusion. |
| `DENIED` | `denied` | A valid request was authoritatively refused and created no authority. |
| `RETRY_REQUIRED` | `retry_required` | A valid preparation lost a known read-set/CAS race and must be prepared again from a fresh snapshot. |
| `FINALITY_UNAVAILABLE` | `finality_unavailable` | The store cannot currently prove whether the transition committed. |
| `INVALID` | `invalid` | The input, identity, binding, Trace, receipt, inclusion, or proof is malformed, conflicting, cross-boundary, or tampered. |

No `conflict`, `stale`, `unavailable`, `malformed`, `success`, or other wire
disposition may be added to this version.

### 2.2 Historical position

`GovernanceCommitPositionV2` has exactly three lowercase wire values:

| Python label | Wire value | Meaning |
| --- | --- | --- |
| `CURRENT` | `current` | The transition is the observed actionable head at the observation snapshot. |
| `SUPERSEDED` | `superseded` | A legal successor exists; historical inclusion remains valid. |
| `SEALED` | `sealed` | The transition is included in a sealed domain; the domain accepts no new commit. |

Disposition and position are orthogonal. Position exists only for a verified
`committed` result. A legal successor changes an observation from `current`
to `superseded`; it MUST NOT change the historical disposition to `invalid`.
A domain seal changes all included historical observations in that scope to
`sealed`; it does not rewrite their receipts or inclusion proofs.

### 2.3 Diagnostic registry

The exact `AuthorityDiagnosticCodeV2` wire registry and default Governance
mapping are:

| Exact diagnostic | Disposition |
| --- | --- |
| `authority_profile_unsupported` | `invalid` |
| `authority_session_required` | `denied` |
| `authority_session_store_mismatch` | `invalid` |
| `authority_scope_mismatch` | `invalid` |
| `authority_operation_denied` | `denied` |
| `authority_binding_mismatch` | `invalid` |
| `authority_grant_unverified` | `denied` |
| `authority_grant_expired` | `denied` |
| `authority_grant_revoked` | `denied` |
| `governance_read_set_invalid` | `invalid` |
| `governance_read_set_stale` | `retry_required` |
| `governance_transition_conflict` | `invalid` |
| `governance_domain_sealed` | `denied` |
| `governance_finality_unavailable` | `finality_unavailable` |
| `governance_committed_transition_invalid` | `invalid` |
| `governance_action_not_authorized` | `denied` |
| `governance_trace_lineage_invalid` | `invalid` |

WP-02 emits only the subset relevant to store/session binding, scope and
payload binding, read-sets, transition identity, seal, finality, historical
proof, and authority-critical Trace. WP-03 and WP-04 reuse the same registry.

## 3. Canonical JSON and roots

### 3.1 Canonical value rules

Authority v2 root bodies use one deterministic JSON subset:

- object keys and string values MUST already be Unicode NFC;
- object keys are strings and are serialized in ascending key order;
- strings are encoded as UTF-8 without ASCII escaping;
- permitted scalar values are `null`, booleans, NFC strings, and JSON-safe
  integers in `-9007199254740991..9007199254740991`;
- arrays preserve their declared order;
- floats, `NaN`, infinities, binary values, tuples, sets, arbitrary objects,
  duplicate JSON keys, and non-NFC values are invalid;
- serialization uses `allow_nan=false`, `ensure_ascii=false`,
  `separators=(",", ":")`, and `sort_keys=true`; and
- encoded bytes are UTF-8 without BOM or trailing newline.

Closed wire objects reject extension fields. The nullable fields explicitly
listed in this document are the only permitted `null` values in those
objects. The canonical authority read-set is stricter and permits no `null`.

Every root is lowercase `sha256:` followed by exactly 64 lowercase
hexadecimal characters.

### 3.2 Root function

Except for the read-set, every v2 root uses this exact function:

```text
root_v2(separator, body) =
    "sha256:" + lowercase_hex(
        SHA-256(UTF8(separator) || 0x00 || canonical_authority_bytes_v2(body))
    )
```

`body` contains every exact wire field except the object's own stored root
field. The schema discriminator remains in `body`. A nested object's stored
root remains present when its parent body is hashed. Constructors and
`from_dict()` MUST recompute and constant-time compare caller-supplied roots;
they MUST NOT trust a supplied digest.

The read-set is the deliberate exception frozen by WP-01:

```text
read_set_root =
    "sha256:" + lowercase_hex(SHA-256(read_set.canonical_bytes()))
```

There is no additional domain separator for that hash because the complete
read-set object already contains the exact
`pheroos-governance-authority-read-set-v2` discriminator and WP-01 froze the
direct hash.

### 3.3 Exact schema and separator registry

| Object/root | Exact `schema` | Exact separator | Stored root field |
| --- | --- | --- | --- |
| Authority domain | `pheroos-governance-authority-domain-v2` | `pheroos-governance-authority-v2:domain` | `domain_root` |
| State snapshot body | `pheroos-governance-authority-state-v2` | `pheroos-governance-authority-v2:state` | `state_root` |
| Stream head | `pheroos-governance-authority-head-v2` | `pheroos-governance-authority-v2:head` | `head_root` |
| Prepared transition | `pheroos-governance-prepared-transition-v2` | `pheroos-governance-authority-v2:transition` | `transition_root` |
| Trace batch | `pheroos-governance-trace-batch-v2` | `pheroos-governance-authority-v2:trace-batch` | `trace_root` |
| Commit batch | `pheroos-governance-commit-batch-v2` | `pheroos-governance-authority-v2:commit-batch` | `batch_root` |
| Commit receipt | `pheroos-governance-commit-receipt-v2` | `pheroos-governance-authority-v2:receipt` | `receipt_root` |
| Inclusion proof | `pheroos-governance-commit-inclusion-proof-v2` | `pheroos-governance-authority-v2:inclusion` | `inclusion_root` |
| Committed transition | `pheroos-governance-committed-transition-v2` | `pheroos-governance-authority-v2:committed-transition` | `committed_transition_root` |
| Position observation | `pheroos-governance-commit-position-observation-v2` | `pheroos-governance-authority-v2:position-observation` | `observation_root` |
| Failure | `pheroos-governance-failure-v2` | `pheroos-governance-authority-v2:failure` | `failure_root` |
| Commit attempt | `pheroos-governance-commit-attempt-v2` | `pheroos-governance-authority-v2:attempt` | `attempt_root` |
| Commit view | `pheroos-governance-commit-view-v2` | `pheroos-governance-authority-v2:view` | `view_root` |
| Seal head set | no independent wire object | `pheroos-governance-authority-v2:seal-heads` | `final_heads_root` |
| Domain seal | `pheroos-governance-domain-seal-v2` | `pheroos-governance-authority-v2:seal` | `seal_root` |

The separator bytes are exactly the UTF-8 spelling shown in the table. The
single `0x00` separator byte is appended by `root_v2`; it is not part of the
table string.

### 3.4 Public canonical methods

Every root-bearing public Governance class provides:

```text
to_dict() -> detached exact wire dict
from_dict(value) -> validated detached instance
canonical_bytes() -> canonical bytes of the complete wire, including its root
root() -> the recomputed and verified stored root string
```

`canonical_bytes()` and `root()` have different inputs: the first encodes the
complete wire; the second returns the digest computed from the root body with
the object's own root field removed.

## 4. Canonical authority read-set

`GovernanceReadPreconditionV2` has exactly these fields:

```json
{
  "expected_revision": 0,
  "expected_root": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "stream_ref": "authority:example"
}
```

`GovernanceAuthorityReadSetV2` has exactly these fields:

```json
{
  "canonical_version": "pheroos-authority-canonical-v2",
  "entries": [],
  "schema": "pheroos-governance-authority-read-set-v2"
}
```

The illustrative empty `entries` value above shows only the object shape; it
is invalid. A valid read-set contains 1 through 128 entries.

The exact validation rules are:

1. `stream_ref` is non-blank, has no leading or trailing whitespace, and is
   already NFC.
2. Entries are unique by `stream_ref` and sorted by unsigned UTF-8 bytes of
   the NFC `stream_ref` in ascending order.
3. `expected_revision` has Python type `int`, not `bool`, and is in
   `0..9007199254740991`.
4. `expected_root` is one exact lowercase SHA-256 root.
5. Every field is required; unknown fields, duplicate JSON keys, floats,
   `null`, and undeclared values are invalid.
6. `loads_governance_authority_read_set_v2()` accepts only
   `str | bytes | bytearray`, performs strict duplicate-key and non-finite
   rejection, and then uses the same constructor validation.

For this StateStore contract, `expected_root` always means the exact current
**stream head root**. It never means a state root, transition root, batch
root, receipt root, inclusion root, or Trace root.

An ordinary transition is bounded multi-read/single-write. Its write stream
MUST appear exactly once in the read-set. The target entry's revision/root
MUST equal the prepared transition's `expected_revision`/`expected_root`.
The Store validates every entry against one atomic snapshot and publishes
nothing if any entry differs.

## 5. Genesis, state, and head algorithms

### 5.1 Genesis parent

The exact genesis parent is:

```text
GOVERNANCE_GENESIS_PARENT_ROOT_V2 =
  sha256:fb5aac1257de4967a1a6f3d2d41b279e5a423e98141b1a0380c69becd81bfa93
```

It is SHA-256 of
`UTF8("pheroos-governance-authority-v2:genesis-parent") || 0x00`.
It is a sentinel, not a receipt or committed transition.

### 5.2 State root

There is no additional public `GovernanceAuthorityStateV2` dataclass. The
minimal public helper is:

```python
governance_authority_state_root_v2(
    scope_ref,
    stream_ref,
    state_records,
) -> str
```

It hashes this exact private state body with the state separator:

```json
{
  "canonical_version": "pheroos-authority-canonical-v2",
  "ledger_version": "pheroos-governance-authority-ledger-v2",
  "schema": "pheroos-governance-authority-state-v2",
  "scope_ref": "scope:example",
  "state_records": {},
  "stream_ref": "authority:example"
}
```

`state_records` is the complete post-transition state snapshot, not a patch.
The empty-state root is the result for `{}` and is therefore scope- and
stream-specific.

### 5.3 Genesis head

`GovernanceHeadV2.genesis(domain, stream_ref)` has:

- `revision = 0`;
- `parent_root = GOVERNANCE_GENESIS_PARENT_ROOT_V2`;
- `state_root = governance_authority_state_root_v2(scope_ref, stream_ref, {})`;
- `transition_id = "genesis"`;
- `batch_root = GOVERNANCE_GENESIS_PARENT_ROOT_V2`; and
- `head_root = root_v2(head-separator, all preceding exact head fields)`.

Caller transitions MUST NOT use the reserved transition ID `genesis`.
Genesis heads are deterministic virtual heads; a Store need not persist an
empty row to return one.

For every committed successor:

```text
new.revision    = previous.revision + 1
new.parent_root = previous.head_root
new.state_root  = transition.state_root, or seal.seal_root for the lifecycle stream
new.transition_id = batch.transition_id
new.batch_root  = batch.batch_root
new.head_root   = root_v2(head separator, exact new head body)
```

A batch's expected write root is always `previous.head_root`. Using the
previous state root as `expected_root` is invalid, even when both states are
otherwise equal.

## 6. Exact public objects

All listed fields are required. `null` is permitted only where a conditional
rule below explicitly requires it. Nested objects use their complete wire
dict, including their stored roots.

### 6.1 `AuthorityDomainV2`

Exact fields, in semantic order, are:

```text
schema
policy_version
profile
wire_version
canonical_version
ledger_version
state_store_version
trace_batch_version
read_set_version
scope_ref
domain_root
```

The eight selector/profile values are supplied explicitly and MUST equal the
accepted registry. There are no defaults. `profile` is exactly local v2 or
authenticated v2. A request cannot infer, select, or downgrade a profile from
shape. `domain_root` binds the complete selection and scope.

### 6.2 `GovernanceHeadV2`

Exact fields are:

```text
schema, canonical_version, ledger_version, domain_root, scope_ref,
stream_ref, revision, parent_root, state_root, transition_id, batch_root,
head_root
```

`revision` is bounded by `MAX_AUTHORITY_REVISION_V2`. Every root and scope
binding is exact. A non-genesis head whose predecessor cannot be verified is
invalid.

### 6.3 `PreparedGovernanceTransitionV2`

Exact fields are:

```text
schema, canonical_version, ledger_version, domain_root, scope_ref,
stream_ref, transition_id, expected_revision, expected_root, read_set_root,
state_records, state_root, transition_root
```

`state_root` is recomputed from the complete `state_records` with the state
algorithm. `transition_root` binds all other fields. The read-set target entry
must match the expected pair. Ordinary transitions MUST NOT target the
reserved lifecycle stream `authority:domain-lifecycle`.

### 6.4 `GovernanceTraceBatchV2`

Exact fields are:

```text
schema, canonical_version, domain_root, scope_ref, stream_ref,
transition_id, events, trace_root
```

`events` contains 1 through 128 ordered canonical snapshots of
`pheroos.trace.TraceEvent`. Each event snapshot has exactly the existing
canonical object's five fields:

```text
event_type, protocol_id, target, reason, lineage
```

The batch MUST construct or receive actual `pheroos.trace.TraceEvent`
instances, validate each through the existing Trace ABI, and snapshot nested
lineage before hashing. Each event's lineage MUST contain exact `scope_ref`,
`stream_ref`, and `transition_id` values matching the batch. The Trace batch
may return detached `TraceEvent` clones while retaining private canonical
snapshots to prevent nested mutation.

This encoding does not define a second Trace event model. `TraceEvent` remains
the sole Trace ABI. `pheroos-governance-trace-batch-v2` is only the ordered,
atomic ledger container. An external `TraceStore` remains a derived,
idempotent projection sink and is never the authority trust root.

### 6.5 `GovernanceDomainSealV2`

The reserved lifecycle stream is exactly:

```text
GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2 = "authority:domain-lifecycle"
```

The seal fields are:

```text
schema, canonical_version, ledger_version, domain_root, scope_ref,
transition_id, expected_revision, expected_root, final_heads,
final_heads_root, seal_root
```

Each `final_heads` entry has exactly:

```text
stream_ref, revision, head_root
```

Entries are unique and ordered by unsigned UTF-8 bytes of `stream_ref`.
`final_heads_root` is exactly:

```text
root_v2(
  "pheroos-governance-authority-v2:seal-heads",
  {
    "canonical_version": "pheroos-authority-canonical-v2",
    "domain_root": seal.domain_root,
    "scope_ref": seal.scope_ref,
    "entries": seal.final_heads
  }
)
```

That four-field root body is exact. It is not a separately serialized wire
object and therefore has no additional schema discriminator.
`seal_root` hashes the full seal body excluding only `seal_root`.

A selected authority v2 scope has at most 127 non-lifecycle streams. An
attempt to create the 128th returns
`invalid/governance_read_set_invalid` at canonical path `/read_set` and
publishes nothing. This is an explicit resource bound required so every valid
domain remains sealable; the lifecycle stream does not count toward 127.

A seal batch's canonical read-set contains:

1. the lifecycle stream precondition; and
2. one entry for every current non-lifecycle stream in the scope.

It therefore contains 1 through 128 entries. `final_heads` is exactly the
read-set with the lifecycle entry removed, with `revision` copied from
`expected_revision` and `head_root` copied from `expected_root`. The seal's
`expected_revision`/`expected_root` exactly equal the lifecycle entry.

Inside the atomic boundary the Store compares both the values and the entire
observed non-lifecycle stream set. An omitted stream, an extra stream, a
changed head, or a new stream racing the seal yields
`retry_required/governance_read_set_stale`; no partial seal is visible.

### 6.6 `GovernanceCommitBatchV2`

Exact fields are:

```text
schema, canonical_version, ledger_version, domain, domain_root, scope_ref,
stream_ref, transition_id, kind, read_set, read_set_root, transition,
transition_root, seal, seal_root, trace_batch, trace_root, batch_root
```

`kind` is a closed lowercase wire enum with exactly `transition` and `seal`.
The following exclusive rules apply:

| `kind` | `transition` / `transition_root` | `seal` / `seal_root` | `stream_ref` |
| --- | --- | --- | --- |
| `transition` | both present | both `null` | any declared non-lifecycle stream |
| `seal` | both `null` | both present | `authority:domain-lifecycle` |

`read_set`, `read_set_root`, `trace_batch`, and `trace_root` are present for
both kinds. All duplicated domain, scope, stream, transition, and root values
must match exactly. `domain` is a complete `AuthorityDomainV2` wire and its
root must equal `domain_root`.

A normal batch is multi-read/single-write. A seal is a distinguished
store-level lifecycle write, not a transition inferred from state shape.

### 6.7 `GovernanceCommitReceiptV2`

Exact fields are:

```text
schema, canonical_version, ledger_version, domain_root, scope_ref,
stream_ref, transition_id, revision, parent_root, head_root, state_root,
read_set_root, trace_root, batch_root, receipt_root
```

For a transition receipt, `state_root` is the prepared state root. For a seal
receipt, `state_root` is the seal root. `parent_root` is the exact prior head
root; `head_root` is the new head root. A receipt is deterministic and contains
no clock, random nonce, database identifier, or provider-specific proof.

### 6.8 `GovernanceCommitInclusionProofV2`

Exact fields are:

```text
schema, canonical_version, ledger_version, domain_root, scope_ref,
stream_ref, transition_id, revision, batch_root, receipt_root, head_root,
inclusion_root
```

The proof binds the immutable ledger entry at its committed revision. It does
not claim that the entry is still current. Its bytes alone create no local
authority: the selected StateStore must verify that the exact proof is present
in its committed history.

### 6.9 `GovernanceCommittedTransitionV2`

Exact fields are:

```text
schema, canonical_version, ledger_version, batch, receipt, inclusion_proof,
committed_transition_root
```

All nested roots and duplicate bindings must match. It deliberately contains
no current position. Historical proof is immutable; position is observed
separately.

### 6.10 `GovernanceCommitPositionObservationV2`

Exact fields are:

```text
schema, canonical_version, ledger_version, domain_root, scope_ref,
stream_ref, transition_id, receipt_root, observed_revision,
observed_head_root, position, seal_root, observation_root
```

`seal_root` is `null` for `current` and `superseded`, and is a verified root
for `sealed`. The observation is an immutable fact from one Store snapshot;
it is not inserted into or used to recompute the historical proof.

### 6.11 `GovernanceFailureV2`

Exact fields are:

```text
schema, code, path, stage, failure_root
```

`code` is the exact Protocol-owned diagnostic enum. `path` is a canonical
RFC 6901 JSON Pointer; the empty string means the request root. Pointer tokens
use only the required `~0` and `~1` escapes and array indexes use canonical
base-10 form without leading zeros. A free-form message is not part of the
wire ABI.

`GovernanceFailureStageV2` has exactly these lowercase values:

```text
validation
reconciliation
precondition
trace
commit
finality
load
seal
```

Failure stage is diagnostic context, not another disposition.

### 6.12 `GovernanceCommitAttemptV2`

Exact fields are:

```text
schema, canonical_version, domain_root, scope_ref, stream_ref, transition_id,
disposition, failure, committed_transition, position_observation,
attempt_root
```

The exact union is:

| Disposition | `failure` | `committed_transition` | `position_observation` |
| --- | --- | --- | --- |
| `committed` | `null` | present | present |
| any other value | present | `null` | `null` |

Success never fabricates a success diagnostic. A non-committed attempt never
carries a receipt, inclusion proof, position, or committed transition.

### 6.13 `GovernanceCommitViewV2`

Exact fields are:

```text
schema, canonical_version, domain_root, scope_ref, stream_ref, transition_id,
expected_receipt_root, disposition, failure, committed_transition,
position_observation, observed_revision, observed_head_root, view_root
```

`expected_receipt_root` is either the exact requested root or `null` when the
caller is reconciling only by transition identity. `observed_revision` and
`observed_head_root` are either both present or both `null`.

Only these union states are reachable:

| Disposition | Failure | Committed transition / position | Observed head pair |
| --- | --- | --- | --- |
| `committed` | `null` | both present | both present and equal the position observation |
| `invalid` | present | both `null` | both present if the same reliable snapshot observed the stream; otherwise both `null` |
| `finality_unavailable` | present | both `null` | both `null` |

`denied` and `retry_required` are commit-time decisions and MUST NOT be
invented by the historical view loader.

## 7. Scope-wide identity and idempotency

`transition_id` is unique across the entire `scope_ref`, not merely within a
stream. The same namespace covers ordinary transitions and seal transitions.
The Store maintains a scope-wide transition index.

Reconciliation order is normative:

1. Look up the transition ID before applying current-head or sealed-domain
   rejection.
2. If the stored `batch_root` equals the submitted `batch_root`, return the
   same committed transition and receipt with a fresh dynamic position
   observation.
3. If the ID exists with different canonical batch bytes/root, return
   `invalid/governance_transition_conflict` at `/transition_id`.
4. If the ID is absent, continue normal validation and commit.

Thus an exact retry remains idempotent even after a legal successor or domain
seal. Changing one payload leaf under an existing ID is substitution, not a
retry. Random or implicit IDs are forbidden by the ABI.

## 8. Atomic commit algorithm

`GovernanceStateWriterV2.atomic_commit_v2(batch)` is total for every validly
constructed `GovernanceCommitBatchV2` and returns
`GovernanceCommitAttemptV2`.

The observable linearization algorithm is:

1. Detach and recanonicalize the complete batch; validate exact schemas,
   versions, roots, domain, scope, stream, and transition bindings.
2. Reconcile the scope-wide transition ID as specified above.
3. Reject a new ordinary transition in a sealed scope with
   `denied/governance_domain_sealed` at `/domain_root`.
4. Validate the complete canonical read-set and target-write relation. For a
   seal, also validate lifecycle/final-head completeness and the 127-stream
   bound.
5. Validate every canonical `TraceEvent`, ordered Trace snapshot, and
   `trace_root`.
6. Enter one Store atomic boundary and take one consistent domain snapshot.
7. Compare every expected revision/head root. A known drift returns
   `retry_required/governance_read_set_stale` at `/read_set`; it is not
   `invalid`.
8. For a seal, compare the complete observed non-lifecycle stream set and
   lifecycle precondition inside the same boundary.
9. Stage the full state or seal, new head, immutable batch, authority-critical
   Trace batch, receipt, inclusion proof, and scope-wide identity index in
   private state.
10. Publish all staged values at one linearization point.
11. Return the committed transition and position observation from that
    snapshot.

No state, head, Trace batch, receipt, inclusion proof, transition index, or
seal may become observable before step 10. A failure before publication leaves
all seven categories byte-for-byte unchanged. A failure after publication but
before the caller receives a response returns or is reconciled as
`finality_unavailable/governance_finality_unavailable`; it MUST NOT blindly
repeat an external effect.

### 8.1 Required failure-injection boundaries

Conformance adapters must be testable at these semantic boundaries, even when
their private hook names differ:

```text
before validation
after identity reconciliation
after read-set validation and before private staging
after state/head staging
after Trace staging
after receipt/inclusion staging
after atomic publication and before response
```

Failures through receipt/inclusion staging expose zero partial writes. The
post-publication failure is an unknown-response case and must be recoverable
by `load_commit_view_v2()`.

Wrong Python argument types, use of a destroyed test fixture, interpreter
failure, and implementation bugs may raise. Expected denial, stale input,
identity conflict, invalid proof, seal, and store unavailability MUST use the
typed total result. Callers MUST NOT parse exception messages.

### 8.2 Denial Trace is not an authority commit

A `denied` attempt carries no batch, receipt, inclusion, position, or
authority-critical Trace batch. After a valid scope/session is established, a
declared policy may request one separate idempotent denial `TraceEvent` append
to a non-authoritative audit sink. Its outcome is independent telemetry and
cannot change the denial. Pre-auth malformed or unsupported input cannot force
either a StateStore write or that audit append.

## 9. Total historical view

`GovernanceStateReaderV2` exposes exactly the public total loader for a scope
already selected by that Store:

```python
load_commit_view_v2(
    scope_ref,
    stream_ref,
    transition_id,
    *,
    expected_receipt_root=None,
) -> GovernanceCommitViewV2
```

It performs one consistent read snapshot and this exact sequence:

1. resolve the selected domain and scope-wide transition identity;
2. detach the immutable batch, receipt, inclusion proof, and stored Trace
   batch from the same snapshot;
3. when supplied, compare `expected_receipt_root` exactly;
4. recompute every nested root and cross-binding;
5. verify committed inclusion in the selected Store;
6. observe the target stream head and domain seal in the same snapshot; and
7. construct a detached committed transition plus dynamic position.

Its result mapping is:

- verified inclusion in an open scope and exact observed head identity:
  `committed/current`;
- verified inclusion with a legal descendant in an open scope:
  `committed/superseded`;
- verified inclusion in a sealed scope: `committed/sealed` with the exact
  `seal_root`;
- absent, mismatched, malformed, cross-domain, cross-stream, or tampered
  committed material: `invalid/governance_committed_transition_invalid`;
- invalid required Trace lineage:
  `invalid/governance_trace_lineage_invalid`; and
- no reliable answer from the selected Store:
  `finality_unavailable/governance_finality_unavailable`.

`expected_receipt_root=None` is the required response-loss reconciliation
path. When a root is supplied it must match exactly. The loader never treats a
current-head mismatch alone as historical invalidity. A bare optional receipt
loader, optional historical loader, or position-only reader may exist as a
private helper but is not the public v2 ABI.

Portable bytes, correct digests, a copied dataclass, and a TraceStore event
remain data until this selected Store verifies committed inclusion. A view
object is detached so later Store progress cannot mutate the earlier
observation.

The Store selection boundary is explicit: `load_head_v2()`, `load_state_v2()`,
and `load_commit_view_v2()` may reject an unknown/unregistered `scope_ref` as a
Python/deployment calling-contract error. The view signature intentionally
does not carry an `AuthorityDomainV2`, so a Store MUST NOT invent a local or
authenticated profile merely to manufacture a result for an unselected
scope. Once a scope is selected, every well-typed view outcome is represented
by the total `GovernanceCommitViewV2` union above.

All selector arguments must also satisfy their declared lexical contracts:
refs are non-empty canonical text and a supplied `expected_receipt_root` is an
exact lowercase `sha256:` root. A malformed selector is a Python calling-
contract error and may be rejected before taking a Store snapshot; it is not a
fourth view disposition and a Store must not echo non-canonical bytes into the
canonical view wire.

## 10. Seal semantics and ownership stages

WP-02 owns only the store-level atomic seal primitive and its proof semantics:

- seal competes atomically with ordinary commits;
- exactly one linearization order wins;
- when an ordinary commit advances first, the stale seal receives
  `retry_required/governance_read_set_stale`;
- when the seal publishes first, the raced ordinary commit observes the
  terminal domain and receives `denied/governance_domain_sealed`;
- after seal, new commits are denied;
- pre-seal batches, receipts, inclusion proofs, Trace, and delivery remain
  verifiable; and
- a seal is itself a committed lifecycle batch with standard receipt and
  inclusion proof.

WP-03 decides which scope-bound operation/capability may request a seal. WP-02
does not expose writer possession to agents, models, Drivers, or untrusted
extensions. WP-05 migrates legacy replay/window/certificate/retire callers to
the primitive. WP-05 MUST NOT redefine the seal root, revive destructive
retirement, or turn `sealed` into a fourth position.

Until those caller migrations land, v1 `retire()` and process-local
compatibility behavior remain unchanged. A v2 seal is never inferred from a
v1 tombstone, missing directory, closed database connection, or arbitrary
state record.

## 11. Snapshot, checkpoint, and restart

The public ABI specifies restart equivalence, not a database or snapshot file
format. A conforming adapter may use an append-only log, copy-on-write image,
transactional rows, or another durable representation.

An exported reference snapshot is deterministic and orders:

1. domains by unsigned UTF-8 bytes of `scope_ref`;
2. heads and states within a domain by unsigned UTF-8 bytes of `stream_ref`;
3. committed entries in their actual cross-stream linearization order, using
   a private per-domain monotonic commit sequence;
4. the scope-wide transition index by transition ID UTF-8 bytes; and
5. Trace events in their original batch order.

The private commit sequence is snapshot metadata, not a public receipt, head,
batch, inclusion, or Python ABI field. It starts at one and has no duplicate,
gap, or reorder. Restore rejects a sequence that is missing, duplicated, or
inconsistent with stream revisions, predecessor heads, the transition index,
or the seal linearization point. Sorting committed entries by stream would
erase the real order of multi-stream read dependencies and is forbidden.

Restore validates into private state before exposing a reader or writer. Its
dependency order is:

1. exact snapshot/store/canonical version selection;
2. domain descriptors and `domain_root` values;
3. state roots and genesis/non-genesis head chains;
4. batches and Trace roots;
5. receipts and inclusion proofs;
6. the gap-free private global commit sequence and scope-wide transition
   index;
7. lifecycle head and seal/final-head closure; and
8. all derived indexes and current observations.

The restored image is published atomically only after every check succeeds.
Failure leaves the prior Store image unchanged. A sealed flag/root is
validated before the restored writer becomes available, so restart never
opens a write window into a sealed scope.

The Conformance restart hook is test instrumentation rather than a public
StateStore method. It reports an unsupported/invalid persisted image shape with
`TypeError` and an integrity-validation rejection with `ValueError`. Returning
any Store from a corrupt image, or raising another exception class, fails that
adapter's deterministic Conformance run. These exception classes do not become
wire diagnostics or a production storage API requirement.

After a restart, the following observations must be identical:

- every current head revision/root;
- every exact retry receipt;
- every historical committed transition and inclusion result;
- every `current`, `superseded`, or `sealed` position derived from the same
  snapshot;
- the scope-wide transition-conflict result;
- the non-lifecycle stream-count bound; and
- the seal root and rejection of new commits.

Snapshot ordering is a deterministic reference requirement and test oracle.
It does not require independent adapters to expose or share the reference
snapshot bytes. Their public restart behavior is tested through the v2
StateStore Conformance contract.

## 12. Public protocols and immutability

The exact public protocol surfaces are:

```python
class GovernanceStateReaderV2(Protocol):
    def load_head_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> GovernanceHeadV2: ...

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]: ...

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2: ...


class GovernanceStateWriterV2(Protocol):
    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2: ...


class GovernanceStateStoreV2(
    GovernanceStateReaderV2,
    GovernanceStateWriterV2,
    Protocol,
):
    @property
    def state_store_version(self) -> str: ...
```

`GovernanceStateStoreV2` combines the reader and writer structural protocols.
Its read-only `state_store_version` property is exactly
`pheroos-governance-state-store-v2`. Seal uses the explicit `seal` batch kind;
there is no second public seal method. Snapshot/export/restore hooks are
adapter-private Conformance surfaces rather than additions to this public
protocol.

`load_head_v2()` and `load_state_v2()` return detached values for preparation.
Separate preparation reads are not commit authority: the full read-set is
rechecked atomically by `atomic_commit_v2()`. Only
`load_commit_view_v2()` provides the public total historical/finality view.
Writer possession is a deployment capability, not a serializable authority
record. Reader-for-writer substitution must fail.

The exact public model names are:

```text
AuthorityDomainV2
GovernanceHeadV2
PreparedGovernanceTransitionV2
GovernanceTraceBatchV2
GovernanceDomainSealV2
GovernanceCommitBatchV2
GovernanceCommitReceiptV2
GovernanceCommitInclusionProofV2
GovernanceCommittedTransitionV2
GovernanceCommitPositionObservationV2
GovernanceFailureStageV2
GovernanceFailureV2
GovernanceCommitAttemptV2
GovernanceCommitViewV2
GovernanceCommitDispositionV2
GovernanceCommitPositionV2
```

Constructors snapshot caller-owned mappings, arrays, read-sets, and Trace
lineage. Accessors and `to_dict()` return detached values. A caller mutating an
original nested mapping after construction cannot alter any canonical bytes or
root. Frozen dataclass syntax alone is not considered deep immutability.

## 13. Compatibility and non-goals

WP-02 adds new versioned owners. It MUST NOT alter the bytes, semantics,
pickle identity, facade identity, or behavior of:

- `pheroos-governance-authority-ledger-v1`;
- `AuthorityDomain`, `GovernanceHead`, `PreparedGovernanceTransition`,
  `GovernanceCommitBatch`, or `GovernanceCommitReceipt` v1;
- `authority_domain.py`, `_authority/ledger.py`, `atomic_evaluation.py`, or
  `authority_ledger_contract.py` v1 behavior;
- Protocol/Capability schema-document v1 or v2;
- Commit TCK v1/v2;
- `pheroos-source-v3`; or
- `pheroos-trace-store-conformance-v1`.

There is no automatic v1-to-v2 reader, no receipt upgrade, no v1 tombstone to
v2 seal conversion, no schema-shape dispatch, and no assurance downgrade.
Existing baseline protocols stay on `pheroos.protocol.v1` until explicit
migration.

This contract intentionally does not add:

- a SQL/SQLite/PostgreSQL schema;
- a database migration framework;
- a server, endpoint, API gateway, queue, worker, or daemon;
- an agent/model/provider client;
- an identity provider, KMS, credential loader, or secret manager;
- a general policy/capability/security manager; or
- external effect execution.

Production database adapters and operational topology are deployment work.
They prove compatibility against this ABI rather than changing it.

## 14. Required conformance evidence

Before WP-02 can close, the reference store and an independent stdlib adapter
that imports only public v2 contracts must prove at least:

- exact batch retry returns the same receipt;
- same scope-wide transition ID with different canonical bytes is invalid;
- 32 identical workers yield one commit and one receipt;
- 32 conflicting genesis batches yield one winner;
- a legal B successor leaves A `committed/superseded`, never invalid;
- response loss after publication reconciles by transition ID;
- mutation of every batch/receipt/inclusion/history/head/state/Trace/scope/
  stream/root/index/sequence/seal binding is rejected;
- reordering a cross-stream dependency while rewriting sequence/index metadata
  is rejected by historical full-read-set replay;
- any read-set drift publishes no state, Trace, receipt, inclusion, or index;
- all declared pre-publication failure stages expose zero partial writes;
- snapshot/restart preserves history, idempotency, current heads, and seal;
- the 128th non-lifecycle stream is rejected at `/read_set`;
- seal read-set/final-head omission, addition, and races fail atomically;
- old proof remains readable after seal while every new write is denied;
- `load_commit_view_v2()` reaches only its three declared dispositions and
  obeys every nullable-field invariant;
- `TraceEvent` remains the sole Trace event object; and
- frozen v1 fixtures and differential tests remain byte-identical.

Passing only the in-memory reference is insufficient. An independent adapter
must demonstrate the same roots, total results, race outcomes, restart
observations, and seal semantics without importing reference/private ledger
logic.

The Conformance adapter's observation, restart, failure-injection, and mutation
hooks are trusted test instrumentation selected by the test operator. They
return detached canonical image bytes so the harness can independently parse
the seven declared artifact categories and recompute their fingerprint. This
detects inconsistent or incomplete instrumentation and proves byte-level
stability for an honestly instrumented implementation; it is not a remote
attestation protocol and cannot prove private state against an adapter that
colludes by fabricating both its image bytes and its hash.
