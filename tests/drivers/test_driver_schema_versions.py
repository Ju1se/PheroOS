from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import (  # type: ignore[import-untyped]  # dependency ships no stubs
    Draft202012Validator,
    ValidationError,
)

from pheroos.drivers import (
    DRIVER_DESCRIPTOR_VERSION_V2,
    DRIVER_SCHEMA_V1_ID,
    DRIVER_SCHEMA_V2_ID,
    DriverDescriptor,
    DriverDescriptorDocument,
    DriverSchemaVersionError,
    driver_descriptor_from_dict,
    driver_descriptor_v1_from_dict,
    driver_schema,
    driver_schema_v2,
    upgrade_driver_descriptor_v1,
)


ROOT = Path(__file__).resolve().parents[2]
V1_ROOT = "44171e85e1076231d9120f67abafcf521748ccbb8932a805df12c43823587fbd"


def _fixture() -> dict[str, object]:
    return json.loads(
        (ROOT / "tests/fixtures/schema-v1/driver-descriptor.json").read_text()
    )


def test_driver_v1_artifact_is_frozen_and_alias_is_byte_equivalent() -> None:
    artifact = ROOT / "schemas/driver.schema.json"
    expected = (json.dumps(driver_schema(), indent=2, sort_keys=True) + "\n").encode()

    assert artifact.read_bytes() == expected
    assert sha256(expected).hexdigest() == V1_ROOT
    assert driver_schema()["$id"] == DRIVER_SCHEMA_V1_ID


def test_driver_v2_artifact_is_strict_versioned_and_checked_in() -> None:
    generated = driver_schema_v2()
    artifact = json.loads((ROOT / "schemas/driver-v2.schema.json").read_text())

    Draft202012Validator.check_schema(generated)
    assert artifact == generated
    assert generated["$id"] == DRIVER_SCHEMA_V2_ID
    assert generated["properties"]["descriptor_version"] == {
        "const": DRIVER_DESCRIPTOR_VERSION_V2
    }


def test_legacy_reader_preserves_old_legal_values_but_upgrade_does_not_mutate_them() -> (
    None
):
    payload = _fixture()
    Draft202012Validator(driver_schema()).validate(payload)
    descriptor = driver_descriptor_v1_from_dict(payload)

    assert descriptor.capabilities == ("tool:invoke", "tool:invoke")
    assert descriptor.permissions == ("",)
    with pytest.raises(
        DriverSchemaVersionError,
        match="cannot accept without mutation",
    ) as raised:
        upgrade_driver_descriptor_v1(descriptor)
    assert raised.value.code == "driver_descriptor_v1_not_migratable"
    assert descriptor.capabilities == ("tool:invoke", "tool:invoke")
    with pytest.raises(ValidationError):
        Draft202012Validator(driver_schema_v2()).validate(payload)


def test_driver_v2_reader_round_trips_provider_version_separately() -> None:
    payload = {
        "descriptor_version": DRIVER_DESCRIPTOR_VERSION_V2,
        "id": "driver:strict",
        "kind": "tool",
        "version": "provider-7",
        "capabilities": ["tool:invoke"],
        "permissions": ["driver:invoke"],
        "config_ref": "",
        "extensions": {"ext.example.mode": {"values": ["strict"]}},
    }

    document = driver_descriptor_from_dict(payload)

    assert isinstance(document, DriverDescriptorDocument)
    assert document.descriptor.version == "provider-7"
    assert document.descriptor_version == DRIVER_DESCRIPTOR_VERSION_V2
    assert document.to_dict() == payload
    assert DriverDescriptorDocument.from_dict(payload) == document
    Draft202012Validator(driver_schema_v2()).validate(payload)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            {"id": "driver:x", "kind": "tool", "version": "1"},
            "driver_descriptor_version_missing",
        ),
        (
            {
                "descriptor_version": "pheroos-driver-descriptor-v999",
                "id": "driver:x",
                "kind": "tool",
                "version": "1",
            },
            "driver_descriptor_version_unsupported",
        ),
        (
            {
                "descriptor_version": "pheroos-kernel-plan-v2",
                "id": "driver:x",
                "kind": "tool",
                "version": "1",
            },
            "driver_descriptor_version_unsupported",
        ),
    ],
)
def test_driver_authoritative_reader_fails_closed_on_missing_unknown_or_cross_version(
    payload: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(DriverSchemaVersionError) as raised:
        driver_descriptor_from_dict(payload)

    assert raised.value.code == code


def test_driver_document_public_readers_cover_each_structural_boundary() -> None:
    valid = {
        "descriptor_version": DRIVER_DESCRIPTOR_VERSION_V2,
        "id": "driver:strict",
        "kind": "tool",
        "version": "1.0.0",
        "capabilities": ["tool:invoke"],
        "permissions": ["driver:invoke"],
        "config_ref": "",
        "extensions": {},
    }

    with pytest.raises(DriverSchemaVersionError, match="unsupported"):
        DriverDescriptorDocument(
            descriptor=DriverDescriptor(
                id="driver:strict",
                kind="tool",
                version="1.0.0",
            ),
            descriptor_version="unknown",
        )
    with pytest.raises(DriverSchemaVersionError, match="invariants"):
        DriverDescriptorDocument(
            descriptor=DriverDescriptor(id="", kind="tool", version="1.0.0")
        )
    with pytest.raises(DriverSchemaVersionError, match="must be an object"):
        driver_descriptor_from_dict(cast(Any, []))
    with pytest.raises(DriverSchemaVersionError, match="must be an object"):
        driver_descriptor_v1_from_dict(cast(Any, []))

    mutations: tuple[tuple[dict[str, object], str], ...] = (
        ({**valid, "unknown": True}, "unknown fields"),
        ({key: value for key, value in valid.items() if key != "id"}, "missing fields"),
        ({**valid, "id": 1}, "id must be text"),
        ({**valid, "config_ref": 1}, "config_ref must be text"),
        ({**valid, "capabilities": [1]}, "capabilities must be a string array"),
        (
            {**valid, "permissions": "driver:invoke"},
            "permissions must be a string array",
        ),
        ({**valid, "extensions": []}, "extensions must be an object"),
        (
            {
                **valid,
                "extensions": {"x-mode": "declared"},
                "x-mode": "inline",
            },
            "declared twice",
        ),
    )
    for payload, message in mutations:
        with pytest.raises(DriverSchemaVersionError, match=message):
            driver_descriptor_from_dict(payload)

    upgraded = upgrade_driver_descriptor_v1(
        {name: value for name, value in valid.items() if name != "descriptor_version"}
    )
    assert upgraded.descriptor.id == "driver:strict"

    inline = driver_descriptor_from_dict({**valid, "x-example-mode": {"enabled": True}})
    assert inline.descriptor.extensions["x-example-mode"] == {"enabled": True}


def test_driver_document_projects_nested_sequences_and_frozensets_portably() -> None:
    document = DriverDescriptorDocument(
        DriverDescriptor(
            id="driver:portable",
            kind="tool",
            version="1.0.0",
            extensions={"ext.example.values": ({"labels": frozenset(("b", "a"))},)},
        )
    )

    payload = document.to_dict()
    extensions = cast(dict[str, object], payload["extensions"])
    values = cast(list[object], extensions["ext.example.values"])
    assert cast(dict[str, object], values[0])["labels"] == ["a", "b"]
