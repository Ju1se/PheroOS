from __future__ import annotations

from typing import Any


def extensions_schema() -> dict[str, Any]:
    return {"type": "object"}


def protocol_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/protocol.schema.json",
        "type": "object",
        "required": ["protocol_version", "id", "targets", "candidates", "quorum_policy", "output_policy", "trace_policy"],
        "properties": {
            "protocol_version": {"type": "string"},
            "id": {"type": "string"},
            "targets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "extensions": extensions_schema(),
                    },
                },
            },
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "target"],
                    "properties": {
                        "id": {"type": "string"},
                        "target": {"type": "string"},
                        "safe_fallback": {"type": "boolean"},
                        "label": {"type": "string"},
                        "extensions": extensions_schema(),
                    },
                },
            },
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["type", "target"],
                    "properties": {
                        "type": {"type": "string"},
                        "target": {"type": "string"},
                        "authority_required": {"type": "string"},
                        "extensions": extensions_schema(),
                    },
                },
            },
            "quorum_policy": {
                "type": "object",
                "required": ["target", "fallback_candidate"],
                "properties": {
                    "target": {"type": "string"},
                    "fallback_candidate": {"type": "string"},
                    "commit_threshold": {"type": "integer", "minimum": 1},
                    "extensions": extensions_schema(),
                },
            },
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
                    "pheromone_decay_model": {"enum": ["linear", "exponential", "step"]},
                    "pheromone_min_strength": {"type": "number"},
                    "pheromone_max_strength": {"type": "number"},
                    "pheromone_positive_weight": {"type": "number", "minimum": 0},
                    "pheromone_negative_weight": {"type": "number", "minimum": 0},
                    "pheromone_cautionary_weight": {"type": "number", "minimum": 0},
                    "pheromone_cautionary_override_threshold": {"type": "number", "minimum": 0},
                    "pheromone_novelty_weight": {"type": "number", "minimum": 0},
                    "pheromone_per_source_cap": {"type": "number", "minimum": 0},
                    "pheromone_per_round_deposit_cap": {"type": "number", "minimum": 0},
                    "pheromone_min_source_diversity": {"type": "integer", "minimum": 1},
                    "pheromone_require_provenance": {"type": "boolean"},
                    "pheromone_require_trace": {"type": "boolean"},
                    "fallback_candidate": {"type": "string"},
                    "extensions": extensions_schema(),
                },
            },
            "output_policy": {"type": "object", "properties": {"extensions": extensions_schema()}},
            "trace_policy": {
                "type": "object",
                "properties": {
                    "required_events": {"type": "array", "items": {"type": "string"}},
                    "extensions": extensions_schema(),
                },
            },
            "extensions": extensions_schema(),
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
            "permissions": {"type": "array", "items": {"type": "string"}},
            "required_connections": {"type": "array", "items": {"type": "string"}},
            "drivers": {"type": "array", "items": driver_spec_schema()},
            "protocol": protocol_schema(),
            "extensions": extensions_schema(),
        },
    }


def driver_spec_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["id", "kind", "version"],
        "properties": {
            "id": {"type": "string"},
            "kind": {"type": "string"},
            "version": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "config_ref": {"type": "string"},
            "extensions": extensions_schema(),
        },
    }
