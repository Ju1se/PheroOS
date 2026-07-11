# Adaptive Pheromone Core Plan

This document defines how PheroOS should keep pheromone support simple inside
`protocol-core` while preserving a strong extension path for future
machine-learning or reinforcement-learning driven pheromone runtimes.

The plan is intentionally protocol-core scoped. It does not propose adding an
ML runtime, RL trainer, agent colony, environment simulator, model provider,
server, database, queue, dashboard, or worker system to this repository.

## 1. Design Position

PheroOS core should treat pheromone as a deterministic, traceable collective
memory signal.

Pheromone may influence:

- candidate scoring
- route preference
- recruitment pressure
- inhibition pressure
- exploration pressure
- layer proposal coordination
- safe fallback pressure

Pheromone must not become:

- evidence
- authority
- candidate declaration
- quorum by itself
- output authorization
- runtime memory storage
- an agent framework
- an ML or RL execution loop

The core rule remains:

```text
Agents are not authority.
Protocol is authority.
Pheromone is collective memory, not authority.
```

## 2. Current Code Baseline

The current implementation already exposes the main ABI pieces required for a
simple pheromone core and future adaptive runtimes.

Protocol ABI:

- `CollectiveDecisionPolicy`
- `PheromoneKindProfile`
- `pheromone_scored_subject_types`
- `pheromone_kind_profiles`
- `pheromone_response_model`
- `pheromone_diffusion_enabled`
- `pheromone_feedback_enabled`
- `layer_coordination_enabled`
- `policy_adjustment_bounds`

Governance ABI:

- `PheromoneTrail`
- `PheromonePolicy`
- `PheromoneSubject`
- `PheromoneNeighborhood`
- `PheromoneEdge`
- `PheromoneDiffusionPolicy`
- `PheromoneFeedback`
- `LayerProposal`
- `LayerCoordinationPolicy`
- `LayerCoordinationState`
- `PolicyAdjustmentProposal`
- `CollectiveDecisionState`

Reference functions:

- `deposit_pheromone(...)`
- `evaporate_trails(...)`
- `diffuse_pheromone_trails(...)`
- `reinforce_pheromone_trails(...)`
- `score_pheromone_trails(...)`
- `score_pheromone_trails_with_breakdown(...)`
- `evaluate_layer_coordination(...)`
- `validate_policy_adjustment_proposal(...)`
- `score_candidates(...)`
- `evaluate_collective_decision(...)`

Conformance already includes checks for pheromone policy, behavior, subject
scoring, kind profiles, diffusion, reinforcement, response models, layer
coordination, policy adjustment bounds, hybrid trace contracts, and hybrid
authority boundaries.

## 3. Target Shape

The pheromone subsystem should be organized conceptually into two layers:

```text
Basic Pheromone Core
  - simple deterministic candidate pheromone
  - deposit
  - evaporation
  - expiry
  - scoring
  - score breakdown
  - trace lineage
  - conformance

Hybrid / Adaptive Extension ABI
  - route/tool/agent subject scoring
  - diffusion over declared topology
  - feedback reinforcement
  - nonlinear response models
  - layer proposals
  - bounded policy adjustment proposals
  - external ML/RL compatibility
```

The default behavior should remain the Basic Pheromone Core.

Hybrid and adaptive behavior should activate only when a manifest explicitly
declares it.

## 4. Basic Pheromone Core

The Basic Pheromone Core is the minimal protocol-level pheromone feature set.
It should remain small, deterministic, and easy to reason about.

### 4.1 Default Policy

Default collective pheromone behavior should be:

```text
pheromone_enabled: false unless explicitly declared
pheromone_scored_subject_types: ["candidate"]
pheromone_response_model: "linear"
pheromone_competition_mode: "none"
pheromone_diffusion_enabled: false
pheromone_feedback_enabled: false
layer_coordination_enabled: false
```

This means baseline protocols are not forced to become swarm protocols, and
basic swarm protocols are not forced to become hybrid adaptive protocols.

### 4.2 Minimal Lifecycle

The core pheromone lifecycle should remain:

```text
declare policy
-> validate trail
-> deposit
-> evaporate
-> expire stale trails
-> score declared candidates
-> expose score breakdown
-> evaluate collective decision
-> emit trace lineage
```

This lifecycle should be the first path maintained by tests and conformance.

### 4.3 Minimal Objects

The minimal stable object set is:

- `PheromoneTrail`
- `PheromonePolicy`
- `PheromoneKindProfile`
- `CollectiveDecisionState`

The minimal stable function set is:

- `validate_pheromone_trail(...)`
- `deposit_pheromone(...)`
- `evaporate_trails(...)`
- `score_pheromone_trails(...)`
- `score_pheromone_trails_with_breakdown(...)`
- `score_candidates(...)`
- `evaluate_collective_decision(...)`

### 4.4 Minimal Kinds

The built-in pheromone kinds should stay:

- `positive`
- `negative`
- `cautionary`
- `alarm`
- `novelty`
- `stale`

Kind semantics:

- `positive` increases support for a declared candidate or candidate-bound
  subject.
- `negative` decreases support.
- `cautionary` applies risk pressure and may suppress positive support.
- `alarm` applies high-priority emergency pressure and should favor caution or
  fallback, not direct output.
- `novelty` adds bounded exploration support.
- `stale` is expired memory and must not score.

### 4.5 Minimal Subjects

The built-in subject types should stay:

- `candidate`
- `route`
- `tool`
- `evidence`
- `agent`

Default scoring should be candidate-only:

```text
pheromone_scored_subject_types = ["candidate"]
```

Rules:

- `candidate` pheromone can directly influence that declared candidate.
- `route` pheromone may influence a candidate only when the trail is bound to a
  declared candidate and the manifest allows route scoring.
- `tool` pheromone may influence preference only when declared; it must not
  commit a candidate.
- `evidence` pheromone records reference memory only; it must not create
  evidence and must never score. Protocol validation rejects `evidence` in
  policy-wide and per-kind scored-subject declarations.
- `agent` pheromone records source reliability or collaboration memory; it must
  not grant authority.
- Unknown namespaced subject types are metadata by default and must not score
  unless explicitly declared by protocol policy.

Built-in kinds may inherit the policy-wide scored-subject declaration. A
namespaced extension kind is metadata-only unless its own kind profile has a
non-empty `scored_subject_types`; merely adding a profile object does not opt
the extension kind into scoring.

## 5. Core Invariants

The most important optimization is not adding smarter behavior. It is making
the core invariants clearer and harder to bypass.

Pheromone must not:

- create a candidate
- create evidence
- grant authority
- bypass the independent scout gate
- bypass quorum thresholds
- bypass safe fallback
- authorize output
- disable trace requirements
- mutate the manifest
- change output policy
- change evidence policy
- change declared fallback candidates

Pheromone must:

- reference declared candidates when candidate-bound
- carry provenance when policy requires provenance
- carry trace lineage when policy requires trace
- remain bounded by min/max strength
- remain bounded by per-source contribution caps
- remain bounded by per-round deposit caps
- respect source diversity requirements
- expire to `stale` when TTL requires it
- produce deterministic scores
- expose reconstructable score breakdowns

These invariants are more important than any future learning algorithm.

## 6. Score Breakdown as Protocol Semantics

`score_breakdown` should become a first-class protocol concept rather than
incidental debugging data.

Each candidate score should be reconstructable from categories such as:

```text
scout
recruitment
inhibition
pheromone_positive
pheromone_negative
pheromone_cautionary
pheromone_alarm
pheromone_novelty
pheromone_route
pheromone_tool
pheromone_agent
layer_reactive
layer_learned
layer_evolutionary
layer_metacognitive
```

Required property:

```text
sum(score_breakdown[candidate_id].values()) == scores[candidate_id]
```

This matters for three reasons:

1. Governance remains explainable.
2. Trace records can reconstruct why a decision happened.
3. Future external learners can replay decisions without needing hidden state.

## 7. Trace Requirements

Trace should explain how pheromone influenced a collective decision. It should
not become a database, queue, monitor, or runtime event bus.

The trace ABI should support these lifecycle events:

- `pheromone_deposit`
- `pheromone_evaporate`
- `pheromone_clip`
- `pheromone_expire`
- `pheromone_score`
- `candidate_score`

Hybrid/adaptive behavior should add:

- `pheromone_observe`
- `pheromone_diffuse`
- `pheromone_reinforce`
- `pheromone_normalize`
- `layer_proposal`
- `coordination_assess`
- `coordination_resolve`
- `policy_adjustment`

Recommended trace lineage fields:

- `candidate_id`
- `subject_type`
- `subject_id`
- `kind`
- `source_id`
- `evidence_id`
- `provenance`
- `trace_event_id`
- `old_strength`
- `new_strength`
- `step`
- `score_delta`
- `score_breakdown`
- `fallback_used`
- `resolution`

Trace records must remain observational. They do not become evidence or
authority.

## 8. Hybrid / Adaptive Extension ABI

The Hybrid / Adaptive Extension ABI is the forward-compatible surface for
stronger runtime behavior, including ML/RL-driven pheromone systems.

It should remain an ABI, not an implementation of learning.

### 8.1 Diffusion

Diffusion is optional and deterministic.

Core may define:

- `PheromoneSubject`
- `PheromoneNeighborhood`
- `PheromoneEdge`
- `PheromoneDiffusionPolicy`
- `validate_pheromone_topology(...)`
- `diffuse_pheromone_trails(...)`

Core must not simulate physical space, environment dynamics, or agent motion.

External runtimes may map their world model to a declared subject graph. Core
only validates and propagates along that graph.

Diffusion rules:

- Edges must reference declared subjects.
- Candidate-bound subjects must reference declared candidates.
- Attenuation must be bounded.
- Hop count must be bounded.
- Diffusion must not create undeclared candidates.
- Diffused trails inherit provenance and trace lineage.

### 8.2 Feedback Reinforcement

Feedback reinforcement is optional and deterministic.

Core may accept `PheromoneFeedback` from an external runtime or learner.

Supported outcome mapping:

```text
success          -> positive
failure          -> negative
blocked          -> cautionary
congested        -> cautionary
hazard           -> alarm
novel            -> novelty
stale            -> stale
```

Feedback rules:

- Feedback must reference declared subjects and candidates when candidate-bound.
- Feedback must carry provenance when required.
- Feedback must carry trace lineage when required.
- Feedback must remain bounded by per-round and per-source caps.
- Feedback must not create evidence.
- Feedback must not directly commit a candidate.
- Feedback must not authorize output.

### 8.3 Nonlinear Response

Response models are optional scoring transforms.

Supported response models:

- `linear`
- `saturating`
- `threshold`
- `competitive`

Rules:

- Response models affect score only.
- They must not affect evidence, authority, candidate declaration, fallback, or
  output authorization.
- Saturation should prevent runaway positive feedback.
- Thresholds should prevent weak noise from scoring.
- Competitive normalization should keep relative preference meaningful without
  raising all candidates together.

### 8.4 Layer Proposals

Layer proposals are optional score inputs from external runtime layers.

Supported layer IDs:

- `reactive`
- `learned`
- `evolutionary`
- `metacognitive`

`LayerProposal` may express:

- confidence
- support
- risk
- candidate preference
- proposed pheromone kind
- proposed strength
- evidence reference
- provenance
- trace lineage

Rules:

- Proposals may influence score.
- Proposals must reference declared candidates when candidate-bound.
- Learned, evolutionary, and metacognitive layers may propose, not decide.
- Reactive emergency proposals may increase alarm or fallback pressure, not
  output authority.
- Unresolved conflict should use the declared safe fallback when the policy
  requires fallback.

### 8.5 Policy Adjustment Proposals

Policy adjustment is optional and bounded.

External adaptive runtimes may propose run-scoped changes such as:

- evaporation rate
- kind weight
- response model
- exploration floor
- layer weight hint

All changes must stay inside manifest-declared `policy_adjustment_bounds`.

Policy adjustment must not allow changes to:

- declared candidates
- safe fallback
- fallback candidate
- trace requirements
- provenance requirements
- evidence policy
- output policy
- publication permission requirements

The manifest remains the authority. Policy adjustment is a bounded proposal,
not a manifest rewrite.

## 9. External ML/RL Compatibility

Future ML/RL systems should be implemented outside protocol-core.

The recommended external runtime role is:

```text
read trace
-> reconstruct episode
-> compute reward
-> generate feedback/proposals/adjustments
-> submit to protocol-core ABI
-> let governance validate and decide
```

External ML/RL output should be limited to:

- `PheromoneFeedback[]`
- `LayerProposal[]`
- `PolicyAdjustmentProposal[]`

The external learner may decide:

- which route seems successful
- which candidate needs caution
- which layer has performed well
- which bounded parameter adjustment to propose
- which feedback outcome and strength delta to emit

The external learner must not decide:

- final committed candidate
- evidence truth
- authority level
- publication permission
- safe fallback override
- manifest mutation

## 10. External Runtime Record Contract

External adaptive runtimes should integrate by producing protocol-core records,
not by calling private internals or mutating manifests.

The runtime-facing contract is:

```text
inputs read from protocol-core ABI:
  - manifest-declared CollectiveDecisionPolicy
  - trace events

inputs owned by the external runtime:
  - prior PheromoneTrail records
  - optional decision outcome labels
  - optional private learner state

outputs submitted to protocol-core:
  - PheromoneFeedback[]
  - LayerProposal[]
  - PolicyAdjustmentProposal[]
```

The external runtime may maintain private state, learned parameters, reward
tables, replay buffers, or model weights outside protocol-core. None of that
state becomes protocol authority. Only the records submitted through the ABI are
visible to governance.

### 10.1 Feedback Record Rules

`PheromoneFeedback` is the preferred bridge from outcome learning to pheromone
memory.

Required properties:

- `source_id` identifies the adaptive runtime, agent, layer, or replay source.
- `subject_type` and `subject_id` identify the pheromone subject being updated.
- `candidate_id` is required when the subject is candidate-bound.
- `target` must match a declared protocol target.
- `outcome` must use a supported outcome value.
- `reward` and `strength_delta` must be bounded before reinforcement.
- `evidence_id`, `provenance`, and `trace_event_id` must be present whenever
  the active policy requires provenance and trace lineage.
- `step` must be deterministic and non-negative.

Governance applies outcome mapping, clipping, candidate validation, provenance
validation, trace validation, and caps. The runtime does not get to directly
write final pheromone strength.

### 10.2 Layer Proposal Record Rules

`LayerProposal` is the preferred bridge from learned, evolutionary, reactive, or
metacognitive evaluation to collective decision scoring.

Required properties:

- `layer_id` must be one of `reactive`, `learned`, `evolutionary`, or
  `metacognitive`.
- `target` must match the active declared target.
- `candidate_id` must reference a declared candidate when present.
- `confidence`, `support`, `risk`, and `proposed_strength` must be
  non-negative.
- `provenance` and `trace_event_id` are required for traceable coordination.

Governance may weight layer proposals and include them in score breakdowns.
Layer proposals cannot commit candidates, create evidence, authorize output, or
change protocol policy.

### 10.3 Policy Adjustment Record Rules

`PolicyAdjustmentProposal` is the preferred bridge from adaptive optimization
to bounded run-scoped policy changes.

Required properties:

- `layer_id` must be `learned`, `evolutionary`, or `metacognitive`.
- `reactive` layers cannot propose policy adjustment.
- `adjustments` must reference keys declared in `policy_adjustment_bounds`.
- each proposed value must stay inside its declared numeric range or allowed
  value set.
- `provenance` and `trace_event_id` are required.

Policy adjustment must remain run-scoped. It should not rewrite the manifest,
change declared candidates, change safe fallback, weaken trace requirements,
weaken evidence requirements, or weaken output authorization.

### 10.4 Stable Integration Boundary

External runtimes should treat protocol-core as a validator and governance
authority, not as an object store or scheduler.

Allowed integration:

```text
load manifest
-> read policy bounds
-> generate ABI records
-> call public governance functions
-> append trace events
-> run conformance
```

Disallowed integration:

```text
modify manifest at runtime
-> patch candidate declarations
-> bypass validate_* functions
-> write committed decisions directly
-> treat reward as evidence
-> call provider SDKs from protocol-core
-> persist learner state inside protocol-core
```

## 11. Recommended Adaptive Runtime Evolution

Do not start with full reinforcement learning.

The recommended evolution path is:

```text
1. Deterministic trace replay learner
2. Rule-based reward model
3. Contextual bandit
4. Offline RL
5. Guarded online RL
```

### 11.1 Trace Replay Learner

The first external adaptive runtime should be deterministic.

Responsibilities:

- read trace records
- group them into decision episodes
- identify committed candidate or fallback
- identify referenced routes, tools, agents, and evidence
- compute deterministic outcome labels
- emit `PheromoneFeedback`

Example output:

```text
commit candidate:alpha succeeded using route:alpha
-> PheromoneFeedback(outcome="success", subject_type="route", subject_id="route:alpha")

candidate:beta caused fallback or congestion
-> PheromoneFeedback(outcome="congested", subject_type="route", subject_id="route:beta")
```

### 11.2 Rule-Based Reward Model

Before ML, define deterministic reward rules.

Example reward mapping:

```text
success: +1.0
fallback: -0.2
blocked: -0.5
hazard: -1.0
missing_evidence: -0.4
trace_complete: +0.1
conflict_resolved: +0.2
```

The reward model should generate bounded feedback strength. It should not
directly alter governance.

### 11.3 Contextual Bandit

A contextual bandit is a better first adaptive algorithm than full RL.

Possible arms:

- candidate
- route
- tool
- agent source
- layer weight profile
- pheromone kind profile

Possible context fields:

- target
- candidate_id
- route_id
- source_id
- recent success rate
- recent fallback rate
- recent conflict rate
- evidence coverage
- trace coverage

Bandit output should still be ABI records:

- `PheromoneFeedback`
- `LayerProposal`
- `PolicyAdjustmentProposal`

### 11.4 Offline RL

Offline RL should only be considered after:

- trace episodes are stable
- reward definitions are stable
- conformance boundaries are strong
- failure paths are replayable
- policy outputs can be validated offline

### 11.5 Guarded Online RL

Online RL should be the last step.

It must remain guarded by:

- manifest-declared bounds
- provenance requirements
- trace requirements
- conformance checks
- rollback or fallback behavior
- no direct commit authority

## 12. Internal Cohesion Plan

The current public API can remain stable while implementation cohesion improves.

Recommended internal organization:

```text
pheroos/governance/collective.py
  - scout/recruitment/inhibition scoring
  - collective state evaluation
  - commit or fallback decision

pheroos/governance/pheromone.py
  - PheromoneTrail
  - PheromonePolicy
  - PheromoneSubject
  - PheromoneNeighborhood
  - PheromoneEdge
  - deposit
  - evaporation
  - expiry
  - scoring
  - score breakdown
  - diffusion validation
  - deterministic propagation

pheroos/governance/pheromone_feedback.py
  - PheromoneFeedback
  - feedback validation
  - reinforcement mapping

pheroos/governance/layer_coordination.py
  - LayerProposal
  - LayerCoordinationPolicy
  - conflict detection
  - layer weighting
  - safe fallback resolution

pheroos/governance/policy_adjustment.py
  - PolicyAdjustmentProposal
  - bounds validation
```

`pheroos.governance` should continue to re-export the public ABI names.

This keeps core internally cohesive while preserving a low-coupling external
API.

Diffusion is intentionally kept with the core pheromone module for now. It uses
the same subject identity helpers, trail validation, clipping, and scoring
breakdown semantics, so splitting it further would add import surface before it
adds protocol clarity.

## 13. Conformance Plan

Conformance should prove both the simple core and the adaptive extension
boundary.

Basic pheromone conformance should prove:

- candidate pheromone can score a declared candidate
- non-declared candidate references are rejected
- missing provenance is rejected when required
- missing trace lineage is rejected when required
- stale pheromone does not score
- high pheromone without independent scouts falls back
- pheromone cannot authorize output
- pheromone cannot create evidence

Hybrid/adaptive conformance should prove:

- route/tool/agent scoring is opt-in
- diffusion stays inside declared topology
- feedback reinforcement is bounded
- nonlinear response models are deterministic
- layer proposals cannot commit
- reactive emergency pressure cannot authorize output
- unresolved layer conflicts use declared safe fallback
- policy adjustment cannot change safety-critical invariants
- hybrid trace events are required when hybrid behavior is declared

## 14. Documentation Plan

Documentation should make the boundary obvious:

- `docs/protocol/overview.md` should describe pheromone as protocol-declared
  collective memory.
- `docs/protocol/runtime-integration.md` should explain how external runtimes
  submit feedback, proposals, and bounded adjustments.
- `docs/protocol/hybrid-pheromone-abi.md` should remain the detailed hybrid ABI
  reference.
- This document should guide the core simplification and future adaptive
  runtime path.

Documentation should not include provider setup, model SDK setup, server
deployment, dashboards, or application workflows.

## 15. Near-Term Implementation Roadmap

### Phase 1: Stabilize Basic Core

Goals:

- keep candidate-only pheromone as the default
- ensure simple deposit, evaporation, expiry, and scoring are easy to audit
- make score breakdown reconstructable in tests
- keep swarm behavior opt-in

Acceptance evidence:

- existing toy protocol validates and passes conformance
- existing swarm protocol validates and passes conformance
- basic pheromone tests prove commit/fallback boundaries

### Phase 2: Improve Internal Cohesion

Goals:

- split large governance implementation into cohesive internal modules
- keep public re-exports stable
- preserve behavior during the split

Acceptance evidence:

- no import boundary regression
- full test suite passes
- public API imports continue to work

### Phase 3: Harden Trace and Breakdown

Goals:

- standardize trace lineage fields for pheromone lifecycle events
- ensure `candidate_score` can reconstruct candidate totals
- ensure `pheromone_score` can cite trail lineage

Acceptance evidence:

- tests validate score reconstruction
- conformance fails when required swarm/hybrid trace events are missing

### Phase 4: Harden Adaptive Boundaries

Goals:

- strengthen negative conformance around feedback and policy adjustment
- prove external proposals cannot commit or authorize output
- prove unsafe adjustment fields are rejected

Acceptance evidence:

- conformance covers unsafe adjustment attempts
- conformance covers learned/evolutionary direct-commit attempts
- conformance covers missing provenance and trace lineage

### Phase 5: External Adaptive Runtime Contract

Goals:

- document the external adaptive runtime input/output contract
- provide a provider-free trace replay example outside core runtime concerns
- keep the learner as a proposal generator only

Acceptance evidence:

- example emits `PheromoneFeedback` or `PolicyAdjustmentProposal`
- core validates the records
- governance remains responsible for final decision

Reference example:

- `examples/adaptive-pheromone-replay/replay.py`

## 16. Completion Checklist

Use this checklist to decide whether an implementation or refactor still
matches this plan.

Core behavior:

- Basic candidate pheromone works without hybrid features.
- Baseline protocols remain non-swarm unless they explicitly declare swarm
  behavior.
- Swarm protocols remain non-hybrid unless they explicitly declare hybrid or
  adaptive behavior.
- Pheromone deposit, evaporation, expiry, and scoring are deterministic.
- `stale` pheromone never scores.
- Score breakdown reconstructs candidate totals.

Core boundaries:

- Protocol owns declarations and validation.
- Governance owns scoring, coordination, commit, and fallback semantics.
- Trace owns lineage only.
- Conformance proves compatibility and authority boundaries.
- No provider SDK, model runtime, server, queue, database, scheduler, or learner
  state is added to protocol-core.

Adaptive compatibility:

- External learners can emit `PheromoneFeedback`.
- External learners can emit `LayerProposal`.
- External learners can emit `PolicyAdjustmentProposal`.
- Every adaptive record is validated before it can affect scoring.
- Unsafe policy adjustment keys are rejected.
- Learned, evolutionary, and metacognitive layers propose but do not decide.

Authority boundaries:

- Pheromone cannot create evidence.
- Pheromone cannot declare candidates.
- Pheromone cannot bypass the independent scout gate.
- Pheromone cannot bypass safe fallback.
- Pheromone cannot authorize output.
- External ML/RL output remains proposal data until governance accepts it.

## 17. Success Criteria

The pheromone design is successful when:

- simple pheromone behavior is easy to understand and test
- baseline protocols are not forced into swarm behavior
- swarm protocols are not forced into hybrid adaptive behavior
- score lineage is reconstructable
- conformance proves core authority boundaries
- external ML/RL systems can integrate through ABI records
- no ML/RL implementation is required inside protocol-core
- protocol-core stays deterministic, provider-free, domain-neutral, and small

## 18. Final Guidance

Optimize pheromone in core for protocol quality, not algorithmic ambition.

Prefer:

- explicit ABI objects
- pure functions
- deterministic scoring
- small validation rules
- traceable lifecycle events
- conformance-backed invariants
- provider-free examples

Do not add:

- embedded learning loops
- neural network code
- RL training code
- runtime schedulers
- persistent memory stores
- app-specific agent workflows
- provider gateways

The right long-term shape is:

```text
protocol-core
  - simple deterministic pheromone
  - adaptive extension ABI
  - governance reference semantics
  - trace lineage
  - conformance

external adaptive runtime
  - trace replay
  - reward modeling
  - bandit or ML/RL optimization
  - feedback/proposal/adjustment generation
```

In short:

```text
Keep pheromone simple in core.
Keep adaptive intelligence outside core.
Let protocol-core validate every adaptive influence before it can affect a
collective decision.
```
