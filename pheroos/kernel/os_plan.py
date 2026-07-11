from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.kernel._immutable import freeze_abi_sequence
from pheroos.kernel.connection import ConnectionRequirement
from pheroos.kernel.permission import PermissionGrant


@dataclass(frozen=True)
class DriverExposure:
    driver_id: str
    capability_id: str
    permissions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", freeze_abi_sequence(self.permissions))


@dataclass(frozen=True)
class ToolExposure:
    tool_id: str
    capability_id: str
    permissions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", freeze_abi_sequence(self.permissions))


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
    capability_resolutions: tuple[CapabilityResolution, ...] = field(default_factory=tuple)
    permission_grants: tuple[PermissionGrant, ...] = field(default_factory=tuple)
    connection_requirements: tuple[ConnectionRequirement, ...] = field(default_factory=tuple)
    driver_exposures: tuple[DriverExposure, ...] = field(default_factory=tuple)
    tool_exposures: tuple[ToolExposure, ...] = field(default_factory=tuple)
    diagnostics: tuple[KernelDiagnostic, ...] = field(default_factory=tuple)
    runtime_ready: bool = True
    degraded: bool = False

    def __post_init__(self) -> None:
        for name in (
            "capability_resolutions",
            "permission_grants",
            "connection_requirements",
            "driver_exposures",
            "tool_exposures",
            "diagnostics",
        ):
            object.__setattr__(self, name, freeze_abi_sequence(getattr(self, name)))
