from __future__ import annotations

from dataclasses import dataclass

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.stop_signal import StopResolution


@dataclass(frozen=True)
class QuorumDecision:
    target: str
    candidate_id: str
    committed: bool
    reason: str


def commit_candidate(
    *,
    candidate_set: CandidateSet,
    candidate_id: str,
    target: str,
    stop_resolutions: list[StopResolution] | None = None,
) -> QuorumDecision:
    candidate = candidate_set.require_declared(candidate_id)
    blocked = [
        resolution for resolution in stop_resolutions or []
        if resolution.target == target and resolution.blocked
    ]
    if blocked:
        return QuorumDecision(target=target, candidate_id=candidate.id, committed=False, reason="blocked_by_stop_signal")
    return QuorumDecision(target=target, candidate_id=candidate.id, committed=True, reason="declared_candidate_committed")
