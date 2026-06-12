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
    return DriverRegistration(descriptor=descriptor, registered=validate(descriptor))


def probe(registration: DriverRegistration) -> DriverProbeResult:
    return DriverProbeResult(driver_id=registration.descriptor.id, available=registration.registered)


def bind(registration: DriverRegistration, *, tenant_id: str, permissions: list[str]) -> DriverBinding:
    return DriverBinding(driver_id=registration.descriptor.id, tenant_id=tenant_id, permissions=permissions)


def expose(binding: DriverBinding) -> DriverHandle:
    return DriverHandle(binding=binding, exposed=bool(binding.permissions))


def invoke(handle: DriverHandle, *, payload: dict[str, Any], provenance: str) -> DriverResult:
    if not handle.exposed:
        raise DriverError(f"driver handle is not exposed: {handle.binding.driver_id}")
    return DriverResult(
        driver_id=handle.binding.driver_id,
        ok=True,
        payload=dict(payload),
        provenance=provenance,
    )
