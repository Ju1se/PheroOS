from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import deep_freeze


class SignalStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"


_SIGNAL_VERIFICATION_ISSUANCE = object()


@dataclass(frozen=True)
class SignalVerification:
    """Governance-issued verification bound to one source, subject, and target.

    A caller-provided boolean is intentionally not an authority record.  The
    verifier identity and lineage remain explicit so quorum and swarm inputs can
    be audited without making an agent itself authoritative.
    """

    target: str
    source_id: str
    subject_id: str
    verifier_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(default=None, init=False, repr=False, compare=False)


def verify_signal_input(
    *,
    target: str,
    source_id: str,
    subject_id: str,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> SignalVerification:
    if not isinstance(authority, AuthorityLevel) or not can_verify(authority):
        raise GovernanceError("signal verification requires governance authority")
    values = {
        "target": target,
        "source_id": source_id,
        "subject_id": subject_id,
        "verifier_id": verifier_id,
        "provenance": provenance,
        "trace_event_id": trace_event_id,
    }
    missing = [
        name
        for name, value in values.items()
        if not is_nonblank_string(value)
    ]
    if missing:
        raise GovernanceError(f"signal verification is missing {missing[0]}")
    verification = SignalVerification(
        target=target,
        source_id=source_id,
        subject_id=subject_id,
        verifier_id=verifier_id,
        authority=authority,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    object.__setattr__(
        verification,
        "_issuance",
        (
            _SIGNAL_VERIFICATION_ISSUANCE,
            _signal_verification_snapshot(verification),
        ),
    )
    return verification


def _signal_verification_snapshot(
    verification: SignalVerification,
) -> tuple[str, str, str, str, AuthorityLevel, str, str]:
    return (
        verification.target,
        verification.source_id,
        verification.subject_id,
        verification.verifier_id,
        verification.authority,
        verification.provenance,
        verification.trace_event_id,
    )


def _signal_verification_is_authoritative(verification: object) -> bool:
    if type(verification) is not SignalVerification:
        return False
    try:
        issuance = verification._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _SIGNAL_VERIFICATION_ISSUANCE
            and issuance[1] == _signal_verification_snapshot(verification)
            and isinstance(verification.authority, AuthorityLevel)
            and can_verify(verification.authority)
            and is_nonblank_string(verification.target)
            and is_nonblank_string(verification.source_id)
            and is_nonblank_string(verification.subject_id)
            and is_nonblank_string(verification.verifier_id)
            and is_nonblank_string(verification.provenance)
            and is_nonblank_string(verification.trace_event_id)
        )
    except Exception:
        # Frozen dataclasses can still be corrupted through object.__setattr__.
        # Corrupt authority records must fail closed at every consumption site.
        return False


def signal_verification_matches(
    verification: SignalVerification | None,
    *,
    target: str,
    source_id: str,
    subject_id: str,
) -> bool:
    return bool(
        _signal_verification_is_authoritative(verification)
        and verification.target == target
        and verification.source_id == source_id
        and verification.subject_id == subject_id
    )


@dataclass(frozen=True)
class Signal:
    target: str
    type: str
    source: str
    status: SignalStatus = SignalStatus.PROPOSED
    authority: AuthorityLevel = AuthorityLevel.AGENT
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))

    def verified(self) -> "Signal":
        if not can_verify(self.authority):
            return Signal(
                target=self.target,
                type=self.type,
                source=self.source,
                status=SignalStatus.REJECTED,
                authority=self.authority,
                metadata={**self.metadata, "reason": "insufficient_authority"},
            )
        return Signal(
            target=self.target,
            type=self.type,
            source=self.source,
            status=SignalStatus.VERIFIED,
            authority=self.authority,
            metadata=self.metadata,
        )
