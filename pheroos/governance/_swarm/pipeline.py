from __future__ import annotations

from collections.abc import Mapping
from pheroos.governance._legacy.hybrid_v1 import select_legacy_blended_decision
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import LayerCoordinationState
from pheroos.governance.layer_coordination import LayerPerformanceSnapshot
from pheroos.governance.layer_coordination import LayerProposal
from pheroos.governance.layer_coordination import StrategyBias
from pheroos.governance.layer_coordination import evaluate_layer_coordination
from pheroos.governance.layer_coordination import (
    layer_coordination_policy_from_collective,
)
from pheroos.governance.layer_coordination import materialize_layer_pheromone_proposals
from pheroos.governance._pheromone.diffusion import (
    diffuse_pheromone_trails_with_records,
)
from pheroos.governance._pheromone.invariants import (
    diffusion_policy_from_collective,
    pheromone_bound_candidate_id,
    pheromone_policy_from_collective,
    pheromone_subject_id,
    pheromone_subject_type,
    scoreable_pheromone_candidate_id,
    validate_pheromone_subject_binding,
    validate_pheromone_trail,
)
from pheroos.governance._pheromone.lifecycle import (
    PheromoneBudgetState,
    deposit_pheromone_trails,
    evaporate_trails,
    evaporate_trails_with_records,
)
from pheroos.governance._pheromone.records import PheromoneNeighborhood, PheromoneTrail
from pheroos.governance._pheromone.scoring import observe_pheromone_exploration
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.governance.pheromone_feedback import (
    reinforce_pheromone_trails_with_records,
)
from pheroos.governance.policy_adjustment import PolicyAdjustmentProposal
from pheroos.governance.policy_adjustment import apply_policy_adjustment_overlay
from pheroos.governance.policy_adjustment import validate_policy_adjustment_proposals
from pheroos.governance.quorum import QuorumDecision
from pheroos.governance.quorum import _issue_quorum_decision
from pheroos.governance.runtime_policy import resolve_collective_fallback_id
from pheroos.governance.runtime_policy import validate_collective_runtime_policy
from pheroos.protocol.models import CollectiveDecisionPolicy
from typing import Any
from pheroos.governance._swarm.records import (
    CollectiveDecisionState,
    CollectiveDecisionStep,
    HybridCollectiveStep,
    HybridReplayState,
)
from pheroos.governance._swarm.replay import (
    _adjustment_replay_fingerprint,
    _extend_replay_receipts,
    _feedback_replay_fingerprint,
    _hybrid_replay_state_bindings_match,
    _issue_hybrid_collective_step,
    _trail_replay_fingerprint,
    _validate_complete_hybrid_trace_identity,
    _validate_replay_receipts,
    hybrid_replay_state_is_authoritative,
)
from pheroos.governance._swarm.scoring import (
    merge_candidate_breakdown,
    score_candidates,
    validate_score_breakdown,
)
from pheroos.governance._swarm.signals import (
    InhibitionSignal,
    RecruitmentSignal,
    ScoutReport,
)
from pheroos.governance._swarm.trace import _hybrid_step_trace_events


def merge_governed_layer_coordination(
    state: CollectiveDecisionState,
    layer_state: LayerCoordinationState,
) -> CollectiveDecisionState:
    """Merge a state produced by the governance layer evaluator.

    This helper is intentionally not an external-state trust path: the Hybrid
    entry calls it immediately after `evaluate_layer_coordination`.  Public
    scoring rejects caller-constructed layer state in Hybrid mode.
    """

    score_breakdown = {
        candidate_id: dict(categories)
        for candidate_id, categories in state.score_breakdown.items()
    }
    if not layer_state.fallback_used:
        for candidate_id, candidate_breakdown in layer_state.score_breakdown.items():
            if candidate_id not in score_breakdown:
                raise GovernanceError(
                    f"layer coordination scored an undeclared active candidate: {candidate_id}"
                )
            merge_candidate_breakdown(
                score_breakdown, candidate_id, candidate_breakdown
            )
    scores = {
        candidate_id: sum(candidate_breakdown.values())
        for candidate_id, candidate_breakdown in score_breakdown.items()
    }
    merged = CollectiveDecisionState(
        scores=scores,
        independent_scouts=state.independent_scouts,
        pheromone_source_diversity=state.pheromone_source_diversity,
        score_breakdown=score_breakdown,
        layer_coordination=layer_state,
    )
    validate_score_breakdown(merged)
    return merged


def evaluate_collective_decision(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
    layer_coordination_state: LayerCoordinationState | None = None,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
    state = score_candidates(
        candidate_set=candidate_set,
        policy=policy,
        scout_reports=scout_reports,
        target=target,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        pheromone_trails=pheromone_trails,
        layer_coordination_state=layer_coordination_state,
    )
    return _decide_collective_state(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        state=state,
        fallback_candidate_id=fallback_candidate_id,
    )


def evaluate_collective_decision_step(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    scout_reports: list[ScoutReport],
    current_step: int,
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
    layer_coordination_state: LayerCoordinationState | None = None,
    fallback_candidate_id: str | None = None,
) -> CollectiveDecisionStep:
    validate_collective_runtime_policy(policy)
    active_trails = list(pheromone_trails or [])
    if policy.pheromone_enabled:
        active_trails = evaporate_trails(
            active_trails,
            pheromone_policy_from_collective(policy),
            current_step=current_step,
        )
    state = score_candidates(
        candidate_set=candidate_set,
        policy=policy,
        scout_reports=scout_reports,
        target=target,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        pheromone_trails=active_trails,
        layer_coordination_state=layer_coordination_state,
    )
    decision = _decide_collective_state(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        state=state,
        fallback_candidate_id=fallback_candidate_id,
    )
    return CollectiveDecisionStep(
        decision=decision, state=state, pheromone_trails=active_trails
    )


def evaluate_hybrid_collective_step(
    *,
    protocol_id: str,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    current_step: int,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    existing_trails: list[PheromoneTrail] | None = None,
    deposits: list[PheromoneTrail] | None = None,
    topology: PheromoneNeighborhood | None = None,
    feedback: list[PheromoneFeedback] | None = None,
    layer_proposals: list[LayerProposal] | None = None,
    performance_snapshots: list[LayerPerformanceSnapshot] | None = None,
    strategy_biases: list[StrategyBias] | None = None,
    adjustment_proposals: list[PolicyAdjustmentProposal] | None = None,
    processed_pheromone_event_ids: frozenset[str] = frozenset(),
    processed_feedback_ids: frozenset[str] = frozenset(),
    processed_adjustment_ids: frozenset[str] = frozenset(),
    replay_state: HybridReplayState | None = None,
    fallback_candidate_id: str | None = None,
    attention_only: bool = False,
) -> HybridCollectiveStep:
    """Evaluate one complete Hybrid step through the legacy Draft surface."""

    return _evaluate_hybrid_collective_step(
        protocol_id=protocol_id,
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        current_step=current_step,
        scout_reports=scout_reports,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        existing_trails=existing_trails,
        deposits=deposits,
        topology=topology,
        feedback=feedback,
        layer_proposals=layer_proposals,
        performance_snapshots=performance_snapshots,
        strategy_biases=strategy_biases,
        adjustment_proposals=adjustment_proposals,
        processed_pheromone_event_ids=processed_pheromone_event_ids,
        processed_feedback_ids=processed_feedback_ids,
        processed_adjustment_ids=processed_adjustment_ids,
        replay_state=replay_state,
        fallback_candidate_id=fallback_candidate_id,
        attention_only=attention_only,
        require_legacy_replay_authority=True,
        issue_legacy_result=True,
    )


def _evaluate_hybrid_collective_step_v2(
    *,
    protocol_id: str,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    current_step: int,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    existing_trails: list[PheromoneTrail] | None = None,
    deposits: list[PheromoneTrail] | None = None,
    topology: PheromoneNeighborhood | None = None,
    feedback: list[PheromoneFeedback] | None = None,
    layer_proposals: list[LayerProposal] | None = None,
    performance_snapshots: list[LayerPerformanceSnapshot] | None = None,
    strategy_biases: list[StrategyBias] | None = None,
    adjustment_proposals: list[PolicyAdjustmentProposal] | None = None,
    replay_state: HybridReplayState | None = None,
    fallback_candidate_id: str | None = None,
    attention_only: bool = False,
) -> HybridCollectiveStep:
    """Run the pure Hybrid engine after a v2 owner verified replay currentness.

    This is not an authority entry point. It accepts only the normalized replay
    projection reconstructed by Hybrid Replay v2 and deliberately neither reads
    nor issues the legacy process-local replay/step tokens.
    """

    return _evaluate_hybrid_collective_step(
        protocol_id=protocol_id,
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        current_step=current_step,
        scout_reports=scout_reports,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        existing_trails=existing_trails,
        deposits=deposits,
        topology=topology,
        feedback=feedback,
        layer_proposals=layer_proposals,
        performance_snapshots=performance_snapshots,
        strategy_biases=strategy_biases,
        adjustment_proposals=adjustment_proposals,
        replay_state=replay_state,
        fallback_candidate_id=fallback_candidate_id,
        attention_only=attention_only,
        require_legacy_replay_authority=False,
        issue_legacy_result=False,
    )


def _evaluate_hybrid_collective_step(
    *,
    protocol_id: str,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    current_step: int,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    existing_trails: list[PheromoneTrail] | None = None,
    deposits: list[PheromoneTrail] | None = None,
    topology: PheromoneNeighborhood | None = None,
    feedback: list[PheromoneFeedback] | None = None,
    layer_proposals: list[LayerProposal] | None = None,
    performance_snapshots: list[LayerPerformanceSnapshot] | None = None,
    strategy_biases: list[StrategyBias] | None = None,
    adjustment_proposals: list[PolicyAdjustmentProposal] | None = None,
    processed_pheromone_event_ids: frozenset[str] = frozenset(),
    processed_feedback_ids: frozenset[str] = frozenset(),
    processed_adjustment_ids: frozenset[str] = frozenset(),
    replay_state: HybridReplayState | None = None,
    fallback_candidate_id: str | None = None,
    attention_only: bool = False,
    require_legacy_replay_authority: bool,
    issue_legacy_result: bool,
) -> HybridCollectiveStep:
    """Evaluate one complete, deterministic Hybrid Pheromone governance step.

    All inputs are validated before a result is returned, all lifecycle
    transitions are pure, and no caller-provided decision or coordination state
    is accepted.  Proposal layers can influence bounded score categories but
    the independent-scout gate and safe fallback remain authoritative.
    """

    validate_collective_runtime_policy(policy)
    if type(attention_only) is not bool:
        raise GovernanceError("hybrid attention_only must be boolean")
    if any(
        (
            processed_pheromone_event_ids,
            processed_feedback_ids,
            processed_adjustment_ids,
        )
    ):
        raise GovernanceError(
            "raw processed replay ids are not authoritative; use a governance-issued replay state"
        )
    deposit_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    diffusion_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    feedback_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    adjustment_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    if replay_state is not None:
        if require_legacy_replay_authority:
            if not hybrid_replay_state_is_authoritative(replay_state):
                raise GovernanceError("hybrid replay state is not governance-issued")
        elif not _hybrid_replay_state_bindings_match(
            replay_state,
            protocol_id=protocol_id,
            target=target,
        ):
            raise GovernanceError("Hybrid Replay v2 state projection is malformed")
        if replay_state.protocol_id != protocol_id or replay_state.target != target:
            raise GovernanceError(
                "hybrid replay state does not match the active protocol and target"
            )
        if existing_trails:
            raise GovernanceError(
                "existing trails cannot override governance-issued replay memory"
            )
        existing_trails = list(replay_state.active_trails)
        processed_pheromone_event_ids = replay_state.processed_pheromone_event_ids
        processed_feedback_ids = replay_state.processed_feedback_ids
        processed_adjustment_ids = replay_state.processed_adjustment_ids
        deposit_replay_receipts = replay_state.deposit_replay_receipts
        diffusion_replay_receipts = replay_state.diffusion_replay_receipts
        feedback_replay_receipts = replay_state.feedback_replay_receipts
        adjustment_replay_receipts = replay_state.adjustment_replay_receipts
    if not is_nonblank_string(protocol_id):
        raise GovernanceError("hybrid collective step requires protocol_id")
    if policy.mode != "hybrid":
        raise GovernanceError("hybrid collective step requires mode='hybrid'")
    if not is_nonblank_string(target):
        raise GovernanceError("hybrid collective step requires an active target")
    if (
        isinstance(current_step, bool)
        or not isinstance(current_step, int)
        or current_step < 0
    ):
        raise GovernanceError(
            "hybrid collective current_step must be a non-negative integer"
        )
    if not (
        policy.pheromone_enabled
        and policy.pheromone_diffusion_enabled
        and policy.pheromone_feedback_enabled
        and policy.layer_coordination_enabled
        and bool(policy.pheromone_kind_profiles)
        and bool(policy.policy_adjustment_bounds)
        and policy.pheromone_require_provenance
        and policy.pheromone_require_trace
    ):
        raise GovernanceError(
            "hybrid collective step requires the complete declared Hybrid path"
        )
    if topology is None:
        raise GovernanceError(
            "hybrid collective step requires declared pheromone topology"
        )

    fallback_id = resolve_collective_fallback_id(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        fallback_candidate_id=fallback_candidate_id,
    )
    fallback = candidate_set.require_declared_for_target(fallback_id, target)
    if not fallback.safe_fallback:
        raise GovernanceError(
            f"hybrid fallback candidate is not marked safe: {fallback.id}"
        )
    active_candidates = [
        candidate
        for candidate in candidate_set.candidates
        if candidate.target == target
    ]
    if not active_candidates:
        raise GovernanceError(
            "hybrid collective step has no candidates for the active target"
        )

    # Run-scoped adaptation is validated as one atomic batch and applied to an
    # immutable replacement policy; the manifest-owned object is never mutated.
    scout_inputs = list(scout_reports)
    recruitment_inputs = list(recruitment_signals or [])
    inhibition_inputs = list(inhibition_signals or [])
    explicit_deposits = list(deposits or [])
    feedback_inputs = list(feedback or [])
    strategy_bias_inputs = list(strategy_biases or [])
    adjustment_inputs = list(adjustment_proposals or [])
    _validate_replay_receipts(
        items=adjustment_inputs,
        processed_ids=processed_adjustment_ids,
        receipts=adjustment_replay_receipts,
        fingerprint=_adjustment_replay_fingerprint,
        label="policy adjustment",
    )
    adjustment_batch = validate_policy_adjustment_proposals(
        adjustment_inputs,
        policy,
        processed_trace_event_ids=processed_adjustment_ids,
    )
    effective_policy = apply_policy_adjustment_overlay(policy, adjustment_batch.overlay)
    validate_collective_runtime_policy(effective_policy)
    pheromone_policy = pheromone_policy_from_collective(effective_policy)
    diffusion_policy = diffusion_policy_from_collective(effective_policy)
    layer_policy = layer_coordination_policy_from_collective(effective_policy)
    layer_inputs = list(layer_proposals or [])
    # Layer processing is deliberately two-phase.  Phase 1 validates the whole
    # proposal batch and materializes only proposal-owned memory inputs; these
    # trails have no score or authority until the normal pheromone pipeline
    # accepts them below.  Phase 2 performs confidence/coverage/conflict
    # coordination after pheromone dynamics, using the same validated records.
    proposed_layer_trails = materialize_layer_pheromone_proposals(
        proposals=layer_inputs,
        candidate_set=candidate_set,
        target=target,
        current_step=current_step,
        policy=layer_policy,
        neighborhood=topology,
    )
    _validate_complete_hybrid_trace_identity(
        scout_reports=scout_inputs,
        recruitment_signals=recruitment_inputs,
        inhibition_signals=inhibition_inputs,
        deposits=explicit_deposits,
        layer_proposals=layer_inputs,
        materialized_layer_deposits=proposed_layer_trails,
        feedback=feedback_inputs,
        strategy_biases=strategy_bias_inputs,
        adjustment_proposals=adjustment_inputs,
        existing_trails=list(existing_trails or []),
        deposit_replay_receipts=deposit_replay_receipts,
        diffusion_replay_receipts=diffusion_replay_receipts,
        feedback_replay_receipts=feedback_replay_receipts,
        adjustment_replay_receipts=adjustment_replay_receipts,
    )
    deposit_inputs = [*explicit_deposits, *proposed_layer_trails]
    for trail in deposit_inputs:
        validate_pheromone_subject_binding(
            topology,
            subject_type=pheromone_subject_type(trail),
            subject_id=pheromone_subject_id(trail),
            candidate_id=pheromone_bound_candidate_id(trail),
            require_declared=bool(
                scoreable_pheromone_candidate_id(trail, pheromone_policy)
            ),
        )
    _validate_replay_receipts(
        items=deposit_inputs,
        processed_ids=processed_pheromone_event_ids,
        receipts=deposit_replay_receipts,
        fingerprint=_trail_replay_fingerprint,
        label="pheromone deposit",
    )

    # Thread one source/round budget through every state-changing pheromone
    # stage.  Splitting equivalent input across deposit, diffusion, or feedback
    # cannot multiply the declared cap.
    budget = PheromoneBudgetState.for_policy(pheromone_policy)
    deposit_result = deposit_pheromone_trails(
        deposit_inputs,
        pheromone_policy,
        candidate_set=candidate_set,
        target=target,
        budget_state=budget,
        processed_event_ids=processed_pheromone_event_ids,
    )
    budget = deposit_result.budget_state or budget
    combined_trails = [*list(existing_trails or []), *deposit_result.trails]
    seen_trail_ids: set[str] = set()
    for trail in combined_trails:
        validate_pheromone_trail(
            trail,
            pheromone_policy,
            candidate_set=candidate_set,
            target=target,
        )
        if not pheromone_bound_candidate_id(trail):
            raise GovernanceError(
                "hybrid pheromone trail must bind a declared candidate"
            )
        if trail.trace_event_id in seen_trail_ids:
            raise GovernanceError(
                f"duplicate active pheromone trace_event_id: {trail.trace_event_id}"
            )
        seen_trail_ids.add(trail.trace_event_id)

    evaporation_result = evaporate_trails_with_records(
        combined_trails,
        pheromone_policy,
        current_step=current_step,
    )
    pre_diffusion_trails = tuple(evaporation_result.trails)
    processed_pheromone = frozenset(
        set(processed_pheromone_event_ids) | set(deposit_result.processed_event_ids)
    )
    diffusion_result = diffuse_pheromone_trails_with_records(
        list(pre_diffusion_trails),
        topology,
        pheromone_policy,
        diffusion_policy,
        candidate_set=candidate_set,
        target=target,
        budget_state=budget,
        processed_event_ids=processed_pheromone,
        processed_event_receipts=diffusion_replay_receipts,
    )
    budget = diffusion_result.budget_state or budget
    processed_pheromone = frozenset(
        set(processed_pheromone) | set(diffusion_result.processed_event_ids)
    )
    _validate_replay_receipts(
        items=feedback_inputs,
        processed_ids=processed_feedback_ids,
        receipts=feedback_replay_receipts,
        fingerprint=_feedback_replay_fingerprint,
        label="pheromone feedback",
    )
    reinforcement_result = reinforce_pheromone_trails_with_records(
        list(diffusion_result.trails),
        feedback_inputs,
        pheromone_policy,
        candidate_set=candidate_set,
        target=target,
        processed_feedback_ids=processed_feedback_ids,
        budget_state=budget,
        neighborhood=topology,
    )
    budget = reinforcement_result.budget_state or budget
    post_reinforcement_expiration = evaporate_trails_with_records(
        list(reinforcement_result.trails),
        pheromone_policy,
        current_step=current_step,
    )
    active_trails = tuple(
        sorted(
            post_reinforcement_expiration.trails,
            key=lambda trail: (
                trail.target,
                pheromone_bound_candidate_id(trail),
                pheromone_subject_type(trail),
                pheromone_subject_id(trail),
                trail.kind,
                trail.source_id,
                trail.trace_event_id,
            ),
        )
    )

    observations = observe_pheromone_exploration(
        candidate_set=CandidateSet(tuple(active_candidates)),
        trails=list(active_trails),
        policy=pheromone_policy,
        current_step=current_step,
        target=target,
    )
    # Phase 2: proposals now affect only declared layer score categories,
    # coverage assessment, conflict resolution, or safe fallback.
    layer_state = evaluate_layer_coordination(
        candidate_set=candidate_set,
        target=target,
        policy=layer_policy,
        proposals=layer_inputs,
        fallback_candidate_id=fallback.id,
        snapshots=list(performance_snapshots or []),
        strategy_biases=strategy_bias_inputs,
    )

    # This is the only scoring call in the reference path.  Layer state is
    # merged only after governance computed it above, never accepted from a
    # caller as authority.
    base_state = score_candidates(
        candidate_set=candidate_set,
        policy=effective_policy,
        scout_reports=scout_inputs,
        target=target,
        recruitment_signals=recruitment_inputs,
        inhibition_signals=inhibition_inputs,
        pheromone_trails=list(active_trails),
    )
    state = merge_governed_layer_coordination(base_state, layer_state)
    if attention_only:
        # This is deliberately not a commit result.  The full memory,
        # diffusion, feedback, nonlinear response, layer coordination and
        # bounded adjustment pipeline above remains shared with the legacy
        # Hybrid ABI, while the Optimal Commit evaluator receives only an
        # explicitly non-authoritative attention ranking.
        decision = _issue_quorum_decision(
            target=target,
            candidate_id=fallback.id,
            committed=False,
            reason="attention_only_no_commit_authority",
        )
    else:
        decision = _decide_collective_state(
            candidate_set=candidate_set,
            policy=effective_policy,
            target=target,
            state=state,
            fallback_candidate_id=fallback.id,
        )

    events = _hybrid_step_trace_events(
        protocol_id=protocol_id,
        target=target,
        candidate_set=candidate_set,
        policy=effective_policy,
        pheromone_policy=pheromone_policy,
        scout_reports=list(scout_reports),
        recruitment_signals=list(recruitment_signals or []),
        inhibition_signals=list(inhibition_signals or []),
        deposit_inputs=deposit_inputs,
        deposit_result=deposit_result,
        deposit_replay_receipts=deposit_replay_receipts,
        diffusion_replay_receipts=diffusion_replay_receipts,
        feedback_replay_receipts=feedback_replay_receipts,
        adjustment_replay_receipts=adjustment_replay_receipts,
        evaporation_records=evaporation_result.records,
        pre_diffusion_trails=pre_diffusion_trails,
        diffusion_result=diffusion_result,
        feedback=feedback_inputs,
        reinforcement_result=reinforcement_result,
        post_reinforcement_expiration_records=post_reinforcement_expiration.records,
        active_trails=active_trails,
        observations=observations,
        layer_proposals=layer_inputs,
        performance_snapshots=list(performance_snapshots or []),
        strategy_biases=strategy_bias_inputs,
        layer_state=layer_state,
        adjustment_proposals=adjustment_inputs,
        adjustment_batch=adjustment_batch,
        state=state,
        decision=decision,
        current_step=current_step,
        include_legacy_decision=not attention_only,
    )

    result = HybridCollectiveStep(
        decision=decision,
        state=state,
        active_trails=active_trails,
        layer_coordination=layer_state,
        adjustment_overlay=adjustment_batch.overlay,
        effective_policy=effective_policy,
        deposit_records=deposit_result.records,
        evaporation_records=(
            *evaporation_result.records,
            *post_reinforcement_expiration.records,
        ),
        diffusion_records=diffusion_result.records,
        reinforcement_records=reinforcement_result.records,
        exploration_observations=observations,
        processed_pheromone_event_ids=processed_pheromone,
        processed_feedback_ids=reinforcement_result.processed_feedback_ids,
        processed_adjustment_ids=adjustment_batch.processed_trace_event_ids,
        deposit_replay_receipts=_extend_replay_receipts(
            deposit_replay_receipts,
            deposit_inputs,
            _trail_replay_fingerprint,
        ),
        diffusion_replay_receipts=dict(diffusion_result._processed_event_receipts),
        feedback_replay_receipts=_extend_replay_receipts(
            feedback_replay_receipts,
            feedback_inputs,
            _feedback_replay_fingerprint,
        ),
        adjustment_replay_receipts=_extend_replay_receipts(
            adjustment_replay_receipts,
            adjustment_inputs,
            _adjustment_replay_fingerprint,
        ),
        budget_state=budget,
        trace_events=tuple(events),
    )
    if issue_legacy_result:
        return _issue_hybrid_collective_step(
            result,
            protocol_id=protocol_id,
            target=target,
        )
    return result


def _decide_collective_state(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    state: CollectiveDecisionState,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
    validate_score_breakdown(state)
    active_ids = {
        candidate.id
        for candidate in candidate_set.candidates
        if candidate.target == target
    }
    if set(state.scores) != active_ids or set(state.independent_scouts) != active_ids:
        raise GovernanceError(
            "collective decision state must cover exactly the active target candidates"
        )
    for candidate_id, scouts in state.independent_scouts.items():
        if any(not isinstance(scout_id, str) or not scout_id for scout_id in scouts):
            raise GovernanceError(
                f"collective state contains an invalid scout identity: {candidate_id}"
            )
    candidate_id, reason = select_legacy_blended_decision(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        scores=state.scores,
        independent_scouts=state.independent_scouts,
        layer_fallback_used=(
            state.layer_coordination is not None
            and state.layer_coordination.fallback_used
        ),
        fallback_candidate_id=fallback_candidate_id,
    )
    return _issue_quorum_decision(
        target=target,
        candidate_id=candidate_id,
        committed=True,
        reason=reason,
    )


for _compat_function in (
    merge_governed_layer_coordination,
    evaluate_collective_decision,
    evaluate_collective_decision_step,
    evaluate_hybrid_collective_step,
    _decide_collective_state,
):
    _compat_function.__module__ = "pheroos.governance.collective"
del _compat_function

__all__ = (
    "_decide_collective_state",
    "evaluate_collective_decision",
    "evaluate_collective_decision_step",
    "evaluate_hybrid_collective_step",
    "merge_governed_layer_coordination",
)
