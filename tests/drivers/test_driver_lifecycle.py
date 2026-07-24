from dataclasses import replace
from typing import Any, cast

import pytest

from pheroos.drivers import (
    DriverBinding,
    DriverDescriptor,
    DriverRegistration,
    bind,
    declare,
    expose,
    invoke,
    probe,
    register,
    validate,
)
from pheroos.drivers.errors import DriverError


def test_driver_lifecycle() -> None:
    descriptor = declare(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )

    registration = register(descriptor)
    probe_result = probe(registration)
    binding = bind(registration, tenant_id="tenant-a", permissions=["tool:use"])
    handle = expose(binding)

    assert validate(descriptor) is True
    assert probe_result.available is True
    assert probe_result.version == "0.1.0"
    assert probe_result.capabilities == ()
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


def test_driver_lifecycle_rejects_unpermissioned_exposure_and_missing_provenance() -> (
    None
):
    descriptor = DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    registration = register(descriptor)
    binding = bind(registration, tenant_id="tenant-a", permissions=[])

    with pytest.raises(DriverError, match="no granted permissions"):
        expose(binding)

    handle = expose(bind(registration, tenant_id="tenant-a", permissions=["tool:use"]))
    with pytest.raises(DriverError, match="provenance"):
        invoke(handle, payload={"ok": True}, provenance="")


def test_binding_snapshots_permissions_and_rejects_mutation_bypass() -> None:
    registration = register(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )
    caller_permissions = ["driver:invoke"]

    binding = bind(
        registration,
        tenant_id="tenant-a",
        permissions=caller_permissions,
    )
    caller_permissions.append("driver:admin")

    assert binding.permissions == ("driver:invoke",)
    with pytest.raises(AttributeError):
        getattr(binding.permissions, "append")("driver:admin")

    forged = DriverBinding(
        driver_id="driver:toy",
        tenant_id="tenant-a",
        permissions=cast(tuple[str, ...], ["driver:invoke"]),
    )
    object.__setattr__(forged, "permissions", ["driver:invoke"])
    with pytest.raises(DriverError, match="immutable"):
        expose(forged)


@pytest.mark.parametrize(
    ("tenant_id", "permissions", "message"),
    [
        ("   ", ["driver:invoke"], "tenant id"),
        ("tenant-a", ["   "], "nonblank"),
        ("tenant-a", [7], "nonblank"),
    ],
)
def test_bind_rejects_blank_authority_identities(
    tenant_id: str,
    permissions: list[object],
    message: str,
) -> None:
    registration = register(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )

    with pytest.raises(DriverError, match=message):
        bind(
            registration,
            tenant_id=tenant_id,
            permissions=permissions,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "descriptor",
    (
        cast(DriverDescriptor, object()),
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            permissions=["driver:invoke", "driver:invoke"],
        ),
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            capabilities=["tool:invoke", "tool:invoke"],
        ),
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            permissions=[""],
        ),
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            config_ref=cast(str, object()),
        ),
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            config_ref="   ",
        ),
    ),
)
def test_driver_validation_rejects_each_descriptor_boundary(
    descriptor: DriverDescriptor,
) -> None:
    assert validate(descriptor) is False


def test_canonical_descriptor_and_bind_reject_invalid_public_records() -> None:
    with pytest.raises(DriverError, match="descriptor is invalid"):
        register(cast(DriverDescriptor, object()))
    with pytest.raises(DriverError, match="registration is invalid"):
        bind(
            cast(DriverRegistration, object()),
            tenant_id="tenant-a",
            permissions=("driver:invoke",),
        )
    registration = register(
        DriverDescriptor(id="driver:toy", kind="tool", version="0.1.0")
    )
    with pytest.raises(DriverError, match="run id"):
        bind(
            registration,
            tenant_id="tenant-a",
            run_id="",
            permissions=("driver:invoke",),
        )


def _valid_handle() -> Any:
    registration = register(
        DriverDescriptor(
            id="driver:toy",
            kind="tool",
            version="0.1.0",
            capabilities=["tool:invoke"],
        )
    )
    binding = bind(
        registration,
        tenant_id="tenant-a",
        run_id="run-a",
        permissions=("driver:invoke",),
    )
    return expose(binding)


def test_driver_invoke_public_boundaries_and_success() -> None:
    handle = _valid_handle()
    result = invoke(
        handle,
        payload={"input": "ping"},
        provenance="urn:test:driver",
        capability="tool:invoke",
        invocation_id="invocation:one",
        idempotency_key="idempotency:one",
    )
    assert result.payload == {"input": "ping"}
    assert result.scope_ref == handle.binding.scope_ref

    with pytest.raises(DriverError, match="handle is invalid"):
        invoke(cast(Any, object()), payload={}, provenance="urn:test:driver")
    hidden = replace(handle, exposed=False)
    with pytest.raises(DriverError, match="not exposed"):
        invoke(hidden, payload={}, provenance="urn:test:driver")
    with pytest.raises(DriverError, match="payload"):
        invoke(handle, payload=cast(Any, ()), provenance="urn:test:driver")
    with pytest.raises(DriverError, match="operation is not granted"):
        invoke(
            handle,
            payload={},
            provenance="urn:test:driver",
            operation="driver:admin",
        )
    with pytest.raises(DriverError, match="capability is not declared"):
        invoke(
            handle,
            payload={},
            provenance="urn:test:driver",
            capability="tool:missing",
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"operation": ""},
        {"capability": ""},
        {"invocation_id": ""},
        {"idempotency_key": ""},
    ),
)
def test_driver_invoke_rejects_each_blank_request_identity(
    changes: dict[str, str],
) -> None:
    with pytest.raises(DriverError, match="is required"):
        invoke(
            _valid_handle(),
            payload={},
            provenance="urn:test:driver",
            **changes,
        )


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    (
        ("driver_id", "", "missing driver id"),
        ("tenant_id", "", "missing tenant id"),
        ("run_id", "", "missing run id"),
        ("scope_ref", "sha256:wrong", "scope_ref"),
        ("permissions", ("",), "permissions"),
        ("capabilities", ("",), "capabilities"),
    ),
)
def test_expose_rejects_each_binding_boundary(
    field_name: str,
    value: object,
    match: str,
) -> None:
    handle = _valid_handle()
    object.__setattr__(handle.binding, field_name, value)
    with pytest.raises(DriverError, match=match):
        expose(handle.binding)

    with pytest.raises(DriverError, match="binding is invalid"):
        expose(cast(Any, object()))
