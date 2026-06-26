from __future__ import annotations

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


def validate(descriptor: DriverDescriptor) -> bool:
    return bool(descriptor.id and descriptor.kind and descriptor.version)


def register(descriptor: DriverDescriptor) -> DriverRegistration:
    if not validate(descriptor):
        raise DriverError("driver descriptor is invalid")
    return DriverRegistration(descriptor=descriptor, registered=True)


def probe(registration: DriverRegistration) -> DriverProbeResult:
    return DriverProbeResult(driver_id=registration.descriptor.id, available=registration.registered)


def bind(registration: DriverRegistration, *, tenant_id: str, permissions: list[str]) -> DriverBinding:
    if not registration.registered:
        raise DriverError(f"driver registration is not active: {registration.descriptor.id}")
    if not tenant_id:
        raise DriverError("tenant id is required")
    return DriverBinding(
        driver_id=registration.descriptor.id,
        tenant_id=tenant_id,
        permissions=[permission for permission in permissions if permission],
    )


def expose(binding: DriverBinding) -> DriverHandle:
    if not binding.driver_id:
        raise DriverError("driver binding is missing driver id")
    if not binding.permissions:
        raise DriverError(f"driver binding has no granted permissions: {binding.driver_id}")
    return DriverHandle(binding=binding, exposed=bool(binding.permissions))


def invoke(handle: DriverHandle, *, payload: dict[str, Any], provenance: str) -> DriverResult:
    if not handle.exposed:
        raise DriverError(f"driver handle is not exposed: {handle.binding.driver_id}")
    if not provenance:
        raise DriverError("driver result provenance is required")
    return DriverResult(
        driver_id=handle.binding.driver_id,
        ok=True,
        payload=dict(payload),
        provenance=provenance,
    )
