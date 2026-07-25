from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from pheroos.conformance.checks._manifest import candidate_set
from pheroos.governance import (
    LayerPerformanceSnapshot,
    LayerProposal,
    PolicyAdjustmentProposal,
    StrategyBias,
    apply_policy_adjustment_overlay,
    evaluate_layer_coordination,
    layer_action_effect,
    layer_coordination_policy_from_collective,
    validate_policy_adjustment_proposal,
    validate_policy_adjustment_proposals,
)
from pheroos.protocol.models import (
    CapabilityManifest,
    collective_fallback_id,
    thaw_protocol_value,
)
from pheroos.trace import TraceEvent

from ._hybrid_trace_score import nested_numeric_mapping_near
from ._hybrid_trace_shared import near


@dataclass
class _AdjustmentSeen:
    keys: set[str] = field(default_factory=set)
    trace_ids: set[str] = field(default_factory=set)


def policy_adjustment_trace_problems(
    policy: Any,
    events: tuple[TraceEvent, ...],
) -> list[str]:
    """Revalidate adjustment lineage against manifest authority and allowlists."""

    problems: list[str] = []
    seen = _AdjustmentSeen()
    for index, event in enumerate(events):
        if event.event_type == "policy_adjustment":
            problems.extend(_adjustment_event_problems(policy, index, event, seen))
    return problems


def _adjustment_event_problems(
    policy: Any,
    index: int,
    event: TraceEvent,
    seen: _AdjustmentSeen,
) -> list[str]:
    lineage = event.lineage
    trace_id = lineage.get("source_trace_event_id")
    if not isinstance(trace_id, str) or not trace_id:
        return [f"authority_policy_adjustment_trace:{index}"]
    problems = _adjustment_header_problems(index, lineage, trace_id, seen)
    proposed = lineage.get("proposed_values", {})
    problems.extend(_adjustment_key_problems(policy, lineage, proposed, seen))
    problems.extend(
        _adjustment_overlay_problems(policy, index, lineage, proposed, trace_id)
    )
    return problems


def _adjustment_header_problems(
    index: int,
    lineage: Any,
    trace_id: str,
    seen: _AdjustmentSeen,
) -> list[str]:
    problems: list[str] = []
    if trace_id in seen.trace_ids:
        problems.append(f"authority_policy_adjustment_duplicate_trace:{trace_id}")
    seen.trace_ids.add(trace_id)
    if lineage.get("result") not in {"accepted", "replay_ignored"}:
        problems.append(f"authority_policy_adjustment_result:{index}")
    expected_replayed = lineage.get("result") == "replay_ignored"
    if lineage.get("replayed") is not expected_replayed:
        problems.append(f"authority_policy_adjustment_replayed:{index}")
    return problems


def _adjustment_key_problems(
    policy: Any,
    lineage: Any,
    proposed: Any,
    seen: _AdjustmentSeen,
) -> list[str]:
    problems: list[str] = []
    declared = lineage.get("declared_bounds", {})
    for key in proposed:
        if lineage.get("result") == "accepted":
            if key in seen.keys:
                problems.append(f"authority_policy_adjustment_duplicate_key:{key}")
            seen.keys.add(key)
        if key not in policy.policy_adjustment_bounds:
            problems.append(f"authority_policy_adjustment_undeclared:{key}")
        elif declared.get(key) != thaw_protocol_value(
            policy.policy_adjustment_bounds[key]
        ):
            problems.append(f"authority_policy_adjustment_bound:{key}")
    return problems


def _adjustment_overlay_problems(
    policy: Any,
    index: int,
    lineage: Any,
    proposed: Any,
    trace_id: str,
) -> list[str]:
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
        return [f"authority_policy_adjustment_invalid:{index}"]
    return (
        [f"authority_policy_adjustment_overlay:{index}"]
        if dict(overlay) != dict(proposed)
        else []
    )


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

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return ["authority_coordination_policy_missing"]
    try:
        reconstructed, problems = _reconstruct_coordination(
            manifest,
            policy,
            events,
            proposal_events,
            assessment_event,
        )
    except Exception as exc:
        return [f"authority_coordination_reconstruction:{type(exc).__name__}"]
    problems.extend(_assessment_problems(assessment_event.lineage, reconstructed))
    problems.extend(_resolution_problems(resolution_event.lineage, reconstructed))
    problems.extend(_layer_score_problems(breakdown, active_ids, reconstructed))
    return problems


def _reconstruct_coordination(
    manifest: CapabilityManifest,
    policy: Any,
    events: tuple[TraceEvent, ...],
    proposal_events: list[TraceEvent],
    assessment_event: TraceEvent,
) -> tuple[Any, list[str]]:
    accepted = _accepted_adjustment_proposals(events)
    batch = validate_policy_adjustment_proposals(accepted, policy)
    effective_policy = apply_policy_adjustment_overlay(policy, batch.overlay)
    coordination_policy = layer_coordination_policy_from_collective(effective_policy)
    proposals, biases, problems = _coordination_inputs(
        proposal_events,
        coordination_policy,
    )
    reconstructed = evaluate_layer_coordination(
        candidate_set=candidate_set(manifest),
        target=manifest.protocol.quorum_policy.target,
        policy=coordination_policy,
        proposals=proposals,
        fallback_candidate_id=collective_fallback_id(manifest.protocol),
        snapshots=_performance_snapshots(assessment_event),
        strategy_biases=biases,
    )
    return reconstructed, problems


def _accepted_adjustment_proposals(
    events: tuple[TraceEvent, ...],
) -> list[PolicyAdjustmentProposal]:
    return [
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


def _coordination_inputs(
    events: list[TraceEvent],
    coordination_policy: Any,
) -> tuple[list[LayerProposal], list[StrategyBias], list[str]]:
    proposals: list[LayerProposal] = []
    biases: list[StrategyBias] = []
    problems: list[str] = []
    for event in events:
        if event.lineage.get("action") == "strategy_bias":
            bias, issue = _strategy_bias(event)
            biases.append(bias)
        else:
            proposal, issue = _layer_proposal(event, coordination_policy)
            proposals.append(proposal)
        if issue is not None:
            problems.append(issue)
    return proposals, biases, problems


def _strategy_bias(event: TraceEvent) -> tuple[StrategyBias, str | None]:
    item = event.lineage
    issue = (
        None
        if item.get("effect") == "bounded_candidate_preference"
        else "authority_strategy_bias_effect"
    )
    return (
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
        ),
        issue,
    )


def _layer_proposal(
    event: TraceEvent, coordination_policy: Any
) -> tuple[LayerProposal, str | None]:
    item = event.lineage
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
            "subject_id": item.get("subject_id", str(item.get("candidate_id", ""))),
        },
    )
    issue = (
        None
        if item.get("effect") == layer_action_effect(proposal, coordination_policy)
        else "authority_layer_proposal_effect"
    )
    return proposal, issue


def _performance_snapshots(event: TraceEvent) -> list[LayerPerformanceSnapshot]:
    return [
        LayerPerformanceSnapshot(
            layer_id=str(layer_id),
            recent_success_rate=float(item.get("recent_success_rate", 0.0)),
            recent_conflict_rate=float(item.get("recent_conflict_rate", 0.0)),
            recent_fallback_rate=float(item.get("recent_fallback_rate", 0.0)),
            mean_confidence=float(item.get("mean_confidence", 0.0)),
            evidence_coverage=float(item.get("evidence_coverage", 0.0)),
            trace_coverage=float(item.get("trace_coverage", 0.0)),
        )
        for layer_id, item in event.lineage.get("snapshots", {}).items()
        if item.get("present", False)
    ]


def _assessment_problems(assessment: Any, reconstructed: Any) -> list[str]:
    snapshots = assessment.get("snapshots", {})
    expected_coverage = {
        layer_id: {
            "mean_confidence": item.get("mean_confidence", 0.0),
            "evidence_coverage": item.get("evidence_coverage", 0.0),
            "trace_coverage": item.get("trace_coverage", 0.0),
        }
        for layer_id, item in snapshots.items()
    }
    expected_coverage["governance_trace_confirmations"] = dict(
        reconstructed.trace_coverage_confirmations
    )
    checks = (
        (
            not nested_numeric_mapping_near(
                assessment.get("confidences", {}), reconstructed.confidences
            ),
            "authority_coordination_confidences",
        ),
        (
            not nested_numeric_mapping_near(
                assessment.get("weights", {}), reconstructed.allocated_weights
            ),
            "authority_coordination_weights",
        ),
        (
            dict(assessment.get("action_effects", {}))
            != dict(reconstructed.action_effects),
            "authority_coordination_action_effects",
        ),
        (
            not nested_numeric_mapping_near(
                assessment.get("trace_coverage_confirmations", {}),
                reconstructed.trace_coverage_confirmations,
            ),
            "authority_coordination_trace_confirmations",
        ),
        (
            assessment.get("coverage", {}) != expected_coverage,
            "authority_coordination_coverage",
        ),
        (
            list(assessment.get("proposal_lineage", ()))
            != list(reconstructed.trace_lineage),
            "authority_coordination_trace_lineage",
        ),
    )
    return [message for failed, message in checks if failed]


def _resolution_problems(resolution: Any, reconstructed: Any) -> list[str]:
    expected = {
        "conflicts": list(reconstructed.conflicts),
        "resolution": reconstructed.resolution,
        "selected_candidate": reconstructed.selected_candidate,
        "fallback_used": reconstructed.fallback_used,
        "reason": reconstructed.resolution,
        "proposal_lineage": list(reconstructed.trace_lineage),
    }
    return [
        f"authority_coordination_resolution_{field_name}"
        for field_name, expected_value in expected.items()
        if resolution.get(field_name) != expected_value
    ]


def _layer_score_problems(
    breakdown: dict[str, Any],
    active_ids: set[str],
    reconstructed: Any,
) -> list[str]:
    problems: list[str] = []
    categories = tuple(
        f"layer_{layer_id}"
        for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
    )
    for candidate_id in active_ids:
        expected = reconstructed.score_breakdown.get(candidate_id, {})
        for category in categories:
            value = (
                0.0
                if reconstructed.fallback_used
                else float(expected.get(category, 0.0))
            )
            if not near(breakdown.get(candidate_id, {}).get(category, 0.0), value):
                problems.append(f"authority_{category}_score:{candidate_id}")
    return problems


def layer_pheromone_lineage_problems(
    events: tuple[TraceEvent, ...],
    proposal_events: list[TraceEvent],
) -> list[str]:
    """Verify proposal-owned deposits point backward to their declared source."""

    proposals = _proposal_index(events)
    deposits, clips = _proposal_effect_indexes(events, proposals)
    problems: list[str] = []
    for event in proposal_events:
        if event.lineage.get("action") == "propose_pheromone":
            problems.extend(
                _proposal_effect_problems(event, proposals, deposits, clips)
            )
    return problems


def _proposal_index(
    events: tuple[TraceEvent, ...],
) -> dict[str, tuple[int, TraceEvent]]:
    proposals: dict[str, tuple[int, TraceEvent]] = {}
    for index, event in enumerate(events):
        trace_id = event.lineage.get("source_trace_event_id")
        if (
            event.event_type == "layer_proposal"
            and isinstance(trace_id, str)
            and trace_id
        ):
            proposals[trace_id] = (index, event)
    return proposals


def _proposal_effect_indexes(
    events: tuple[TraceEvent, ...],
    proposals: dict[str, tuple[int, TraceEvent]],
) -> tuple[
    dict[str, list[tuple[int, TraceEvent]]],
    dict[str, list[tuple[int, TraceEvent]]],
]:
    deposits: dict[str, list[tuple[int, TraceEvent]]] = {}
    clips: dict[str, list[tuple[int, TraceEvent]]] = {}
    for index, event in enumerate(events):
        _index_proposal_effect(index, event, proposals, deposits, clips)
    return deposits, clips


def _index_proposal_effect(
    index: int,
    event: TraceEvent,
    proposals: dict[str, tuple[int, TraceEvent]],
    deposits: dict[str, list[tuple[int, TraceEvent]]],
    clips: dict[str, list[tuple[int, TraceEvent]]],
) -> None:
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


def _proposal_effect_problems(
    event: TraceEvent,
    proposals: dict[str, tuple[int, TraceEvent]],
    deposits: dict[str, list[tuple[int, TraceEvent]]],
    clips: dict[str, list[tuple[int, TraceEvent]]],
) -> list[str]:
    item = event.lineage
    trace_id = cast(str, item.get("source_trace_event_id"))
    proposal_index = proposals.get(trace_id, (-1, event))[0]
    matching_deposits = deposits.get(trace_id, [])
    matching_clips = clips.get(trace_id, [])
    if not matching_deposits and not matching_clips:
        return [f"authority_layer_pheromone_effect_missing:{trace_id}"]
    problems = _proposal_effect_shape_problems(
        trace_id,
        proposal_index,
        matching_deposits,
        matching_clips,
    )
    requested = float(item.get("proposed_strength", 0.0)) * float(
        item.get("confidence", 0.0)
    )
    applied, clip_problems = _proposal_clip_problems(
        trace_id, matching_clips, requested
    )
    problems.extend(clip_problems)
    problems.extend(
        _proposal_deposit_problems(trace_id, item, matching_deposits, applied)
    )
    return problems


def _proposal_effect_shape_problems(
    trace_id: Any,
    proposal_index: int,
    deposits: list[tuple[int, TraceEvent]],
    clips: list[tuple[int, TraceEvent]],
) -> list[str]:
    problems: list[str] = []
    if len(deposits) > 1 or len(clips) > 1:
        problems.append(f"authority_layer_pheromone_effect_count:{trace_id}")
    if any(index <= proposal_index for index, _ in [*clips, *deposits]):
        problems.append(f"authority_layer_pheromone_forward_reference:{trace_id}")
    return problems


def _proposal_clip_problems(
    trace_id: Any,
    clips: list[tuple[int, TraceEvent]],
    requested: float,
) -> tuple[float, list[str]]:
    if not clips:
        return requested, []
    lineage = clips[0][1].lineage
    problems = (
        [f"authority_layer_pheromone_requested_strength:{trace_id}"]
        if not near(lineage.get("requested_strength"), requested)
        else []
    )
    return float(lineage.get("applied_strength", 0.0)), problems


def _proposal_deposit_problems(
    trace_id: Any,
    proposal: Any,
    deposits: list[tuple[int, TraceEvent]],
    applied: float,
) -> list[str]:
    if not deposits:
        return (
            [f"authority_layer_pheromone_deposit_missing:{trace_id}"]
            if not near(applied, 0.0)
            else []
        )
    deposit = deposits[0][1].lineage
    expected = {
        "source_id": proposal.get("source_id"),
        "candidate_id": proposal.get("candidate_id"),
        "kind": proposal.get("proposed_pheromone_kind"),
        "subject_type": proposal.get("subject_type"),
        "subject_id": proposal.get("subject_id"),
    }
    problems: list[str] = []
    if any(deposit.get(field) != value for field, value in expected.items()):
        problems.append(f"authority_layer_pheromone_subject_lineage:{trace_id}")
    delta = float(deposit.get("new_strength", 0.0)) - float(
        deposit.get("old_strength", 0.0)
    )
    if not near(delta, applied):
        problems.append(f"authority_layer_pheromone_applied_strength:{trace_id}")
    return problems
