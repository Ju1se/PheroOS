from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.signal import SignalVerification, signal_verification_matches
from pheroos.governance.stop_signal import StopResolution
from pheroos.protocol.models import QuorumPolicy, deep_freeze

_QUORUM_DECISION_ISSUANCE = object()


@dataclass(frozen=True)
class QuorumDecision:
    target: str
    candidate_id: str
    committed: bool
    reason: str
    _issuance: object | None = field(
        default=None, init=False, repr=False, compare=False
    )


def _issue_quorum_decision(
    *,
    target: str,
    candidate_id: str,
    committed: bool,
    reason: str,
) -> QuorumDecision:
    decision = QuorumDecision(
        target=target,
        candidate_id=candidate_id,
        committed=committed,
        reason=reason,
    )
    object.__setattr__(
        decision,
        "_issuance",
        (
            _QUORUM_DECISION_ISSUANCE,
            _quorum_decision_snapshot(decision),
        ),
    )
    return decision


def _quorum_decision_snapshot(
    decision: QuorumDecision,
) -> tuple[str, str, bool, str]:
    return (
        decision.target,
        decision.candidate_id,
        decision.committed,
        decision.reason,
    )


def quorum_decision_is_authoritative(decision: QuorumDecision) -> bool:
    if type(decision) is not QuorumDecision:
        return False
    try:
        issuance = decision._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _QUORUM_DECISION_ISSUANCE
            and issuance[1] == _quorum_decision_snapshot(decision)
            and isinstance(decision.target, str)
            and bool(decision.target.strip())
            and isinstance(decision.candidate_id, str)
            and bool(decision.candidate_id.strip())
            and isinstance(decision.committed, bool)
            and isinstance(decision.reason, str)
            and bool(decision.reason.strip())
        )
    except Exception:
        # A malformed or object.__setattr__-tampered record is never authority.
        return False


@dataclass(frozen=True)
class QuorumSignal:
    source_id: str
    candidate_id: str
    target: str
    verified: bool = False
    metadata: dict[str, object] = field(default_factory=dict)
    verification: SignalVerification | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))


def commit_candidate(
    *,
    candidate_set: CandidateSet,
    candidate_id: str,
    target: str,
    stop_resolutions: list[StopResolution] | None = None,
) -> QuorumDecision:
    candidate = candidate_set.require_declared_for_target(candidate_id, target)
    blocked = [
        resolution
        for resolution in stop_resolutions or []
        if resolution.target == target and resolution.blocked
    ]
    if blocked:
        return _issue_quorum_decision(
            target=target,
            candidate_id=candidate.id,
            committed=False,
            reason="blocked_by_stop_signal",
        )
    return _issue_quorum_decision(
        target=target,
        candidate_id=candidate.id,
        committed=True,
        reason="declared_candidate_committed",
    )


def evaluate_quorum_decision(
    *,
    candidate_set: CandidateSet,
    policy: QuorumPolicy,
    signals: list[QuorumSignal],
    stop_resolutions: list[StopResolution] | None = None,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
    _validate_quorum_policy(policy)
    supporters = _quorum_supporters(candidate_set, policy, signals)
    decision = _threshold_decision(
        candidate_set,
        policy,
        supporters,
        stop_resolutions=stop_resolutions,
    )
    if decision is not None:
        return decision
    return _fallback_decision(
        candidate_set,
        policy,
        stop_resolutions=stop_resolutions,
        fallback_candidate_id=fallback_candidate_id,
    )


def _quorum_supporters(
    candidate_set: CandidateSet,
    policy: QuorumPolicy,
    signals: list[QuorumSignal],
) -> dict[str, set[str]]:
    supporters: dict[str, set[str]] = {
        candidate.id: set()
        for candidate in candidate_set.candidates
        if candidate.target == policy.target
    }
    for signal in signals:
        if signal.target != policy.target:
            continue
        if not signal_verification_matches(
            signal.verification,
            target=signal.target,
            source_id=signal.source_id,
            subject_id=signal.candidate_id,
        ):
            continue
        candidate = candidate_set.require_declared_for_target(
            signal.candidate_id, policy.target
        )
        if signal.source_id:
            supporters[candidate.id].add(signal.source_id)
    return supporters


def _threshold_decision(
    candidate_set: CandidateSet,
    policy: QuorumPolicy,
    supporters: dict[str, set[str]],
    *,
    stop_resolutions: list[StopResolution] | None,
) -> QuorumDecision | None:
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
                return _issue_quorum_decision(
                    target=policy.target,
                    candidate_id=decision.candidate_id,
                    committed=True,
                    reason="quorum_threshold_met",
                )
            return decision
    return None


def _fallback_decision(
    candidate_set: CandidateSet,
    policy: QuorumPolicy,
    *,
    stop_resolutions: list[StopResolution] | None,
    fallback_candidate_id: str | None,
) -> QuorumDecision:
    if (
        fallback_candidate_id is not None
        and fallback_candidate_id != policy.fallback_candidate
    ):
        raise GovernanceError(
            "runtime fallback cannot override the declared quorum fallback"
        )
    fallback = candidate_set.require_declared_for_target(
        policy.fallback_candidate, policy.target
    )
    if not fallback.safe_fallback:
        raise GovernanceError(
            f"quorum fallback candidate is not marked safe: {fallback.id}"
        )
    decision = commit_candidate(
        candidate_set=candidate_set,
        candidate_id=fallback.id,
        target=policy.target,
        stop_resolutions=stop_resolutions,
    )
    if decision.committed:
        return _issue_quorum_decision(
            target=policy.target,
            candidate_id=fallback.id,
            committed=True,
            reason="safe_quorum_fallback",
        )
    return decision


def _validate_quorum_policy(policy: QuorumPolicy) -> None:
    if not isinstance(policy, QuorumPolicy):
        raise GovernanceError(
            "quorum policy must use the canonical protocol declaration"
        )
    if not isinstance(policy.target, str) or not policy.target.strip():
        raise GovernanceError("quorum policy target must be non-empty")
    if (
        not isinstance(policy.fallback_candidate, str)
        or not policy.fallback_candidate.strip()
    ):
        raise GovernanceError("quorum policy fallback candidate must be non-empty")
    if (
        not isinstance(policy.commit_threshold, int)
        or isinstance(policy.commit_threshold, bool)
        or policy.commit_threshold <= 0
    ):
        raise GovernanceError(
            "quorum policy commit threshold must be a positive integer"
        )
