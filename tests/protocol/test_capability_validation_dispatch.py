from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
import json
from pathlib import Path

from pheroos.protocol import (
    CAPABILITY_SCHEMA_V3,
    ScopedCapabilityManifestV2,
    load_capability_manifest,
    read_capability_manifest,
    validate_capability_manifest,
)
from pheroos.protocol.validation import _validate_capability_manifest_v1
from pheroos.protocol.authority_manifest_v2 import ScopedManifestV2Error
from pheroos.protocol.models import SignalSpec

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _scoped_manifest() -> ScopedCapabilityManifestV2:
    payload = json.loads(
        (ROOT / "examples/scoped-output-protocol/capability.json").read_text(
            encoding="utf-8"
        )
    )
    value = read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)
    assert type(value) is ScopedCapabilityManifestV2
    return value


def test_validation_dispatch_preserves_the_exact_legacy_diagnostic_path() -> None:
    manifest = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    invalid = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            protocol_version="pheroos.protocol.unsupported",
        ),
    )

    for value in (manifest, invalid):
        assert validate_capability_manifest(value) == (
            _validate_capability_manifest_v1(value)
        )


def test_validation_dispatch_accepts_the_canonical_scoped_manifest() -> None:
    assert validate_capability_manifest(_scoped_manifest()) == []


def test_validation_dispatch_fails_closed_for_tampered_scoped_values() -> None:
    manifest = _scoped_manifest()
    object.__setattr__(manifest, "permissions", ["permission:publish"])

    diagnostics = validate_capability_manifest(manifest)

    assert [item.code for item in diagnostics] == ["scoped_capability_manifest_invalid"]
    assert diagnostics[0].path == "$"


def test_validation_dispatch_rejects_unsupported_duck_types_without_attribute_access() -> (
    None
):
    class CapabilityLike:
        id = "duck:capability"

    diagnostics = validate_capability_manifest(cast(Any, CapabilityLike()))

    assert [item.code for item in diagnostics] == [
        "capability_manifest_type_unsupported"
    ]
    assert diagnostics[0].path == "$"


def test_direct_scoped_constructor_rejects_semantically_invalid_nested_values() -> None:
    manifest = _scoped_manifest()

    with pytest.raises(ScopedManifestV2Error, match="signal target"):
        replace(
            manifest.protocol,
            signals=(
                SignalSpec(
                    type="proposal",
                    target="decision:undeclared",
                    authority_required="governance",
                ),
            ),
        )


def test_public_validator_rejects_semantically_tampered_scoped_values() -> None:
    manifest = _scoped_manifest()
    object.__setattr__(manifest.protocol.signals[0], "target", "decision:missing")

    diagnostics = validate_capability_manifest(manifest)

    assert [item.code for item in diagnostics] == ["scoped_capability_manifest_invalid"]
