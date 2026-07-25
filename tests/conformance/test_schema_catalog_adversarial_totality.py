from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import pheroos.conformance.schema_catalog as catalog
from pheroos.conformance._runtime_integration_codec import (
    RuntimeIntegrationTranscriptErrorV1,
    text_value,
)
from pheroos.protocol.models import (
    CapabilityManifest,
    ProtocolManifest,
    QuorumPolicy,
)


def _raising_factory() -> dict[str, object]:
    raise RuntimeError("declared schema factory failed")


def test_unknown_surface_and_non_mapping_wire_values_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown schema surface"):
        catalog.schema_spec_for_surface("not-a-declared-surface")

    for value in ([], {1: "non-string key"}):
        with pytest.raises(TypeError, match="string-keyed object"):
            catalog._mapping(value, "adversarial value")


def test_catalog_reports_missing_orphan_and_factory_failures(tmp_path: Path) -> None:
    schema_dir = tmp_path / catalog.SCHEMA_ARTIFACT_DIRECTORY
    schema_dir.mkdir()
    (schema_dir / "orphan.schema.json").write_text("{}\n", encoding="utf-8")

    problems = catalog.schema_catalog_problems(tmp_path)

    assert "orphan:schemas/orphan.schema.json" in problems
    assert any(item.startswith("missing:schemas/") for item in problems)

    broken = replace(
        catalog.SCHEMA_ARTIFACT_SPECS[0],
        surface="broken-factory",
        factory=_raising_factory,
    )
    factory_problems: list[str] = []
    catalog._validate_spec(tmp_path, broken, factory_problems)
    assert factory_problems == ["factory:broken-factory:RuntimeError"]


def test_catalog_metadata_diagnostics_are_independent_and_exact() -> None:
    original = catalog.SCHEMA_ARTIFACT_SPECS[0]
    malformed = replace(
        original,
        surface="malformed-metadata",
        typed_reader=None,
        typed_reader_not_applicable_reason=None,
        semantic_validator=None,
        semantic_validator_not_applicable_reason=None,
        cli_surfaces=(),
        frozen=True,
        frozen_sha256=None,
        package_data_required=True,
        package_resource_path=None,
    )
    problems: list[str] = []

    catalog._validate_spec_metadata({}, malformed, problems)

    assert problems == [
        "draft:malformed-metadata",
        "schema_id:malformed-metadata",
        "typed_reader:malformed-metadata",
        "semantic_validator:malformed-metadata",
        "canonical_surface:malformed-metadata",
        "frozen_metadata:malformed-metadata",
        "package_data:malformed-metadata",
    ]


def test_catalog_artifact_drift_and_frozen_hash_are_separate(tmp_path: Path) -> None:
    path = tmp_path / "schemas" / "adversarial.schema.json"
    path.parent.mkdir()
    path.write_bytes(b"observed\n")
    spec = replace(
        catalog.SCHEMA_ARTIFACT_SPECS[0],
        surface="adversarial-artifact",
        path="schemas/adversarial.schema.json",
        frozen=True,
        frozen_sha256="0" * 64,
    )
    problems: list[str] = []

    catalog._validate_spec_artifact(tmp_path, spec, b"expected\n", problems)

    assert problems == [
        "bytes:adversarial-artifact",
        "frozen_hash:adversarial-artifact",
    ]


def test_wire_dispatch_helpers_reject_malformed_documents() -> None:
    exact_unknown_trace = {
        "event_type": "undeclared-event",
        "protocol_id": "pheroos.protocol.v1",
        "target": "target:test",
        "reason": "adversarial",
        "lineage": {},
    }
    with pytest.raises(ValueError, match="fields are not exact"):
        catalog._read_trace_event({"event_type": "missing-required-fields"})
    with pytest.raises(ValueError):
        catalog._wire_trace(exact_unknown_trace, "trace")

    invalid_calls = (
        (catalog._wire_conformance_report, {}),
        (catalog._wire_scoped_trace, {}),
        (catalog._wire_authority_v2, {}),
        (catalog._wire_scoped_authority_tck_v2, {}),
        (catalog._wire_commit_tck_request_v2, {}),
        (catalog._wire_commit_tck_response_v2, {}),
    )
    for validator, payload in invalid_calls:
        with pytest.raises((TypeError, ValueError, KeyError)):
            validator(payload, "adversarial-wire")

    with pytest.raises(ValueError):
        catalog._wire_commit({}, "commit")


def test_legacy_surface_guards_reject_scoped_or_invalid_values() -> None:
    with pytest.raises(ValueError, match="scoped manifest"):
        catalog._validate_legacy_capability(object())
    with pytest.raises(ValueError, match="scoped manifest"):
        catalog._validate_legacy_protocol(object())

    invalid_protocol = ProtocolManifest(
        protocol_version="unsupported",
        id="",
        targets=[],
        candidates=[],
        quorum_policy=QuorumPolicy(target="", fallback_candidate=""),
    )
    invalid_capability = CapabilityManifest(
        id="",
        name="",
        version="",
        protocol=invalid_protocol,
    )
    with pytest.raises(ValueError):
        catalog._validate_legacy_capability(invalid_capability)
    with pytest.raises(ValueError):
        catalog._validate_legacy_protocol(invalid_protocol)


def test_valid_informational_trace_and_tck_loader_reach_owned_dispatch() -> None:
    event = catalog._read_trace_event(
        {
            "event_type": "plan",
            "protocol_id": "pheroos.protocol.v1",
            "target": "target:test",
            "reason": "provider-free plan",
            "lineage": {},
        }
    )
    assert event.event_type == "plan"

    with pytest.raises((FileNotFoundError, ValueError)):
        catalog._wire_commit_tck_v1({}, "missing-commit-tck.json")

    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="must be text"):
        text_value(1, "runtime label")


def test_scoped_trace_frozen_renderer_rejects_shape_drift() -> None:
    with pytest.raises(TypeError, match="object properties"):
        catalog._render_scoped_trace_v1_artifact({"type": "object"})
    with pytest.raises(ValueError, match="property set changed"):
        catalog._render_scoped_trace_v1_artifact(
            {"type": "object", "properties": {"unexpected": {}}}
        )

    assert catalog._sorted_json_value({"z": [2, {"b": 1, "a": 0}]}) == {
        "z": [2, {"a": 0, "b": 1}]
    }
