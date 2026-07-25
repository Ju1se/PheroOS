# PheroOS Hybrid Pheromone ABI Final Plan

This document is the implementation reference for the PheroOS hybrid pheromone
enhancement track. It is intended for Goal-mode execution.

This is not a minimal landing plan and must not be downgraded into a small
candidate-scoring patch. The objective is a full ABI-backed pheromone protocol
for swarm-native multi-agent coordination: external collective memory, local
diffusion, route reinforcement, alarm and cautionary inhibition, feedback-based
adaptation, evolutionary policy adjustment bounds, metacognitive cross-layer
coordination, complete trace lineage, and conformance proof.

The design remains protocol-core scoped. PheroOS core defines contracts,
deterministic governance semantics, trace lineage, conformance, provider-free
examples, and tests. External runtimes implement neural learning, evolutionary
optimization, environment simulation, agent colonies, analytics, and continuous
operation.

## 1. Core Position

Pheromone is a core PheroOS swarm mechanism, but it is not authority.

Pheromone belongs in these core surfaces:

- Protocol ABI: declares pheromone, feedback, diffusion, reinforcement,
  coordination, and policy-adjustment rules.
- Governance Core: defines how pheromone influences candidates, routes,
  recruitment, inhibition, consensus, and fallback.
- Trace ABI: records pheromone lifecycle and cross-layer decision lineage.
- Conformance: proves that pheromone cannot bypass declared candidates, safe
  fallback, evidence, quorum, stop resolution, or output authorization.

Pheromone does not belong in these surfaces:

- model-provider routing
- app runtime code
- neural-network training infrastructure
- evolutionary algorithm executors
- environment simulators
- agent-colony runtimes
- dashboards, servers, queues, daemons, or worker pools

The implementation model is Core + Runtime ABI:

- `protocol-core` implements deterministic ABI, pure governance reference
  behavior, schema, validation, trace, conformance, provider-free examples, and
  tests.
- External runtimes implement the four-layer hybrid intelligence system,
  environment model, agent colony, learning, evolution, monitoring, and
  long-running operation.

## 2. Target Architecture

PheroOS core consumes declarative signals from external runtimes. It does not
run the intelligent ecosystem itself.

```text
External Hybrid Runtime
+-- L1 ReactivePheromoneLayer
|   +-- emergency detector
|   +-- rule engine
|   +-- emits alarm, warning, repulsion, and recruitment proposals
+-- L2 NeuralPheromoneLayer
|   +-- perception
|   +-- evaluation
|   +-- parameter prediction
|   +-- emits learned proposals, feedback, and bounded adjustments
+-- L3 EvolutionaryLayer
|   +-- strategy population
|   +-- fitness evaluation
|   +-- emits strategy bias and bounded policy-adjustment proposals
+-- L4 MetacognitiveCoordinator
|   +-- confidence assessment
|   +-- dynamic weight allocation
|   +-- conflict resolution
|   +-- emits coordination decisions and trace lineage
+-- DynamicPheromoneEcosystem
    +-- environment
    +-- agent colony
    +-- analytics
    +-- runtime-owned learning and evolution loop

PheroOS protocol-core
+-- Protocol ABI
+-- Governance reference functions
+-- Trace ABI
+-- Conformance suite
+-- Provider-free examples
```

Boundary rules:

- L1/L2/L3/L4 layers may emit proposals, feedback, and policy-adjustment
  requests.
- Governance decides how those inputs affect collective decision state.
- Protocol declares which behavior exists and which bounds apply.
- Trace explains every influence path.
- Conformance proves that no signal becomes authority by accident.

## 3. Pheromone Semantics Upgrade

The current implementation supports `candidate`, `route`, `tool`, `evidence`,
and `agent` pheromone subjects, while only candidate pheromone scores by
default. The hybrid ABI upgrades pheromone into multi-subject, diffusive,
reinforceable, competitive swarm memory.

### 3.1 Pheromone Subjects

Retain the existing subject types:

- `candidate`
- `route`
- `tool`
- `evidence`
- `agent`

Add a declarative scoring policy:

- `pheromone_scored_subject_types`
- default: `["candidate"]`
- hybrid example: `["candidate", "route", "tool", "agent"]`

Rules:

- `candidate` pheromone directly influences a declared candidate.
- `route` pheromone may influence a declared candidate only when the trail is
  bound to that candidate.
- `tool` pheromone may influence tool or path preference, but cannot directly
  commit a candidate.
- `evidence` pheromone records access or reference memory only. It never
  contributes to candidate scoring and is invalid in either a policy-wide or
  per-kind `scored_subject_types` declaration; pheromone cannot become
  evidence authority.
- `agent` pheromone records source reliability, role trace, or collaboration
  memory, but cannot grant authority.
- Unknown namespaced subject types are metadata by default and score only when
  explicitly named by a valid scoring declaration.

### 3.2 Pheromone Kinds

Retain the current built-ins and add emergency semantics:

- `positive`: route or candidate reinforcement, analogous to trail pheromone.
- `negative`: suppression of failed routes or low-value candidates.
- `cautionary`: risk, crowding, blockage, or warning pressure.
- `alarm`: high-priority emergency signal with short TTL and strong inhibitory
  pressure; it cannot directly commit or authorize output.
- `novelty`: exploration support for new routes or candidates; it decays
  quickly.
- `stale`: expired memory; it does not score.

Runtime mapping:

- `ALERT_COLONY` -> `alarm`
- `AVOID_AREA` -> `cautionary`
- `RECRUITMENT` -> `positive` plus a recruitment signal
- `PATH_STRENGTHENING` -> `positive` on a route subject
- `REPULSION` -> `negative` or `cautionary`

### 3.3 Kind Profiles

Add `pheromone_kind_profiles`. Each kind may declare:

- `weight`
- `evaporation_rate`
- `ttl_steps`
- `response_model`
- `priority`
- `can_suppress_positive`
- `scored_subject_types`

Built-in kinds with an empty per-kind `scored_subject_types` inherit
`pheromone_scored_subject_types` for compatibility. A namespaced extension
kind never inherits that policy-wide list: it remains metadata-only unless its
own profile declares a non-empty `scored_subject_types` list. That per-kind
list is the sole scoring opt-in for extension kinds.

Recommended defaults:

```text
positive:   longer TTL, moderate evaporation, supports convergence
negative:   medium TTL, medium evaporation, discourages failed paths
cautionary: short TTL, high priority, can suppress positive support
alarm:      very short TTL, highest priority, routes to inhibition/fallback pressure
novelty:    short TTL, low-to-medium support, encourages exploration
stale:      no scoring
```

Constraints:

- Kind profile weights, TTL values, and evaporation rates must be non-negative.
- `alarm` and `cautionary` cannot directly authorize output.
- `stale` must remain no-score.

## 4. Insect-Inspired Dynamic Mechanisms

### 4.1 Local Diffusion

Real pheromone is not global broadcast. It diffuses locally through an
environment. Protocol-core does not simulate space, but it defines a
provider-free topology ABI that external runtimes can populate.

Add these concepts:

- `PheromoneSubject`
- `PheromoneNeighborhood`
- `PheromoneEdge`
- `PheromoneDiffusionPolicy`

Core semantics:

- External runtimes map radius, spread cone, layout, path graph, or tool graph
  into declared subject topology.
- Core operates only on declared subject graph data.
- Diffusion decays by hop count and attenuation.
- Diffusion must not create undeclared candidates.
- Diffused trails inherit provenance and trace lineage.

Reference functions:

- `validate_pheromone_topology(...)`
- `diffuse_pheromone_trails(...)`

### 4.2 Nonlinear Response

Insect collective decisions use positive feedback, but unchecked positive
feedback can lock onto an early path too aggressively. The ABI therefore needs
saturation and competition while preserving deterministic behavior.

Add `pheromone_response_model`:

- `linear`: backward-compatible behavior.
- `saturating`: diminishing returns; recommended for the hybrid profile.
- `threshold`: no contribution below an activation threshold.
- `competitive`: candidate-level normalization to prevent all candidates from
  rising together.

Add policy fields:

- `pheromone_activation_threshold`
- `pheromone_saturation_threshold`
- `pheromone_competition_mode`
- `pheromone_exploration_floor`

Constraints:

- Response models affect score only.
- `pheromone_exploration_floor` is the bounded response floor: it raises only
  non-negative, sub-floor pheromone scores and never cancels negative pressure.
- Response models do not affect evidence, authority, permission, or output.
- High pheromone still requires the independent-scout gate.
- Pheromone alone cannot commit a candidate.

### 4.3 Feedback Reinforcement

Real pheromone is strengthened or weakened through outcomes. Runtime feedback
must become a standard core input, not an ad hoc side channel.

Add `PheromoneFeedback`:

- `source_id`
- `subject_type`
- `subject_id`
- `candidate_id`
- `target`
- `outcome`
- `reward`
- `strength_delta`
- `evidence_id`
- `provenance`
- `trace_event_id`
- `step`

Supported outcomes:

- `success`
- `failure`
- `blocked`
- `congested`
- `hazard`
- `novel`
- `stale`

Reference functions:

- `validate_pheromone_feedback(...)`
- `reinforce_pheromone_trails(...)`

Outcome mapping:

- `success` -> positive reinforcement
- `failure` -> negative reinforcement
- `blocked` or `congested` -> cautionary reinforcement
- `hazard` -> alarm or cautionary reinforcement
- `novel` -> novelty deposit
- `stale` -> stale conversion or no-score trail

Constraints:

- Feedback must carry provenance.
- Feedback must carry trace lineage.
- Feedback can adjust only declared subjects and candidates.
- Feedback remains bounded by per-source cap, per-round deposit cap, maximum
  strength, and kind profile.
- Feedback cannot create evidence.

### 4.4 Exploration and Exploitation

Swarm systems should not exploit only the strongest current path. They must
retain controlled exploration.

Add policy fields:

- `exploration_enabled`
- `exploration_floor`
- `novelty_decay_rate`
- `stale_route_reopen_threshold`

Behavior:

- `exploration_floor` is separate from the response floor and adds bounded
  novelty pressure only while `exploration_enabled` is true.
- Novelty trails are no-score while exploration is disabled. When enabled,
  `novelty_decay_rate` is applied during the full evaporation lifecycle before
  the trail timestamp advances, so the complete Hybrid step cannot erase its age.
- Strong positive trails increase exploitation pressure.
- Novelty trails increase exploration pressure.
- Stale trails do not score, but may remain external runtime hints.
- Core does not make random choices. External runtimes may explore, but must
  feed exploration results back through scout reports, feedback, and trace.

## 5. L1-L4 Hybrid Intelligence ABI

Do not place `HybridPheromoneSystem` itself inside protocol-core. The core ABI
standardizes the outputs of that system as governance-readable records.

### 5.1 LayerProposal

Add `LayerProposal`:

- `layer_id`: `reactive | learned | evolutionary | metacognitive`
- `source_id`
- `target`
- `candidate_id`
- `action`
- `confidence`
- `support`
- `risk`
- `proposed_pheromone_kind`
- `proposed_strength`
- `evidence_id`
- `provenance`
- `trace_event_id`
- `metadata`

Rules:

- A proposal must reference a declared target.
- A candidate proposal must reference a declared candidate.
- Learned and evolutionary proposals do not have commit authority.
- Reactive emergency proposals may raise alarm or cautionary pressure, but still
  pass through governance commit and fallback semantics.

### 5.2 L1 Reactive Layer

Mapping from the provided reactive layer:

- Critical emergency -> `alarm` plus inhibition or fallback pressure.
- High emergency -> `cautionary` plus route avoidance pressure.
- Food/resource discovery -> `positive` plus recruitment signal.
- Efficient path traversal -> `positive` route pheromone.
- Crowding -> `negative` or `cautionary` route pheromone.

Core behavior:

- Accept reactive proposals as records.
- Validate declared target, candidate, and subject references.
- Produce traceable pheromone actions.
- Never let the reactive layer directly authorize output.

### 5.3 L2 Learning Layer

The external runtime owns perception networks, value assessment, parameter
generation, online learning, and memory buffers.

Core accepts only:

- learned `LayerProposal`
- learned `PheromoneFeedback`
- bounded `PolicyAdjustmentProposal`

Constraints:

- Learned confidence is a scoring and coordination input only.
- Learned proposals must carry provenance.
- Learned feedback must be traceable.
- Learned parameter changes can apply only within manifest-declared bounds.

### 5.4 L3 Evolutionary Layer

The external runtime owns strategy populations, fitness evaluation, selection,
crossover, mutation, and long-horizon adaptation.

Core accepts only:

- evolutionary `LayerProposal`
- `StrategyBias`
- `PolicyAdjustmentProposal`

Allowed adjustment dimensions:

- evaporation rates within declared bounds
- kind weights within declared bounds
- response model from an allowed set
- exploration floor within declared bounds
- layer weight hints within declared bounds
- cautionary and alarm thresholds within declared bounds

Disallowed behavior:

- rewriting the manifest
- declaring new candidates
- disabling required trace
- disabling safe fallback
- bypassing output policy

### 5.5 L4 Metacognitive Coordination

L4 is the cross-layer coordination and health-monitoring interface. It must be
represented in the core ABI because it decides how layer proposals combine, but
the concrete performance tracker, weight allocator, confidence assessor, and
conflict resolver remain external runtime components.

Add `LayerCoordinationPolicy`:

- `enabled`
- `layer_weight_bounds`
- `default_layer_weights`
- `confidence_thresholds`
- `conflict_threshold`
- `emergency_override_threshold`
- `min_layer_provenance`
- `fallback_on_unresolved_conflict`
- `policy_adjustment_bounds`

Add `LayerPerformanceSnapshot`:

- `layer_id`
- `recent_success_rate`
- `recent_conflict_rate`
- `recent_fallback_rate`
- `mean_confidence`
- `evidence_coverage`
- `trace_coverage`

Add `LayerCoordinationState`:

- `confidences`
- `allocated_weights`
- `conflicts`
- `resolution`
- `selected_candidate`
- `fallback_used`
- `score_breakdown`
- `trace_lineage`

Reference functions:

- `assess_layer_confidences(...)`
- `detect_layer_conflicts(...)`
- `allocate_layer_weights(...)`
- `resolve_layer_conflicts(...)`
- `evaluate_layer_coordination(...)`

Conflict rules:

- Different layers support different candidates with similar confidence.
- Strong positive support and strong alarm/cautionary pressure target the same
  route or candidate.
- Learned or evolutionary proposals are strong, but scout or evidence coverage
  is insufficient.
- Reactive emergency pressure conflicts with learned high-confidence
  exploitation. The emergency path becomes cautionary/fallback pressure, not
  direct output authority.

Resolution strategy:

- Critical emergency -> alarm/cautionary pressure plus safe-fallback preference.
- Insufficient evidence or scouts -> request more scouting or choose safe
  fallback.
- High recent conflict rate -> reduce conflicting layer weight within bounds.
- Low reactive performance -> reduce reactive weight only when there is no
  active emergency condition.
- Unresolved conflict -> declared safe fallback.

Meta-learning boundary:

- The runtime may learn coordinator strategy.
- Core validates only whether the learned coordination output stays within
  manifest policy bounds.
- Runtime policy adjustment is run-scoped and does not mutate the manifest.
- A run-scoped global evaporation or response-model adjustment takes
  precedence over declared per-kind overrides for that run; accepted
  adjustments therefore cannot be silently shadowed into no-ops.

## 6. Collective Decision Pipeline

This section specifies the deterministic v1 Hybrid scoring/reducer semantics.
For authority that must continue across calls, processes, or restarts, runtimes
MUST use the Store-backed [Hybrid Replay v2](hybrid-replay-v2.md) journey. The
v1 `HybridReplayState` described below is a Deprecated Draft compatibility
carrier; it is not a durable StateStore inclusion/currentness proof.

The canonical pure reference entry point is
`evaluate_hybrid_collective_step(...) -> HybridCollectiveStep`. External
runtimes submit ABI records; they do not submit a precomputed decision,
coordination state, score, or output authorization. A later step derives its
immutable replay input with `replay_state_from_hybrid_step(...)`. Raw
processed-id sets and caller-selected replacement trails are not replay
authority. Issued state carries mutually disjoint deposit, diffusion, feedback,
and adjustment receipt maps. Each `replay_ignored` event exposes the complete
canonical receipt as `replay_payload`; Trace recomputes its digest, and
conformance binds it to the explicitly supplied governance-issued prior state.
A matching event hash and score snapshot without that state is not authority.

The complete hybrid pheromone path is:

1. Load a capability manifest.
2. Validate protocol invariants.
3. Materialize runtime-owned `PheromoneContext`.
4. L1 emits reactive proposals.
5. L2 emits learned proposals and feedback.
6. L3 emits strategy bias and bounded policy-adjustment proposals.
7. L4 evaluates confidence, conflicts, and layer weights.
8. Governance validates all proposals.
9. Deposit pheromone trails.
10. Evaporate existing trails.
11. Diffuse trails through declared topology.
12. Reinforce trails from feedback.
13. Score scouts, recruitment, inhibition, pheromone, and layer coordination.
14. Enforce the independent-scout gate.
15. Commit only a declared candidate if thresholds are met.
16. Otherwise use the declared safe fallback.
17. Authorize output only through the output contract.
18. Emit trace events for full lineage.
19. Pass the active conformance profile.

## 7. Score Breakdown

`CollectiveDecisionState` must expose score lineage for L4 and trace.

Add breakdown categories:

- `scout`
- `recruitment`
- `inhibition`
- `pheromone_positive`
- `pheromone_negative`
- `pheromone_cautionary`
- `pheromone_alarm`
- `pheromone_novelty`
- `pheromone_route`
- `pheromone_tool`
- `pheromone_agent`
- `layer_reactive`
- `layer_learned`
- `layer_evolutionary`
- `layer_metacognitive`

Requirements:

- The total score must be reconstructable from the breakdown.
- Stale contribution must be zero.
- Extension metadata must not score by default.
- `pheromone_score` carries the canonical active-trail/source set as well as
  reconstructable breakdowns. `candidate_score` and the final decision cite
  every score-affecting scout, recruitment, inhibition, adjustment, pheromone,
  and layer lineage.

## 8. Protocol Manifest Additions

Add optional fields under `collective_decision_policy`. Defaults must preserve
existing baseline and swarm behavior.

Proposed fields:

```text
pheromone_scored_subject_types
pheromone_kind_profiles
pheromone_response_model
pheromone_activation_threshold
pheromone_saturation_threshold
pheromone_competition_mode
pheromone_exploration_floor
pheromone_diffusion_enabled
pheromone_diffusion_max_hops
pheromone_diffusion_attenuation
pheromone_feedback_enabled
layer_coordination_enabled
layer_weight_bounds
layer_default_weights
layer_confidence_thresholds
layer_conflict_threshold
layer_emergency_override_threshold
policy_adjustment_bounds
```

Validation invariants:

- All weights must be non-negative.
- All thresholds must be non-negative.
- Evaporation rates must be in `[0, 1]`.
- TTL values must be non-negative.
- Scored subject types must be supported built-ins or namespaced extension
  values.
- `evidence` is a supported memory subject but is prohibited from scored
  subject declarations.
- A namespaced extension kind scores only through its own non-empty
  `scored_subject_types`; an empty extension profile remains metadata-only.
- Response model must be supported.
- Diffusion attenuation must be in `[0, 1]`.
- Layer weights must be non-negative.
- Policy-adjustment bounds must not permit disabling trace, fallback,
  provenance, or declared-candidate checks.

## 9. Trace ABI

Add trace event types:

- `pheromone_observe`
- `pheromone_diffuse`
- `pheromone_reinforce`
- `pheromone_normalize`
- `layer_proposal`
- `coordination_assess`
- `coordination_resolve`
- `policy_adjustment`

Continue using existing trace event types:

- `explore`
- `scout_report`
- `recruit`
- `inhibit`
- `pheromone_deposit`
- `pheromone_evaporate`
- `pheromone_score`
- `pheromone_clip`
- `pheromone_expire`
- `candidate_score`
- `consensus_check`
- `commit`
- `fallback`
- `recovery`
- `output`

Trace lineage must carry:

- source layer
- source id
- subject type and subject id
- candidate id when applicable
- old and new strength
- kind
- policy profile used
- feedback outcome when applicable
- coordination weights
- conflict resolution reason
- policy-adjustment bounds result

Rejected `pheromone_clip` variants additionally carry a versioned
`causal_payload` plus `causal_fingerprint`. Deposit receipts bind the complete
input trail, diffusion receipts bind the source trail, declared target subject,
edge and hop, and feedback receipts bind every feedback field plus the source
memory state. The canonical Trace ABI reconstructs requested strength from the
payload and rejects any missing, altered, non-finite, or mismatched receipt.
The receipt explains a governance transition; it is not evidence, verification,
permission, or commit authority.

## 10. Conformance

Add profile: `pheroos-hybrid-swarm-v1`.

Activation conditions:

- The manifest declares a swarm collective mode.
- At least one hybrid pheromone feature is enabled: diffusion, feedback,
  nonlinear response, layer coordination, or policy adjustment.

Add checks:

- `pheromone_subject_scoring`
- `pheromone_kind_profile`
- `pheromone_diffusion`
- `pheromone_reinforcement`
- `pheromone_response_model`
- `layer_coordination_policy`
- `policy_adjustment_bounds`
- `hybrid_trace_contract`
- `hybrid_authority_boundary`

Conformance must prove:

- Route, tool, and agent pheromone cannot create undeclared candidates.
- Diffusion cannot move beyond declared topology.
- Feedback without provenance or trace is rejected.
- Saturating, threshold, and competitive response models are deterministic.
- Learned and evolutionary proposals cannot directly commit.
- Reactive emergency proposals cannot directly authorize output.
- L4 unresolved conflict falls back to a declared safe fallback.
- Policy adjustment cannot disable safety-critical invariants.
- Output authorization still requires a committed candidate, evidence
  provenance, stop resolution, and publication permission.

## 11. Provider-Free Example

Add `examples/hybrid-pheromone-protocol`.

The example must be deterministic, network-free, provider-free, and
domain-neutral.

Scenario:

1. Declare target `decision:collective`.
2. Declare candidates `candidate:alpha`, `candidate:beta`, and
   `candidate:safe_fallback`.
3. Declare route subjects `route:alpha` and `route:beta`.
4. L1 emits positive route pheromone for an efficient route.
5. L1 emits cautionary route pheromone for crowding.
6. L2 learned proposal favors alpha with provenance.
7. L3 strategy bias proposes lower positive evaporation within bounds.
8. L4 detects a learned-vs-cautionary conflict.
9. Feedback reinforces the successful route and suppresses the congested route.
10. Diffusion propagates route signal to a candidate-bound subject.
11. Score breakdown explains every contribution.
12. Consensus commits alpha only if scout and score thresholds pass.
13. Otherwise the safe fallback is committed.
14. Output is authorized only after evidence and stop resolution pass.

## 12. Goal-Mode Implementation Phases

These phases are intentionally not minimal. Each phase should land the complete
ABI behavior for its scope, with tests and conformance updates.

### Phase 1: Protocol ABI

Deliver:

- Manifest fields for subject scoring, kind profiles, response model, diffusion,
  feedback, layer coordination, and policy-adjustment bounds.
- Schema export updates.
- Loader updates.
- Validation diagnostics.
- Tests for valid and invalid manifest shapes.

Done when:

- Existing examples validate unchanged.
- Hybrid example manifest loads and validates.
- Invalid fields produce deterministic diagnostics.

### Phase 2: Governance Pheromone Dynamics

Deliver:

- Dataclasses for subject topology, diffusion, feedback, kind profiles, and
  response policy.
- Deterministic functions for diffusion, reinforcement, response transform, and
  score breakdown.
- Candidate scoring integration that does not weaken the scout gate or safe
  fallback.
- Backward-compatible defaults.

Done when:

- Existing governance tests pass.
- New tests prove diffusion, reinforcement, nonlinear response, route scoring,
  and stale no-score behavior.

### Phase 3: L4 Coordination ABI

Deliver:

- Layer proposal, performance snapshot, coordination policy, and coordination
  state dataclasses.
- Pure functions for confidence assessment, weight allocation, conflict
  detection, and conflict resolution.
- Integration of coordination contribution into `CollectiveDecisionState`.
- Safe fallback for unresolved conflict.

Done when:

- Tests prove reactive emergency, learned proposal, evolutionary bias, and
  metacognitive resolution are deterministic.
- L2 and L3 cannot directly commit or authorize output.

### Phase 4: Trace and Conformance

Deliver:

- New trace event types.
- Hybrid swarm conformance profile.
- Checks for diffusion, reinforcement, response model, L4 coordination, policy
  bounds, trace contract, and authority boundaries.

Done when:

- Hybrid trace contract fails if required lifecycle events are missing.
- Conformance proves pheromone cannot become evidence, authority, quorum, or
  output permission.

### Phase 5: Example and Documentation

Deliver:

- Provider-free hybrid pheromone example.
- Example README.
- Conformance documentation update.
- Protocol/runtime integration documentation update.

Done when:

- Toy, e2e, swarm, and hybrid examples all validate and pass conformance.

## 13. Acceptance Commands

Use the repository virtual environment because this shell may not expose
`python`.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pheroos.cli.main validate examples/toy-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/toy-protocol
.venv/bin/python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/swarm-protocol
.venv/bin/python -m pheroos.cli.main validate examples/hybrid-pheromone-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/hybrid-pheromone-protocol
```

## 14. Final Invariants

- Agents are not authority.
- Protocol is authority.
- Pheromone is collective memory, not truth.
- Pheromone can bias exploration, recruitment, inhibition, route preference,
  layer coordination, and consensus scoring.
- Pheromone cannot create evidence.
- Pheromone cannot declare candidates.
- Pheromone cannot bypass fallback.
- Pheromone cannot authorize output.
- Learned and evolutionary layers may propose, not decide.
- Metacognitive coordination may resolve conflicts only inside declared
  protocol bounds.
- External runtimes may optimize behavior, but protocol-core must remain
  deterministic, provider-free, domain-neutral, and conformance-backed.

## 15. Implementation Status

This ABI track is implemented in protocol-core as deterministic contracts and
reference behavior:

- Protocol ABI fields, schema export, loader defaults, and validation
  diagnostics cover subject scoring, kind profiles, nonlinear response,
  diffusion, feedback, layer coordination, and policy-adjustment bounds.
- Governance reference functions cover diffusion, feedback reinforcement,
  response shaping, score breakdown, layer coordination, and bounded policy
  adjustment validation while preserving declared-candidate, scout-gate, safe
  fallback, evidence, and output-authorization boundaries.
- Trace ABI includes hybrid lifecycle event types on the canonical
  `TraceEvent`.
- Conformance includes `pheroos-hybrid-swarm-v1` and checks for hybrid
  pheromone behavior, trace lineage, and authority boundaries.
- `examples/hybrid-pheromone-protocol` provides the provider-free, network-free,
  domain-neutral example.

The external hybrid runtime remains outside protocol-core by design.
