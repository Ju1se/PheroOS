from __future__ import annotations

from pheroos.kernel.input_envelope import InputEnvelope
from pheroos.kernel.connection import ConnectionRequirement
from pheroos.kernel.os_plan import CapabilityResolution, DriverExposure, KernelDiagnostic, OSPlan
from pheroos.kernel.permission import PermissionGrant
from pheroos.protocol.models import CapabilityManifest, DriverSpec


class OSKernel:
    """Plan available resources without making domain conclusions."""

    def plan(self, envelope: InputEnvelope, capabilities: list[CapabilityManifest]) -> OSPlan:
        resolutions = [
            CapabilityResolution(capability_id=capability.id, available=True)
            for capability in capabilities
        ]
        diagnostics: list[KernelDiagnostic] = []
        if not capabilities:
            diagnostics.append(
                KernelDiagnostic(
                    code="missing_capability",
                    message="No compatible capability was available.",
                    severity="warning",
                )
            )
        permission_grants = [
            PermissionGrant(capability_id=capability.id, permission=permission)
            for capability in capabilities
            for permission in capability.permissions
        ]
        connection_requirements = [
            ConnectionRequirement(capability_id=capability.id, connection=connection)
            for capability in capabilities
            for connection in capability.required_connections
        ]
        driver_exposures: list[DriverExposure] = []
        for capability in capabilities:
            for driver in capability.drivers:
                driver_id = driver_spec_id(driver)
                if not driver_id:
                    continue
                permissions = driver_spec_permissions(driver)
                if not permissions:
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_permissions_missing",
                            message=f"Driver {driver_id} has no declared driver permissions.",
                            severity="warning",
                        )
                    )
                    continue
                driver_exposures.append(
                    DriverExposure(
                        driver_id=driver_id,
                        capability_id=capability.id,
                        permissions=permissions,
                    )
                )
        return OSPlan(
            tenant_id=envelope.tenant_id,
            request_id=str(envelope.metadata.get("request_id") or "request"),
            capability_resolutions=resolutions,
            permission_grants=permission_grants,
            connection_requirements=connection_requirements,
            driver_exposures=driver_exposures,
            diagnostics=diagnostics,
            runtime_ready=bool(capabilities),
            degraded=not capabilities,
        )


def text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def driver_spec_id(driver: DriverSpec | dict[str, object]) -> str:
    if isinstance(driver, DriverSpec):
        return driver.id.strip()
    return str(driver.get("id") or "").strip()


def driver_spec_permissions(driver: DriverSpec | dict[str, object]) -> list[str]:
    if isinstance(driver, DriverSpec):
        return [permission for permission in driver.permissions if permission]
    return text_list(driver.get("permissions"))
