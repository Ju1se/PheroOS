import pytest

from pheroos.drivers import DriverResult
from pheroos.kernel import DriverExposure, DriverInvokeRequest, KernelSyscalls, RuntimeContext, ToolExposure
from pheroos.kernel.errors import KernelError


def test_driver_invoke_requires_exposed_driver() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"])],
    )
    request = DriverInvokeRequest(driver_id="driver:toy", payload={"input": "ping"})
    result = DriverResult(driver_id="driver:toy", ok=True, payload={"output": "pong"}, provenance="driver:toy")

    reply = KernelSyscalls().invoke_driver(context, request, result)

    assert reply.request.payload["input"] == "ping"
    assert reply.result.provenance == "driver:toy"


def test_driver_invoke_rejects_unexposed_driver() -> None:
    context = RuntimeContext(tenant_id="tenant-a", request_id="req-1")
    request = DriverInvokeRequest(driver_id="driver:missing")
    result = DriverResult(driver_id="driver:missing", ok=True)

    with pytest.raises(KernelError):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_not_ready_context() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"])],
        ready=False,
    )
    request = DriverInvokeRequest(driver_id="driver:toy")
    result = DriverResult(driver_id="driver:toy", ok=True)

    with pytest.raises(KernelError, match="not ready"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_unpermissioned_exposure() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy")],
    )
    request = DriverInvokeRequest(driver_id="driver:toy")
    result = DriverResult(driver_id="driver:toy", ok=True)

    with pytest.raises(KernelError, match="no granted permissions"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_mismatched_result_driver() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"])],
    )
    request = DriverInvokeRequest(driver_id="driver:toy")
    result = DriverResult(driver_id="driver:other", ok=True, provenance="driver:other")

    with pytest.raises(KernelError, match="does not match"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_missing_result_provenance() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"])],
    )
    request = DriverInvokeRequest(driver_id="driver:toy")
    result = DriverResult(driver_id="driver:toy", ok=True)

    with pytest.raises(KernelError, match="provenance"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_tool_exposure_requires_ready_context_and_permissions() -> None:
    syscalls = KernelSyscalls()
    ready_context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        tool_exposures=[
            ToolExposure(tool_id="tool:allowed", capability_id="toy", permissions=["tool:use"]),
            ToolExposure(tool_id="tool:hidden", capability_id="toy"),
        ],
    )
    not_ready_context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        tool_exposures=[ToolExposure(tool_id="tool:allowed", capability_id="toy", permissions=["tool:use"])],
        ready=False,
    )

    assert syscalls.expose_tool(ready_context, "tool:allowed").tool_id == "tool:allowed"
    with pytest.raises(KernelError, match="no granted permissions"):
        syscalls.expose_tool(ready_context, "tool:hidden")
    with pytest.raises(KernelError, match="not ready"):
        syscalls.expose_tool(not_ready_context, "tool:allowed")


def test_syscall_snapshots_nested_request_and_result_payloads() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
            )
        ],
    )
    request_payload = {"nested": {"values": ["request"]}}
    result_payload = {"nested": {"values": ["result"]}}
    request = DriverInvokeRequest(driver_id="driver:toy", payload=request_payload)
    result = DriverResult(
        driver_id="driver:toy",
        ok=True,
        payload=result_payload,
        provenance="driver:toy",
    )
    request_payload["nested"]["values"].append("mutated")
    result_payload["nested"]["values"].append("mutated")

    reply = KernelSyscalls().invoke_driver(context, request, result)

    assert reply.request.payload["nested"]["values"] == ("request",)
    assert reply.result.payload["nested"]["values"] == ("result",)
    with pytest.raises(TypeError):
        reply.request.payload["forged"] = True


def test_syscall_rejects_mutable_context_and_payload_bypasses() -> None:
    exposure = DriverExposure(
        driver_id="driver:toy",
        capability_id="toy",
        permissions=["driver:invoke"],
    )
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[exposure],
    )
    request = DriverInvokeRequest(driver_id="driver:toy")
    result = DriverResult(
        driver_id="driver:toy",
        ok=True,
        provenance="driver:toy",
    )
    object.__setattr__(request, "payload", {})

    with pytest.raises(KernelError, match="immutable mapping"):
        KernelSyscalls().invoke_driver(context, request, result)

    forged_context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[exposure],
    )
    object.__setattr__(forged_context, "driver_exposures", [exposure])
    with pytest.raises(KernelError, match="must be immutable"):
        KernelSyscalls().expose_driver(forged_context, "driver:toy")


@pytest.mark.parametrize("identity", ["", "   ", 7])
def test_syscall_exposure_requires_nonblank_string_identity(identity: object) -> None:
    context = RuntimeContext(tenant_id="tenant-a", request_id="req-1")

    with pytest.raises(KernelError, match="driver id"):
        KernelSyscalls().expose_driver(context, identity)  # type: ignore[arg-type]
    with pytest.raises(KernelError, match="tool id"):
        KernelSyscalls().expose_tool(context, identity)  # type: ignore[arg-type]


def test_syscall_rejects_whitespace_result_provenance() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
            )
        ],
    )

    with pytest.raises(KernelError, match="provenance"):
        KernelSyscalls().invoke_driver(
            context,
            DriverInvokeRequest(driver_id="driver:toy"),
            DriverResult(
                driver_id="driver:toy",
                ok=True,
                provenance="   ",
            ),
        )
