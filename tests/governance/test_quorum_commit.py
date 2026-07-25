import pytest

from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    QuorumSignal,
    SignalVerification,
    StopResolution,
    commit_candidate,
    evaluate_quorum_decision,
    verify_signal_input,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import QuorumPolicy


def test_quorum_commits_only_declared_candidate() -> None:
    candidates = CandidateSet(
        [Candidate(id="candidate:accept", target="decision:review")]
    )

    decision = commit_candidate(
        candidate_set=candidates,
        candidate_id="candidate:accept",
        target="decision:review",
    )

    assert decision.committed is True


def test_quorum_rejects_undeclared_candidate() -> None:
    candidates = CandidateSet([])

    with pytest.raises(GovernanceError):
        commit_candidate(
            candidate_set=candidates,
            candidate_id="candidate:missing",
            target="decision:review",
        )


def test_quorum_rejects_candidate_for_different_target() -> None:
    candidates = CandidateSet(
        [Candidate(id="candidate:other", target="decision:other", safe_fallback=True)]
    )

    with pytest.raises(GovernanceError, match="not active target"):
        commit_candidate(
            candidate_set=candidates,
            candidate_id="candidate:other",
            target="decision:review",
        )


def test_quorum_cannot_commit_through_stop_resolution() -> None:
    candidates = CandidateSet(
        [Candidate(id="candidate:accept", target="decision:review")]
    )

    decision = commit_candidate(
        candidate_set=candidates,
        candidate_id="candidate:accept",
        target="decision:review",
        stop_resolutions=[
            StopResolution(target="decision:review", action="publish", blocked=True)
        ],
    )

    assert decision.committed is False


def test_quorum_evaluator_requires_threshold_before_commit() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:accept", target="decision:review"),
            Candidate(
                id="candidate:fallback", target="decision:review", safe_fallback=True
            ),
        ]
    )
    policy = QuorumPolicy(
        target="decision:review",
        fallback_candidate="candidate:fallback",
        commit_threshold=2,
    )

    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=policy,
        signals=[
            verified_quorum_signal(
                "governance:a", "candidate:accept", "decision:review"
            ),
            QuorumSignal(
                source_id="agent:b",
                candidate_id="candidate:accept",
                target="decision:review",
                verified=False,
            ),
            verified_quorum_signal(
                "governance:c", "candidate:accept", "decision:other"
            ),
        ],
    )

    assert decision.candidate_id == "candidate:fallback"
    assert decision.reason == "safe_quorum_fallback"


def test_quorum_rejects_runtime_override_of_declared_fallback() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:accept", target="decision:review"),
            Candidate(
                id="candidate:fallback", target="decision:review", safe_fallback=True
            ),
            Candidate(
                id="candidate:alternate", target="decision:review", safe_fallback=True
            ),
        ]
    )

    with pytest.raises(GovernanceError, match="declared quorum fallback"):
        evaluate_quorum_decision(
            candidate_set=candidates,
            policy=QuorumPolicy(
                target="decision:review",
                fallback_candidate="candidate:fallback",
                commit_threshold=2,
            ),
            signals=[],
            fallback_candidate_id="candidate:alternate",
        )


def test_quorum_evaluator_commits_when_threshold_is_met() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:accept", target="decision:review"),
            Candidate(
                id="candidate:fallback", target="decision:review", safe_fallback=True
            ),
        ]
    )
    policy = QuorumPolicy(
        target="decision:review",
        fallback_candidate="candidate:fallback",
        commit_threshold=2,
    )

    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=policy,
        signals=[
            verified_quorum_signal(
                "governance:a", "candidate:accept", "decision:review"
            ),
            verified_quorum_signal(
                "governance:b", "candidate:accept", "decision:review"
            ),
        ],
    )

    assert decision.candidate_id == "candidate:accept"
    assert decision.reason == "quorum_threshold_met"


@pytest.mark.parametrize("commit_threshold", [0, -1, True, 1.0, "1"])
def test_direct_quorum_policy_rejects_invalid_commit_threshold(
    commit_threshold: object,
) -> None:
    with pytest.raises(GovernanceError, match="positive integer"):
        evaluate_quorum_decision(
            candidate_set=CandidateSet(
                [Candidate("candidate:fallback", "decision:review", safe_fallback=True)]
            ),
            policy=QuorumPolicy(
                target="decision:review",
                fallback_candidate="candidate:fallback",
                commit_threshold=commit_threshold,
            ),
            signals=[],
        )


@pytest.mark.parametrize(
    ("target", "fallback", "message"),
    [
        ("", "candidate:fallback", "target must be non-empty"),
        ("decision:review", "", "fallback candidate must be non-empty"),
    ],
)
def test_direct_quorum_policy_rejects_empty_authority_bindings(
    target: str,
    fallback: str,
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        evaluate_quorum_decision(
            candidate_set=CandidateSet(
                [Candidate("candidate:fallback", "decision:review", safe_fallback=True)]
            ),
            policy=QuorumPolicy(
                target=target,
                fallback_candidate=fallback,
                commit_threshold=1,
            ),
            signals=[],
        )


def test_caller_boolean_cannot_forge_quorum_verification() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:accept", target="decision:review"),
            Candidate(
                id="candidate:fallback", target="decision:review", safe_fallback=True
            ),
        ]
    )
    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=QuorumPolicy(
            target="decision:review",
            fallback_candidate="candidate:fallback",
            commit_threshold=1,
        ),
        signals=[
            QuorumSignal(
                source_id="agent:self-asserted",
                candidate_id="candidate:accept",
                target="decision:review",
                verified=True,
            )
        ],
    )

    assert decision.candidate_id == "candidate:fallback"


def test_direct_verification_record_cannot_forge_quorum_authority() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:accept", target="decision:review"),
            Candidate(
                id="candidate:fallback", target="decision:review", safe_fallback=True
            ),
        ]
    )
    forged = SignalVerification(
        target="decision:review",
        source_id="agent:self-asserted",
        subject_id="candidate:accept",
        verifier_id="agent:self-asserted",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="agent:self-assertion",
        trace_event_id="trace:self-assertion",
    )

    decision = evaluate_quorum_decision(
        candidate_set=candidates,
        policy=QuorumPolicy(
            target="decision:review",
            fallback_candidate="candidate:fallback",
            commit_threshold=1,
        ),
        signals=[
            QuorumSignal(
                source_id="agent:self-asserted",
                candidate_id="candidate:accept",
                target="decision:review",
                verification=forged,
            )
        ],
    )

    assert decision.candidate_id == "candidate:fallback"


@pytest.mark.parametrize(
    ("field_name", "issued_value", "tampered_value"),
    [
        ("target", "decision:other", "decision:review"),
        ("source_id", "governance:other", "governance:expected"),
        ("subject_id", "candidate:other", "candidate:accept"),
        ("verifier_id", "governance:quorum", "governance:forged"),
        ("authority", AuthorityLevel.GOVERNANCE, AuthorityLevel.KERNEL),
        ("provenance", "governance:original", "governance:forged"),
        ("trace_event_id", "trace:verify:original", "trace:verify:forged"),
    ],
)
def test_issued_signal_verification_snapshot_rejects_every_field_rebinding(
    field_name: str,
    issued_value: object,
    tampered_value: object,
) -> None:
    verification_values = {
        "target": "decision:review",
        "source_id": "governance:expected",
        "subject_id": "candidate:accept",
        "verifier_id": "governance:quorum",
        "authority": AuthorityLevel.GOVERNANCE,
        "provenance": "governance:original",
        "trace_event_id": "trace:verify:original",
    }
    verification_values[field_name] = issued_value
    verification = verify_signal_input(**verification_values)
    object.__setattr__(verification, field_name, tampered_value)

    decision = evaluate_quorum_decision(
        candidate_set=CandidateSet(
            [
                Candidate("candidate:accept", "decision:review"),
                Candidate("candidate:fallback", "decision:review", safe_fallback=True),
            ]
        ),
        policy=QuorumPolicy(
            target="decision:review",
            fallback_candidate="candidate:fallback",
            commit_threshold=1,
        ),
        signals=[
            QuorumSignal(
                source_id="governance:expected",
                candidate_id="candidate:accept",
                target="decision:review",
                verification=verification,
            )
        ],
    )

    assert decision.candidate_id == "candidate:fallback"
    assert decision.reason == "safe_quorum_fallback"


def verified_quorum_signal(
    source_id: str, candidate_id: str, target: str
) -> QuorumSignal:
    return QuorumSignal(
        source_id=source_id,
        candidate_id=candidate_id,
        target=target,
        verification=verify_signal_input(
            target=target,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:quorum",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:quorum-verification",
            trace_event_id=f"trace:verify:{source_id}",
        ),
    )
