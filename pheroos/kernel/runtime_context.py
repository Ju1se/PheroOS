from __future__ import annotations

from dataclasses import dataclass, field

from pheroos._immutable import freeze_abi_sequence
from pheroos.kernel.os_plan import DriverExposure, ToolExposure
from pheroos.kernel.permission import PermissionGrant
from pheroos.kernel.run_scope import RuntimeScope


@dataclass(frozen=True)
class RuntimeContext:
    tenant_id: str
    request_id: str
    run_id: str = ""
    scope_ref: str = ""
    permission_grants: tuple[PermissionGrant, ...] = field(default_factory=tuple)
    driver_exposures: tuple[DriverExposure, ...] = field(default_factory=tuple)
    tool_exposures: tuple[ToolExposure, ...] = field(default_factory=tuple)
    ready: bool = True
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
        for name in ("permission_grants", "driver_exposures", "tool_exposures"):
            object.__setattr__(self, name, freeze_abi_sequence(getattr(self, name)))
