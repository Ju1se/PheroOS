from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.kernel.os_plan import DriverExposure, ToolExposure
from pheroos.kernel.permission import PermissionGrant


@dataclass(frozen=True)
class RuntimeContext:
    tenant_id: str
    request_id: str
    permission_grants: list[PermissionGrant] = field(default_factory=list)
    driver_exposures: list[DriverExposure] = field(default_factory=list)
    tool_exposures: list[ToolExposure] = field(default_factory=list)
    ready: bool = True
    degraded: bool = False
