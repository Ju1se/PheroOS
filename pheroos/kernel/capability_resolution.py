from __future__ import annotations

from collections.abc import Sequence

from pheroos.drivers.base import DriverProbeSnapshot
from pheroos.kernel.input_envelope import InputEnvelope
from pheroos.kernel.connection import ConnectionReadiness, ConnectionRequirement
from pheroos.kernel.os_plan import CapabilityResolution, DriverExposure, KernelDiagnostic, OSPlan
from pheroos.kernel.permission import PermissionGrant
from pheroos.protocol.models import CapabilityManifest, DriverSpec
from pheroos.protocol.validation import validate_capability_manifest


class OSKernel:
    """Plan available resources without making domain conclusions."""

    def plan(
        self,
        envelope: InputEnvelope,
        capabilities: list[CapabilityManifest],
        *,
        driver_probe_snapshots: Sequence[DriverProbeSnapshot] = (),
        connection_readiness: Sequence[ConnectionReadiness] = (),
    ) -> OSPlan:
        request_id = str(envelope.metadata.get("request_id") or "request")
        run_id = str(envelope.metadata.get("run_id") or request_id)
        diagnostics: list[KernelDiagnostic] = []
        probes, ambiguous_probes = _index_driver_probes(driver_probe_snapshots, diagnostics)
        connections, ambiguous_connections = _index_connection_readiness(
            connection_readiness,
            diagnostics,
        )
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
        resolutions: list[CapabilityResolution] = []
        for capability in capabilities:
            failure_codes: list[str] = []
            manifest_errors = [
                item
                for item in validate_capability_manifest(capability)
                if item.level == "error"
            ]
            for item in manifest_errors:
                code = f"manifest_{item.code}"
                failure_codes.append(code)
                diagnostics.append(
                    KernelDiagnostic(
                        code=code,
                        message=f"Capability {capability.id}: {item.message}",
                        severity="error",
                    )
                )

            for connection in capability.required_connections:
                if connection in ambiguous_connections:
                    failure_codes.append("connection_readiness_ambiguous")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="connection_readiness_ambiguous",
                            message=f"Connection {connection} has conflicting readiness snapshots.",
                            severity="error",
                        )
                    )
                    continue
                readiness = connections.get(connection)
                if readiness is None:
                    failure_codes.append("connection_readiness_missing")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="connection_readiness_missing",
                            message=f"Connection {connection} has no readiness snapshot.",
                            severity="warning",
                        )
                    )
                elif not readiness.available:
                    failure_codes.append("connection_unavailable")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="connection_unavailable",
                            message=(
                                f"Connection {connection} is unavailable"
                                + (f": {readiness.detail}" if readiness.detail else ".")
                            ),
                            severity="warning",
                        )
                    )

            pending_exposures: list[DriverExposure] = []
            for driver in capability.drivers:
                driver_id = driver_spec_id(driver)
                if not driver_id:
                    failure_codes.append("driver_identity_missing")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_identity_missing",
                            message=f"Capability {capability.id} has a driver without an id.",
                            severity="error",
                        )
                    )
                    continue
                permissions = driver_spec_permissions(driver)
                if not permissions:
                    failure_codes.append("driver_permissions_missing")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_permissions_missing",
                            message=f"Driver {driver_id} has no declared driver permissions.",
                            severity="warning",
                        )
                    )
                    continue
                if driver_id in ambiguous_probes:
                    failure_codes.append("driver_probe_ambiguous")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_probe_ambiguous",
                            message=f"Driver {driver_id} has conflicting probe snapshots.",
                            severity="error",
                        )
                    )
                    continue
                probe_snapshot = probes.get(driver_id)
                if probe_snapshot is None:
                    failure_codes.append("driver_probe_missing")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_probe_missing",
                            message=f"Driver {driver_id} has no probe snapshot.",
                            severity="warning",
                        )
                    )
                    continue
                if not probe_snapshot.available:
                    failure_codes.append("driver_probe_unavailable")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_probe_unavailable",
                            message=(
                                f"Driver {driver_id} is unavailable"
                                + (f": {probe_snapshot.detail}" if probe_snapshot.detail else ".")
                            ),
                            severity="warning",
                        )
                    )
                    continue
                if probe_snapshot.version != driver.version:
                    failure_codes.append("driver_version_mismatch")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_version_mismatch",
                            message=(
                                f"Driver {driver_id} version {probe_snapshot.version!r} does not "
                                f"match required version {driver.version!r}."
                            ),
                            severity="error",
                        )
                    )
                    continue
                missing_capabilities = sorted(
                    set(driver.capabilities) - set(probe_snapshot.capabilities)
                )
                if missing_capabilities:
                    failure_codes.append("driver_capability_mismatch")
                    diagnostics.append(
                        KernelDiagnostic(
                            code="driver_capability_mismatch",
                            message=(
                                f"Driver {driver_id} is missing required capabilities: "
                                + ", ".join(missing_capabilities)
                            ),
                            severity="error",
                        )
                    )
                    continue
                pending_exposures.append(
                    DriverExposure(
                        driver_id=driver_id,
                        capability_id=capability.id,
                        permissions=permissions,
                        capabilities=list(driver.capabilities),
                    )
                )
            available = not failure_codes
            if available:
                driver_exposures.extend(pending_exposures)
            resolutions.append(
                CapabilityResolution(
                    capability_id=capability.id,
                    available=available,
                    reason=",".join(dict.fromkeys(failure_codes)),
                )
            )
        runtime_ready = bool(resolutions) and all(item.available for item in resolutions)
        return OSPlan(
            tenant_id=envelope.tenant_id,
            request_id=request_id,
            run_id=run_id,
            capability_resolutions=resolutions,
            permission_grants=permission_grants,
            connection_requirements=connection_requirements,
            connection_readiness=tuple(connections.values()),
            driver_probe_snapshots=tuple(probes.values()),
            driver_exposures=driver_exposures,
            diagnostics=diagnostics,
            runtime_ready=runtime_ready,
            degraded=not runtime_ready,
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


def _index_driver_probes(
    snapshots: Sequence[DriverProbeSnapshot],
    diagnostics: list[KernelDiagnostic],
) -> tuple[dict[str, DriverProbeSnapshot], set[str]]:
    indexed: dict[str, DriverProbeSnapshot] = {}
    ambiguous: set[str] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, DriverProbeSnapshot):
            diagnostics.append(
                KernelDiagnostic(
                    code="driver_probe_invalid",
                    message="Driver probe input is not a canonical snapshot.",
                    severity="error",
                )
            )
            continue
        if not (
            isinstance(snapshot.driver_id, str)
            and snapshot.driver_id.strip()
            and isinstance(snapshot.version, str)
            and snapshot.version.strip()
            and isinstance(snapshot.available, bool)
            and isinstance(snapshot.detail, str)
            and isinstance(snapshot.capabilities, tuple)
            and all(
                isinstance(item, str) and bool(item.strip())
                for item in snapshot.capabilities
            )
        ):
            diagnostics.append(
                KernelDiagnostic(
                    code="driver_probe_invalid",
                    message="Driver probe identity and version must be nonblank.",
                    severity="error",
                )
            )
            continue
        previous = indexed.get(snapshot.driver_id)
        if previous is not None and previous != snapshot:
            ambiguous.add(snapshot.driver_id)
            continue
        indexed[snapshot.driver_id] = snapshot
    return indexed, ambiguous


def _index_connection_readiness(
    snapshots: Sequence[ConnectionReadiness],
    diagnostics: list[KernelDiagnostic],
) -> tuple[dict[str, ConnectionReadiness], set[str]]:
    indexed: dict[str, ConnectionReadiness] = {}
    ambiguous: set[str] = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, ConnectionReadiness):
            diagnostics.append(
                KernelDiagnostic(
                    code="connection_readiness_invalid",
                    message="Connection readiness input is not a canonical snapshot.",
                    severity="error",
                )
            )
            continue
        if not (
            isinstance(snapshot.connection, str)
            and snapshot.connection.strip()
            and isinstance(snapshot.available, bool)
            and isinstance(snapshot.detail, str)
        ):
            diagnostics.append(
                KernelDiagnostic(
                    code="connection_readiness_invalid",
                    message="Connection readiness identity must be nonblank.",
                    severity="error",
                )
            )
            continue
        previous = indexed.get(snapshot.connection)
        if previous is not None and previous != snapshot:
            ambiguous.add(snapshot.connection)
            continue
        indexed[snapshot.connection] = snapshot
    return indexed, ambiguous
