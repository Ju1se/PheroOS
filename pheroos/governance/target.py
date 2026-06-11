from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalTarget:
    id: str
    kind: str = "decision"
