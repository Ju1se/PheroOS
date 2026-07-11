from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.conformance.checks._manifest import active_target, candidate_set, exercise_candidate_id
from pheroos.governance import (
    Candidate,
    CandidateSet,
    PheromoneFeedback,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneSubject,
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
        return CheckResult("pheromone_reinforcement", False, "active_target_candidates")
    target = active_target(manifest)
    collective_policy = manifest.protocol.collective_decision_policy
    if collective_policy is None:
        return CheckResult("pheromone_reinforcement", False, "collective_policy")
    policy = pheromone_policy_from_collective(collective_policy)
    neighborhood = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "route",
                "route:conformance",
                candidate_id=candidate_id,
                target=target,
            )
        ]
    )
    probe_strength = manifest_feedback_strength(policy)
    feedback = [
        item(candidate_id, target=target, outcome="success", delta=probe_strength, trace="trace:success"),
        item(candidate_id, target=target, outcome="congested", delta=probe_strength, trace="trace:congested"),
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
    try:
        validate_pheromone_feedback(
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
            candidate_set=candidates,
            target=target,
        )
    except GovernanceError:
        rejects_missing_lineage = True
    else:
        rejects_missing_lineage = False

    kinds = {trail.kind: trail.strength for trail in trails}
    problems = []
    requested_total = 2 * min(probe_strength, policy.max_strength)
    applied_total = sum(kinds.values())
    if applied_total > min(requested_total, policy.per_round_deposit_cap, policy.per_source_cap):
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
    if min(policy.per_round_deposit_cap, policy.per_source_cap, policy.max_strength) > 0 and not any(
        trail.kind == "cautionary" for trail in isolated
    ):
        problems.append("congested_kind")
    try:
        validate_pheromone_feedback(
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
            candidate_set=candidates,
            target=target,
        )
    except GovernanceError:
        rejects_wrong_target = True
    else:
        rejects_wrong_target = False
    try:
        validate_pheromone_feedback(
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
            candidate_set=candidates,
            target=target,
        )
    except GovernanceError:
        rejects_missing_source = True
    else:
        rejects_missing_source = False
    try:
        validate_pheromone_feedback(
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
            candidate_set=candidates,
            target=target,
        )
    except GovernanceError:
        rejects_unbound_candidate_subject = True
    else:
        rejects_unbound_candidate_subject = False
    try:
        validate_pheromone_feedback(
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
            candidate_set=candidates,
            target=target,
        )
    except GovernanceError:
        rejects_negative_delta = True
    else:
        rejects_negative_delta = False
    alternate_candidate_id = next(
        (
            candidate.id
            for candidate in candidates.candidates
            if candidate.target == target and candidate.id != candidate_id
        ),
        None,
    )
    if alternate_candidate_id is None:
        rejects_wrong_subject_binding = True
    else:
        try:
            validate_pheromone_feedback(
                item(
                    alternate_candidate_id,
                    target=target,
                    outcome="success",
                    delta=probe_strength,
                    trace="trace:wrong-subject-binding",
                ),
                policy,
                candidate_set=candidates,
                target=target,
                neighborhood=neighborhood,
            )
        except GovernanceError:
            rejects_wrong_subject_binding = True
        else:
            rejects_wrong_subject_binding = False
    try:
        validate_pheromone_feedback(
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
            candidate_set=candidates,
            target=target,
            neighborhood=neighborhood,
        )
    except GovernanceError:
        rejects_undeclared_subject = True
    else:
        rejects_undeclared_subject = False
    if not rejects_missing_lineage:
        problems.append("lineage_required")
    if not rejects_wrong_target:
        problems.append("target_required")
    if not rejects_missing_source:
        problems.append("source_required")
    if not rejects_unbound_candidate_subject:
        problems.append("candidate_binding_required")
    if not rejects_negative_delta:
        problems.append("negative_delta")
    if not rejects_wrong_subject_binding:
        problems.append("topology_candidate_binding")
    if not rejects_undeclared_subject:
        problems.append("topology_subject_declaration")
    return CheckResult("pheromone_reinforcement", not problems, ", ".join(problems))


def item(candidate_id: str, *, target: str, outcome: str, delta: float, trace: str) -> PheromoneFeedback:
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
