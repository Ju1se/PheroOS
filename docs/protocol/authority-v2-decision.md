# Authority v2 Version and Trust-Boundary Decision

Status: accepted and implemented for the Draft local scoped-authority profile;
authenticated production promotion remains gated

Decision date: 2026-07-21

Scope: WP-01 of the production-readiness hardening plan

This decision freezes the version axes and trust boundary implemented across
WP-02 through WP-08. The repository now provides the Draft StateStore and
Authority Session v2 ABIs, Baseline Output v2, Capability/Protocol schema v3
exact dispatch, Authority v2 and scoped-authority TCK schema/strict readers,
Runtime Integration v1, provider-free references, and exact-version
Conformance. The local scoped-authority profile is an active Draft selection;
it never falls back to a v1 reader or assurance profile. The authenticated
production path still requires an independent external grant-verifier adapter,
aggregate profile evidence, and the later Stable promotion gates.

## Context

The current Draft authority path is a trusted-host compatibility mechanism.
Public issuer functions, `AuthorityLevel`, caller booleans, issuer strings,
digests, and process-local registries are useful for deterministic reference
semantics, but none authenticates a principal. A receipt also proves neither
identity nor current permission merely because its digest is valid.

The current finalize path additionally couples historical commit validity to
the current head. A valid successor can therefore make an earlier committed
transition look invalid. Process-local replay state cannot recover durable
currentness after a restart, and validating an action permission before a
separate commit leaves a time-of-check/time-of-use gap.

Several existing identifiers already contain `v2`, but their version axes are
not scoped authority semantics:

- `pheroos-protocol-schema-v2` and `pheroos-capability-schema-v2` are strict
  schema-document versions for payloads whose semantic discriminator remains
  `pheroos.protocol.v1`;
- `pheroos-commit-integrity-tck-v2`, its request/response/JSONL v2 protocols,
  and `pheroos-conformance-report-v2` remain the existing Commit and report
  contracts;
- `pheroos-driver-descriptor-v2` and `pheroos-kernel-plan-v2` remain the
  Driver and Kernel ABI discriminators; and
- `pheroos-source-v3` remains the currently active source profile.

Reusing any of those identifiers would silently reinterpret public contracts.
A separate, exact authority semantic/profile/schema dispatch is required.

## Decision

### Authority invariants

The implementation must preserve these rules:

1. Agent, model, scout, tool, pheromone, attention, and extension data is a
   proposal. It cannot create evidence or authority.
2. `AuthorityLevel` classifies a record. It is not a credential.
3. Every v2 issuance, replay-currentness change, commit, recovery, and external
   action authorization binds the exact scope, operation, issuer grant,
   target/action, ledger/domain, payload, and required Trace lineage.
4. A portable record regains local authority only after the selected
   StateStore verifies its committed inclusion. A digest, receipt identifier,
   same-shaped dataclass, or boolean alone never grants authority.
5. Historical validity and current actionability are independent. A legal
   successor cannot invalidate an included historical transition.
6. Capabilities are non-portable, least-privilege, scope-bound, and subject to
   expiry and revocation. They cannot be replayed across scope, store, domain,
   target, action, operation, epoch, or payload.
7. Domain sealing forbids new commits while retaining verification material
   for pre-seal history.
8. Replay advance is append-only, CAS-protected, and recoverable across a
   restart.
9. Every declared or producible Governance terminal outcome is deliverable.
   Publication and execution remain separate, current actions.
10. Normal denial, conflict, stale input, and store unavailability use total,
    typed results rather than exception-message parsing.
11. Every output authorization commit validates the complete canonical
    authority read-set and commits authority state, authority-critical Trace,
    and its receipt within one atomic StateStore boundary.

### Four authority actors

The v2 trust model has four distinct actors. No one actor's record substitutes
for another actor's responsibility.

| Responsibility | Actor and authority source |
| --- | --- |
| Issue | A trusted authority coordinator binds a local, non-portable session. Under the authenticated profile it first uses a host-selected external issuer-grant verifier. The untrusted request cannot select that verifier. |
| Commit | The deployment-selected `GovernanceStateStoreV2` writer atomically validates every read-set precondition and commits the exact state, authority-critical Trace batch, and receipt. Writer possession is not exposed to agents or Drivers. |
| Restore | A recovery coordinator using the selected store reader loads the immutable committed transition and verifies batch, receipt, inclusion, scope, and ledger/domain bindings before treating a portable payload as historical authority. |
| Execute external action | The external runtime or sink publishes/executes only from a current target/action/payload-bound authorization. Protocol-core records the decision but does not perform the effect. Delivery alone is not publication or execution. |

### Frozen version registry

The following identifiers are exact and case-sensitive. Their activation is
surface-specific and requires implementation, artifacts, negative tests, and
exact-version dispatch; an implemented Draft identifier is not a Stable or
production-runtime claim.

| Axis | Exact identifier | Decision |
| --- | --- | --- |
| Protocol semantics | `pheroos.protocol.v2` | Explicit opt-in to scoped authority semantics; no shape inference. |
| Protocol schema selector | `pheroos-protocol-schema-v3` | Selects the v3 Protocol schema document. |
| Capability schema selector | `pheroos-capability-schema-v3` | Selects the v3 Capability schema document. |
| Authority policy | `pheroos-scoped-authority-policy-v2` | Closed authority-policy discriminator. |
| Local profile | `pheroos-scoped-authority-local-v2` | Trusted-host/store-possession reference profile. |
| Authenticated profile | `pheroos-scoped-authority-authenticated-v2` | Requires a host-selected issuer-grant verifier. |
| Wire | `pheroos-authority-wire-v2` | Portable authority envelope encoding. |
| Canonicalization | `pheroos-authority-canonical-v2` | Canonical JSON and content-root rules. |
| Authority schema selector | `pheroos-authority-schema-v2` | Selects the authority v2 wire schema. |
| Authority read-set schema | `pheroos-governance-authority-read-set-v2` | Closed canonical read-set object described below. |
| Ledger | `pheroos-governance-authority-ledger-v2` | Historical authority ledger semantics. |
| StateStore | `pheroos-governance-state-store-v2` | Reader/writer/store ABI with atomic multi-head preconditions. |
| StateStore Conformance | `pheroos-governance-state-store-conformance-v2` | Exact provider-neutral store-adapter test contract. |
| Atomic Trace batch | `pheroos-governance-trace-batch-v2` | Trace records committed with the authority transition. |
| Grant-verifier Conformance | `pheroos-issuer-grant-verifier-conformance-v2` | Exact external verifier-adapter test contract. |
| Scoped authority TCK | `pheroos-scoped-authority-tck-v2` | Authority v2 adversarial vectors and session protocol. |
| Source profile | `pheroos-source-v4` | Source-boundary checks after authority v2 owners land. |

The existing `pheroos.trace.TraceEvent` remains the only canonical Trace ABI.
`pheroos-governance-trace-batch-v2` is an atomic ledger batch encoding, not a
second Trace event type.

The existing `TraceStore` remains a derived, append-only lineage sink governed
by `pheroos-trace-store-conformance-v1`; it is not the durable authority trust
root and does not gain authority v2 semantics by renaming. Authority-critical
Trace is first committed inside `pheroos-governance-state-store-v2`. A
crash-safe projector may then append idempotent canonical `TraceEvent` records
to an external TraceStore. A successful standalone Trace append cannot prove
that an authority transition committed, and a failed projection cannot erase
the store's committed history.

The exact 17-code authority diagnostic registry is now owned by the additive
Draft `pheroos.protocol.authority_v2.AuthorityDiagnosticCodeV2` contract.
Protocol owns profile/schema dispatch and therefore cannot import a Governance
enum. Governance consumes that exact enum and may re-export the same object as
a facade alias, but it must not define a second diagnostic type or copy the
strings into a competing registry. Governance owns the mapping from those
diagnostics to `GovernanceCommitDispositionV2`. This implemented registry began
in the WP-02 StateStore slice and is now used by the active Draft local profile.
It does not satisfy the independent authenticated-verifier or Stable promotion
gates. Input rejected before authority-v2
dispatch retains the existing generic Protocol schema/version diagnostic and
is not relabeled as a successfully selected v2 profile.

### Schema files and `$id` values

No existing schema file or `$id` may change bytes or meaning. Authority v2
uses new files:

| Surface | File | Exact `$id` | Selector/discriminator |
| --- | --- | --- | --- |
| Protocol | `protocol-v3.schema.json` | `https://pheroos.dev/schemas/protocol-v3.schema.json` | `pheroos-protocol-schema-v3` |
| Capability | `capability-v3.schema.json` | `https://pheroos.dev/schemas/capability-v3.schema.json` | `pheroos-capability-schema-v3` |
| Authority wire | `authority-v2.schema.json` | `https://pheroos.dev/schemas/authority-v2.schema.json` | `pheroos-authority-schema-v2` |
| Scoped authority TCK | `scoped-authority-tck-v2.schema.json` | `https://pheroos.dev/schemas/scoped-authority-tck-v2.schema.json` | `pheroos-scoped-authority-tck-v2` |

Protocol and Capability schema-document v3 require semantic discriminator
`pheroos.protocol.v2` and an exact scoped authority policy/profile selection.
Legacy manifests remain explicitly `pheroos.protocol.v1`; they are not
silently upgraded. Unknown or mismatched selectors fail closed. Readers do not
infer a version from object shape.

The v2 Protocol document selects authority through one closed
`protocol.authority_policy` object containing exactly `policy_version`,
`profile`, `wire_version`, `canonical_version`, `ledger_version`,
`state_store_version`, `trace_batch_version`, and `read_set_version`. Each
value is the corresponding exact identifier in the registry above. A v1
Protocol document cannot contain this object. Verifier configuration is
deliberately absent: the authenticated profile requires a verifier, but only
trusted deployment configuration may select its implementation.

### Local and authenticated profiles

`pheroos-scoped-authority-local-v2` uses possession of the deployment-selected
StateStore writer and the trusted coordinator boundary as its trust root. It is
the deterministic provider-free reference profile. It authenticates neither a
remote person nor an external workload and must be described as local
trusted-host authority, not production identity assurance.

`pheroos-scoped-authority-authenticated-v2` adds verification of an issuer
grant by an `IssuerGrantVerifier` selected through trusted deployment
configuration. The request, agent, or model cannot provide or downgrade the
verifier. The durable transition binds the stable grant reference, verified
operations and bounds, verifier result, revocation/expiry epoch, and
non-secret grant binding. Protocol-core does not load credentials, manage
keys, call an IdP/KMS, or implement network authentication.

There is no fallback from authenticated to local. A missing, unavailable, or
failing verifier produces a typed non-authoritative result. Promotion of the
authenticated production path to Stable requires at least one independent
external adapter to pass
`pheroos-issuer-grant-verifier-conformance-v2`. Passing only the in-memory
local reference profile cannot satisfy that promotion gate.

### Canonical authority read-set

Every authority v2 commit contains one complete read-set. Its exact canonical
object has only these fields:

```json
{
  "canonical_version": "pheroos-authority-canonical-v2",
  "entries": [
    {
      "expected_revision": 0,
      "expected_root": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "stream_ref": "authority:example"
    }
  ],
  "schema": "pheroos-governance-authority-read-set-v2"
}
```

Canonicalization and validation rules are:

- the object contains exactly `canonical_version`, `entries`, and `schema`;
  each entry contains exactly `stream_ref`, `expected_revision`, and
  `expected_root`; duplicate JSON keys and extension fields are rejected;
- the read-set contains from 1 through 128 entries;
- `stream_ref` is a non-blank string without surrounding whitespace, already
  normalized to Unicode NFC; entries are unique and sorted by the unsigned
  UTF-8 bytes of their NFC `stream_ref` in ascending order;
- `expected_revision` is a JSON integer, not a boolean, in the inclusive range
  `0..9007199254740991`;
- `expected_root` is exactly `sha256:` followed by 64 lowercase hexadecimal
  characters;
- strings and object keys must already be NFC. Floats, `NaN`, positive or
  negative infinity, binary values, nulls, and non-declared values are invalid;
- canonical bytes are UTF-8 without BOM, produced with sorted object keys,
  no insignificant whitespace, no ASCII escaping of Unicode, and no trailing
  newline; equivalently the JSON settings are `allow_nan=false`,
  `ensure_ascii=false`, `separators=(",", ":")`, and `sort_keys=true`; and
- the read-set root is lowercase `sha256:` plus SHA-256 of those exact
  canonical bytes. The batch binds that root and the store recomputes it.

The store validates all listed revision/root pairs in the same atomic boundary
that writes state, `pheroos-governance-trace-batch-v2`, and the receipt. A
single mismatch commits nothing. A reference store may serialize all entries
onto one internal authority stream; an external adapter may use a multi-head
transaction. Both must expose identical all-or-nothing behavior. The maximum
of 128 is an ABI bound, not a suggestion, and cannot be bypassed with an
extension field or nested read-set.

### Typed commit outcome and historical position

`GovernanceCommitDispositionV2` is a closed wire enum:

| Python label | Wire value | Meaning |
| --- | --- | --- |
| `COMMITTED` | `committed` | The exact transition has verified durable inclusion. |
| `DENIED` | `denied` | A well-formed request was authoritatively refused by scope, grant, operation, action, revocation, expiry, seal, or declared policy. No receipt or authority is created. |
| `RETRY_REQUIRED` | `retry_required` | A valid preparation lost a CAS/read-set race or used a known stale parent. The caller must obtain a new snapshot before preparing again. |
| `FINALITY_UNAVAILABLE` | `finality_unavailable` | The store cannot currently prove whether the transition committed. This is neither authority nor proof of non-commit; reconcile by transition identity before any external effect. |
| `INVALID` | `invalid` | Input, identity, scope, batch, receipt, inclusion, or proof is malformed, conflicting, cross-boundary, or tampered. |

`GovernanceCommitPositionV2` is a separate closed wire enum:

| Python label | Wire value | Meaning |
| --- | --- | --- |
| `CURRENT` | `current` | The committed transition is the observed actionable head. |
| `SUPERSEDED` | `superseded` | A legal successor exists; historical inclusion remains valid but current publish/execute authority does not follow automatically. |
| `SEALED` | `sealed` | The transition is verified in a sealed domain's immutable history; the domain accepts no new commit. |

Position is present only after committed inclusion has been verified. A result
can be `disposition=committed` and later be observed as
`position=superseded` or `position=sealed`; that change never rewrites its
historical disposition. Non-committed dispositions carry no fabricated
position, receipt, or committed transition. A caller cannot turn `denied`,
`retry_required`, `finality_unavailable`, or `invalid` into a fallback commit.

`DENIED` carries no authority receipt, inclusion proof, position, or committed
transition. It also never masquerades as a committed audit transition. After a
valid scope/session exists, a policy may require a canonical denial
`TraceEvent` in a scoped audit sink. When required, the implementation makes
one idempotent append attempt and exposes its outcome separately as audit
telemetry. That append is a separate,
non-authoritative audit operation: it carries no authority receipt, inclusion
proof, or position; it cannot be loaded as a
`GovernanceCommittedTransitionV2`; and its success or unavailability cannot
change the already determined denial. Only a successful authority state change
uses `pheroos-governance-trace-batch-v2` in the same atomic Store commit as
state and receipt. Pre-auth malformed or unsupported input cannot force either
an authority write or canonical denial-audit write.

### Same-process boundary

Opaque session/capability handles prevent ordinary serialization, accidental
cross-scope reuse, and use through public wire APIs. They are not a sandbox
against arbitrary Python code running in the trusted coordinator or
StateStore-writer process. Such code can observe process memory and invoke
trusted objects, so it is inside the trust boundary.

Production deployments must isolate untrusted agents, tools, provider
adapters, and plugins from that process and restrict access to StateStore
writer credentials. Protocol-core supplies contracts and Conformance; it does
not supply process isolation, a secret manager, authentication middleware, or
a generic capability/security manager.

## Consequences

- The scoped-authority activation checklist now has unambiguous names for
  implementation, schema generation, exact dispatch, TCK vectors,
  Conformance, and migration.
- Historical proof can survive legal successors, restart, and domain sealing,
  while current action authority remains explicitly re-evaluated.
- Full read-set validation closes the separate-read/separate-commit TOCTOU
  path and allows both serialized reference stores and external transactional
  stores without specifying a database.
- Local provider-free tests remain possible, but the local profile cannot be
  presented as authenticated production authority.
- Implementers must add new readers, schemas, typed models, store behavior,
  independent adapters, negative tests, and migration fixtures. Existing v1
  consumers receive no automatic upgrade.
- The bounded, closed authority wire is intentionally stricter than
  namespaced non-authoritative manifest extensions. Extensibility remains
  outside the authority projection; new authority-critical meaning requires a
  new exact version.
- Existing Commit TCK v2, report v2, Driver v2, Kernel v2, schema-document v2,
  TraceStore v1, and source v3 artifacts remain byte- and meaning-stable.

## Rejected alternatives

### Reinterpret existing v2 identifiers

Rejected because Capability/Protocol schema v2, Commit TCK v2, report v2,
Driver v2, and Kernel v2 already identify independent public contracts. A
global meaning for the number `v2` would create ambiguous dispatch and silent
breaking changes.

### Treat `AuthorityLevel`, an issuer string, boolean, digest, or receipt id as a credential

Rejected because those values are caller-constructible or integrity-only.
They do not prove an authenticated grant, least privilege, currentness, or
possession of the selected writer.

### Keep current-head equality as the finality test

Rejected because a valid descendant would erase the observable validity of an
already committed transition. Historical inclusion and dynamic position must
be queried separately.

### Commit state and append Trace in separate trust boundaries

Rejected because either side can succeed alone after a crash. Authority-
critical Trace belongs in the StateStore atomic batch; the external TraceStore
is a derived, idempotent projection.

### Limit the public ABI to one internal authority stream

Rejected because output authorization must atomically bind a finite set of
manifest, decision, evidence, stop, grant, permission, replay, and head roots.
The bounded read-set permits a serialized implementation without weakening
the externally observable multi-precondition guarantee.

### Allow unbounded read-sets or extension-defined preconditions

Rejected because they make resource use and authority meaning open-ended. The
closed 128-entry maximum is sufficient for the declared authority projection;
new critical semantics require a versioned contract.

### Let authenticated deployments fall back to local authority

Rejected because verifier failure would become an assurance downgrade. Exact
profile selection fails closed.

### Put identity providers, keys, KMS, or authentication in protocol-core

Rejected because protocol-core owns provider-neutral ABI and deterministic
semantics, not deployment credentials or network identity. External verifiers
integrate through a small conformance-tested boundary.

### Build a generic security or capability manager

Rejected because the required object is a small, store-bound authority session
with a closed operation set. A general manager would enlarge the attack and
ABI surface without enforcing an additional protocol invariant.

### Force all v1, baseline, swarm, or Hybrid manifests to opt in

Rejected because scoped authority is versioned and explicit. Existing Draft
profiles continue to validate under their frozen v1 semantics while migration
is deliberate and tested.
