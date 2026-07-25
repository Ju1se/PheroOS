from __future__ import annotations

from math import isclose

from pheroos.conformance.checks._manifest import (
    active_target,
    candidate_set,
    exercise_candidate_id,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    CandidateSet,
    PheromonePolicy,
    PheromoneTrail,
    pheromone_policy_from_collective,
    score_pheromone_trails,
    score_pheromone_trails_result,
    validate_pheromone_trail,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import (
    CapabilityManifest,
    PheromoneKindProfile,
    SUPPORTED_PHEROMONE_KINDS,
    effective_pheromone_scored_subject_types,
    has_hybrid_pheromone_features,
)


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(policy):
        return CheckResult("pheromone_subject_scoring", True)
    if policy is None:
        return CheckResult("pheromone_subject_scoring", True)

    try:
        return check_hybrid(manifest)
    except Exception as exc:  # total-function boundary for direct check consumers
        return CheckResult("pheromone_subject_scoring", False, fixture_error(exc))


def check_hybrid(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return CheckResult("pheromone_subject_scoring", False, "collective_policy")
    candidates = candidate_set(manifest)
    candidate_id = exercise_candidate_id(manifest)
    if candidate_id is None:
        return CheckResult(
            "pheromone_subject_scoring", False, "active_target_candidates"
        )
    target = active_target(manifest)
    pheromone_policy = pheromone_policy_from_collective(policy)
    baseline = score_pheromone_trails(
        candidate_set=candidates, policy=pheromone_policy, trails=[]
    )
    declared_subjects = list(pheromone_policy.scored_subject_types)
    subject_scores = _collect_subject_scores(
        declared_subjects=declared_subjects,
        candidates=candidates,
        candidate_id=candidate_id,
        target=target,
        policy=pheromone_policy,
    )
    evidence_score = score_pheromone_trails(
        candidate_set=candidates,
        policy=pheromone_policy,
        trails=manifest_trails(
            candidate_id=candidate_id,
            subject_type="evidence",
            subject_id="evidence:conformance",
            strength=manifest_trail_strength(pheromone_policy),
            target=target,
            kind="positive",
            diversity=pheromone_policy.min_source_diversity,
        ),
    )[candidate_id]
    rejects_undeclared = _rejects_undeclared_candidate_binding(
        candidates=candidates,
        target=target,
        policy=pheromone_policy,
    )

    competitive = (
        pheromone_policy.response_model == "competitive"
        or pheromone_policy.competition_mode == "normalize"
    )
    problems = _subject_score_problems(
        subject_scores,
        competitive_singleton=competitive and len(candidates.candidates) == 1,
    )
    if evidence_score != baseline[candidate_id]:
        problems.append("evidence_subject_scored")
    if not rejects_undeclared:
        problems.append("undeclared_candidate_binding")
    return CheckResult("pheromone_subject_scoring", not problems, ", ".join(problems))


def _collect_subject_scores(
    *,
    declared_subjects: list[str],
    candidates: CandidateSet,
    candidate_id: str,
    target: str,
    policy: PheromonePolicy,
) -> dict[str, tuple[float, bool]]:
    return {
        subject_type: _score_declared_subject(
            subject_type=subject_type,
            candidates=candidates,
            candidate_id=candidate_id,
            target=target,
            policy=policy,
        )
        for subject_type in declared_subjects
    }


def _score_declared_subject(
    *,
    subject_type: str,
    candidates: CandidateSet,
    candidate_id: str,
    target: str,
    policy: PheromonePolicy,
) -> tuple[float, bool]:
    scoring_kind = _scoring_kind_for_subject(subject_type, policy)
    subject_id = (
        candidate_id if subject_type == "candidate" else f"{subject_type}:conformance"
    )
    trails = manifest_trails(
        candidate_id=candidate_id,
        subject_type=subject_type,
        subject_id=subject_id,
        strength=manifest_trail_strength(policy),
        target=target,
        kind=scoring_kind,
        diversity=policy.min_source_diversity,
    )
    result = score_pheromone_trails_result(
        candidate_set=candidates,
        policy=policy,
        trails=trails,
    )
    if subject_type == "candidate":
        contribution = float(result.kind_breakdown[candidate_id].get(scoring_kind, 0.0))
    else:
        contribution = float(
            result.subject_breakdown[candidate_id].get(subject_type, 0.0)
        )
    profile = policy.kind_profiles.get(scoring_kind)
    active = bool(
        kind_response_can_score(scoring_kind, profile, policy)
        and subject_type
        in effective_pheromone_scored_subject_types(
            scoring_kind,
            profile,
            policy.scored_subject_types,
        )
    )
    return contribution, active


def _scoring_kind_for_subject(subject_type: str, policy: PheromonePolicy) -> str:
    scoring_kind = next(
        (
            kind
            for kind in sorted(
                set(policy.kind_profiles) | (set(SUPPORTED_PHEROMONE_KINDS) - {"stale"})
            )
            for profile in (policy.kind_profiles.get(kind),)
            if kind_response_can_score(kind, profile, policy)
            and subject_type
            in effective_pheromone_scored_subject_types(
                kind,
                profile,
                policy.scored_subject_types,
            )
        ),
        "",
    )
    if scoring_kind:
        return scoring_kind
    # A globally declared subject is allowed to have no active kind under this
    # exact policy. Exercise one declared binding and prove it remains no-score.
    return no_score_probe_kind(subject_type, policy)


def _subject_score_problems(
    subject_scores: dict[str, tuple[float, bool]],
    *,
    competitive_singleton: bool,
) -> list[str]:
    problems: list[str] = []
    for subject_type, (contribution, response_active) in subject_scores.items():
        if (
            response_active
            and isclose(contribution, 0.0, abs_tol=1e-12)
            and not competitive_singleton
        ):
            problems.append(f"declared_{subject_type}_subject_no_score")
        if not response_active and not isclose(
            contribution,
            0.0,
            abs_tol=1e-12,
        ):
            problems.append(f"declared_{subject_type}_unexpected_score")
    return problems


def _rejects_undeclared_candidate_binding(
    *,
    candidates: CandidateSet,
    target: str,
    policy: PheromonePolicy,
) -> bool:
    try:
        validate_pheromone_trail(
            trail(
                candidate_id="candidate:missing",
                subject_type="route",
                subject_id="route:missing",
                strength=manifest_trail_strength(policy),
                target=target,
                source_suffix="missing",
            ),
            policy,
            candidate_set=candidates,
        )
    except GovernanceError:
        return True
    return False


def manifest_trails(
    *,
    candidate_id: str,
    subject_type: str,
    subject_id: str,
    strength: float,
    target: str,
    kind: str,
    diversity: int,
) -> list[PheromoneTrail]:
    return [
        trail(
            candidate_id=candidate_id,
            subject_type=subject_type,
            subject_id=subject_id,
            strength=strength,
            target=target,
            kind=kind,
            source_suffix=str(index),
        )
        for index in range(diversity)
    ]


def manifest_trail_strength(policy: PheromonePolicy) -> float:
    """Use the strongest valid active trail to exercise declared response thresholds."""

    return float(policy.max_strength)


def kind_response_can_score(
    kind: str,
    profile: PheromoneKindProfile | None,
    policy: PheromonePolicy,
) -> bool:
    if not effective_pheromone_scored_subject_types(
        kind,
        profile,
        policy.scored_subject_types,
    ):
        return False
    weight = (
        float(profile.weight)
        if profile is not None
        else legacy_kind_weight(kind, policy)
    )
    if kind == "stale" or weight <= 0:
        return False
    if kind == "novelty" and not policy.exploration_enabled:
        return False
    raw_magnitude = float(policy.max_strength) * weight
    if raw_magnitude <= 0:
        return False
    response_model = (
        profile.response_model if profile is not None else policy.response_model
    )
    if response_model == "threshold":
        return raw_magnitude >= float(policy.activation_threshold)
    if response_model == "saturating":
        return float(policy.saturation_threshold) > 0
    return True


def legacy_kind_weight(kind: str, policy: PheromonePolicy) -> float:
    if kind == "positive":
        return float(policy.positive_weight)
    if kind == "negative":
        return float(policy.negative_weight)
    if kind in {"cautionary", "alarm"}:
        return float(policy.cautionary_weight)
    if kind == "novelty":
        return float(policy.novelty_weight)
    return 0.0


def no_score_probe_kind(subject_type: str, policy: PheromonePolicy) -> str:
    return next(
        (
            kind
            for kind, profile in sorted(policy.kind_profiles.items())
            if kind != "stale"
            and subject_type
            in effective_pheromone_scored_subject_types(
                kind,
                profile,
                policy.scored_subject_types,
            )
        ),
        "positive",
    )


def fixture_error(exc: Exception) -> str:
    detail = str(exc).strip()
    suffix = f":{detail}" if detail else ""
    return f"fixture_error:{type(exc).__name__}{suffix}"


def trail(
    candidate_id: str,
    subject_type: str,
    subject_id: str,
    strength: float,
    *,
    target: str,
    kind: str = "positive",
    source_suffix: str = "default",
) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type=subject_type,
        subject_id=subject_id,
        target=target,
        kind=kind,
        source_id=f"agent:conformance:{source_suffix}",
        evidence_id="evidence:conformance",
        provenance="driver:conformance",
        trace_event_id=f"trace:conformance:{subject_id}:{source_suffix}",
    )
