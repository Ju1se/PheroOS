from __future__ import annotations

from typing import Any


EXTENSION_KEY_PATTERN = r"^(x-|ext\.).+"
SUPPORTED_PHEROMONE_KINDS = ("positive", "negative", "cautionary", "alarm", "novelty", "stale")
SUPPORTED_LAYER_IDS = ("reactive", "learned", "evolutionary", "metacognitive")
ADJUSTABLE_LAYER_IDS = ("learned", "evolutionary", "metacognitive")


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


def layer_number_map_schema(*, maximum: float) -> dict[str, Any]:
    return {
        "type": "object",
        "patternProperties": {
            exact_value_pattern(SUPPORTED_LAYER_IDS): {
                "type": "number",
                "minimum": 0,
                "maximum": maximum,
            }
        },
        "additionalProperties": False,
    }


def numeric_bounds_schema(*, maximum: float) -> dict[str, Any]:
    number_schema = {"type": "number", "minimum": 0, "maximum": maximum}
    return {
        "oneOf": [
            {
                "type": "array",
                "items": number_schema,
                "minItems": 2,
                "maxItems": 2,
            },
            object_schema(
                {
                    "min": number_schema,
                    "max": number_schema,
                },
                required=["min", "max"],
            ),
        ]
    }


def layer_bounds_map_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "patternProperties": {
            exact_value_pattern(SUPPORTED_LAYER_IDS): numeric_bounds_schema(maximum=10)
        },
        "additionalProperties": False,
    }


def pheromone_kind_profile_schema() -> dict[str, Any]:
    return object_schema(
        {
            "weight": {"type": "number", "minimum": 0},
            "evaporation_rate": {"type": "number", "minimum": 0, "maximum": 1},
            "ttl_steps": {"type": "integer", "minimum": 0},
            "response_model": {"enum": ["linear", "saturating", "threshold", "competitive"]},
            "priority": {"type": "integer", "minimum": 0},
            "can_suppress_positive": {"type": "boolean"},
            "scored_subject_types": {"type": "array", "items": {"type": "string"}},
            "extensions": extensions_schema(),
        }
    )


def pheromone_kind_profiles_schema() -> dict[str, Any]:
    profile_schema = pheromone_kind_profile_schema()
    return {
        "type": "object",
        "patternProperties": {
            exact_value_pattern(SUPPORTED_PHEROMONE_KINDS): profile_schema,
            EXTENSION_KEY_PATTERN: profile_schema,
        },
        "additionalProperties": False,
    }


def response_model_adjustment_bound_schema() -> dict[str, Any]:
    return object_schema(
        {
            "allowed_values": {
                "type": "array",
                "items": {"enum": ["linear", "saturating", "threshold", "competitive"]},
                "minItems": 1,
            }
        },
        required=["allowed_values"],
    )


def policy_adjustment_bounds_schema() -> dict[str, Any]:
    unit_range_fields = (
        "pheromone_evaporation_rate",
        "pheromone_exploration_floor",
        "layer_emergency_override_threshold",
    )
    bounded_weight_fields = (
        "pheromone_positive_weight",
        "pheromone_negative_weight",
        "pheromone_cautionary_weight",
        "pheromone_alarm_weight",
        "pheromone_novelty_weight",
        "pheromone_cautionary_override_threshold",
        *(f"layer_{layer_id}_weight" for layer_id in ADJUSTABLE_LAYER_IDS),
    )
    return {
        "type": "object",
        "patternProperties": {
            exact_value_pattern(unit_range_fields): numeric_bounds_schema(maximum=1),
            exact_value_pattern(bounded_weight_fields): numeric_bounds_schema(maximum=10),
            r"^pheromone_response_model$": response_model_adjustment_bound_schema(),
        },
        "additionalProperties": False,
    }


def exact_value_pattern(values: tuple[str, ...]) -> str:
    return rf"^({'|'.join(values)})$"


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
                    "pheromone_min_strength": {"type": "number", "minimum": 0},
                    "pheromone_max_strength": {"type": "number", "minimum": 0},
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
                    "pheromone_scored_subject_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "pheromone_kind_profiles": pheromone_kind_profiles_schema(),
                    "pheromone_response_model": {"enum": ["linear", "saturating", "threshold", "competitive"]},
                    "pheromone_activation_threshold": {"type": "number", "minimum": 0},
                    "pheromone_saturation_threshold": {"type": "number", "minimum": 0},
                    "pheromone_competition_mode": {"enum": ["none", "normalize"]},
                    "pheromone_exploration_floor": {"type": "number", "minimum": 0, "maximum": 1},
                    "pheromone_diffusion_enabled": {"type": "boolean"},
                    "pheromone_diffusion_max_hops": {"type": "integer", "minimum": 0},
                    "pheromone_diffusion_attenuation": {"type": "number", "minimum": 0, "maximum": 1},
                    "pheromone_feedback_enabled": {"type": "boolean"},
                    "exploration_enabled": {"type": "boolean"},
                    "exploration_floor": {"type": "number", "minimum": 0, "maximum": 1},
                    "novelty_decay_rate": {"type": "number", "minimum": 0, "maximum": 1},
                    "stale_route_reopen_threshold": {"type": "number", "minimum": 0},
                    "layer_coordination_enabled": {"type": "boolean"},
                    "layer_weight_bounds": layer_bounds_map_schema(),
                    "layer_default_weights": layer_number_map_schema(maximum=10),
                    "layer_confidence_thresholds": layer_number_map_schema(maximum=1),
                    "layer_conflict_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                    "layer_emergency_override_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                    "layer_min_provenance": {"type": "integer", "minimum": 1},
                    "layer_fallback_on_unresolved_conflict": {"type": "boolean"},
                    "policy_adjustment_bounds": policy_adjustment_bounds_schema(),
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
                    "requires_committed_candidate": {"type": "boolean", "const": True},
                    "requires_evidence_contract": {"type": "boolean", "const": True},
                    "requires_stop_resolution": {"type": "boolean", "const": True},
                    "requires_publication_permission": {"type": "boolean", "const": True},
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
