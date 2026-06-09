from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionRequirement:
    capability_id: str
    connection: str
    required: bool = True
