"""Shared replay namespace vocabulary for legacy and durable Commit owners.

This leaf module owns data vocabulary only.  It deliberately has no authority
registry, issuance token, cursor, lock, or dependency on either Commit owner.
"""

from __future__ import annotations

from enum import StrEnum


class ReplayNamespace(StrEnum):
    PRINCIPAL = "principal"
    OBSERVATION = "observation"
    CHALLENGE = "challenge"
    COUNTEREVIDENCE_DISPOSITION = "counterevidence_disposition"
    MEMBERSHIP = "membership"
    SUPPORT_LEASE = "support_lease"
    SUPPORT_REVOCATION = "support_revocation"
    RISK_ASSESSMENT = "risk_assessment"
    THRESHOLD = "threshold"
    STOP_RESOLUTION = "stop_resolution"
    ACTION_PERMISSION = "action_permission"
    ASSESSMENT = "assessment"
    WITNESS = "witness"


ReplayNamespace.__module__ = "pheroos.governance.commit_state"


__all__ = ["ReplayNamespace"]
