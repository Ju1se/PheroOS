import pytest

from pheroos.drivers import DriverDescriptor, DriverRegistration, bind, declare, expose, invoke, probe, register, validate
from pheroos.drivers.errors import DriverError


def test_driver_lifecycle() -> None:
    descriptor = declare(DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0"))

    registration = register(descriptor)
    probe_result = probe(registration)
    binding = bind(registration, tenant_id="tenant-a", permissions=["tool:use"])
    handle = expose(binding)

    assert validate(descriptor) is True
    assert probe_result.available is True
    assert handle.exposed is True


def test_driver_lifecycle_rejects_invalid_descriptor() -> None:
    descriptor = DriverDescriptor(id="", kind="tool", version="")

    assert validate(descriptor) is False
    with pytest.raises(DriverError, match="invalid"):
        register(descriptor)


def test_driver_lifecycle_rejects_inactive_registration() -> None:
    registration = DriverRegistration(
        descriptor=DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0"),
        registered=False,
    )

    with pytest.raises(DriverError, match="not active"):
        bind(registration, tenant_id="tenant-a", permissions=["tool:use"])


def test_driver_lifecycle_rejects_unpermissioned_exposure_and_missing_provenance() -> None:
    descriptor = DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    registration = register(descriptor)
    binding = bind(registration, tenant_id="tenant-a", permissions=[])

    with pytest.raises(DriverError, match="no granted permissions"):
        expose(binding)

    handle = expose(bind(registration, tenant_id="tenant-a", permissions=["tool:use"]))
    with pytest.raises(DriverError, match="provenance"):
        invoke(handle, payload={"ok": True}, provenance="")
