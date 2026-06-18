from __future__ import annotations

from dataclasses import dataclass, field, replace

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.quorum import QuorumDecision
from pheroos.protocol.models import CollectiveDecisionPolicy


SUPPORTED_PHEROMONE_KINDS = frozenset({"positive", "negative", "cautionary", "novelty", "stale"})
SUPPORTED_PHEROMONE_SUBJECT_TYPES = frozenset({"candidate", "route", "tool", "evidence", "agent"})
PHEROMONE_EXTENSION_PREFIXES = ("x-", "ext.")


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
    subject_type: str = "candidate"
    subject_id: str = ""
    target: str = ""
    route_id: str = ""
    tool_id: str = ""
    kind: str = "positive"
    source_id: str = ""
    source_role: str = ""
    evidence_id: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    deposited_at_step: int = 0
    updated_at_step: int = 0
    ttl_steps: int | None = None


@dataclass(frozen=True)
class PheromonePolicy:
    enabled: bool = False
    evaporation_rate: float = 0.0
    decay_model: str = "exponential"
    min_strength: float = 0.0
    max_strength: float = 10.0
    positive_weight: float = 1.0
    negative_weight: float = 1.0
    cautionary_weight: float = 1.0
    cautionary_override_threshold: float = 1.0
    novelty_weight: float = 0.5
    per_source_cap: float = 3.0
    per_round_deposit_cap: float = 5.0
    min_source_diversity: int = 1
    require_provenance: bool = True
    require_trace: bool = True


@dataclass(frozen=True)
class CollectiveDecisionState:
    scores: dict[str, float] = field(default_factory=dict)
    independent_scouts: dict[str, set[str]] = field(default_factory=dict)
    pheromone_source_diversity: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectiveDecisionStep:
    decision: QuorumDecision
    state: CollectiveDecisionState
    pheromone_trails: list[PheromoneTrail] = field(default_factory=list)


def pheromone_policy_from_collective(policy: CollectiveDecisionPolicy) -> PheromonePolicy:
    return PheromonePolicy(
        enabled=policy.pheromone_enabled,
        evaporation_rate=policy.pheromone_evaporation_rate,
        decay_model=policy.pheromone_decay_model,
        min_strength=policy.pheromone_min_strength,
        max_strength=policy.pheromone_max_strength,
        positive_weight=policy.pheromone_positive_weight,
        negative_weight=policy.pheromone_negative_weight,
        cautionary_weight=policy.pheromone_cautionary_weight,
        cautionary_override_threshold=policy.pheromone_cautionary_override_threshold,
        novelty_weight=policy.pheromone_novelty_weight,
        per_source_cap=policy.pheromone_per_source_cap,
        per_round_deposit_cap=policy.pheromone_per_round_deposit_cap,
        min_source_diversity=policy.pheromone_min_source_diversity,
        require_provenance=policy.pheromone_require_provenance,
        require_trace=policy.pheromone_require_trace,
    )


def clip_pheromone_strength(strength: float, policy: PheromonePolicy) -> float:
    return min(policy.max_strength, max(policy.min_strength, strength))


def validate_pheromone_trail(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
) -> None:
    if trail.subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES and not is_extension_pheromone_value(trail.subject_type):
        raise GovernanceError(f"unsupported pheromone subject type: {trail.subject_type}")
    if trail.kind not in SUPPORTED_PHEROMONE_KINDS and not is_extension_pheromone_value(trail.kind):
        raise GovernanceError(f"unsupported pheromone kind: {trail.kind}")
    if trail.strength < 0:
        raise GovernanceError("pheromone strength must be non-negative")
    if not pheromone_subject_id(trail):
        raise GovernanceError("pheromone trail must declare a subject")
    candidate_id = pheromone_candidate_id(trail)
    if candidate_id and candidate_set is not None:
        candidate_set.require_declared(candidate_id)
    if policy.require_provenance and not trail.provenance:
        raise GovernanceError("pheromone trail is missing provenance")
    if policy.require_trace and not trail.trace_event_id:
        raise GovernanceError("pheromone trail is missing trace event id")
    if trail.deposited_at_step < 0 or trail.updated_at_step < 0:
        raise GovernanceError("pheromone trail steps must be non-negative")
    if trail.updated_at_step < trail.deposited_at_step:
        raise GovernanceError("pheromone updated step must not precede deposit step")
    if trail.ttl_steps is not None and trail.ttl_steps < 0:
        raise GovernanceError("pheromone ttl_steps must be non-negative")


def deposit_pheromone(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
) -> PheromoneTrail:
    validate_pheromone_trail(trail, policy, candidate_set=candidate_set)
    return replace(trail, strength=clip_pheromone_deposit_strength(trail.strength, policy))


def clip_pheromone_deposit_strength(strength: float, policy: PheromonePolicy) -> float:
    return min(policy.per_round_deposit_cap, clip_pheromone_strength(strength, policy))


def evaporate_trails(
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> list[PheromoneTrail]:
    if not policy.enabled:
        return list(trails)
    return [evaporate_trail(trail, policy, current_step=current_step) for trail in trails]


def evaporate_trail(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> PheromoneTrail:
    step = trail.updated_at_step + 1 if current_step is None else current_step
    if step < trail.updated_at_step:
        raise GovernanceError("current_step must not precede pheromone updated step")
    if is_expired(trail, step):
        return replace(trail, kind="stale", strength=policy.min_strength, updated_at_step=step)

    elapsed_steps = max(1, step - trail.updated_at_step)
    retained = retained_pheromone_strength(trail.strength, policy, elapsed_steps)
    return replace(
        trail,
        strength=clip_pheromone_strength(retained, policy),
        updated_at_step=step,
    )


def retained_pheromone_strength(strength: float, policy: PheromonePolicy, elapsed_steps: int) -> float:
    retention = max(0.0, min(1.0, 1.0 - policy.evaporation_rate))
    if policy.decay_model == "exponential":
        return strength * (retention ** elapsed_steps)
    if policy.decay_model == "step":
        return strength * retention if elapsed_steps > 0 else strength
    return strength * max(0.0, 1.0 - policy.evaporation_rate * elapsed_steps)


def is_expired(trail: PheromoneTrail, current_step: int) -> bool:
    return trail.ttl_steps is not None and current_step - trail.deposited_at_step >= trail.ttl_steps


def pheromone_subject_type(trail: PheromoneTrail) -> str:
    if trail.subject_id:
        return trail.subject_type
    if trail.candidate_id:
        return "candidate"
    if trail.route_id:
        return "route"
    if trail.tool_id:
        return "tool"
    return trail.subject_type


def pheromone_subject_id(trail: PheromoneTrail) -> str:
    if trail.subject_id:
        return trail.subject_id
    if trail.candidate_id:
        return trail.candidate_id
    if trail.route_id:
        return trail.route_id
    if trail.tool_id:
        return trail.tool_id
    return ""


def pheromone_candidate_id(trail: PheromoneTrail) -> str:
    subject_type = pheromone_subject_type(trail)
    if subject_type != "candidate":
        return ""
    return pheromone_subject_id(trail)


def pheromone_source_id(trail: PheromoneTrail) -> str:
    return trail.source_id or trail.provenance or ""


def collect_pheromone_source_diversity(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> dict[str, int]:
    sources = {candidate.id: set() for candidate in candidate_set.candidates}
    if not policy.enabled:
        return {candidate_id: 0 for candidate_id in sources}
    for trail in trails:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set)
        if current_step is not None and is_expired(trail, current_step):
            continue
        candidate_id = pheromone_candidate_id(trail)
        if candidate_id:
            sources[candidate_id].add(pheromone_source_id(trail))
    return {candidate_id: len(candidate_sources) for candidate_id, candidate_sources in sources.items()}


def score_pheromone_trails(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> dict[str, float]:
    scores = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    positive_support = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    cautionary_support = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    source_diversity = collect_pheromone_source_diversity(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    )
    source_contribution: dict[tuple[str, str], float] = {}
    if not policy.enabled:
        return scores

    for trail in trails:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set)
        if current_step is not None and is_expired(trail, current_step):
            continue
        candidate_id = pheromone_candidate_id(trail)
        if not candidate_id:
            continue
        if source_diversity[candidate_id] < policy.min_source_diversity:
            continue
        source_id = pheromone_source_id(trail)
        strength = clip_pheromone_strength(trail.strength, policy)
        if trail.kind == "positive":
            raw_delta = strength * policy.positive_weight
            delta = cap_source_contribution(raw_delta, candidate_id, source_id, policy, source_contribution)
            scores[candidate_id] += delta
            positive_support[candidate_id] += delta
        elif trail.kind == "negative":
            raw_delta = -(strength * policy.negative_weight)
            scores[candidate_id] += cap_source_contribution(raw_delta, candidate_id, source_id, policy, source_contribution)
        elif trail.kind == "cautionary":
            raw_delta = -(strength * policy.cautionary_weight)
            delta = cap_source_contribution(raw_delta, candidate_id, source_id, policy, source_contribution)
            scores[candidate_id] += delta
            cautionary_support[candidate_id] += abs(delta)
        elif trail.kind == "novelty":
            raw_delta = strength * policy.novelty_weight
            scores[candidate_id] += cap_source_contribution(raw_delta, candidate_id, source_id, policy, source_contribution)

    for candidate_id, cautionary in cautionary_support.items():
        if cautionary > 0 and cautionary >= policy.cautionary_override_threshold:
            scores[candidate_id] -= positive_support[candidate_id]
    return scores


def cap_source_contribution(
    delta: float,
    candidate_id: str,
    source_id: str,
    policy: PheromonePolicy,
    source_contribution: dict[tuple[str, str], float],
) -> float:
    key = (candidate_id, source_id)
    used = source_contribution.get(key, 0.0)
    remaining = max(0.0, policy.per_source_cap - used)
    allowed = min(abs(delta), remaining)
    source_contribution[key] = used + allowed
    return allowed if delta >= 0 else -allowed


def is_extension_pheromone_value(value: str) -> bool:
    return any(value.startswith(prefix) and len(value) > len(prefix) for prefix in PHEROMONE_EXTENSION_PREFIXES)


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
    pheromone_source_diversity = {candidate.id: 0 for candidate in candidate_set.candidates}

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
        pheromone_policy = pheromone_policy_from_collective(policy)
        pheromone_source_diversity = collect_pheromone_source_diversity(
            candidate_set=candidate_set,
            trails=pheromone_trails or [],
            policy=pheromone_policy,
        )
        pheromone_scores = score_pheromone_trails(
            candidate_set=candidate_set,
            trails=pheromone_trails or [],
            policy=pheromone_policy,
        )
        for candidate_id, score in pheromone_scores.items():
            scores[candidate_id] += score

    return CollectiveDecisionState(
        scores=scores,
        independent_scouts=independent_scouts,
        pheromone_source_diversity=pheromone_source_diversity,
    )


def evaluate_collective_decision(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
    state = score_candidates(
        candidate_set=candidate_set,
        policy=policy,
        scout_reports=scout_reports,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        pheromone_trails=pheromone_trails,
    )
    return decide_collective_state(
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
    fallback_candidate_id: str | None = None,
) -> CollectiveDecisionStep:
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
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        pheromone_trails=active_trails,
    )
    decision = decide_collective_state(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        state=state,
        fallback_candidate_id=fallback_candidate_id,
    )
    return CollectiveDecisionStep(decision=decision, state=state, pheromone_trails=active_trails)


def decide_collective_state(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    state: CollectiveDecisionState,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
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

    fallback = candidate_set.require_declared(fallback_candidate_id or policy.fallback_candidate)
    if not fallback.safe_fallback:
        raise GovernanceError(f"collective fallback candidate is not marked safe: {fallback.id}")
    return QuorumDecision(
        target=target,
        candidate_id=fallback.id,
        committed=True,
        reason="safe_collective_fallback",
    )
