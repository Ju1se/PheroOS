from __future__ import annotations

from typing import Any, cast

import pytest

from pheroos.drivers import DriverProbeSnapshot
from pheroos.kernel import (
    CapabilityResolution,
    ConnectionReadiness,
    ConnectionRequirement,
    DriverExposure,
    KernelDiagnostic,
    KernelSyscalls,
    OSPlan,
    PermissionGrant,
    RuntimeContext,
    RuntimeMaterializer,
    ToolExposure,
)
from pheroos.kernel.errors import KernelError


def _valid_plan(**changes: Any) -> OSPlan:
    values: dict[str, Any] = {
        "tenant_id": "tenant:validation",
        "request_id": "request:validation",
        "capability_resolutions": (
            CapabilityResolution(capability_id="capability:one", available=True),
        ),
        "permission_grants": (
            PermissionGrant(
                capability_id="capability:one",
                permission="driver:invoke",
            ),
        ),
        "connection_requirements": (
            ConnectionRequirement(
                capability_id="capability:one",
                connection="connection:one",
            ),
        ),
        "connection_readiness": (
            ConnectionReadiness(connection="connection:one", available=True),
        ),
        "driver_probe_snapshots": (
            DriverProbeSnapshot(
                driver_id="driver:one",
                available=True,
                version="1.0.0",
                capabilities=("capability:one",),
            ),
        ),
        "driver_exposures": (
            DriverExposure(
                driver_id="driver:one",
                capability_id="capability:one",
                permissions=("driver:invoke",),
                capabilities=("capability:one",),
            ),
        ),
        "tool_exposures": (
            ToolExposure(
                tool_id="tool:one",
                capability_id="capability:one",
                permissions=("tool:use",),
            ),
        ),
        "diagnostics": (
            KernelDiagnostic(
                code="ready",
                message="runtime is ready",
                severity="info",
            ),
        ),
    }
    values.update(changes)
    return OSPlan(**values)


def _materialize_rejected(plan: OSPlan, match: str) -> None:
    with pytest.raises(KernelError, match=match):
        RuntimeMaterializer().materialize(plan)


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    (
        ("tenant_id", "", "tenant id"),
        ("request_id", "", "request id"),
        ("run_id", "", "scope"),
        ("scope_ref", "", "scope_ref is not canonical"),
        ("runtime_ready", 1, "runtime_ready"),
        ("degraded", 0, "degraded"),
    ),
)
def test_materializer_rejects_invalid_plan_scalar_boundaries(
    field_name: str,
    value: object,
    match: str,
) -> None:
    plan = _valid_plan()
    object.__setattr__(plan, field_name, value)
    _materialize_rejected(plan, match)


def test_materializer_rejects_non_plan_input() -> None:
    with pytest.raises(KernelError, match="OS plan is invalid"):
        RuntimeMaterializer().materialize(cast(OSPlan, object()))


@pytest.mark.parametrize(
    "field_name",
    (
        "capability_resolutions",
        "permission_grants",
        "connection_requirements",
        "connection_readiness",
        "driver_probe_snapshots",
        "driver_exposures",
        "tool_exposures",
        "diagnostics",
    ),
)
def test_materializer_rejects_each_mutable_plan_collection(field_name: str) -> None:
    plan = _valid_plan()
    object.__setattr__(plan, field_name, list(getattr(plan, field_name)))
    _materialize_rejected(plan, "must be immutable")


@pytest.mark.parametrize(
    ("field_name", "record", "match"),
    (
        ("capability_resolutions", object(), "capability resolution is invalid"),
        (
            "capability_resolutions",
            CapabilityResolution(capability_id="", available=True),
            "resolution id",
        ),
        (
            "capability_resolutions",
            CapabilityResolution(
                capability_id="capability:one",
                available=cast(bool, 1),
            ),
            "availability",
        ),
        ("permission_grants", object(), "permission grant is invalid"),
        (
            "permission_grants",
            PermissionGrant(capability_id="", permission="driver:invoke"),
            "grant capability id",
        ),
        (
            "permission_grants",
            PermissionGrant(capability_id="capability:one", permission=""),
            "grant identity",
        ),
        (
            "permission_grants",
            PermissionGrant(
                capability_id="capability:one",
                permission="driver:invoke",
                granted=cast(bool, 1),
            ),
            "granted flag",
        ),
        ("connection_requirements", object(), "connection requirement is invalid"),
        (
            "connection_requirements",
            ConnectionRequirement(capability_id="", connection="connection:one"),
            "requirement capability id",
        ),
        (
            "connection_requirements",
            ConnectionRequirement(capability_id="capability:one", connection=""),
            "requirement identity",
        ),
        (
            "connection_requirements",
            ConnectionRequirement(
                capability_id="capability:one",
                connection="connection:one",
                required=cast(bool, 1),
            ),
            "required flag",
        ),
        ("connection_readiness", object(), "readiness snapshot is invalid"),
        (
            "connection_readiness",
            ConnectionReadiness(connection="", available=True),
            "readiness identity",
        ),
        (
            "connection_readiness",
            ConnectionReadiness(
                connection="connection:one",
                available=cast(bool, 1),
            ),
            "readiness availability",
        ),
        (
            "connection_readiness",
            ConnectionReadiness(
                connection="connection:one",
                available=True,
                detail=cast(str, object()),
            ),
            "readiness detail",
        ),
        ("driver_probe_snapshots", object(), "probe snapshot is invalid"),
        (
            "driver_probe_snapshots",
            DriverProbeSnapshot(driver_id="", available=True, version="1.0.0"),
            "snapshot id",
        ),
        (
            "driver_probe_snapshots",
            DriverProbeSnapshot(driver_id="driver:one", available=True, version=""),
            "snapshot version",
        ),
        (
            "driver_probe_snapshots",
            DriverProbeSnapshot(
                driver_id="driver:one",
                available=cast(bool, 1),
                version="1.0.0",
            ),
            "snapshot availability",
        ),
        (
            "driver_probe_snapshots",
            DriverProbeSnapshot(
                driver_id="driver:one",
                available=True,
                version="1.0.0",
                detail=cast(str, object()),
            ),
            "snapshot detail",
        ),
        (
            "driver_probe_snapshots",
            DriverProbeSnapshot(
                driver_id="driver:one",
                available=True,
                version="1.0.0",
                capabilities=("",),
            ),
            "snapshot capabilities",
        ),
        ("driver_exposures", object(), "driver exposure is invalid"),
        (
            "driver_exposures",
            DriverExposure(driver_id="", capability_id="capability:one"),
            "exposure id",
        ),
        (
            "driver_exposures",
            DriverExposure(driver_id="driver:one", capability_id=""),
            "exposure capability id",
        ),
        (
            "driver_exposures",
            DriverExposure(
                driver_id="driver:one",
                capability_id="capability:one",
                permissions=("",),
            ),
            "exposure permissions",
        ),
        (
            "driver_exposures",
            DriverExposure(
                driver_id="driver:one",
                capability_id="capability:one",
                capabilities=("",),
            ),
            "exposure capabilities",
        ),
        ("tool_exposures", object(), "tool exposure is invalid"),
        (
            "tool_exposures",
            ToolExposure(tool_id="", capability_id="capability:one"),
            "exposure id",
        ),
        (
            "tool_exposures",
            ToolExposure(tool_id="tool:one", capability_id=""),
            "exposure capability id",
        ),
        (
            "tool_exposures",
            ToolExposure(
                tool_id="tool:one",
                capability_id="capability:one",
                permissions=("",),
            ),
            "exposure permissions",
        ),
        ("diagnostics", object(), "kernel diagnostic is invalid"),
        (
            "diagnostics",
            KernelDiagnostic(code="", message="message", severity="info"),
            "diagnostic fields",
        ),
    ),
)
def test_materializer_rejects_invalid_nested_plan_records(
    field_name: str,
    record: object,
    match: str,
) -> None:
    plan = _valid_plan(**{field_name: (record,)})
    _materialize_rejected(plan, match)


def _valid_context(**changes: Any) -> RuntimeContext:
    values: dict[str, Any] = {
        "tenant_id": "tenant:validation",
        "request_id": "request:validation",
        "permission_grants": (
            PermissionGrant(
                capability_id="capability:one",
                permission="driver:invoke",
            ),
        ),
        "driver_exposures": (
            DriverExposure(
                driver_id="driver:one",
                capability_id="capability:one",
                permissions=("driver:invoke",),
                capabilities=("capability:one",),
            ),
        ),
        "tool_exposures": (
            ToolExposure(
                tool_id="tool:one",
                capability_id="capability:one",
                permissions=("tool:use",),
            ),
        ),
    }
    values.update(changes)
    return RuntimeContext(**values)


def _context_rejected(context: RuntimeContext, match: str) -> None:
    with pytest.raises(KernelError, match=match):
        KernelSyscalls().expose_driver(context, "driver:one")


def test_syscall_rejects_non_context_input() -> None:
    with pytest.raises(KernelError, match="runtime context is invalid"):
        KernelSyscalls().expose_driver(cast(RuntimeContext, object()), "driver:one")


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    (
        ("tenant_id", "", "tenant id"),
        ("request_id", "", "request id"),
        ("run_id", "", "scope"),
        ("scope_ref", "", "scope_ref is not canonical"),
        ("ready", 1, "readiness flags"),
        ("degraded", 0, "readiness flags"),
    ),
)
def test_syscall_rejects_invalid_context_scalar_boundaries(
    field_name: str,
    value: object,
    match: str,
) -> None:
    context = _valid_context()
    object.__setattr__(context, field_name, value)
    _context_rejected(context, match)


@pytest.mark.parametrize(
    "field_name",
    ("permission_grants", "driver_exposures", "tool_exposures"),
)
def test_syscall_rejects_each_mutable_context_collection(field_name: str) -> None:
    context = _valid_context()
    object.__setattr__(context, field_name, list(getattr(context, field_name)))
    _context_rejected(context, "must be immutable")


@pytest.mark.parametrize(
    ("field_name", "record", "match"),
    (
        ("permission_grants", object(), "permission grant is invalid"),
        ("driver_exposures", object(), "driver exposure is invalid"),
        ("tool_exposures", object(), "tool exposure is invalid"),
    ),
)
def test_syscall_rejects_invalid_nested_context_records(
    field_name: str,
    record: object,
    match: str,
) -> None:
    context = _valid_context(**{field_name: (record,)})
    _context_rejected(context, match)


def test_public_materializer_and_syscall_accept_complete_valid_records() -> None:
    context = RuntimeMaterializer().materialize(_valid_plan())

    assert context.ready is True
    assert (
        KernelSyscalls().expose_driver(context, "driver:one").driver_id == "driver:one"
    )
    assert KernelSyscalls().expose_tool(context, "tool:one").tool_id == "tool:one"
