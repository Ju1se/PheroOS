from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias, TypeGuard

from pheroos.drivers.base import DriverProbeSnapshot
from pheroos.kernel.input_envelope import InputEnvelope
from pheroos.kernel.connection import ConnectionReadiness, ConnectionRequirement
from pheroos.kernel.errors import KernelError
from pheroos.kernel.os_plan import (
    CapabilityResolution,
    DriverExposure,
    KernelDiagnostic,
    OSPlan,
)
from pheroos.kernel.permission import PermissionGrant
from pheroos.kernel.run_scope import RuntimeScope
from pheroos.protocol.authority_manifest_v2 import ScopedCapabilityManifestV2
from pheroos.protocol.models import CapabilityManifest, DriverSpec
from pheroos.protocol.models import ValidationDiagnostic
from pheroos.protocol.validation import validate_capability_manifest


_CapabilityDeclaration: TypeAlias = CapabilityManifest | ScopedCapabilityManifestV2


class OSKernel:
    """Plan available resources without making domain conclusions."""

    def plan(
        self,
        envelope: InputEnvelope,
        capabilities: list[_CapabilityDeclaration],
        *,
        driver_probe_snapshots: Sequence[DriverProbeSnapshot] = (),
        connection_readiness: Sequence[ConnectionReadiness] = (),
    ) -> OSPlan:
        scope = _runtime_scope_from_envelope(envelope)
        request_id = scope.request_id
        run_id = scope.run_id
        diagnostics: list[KernelDiagnostic] = []
        probes, ambiguous_probes = _index_driver_probes(
            driver_probe_snapshots, diagnostics
        )
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
        validated_capabilities = [
            (capability, validate_capability_manifest(capability))
            for capability in capabilities
        ]
        resolvable_capabilities = [
            capability
            for capability, manifest_diagnostics in validated_capabilities
            if _is_supported_capability(capability)
            and _can_resolve_capability(capability, manifest_diagnostics)
        ]
        permission_grants = [
            PermissionGrant(capability_id=capability.id, permission=permission)
            for capability in resolvable_capabilities
            for permission in capability.permissions
        ]
        connection_requirements = [
            ConnectionRequirement(capability_id=capability.id, connection=connection)
            for capability in resolvable_capabilities
            for connection in capability.required_connections
        ]
        driver_exposures: list[DriverExposure] = []
        resolutions: list[CapabilityResolution] = []
        for capability, manifest_diagnostics in validated_capabilities:
            resolution, exposures = _resolve_capability(
                capability,
                manifest_diagnostics,
                diagnostics,
                probes=probes,
                ambiguous_probes=ambiguous_probes,
                connections=connections,
                ambiguous_connections=ambiguous_connections,
            )
            resolutions.append(resolution)
            driver_exposures.extend(exposures)
        runtime_ready = bool(resolutions) and all(
            item.available for item in resolutions
        )
        return OSPlan(
            tenant_id=scope.tenant_id,
            request_id=request_id,
            run_id=run_id,
            scope_ref=scope.scope_ref,
            capability_resolutions=tuple(resolutions),
            permission_grants=tuple(permission_grants),
            connection_requirements=tuple(connection_requirements),
            connection_readiness=tuple(connections.values()),
            driver_probe_snapshots=tuple(probes.values()),
            driver_exposures=tuple(driver_exposures),
            diagnostics=tuple(diagnostics),
            runtime_ready=runtime_ready,
            degraded=not runtime_ready,
        )


def _resolve_capability(
    capability: object,
    manifest_diagnostics: Sequence[ValidationDiagnostic],
    diagnostics: list[KernelDiagnostic],
    *,
    probes: dict[str, DriverProbeSnapshot],
    ambiguous_probes: set[str],
    connections: dict[str, ConnectionReadiness],
    ambiguous_connections: set[str],
) -> tuple[CapabilityResolution, tuple[DriverExposure, ...]]:
    capability_id, failure_codes = _record_manifest_diagnostics(
        capability,
        manifest_diagnostics,
        diagnostics,
    )
    if not _is_resolvable_capability(capability, manifest_diagnostics):
        return _capability_resolution(capability_id, failure_codes), ()
    _record_connection_failures(
        capability.required_connections,
        failure_codes,
        diagnostics,
        connections=connections,
        ambiguous_connections=ambiguous_connections,
    )
    pending_exposures = _resolve_driver_exposures(
        capability,
        failure_codes,
        diagnostics,
        probes=probes,
        ambiguous_probes=ambiguous_probes,
    )
    resolution = _capability_resolution(capability.id, failure_codes)
    return resolution, tuple(pending_exposures) if resolution.available else ()


def _capability_resolution(
    capability_id: str,
    failure_codes: Sequence[str],
) -> CapabilityResolution:
    return CapabilityResolution(
        capability_id=capability_id,
        available=not failure_codes,
        reason=",".join(dict.fromkeys(failure_codes)),
    )


def _record_connection_failures(
    required_connections: Sequence[str],
    failure_codes: list[str],
    diagnostics: list[KernelDiagnostic],
    *,
    connections: dict[str, ConnectionReadiness],
    ambiguous_connections: set[str],
) -> None:
    for connection in required_connections:
        problem = _connection_problem(
            connection,
            connections=connections,
            ambiguous_connections=ambiguous_connections,
        )
        if problem is not None:
            code, message, severity = problem
            failure_codes.append(code)
            diagnostics.append(
                KernelDiagnostic(code=code, message=message, severity=severity)
            )


def _connection_problem(
    connection: str,
    *,
    connections: dict[str, ConnectionReadiness],
    ambiguous_connections: set[str],
) -> tuple[str, str, str] | None:
    if connection in ambiguous_connections:
        return (
            "connection_readiness_ambiguous",
            f"Connection {connection} has conflicting readiness snapshots.",
            "error",
        )
    readiness = connections.get(connection)
    if readiness is None:
        return (
            "connection_readiness_missing",
            f"Connection {connection} has no readiness snapshot.",
            "warning",
        )
    if not readiness.available:
        detail = f": {readiness.detail}" if readiness.detail else "."
        return (
            "connection_unavailable",
            f"Connection {connection} is unavailable{detail}",
            "warning",
        )
    return None


def _resolve_driver_exposures(
    capability: _CapabilityDeclaration,
    failure_codes: list[str],
    diagnostics: list[KernelDiagnostic],
    *,
    probes: dict[str, DriverProbeSnapshot],
    ambiguous_probes: set[str],
) -> list[DriverExposure]:
    exposures: list[DriverExposure] = []
    for driver in capability.drivers:
        exposure, problem = _driver_exposure_or_problem(
            capability,
            driver,
            probes=probes,
            ambiguous_probes=ambiguous_probes,
        )
        if problem is not None:
            code, message, severity = problem
            failure_codes.append(code)
            diagnostics.append(
                KernelDiagnostic(code=code, message=message, severity=severity)
            )
        elif exposure is not None:
            exposures.append(exposure)
    return exposures


def _driver_exposure_or_problem(
    capability: _CapabilityDeclaration,
    driver: DriverSpec,
    *,
    probes: dict[str, DriverProbeSnapshot],
    ambiguous_probes: set[str],
) -> tuple[DriverExposure | None, tuple[str, str, str] | None]:
    driver_id = driver_spec_id(driver)
    if not driver_id:
        return None, (
            "driver_identity_missing",
            f"Capability {capability.id} has a driver without an id.",
            "error",
        )
    permissions = driver_spec_permissions(driver)
    problem = _driver_probe_problem(
        driver,
        driver_id=driver_id,
        permissions=permissions,
        probes=probes,
        ambiguous_probes=ambiguous_probes,
    )
    if problem is not None:
        return None, problem
    return (
        DriverExposure(
            driver_id=driver_id,
            capability_id=capability.id,
            permissions=tuple(permissions),
            capabilities=tuple(driver.capabilities),
        ),
        None,
    )


def _driver_probe_problem(
    driver: DriverSpec,
    *,
    driver_id: str,
    permissions: Sequence[str],
    probes: dict[str, DriverProbeSnapshot],
    ambiguous_probes: set[str],
) -> tuple[str, str, str] | None:
    if not permissions:
        return (
            "driver_permissions_missing",
            f"Driver {driver_id} has no declared driver permissions.",
            "warning",
        )
    if driver_id in ambiguous_probes:
        return (
            "driver_probe_ambiguous",
            f"Driver {driver_id} has conflicting probe snapshots.",
            "error",
        )
    probe_snapshot = probes.get(driver_id)
    if probe_snapshot is None:
        return (
            "driver_probe_missing",
            f"Driver {driver_id} has no probe snapshot.",
            "warning",
        )
    if not probe_snapshot.available:
        detail = f": {probe_snapshot.detail}" if probe_snapshot.detail else "."
        return (
            "driver_probe_unavailable",
            f"Driver {driver_id} is unavailable{detail}",
            "warning",
        )
    if probe_snapshot.version != driver.version:
        return (
            "driver_version_mismatch",
            f"Driver {driver_id} version {probe_snapshot.version!r} does not "
            f"match required version {driver.version!r}.",
            "error",
        )
    missing = sorted(set(driver.capabilities) - set(probe_snapshot.capabilities))
    if missing:
        return (
            "driver_capability_mismatch",
            f"Driver {driver_id} is missing required capabilities: "
            + ", ".join(missing),
            "error",
        )
    return None


def _runtime_scope_from_envelope(envelope: InputEnvelope) -> RuntimeScope:
    metadata = envelope.metadata
    request_id = metadata["request_id"] if "request_id" in metadata else "request"
    run_id = metadata["run_id"] if "run_id" in metadata else request_id
    try:
        scope = RuntimeScope(
            tenant_id=envelope.tenant_id,
            run_id=run_id,
            request_id=request_id,
        )
        RuntimeScope.from_dict(scope.to_dict())
    except (TypeError, ValueError) as exc:
        raise KernelError(f"runtime scope input is invalid: {exc}") from exc
    return scope


def _is_supported_capability(value: object) -> TypeGuard[_CapabilityDeclaration]:
    return (
        isinstance(value, CapabilityManifest)
        or type(value) is ScopedCapabilityManifestV2
    )


def _record_manifest_diagnostics(
    capability: object,
    manifest_diagnostics: Sequence[ValidationDiagnostic],
    diagnostics: list[KernelDiagnostic],
) -> tuple[str, list[str]]:
    capability_id = (
        capability.id if _is_supported_capability(capability) else "<unsupported>"
    )
    failure_codes: list[str] = []
    for item in manifest_diagnostics:
        if item.level != "error":
            continue
        code = f"manifest_{item.code}"
        failure_codes.append(code)
        diagnostics.append(
            KernelDiagnostic(
                code=code,
                message=f"Capability {capability_id}: {item.message}",
                severity="error",
            )
        )
    return capability_id, failure_codes


def _is_resolvable_capability(
    capability: object,
    diagnostics: Sequence[ValidationDiagnostic],
) -> TypeGuard[_CapabilityDeclaration]:
    return _is_supported_capability(capability) and _can_resolve_capability(
        capability,
        diagnostics,
    )


def _can_resolve_capability(
    capability: _CapabilityDeclaration,
    diagnostics: Sequence[ValidationDiagnostic],
) -> bool:
    return type(capability) is not ScopedCapabilityManifestV2 or not any(
        item.level == "error" for item in diagnostics
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
