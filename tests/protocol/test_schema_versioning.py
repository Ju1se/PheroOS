from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.protocol.schema_document import (
    ProtocolSchemaVersionError,
    read_capability_manifest,
    read_protocol_manifest,
)
from pheroos.protocol.schema import (
    CAPABILITY_SCHEMA_V1,
    CAPABILITY_SCHEMA_V1_ID,
    CAPABILITY_SCHEMA_V2,
    CAPABILITY_SCHEMA_V2_ID,
    PROTOCOL_SCHEMA_V1,
    PROTOCOL_SCHEMA_V1_ID,
    PROTOCOL_SCHEMA_V2,
    PROTOCOL_SCHEMA_V2_ID,
    capability_schema,
    capability_schema_v2,
    protocol_schema,
    protocol_schema_v2,
)
from pheroos.protocol.schema_validation import validate_json_schema


ROOT = Path(__file__).resolve().parents[2]
LEGACY_SCHEMA_SHA256 = {
    "capability.schema.json": (
        "5d3a88ed54d9acf83813713abec493ebb85e245cd6766de9fffa03351cdb62cf"
    ),
    "protocol.schema.json": (
        "1abc0b228c72fc05f8ec6272d327d9c06ca3e3a7e37ea2487ccfeff60c86cdb6"
    ),
}


def _render(schema: dict[str, object]) -> bytes:
    return (json.dumps(schema, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _toy_payload() -> dict[str, object]:
    return json.loads(
        (ROOT / "examples/toy-protocol/capability.json").read_text(encoding="utf-8")
    )


def test_legacy_protocol_schema_documents_are_byte_frozen() -> None:
    generated = {
        "capability.schema.json": capability_schema(),
        "protocol.schema.json": protocol_schema(),
    }
    for filename, schema in generated.items():
        artifact = (ROOT / "schemas" / filename).read_bytes()
        assert artifact == _render(schema)
        assert sha256(artifact).hexdigest() == LEGACY_SCHEMA_SHA256[filename]

    assert capability_schema()["$id"] == CAPABILITY_SCHEMA_V1_ID
    assert protocol_schema()["$id"] == PROTOCOL_SCHEMA_V1_ID


def test_strict_v2_protocol_schema_documents_are_versioned_and_checked_in() -> None:
    generated = {
        "capability-v2.schema.json": capability_schema_v2(),
        "protocol-v2.schema.json": protocol_schema_v2(),
    }
    for filename, schema in generated.items():
        assert (ROOT / "schemas" / filename).read_bytes() == _render(schema)

    assert capability_schema_v2()["$id"] == CAPABILITY_SCHEMA_V2_ID
    assert protocol_schema_v2()["$id"] == PROTOCOL_SCHEMA_V2_ID


def test_legacy_schema_remains_inspectable_but_authority_reader_fails_closed() -> None:
    payload = _toy_payload()
    protocol = payload["protocol"]
    assert isinstance(protocol, dict)
    protocol["protocol_version"] = "pheroos.protocol.future"

    assert validate_json_schema(payload, capability_schema()) == []
    assert validate_json_schema(protocol, protocol_schema()) == []
    assert validate_json_schema(payload, capability_schema_v2())
    assert validate_json_schema(protocol, protocol_schema_v2())

    with pytest.raises(ValueError, match="manifest schema invalid"):
        capability_manifest_from_dict(payload)
    with pytest.raises(
        ProtocolSchemaVersionError,
        match="unsupported protocol authority document",
    ) as exc:
        read_protocol_manifest(protocol, schema_version=PROTOCOL_SCHEMA_V1)
    assert exc.value.code == "protocol_version_unsupported"
    assert exc.value.path == "$.protocol_version"


@pytest.mark.parametrize(
    "schema_version",
    [CAPABILITY_SCHEMA_V1, CAPABILITY_SCHEMA_V2],
)
def test_capability_reader_requires_an_explicit_supported_schema_version(
    schema_version: str,
) -> None:
    manifest = read_capability_manifest(
        deepcopy(_toy_payload()),
        schema_version=schema_version,
    )
    assert manifest.protocol.protocol_version == "pheroos.protocol.v1"

    with pytest.raises(TypeError, match="schema_version"):
        read_capability_manifest(deepcopy(_toy_payload()))  # type: ignore[call-arg]
    with pytest.raises(
        ProtocolSchemaVersionError,
        match="unsupported capability schema version",
    ) as exc:
        read_capability_manifest(
            deepcopy(_toy_payload()),
            schema_version="pheroos-capability-schema-future",
        )
    assert exc.value.code == "capability_schema_version_unsupported"
    assert exc.value.path == "$.schema_version"


@pytest.mark.parametrize("schema_version", [PROTOCOL_SCHEMA_V1, PROTOCOL_SCHEMA_V2])
def test_protocol_reader_requires_an_explicit_supported_schema_version(
    schema_version: str,
) -> None:
    payload = _toy_payload()["protocol"]
    assert isinstance(payload, dict)
    manifest = read_protocol_manifest(payload, schema_version=schema_version)
    assert manifest.protocol_version == "pheroos.protocol.v1"

    with pytest.raises(TypeError, match="schema_version"):
        read_protocol_manifest(payload)  # type: ignore[call-arg]
    with pytest.raises(
        ProtocolSchemaVersionError,
        match="unsupported protocol schema version",
    ) as exc:
        read_protocol_manifest(
            payload,
            schema_version="pheroos-protocol-schema-future",
        )
    assert exc.value.code == "protocol_schema_version_unsupported"
    assert exc.value.path == "$.schema_version"


def test_schema_readers_reject_blank_and_cross_surface_versions() -> None:
    capability_payload = deepcopy(_toy_payload())
    protocol_payload = capability_payload["protocol"]
    assert isinstance(protocol_payload, dict)

    with pytest.raises(ProtocolSchemaVersionError) as capability_missing:
        read_capability_manifest(capability_payload, schema_version="")
    assert capability_missing.value.code == "capability_schema_version_missing"
    assert capability_missing.value.path == "$.schema_version"

    with pytest.raises(ProtocolSchemaVersionError) as capability_cross_surface:
        read_capability_manifest(
            capability_payload,
            schema_version=PROTOCOL_SCHEMA_V2,
        )
    assert (
        capability_cross_surface.value.code
        == "capability_schema_version_unsupported"
    )
    assert capability_cross_surface.value.path == "$.schema_version"

    with pytest.raises(ProtocolSchemaVersionError) as protocol_missing:
        read_protocol_manifest(protocol_payload, schema_version="")
    assert protocol_missing.value.code == "protocol_schema_version_missing"
    assert protocol_missing.value.path == "$.schema_version"

    with pytest.raises(ProtocolSchemaVersionError) as protocol_cross_surface:
        read_protocol_manifest(
            protocol_payload,
            schema_version=CAPABILITY_SCHEMA_V2,
        )
    assert protocol_cross_surface.value.code == "protocol_schema_version_unsupported"
    assert protocol_cross_surface.value.path == "$.schema_version"
