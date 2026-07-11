from __future__ import annotations

from dataclasses import replace
from math import isclose

from pheroos.conformance.checks._manifest import active_target, candidate_set, exercise_candidate_id
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    PheromoneTrail,
    PheromoneBudgetState,
    collect_pheromone_source_diversity,
    deposit_pheromone_trails,
    evaporate_trails,
    pheromone_policy_from_collective,
    score_pheromone_trails_result,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import (
    CapabilityManifest,
    SUPPORTED_PHEROMONE_KINDS,
    effective_pheromone_scored_subject_types,
    has_hybrid_pheromone_features,
)


NEGATIVE_KINDS = frozenset({"negative", "cautionary", "alarm"})


def check(manifest: CapabilityManifest) -> CheckResult:
    collective_policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(collective_policy):
        return CheckResult("pheromone_kind_profile", True)
    if collective_policy is None:
        return CheckResult("pheromone_kind_profile", False, "collective_policy")
    try:
        problems = kind_profile_problems(manifest)
    except Exception as exc:  # total-function boundary for direct check consumers
        detail = str(exc).strip()
        return CheckResult(
            "pheromone_kind_profile",
            False,
            f"exercise:{type(exc).__name__}" + (f":{detail}" if detail else ""),
        )
    return CheckResult("pheromone_kind_profile", not problems, ", ".join(problems))


def kind_profile_problems(manifest: CapabilityManifest) -> list[str]:
    candidates = candidate_set(manifest)
    candidate_id = exercise_candidate_id(manifest)
    if candidate_id is None:
        return ["active_target_candidates"]
    target = active_target(manifest)
    collective_policy = manifest.protocol.collective_decision_policy
    if collective_policy is None:
        return ["collective_policy"]
    policy = pheromone_policy_from_collective(collective_policy)
    strength = float(policy.max_strength)
    problems: list[str] = []

    for kind, profile in sorted(policy.kind_profiles.items()):
        competitive_singleton = (
            policy.response_model == "competitive"
            or policy.competition_mode == "normalize"
            or profile.response_model == "competitive"
        ) and len(candidates.candidates) == 1
        subject_types = effective_pheromone_scored_subject_types(
            kind,
            profile,
            policy.scored_subject_types,
        )
        # Stale is a mandatory no-score terminal state even though its profile
        # deliberately declares no scored subjects. A namespaced extension kind
        # with no per-kind subject declaration is likewise exercised as a
        # mandatory metadata-only path.
        exercise_subjects = subject_types or (
            ("candidate",)
            if kind == "stale" or kind not in SUPPORTED_PHEROMONE_KINDS
            else ()
        )
        if (
            not exercise_subjects
            and profile.weight > 0
            and kind in SUPPORTED_PHEROMONE_KINDS
        ):
            problems.append(f"{kind}_no_scored_subjects")

        for subject_type in exercise_subjects:
            items = profile_trails(
                candidate_id,
                target=target,
                kind=kind,
                subject_type=subject_type,
                strength=strength,
                source_count=policy.min_source_diversity,
            )
            score_result = score_pheromone_trails_result(
                candidate_set=candidates,
                policy=policy,
                trails=items,
            )
            observed = float(
                score_result.kind_breakdown[candidate_id].get(kind, 0.0)
            )
            response_active = bool(subject_types) and kind_response_can_score(
                kind,
                strength,
                profile.weight,
                policy,
            )
            label = f"{kind}_{subject_type}"
            if kind == "stale" or not response_active:
                if observed != 0.0:
                    problems.append(f"{label}_unexpected_score")
            elif not competitive_singleton and kind in NEGATIVE_KINDS and observed >= 0.0:
                problems.append(f"{label}_pressure")
            elif not competitive_singleton and kind not in NEGATIVE_KINDS and observed <= 0.0:
                problems.append(f"{label}_pressure")

        if profile.ttl_steps is not None:
            ttl_subject = subject_types[0] if subject_types else "candidate"
            expiring = profile_trails(
                candidate_id,
                target=target,
                kind=kind,
                subject_type=ttl_subject,
                strength=strength,
                source_count=1,
            )[0]
            expired = evaporate_trails(
                [expiring],
                policy,
                current_step=profile.ttl_steps,
            )[0]
            if expired.kind != "stale" or not isclose(
                expired.strength,
                float(policy.min_strength),
                abs_tol=1e-9,
            ):
                problems.append(f"{kind}_profile_ttl")

    problems.extend(
        kind_priority_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
    )
    problems.extend(
        kind_suppression_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
    )
    problems.extend(
        post_cap_source_diversity_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
    )
    return problems


def post_cap_source_diversity_problems(
    *,
    candidates: object,
    candidate_id: str,
    target: str,
    policy: object,
) -> list[str]:
    """Prove a globally exhausted source cannot unlock another candidate."""

    diversity = policy.min_source_diversity
    if diversity < 2 or policy.per_source_cap <= 0:
        return []
    other_ids = sorted(
        candidate.id
        for candidate in candidates.candidates
        if candidate.target == target and candidate.id != candidate_id
    )
    if not other_ids:
        return []
    alarm_profile = policy.kind_profiles.get("alarm")
    positive_profile = policy.kind_profiles.get("positive")
    if alarm_profile is None or positive_profile is None:
        return []
    if (
        "candidate" not in effective_pheromone_scored_subject_types(
            "alarm",
            alarm_profile,
            policy.scored_subject_types,
        )
        or "candidate" not in effective_pheromone_scored_subject_types(
            "positive",
            positive_profile,
            policy.scored_subject_types,
        )
        or alarm_profile.priority <= positive_profile.priority
        or not kind_response_can_score(
            "alarm",
            float(policy.max_strength),
            float(alarm_profile.weight),
            policy,
        )
        or not kind_response_can_score(
            "positive",
            float(policy.max_strength),
            float(positive_profile.weight),
            policy,
        )
        or kind_response_magnitude(
            "alarm",
            float(policy.max_strength),
            float(alarm_profile.weight),
            policy,
        )
        < float(policy.per_source_cap)
    ):
        return []

    other_id = other_ids[0]
    shared_source = "agent:conformance:post-cap:shared"
    high = profile_trails(
        candidate_id,
        target=target,
        kind="alarm",
        subject_type="candidate",
        strength=float(policy.max_strength),
        source_count=diversity,
    )
    high[0] = replace(
        high[0],
        source_id=shared_source,
        trace_event_id="trace:conformance:post-cap:high:shared",
    )
    low = profile_trails(
        other_id,
        target=target,
        kind="positive",
        subject_type="candidate",
        strength=float(policy.max_strength),
        source_count=diversity,
    )
    low[0] = replace(
        low[0],
        source_id=shared_source,
        trace_event_id="trace:conformance:post-cap:low:shared",
    )
    trails = [*high, *low]
    observed_diversity = collect_pheromone_source_diversity(
        candidate_set=candidates,
        trails=trails,
        policy=policy,
    )
    result = score_pheromone_trails_result(
        candidate_set=candidates,
        trails=trails,
        policy=policy,
    )
    reverse_diversity = collect_pheromone_source_diversity(
        candidate_set=candidates,
        trails=list(reversed(trails)),
        policy=policy,
    )
    reverse_result = score_pheromone_trails_result(
        candidate_set=candidates,
        trails=list(reversed(trails)),
        policy=policy,
    )

    problems: list[str] = []
    if observed_diversity.get(candidate_id) != diversity:
        problems.append("post_cap_source_diversity_priority_candidate")
    if observed_diversity.get(other_id) != diversity - 1:
        problems.append("post_cap_source_diversity_exhausted_source")
    if not isclose(
        float(result.kind_breakdown[other_id].get("positive", 0.0)),
        0.0,
        abs_tol=1e-9,
    ):
        problems.append("post_cap_source_diversity_gate")
    if reverse_diversity != observed_diversity or reverse_result.scores != result.scores:
        problems.append("post_cap_source_diversity_permutation")
    return problems


def kind_priority_problems(
    *,
    candidates: object,
    candidate_id: str,
    target: str,
    policy: object,
) -> list[str]:
    strength = min(
        float(policy.max_strength),
        float(policy.per_source_cap),
        float(policy.per_round_deposit_cap),
    )
    items = [
        profile_trails(
            candidate_id,
            target=target,
            kind=kind,
            subject_type="candidate",
            strength=strength,
            source_count=1,
        )[0]
        for kind in policy.kind_profiles
    ]
    forward = deposit_pheromone_trails(
        items,
        policy,
        candidate_set=candidates,
        target=target,
    )
    reverse = deposit_pheromone_trails(
        list(reversed(items)),
        policy,
        candidate_set=candidates,
        target=target,
    )
    forward_kinds = [record.kind for record in forward.records]
    reverse_kinds = [record.kind for record in reverse.records]
    observed_priorities = [policy.kind_profiles[kind].priority for kind in forward_kinds]
    problems: list[str] = []
    if sorted(forward_kinds) != sorted(policy.kind_profiles):
        problems.append("kind_priority_coverage")
    if observed_priorities != sorted(observed_priorities, reverse=True):
        problems.append("kind_priority_order")
    if forward_kinds != reverse_kinds:
        problems.append("kind_priority_permutation")
    problems.extend(
        same_source_priority_problems(
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
    )
    return problems


def same_source_priority_problems(
    *,
    candidates: object,
    candidate_id: str,
    target: str,
    policy: object,
) -> list[str]:
    """Prove higher-priority emergency memory wins one shared source budget."""

    emergency = sorted(
        (
            (profile.priority, kind)
            for kind, profile in policy.kind_profiles.items()
            if kind in {"alarm", "cautionary"}
        ),
        reverse=True,
    )
    if not emergency:
        return []
    high_priority, high_kind = emergency[0]
    lower = sorted(
        (
            (profile.priority, kind)
            for kind, profile in policy.kind_profiles.items()
            if profile.priority < high_priority
        ),
        key=lambda item: (item[0], item[1]),
    )
    if not lower:
        return []
    _, low_kind = lower[0]
    allowance = min(
        float(policy.max_strength),
        float(policy.per_source_cap),
        float(policy.per_round_deposit_cap),
    )
    consumed = float(policy.per_source_cap) - allowance
    # A source-only constraint can be isolated when its pre-consumption also
    # fits the declared round budget. Other cap relationships are already
    # exercised by the lifecycle budget checks.
    if (
        allowance <= 0
        or consumed < 0
        or float(policy.per_source_cap) > float(policy.per_round_deposit_cap)
    ):
        return []
    source_id = "agent:conformance:shared-priority"
    budget = PheromoneBudgetState(
        round_cap=float(policy.per_round_deposit_cap),
        per_source_cap=float(policy.per_source_cap),
        round_used=consumed,
        source_used={source_id: consumed} if consumed else {},
    )
    high = replace(
        profile_trails(
            candidate_id,
            target=target,
            kind=high_kind,
            subject_type="candidate",
            strength=allowance,
            source_count=1,
        )[0],
        source_id=source_id,
    )
    low = replace(
        profile_trails(
            candidate_id,
            target=target,
            kind=low_kind,
            subject_type="candidate",
            strength=allowance,
            source_count=1,
        )[0],
        source_id=source_id,
    )
    forward = deposit_pheromone_trails(
        [low, high],
        policy,
        candidate_set=candidates,
        target=target,
        budget_state=budget,
    )
    reverse = deposit_pheromone_trails(
        [high, low],
        policy,
        candidate_set=candidates,
        target=target,
        budget_state=budget,
    )
    forward_applied = {
        record.kind: record.applied_strength for record in forward.records
    }
    reverse_applied = {
        record.kind: record.applied_strength for record in reverse.records
    }
    problems: list[str] = []
    if not isclose(forward_applied.get(high_kind, -1.0), allowance, abs_tol=1e-9):
        problems.append("kind_priority_shared_source_high")
    if not isclose(forward_applied.get(low_kind, -1.0), 0.0, abs_tol=1e-9):
        problems.append("kind_priority_shared_source_low")
    if forward_applied != reverse_applied:
        problems.append("kind_priority_shared_source_permutation")
    return problems


def kind_suppression_problems(
    *,
    candidates: object,
    candidate_id: str,
    target: str,
    policy: object,
) -> list[str]:
    positive_profile = policy.kind_profiles.get("positive")
    positive_subjects = (
        positive_profile.scored_subject_types or policy.scored_subject_types
        if positive_profile is not None
        else policy.scored_subject_types
    )
    if not positive_subjects:
        return []
    positive_subject = positive_subjects[0]
    positive = profile_trails(
        candidate_id,
        target=target,
        kind="positive",
        subject_type=positive_subject,
        strength=float(policy.max_strength),
        source_count=policy.min_source_diversity,
    )
    problems: list[str] = []
    for kind, profile in sorted(policy.kind_profiles.items()):
        if kind not in {"alarm", "cautionary"}:
            continue
        subjects = profile.scored_subject_types or policy.scored_subject_types
        if not subjects:
            continue
        pressure = profile_trails(
            candidate_id,
            target=target,
            kind=kind,
            subject_type=subjects[0],
            strength=float(policy.max_strength),
            source_count=policy.min_source_diversity,
        )
        pressure_result = score_pheromone_trails_result(
            candidate_set=candidates,
            policy=policy,
            trails=pressure,
        )
        pressure_value = abs(
            float(pressure_result.kind_breakdown[candidate_id].get(kind, 0.0))
        )
        combined = score_pheromone_trails_result(
            candidate_set=candidates,
            policy=policy,
            trails=[*positive, *pressure],
        )
        suppression = float(
            combined.kind_breakdown[candidate_id].get("cautionary_suppression", 0.0)
        )
        threshold_reached = (
            pressure_value > 0
            and pressure_value >= float(policy.cautionary_override_threshold)
        )
        if profile.can_suppress_positive and threshold_reached:
            positive_value = float(
                combined.kind_breakdown[candidate_id].get("positive", 0.0)
            )
            if positive_value > 0 and not isclose(
                suppression,
                -positive_value,
                abs_tol=1e-9,
            ):
                problems.append(f"kind_suppression:{kind}")
        elif not isclose(suppression, 0.0, abs_tol=1e-9):
            problems.append(f"kind_suppression_disabled:{kind}")
    return problems


def kind_response_can_score(kind: str, strength: float, weight: float, policy: object) -> bool:
    return kind_response_magnitude(kind, strength, weight, policy) > 0


def kind_response_magnitude(kind: str, strength: float, weight: float, policy: object) -> float:
    if kind == "stale" or weight <= 0 or strength <= 0:
        return 0.0
    if kind == "novelty" and not policy.exploration_enabled:
        return 0.0
    profile = policy.kind_profiles[kind]
    raw_magnitude = strength * weight
    if profile.response_model == "threshold":
        return raw_magnitude if raw_magnitude >= policy.activation_threshold else 0.0
    if profile.response_model == "saturating":
        if policy.saturation_threshold <= 0:
            return 0.0
        return (
            raw_magnitude * float(policy.saturation_threshold)
        ) / (raw_magnitude + float(policy.saturation_threshold))
    return raw_magnitude


def profile_trails(
    candidate_id: str,
    *,
    target: str,
    kind: str,
    subject_type: str,
    strength: float,
    source_count: int,
) -> list[PheromoneTrail]:
    subject_id = candidate_id if subject_type == "candidate" else f"{subject_type}:conformance:{kind}"
    return [
        PheromoneTrail(
            candidate_id=candidate_id,
            strength=strength,
            subject_type=subject_type,
            subject_id=subject_id,
            target=target,
            kind=kind,
            source_id=f"agent:conformance:{kind}:{index}",
            evidence_id=f"evidence:conformance:{kind}:{index}",
            provenance="driver:conformance",
            trace_event_id=f"trace:conformance:{kind}:{subject_type}:{index}",
        )
        for index in range(source_count)
    ]
