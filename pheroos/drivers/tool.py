from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class ToolDriverDescriptor(DriverDescriptor):
    tool_id: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effect_class: str = "read_only"
    network_policy: dict[str, Any] = field(default_factory=dict)
    filesystem_policy: dict[str, Any] = field(default_factory=dict)
    provenance_policy: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        *,
        tool_id: str,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        permissions: list[str] | None = None,
        side_effect_class: str = "read_only",
        network_policy: dict[str, Any] | None = None,
        filesystem_policy: dict[str, Any] | None = None,
        provenance_policy: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "driver_id", tool_id)
        object.__setattr__(self, "driver_kind", "tool")
        object.__setattr__(self, "version", "0.1.0")
        object.__setattr__(self, "permissions", list(permissions or []))
        object.__setattr__(self, "safety_metadata", {})
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "input_schema", dict(input_schema or {}))
        object.__setattr__(self, "output_schema", dict(output_schema or {}))
        object.__setattr__(self, "side_effect_class", side_effect_class)
        object.__setattr__(self, "network_policy", dict(network_policy or {}))
        object.__setattr__(self, "filesystem_policy", dict(filesystem_policy or {}))
        object.__setattr__(self, "provenance_policy", dict(provenance_policy or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "tool_id": self.tool_id,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "side_effect_class": self.side_effect_class,
            "network_policy": dict(self.network_policy),
            "filesystem_policy": dict(self.filesystem_policy),
            "provenance_policy": dict(self.provenance_policy),
        }
