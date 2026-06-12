from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.quorum import QuorumDecision
from pheroos.protocol.models import CollectiveDecisionPolicy


@dataclass(frozen=True)
class ScoutReport:
    scout_id: str
    candidate_id: str
    evidence_id: str
    provenance: str
    support: float = 1.0


@dataclass(frozen=True)
class RecruitmentSignal:
    source_id: str
    candidate_id: str
    strength: float = 1.0


@dataclass(frozen=True)
class InhibitionSignal:
    source_id: str
    candidate_id: str
    strength: float = 1.0


@dataclass(frozen=True)
class PheromoneTrail:
    candidate_id: str
    strength: float


@dataclass(frozen=True)
class PheromonePolicy:
    enabled: bool = False
    evaporation_rate: float = 0.0


@dataclass(frozen=True)
class CollectiveDecisionState:
    scores: dict[str, float] = field(default_factory=dict)
    independent_scouts: dict[str, set[str]] = field(default_factory=dict)


def evaporate_trails(trails: list[PheromoneTrail], policy: PheromonePolicy) -> list[PheromoneTrail]:
    if not policy.enabled:
        return list(trails)
    retention = max(0.0, min(1.0, 1.0 - policy.evaporation_rate))
    return [
        PheromoneTrail(candidate_id=trail.candidate_id, strength=trail.strength * retention)
        for trail in trails
    ]


def score_candidates(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
) -> CollectiveDecisionState:
    scores = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    independent_scouts = {candidate.id: set() for candidate in candidate_set.candidates}

    for report in scout_reports:
        candidate_set.require_declared(report.candidate_id)
        if not report.provenance:
            raise GovernanceError(f"scout report evidence is missing provenance: {report.evidence_id}")
        scores[report.candidate_id] += max(0.0, report.support)
        independent_scouts[report.candidate_id].add(report.scout_id)

    if policy.recruitment_enabled:
        for signal in recruitment_signals or []:
            candidate_set.require_declared(signal.candidate_id)
            scores[signal.candidate_id] += max(0.0, signal.strength)

    if policy.inhibition_enabled:
        for signal in inhibition_signals or []:
            candidate_set.require_declared(signal.candidate_id)
            scores[signal.candidate_id] -= max(0.0, signal.strength)

    if policy.pheromone_enabled:
        for trail in pheromone_trails or []:
            candidate_set.require_declared(trail.candidate_id)
            scores[trail.candidate_id] += max(0.0, trail.strength)

    return CollectiveDecisionState(scores=scores, independent_scouts=independent_scouts)


def evaluate_collective_decision(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
) -> QuorumDecision:
    state = score_candidates(
        candidate_set=candidate_set,
        policy=policy,
        scout_reports=scout_reports,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        pheromone_trails=pheromone_trails,
    )
    candidates_by_score = sorted(state.scores.items(), key=lambda item: (-item[1], item[0]))
    for candidate_id, score in candidates_by_score:
        scout_count = len(state.independent_scouts[candidate_id])
        if scout_count >= policy.min_independent_scouts and score >= policy.quorum_threshold:
            candidate = candidate_set.require_declared(candidate_id)
            return QuorumDecision(
                target=target,
                candidate_id=candidate.id,
                committed=True,
                reason="collective_consensus",
            )

    fallback = candidate_set.require_declared(policy.fallback_candidate)
    if not fallback.safe_fallback:
        raise GovernanceError(f"collective fallback candidate is not marked safe: {fallback.id}")
    return QuorumDecision(
        target=target,
        candidate_id=fallback.id,
        committed=True,
        reason="safe_collective_fallback",
    )
