from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields
from typing import Any

from pheroos._scope import runtime_scope_ref
from pheroos.drivers.base import (
    DriverBinding,
    DriverDescriptor,
    DriverHandle,
    DriverProbeResult,
    DriverRegistration,
    DriverResult,
)
from pheroos.drivers.errors import DriverError
from pheroos.drivers.invocation import driver_request_digest


def declare(descriptor: DriverDescriptor) -> DriverDescriptor:
    return descriptor


def validate(descriptor: object) -> bool:
    """Validate the canonical provider-neutral driver descriptor shape."""

    if not isinstance(descriptor, DriverDescriptor):
        return False
    identities = (descriptor.id, descriptor.kind, descriptor.version)
    if not all(isinstance(value, str) and bool(value.strip()) for value in identities):
        return False
    if not _valid_text_tuple(descriptor.capabilities):
        return False
    if not _valid_text_tuple(descriptor.permissions):
        return False
    if len(set(descriptor.capabilities)) != len(descriptor.capabilities):
        return False
    if len(set(descriptor.permissions)) != len(descriptor.permissions):
        return False
    if not isinstance(descriptor.config_ref, str):
        return False
    if descriptor.config_ref and not descriptor.config_ref.strip():
        return False
    return isinstance(descriptor.extensions, Mapping) and all(
        isinstance(key, str) and bool(key.strip())
        for key in descriptor.extensions
    )


def register(descriptor: DriverDescriptor) -> DriverRegistration:
    snapshot = canonical_driver_descriptor(descriptor)
    if not validate(snapshot):
        raise DriverError("driver descriptor is invalid")
    return DriverRegistration(descriptor=snapshot, registered=True)


def canonical_driver_descriptor(descriptor: object) -> DriverDescriptor:
    """Normalize legacy descriptor subclasses into the single Driver ABI."""

    if not isinstance(descriptor, DriverDescriptor):
        raise DriverError("driver descriptor is invalid")
    base_names = {item.name for item in fields(DriverDescriptor)}
    extra_fields = {
        item.name: getattr(descriptor, item.name)
        for item in fields(type(descriptor))
        if item.name not in base_names
    }
    extensions = dict(descriptor.extensions)
    if extra_fields:
        extensions["ext.pheroos.legacy_descriptor"] = {
            "type": type(descriptor).__name__,
            "fields": extra_fields,
        }
    return DriverDescriptor(
        id=descriptor.id,
        kind=descriptor.kind,
        version=descriptor.version,
        capabilities=descriptor.capabilities,
        permissions=descriptor.permissions,
        config_ref=descriptor.config_ref,
        extensions=extensions,
    )


def probe(registration: DriverRegistration) -> DriverProbeResult:
    return DriverProbeResult(
        driver_id=registration.descriptor.id,
        available=registration.registered,
        version=registration.descriptor.version,
        capabilities=registration.descriptor.capabilities,
    )


def bind(
    registration: DriverRegistration,
    *,
    tenant_id: str,
    permissions: Sequence[str],
    run_id: str = "legacy",
) -> DriverBinding:
    if not isinstance(registration, DriverRegistration) or not validate(registration.descriptor):
        raise DriverError("driver registration is invalid")
    if registration.registered is not True:
        raise DriverError(f"driver registration is not active: {registration.descriptor.id}")
    if not _is_nonblank_text(tenant_id):
        raise DriverError("tenant id is required")
    if not _is_nonblank_text(run_id):
        raise DriverError("run id is required")
    if not isinstance(permissions, (list, tuple)) or not all(
        _is_nonblank_text(permission) for permission in permissions
    ):
        raise DriverError("driver permissions must be nonblank strings")
    return DriverBinding(
        driver_id=registration.descriptor.id,
        tenant_id=tenant_id,
        run_id=run_id,
        scope_ref=runtime_scope_ref(tenant_id, run_id),
        permissions=tuple(permissions),
        capabilities=registration.descriptor.capabilities,
    )


def expose(binding: DriverBinding) -> DriverHandle:
    _validate_binding(binding)
    if not binding.permissions:
        raise DriverError(f"driver binding has no granted permissions: {binding.driver_id}")
    return DriverHandle(binding=binding, exposed=True)


def invoke(
    handle: DriverHandle,
    *,
    payload: Mapping[str, Any],
    provenance: str,
    operation: str = "driver:invoke",
    capability: str = "driver:invoke",
    invocation_id: str = "legacy-invocation",
    idempotency_key: str = "legacy-idempotency",
) -> DriverResult:
    if not isinstance(handle, DriverHandle):
        raise DriverError("driver handle is invalid")
    _validate_binding(handle.binding)
    if handle.exposed is not True:
        raise DriverError(f"driver handle is not exposed: {handle.binding.driver_id}")
    if not isinstance(payload, Mapping):
        raise DriverError("driver payload must be a mapping")
    if not _is_nonblank_text(provenance):
        raise DriverError("driver result provenance is required")
    for name, value in (
        ("operation", operation),
        ("capability", capability),
        ("invocation id", invocation_id),
        ("idempotency key", idempotency_key),
    ):
        if not _is_nonblank_text(value):
            raise DriverError(f"driver {name} is required")
    if operation not in handle.binding.permissions:
        raise DriverError("driver operation is not granted by the active binding")
    if handle.binding.capabilities and capability not in handle.binding.capabilities:
        raise DriverError("driver capability is not declared by the active binding")
    request_digest = driver_request_digest(
        scope_ref=handle.binding.scope_ref,
        invocation_id=invocation_id,
        driver_id=handle.binding.driver_id,
        operation=operation,
        capability=capability,
        idempotency_key=idempotency_key,
        payload=payload,
    )
    return DriverResult(
        driver_id=handle.binding.driver_id,
        ok=True,
        payload=payload,
        provenance=provenance,
        scope_ref=handle.binding.scope_ref,
        invocation_id=invocation_id,
        operation=operation,
        request_digest=request_digest,
    )


def _validate_binding(binding: object) -> None:
    if not isinstance(binding, DriverBinding):
        raise DriverError("driver binding is invalid")
    if not _is_nonblank_text(binding.driver_id):
        raise DriverError("driver binding is missing driver id")
    if not _is_nonblank_text(binding.tenant_id):
        raise DriverError("driver binding is missing tenant id")
    if not _is_nonblank_text(binding.run_id):
        raise DriverError("driver binding is missing run id")
    try:
        expected_scope = runtime_scope_ref(binding.tenant_id, binding.run_id)
    except ValueError as exc:
        raise DriverError(str(exc)) from exc
    if binding.scope_ref != expected_scope:
        raise DriverError("driver binding scope_ref does not match tenant and run")
    if not isinstance(binding.permissions, tuple) or not all(
        _is_nonblank_text(permission) for permission in binding.permissions
    ):
        raise DriverError("driver binding permissions must be immutable nonblank strings")
    if not isinstance(binding.capabilities, tuple) or not all(
        _is_nonblank_text(capability) for capability in binding.capabilities
    ):
        raise DriverError("driver binding capabilities must be immutable nonblank strings")


def _is_nonblank_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_text_tuple(value: object) -> bool:
    return isinstance(value, tuple) and all(_is_nonblank_text(item) for item in value)
