# Runtime Integration Contract

PheroOS protocol-core defines the ABI boundary for external multi-agent runtimes.

It does not implement the runtime.

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

Directly constructed Python records do not bypass the boundary. Governance
entry points reject booleans used as numbers, non-finite values, invalid
bounds, undeclared subjects or candidates, cross-target records, and incomplete
lineage. Public frozen records defensively snapshot nested lists and mappings
at their trust boundary; a runtime should still treat submitted records as
immutable.

## Trace Extensions

Trace events use canonical built-in event types or namespaced extension event types.

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

## Pheromone Workflow

Pheromone is bounded collective memory.

External runtimes may store pheromone history outside protocol-core, then pass current trails into governance reference functions.

Basic swarm runtimes may use the smaller collective helpers. Hybrid runtimes
should use the complete pure reference entry point:

```text
evaluate_hybrid_collective_step(
    protocol_id,
    candidate_set,
    policy,
    target,
    current_step,
    ...
) -> HybridCollectiveStep
```

Its inputs include governance-verified scout, recruitment, and inhibition
records; existing and newly deposited trails; declared topology; feedback;
layer proposals, snapshots, and strategy biases; bounded adjustment proposals;
and, for a subsequent step, a governance-issued `HybridReplayState`. The
function validates batches before applying any state
transition and performs the declared adjustment, deposit, evaporation, diffusion,
reinforcement, response, L1-L4 coordination, scoring, independent-scout gate,
and commit-or-safe-fallback order.

The Draft ABI keeps two explicitly different bounded exploration controls.
`pheromone_exploration_floor` supplies a response baseline for non-negative
sub-floor pheromone scores. `exploration_floor` supplies additional novelty
pressure only when `exploration_enabled` is declared. Neither bypasses the
independent-scout gate, and both are constrained to `[0, 1]`.
Novelty trails do not score when exploration is disabled. In the complete step,
novelty decay is folded into evaporation before lifecycle timestamps advance.

The result contains `decision`, `state`, `active_trails`,
`layer_coordination`, `adjustment_overlay`, `effective_policy`, deposit,
evaporation, diffusion, and reinforcement lifecycle record tuples, exploration
observations, processed replay identities, and `budget_state`. Its
`trace_events: tuple[TraceEvent, ...]` contains the canonical events to persist;
do not synthesize an expire, fallback, reinforcement, or other lifecycle event
when that transition did not occur.

To continue a Hybrid run, call
`replay_state_from_hybrid_step(previous_step)` and pass the result as
`replay_state` to the next complete step. Raw `processed_*` identity sets are
not authoritative, and caller-provided `existing_trails` cannot replace memory
inside an issued replay state. `HybridReplayState` and `HybridCollectiveStep`
constructors remain public ABI shapes, but only instances issued by governance
are accepted at this trust boundary.
Issued replay state also carries disjoint immutable payload receipts for
deposit, diffusion, feedback, and adjustment lifecycles. Reusing an id is
idempotent only when the complete ABI payload is the same; changing a subject,
outcome, strength, topology attenuation, provenance, or adjustment fails
closed. `replay_ignored` trace lineage includes the complete canonical
`replay_payload` and both payload fingerprints. Trace validation recomputes the
current fingerprint, while actual-trace conformance additionally requires the
matching governance-issued prior `HybridReplayState`; two matching
caller-authored digest strings are not proof of prior processing.

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

The manifest declaration type is
`pheroos.protocol.PheromoneKindProfile`. The
`pheroos.governance.PheromoneKindProfile` compatibility export is the same
type; runtimes should use the protocol owner for new imports.

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

Baseline protocols do not need swarm behavior.

Swarm-specific validation and conformance apply only when a manifest declares a swarm collective mode.

Hybrid declarations select `pheroos-hybrid-swarm-v1`, which composes the core,
swarm, and Hybrid checks. Basic swarm manifests remain on
`pheroos-swarm-v1`, and baseline governed manifests remain on
`pheroos-core-v1` without Hybrid-only fields.

See [hybrid-pheromone-v1-migration.md](hybrid-pheromone-v1-migration.md) for the
draft Hybrid v1 consumer migration sequence.

External runtimes should use conformance to prove that their manifests and ABI usage remain compatible with protocol-core.
