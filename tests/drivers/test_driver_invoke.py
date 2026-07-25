import pytest

from pheroos.drivers import (
    DriverDescriptor,
    DriverHandle,
    bind,
    declare,
    expose,
    invoke,
    register,
)
from pheroos.drivers.errors import DriverError


def test_driver_invoke_returns_result_with_provenance() -> None:
    descriptor = declare(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )
    registration = register(descriptor)
    handle = expose(
        bind(registration, tenant_id="tenant-a", permissions=["driver:invoke"])
    )

    result = invoke(handle, payload={"value": "ok"}, provenance="driver:toy")

    assert result.ok is True
    assert result.payload["value"] == "ok"
    assert result.provenance == "driver:toy"


def test_driver_invoke_rejects_unexposed_handle() -> None:
    descriptor = declare(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )
    registration = register(descriptor)
    binding = bind(registration, tenant_id="tenant-a", permissions=["driver:invoke"])
    handle = DriverHandle(binding=binding, exposed=False)

    with pytest.raises(DriverError):
        invoke(handle, payload={}, provenance="driver:toy")


def test_driver_result_recursively_snapshots_payload() -> None:
    descriptor = declare(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )
    handle = expose(
        bind(
            register(descriptor),
            tenant_id="tenant-a",
            permissions=["driver:invoke"],
        )
    )
    caller_payload = {"nested": {"values": ["original"]}}

    result = invoke(handle, payload=caller_payload, provenance="driver:toy")
    caller_payload["nested"]["values"].append("mutated")

    assert result.payload["nested"]["values"] == ("original",)
    with pytest.raises(TypeError):
        result.payload["new"] = "forged"


@pytest.mark.parametrize("provenance", ["", "   ", 7])
def test_driver_invoke_requires_nonblank_string_provenance(provenance: object) -> None:
    descriptor = declare(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )
    handle = expose(
        bind(
            register(descriptor),
            tenant_id="tenant-a",
            permissions=["driver:invoke"],
        )
    )

    with pytest.raises(DriverError, match="provenance"):
        invoke(handle, payload={}, provenance=provenance)  # type: ignore[arg-type]
