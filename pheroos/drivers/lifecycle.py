from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pheroos.drivers.base import (
    DriverBinding,
    DriverDescriptor,
    DriverHandle,
    DriverProbeResult,
    DriverRegistration,
    DriverResult,
)
from pheroos.drivers.errors import DriverError


def declare(descriptor: DriverDescriptor) -> DriverDescriptor:
    return descriptor


def validate(descriptor: object) -> bool:
    """Validate the canonical provider-neutral driver descriptor shape."""

    if not isinstance(descriptor, DriverDescriptor):
        return False
    identities = (descriptor.id, descriptor.kind, descriptor.version)
    if not all(isinstance(value, str) and bool(value.strip()) for value in identities):
        return False
    return isinstance(descriptor.capabilities, tuple) and all(
        isinstance(capability, str) and bool(capability.strip())
        for capability in descriptor.capabilities
    )


def register(descriptor: DriverDescriptor) -> DriverRegistration:
    if not validate(descriptor):
        raise DriverError("driver descriptor is invalid")
    # Registration is a trust boundary. Reconstruct the canonical descriptor
    # so even a caller retaining the original frozen object cannot rewrite the
    # registered state through object.__setattr__.
    snapshot = DriverDescriptor(
        id=descriptor.id,
        kind=descriptor.kind,
        version=descriptor.version,
        capabilities=descriptor.capabilities,
    )
    return DriverRegistration(descriptor=snapshot, registered=True)


def probe(registration: DriverRegistration) -> DriverProbeResult:
    return DriverProbeResult(driver_id=registration.descriptor.id, available=registration.registered)


def bind(
    registration: DriverRegistration,
    *,
    tenant_id: str,
    permissions: Sequence[str],
) -> DriverBinding:
    if not isinstance(registration, DriverRegistration) or not validate(registration.descriptor):
        raise DriverError("driver registration is invalid")
    if registration.registered is not True:
        raise DriverError(f"driver registration is not active: {registration.descriptor.id}")
    if not _is_nonblank_text(tenant_id):
        raise DriverError("tenant id is required")
    if not isinstance(permissions, (list, tuple)) or not all(
        _is_nonblank_text(permission) for permission in permissions
    ):
        raise DriverError("driver permissions must be nonblank strings")
    return DriverBinding(
        driver_id=registration.descriptor.id,
        tenant_id=tenant_id,
        permissions=tuple(permissions),
    )


def expose(binding: DriverBinding) -> DriverHandle:
    _validate_binding(binding)
    if not binding.permissions:
        raise DriverError(f"driver binding has no granted permissions: {binding.driver_id}")
    return DriverHandle(binding=binding, exposed=True)


def invoke(handle: DriverHandle, *, payload: Mapping[str, Any], provenance: str) -> DriverResult:
    if not isinstance(handle, DriverHandle):
        raise DriverError("driver handle is invalid")
    _validate_binding(handle.binding)
    if handle.exposed is not True:
        raise DriverError(f"driver handle is not exposed: {handle.binding.driver_id}")
    if not isinstance(payload, Mapping):
        raise DriverError("driver payload must be a mapping")
    if not _is_nonblank_text(provenance):
        raise DriverError("driver result provenance is required")
    return DriverResult(
        driver_id=handle.binding.driver_id,
        ok=True,
        payload=payload,
        provenance=provenance,
    )


def _validate_binding(binding: object) -> None:
    if not isinstance(binding, DriverBinding):
        raise DriverError("driver binding is invalid")
    if not _is_nonblank_text(binding.driver_id):
        raise DriverError("driver binding is missing driver id")
    if not _is_nonblank_text(binding.tenant_id):
        raise DriverError("driver binding is missing tenant id")
    if not isinstance(binding.permissions, tuple) or not all(
        _is_nonblank_text(permission) for permission in binding.permissions
    ):
        raise DriverError("driver binding permissions must be immutable nonblank strings")


def _is_nonblank_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
