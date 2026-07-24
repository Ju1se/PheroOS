from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    Candidate,
    CandidateSet,
    InhibitionSignal,
    PheromoneTrail,
    RecruitmentSignal,
    ScoutReport,
    AuthorityLevel,
    candidate_score_lineage,
    score_candidates,
    validate_score_breakdown,
    verify_signal_input,
)
from pheroos.governance.signal import SignalVerification
from pheroos.protocol.models import (
    CapabilityManifest,
    CollectiveDecisionPolicy,
    is_swarm_policy,
)


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if not is_swarm_policy(policy):
        return CheckResult("score_breakdown_contract", True)
    if policy is None:
        return CheckResult("score_breakdown_contract", True)

    try:
        target = manifest.protocol.quorum_policy.target
        candidate_set = CandidateSet(
            tuple(
                Candidate(candidate.id, candidate.target, candidate.safe_fallback)
                for candidate in manifest.protocol.candidates
            )
        )
        target_candidates = [
            candidate
            for candidate in manifest.protocol.candidates
            if candidate.target == target
        ]
        if not target_candidates:
            return CheckResult("score_breakdown_contract", False, "target_candidates")
        candidate_id = next(
            (
                candidate.id
                for candidate in target_candidates
                if not candidate.safe_fallback
            ),
            target_candidates[0].id,
        )
        # Signal magnitude is bounded by the manifest's collective threshold.
        # Keep the fixture inside that authority boundary even when a valid
        # protocol intentionally declares a threshold below the historical
        # conformance probe values.
        scout_support = min(2.0, float(policy.quorum_threshold))
        recruitment_strength = min(1.0, float(policy.quorum_threshold))
        inhibition_strength = min(0.5, float(policy.quorum_threshold))
        scout_verification = verification(
            target, "scout:conformance", candidate_id, "scout"
        )
        recruit_verification = verification(
            target, "recruit:conformance", candidate_id, "recruit"
        )
        inhibit_verification = verification(
            target, "inhibit:conformance", candidate_id, "inhibit"
        )
        state = score_candidates(
            candidate_set=candidate_set,
            policy=policy,
            target=target,
            scout_reports=[
                ScoutReport(
                    "scout:conformance",
                    candidate_id,
                    "evidence:conformance",
                    "driver:conformance",
                    support=scout_support,
                    target=target,
                    trace_event_id="trace:scout:conformance",
                    verification=scout_verification,
                )
            ],
            recruitment_signals=[
                RecruitmentSignal(
                    "recruit:conformance",
                    candidate_id,
                    strength=recruitment_strength,
                    target=target,
                    provenance="driver:conformance",
                    trace_event_id="trace:recruit:conformance",
                    verification=recruit_verification,
                )
            ]
            if policy.recruitment_enabled
            else [],
            inhibition_signals=[
                InhibitionSignal(
                    "inhibit:conformance",
                    candidate_id,
                    strength=inhibition_strength,
                    target=target,
                    provenance="driver:conformance",
                    trace_event_id="trace:inhibit:conformance",
                    verification=inhibit_verification,
                )
            ]
            if policy.inhibition_enabled
            else [],
            pheromone_trails=(
                manifest_pheromone_trails(
                    policy, candidate_id=candidate_id, target=target
                )
                if policy.pheromone_enabled
                else []
            ),
        )
        validate_score_breakdown(state)
        lineage = candidate_score_lineage(state, candidate_id=candidate_id)
    except Exception as exc:  # total-function boundary for direct check consumers
        return CheckResult(
            "score_breakdown_contract",
            False,
            fixture_error(exc),
        )

    problems = []
    if sum(state.score_breakdown[candidate_id].values()) != state.scores[candidate_id]:
        problems.append("score_not_reconstructable")
    if lineage["scores"].get(candidate_id) != state.scores[candidate_id]:
        problems.append("lineage_missing_score")
    if (
        lineage["score_breakdown"].get(candidate_id)
        != state.score_breakdown[candidate_id]
    ):
        problems.append("lineage_missing_breakdown")
    return CheckResult("score_breakdown_contract", not problems, ", ".join(problems))


def manifest_pheromone_trails(
    policy: CollectiveDecisionPolicy,
    *,
    candidate_id: str,
    target: str,
) -> list[PheromoneTrail]:
    """Build a valid scoring probe from the manifest's own strength and diversity bounds."""

    diversity = policy.pheromone_min_source_diversity
    strength = min(
        float(policy.pheromone_max_strength),
        float(policy.pheromone_per_source_cap),
        float(policy.pheromone_per_round_deposit_cap),
    )
    return [
        PheromoneTrail(
            candidate_id=candidate_id,
            subject_type="candidate",
            subject_id=candidate_id,
            target=target,
            strength=strength,
            source_id=f"agent:conformance:{index}",
            evidence_id="evidence:conformance",
            provenance="driver:conformance",
            trace_event_id=f"trace:score-breakdown:{index}",
        )
        for index in range(diversity)
    ]


def fixture_error(exc: Exception) -> str:
    detail = str(exc).strip()
    suffix = f":{detail}" if detail else ""
    return f"fixture_error:{type(exc).__name__}{suffix}"


def verification(
    target: str, source_id: str, candidate_id: str, suffix: str
) -> SignalVerification:
    return verify_signal_input(
        target=target,
        source_id=source_id,
        subject_id=candidate_id,
        verifier_id="governance:conformance",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="conformance:governance",
        trace_event_id=f"trace:verify:{suffix}",
    )
