from __future__ import annotations

from dataclasses import dataclass, field

from pheroos._immutable import freeze_abi_sequence
from pheroos.drivers.base import DriverProbeSnapshot
from pheroos.kernel.connection import ConnectionReadiness, ConnectionRequirement
from pheroos.kernel.permission import PermissionGrant
from pheroos.kernel.run_scope import RuntimeScope


@dataclass(frozen=True)
class DriverExposure:
    driver_id: str
    capability_id: str
    permissions: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", freeze_abi_sequence(self.permissions))
        object.__setattr__(self, "capabilities", freeze_abi_sequence(self.capabilities))


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
    run_id: str = ""
    scope_ref: str = ""
    capability_resolutions: tuple[CapabilityResolution, ...] = field(default_factory=tuple)
    permission_grants: tuple[PermissionGrant, ...] = field(default_factory=tuple)
    connection_requirements: tuple[ConnectionRequirement, ...] = field(default_factory=tuple)
    connection_readiness: tuple[ConnectionReadiness, ...] = field(default_factory=tuple)
    driver_probe_snapshots: tuple[DriverProbeSnapshot, ...] = field(default_factory=tuple)
    driver_exposures: tuple[DriverExposure, ...] = field(default_factory=tuple)
    tool_exposures: tuple[ToolExposure, ...] = field(default_factory=tuple)
    diagnostics: tuple[KernelDiagnostic, ...] = field(default_factory=tuple)
    runtime_ready: bool = True
    degraded: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.tenant_id, str)
            and self.tenant_id.strip()
            and isinstance(self.request_id, str)
            and self.request_id.strip()
        ):
            run_id = self.run_id or self.request_id
            try:
                scope = RuntimeScope(
                    tenant_id=self.tenant_id,
                    run_id=run_id,
                    request_id=self.request_id,
                    scope_ref=self.scope_ref,
                )
            except ValueError:
                pass
            else:
                object.__setattr__(self, "run_id", scope.run_id)
                object.__setattr__(self, "scope_ref", scope.scope_ref)
        for name in (
            "capability_resolutions",
            "permission_grants",
            "connection_requirements",
            "connection_readiness",
            "driver_probe_snapshots",
            "driver_exposures",
            "tool_exposures",
            "diagnostics",
        ):
            object.__setattr__(self, name, freeze_abi_sequence(getattr(self, name)))
