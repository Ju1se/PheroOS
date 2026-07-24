# Baseline Output v2 Normative Contract

Status: **Draft public ABI; locally activated only for the provider-free
trusted-host profile and its Conformance matrix**

This document is the normative description of the implemented Baseline Output
v2 vertical slice. It covers the Protocol v3 declaration, Governance records
and operations, StateStore dependencies, Trace lineage, and Conformance surface.
If an older plan or design draft disagrees with the exact identifiers, fields,
signatures, events, or reachability rules below, this document controls for this
Draft slice.

The governing rule is:

> Portable data is not authority. An external action is authorized only by a
> Governance-computed permission whose exact durable inclusion and dependencies
> remain current in the selected StateStore.

This is a protocol-core contract. It does not perform the declared `publish` or
`execute` effect, call a model provider, manage secrets, provide a server, run an
agent framework, or prescribe a database implementation.

## 1. Activation, versions, and trust boundary

Baseline Output v2 is an additive, explicit opt-in path. A reader selects it
only with the v3 schema selector and a Protocol document whose semantic version
is exactly `pheroos.protocol.v2`. Readers must not infer v3 from object shape.
The v1 and v2 schema selectors continue to select the legacy v1 Protocol
contract, and no v2 operation silently falls back to that contract.

<!-- baseline-output-v2-version-registry:start -->
| Axis | Exact identifier |
| --- | --- |
| Protocol semantics | `pheroos.protocol.v2` |
| Protocol schema selector | `pheroos-protocol-schema-v3` |
| Protocol schema file | `protocol-v3.schema.json` |
| Protocol schema `$id` | `https://pheroos.dev/schemas/protocol-v3.schema.json` |
| Capability schema selector | `pheroos-capability-schema-v3` |
| Capability schema file | `capability-v3.schema.json` |
| Capability schema `$id` | `https://pheroos.dev/schemas/capability-v3.schema.json` |
| Authority policy | `pheroos-scoped-authority-policy-v2` |
| Local authority profile | `pheroos-scoped-authority-local-v2` |
| Authenticated authority profile | `pheroos-scoped-authority-authenticated-v2` |
| Authority wire | `pheroos-authority-wire-v2` |
| Authority canonicalization | `pheroos-authority-canonical-v2` |
| Authority ledger | `pheroos-governance-authority-ledger-v2` |
| Authority StateStore | `pheroos-governance-state-store-v2` |
| Authority read-set | `pheroos-governance-authority-read-set-v2` |
| Authority Trace batch | `pheroos-governance-trace-batch-v2` |
| Baseline output policy | `pheroos-baseline-output-policy-v2` |
| Baseline Conformance | `pheroos-baseline-output-conformance-v2` |
<!-- baseline-output-v2-version-registry:end -->

The current active proof is the Draft local profile. Under that profile, issuer
capability custody and verifier selection are trusted-host responsibilities; a
portable request, API key, hash, agent identity, or returned dataclass is not an
identity credential. The local profile therefore makes no claim about portable
authentication of a person, workload, model, tenant, or network peer. An
authenticated deployment must satisfy the separate host-verifier and
StateStore requirements in the [Authority Session v2 contract](authority-session-v2.md)
and [trust model](authority-trust-model-v2.md); passing the local matrix must not
be relabeled as authenticated assurance.

The exact portable and durable schema identifiers are:

<!-- baseline-output-v2-schema-registry:start -->
| Constant | Exact identifier |
| --- | --- |
| `BASELINE_OUTPUT_REQUEST_SCHEMA_V2` | `pheroos-governance-baseline-output-request-v2` |
| `ACTION_PERMISSION_SCHEMA_V2` | `pheroos-governance-action-permission-v2` |
| `BASELINE_OUTPUT_RESULT_SCHEMA_V2` | `pheroos-governance-baseline-output-result-v2` |
| `BASELINE_MANIFEST_STATE_SCHEMA_V2` | `pheroos-governance-baseline-manifest-state-v2` |
| `BASELINE_EVIDENCE_STATE_SCHEMA_V2` | `pheroos-governance-baseline-evidence-state-v2` |
| `BASELINE_STOP_STATE_SCHEMA_V2` | `pheroos-governance-baseline-stop-state-v2` |
| `BASELINE_DECISION_STATE_SCHEMA_V2` | `pheroos-governance-baseline-decision-state-v2` |
| `BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2` | `pheroos-governance-baseline-action-permission-state-v2` |
| `BASELINE_OUTPUT_STATE_SCHEMA_V2` | `pheroos-governance-baseline-output-state-v2` |
<!-- baseline-output-v2-schema-registry:end -->

## 2. Protocol v3 declaration

The Governance request carries one exact `ScopedProtocolManifestV2`. It does
not carry a Capability document. The manifest is declaration-only Protocol
data: Governance validates it and derives authority roots, but Protocol neither
opens sessions nor writes StateStore records.

`ScopedAuthorityPolicyV2` has the exact fields `policy_version`, `profile`,
`wire_version`, `canonical_version`, `ledger_version`, `state_store_version`,
`trace_batch_version`, and `read_set_version`. Every version except `profile`
must match the exact registry above; `profile` must select one of the two
declared scoped-authority profiles.

The complete baseline policy shape is:

```json
{
  "policy_version": "pheroos-baseline-output-policy-v2",
  "decision_mode": "quorum",
  "actions": [
    {
      "action_ref": "action:publish",
      "effect": "publish",
      "target": "target:answer",
      "allowed_outcomes": ["evidence_commit", "safe_fallback"]
    }
  ]
}
```

The closed action object has exactly these fields:

<!-- baseline-output-v2-action-policy-fields:start -->
```text
action_ref
effect
target
allowed_outcomes
```
<!-- baseline-output-v2-action-policy-fields:end -->

The closed output policy has exactly these fields:

<!-- baseline-output-v2-output-policy-fields:start -->
```text
policy_version
decision_mode
actions
```
<!-- baseline-output-v2-output-policy-fields:end -->

The Protocol invariants are:

- `decision_mode` is exactly `quorum` or `direct_governance`;
- `effect` is exactly `publish` or `execute`;
- every action target equals `quorum_policy.target`, and the referenced
  `fallback_candidate` is one declared safe candidate for that same target;
- actions contain at most 128 entries, have unique `action_ref` values, and use
  unsigned UTF-8 `action_ref` order;
- `allowed_outcomes` is a non-empty, unique, unsigned UTF-8 ordered tuple drawn
  only from `evidence_commit` and `safe_fallback`;
- targets and candidates are non-empty and uniquely declared;
- the quorum fallback is exactly one declared `safe_fallback=True` candidate
  for the quorum target;
- `evidence_policy.require_provenance` is `True` and
  `evidence_policy.allow_agent_fact_creation` is `False`; and
- the Trace policy contains all six required Baseline Output events.

The declaration does not require a `collective_decision_policy`, a
`collective_commit_policy`, a swarm mode, or an Optimal Commit certificate.
Those optional Protocol declarations do not become authority inputs to this
baseline evaluator.

## 3. Public Governance ABI

`pheroos.governance.baseline_output_v2` is the public owner-facing facade. Its
public export list is exact:

<!-- baseline-output-v2-public-api:start -->
```text
ACTION_PERMISSION_SCHEMA_V2
BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2
BASELINE_DECISION_STATE_SCHEMA_V2
BASELINE_EVIDENCE_STATE_SCHEMA_V2
BASELINE_MANIFEST_STATE_SCHEMA_V2
BASELINE_OUTPUT_REQUEST_SCHEMA_V2
BASELINE_OUTPUT_RESULT_SCHEMA_V2
BASELINE_OUTPUT_STATE_SCHEMA_V2
BASELINE_STOP_STATE_SCHEMA_V2
ActionPermissionDispositionV2
ActionPermissionV2
BaselineOutputActionDispositionV2
BaselineOutputDeliveryDispositionV2
BaselineOutputRequestV2
BaselineOutputResultV2
BaselineOutputTerminalStatusV2
baseline_action_permission_stream_ref_v2
baseline_decision_stream_ref_v2
baseline_evidence_stream_ref_v2
baseline_manifest_stream_ref_v2
baseline_output_result_root_v2
baseline_output_stream_ref_v2
baseline_stop_stream_ref_v2
baseline_verified_signal_proposal_root_v2
evaluate_and_commit_baseline_output_v2
evaluate_and_commit_governed_baseline_output_v2
issue_action_permission_v2
open_baseline_output_authority_session_v2
recover_baseline_output_result_v2
```
<!-- baseline-output-v2-public-api:end -->

The five journey entrypoints are exactly:

<!-- baseline-output-v2-entrypoints:start -->
```python
def open_baseline_output_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: BaselineOutputRequestV2,
    operation: GovernanceIssuerOperationV2,
) -> GovernanceAuthoritySessionV2: ...

def issue_action_permission_v2(
    request: BaselineOutputRequestV2,
    *,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2: ...

def evaluate_and_commit_baseline_output_v2(
    request: BaselineOutputRequestV2,
    *,
    authority_session: object = None,
) -> BaselineOutputResultV2: ...

def evaluate_and_commit_governed_baseline_output_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    activation_transition_id: str,
    activation_observed_epoch: int,
    request: BaselineOutputRequestV2,
    *,
    verified_signal_requests: tuple[GovernanceVerifiedSignalRequestV2, ...] = (),
    verifier: IssuerGrantVerifierV2 | None = None,
) -> GovernanceCommitAttemptV2 | BaselineOutputResultV2: ...

def recover_baseline_output_result_v2(
    request: BaselineOutputRequestV2,
    *,
    state_reader: GovernanceStateReaderV2,
) -> BaselineOutputResultV2: ...
```
<!-- baseline-output-v2-entrypoints:end -->

The high-level governed entrypoint is the external-runtime write boundary for
the Draft Stable promotion candidate. The caller supplies only the exact
versioned Store, domain, portable grant, grant-activation identity/epoch,
portable verified-signal requests, optional host-selected verifier, and
portable output request. Governance internally activates or reconciles the
grant, binds a fresh Store-local capability, commits every one-to-one
signal/proposal binding, opens and commits permission, then opens, evaluates,
and atomically commits output.

`activation_transition_id` and `activation_observed_epoch` describe the grant
lifecycle request. They remain unchanged across exact retry and restart and
are deliberately independent of the later `request.observed_epoch`, while the
activation epoch must not be later than the output request epoch. Signal
transition identifiers are bound by their exact portable request roots;
permission identifiers are derived from the Baseline request; the unsuffixed
output identifier is part of that request root.

The return union is closed: `GovernanceCommitAttemptV2` means activation,
signal, binding/session projection, or permission stopped before the output
operation; `BaselineOutputResultV2` means the output operation was reached.
Callers discriminate by exact record type and then the existing disposition.
The composition never loops, publishes, executes, creates Trace on failure, or
turns a portable record into authority.

Opaque capability and session objects exist only as local variables inside
this entrypoint. They are never returned, serialized, traced, or included in
the promotion-candidate type closure. Binding/open failures project into the
existing portable diagnostic and failure-attempt vocabulary without a
committed transition. Local-profile calls still require `verifier=None`;
authenticated-profile calls still require a matching accepted verifier result
at activation and every fresh bind.

The session opener accepts only `ISSUE_ACTION_PERMISSION` and
`AUTHORIZE_OUTPUT`, and binds the exact domain, scope, run, request root,
observed epoch, target, action, operation, and selected writer. The two commit
entrypoints accept that opaque session only as a keyword argument.

Before either operation may write, every field of the manifest's
`authority_policy` must exactly match the selected session domain: policy,
profile, wire, canonical, ledger, StateStore, Trace batch, and read-set version.
A manifest-selected profile cannot reinterpret a session opened in another
authority domain.

`issue_action_permission_v2` computes the decision and permission from the
manifest, verified durable signals, complete stop resolutions, payload root,
and issuer session. It returns the StateStore commit attempt; the portable
permission is read from the committed permission state. It accepts no
caller-supplied permission, Boolean authorization gate, or precommitted
decision. `evaluate_and_commit_baseline_output_v2` independently reloads and
recomputes every durable gate before committing output.

`recover_baseline_output_result_v2` is the read-only restart and historical
entrypoint. It accepts the exact request and a StateReader, loads the exact
output transition once, and canonical-round-trips the complete commit view,
receipt, inclusion proof, state, permission, result, Trace, and original
read-set bindings. It accepts no caller-provided result, permission,
authorization, receipt, or authority session. Missing, unavailable, malformed,
cross-scope, or substituted reads return a typed fail-closed result rather than
creating authority or falling back to v1.

## 4. Canonical records and roots

The three public records are frozen, slotted dataclasses. Each implements exact
`to_dict()`, exact-field `from_dict()`, `canonical_bytes()`, and `root()`.
Their wire readers reject missing or unknown fields and recompute every supplied
derived root. `canonical_bytes()` serializes the complete wire object, including
its root field, using UTF-8 JSON with `allow_nan=False`, `ensure_ascii=False`,
`separators=(",", ":")`, and `sort_keys=True`.

Governance roots use:

```text
"sha256:" + hex(SHA-256(
  UTF8("pheroos-governance-authority-v2:" + kind)
  || NUL
  || canonical_json(body)
))
```

Portable mappings are recursively frozen. Strings and keys must already be
Unicode NFC; keys are strings; integers stay within the exact JSON-safe range;
floating-point and non-JSON values are rejected. A root proves deterministic
content binding, not authority or currentness.

### 4.1 `BaselineOutputRequestV2`

The dataclass and wire key set has exactly these fields; the list follows
dataclass order:

<!-- baseline-output-v2-request-fields:start -->
```text
domain_root
scope_ref
run_ref
request_ref
output_transition_id
manifest
target_ref
action_ref
proposed_candidate_ref
verified_signals
stop_resolutions
output_payload
observed_epoch
manifest_stream_ref
evidence_stream_ref
stop_stream_ref
decision_stream_ref
permission_stream_ref
output_stream_ref
output_payload_root
schema
canonical_version
request_root
```
<!-- baseline-output-v2-request-fields:end -->

The caller supplies identity and scope bindings, `output_transition_id`, the
exact `ScopedProtocolManifestV2`, target/action selection, proposal inputs, the
actual JSON `output_payload`, and `observed_epoch`. `direct_governance` requires
`proposed_candidate_ref` to name a declared candidate for the target; `quorum`
requires it to be `None`.

Every `verified_signals` proposal has exactly:

<!-- baseline-output-v2-verified-signal-fields:start -->
```text
candidate_ref
evidence_root
provenance_ref
signal_ref
signal_root
signal_transition_id
source_ref
```
<!-- baseline-output-v2-verified-signal-fields:end -->

The tuple is unique and sorted by unsigned UTF-8
`(source_ref, signal_ref)`. `candidate_ref` must be declared for the target.
`signal_transition_id` locates the exact committed verified-signal transition;
that transition must be committed, current, `verified`, and match scope, run,
target, signal, signal root, and evidence root.

The public proposal-root helper has exact keyword-only inputs:

```python
baseline_verified_signal_proposal_root_v2(
    *,
    domain_root,
    scope_ref,
    run_ref,
    target_ref,
    candidate_ref,
    signal_ref,
    evidence_root,
    provenance_ref,
    source_ref,
)
```

It binds domain, scope, run, target, candidate, signal, evidence, provenance,
and independent source into `signal_root`. The verified-signal state commits
that root. Consequently, changing candidate, source, or provenance and merely
recomputing the request proposal cannot reinterpret the already committed
verified signal. Qualified evidence also stores the verified-signal stream and
receipt roots.

Every `stop_resolutions` proposal has exactly:

<!-- baseline-output-v2-stop-fields:start -->
```text
action_ref
blocked
provenance_ref
reason_ref
```
<!-- baseline-output-v2-stop-fields:end -->

The tuple must cover every declared output action for the target exactly once
and in manifest action order. `blocked` is an exact Boolean, `provenance_ref` is
a root, and `reason_ref` is non-blank text. The requested action's resolution
is used for the decision, while complete coverage prevents an omitted action
from becoming an implicit allow.

The request derives and verifies all six stream references:

<!-- baseline-output-v2-stream-bindings:start -->
| Field | Stream kind | Ordered hash bindings |
| --- | --- | --- |
| `manifest_stream_ref` | `baseline-manifest` | `scope_ref`, `manifest.id` |
| `evidence_stream_ref` | `baseline-evidence` | `scope_ref`, `run_ref`, `target_ref` |
| `stop_stream_ref` | `baseline-stop` | `scope_ref`, `run_ref`, `target_ref` |
| `decision_stream_ref` | `baseline-decision` | `scope_ref`, `run_ref`, `target_ref` |
| `permission_stream_ref` | `baseline-action-permission` | `scope_ref`, `run_ref`, `target_ref`, `action_ref` |
| `output_stream_ref` | `baseline-output` | `scope_ref`, `run_ref`, `target_ref`, `action_ref` |
<!-- baseline-output-v2-stream-bindings:end -->

For each row, the stream value is
`authority:<kind>:<lowercase SHA-256 hex>` over the ordered UTF-8 bindings
joined with NUL bytes. The request also derives `output_payload_root` from the
actual frozen payload and derives `request_root` from the complete request body.
Supplying a mismatched derived stream or root fails construction.

`output_transition_id` is the final output transition identifier. The manifest,
evidence, stop, decision, and permission stages use respectively
`<output_transition_id>:manifest`, `:evidence`, `:stop`, `:decision`, and
`:permission`. The final output stage uses the unsuffixed value.

### 4.2 `ActionPermissionV2`

The portable permission has exactly:

<!-- baseline-output-v2-permission-fields:start -->
```text
domain_root
scope_ref
run_ref
request_ref
request_root
permission_transition_id
permission_stream_ref
manifest_root
output_policy_root
evidence_root
stop_root
decision_root
target_ref
candidate_ref
action_ref
effect
terminal_status
output_payload_root
disposition
issued_epoch
expires_at_epoch
grant_ref
grant_root
grant_binding_ref
schema
canonical_version
permission_root
```
<!-- baseline-output-v2-permission-fields:end -->

`ActionPermissionDispositionV2` is exactly `authorized` or `denied`.
Governance sets `issued_epoch` to the request epoch and
`expires_at_epoch` to that epoch plus one. Output evaluation requires
`issued_epoch <= request.observed_epoch < expires_at_epoch`, exact request,
manifest, policy, evidence, stop, decision, target, candidate, action, effect,
terminal, payload, and issuer-grant bindings, plus a current durable permission
state. Possession or deserialization of this record alone creates no authority.

The permission issuer grant must still be active, root/binding matched, valid at
issuance, scoped to the target/action, and include the complete operation set
used during issuance: `ISSUE_ACTION_PERMISSION`, `QUALIFY_EVIDENCE`,
`RESOLVE_STOP`, plus `EVALUATE_QUORUM` in quorum mode.
The output-authorizing grant may be a different grant; both grant heads then
become final output dependencies.

### 4.3 `BaselineOutputResultV2`

The total result has exactly:

<!-- baseline-output-v2-result-fields:start -->
```text
domain_root
scope_ref
run_ref
request_ref
request_root
output_transition_id
output_payload_root
terminal_status
candidate_ref
delivery_disposition
action_disposition
permission_root
authorization
commit_attempt
result_root
schema
canonical_version
```
<!-- baseline-output-v2-result-fields:end -->

`disposition` and `position` are read-only projections of `commit_attempt`, not
wire fields. `permission_root` is present for every result, including retry and
diagnostic envelopes. `authorization` is an `ActionPermissionV2` only when the
action is currently authorized; otherwise it is `None`.

The exact reader validates the attempt's domain, scope, transition and, for a
committed result, output stream and durable output state. Any exposed
authorization must match the result's request, payload, terminal, candidate,
permission root, and `:permission` transition, must itself be authorized, and
must accompany a current committed output.

For a deliverable result, `result_root` binds schema/canonical version, domain,
scope, run, request identity/root, output transition and payload root, terminal
status, candidate, `deliverable`, and `permission_root`. For a retry it binds
`request_root` and `commit_attempt.attempt_root`. `to_dict()` embeds the complete
portable permission and commit attempt; `from_dict()` reconstructs both and
revalidates all bindings.

## 5. Deterministic decision and permission semantics

Permission issuance materializes five stages in order: manifest, evidence,
stop, decision, then permission. The issuing grant must include
`ISSUE_ACTION_PERMISSION`, `QUALIFY_EVIDENCE`, and `RESOLVE_STOP`; quorum mode
also requires `EVALUATE_QUORUM`. Verified signals were separately committed
under `VERIFY_SIGNAL` authority.

Decision evaluation is deterministic:

1. If the requested action is blocked, choose the declared safe fallback and
   emit terminal `blocked`.
2. In `direct_governance`, validate and choose `proposed_candidate_ref`, then
   emit `evidence_commit`.
3. In `quorum`, count distinct `source_ref` values per candidate. Rank by
   descending source count and then candidate reference. The first candidate
   reaching `commit_threshold` becomes `evidence_commit`; otherwise choose the
   safe fallback and emit `safe_fallback`.

Governance authorizes the permission only when all three conditions hold:

- the terminal is `evidence_commit` or `safe_fallback`;
- the exact action policy includes that terminal in `allowed_outcomes`; and
- qualified evidence is non-empty; for `evidence_commit`, at least one verified
  signal supports the selected candidate, while any verified signal is enough
  for a safe fallback.

Thus a direct decision or fallback remains deliverable when evidence is absent,
but it does not authorize an external action. `blocked` is always denied.

## 6. Durable states, read-sets, and currentness

Each successful stage writes one stream and one exact state snapshot:

<!-- baseline-output-v2-state-stages:start -->
| Role | Durable schema | Trace event | Session operation |
| --- | --- | --- | --- |
| Manifest | `pheroos-governance-baseline-manifest-state-v2` | `baseline_manifest_activated` | `issue_action_permission` |
| Evidence | `pheroos-governance-baseline-evidence-state-v2` | `baseline_evidence_qualified` | `issue_action_permission` |
| Stop | `pheroos-governance-baseline-stop-state-v2` | `baseline_stop_resolved` | `issue_action_permission` |
| Decision | `pheroos-governance-baseline-decision-state-v2` | `baseline_decision_evaluated` | `issue_action_permission` |
| Permission | `pheroos-governance-baseline-action-permission-state-v2` | `baseline_action_permission_issued` | `issue_action_permission` |
| Output | `pheroos-governance-baseline-output-state-v2` | `baseline_output_committed` | `authorize_output` |
<!-- baseline-output-v2-state-stages:end -->

The exact state key sets are:

| Role | Exact state keys |
| --- | --- |
| Manifest | `schema`, `domain_root`, `scope_ref`, `stream_ref`, `protocol_ref`, `manifest`, `manifest_root`, `output_policy_root`, `request_root`, `session_binding` |
| Evidence | `schema`, `domain_root`, `scope_ref`, `stream_ref`, `request_root`, `manifest_root`, `output_policy_root`, `target_ref`, `signals`, `qualified_signal_count`, `evidence_root`, `session_binding` |
| Stop | `schema`, `domain_root`, `scope_ref`, `stream_ref`, `request_root`, `manifest_root`, `output_policy_root`, `target_ref`, `resolutions`, `stop_root`, `session_binding` |
| Decision | `schema`, `domain_root`, `scope_ref`, `stream_ref`, `request_root`, `manifest_root`, `output_policy_root`, `target_ref`, `candidate_ref`, `terminal_status`, `evidence_root`, `stop_root`, `decision_root`, `session_binding` |
| Permission | `schema`, `domain_root`, `scope_ref`, `stream_ref`, `request_root`, `output_payload_root`, `permission`, `permission_root`, `session_binding` |
| Output | `schema`, `domain_root`, `scope_ref`, `stream_ref`, `request_root`, `output_payload_root`, `manifest_root`, `output_policy_root`, `evidence_root`, `stop_root`, `decision_root`, `candidate_ref`, `terminal_status`, `permission`, `permission_root`, `result_root`, `delivery_disposition`, `action_disposition`, `session_binding` |

Every commit uses one write head and the complete dependency set below. `own`
means the stage's write-stream head. Grant and lifecycle entries are the exact
revision/root preconditions captured by the opaque session.

<!-- baseline-output-v2-read-sets:start -->
| Role | Exact required streams |
| --- | --- |
| Manifest | `own`, `permission issuer grant`, `domain lifecycle` |
| Evidence | `own`, `manifest`, `each verified-signal stream`, `permission issuer grant`, `domain lifecycle` |
| Stop | `own`, `manifest`, `permission issuer grant`, `domain lifecycle` |
| Decision | `own`, `manifest`, `evidence`, `stop`, `permission issuer grant`, `domain lifecycle` |
| Permission | `own`, `manifest`, `evidence`, `stop`, `decision`, `permission issuer grant`, `domain lifecycle` |
| Output | `own`, `manifest`, `evidence`, `stop`, `decision`, `permission`, `permission issuer grant if distinct`, `output authorizer grant`, `domain lifecycle` |
<!-- baseline-output-v2-read-sets:end -->

When both sessions use the same grant, the grant dependency appears once.
Read-set entries are unique and unsigned UTF-8 sorted. Their revisions and head
roots, the write precondition, the read-set root, state, and one Trace event are
validated and committed in one StateStore atomic boundary. There is no
check-then-write publication gap.

Before final commit, Governance reloads all five durable prerequisite states,
recomputes the decision, checks the complete permission binding and expiry, and
validates the permission issuer grant. The output batch then reads those five
heads, both applicable grant heads, the lifecycle head, and its own write head.

Exact transition retry reconciles to the same committed receipt only when the
durable state and session binding match. A stale atomic read-set returns a
bounded retry result; core does not sleep, poll, or loop. After restart, the same
matrix and durable heads produce the same reconciliation behavior.

Current external action authority is stricter than historical delivery. The
result exposes `authorization` only if:

- the permission disposition is authorized;
- the output commit position is `CURRENT`;
- the current permission state still contains the exact `permission_root`;
- the output state contains the same root; and
- every output read-set dependency other than the output write stream still has
  its exact revision and head root.

A successor output, permission/dependency successor, issuer-grant revocation,
or domain seal may leave a committed result historically deliverable while
making `action_disposition=denied` and `authorization=None`.

Recovery proves the historical fact committed by the selected StateStore; it
does not restore authority from portable bytes. Action authorization is exposed
only when the recovered output is `CURRENT`, the permission is valid at the
request-bound logical `observed_epoch`, the current permission state still
contains the exact permission root, and every original non-output read-set
dependency remains at its committed revision and head root. A historical,
superseded, sealed, expired, revoked, or dependency-stale output therefore
remains terminal and deliverable but is never reconstructed as current
authority.

## 7. Delivery and action reachability

Delivery and external action are independent dimensions. `deliverable` means a
caller can inspect a terminal Governance envelope; it never means that the
payload may be published or executed.

<!-- baseline-output-v2-terminal-matrix:start -->
| Terminal status | Delivery disposition | Durable business output | Action disposition | Candidate |
| --- | --- | --- | --- | --- |
| `evidence_commit` | `deliverable` | committed when the output attempt commits | authorized only when policy, evidence, permission, inclusion, and currentness all pass | declared selected candidate |
| `safe_fallback` | `deliverable` | committed when the output attempt commits | authorized only when fallback is allowed and verified evidence, permission, inclusion, and currentness all pass | declared safe fallback |
| `blocked` | `deliverable` | committed Governance terminal output | always denied | declared safe fallback |
| `invalid` | `deliverable` | no; diagnostic envelope, not a committed business output | denied | known decision candidate or declared safe fallback |
| `finality_unavailable` | `deliverable` | no; diagnostic envelope, not a committed business output | denied | known decision candidate or declared safe fallback |
| `None` | `retry_required` | no; nonterminal retry envelope | denied | `None` |
<!-- baseline-output-v2-terminal-matrix:end -->

`invalid` and `finality_unavailable` carry the underlying failed commit attempt
and a deterministic result root, but they do not fabricate output inclusion or
emit `baseline_output_committed`. A retry has neither terminal status nor
candidate and must be retried by the caller with a newly valid session/read-set.
No failure lane downgrades to legacy v1.

## 8. Trace ABI and v1 isolation

The manifest must include all six event types below. A fresh full
materialization emits one of each:

<!-- baseline-output-v2-trace-events:start -->
```text
baseline_manifest_activated
baseline_evidence_qualified
baseline_stop_resolved
baseline_decision_evaluated
baseline_action_permission_issued
baseline_output_committed
```
<!-- baseline-output-v2-trace-events:end -->

Trace owns these provider-neutral lineage contracts in
`pheroos.trace._contracts.authority` without importing Governance. Every event
uses `protocol_id=pheroos.protocol.v2` and binds domain, scope, stream,
transition, run, request/root, grant/root/binding, operation, observed epoch,
session binding, target/action, manifest root, and output policy root.

The first five events require `operation=issue_action_permission`; the final
event requires `operation=authorize_output`. Evidence adds evidence root/count;
stop adds stop root; decision adds evidence/stop/decision roots, candidate, and
terminal; permission adds effect, payload/permission roots, disposition, and
expiry; output adds effect, payload/permission/result/read-set roots and both
delivery and action dispositions. `blocked` must be denied.

`baseline_action_permission_issued` is the only permission event added by this
ABI. The legacy v1 bare `action_permission_issued` event remains owned by
`pheroos.trace.commit_contracts` with its original lineage and behavior. The two
names are not aliases and must not be renamed into one another.

An already matching active manifest and an exact transition retry may reuse or
reconcile their durable transition; they do not append duplicate Trace events.
The six names are the required event set, not a requirement to rewrite an
unchanged manifest for every output request.

## 9. Conformance and compatibility

`run_governance_baseline_output_conformance_v2` exposes the exact version
`pheroos-baseline-output-conformance-v2`. The same provider-free, network-free,
no-skip matrix runs unchanged against both the reference StateStore adapter and
the independent stdlib adapter. It verifies:

- explicit Protocol/capability v3 selection and rejection of cross-selector
  shape inference;
- quorum evidence commit, direct Governance, safe fallback, and blocked paths;
- permission issuance as a separate prerequisite to output;
- exact schemas, durable roots, six stage states, complete sorted read-sets,
  current inclusion, and one valid Trace event per stage;
- proposal substitution resistance for candidate, source, and provenance;
- exact retry and read-only recovery across restart, successor currentness,
  historical denial, and independent-Store recovery of fallback/blocked
  delivery without authority; and
- adapter version/protocol rejection through one total `CheckResult` boundary.

Conformance composes only public Protocol, Governance, StateStore, and Trace
surfaces; it is not a second private decision oracle. An adapter that passes the
matrix proves compatibility with this Draft local contract. It does not become
an identity provider, effect executor, database service, or authenticated
production authority by implication.

Legacy v1 manifests, APIs, and the bare v1 permission event remain unchanged.
Migration to this surface requires explicit schema v3 selection and construction
of the exact v2 request/session journey described here.
