import json
from pathlib import Path
from typing import Any

from pheroos.cli.main import main


def test_schema_export_matches_checked_in_surface_artifacts(capsys: Any) -> None:
    for surface in ["capability", "protocol", "kernel", "driver", "trace"]:
        schema = exported_schema(surface, capsys)
        expected = json.loads(Path(f"schemas/{surface}.schema.json").read_text())

        assert schema == expected


def test_schema_export_capability_exposes_full_manifest_shape(capsys: Any) -> None:
    schema = exported_schema("capability", capsys)
    properties = schema["properties"]
    protocol_properties = properties["protocol"]["properties"]

    assert schema["$id"] == "https://pheroos.dev/schemas/capability.schema.json"
    assert schema["required"] == ["id", "name", "version", "protocol"]
    assert properties["drivers"]["items"]["required"] == ["id", "kind", "version"]
    assert protocol_properties["recovery_protocols"]["items"]["required"] == ["id", "trigger_targets"]
    assert protocol_properties["evidence_policy"]["properties"]["require_provenance"]["type"] == "boolean"
    assert protocol_properties["output_policy"]["properties"]["requires_committed_candidate"]["type"] == "boolean"
    assert schema["additionalProperties"] is False
    assert "^(x-|ext\\.).+" in schema["patternProperties"]


def test_schema_export_protocol_exposes_collective_policy_shape(capsys: Any) -> None:
    schema = exported_schema("protocol", capsys)
    properties = schema["properties"]
    collective_properties = properties["collective_decision_policy"]["properties"]

    assert schema["$id"] == "https://pheroos.dev/schemas/protocol.schema.json"
    assert schema["required"] == [
        "protocol_version",
        "id",
        "targets",
        "candidates",
        "quorum_policy",
        "output_policy",
        "trace_policy",
    ]
    assert properties["targets"]["items"]["required"] == ["id"]
    assert properties["targets"]["items"]["properties"]["extensions"]["type"] == "object"
    assert properties["candidates"]["items"]["required"] == ["id", "target"]
    assert properties["candidates"]["items"]["properties"]["extensions"]["type"] == "object"
    assert properties["signals"]["items"]["properties"]["extensions"]["type"] == "object"
    assert properties["quorum_policy"]["properties"]["extensions"]["type"] == "object"
    assert collective_properties["mode"]["enum"] == ["quorum", "bee_swarm", "ant_colony", "hybrid"]
    assert collective_properties["min_independent_scouts"]["minimum"] == 1
    assert collective_properties["quorum_threshold"]["minimum"] == 1
    assert collective_properties["pheromone_evaporation_rate"]["maximum"] == 1
    assert collective_properties["pheromone_decay_model"]["enum"] == ["linear", "exponential", "step"]
    assert collective_properties["pheromone_positive_weight"]["minimum"] == 0
    assert collective_properties["pheromone_negative_weight"]["minimum"] == 0
    assert collective_properties["pheromone_cautionary_weight"]["minimum"] == 0
    assert collective_properties["pheromone_cautionary_override_threshold"]["minimum"] == 0
    assert collective_properties["pheromone_novelty_weight"]["minimum"] == 0
    assert collective_properties["pheromone_per_source_cap"]["minimum"] == 0
    assert collective_properties["pheromone_per_round_deposit_cap"]["minimum"] == 0
    assert collective_properties["pheromone_min_source_diversity"]["minimum"] == 1
    assert collective_properties["pheromone_require_provenance"]["type"] == "boolean"
    assert collective_properties["pheromone_require_trace"]["type"] == "boolean"
    assert collective_properties["extensions"]["type"] == "object"
    assert properties["extensions"]["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "^(x-|ext\\.).+" in schema["patternProperties"]


def test_schema_export_driver_exposes_provider_neutral_driver_spec(capsys: Any) -> None:
    schema = exported_schema("driver", capsys)
    properties = schema["properties"]

    assert properties["permissions"]["items"]["type"] == "string"
    assert properties["config_ref"]["type"] == "string"
    assert properties["extensions"]["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "^(x-|ext\\.).+" in schema["patternProperties"]


def test_schema_export_kernel_exposes_strict_runtime_context_shape(capsys: Any) -> None:
    schema = exported_schema("kernel", capsys)

    assert schema["additionalProperties"] is False


def test_schema_export_trace_documents_namespaced_extension_events(capsys: Any) -> None:
    schema = exported_schema("trace", capsys)

    assert "x-*" in schema["properties"]["event_type"]["description"]
    assert "ext.*" in schema["properties"]["event_type"]["description"]
    assert schema["additionalProperties"] is False


def exported_schema(surface: str, capsys: Any) -> dict[str, Any]:
    status = main(["schema", "export", surface])
    captured = capsys.readouterr()

    assert status == 0
    return json.loads(captured.out)
