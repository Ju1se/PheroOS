from __future__ import annotations

from typing import Any


def protocol_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/protocol.schema.json",
        "type": "object",
        "required": ["protocol_version", "id", "targets", "candidates", "quorum_policy", "output_policy", "trace_policy"],
        "properties": {
            "protocol_version": {"type": "string"},
            "id": {"type": "string"},
            "targets": {"type": "array", "items": {"type": "object", "required": ["id"]}},
            "candidates": {"type": "array", "items": {"type": "object", "required": ["id", "target"]}},
            "quorum_policy": {"type": "object", "required": ["target", "fallback_candidate"]},
            "output_policy": {"type": "object"},
            "trace_policy": {"type": "object"},
        },
    }


def capability_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/capability.schema.json",
        "type": "object",
        "required": ["id", "name", "version", "protocol"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "version": {"type": "string"},
            "protocol": protocol_schema(),
        },
    }
