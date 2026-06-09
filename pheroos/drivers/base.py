from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DriverDescriptor:
    driver_id: str
    driver_kind: str
    version: str = "0.1.0"
    permissions: list[str] = field(default_factory=list)
    safety_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "pheroos.driver.v0.1",
            "driver_id": self.driver_id,
            "driver_kind": self.driver_kind,
            "version": self.version,
            "permissions": list(self.permissions),
            "safety_metadata": dict(self.safety_metadata),
        }
