import pytest

from pheroos.governance import Candidate, CandidateSet, QuorumSignal, StopResolution, commit_candidate, evaluate_quorum_decision
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import QuorumPolicy


def test_quorum_commits_only_declared_candidate() -> None:
    candidates = CandidateSet([Candidate(id="candidate:accept", target="decision:review")])

    decision = commit_candidate(candidate_set=candidates, candidate_id="candidate:accept", target="decision:review")

    assert decision.committed is True


def test_quorum_rejects_undeclared_candidate() -> None:
    candidates = CandidateSet([])

    with pytest.raises(GovernanceError):
        commit_candidate(candidate_set=candidates, candidate_id="candidate:missing", target="decision:review")


def test_quorum_rejects_candidate_for_different_target() -> None:
    candidates = CandidateSet([Candidate(id="candidate:other", target="decision:other", safe_fallback=True)])

    with pytest.raises(GovernanceError, match="not active target"):
        commit_candidate(candidate_set=candidates, candidate_id="candidate:other", target="decision:review")


def test_quorum_cannot_commit_through_stop_resolution() -> None:
    candidates = CandidateSet([Candidate(id="candidate:accept", target="decision:review")])

    decision = commit_candidate(
        candidate_set=candidates,
        candidate_id="candidate:accept",
        target="decision:review",
        stop_resolutions=[StopResolution(target="decision:review", action="publish", blocked=True)],
    )

    assert decision.committed is False


def test_quorum_evaluator_requires_threshold_before_commit() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:accept", target="decision:review"),
            Candidate(id="candidate:fallback", target="decision:review", safe_fallback=True),
        ]
    )
    policy = QuorumPolicy(target="decision:review", fallback_candidate="candidate:fallback", commit_threshold=2)

    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=policy,
        signals=[
            QuorumSignal(source_id="governance:a", candidate_id="candidate:accept", target="decision:review"),
            QuorumSignal(source_id="agent:b", candidate_id="candidate:accept", target="decision:review", verified=False),
            QuorumSignal(source_id="governance:c", candidate_id="candidate:accept", target="decision:other"),
        ],
    )

    assert decision.candidate_id == "candidate:fallback"
    assert decision.reason == "safe_quorum_fallback"


def test_quorum_evaluator_commits_when_threshold_is_met() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:accept", target="decision:review"),
            Candidate(id="candidate:fallback", target="decision:review", safe_fallback=True),
        ]
    )
    policy = QuorumPolicy(target="decision:review", fallback_candidate="candidate:fallback", commit_threshold=2)

    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=policy,
        signals=[
            QuorumSignal(source_id="governance:a", candidate_id="candidate:accept", target="decision:review"),
            QuorumSignal(source_id="governance:b", candidate_id="candidate:accept", target="decision:review"),
        ],
    )

    assert decision.candidate_id == "candidate:accept"
    assert decision.reason == "quorum_threshold_met"
