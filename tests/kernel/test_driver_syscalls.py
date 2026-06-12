import pytest

from pheroos.drivers import DriverResult
from pheroos.kernel import DriverExposure, DriverInvokeRequest, KernelSyscalls, RuntimeContext
from pheroos.kernel.errors import KernelError


def test_driver_invoke_requires_exposed_driver() -> None:
    context = RuntimeContext(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy")],
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
