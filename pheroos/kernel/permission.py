from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionGrant:
    capability_id: str
    permission: str
    granted: bool = True
    reason: str = ""
