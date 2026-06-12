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
            "collective_decision_policy": {
                "type": "object",
                "properties": {
                    "mode": {"enum": ["quorum", "bee_swarm", "ant_colony", "hybrid"]},
                    "min_independent_scouts": {"type": "integer", "minimum": 1},
                    "quorum_threshold": {"type": "integer", "minimum": 1},
                    "recruitment_enabled": {"type": "boolean"},
                    "inhibition_enabled": {"type": "boolean"},
                    "pheromone_enabled": {"type": "boolean"},
                    "pheromone_evaporation_rate": {"type": "number", "minimum": 0, "maximum": 1},
                    "fallback_candidate": {"type": "string"},
                },
            },
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
