import pytest

from pheroos.drivers import DriverDescriptor, bind, declare, expose, invoke, register
from pheroos.drivers.errors import DriverError


def test_driver_invoke_returns_result_with_provenance() -> None:
    descriptor = declare(DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0"))
    registration = register(descriptor)
    handle = expose(bind(registration, tenant_id="tenant-a", permissions=["driver:invoke"]))

    result = invoke(handle, payload={"value": "ok"}, provenance="driver:toy")

    assert result.ok is True
    assert result.payload["value"] == "ok"
    assert result.provenance == "driver:toy"


def test_driver_invoke_rejects_unexposed_handle() -> None:
    descriptor = declare(DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0"))
    registration = register(descriptor)
    handle = expose(bind(registration, tenant_id="tenant-a", permissions=[]))

    with pytest.raises(DriverError):
        invoke(handle, payload={}, provenance="driver:toy")
