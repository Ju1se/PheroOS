from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.protocol.manifest import (
    capability_manifest_from_dict,
    protocol_manifest_from_dict,
)
from pheroos.protocol.models import CapabilityManifest, ProtocolManifest
from pheroos.protocol.schema import (
    CAPABILITY_SCHEMA_V1,
    CAPABILITY_SCHEMA_V2,
    PROTOCOL_SCHEMA_V1,
    PROTOCOL_SCHEMA_V2,
    capability_schema,
    capability_schema_v2,
    protocol_schema,
    protocol_schema_v2,
)
from pheroos.protocol.schema_validation import validate_json_schema


class ProtocolSchemaVersionError(ValueError):
    """A manifest schema document cannot be selected or authorized safely."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def read_capability_manifest(
    payload: Mapping[str, Any],
    *,
    schema_version: str,
) -> CapabilityManifest:
    """Read a capability document through an explicitly selected schema.

    The legacy schema remains readable, but authoritative typed loading always
    applies the strict supported-protocol check before returning a manifest.
    Missing or unknown schema versions are never inferred from payload shape.
    """

    if not isinstance(schema_version, str) or not schema_version:
        raise ProtocolSchemaVersionError(
            "capability_schema_version_missing",
            "capability schema version is required",
            path="$.schema_version",
        )
    schema_by_version = {
        CAPABILITY_SCHEMA_V1: capability_schema,
        CAPABILITY_SCHEMA_V2: capability_schema_v2,
    }
    factory = schema_by_version.get(schema_version)
    if factory is None:
        raise ProtocolSchemaVersionError(
            "capability_schema_version_unsupported",
            f"unsupported capability schema version: {schema_version}",
            path="$.schema_version",
        )
    if not isinstance(payload, Mapping):
        raise ProtocolSchemaVersionError(
            "capability_schema_document_invalid",
            "capability schema document must be an object",
        )
    value = dict(payload)
    schema_errors = validate_json_schema(value, factory())
    if schema_errors:
        raise ProtocolSchemaVersionError(
            "capability_schema_document_invalid",
            "capability schema invalid: " + "; ".join(schema_errors),
        )
    try:
        return capability_manifest_from_dict(value)
    except ValueError as exc:
        raise ProtocolSchemaVersionError(
            "capability_authority_document_invalid",
            str(exc),
        ) from exc


def read_protocol_manifest(
    payload: Mapping[str, Any],
    *,
    schema_version: str,
) -> ProtocolManifest:
    """Read a protocol document using an explicit schema-document version."""

    if not isinstance(schema_version, str) or not schema_version:
        raise ProtocolSchemaVersionError(
            "protocol_schema_version_missing",
            "protocol schema version is required",
            path="$.schema_version",
        )
    schema_by_version = {
        PROTOCOL_SCHEMA_V1: protocol_schema,
        PROTOCOL_SCHEMA_V2: protocol_schema_v2,
    }
    factory = schema_by_version.get(schema_version)
    if factory is None:
        raise ProtocolSchemaVersionError(
            "protocol_schema_version_unsupported",
            f"unsupported protocol schema version: {schema_version}",
            path="$.schema_version",
        )
    if not isinstance(payload, Mapping):
        raise ProtocolSchemaVersionError(
            "protocol_schema_document_invalid",
            "protocol schema document must be an object",
        )
    value = dict(payload)
    schema_errors = validate_json_schema(value, factory())
    if schema_errors:
        raise ProtocolSchemaVersionError(
            "protocol_schema_document_invalid",
            "protocol schema invalid: " + "; ".join(schema_errors),
        )
    strict_errors = validate_json_schema(value, protocol_schema_v2())
    if strict_errors:
        raise ProtocolSchemaVersionError(
            "protocol_version_unsupported",
            "unsupported protocol authority document: " + "; ".join(strict_errors),
            path="$.protocol_version",
        )
    return protocol_manifest_from_dict(value)


__all__ = [
    "ProtocolSchemaVersionError",
    "read_capability_manifest",
    "read_protocol_manifest",
]
