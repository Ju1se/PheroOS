from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.stop_signal import StopResolution
from pheroos.protocol.models import QuorumPolicy


@dataclass(frozen=True)
class QuorumDecision:
    target: str
    candidate_id: str
    committed: bool
    reason: str


@dataclass(frozen=True)
class QuorumSignal:
    source_id: str
    candidate_id: str
    target: str
    verified: bool = True
    metadata: dict[str, object] = field(default_factory=dict)


def commit_candidate(
    *,
    candidate_set: CandidateSet,
    candidate_id: str,
    target: str,
    stop_resolutions: list[StopResolution] | None = None,
) -> QuorumDecision:
    candidate = candidate_set.require_declared_for_target(candidate_id, target)
    blocked = [
        resolution for resolution in stop_resolutions or []
        if resolution.target == target and resolution.blocked
    ]
    if blocked:
        return QuorumDecision(target=target, candidate_id=candidate.id, committed=False, reason="blocked_by_stop_signal")
    return QuorumDecision(target=target, candidate_id=candidate.id, committed=True, reason="declared_candidate_committed")


def evaluate_quorum_decision(
    *,
    candidate_set: CandidateSet,
    policy: QuorumPolicy,
    signals: list[QuorumSignal],
    stop_resolutions: list[StopResolution] | None = None,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
    supporters: dict[str, set[str]] = {
        candidate.id: set()
        for candidate in candidate_set.candidates
        if candidate.target == policy.target
    }
    for signal in signals:
        if not signal.verified or signal.target != policy.target:
            continue
        candidate = candidate_set.require_declared_for_target(signal.candidate_id, policy.target)
        if signal.source_id:
            supporters[candidate.id].add(signal.source_id)

    ranked = sorted(supporters.items(), key=lambda item: (-len(item[1]), item[0]))
    for candidate_id, source_ids in ranked:
        if len(source_ids) >= policy.commit_threshold:
            decision = commit_candidate(
                candidate_set=candidate_set,
                candidate_id=candidate_id,
                target=policy.target,
                stop_resolutions=stop_resolutions,
            )
            if decision.committed:
                return QuorumDecision(
                    target=policy.target,
                    candidate_id=decision.candidate_id,
                    committed=True,
                    reason="quorum_threshold_met",
                )
            return decision

    fallback = candidate_set.require_declared_for_target(
        fallback_candidate_id or policy.fallback_candidate,
        policy.target,
    )
    if not fallback.safe_fallback:
        raise GovernanceError(f"quorum fallback candidate is not marked safe: {fallback.id}")
    decision = commit_candidate(
        candidate_set=candidate_set,
        candidate_id=fallback.id,
        target=policy.target,
        stop_resolutions=stop_resolutions,
    )
    if decision.committed:
        return QuorumDecision(
            target=policy.target,
            candidate_id=fallback.id,
            committed=True,
            reason="safe_quorum_fallback",
        )
    return decision
