from __future__ import annotations

from collections.abc import Mapping
from math import fsum, isclose
from typing import Any

from pheroos.conformance.checks._manifest import active_target, candidate_set, exercise_candidate_id, target_candidate_ids
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    AuthorityLevel,
    EvidenceGraph,
    EvidenceNode,
    HybridReplayState,
    InhibitionSignal,
    LayerPerformanceSnapshot,
    LayerProposal,
    OutputContract,
    PheromoneEdge,
    PheromoneFeedback,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
    PolicyAdjustmentProposal,
    RecruitmentSignal,
    ScoutReport,
    StopResolution,
    StrategyBias,
    apply_policy_adjustment_overlay,
    collect_pheromone_source_diversity,
    evaluate_hybrid_collective_step,
    evaluate_layer_coordination,
    evaluate_output_authorization,
    hybrid_replay_state_is_authoritative,
    layer_action_effect,
    layer_coordination_policy_from_collective,
    observe_pheromone_exploration,
    pheromone_policy_from_collective,
    replay_state_from_hybrid_step,
    score_pheromone_trails_result,
    validate_policy_adjustment_proposal,
    validate_policy_adjustment_proposals,
    verify_signal_input,
)
from pheroos.governance.quorum import QuorumDecision
from pheroos.governance.pheromone import (
    BREAKDOWN_CATEGORIES,
    pheromone_diffusion_trace_event_id,
)
from pheroos.protocol.models import (
    CapabilityManifest,
    collective_fallback_id,
    effective_pheromone_scored_subject_types,
    has_hybrid_pheromone_features,
    is_supported_pheromone_subject_type,
    required_swarm_trace_events,
    thaw_protocol_value,
)
from pheroos.trace import TraceEvent, pheromone_clip_payload_fingerprint


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(policy):
        return CheckResult("hybrid_trace_contract", True)
    missing = sorted(required_swarm_trace_events(policy) - set(manifest.protocol.trace_policy.required_events))
    if missing:
        return CheckResult("hybrid_trace_contract", False, ", ".join(missing))
    try:
        step, output_event = manifest_replay(manifest)
        replay_state = replay_state_from_hybrid_step(step)
        replayed_step, replayed_output_event = manifest_replay(
            manifest,
            replay_state=replay_state,
        )
        fallback_step, fallback_output_event = manifest_replay(manifest, force_fallback=True)
        diffusion_step, diffusion_output_event = manifest_replay(
            manifest,
            force_fallback=True,
            lifecycle_focus="diffusion",
        )
        reinforcement_step, reinforcement_output_event = manifest_replay(
            manifest,
            force_fallback=True,
            lifecycle_focus="reinforcement",
        )
    except Exception as exc:
        detail = str(exc).strip()
        return CheckResult(
            "hybrid_trace_contract",
            False,
            f"replay:{type(exc).__name__}" + (f":{detail}" if detail else ""),
        )
    primary_result = check_actual_trace(
        manifest,
        [*step.trace_events, output_event],
        decision=step.decision,
    )
    if not primary_result.ok:
        return primary_result
    replayed_result = check_actual_trace(
        manifest,
        [*replayed_step.trace_events, replayed_output_event],
        decision=replayed_step.decision,
        replay_state=replay_state,
    )
    if not replayed_result.ok:
        return CheckResult(
            "hybrid_trace_contract",
            False,
            f"idempotent_replay:{replayed_result.detail}",
        )
    fallback_result = check_actual_trace(
        manifest,
        [*fallback_step.trace_events, fallback_output_event],
        decision=fallback_step.decision,
    )
    if not fallback_result.ok:
        return CheckResult("hybrid_trace_contract", False, f"fallback_replay:{fallback_result.detail}")
    if "fallback" not in {event.event_type for event in fallback_step.trace_events}:
        return CheckResult("hybrid_trace_contract", False, "fallback_replay:fallback_event_missing")
    diffusion_result = check_actual_trace(
        manifest,
        [*diffusion_step.trace_events, diffusion_output_event],
        decision=diffusion_step.decision,
    )
    if not diffusion_result.ok:
        return CheckResult(
            "hybrid_trace_contract",
            False,
            f"diffusion_replay:{diffusion_result.detail}",
        )
    reinforcement_result = check_actual_trace(
        manifest,
        [*reinforcement_step.trace_events, reinforcement_output_event],
        decision=reinforcement_step.decision,
    )
    if not reinforcement_result.ok:
        return CheckResult(
            "hybrid_trace_contract",
            False,
            f"reinforcement_replay:{reinforcement_result.detail}",
        )
    coverage_events = (
        *step.trace_events,
        output_event,
        *replayed_step.trace_events,
        replayed_output_event,
        *diffusion_step.trace_events,
        diffusion_output_event,
        *reinforcement_step.trace_events,
        reinforcement_output_event,
    )
    observed = {event.event_type for event in coverage_events}
    coverage_problems = actual_trace_coverage_problems(
        policy,
        observed,
        events=coverage_events,
    )
    if coverage_problems:
        return CheckResult("hybrid_trace_contract", False, "; ".join(coverage_problems))
    return primary_result


def check_actual_trace(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...] | list[TraceEvent],
    *,
    decision: QuorumDecision | None = None,
    replay_state: HybridReplayState | None = None,
    enforce_declared_coverage: bool = False,
) -> CheckResult:
    """Validate a real Hybrid replay, including decision lineage and ordering."""

    policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(policy):
        return CheckResult("hybrid_trace_contract", True)
    items = tuple(events)
    problems: list[str] = []
    target = manifest.protocol.quorum_policy.target
    protocol_id = manifest.protocol.id
    active_candidates = {
        candidate.id: candidate
        for candidate in manifest.protocol.candidates
        if candidate.target == target
    }
    if not items:
        return CheckResult("hybrid_trace_contract", False, "actual_trace_empty")
    for index, event in enumerate(items):
        try:
            event.validate()
        except (TypeError, ValueError) as exc:
            problems.append(f"event:{index}:{event.event_type}:{exc}")
            continue
        if event.protocol_id != protocol_id:
            problems.append(f"event:{index}:protocol_id")
        if event.target != target:
            problems.append(f"event:{index}:target")

    score_indexes = [index for index, event in enumerate(items) if event.event_type == "candidate_score"]
    decision_indexes = [index for index, event in enumerate(items) if event.event_type in {"commit", "fallback"}]
    if not score_indexes:
        problems.append("candidate_score_missing")
    if len(decision_indexes) != 1:
        problems.append("decision_event_count")
    elif score_indexes and decision_indexes[0] <= score_indexes[-1]:
        problems.append("decision_precedes_score")

    for index in score_indexes:
        lineage = items[index].lineage
        if set(lineage.get("scores", {})) != set(active_candidates):
            problems.append(f"event:{index}:score_target_coverage")
        if set(lineage.get("scout_diversity", {})) != set(active_candidates):
            problems.append(f"event:{index}:scout_diversity_coverage")
        if set(lineage.get("pheromone_source_diversity", {})) != set(active_candidates):
            problems.append(f"event:{index}:pheromone_diversity_coverage")

    for index, event in enumerate(items):
        if event.event_type == "pheromone_score" and set(event.lineage.get("scores", {})) != set(active_candidates):
            problems.append(f"event:{index}:pheromone_score_target_coverage")

    if len(decision_indexes) == 1:
        event = items[decision_indexes[0]]
        candidate_id = event.lineage.get("candidate_id")
        candidate = active_candidates.get(candidate_id)
        if candidate is None:
            problems.append("decision_undeclared_candidate")
        if event.event_type == "fallback" and (candidate is None or not candidate.safe_fallback):
            problems.append("fallback_not_safe")
        if event.event_type == "commit" and "fallback" in str(event.lineage.get("decision_reason", "")):
            problems.append("fallback_mislabeled_commit")
        if decision is not None:
            expected_type = "fallback" if "fallback" in decision.reason else "commit"
            if event.event_type != expected_type:
                problems.append("decision_event_type")
            if candidate_id != decision.candidate_id or event.lineage.get("decision_reason") != decision.reason:
                problems.append("decision_lineage_mismatch")

    output_indexes = [index for index, event in enumerate(items) if event.event_type == "output"]
    if output_indexes and decision_indexes and min(output_indexes) <= decision_indexes[0]:
        problems.append("output_precedes_decision")
    causal_committed_candidate = len(decision_indexes) == 1
    for index in output_indexes:
        if items[index].lineage.get("committed_candidate") is not causal_committed_candidate:
            problems.append(f"authority_output_committed_candidate:{index}")

    try:
        problems.extend(
            collective_authority_problems(
                manifest,
                items,
                replay_state=replay_state,
            )
        )
    except Exception as exc:
        detail = str(exc).strip()
        problems.append(
            f"authority_reconstruction:{type(exc).__name__}" + (f":{detail}" if detail else "")
        )

    if enforce_declared_coverage and policy is not None:
        problems.extend(
            actual_trace_coverage_problems(
                policy,
                {event.event_type for event in items},
                events=items,
            )
        )

    return CheckResult("hybrid_trace_contract", not problems, "; ".join(problems))


def actual_trace_coverage_problems(
    policy: Any,
    observed: set[str],
    *,
    events: tuple[TraceEvent, ...] | list[TraceEvent] = (),
) -> list[str]:
    required = set(required_swarm_trace_events(policy))
    competitive = (
        policy.pheromone_response_model == "competitive"
        or policy.pheromone_competition_mode == "normalize"
        or any(
            profile.response_model == "competitive"
            and bool(
                effective_pheromone_scored_subject_types(
                    kind,
                    profile,
                    policy.pheromone_scored_subject_types,
                )
            )
            for kind, profile in policy.pheromone_kind_profiles.items()
        )
    )
    if not competitive:
        required.discard("pheromone_normalize")
    if not policy.exploration_enabled:
        required.discard("pheromone_observe")
    if (
        replay_evaporation_kind(policy) is None
        or policy.pheromone_max_strength <= policy.pheromone_min_strength
    ):
        required.discard("pheromone_evaporate")
    if (
        policy.pheromone_max_strength * policy.pheromone_diffusion_attenuation
        < policy.pheromone_min_strength
    ):
        # The declared bounded transition is a truthful diffuse_rejected clip;
        # no valid active trail can cross the minimum-strength floor.
        required.discard("pheromone_diffuse")
    # A replay produces exactly one of the two decision transitions.
    if observed & {"commit", "fallback"}:
        required -= ({"commit", "fallback"} - observed)
    problems = [
        f"actual_event_missing:{event_type}"
        for event_type in sorted(required - observed)
    ]
    if (
        "pheromone_reinforce" in required
        and "pheromone_reinforce" in observed
        and events
        and not has_positive_reinforcement_state_change(events)
    ):
        problems.append("actual_event_missing:pheromone_reinforce_state_change")
    return problems


def has_positive_reinforcement_state_change(
    events: tuple[TraceEvent, ...] | list[TraceEvent],
) -> bool:
    for event in events:
        if event.event_type != "pheromone_reinforce":
            continue
        try:
            delta = float(event.lineage.get("delta", 0.0))
            old_strength = float(event.lineage.get("old_strength", 0.0))
            new_strength = float(event.lineage.get("new_strength", 0.0))
        except (TypeError, ValueError):
            continue
        if delta > 0.0 and new_strength > old_strength:
            return True
    return False


def collective_authority_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    *,
    replay_state: HybridReplayState | None = None,
) -> list[str]:
    """Reconstruct the authority gates that justify commit or safe fallback."""

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return ["authority_collective_policy_missing"]
    problems: list[str] = []
    candidate_events = [(index, event) for index, event in enumerate(events) if event.event_type == "candidate_score"]
    consensus_events = [(index, event) for index, event in enumerate(events) if event.event_type == "consensus_check"]
    decision_events = [
        (index, event) for index, event in enumerate(events) if event.event_type in {"commit", "fallback"}
    ]
    if len(candidate_events) != 1:
        return ["authority_candidate_score_count"]
    if len(consensus_events) != 1:
        return ["authority_consensus_check_count"]
    if len(decision_events) != 1:
        return ["authority_decision_event_count"]
    score_index, score_event = candidate_events[0]
    consensus_index, consensus_event = consensus_events[0]
    decision_index, decision_event = decision_events[0]
    if not score_index < consensus_index < decision_index:
        problems.append("authority_score_consensus_decision_order")
    problems.extend(event_stage_order_problems(events))

    consensus = consensus_event.lineage
    if consensus.get("quorum_threshold") != policy.quorum_threshold:
        problems.append("authority_quorum_threshold_mismatch")
    if consensus.get("min_independent_scouts") != policy.min_independent_scouts:
        problems.append("authority_scout_threshold_mismatch")

    scores = score_event.lineage.get("scores", {})
    breakdown = score_event.lineage.get("score_breakdown", {})
    scout_diversity = score_event.lineage.get("scout_diversity", {})
    active_ids = {
        candidate.id
        for candidate in manifest.protocol.candidates
        if candidate.target == manifest.protocol.quorum_policy.target
    }
    scout_ids: dict[str, set[str]] = {candidate_id: set() for candidate_id in active_ids}
    all_scout_ids: set[str] = set()
    scout_support: dict[str, float] = {candidate_id: 0.0 for candidate_id in active_ids}
    recruitment: dict[str, float] = {candidate_id: 0.0 for candidate_id in active_ids}
    inhibition: dict[str, float] = {candidate_id: 0.0 for candidate_id in active_ids}
    recruitment_sources: set[tuple[str, str]] = set()
    inhibition_sources: set[tuple[str, str]] = set()
    scout_trace_ids: set[str] = set()
    recruitment_trace_ids: set[str] = set()
    inhibition_trace_ids: set[str] = set()
    collective_lineage_ids: set[str] = set()

    def record_collective_lineage(
        source_trace: Any,
        verification_trace: Any,
        index: int,
    ) -> None:
        for trace_event_id in (source_trace, verification_trace):
            if not isinstance(trace_event_id, str) or not trace_event_id:
                continue
            if trace_event_id in collective_lineage_ids:
                problems.append(
                    f"authority_duplicate_collective_trace:{index}:{trace_event_id}"
                )
            collective_lineage_ids.add(trace_event_id)
    observed_scout_count = 0
    for index, event in enumerate(events[:score_index]):
        lineage = event.lineage
        if event.event_type == "scout_report":
            observed_scout_count += 1
            candidate_id = lineage.get("candidate_id")
            scout_id = lineage.get("scout_id")
            if candidate_id not in active_ids:
                problems.append(f"authority_scout_target:{index}")
                continue
            if scout_id in all_scout_ids:
                problems.append(f"authority_duplicate_scout:{scout_id}")
            all_scout_ids.add(scout_id)
            scout_ids[candidate_id].add(scout_id)
            support = float(lineage.get("support", 0.0))
            if support > float(policy.quorum_threshold):
                problems.append(f"authority_scout_strength_bound:{index}")
            scout_support[candidate_id] += support
            source_trace = lineage.get("source_trace_event_id")
            verification_trace = lineage.get("verification_trace_event_id")
            if not source_trace or not verification_trace:
                problems.append(f"authority_scout_verification_lineage:{index}")
            else:
                record_collective_lineage(source_trace, verification_trace, index)
                scout_trace_ids.add(source_trace)
        elif event.event_type == "recruit":
            candidate_id = lineage.get("candidate_id")
            identity = (lineage.get("source_id"), candidate_id)
            if not policy.recruitment_enabled:
                problems.append(f"authority_recruitment_disabled:{index}")
            if identity in recruitment_sources:
                problems.append(f"authority_duplicate_recruitment:{identity[0]}")
            recruitment_sources.add(identity)
            if candidate_id not in active_ids or not lineage.get("verification_trace_event_id"):
                problems.append(f"authority_recruitment_lineage:{index}")
                continue
            record_collective_lineage(
                lineage.get("source_trace_event_id"),
                lineage.get("verification_trace_event_id"),
                index,
            )
            recruitment_trace_ids.add(str(lineage.get("source_trace_event_id")))
            strength = float(lineage.get("strength", 0.0))
            if strength > float(policy.quorum_threshold):
                problems.append(f"authority_recruitment_strength_bound:{index}")
            recruitment[candidate_id] += strength
        elif event.event_type == "inhibit":
            candidate_id = lineage.get("candidate_id")
            identity = (lineage.get("source_id"), candidate_id)
            if not policy.inhibition_enabled:
                problems.append(f"authority_inhibition_disabled:{index}")
            if identity in inhibition_sources:
                problems.append(f"authority_duplicate_inhibition:{identity[0]}")
            inhibition_sources.add(identity)
            if candidate_id not in active_ids or not lineage.get("verification_trace_event_id"):
                problems.append(f"authority_inhibition_lineage:{index}")
                continue
            record_collective_lineage(
                lineage.get("source_trace_event_id"),
                lineage.get("verification_trace_event_id"),
                index,
            )
            inhibition_trace_ids.add(str(lineage.get("source_trace_event_id")))
            strength = float(lineage.get("strength", 0.0))
            if strength > float(policy.quorum_threshold):
                problems.append(f"authority_inhibition_strength_bound:{index}")
            inhibition[candidate_id] += strength

    explore_events = [event for event in events[:score_index] if event.event_type == "explore"]
    if observed_scout_count:
        if len(explore_events) != 1 or explore_events[0].lineage.get("scout_count") != observed_scout_count:
            problems.append("authority_explore_scout_count")
    elif explore_events:
        problems.append("authority_explore_without_scouts")

    problems.extend(pheromone_lifecycle_policy_problems(manifest, events[:score_index]))
    problems.extend(policy_adjustment_trace_problems(policy, events[:score_index]))
    pheromone_score_events = [
        event for event in events if event.event_type == "pheromone_score"
    ]
    if len(pheromone_score_events) != 1:
        problems.append("authority_pheromone_score_count")
    else:
        problems.extend(
            replay_trace_problems(
                events,
                pheromone_score_events[0],
                replay_state=replay_state,
                protocol_id=manifest.protocol.id,
                target=manifest.protocol.quorum_policy.target,
            )
        )

    for candidate_id in active_ids:
        categories = breakdown.get(candidate_id, {})
        if set(categories) != set(BREAKDOWN_CATEGORIES):
            problems.append(f"authority_score_categories:{candidate_id}")
        if scout_diversity.get(candidate_id) != len(scout_ids[candidate_id]):
            problems.append(f"authority_scout_diversity:{candidate_id}")
        if not near(categories.get("scout", 0.0), scout_support[candidate_id]):
            problems.append(f"authority_scout_score:{candidate_id}")
        if not near(categories.get("recruitment", 0.0), recruitment[candidate_id]):
            problems.append(f"authority_recruitment_score:{candidate_id}")
        if not near(categories.get("inhibition", 0.0), -inhibition[candidate_id]):
            problems.append(f"authority_inhibition_score:{candidate_id}")

    pheromone_events = [
        event for event in events[:score_index] if event.event_type == "pheromone_score"
    ]
    if policy.pheromone_enabled:
        if len(pheromone_events) != 1:
            problems.append("authority_pheromone_score_count")
        else:
            pheromone_lineage = pheromone_events[0].lineage
            pheromone_scores = pheromone_lineage.get("scores", {})
            pheromone_breakdown = pheromone_lineage.get("score_breakdown", {})
            problems.extend(
                pheromone_score_reconstruction_problems(
                    manifest,
                    events[:score_index],
                    pheromone_events[0],
                    score_event,
                )
            )
            for candidate_id in active_ids:
                pheromone_total = fsum(
                    float(value)
                    for category, value in breakdown.get(candidate_id, {}).items()
                    if category.startswith("pheromone_")
                )
                if not near(pheromone_total, pheromone_scores.get(candidate_id, 0.0)):
                    problems.append(f"authority_pheromone_score:{candidate_id}")
                for category in (
                    item for item in BREAKDOWN_CATEGORIES if item.startswith("pheromone_")
                ):
                    if not near(
                        breakdown.get(candidate_id, {}).get(category, 0.0),
                        pheromone_breakdown.get(candidate_id, {}).get(category, 0.0),
                    ):
                        problems.append(
                            f"authority_pheromone_category:{candidate_id}:{category}"
                        )

    coordination_events = [
        event for event in events[:score_index] if event.event_type == "coordination_assess"
    ]
    resolution_events = [
        event for event in events[:score_index] if event.event_type == "coordination_resolve"
    ]
    proposal_events = [
        event for event in events[:score_index] if event.event_type == "layer_proposal"
    ]
    resolution = resolution_events[-1].lineage if resolution_events else {}
    proposal_trace_ids = {
        event.lineage.get("source_trace_event_id") for event in proposal_events
    }
    proposal_trace_ids.discard(None)
    if len(proposal_trace_ids) != len(proposal_events):
        problems.append("authority_duplicate_layer_proposal_lineage")
    problems.extend(layer_pheromone_lineage_problems(events[:score_index], proposal_events))
    if len(coordination_events) != 1 or len(resolution_events) != 1:
        problems.append("authority_coordination_event_count")
    else:
        if set(coordination_events[0].lineage.get("proposal_lineage", ())) != proposal_trace_ids:
            problems.append("authority_coordination_proposal_lineage")
        if set(resolution.get("proposal_lineage", ())) != proposal_trace_ids:
            problems.append("authority_resolution_proposal_lineage")
        problems.extend(
            coordination_replay_problems(
                manifest,
                events[:score_index],
                proposal_events,
                coordination_events[0],
                resolution_events[0],
                breakdown,
                active_ids,
            )
        )

    qualified = sorted(
        (
            candidate_id
            for candidate_id in active_ids
            if float(scores.get(candidate_id, 0.0)) >= float(policy.quorum_threshold)
            and int(scout_diversity.get(candidate_id, 0)) >= policy.min_independent_scouts
        ),
        key=lambda candidate_id: (-float(scores[candidate_id]), candidate_id),
    )
    decision_candidate = decision_event.lineage.get("candidate_id")
    coordination_fallback = bool(resolution.get("fallback_used", False))
    if decision_event.event_type == "commit":
        if coordination_fallback:
            problems.append("authority_commit_during_coordination_fallback")
        if not qualified:
            problems.append("authority_commit_without_consensus")
        elif decision_candidate != qualified[0]:
            problems.append("authority_commit_not_top_qualified_candidate")
    else:
        if qualified and not coordination_fallback:
            problems.append("authority_fallback_despite_consensus")
        if coordination_fallback and resolution.get("selected_candidate") != decision_candidate:
            problems.append("authority_coordination_fallback_candidate")

    if coordination_fallback:
        expected_event_type = "fallback"
        expected_candidate = resolution.get("selected_candidate")
        expected_reason = "safe_layer_coordination_fallback"
    elif qualified:
        expected_event_type = "commit"
        expected_candidate = qualified[0]
        expected_reason = "collective_consensus"
    else:
        expected_event_type = "fallback"
        expected_candidate = collective_fallback_id(manifest.protocol)
        expected_reason = "safe_collective_fallback"
    if decision_event.event_type != expected_event_type:
        problems.append("authority_decision_semantic_event_type")
    if decision_candidate != expected_candidate:
        problems.append("authority_decision_semantic_candidate")
    if decision_event.lineage.get("decision_reason") != expected_reason:
        problems.append("authority_decision_semantic_reason")
    if decision_event.reason != expected_reason:
        problems.append("authority_decision_event_reason")

    upstream = set(decision_event.lineage.get("upstream_score_lineage", ()))
    if "candidate_score" not in upstream:
        problems.append("authority_candidate_score_lineage")
    if not scout_trace_ids.issubset(upstream):
        problems.append("authority_scout_upstream_lineage")
    if not recruitment_trace_ids.issubset(upstream):
        problems.append("authority_recruitment_upstream_lineage")
    if not inhibition_trace_ids.issubset(upstream):
        problems.append("authority_inhibition_upstream_lineage")
    accepted_adjustment_ids = {
        str(event.lineage.get("source_trace_event_id"))
        for event in events[:score_index]
        if event.event_type == "policy_adjustment" and event.lineage.get("result") == "accepted"
    }
    if not accepted_adjustment_ids.issubset(upstream):
        problems.append("authority_adjustment_upstream_lineage")
    pheromone_trace_ids = {
        str(item.get("trace_event_id"))
        for event in pheromone_events
        for item in event.lineage.get("active_trails", ())
    }
    if policy.pheromone_enabled and "pheromone_score" not in upstream:
        problems.append("authority_pheromone_score_upstream_lineage")
    if not pheromone_trace_ids.issubset(upstream):
        problems.append("authority_pheromone_trail_upstream_lineage")
    if not proposal_trace_ids.issubset(upstream):
        problems.append("authority_layer_upstream_lineage")
    return problems


def replay_trace_problems(
    events: tuple[TraceEvent, ...],
    score_event: TraceEvent,
    *,
    replay_state: HybridReplayState | None,
    protocol_id: str,
    target: str,
) -> list[str]:
    """Bind every replay claim to an externally supplied issued replay state."""

    problems: list[str] = []
    authoritative: dict[str, Mapping[str, tuple[Any, ...]]] = {
        lifecycle: {}
        for lifecycle in ("deposit", "diffusion", "feedback", "adjustment")
    }
    if replay_state is not None:
        if not hybrid_replay_state_is_authoritative(replay_state):
            return ["authority_replay_state_not_issued"]
        if replay_state.protocol_id != protocol_id or replay_state.target != target:
            return ["authority_replay_state_binding"]
        authoritative = {
            "deposit": replay_state.deposit_replay_receipts,
            "diffusion": replay_state.diffusion_replay_receipts,
            "feedback": replay_state.feedback_replay_receipts,
            "adjustment": replay_state.adjustment_replay_receipts,
        }
    expected: dict[str, dict[str, str]] = {
        lifecycle: {}
        for lifecycle in ("deposit", "diffusion", "feedback", "adjustment")
    }
    for index, event in enumerate(events):
        lineage = event.lineage
        if (
            event.event_type == "pheromone_observe"
            and lineage.get("result") == "replay_ignored"
        ):
            lifecycle = str(lineage.get("lifecycle", ""))
        elif (
            event.event_type == "policy_adjustment"
            and lineage.get("result") == "replay_ignored"
        ):
            lifecycle = "adjustment"
        else:
            continue
        trace_event_id = str(lineage.get("source_trace_event_id", ""))
        if lifecycle not in expected:
            problems.append(f"authority_replay_lifecycle:{index}")
            continue
        if trace_event_id in expected[lifecycle]:
            problems.append(
                f"authority_replay_duplicate:{lifecycle}:{trace_event_id}"
            )
        replay_payload = lineage.get("replay_payload")
        if not isinstance(replay_payload, (list, tuple)):
            problems.append(f"authority_replay_payload:{index}")
            continue
        current_receipt = _canonical_trace_replay_receipt(replay_payload)
        processed_receipt = authoritative[lifecycle].get(trace_event_id)
        if processed_receipt is None:
            problems.append(
                f"authority_replay_receipt_not_in_state:{lifecycle}:{trace_event_id}"
            )
            continue
        if current_receipt != processed_receipt:
            problems.append(
                f"authority_replay_payload_state_mismatch:{lifecycle}:{trace_event_id}"
            )
        processed_digest = _replay_receipt_fingerprint(processed_receipt)
        if lineage.get("replay_payload_fingerprint") != processed_digest:
            problems.append(
                f"authority_replay_payload_fingerprint:{lifecycle}:{trace_event_id}"
            )
        if lineage.get("processed_payload_fingerprint") != processed_digest:
            problems.append(
                f"authority_replay_processed_fingerprint:{lifecycle}:{trace_event_id}"
            )
        expected[lifecycle][trace_event_id] = processed_digest

    observed = score_event.lineage.get("processed_replay_receipts")
    if not isinstance(observed, dict):
        return [*problems, "authority_replay_receipt_snapshot_missing"]
    if set(observed) != set(expected):
        problems.append("authority_replay_receipt_snapshot_lifecycles")
        return problems
    for lifecycle, receipts in expected.items():
        if observed.get(lifecycle) != receipts:
            problems.append(f"authority_replay_receipt_snapshot:{lifecycle}")
    return problems


def _canonical_trace_replay_receipt(value: Any) -> tuple[Any, ...]:
    def freeze(item: Any) -> Any:
        if isinstance(item, Mapping):
            return tuple(
                (str(key), freeze(nested))
                for key, nested in sorted(item.items(), key=lambda pair: str(pair[0]))
            )
        if isinstance(item, (list, tuple)):
            return tuple(freeze(nested) for nested in item)
        return item

    return tuple(freeze(item) for item in value)


def _replay_receipt_fingerprint(receipt: tuple[Any, ...]) -> str:
    return pheromone_clip_payload_fingerprint(
        {
            "lifecycle": "replay_receipt",
            "receipt": receipt,
        }
    )


def pheromone_lifecycle_policy_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
) -> list[str]:
    """Causally replay lifecycle transitions into the scored active memory."""

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return ["authority_pheromone_policy_missing"]
    problems: list[str] = []
    try:
        accepted = [
            PolicyAdjustmentProposal(
                layer_id=str(event.lineage.get("layer_id", "")),
                source_id=str(event.lineage.get("source_id", "")),
                adjustments=dict(event.lineage.get("proposed_values", {})),
                provenance=str(event.lineage.get("provenance", "")),
                trace_event_id=str(event.lineage.get("source_trace_event_id", "")),
            )
            for event in events
            if event.event_type == "policy_adjustment"
            and event.lineage.get("result") == "accepted"
        ]
        batch = validate_policy_adjustment_proposals(accepted, policy)
        effective_policy = apply_policy_adjustment_overlay(policy, batch.overlay)
        runtime_policy = pheromone_policy_from_collective(effective_policy)
    except Exception as exc:
        return [f"authority_pheromone_lifecycle_policy:{type(exc).__name__}"]

    maximum = float(runtime_policy.max_strength)
    minimum = float(runtime_policy.min_strength)
    round_cap = float(runtime_policy.per_round_deposit_cap)
    source_cap = float(runtime_policy.per_source_cap)
    round_used = 0.0
    source_used: dict[str, float] = {}
    states: dict[str, dict[str, Any]] = {}
    diffusion_lineage: dict[str, tuple[str, int]] = {}
    diffusion_parents: dict[str, str] = {}
    expiration_effective_ttls: dict[str, tuple[str, int]] = {}
    score_events = [event for event in events if event.event_type == "pheromone_score"]
    score_current_step = (
        int(score_events[0].lineage.get("current_step", 0))
        if len(score_events) == 1
        else None
    )
    declared_candidate_ids = {
        candidate.id
        for candidate in manifest.protocol.candidates
        if candidate.target == manifest.protocol.quorum_policy.target
    }

    def state(
        *,
        trace_event_id: str,
        source_id: str,
        candidate_id: str,
        subject_type: str,
        subject_id: str,
        kind: str,
        strength: float,
        source_kind: str | None = None,
        provenance: str | None = None,
        deposited_at_step: int | None = None,
        updated_at_step: int | None = None,
        ttl_steps: int | None = None,
        ttl_bound: bool = False,
    ) -> dict[str, Any]:
        return {
            "trace_event_id": trace_event_id,
            "source_id": source_id,
            "candidate_id": candidate_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "kind": kind,
            "strength": strength,
            "source_kind": source_kind,
            "provenance": provenance,
            "deposited_at_step": deposited_at_step,
            "updated_at_step": updated_at_step,
            "ttl_steps": ttl_steps,
            "ttl_bound": ttl_bound,
        }

    def source_state(index: int, event: TraceEvent) -> dict[str, Any]:
        item = event.lineage
        source_trace_id = str(item.get("source_trace_event_id", ""))
        if event.event_type == "pheromone_diffuse" or (
            event.event_type == "pheromone_clip"
            and item.get("lifecycle") == "diffusion"
        ):
            source_subject = item.get("source_subject", {})
            subject_type = str(source_subject.get("type", ""))
            subject_id = str(source_subject.get("id", ""))
        else:
            subject_type = str(item.get("subject_type", ""))
            subject_id = str(item.get("subject_id", ""))
        claimed = state(
            trace_event_id=source_trace_id,
            source_id=str(item.get("source_id", "")),
            candidate_id=str(item.get("candidate_id", "")),
            subject_type=subject_type,
            subject_id=subject_id,
            kind=str(item.get("source_kind", "")),
            strength=float(item.get("source_strength", 0.0)),
            # ``source_kind`` describes the resulting transition state, not
            # the identity of the source state.  A stale trail, for example,
            # retains the alarm kind it expired from.  Bind this field only
            # when replaying the result below.
            source_kind=None,
            provenance=(
                str(item.get("provenance", ""))
                if event.event_type != "pheromone_reinforce"
                else None
            ),
            deposited_at_step=(
                int(item["deposited_at_step"])
                if event.event_type in {"pheromone_evaporate", "pheromone_expire"}
                else None
            ),
            updated_at_step=(
                int(item["source_updated_at_step"])
                if event.event_type in {"pheromone_evaporate", "pheromone_expire"}
                else None
            ),
            ttl_steps=(
                int(item["ttl_steps"])
                if item.get("ttl_steps") is not None
                else None
            ),
            # Expiration lineage records the effective TTL (explicit trail
            # override or kind-profile fallback), not necessarily the raw TTL
            # retained by the stale trail.
            ttl_bound="ttl_steps" in item and event.event_type != "pheromone_expire",
        )
        known = states.get(source_trace_id)
        if known is None:
            states[source_trace_id] = claimed
            return claimed
        if not lifecycle_state_near(known, claimed):
            problems.append(f"authority_pheromone_source_transition:{index}")
        return known

    def consume_budget(
        *,
        index: int,
        source_id: str,
        requested: float,
        applied: float,
        round_remaining: Any,
        source_remaining: Any,
        enforce_minimum: bool,
    ) -> None:
        nonlocal round_used
        available_round = max(0.0, round_cap - round_used)
        used_by_source = source_used.get(source_id, 0.0)
        available_source = max(0.0, source_cap - used_by_source)
        expected = min(requested, maximum, available_round, available_source)
        if enforce_minimum and expected < minimum:
            expected = 0.0
        if not near(applied, expected):
            problems.append(f"authority_pheromone_budget_applied:{index}")
            # Replay the recorded state after reporting so one forged amount
            # cannot create a cascade of misleading remaining-budget errors.
            expected = applied
        round_used += expected
        source_used[source_id] = used_by_source + expected
        if not near(round_remaining, max(0.0, round_cap - round_used)):
            problems.append(f"authority_pheromone_round_budget_lineage:{index}")
        if not near(source_remaining, max(0.0, source_cap - source_used[source_id])):
            problems.append(f"authority_pheromone_source_budget_lineage:{index}")

    def expected_budget_application(
        *,
        source_id: str,
        requested: float,
        enforce_minimum: bool,
    ) -> tuple[float, float, float]:
        available_round = max(0.0, round_cap - round_used)
        available_source = max(0.0, source_cap - source_used.get(source_id, 0.0))
        applied = min(requested, maximum, available_round, available_source)
        if enforce_minimum and applied < minimum:
            applied = 0.0
        return (
            applied,
            max(0.0, available_round - applied),
            max(0.0, available_source - applied),
        )

    deposit_events_by_trace = {
        str(event.lineage.get("trace_event_id", "")): event
        for event in events
        if event.event_type == "pheromone_deposit"
    }
    diffuse_events_by_trace = {
        str(event.lineage.get("trace_event_id", "")): event
        for event in events
        if event.event_type == "pheromone_diffuse"
    }
    observed_clip_ids: set[str] = set()

    for index, event in enumerate(events):
        item = event.lineage
        event_type = event.event_type
        if event_type not in {
            "pheromone_deposit",
            "pheromone_evaporate",
            "pheromone_expire",
            "pheromone_diffuse",
            "pheromone_reinforce",
            "pheromone_clip",
        }:
            continue
        if event_type == "pheromone_clip":
            trace_id = str(item.get("trace_event_id", ""))
            if trace_id in observed_clip_ids:
                problems.append(f"authority_pheromone_clip_duplicate:{trace_id}")
            observed_clip_ids.add(trace_id)
            lifecycle = str(item.get("lifecycle", ""))
            source_id = str(item.get("source_id", ""))
            requested = float(item.get("requested_strength", 0.0))
            applied = float(item.get("applied_strength", 0.0))
            if applied > maximum:
                problems.append(f"authority_pheromone_clip_strength_bound:{index}")
            if item.get("candidate_id") not in declared_candidate_ids:
                problems.append(f"authority_pheromone_clip_candidate:{index}")
            if not is_supported_pheromone_subject_type(
                str(item.get("subject_type", ""))
            ):
                problems.append(f"authority_pheromone_clip_subject_type:{index}")
            if (
                item.get("subject_type") == "candidate"
                and item.get("subject_id") != item.get("candidate_id")
            ):
                problems.append(f"authority_pheromone_clip_subject_id:{index}")
            if score_current_step is not None and int(item.get("step", 0)) > score_current_step:
                problems.append(f"authority_pheromone_clip_future_step:{index}")
            if lifecycle == "deposit":
                expected, round_remaining, source_remaining = expected_budget_application(
                    source_id=source_id,
                    requested=requested,
                    enforce_minimum=True,
                )
                if not near(applied, expected):
                    problems.append(f"authority_pheromone_clip_deposit_applied:{index}")
                deposit_event = deposit_events_by_trace.get(trace_id)
                if applied > 0:
                    if deposit_event is None:
                        problems.append(f"authority_pheromone_clip_deposit_missing:{index}")
                    else:
                        deposit = deposit_event.lineage
                        for field_name in (
                            "source_id",
                            "provenance",
                            "candidate_id",
                            "subject_type",
                            "subject_id",
                            "kind",
                            "source_kind",
                            "source_trace_event_id",
                            "trace_event_id",
                            "requested_strength",
                            "applied_strength",
                            "new_strength",
                            "step",
                        ):
                            left = item.get(field_name)
                            right = deposit.get(field_name)
                            if isinstance(left, (int, float)) and not isinstance(left, bool):
                                if not near(left, right):
                                    problems.append(
                                        f"authority_pheromone_clip_deposit_transition:{index}:{field_name}"
                                    )
                            elif left != right:
                                problems.append(
                                    f"authority_pheromone_clip_deposit_transition:{index}:{field_name}"
                                )
                elif deposit_event is not None:
                    problems.append(f"authority_pheromone_clip_rejected_deposit_applied:{index}")
            elif lifecycle == "diffusion":
                source = source_state(index, event)
                source_trace_id = str(item.get("source_trace_event_id", ""))
                hop = int(item.get("hop", 0))
                root_trace_id = str(item.get("root_trace_event_id", ""))
                target_subject = item.get("target_subject", {})
                if hop > int(effective_policy.pheromone_diffusion_max_hops):
                    problems.append(f"authority_pheromone_clip_diffusion_hop:{index}")
                if not near(
                    item.get("policy_attenuation"),
                    effective_policy.pheromone_diffusion_attenuation,
                ):
                    problems.append(
                        f"authority_pheromone_clip_diffusion_policy_attenuation:{index}"
                    )
                parent = diffusion_lineage.get(source_trace_id)
                if parent is None:
                    if hop != 1 or root_trace_id != source_trace_id:
                        problems.append(
                            f"authority_pheromone_clip_diffusion_parent_lineage:{index}"
                        )
                elif root_trace_id != parent[0] or hop != parent[1] + 1:
                    problems.append(
                        f"authority_pheromone_clip_diffusion_parent_lineage:{index}"
                    )
                if (
                    target_subject.get("type") != item.get("subject_type")
                    or target_subject.get("id") != item.get("subject_id")
                ):
                    problems.append(
                        f"authority_pheromone_clip_diffusion_target_subject:{index}"
                    )
                canonical_trace_id = pheromone_diffusion_trace_event_id(
                    root_trace_id,
                    hop,
                    str(target_subject.get("type", "")),
                    str(target_subject.get("id", "")),
                )
                if trace_id != canonical_trace_id or trace_id in states:
                    problems.append(
                        f"authority_pheromone_clip_diffusion_trace_lineage:{index}"
                    )
                expected, round_remaining, source_remaining = expected_budget_application(
                    source_id=source_id,
                    requested=requested,
                    enforce_minimum=True,
                )
                if not near(expected, 0.0) or not near(applied, 0.0):
                    problems.append(f"authority_pheromone_clip_diffusion_rejection:{index}")
                if trace_id in diffuse_events_by_trace:
                    problems.append(f"authority_pheromone_clip_diffusion_applied:{index}")
                if item.get("source_kind") != source.get("kind"):
                    problems.append(f"authority_pheromone_clip_diffusion_source_kind:{index}")
                if item.get("kind") != item.get("source_kind"):
                    problems.append(f"authority_pheromone_clip_diffusion_kind:{index}")
                if item.get("provenance") != source.get("provenance"):
                    problems.append(f"authority_pheromone_clip_diffusion_provenance:{index}")
                if score_current_step is not None and int(item.get("step", 0)) > score_current_step:
                    problems.append(f"authority_pheromone_clip_diffusion_future_step:{index}")
            else:
                source_trace_id = str(item.get("source_trace_event_id", ""))
                feedback_trace_id = str(item.get("feedback_trace_event_id", ""))
                source_was_known = source_trace_id in states
                source = source_state(index, event)
                expected_kind = {
                    "success": "positive",
                    "failure": "negative",
                    "blocked": "cautionary",
                    "congested": "cautionary",
                    "hazard": "alarm",
                    "novel": "novelty",
                    "stale": "stale",
                }.get(str(item.get("outcome", "")))
                if expected_kind is None or item.get("kind") != expected_kind:
                    problems.append(f"authority_pheromone_clip_feedback_outcome_kind:{index}")
                if item.get("source_kind") != item.get("kind"):
                    problems.append(f"authority_pheromone_clip_feedback_source_kind:{index}")
                if item.get("candidate_id") not in declared_candidate_ids:
                    problems.append(f"authority_pheromone_clip_feedback_candidate:{index}")
                if not is_supported_pheromone_subject_type(
                    str(item.get("subject_type", ""))
                ):
                    problems.append(f"authority_pheromone_clip_feedback_subject_type:{index}")
                if (
                    item.get("subject_type") == "candidate"
                    and item.get("subject_id") != item.get("candidate_id")
                ):
                    problems.append(f"authority_pheromone_clip_feedback_subject_id:{index}")
                if score_current_step is not None and int(item.get("step", 0)) > score_current_step:
                    problems.append(f"authority_pheromone_clip_feedback_future_step:{index}")
                if trace_id != feedback_trace_id:
                    problems.append(f"authority_pheromone_clip_feedback_lineage:{index}")
                if float(item.get("source_strength", 0.0)) <= 0.0 and not (
                    source_trace_id == feedback_trace_id == trace_id
                ):
                    problems.append(
                        f"authority_pheromone_clip_feedback_new_trail_lineage:{index}"
                    )
                headroom_request = min(
                    requested,
                    max(0.0, maximum - float(source.get("strength", 0.0))),
                )
                expected, round_remaining, source_remaining = expected_budget_application(
                    source_id=source_id,
                    requested=headroom_request,
                    enforce_minimum=float(source.get("strength", 0.0)) <= 0.0,
                )
                if not near(expected, 0.0) or not near(applied, 0.0):
                    problems.append(f"authority_pheromone_clip_feedback_rejection:{index}")
                if not source_was_known:
                    states.pop(source_trace_id, None)
            if not near(item.get("round_budget_remaining"), round_remaining):
                problems.append(f"authority_pheromone_clip_round_budget:{index}")
            if not near(item.get("source_budget_remaining"), source_remaining):
                problems.append(f"authority_pheromone_clip_source_budget:{index}")
            continue

        for field_name in ("source_strength", "new_strength"):
            if float(item.get(field_name, 0.0)) > maximum:
                problems.append(f"authority_{event_type}_{field_name}_bound:{index}")

        if event_type == "pheromone_deposit":
            trace_id = str(item.get("trace_event_id", ""))
            if trace_id in states:
                problems.append(f"authority_pheromone_duplicate_transition:{trace_id}")
            applied = float(item.get("applied_strength", 0.0))
            consume_budget(
                index=index,
                source_id=str(item.get("source_id", "")),
                requested=float(item.get("requested_strength", 0.0)),
                applied=applied,
                round_remaining=item.get("round_budget_remaining"),
                source_remaining=item.get("source_budget_remaining"),
                enforce_minimum=True,
            )
            states[trace_id] = state(
                trace_event_id=trace_id,
                source_id=str(item.get("source_id", "")),
                candidate_id=str(item.get("candidate_id", "")),
                subject_type=str(item.get("subject_type", "")),
                subject_id=str(item.get("subject_id", "")),
                kind=str(item.get("kind", "")),
                strength=float(item.get("new_strength", 0.0)),
                source_kind=str(item.get("source_kind", "")),
                provenance=str(item.get("provenance", "")),
                deposited_at_step=int(item.get("deposited_at_step", 0)),
                updated_at_step=int(item.get("updated_at_step", 0)),
                ttl_steps=(
                    int(item["ttl_steps"])
                    if item.get("ttl_steps") is not None
                    else None
                ),
                # Deposits with no explicit TTL must remain distinguishable
                # from a forged active-trail override.
                ttl_bound=True,
            )
            continue

        source = source_state(index, event)
        source_trace_id = str(item.get("source_trace_event_id", ""))
        result_trace_id = str(item.get("trace_event_id", ""))

        if event_type == "pheromone_evaporate":
            elapsed = int(item.get("elapsed_steps", 0))
            profile = runtime_policy.kind_profiles.get(source["kind"])
            rate = (
                profile.evaporation_rate
                if profile is not None and profile.evaporation_rate is not None
                else runtime_policy.evaporation_rate
            )
            retention = max(0.0, min(1.0, 1.0 - float(rate)))
            if runtime_policy.decay_model == "exponential":
                expected = source["strength"] * (retention ** elapsed)
            elif runtime_policy.decay_model == "step":
                expected = source["strength"] * retention
            else:
                expected = source["strength"] * max(0.0, 1.0 - float(rate) * elapsed)
            if source["kind"] == "novelty" and runtime_policy.exploration_enabled:
                expected *= (1.0 - runtime_policy.novelty_decay_rate) ** elapsed
            expected = min(maximum, max(minimum, expected))
            expected_profile = (
                f"kind:{source['kind']}"
                if source["kind"] in runtime_policy.kind_profiles
                else f"global:{runtime_policy.decay_model}"
            )
            if not near(item.get("new_strength"), expected):
                problems.append(f"authority_pheromone_evaporation_replay:{index}")
            if item.get("profile") != expected_profile:
                problems.append(f"authority_pheromone_evaporation_profile:{index}")
            states[source_trace_id] = state(
                **{
                    **source,
                    "trace_event_id": result_trace_id,
                    "kind": str(item.get("kind", "")),
                    "strength": float(item.get("new_strength", 0.0)),
                    "source_kind": str(item.get("source_kind", "")),
                    "provenance": str(item.get("provenance", "")),
                    "deposited_at_step": int(item.get("deposited_at_step", 0)),
                    "updated_at_step": int(item.get("step", 0)),
                    "ttl_steps": source.get("ttl_steps"),
                    "ttl_bound": source.get("ttl_bound", False),
                }
            )
            continue

        if event_type == "pheromone_expire":
            if not near(item.get("new_strength"), minimum):
                problems.append(f"authority_pheromone_expiry_floor:{index}")
            expiration_effective_ttls[result_trace_id] = (
                str(item.get("source_kind", "")),
                int(item.get("ttl_steps", 0)),
            )
            states[source_trace_id] = state(
                **{
                    **source,
                    "trace_event_id": result_trace_id,
                    "kind": str(item.get("kind", "")),
                    "strength": float(item.get("new_strength", 0.0)),
                    "source_kind": str(item.get("source_kind", "")),
                    "provenance": str(item.get("provenance", "")),
                    "deposited_at_step": int(item.get("deposited_at_step", 0)),
                    "updated_at_step": int(item.get("step", 0)),
                    # Expiration preserves the trail's raw TTL.  The event's
                    # ttl_steps is the effective value and is checked against
                    # the scored raw trail plus the kind profile below.
                    "ttl_steps": source.get("ttl_steps"),
                    "ttl_bound": source.get("ttl_bound", False),
                }
            )
            continue

        if event_type == "pheromone_diffuse":
            hop = int(item.get("hop", 0))
            root_trace_id = str(item.get("root_trace_event_id", ""))
            if hop > int(effective_policy.pheromone_diffusion_max_hops):
                problems.append(f"authority_pheromone_diffuse_hop_bound:{index}")
            if float(item.get("attenuation", 0.0)) > float(
                effective_policy.pheromone_diffusion_attenuation
            ) + 1e-9:
                problems.append(f"authority_pheromone_diffuse_attenuation_bound:{index}")
            if not near(
                item.get("policy_attenuation"),
                effective_policy.pheromone_diffusion_attenuation,
            ):
                problems.append(f"authority_pheromone_diffuse_policy_attenuation:{index}")
            parent = diffusion_lineage.get(source_trace_id)
            if parent is None:
                if hop != 1 or root_trace_id != source_trace_id:
                    problems.append(f"authority_pheromone_diffuse_parent_lineage:{index}")
            elif root_trace_id != parent[0] or hop != parent[1] + 1:
                problems.append(f"authority_pheromone_diffuse_parent_lineage:{index}")
            target_subject = item.get("target_subject", {})
            canonical_trace_id = pheromone_diffusion_trace_event_id(
                root_trace_id,
                hop,
                str(target_subject.get("type", "")),
                str(target_subject.get("id", "")),
            )
            if result_trace_id != canonical_trace_id or result_trace_id in states:
                problems.append(f"authority_pheromone_diffuse_trace_lineage:{index}")
            applied = float(item.get("applied_strength", 0.0))
            consume_budget(
                index=index,
                source_id=str(item.get("source_id", "")),
                requested=float(item.get("requested_strength", 0.0)),
                applied=applied,
                round_remaining=item.get("round_budget_remaining"),
                source_remaining=item.get("source_budget_remaining"),
                enforce_minimum=True,
            )
            states[result_trace_id] = state(
                trace_event_id=result_trace_id,
                source_id=str(item.get("source_id", "")),
                candidate_id=str(item.get("candidate_id", "")),
                subject_type=str(target_subject.get("type", "")),
                subject_id=str(target_subject.get("id", "")),
                kind=str(item.get("kind", "")),
                strength=float(item.get("new_strength", 0.0)),
                source_kind=str(item.get("source_kind", "")),
                provenance=str(item.get("provenance", "")),
                deposited_at_step=source.get("deposited_at_step"),
                updated_at_step=source.get("updated_at_step"),
                ttl_steps=source.get("ttl_steps"),
                ttl_bound=bool(source.get("ttl_bound", False)),
            )
            diffusion_lineage[result_trace_id] = (root_trace_id, hop)
            diffusion_parents[result_trace_id] = source_trace_id
            continue

        delta = float(item.get("delta", 0.0))
        feedback_trace_id = str(item.get("feedback_trace_event_id", ""))
        expected_kind = {
            "success": "positive",
            "failure": "negative",
            "blocked": "cautionary",
            "congested": "cautionary",
            "hazard": "alarm",
            "novel": "novelty",
            "stale": "stale",
        }.get(str(item.get("outcome", "")))
        if expected_kind is None or item.get("kind") != expected_kind:
            problems.append(f"authority_pheromone_reinforce_outcome_kind:{index}")
        if result_trace_id != feedback_trace_id:
            problems.append(f"authority_pheromone_reinforce_feedback_lineage:{index}")
        if source["strength"] <= 0.0 and source_trace_id != feedback_trace_id:
            problems.append(f"authority_pheromone_reinforce_new_trail_lineage:{index}")
        if result_trace_id == source_trace_id and source["strength"] > 0.0:
            problems.append(f"authority_pheromone_reinforce_self_transition:{index}")
        if result_trace_id != source_trace_id and result_trace_id in states:
            problems.append(f"authority_pheromone_duplicate_transition:{result_trace_id}")
        if delta >= 0.0:
            headroom_request = min(
                float(item.get("requested_strength", 0.0)),
                max(0.0, maximum - source["strength"]),
            )
            consume_budget(
                index=index,
                source_id=str(item.get("source_id", "")),
                requested=headroom_request,
                applied=float(item.get("applied_strength", 0.0)),
                round_remaining=item.get("budget_result", {}).get("round_remaining"),
                source_remaining=item.get("budget_result", {}).get("source_remaining"),
                enforce_minimum=source["strength"] <= 0.0,
            )
        else:
            if not near(item.get("new_strength"), minimum):
                problems.append(f"authority_pheromone_reinforce_stale_floor:{index}")
            budget = item.get("budget_result", {})
            if not near(budget.get("round_remaining"), max(0.0, round_cap - round_used)):
                problems.append(f"authority_pheromone_round_budget_lineage:{index}")
            source_remaining = max(
                0.0,
                source_cap - source_used.get(str(item.get("source_id", "")), 0.0),
            )
            if not near(budget.get("source_remaining"), source_remaining):
                problems.append(f"authority_pheromone_source_budget_lineage:{index}")
        if result_trace_id != source_trace_id:
            states.pop(source_trace_id, None)
        states[result_trace_id] = state(
            trace_event_id=result_trace_id,
            source_id=str(item.get("source_id", "")),
            candidate_id=str(item.get("candidate_id", "")),
            subject_type=str(item.get("subject_type", "")),
            subject_id=str(item.get("subject_id", "")),
            kind=str(item.get("kind", "")),
            strength=float(item.get("new_strength", 0.0)),
            source_kind=str(item.get("source_kind", "")),
            provenance=str(item.get("provenance", "")),
            deposited_at_step=(
                source.get("deposited_at_step")
                if source["strength"] > 0.0
                else int(item.get("step", 0))
            ),
            updated_at_step=int(item.get("step", 0)),
            ttl_steps=(
                source.get("ttl_steps")
                if source["strength"] > 0.0
                else (
                    runtime_policy.kind_profiles.get(str(item.get("kind", ""))).ttl_steps
                    if str(item.get("kind", "")) in runtime_policy.kind_profiles
                    else None
                )
            ),
            ttl_bound=True,
        )

    if len(score_events) == 1:
        current_step = int(score_events[0].lineage.get("current_step", 0))
        for index, event in enumerate(events):
            if event.event_type not in {
                "pheromone_deposit",
                "pheromone_evaporate",
                "pheromone_expire",
                "pheromone_reinforce",
            }:
                continue
            lifecycle_step = int(event.lineage.get("step", 0))
            if lifecycle_step > current_step:
                problems.append(f"authority_pheromone_lifecycle_future_step:{index}")
            if (
                event.event_type in {"pheromone_evaporate", "pheromone_expire"}
                and lifecycle_step != current_step
            ):
                problems.append(f"authority_pheromone_lifecycle_current_step:{index}")
        active = {
            str(item.get("trace_event_id", "")): dict(item)
            for item in score_events[0].lineage.get("active_trails", ())
        }
        for trace_id, expected in states.items():
            observed = active.get(trace_id)
            if observed is None or not lifecycle_state_near(observed, expected):
                problems.append(f"authority_pheromone_active_transition:{trace_id}")
        for trace_id, source_trace_id in diffusion_parents.items():
            observed = active.get(trace_id)
            source_observed = active.get(source_trace_id)
            if (
                observed is not None
                and source_observed is not None
                and observed.get("ttl_steps") != source_observed.get("ttl_steps")
            ):
                problems.append(f"authority_pheromone_diffuse_ttl:{trace_id}")
        for trace_id, (source_kind, recorded_effective_ttl) in expiration_effective_ttls.items():
            observed = active.get(trace_id)
            if observed is None:
                continue
            raw_ttl = observed.get("ttl_steps")
            profile = runtime_policy.kind_profiles.get(source_kind)
            expected_effective_ttl = (
                raw_ttl
                if raw_ttl is not None
                else (profile.ttl_steps if profile is not None else None)
            )
            if expected_effective_ttl != recorded_effective_ttl:
                problems.append(f"authority_pheromone_expire_ttl:{trace_id}")
    return problems


def lifecycle_state_near(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    for field_name in (
        "trace_event_id",
        "source_id",
        "candidate_id",
        "subject_type",
        "subject_id",
        "kind",
    ):
        if observed.get(field_name) != expected.get(field_name):
            return False
    if not near(observed.get("strength"), expected.get("strength")):
        return False
    for field_name in ("deposited_at_step", "updated_at_step"):
        expected_value = expected.get(field_name)
        if expected_value is not None and observed.get(field_name) != expected_value:
            return False
    expected_provenance = expected.get("provenance")
    if expected_provenance is not None and observed.get("provenance") != expected_provenance:
        return False
    expected_source_kind = expected.get("source_kind")
    if expected_source_kind is not None and observed.get("source_kind") != expected_source_kind:
        return False
    if expected.get("ttl_bound") and observed.get("ttl_steps") != expected.get("ttl_steps"):
        return False
    return True


def pheromone_score_reconstruction_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    pheromone_score_event: TraceEvent,
    candidate_score_event: TraceEvent,
) -> list[str]:
    """Re-score canonical active-trail lineage through the governance ABI."""

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return ["authority_pheromone_policy_missing"]
    accepted_proposals: list[PolicyAdjustmentProposal] = []
    for event in events:
        if event.event_type != "policy_adjustment" or event.lineage.get("result") != "accepted":
            continue
        accepted_proposals.append(
            PolicyAdjustmentProposal(
                layer_id=str(event.lineage.get("layer_id", "")),
                source_id=str(event.lineage.get("source_id", "")),
                adjustments=dict(event.lineage.get("proposed_values", {})),
                provenance=str(event.lineage.get("provenance", "")),
                trace_event_id=str(event.lineage.get("source_trace_event_id", "")),
            )
        )
    try:
        adjustment_batch = validate_policy_adjustment_proposals(
            accepted_proposals,
            policy,
        )
        effective_policy = apply_policy_adjustment_overlay(
            policy,
            adjustment_batch.overlay,
        )
        runtime_policy = pheromone_policy_from_collective(effective_policy)
        trails = [
            PheromoneTrail(
                candidate_id=str(item["candidate_id"]),
                strength=float(item["strength"]),
                subject_type=str(item["subject_type"]),
                subject_id=str(item["subject_id"]),
                target=pheromone_score_event.target,
                kind=str(item["kind"]),
                source_id=str(item["source_id"]),
                provenance=str(item["provenance"]),
                trace_event_id=str(item["trace_event_id"]),
                deposited_at_step=int(item["deposited_at_step"]),
                updated_at_step=int(item["updated_at_step"]),
                ttl_steps=(
                    int(item["ttl_steps"])
                    if item.get("ttl_steps") is not None
                    else None
                ),
            )
            for item in pheromone_score_event.lineage.get("active_trails", ())
        ]
        candidates = candidate_set(manifest)
        current_step = int(pheromone_score_event.lineage["current_step"])
        reconstructed = score_pheromone_trails_result(
            candidate_set=candidates,
            trails=trails,
            policy=runtime_policy,
            current_step=current_step,
        )
        diversity = collect_pheromone_source_diversity(
            candidate_set=candidates,
            trails=trails,
            policy=runtime_policy,
            current_step=current_step,
        )
    except Exception as exc:
        return [f"authority_pheromone_reconstruction:{type(exc).__name__}"]

    lineage = pheromone_score_event.lineage
    problems: list[str] = []
    for trail in trails:
        if trail.updated_at_step != current_step:
            problems.append(
                f"authority_pheromone_active_current_step:{trail.trace_event_id}"
            )
        profile = runtime_policy.kind_profiles.get(trail.kind)
        effective_ttl = (
            trail.ttl_steps
            if trail.ttl_steps is not None
            else (profile.ttl_steps if profile is not None else None)
        )
        if (
            effective_ttl is not None
            and current_step - trail.deposited_at_step >= effective_ttl
            and trail.kind != "stale"
        ):
            problems.append(
                f"authority_pheromone_active_ttl:{trail.trace_event_id}"
            )
    expected_dimensions = {
        "scores": reconstructed.scores,
        "score_breakdown": reconstructed.score_breakdown,
        "kind_breakdown": reconstructed.kind_breakdown,
        "subject_breakdown": reconstructed.subject_breakdown,
    }
    for field_name, expected in expected_dimensions.items():
        if not nested_numeric_mapping_near(lineage.get(field_name, {}), expected):
            problems.append(f"authority_pheromone_reconstruction_{field_name}")
    if dict(candidate_score_event.lineage.get("pheromone_source_diversity", {})) != diversity:
        problems.append("authority_pheromone_source_diversity")
    problems.extend(
        pheromone_derived_trace_problems(
            events=events,
            pheromone_score_event=pheromone_score_event,
            reconstructed=reconstructed,
            runtime_policy=runtime_policy,
            candidates=candidates,
            trails=trails,
            current_step=current_step,
        )
    )
    return problems


def pheromone_derived_trace_problems(
    *,
    events: tuple[TraceEvent, ...],
    pheromone_score_event: TraceEvent,
    reconstructed: Any,
    runtime_policy: Any,
    candidates: Any,
    trails: list[PheromoneTrail],
    current_step: int,
) -> list[str]:
    """Reconstruct normalization and exploration records from scored memory."""

    problems: list[str] = []
    score_index = next(
        (index for index, event in enumerate(events) if event is pheromone_score_event),
        -1,
    )
    normalization_events = [
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "pheromone_normalize"
    ]
    expected_normalization = reconstructed.normalization
    if expected_normalization is None:
        if normalization_events:
            problems.append("authority_pheromone_normalize_unexpected")
    elif len(normalization_events) != 1:
        problems.append("authority_pheromone_normalize_count")
    else:
        index, event = normalization_events[0]
        if index <= score_index:
            problems.append("authority_pheromone_normalize_order")
        lineage = event.lineage
        if list(lineage.get("candidates", ())) != list(
            expected_normalization.candidate_ids
        ):
            problems.append("authority_pheromone_normalize_candidates")
        if not nested_numeric_mapping_near(
            lineage.get("pre_scores", {}),
            expected_normalization.pre_scores,
        ):
            problems.append("authority_pheromone_normalize_pre_scores")
        if not nested_numeric_mapping_near(
            lineage.get("post_scores", {}),
            expected_normalization.post_scores,
        ):
            problems.append("authority_pheromone_normalize_post_scores")
        if lineage.get("response_model") != expected_normalization.response_model:
            problems.append("authority_pheromone_normalize_response_model")
        if lineage.get("competition_mode") != expected_normalization.competition_mode:
            problems.append("authority_pheromone_normalize_competition_mode")

    state_observations = [
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "pheromone_observe"
        and "candidate_id" in event.lineage
    ]
    floor_observations = [
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "pheromone_observe"
        and "exploration_floor" in event.lineage
    ]
    expected_observations = observe_pheromone_exploration(
        candidate_set=candidates,
        trails=trails,
        policy=runtime_policy,
        current_step=current_step,
        target=pheromone_score_event.target,
    )
    if len(state_observations) != len(expected_observations):
        problems.append("authority_pheromone_observe_count")
    for position, expected in enumerate(expected_observations):
        if position >= len(state_observations):
            break
        index, event = state_observations[position]
        lineage = event.lineage
        if index <= score_index:
            problems.append("authority_pheromone_observe_order")
        expected_fields = {
            "candidate_id": expected.candidate_id,
            "subject_type": expected.subject_type,
            "subject_id": expected.subject_id,
            "reopen_eligible": expected.reopen_eligible,
            "source_trace_event_id": expected.trace_event_id,
        }
        if any(lineage.get(name) != value for name, value in expected_fields.items()):
            problems.append(f"authority_pheromone_observe_lineage:{position}")
        if not near(lineage.get("novelty_pressure"), expected.novelty_pressure):
            problems.append(f"authority_pheromone_observe_novelty:{position}")
        if event.reason != expected.reason:
            problems.append(f"authority_pheromone_observe_reason:{position}")

    expected_floor_candidates = [
        candidate.id for candidate in candidates.candidates if not candidate.safe_fallback
    ]
    floor_expected = bool(
        runtime_policy.exploration_enabled
        and runtime_policy.exploration_floor > 0
        and expected_floor_candidates
    )
    if len(floor_observations) != (1 if floor_expected else 0):
        problems.append("authority_pheromone_exploration_floor_count")
    elif floor_expected:
        index, event = floor_observations[0]
        if index <= score_index:
            problems.append("authority_pheromone_exploration_floor_order")
        if not near(
            event.lineage.get("exploration_floor"),
            runtime_policy.exploration_floor,
        ):
            problems.append("authority_pheromone_exploration_floor_value")
        if list(event.lineage.get("candidate_ids", ())) != expected_floor_candidates:
            problems.append("authority_pheromone_exploration_floor_candidates")
    return problems


def nested_numeric_mapping_near(observed: Any, expected: Any) -> bool:
    if not isinstance(observed, dict) or not hasattr(expected, "items"):
        return False
    expected_dict = dict(expected)
    if set(observed) != set(expected_dict):
        return False
    for key, expected_value in expected_dict.items():
        observed_value = observed[key]
        if hasattr(expected_value, "items"):
            if not nested_numeric_mapping_near(observed_value, expected_value):
                return False
        elif not near(observed_value, expected_value):
            return False
    return True


def policy_adjustment_trace_problems(
    policy: Any,
    events: tuple[TraceEvent, ...],
) -> list[str]:
    """Revalidate adjustment lineage against manifest authority and allowlists."""

    problems: list[str] = []
    observed_keys: set[str] = set()
    observed_trace_ids: set[str] = set()
    for index, event in enumerate(events):
        if event.event_type != "policy_adjustment":
            continue
        lineage = event.lineage
        proposed = lineage.get("proposed_values", {})
        declared = lineage.get("declared_bounds", {})
        trace_id = lineage.get("source_trace_event_id")
        if not isinstance(trace_id, str) or not trace_id:
            problems.append(f"authority_policy_adjustment_trace:{index}")
            continue
        if trace_id in observed_trace_ids:
            problems.append(f"authority_policy_adjustment_duplicate_trace:{trace_id}")
        observed_trace_ids.add(trace_id)
        if lineage.get("result") not in {"accepted", "replay_ignored"}:
            problems.append(f"authority_policy_adjustment_result:{index}")
        expected_replayed = lineage.get("result") == "replay_ignored"
        if lineage.get("replayed") is not expected_replayed:
            problems.append(f"authority_policy_adjustment_replayed:{index}")
        for key in proposed:
            if lineage.get("result") == "accepted":
                if key in observed_keys:
                    problems.append(f"authority_policy_adjustment_duplicate_key:{key}")
                observed_keys.add(key)
            if key not in policy.policy_adjustment_bounds:
                problems.append(f"authority_policy_adjustment_undeclared:{key}")
            elif declared.get(key) != thaw_protocol_value(policy.policy_adjustment_bounds[key]):
                problems.append(f"authority_policy_adjustment_bound:{key}")
        try:
            overlay = validate_policy_adjustment_proposal(
                PolicyAdjustmentProposal(
                    layer_id=str(lineage.get("layer_id", "")),
                    source_id=str(lineage.get("source_id", "")),
                    adjustments=dict(proposed),
                    provenance=str(lineage.get("provenance", "")),
                    trace_event_id=trace_id,
                ),
                policy,
            )
        except Exception:
            problems.append(f"authority_policy_adjustment_invalid:{index}")
        else:
            if dict(overlay) != dict(proposed):
                problems.append(f"authority_policy_adjustment_overlay:{index}")
    return problems


def coordination_replay_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    proposal_events: list[TraceEvent],
    assessment_event: TraceEvent,
    resolution_event: TraceEvent,
    breakdown: dict[str, Any],
    active_ids: set[str],
) -> list[str]:
    """Re-evaluate complete coordination state from causal trace inputs."""

    problems: list[str] = []
    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return ["authority_coordination_policy_missing"]

    accepted_proposals = [
        PolicyAdjustmentProposal(
            layer_id=str(event.lineage.get("layer_id", "")),
            source_id=str(event.lineage.get("source_id", "")),
            adjustments=dict(event.lineage.get("proposed_values", {})),
            provenance=str(event.lineage.get("provenance", "")),
            trace_event_id=str(event.lineage.get("source_trace_event_id", "")),
        )
        for event in events
        if event.event_type == "policy_adjustment"
        and event.lineage.get("result") == "accepted"
    ]
    proposals: list[LayerProposal] = []
    biases: list[StrategyBias] = []
    try:
        adjustment_batch = validate_policy_adjustment_proposals(
            accepted_proposals,
            policy,
        )
        effective_policy = apply_policy_adjustment_overlay(
            policy,
            adjustment_batch.overlay,
        )
        coordination_policy = layer_coordination_policy_from_collective(effective_policy)
        for event in proposal_events:
            item = event.lineage
            if item.get("action") == "strategy_bias":
                if item.get("effect") != "bounded_candidate_preference":
                    problems.append("authority_strategy_bias_effect")
                biases.append(
                    StrategyBias(
                        layer_id=str(item.get("layer_id", "")),
                        candidate_id=str(item.get("candidate_id", "")),
                        support=float(item.get("support", 0.0)),
                        provenance=str(item.get("provenance", "")),
                        trace_event_id=str(item.get("source_trace_event_id", "")),
                        target=event.target,
                        source_id=str(item.get("source_id", "")),
                        confidence=float(item.get("confidence", 0.0)),
                        evidence_id=str(item.get("evidence_id", "")),
                    )
                )
            else:
                proposal = LayerProposal(
                    layer_id=str(item.get("layer_id", "")),
                    source_id=str(item.get("source_id", "")),
                    target=event.target,
                    candidate_id=str(item.get("candidate_id", "")),
                    action=str(item.get("action", "")),
                    confidence=float(item.get("confidence", 0.0)),
                    support=float(item.get("support", 0.0)),
                    risk=float(item.get("risk", 0.0)),
                    proposed_pheromone_kind=str(item.get("proposed_pheromone_kind", "")),
                    proposed_strength=float(item.get("proposed_strength", 0.0)),
                    evidence_id=str(item.get("evidence_id", "")),
                    provenance=str(item.get("provenance", "")),
                    trace_event_id=str(item.get("source_trace_event_id", "")),
                    metadata={
                        "subject_type": item.get("subject_type", "candidate"),
                        "subject_id": item.get(
                            "subject_id",
                            str(item.get("candidate_id", "")),
                        ),
                    },
                )
                if item.get("effect") != layer_action_effect(
                    proposal,
                    coordination_policy,
                ):
                    problems.append("authority_layer_proposal_effect")
                proposals.append(proposal)
        snapshots: list[LayerPerformanceSnapshot] = []
        for layer_id, item in assessment_event.lineage.get("snapshots", {}).items():
            if not item.get("present", False):
                continue
            snapshots.append(
                LayerPerformanceSnapshot(
                    layer_id=str(layer_id),
                    recent_success_rate=float(item.get("recent_success_rate", 0.0)),
                    recent_conflict_rate=float(item.get("recent_conflict_rate", 0.0)),
                    recent_fallback_rate=float(item.get("recent_fallback_rate", 0.0)),
                    mean_confidence=float(item.get("mean_confidence", 0.0)),
                    evidence_coverage=float(item.get("evidence_coverage", 0.0)),
                    trace_coverage=float(item.get("trace_coverage", 0.0)),
                )
            )
        reconstructed = evaluate_layer_coordination(
            candidate_set=candidate_set(manifest),
            target=manifest.protocol.quorum_policy.target,
            policy=coordination_policy,
            proposals=proposals,
            fallback_candidate_id=collective_fallback_id(manifest.protocol),
            snapshots=snapshots,
            strategy_biases=biases,
        )
    except Exception as exc:
        return [f"authority_coordination_reconstruction:{type(exc).__name__}"]

    assessment = assessment_event.lineage
    resolution = resolution_event.lineage
    if not nested_numeric_mapping_near(
        assessment.get("confidences", {}),
        reconstructed.confidences,
    ):
        problems.append("authority_coordination_confidences")
    if not nested_numeric_mapping_near(
        assessment.get("weights", {}),
        reconstructed.allocated_weights,
    ):
        problems.append("authority_coordination_weights")
    if dict(assessment.get("action_effects", {})) != dict(reconstructed.action_effects):
        problems.append("authority_coordination_action_effects")
    if not nested_numeric_mapping_near(
        assessment.get("trace_coverage_confirmations", {}),
        reconstructed.trace_coverage_confirmations,
    ):
        problems.append("authority_coordination_trace_confirmations")
    snapshots_lineage = assessment.get("snapshots", {})
    expected_coverage = {
        layer_id: {
            "mean_confidence": item.get("mean_confidence", 0.0),
            "evidence_coverage": item.get("evidence_coverage", 0.0),
            "trace_coverage": item.get("trace_coverage", 0.0),
        }
        for layer_id, item in snapshots_lineage.items()
    }
    expected_coverage["governance_trace_confirmations"] = dict(
        reconstructed.trace_coverage_confirmations
    )
    if assessment.get("coverage", {}) != expected_coverage:
        problems.append("authority_coordination_coverage")
    if list(assessment.get("proposal_lineage", ())) != list(reconstructed.trace_lineage):
        problems.append("authority_coordination_trace_lineage")

    expected_resolution = {
        "conflicts": list(reconstructed.conflicts),
        "resolution": reconstructed.resolution,
        "selected_candidate": reconstructed.selected_candidate,
        "fallback_used": reconstructed.fallback_used,
        "reason": reconstructed.resolution,
        "proposal_lineage": list(reconstructed.trace_lineage),
    }
    for field_name, expected_value in expected_resolution.items():
        if resolution.get(field_name) != expected_value:
            problems.append(f"authority_coordination_resolution_{field_name}")

    layer_categories = tuple(
        f"layer_{layer_id}"
        for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
    )
    for candidate_id in active_ids:
        expected_categories = reconstructed.score_breakdown.get(candidate_id, {})
        for category in layer_categories:
            expected_value = (
                0.0
                if reconstructed.fallback_used
                else float(expected_categories.get(category, 0.0))
            )
            if not near(
                breakdown.get(candidate_id, {}).get(category, 0.0),
                expected_value,
            ):
                problems.append(f"authority_{category}_score:{candidate_id}")
    return problems


def layer_pheromone_lineage_problems(
    events: tuple[TraceEvent, ...],
    proposal_events: list[TraceEvent],
) -> list[str]:
    """Verify proposal-owned deposits point backward to their declared source.

    A ``propose_pheromone`` action has no direct authority.  Its only valid
    state-changing effect is a later deposit (possibly preceded by a budget
    clip) carrying the proposal trace id and matching its declared subject.
    """

    problems: list[str] = []
    proposals: dict[str, tuple[int, TraceEvent]] = {}
    for index, event in enumerate(events):
        if event.event_type != "layer_proposal":
            continue
        trace_id = event.lineage.get("source_trace_event_id")
        if isinstance(trace_id, str) and trace_id:
            proposals[trace_id] = (index, event)

    deposits: dict[str, list[tuple[int, TraceEvent]]] = {}
    clips: dict[str, list[tuple[int, TraceEvent]]] = {}
    for index, event in enumerate(events):
        if event.event_type == "pheromone_deposit":
            trace_id = event.lineage.get("source_trace_event_id")
            if trace_id in proposals:
                deposits.setdefault(trace_id, []).append((index, event))
        elif (
            event.event_type == "pheromone_clip"
            and event.lineage.get("lifecycle") != "diffusion"
        ):
            trace_id = event.lineage.get("trace_event_id")
            if trace_id in proposals:
                clips.setdefault(trace_id, []).append((index, event))

    for proposal_event in proposal_events:
        item = proposal_event.lineage
        if item.get("action") != "propose_pheromone":
            continue
        trace_id = item.get("source_trace_event_id")
        proposal_index = proposals.get(trace_id, (-1, proposal_event))[0]
        matching_deposits = deposits.get(trace_id, [])
        matching_clips = clips.get(trace_id, [])
        if not matching_deposits and not matching_clips:
            problems.append(f"authority_layer_pheromone_effect_missing:{trace_id}")
            continue
        if len(matching_deposits) > 1 or len(matching_clips) > 1:
            problems.append(f"authority_layer_pheromone_effect_count:{trace_id}")
        if any(index <= proposal_index for index, _ in [*matching_clips, *matching_deposits]):
            problems.append(f"authority_layer_pheromone_forward_reference:{trace_id}")
        requested = float(item.get("proposed_strength", 0.0)) * float(
            item.get("confidence", 0.0)
        )
        applied = requested
        if matching_clips:
            clip = matching_clips[0][1].lineage
            if not near(clip.get("requested_strength"), requested):
                problems.append(f"authority_layer_pheromone_requested_strength:{trace_id}")
            applied = float(clip.get("applied_strength", 0.0))
        if matching_deposits:
            deposit = matching_deposits[0][1].lineage
            expected = {
                "source_id": item.get("source_id"),
                "candidate_id": item.get("candidate_id"),
                "kind": item.get("proposed_pheromone_kind"),
                "subject_type": item.get("subject_type"),
                "subject_id": item.get("subject_id"),
            }
            if any(deposit.get(field) != value for field, value in expected.items()):
                problems.append(f"authority_layer_pheromone_subject_lineage:{trace_id}")
            if not near(
                float(deposit.get("new_strength", 0.0))
                - float(deposit.get("old_strength", 0.0)),
                applied,
            ):
                problems.append(f"authority_layer_pheromone_applied_strength:{trace_id}")
        elif not near(applied, 0.0):
            problems.append(f"authority_layer_pheromone_deposit_missing:{trace_id}")
    return problems


def event_stage_order_problems(events: tuple[TraceEvent, ...]) -> list[str]:
    problems: list[str] = []
    previous = -1
    for index, event in enumerate(events):
        stage = event_stage(event)
        if stage is None:
            continue
        if stage < previous:
            problems.append(f"authority_event_order:{index}:{event.event_type}")
        previous = max(previous, stage)
    return problems


def event_stage(event: TraceEvent) -> int | None:
    if event.event_type in {"explore", "scout_report", "recruit", "inhibit"}:
        return 0
    if event.event_type == "policy_adjustment":
        return 1
    # Accepted layer proposals are declared before pheromone materialization:
    # a proposal may itself be the source of a bounded deposit. Coordination
    # still occurs only after pheromone scoring/observation below.
    if event.event_type == "layer_proposal":
        return 2
    if event.event_type == "pheromone_clip":
        if event.lineage.get("lifecycle") == "diffusion":
            return 5
        if event.lineage.get("lifecycle") == "feedback":
            return 6
        return 3
    if event.event_type == "pheromone_deposit":
        return 3
    if event.event_type in {"pheromone_evaporate", "pheromone_expire"}:
        if event.lineage.get("phase") == "post_reinforcement":
            return 6
        return 4
    if event.event_type == "pheromone_diffuse":
        return 5
    if event.event_type == "pheromone_reinforce":
        return 6
    if event.event_type in {"pheromone_score", "pheromone_normalize", "pheromone_observe"}:
        return 7
    if event.event_type in {"coordination_assess", "coordination_resolve"}:
        return 8
    if event.event_type == "candidate_score":
        return 9
    if event.event_type == "consensus_check":
        return 10
    if event.event_type in {"commit", "fallback"}:
        return 11
    if event.event_type == "output":
        return 12
    return None


def near(left: Any, right: Any) -> bool:
    try:
        return isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9)
    except (TypeError, ValueError):
        return False


def replay_evaporation_kind(policy: Any) -> str | None:
    """Choose a declared/effective kind that changes before TTL at step one."""

    kinds = {
        "positive",
        "negative",
        "cautionary",
        "alarm",
        "novelty",
        *policy.pheromone_kind_profiles,
    }
    for kind in sorted(kinds):
        profile = policy.pheromone_kind_profiles.get(kind)
        rate = (
            profile.evaporation_rate
            if profile is not None and profile.evaporation_rate is not None
            else policy.pheromone_evaporation_rate
        )
        ttl_steps = profile.ttl_steps if profile is not None else None
        if rate > 0 and (ttl_steps is None or ttl_steps > 1):
            return kind
    return None


def manifest_replay(
    manifest: CapabilityManifest,
    *,
    force_fallback: bool = False,
    lifecycle_focus: str | None = None,
    include_layer_inputs: bool = True,
    memory_only_feedback: bool = False,
    replay_state: HybridReplayState | None = None,
) -> tuple[Any, TraceEvent]:
    """Execute a deterministic replay derived entirely from manifest policy."""

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        raise ValueError("hybrid replay requires collective policy")
    target = active_target(manifest)
    candidates = candidate_set(manifest)
    primary = exercise_candidate_id(manifest)
    if primary is None:
        raise ValueError("hybrid replay has no active target candidate")
    active_ids = target_candidate_ids(manifest)
    secondary = next((candidate_id for candidate_id in active_ids if candidate_id != primary), primary)

    scouts = [] if force_fallback else [
        verified_scout(
            source_id=f"scout:conformance:{index}",
            candidate_id=primary,
            target=target,
            support=max(1.0, float(policy.quorum_threshold)),
        )
        for index in range(policy.min_independent_scouts)
    ]
    recruitment = (
        [verified_recruitment("recruit:conformance", primary, target)]
        if policy.recruitment_enabled and not force_fallback
        else []
    )
    inhibition = (
        [verified_inhibition("inhibit:conformance", secondary, target)]
        if policy.inhibition_enabled and not force_fallback
        else []
    )

    unit = max(
        float(policy.pheromone_min_strength),
        min(
            float(policy.pheromone_max_strength) / 4,
            float(policy.pheromone_per_source_cap) / 4,
            float(policy.pheromone_per_round_deposit_cap) / 12,
        ),
    )
    if unit <= 0:
        raise ValueError("hybrid replay requires positive declared pheromone budgets")
    route_ids = {candidate_id: f"route:conformance:{index}" for index, candidate_id in enumerate(active_ids)}
    deposit_items = [
        route_trail(
            primary,
            route_ids[primary],
            target,
            "positive",
            max(
                unit,
                float(policy.pheromone_max_strength),
                float(policy.pheromone_per_source_cap),
                float(policy.pheromone_per_round_deposit_cap),
            )
            + 1,
            "source:deposit:primary",
            "trace:deposit:primary",
            step=1,
        )
    ]
    if secondary != primary:
        deposit_items.append(
            route_trail(
                secondary,
                route_ids[secondary],
                target,
                "cautionary",
                unit,
                "source:deposit:secondary",
                "trace:deposit:secondary",
                step=1,
            )
        )
    evaporation_kind = replay_evaporation_kind(policy) or "positive"
    existing = [
        route_trail(
            primary,
            "route:conformance:evaporating",
            target,
            evaporation_kind,
            float(policy.pheromone_max_strength),
            "source:existing:evaporating",
            "trace:existing:evaporating",
            step=0,
        ),
        route_trail(
            primary,
            "route:conformance:expiring",
            target,
            "alarm",
            float(policy.pheromone_max_strength),
            "source:existing:expiring",
            "trace:existing:expiring",
            step=0,
            ttl_steps=1,
        ),
    ]
    topology = replay_topology(target, active_ids, route_ids, existing)
    feedback_subject_type = "route"
    feedback_subject_id = route_ids[primary]
    if memory_only_feedback:
        feedback_subject_type = "evidence"
        feedback_subject_id = "evidence:memory:primary"
        topology = PheromoneNeighborhood(
            subjects=[
                *topology.subjects,
                PheromoneSubject(
                    feedback_subject_type,
                    feedback_subject_id,
                    primary,
                    target,
                ),
            ],
            edges=list(topology.edges),
        )
    feedback = [
        PheromoneFeedback(
            source_id="source:feedback:primary",
            subject_type=feedback_subject_type,
            subject_id=feedback_subject_id,
            candidate_id=primary,
            target=target,
            outcome="success",
            reward=1.0,
            strength_delta=unit,
            evidence_id="evidence:feedback:primary",
            provenance="conformance:feedback",
            trace_event_id="trace:feedback:primary",
            step=1,
        )
    ]
    if lifecycle_focus == "diffusion":
        # Use a separate real step to prove diffusion and feedback when a
        # legal tight round budget cannot also fund the deposit transition.
        # The source trail is current at this step, so declared minimum
        # strength remains reachable before bounded attenuation.
        deposit_items = []
        existing = [
            route_trail(
                primary,
                route_ids[primary],
                target,
                "positive",
                float(policy.pheromone_max_strength),
                "source:lifecycle:existing",
                "trace:lifecycle:existing",
                step=1,
                ttl_steps=2,
            )
        ]
        topology = replay_topology(target, active_ids, route_ids, existing)
        feedback = []
    elif lifecycle_focus == "reinforcement":
        deposit_items = []
        existing = []
        topology = PheromoneNeighborhood(
            subjects=[
                PheromoneSubject("route", route_ids[primary], primary, target),
            ],
            edges=[],
        )
        feedback = [
            PheromoneFeedback(
                source_id="source:lifecycle:feedback",
                subject_type="route",
                subject_id=route_ids[primary],
                candidate_id=primary,
                target=target,
                outcome="success",
                reward=1.0,
                strength_delta=unit,
                evidence_id="evidence:lifecycle:feedback",
                provenance="conformance:lifecycle:feedback",
                trace_event_id="trace:lifecycle:feedback",
                step=1,
            )
        ]
    layer_proposals = [
        LayerProposal(
            layer_id=layer_id,
            source_id=f"layer:conformance:{layer_id}",
            target=target,
            candidate_id=primary,
            action="support",
            confidence=max(0.9, float(policy.layer_confidence_thresholds.get(layer_id, 0.0))),
            support=1.0,
            evidence_id=f"evidence:layer:{layer_id}",
            provenance=f"conformance:layer:{layer_id}",
            trace_event_id=f"trace:layer:{layer_id}",
        )
        for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
    ]
    snapshots = [
        LayerPerformanceSnapshot(
            layer_id,
            recent_success_rate=0.8,
            recent_conflict_rate=0.1,
            recent_fallback_rate=0.1,
            mean_confidence=0.8,
            evidence_coverage=1.0,
            trace_coverage=1.0,
        )
        for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
    ]
    biases = [
        StrategyBias(
            layer_id="evolutionary",
            candidate_id=primary,
            support=0.25,
            provenance="conformance:strategy-bias",
            trace_event_id="trace:strategy-bias",
            target=target,
            source_id="layer:conformance:evolutionary",
            confidence=0.8,
            evidence_id="evidence:strategy-bias",
        )
    ]
    adjustment_key = sorted(policy.policy_adjustment_bounds)[0]
    adjustment = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="layer:conformance:evolutionary",
        adjustments={adjustment_key: accepted_adjustment_value(policy.policy_adjustment_bounds[adjustment_key])},
        provenance="conformance:adjustment",
        trace_event_id="trace:adjustment",
    )

    step = evaluate_hybrid_collective_step(
        protocol_id=manifest.protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=scouts,
        recruitment_signals=recruitment,
        inhibition_signals=inhibition,
        existing_trails=(None if replay_state is not None else existing),
        deposits=deposit_items,
        topology=topology,
        feedback=feedback,
        layer_proposals=layer_proposals if include_layer_inputs else [],
        performance_snapshots=snapshots if include_layer_inputs else [],
        strategy_biases=biases if include_layer_inputs else [],
        adjustment_proposals=[adjustment],
        replay_state=replay_state,
        fallback_candidate_id=collective_fallback_id(manifest.protocol),
    )
    evidence = EvidenceGraph(
        [EvidenceNode(report.evidence_id, report.candidate_id, report.provenance) for report in scouts]
    )
    output_policy = manifest.protocol.output_policy
    output = evaluate_output_authorization(
        OutputContract(
            committed_candidate_required=output_policy.requires_committed_candidate,
            evidence_required=output_policy.requires_evidence_contract,
            stop_resolution_required=output_policy.requires_stop_resolution,
            publication_permission_required=output_policy.requires_publication_permission,
        ),
        step.decision,
        evidence,
        [StopResolution(target=target, action="publish", blocked=False, reason="conformance")],
        publication_permission=True,
        protocol_id=manifest.protocol.id,
        candidate_set=candidates,
    )
    return step, output.trace_event


def verified_scout(*, source_id: str, candidate_id: str, target: str, support: float) -> ScoutReport:
    trace_event_id = f"trace:{source_id}"
    return ScoutReport(
        source_id,
        candidate_id,
        f"evidence:{source_id}",
        f"conformance:{source_id}",
        support=support,
        target=target,
        trace_event_id=trace_event_id,
        verification=verification(source_id, candidate_id, target, trace_event_id),
    )


def verified_recruitment(source_id: str, candidate_id: str, target: str) -> RecruitmentSignal:
    trace_event_id = f"trace:{source_id}"
    return RecruitmentSignal(
        source_id,
        candidate_id,
        strength=0.5,
        target=target,
        provenance=f"conformance:{source_id}",
        trace_event_id=trace_event_id,
        verification=verification(source_id, candidate_id, target, trace_event_id),
    )


def verified_inhibition(source_id: str, candidate_id: str, target: str) -> InhibitionSignal:
    trace_event_id = f"trace:{source_id}"
    return InhibitionSignal(
        source_id,
        candidate_id,
        strength=0.25,
        target=target,
        provenance=f"conformance:{source_id}",
        trace_event_id=trace_event_id,
        verification=verification(source_id, candidate_id, target, trace_event_id),
    )


def verification(source_id: str, candidate_id: str, target: str, trace_event_id: str) -> Any:
    return verify_signal_input(
        target=target,
        source_id=source_id,
        subject_id=candidate_id,
        verifier_id="governance:conformance",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="conformance:governance",
        trace_event_id=f"{trace_event_id}:verified",
    )


def route_trail(
    candidate_id: str,
    route_id: str,
    target: str,
    kind: str,
    strength: float,
    source_id: str,
    trace_event_id: str,
    *,
    step: int,
    ttl_steps: int | None = None,
) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type="route",
        subject_id=route_id,
        target=target,
        kind=kind,
        source_id=source_id,
        evidence_id=f"evidence:{route_id}",
        provenance=f"conformance:{route_id}",
        trace_event_id=trace_event_id,
        deposited_at_step=step,
        updated_at_step=step,
        ttl_steps=ttl_steps,
    )


def replay_topology(
    target: str,
    candidate_ids: list[str],
    route_ids: dict[str, str],
    existing: list[PheromoneTrail],
) -> PheromoneNeighborhood:
    subjects: list[PheromoneSubject] = []
    edges: list[PheromoneEdge] = []
    seen_routes: set[str] = set()
    for candidate_id in candidate_ids:
        subjects.append(PheromoneSubject("candidate", candidate_id, candidate_id, target))
        route_id = route_ids[candidate_id]
        seen_routes.add(route_id)
        subjects.append(PheromoneSubject("route", route_id, candidate_id, target))
        edges.append(PheromoneEdge("route", route_id, "candidate", candidate_id, 1.0))
    for trail in existing:
        if trail.subject_id in seen_routes:
            continue
        seen_routes.add(trail.subject_id)
        subjects.append(PheromoneSubject("route", trail.subject_id, trail.candidate_id, target))
        edges.append(PheromoneEdge("route", trail.subject_id, "candidate", trail.candidate_id, 1.0))
    return PheromoneNeighborhood(subjects=subjects, edges=edges)


def accepted_adjustment_value(bounds: Any) -> Any:
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        return bounds[0]
    if isinstance(bounds, Mapping) and bounds.get("allowed_values"):
        return bounds["allowed_values"][0]
    if isinstance(bounds, Mapping) and "min" in bounds:
        return bounds["min"]
    raise ValueError("hybrid replay adjustment bound is malformed")


__all__ = ["check", "check_actual_trace", "manifest_replay"]
