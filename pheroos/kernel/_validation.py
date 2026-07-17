from __future__ import annotations

from pheroos.drivers.base import DriverProbeSnapshot
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
from pheroos.kernel.runtime_context import RuntimeContext


def is_nonblank_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_driver_exposure(exposure: object) -> None:
    if not isinstance(exposure, DriverExposure):
        raise KernelError("driver exposure is invalid")
    if not is_nonblank_text(exposure.driver_id):
        raise KernelError("driver exposure id is required")
    if not is_nonblank_text(exposure.capability_id):
        raise KernelError("driver exposure capability id is required")
    validate_permissions(exposure.permissions, subject="driver exposure")
    if not isinstance(exposure.capabilities, tuple) or not all(
        is_nonblank_text(item) for item in exposure.capabilities
    ):
        raise KernelError(
            "driver exposure capabilities must be immutable nonblank strings"
        )


def validate_tool_exposure(exposure: object) -> None:
    if not isinstance(exposure, ToolExposure):
        raise KernelError("tool exposure is invalid")
    if not is_nonblank_text(exposure.tool_id):
        raise KernelError("tool exposure id is required")
    if not is_nonblank_text(exposure.capability_id):
        raise KernelError("tool exposure capability id is required")
    validate_permissions(exposure.permissions, subject="tool exposure")


def validate_permissions(value: object, *, subject: str) -> None:
    if not isinstance(value, tuple) or not all(is_nonblank_text(item) for item in value):
        raise KernelError(f"{subject} permissions must be immutable nonblank strings")


def validate_os_plan(plan: object) -> OSPlan:
    if not isinstance(plan, OSPlan):
        raise KernelError("OS plan is invalid")
    if not is_nonblank_text(plan.tenant_id):
        raise KernelError("OS plan tenant id is required")
    if not is_nonblank_text(plan.request_id):
        raise KernelError("OS plan request id is required")
    _validate_scope(
        tenant_id=plan.tenant_id,
        run_id=plan.run_id,
        request_id=plan.request_id,
        scope_ref=plan.scope_ref,
        subject="OS plan",
    )
    if plan.runtime_ready not in (True, False) or not isinstance(plan.runtime_ready, bool):
        raise KernelError("OS plan runtime_ready must be boolean")
    if plan.degraded not in (True, False) or not isinstance(plan.degraded, bool):
        raise KernelError("OS plan degraded must be boolean")
    _validate_plan_collections(plan)
    return plan


def validate_runtime_context(context: object) -> RuntimeContext:
    if not isinstance(context, RuntimeContext):
        raise KernelError("runtime context is invalid")
    if not is_nonblank_text(context.tenant_id):
        raise KernelError("runtime context tenant id is required")
    if not is_nonblank_text(context.request_id):
        raise KernelError("runtime context request id is required")
    _validate_scope(
        tenant_id=context.tenant_id,
        run_id=context.run_id,
        request_id=context.request_id,
        scope_ref=context.scope_ref,
        subject="runtime context",
    )
    if not isinstance(context.ready, bool) or not isinstance(context.degraded, bool):
        raise KernelError("runtime context readiness flags must be boolean")
    for name in ("permission_grants", "driver_exposures", "tool_exposures"):
        if not isinstance(getattr(context, name), tuple):
            raise KernelError(f"runtime context {name} must be immutable")
    for grant in context.permission_grants:
        _validate_permission_grant(grant)
    for exposure in context.driver_exposures:
        validate_driver_exposure(exposure)
    for exposure in context.tool_exposures:
        validate_tool_exposure(exposure)
    return context


def _validate_plan_collections(plan: OSPlan) -> None:
    names = (
        "capability_resolutions",
        "permission_grants",
        "connection_requirements",
        "connection_readiness",
        "driver_probe_snapshots",
        "driver_exposures",
        "tool_exposures",
        "diagnostics",
    )
    for name in names:
        if not isinstance(getattr(plan, name), tuple):
            raise KernelError(f"OS plan {name} must be immutable")
    for resolution in plan.capability_resolutions:
        if not isinstance(resolution, CapabilityResolution):
            raise KernelError("capability resolution is invalid")
        if not is_nonblank_text(resolution.capability_id):
            raise KernelError("capability resolution id is required")
        if not isinstance(resolution.available, bool):
            raise KernelError("capability resolution availability must be boolean")
    for grant in plan.permission_grants:
        _validate_permission_grant(grant)
    for requirement in plan.connection_requirements:
        if not isinstance(requirement, ConnectionRequirement):
            raise KernelError("connection requirement is invalid")
        if not is_nonblank_text(requirement.capability_id):
            raise KernelError("connection requirement capability id is required")
        if not is_nonblank_text(requirement.connection):
            raise KernelError("connection requirement identity is required")
        if not isinstance(requirement.required, bool):
            raise KernelError("connection requirement required flag must be boolean")
    for readiness in plan.connection_readiness:
        if not isinstance(readiness, ConnectionReadiness):
            raise KernelError("connection readiness snapshot is invalid")
        if not is_nonblank_text(readiness.connection):
            raise KernelError("connection readiness identity is required")
        if not isinstance(readiness.available, bool):
            raise KernelError("connection readiness availability must be boolean")
        if not isinstance(readiness.detail, str):
            raise KernelError("connection readiness detail must be text")
    for snapshot in plan.driver_probe_snapshots:
        if not isinstance(snapshot, DriverProbeSnapshot):
            raise KernelError("driver probe snapshot is invalid")
        if not is_nonblank_text(snapshot.driver_id):
            raise KernelError("driver probe snapshot id is required")
        if not is_nonblank_text(snapshot.version):
            raise KernelError("driver probe snapshot version is required")
        if not isinstance(snapshot.available, bool):
            raise KernelError("driver probe snapshot availability must be boolean")
        if not isinstance(snapshot.detail, str):
            raise KernelError("driver probe snapshot detail must be text")
        if not isinstance(snapshot.capabilities, tuple) or not all(
            is_nonblank_text(item) for item in snapshot.capabilities
        ):
            raise KernelError(
                "driver probe snapshot capabilities must be immutable nonblank strings"
            )
    for exposure in plan.driver_exposures:
        validate_driver_exposure(exposure)
    for exposure in plan.tool_exposures:
        validate_tool_exposure(exposure)
    for diagnostic in plan.diagnostics:
        if not isinstance(diagnostic, KernelDiagnostic):
            raise KernelError("kernel diagnostic is invalid")
        if not all(
            is_nonblank_text(value)
            for value in (diagnostic.code, diagnostic.message, diagnostic.severity)
        ):
            raise KernelError("kernel diagnostic fields must be nonblank strings")


def _validate_permission_grant(grant: object) -> None:
    if not isinstance(grant, PermissionGrant):
        raise KernelError("permission grant is invalid")
    if not is_nonblank_text(grant.capability_id):
        raise KernelError("permission grant capability id is required")
    if not is_nonblank_text(grant.permission):
        raise KernelError("permission grant identity is required")
    if not isinstance(grant.granted, bool):
        raise KernelError("permission grant granted flag must be boolean")


def _validate_scope(
    *,
    tenant_id: object,
    run_id: object,
    request_id: object,
    scope_ref: object,
    subject: str,
) -> None:
    try:
        scope = RuntimeScope(
            tenant_id=tenant_id,  # type: ignore[arg-type]
            run_id=run_id,  # type: ignore[arg-type]
            request_id=request_id,  # type: ignore[arg-type]
            scope_ref=scope_ref,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise KernelError(f"{subject} scope is invalid: {exc}") from exc
    if scope.scope_ref != scope_ref:
        raise KernelError(f"{subject} scope_ref is not canonical")


__all__ = [
    "is_nonblank_text",
    "validate_driver_exposure",
    "validate_os_plan",
    "validate_runtime_context",
    "validate_tool_exposure",
]
