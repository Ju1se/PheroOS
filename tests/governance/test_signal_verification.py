from pheroos.governance import AuthorityLevel, Signal, SignalStatus


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
