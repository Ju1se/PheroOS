from __future__ import annotations

from typing import Any


def trace_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/trace.schema.json",
        "type": "object",
        "required": ["event_type", "protocol_id", "target", "reason"],
        "additionalProperties": False,
        "properties": {
            "event_type": {
                "type": "string",
                "description": "Built-in trace event type or namespaced extension event using x-* or ext.*.",
            },
            "protocol_id": {"type": "string"},
            "target": {"type": "string"},
            "reason": {"type": "string"},
            "lineage": {"type": "object"},
        },
    }
