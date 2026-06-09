from pheroos.drivers import DriverDescriptor, DriverRegistry


def test_driver_descriptor_registers_by_id() -> None:
    descriptor = DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0", capabilities=["invoke"])
    registry = DriverRegistry()

    registry.register(descriptor)

    assert registry.get("driver:toy") == descriptor
