from __future__ import annotations

from enum import Enum
from typing import Any


class SignalLifecycleState(str, Enum):
    PROPOSED = "proposed"
    OBSERVED = "observed"
    VERIFIED = "verified"
    BLOCKING = "blocking"
    PENDING_APPROVAL = "pending_approval"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    REJECTED_BY_GATE = "rejected_by_gate"
    ACCEPTED_PATCH = "accepted_patch"
    EXPIRED = "expired"


class BlockingStatus(str, Enum):
    OPEN = "open"
    BLOCKING = "blocking"
    RESOLVED = "resolved"
    REJECTED = "rejected"


TERMINAL_LIFECYCLE_STATES = {
    SignalLifecycleState.RESOLVED.value,
    SignalLifecycleState.REJECTED.value,
    SignalLifecycleState.REJECTED_BY_GATE.value,
    SignalLifecycleState.ACCEPTED_PATCH.value,
    SignalLifecycleState.EXPIRED.value,
}


def lifecycle_state_for_signal(signal: dict[str, Any]) -> SignalLifecycleState:
    explicit = normalize_lifecycle_state(signal.get("lifecycle_state") or signal.get("status"))
    if explicit is not None:
        return explicit
    verification = str(signal.get("verification_state") or "").strip().lower()
    if bool(signal.get("blocking")) or verification == "blocking":
        return SignalLifecycleState.BLOCKING
    if verification == "verified":
        return SignalLifecycleState.VERIFIED
    if verification == "rejected":
        return SignalLifecycleState.REJECTED
    if verification == "contested":
        return SignalLifecycleState.PROPOSED
    if verification == "unverified":
        return SignalLifecycleState.OBSERVED
    return SignalLifecycleState.OBSERVED


def blocking_status_for_signal(signal: dict[str, Any]) -> BlockingStatus:
    state = lifecycle_state_for_signal(signal)
    if state == SignalLifecycleState.BLOCKING:
        return BlockingStatus.BLOCKING
    if state == SignalLifecycleState.RESOLVED:
        return BlockingStatus.RESOLVED
    if state == SignalLifecycleState.ACCEPTED_PATCH:
        return BlockingStatus.RESOLVED
    if state == SignalLifecycleState.REJECTED:
        return BlockingStatus.REJECTED
    if state == SignalLifecycleState.REJECTED_BY_GATE:
        return BlockingStatus.REJECTED
    return BlockingStatus.OPEN


def is_active_blocker(signal: dict[str, Any]) -> bool:
    return blocking_status_for_signal(signal) == BlockingStatus.BLOCKING


def normalize_lifecycle_state(value: Any) -> SignalLifecycleState | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    aliases = {
        "block": "blocking",
        "blocked": "blocking",
        "hard_block": "blocking",
        "hard-block": "blocking",
        "accepted": "verified",
        "promoted": "verified",
        "deny": "rejected",
        "denied": "rejected",
        "gate_rejected": "rejected_by_gate",
        "blocked_by_gate": "rejected_by_gate",
        "rejected by gate": "rejected_by_gate",
        "awaiting_approval": "pending_approval",
        "approval_pending": "pending_approval",
        "approved_patch": "accepted_patch",
        "patch_accepted": "accepted_patch",
        "closed": "resolved",
        "done": "resolved",
    }
    text = aliases.get(text, text)
    try:
        return SignalLifecycleState(text)
    except ValueError:
        return None


def lifecycle_payload(signal: dict[str, Any]) -> dict[str, str]:
    lifecycle = lifecycle_state_for_signal(signal)
    return {
        "lifecycle_state": lifecycle.value,
        "blocking_status": blocking_status_for_signal(signal).value,
    }
