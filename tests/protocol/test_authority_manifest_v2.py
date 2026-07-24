from __future__ import annotations

from collections import UserDict, UserList
from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import pheroos.protocol as protocol
import pheroos.protocol.schema_document as schema_document
from pheroos.protocol import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    CAPABILITY_SCHEMA_V2,
    CAPABILITY_SCHEMA_V3,
    PROTOCOL_SCHEMA_V3,
    PROTOCOL_VERSION_V2,
    BaselineOutputActionPolicyV2,
    BaselineOutputPolicyV2,
    CommitAssurance,
    ScopedAuthorityPolicyV2,
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    ValidationDiagnostic,
    read_capability_manifest,
    read_protocol_manifest,
)
from pheroos.protocol.authority_manifest_v2 import ScopedManifestV2Error
from pheroos.protocol.schema_document import ProtocolSchemaVersionError


ROOT = Path(__file__).resolve().parents[2]


class _TextMode(Enum):
    READY = "ready"
    LATE = "late"


@dataclass
class _MutableExtensionRecord:
    mode: _TextMode
    values: list[str]


def _payload() -> dict[str, object]:
    return json.loads(
        (ROOT / "examples/scoped-output-protocol/capability.json").read_text(
            encoding="utf-8"
        )
    )


def _full_policy_payload() -> dict[str, object]:
    """Lift the complete Hybrid Commit declaration into scoped v2 selectors."""

    scoped = _payload()
    source = json.loads(
        (ROOT / "examples/hybrid-commit-protocol/capability.json").read_text(
            encoding="utf-8"
        )
    )
    source_protocol = source["protocol"]
    scoped_protocol = scoped["protocol"]
    assert isinstance(source_protocol, dict)
    assert isinstance(scoped_protocol, dict)
    source_protocol["protocol_version"] = PROTOCOL_VERSION_V2
    source_protocol["authority_policy"] = deepcopy(scoped_protocol["authority_policy"])
    target = source_protocol["quorum_policy"]["target"]
    source_protocol["output_policy"] = {
        "policy_version": BASELINE_OUTPUT_POLICY_VERSION_V2,
        "decision_mode": "quorum",
        "actions": [
            {
                "action_ref": "action:hybrid-commit",
                "effect": "publish",
                "target": target,
                "allowed_outcomes": ["evidence_commit", "safe_fallback"],
            }
        ],
    }
    required_events = set(source_protocol["trace_policy"]["required_events"]) | set(
        scoped_protocol["trace_policy"]["required_events"]
    )
    source_protocol["trace_policy"]["required_events"] = sorted(required_events)
    scoped["protocol"] = source_protocol
    return scoped


def test_scoped_manifest_example_uses_exact_public_v2_types_and_roots() -> None:
    value = read_capability_manifest(_payload(), schema_version=CAPABILITY_SCHEMA_V3)

    assert type(value) is ScopedCapabilityManifestV2
    assert type(value.protocol) is ScopedProtocolManifestV2
    assert type(value.protocol.authority_policy) is ScopedAuthorityPolicyV2
    assert type(value.protocol.output_policy) is BaselineOutputPolicyV2
    assert value.protocol.protocol_version == PROTOCOL_VERSION_V2
    assert value.protocol.output_policy.policy_version == (
        BASELINE_OUTPUT_POLICY_VERSION_V2
    )
    assert value.root().startswith("sha256:")
    assert len(value.root()) == 71
    assert value.manifest_root == value.root()
    assert value.protocol.manifest_root == value.protocol.root()
    assert value.protocol.output_policy.policy_root == (
        value.protocol.output_policy.root()
    )
    assert value.root() == (
        "sha256:a30d72cad5f9cc81fb9e6ed8b1c5dad74e68f54dfa02c395e445a3e497aa7528"
    )
    assert value.protocol.root() == (
        "sha256:06837303bf54359c9a6f12fedb2e16bd2c1420a2919e3fb65fa71ca1d257e97d"
    )
    assert value.protocol.output_policy.root() == (
        "sha256:41d602b876f3aab2d4f894fc36fa66f5f559aa80670bcd51ccc4f504f1728b7d"
    )

    reread = ScopedCapabilityManifestV2.from_dict(value.to_dict())
    assert type(reread) is ScopedCapabilityManifestV2
    assert reread.to_dict() == value.to_dict()
    assert reread.root() == value.root()
    protocol_reread = ScopedProtocolManifestV2.from_dict(value.protocol.to_dict())
    assert protocol_reread.manifest_root == value.protocol.manifest_root


def test_scoped_protocol_reader_returns_exact_type_without_capability_envelope() -> (
    None
):
    payload = _payload()["protocol"]
    assert isinstance(payload, dict)

    value = read_protocol_manifest(payload, schema_version=PROTOCOL_SCHEMA_V3)

    assert type(value) is ScopedProtocolManifestV2
    assert value.output_policy.actions[0].effect == "publish"


def test_scoped_reader_does_not_promote_non_error_diagnostics_to_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        schema_document,
        "_scoped_protocol_semantic_diagnostics",
        lambda _protocol: [
            ValidationDiagnostic(
                code="extension_advisory",
                message="noncritical namespaced metadata is advisory",
                level="warning",
                path="protocol.extensions.x-observability",
            )
        ],
    )
    payload = _payload()
    protocol_payload = payload["protocol"]
    assert isinstance(protocol_payload, dict)
    protocol_payload["x-observability"] = {"mode": "external"}

    value = read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)

    assert type(value) is ScopedCapabilityManifestV2
    assert value.protocol.extensions["x-observability"] == {"mode": "external"}


def test_scoped_manifest_identity_rejects_nul_delimiter_material() -> None:
    payload = deepcopy(_payload()["protocol"])
    assert isinstance(payload, dict)
    payload["id"] = "protocol:scoped\x00run:alias"

    with pytest.raises(ScopedManifestV2Error, match=r"U\+0000"):
        ScopedProtocolManifestV2.from_dict(payload)


@pytest.mark.parametrize(
    "extension",
    [
        {"nested\x00key": "value"},
        {"nested": "value\x00suffix"},
        {"e\u0301": "decomposed-key"},
    ],
)
def test_scoped_extensions_reject_noncanonical_nested_keys_and_values(
    extension: dict[object, object],
) -> None:
    payload = _payload()
    protocol_payload = payload["protocol"]
    assert isinstance(protocol_payload, dict)
    protocol_payload["x-observability"] = extension

    with pytest.raises(ProtocolSchemaVersionError, match="scoped manifest strings"):
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)


def test_direct_scoped_extensions_never_coerce_keys_or_custom_mappings() -> None:
    value = read_capability_manifest(_payload(), schema_version=CAPABILITY_SCHEMA_V3)
    assert type(value) is ScopedCapabilityManifestV2

    with pytest.raises(ScopedManifestV2Error, match="exact non-empty strings"):
        replace(value, extensions={1: "integer", "1": "text"})
    with pytest.raises(ScopedManifestV2Error, match="exact dict or mappingproxy"):
        replace(value, extensions=UserDict({"x-observability": "external"}))


@pytest.mark.parametrize("owner", ("capability", "protocol"))
def test_scoped_extensions_are_recursive_canonical_snapshots(owner: str) -> None:
    capability = read_capability_manifest(
        _payload(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    assert type(capability) is ScopedCapabilityManifestV2

    class _MutablePayload(Enum):
        VALUE = {"items": ["enum:original"]}

    sequence_values = ["sequence:original"]
    record_values = ["record:original"]
    record = _MutableExtensionRecord(_TextMode.READY, record_values)
    nested: dict[str, object] = {
        "enum": _MutablePayload.VALUE,
        "record": record,
        "sequence": sequence_values,
    }
    source: dict[str, object] = {"x-snapshot": nested}
    declaration = (
        replace(capability, extensions=source)
        if owner == "capability"
        else replace(capability.protocol, extensions=source)
    )
    expected = {
        "x-snapshot": {
            "enum": {"items": ["enum:original"]},
            "record": {"mode": "ready", "values": ["record:original"]},
            "sequence": ["sequence:original"],
        }
    }
    wire_before = deepcopy(declaration.to_dict())
    root_before = declaration.root()

    assert wire_before["extensions"] == expected
    assert declaration.manifest_root == root_before

    enum_value = _MutablePayload.VALUE.value
    assert isinstance(enum_value, dict)
    enum_items = enum_value["items"]
    assert isinstance(enum_items, list)
    enum_items.append("enum:mutated")
    record_values.append("record:mutated")
    sequence_values.append("sequence:mutated")
    nested["late"] = "mutation"
    source["x-late"] = "mutation"

    assert declaration.to_dict() == wire_before
    assert declaration.root() == root_before
    assert declaration.manifest_root == root_before


def test_nested_declaration_extensions_cannot_change_protocol_root() -> None:
    capability = read_capability_manifest(
        _payload(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    assert type(capability) is ScopedCapabilityManifestV2
    record_values = ["target:original"]
    record = _MutableExtensionRecord(_TextMode.READY, record_values)
    target = replace(
        capability.protocol.targets[0],
        extensions={"x-record": record},
    )
    manifest = replace(
        capability.protocol,
        targets=(target, *capability.protocol.targets[1:]),
    )
    wire_before = deepcopy(manifest.to_dict())
    root_before = manifest.root()

    record_values.append("target:mutated")
    record.mode = _TextMode.LATE

    assert manifest.to_dict() == wire_before
    assert manifest.root() == root_before
    assert manifest.manifest_root == root_before


def test_public_protocol_projection_portably_unwraps_declared_string_enums() -> None:
    capability = read_capability_manifest(
        _full_policy_payload(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    assert type(capability) is ScopedCapabilityManifestV2
    commit_policy = capability.protocol.collective_commit_policy
    assert commit_policy is not None
    protocol_manifest = replace(
        capability.protocol,
        collective_commit_policy=replace(
            commit_policy,
            assurance=CommitAssurance.EVIDENCE_BOUND,
        ),
    )

    projected = protocol_manifest.to_dict()
    projected_commit_policy = projected["collective_commit_policy"]
    assert isinstance(projected_commit_policy, dict)
    assert projected_commit_policy["assurance"] == "evidence_bound"


def test_scoped_extension_roots_are_unique_without_key_normalization() -> None:
    first_payload = _payload()
    second_payload = _payload()
    first_protocol = first_payload["protocol"]
    second_protocol = second_payload["protocol"]
    assert isinstance(first_protocol, dict)
    assert isinstance(second_protocol, dict)
    first_protocol["x-observability"] = {"é": "value"}
    second_protocol["x-observability"] = {"e": "value"}

    first = read_capability_manifest(
        first_payload,
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    second = read_capability_manifest(
        second_payload,
        schema_version=CAPABILITY_SCHEMA_V3,
    )

    assert first.root() != second.root()


def test_protocol_facade_exports_the_canonical_scoped_manifest_objects() -> None:
    assert protocol.ScopedCapabilityManifestV2 is ScopedCapabilityManifestV2
    assert protocol.ScopedProtocolManifestV2 is ScopedProtocolManifestV2
    assert protocol.ScopedAuthorityPolicyV2 is ScopedAuthorityPolicyV2
    assert protocol.BaselineOutputPolicyV2 is BaselineOutputPolicyV2
    assert protocol.BaselineOutputActionPolicyV2 is BaselineOutputActionPolicyV2


@pytest.mark.parametrize(
    "field",
    [
        "policy_version",
        "profile",
        "wire_version",
        "canonical_version",
        "ledger_version",
        "state_store_version",
        "trace_batch_version",
        "read_set_version",
    ],
)
def test_each_scoped_authority_selector_mutation_fails_with_stable_code_and_path(
    field: str,
) -> None:
    payload = _payload()
    policy = payload["protocol"]["authority_policy"]  # type: ignore[index]
    assert isinstance(policy, dict)
    policy[field] = "pheroos-unsupported-version"

    with pytest.raises(ProtocolSchemaVersionError) as exc:
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)

    assert exc.value.code == "authority_profile_unsupported"
    assert exc.value.path == f"$.protocol.authority_policy.{field}"


def test_schema_semantic_cross_products_fail_closed_without_shape_inference() -> None:
    scoped = _payload()
    legacy = json.loads(
        (ROOT / "examples/toy-protocol/capability.json").read_text(encoding="utf-8")
    )

    with pytest.raises(ProtocolSchemaVersionError) as legacy_reader:
        read_capability_manifest(scoped, schema_version=CAPABILITY_SCHEMA_V2)
    assert legacy_reader.value.code == "capability_schema_document_invalid"

    with pytest.raises(ProtocolSchemaVersionError) as scoped_reader:
        read_capability_manifest(legacy, schema_version=CAPABILITY_SCHEMA_V3)
    assert scoped_reader.value.code == "authority_profile_unsupported"
    assert scoped_reader.value.path == "$.protocol.protocol_version"


def test_v2_output_policy_is_closed_and_has_no_legacy_boolean_gates() -> None:
    schema = protocol.protocol_schema_v3()
    output = schema["properties"]["output_policy"]

    assert output["additionalProperties"] is False
    assert set(output["properties"]) == {
        "policy_version",
        "decision_mode",
        "actions",
    }
    assert all("requires_" not in name for name in output["properties"])
    assert schema["properties"]["authority_policy"]["additionalProperties"] is False

    payload = _payload()
    payload["protocol"]["output_policy"]["requires_publication_permission"] = True  # type: ignore[index]
    with pytest.raises(ProtocolSchemaVersionError) as exc:
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)
    assert exc.value.code == "capability_schema_document_invalid"


def test_scoped_trace_policy_requires_the_complete_baseline_authority_lineage() -> None:
    required = {
        "baseline_manifest_activated",
        "baseline_evidence_qualified",
        "baseline_stop_resolved",
        "baseline_decision_evaluated",
        "baseline_action_permission_issued",
        "baseline_output_committed",
    }
    trace_events = protocol.protocol_schema_v3()["properties"]["trace_policy"][
        "properties"
    ]["required_events"]
    assert {
        condition["contains"]["const"] for condition in trace_events["allOf"]
    } == required
    assert all(condition["minContains"] == 1 for condition in trace_events["allOf"])

    for event in sorted(required):
        payload = _payload()
        events = payload["protocol"]["trace_policy"]["required_events"]  # type: ignore[index]
        assert isinstance(events, list)
        events.remove(event)
        protocol_payload = payload["protocol"]
        assert isinstance(protocol_payload, dict)
        assert list(
            Draft202012Validator(protocol.protocol_schema_v3()).iter_errors(
                protocol_payload
            )
        )
        with pytest.raises(ProtocolSchemaVersionError) as exc:
            read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)
        assert exc.value.code == "capability_schema_document_invalid"
        assert event in str(exc.value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda output: output["actions"].append(deepcopy(output["actions"][0])),
        lambda output: output["actions"][0].update({"x-critical": True}),
        lambda output: output["actions"][0].update({"effect": "deliver"}),
        lambda output: output["actions"][0].update(
            {"allowed_outcomes": ["safe_fallback", "evidence_commit"]}
        ),
    ],
)
def test_output_action_policy_rejects_duplicate_extension_effect_and_order(
    mutation: object,
) -> None:
    payload = _payload()
    output = payload["protocol"]["output_policy"]  # type: ignore[index]
    assert isinstance(output, dict)
    mutation(output)  # type: ignore[operator]

    with pytest.raises(ProtocolSchemaVersionError):
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)


def test_action_policy_constructor_requires_utf8_order_and_exact_effect() -> None:
    with pytest.raises(ScopedManifestV2Error):
        BaselineOutputActionPolicyV2(
            action_ref="action:publish",
            effect="deliver",
            target="decision:review",
            allowed_outcomes=("evidence_commit",),
        )
    with pytest.raises(ScopedManifestV2Error):
        BaselineOutputActionPolicyV2(
            action_ref="action:publish",
            effect="publish",
            target="decision:review",
            allowed_outcomes=("safe_fallback", "evidence_commit"),
        )

    with pytest.raises(ScopedManifestV2Error):
        BaselineOutputActionPolicyV2(
            action_ref="action:publish",
            effect="publish",
            target="decision:review",
            allowed_outcomes=("blocked",),
        )


def test_baseline_action_cannot_select_a_target_without_its_safe_fallback() -> None:
    payload = _payload()
    protocol_payload = payload["protocol"]
    assert isinstance(protocol_payload, dict)
    targets = protocol_payload["targets"]
    output = protocol_payload["output_policy"]
    assert isinstance(targets, list)
    assert isinstance(output, dict)
    actions = output["actions"]
    assert isinstance(actions, list)
    targets.append(
        {
            "id": "decision:secondary",
            "description": "A target without a declared safe fallback.",
        }
    )
    actions[0]["target"] = "decision:secondary"

    with pytest.raises(ProtocolSchemaVersionError) as exc:
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)

    assert exc.value.code == "capability_authority_document_invalid"
    assert "quorum fallback target" in str(exc.value)


def test_scoped_manifest_rejects_noncanonical_text_and_boolean_integer() -> None:
    whitespace = _payload()
    whitespace["protocol"]["id"] = " scoped.output.review"  # type: ignore[index]
    with pytest.raises(ProtocolSchemaVersionError):
        read_capability_manifest(whitespace, schema_version=CAPABILITY_SCHEMA_V3)

    boolean = _payload()
    boolean["protocol"]["quorum_policy"]["commit_threshold"] = True  # type: ignore[index]
    with pytest.raises(ProtocolSchemaVersionError) as exc:
        read_capability_manifest(boolean, schema_version=CAPABILITY_SCHEMA_V3)
    assert exc.value.code == "capability_schema_document_invalid"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda protocol: protocol["signals"][0].update(
                {"target": "decision:missing"}
            ),
            "signal target",
        ),
        (
            lambda protocol: protocol.update(
                {
                    "recovery_protocols": [
                        {
                            "id": "recovery:review",
                            "trigger_targets": ["decision:missing"],
                        }
                    ]
                }
            ),
            "recovery trigger target",
        ),
        (
            lambda protocol: protocol.update(
                {
                    "recovery_protocols": [
                        {
                            "id": "recovery:review",
                            "trigger_targets": ["decision:review"],
                            "failure_candidate": "candidate:missing",
                        }
                    ]
                }
            ),
            "recovery failure candidate",
        ),
        (
            lambda protocol: protocol.update(
                {
                    "recovery_protocols": [
                        {
                            "id": "recovery:duplicate",
                            "trigger_targets": ["decision:review"],
                        },
                        {
                            "id": "recovery:duplicate",
                            "trigger_targets": ["decision:review"],
                        },
                    ]
                }
            ),
            "recovery protocol ids",
        ),
    ],
)
def test_scoped_reader_fails_closed_for_every_cross_reference_domain(
    mutate: object,
    message: str,
) -> None:
    payload = _payload()
    protocol_payload = payload["protocol"]
    assert isinstance(protocol_payload, dict)
    mutate(protocol_payload)  # type: ignore[operator]

    with pytest.raises(ProtocolSchemaVersionError) as exc:
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)

    assert exc.value.code == "capability_authority_document_invalid"
    assert message in str(exc.value)


def test_scoped_v2_validates_complete_collective_commit_and_lineage_semantics() -> None:
    payload = _full_policy_payload()
    value = read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)
    assert type(value) is ScopedCapabilityManifestV2

    mutations = (
        (
            lambda protocol: protocol["collective_decision_policy"].update(
                {"fallback_candidate": "candidate:missing"}
            ),
            "collective fallback",
        ),
        (
            lambda protocol: protocol["collective_commit_policy"].update(
                {"target": "decision:missing"}
            ),
            "commit target",
        ),
        (
            lambda protocol: protocol["collective_commit_policy"][
                "terminal_outcome"
            ].update({"safe_fallback_candidate": "candidate:missing"}),
            "commit fallback",
        ),
        (
            lambda protocol: protocol["evidence_policy"].update(
                {"require_provenance": False}
            ),
            "provenance",
        ),
    )
    for mutate, message in mutations:
        invalid = deepcopy(payload)
        protocol_payload = invalid["protocol"]
        assert isinstance(protocol_payload, dict)
        mutate(protocol_payload)
        with pytest.raises(ProtocolSchemaVersionError) as exc:
            read_capability_manifest(invalid, schema_version=CAPABILITY_SCHEMA_V3)
        assert exc.value.code == "capability_authority_document_invalid"
        assert message in str(exc.value)


def test_direct_authority_and_output_policy_constructors_fail_closed() -> None:
    capability = read_capability_manifest(
        _payload(), schema_version=CAPABILITY_SCHEMA_V3
    )
    authority = capability.protocol.authority_policy
    output = capability.protocol.output_policy
    action = output.actions[0]

    for field_name in (
        "policy_version",
        "wire_version",
        "canonical_version",
        "ledger_version",
        "state_store_version",
        "trace_batch_version",
        "read_set_version",
    ):
        with pytest.raises(ScopedManifestV2Error, match=field_name):
            replace(authority, **{field_name: "unsupported"})
    with pytest.raises(ScopedManifestV2Error, match="profile"):
        replace(authority, profile="unsupported")

    with pytest.raises(ScopedManifestV2Error, match="must be an array"):
        BaselineOutputActionPolicyV2.from_dict(
            {**action.to_dict(), "allowed_outcomes": action.allowed_outcomes}
        )
    with pytest.raises(ScopedManifestV2Error, match="must be an array"):
        BaselineOutputPolicyV2.from_dict(
            {**output.to_dict(), "actions": output.actions}
        )

    invalid_policies = (
        {"policy_version": "unsupported"},
        {"decision_mode": "unsupported"},
        {"actions": []},
        {"actions": (action,) * 129},
        {"actions": (object(),)},
        {"actions": (action, action)},
        {
            "actions": (
                replace(action, action_ref="action:z"),
                replace(action, action_ref="action:a"),
            )
        },
    )
    for mutation in invalid_policies:
        with pytest.raises(ScopedManifestV2Error):
            replace(output, **mutation)


def test_direct_scoped_manifest_exact_types_and_declarations_fail_closed() -> None:
    capability = read_capability_manifest(
        _payload(), schema_version=CAPABILITY_SCHEMA_V3
    )
    manifest = capability.protocol

    invalid_fields = (
        {"protocol_version": "unsupported"},
        {"quorum_policy": object()},
        {"authority_policy": object()},
        {"output_policy": object()},
        {"trace_policy": object()},
        {"evidence_policy": object()},
        {"targets": ()},
        {"candidates": ()},
        {"targets": []},
    )
    for mutation in invalid_fields:
        with pytest.raises(ScopedManifestV2Error):
            replace(manifest, **mutation)

    quorum = manifest.quorum_policy
    for mutation in (
        {"commit_threshold": True},
        {"target": "decision:missing"},
        {"fallback_candidate": "candidate:missing"},
    ):
        with pytest.raises(ScopedManifestV2Error):
            replace(manifest, quorum_policy=replace(quorum, **mutation))

    unsafe_candidate = replace(manifest.candidates[0], safe_fallback=1)
    with pytest.raises(ScopedManifestV2Error, match="exact boolean"):
        replace(manifest, candidates=(unsafe_candidate,))
    wrong_target = replace(manifest.candidates[0], target="decision:missing")
    with pytest.raises(ScopedManifestV2Error, match="candidate target"):
        replace(manifest, candidates=(wrong_target,))

    with pytest.raises(ScopedManifestV2Error, match="exact v2 manifest type"):
        replace(capability, protocol=object())
    with pytest.raises(ScopedManifestV2Error, match="immutable tuple"):
        replace(capability, permissions=[])


def test_direct_recovery_collective_and_safety_cross_bindings_fail_closed() -> None:
    payload = deepcopy(_payload()["protocol"])
    assert isinstance(payload, dict)
    payload["targets"].append(
        {"id": "decision:secondary", "description": "Secondary target."}
    )
    payload["candidates"].append(
        {
            "id": "candidate:secondary",
            "target": "decision:secondary",
            "description": "Secondary fallback.",
            "safe_fallback": True,
        }
    )
    payload["recovery_protocols"] = [
        {
            "id": "recovery:cross-target",
            "trigger_targets": ["decision:review"],
            "failure_candidate": "candidate:secondary",
        }
    ]
    with pytest.raises(ScopedManifestV2Error, match="target a trigger target"):
        ScopedProtocolManifestV2.from_dict(payload)

    valid_recovery = deepcopy(_payload()["protocol"])
    assert isinstance(valid_recovery, dict)
    valid_recovery["recovery_protocols"] = [
        {
            "id": "recovery:no-failure-candidate",
            "trigger_targets": ["decision:review"],
        }
    ]
    assert ScopedProtocolManifestV2.from_dict(valid_recovery).recovery_protocols

    manifest = read_protocol_manifest(
        _payload()["protocol"], schema_version=PROTOCOL_SCHEMA_V3
    )
    with pytest.raises(ScopedManifestV2Error, match="collective decision policy"):
        replace(manifest, collective_decision_policy=manifest.quorum_policy)
    with pytest.raises(ScopedManifestV2Error, match="collective commit policy"):
        replace(manifest, collective_commit_policy=manifest.quorum_policy)

    unsafe_evidence = replace(manifest.evidence_policy, allow_agent_fact_creation=True)
    with pytest.raises(ScopedManifestV2Error, match="agent fact creation"):
        replace(manifest, evidence_policy=unsafe_evidence)
    incomplete_trace = replace(
        manifest.trace_policy,
        required_events=tuple(
            event
            for event in manifest.trace_policy.required_events
            if event != "baseline_output_committed"
        ),
    )
    with pytest.raises(ScopedManifestV2Error, match="missing required events"):
        replace(manifest, trace_policy=incomplete_trace)

    missing_target_action = replace(
        manifest.output_policy.actions[0], target="decision:missing"
    )
    with pytest.raises(ScopedManifestV2Error, match="target must be declared"):
        replace(
            manifest,
            output_policy=replace(
                manifest.output_policy, actions=(missing_target_action,)
            ),
        )

    full = read_capability_manifest(
        _full_policy_payload(), schema_version=CAPABILITY_SCHEMA_V3
    ).protocol
    assert "collective_decision_policy" in full.to_dict()
    assert "collective_commit_policy" in full.to_dict()
    commit_without_collective = replace(full, collective_decision_policy=None)
    assert "collective_decision_policy" not in commit_without_collective.to_dict()
    assert "collective_commit_policy" in commit_without_collective.to_dict()


def test_scoped_manifest_malformed_container_and_text_edges_are_rejected() -> None:
    with pytest.raises(ScopedManifestV2Error, match="exact JSON object"):
        ScopedCapabilityManifestV2.from_dict(UserDict())
    with pytest.raises(ScopedManifestV2Error, match="fields are invalid"):
        ScopedAuthorityPolicyV2.from_dict({})
    with pytest.raises(ScopedManifestV2Error, match="fields are invalid"):
        ScopedCapabilityManifestV2.from_dict({})

    payload = deepcopy(_payload()["protocol"])
    assert isinstance(payload, dict)
    payload["targets"] = ()
    with pytest.raises(ScopedManifestV2Error, match="targets must be an array"):
        ScopedProtocolManifestV2.from_dict(payload)

    payload = deepcopy(_payload())
    payload["permissions"] = [1]
    with pytest.raises(ScopedManifestV2Error, match="must contain strings"):
        ScopedCapabilityManifestV2.from_dict(payload)

    payload = deepcopy(_payload()["protocol"])
    assert isinstance(payload, dict)
    payload["trace_policy"] = []
    with pytest.raises(ScopedManifestV2Error, match="must be an object"):
        ScopedProtocolManifestV2.from_dict(payload)

    payload = deepcopy(_payload()["protocol"])
    assert isinstance(payload, dict)
    payload["quorum_policy"]["commit_threshold"] = 0
    with pytest.raises(ScopedManifestV2Error, match="positive exact integer"):
        ScopedProtocolManifestV2.from_dict(payload)

    capability = read_capability_manifest(
        _payload(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    assert type(capability) is ScopedCapabilityManifestV2
    for text in ("", " surrounding ", "\x00", "\ud800", "e\u0301"):
        with pytest.raises(ScopedManifestV2Error):
            replace(capability, id=text)

    payload = _payload()
    del payload["id"]
    with pytest.raises(ProtocolSchemaVersionError, match="missing required field"):
        read_capability_manifest(payload, schema_version=CAPABILITY_SCHEMA_V3)


def test_scoped_manifest_canonical_tree_and_portable_boundaries() -> None:
    capability = read_capability_manifest(
        _payload(), schema_version=CAPABILITY_SCHEMA_V3
    )

    with pytest.raises(ScopedManifestV2Error, match="exact list or tuple"):
        replace(capability, extensions={"x-values": UserList(["a"])})
    with pytest.raises(ScopedManifestV2Error, match="exact dict or mappingproxy"):
        replace(capability, extensions=[])
    with pytest.raises(ScopedManifestV2Error, match="exact dict or mappingproxy"):
        replace(capability.protocol, extensions=())
    with pytest.raises(ScopedManifestV2Error, match="canonical JSON"):
        replace(capability, extensions={"x-value": object()})
    with pytest.raises(ScopedManifestV2Error, match="UTF-8"):
        replace(capability, extensions={"x-value": "\ud800"})

    enum_extension = replace(capability, extensions={"x-mode": _TextMode.READY})
    assert enum_extension.extensions["x-mode"] == "ready"
    assert enum_extension.to_dict()["extensions"] == {"x-mode": "ready"}
    sequence_extension = replace(capability, extensions={"x-values": ["a", "b"]})
    assert sequence_extension.extensions["x-values"] == ("a", "b")
    assert sequence_extension.to_dict()["extensions"] == {"x-values": ["a", "b"]}

    with pytest.raises(ScopedManifestV2Error, match="must not be empty"):
        replace(capability.protocol.output_policy.actions[0], allowed_outcomes=())
