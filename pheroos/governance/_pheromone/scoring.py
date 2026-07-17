from __future__ import annotations

from dataclasses import replace
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
import math
from pheroos.governance._pheromone.invariants import _finite_number, _non_negative_step, clip_pheromone_strength, legacy_pheromone_weight, pheromone_bound_candidate_id, pheromone_processing_key, pheromone_source_id, pheromone_subject_id, pheromone_subject_type, scoreable_pheromone_candidate_id, validate_pheromone_policy, validate_pheromone_trail
from pheroos.governance._pheromone.lifecycle import is_expired_with_policy
from pheroos.governance._pheromone.records import BREAKDOWN_CATEGORIES, PheromoneExplorationObservation, PheromoneNormalizationRecord, PheromonePolicy, PheromoneScoreResult, PheromoneTrail, SUPPORTED_PHEROMONE_KINDS

def collect_pheromone_source_diversity(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> dict[str, int]:
    _, source_diversity = _capped_pheromone_score_contributions(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    )
    return source_diversity


def _capped_pheromone_score_contributions(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None,
) -> tuple[
    tuple[tuple[PheromoneTrail, str, str, float, str], ...],
    dict[str, int],
]:
    """Resolve deterministic score deltas before applying the diversity gate.

    The per-source cap is global across candidates, so source diversity cannot
    be computed from merely eligible trail presence.  First allocate that cap
    in canonical kind/candidate/source order, then count only sources whose
    post-cap delta is nonzero for each candidate.  The caller can subsequently
    apply the minimum-diversity gate without letting a fully consumed source
    unlock another candidate.
    """

    validate_pheromone_policy(policy)
    if current_step is not None:
        _non_negative_step(current_step, "current_step")
    sources = {candidate.id: set() for candidate in candidate_set.candidates}
    if not policy.enabled:
        return (), {candidate_id: 0 for candidate_id in sources}

    items = list(trails)
    for trail in items:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set)
        if current_step is not None and current_step < trail.updated_at_step:
            raise GovernanceError("current_step must not precede pheromone updated step")
    ordered = [
        trail
        for _, trail in sorted(
            enumerate(items),
            key=lambda item: pheromone_processing_key(item[1], item[0], policy),
        )
    ]
    source_contribution: dict[object, float] = {}
    contributions: list[tuple[PheromoneTrail, str, str, float, str]] = []
    for trail in ordered:
        if current_step is not None and is_expired_with_policy(trail, policy, current_step):
            continue
        candidate_id = scoreable_pheromone_candidate_id(trail, policy)
        if not candidate_id:
            continue
        source_id = pheromone_source_id(trail)
        raw_delta, category = raw_pheromone_delta(trail, policy)
        if trail.kind == "novelty" and policy.exploration_enabled and current_step is not None:
            elapsed = current_step - trail.updated_at_step
            raw_delta *= (1.0 - policy.novelty_decay_rate) ** elapsed
        if raw_delta == 0:
            continue
        responded_delta = apply_pheromone_response(raw_delta, trail, policy)
        if not math.isfinite(responded_delta):
            raise GovernanceError("pheromone response must remain finite")
        if responded_delta == 0:
            continue
        delta = cap_source_contribution(
            responded_delta,
            candidate_id,
            source_id,
            policy,
            source_contribution,
        )
        if not math.isfinite(delta):
            raise GovernanceError("pheromone source contribution must remain finite")
        if delta == 0:
            continue
        contributions.append((trail, candidate_id, source_id, delta, category))
        if source_id:
            sources[candidate_id].add(source_id)
    return tuple(contributions), {
        candidate_id: len(candidate_sources)
        for candidate_id, candidate_sources in sources.items()
    }


def score_pheromone_trails(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> dict[str, float]:
    return dict(score_pheromone_trails_result(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    ).scores)


def score_pheromone_trails_with_breakdown(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    result = score_pheromone_trails_result(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    )
    return dict(result.scores), {
        candidate_id: dict(categories)
        for candidate_id, categories in result.score_breakdown.items()
    }


def score_pheromone_trails_result(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> PheromoneScoreResult:
    validate_pheromone_policy(policy)
    if current_step is not None:
        _non_negative_step(current_step, "current_step")
    scores = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    breakdown = empty_score_breakdown(candidate_set)
    kind_breakdown: dict[str, dict[str, float]] = {
        candidate.id: {} for candidate in candidate_set.candidates
    }
    subject_breakdown: dict[str, dict[str, float]] = {
        candidate.id: {} for candidate in candidate_set.candidates
    }
    positive_support = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    positive_subject_support: dict[str, dict[str, float]] = {
        candidate.id: {} for candidate in candidate_set.candidates
    }
    suppressing_support = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    if not policy.enabled:
        return PheromoneScoreResult(
            scores=scores,
            score_breakdown=breakdown,
            kind_breakdown=kind_breakdown,
            subject_breakdown=subject_breakdown,
        )

    contributions, source_diversity = _capped_pheromone_score_contributions(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    )
    competitive_response = policy.response_model == "competitive" or policy.competition_mode == "normalize"
    competitive_kinds: set[str] = set()
    for trail, candidate_id, _, delta, category in contributions:
        if source_diversity[candidate_id] < policy.min_source_diversity:
            continue
        profile = policy.kind_profiles.get(trail.kind)
        if profile is not None and profile.response_model == "competitive":
            competitive_response = True
            competitive_kinds.add(trail.kind)
        scores[candidate_id] += delta
        add_breakdown(breakdown, candidate_id, category, delta)
        add_dimension_breakdown(kind_breakdown, candidate_id, trail.kind, delta)
        subject_dimension = pheromone_subject_type(trail)
        add_dimension_breakdown(subject_breakdown, candidate_id, subject_dimension, delta)
        if trail.kind == "positive":
            positive_support[candidate_id] += delta
            add_dimension_breakdown(
                positive_subject_support,
                candidate_id,
                subject_dimension,
                delta,
            )
        elif trail.kind in {"cautionary", "alarm"} and pheromone_kind_can_suppress_positive(trail.kind, policy):
            suppressing_support[candidate_id] += abs(delta)

    for candidate_id, cautionary in suppressing_support.items():
        if cautionary > 0 and cautionary >= policy.cautionary_override_threshold:
            scores[candidate_id] -= positive_support[candidate_id]
            add_breakdown(breakdown, candidate_id, "pheromone_cautionary", -positive_support[candidate_id])
            add_dimension_breakdown(
                kind_breakdown,
                candidate_id,
                "cautionary_suppression",
                -positive_support[candidate_id],
            )
            for subject_type, positive_delta in positive_subject_support[candidate_id].items():
                add_dimension_breakdown(
                    subject_breakdown,
                    candidate_id,
                    subject_type,
                    -positive_delta,
                )
    if policy.response_exploration_floor > 0:
        response_floor = min(float(policy.max_strength), float(policy.response_exploration_floor))
        for candidate in candidate_set.candidates:
            if candidate.safe_fallback:
                continue
            candidate_id = candidate.id
            current = scores[candidate_id]
            if current < 0 or current >= response_floor:
                continue
            delta = response_floor - current
            scores[candidate_id] += delta
            add_breakdown(breakdown, candidate_id, "pheromone_response_floor", delta)
            add_dimension_breakdown(
                kind_breakdown,
                candidate_id,
                "response_exploration_floor",
                delta,
            )
            add_dimension_breakdown(
                subject_breakdown,
                candidate_id,
                "candidate",
                delta,
            )
    if policy.exploration_enabled and policy.exploration_floor > 0:
        for candidate in candidate_set.candidates:
            if candidate.safe_fallback:
                continue
            candidate_id = candidate.id
            scores[candidate_id] += policy.exploration_floor
            add_breakdown(breakdown, candidate_id, "pheromone_novelty", policy.exploration_floor)
            add_dimension_breakdown(
                kind_breakdown,
                candidate_id,
                "exploration_floor",
                policy.exploration_floor,
            )
            add_dimension_breakdown(
                subject_breakdown,
                candidate_id,
                "candidate",
                policy.exploration_floor,
            )
    normalization: PheromoneNormalizationRecord | None = None
    if competitive_response:
        pre_scores = dict(scores)
        normalization_offsets = normalize_pheromone_scores(scores, breakdown)
        for candidate_id, offset in normalization_offsets.items():
            add_dimension_breakdown(kind_breakdown, candidate_id, "normalization", offset)
            add_dimension_breakdown(subject_breakdown, candidate_id, "candidate", offset)
        response_model = policy.response_model
        if response_model != "competitive" and competitive_kinds:
            response_model = "competitive:" + ",".join(sorted(competitive_kinds))
        normalization = PheromoneNormalizationRecord(
            response_model=response_model,
            competition_mode=policy.competition_mode,
            candidate_ids=tuple(sorted(scores)),
            pre_scores=pre_scores,
            post_scores=dict(scores),
        )
    for candidate_id in scores:
        reconstructed = math.fsum(breakdown[candidate_id].values())
        if not math.isfinite(reconstructed):
            raise GovernanceError("pheromone score breakdown must remain finite")
        if abs(math.fsum(kind_breakdown[candidate_id].values()) - reconstructed) > 1e-9:
            raise GovernanceError("pheromone kind breakdown does not reconstruct candidate score")
        if abs(math.fsum(subject_breakdown[candidate_id].values()) - reconstructed) > 1e-9:
            raise GovernanceError("pheromone subject breakdown does not reconstruct candidate score")
        scores[candidate_id] = reconstructed
    if normalization is not None:
        normalization = replace(normalization, post_scores=dict(scores))
    return PheromoneScoreResult(
        scores=scores,
        score_breakdown=breakdown,
        kind_breakdown=kind_breakdown,
        subject_breakdown=subject_breakdown,
        normalization=normalization,
    )


def pheromone_kind_can_suppress_positive(kind: str, policy: PheromonePolicy) -> bool:
    profile = policy.kind_profiles.get(kind)
    if profile is not None:
        return profile.can_suppress_positive
    # Preserve the pre-profile cautionary override as the legacy default.
    return kind in {"cautionary", "alarm"}


def raw_pheromone_delta(trail: PheromoneTrail, policy: PheromonePolicy) -> tuple[float, str]:
    strength = clip_pheromone_strength(trail.strength, policy)
    profile = policy.kind_profiles.get(trail.kind)
    if trail.kind not in SUPPORTED_PHEROMONE_KINDS and profile is None:
        return 0.0, "pheromone_positive"
    weight = profile.weight if profile is not None else legacy_pheromone_weight(trail.kind, policy)
    if trail.kind == "stale" or weight == 0:
        return 0.0, "pheromone_positive"
    subject_category = subject_breakdown_category(pheromone_subject_type(trail))
    category = subject_category or kind_breakdown_category(trail.kind)
    if trail.kind in {"negative", "cautionary", "alarm"}:
        return -(strength * weight), category
    return strength * weight, category


def kind_breakdown_category(kind: str) -> str:
    if kind == "negative":
        return "pheromone_negative"
    if kind == "cautionary":
        return "pheromone_cautionary"
    if kind == "alarm":
        return "pheromone_alarm"
    if kind == "novelty":
        return "pheromone_novelty"
    return "pheromone_positive"


def subject_breakdown_category(subject_type: str) -> str:
    if subject_type == "route":
        return "pheromone_route"
    if subject_type == "tool":
        return "pheromone_tool"
    if subject_type == "agent":
        return "pheromone_agent"
    return ""


def apply_pheromone_response(delta: float, trail: PheromoneTrail, policy: PheromonePolicy) -> float:
    value = _finite_number(delta, "pheromone score delta")
    profile = policy.kind_profiles.get(trail.kind)
    response_model = profile.response_model if profile is not None else policy.response_model
    if response_model == "threshold" and abs(value) < policy.activation_threshold:
        return 0.0
    if response_model == "saturating":
        threshold = policy.saturation_threshold
        if threshold <= 0:
            return 0.0
        sign = 1 if value >= 0 else -1
        magnitude = abs(value)
        response = sign * ((magnitude * threshold) / (magnitude + threshold))
        if not math.isfinite(response):
            raise GovernanceError("pheromone response must remain finite")
        return response
    return value


def normalize_pheromone_scores(
    scores: dict[str, float],
    breakdown: dict[str, dict[str, float]],
) -> dict[str, float]:
    if not scores:
        return {}
    for candidate_id, score in scores.items():
        _finite_number(score, f"pheromone score for {candidate_id}")
    mean_score = math.fsum(scores.values()) / len(scores)
    if not math.isfinite(mean_score):
        raise GovernanceError("normalized pheromone mean must remain finite")
    offsets: dict[str, float] = {}
    for candidate_id in sorted(scores):
        scores[candidate_id] -= mean_score
        add_breakdown(breakdown, candidate_id, "pheromone_positive", -mean_score)
        offsets[candidate_id] = -mean_score
    return offsets


def empty_score_breakdown(candidate_set: CandidateSet) -> dict[str, dict[str, float]]:
    return {
        candidate.id: {category: 0.0 for category in BREAKDOWN_CATEGORIES}
        for candidate in candidate_set.candidates
    }


def add_breakdown(
    breakdown: dict[str, dict[str, float]],
    candidate_id: str,
    category: str,
    delta: float,
) -> None:
    value = _finite_number(delta, f"score breakdown {category}")
    if candidate_id not in breakdown:
        breakdown[candidate_id] = {item: 0.0 for item in BREAKDOWN_CATEGORIES}
    if category not in breakdown[candidate_id]:
        breakdown[candidate_id][category] = 0.0
    updated = breakdown[candidate_id][category] + value
    if not math.isfinite(updated):
        raise GovernanceError(f"score breakdown {category} must remain finite")
    breakdown[candidate_id][category] = updated


def add_dimension_breakdown(
    breakdown: dict[str, dict[str, float]],
    candidate_id: str,
    dimension: str,
    delta: float,
) -> None:
    value = _finite_number(delta, f"pheromone dimension breakdown {dimension}")
    categories = breakdown.setdefault(candidate_id, {})
    updated = categories.get(dimension, 0.0) + value
    if not math.isfinite(updated):
        raise GovernanceError(f"pheromone dimension breakdown must remain finite: {dimension}")
    categories[dimension] = updated


def observe_pheromone_exploration(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int,
    target: str | None = None,
) -> tuple[PheromoneExplorationObservation, ...]:
    """Return deterministic runtime-facing exploration observations.

    Observations never create candidates, evidence, or score by themselves.
    Stale route reopening is eligibility only; the runtime must still produce a
    governed scout report before the route can affect commitment.
    """

    validate_pheromone_policy(policy)
    _non_negative_step(current_step, "current_step")
    if not policy.exploration_enabled:
        return ()
    observations: list[PheromoneExplorationObservation] = []
    items = list(trails)
    for trail in items:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set, target=target)
    for _, trail in sorted(
        enumerate(items),
        key=lambda item: pheromone_processing_key(item[1], item[0], policy),
    ):
        expired = is_expired_with_policy(trail, policy, current_step)
        is_stale_route = pheromone_subject_type(trail) == "route" and (trail.kind == "stale" or expired)
        novelty_pressure = 0.0
        if trail.kind == "novelty" and not expired:
            elapsed = current_step - trail.updated_at_step
            novelty_pressure = float(trail.strength) * ((1.0 - policy.novelty_decay_rate) ** elapsed)
            novelty_pressure = min(float(policy.max_strength), max(0.0, novelty_pressure))
        reopen_eligible = (
            is_stale_route
            and float(trail.strength) <= float(policy.stale_route_reopen_threshold)
        )
        if novelty_pressure <= 0 and not reopen_eligible:
            continue
        reason = "stale_route_reopen_eligible" if reopen_eligible else "novelty_pressure_observed"
        observations.append(
            PheromoneExplorationObservation(
                target=trail.target,
                candidate_id=pheromone_bound_candidate_id(trail),
                subject_type=pheromone_subject_type(trail),
                subject_id=pheromone_subject_id(trail),
                novelty_pressure=novelty_pressure,
                reopen_eligible=reopen_eligible,
                reason=reason,
                trace_event_id=trail.trace_event_id,
            )
        )
    return tuple(observations)


def cap_source_contribution(
    delta: float,
    candidate_id: str,
    source_id: str,
    policy: PheromonePolicy,
    source_contribution: dict[object, float],
) -> float:
    del candidate_id  # The cap follows source identity across all candidates.
    _finite_number(delta, "pheromone source contribution")
    key = source_id
    used = source_contribution.get(key, 0.0)
    remaining = max(0.0, policy.per_source_cap - used)
    allowed = min(abs(delta), remaining)
    source_contribution[key] = used + allowed
    return allowed if delta >= 0 else -allowed


for _compat_function in (collect_pheromone_source_diversity, _capped_pheromone_score_contributions, score_pheromone_trails, score_pheromone_trails_with_breakdown, score_pheromone_trails_result, pheromone_kind_can_suppress_positive, raw_pheromone_delta, kind_breakdown_category, subject_breakdown_category, apply_pheromone_response, normalize_pheromone_scores, empty_score_breakdown, add_breakdown, add_dimension_breakdown, observe_pheromone_exploration, cap_source_contribution,):
    _compat_function.__module__ = 'pheroos.governance.pheromone'
del _compat_function

__all__ = ('_capped_pheromone_score_contributions', 'add_breakdown', 'add_dimension_breakdown', 'apply_pheromone_response', 'cap_source_contribution', 'collect_pheromone_source_diversity', 'empty_score_breakdown', 'kind_breakdown_category', 'normalize_pheromone_scores', 'observe_pheromone_exploration', 'pheromone_kind_can_suppress_positive', 'raw_pheromone_delta', 'score_pheromone_trails', 'score_pheromone_trails_result', 'score_pheromone_trails_with_breakdown', 'subject_breakdown_category')
