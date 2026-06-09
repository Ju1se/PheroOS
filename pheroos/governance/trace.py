from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    event_type: str
    protocol_id: str
    target: str
    reason: str
    lineage: dict[str, Any] = field(default_factory=dict)
