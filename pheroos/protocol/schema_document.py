from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from pheroos.protocol.manifest import (
    capability_manifest_from_dict,
    protocol_manifest_from_dict,
)
from pheroos.protocol.models import CapabilityManifest, ProtocolManifest
from pheroos.protocol.authority_manifest_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    PROTOCOL_VERSION_V2,
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    scoped_capability_manifest_v2_from_dict,
    scoped_protocol_manifest_v2_from_dict,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
)
from pheroos.protocol.authority_schema_v2 import (
    CAPABILITY_SCHEMA_V3,
    PROTOCOL_SCHEMA_V3,
    capability_schema_v3,
    protocol_schema_v3,
)
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
from pheroos.protocol.validation import _scoped_protocol_semantic_diagnostics


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
) -> CapabilityManifest | ScopedCapabilityManifestV2:
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
        CAPABILITY_SCHEMA_V3: capability_schema_v3,
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
    if schema_version == CAPABILITY_SCHEMA_V3:
        protocol = value.get("protocol")
        if type(protocol) is not dict:
            raise ProtocolSchemaVersionError(
                AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED.value,
                "scoped capability requires an exact protocol object",
                path="$.protocol",
            )
        _preflight_scoped_selection(protocol, path="$.protocol")
    schema_errors = validate_json_schema(value, factory())
    if schema_errors:
        raise ProtocolSchemaVersionError(
            "capability_schema_document_invalid",
            "capability schema invalid: " + "; ".join(schema_errors),
        )
    try:
        if schema_version == CAPABILITY_SCHEMA_V3:
            manifest = scoped_capability_manifest_v2_from_dict(value)
            _require_scoped_semantics(manifest.protocol)
            return manifest
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
) -> ProtocolManifest | ScopedProtocolManifestV2:
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
        PROTOCOL_SCHEMA_V3: protocol_schema_v3,
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
    if schema_version == PROTOCOL_SCHEMA_V3:
        _preflight_scoped_selection(value, path="$")
    schema_errors = validate_json_schema(value, factory())
    if schema_errors:
        raise ProtocolSchemaVersionError(
            "protocol_schema_document_invalid",
            "protocol schema invalid: " + "; ".join(schema_errors),
        )
    if schema_version == PROTOCOL_SCHEMA_V3:
        try:
            protocol = scoped_protocol_manifest_v2_from_dict(value)
            _require_scoped_semantics(protocol)
            return protocol
        except ValueError as exc:
            raise ProtocolSchemaVersionError(
                "protocol_authority_document_invalid",
                str(exc),
            ) from exc
    strict_errors = validate_json_schema(value, protocol_schema_v2())
    if strict_errors:
        raise ProtocolSchemaVersionError(
            "protocol_version_unsupported",
            "unsupported protocol authority document: " + "; ".join(strict_errors),
            path="$.protocol_version",
        )
    return protocol_manifest_from_dict(value)


def _require_scoped_semantics(protocol: ScopedProtocolManifestV2) -> None:
    diagnostics = [
        item
        for item in _scoped_protocol_semantic_diagnostics(protocol)
        if item.level == "error"
    ]
    if diagnostics:
        details = "; ".join(
            f"{item.code}@{item.path}: {item.message}" for item in diagnostics
        )
        raise ValueError("scoped protocol semantic validation failed: " + details)


def _preflight_scoped_selection(
    protocol: dict[str, Any],
    *,
    path: str,
) -> None:
    expected_policy = {
        "policy_version": AUTHORITY_POLICY_VERSION_V2,
        "wire_version": AUTHORITY_WIRE_VERSION_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
        "ledger_version": AUTHORITY_LEDGER_VERSION_V2,
        "state_store_version": GOVERNANCE_STATE_STORE_VERSION_V2,
        "trace_batch_version": GOVERNANCE_TRACE_BATCH_VERSION_V2,
        "read_set_version": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    }
    _require_scoped_exact(
        protocol.get("protocol_version"),
        PROTOCOL_VERSION_V2,
        path=f"{path}.protocol_version",
    )
    policy = protocol.get("authority_policy")
    expected_fields = {*expected_policy, "profile"}
    if type(policy) is not dict or set(policy) != expected_fields:
        _unsupported_scoped(
            "authority policy fields are invalid", f"{path}.authority_policy"
        )
    assert type(policy) is dict
    for name, expected in expected_policy.items():
        _require_scoped_exact(
            policy.get(name),
            expected,
            path=f"{path}.authority_policy.{name}",
        )
    if policy.get("profile") not in {
        AUTHORITY_LOCAL_PROFILE_V2,
        AUTHORITY_AUTHENTICATED_PROFILE_V2,
    }:
        _unsupported_scoped(
            "authority profile is unsupported",
            f"{path}.authority_policy.profile",
        )
    output = protocol.get("output_policy")
    if type(output) is not dict:
        _unsupported_scoped(
            "baseline output policy is missing",
            f"{path}.output_policy",
        )
    assert type(output) is dict
    _require_scoped_exact(
        output.get("policy_version"),
        BASELINE_OUTPUT_POLICY_VERSION_V2,
        path=f"{path}.output_policy.policy_version",
    )


def _require_scoped_exact(value: object, expected: str, *, path: str) -> None:
    if type(value) is not str or value != expected:
        _unsupported_scoped("scoped authority version is unsupported", path)


def _unsupported_scoped(message: str, path: str) -> NoReturn:
    raise ProtocolSchemaVersionError(
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED.value,
        message,
        path=path,
    )


__all__ = [
    "ProtocolSchemaVersionError",
    "read_capability_manifest",
    "read_protocol_manifest",
]
