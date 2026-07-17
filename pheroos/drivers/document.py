from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pheroos.drivers._versions import DRIVER_DESCRIPTOR_VERSION_V2
from pheroos.drivers.base import DriverDescriptor
from pheroos.drivers.lifecycle import validate


_BASE_FIELDS = frozenset(
    {
        "id",
        "kind",
        "version",
        "capabilities",
        "permissions",
        "config_ref",
        "extensions",
    }
)
_REQUIRED_FIELDS = frozenset({"id", "kind", "version"})
_EXTENSION_PREFIXES = ("x-", "ext.")


class DriverSchemaVersionError(ValueError):
    """A Driver descriptor document cannot be selected or migrated safely."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


@dataclass(frozen=True)
class DriverDescriptorDocument:
    """Versioned wire document around the provider-neutral descriptor model."""

    descriptor: DriverDescriptor
    descriptor_version: str = DRIVER_DESCRIPTOR_VERSION_V2

    def __post_init__(self) -> None:
        if self.descriptor_version != DRIVER_DESCRIPTOR_VERSION_V2:
            raise DriverSchemaVersionError(
                "driver_descriptor_version_unsupported",
                "driver descriptor version is unsupported",
                path="$.descriptor_version",
            )
        if not validate(self.descriptor):
            raise DriverSchemaVersionError(
                "driver_descriptor_v2_invalid",
                "driver descriptor does not satisfy the v2 invariants",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "descriptor_version": self.descriptor_version,
            "id": self.descriptor.id,
            "kind": self.descriptor.kind,
            "version": self.descriptor.version,
            "capabilities": list(self.descriptor.capabilities),
            "permissions": list(self.descriptor.permissions),
            "config_ref": self.descriptor.config_ref,
            "extensions": _portable_value(self.descriptor.extensions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DriverDescriptorDocument:
        return driver_descriptor_from_dict(payload)


def driver_descriptor_v1_from_dict(payload: Mapping[str, Any]) -> DriverDescriptor:
    """Read the exact frozen legacy shape without applying v2 tightening."""

    value = _descriptor_payload(payload, versioned=False)
    return DriverDescriptor(**value)


def driver_descriptor_from_dict(
    payload: Mapping[str, Any],
) -> DriverDescriptorDocument:
    """Read an authoritative v2 document by exact discriminator dispatch."""

    version = _document_version(payload)
    if version != DRIVER_DESCRIPTOR_VERSION_V2:
        raise DriverSchemaVersionError(
            "driver_descriptor_version_unsupported",
            "driver descriptor version is unsupported",
            path="$.descriptor_version",
        )
    value = _descriptor_payload(payload, versioned=True)
    descriptor = DriverDescriptor(**value)
    return DriverDescriptorDocument(descriptor=descriptor, descriptor_version=version)


def upgrade_driver_descriptor_v1(
    value: Mapping[str, Any] | DriverDescriptor,
) -> DriverDescriptorDocument:
    """Explicitly upgrade a v1 descriptor without normalizing its declarations."""

    descriptor = (
        value
        if isinstance(value, DriverDescriptor)
        else driver_descriptor_v1_from_dict(value)
    )
    if not validate(descriptor):
        raise DriverSchemaVersionError(
            "driver_descriptor_v1_not_migratable",
            "legacy descriptor contains values that v2 cannot accept without mutation",
        )
    return DriverDescriptorDocument(descriptor=descriptor)


def _document_version(payload: Mapping[str, Any]) -> Any:
    if not isinstance(payload, Mapping):
        raise DriverSchemaVersionError(
            "driver_descriptor_document_invalid",
            "driver descriptor document must be an object",
        )
    if "descriptor_version" not in payload:
        raise DriverSchemaVersionError(
            "driver_descriptor_version_missing",
            "driver descriptor version is required",
            path="$.descriptor_version",
        )
    return payload["descriptor_version"]


def _descriptor_payload(
    payload: Mapping[str, Any],
    *,
    versioned: bool,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise DriverSchemaVersionError(
            "driver_descriptor_document_invalid",
            "driver descriptor document must be an object",
        )
    allowed = _BASE_FIELDS | ({"descriptor_version"} if versioned else set())
    unknown = {
        key
        for key in payload
        if key not in allowed
        and not (isinstance(key, str) and key.startswith(_EXTENSION_PREFIXES))
    }
    if unknown:
        raise DriverSchemaVersionError(
            "driver_descriptor_fields_invalid",
            "driver descriptor contains unknown fields: "
            + ", ".join(sorted(str(key) for key in unknown)),
        )
    missing = _REQUIRED_FIELDS - set(payload)
    if missing:
        raise DriverSchemaVersionError(
            "driver_descriptor_fields_invalid",
            "driver descriptor is missing fields: " + ", ".join(sorted(missing)),
        )
    for name in ("id", "kind", "version"):
        if not isinstance(payload[name], str):
            raise DriverSchemaVersionError(
                "driver_descriptor_fields_invalid",
                f"driver descriptor {name} must be text",
                path=f"$.{name}",
            )
    capabilities = _string_list(payload.get("capabilities", []), "capabilities")
    permissions = _string_list(payload.get("permissions", []), "permissions")
    config_ref = payload.get("config_ref", "")
    if not isinstance(config_ref, str):
        raise DriverSchemaVersionError(
            "driver_descriptor_fields_invalid",
            "driver descriptor config_ref must be text",
            path="$.config_ref",
        )
    declared_extensions = payload.get("extensions", {})
    if not isinstance(declared_extensions, Mapping):
        raise DriverSchemaVersionError(
            "driver_descriptor_fields_invalid",
            "driver descriptor extensions must be an object",
            path="$.extensions",
        )
    extensions = dict(declared_extensions)
    for key, item in payload.items():
        if isinstance(key, str) and key.startswith(_EXTENSION_PREFIXES):
            if key in extensions:
                raise DriverSchemaVersionError(
                    "driver_descriptor_extension_conflict",
                    f"driver descriptor extension is declared twice: {key}",
                    path=f"$.{key}",
                )
            extensions[key] = item
    return {
        "id": payload["id"],
        "kind": payload["kind"],
        "version": payload["version"],
        "capabilities": capabilities,
        "permissions": permissions,
        "config_ref": config_ref,
        "extensions": extensions,
    }


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DriverSchemaVersionError(
            "driver_descriptor_fields_invalid",
            f"driver descriptor {name} must be a string array",
            path=f"$.{name}",
        )
    return list(value)


def _portable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _portable_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_portable_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(_portable_value(item) for item in value)
    return deepcopy(value)


__all__ = [
    "DriverDescriptorDocument",
    "DriverSchemaVersionError",
    "driver_descriptor_from_dict",
    "driver_descriptor_v1_from_dict",
    "upgrade_driver_descriptor_v1",
]
