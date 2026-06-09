from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConformanceProfile:
    name: str = "core"
    required_checks: list[str] = field(default_factory=list)
