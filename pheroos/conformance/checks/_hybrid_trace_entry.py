from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    HybridReplayState,
    replay_state_from_hybrid_step,
)
from pheroos.governance.quorum import QuorumDecision
from pheroos.protocol.models import (
    CapabilityManifest,
    effective_pheromone_scored_subject_types,
    has_hybrid_pheromone_features,
    required_swarm_trace_events,
)
from pheroos.trace import TraceEvent

from ._hybrid_trace_authority import collective_authority_problems
from ._hybrid_trace_replay import manifest_replay, replay_evaporation_kind


@dataclass(frozen=True)
class _ReplayBundle:
    primary: tuple[Any, TraceEvent]
    replayed: tuple[Any, TraceEvent]
    fallback: tuple[Any, TraceEvent]
    diffusion: tuple[Any, TraceEvent]
    reinforcement: tuple[Any, TraceEvent]
    replay_state: HybridReplayState


@dataclass(frozen=True)
class _TraceIndexes:
    scores: tuple[int, ...]
    decisions: tuple[int, ...]
    outputs: tuple[int, ...]


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(policy):
        return CheckResult("hybrid_trace_contract", True)
    missing = _missing_declared_events(manifest, policy)
    if missing:
        return CheckResult("hybrid_trace_contract", False, ", ".join(missing))
    try:
        bundle = _build_replay_bundle(manifest)
    except Exception as exc:
        return _replay_exception_result(exc)
    return _check_replay_bundle(manifest, policy, bundle)


def _missing_declared_events(manifest: CapabilityManifest, policy: Any) -> list[str]:
    return sorted(
        required_swarm_trace_events(policy)
        - set(manifest.protocol.trace_policy.required_events)
    )


def _build_replay_bundle(manifest: CapabilityManifest) -> _ReplayBundle:
    primary = manifest_replay(manifest)
    replay_state = replay_state_from_hybrid_step(primary[0])
    return _ReplayBundle(
        primary=primary,
        replayed=manifest_replay(manifest, replay_state=replay_state),
        fallback=manifest_replay(manifest, force_fallback=True),
        diffusion=manifest_replay(
            manifest,
            force_fallback=True,
            lifecycle_focus="diffusion",
        ),
        reinforcement=manifest_replay(
            manifest,
            force_fallback=True,
            lifecycle_focus="reinforcement",
        ),
        replay_state=replay_state,
    )


def _replay_exception_result(exc: Exception) -> CheckResult:
    detail = str(exc).strip()
    suffix = f":{detail}" if detail else ""
    return CheckResult(
        "hybrid_trace_contract",
        False,
        f"replay:{type(exc).__name__}{suffix}",
    )


def _check_replay_bundle(
    manifest: CapabilityManifest,
    policy: Any,
    bundle: _ReplayBundle,
) -> CheckResult:
    primary_result = _check_replay_pair(manifest, bundle.primary)
    if not primary_result.ok:
        return primary_result
    failure = _secondary_replay_failure(manifest, bundle)
    if failure is not None:
        return failure
    coverage = _coverage_events(bundle)
    problems = actual_trace_coverage_problems(
        policy,
        {event.event_type for event in coverage},
        events=coverage,
    )
    return (
        CheckResult("hybrid_trace_contract", False, "; ".join(problems))
        if problems
        else primary_result
    )


def _check_replay_pair(
    manifest: CapabilityManifest,
    pair: tuple[Any, TraceEvent],
    *,
    replay_state: HybridReplayState | None = None,
) -> CheckResult:
    step, output = pair
    return check_actual_trace(
        manifest,
        [*step.trace_events, output],
        decision=step.decision,
        replay_state=replay_state,
    )


def _secondary_replay_failure(
    manifest: CapabilityManifest,
    bundle: _ReplayBundle,
) -> CheckResult | None:
    checks = (
        ("idempotent_replay", bundle.replayed, bundle.replay_state),
        ("fallback_replay", bundle.fallback, None),
        ("diffusion_replay", bundle.diffusion, None),
        ("reinforcement_replay", bundle.reinforcement, None),
    )
    for label, pair, replay_state in checks:
        result = _check_replay_pair(manifest, pair, replay_state=replay_state)
        if not result.ok:
            return CheckResult(
                "hybrid_trace_contract",
                False,
                f"{label}:{result.detail}",
            )
        if label == "fallback_replay" and not _has_fallback_event(pair[0]):
            return CheckResult(
                "hybrid_trace_contract",
                False,
                "fallback_replay:fallback_event_missing",
            )
    return None


def _has_fallback_event(step: Any) -> bool:
    return "fallback" in {event.event_type for event in step.trace_events}


def _coverage_events(bundle: _ReplayBundle) -> tuple[TraceEvent, ...]:
    pairs = (
        bundle.primary,
        bundle.replayed,
        bundle.diffusion,
        bundle.reinforcement,
    )
    return tuple(
        event for step, output in pairs for event in (*step.trace_events, output)
    )


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
    if not items:
        return CheckResult("hybrid_trace_contract", False, "actual_trace_empty")
    active_candidates = _active_candidates(manifest)
    indexes = _trace_indexes(items)
    problems = _trace_shape_problems(
        manifest,
        items,
        active_candidates,
        indexes,
        decision,
    )
    problems.extend(_authority_problems(manifest, items, replay_state))
    if enforce_declared_coverage:
        problems.extend(_declared_coverage_problems(policy, items))
    return CheckResult("hybrid_trace_contract", not problems, "; ".join(problems))


def _active_candidates(manifest: CapabilityManifest) -> dict[str, Any]:
    target = manifest.protocol.quorum_policy.target
    return {
        candidate.id: candidate
        for candidate in manifest.protocol.candidates
        if candidate.target == target
    }


def _trace_indexes(items: tuple[TraceEvent, ...]) -> _TraceIndexes:
    return _TraceIndexes(
        scores=tuple(
            index
            for index, event in enumerate(items)
            if event.event_type == "candidate_score"
        ),
        decisions=tuple(
            index
            for index, event in enumerate(items)
            if event.event_type in {"commit", "fallback"}
        ),
        outputs=tuple(
            index for index, event in enumerate(items) if event.event_type == "output"
        ),
    )


def _trace_shape_problems(
    manifest: CapabilityManifest,
    items: tuple[TraceEvent, ...],
    active_candidates: dict[str, Any],
    indexes: _TraceIndexes,
    decision: QuorumDecision | None,
) -> list[str]:
    problems = _event_envelope_problems(manifest, items)
    problems.extend(_index_order_problems(indexes))
    problems.extend(_score_coverage_problems(items, active_candidates, indexes))
    problems.extend(_decision_problems(items, active_candidates, indexes, decision))
    problems.extend(_output_problems(items, indexes))
    return problems


def _event_envelope_problems(
    manifest: CapabilityManifest,
    items: tuple[TraceEvent, ...],
) -> list[str]:
    problems: list[str] = []
    target = manifest.protocol.quorum_policy.target
    protocol_id = manifest.protocol.id
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
    return problems


def _index_order_problems(indexes: _TraceIndexes) -> list[str]:
    problems: list[str] = []
    if not indexes.scores:
        problems.append("candidate_score_missing")
    if len(indexes.decisions) != 1:
        problems.append("decision_event_count")
    elif indexes.scores and indexes.decisions[0] <= indexes.scores[-1]:
        problems.append("decision_precedes_score")
    return problems


def _score_coverage_problems(
    items: tuple[TraceEvent, ...],
    active_candidates: dict[str, Any],
    indexes: _TraceIndexes,
) -> list[str]:
    problems: list[str] = []
    expected = set(active_candidates)
    for index in indexes.scores:
        lineage = items[index].lineage
        fields = (
            ("scores", "score_target_coverage"),
            ("scout_diversity", "scout_diversity_coverage"),
            ("pheromone_source_diversity", "pheromone_diversity_coverage"),
        )
        for field, label in fields:
            if set(lineage.get(field, {})) != expected:
                problems.append(f"event:{index}:{label}")
    problems.extend(_pheromone_score_coverage_problems(items, expected))
    return problems


def _pheromone_score_coverage_problems(
    items: tuple[TraceEvent, ...],
    expected: set[str],
) -> list[str]:
    return [
        f"event:{index}:pheromone_score_target_coverage"
        for index, event in enumerate(items)
        if event.event_type == "pheromone_score"
        and set(event.lineage.get("scores", {})) != expected
    ]


def _decision_problems(
    items: tuple[TraceEvent, ...],
    active_candidates: dict[str, Any],
    indexes: _TraceIndexes,
    decision: QuorumDecision | None,
) -> list[str]:
    if len(indexes.decisions) != 1:
        return []
    event = items[indexes.decisions[0]]
    candidate_id = cast(str, event.lineage.get("candidate_id"))
    candidate = active_candidates.get(candidate_id)
    problems = _declared_decision_problems(event, candidate)
    if decision is not None:
        problems.extend(_expected_decision_problems(event, candidate_id, decision))
    return problems


def _declared_decision_problems(event: TraceEvent, candidate: Any) -> list[str]:
    problems: list[str] = []
    if candidate is None:
        problems.append("decision_undeclared_candidate")
    if event.event_type == "fallback" and (
        candidate is None or not candidate.safe_fallback
    ):
        problems.append("fallback_not_safe")
    if event.event_type == "commit" and "fallback" in str(
        event.lineage.get("decision_reason", "")
    ):
        problems.append("fallback_mislabeled_commit")
    return problems


def _expected_decision_problems(
    event: TraceEvent,
    candidate_id: Any,
    decision: QuorumDecision,
) -> list[str]:
    problems: list[str] = []
    expected_type = "fallback" if "fallback" in decision.reason else "commit"
    if event.event_type != expected_type:
        problems.append("decision_event_type")
    if (
        candidate_id != decision.candidate_id
        or event.lineage.get("decision_reason") != decision.reason
    ):
        problems.append("decision_lineage_mismatch")
    return problems


def _output_problems(
    items: tuple[TraceEvent, ...],
    indexes: _TraceIndexes,
) -> list[str]:
    problems: list[str] = []
    if (
        indexes.outputs
        and indexes.decisions
        and min(indexes.outputs) <= indexes.decisions[0]
    ):
        problems.append("output_precedes_decision")
    causal_commit = len(indexes.decisions) == 1
    for index in indexes.outputs:
        if items[index].lineage.get("committed_candidate") is not causal_commit:
            problems.append(f"authority_output_committed_candidate:{index}")
    return problems


def _authority_problems(
    manifest: CapabilityManifest,
    items: tuple[TraceEvent, ...],
    replay_state: HybridReplayState | None,
) -> list[str]:
    try:
        return collective_authority_problems(
            manifest,
            items,
            replay_state=replay_state,
        )
    except Exception as exc:
        detail = str(exc).strip()
        suffix = f":{detail}" if detail else ""
        return [f"authority_reconstruction:{type(exc).__name__}{suffix}"]


def _declared_coverage_problems(
    policy: Any,
    items: tuple[TraceEvent, ...],
) -> list[str]:
    if policy is None:
        return []
    return actual_trace_coverage_problems(
        policy,
        {event.event_type for event in items},
        events=items,
    )


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
        required -= {"commit", "fallback"} - observed
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
