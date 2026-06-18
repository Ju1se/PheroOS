from __future__ import annotations

from dataclasses import replace

from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    OutputContract,
    PheromonePolicy,
    PheromoneTrail,
    QuorumDecision,
    deposit_pheromone,
    evaporate_trails,
    evaluate_collective_decision,
    output_authorized,
    pheromone_policy_from_collective,
    score_pheromone_trails,
    validate_pheromone_trail,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import CapabilityManifest, collective_fallback_id


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None or not policy.pheromone_enabled:
        return CheckResult("pheromone_behavior", True)

    problems: list[str] = []
    target = manifest.protocol.quorum_policy.target
    candidate_set = CandidateSet(
        [
            Candidate(id=candidate.id, target=candidate.target, safe_fallback=candidate.safe_fallback)
            for candidate in manifest.protocol.candidates
        ]
    )
    fallback_id = collective_fallback_id(manifest.protocol)
    try:
        fallback = candidate_set.require_declared(fallback_id)
    except GovernanceError:
        return CheckResult("pheromone_behavior", False, "safe_fallback")
    if not fallback.safe_fallback:
        return CheckResult("pheromone_behavior", False, "safe_fallback")

    candidate_id = next(
        (candidate.id for candidate in manifest.protocol.candidates if candidate.id != fallback_id),
        fallback_id,
    )
    pheromone_policy = replace(
        pheromone_policy_from_collective(policy),
        enabled=True,
        min_strength=0.0,
        max_strength=10.0,
        per_round_deposit_cap=4.0,
        per_source_cap=100.0,
        min_source_diversity=1,
        require_provenance=True,
        require_trace=True,
    )

    if not rejects_missing_provenance(candidate_id, pheromone_policy, candidate_set):
        problems.append("missing_provenance")
    if not rejects_missing_trace(candidate_id, pheromone_policy, candidate_set):
        problems.append("missing_trace")
    if not clips_pheromone(candidate_id, pheromone_policy, candidate_set):
        problems.append("clip")
    if not non_candidate_pheromone_does_not_score(candidate_set, pheromone_policy):
        problems.append("non_candidate_no_score")
    if not stale_pheromone_does_not_score(candidate_id, candidate_set, pheromone_policy):
        problems.append("stale_no_score")
    if not high_pheromone_without_scouts_falls_back(
        candidate_id,
        fallback_id,
        target,
        candidate_set,
        policy,
    ):
        problems.append("no_direct_commit")
    if not pheromone_is_not_evidence(candidate_id, target):
        problems.append("not_evidence")
    if not pheromone_score_cannot_authorize_output(candidate_id, target):
        problems.append("no_direct_output")

    return CheckResult("pheromone_behavior", not problems, ", ".join(problems))


def traceable_candidate_pheromone(candidate_id: str, strength: float = 1.0, *, kind: str = "positive") -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type="candidate",
        subject_id=candidate_id,
        target="decision:conformance",
        kind=kind,
        source_id="agent:conformance",
        evidence_id="evidence:conformance",
        provenance="driver:conformance",
        trace_event_id="trace:pheromone:conformance",
    )


def rejects_missing_provenance(
    candidate_id: str,
    policy: PheromonePolicy,
    candidate_set: CandidateSet,
) -> bool:
    try:
        validate_pheromone_trail(
            PheromoneTrail(candidate_id, 1, trace_event_id="trace:pheromone"),
            policy,
            candidate_set=candidate_set,
        )
    except GovernanceError:
        return True
    return False


def rejects_missing_trace(candidate_id: str, policy: PheromonePolicy, candidate_set: CandidateSet) -> bool:
    try:
        validate_pheromone_trail(
            PheromoneTrail(candidate_id, 1, provenance="driver:conformance"),
            policy,
            candidate_set=candidate_set,
        )
    except GovernanceError:
        return True
    return False


def clips_pheromone(candidate_id: str, policy: PheromonePolicy, candidate_set: CandidateSet) -> bool:
    deposited = deposit_pheromone(
        traceable_candidate_pheromone(candidate_id, strength=9),
        policy,
        candidate_set=candidate_set,
    )
    return deposited.strength == 4.0


def non_candidate_pheromone_does_not_score(candidate_set: CandidateSet, policy: PheromonePolicy) -> bool:
    scores = score_pheromone_trails(
        candidate_set=candidate_set,
        policy=policy,
        trails=[
            PheromoneTrail(
                "",
                3,
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
    return all(score == 0.0 for score in scores.values())


def stale_pheromone_does_not_score(candidate_id: str, candidate_set: CandidateSet, policy: PheromonePolicy) -> bool:
    expired = evaporate_trails(
        [replace(traceable_candidate_pheromone(candidate_id, strength=5), ttl_steps=1)],
        policy,
        current_step=1,
    )[0]
    scores = score_pheromone_trails(candidate_set=candidate_set, policy=policy, trails=[expired])
    return expired.kind == "stale" and all(score == 0.0 for score in scores.values())


def high_pheromone_without_scouts_falls_back(
    candidate_id: str,
    fallback_id: str,
    target: str,
    candidate_set: CandidateSet,
    policy: object,
) -> bool:
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
        pheromone_trails=[traceable_candidate_pheromone(candidate_id, strength=10)],
        fallback_candidate_id=fallback_id,
    )
    return decision.reason == "safe_collective_fallback" and decision.candidate_id == fallback_id


def pheromone_is_not_evidence(candidate_id: str, target: str) -> bool:
    committed = QuorumDecision(
        target=target,
        candidate_id=candidate_id,
        committed=True,
        reason="declared_candidate_committed",
    )
    missing_evidence = EvidenceGraph(
        [EvidenceNode(id="evidence:pheromone", content="pheromone is not evidence", provenance="")]
    )
    return not output_authorized(
        OutputContract(),
        committed,
        missing_evidence,
        [],
        publication_permission=True,
    )


def pheromone_score_cannot_authorize_output(candidate_id: str, target: str) -> bool:
    uncommitted = QuorumDecision(
        target=target,
        candidate_id=candidate_id,
        committed=False,
        reason="pheromone_score_only",
    )
    missing_evidence = EvidenceGraph(
        [EvidenceNode(id="evidence:pheromone", content="pheromone is not evidence", provenance="")]
    )
    return not output_authorized(
        OutputContract(),
        uncommitted,
        missing_evidence,
        [],
        publication_permission=True,
    )
