from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from pheroos.drivers import DriverInvocationLedger, DriverResult
from pheroos.kernel import DriverExposure, DriverInvokeRequest, KernelSyscalls, RuntimeContext, ToolExposure
from pheroos.kernel.errors import KernelError


def invocation_request(
    context: RuntimeContext,
    *,
    driver_id: str = "driver:toy",
    payload: dict[str, object] | None = None,
    operation: str = "driver:invoke",
    capability: str = "tool:invoke",
) -> DriverInvokeRequest:
    return DriverInvokeRequest(
        driver_id=driver_id,
        scope_ref=context.scope_ref,
        invocation_id="invoke-1",
        operation=operation,
        capability=capability,
        idempotency_key="idempotency-1",
        payload=payload or {},
    )


def invocation_result(
    request: DriverInvokeRequest,
    *,
    driver_id: str | None = None,
    payload: dict[str, object] | None = None,
    provenance: str = "driver:toy",
    scope_ref: str | None = None,
) -> DriverResult:
    return DriverResult(
        driver_id=driver_id or request.driver_id,
        ok=True,
        payload=payload or {},
        provenance=provenance,
        scope_ref=scope_ref or request.scope_ref,
        invocation_id=request.invocation_id,
        operation=request.operation,
        request_digest=request.request_digest,
    )


def test_driver_invoke_requires_exposed_driver() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"], capabilities=["tool:invoke"])],
    )
    request = invocation_request(context, payload={"input": "ping"})
    result = invocation_result(request, payload={"output": "pong"})

    reply = KernelSyscalls().invoke_driver(context, request, result)

    assert reply.request.payload["input"] == "ping"
    assert reply.result.provenance == "driver:toy"


def test_driver_invoke_rejects_unexposed_driver() -> None:
    context = RuntimeContext(tenant_id="tenant-a", request_id="req-1")
    request = invocation_request(context, driver_id="driver:missing")
    result = invocation_result(request, provenance="driver:missing")

    with pytest.raises(KernelError):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_not_ready_context() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"], capabilities=["tool:invoke"])],
        ready=False,
    )
    request = invocation_request(context)
    result = invocation_result(request)

    with pytest.raises(KernelError, match="not ready"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_unpermissioned_exposure() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", capabilities=["tool:invoke"])],
    )
    request = invocation_request(context)
    result = invocation_result(request)

    with pytest.raises(KernelError, match="no granted permissions"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_mismatched_result_driver() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"], capabilities=["tool:invoke"])],
    )
    request = invocation_request(context)
    result = invocation_result(request, driver_id="driver:other", provenance="driver:other")

    with pytest.raises(KernelError, match="does not match"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_missing_result_provenance() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"], capabilities=["tool:invoke"])],
    )
    request = invocation_request(context)
    result = invocation_result(request, provenance="")

    with pytest.raises(KernelError, match="provenance"):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_cross_scope_result() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        run_id="run-1",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
                capabilities=["tool:invoke"],
            )
        ],
    )
    foreign = RuntimeContext(
        tenant_id="tenant-b",
        run_id="run-1",
        request_id="req-1",
    )
    request = invocation_request(context)
    result = invocation_result(request, scope_ref=foreign.scope_ref)

    with pytest.raises(KernelError, match="result scope"):
        KernelSyscalls().invoke_driver(context, request, result)


@pytest.mark.parametrize(
    ("operation", "capability", "message"),
    [
        ("driver:delete", "tool:invoke", "operation is not granted"),
        ("driver:invoke", "tool:admin", "capability is not exposed"),
    ],
)
def test_driver_invoke_rejects_undeclared_operation_or_capability(
    operation: str,
    capability: str,
    message: str,
) -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
                capabilities=["tool:invoke"],
            )
        ],
    )
    request = invocation_request(context, operation=operation, capability=capability)
    result = invocation_result(request)

    with pytest.raises(KernelError, match=message):
        KernelSyscalls().invoke_driver(context, request, result)


def test_driver_invoke_rejects_request_and_result_digest_mismatch() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
                capabilities=["tool:invoke"],
            )
        ],
    )
    canonical = invocation_request(context, payload={"value": 1})
    request = DriverInvokeRequest(
        driver_id=canonical.driver_id,
        scope_ref=canonical.scope_ref,
        invocation_id=canonical.invocation_id,
        operation=canonical.operation,
        capability=canonical.capability,
        idempotency_key=canonical.idempotency_key,
        payload={"value": 2},
        request_digest=canonical.request_digest,
    )
    valid_result = invocation_result(canonical)

    with pytest.raises(KernelError, match="request digest"):
        KernelSyscalls().invoke_driver(context, request, valid_result)

    request = invocation_request(context)
    forged_result = invocation_result(request)
    object.__setattr__(forged_result, "request_digest", "sha256:forged")
    with pytest.raises(KernelError, match="result digest"):
        KernelSyscalls().invoke_driver(context, request, forged_result)


def test_driver_invoke_is_idempotent_and_rejects_key_reuse_conflicts() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
                capabilities=["tool:invoke"],
            )
        ],
    )
    ledger = DriverInvocationLedger()
    syscalls = KernelSyscalls(ledger)
    request = invocation_request(context, payload={"value": 1})
    result = invocation_result(request, payload={"value": "one"})

    first = syscalls.invoke_driver(context, request, result)
    retry = syscalls.invoke_driver(context, request, result)

    assert retry == first
    assert len(ledger.receipts) == 1

    conflicting_request = invocation_request(context, payload={"value": 2})
    with pytest.raises(KernelError, match="idempotency conflict"):
        syscalls.invoke_driver(
            context,
            conflicting_request,
            invocation_result(conflicting_request, payload={"value": "two"}),
        )

    conflicting_result = invocation_result(request, payload={"value": "forged"})
    with pytest.raises(KernelError, match="idempotency conflict"):
        syscalls.invoke_driver(context, request, conflicting_result)


def test_driver_invoke_idempotency_claim_is_atomic_for_concurrent_retries() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
                capabilities=["tool:invoke"],
            )
        ],
    )
    ledger = DriverInvocationLedger()
    syscalls = KernelSyscalls(ledger)
    request = invocation_request(context, payload={"value": 1})
    result = invocation_result(request, payload={"value": "one"})

    with ThreadPoolExecutor(max_workers=32) as pool:
        replies = tuple(
            pool.map(
                lambda _: syscalls.invoke_driver(context, request, result),
                range(32),
            )
        )

    assert all(reply == replies[0] for reply in replies)
    assert len(ledger.receipts) == 1


def test_driver_invoke_rejects_unknown_request_and_result_versions() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
                capabilities=["tool:invoke"],
            )
        ],
    )
    request = invocation_request(context)
    result = invocation_result(request)

    with pytest.raises(KernelError, match="request version"):
        KernelSyscalls().invoke_driver(
            context,
            replace(request, version="pheroos-driver-invocation-v999"),
            result,
        )
    with pytest.raises(KernelError, match="result invocation version"):
        KernelSyscalls().invoke_driver(
            context,
            request,
            replace(result, invocation_version="pheroos-driver-invocation-v999"),
        )


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
                capabilities=["tool:invoke"],
            )
        ],
    )
    request_payload = {"nested": {"values": ["request"]}}
    result_payload = {"nested": {"values": ["result"]}}
    request = invocation_request(context, payload=request_payload)
    result = invocation_result(request, payload=result_payload)
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
        capabilities=["tool:invoke"],
    )
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[exposure],
    )
    request = invocation_request(context)
    result = invocation_result(request)
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
                capabilities=["tool:invoke"],
            )
        ],
    )

    with pytest.raises(KernelError, match="provenance"):
        request = invocation_request(context)
        KernelSyscalls().invoke_driver(
            context,
            request,
            invocation_result(request, provenance="   "),
        )
