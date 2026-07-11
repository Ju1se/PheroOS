from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.kernel._immutable import freeze_abi_sequence
from pheroos.kernel.os_plan import DriverExposure, ToolExposure
from pheroos.kernel.permission import PermissionGrant


@dataclass(frozen=True)
class RuntimeContext:
    tenant_id: str
    request_id: str
    permission_grants: tuple[PermissionGrant, ...] = field(default_factory=tuple)
    driver_exposures: tuple[DriverExposure, ...] = field(default_factory=tuple)
    tool_exposures: tuple[ToolExposure, ...] = field(default_factory=tuple)
    ready: bool = True
    degraded: bool = False

    def __post_init__(self) -> None:
        for name in ("permission_grants", "driver_exposures", "tool_exposures"):
            object.__setattr__(self, name, freeze_abi_sequence(getattr(self, name)))
