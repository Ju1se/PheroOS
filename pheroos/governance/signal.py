from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pheroos.governance.authority import AuthorityLevel, can_verify


class SignalStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Signal:
    target: str
    type: str
    source: str
    status: SignalStatus = SignalStatus.PROPOSED
    authority: AuthorityLevel = AuthorityLevel.AGENT
    metadata: dict[str, Any] = field(default_factory=dict)

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
