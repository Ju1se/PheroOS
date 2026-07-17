from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pheroos._immutable import freeze_abi_sequence
from pheroos.drivers.base import DriverProbeSnapshot
from pheroos.kernel._validation import validate_os_plan
from pheroos.kernel._versions import KERNEL_PLAN_VERSION_V2
from pheroos.kernel.connection import ConnectionReadiness, ConnectionRequirement
from pheroos.kernel.errors import KernelError
from pheroos.kernel.os_plan import (
    CapabilityResolution,
    DriverExposure,
    KernelDiagnostic,
    OSPlan,
    ToolExposure,
)
from pheroos.kernel.permission import PermissionGrant
from pheroos.kernel.run_scope import RuntimeScope


_V1_FIELDS = frozenset(
    {
        "tenant_id",
        "request_id",
        "capability_resolutions",
        "permission_grants",
        "connection_requirements",
        "driver_exposures",
        "tool_exposures",
        "diagnostics",
        "runtime_ready",
        "degraded",
    }
)
_V2_FIELDS = _V1_FIELDS | {
    "plan_version",
    "run_id",
    "scope_ref",
    "connection_readiness",
    "driver_probe_snapshots",
}


class KernelPlanVersionError(ValueError):
    """A Kernel plan document cannot be selected or upgraded safely."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


@dataclass(frozen=True)
class LegacyOSPlan:
    """Typed, non-authoritative representation of the frozen v1 wire shape."""

    tenant_id: str
    request_id: str
    capability_resolutions: tuple[CapabilityResolution, ...] = field(
        default_factory=tuple
    )
    permission_grants: tuple[PermissionGrant, ...] = field(default_factory=tuple)
    connection_requirements: tuple[ConnectionRequirement, ...] = field(
        default_factory=tuple
    )
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


@dataclass(frozen=True)
class OSPlanDocument:
    """Versioned wire document for an authority-safe v2 OSPlan."""

    plan: OSPlan
    plan_version: str = KERNEL_PLAN_VERSION_V2

    def __post_init__(self) -> None:
        if self.plan_version != KERNEL_PLAN_VERSION_V2:
            raise KernelPlanVersionError(
                "kernel_plan_version_unsupported",
                "kernel plan version is unsupported",
                path="$.plan_version",
            )
        try:
            validate_os_plan(self.plan)
        except KernelError as exc:
            raise KernelPlanVersionError(
                "kernel_plan_v2_invalid",
                f"kernel plan does not satisfy v2 invariants: {exc}",
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        plan = self.plan
        return {
            "plan_version": self.plan_version,
            "tenant_id": plan.tenant_id,
            "request_id": plan.request_id,
            "run_id": plan.run_id,
            "scope_ref": plan.scope_ref,
            "capability_resolutions": [
                {
                    "capability_id": item.capability_id,
                    "available": item.available,
                    "reason": item.reason,
                }
                for item in plan.capability_resolutions
            ],
            "permission_grants": [
                {
                    "capability_id": item.capability_id,
                    "permission": item.permission,
                    "granted": item.granted,
                    "reason": item.reason,
                }
                for item in plan.permission_grants
            ],
            "connection_requirements": [
                {
                    "capability_id": item.capability_id,
                    "connection": item.connection,
                    "required": item.required,
                }
                for item in plan.connection_requirements
            ],
            "connection_readiness": [
                {
                    "connection": item.connection,
                    "available": item.available,
                    "detail": item.detail,
                }
                for item in plan.connection_readiness
            ],
            "driver_probe_snapshots": [
                {
                    "driver_id": item.driver_id,
                    "available": item.available,
                    "detail": item.detail,
                    "version": item.version,
                    "capabilities": list(item.capabilities),
                }
                for item in plan.driver_probe_snapshots
            ],
            "driver_exposures": [
                {
                    "driver_id": item.driver_id,
                    "capability_id": item.capability_id,
                    "permissions": list(item.permissions),
                    "capabilities": list(item.capabilities),
                }
                for item in plan.driver_exposures
            ],
            "tool_exposures": [
                {
                    "tool_id": item.tool_id,
                    "capability_id": item.capability_id,
                    "permissions": list(item.permissions),
                }
                for item in plan.tool_exposures
            ],
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity,
                }
                for item in plan.diagnostics
            ],
            "runtime_ready": plan.runtime_ready,
            "degraded": plan.degraded,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> OSPlanDocument:
        return os_plan_from_dict(payload)


def os_plan_v1_from_dict(payload: Mapping[str, Any]) -> LegacyOSPlan:
    """Read v1 for compatibility inspection without synthesizing run authority."""

    value = _exact_object(payload, _V1_FIELDS, "kernel plan v1")
    return LegacyOSPlan(
        tenant_id=_text(value, "tenant_id"),
        request_id=_text(value, "request_id"),
        capability_resolutions=_capability_resolutions(
            value["capability_resolutions"]
        ),
        permission_grants=_permission_grants(value["permission_grants"]),
        connection_requirements=_connection_requirements(
            value["connection_requirements"]
        ),
        driver_exposures=_driver_exposures(
            value["driver_exposures"],
            versioned=False,
        ),
        tool_exposures=_tool_exposures(value["tool_exposures"]),
        diagnostics=_diagnostics(value["diagnostics"]),
        runtime_ready=_boolean(value, "runtime_ready"),
        degraded=_boolean(value, "degraded"),
    )


def os_plan_from_dict(payload: Mapping[str, Any]) -> OSPlanDocument:
    """Read an authoritative v2 plan by exact discriminator dispatch."""

    if not isinstance(payload, Mapping):
        raise KernelPlanVersionError(
            "kernel_plan_document_invalid",
            "kernel plan document must be an object",
        )
    if "plan_version" not in payload:
        raise KernelPlanVersionError(
            "kernel_plan_version_missing",
            "kernel plan version is required",
            path="$.plan_version",
        )
    if payload["plan_version"] != KERNEL_PLAN_VERSION_V2:
        raise KernelPlanVersionError(
            "kernel_plan_version_unsupported",
            "kernel plan version is unsupported",
            path="$.plan_version",
        )
    value = _exact_object(payload, _V2_FIELDS, "kernel plan v2")
    plan = OSPlan(
        tenant_id=_text(value, "tenant_id"),
        request_id=_text(value, "request_id"),
        run_id=_text(value, "run_id"),
        scope_ref=_text(value, "scope_ref"),
        capability_resolutions=_capability_resolutions(
            value["capability_resolutions"]
        ),
        permission_grants=_permission_grants(value["permission_grants"]),
        connection_requirements=_connection_requirements(
            value["connection_requirements"]
        ),
        connection_readiness=_connection_readiness(value["connection_readiness"]),
        driver_probe_snapshots=_driver_probes(value["driver_probe_snapshots"]),
        driver_exposures=_driver_exposures(
            value["driver_exposures"],
            versioned=True,
        ),
        tool_exposures=_tool_exposures(value["tool_exposures"]),
        diagnostics=_diagnostics(value["diagnostics"]),
        runtime_ready=_boolean(value, "runtime_ready"),
        degraded=_boolean(value, "degraded"),
    )
    return OSPlanDocument(plan=plan, plan_version=value["plan_version"])


def upgrade_os_plan_v1(
    value: Mapping[str, Any] | LegacyOSPlan,
    *,
    run_id: str,
    scope_ref: str,
    connection_readiness: Sequence[ConnectionReadiness],
    driver_probe_snapshots: Sequence[DriverProbeSnapshot],
    driver_capabilities: Mapping[str, Sequence[str]],
    driver_versions: Mapping[str, str],
) -> OSPlanDocument:
    """Upgrade only when the caller supplies all authority-bearing v2 facts."""

    legacy = value if isinstance(value, LegacyOSPlan) else os_plan_v1_from_dict(value)
    try:
        scope = RuntimeScope(
            tenant_id=legacy.tenant_id,
            run_id=run_id,
            request_id=legacy.request_id,
            scope_ref=scope_ref,
        )
    except ValueError as exc:
        raise KernelPlanVersionError(
            "kernel_plan_v1_scope_invalid",
            f"legacy plan upgrade scope is invalid: {exc}",
            path="$.scope_ref",
        ) from exc

    readiness = _index_readiness(connection_readiness)
    probes = _index_probes(driver_probe_snapshots)
    for requirement in legacy.connection_requirements:
        snapshot = readiness.get(requirement.connection)
        if snapshot is None:
            raise KernelPlanVersionError(
                "kernel_plan_v1_readiness_missing",
                f"legacy plan upgrade is missing readiness for {requirement.connection}",
            )
        if legacy.runtime_ready and requirement.required and not snapshot.available:
            raise KernelPlanVersionError(
                "kernel_plan_v1_readiness_conflict",
                f"legacy ready plan has unavailable connection {requirement.connection}",
            )

    exposures: list[DriverExposure] = []
    for exposure in legacy.driver_exposures:
        capabilities = driver_capabilities.get(exposure.driver_id)
        provider_version = driver_versions.get(exposure.driver_id)
        probe = probes.get(exposure.driver_id)
        if capabilities is None or provider_version is None or probe is None:
            raise KernelPlanVersionError(
                "kernel_plan_v1_driver_authority_missing",
                f"legacy plan upgrade lacks driver authority for {exposure.driver_id}",
            )
        canonical_capabilities = _canonical_text_sequence(
            capabilities,
            f"driver capabilities for {exposure.driver_id}",
        )
        if probe.version != provider_version:
            raise KernelPlanVersionError(
                "kernel_plan_v1_driver_version_conflict",
                f"legacy plan driver version conflicts with probe for {exposure.driver_id}",
            )
        if legacy.runtime_ready and not probe.available:
            raise KernelPlanVersionError(
                "kernel_plan_v1_driver_unavailable",
                f"legacy ready plan has unavailable driver {exposure.driver_id}",
            )
        if not set(canonical_capabilities).issubset(probe.capabilities):
            raise KernelPlanVersionError(
                "kernel_plan_v1_driver_capability_conflict",
                f"legacy plan driver capabilities conflict with probe for {exposure.driver_id}",
            )
        exposures.append(
            DriverExposure(
                driver_id=exposure.driver_id,
                capability_id=exposure.capability_id,
                permissions=exposure.permissions,
                capabilities=canonical_capabilities,
            )
        )

    plan = OSPlan(
        tenant_id=legacy.tenant_id,
        request_id=legacy.request_id,
        run_id=scope.run_id,
        scope_ref=scope.scope_ref,
        capability_resolutions=legacy.capability_resolutions,
        permission_grants=legacy.permission_grants,
        connection_requirements=legacy.connection_requirements,
        connection_readiness=tuple(readiness.values()),
        driver_probe_snapshots=tuple(probes.values()),
        driver_exposures=exposures,
        tool_exposures=legacy.tool_exposures,
        diagnostics=legacy.diagnostics,
        runtime_ready=legacy.runtime_ready,
        degraded=legacy.degraded,
    )
    return OSPlanDocument(plan=plan)


def _capability_resolutions(value: Any) -> tuple[CapabilityResolution, ...]:
    return tuple(
        CapabilityResolution(
            capability_id=_text(item, "capability_id"),
            available=_boolean(item, "available"),
            reason=_text(item, "reason", default=""),
        )
        for item in _object_array(value, "capability_resolutions")
        if not _reject_unknown(
            item,
            {"capability_id", "available", "reason"},
            "capability resolution",
        )
    )


def _permission_grants(value: Any) -> tuple[PermissionGrant, ...]:
    return tuple(
        PermissionGrant(
            capability_id=_text(item, "capability_id"),
            permission=_text(item, "permission"),
            granted=_boolean(item, "granted", default=True),
            reason=_text(item, "reason", default=""),
        )
        for item in _object_array(value, "permission_grants")
        if not _reject_unknown(
            item,
            {"capability_id", "permission", "granted", "reason"},
            "permission grant",
        )
    )


def _connection_requirements(value: Any) -> tuple[ConnectionRequirement, ...]:
    return tuple(
        ConnectionRequirement(
            capability_id=_text(item, "capability_id"),
            connection=_text(item, "connection"),
            required=_boolean(item, "required", default=True),
        )
        for item in _object_array(value, "connection_requirements")
        if not _reject_unknown(
            item,
            {"capability_id", "connection", "required"},
            "connection requirement",
        )
    )


def _connection_readiness(value: Any) -> tuple[ConnectionReadiness, ...]:
    return tuple(
        ConnectionReadiness(
            connection=_text(item, "connection"),
            available=_boolean(item, "available"),
            detail=_text(item, "detail", default=""),
        )
        for item in _object_array(value, "connection_readiness")
        if not _reject_unknown(
            item,
            {"connection", "available", "detail"},
            "connection readiness",
        )
    )


def _driver_probes(value: Any) -> tuple[DriverProbeSnapshot, ...]:
    return tuple(
        DriverProbeSnapshot(
            driver_id=_text(item, "driver_id"),
            available=_boolean(item, "available"),
            detail=_text(item, "detail", default=""),
            version=_text(item, "version"),
            capabilities=_text_array(item, "capabilities"),
        )
        for item in _object_array(value, "driver_probe_snapshots")
        if not _reject_unknown(
            item,
            {"driver_id", "available", "detail", "version", "capabilities"},
            "driver probe snapshot",
        )
    )


def _driver_exposures(
    value: Any,
    *,
    versioned: bool,
) -> tuple[DriverExposure, ...]:
    allowed = {"driver_id", "capability_id", "permissions"}
    if versioned:
        allowed.add("capabilities")
    return tuple(
        DriverExposure(
            driver_id=_text(item, "driver_id"),
            capability_id=_text(item, "capability_id"),
            permissions=_text_array(item, "permissions", default=()),
            capabilities=(
                _text_array(item, "capabilities", default=())
                if versioned
                else ()
            ),
        )
        for item in _object_array(value, "driver_exposures")
        if not _reject_unknown(item, allowed, "driver exposure")
    )


def _tool_exposures(value: Any) -> tuple[ToolExposure, ...]:
    return tuple(
        ToolExposure(
            tool_id=_text(item, "tool_id"),
            capability_id=_text(item, "capability_id"),
            permissions=_text_array(item, "permissions", default=()),
        )
        for item in _object_array(value, "tool_exposures")
        if not _reject_unknown(
            item,
            {"tool_id", "capability_id", "permissions"},
            "tool exposure",
        )
    )


def _diagnostics(value: Any) -> tuple[KernelDiagnostic, ...]:
    return tuple(
        KernelDiagnostic(
            code=_text(item, "code"),
            message=_text(item, "message"),
            severity=_text(item, "severity", default="info"),
        )
        for item in _object_array(value, "diagnostics")
        if not _reject_unknown(
            item,
            {"code", "message", "severity"},
            "kernel diagnostic",
        )
    )


def _exact_object(
    value: Mapping[str, Any],
    fields: frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise KernelPlanVersionError(
            "kernel_plan_fields_invalid",
            f"{label} fields are invalid",
        )
    return value


def _object_array(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise KernelPlanVersionError(
            "kernel_plan_fields_invalid",
            f"kernel plan {label} must be an object array",
            path=f"$.{label}",
        )
    return tuple(value)


def _reject_unknown(
    value: Mapping[str, Any],
    allowed: set[str],
    label: str,
) -> bool:
    unknown = set(value) - allowed
    if unknown:
        raise KernelPlanVersionError(
            "kernel_plan_fields_invalid",
            f"{label} contains unknown fields: {', '.join(sorted(unknown))}",
        )
    return False


def _text(
    value: Mapping[str, Any],
    name: str,
    *,
    default: str | None = None,
) -> str:
    item = value.get(name, default)
    if not isinstance(item, str):
        raise KernelPlanVersionError(
            "kernel_plan_fields_invalid",
            f"kernel plan {name} must be text",
            path=f"$.{name}",
        )
    return item


def _boolean(
    value: Mapping[str, Any],
    name: str,
    *,
    default: bool | None = None,
) -> bool:
    item = value.get(name, default)
    if type(item) is not bool:
        raise KernelPlanVersionError(
            "kernel_plan_fields_invalid",
            f"kernel plan {name} must be boolean",
            path=f"$.{name}",
        )
    return item


def _text_array(
    value: Mapping[str, Any],
    name: str,
    *,
    default: Sequence[str] | None = None,
) -> tuple[str, ...]:
    item = value.get(name, list(default) if default is not None else None)
    if not isinstance(item, list) or any(not isinstance(entry, str) for entry in item):
        raise KernelPlanVersionError(
            "kernel_plan_fields_invalid",
            f"kernel plan {name} must be a string array",
            path=f"$.{name}",
        )
    return tuple(item)


def _canonical_text_sequence(value: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise KernelPlanVersionError(
            "kernel_plan_v1_driver_authority_invalid",
            f"{label} must contain nonblank strings",
        )
    result = tuple(value)
    if len(result) != len(set(result)):
        raise KernelPlanVersionError(
            "kernel_plan_v1_driver_authority_invalid",
            f"{label} must not contain duplicates",
        )
    return result


def _index_readiness(
    values: Sequence[ConnectionReadiness],
) -> dict[str, ConnectionReadiness]:
    result: dict[str, ConnectionReadiness] = {}
    for item in values:
        if not isinstance(item, ConnectionReadiness) or item.connection in result:
            raise KernelPlanVersionError(
                "kernel_plan_v1_readiness_invalid",
                "legacy plan upgrade readiness snapshots are invalid or ambiguous",
            )
        result[item.connection] = item
    return result


def _index_probes(
    values: Sequence[DriverProbeSnapshot],
) -> dict[str, DriverProbeSnapshot]:
    result: dict[str, DriverProbeSnapshot] = {}
    for item in values:
        if not isinstance(item, DriverProbeSnapshot) or item.driver_id in result:
            raise KernelPlanVersionError(
                "kernel_plan_v1_probe_invalid",
                "legacy plan upgrade driver probes are invalid or ambiguous",
            )
        result[item.driver_id] = item
    return result


__all__ = [
    "KernelPlanVersionError",
    "LegacyOSPlan",
    "OSPlanDocument",
    "os_plan_from_dict",
    "os_plan_v1_from_dict",
    "upgrade_os_plan_v1",
]
