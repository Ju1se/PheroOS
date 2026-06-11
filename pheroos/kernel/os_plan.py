from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.kernel.connection import ConnectionRequirement
from pheroos.kernel.permission import PermissionGrant


@dataclass(frozen=True)
class DriverExposure:
    driver_id: str
    capability_id: str
    permissions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolExposure:
    tool_id: str
    capability_id: str
    permissions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class KernelDiagnostic:
    code: str
    message: str
    severity: str = "info"


@dataclass(frozen=True)
class CapabilityResolution:
    capability_id: str
    available: bool
    reason: str = ""


@dataclass(frozen=True)
class OSPlan:
    tenant_id: str
    request_id: str
    capability_resolutions: list[CapabilityResolution] = field(default_factory=list)
    permission_grants: list[PermissionGrant] = field(default_factory=list)
    connection_requirements: list[ConnectionRequirement] = field(default_factory=list)
    driver_exposures: list[DriverExposure] = field(default_factory=list)
    tool_exposures: list[ToolExposure] = field(default_factory=list)
    diagnostics: list[KernelDiagnostic] = field(default_factory=list)
    runtime_ready: bool = True
    degraded: bool = False
