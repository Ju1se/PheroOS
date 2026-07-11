from __future__ import annotations

from dataclasses import replace

from pheroos.conformance.checks._manifest import active_target, candidate_set, exercise_candidate_id
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    OutputContract,
    PheromonePolicy,
    PheromoneTrail,
    QuorumDecision,
    StopResolution,
    commit_candidate,
    deposit_pheromone_trails,
    evaporate_trails,
    evaluate_collective_decision,
    output_authorized,
    pheromone_policy_from_collective,
    score_pheromone_trails,
    validate_pheromone_trail,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import (
    CapabilityManifest,
    CollectiveDecisionPolicy,
    collective_fallback_id,
)


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None or not policy.pheromone_enabled:
        return CheckResult("pheromone_behavior", True)

    try:
        return check_enabled(manifest, policy)
    except Exception as exc:  # total-function boundary for direct check consumers
        return CheckResult("pheromone_behavior", False, fixture_error(exc))


def check_enabled(
    manifest: CapabilityManifest,
    policy: CollectiveDecisionPolicy,
) -> CheckResult:
    problems: list[str] = []
    target = active_target(manifest)
    candidates = candidate_set(manifest)
    fallback_id = collective_fallback_id(manifest.protocol)
    try:
        fallback = candidates.require_declared_for_target(fallback_id, target)
    except GovernanceError:
        return CheckResult("pheromone_behavior", False, "safe_fallback")
    if not fallback.safe_fallback:
        return CheckResult("pheromone_behavior", False, "safe_fallback")

    candidate_id = exercise_candidate_id(manifest)
    if candidate_id is None:
        return CheckResult("pheromone_behavior", False, "active_target_candidates")
    pheromone_policy = pheromone_policy_from_collective(policy)

    if pheromone_policy.require_provenance and not rejects_missing_provenance(
        candidate_id, target, pheromone_policy, candidates
    ):
        problems.append("missing_provenance")
    if pheromone_policy.require_trace and not rejects_missing_trace(
        candidate_id, target, pheromone_policy, candidates
    ):
        problems.append("missing_trace")
    if not clips_pheromone(candidate_id, target, pheromone_policy, candidates):
        problems.append("clip")
    if not non_candidate_pheromone_does_not_score(target, candidates, pheromone_policy):
        problems.append("non_candidate_no_score")
    if not stale_pheromone_does_not_score(candidate_id, target, candidates, pheromone_policy):
        problems.append("stale_no_score")
    if not empty_trail_cannot_satisfy_source_diversity(
        candidate_id,
        target,
        candidates,
        pheromone_policy,
    ):
        problems.append("empty_source_diversity")
    if not high_pheromone_without_scouts_falls_back(
        candidate_id,
        fallback_id,
        target,
        candidates,
        policy,
    ):
        problems.append("no_direct_commit")
    if not pheromone_is_not_evidence(candidate_id, target, candidates):
        problems.append("not_evidence")
    if not pheromone_score_cannot_authorize_output(candidate_id, target, candidates):
        problems.append("no_direct_output")

    return CheckResult("pheromone_behavior", not problems, ", ".join(problems))


def traceable_candidate_pheromone(
    candidate_id: str,
    target: str,
    strength: float = 1.0,
    *,
    kind: str = "positive",
    source_suffix: str = "default",
) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type="candidate",
        subject_id=candidate_id,
        target=target,
        kind=kind,
        source_id=f"agent:conformance:{source_suffix}",
        evidence_id="evidence:conformance",
        provenance="driver:conformance",
        trace_event_id=f"trace:pheromone:conformance:{source_suffix}",
    )


def rejects_missing_provenance(
    candidate_id: str,
    target: str,
    policy: PheromonePolicy,
    candidate_set: CandidateSet,
) -> bool:
    try:
        validate_pheromone_trail(
            PheromoneTrail(
                candidate_id,
                manifest_trail_strength(policy),
                target=target,
                trace_event_id="trace:pheromone",
            ),
            policy,
            candidate_set=candidate_set,
        )
    except GovernanceError:
        return True
    return False


def rejects_missing_trace(
    candidate_id: str,
    target: str,
    policy: PheromonePolicy,
    candidate_set: CandidateSet,
) -> bool:
    try:
        validate_pheromone_trail(
            PheromoneTrail(
                candidate_id,
                manifest_trail_strength(policy),
                target=target,
                provenance="driver:conformance",
            ),
            policy,
            candidate_set=candidate_set,
        )
    except GovernanceError:
        return True
    return False


def clips_pheromone(
    candidate_id: str,
    target: str,
    policy: PheromonePolicy,
    candidate_set: CandidateSet,
) -> bool:
    requested = max(policy.max_strength, policy.per_round_deposit_cap, policy.per_source_cap) + 1
    result = deposit_pheromone_trails(
        [traceable_candidate_pheromone(candidate_id, target, strength=requested)],
        policy,
        candidate_set=candidate_set,
        target=target,
    )
    expected = min(policy.max_strength, policy.per_round_deposit_cap, policy.per_source_cap, requested)
    if expected < policy.min_strength:
        expected = 0.0
    actual = result.trails[0].strength if result.trails else 0.0
    return actual == expected


def non_candidate_pheromone_does_not_score(
    target: str,
    candidate_set: CandidateSet,
    policy: PheromonePolicy,
) -> bool:
    baseline = score_pheromone_trails(candidate_set=candidate_set, policy=policy, trails=[])
    scores = score_pheromone_trails(
        candidate_set=candidate_set,
        policy=policy,
        trails=[
            PheromoneTrail(
                "",
                manifest_trail_strength(policy),
                target=target,
                subject_type="route",
                subject_id="route:conformance",
                kind="positive",
                source_id="agent:conformance",
                evidence_id="evidence:conformance",
                provenance="driver:conformance",
                trace_event_id="trace:pheromone:route",
            )
        ],
    )
    return scores == baseline


def stale_pheromone_does_not_score(
    candidate_id: str,
    target: str,
    candidate_set: CandidateSet,
    policy: PheromonePolicy,
) -> bool:
    expired = evaporate_trails(
        [
            replace(
                traceable_candidate_pheromone(
                    candidate_id,
                    target,
                    strength=manifest_trail_strength(policy),
                ),
                ttl_steps=1,
            )
        ],
        policy,
        current_step=1,
    )[0]
    baseline = score_pheromone_trails(candidate_set=candidate_set, policy=policy, trails=[])
    scores = score_pheromone_trails(candidate_set=candidate_set, policy=policy, trails=[expired])
    return expired.kind == "stale" and scores == baseline


def empty_trail_cannot_satisfy_source_diversity(
    candidate_id: str,
    target: str,
    candidate_set: CandidateSet,
    policy: PheromonePolicy,
) -> bool:
    """Prove an empty source cannot unlock otherwise under-diverse memory."""

    positive_strength = manifest_trail_strength(policy)
    contributing = [
        traceable_candidate_pheromone(
            candidate_id,
            target,
            strength=positive_strength,
            source_suffix=f"diversity:{index}",
        )
        for index in range(max(0, policy.min_source_diversity - 1))
    ]
    empty = traceable_candidate_pheromone(
        candidate_id,
        target,
        strength=0.0,
        source_suffix="diversity:empty",
    )
    try:
        validate_pheromone_trail(empty, policy, candidate_set=candidate_set)
    except GovernanceError:
        # A positive minimum strength already rejects empty active memory.
        return policy.min_strength > 0
    baseline = score_pheromone_trails(
        candidate_set=candidate_set,
        policy=policy,
        trails=[],
    )
    observed = score_pheromone_trails(
        candidate_set=candidate_set,
        policy=policy,
        trails=[*contributing, empty],
    )
    return observed == baseline


def high_pheromone_without_scouts_falls_back(
    candidate_id: str,
    fallback_id: str,
    target: str,
    candidate_set: CandidateSet,
    policy: object,
) -> bool:
    trails = [
        traceable_candidate_pheromone(
            candidate_id,
            target,
            strength=manifest_trail_strength(
                pheromone_policy_from_collective(policy),
            ),
            source_suffix=str(index),
        )
        for index in range(policy.pheromone_min_source_diversity)
    ]
    decision = evaluate_collective_decision(
        candidate_set=candidate_set,
        policy=replace(
            policy,
            pheromone_enabled=True,
            pheromone_require_provenance=True,
            pheromone_require_trace=True,
            min_independent_scouts=1,
            quorum_threshold=1,
            fallback_candidate="",
        ),
        target=target,
        scout_reports=[],
        pheromone_trails=trails,
        fallback_candidate_id=fallback_id,
    )
    return decision.reason == "safe_collective_fallback" and decision.candidate_id == fallback_id


def pheromone_is_not_evidence(
    candidate_id: str,
    target: str,
    candidates: CandidateSet,
) -> bool:
    committed = commit_candidate(
        candidate_set=candidates,
        candidate_id=candidate_id,
        target=target,
    )
    missing_evidence = EvidenceGraph(
        [EvidenceNode(id="evidence:pheromone", content="pheromone is not evidence", provenance="")]
    )
    return not output_authorized(
        OutputContract(),
        committed,
        missing_evidence,
        [StopResolution(target=target, action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates,
    )


def manifest_trail_strength(policy: PheromonePolicy) -> float:
    """Use a valid active-trail strength bounded by every declared deposit cap."""

    return min(
        float(policy.max_strength),
        float(policy.per_source_cap),
        float(policy.per_round_deposit_cap),
    )


def fixture_error(exc: Exception) -> str:
    detail = str(exc).strip()
    suffix = f":{detail}" if detail else ""
    return f"fixture_error:{type(exc).__name__}{suffix}"


def pheromone_score_cannot_authorize_output(
    candidate_id: str,
    target: str,
    candidates: CandidateSet,
) -> bool:
    uncommitted = QuorumDecision(
        target=target,
        candidate_id=candidate_id,
        committed=False,
        reason="pheromone_score_only",
    )
    evidence = EvidenceGraph(
        [EvidenceNode(id="evidence:real", content="governed evidence", provenance="driver:real")]
    )
    return not output_authorized(
        OutputContract(),
        uncommitted,
        evidence,
        [StopResolution(target=target, action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates,
    )
