from pheroos.drivers import DriverDescriptor, bind, declare, expose, probe, register, validate


def test_driver_lifecycle() -> None:
    descriptor = declare(DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0"))

    registration = register(descriptor)
    probe_result = probe(registration)
    binding = bind(registration, tenant_id="tenant-a", permissions=["tool:use"])
    handle = expose(binding)

    assert validate(descriptor) is True
    assert probe_result.available is True
    assert handle.exposed is True
