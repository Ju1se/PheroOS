from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.swarm.target_registry import canonical_target, target_kind


GOAL_ROUTER_VERSION = "pheroos.goal_router.v1"


@dataclass(frozen=True)
class GoalTarget:
    target: str
    demand_strength: float
    keywords: tuple[str, ...]
    summary: str

    def to_signal(self) -> dict[str, Any]:
        canonical = canonical_target(self.target)
        return {
            "schema_version": GOAL_ROUTER_VERSION,
            "type": "goal",
            "target": self.target,
            "canonical_target": canonical,
            "target_kind": target_kind(canonical),
            "demand_strength": round(self.demand_strength, 3),
            "source_module": "os_kernel.goal_router",
            "lifecycle_state": "active",
            "content": self.summary,
        }
