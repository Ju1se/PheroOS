from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class ModelDriverDescriptor(DriverDescriptor):
    provider: str = ""
    supported_models: list[str] = field(default_factory=list)
    context_limits: dict[str, int] = field(default_factory=dict)
    tool_call_support: bool = False
    streaming_support: bool = False
    auth_requirements: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        *,
        driver_id: str,
        provider: str,
        supported_models: list[str] | None = None,
        context_limits: dict[str, int] | None = None,
        tool_call_support: bool = False,
        streaming_support: bool = False,
        auth_requirements: dict[str, Any] | None = None,
        permissions: list[str] | None = None,
        safety_metadata: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "driver_id", driver_id)
        object.__setattr__(self, "driver_kind", "model")
        object.__setattr__(self, "version", "0.1.0")
        object.__setattr__(self, "permissions", list(permissions or []))
        object.__setattr__(self, "safety_metadata", dict(safety_metadata or {}))
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "supported_models", list(supported_models or []))
        object.__setattr__(self, "context_limits", dict(context_limits or {}))
        object.__setattr__(self, "tool_call_support", tool_call_support)
        object.__setattr__(self, "streaming_support", streaming_support)
        object.__setattr__(self, "auth_requirements", dict(auth_requirements or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "provider": self.provider,
            "supported_models": list(self.supported_models),
            "context_limits": dict(self.context_limits),
            "tool_call_support": self.tool_call_support,
            "streaming_support": self.streaming_support,
            "auth_requirements": dict(self.auth_requirements),
        }
