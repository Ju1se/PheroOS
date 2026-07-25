"""Schema-document v3 for explicit scoped-authority v2 manifests."""

from __future__ import annotations

from typing import Any

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
    REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
)
from pheroos.protocol.schema import capability_schema, protocol_schema


PROTOCOL_SCHEMA_V3_ID = "https://pheroos.dev/schemas/protocol-v3.schema.json"
CAPABILITY_SCHEMA_V3_ID = "https://pheroos.dev/schemas/capability-v3.schema.json"
PROTOCOL_SCHEMA_V3 = "pheroos-protocol-schema-v3"
CAPABILITY_SCHEMA_V3 = "pheroos-capability-schema-v3"


def _closed_object(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(required),
        "properties": properties,
        "additionalProperties": False,
    }


def scoped_authority_policy_schema_v2() -> dict[str, Any]:
    """Return the exact, extension-free scoped-authority selector object."""

    return _closed_object(
        {
            "policy_version": {"const": AUTHORITY_POLICY_VERSION_V2},
            "profile": {
                "enum": [
                    AUTHORITY_LOCAL_PROFILE_V2,
                    AUTHORITY_AUTHENTICATED_PROFILE_V2,
                ]
            },
            "wire_version": {"const": AUTHORITY_WIRE_VERSION_V2},
            "canonical_version": {"const": AUTHORITY_CANONICAL_VERSION_V2},
            "ledger_version": {"const": AUTHORITY_LEDGER_VERSION_V2},
            "state_store_version": {"const": GOVERNANCE_STATE_STORE_VERSION_V2},
            "trace_batch_version": {"const": GOVERNANCE_TRACE_BATCH_VERSION_V2},
            "read_set_version": {"const": GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2},
        },
        required=(
            "policy_version",
            "profile",
            "wire_version",
            "canonical_version",
            "ledger_version",
            "state_store_version",
            "trace_batch_version",
            "read_set_version",
        ),
    )


def baseline_output_policy_schema_v2() -> dict[str, Any]:
    """Return the exact v2 output declaration with no caller Boolean gates."""

    action = _closed_object(
        {
            "action_ref": {"type": "string", "minLength": 1},
            "effect": {"enum": ["publish", "execute"]},
            "target": {"type": "string", "minLength": 1},
            "allowed_outcomes": {
                "type": "array",
                "items": {"enum": ["evidence_commit", "safe_fallback"]},
                "minItems": 1,
                "uniqueItems": True,
            },
        },
        required=("action_ref", "effect", "target", "allowed_outcomes"),
    )
    return _closed_object(
        {
            "policy_version": {"const": BASELINE_OUTPUT_POLICY_VERSION_V2},
            "decision_mode": {"enum": ["quorum", "direct_governance"]},
            "actions": {
                "type": "array",
                "items": action,
                "maxItems": 128,
            },
        },
        required=("policy_version", "decision_mode", "actions"),
    )


def protocol_schema_v3() -> dict[str, Any]:
    """Return the new schema document for ``pheroos.protocol.v2`` data."""

    schema = protocol_schema()
    schema["$id"] = PROTOCOL_SCHEMA_V3_ID
    properties = schema["properties"]
    properties["protocol_version"] = {"const": PROTOCOL_VERSION_V2}
    properties["authority_policy"] = scoped_authority_policy_schema_v2()
    properties["output_policy"] = baseline_output_policy_schema_v2()
    trace_events = properties["trace_policy"]["properties"]["required_events"]
    trace_events["uniqueItems"] = True
    trace_events["minItems"] = len(REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2)
    trace_events["allOf"] = [
        {"contains": {"const": event_type}, "minContains": 1}
        for event_type in sorted(REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2)
    ]
    required = list(schema["required"])
    required.insert(required.index("output_policy"), "authority_policy")
    schema["required"] = required
    _mark_exact_integers(schema)
    return schema


def capability_schema_v3() -> dict[str, Any]:
    """Return the Capability document that embeds Protocol schema v3."""

    schema = capability_schema()
    schema["$id"] = CAPABILITY_SCHEMA_V3_ID
    schema["properties"]["protocol"] = protocol_schema_v3()
    _mark_exact_integers(schema)
    return schema


def _mark_exact_integers(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "integer":
            schema["x-pheroos-exact-integer"] = True
        for value in schema.values():
            _mark_exact_integers(value)
    elif isinstance(schema, list):
        for value in schema:
            _mark_exact_integers(value)


__all__ = [
    "CAPABILITY_SCHEMA_V3",
    "CAPABILITY_SCHEMA_V3_ID",
    "PROTOCOL_SCHEMA_V3",
    "PROTOCOL_SCHEMA_V3_ID",
    "baseline_output_policy_schema_v2",
    "capability_schema_v3",
    "protocol_schema_v3",
    "scoped_authority_policy_schema_v2",
]
