from __future__ import annotations

from collections.abc import Callable

from pheroos.conformance.report import CheckResult
from pheroos.drivers import DriverResult
from pheroos.kernel import (
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
        InputEnvelope(request="conformance kernel contract", tenant_id="conformance", metadata={"request_id": "kernel"}),
        [manifest],
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
    if any(not exposure.permissions for exposure in context.tool_exposures):
        problems.append("manifest_plan:unpermissioned_context_tool")
    return problems


def driver_permission_fallback_problems() -> list[str]:
    plan = OSKernel().plan(
        InputEnvelope(request="driver fallback", tenant_id="conformance", metadata={"request_id": "fallback"}),
        [capability_with_unpermissioned_driver()],
    )
    problems: list[str] = []
    if plan.driver_exposures:
        problems.append("driver_permission_fallback:exposed")
    if "driver_permissions_missing" not in {diagnostic.code for diagnostic in plan.diagnostics}:
        problems.append("driver_permission_fallback:missing_diagnostic")
    return problems


def materialization_boundary_problems() -> list[str]:
    ready_plan = OSPlan(
        tenant_id="conformance",
        request_id="ready",
        driver_exposures=[
            DriverExposure(driver_id="driver:blocked", capability_id="capability:test"),
            DriverExposure(driver_id="driver:allowed", capability_id="capability:test", permissions=["driver:invoke"]),
        ],
        tool_exposures=[
            ToolExposure(tool_id="tool:blocked", capability_id="capability:test"),
            ToolExposure(tool_id="tool:allowed", capability_id="capability:test", permissions=["tool:use"]),
        ],
    )
    ready_context = RuntimeMaterializer().materialize(ready_plan)
    not_ready_context = RuntimeMaterializer().materialize(
        OSPlan(
            tenant_id="conformance",
            request_id="not-ready",
            driver_exposures=[
                DriverExposure(driver_id="driver:allowed", capability_id="capability:test", permissions=["driver:invoke"]),
            ],
            tool_exposures=[
                ToolExposure(tool_id="tool:allowed", capability_id="capability:test", permissions=["tool:use"]),
            ],
            runtime_ready=False,
            degraded=True,
        )
    )

    problems: list[str] = []
    if [exposure.driver_id for exposure in ready_context.driver_exposures] != ["driver:allowed"]:
        problems.append("materializer:driver_permission_gate")
    if [exposure.tool_id for exposure in ready_context.tool_exposures] != ["tool:allowed"]:
        problems.append("materializer:tool_permission_gate")
    if not_ready_context.driver_exposures or not_ready_context.tool_exposures:
        problems.append("materializer:not_ready_exposed")
    return problems


def authority_snapshot_problems() -> list[str]:
    permissions = ["driver:invoke"]
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
            permissions=permissions,
        )
    ]
    plan = OSPlan(
        tenant_id="conformance",
        request_id="snapshot",
        permission_grants=grants,
        driver_exposures=exposures,
    )
    permissions.append("driver:admin")
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
            permissions=["driver:invoke"],
        )
    )
    context = RuntimeMaterializer().materialize(plan)

    problems: list[str] = []
    if plan.driver_exposures[0].permissions != ("driver:invoke",):
        problems.append("authority_snapshot:exposure_permissions")
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
                driver_exposures=[
                    DriverExposure(
                        driver_id="driver:allowed",
                        capability_id="capability:test",
                        permissions=["   "],
                    )
                ],
            )
        )
    ):
        problems.append("authority_snapshot:blank_permission")
    return problems


def syscall_boundary_problems() -> list[str]:
    syscalls = KernelSyscalls()
    ready_context = RuntimeContext(
        tenant_id="conformance",
        request_id="syscall",
        driver_exposures=[
            DriverExposure(driver_id="driver:allowed", capability_id="capability:test", permissions=["driver:invoke"]),
        ],
        tool_exposures=[
            ToolExposure(tool_id="tool:allowed", capability_id="capability:test", permissions=["tool:use"]),
        ],
    )
    unpermissioned_context = RuntimeContext(
        tenant_id="conformance",
        request_id="syscall",
        driver_exposures=[DriverExposure(driver_id="driver:blocked", capability_id="capability:test")],
        tool_exposures=[ToolExposure(tool_id="tool:blocked", capability_id="capability:test")],
    )
    not_ready_context = RuntimeContext(
        tenant_id="conformance",
        request_id="syscall",
        driver_exposures=[
            DriverExposure(driver_id="driver:allowed", capability_id="capability:test", permissions=["driver:invoke"]),
        ],
        tool_exposures=[
            ToolExposure(tool_id="tool:allowed", capability_id="capability:test", permissions=["tool:use"]),
        ],
        ready=False,
    )

    expectations = {
        "syscall:unexposed_driver": lambda: syscalls.invoke_driver(
            ready_context,
            DriverInvokeRequest(driver_id="driver:missing"),
            DriverResult(driver_id="driver:missing", ok=True, provenance="driver:missing"),
        ),
        "syscall:unpermissioned_driver": lambda: syscalls.invoke_driver(
            unpermissioned_context,
            DriverInvokeRequest(driver_id="driver:blocked"),
            DriverResult(driver_id="driver:blocked", ok=True, provenance="driver:blocked"),
        ),
        "syscall:driver_id_mismatch": lambda: syscalls.invoke_driver(
            ready_context,
            DriverInvokeRequest(driver_id="driver:allowed"),
            DriverResult(driver_id="driver:other", ok=True, provenance="driver:other"),
        ),
        "syscall:missing_provenance": lambda: syscalls.invoke_driver(
            ready_context,
            DriverInvokeRequest(driver_id="driver:allowed"),
            DriverResult(driver_id="driver:allowed", ok=True),
        ),
        "syscall:not_ready_driver": lambda: syscalls.invoke_driver(
            not_ready_context,
            DriverInvokeRequest(driver_id="driver:allowed"),
            DriverResult(driver_id="driver:allowed", ok=True, provenance="driver:allowed"),
        ),
        "syscall:unpermissioned_tool": lambda: syscalls.expose_tool(unpermissioned_context, "tool:blocked"),
        "syscall:not_ready_tool": lambda: syscalls.expose_tool(not_ready_context, "tool:allowed"),
    }
    return [name for name, operation in expectations.items() if not raises_kernel_error(operation)]


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
            candidates=[CandidateSpec(id="candidate:fallback", target="decision:kernel", safe_fallback=True)],
            quorum_policy=QuorumPolicy(target="decision:kernel", fallback_candidate="candidate:fallback"),
            output_policy=OutputPolicy(),
            trace_policy=TracePolicy(),
        ),
    )
