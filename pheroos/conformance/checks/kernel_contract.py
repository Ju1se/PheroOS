from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from pheroos.conformance.report import CheckResult
from pheroos.drivers import DriverProbeSnapshot, DriverResult
from pheroos.kernel import (
    ConnectionReadiness,
    DriverExposure,
    DriverInvokeRequest,
    InputEnvelope,
    KernelSyscalls,
    OSKernel,
    OSPlan,
    PermissionGrant,
    RuntimeContext,
    RuntimeMaterializer,
    ToolExposure,
)
from pheroos.kernel.errors import KernelError
from pheroos.protocol.models import (
    CandidateSpec,
    CapabilityManifest,
    DriverSpec,
    OutputPolicy,
    ProtocolManifest,
    QuorumPolicy,
    TargetSpec,
    TracePolicy,
)


def check(manifest: CapabilityManifest) -> CheckResult:
    problems: list[str] = []
    problems.extend(manifest_plan_problems(manifest))
    problems.extend(driver_permission_fallback_problems())
    problems.extend(materialization_boundary_problems())
    problems.extend(authority_snapshot_problems())
    problems.extend(syscall_boundary_problems())
    return CheckResult("kernel_contract", not problems, ", ".join(problems))


def manifest_plan_problems(manifest: CapabilityManifest) -> list[str]:
    plan = OSKernel().plan(
        InputEnvelope(
            request="conformance kernel contract",
            tenant_id="conformance",
            metadata={"request_id": "kernel"},
        ),
        [manifest],
        driver_probe_snapshots=[
            DriverProbeSnapshot(
                driver_id=driver.id,
                available=True,
                version=driver.version,
                capabilities=tuple(driver.capabilities),
            )
            for driver in manifest.drivers
        ],
        connection_readiness=[
            ConnectionReadiness(connection=connection, available=True)
            for connection in manifest.required_connections
        ],
    )
    problems = plan_authority_problems(plan)
    problems.extend(manifest_context_problems(plan))
    return problems


def plan_authority_problems(plan: OSPlan) -> list[str]:
    problems: list[str] = []
    if not plan.runtime_ready:
        problems.append("plan:not_ready")
    if any(not exposure.permissions for exposure in plan.driver_exposures):
        problems.append("plan:unpermissioned_driver_exposure")
    if any(not exposure.capabilities for exposure in plan.driver_exposures):
        problems.append("plan:uncapable_driver_exposure")
    if any(not exposure.permissions for exposure in plan.tool_exposures):
        problems.append("plan:unpermissioned_tool_exposure")
    return problems


def manifest_context_problems(plan: OSPlan) -> list[str]:
    context = RuntimeMaterializer().materialize(plan)
    problems: list[str] = []
    if context.ready != plan.runtime_ready:
        problems.append("manifest_plan:context_ready_mismatch")
    if any(not exposure.permissions for exposure in context.driver_exposures):
        problems.append("manifest_plan:unpermissioned_context_driver")
    if tuple(context.driver_exposures) != tuple(plan.driver_exposures):
        problems.append("manifest_plan:driver_exposure_binding_mismatch")
    if any(not exposure.permissions for exposure in context.tool_exposures):
        problems.append("manifest_plan:unpermissioned_context_tool")
    return problems


def driver_permission_fallback_problems() -> list[str]:
    plan = OSKernel().plan(
        InputEnvelope(
            request="driver fallback",
            tenant_id="conformance",
            metadata={"request_id": "fallback"},
        ),
        [capability_with_unpermissioned_driver()],
    )
    problems: list[str] = []
    if plan.driver_exposures:
        problems.append("driver_permission_fallback:exposed")
    if "driver_permissions_missing" not in {
        diagnostic.code for diagnostic in plan.diagnostics
    }:
        problems.append("driver_permission_fallback:missing_diagnostic")
    return problems


def materialization_boundary_problems() -> list[str]:
    ready_plan = OSPlan(
        tenant_id="conformance",
        request_id="ready",
        driver_exposures=(
            DriverExposure(
                driver_id="driver:blocked",
                capability_id="capability:test",
                capabilities=("evidence:read",),
            ),
            DriverExposure(
                driver_id="driver:allowed",
                capability_id="capability:test",
                permissions=("driver:invoke",),
                capabilities=("evidence:read",),
            ),
        ),
        tool_exposures=(
            ToolExposure(tool_id="tool:blocked", capability_id="capability:test"),
            ToolExposure(
                tool_id="tool:allowed",
                capability_id="capability:test",
                permissions=("tool:use",),
            ),
        ),
    )
    ready_context = RuntimeMaterializer().materialize(ready_plan)
    not_ready_context = RuntimeMaterializer().materialize(
        OSPlan(
            tenant_id="conformance",
            request_id="not-ready",
            driver_exposures=(
                DriverExposure(
                    driver_id="driver:allowed",
                    capability_id="capability:test",
                    permissions=("driver:invoke",),
                    capabilities=("evidence:read",),
                ),
            ),
            tool_exposures=(
                ToolExposure(
                    tool_id="tool:allowed",
                    capability_id="capability:test",
                    permissions=("tool:use",),
                ),
            ),
            runtime_ready=False,
            degraded=True,
        )
    )

    problems: list[str] = []
    if [exposure.driver_id for exposure in ready_context.driver_exposures] != [
        "driver:allowed"
    ]:
        problems.append("materializer:driver_permission_gate")
    if [exposure.tool_id for exposure in ready_context.tool_exposures] != [
        "tool:allowed"
    ]:
        problems.append("materializer:tool_permission_gate")
    if not_ready_context.driver_exposures or not_ready_context.tool_exposures:
        problems.append("materializer:not_ready_exposed")
    return problems


def authority_snapshot_problems() -> list[str]:
    permissions = ["driver:invoke"]
    capabilities = ["evidence:read"]
    grants = [
        PermissionGrant(
            capability_id="capability:test",
            permission="driver:invoke",
        )
    ]
    exposures = [
        DriverExposure(
            driver_id="driver:allowed",
            capability_id="capability:test",
            permissions=cast(tuple[str, ...], permissions),
            capabilities=cast(tuple[str, ...], capabilities),
        )
    ]
    plan = OSPlan(
        tenant_id="conformance",
        request_id="snapshot",
        permission_grants=cast(tuple[PermissionGrant, ...], grants),
        driver_exposures=cast(tuple[DriverExposure, ...], exposures),
    )
    permissions.append("driver:admin")
    capabilities.append("evidence:write")
    grants.append(
        PermissionGrant(
            capability_id="capability:test",
            permission="driver:admin",
        )
    )
    exposures.append(
        DriverExposure(
            driver_id="driver:forged",
            capability_id="capability:test",
            permissions=("driver:invoke",),
            capabilities=("evidence:read",),
        )
    )
    context = RuntimeMaterializer().materialize(plan)

    problems: list[str] = []
    if plan.driver_exposures[0].permissions != ("driver:invoke",):
        problems.append("authority_snapshot:exposure_permissions")
    if plan.driver_exposures[0].capabilities != ("evidence:read",):
        problems.append("authority_snapshot:exposure_capabilities")
    if len(plan.permission_grants) != 1 or len(plan.driver_exposures) != 1:
        problems.append("authority_snapshot:plan_collections")
    if not isinstance(context.driver_exposures, tuple):
        problems.append("authority_snapshot:context_collections")

    forged_plan = OSPlan(tenant_id="conformance", request_id="forged")
    object.__setattr__(forged_plan, "driver_exposures", [])
    if not raises_kernel_error(lambda: RuntimeMaterializer().materialize(forged_plan)):
        problems.append("authority_snapshot:mutable_plan_bypass")
    if not raises_kernel_error(
        lambda: RuntimeMaterializer().materialize(
            OSPlan(tenant_id="   ", request_id="blank-tenant")
        )
    ):
        problems.append("authority_snapshot:blank_tenant")
    if not raises_kernel_error(
        lambda: RuntimeMaterializer().materialize(
            OSPlan(
                tenant_id="conformance",
                request_id="blank-permission",
                driver_exposures=(
                    DriverExposure(
                        driver_id="driver:allowed",
                        capability_id="capability:test",
                        permissions=("   ",),
                        capabilities=("evidence:read",),
                    ),
                ),
            )
        )
    ):
        problems.append("authority_snapshot:blank_permission")
    return problems


def syscall_boundary_problems() -> list[str]:
    syscalls = KernelSyscalls()
    ready_context = RuntimeContext(
        tenant_id="conformance",
        run_id="run:syscall",
        request_id="syscall",
        driver_exposures=(
            DriverExposure(
                driver_id="driver:allowed",
                capability_id="capability:test",
                permissions=("driver:invoke",),
                capabilities=("evidence:read",),
            ),
        ),
        tool_exposures=(
            ToolExposure(
                tool_id="tool:allowed",
                capability_id="capability:test",
                permissions=("tool:use",),
            ),
        ),
    )
    unpermissioned_context = RuntimeContext(
        tenant_id="conformance",
        run_id="run:syscall",
        request_id="syscall",
        driver_exposures=(
            DriverExposure(
                driver_id="driver:blocked",
                capability_id="capability:test",
                capabilities=("evidence:read",),
            ),
        ),
        tool_exposures=(
            ToolExposure(tool_id="tool:blocked", capability_id="capability:test"),
        ),
    )
    not_ready_context = RuntimeContext(
        tenant_id="conformance",
        run_id="run:syscall",
        request_id="syscall",
        driver_exposures=(
            DriverExposure(
                driver_id="driver:allowed",
                capability_id="capability:test",
                permissions=("driver:invoke",),
                capabilities=("evidence:read",),
            ),
        ),
        tool_exposures=(
            ToolExposure(
                tool_id="tool:allowed",
                capability_id="capability:test",
                permissions=("tool:use",),
            ),
        ),
        ready=False,
    )
    foreign_context = RuntimeContext(
        tenant_id="other-tenant",
        run_id="run:syscall",
        request_id="syscall",
    )

    valid_request = _driver_invoke_request(ready_context)
    valid_result = _driver_result_for_request(valid_request)
    problems: list[str] = []
    try:
        reply = syscalls.invoke_driver(ready_context, valid_request, valid_result)
    except KernelError:
        problems.append("syscall:valid_binding_rejected")
    else:
        if reply.request != valid_request or reply.result != valid_result:
            problems.append("syscall:valid_binding_not_preserved")

    missing_request = _driver_invoke_request(
        ready_context,
        driver_id="driver:missing",
    )
    blocked_request = _driver_invoke_request(
        unpermissioned_context,
        driver_id="driver:blocked",
    )
    foreign_request = replace(
        valid_request,
        scope_ref=foreign_context.scope_ref,
        request_digest="",
    )
    unauthorized_operation = _driver_invoke_request(
        ready_context,
        operation="driver:admin",
    )
    unauthorized_capability = _driver_invoke_request(
        ready_context,
        capability="evidence:write",
    )
    conflicting_idempotent_request = replace(
        valid_request,
        payload={"request": "conflicting"},
        request_digest="",
    )

    expectations = {
        "syscall:unexposed_driver": lambda: syscalls.invoke_driver(
            ready_context,
            missing_request,
            _driver_result_for_request(missing_request),
        ),
        "syscall:unpermissioned_driver": lambda: syscalls.invoke_driver(
            unpermissioned_context,
            blocked_request,
            _driver_result_for_request(blocked_request),
        ),
        "syscall:driver_id_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(valid_result, driver_id="driver:other"),
        ),
        "syscall:missing_provenance": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(valid_result, provenance=""),
        ),
        "syscall:not_ready_driver": lambda: syscalls.invoke_driver(
            not_ready_context,
            valid_request,
            valid_result,
        ),
        "syscall:request_scope_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            foreign_request,
            _driver_result_for_request(foreign_request),
        ),
        "syscall:result_scope_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(valid_result, scope_ref=foreign_context.scope_ref),
        ),
        "syscall:result_invocation_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(valid_result, invocation_id="invoke:other"),
        ),
        "syscall:result_operation_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(valid_result, operation="driver:other"),
        ),
        "syscall:operation_not_granted": lambda: syscalls.invoke_driver(
            ready_context,
            unauthorized_operation,
            _driver_result_for_request(unauthorized_operation),
        ),
        "syscall:capability_not_exposed": lambda: syscalls.invoke_driver(
            ready_context,
            unauthorized_capability,
            _driver_result_for_request(unauthorized_capability),
        ),
        "syscall:request_digest_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            replace(valid_request, request_digest="sha256:" + "0" * 64),
            valid_result,
        ),
        "syscall:result_digest_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(valid_result, request_digest="sha256:" + "0" * 64),
        ),
        "syscall:request_version_unsupported": lambda: syscalls.invoke_driver(
            ready_context,
            replace(valid_request, version="pheroos-driver-invocation-v999"),
            valid_result,
        ),
        "syscall:result_version_unsupported": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(
                valid_result,
                invocation_version="pheroos-driver-invocation-v999",
            ),
        ),
        "syscall:idempotency_request_conflict": lambda: syscalls.invoke_driver(
            ready_context,
            conflicting_idempotent_request,
            _driver_result_for_request(conflicting_idempotent_request),
        ),
        "syscall:idempotency_result_conflict": lambda: syscalls.invoke_driver(
            ready_context,
            valid_request,
            replace(valid_result, payload={"evidence": "conflicting"}),
        ),
        "syscall:unpermissioned_tool": lambda: syscalls.expose_tool(
            unpermissioned_context, "tool:blocked"
        ),
        "syscall:not_ready_tool": lambda: syscalls.expose_tool(
            not_ready_context, "tool:allowed"
        ),
    }
    problems.extend(
        name
        for name, operation in expectations.items()
        if not raises_kernel_error(operation)
    )
    return problems


def _driver_invoke_request(
    context: RuntimeContext,
    *,
    driver_id: str = "driver:allowed",
    operation: str = "driver:invoke",
    capability: str = "evidence:read",
) -> DriverInvokeRequest:
    return DriverInvokeRequest(
        driver_id=driver_id,
        scope_ref=context.scope_ref,
        invocation_id="invoke:kernel-contract",
        operation=operation,
        capability=capability,
        idempotency_key="idempotency:kernel-contract",
        payload={"request": "kernel contract"},
    )


def _driver_result_for_request(request: DriverInvokeRequest) -> DriverResult:
    return DriverResult(
        driver_id=request.driver_id,
        ok=True,
        payload={"evidence": "provider-free"},
        provenance=request.driver_id,
        scope_ref=request.scope_ref,
        invocation_id=request.invocation_id,
        operation=request.operation,
        request_digest=request.request_digest,
    )


def raises_kernel_error(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except KernelError:
        return True
    return False


def capability_with_unpermissioned_driver() -> CapabilityManifest:
    return CapabilityManifest(
        id="capability:kernel-contract",
        name="Kernel Contract",
        version="0.1.0",
        permissions=["driver:invoke"],
        drivers=[
            DriverSpec(
                id="driver:kernel-contract",
                kind="tool",
                version="0.1.0",
                capabilities=["tool:invoke"],
                permissions=[],
            )
        ],
        protocol=ProtocolManifest(
            protocol_version="pheroos.protocol.v1",
            id="kernel.contract",
            targets=[TargetSpec(id="decision:kernel")],
            candidates=[
                CandidateSpec(
                    id="candidate:fallback",
                    target="decision:kernel",
                    safe_fallback=True,
                )
            ],
            quorum_policy=QuorumPolicy(
                target="decision:kernel", fallback_candidate="candidate:fallback"
            ),
            output_policy=OutputPolicy(),
            trace_policy=TracePolicy(),
        ),
    )
