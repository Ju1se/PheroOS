from __future__ import annotations

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import LayerCoordinationState
from pheroos.governance._pheromone.invariants import pheromone_policy_from_collective
from pheroos.governance._pheromone.records import PheromoneTrail
from pheroos.governance._pheromone.scoring import (
    add_breakdown,
    collect_pheromone_source_diversity,
    empty_score_breakdown,
    score_pheromone_trails_with_breakdown,
)
from pheroos.governance.runtime_policy import validate_collective_runtime_policy
from pheroos.governance.signal import SignalVerification
from pheroos.protocol.models import CollectiveDecisionPolicy
from pheroos.protocol.models import SWARM_COLLECTIVE_MODES
from typing import Any
import math
from pheroos.governance._swarm.records import CollectiveDecisionState
from pheroos.governance._swarm.signals import (
    InhibitionSignal,
    RecruitmentSignal,
    ScoutReport,
    require_finite_non_negative,
    validate_collective_signal,
    validate_scout_report,
)


def score_candidates(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    scout_reports: list[ScoutReport],
    target: str | None = None,
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
    layer_coordination_state: LayerCoordinationState | None = None,
) -> CollectiveDecisionState:
    if layer_coordination_state is not None:
        raise GovernanceError(
            "externally constructed layer coordination state is not authoritative; "
            "submit layer proposals through evaluate_hybrid_collective_step"
        )
    validate_collective_runtime_policy(policy)
    strict_authority = policy.mode in SWARM_COLLECTIVE_MODES
    if strict_authority and not target:
        raise GovernanceError("swarm candidate scoring requires an active target")
    candidates = [
        candidate
        for candidate in candidate_set.candidates
        if target is None or candidate.target == target
    ]
    active_candidate_set = CandidateSet(tuple(candidates))
    scores = {candidate.id: 0.0 for candidate in candidates}
    independent_scouts: dict[str, set[str]] = {
        candidate.id: set() for candidate in candidates
    }
    pheromone_source_diversity = {candidate.id: 0 for candidate in candidates}
    score_breakdown = empty_score_breakdown(active_candidate_set)
    collective_lineage_ids: set[str] = set()

    def record_lineage_ids(
        source_trace_event_id: str,
        verification: SignalVerification | None,
    ) -> None:
        identifiers = [source_trace_event_id]
        if verification is not None:
            identifiers.append(verification.trace_event_id)
        for trace_event_id in identifiers:
            if not trace_event_id:
                continue
            if trace_event_id in collective_lineage_ids:
                raise GovernanceError(
                    f"duplicate collective trace_event_id: {trace_event_id}"
                )
            collective_lineage_ids.add(trace_event_id)

    verified_scout_ids: set[str] = set()
    for report in sorted(
        scout_reports,
        key=lambda item: (
            item.candidate_id,
            item.scout_id,
            item.evidence_id,
            item.trace_event_id,
        ),
    ):
        validate_scout_report(
            report,
            target=target,
            require_verification=strict_authority,
            maximum_strength=float(policy.quorum_threshold),
        )
        if target is None:
            candidate_set.require_declared(report.candidate_id)
        else:
            candidate_set.require_declared_for_target(report.candidate_id, target)
        if report.scout_id in verified_scout_ids:
            raise GovernanceError(
                f"duplicate scout identity in collective batch: {report.scout_id}"
            )
        verified_scout_ids.add(report.scout_id)
        record_lineage_ids(report.trace_event_id, report.verification)
        support = float(report.support)
        scores[report.candidate_id] += support
        add_breakdown(score_breakdown, report.candidate_id, "scout", support)
        independent_scouts[report.candidate_id].add(report.scout_id)

    if policy.recruitment_enabled:
        recruitment_sources: set[tuple[str, str]] = set()
        for recruitment in sorted(
            recruitment_signals or [],
            key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
        ):
            validate_collective_signal(
                recruitment,
                target=target,
                require_verification=strict_authority,
                signal_name="recruitment",
                maximum_strength=float(policy.quorum_threshold),
            )
            if target is None:
                candidate_set.require_declared(recruitment.candidate_id)
            else:
                candidate_set.require_declared_for_target(
                    recruitment.candidate_id,
                    target,
                )
            identity = (recruitment.source_id, recruitment.candidate_id)
            if identity in recruitment_sources:
                raise GovernanceError(
                    "duplicate recruitment source in collective batch: "
                    f"{recruitment.source_id}"
                )
            recruitment_sources.add(identity)
            record_lineage_ids(
                recruitment.trace_event_id,
                recruitment.verification,
            )
            support = float(recruitment.strength)
            scores[recruitment.candidate_id] += support
            add_breakdown(
                score_breakdown,
                recruitment.candidate_id,
                "recruitment",
                support,
            )

    if policy.inhibition_enabled:
        inhibition_sources: set[tuple[str, str]] = set()
        for inhibition in sorted(
            inhibition_signals or [],
            key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
        ):
            validate_collective_signal(
                inhibition,
                target=target,
                require_verification=strict_authority,
                signal_name="inhibition",
                maximum_strength=float(policy.quorum_threshold),
            )
            if target is None:
                candidate_set.require_declared(inhibition.candidate_id)
            else:
                candidate_set.require_declared_for_target(
                    inhibition.candidate_id,
                    target,
                )
            identity = (inhibition.source_id, inhibition.candidate_id)
            if identity in inhibition_sources:
                raise GovernanceError(
                    "duplicate inhibition source in collective batch: "
                    f"{inhibition.source_id}"
                )
            inhibition_sources.add(identity)
            record_lineage_ids(inhibition.trace_event_id, inhibition.verification)
            support = float(inhibition.strength)
            scores[inhibition.candidate_id] -= support
            add_breakdown(
                score_breakdown,
                inhibition.candidate_id,
                "inhibition",
                -support,
            )

    if policy.pheromone_enabled:
        pheromone_policy = pheromone_policy_from_collective(policy)
        pheromone_source_diversity = collect_pheromone_source_diversity(
            candidate_set=active_candidate_set,
            trails=pheromone_trails or [],
            policy=pheromone_policy,
        )
        pheromone_scores, pheromone_breakdown = score_pheromone_trails_with_breakdown(
            candidate_set=active_candidate_set,
            trails=pheromone_trails or [],
            policy=pheromone_policy,
        )
        for candidate_id, score in pheromone_scores.items():
            scores[candidate_id] += score
            merge_candidate_breakdown(
                score_breakdown, candidate_id, pheromone_breakdown.get(candidate_id, {})
            )

    # Canonicalize totals from the breakdown.  This makes the breakdown the
    # reconstructable ABI source of truth instead of maintaining a second,
    # independently rounded score accumulator.
    scores = {
        candidate_id: sum(candidate_breakdown.values())
        for candidate_id, candidate_breakdown in score_breakdown.items()
    }
    state = CollectiveDecisionState(
        scores=scores,
        independent_scouts=independent_scouts,
        pheromone_source_diversity=pheromone_source_diversity,
        score_breakdown=score_breakdown,
        layer_coordination=layer_coordination_state,
    )
    validate_score_breakdown(state)
    return state


def merge_candidate_breakdown(
    target: dict[str, dict[str, float]],
    candidate_id: str,
    source: dict[str, float],
) -> None:
    for category, value in source.items():
        add_breakdown(target, candidate_id, category, value)


def validate_score_breakdown(
    state: CollectiveDecisionState, *, tolerance: float = 0.0
) -> None:
    require_finite_non_negative(tolerance, "score breakdown tolerance")
    for candidate_id, score in state.scores.items():
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
        ):
            raise GovernanceError(f"candidate score must be finite: {candidate_id}")
        for category, value in state.score_breakdown.get(candidate_id, {}).items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise GovernanceError(
                    f"score breakdown contains a non-finite value: {candidate_id}.{category}"
                )
        total = sum(state.score_breakdown.get(candidate_id, {}).values())
        if abs(total - score) > tolerance:
            raise GovernanceError(
                f"score breakdown does not reconstruct candidate score: {candidate_id}"
            )


def candidate_score_lineage(
    state: CollectiveDecisionState,
    *,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    validate_score_breakdown(state)
    candidate_ids = [candidate_id] if candidate_id is not None else sorted(state.scores)
    return {
        "scores": {
            item: state.scores[item] for item in candidate_ids if item in state.scores
        },
        "score_breakdown": {
            item: dict(state.score_breakdown.get(item, {}))
            for item in candidate_ids
            if item in state.scores
        },
        "independent_scouts": {
            item: sorted(state.independent_scouts.get(item, set()))
            for item in candidate_ids
            if item in state.scores
        },
        "scout_diversity": {
            item: len(state.independent_scouts.get(item, set()))
            for item in candidate_ids
            if item in state.scores
        },
        "pheromone_source_diversity": {
            item: state.pheromone_source_diversity.get(item, 0)
            for item in candidate_ids
            if item in state.scores
        },
    }


for _compat_function in (
    score_candidates,
    merge_candidate_breakdown,
    validate_score_breakdown,
    candidate_score_lineage,
):
    _compat_function.__module__ = "pheroos.governance.collective"
del _compat_function

__all__ = (
    "candidate_score_lineage",
    "merge_candidate_breakdown",
    "score_candidates",
    "validate_score_breakdown",
)
