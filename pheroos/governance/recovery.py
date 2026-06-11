from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecoveryTrace:
    protocol_id: str
    trigger_target: str
    selected_roles: list[str] = field(default_factory=list)
    selected_tags: list[str] = field(default_factory=list)
    selected_tools: list[str] = field(default_factory=list)
    success: bool = False
    failure_candidate: str = ""
