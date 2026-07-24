import json
from dataclasses import replace
from pathlib import Path

import pytest

from pheroos.protocol import (
    DriverSpec,
    load_capability_manifest,
    validate_capability_manifest,
)
from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.protocol.schema import capability_schema, capability_schema_v2
from pheroos.protocol.schema_validation import validate_json_schema


def test_toy_manifest_validates_without_errors() -> None:
    manifest = load_capability_manifest("examples/toy-protocol/capability.json")

    diagnostics = validate_capability_manifest(manifest)

    assert diagnostics == []


@pytest.mark.parametrize("protocol_version", ["pheroos.protocol.v999", ""])
def test_manifest_schema_and_loader_reject_unsupported_protocol_versions(
    protocol_version: str,
) -> None:
    payload = json.loads(Path("examples/toy-protocol/capability.json").read_text())
    payload["protocol"]["protocol_version"] = protocol_version

    generated_errors = validate_json_schema(payload, capability_schema_v2())
    checked_in_schema = json.loads(
        Path("schemas/capability-v2.schema.json").read_text()
    )
    artifact_errors = validate_json_schema(payload, checked_in_schema)

    expected_path = "$.protocol.protocol_version"
    assert any(expected_path in item for item in generated_errors)
    assert any(expected_path in item for item in artifact_errors)
    with pytest.raises(ValueError, match="manifest schema invalid") as exc:
        capability_manifest_from_dict(payload)
    assert expected_path in str(exc.value)


@pytest.mark.parametrize(
    ("protocol_version", "expected_code"),
    [
        ("pheroos.protocol.v999", "protocol_version_unsupported"),
        ("", "protocol_version_invalid"),
        ("   ", "protocol_version_invalid"),
    ],
)
def test_typed_manifest_validation_rejects_unsupported_protocol_versions(
    protocol_version: str,
    expected_code: str,
) -> None:
    manifest = load_capability_manifest("examples/toy-protocol/capability.json")
    protocol = replace(manifest.protocol, protocol_version=protocol_version)

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))

    assert [(item.code, item.path) for item in diagnostics] == [
        (expected_code, "protocol.protocol_version")
    ]


def test_unknown_protocol_version_combined_with_invalid_shape_reports_all_paths() -> (
    None
):
    payload = json.loads(Path("examples/toy-protocol/capability.json").read_text())
    payload["protocol"]["protocol_version"] = "pheroos.protocol.v999"
    payload["protocol"]["quorum_policy"]["commit_threshold"] = 0

    expected_paths = {
        "$.protocol.protocol_version",
        "$.protocol.quorum_policy.commit_threshold",
    }
    generated_errors = validate_json_schema(payload, capability_schema_v2())
    checked_in_schema = json.loads(
        Path("schemas/capability-v2.schema.json").read_text()
    )
    artifact_errors = validate_json_schema(payload, checked_in_schema)

    for expected_path in expected_paths:
        assert any(expected_path in item for item in generated_errors)
        assert any(expected_path in item for item in artifact_errors)
    with pytest.raises(ValueError, match="manifest schema invalid") as exc:
        capability_manifest_from_dict(payload)
    for expected_path in expected_paths:
        assert expected_path in str(exc.value)


def test_manifest_loader_preserves_namespaced_extension_metadata() -> None:
    payload = json.loads(Path("examples/e2e-protocol/capability.json").read_text())
    payload["extensions"] = {"x-runtime": {"owner": "external"}}
    payload["x-acme.runtime"] = {"adapter": "outside-core"}
    payload["drivers"][0]["extensions"] = {"x-driver": {"adapter": "external"}}
    payload["drivers"][0]["x-acme.driver"] = {"kind": "test-double"}
    payload["protocol"]["extensions"] = {"x-protocol": {"mode": "integration"}}
    payload["protocol"]["targets"][0]["x-target"] = {"scope": "declared"}
    payload["protocol"]["candidates"][0]["extensions"] = {"x-candidate": {"rank": 1}}
    payload["protocol"]["signals"][0]["extensions"] = {"x-signal": {"source": "agent"}}

    manifest = capability_manifest_from_dict(payload)

    assert manifest.extensions["x-runtime"] == {"owner": "external"}
    assert manifest.extensions["x-acme.runtime"] == {"adapter": "outside-core"}
    assert manifest.protocol.extensions["x-protocol"] == {"mode": "integration"}
    assert manifest.protocol.targets[0].extensions["x-target"] == {"scope": "declared"}
    assert manifest.protocol.candidates[0].extensions["x-candidate"] == {"rank": 1}
    assert manifest.protocol.signals[0].extensions["x-signal"] == {"source": "agent"}
    assert isinstance(manifest.drivers[0], DriverSpec)
    assert manifest.drivers[0].extensions["x-driver"] == {"adapter": "external"}
    assert manifest.drivers[0].extensions["x-acme.driver"] == {"kind": "test-double"}
    assert validate_capability_manifest(manifest) == []


def test_manifest_loader_preserves_collective_policy_extensions() -> None:
    payload = json.loads(Path("examples/swarm-protocol/capability.json").read_text())
    payload["protocol"]["collective_decision_policy"]["extensions"] = {
        "x-collective": {"memory": "external-runtime-owned"}
    }
    payload["protocol"]["collective_decision_policy"]["x-acme.policy"] = {
        "mode": "observed"
    }

    manifest = capability_manifest_from_dict(payload)

    assert manifest.protocol.collective_decision_policy is not None
    assert manifest.protocol.collective_decision_policy.extensions["x-collective"] == {
        "memory": "external-runtime-owned"
    }
    assert manifest.protocol.collective_decision_policy.extensions["x-acme.policy"] == {
        "mode": "observed"
    }


def test_e2e_manifest_loads_provider_neutral_driver_specs() -> None:
    manifest = load_capability_manifest("examples/e2e-protocol/capability.json")
    driver = manifest.drivers[0]

    assert isinstance(driver, DriverSpec)
    assert driver.id == "driver:toy-evidence"
    assert driver.kind == "tool"
    assert driver.permissions == ("driver:invoke",)
    assert driver.config_ref == ""
    assert driver.extensions == {}


def test_manifest_loader_rejects_secret_like_fields_before_dropping_unknowns() -> None:
    payload = json.loads(Path("examples/toy-protocol/capability.json").read_text())
    payload["api_key"] = "not-allowed"

    with pytest.raises(ValueError, match="secret-like manifest fields"):
        capability_manifest_from_dict(payload)


def test_protocol_validation_reports_secret_like_extension_fields() -> None:
    manifest = load_capability_manifest("examples/toy-protocol/capability.json")
    bad_manifest = replace(manifest, extensions={"x-runtime": {"token": "not-allowed"}})

    diagnostics = validate_capability_manifest(bad_manifest)

    assert {item.code for item in diagnostics} == {"secret_like_manifest_field"}
    assert diagnostics[0].path == "extensions.x-runtime.token"


@pytest.mark.parametrize(
    ("mutate", "expected_detail"),
    [
        (
            lambda payload: payload["protocol"]["quorum_policy"].__setitem__(
                "commit_threshold", 0
            ),
            "$.protocol.quorum_policy.commit_threshold",
        ),
        (
            lambda payload: payload["protocol"]["targets"].append("not-object"),
            "$.protocol.targets[1]",
        ),
        (
            lambda payload: payload["drivers"]
            .__getitem__(0)
            .__setitem__("capabilities", "not-list"),
            "$.drivers[0].capabilities",
        ),
        (
            lambda payload: payload["protocol"]["candidates"]
            .__getitem__(0)
            .__setitem__("safe_fallback", "false"),
            "$.protocol.candidates[0].safe_fallback",
        ),
        (
            lambda payload: payload["protocol"]["trace_policy"].__setitem__(
                "required_events", "commit"
            ),
            "$.protocol.trace_policy.required_events",
        ),
        (
            lambda payload: payload["protocol"]["targets"]
            .__getitem__(0)
            .__setitem__("unexpected", "value"),
            "$.protocol.targets[0].unexpected",
        ),
    ],
)
def test_manifest_loader_rejects_invalid_manifest_shape(
    mutate, expected_detail: str
) -> None:
    payload = json.loads(Path("examples/e2e-protocol/capability.json").read_text())
    mutate(payload)

    with pytest.raises(ValueError, match="manifest schema invalid") as exc:
        capability_manifest_from_dict(payload)

    assert expected_detail in str(exc.value)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_manifest_file_loader_rejects_non_finite_json_constants(
    tmp_path: Path, constant: str
) -> None:
    raw = Path("examples/hybrid-pheromone-protocol/capability.json").read_text()
    raw = raw.replace(
        '"pheromone_evaporation_rate": 0.2', f'"pheromone_evaporation_rate": {constant}'
    )
    path = tmp_path / "capability.json"
    path.write_text(raw)

    with pytest.raises(ValueError, match="non-finite JSON number"):
        load_capability_manifest(path)


def test_manifest_file_loader_rejects_duplicate_json_object_keys(
    tmp_path: Path,
) -> None:
    raw = Path("examples/toy-protocol/capability.json").read_text()
    raw = raw.replace(
        '"name": "Toy Protocol",',
        '"name": "Toy Protocol", "name": "Duplicate",',
    )
    path = tmp_path / "capability.json"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON object key"):
        load_capability_manifest(path)


@pytest.mark.parametrize("extension_style", ["extensions", "namespaced"])
def test_manifest_loader_rejects_exponent_overflow_in_extension_metadata(
    tmp_path: Path,
    extension_style: str,
) -> None:
    payload = json.loads(Path("examples/toy-protocol/capability.json").read_text())
    if extension_style == "extensions":
        payload.setdefault("extensions", {})["x-overflow"] = {"nested": "__OVERFLOW__"}
    else:
        payload["x-overflow"] = {"nested": "__OVERFLOW__"}
    path = tmp_path / "capability.json"
    path.write_text(
        json.dumps(payload).replace('"__OVERFLOW__"', "1e999"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-finite JSON number"):
        load_capability_manifest(path)


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (
            lambda policy: policy["pheromone_kind_profiles"].__setitem__(
                "positive", "not-an-object"
            ),
            "$.protocol.collective_decision_policy.pheromone_kind_profiles.positive",
        ),
        (
            lambda policy: policy["pheromone_kind_profiles"]["positive"].__setitem__(
                "weight", True
            ),
            "$.protocol.collective_decision_policy.pheromone_kind_profiles.positive.weight",
        ),
        (
            lambda policy: policy["layer_default_weights"].__setitem__(
                "learned", "1.0"
            ),
            "$.protocol.collective_decision_policy.layer_default_weights.learned",
        ),
        (
            lambda policy: policy["layer_weight_bounds"].__setitem__(
                "learned", [0, 1, 2]
            ),
            "$.protocol.collective_decision_policy.layer_weight_bounds.learned",
        ),
        (
            lambda policy: policy["policy_adjustment_bounds"].__setitem__(
                "manifest", [0, 1]
            ),
            "$.protocol.collective_decision_policy.policy_adjustment_bounds.manifest",
        ),
        (
            lambda policy: policy["policy_adjustment_bounds"].__setitem__(
                "pheromone_response_model",
                {"allowed_values": []},
            ),
            "$.protocol.collective_decision_policy.policy_adjustment_bounds.pheromone_response_model.allowed_values",
        ),
    ],
)
def test_hybrid_raw_json_shape_is_rejected_consistently_by_schema_and_loader(
    mutate,
    expected_path: str,
) -> None:
    payload = json.loads(
        Path("examples/hybrid-pheromone-protocol/capability.json").read_text()
    )
    mutate(payload["protocol"]["collective_decision_policy"])
    generated_errors = validate_json_schema(payload, capability_schema())
    checked_in_schema = json.loads(Path("schemas/capability.schema.json").read_text())
    artifact_errors = validate_json_schema(payload, checked_in_schema)

    assert any(expected_path in item for item in generated_errors)
    # The checked-in artifact is regenerated from the same schema in this change.
    assert any(expected_path in item for item in artifact_errors)
    with pytest.raises(ValueError, match="manifest schema invalid") as exc:
        capability_manifest_from_dict(payload)
    assert expected_path in str(exc.value)


def test_manifest_mapping_does_not_repair_invalid_kind_profile_to_defaults() -> None:
    payload = json.loads(
        Path("examples/hybrid-pheromone-protocol/capability.json").read_text()
    )
    payload["protocol"]["collective_decision_policy"]["pheromone_kind_profiles"][
        "alarm"
    ] = []

    with pytest.raises(ValueError, match="pheromone_kind_profiles.alarm"):
        capability_manifest_from_dict(payload)


def test_direct_payload_with_non_finite_number_is_rejected_before_typed_mapping() -> (
    None
):
    payload = json.loads(
        Path("examples/hybrid-pheromone-protocol/capability.json").read_text()
    )
    payload["protocol"]["collective_decision_policy"]["pheromone_evaporation_rate"] = (
        float("nan")
    )

    with pytest.raises(ValueError, match="must be finite"):
        capability_manifest_from_dict(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "requires_committed_candidate",
        "requires_evidence_contract",
        "requires_stop_resolution",
        "requires_publication_permission",
    ],
)
def test_manifest_schema_rejects_disabling_mandatory_output_gate(
    field_name: str,
) -> None:
    payload = json.loads(Path("examples/e2e-protocol/capability.json").read_text())
    payload["protocol"]["output_policy"][field_name] = False

    errors = validate_json_schema(payload, capability_schema())

    assert any(f"$.protocol.output_policy.{field_name}" in item for item in errors)
    with pytest.raises(ValueError, match=rf"output_policy\.{field_name}"):
        capability_manifest_from_dict(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "requires_committed_candidate",
        "requires_evidence_contract",
        "requires_stop_resolution",
        "requires_publication_permission",
    ],
)
def test_typed_manifest_validation_rejects_disabling_mandatory_output_gate(
    field_name: str,
) -> None:
    manifest = load_capability_manifest("examples/e2e-protocol/capability.json")
    output_policy = replace(manifest.protocol.output_policy, **{field_name: False})
    protocol = replace(manifest.protocol, output_policy=output_policy)

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))

    assert [(item.code, item.path) for item in diagnostics] == [
        ("output_gate_disabled", f"protocol.output_policy.{field_name}")
    ]


def test_json_schema_integer_value_is_normalized_to_python_int() -> None:
    payload = json.loads(
        Path("examples/hybrid-pheromone-protocol/capability.json").read_text()
    )
    payload["protocol"]["collective_decision_policy"]["pheromone_kind_profiles"][
        "alarm"
    ]["ttl_steps"] = 1.0

    manifest = capability_manifest_from_dict(payload)
    ttl_steps = manifest.protocol.collective_decision_policy.pheromone_kind_profiles[
        "alarm"
    ].ttl_steps

    assert ttl_steps == 1
    assert isinstance(ttl_steps, int)
