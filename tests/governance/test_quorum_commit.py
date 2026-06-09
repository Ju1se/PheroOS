import pytest

from pheroos.governance import Candidate, CandidateSet, StopResolution, commit_candidate
from pheroos.governance.errors import GovernanceError


def test_quorum_commits_only_declared_candidate() -> None:
    candidates = CandidateSet([Candidate(id="candidate:accept", target="decision:review")])

    decision = commit_candidate(candidate_set=candidates, candidate_id="candidate:accept", target="decision:review")

    assert decision.committed is True


def test_quorum_rejects_undeclared_candidate() -> None:
    candidates = CandidateSet([])

    with pytest.raises(GovernanceError):
        commit_candidate(candidate_set=candidates, candidate_id="candidate:missing", target="decision:review")


def test_quorum_cannot_commit_through_stop_resolution() -> None:
    candidates = CandidateSet([Candidate(id="candidate:accept", target="decision:review")])

    decision = commit_candidate(
        candidate_set=candidates,
        candidate_id="candidate:accept",
        target="decision:review",
        stop_resolutions=[StopResolution(target="decision:review", action="publish", blocked=True)],
    )

    assert decision.committed is False
