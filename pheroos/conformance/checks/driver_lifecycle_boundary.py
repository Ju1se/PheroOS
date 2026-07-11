from __future__ import annotations

from collections.abc import Callable

from pheroos.conformance.report import CheckResult
from pheroos.drivers.base import DriverBinding, DriverDescriptor
from pheroos.drivers.errors import DriverError
from pheroos.drivers.lifecycle import bind, expose, invoke, register
from pheroos.drivers.registry import DriverRegistry


def check() -> CheckResult:
    problems: list[str] = []
    invalid = (
        DriverDescriptor(id="", kind="tool", version="1"),
        DriverDescriptor(id="   ", kind="tool", version="1"),
        DriverDescriptor(id=1, kind="tool", version="1"),  # type: ignore[arg-type]
        DriverDescriptor(id="driver:test", kind="", version="1"),
        DriverDescriptor(id="driver:test", kind=1, version="1"),  # type: ignore[arg-type]
        DriverDescriptor(id="driver:test", kind="tool", version=""),
        DriverDescriptor(id="driver:test", kind="tool", version=1),  # type: ignore[arg-type]
        DriverDescriptor(
            id="driver:test",
            kind="tool",
            version="1",
            capabilities=["invoke", "   "],
        ),
    )
    for index, descriptor in enumerate(invalid):
        lifecycle_rejected = rejects(lambda: register(descriptor))
        registry = DriverRegistry()
        registry_rejected = rejects(lambda: registry.register(descriptor))
        if lifecycle_rejected != registry_rejected or not lifecycle_rejected:
            problems.append(f"descriptor:{index}")
        if registry.descriptors:
            problems.append(f"partial_registration:{index}")
    capabilities = ["invoke"]
    descriptor = DriverDescriptor(
        id="driver:snapshot",
        kind="tool",
        version="1",
        capabilities=capabilities,
    )
    registration = register(descriptor)
    registry = DriverRegistry()
    registry.register(descriptor)
    capabilities.append("mutated")
    if registration.descriptor.capabilities != ("invoke",):
        problems.append("registration_snapshot")
    if registry.get(descriptor.id).capabilities != ("invoke",):
        problems.append("registry_snapshot")
    descriptor_id = descriptor.id
    object.__setattr__(descriptor, "id", "driver:mutated")
    object.__setattr__(descriptor, "capabilities", ("admin",))
    if (
        registration.descriptor.id != descriptor_id
        or registration.descriptor.capabilities != ("invoke",)
    ):
        problems.append("registration_object_snapshot")
    if registry.get(descriptor_id).capabilities != ("invoke",):
        problems.append("registry_object_snapshot")
    descriptor_view = registry.descriptors
    try:
        descriptor_view["driver:forged"] = DriverDescriptor(  # type: ignore[index]
            id="driver:forged",
            kind="tool",
            version="1",
        )
    except TypeError:
        pass
    else:
        problems.append("registry_mutable_view")
    inspected = descriptor_view[descriptor_id]
    object.__setattr__(inspected, "id", "driver:forged")
    if registry.get(descriptor_id).id != descriptor_id:
        problems.append("registry_view_alias")
    permissions = ["driver:invoke"]
    binding = bind(registration, tenant_id="tenant:snapshot", permissions=permissions)
    permissions.append("driver:admin")
    if binding.permissions != ("driver:invoke",):
        problems.append("binding_permission_snapshot")
    forged = DriverBinding(
        driver_id=descriptor.id,
        tenant_id="tenant:snapshot",
        permissions=["driver:invoke"],
    )
    object.__setattr__(forged, "permissions", ["driver:invoke"])
    if not rejects(lambda: expose(forged)):
        problems.append("binding_mutability_bypass")
    payload = {"nested": {"values": ["original"]}}
    result = invoke(expose(binding), payload=payload, provenance=descriptor.id)
    payload["nested"]["values"].append("mutated")
    if result.payload["nested"]["values"] != ("original",):
        problems.append("result_payload_snapshot")
    if not rejects(
        lambda: bind(
            registration,
            tenant_id="   ",
            permissions=["driver:invoke"],
        )
    ):
        problems.append("blank_tenant_bind")
    if not rejects(
        lambda: bind(
            registration,
            tenant_id="tenant:snapshot",
            permissions=["   "],
        )
    ):
        problems.append("blank_permission_bind")
    return CheckResult("driver_lifecycle_boundary", not problems, ", ".join(problems))


def rejects(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except DriverError:
        return True
    return False


__all__ = ["check"]
