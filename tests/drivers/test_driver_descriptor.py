import pytest

from pheroos.drivers import DriverDescriptor, DriverRegistry, register, validate
from pheroos.drivers.errors import DriverError


def test_driver_descriptor_registers_by_id() -> None:
    descriptor = DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0", capabilities=["invoke"])
    registry = DriverRegistry()

    registry.register(descriptor)

    assert registry.get("driver:toy") == descriptor


@pytest.mark.parametrize(
    "descriptor",
    [
        DriverDescriptor(id="", kind="tool", version="0.1.0"),
        DriverDescriptor(id="   ", kind="tool", version="0.1.0"),
        DriverDescriptor(id="driver:toy", kind="", version="0.1.0"),
        DriverDescriptor(id="driver:toy", kind="\t", version="0.1.0"),
        DriverDescriptor(id="driver:toy", kind="tool", version=""),
        DriverDescriptor(id="driver:toy", kind="tool", version="\n"),
        DriverDescriptor(id=7, kind="tool", version="0.1.0"),  # type: ignore[arg-type]
        DriverDescriptor(id="driver:toy", kind=7, version="0.1.0"),  # type: ignore[arg-type]
        DriverDescriptor(id="driver:toy", kind="tool", version=7),  # type: ignore[arg-type]
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            capabilities=["invoke", "   "],
        ),
    ],
)
def test_registry_and_lifecycle_reject_the_same_invalid_descriptors(descriptor: DriverDescriptor) -> None:
    registry = DriverRegistry()

    assert validate(descriptor) is False
    with pytest.raises(DriverError, match="descriptor is invalid"):
        register(descriptor)
    with pytest.raises(DriverError, match="descriptor is invalid"):
        registry.register(descriptor)

    assert registry.descriptors == {}


def test_descriptor_capabilities_are_defensively_snapshotted_for_registration() -> None:
    caller_capabilities = ["invoke"]
    descriptor = DriverDescriptor(
        id="driver:toy",
        kind="tool",
        version="0.1.0",
        capabilities=caller_capabilities,
    )
    registration = register(descriptor)
    registry = DriverRegistry()
    registry.register(descriptor)

    caller_capabilities.append("admin")

    assert validate(descriptor) is True
    assert descriptor.capabilities == ("invoke",)
    assert registration.descriptor.capabilities == ("invoke",)
    assert registry.get("driver:toy").capabilities == ("invoke",)
    with pytest.raises(AttributeError):
        descriptor.capabilities.append("mutate")

    object.__setattr__(descriptor, "id", "driver:mutated")
    object.__setattr__(descriptor, "capabilities", ("admin",))
    assert registration.descriptor.id == "driver:toy"
    assert registration.descriptor.capabilities == ("invoke",)
    assert registry.get("driver:toy").capabilities == ("invoke",)


def test_registry_exposes_only_detached_read_only_descriptor_snapshots() -> None:
    registry = DriverRegistry()
    registry.register(
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            capabilities=["invoke"],
        )
    )

    descriptors = registry.descriptors
    with pytest.raises(TypeError):
        descriptors["driver:forged"] = DriverDescriptor(  # type: ignore[index]
            id="driver:forged",
            kind="tool",
            version="0.1.0",
        )

    inspected = descriptors["driver:toy"]
    object.__setattr__(inspected, "id", "driver:forged")
    retrieved = registry.get("driver:toy")
    object.__setattr__(retrieved, "capabilities", ("admin",))

    assert tuple(registry.descriptors) == ("driver:toy",)
    assert registry.get("driver:toy").id == "driver:toy"
    assert registry.get("driver:toy").capabilities == ("invoke",)
    with pytest.raises(DriverError, match="unknown driver"):
        registry.get("driver:forged")


def test_registry_constructor_routes_initial_descriptors_through_lifecycle_validation() -> None:
    invalid = DriverDescriptor(id="   ", kind="tool", version="0.1.0")

    with pytest.raises(DriverError, match="descriptor is invalid"):
        DriverRegistry({"driver:invalid": invalid})
