from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.conformance.checks._manifest import (
    active_target,
    candidate_set,
    exercise_candidate_id,
)
from pheroos.governance import (
    CandidateSet,
    PheromoneFeedback,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneSubject,
    PheromoneTrail,
    pheromone_policy_from_collective,
    reinforce_pheromone_trails,
    validate_pheromone_feedback,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import CapabilityManifest, has_hybrid_pheromone_features


def check(manifest: CapabilityManifest) -> CheckResult:
    if not has_hybrid_pheromone_features(manifest.protocol.collective_decision_policy):
        return CheckResult("pheromone_reinforcement", True)
    candidates = candidate_set(manifest)
    candidate_id = exercise_candidate_id(manifest)
    if candidate_id is None:
        return CheckResult(
            "pheromone_reinforcement",
            False,
            "active_target_candidates",
        )
    target = active_target(manifest)
    collective_policy = manifest.protocol.collective_decision_policy
    if collective_policy is None:
        return CheckResult("pheromone_reinforcement", False, "collective_policy")
    policy = pheromone_policy_from_collective(collective_policy)
    neighborhood = _feedback_neighborhood(candidate_id, target)
    probe_strength = manifest_feedback_strength(policy)
    feedback = [
        item(
            candidate_id,
            target=target,
            outcome="success",
            delta=probe_strength,
            trace="trace:success",
        ),
        item(
            candidate_id,
            target=target,
            outcome="congested",
            delta=probe_strength,
            trace="trace:congested",
        ),
    ]
    trails = reinforce_pheromone_trails(
        [],
        feedback,
        policy,
        candidate_set=candidates,
        target=target,
        neighborhood=neighborhood,
    )
    isolated = reinforce_pheromone_trails(
        [],
        [
            item(
                candidate_id,
                target=target,
                outcome="congested",
                delta=probe_strength,
                trace="trace:isolated-congested",
            )
        ],
        policy,
        candidate_set=candidates,
        target=target,
        neighborhood=neighborhood,
    )
    rejects_missing_lineage = _feedback_rejected(
        PheromoneFeedback(
            source_id="agent:bad",
            subject_type="route",
            subject_id="route:bad",
            candidate_id=candidate_id,
            target=target,
            outcome="success",
            strength_delta=1,
        ),
        policy,
        candidates,
        target=target,
    )
    problems = _reinforcement_result_problems(
        feedback=feedback,
        trails=trails,
        isolated=isolated,
        probe_strength=probe_strength,
        policy=policy,
        candidates=candidates,
        target=target,
        neighborhood=neighborhood,
    )
    problems.extend(
        _feedback_contract_problems(
            candidate_id=candidate_id,
            target=target,
            probe_strength=probe_strength,
            policy=policy,
            candidates=candidates,
            neighborhood=neighborhood,
            rejects_missing_lineage=rejects_missing_lineage,
        )
    )
    return CheckResult("pheromone_reinforcement", not problems, ", ".join(problems))


def _feedback_neighborhood(candidate_id: str, target: str) -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "route",
                "route:conformance",
                candidate_id=candidate_id,
                target=target,
            )
        ]
    )


def _reinforcement_result_problems(
    *,
    feedback: list[PheromoneFeedback],
    trails: list[PheromoneTrail],
    isolated: list[PheromoneTrail],
    probe_strength: float,
    policy: PheromonePolicy,
    candidates: CandidateSet,
    target: str,
    neighborhood: PheromoneNeighborhood,
) -> list[str]:
    kinds = {trail.kind: trail.strength for trail in trails}
    problems: list[str] = []
    requested_total = 2 * min(probe_strength, policy.max_strength)
    applied_total = sum(kinds.values())
    if applied_total > min(
        requested_total,
        policy.per_round_deposit_cap,
        policy.per_source_cap,
    ):
        problems.append("round_cap")
    reversed_trails = reinforce_pheromone_trails(
        [],
        list(reversed(feedback)),
        policy,
        candidate_set=candidates,
        target=target,
        neighborhood=neighborhood,
    )
    if {(trail.kind, trail.strength) for trail in reversed_trails} != {
        (trail.kind, trail.strength) for trail in trails
    }:
        problems.append("permutation_sensitive")
    if min(
        policy.per_round_deposit_cap,
        policy.per_source_cap,
        policy.max_strength,
    ) > 0 and not any(trail.kind == "cautionary" for trail in isolated):
        problems.append("congested_kind")
    return problems


def _feedback_contract_problems(
    *,
    candidate_id: str,
    target: str,
    probe_strength: float,
    policy: PheromonePolicy,
    candidates: CandidateSet,
    neighborhood: PheromoneNeighborhood,
    rejects_missing_lineage: bool,
) -> list[str]:
    rejects_wrong_target = _feedback_rejected(
        PheromoneFeedback(
            source_id="agent:bad",
            subject_type="route",
            subject_id="route:bad",
            candidate_id=candidate_id,
            target="decision:wrong",
            outcome="success",
            strength_delta=1,
            evidence_id="evidence:conformance",
            provenance="driver:conformance",
            trace_event_id="trace:wrong-target",
        ),
        policy,
        candidates,
        target=target,
    )
    rejects_missing_source = _feedback_rejected(
        PheromoneFeedback(
            source_id="",
            subject_type="route",
            subject_id="route:bad",
            candidate_id=candidate_id,
            target=target,
            outcome="success",
            strength_delta=1,
            evidence_id="evidence:conformance",
            provenance="driver:conformance",
            trace_event_id="trace:missing-source",
        ),
        policy,
        candidates,
        target=target,
    )
    rejects_unbound_candidate_subject = _feedback_rejected(
        PheromoneFeedback(
            source_id="agent:bad",
            subject_type="candidate",
            subject_id=candidate_id,
            candidate_id="",
            target=target,
            outcome="success",
            strength_delta=1,
            evidence_id="evidence:conformance",
            provenance="driver:conformance",
            trace_event_id="trace:missing-candidate-binding",
        ),
        policy,
        candidates,
        target=target,
    )
    rejects_negative_delta = _feedback_rejected(
        PheromoneFeedback(
            source_id="agent:bad",
            subject_type="route",
            subject_id="route:bad",
            candidate_id=candidate_id,
            target=target,
            outcome="success",
            strength_delta=-1,
            evidence_id="evidence:conformance",
            provenance="driver:conformance",
            trace_event_id="trace:negative-delta",
        ),
        policy,
        candidates,
        target=target,
    )
    rejects_wrong_subject_binding = _wrong_subject_binding_rejected(
        candidate_id=candidate_id,
        target=target,
        probe_strength=probe_strength,
        policy=policy,
        candidates=candidates,
        neighborhood=neighborhood,
    )
    rejects_undeclared_subject = _feedback_rejected(
        PheromoneFeedback(
            source_id="agent:conformance",
            subject_type="route",
            subject_id="route:undeclared",
            candidate_id=candidate_id,
            target=target,
            outcome="success",
            strength_delta=probe_strength,
            evidence_id="evidence:conformance",
            provenance="driver:conformance",
            trace_event_id="trace:undeclared-subject",
            step=1,
        ),
        policy,
        candidates,
        target=target,
        neighborhood=neighborhood,
    )
    rejection_contract = (
        (rejects_missing_lineage, "lineage_required"),
        (rejects_wrong_target, "target_required"),
        (rejects_missing_source, "source_required"),
        (rejects_unbound_candidate_subject, "candidate_binding_required"),
        (rejects_negative_delta, "negative_delta"),
        (rejects_wrong_subject_binding, "topology_candidate_binding"),
        (rejects_undeclared_subject, "topology_subject_declaration"),
    )
    return [marker for rejected, marker in rejection_contract if not rejected]


def _wrong_subject_binding_rejected(
    *,
    candidate_id: str,
    target: str,
    probe_strength: float,
    policy: PheromonePolicy,
    candidates: CandidateSet,
    neighborhood: PheromoneNeighborhood,
) -> bool:
    alternate_candidate_id = next(
        (
            candidate.id
            for candidate in candidates.candidates
            if candidate.target == target and candidate.id != candidate_id
        ),
        None,
    )
    if alternate_candidate_id is None:
        return True
    return _feedback_rejected(
        item(
            alternate_candidate_id,
            target=target,
            outcome="success",
            delta=probe_strength,
            trace="trace:wrong-subject-binding",
        ),
        policy,
        candidates,
        target=target,
        neighborhood=neighborhood,
    )


def _feedback_rejected(
    feedback: PheromoneFeedback,
    policy: PheromonePolicy,
    candidates: CandidateSet,
    *,
    target: str,
    neighborhood: PheromoneNeighborhood | None = None,
) -> bool:
    try:
        validate_pheromone_feedback(
            feedback,
            policy,
            candidate_set=candidates,
            target=target,
            neighborhood=neighborhood,
        )
    except GovernanceError:
        return True
    return False


def item(
    candidate_id: str, *, target: str, outcome: str, delta: float, trace: str
) -> PheromoneFeedback:
    return PheromoneFeedback(
        source_id="agent:conformance",
        subject_type="route",
        subject_id="route:conformance",
        candidate_id=candidate_id,
        target=target,
        outcome=outcome,
        strength_delta=delta,
        evidence_id="evidence:conformance",
        provenance="driver:conformance",
        trace_event_id=trace,
        step=1,
    )


def manifest_feedback_strength(policy: PheromonePolicy) -> float:
    return max(
        float(policy.min_strength),
        min(
            float(policy.max_strength),
            float(policy.per_source_cap),
            float(policy.per_round_deposit_cap),
        ),
    )
