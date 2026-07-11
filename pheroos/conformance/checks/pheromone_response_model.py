from __future__ import annotations

from dataclasses import replace
import math

from pheroos.conformance.checks._manifest import active_target, candidate_set, exercise_candidate_id, target_candidate_ids
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    CandidateSet,
    PheromonePolicy,
    PheromoneTrail,
    observe_pheromone_exploration,
    pheromone_policy_from_collective,
    score_pheromone_trails,
    score_pheromone_trails_result,
)
from pheroos.protocol.models import CapabilityManifest, has_hybrid_pheromone_features


def check(manifest: CapabilityManifest) -> CheckResult:
    collective_policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(collective_policy):
        return CheckResult("pheromone_response_model", True)
    if collective_policy is None:
        return CheckResult("pheromone_response_model", False, "collective_policy")

    try:
        problems = response_model_problems(manifest)
    except Exception as exc:  # total-function boundary for direct check consumers
        detail = str(exc).strip()
        return CheckResult(
            "pheromone_response_model",
            False,
            f"exercise:{type(exc).__name__}" + (f":{detail}" if detail else ""),
        )
    return CheckResult("pheromone_response_model", not problems, ", ".join(problems))


def response_model_problems(manifest: CapabilityManifest) -> list[str]:
    collective_policy = manifest.protocol.collective_decision_policy
    if collective_policy is None:
        return ["collective_policy"]

    candidates = candidate_set(manifest)
    candidate_ids = target_candidate_ids(manifest)
    alpha = exercise_candidate_id(manifest)
    if alpha is None:
        return ["active_target_candidates"]
    beta = next((item for item in candidate_ids if item != alpha), alpha)
    target = active_target(manifest)
    policy = pheromone_policy_from_collective(collective_policy)
    strength = min(
        policy.max_strength,
        max(policy.min_strength, 1.0, policy.activation_threshold + 1.0),
    )
    trails = [
        trail(alpha, strength, target=target, source="agent:alpha"),
        trail(beta, strength, target=target, source="agent:beta"),
    ]
    forward = score_pheromone_trails(candidate_set=candidates, policy=policy, trails=trails)
    reverse = score_pheromone_trails(candidate_set=candidates, policy=policy, trails=list(reversed(trails)))
    baseline = score_pheromone_trails(candidate_set=candidates, policy=policy, trails=[])
    profile = policy.kind_profiles.get("positive")
    response_model = profile.response_model if profile is not None else policy.response_model

    problems: list[str] = []
    if forward != reverse:
        problems.append("permutation_sensitive")
    if any(not math.isfinite(score) for score in forward.values()):
        problems.append("non_finite")
    if response_model == "threshold" and policy.activation_threshold > 0 and policy.min_strength == 0:
        below = trail(alpha, 0.0, target=target, source="agent:below")
        if score_pheromone_trails(candidate_set=candidates, policy=policy, trails=[below]) != baseline:
            problems.append("threshold")
    if response_model == "saturating" and policy.saturation_threshold > 0:
        delta = abs(forward[alpha] - baseline[alpha])
        if delta > policy.saturation_threshold:
            problems.append("saturating")
    competitive = response_model == "competitive" or policy.response_model == "competitive" or policy.competition_mode == "normalize"
    if competitive and not math.isclose(math.fsum(forward.values()), 0.0, abs_tol=1e-9):
        problems.append("competitive_normalize")
    nonfallback_ids = {
        candidate.id
        for candidate in candidates.candidates
        if candidate.target == target and not candidate.safe_fallback
    }
    if policy.response_exploration_floor > 0:
        response_floor = min(policy.max_strength, policy.response_exploration_floor)
        response_result = score_pheromone_trails_result(
            candidate_set=candidates,
            policy=replace(policy, exploration_enabled=False, exploration_floor=0.0),
            trails=[],
        )
        if any(
            not math.isclose(
                response_result.kind_breakdown[candidate_id].get(
                    "response_exploration_floor",
                    0.0,
                ),
                response_floor,
                abs_tol=1e-9,
            )
            for candidate_id in nonfallback_ids
        ):
            problems.append("response_exploration_floor")
    if policy.exploration_enabled and policy.exploration_floor > 0:
        exploration_result = score_pheromone_trails_result(
            candidate_set=candidates,
            policy=replace(policy, response_exploration_floor=0.0),
            trails=[],
        )
        if any(
            not math.isclose(
                exploration_result.kind_breakdown[candidate_id].get("exploration_floor", 0.0),
                policy.exploration_floor,
                abs_tol=1e-9,
            )
            for candidate_id in nonfallback_ids
        ):
            problems.append("exploration_floor")
    problems.extend(
        exploration_policy_problems(
            candidates=candidates,
            candidate_id=alpha,
            target=target,
            policy=policy,
        )
    )
    return problems


def exploration_policy_problems(
    *,
    candidates: CandidateSet,
    candidate_id: str,
    target: str,
    policy: PheromonePolicy,
) -> list[str]:
    """Exercise declared exploration decay and stale-route reopening semantics."""

    problems: list[str] = []
    current_step = 2
    maximum = float(policy.max_strength)
    minimum = float(policy.min_strength)
    decay = float(policy.novelty_decay_rate)
    reopen_threshold = float(policy.stale_route_reopen_threshold)

    novelty = trail(
        candidate_id,
        maximum,
        target=target,
        source="agent:novelty",
        subject_type="route",
        subject_id="route:novelty",
        kind="novelty",
        updated_at_step=0,
        ttl_steps=current_step + 1,
        trace_event_id="trace:exploration:novelty",
    )
    if not policy.exploration_enabled:
        return disabled_exploration_problems(
            candidates=candidates,
            policy=policy,
            target=target,
            trails=[novelty],
            current_step=current_step,
        )

    stale_trails: list[PheromoneTrail] = []
    expected_reopen: dict[str, bool] = {}

    # A boundary trail exists only when the threshold intersects the valid
    # active-strength interval. A threshold above max_strength consequently
    # makes every valid stale route eligible, while one below min_strength
    # makes none eligible.
    if reopen_threshold >= minimum:
        boundary_strength = min(reopen_threshold, maximum)
        boundary = trail(
            candidate_id,
            boundary_strength,
            target=target,
            source="agent:stale-boundary",
            subject_type="route",
            subject_id="route:stale-boundary",
            kind="stale",
            trace_event_id="trace:exploration:stale-boundary",
        )
        stale_trails.append(boundary)
        expected_reopen[boundary.trace_event_id] = True
    if reopen_threshold < maximum:
        above_strength = max(minimum, math.nextafter(reopen_threshold, math.inf))
        above = trail(
            candidate_id,
            above_strength,
            target=target,
            source="agent:stale-above",
            subject_type="route",
            subject_id="route:stale-above",
            kind="stale",
            trace_event_id="trace:exploration:stale-above",
        )
        stale_trails.append(above)
        expected_reopen[above.trace_event_id] = False

    exercise_trails = [novelty, *stale_trails]
    observations = observe_pheromone_exploration(
        candidate_set=candidates,
        trails=exercise_trails,
        policy=policy,
        current_step=current_step,
        target=target,
    )

    expected_pressure = maximum * ((1.0 - decay) ** current_step)
    novelty_observations = [
        observation
        for observation in observations
        if observation.trace_event_id == novelty.trace_event_id
    ]
    novelty_observation = novelty_observations[0] if len(novelty_observations) == 1 else None
    if expected_pressure > 0:
        if (
            novelty_observation is None
            or not math.isclose(
                novelty_observation.novelty_pressure,
                expected_pressure,
                rel_tol=1e-9,
                abs_tol=0.0,
            )
            or novelty_observation.reopen_eligible
            or novelty_observation.reason != "novelty_pressure_observed"
        ):
            problems.append("novelty_decay_rate")
    elif novelty_observations:
        problems.append("novelty_decay_rate")
    if novelty_observation is not None and not 0 <= novelty_observation.novelty_pressure <= maximum:
        problems.append("novelty_pressure_bounds")

    for trace_event_id, should_reopen in expected_reopen.items():
        matching = [
            observation
            for observation in observations
            if observation.trace_event_id == trace_event_id
        ]
        if should_reopen and (
            len(matching) != 1
            or not matching[0].reopen_eligible
            or matching[0].reason != "stale_route_reopen_eligible"
        ):
            problems.append("stale_route_reopen_threshold")
            break
        if not should_reopen and matching:
            problems.append("stale_route_reopen_threshold")
            break

    problems.extend(
        disabled_exploration_problems(
            candidates=candidates,
            policy=policy,
            target=target,
            trails=exercise_trails,
            current_step=current_step,
        )
    )
    return problems


def disabled_exploration_problems(
    *,
    candidates: CandidateSet,
    policy: PheromonePolicy,
    target: str,
    trails: list[PheromoneTrail],
    current_step: int,
) -> list[str]:
    problems: list[str] = []
    disabled_policy = replace(policy, exploration_enabled=False)
    disabled = observe_pheromone_exploration(
        candidate_set=candidates,
        trails=trails,
        policy=disabled_policy,
        current_step=current_step,
        target=target,
    )
    if disabled:
        problems.append("exploration_disabled")
    disabled_scores = score_pheromone_trails(
        candidate_set=candidates,
        trails=trails,
        policy=replace(
            disabled_policy,
            exploration_floor=0.0,
            response_exploration_floor=0.0,
        ),
        current_step=current_step,
    )
    if any(not math.isclose(score, 0.0, abs_tol=1e-9) for score in disabled_scores.values()):
        problems.append("exploration_disabled_novelty_score")
    return problems


def trail(
    candidate_id: str,
    strength: float,
    *,
    target: str,
    source: str,
    subject_type: str = "candidate",
    subject_id: str | None = None,
    kind: str = "positive",
    updated_at_step: int = 0,
    ttl_steps: int | None = None,
    trace_event_id: str | None = None,
) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type=subject_type,
        subject_id=candidate_id if subject_id is None else subject_id,
        target=target,
        kind=kind,
        source_id=source,
        evidence_id="evidence:conformance",
        provenance=source,
        trace_event_id=trace_event_id or f"trace:{source}:{candidate_id}",
        updated_at_step=updated_at_step,
        ttl_steps=ttl_steps,
    )
