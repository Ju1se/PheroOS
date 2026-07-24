from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pheroos.conformance.checks._manifest import candidate_set
from pheroos.governance import (
    PheromoneTrail,
    PolicyAdjustmentProposal,
    apply_policy_adjustment_overlay,
    collect_pheromone_source_diversity,
    observe_pheromone_exploration,
    pheromone_policy_from_collective,
    score_pheromone_trails_result,
    validate_policy_adjustment_proposals,
)
from pheroos.protocol.models import (
    CapabilityManifest,
)
from pheroos.trace import TraceEvent

from ._hybrid_trace_shared import near


@dataclass(frozen=True)
class _ScoreReplay:
    runtime_policy: Any
    trails: list[PheromoneTrail]
    candidates: Any
    current_step: int
    reconstructed: Any
    diversity: dict[str, int]


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
    accepted = _accepted_adjustments(events)
    try:
        replay = _reconstruct_score(
            manifest,
            policy,
            accepted,
            pheromone_score_event,
        )
    except Exception as exc:
        return [f"authority_pheromone_reconstruction:{type(exc).__name__}"]
    problems = _trail_state_problems(replay)
    problems.extend(_score_dimension_problems(pheromone_score_event, replay))
    if (
        dict(candidate_score_event.lineage.get("pheromone_source_diversity", {}))
        != replay.diversity
    ):
        problems.append("authority_pheromone_source_diversity")
    problems.extend(
        pheromone_derived_trace_problems(
            events=events,
            pheromone_score_event=pheromone_score_event,
            reconstructed=replay.reconstructed,
            runtime_policy=replay.runtime_policy,
            candidates=replay.candidates,
            trails=replay.trails,
            current_step=replay.current_step,
        )
    )
    return problems


def _accepted_adjustments(
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


def _reconstruct_score(
    manifest: CapabilityManifest,
    policy: Any,
    accepted: list[PolicyAdjustmentProposal],
    pheromone_score_event: TraceEvent,
) -> _ScoreReplay:
    batch = validate_policy_adjustment_proposals(accepted, policy)
    effective_policy = apply_policy_adjustment_overlay(policy, batch.overlay)
    runtime_policy = pheromone_policy_from_collective(effective_policy)
    trails = [
        _trail_from_lineage(item, pheromone_score_event.target)
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
    return _ScoreReplay(
        runtime_policy,
        trails,
        candidates,
        current_step,
        reconstructed,
        diversity,
    )


def _trail_from_lineage(item: Any, target: str) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=str(item["candidate_id"]),
        strength=float(item["strength"]),
        subject_type=str(item["subject_type"]),
        subject_id=str(item["subject_id"]),
        target=target,
        kind=str(item["kind"]),
        source_id=str(item["source_id"]),
        provenance=str(item["provenance"]),
        trace_event_id=str(item["trace_event_id"]),
        deposited_at_step=int(item["deposited_at_step"]),
        updated_at_step=int(item["updated_at_step"]),
        ttl_steps=(
            int(item["ttl_steps"]) if item.get("ttl_steps") is not None else None
        ),
    )


def _trail_state_problems(replay: _ScoreReplay) -> list[str]:
    problems: list[str] = []
    for trail in replay.trails:
        if trail.updated_at_step != replay.current_step:
            problems.append(
                f"authority_pheromone_active_current_step:{trail.trace_event_id}"
            )
        effective_ttl = _effective_ttl(replay.runtime_policy, trail)
        if _trail_is_expired(trail, replay.current_step, effective_ttl):
            problems.append(f"authority_pheromone_active_ttl:{trail.trace_event_id}")
    return problems


def _effective_ttl(runtime_policy: Any, trail: PheromoneTrail) -> int | None:
    if trail.ttl_steps is not None:
        return int(trail.ttl_steps)
    profile = runtime_policy.kind_profiles.get(trail.kind)
    if profile is None or profile.ttl_steps is None:
        return None
    return int(profile.ttl_steps)


def _trail_is_expired(
    trail: PheromoneTrail,
    current_step: int,
    effective_ttl: int | None,
) -> bool:
    return (
        effective_ttl is not None
        and current_step - trail.deposited_at_step >= effective_ttl
        and trail.kind != "stale"
    )


def _score_dimension_problems(
    pheromone_score_event: TraceEvent,
    replay: _ScoreReplay,
) -> list[str]:
    lineage = pheromone_score_event.lineage
    expected_dimensions = {
        "scores": replay.reconstructed.scores,
        "score_breakdown": replay.reconstructed.score_breakdown,
        "kind_breakdown": replay.reconstructed.kind_breakdown,
        "subject_breakdown": replay.reconstructed.subject_breakdown,
    }
    return [
        f"authority_pheromone_reconstruction_{field_name}"
        for field_name, expected in expected_dimensions.items()
        if not nested_numeric_mapping_near(lineage.get(field_name, {}), expected)
    ]


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

    score_index = next(
        (index for index, event in enumerate(events) if event is pheromone_score_event),
        -1,
    )
    problems = _normalization_problems(events, reconstructed, score_index)
    expected_observations = observe_pheromone_exploration(
        candidate_set=candidates,
        trails=trails,
        policy=runtime_policy,
        current_step=current_step,
        target=pheromone_score_event.target,
    )
    problems.extend(_observation_problems(events, expected_observations, score_index))
    problems.extend(
        _exploration_floor_problems(
            events,
            candidates,
            runtime_policy,
            score_index,
        )
    )
    return problems


def _normalization_problems(
    events: tuple[TraceEvent, ...],
    reconstructed: Any,
    score_index: int,
) -> list[str]:
    observed = [
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "pheromone_normalize"
    ]
    expected = reconstructed.normalization
    if expected is None:
        return ["authority_pheromone_normalize_unexpected"] if observed else []
    if len(observed) != 1:
        return ["authority_pheromone_normalize_count"]
    return _normalization_event_problems(observed[0], expected, score_index)


def _normalization_event_problems(
    observed: tuple[int, TraceEvent],
    expected: Any,
    score_index: int,
) -> list[str]:
    index, event = observed
    lineage = event.lineage
    checks = (
        (
            index <= score_index,
            "authority_pheromone_normalize_order",
        ),
        (
            list(lineage.get("candidates", ())) != list(expected.candidate_ids),
            "authority_pheromone_normalize_candidates",
        ),
        (
            not nested_numeric_mapping_near(
                lineage.get("pre_scores", {}),
                expected.pre_scores,
            ),
            "authority_pheromone_normalize_pre_scores",
        ),
        (
            not nested_numeric_mapping_near(
                lineage.get("post_scores", {}),
                expected.post_scores,
            ),
            "authority_pheromone_normalize_post_scores",
        ),
        (
            lineage.get("response_model") != expected.response_model,
            "authority_pheromone_normalize_response_model",
        ),
        (
            lineage.get("competition_mode") != expected.competition_mode,
            "authority_pheromone_normalize_competition_mode",
        ),
    )
    return [message for failed, message in checks if failed]


def _observation_problems(
    events: tuple[TraceEvent, ...],
    expected_observations: Any,
    score_index: int,
) -> list[str]:
    observed = [
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "pheromone_observe" and "candidate_id" in event.lineage
    ]
    problems = (
        ["authority_pheromone_observe_count"]
        if len(observed) != len(expected_observations)
        else []
    )
    for position, expected in enumerate(expected_observations):
        if position >= len(observed):
            break
        problems.extend(
            _observation_event_problems(
                position,
                observed[position],
                expected,
                score_index,
            )
        )
    return problems


def _observation_event_problems(
    position: int,
    observed: tuple[int, TraceEvent],
    expected: Any,
    score_index: int,
) -> list[str]:
    index, event = observed
    lineage = event.lineage
    expected_fields = {
        "candidate_id": expected.candidate_id,
        "subject_type": expected.subject_type,
        "subject_id": expected.subject_id,
        "reopen_eligible": expected.reopen_eligible,
        "source_trace_event_id": expected.trace_event_id,
    }
    checks = (
        (
            index <= score_index,
            "authority_pheromone_observe_order",
        ),
        (
            any(lineage.get(name) != value for name, value in expected_fields.items()),
            f"authority_pheromone_observe_lineage:{position}",
        ),
        (
            not near(lineage.get("novelty_pressure"), expected.novelty_pressure),
            f"authority_pheromone_observe_novelty:{position}",
        ),
        (
            event.reason != expected.reason,
            f"authority_pheromone_observe_reason:{position}",
        ),
    )
    return [message for failed, message in checks if failed]


def _exploration_floor_problems(
    events: tuple[TraceEvent, ...],
    candidates: Any,
    runtime_policy: Any,
    score_index: int,
) -> list[str]:
    observed = [
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "pheromone_observe"
        and "exploration_floor" in event.lineage
    ]
    candidate_ids = [
        candidate.id
        for candidate in candidates.candidates
        if not candidate.safe_fallback
    ]
    expected = bool(
        runtime_policy.exploration_enabled
        and runtime_policy.exploration_floor > 0
        and candidate_ids
    )
    if len(observed) != (1 if expected else 0):
        return ["authority_pheromone_exploration_floor_count"]
    if not expected:
        return []
    return _exploration_floor_event_problems(
        observed[0],
        candidate_ids,
        runtime_policy,
        score_index,
    )


def _exploration_floor_event_problems(
    observed: tuple[int, TraceEvent],
    candidate_ids: list[str],
    runtime_policy: Any,
    score_index: int,
) -> list[str]:
    index, event = observed
    checks = (
        (
            index <= score_index,
            "authority_pheromone_exploration_floor_order",
        ),
        (
            not near(
                event.lineage.get("exploration_floor"),
                runtime_policy.exploration_floor,
            ),
            "authority_pheromone_exploration_floor_value",
        ),
        (
            list(event.lineage.get("candidate_ids", ())) != candidate_ids,
            "authority_pheromone_exploration_floor_candidates",
        ),
    )
    return [message for failed, message in checks if failed]


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
