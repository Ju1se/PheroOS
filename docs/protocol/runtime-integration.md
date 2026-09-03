# Runtime Integration Contract

PheroOS protocol-core defines the ABI boundary for external multi-agent runtimes.

It does not implement the runtime.

The public positioning is governed authority/commit. The collective and
pheromone workflow described later is a retained private/historical profile;
it does not select a public swarm profile or create a requirement for
baseline conformance.

The Draft exact version-composition artifact and evaluator are documented in
[Runtime Compatibility Manifest v1](../conformance/runtime-compatibility-v1.md).
That manifest does not replace the named implementation TCKs or grant output
authority.

The public-facade and strict-typing boundary for the Draft promotion candidate
is the [Stable Core consumer contract](stable-core-consumer.md). It is a
candidate consumption guide, not a formal Stable or production-runtime claim.

## Integration Shape

External runtimes should compose PheroOS in this order:

```text
manifest
-> protocol validation
-> kernel plan
-> external runtime binds adapters
-> agents produce scout reports, evidence, and signals
-> governance evaluates decision
-> trace records lineage
-> output authorization checks authority boundary
-> conformance proves compatibility
```

## Protocol-Core Responsibilities

Protocol-core owns:

- capability and protocol manifest objects
- structural validation
- kernel planning contracts
- provider-neutral driver declarations
- generic driver lifecycle objects
- governance reference semantics
- collective decision and pheromone reference behavior
- trace event ABI
- conformance checks

Protocol-core does not own:

- agent loops
- model calls
- tool calls
- provider adapters
- database persistence
- vector stores
- memory backends
- queues
- scheduling
- servers
- dashboards
- secret management

## External Runtime Responsibilities

An external runtime may implement:

- agent scheduling
- model-provider calls
- tool invocation
- database or memory persistence
- queueing
- credential loading
- provider-specific adapters
- application-specific workflows

Those implementations must stay outside protocol-core.

When a runtime needs to connect provider-specific configuration, it should use an external configuration reference, not inline secrets in a PheroOS manifest.

## Driver Declarations

Driver declarations are provider-neutral.

They describe what a capability exposes, not how a provider is called.

`config_ref` is an opaque external reference. Protocol-core must not resolve it, read secrets from it, or treat it as authority.

The adapter mapping contract is described in [runtime-adapter-guide.md](runtime-adapter-guide.md).

The hardened Driver ABI normalizes declarations into one immutable
`DriverDescriptor`; registration is idempotent only for the same canonical
descriptor and rejects a conflicting reuse of `driver_id`. A provider-neutral
probe reports availability, version, and capabilities before Kernel planning
can mark a runtime context ready.

For invocation, Kernel `DriverInvokeRequest`/`DriverInvokeReply` and Driver
receipts bind `scope_ref`, invocation id, driver id, operation, required
capability, idempotency key, canonical request digest, result status/payload,
provenance, and digest echo. A result from another scope or request fails
closed, and the same idempotency key cannot be reused with different bytes.
These contracts validate an externally performed call; protocol-core still
does not invoke a provider.

## Management and Service Boundary

“API” in protocol-core means Python ABI, checked JSON schemas, the local CLI,
and the provider-neutral TCK JSONL protocol. The repository exposes no HTTP,
REST, RPC, authentication, rate-limit, remote-routing, or service-discovery
server. An external gateway may provide those facilities, but transport
success never creates evidence, permission, commit, or output authority.

## Extensions

Manifest extensions are metadata.

Extensions may describe external runtime behavior when they are namespaced, traceable, and provider-neutral.

Extensions must not:

- contain API keys, tokens, passwords, credentials, or secrets
- create facts
- commit candidates
- authorize output
- bypass governance
- force baseline protocols to become swarm protocols

Unknown extension metadata is preserved for external runtimes, but protocol-core does not give it authority by default.

## Strict Input Boundary

External runtimes should validate generated or persisted manifests before
turning them into runtime records. The manifest loader applies the checked-in
schema before typed mapping, rejects unknown non-namespaced fields and invalid
typed shapes, and rejects `NaN`, `Infinity`, and `-Infinity`.

Kernel planning uses the same Protocol validation dispatch. A legacy
`CapabilityManifest` retains its v1 validation semantics, while an exact
canonical `ScopedCapabilityManifestV2` is validated through its closed v2
declarations and is never projected onto legacy output-policy fields. Both
manifest generations resolve through `OSKernel.plan(...)` to the existing
Kernel Plan v2 document; Capability schema v3 does not imply or create a Kernel
Plan v3. Unsupported, forged, or non-canonical manifest objects fail closed as
typed diagnostics and cannot expose permissions, connections, or Drivers.

Directly constructed Python records do not bypass the boundary. Governance
entry points reject booleans used as numbers, non-finite values, invalid
bounds, undeclared subjects or candidates, cross-target records, and incomplete
lineage. Public frozen records defensively snapshot nested lists and mappings
at their trust boundary; a runtime should still treat submitted records as
immutable.

## Draft Runtime Integration Transcript v1

The exact local `pheroos.protocol.v2` scoped-authority profile is active as a
Draft protocol-core composition. This transcript does not activate the
authenticated external-verifier profile, make any lifecycle entry Stable, or
provide the external runtime itself.

The provisional `pheroos.conformance.runtime_integration` facade defines an
exact-version, provider-free and expected-free transcript TCK. It composes one
preconstructed request through eight ordered layers:

```text
compatibility -> scope -> protocol -> kernel -> drivers
              -> governance -> output -> trace
```

The adapter must independently re-read Capability schema v3, produce Kernel
Plan v2 for the exact portable `RuntimeScope`, validate and persist Driver
Invocation v2, evaluate Baseline Output v2 or consume a closed Commit v2
observation lane, project action eligibility, and append the seven preceding
steps to Scoped TraceStore v2. The verifier re-runs Kernel planning and
recomputes every stage, predecessor, output, and Trace binding; an adapter's
self-reported root is never sufficient.

Driver checkpoints remain implementation-defined bytes. The transcript carries
their canonical base64url encoding and SHA-256 binding, then calls the
adapter's own checkpoint reader to prove the exact receipt survives restart.
The matrix also requires cross-scope and cross-key misses and rejection of a
byte-tampered checkpoint. This does not standardize a database or checkpoint
format.

Crash recovery is not accepted from `recovered_after_commit` alone. For every
recovery case the adapter must expose the `GovernanceStateReaderV2` created by
its post-commit Store restart, keyed by the exact request root and scope. The
TCK calls `recover_baseline_output_result_v2` itself and requires the complete
recovered result to equal the transcript result. Unknown, cross-request, and
cross-scope lookups must not return a reader. After reopening the recovery
image, the fixture advances one deterministic source-only witness stream. The
TCK requires the returned reader to retain the pre-witness genesis head, so a
reader over the still-live source fails. This proves the checkpoint/reopen
snapshot-isolation invariant without object identity, self-report, or a
process-global registry. It does not claim a fresh operating-system process;
fresh-process interoperability remains the WP12 external-runtime gate.

The certificate cases use exact `CommitFinalityProjectionV2`
observed/successor records generated from the same committed Certificate
states, plus a bound `CommitDecisionOutcomeV2` as portable diagnostic data.
Authority is proved on the opaque path: the adapter commits an observed
Certificate state and, for the stale case, a successor, restarts the
Governance Store, and returns the corresponding
`VerifiedCommitCertificateStateV2` handles. The TCK requires the observed
handle to be stale, the successor handle to be current, and the stale handle's
output action to remain denied. No boolean, projection root, or portable
outcome substitutes for that Store-backed currentness check.
Even a current handle can open the action gate only when its committed stream,
revision, transition, snapshot, receipt, seal, frozen dependencies, and step
exactly bind the declared observation. Mandatory positive cases prove current
Certificate-bound publication and execution separately; unrelated current and
unrelated stale/successor pairs are fail-closed.

The stale permission and stop cases each append one legal same-state successor
to the selected Baseline Output dependency stream. After restart the TCK
compares every head in the complete declared output read set: within that set,
exactly the committed output stream and the selected dependency advance. This
is a precise declared-read-set claim, not a claim that the TCK enumerates every
implementation-global stream; the source-only restart witness is deliberately
outside that read set. The output stays deliverable while current action
authority is denied.

Wall-clock timeout and client cancellation are simultaneous-capable outer
runtime observations. They may prevent Governance evaluation, but neither
advances a protocol logical deadline, commits a candidate, or creates output
authority. A deterministic precedence selects the transcript disposition while
both observations remain present in diagnostics.

The same matrix runs against the protocol-core reference adapter and the
public-facade-only independent fixture in
[`examples/runtime-integration-protocol`](../../examples/runtime-integration-protocol/README.md).
The fixture uses independent stdlib Driver, Trace, and Governance stores and a
different Driver checkpoint format. Echo, constant, malformed, out-of-order,
timeout-ignoring, cross-request-state, cross-scope, self-root, checkpoint-liar,
no-restart-recovery, live-source-reader, unrelated-current-certificate,
unrelated-stale-certificate, stale-permission, stale-stop, stale-certificate,
and action-coupling adapters must fail.

This ABI remains Draft/provisional. It creates no provider, clock, scheduler,
task loop, worker, subprocess controller, server, queue, or database. An HTTP
200 response, provider success, Trace append, or delivery acknowledgement is
an observation only; none is evidence, permission, commit, certificate
currentness, publication authority, or execution authority.

## Optional Optimal Commit Workflow

Optimal Commit is activated only when a manifest declares
`collective_commit_policy`. Manifests that omit it continue to use their
existing core, swarm, or Hybrid profile and result/trace behavior.

For an activated policy, the external runtime is responsible for collecting
proposals and asking governance to issue the exact principal, risk,
membership, observation, challenge, evidence, support-lease, stop, permission,
and replay heads required by the declared assurance. It then assesses the
candidate set, advances the returned commit window with monotonic logical
steps, and calls `evaluate_hybrid_commit_step(request=...)` with the exact
authoritative heads. Hybrid pheromone and layer inputs may guide the next
exploration request, but they cannot enter commit metrics or certificate
truth.

Attention is advisory availability, not a commit gate. If an attention record,
exploration directive, step binding, or candidate coverage is missing or
invalid, the total evaluator returns `attention_status=unavailable`, removes
the advisory projection, and emits a nonfatal structured diagnostic. It still
evaluates the independently valid authority envelope. A runtime may repair the
attention channel at a later step without reopening or downgrading a commit.

Each `CommitEvaluationContext` is an immutable authority snapshot. When
governance accepts new evidence or leases, the runtime first advances the
append-only replay head and then asks governance to issue a new context and
current action gates. The old context never accepts a descendant implicitly.
This snapshot rollover can preserve a ready window when the leader and every
gate remain continuous; replay deletion, substitution, stale use, or a fork is
rejected.

If the evaluator returns `DecisionProgress`, the runtime persists the returned
window/replay/progress heads and follows `next_required_inputs`; it must not
synthesize a heartbeat or extend the absolute deadline. Certified and
distributed runtimes transport issuer or witness attestations externally and
submit them for deterministic verification. The core does not collect
witnesses, poll agents, schedule another step, or advance a clock.

Distributed witnesses sign the full proposal envelope and its semantic
commit-value root. Retrying the same candidate/claim/output and authority roots
with a new proposal or proof-envelope identifier is not equivocation and does
not freeze the epoch. A changed semantic root is a distinct value and remains
subject to quorum-intersection conflict detection and recovery.

Agents may still explore and transport records concurrently. A runtime should
snapshot the governance-issued records accepted for one evaluation into an
immutable step envelope and let one run-scoped coordinator advance the logical
step. Records that arrive after that snapshot are considered for a later step;
they do not mutate an already issued assessment or progress heartbeat. This
serializes only the authority projection, not the agents or their exploration.

Bounded liveness therefore means that continued calls with monotonic logical
steps cannot remain pending beyond the declared deadline. It does not mean
that the core runs in the background, and it does not force an evidence
commit. The terminal result may instead be `safe_fallback`, `advisory`,
`blocked`, `invalid`, `finality_unavailable`, or `safety_violation`. Every
governance-issued terminal outcome can be delivered; publication and execution
still require fresh, action-scoped authority and any assurance-specific
certificate or distributed-finality proof.

The exact activation and call sequence is documented in
[optimal-commit-v1-migration.md](optimal-commit-v1-migration.md).

## Scoped Durable Authority

Each external request should create
`RuntimeScope(tenant_id, run_id, request_id)`. The required `request_id`
identifies that request, while the canonical `scope_ref` is derived from the
tenant/run pair and remains stable across the run. Carry `scope_ref` through
Kernel plans, Driver requests/results, Governance authority domains, and scoped
Trace envelopes. A result from a different scope is not reusable authority,
even when its payload is otherwise byte-identical.

The Runtime Scope v1 JSON Schema is structural, not an authority verifier. It
checks the closed fields, exact version, basic text form, and the
1024-character per-component wire resource bound. A forged but syntactically
valid SHA-256-looking `scope_ref` can therefore pass JSON Schema. Every trusted
reader must call `RuntimeScope.from_dict(...)`, which derives the expected
identity from `tenant_id` and `run_id` and fails closed on mismatch. The typed
reader additionally requires Unicode NFC and Unicode scalar values because
those canonicality rules are not expressible by this JSON Schema. The bound
applies to the portable wire ABI
only: legacy Python constructors can still
hold values that `to_dict()` correctly refuses to make portable.

Durable Governance integration uses the provider-neutral
`GovernanceStateStore` protocol. The core supplies
`InMemoryGovernanceStateStore` only as a deterministic reference and test
adapter; production databases, transactions, replication, retention, and
backup remain external runtime responsibilities.

The authoritative publication sequence is:

```text
evaluate_hybrid_commit_step
-> prepare_hybrid_commit_transition against the current scoped head
-> GovernanceStateStore.atomic_commit(state + trace)
-> verify the store-issued receipt and current head
-> finalize_hybrid_commit_transition
-> expose output only from AtomicHybridCommitStatus.COMMITTED
```

That sequence is the current Draft v1 trusted-host compatibility path. Its
finalize step compares a receipt with the current head, so it does not provide
the historical-inclusion/current-actionability separation reserved for scoped
authority v2. New integrations must not describe the v1 receipt as a portable
credential or production identity proof.

WP-02 now implements the additive Draft StateStore v2 storage/finality slice:
`GovernanceStateStoreV2.atomic_commit_v2(...)`, the atomic canonical read-set,
historical committed-transition lookup, separate dynamic commit-position
inspection, and authority-critical Trace in the same Store commit. Its
provider-free reference and independent adapter are covered by the exact
StateStore v2 Conformance contract. The generic `TraceStore` remains a
reconstructible projection, and these v2 names are not aliases or a silent
upgrade of the current v1 methods.

WP-03 now adds the public Draft non-portable Authority Session v2 slice on top
of StateStore v2. A trusted coordinator activates a portable grant, binds a
store- and run-specific capability, opens a request-specific session, and may
atomically commit a verified-signal fact or domain seal. The session owns the
exact selected writer; it never enters agent context, Driver exposure, wire,
checkpoint, or Trace. The same session matrix passes the reference and
independent stdlib StateStore models.

External runtimes using Baseline Output v2 can avoid custody of those opaque
objects through `evaluate_and_commit_governed_baseline_output_v2(...)`. The
runtime supplies only the versioned Store/domain, portable grant and stable
activation identity/epoch, optional host verifier, exact portable
verified-signal requests, and portable Baseline request. Governance performs
activation reconciliation, fresh binding, signal commits, permission issuance,
and output evaluation/commit internally. An activation epoch later than the
request epoch is rejected before any Store mutation. The result is a portable commit
attempt until the output stage is reached, then a portable Baseline result.
Neither transport success nor the returned object performs an external effect.

An external runtime that needs durable risk authority uses the public
[Risk State v2 ABI](risk-state-v2.md) in one explicit sequence:

```text
exact ScopedProtocolManifestV2 + current Risk parent
-> prepare_risk_state_advance_v2(...) -> portable request + local source proof
-> bind QUALIFY_EVIDENCE capability and open request-bound session
-> advance_risk_state_v2(...) -> atomic state + two closed Trace events
-> serialize only the portable request
-> rehydrate_risk_state_v2(...) against a fresh StateStore reader
-> require_current_risk_state_v2(...) before the next advance
```

Epoch changes advance that same target/run/policy stream and record
`parent_epoch` plus a required window reset; they do not allocate one stream per
epoch. The provider-free [`risk-v2-protocol`](../../examples/risk-v2-protocol/README.md)
example advances from epoch 7 to 137 after a reference Store restart; the
public Conformance lane separately prepares all 130 intervening epoch proposals
and proves they resolve to one stream. The
reference Conformance adapter is test infrastructure, not a production database
or runtime. Portable JSON, roots, or the non-portable source proof alone cannot
authorize risk, commit a candidate, or authorize output.

Capability schema v3 dispatch, the scoped authority manifest, Baseline Output
v2, and their reference/independent conformance paths are now implemented as
Draft ABI. Certified and distributed profiles still require their declared
external issuer/witness verifiers and their own exact composite TCK gates;
using StateStore or Authority Session v2 alone cannot authorize publication or
execution. See
the [authority decision](authority-v2-decision.md),
[threat model](authority-trust-model-v2.md), and
[migration contract](authority-v2-migration.md), plus the exact
[Authority Session v2 contract](authority-session-v2.md).

`evaluate_and_commit_hybrid_step(...)` composes that sequence for an explicit
`AuthorityDomain` and store. A stale compare-and-swap head returns
`retry_required`; injected persistence failure cannot advance state without
Trace; a retired scope stays retired; checkpoint rehydration must reproduce
the same heads, batches, receipts, and tombstones. Non-committed results redact
the proposed evaluation, receipt, and output authority while remaining
diagnostically deliverable when declared.

This ABI is intentionally not a database manager or transaction server. An
external store adapter implements the protocol and must pass the restart,
scope-isolation, idempotency, CAS, atomicity, and retirement conformance matrix.

That matrix is reusable by external implementations. A
`GovernanceStateStoreConformanceAdapter` supplies fresh, checkpoint-restored,
snapshot-restored, and failure-injected stores to
`run_governance_state_store_conformance(...)`. The adapter fixture is test
plumbing only; the production store remains the small `GovernanceStateStore`
Protocol and does not depend on conformance. Fixtures declare
`GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION`; unknown versions fail closed.
The required deterministic injection points are published as
`GOVERNANCE_STATE_STORE_FAILURE_STAGES` rather than hidden test strings.
Concurrent correctness is exercised with 32 workers: all workers retrying one
batch must receive one identical receipt, while conflicting genesis batches
must produce exactly one commit and retry conflicts for every loser. The
worker count is test load, not a provider ABI field.

## Trace Extensions

Trace events use canonical built-in event types or namespaced extension event types.
Persistence is supplied through the provider-neutral `TraceStore` Protocol,
which exposes canonical append and immutable chronological snapshots. An
external backend supplies a `TraceStoreConformanceAdapter` factory to
`run_trace_store_conformance(...)`; the matrix verifies validation-before-write,
ordering, immutable input/output snapshots, fresh-store isolation, and
fail-closed malformed events. Its declared
`TRACE_STORE_CONFORMANCE_VERSION` is exact-version dispatched.

Namespaced trace events are useful for external runtime lineage, but they remain trace records only. They do not become evidence, permission, quorum, or output authority.

## Signal Verification

A signal is not verified because its producer sets a boolean. The external
runtime must ask governance authority to issue a `SignalVerification`, for
example through `verify_signal_input(...)`, and attach that record to the
corresponding quorum, scout, recruitment, or inhibition input.

Verification is bound to one target, source, and subject, and also records the
verifier, governance authority, provenance, and trace event. A missing or
mismatched record fails closed. Only the record returned by
`verify_signal_input(...)` carries governance issuance; directly constructing
or replacing a `SignalVerification`, even with `AuthorityLevel.GOVERNANCE`,
does not create authority. In every swarm mode, scouts additionally require a
non-empty scout identity, evidence identity, provenance, and trace identity;
duplicate scouts are rejected after verification and cannot satisfy the
independent-scout gate.

## Historical/private attention and pheromone workflow

Pheromone is bounded collective memory.

Basic swarm runtimes may use the smaller collective helpers. A Hybrid runtime
that needs authority across calls, processes, or restarts must use the durable
Hybrid Replay v2 journey:

```text
exact ScopedProtocolManifestV2 + authority context + deterministic proposals
-> evaluate_hybrid_collective_step_v2(...) -> VerifiedHybridSourceStepV2
-> build_hybrid_replay_advance_request_v2(...)
-> open_hybrid_replay_authority_session_v2(...)
-> advance_hybrid_replay_state_v2(...) -> atomic State + Trace commit
-> rehydrate_hybrid_replay_state_v2(...) after restart
-> evaluate the next step only from the verified current parent
```

The source proof is non-portable and is bound to the exact domain, scope, run,
epoch, manifest, target, candidates, base and effective policy, topology,
current step, and parent snapshot. The advance operation independently rebuilds
that projection and verifies the complete StateStore read set before committing.
Neither a raw JSON snapshot, digest, checkpoint, pickle, legacy replay record,
nor same-shaped dataclass grants authority. A committed historical snapshot can
be rehydrated for proof; only a Store-verified current head may parent the next
advance. A legal concurrent successor produces a bounded retry, while a fork,
rollback, or substitution fails closed.

The complete step inputs include governance-verified scout, recruitment, and
inhibition records; newly deposited trails; declared topology; feedback; layer
proposals, snapshots, and strategy biases; and bounded adjustment proposals.
The evaluator validates the batch before applying any transition and performs
the declared adjustment, deposit, evaporation, diffusion, reinforcement,
response, L1-L4 coordination, scoring, independent-scout gate, and
commit-or-safe-fallback order.

The Draft ABI keeps two explicitly different bounded exploration controls.
`pheromone_exploration_floor` supplies a response baseline for non-negative
sub-floor pheromone scores. `exploration_floor` supplies additional novelty
pressure only when `exploration_enabled` is declared. Neither bypasses the
independent-scout gate, and both are constrained to `[0, 1]`.
Novelty trails do not score when exploration is disabled. In the complete step,
novelty decay is folded into evaporation before lifecycle timestamps advance.

The verified source step contains `decision`, `state`, `active_trails`,
`layer_coordination`, `adjustment_overlay`, `effective_policy`, deposit,
evaporation, diffusion, and reinforcement lifecycle record tuples, exploration
observations, processed replay identities, and `budget_state`. Its
`trace_events: tuple[TraceEvent, ...]` contains the canonical events to persist;
do not synthesize an expire, fallback, reinforcement, or other lifecycle event
when that transition did not occur.

The durable snapshot carries disjoint immutable payload receipts for
deposit, diffusion, feedback, and adjustment lifecycles. Reusing an id is
idempotent only when the complete ABI payload is the same; changing a subject,
outcome, strength, topology attenuation, provenance, or adjustment fails
closed. Snapshot projections preserve the exact four receipt classes, bounded
active memory, budget, cumulative policy overlay, source lineage, and canonical
roots needed to continue after restart without trusting caller-maintained
processed-id sets.

`evaluate_hybrid_collective_step(...)`, `HybridReplayState`, and
`replay_state_from_hybrid_step(...)` are Deprecated Draft compatibility
surfaces for the earlier process-local path. They remain available during the
declared lifecycle window, but a production integration must not use their
sentinel/registry issuance as a durable trust root.

Every governance-produced rejected deposit, diffusion, or feedback
`pheromone_clip` carries a versioned `causal_payload` and
`causal_fingerprint`. The payload snapshots the complete normalized lifecycle
input (including source/subject/target, evidence and provenance metadata,
strength or feedback delta/reward, timing/TTL, and diffusion edge inputs), and
the fingerprint is computed with
`pheroos.trace.pheromone_clip_payload_fingerprint(...)`. Trace validation
cross-binds that receipt to the event and reconstructs the rejected request.
This digest is an append-only integrity receipt, not evidence, permission,
verification, or commit authority. Applied legacy clip records remain schema
compatible without a receipt; the complete Hybrid reference path emits one for
its bounded deposit clips as well.

Hybrid pheromone runtimes may also pass declared topology, feedback records,
layer proposals, layer performance snapshots, and bounded policy-adjustment
proposals into protocol-core. Protocol-core validates and evaluates those
records as deterministic ABI inputs. It does not run neural learning,
evolutionary optimization, environment simulation, agent colonies, analytics
loops, or background coordination.

Adaptive runtime records must be traceable proposal data:

- `PheromoneFeedback` includes `source_id`, subject identity, target, outcome,
  non-negative `strength_delta`, provenance, trace lineage, and a deterministic
  step.
- Candidate-bound feedback references a declared candidate for the active
  target.
- `LayerProposal` and `PolicyAdjustmentProposal` carry provenance and trace
  lineage before they can affect score or bounded run-scoped policy values.
- `candidate_score` lineage carries `scores`, full `score_breakdown`, scout
  diversity, and pheromone-source diversity. `pheromone_score` independently
  carries reconstructable category, kind, and subject breakdowns plus the
  canonical active-trail/source records. Decision lineage references all
  score-affecting scouts, recruitment, inhibition, accepted adjustments,
  active trails, and layer proposals.
- Accepted global evaporation and response-model overlays take run-scoped
  precedence over per-kind overrides, while leaving the manifest unchanged.
- Built-in authority and Hybrid lifecycle events are validated against the
  event-specific contracts exported by `pheroos.trace`; the same conditional
  contracts are published in `schemas/trace.schema.json`.
- Hybrid conformance causally replays deposit, evaporation/expiry, diffusion,
  and reinforcement—including shared budgets—into `active_trails`. It also
  rebuilds coordination from proposals, strategy biases, complete performance
  snapshots, and the effective adjusted policy instead of trusting reported
  confidence, weights, conflicts, resolution, or layer scores.

Pheromone remains:

- not evidence
- not truth
- not permission
- not quorum
- not output authority

Layer proposals remain proposals. Reactive emergency pressure can create alarm
or fallback pressure, learned and evolutionary layers can bias scores or propose
bounded run-scoped adjustments, and metacognitive coordination can resolve
conflicts only inside declared protocol bounds.

`LayerCoordinationState` is returned by governance and is not an authoritative
Hybrid input. Runtimes migrating from a precomputed state must submit
`LayerProposal`, `LayerPerformanceSnapshot`, and `StrategyBias` records instead;
protocol-core validates and recomputes the coordination state inside the full
step. This prevents learned, evolutionary, reactive, or metacognitive layers
from injecting final scores or commits.

The former manifest declaration type `PheromoneKindProfile` is retained only
inside the private historical implementation. It is not a current public
Protocol or Governance export, and external runtimes must not depend on it.

For scoring, an empty built-in kind profile inherits the policy-wide
`pheromone_scored_subject_types`. A namespaced extension kind does not inherit
that list: it is metadata-only until its own profile declares a non-empty
`scored_subject_types`. `evidence` remains a valid memory subject but is never
score-bearing and must not appear in either scored-subject declaration.

## Output Authorization

After the Hybrid step, the outer runtime calls the output contract separately.
Authorization is fail-closed across four independent gates:

- the decision committed a declared candidate
- evidence is present and carries provenance
- at least one `StopResolution` matches the decision target and none of the
  matching resolutions is blocked
- publication permission is present

A runtime must pass the active protocol-derived `CandidateSet` when evaluating
output. The commit gate requires both a candidate declared for the decision
target and a decision issued by the governance quorum or collective path;
directly constructing `QuorumDecision(committed=True, ...)` cannot authorize
output. The four manifest flags and matching `OutputContract` flags are
mandatory and cannot be set to false.

A resolution for another target cannot approve the active target. It also does
not block that target; only matching resolutions participate in its output
gate. Safe-fallback decisions pass through the same four gates.

## Compatibility

Baseline protocols do not need swarm behavior. Collective and pheromone fields
are optional attention inputs and do not select a public swarm profile. A
manifest without `collective_commit_policy` remains on `pheroos-core-v1`;
attention is advisory and cannot create authority. Commit manifests may opt into
the Hybrid Commit profile when attention inputs are present.

The former Hybrid Pheromone migration note is retained as a historical record,
not as a supported external consumer contract.

External runtimes should use conformance to prove that their manifests and ABI usage remain compatible with protocol-core.
