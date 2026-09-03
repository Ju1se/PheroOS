import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from pheroos.cli.main import main
from pheroos.trace import TraceEvent
from pheroos.trace._pheromone_receipts import pheromone_clip_payload_fingerprint


def test_schema_export_matches_checked_in_surface_artifacts(capsys: Any) -> None:
    artifacts = {
        "capability": "schemas/capability.schema.json",
        "capability-v1": "schemas/capability.schema.json",
        "capability-v2": "schemas/capability-v2.schema.json",
        "capability-v3": "schemas/capability-v3.schema.json",
        "protocol": "schemas/protocol.schema.json",
        "protocol-v1": "schemas/protocol.schema.json",
        "protocol-v2": "schemas/protocol-v2.schema.json",
        "protocol-v3": "schemas/protocol-v3.schema.json",
        "kernel": "schemas/kernel.schema.json",
        "kernel-v1": "schemas/kernel.schema.json",
        "kernel-v2": "schemas/kernel-v2.schema.json",
        "runtime-scope-v1": "schemas/runtime-scope-v1.schema.json",
        "driver": "schemas/driver.schema.json",
        "driver-v1": "schemas/driver.schema.json",
        "driver-v2": "schemas/driver-v2.schema.json",
        "trace": "schemas/trace.schema.json",
        "commit": "schemas/commit.schema.json",
        "conformance-report": "schemas/conformance-report-v2.schema.json",
        "scoped-trace": "schemas/scoped-trace-event-v1.schema.json",
        "authority-v2": "schemas/authority-v2.schema.json",
        "scoped-authority-tck-v2": "schemas/scoped-authority-tck-v2.schema.json",
        "commit-tck-v1": "schemas/commit-tck.schema.json",
        "commit-tck-v2": "schemas/commit-tck-v2.schema.json",
        "commit-tck-request-v2": "schemas/commit-tck-request-v2.schema.json",
        "commit-tck-response-v2": "schemas/commit-tck-response-v2.schema.json",
    }
    for surface, artifact in artifacts.items():
        schema = exported_schema(surface, capsys)
        expected = json.loads(Path(artifact).read_text())

        assert schema == expected


def test_schema_export_capability_exposes_full_manifest_shape(capsys: Any) -> None:
    schema = exported_schema("capability", capsys)
    properties = schema["properties"]
    protocol_properties = properties["protocol"]["properties"]

    assert schema["$id"] == "https://pheroos.dev/schemas/capability.schema.json"
    assert schema["required"] == ["id", "name", "version", "protocol"]
    assert properties["drivers"]["items"]["required"] == ["id", "kind", "version"]
    assert protocol_properties["recovery_protocols"]["items"]["required"] == [
        "id",
        "trigger_targets",
    ]
    assert (
        protocol_properties["evidence_policy"]["properties"]["require_provenance"][
            "type"
        ]
        == "boolean"
    )
    output_properties = protocol_properties["output_policy"]["properties"]
    assert output_properties["requires_committed_candidate"] == {
        "type": "boolean",
        "const": True,
    }
    assert output_properties["requires_evidence_contract"] == {
        "type": "boolean",
        "const": True,
    }
    assert output_properties["requires_stop_resolution"] == {
        "type": "boolean",
        "const": True,
    }
    assert output_properties["requires_publication_permission"] == {
        "type": "boolean",
        "const": True,
    }
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
    # The original unversioned ID is the byte-frozen legacy v1 document.
    # Strict supported-version validation is exposed as ``protocol-v2``.
    assert properties["protocol_version"] == {"type": "string"}
    assert properties["targets"]["items"]["required"] == ["id"]
    assert (
        properties["targets"]["items"]["properties"]["extensions"]["type"] == "object"
    )
    assert properties["candidates"]["items"]["required"] == ["id", "target"]
    assert (
        properties["candidates"]["items"]["properties"]["extensions"]["type"]
        == "object"
    )
    assert (
        properties["signals"]["items"]["properties"]["extensions"]["type"] == "object"
    )
    assert properties["quorum_policy"]["properties"]["extensions"]["type"] == "object"
    assert collective_properties["mode"]["enum"] == [
        "quorum",
        "bee_swarm",
        "ant_colony",
        "hybrid",
    ]
    assert collective_properties["min_independent_scouts"]["minimum"] == 1
    assert collective_properties["quorum_threshold"]["minimum"] == 1
    assert collective_properties["pheromone_evaporation_rate"]["maximum"] == 1
    assert collective_properties["pheromone_decay_model"]["enum"] == [
        "linear",
        "exponential",
        "step",
    ]
    assert collective_properties["pheromone_positive_weight"]["minimum"] == 0
    assert collective_properties["pheromone_negative_weight"]["minimum"] == 0
    assert collective_properties["pheromone_cautionary_weight"]["minimum"] == 0
    assert (
        collective_properties["pheromone_cautionary_override_threshold"]["minimum"] == 0
    )
    assert collective_properties["pheromone_novelty_weight"]["minimum"] == 0
    assert collective_properties["pheromone_per_source_cap"]["minimum"] == 0
    assert collective_properties["pheromone_per_round_deposit_cap"]["minimum"] == 0
    assert collective_properties["pheromone_min_source_diversity"]["minimum"] == 1
    assert collective_properties["pheromone_require_provenance"]["type"] == "boolean"
    assert collective_properties["pheromone_require_trace"]["type"] == "boolean"
    assert (
        collective_properties["pheromone_scored_subject_types"]["items"]["type"]
        == "string"
    )
    assert (
        collective_properties["pheromone_kind_profiles"]["additionalProperties"]
        is False
    )
    kind_profile_schemas = collective_properties["pheromone_kind_profiles"][
        "patternProperties"
    ]
    assert (
        next(value for key, value in kind_profile_schemas.items() if "positive" in key)[
            "properties"
        ]["weight"]["minimum"]
        == 0
    )
    assert collective_properties["pheromone_response_model"]["enum"] == [
        "linear",
        "saturating",
        "threshold",
        "competitive",
    ]
    assert collective_properties["pheromone_competition_mode"]["enum"] == [
        "none",
        "normalize",
    ]
    assert collective_properties["pheromone_diffusion_attenuation"]["maximum"] == 1
    assert collective_properties["pheromone_feedback_enabled"]["type"] == "boolean"
    assert (
        next(
            iter(
                collective_properties["layer_weight_bounds"][
                    "patternProperties"
                ].values()
            )
        )["oneOf"][0]["maxItems"]
        == 2
    )
    assert (
        next(
            iter(
                collective_properties["layer_confidence_thresholds"][
                    "patternProperties"
                ].values()
            )
        )["maximum"]
        == 1
    )
    assert (
        collective_properties["policy_adjustment_bounds"]["additionalProperties"]
        is False
    )
    adjustment_patterns = collective_properties["policy_adjustment_bounds"][
        "patternProperties"
    ]
    assert (
        adjustment_patterns["^pheromone_response_model$"]["properties"][
            "allowed_values"
        ]["type"]
        == "array"
    )
    assert all(
        "layer_reactive_weight" not in pattern for pattern in adjustment_patterns
    )
    assert collective_properties["extensions"]["type"] == "object"
    assert properties["extensions"]["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "^(x-|ext\\.).+" in schema["patternProperties"]


def test_schema_export_v2_protocol_documents_are_strict_without_changing_payload_version(
    capsys: Any,
) -> None:
    capability = exported_schema("capability-v2", capsys)
    protocol = exported_schema("protocol-v2", capsys)

    assert capability["$id"] == (
        "https://pheroos.dev/schemas/capability-v2.schema.json"
    )
    assert protocol["$id"] == ("https://pheroos.dev/schemas/protocol-v2.schema.json")
    assert protocol["properties"]["protocol_version"] == {
        "type": "string",
        "enum": ["pheroos.protocol.v1"],
    }
    assert capability["properties"]["protocol"]["properties"]["protocol_version"] == {
        "type": "string",
        "enum": ["pheroos.protocol.v1"],
    }


def test_schema_export_commit_is_strict_and_versioned(capsys: Any) -> None:
    schema = exported_schema("commit", capsys)

    assert schema["$id"] == "https://pheroos.dev/schemas/commit.schema.json"
    schemas = {branch["properties"]["schema"]["const"] for branch in schema["oneOf"]}
    expected_schemas = {
        "pheroos-principal-attestation-v1",
        "pheroos-principal-verification-v1",
        "pheroos-stop-resolution-verification-v1",
        "pheroos-action-permission-v1",
        "pheroos-decision-progress-v1",
        "pheroos-decision-outcome-v1",
        "pheroos-commit-evaluation-context-v1",
        "pheroos-candidate-commit-metrics-v1",
        "pheroos-optimal-commit-assessment-v1",
        "pheroos-commit-window-state-v1",
        "pheroos-commit-window-seal-v1",
        "pheroos-commit-liveness-input-v1",
        "pheroos-commit-finality-verification-v1",
        "pheroos-commit-replay-state-v1",
        "pheroos-commit-replay-receipt-v1",
        "pheroos-observation-attestation-v1",
        "pheroos-verified-observation-v1",
        "pheroos-counterevidence-disposition-v1",
        "pheroos-challenge-attestation-v1",
        "pheroos-verified-challenge-v1",
        "pheroos-challenge-coverage-v1",
        "pheroos-evidence-binding-authority-v1",
        "pheroos-evidence-summary-v1",
        "pheroos-eligible-principal-snapshot-v1",
        "pheroos-eligible-membership-epoch-state-v1",
        "pheroos-support-lease-proposal-v1",
        "pheroos-support-lease-replay-receipt-v1",
        "pheroos-support-lease-replay-state-v1",
        "pheroos-support-lease-v1",
        "pheroos-support-lease-revocation-v1",
        "pheroos-support-lease-evaluation-v1",
        "pheroos-support-equivocation-finding-v1",
        "pheroos-risk-assessment-chain-state-v1",
        "pheroos-risk-assessment-v1",
        "pheroos-commit-threshold-snapshot-v1",
        "pheroos-hybrid-commit-step-v1",
        "pheroos-hybrid-commit-evaluation-v1",
        "pheroos-local-commit-receipt-v1",
        "pheroos-evidence-commit-certificate-v1",
        "pheroos-outcome-certificate-v1",
        "pheroos-commit-output-authorization-v1",
        "pheroos-portable-membership-snapshot-v1",
        "pheroos-distributed-commit-proposal-v1",
        "pheroos-distributed-commit-value-v1",
        "pheroos-quorum-witness-v1",
        "pheroos-witness-verification-v1",
        "pheroos-witness-replay-receipt-v1",
        "pheroos-distributed-commit-state-v1",
        "pheroos-distributed-commit-certificate-v1",
        "pheroos-epoch-transition-certificate-v1",
        "pheroos-distributed-finality-decision-v1",
    }
    assert len(schema["oneOf"]) == len(expected_schemas) == 51
    assert schemas == expected_schemas
    assert schema["discriminator"] == {"propertyName": "schema"}
    assert all(branch["additionalProperties"] is False for branch in schema["oneOf"])
    assert all(
        branch["properties"]["payload"]["additionalProperties"] is False
        for branch in schema["oneOf"]
    )


def test_schema_export_commit_is_external_cwd_stable(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pheroos.cli.main", "schema", "export", "commit"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == json.loads(
        Path("schemas/commit.schema.json").read_text(encoding="utf-8")
    )


def test_schema_export_driver_exposes_provider_neutral_driver_spec(capsys: Any) -> None:
    schema = exported_schema("driver-v2", capsys)
    properties = schema["properties"]

    assert schema["$id"] == "https://pheroos.dev/schemas/driver-v2.schema.json"
    assert properties["descriptor_version"] == {"const": "pheroos-driver-descriptor-v2"}
    assert properties["permissions"]["items"]["type"] == "string"
    assert properties["permissions"]["items"]["minLength"] == 1
    assert properties["permissions"]["uniqueItems"] is True
    assert properties["capabilities"]["items"]["minLength"] == 1
    assert properties["capabilities"]["uniqueItems"] is True
    assert properties["config_ref"]["type"] == "string"
    assert properties["extensions"]["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "^(x-|ext\\.).+" in schema["patternProperties"]


def test_schema_export_kernel_exposes_strict_runtime_context_shape(capsys: Any) -> None:
    schema = exported_schema("kernel-v2", capsys)
    properties = schema["properties"]

    assert schema["$id"] == "https://pheroos.dev/schemas/kernel-v2.schema.json"
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "plan_version",
        "tenant_id",
        "request_id",
        "run_id",
        "scope_ref",
        "capability_resolutions",
        "permission_grants",
        "connection_requirements",
        "connection_readiness",
        "driver_probe_snapshots",
        "driver_exposures",
        "tool_exposures",
        "diagnostics",
        "runtime_ready",
        "degraded",
    ]
    assert properties["plan_version"] == {"const": "pheroos-kernel-plan-v2"}
    assert properties["scope_ref"] == {
        "type": "string",
        "pattern": "^sha256:[0-9a-f]{64}$",
    }
    assert properties["capability_resolutions"]["items"]["required"] == [
        "capability_id",
        "available",
    ]
    assert properties["permission_grants"]["items"]["required"] == [
        "capability_id",
        "permission",
    ]
    assert properties["connection_requirements"]["items"]["required"] == [
        "capability_id",
        "connection",
    ]
    assert properties["connection_readiness"]["items"]["required"] == [
        "connection",
        "available",
    ]
    assert properties["driver_probe_snapshots"]["items"]["required"] == [
        "driver_id",
        "available",
        "version",
        "capabilities",
    ]
    assert properties["driver_exposures"]["items"]["required"] == [
        "driver_id",
        "capability_id",
    ]
    assert properties["driver_exposures"]["items"]["properties"]["capabilities"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert properties["tool_exposures"]["items"]["required"] == [
        "tool_id",
        "capability_id",
    ]
    assert properties["diagnostics"]["items"]["required"] == ["code", "message"]


def test_schema_export_trace_documents_namespaced_extension_events(capsys: Any) -> None:
    schema = exported_schema("trace", capsys)

    assert "x-*" in schema["properties"]["event_type"]["description"]
    assert "ext.*" in schema["properties"]["event_type"]["description"]
    assert schema["additionalProperties"] is False


def test_schema_export_trace_exposes_event_specific_lineage_contracts(
    capsys: Any,
) -> None:
    schema = exported_schema("trace", capsys)
    conditions = {
        item["if"]["properties"]["event_type"]["const"]: item["then"]["properties"][
            "lineage"
        ]
        for item in schema["allOf"]
    }

    clip = conditions["pheromone_clip"]
    assert clip["properties"]["applied_strength"]["minimum"] == 0
    assert (
        clip["properties"]["causal_fingerprint"]["pattern"] == "^sha256:[0-9a-f]{64}$"
    )
    assert {
        branch["properties"]["lifecycle"]["const"]
        for branch in clip["properties"]["causal_payload"]["oneOf"]
    } == {"deposit", "diffusion", "feedback"}
    rejected_receipt = next(
        item
        for item in clip["allOf"]
        if item["if"]["properties"].get("result") == {"const": "rejected"}
    )
    assert rejected_receipt["then"]["required"] == [
        "causal_payload",
        "causal_fingerprint",
    ]
    assert len(conditions["pheromone_observe"]["oneOf"]) == 3
    assert conditions["pheromone_diffuse"]["properties"]["attenuation"]["maximum"] == 1
    assert conditions["pheromone_score"]["required"] == [
        "active_trails",
        "current_step",
        "kind_breakdown",
        "score_breakdown",
        "scores",
        "subject_breakdown",
    ]
    active_trail = conditions["pheromone_score"]["properties"]["active_trails"]["items"]
    assert active_trail["properties"]["updated_at_step"]["minimum"] == 0
    assert "competition_mode" in conditions["pheromone_normalize"]["required"]
    coordination = conditions["coordination_assess"]["properties"]
    assert coordination["confidences"]["properties"]["learned"]["maximum"] == 1
    assert coordination["confidences"]["additionalProperties"] is False
    assert coordination["weights"]["properties"]["reactive"]["minimum"] == 0
    assert (
        coordination["snapshots"]["properties"]["learned"]["properties"][
            "trace_coverage"
        ]["maximum"]
        == 1
    )
    assert coordination["proposal_lineage"].get("minItems") is None
    assert conditions["policy_adjustment"]["required"] == [
        "declared_bounds",
        "layer_id",
        "proposed_values",
        "provenance",
        "result",
        "source_id",
        "source_trace_event_id",
    ]
    assert len(conditions["output"]["allOf"]) == 2


def test_pheromone_observe_mixed_variant_is_rejected_by_runtime_and_schema(
    capsys: Any,
) -> None:
    schema = exported_schema("trace", capsys)
    conditions = {
        condition["if"]["properties"]["event_type"]["const"]: condition["then"][
            "properties"
        ]["lineage"]
        for condition in schema["allOf"]
    }
    receipt = ["deposit-v1", "candidate:alpha"]
    fingerprint = pheromone_clip_payload_fingerprint(
        {"lifecycle": "replay_receipt", "receipt": receipt}
    )
    mixed = {
        "lifecycle": "deposit",
        "result": "replay_ignored",
        "replay_payload": receipt,
        "replay_payload_fingerprint": fingerprint,
        "processed_payload_fingerprint": fingerprint,
        "candidate_id": "candidate:alpha",
        "subject_type": "route",
        "subject_id": "route:alpha",
        "novelty_pressure": 0.1,
        "reopen_eligible": True,
        "source_trace_event_id": "trace:deposit:a",
    }

    with pytest.raises(ValueError, match="exactly the replay receipt fields"):
        TraceEvent(
            event_type="pheromone_observe",
            protocol_id="swarm.collective",
            target="decision:e2e",
            reason="mixed observation variants are ambiguous",
            lineage=mixed,
        ).validate()

    branches = conditions["pheromone_observe"]["oneOf"]
    assert not any(
        set(branch["required"]).issubset(mixed)
        and (
            branch.get("additionalProperties", True) is not False
            or set(mixed).issubset(branch["properties"])
        )
        for branch in branches
    )


def exported_schema(surface: str, capsys: Any) -> dict[str, Any]:
    status = main(["schema", "export", surface])
    captured = capsys.readouterr()

    assert status == 0
    return json.loads(captured.out)
