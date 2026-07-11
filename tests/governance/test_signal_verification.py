import pytest

from pheroos.governance import AuthorityLevel, Signal, SignalStatus, verify_signal_input
from pheroos.governance.errors import GovernanceError


def test_agent_signal_verification_is_rejected() -> None:
    signal = Signal(
        target="decision:e2e",
        type="proposal",
        source="agent",
        authority=AuthorityLevel.AGENT,
    )

    verified = signal.verified()

    assert verified.status == SignalStatus.REJECTED
    assert verified.metadata["reason"] == "insufficient_authority"


def test_governance_signal_verification_succeeds() -> None:
    signal = Signal(
        target="decision:e2e",
        type="proposal",
        source="governance",
        authority=AuthorityLevel.GOVERNANCE,
    )

    assert signal.verified().status == SignalStatus.VERIFIED


def test_agent_cannot_issue_collective_signal_verification() -> None:
    with pytest.raises(GovernanceError, match="governance authority"):
        verify_signal_input(
            target="decision:e2e",
            source_id="agent:scout",
            subject_id="candidate:accept",
            verifier_id="agent:self",
            authority=AuthorityLevel.AGENT,
            provenance="agent:self-assertion",
            trace_event_id="trace:self-assertion",
        )
