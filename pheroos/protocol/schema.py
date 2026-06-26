from __future__ import annotations

from typing import Any


EXTENSION_KEY_PATTERN = r"^(x-|ext\.).+"


def object_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required or [],
        "properties": properties,
        "patternProperties": {EXTENSION_KEY_PATTERN: {}},
        "additionalProperties": False,
    }


def extensions_schema() -> dict[str, Any]:
    return {"type": "object"}


def protocol_schema() -> dict[str, Any]:
    return object_schema(
        {
            "protocol_version": {"type": "string"},
            "id": {"type": "string"},
            "targets": {
                "type": "array",
                "items": object_schema(
                    {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "extensions": extensions_schema(),
                    },
                    required=["id"],
                ),
            },
            "candidates": {
                "type": "array",
                "items": object_schema(
                    {
                        "id": {"type": "string"},
                        "target": {"type": "string"},
                        "safe_fallback": {"type": "boolean"},
                        "label": {"type": "string"},
                        "extensions": extensions_schema(),
                    },
                    required=["id", "target"],
                ),
            },
            "signals": {
                "type": "array",
                "items": object_schema(
                    {
                        "type": {"type": "string"},
                        "target": {"type": "string"},
                        "authority_required": {"type": "string"},
                        "extensions": extensions_schema(),
                    },
                    required=["type", "target"],
                ),
            },
            "quorum_policy": object_schema(
                {
                    "target": {"type": "string"},
                    "fallback_candidate": {"type": "string"},
                    "commit_threshold": {"type": "integer", "minimum": 1},
                    "extensions": extensions_schema(),
                },
                required=["target", "fallback_candidate"],
            ),
            "collective_decision_policy": object_schema(
                {
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
                }
            ),
            "recovery_protocols": {
                "type": "array",
                "items": object_schema(
                    {
                        "id": {"type": "string"},
                        "trigger_targets": {"type": "array", "items": {"type": "string"}},
                        "allowed_roles": {"type": "array", "items": {"type": "string"}},
                        "allowed_tags": {"type": "array", "items": {"type": "string"}},
                        "required_tools": {"type": "array", "items": {"type": "string"}},
                        "failure_candidate": {"type": "string"},
                        "extensions": extensions_schema(),
                    },
                    required=["id", "trigger_targets"],
                ),
            },
            "evidence_policy": object_schema(
                {
                    "require_provenance": {"type": "boolean"},
                    "allow_agent_fact_creation": {"type": "boolean"},
                    "extensions": extensions_schema(),
                }
            ),
            "output_policy": object_schema(
                {
                    "writer_may_create_facts": {"type": "boolean"},
                    "requires_committed_candidate": {"type": "boolean"},
                    "requires_evidence_contract": {"type": "boolean"},
                    "requires_stop_resolution": {"type": "boolean"},
                    "requires_publication_permission": {"type": "boolean"},
                    "extensions": extensions_schema(),
                }
            ),
            "trace_policy": object_schema(
                {
                    "required_events": {"type": "array", "items": {"type": "string"}},
                    "extensions": extensions_schema(),
                }
            ),
            "extensions": extensions_schema(),
        },
        required=["protocol_version", "id", "targets", "candidates", "quorum_policy", "output_policy", "trace_policy"],
    ) | {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/protocol.schema.json",
    }


def capability_schema() -> dict[str, Any]:
    return object_schema(
        {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "version": {"type": "string"},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "required_connections": {"type": "array", "items": {"type": "string"}},
            "drivers": {"type": "array", "items": driver_spec_schema()},
            "protocol": protocol_schema(),
            "extensions": extensions_schema(),
        },
        required=["id", "name", "version", "protocol"],
    ) | {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/capability.schema.json",
    }


def driver_spec_schema() -> dict[str, Any]:
    return object_schema(
        {
            "id": {"type": "string"},
            "kind": {"type": "string"},
            "version": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "config_ref": {"type": "string"},
            "extensions": extensions_schema(),
        },
        required=["id", "kind", "version"],
    )
