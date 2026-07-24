from __future__ import annotations

from typing import Any

from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    MAX_AUTHORITY_INTEGER,
    REQUIRED_COMMIT_RESET_RULES,
    SUPPORTED_CERTIFICATE_MODES,
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_DEADLINE_OUTCOMES,
    SUPPORTED_RISK_BANDS,
    SUPPORTED_TERMINAL_OUTCOMES,
    WEIGHT_SCALE,
)

EXTENSION_KEY_PATTERN = r"^(x-|ext\.).+"
PROTOCOL_SCHEMA_V1_ID = "https://pheroos.dev/schemas/protocol.schema.json"
PROTOCOL_SCHEMA_V2_ID = "https://pheroos.dev/schemas/protocol-v2.schema.json"
CAPABILITY_SCHEMA_V1_ID = "https://pheroos.dev/schemas/capability.schema.json"
CAPABILITY_SCHEMA_V2_ID = "https://pheroos.dev/schemas/capability-v2.schema.json"
PROTOCOL_SCHEMA_V1 = "pheroos-protocol-schema-v1"
PROTOCOL_SCHEMA_V2 = "pheroos-protocol-schema-v2"
CAPABILITY_SCHEMA_V1 = "pheroos-capability-schema-v1"
CAPABILITY_SCHEMA_V2 = "pheroos-capability-schema-v2"
SUPPORTED_PHEROMONE_KINDS = (
    "positive",
    "negative",
    "cautionary",
    "alarm",
    "novelty",
    "stale",
)
SUPPORTED_LAYER_IDS = ("reactive", "learned", "evolutionary", "metacognitive")
ADJUSTABLE_LAYER_IDS = ("learned", "evolutionary", "metacognitive")


def object_schema(
    properties: dict[str, Any], *, required: list[str] | None = None
) -> dict[str, Any]:
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
            "response_model": {
                "enum": ["linear", "saturating", "threshold", "competitive"]
            },
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
            exact_value_pattern(bounded_weight_fields): numeric_bounds_schema(
                maximum=10
            ),
            r"^pheromone_response_model$": response_model_adjustment_bound_schema(),
        },
        "additionalProperties": False,
    }


def exact_value_pattern(values: tuple[str, ...]) -> str:
    return rf"^({'|'.join(values)})$"


def canonical_text_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "pattern": r"^\S(?:.*\S)?$",
    }


def authority_integer_schema(
    *, minimum: int = 0, maximum: int = MAX_AUTHORITY_INTEGER
) -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": minimum,
        "maximum": maximum,
        "x-pheroos-exact-integer": True,
    }


def canonical_text_set_schema(
    *,
    allowed_values: tuple[str, ...] | frozenset[str] | None = None,
    minimum_items: int = 0,
) -> dict[str, Any]:
    item_schema: dict[str, Any]
    if allowed_values is None:
        item_schema = canonical_text_schema()
    else:
        item_schema = {"enum": sorted(allowed_values)}
    return {
        "type": "array",
        "items": item_schema,
        "minItems": minimum_items,
        "uniqueItems": True,
    }


def evidence_qualification_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "numeric_scale": {
                "type": "integer",
                "const": WEIGHT_SCALE,
                "x-pheroos-exact-integer": True,
            },
            "minimum_quality_ppm": authority_integer_schema(maximum=WEIGHT_SCALE),
            "minimum_relevance_ppm": authority_integer_schema(maximum=WEIGHT_SCALE),
            "positive_group_cap": authority_integer_schema(minimum=1),
            "counter_group_cap": authority_integer_schema(minimum=1),
            "counter_weight_ppm": authority_integer_schema(minimum=1),
            "minimum_positive_evidence": authority_integer_schema(minimum=1),
            "maximum_counterevidence": authority_integer_schema(),
            "maximum_counterevidence_ratio_ppm": authority_integer_schema(
                maximum=WEIGHT_SCALE
            ),
            "domain_contribution_floor": authority_integer_schema(minimum=1),
            "minimum_source_diversity": authority_integer_schema(minimum=1),
            "required_challenge_categories": canonical_text_set_schema(minimum_items=1),
            "observation_ttl_steps": authority_integer_schema(minimum=1),
            "require_provenance": {"const": True},
            "require_trace": {"const": True},
            "extensions": extensions_schema(),
        },
        required=[
            "numeric_scale",
            "minimum_quality_ppm",
            "minimum_relevance_ppm",
            "positive_group_cap",
            "counter_group_cap",
            "counter_weight_ppm",
            "minimum_positive_evidence",
            "maximum_counterevidence",
            "maximum_counterevidence_ratio_ppm",
            "domain_contribution_floor",
            "minimum_source_diversity",
            "required_challenge_categories",
            "observation_ttl_steps",
            "require_provenance",
            "require_trace",
        ],
    )


def support_lease_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "minimum_support_clusters": authority_integer_schema(minimum=1),
            "support_ratio_ppm": authority_integer_schema(
                minimum=1, maximum=WEIGHT_SCALE
            ),
            "lease_ttl_steps": authority_integer_schema(minimum=1),
            "membership_mode": {"const": "verified_snapshot_v1"},
            "switch_mode": {"const": "revoke_then_issue_v1"},
            "equivocation_mode": {"const": "exclude_conflicts_v1"},
            "evidence_reference_required": {"const": True},
            "cluster_verification_required": {"const": True},
            "extensions": extensions_schema(),
        },
        required=[
            "minimum_support_clusters",
            "support_ratio_ppm",
            "lease_ttl_steps",
            "membership_mode",
            "switch_mode",
            "equivocation_mode",
            "evidence_reference_required",
            "cluster_verification_required",
        ],
    )


def risk_band_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "minimum_positive_evidence": authority_integer_schema(minimum=1),
            "maximum_counterevidence": authority_integer_schema(),
            "maximum_counterevidence_ratio_ppm": authority_integer_schema(
                maximum=WEIGHT_SCALE
            ),
            "minimum_support_clusters": authority_integer_schema(minimum=1),
            "minimum_support_ratio_ppm": authority_integer_schema(
                minimum=1, maximum=WEIGHT_SCALE
            ),
            "minimum_source_diversity": authority_integer_schema(minimum=1),
            "minimum_margin": authority_integer_schema(minimum=1),
            "stability_steps": authority_integer_schema(minimum=1),
            "required_challenge_categories": canonical_text_set_schema(minimum_items=1),
            "minimum_assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "publishable_outcomes": canonical_text_set_schema(
                allowed_values=SUPPORTED_TERMINAL_OUTCOMES
            ),
            "executable_outcomes": canonical_text_set_schema(
                allowed_values=SUPPORTED_TERMINAL_OUTCOMES
            ),
            "extensions": extensions_schema(),
        },
        required=[
            "minimum_positive_evidence",
            "maximum_counterevidence",
            "maximum_counterevidence_ratio_ppm",
            "minimum_support_clusters",
            "minimum_support_ratio_ppm",
            "minimum_source_diversity",
            "minimum_margin",
            "stability_steps",
            "required_challenge_categories",
            "minimum_assurance",
            "publishable_outcomes",
            "executable_outcomes",
        ],
    )


def risk_bands_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(SUPPORTED_RISK_BANDS),
        "properties": {
            band: risk_band_policy_schema() for band in SUPPORTED_RISK_BANDS
        },
        "additionalProperties": False,
    }


def commit_window_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "minimum_stability_steps": authority_integer_schema(minimum=1),
            "deliberation_deadline_steps": authority_integer_schema(minimum=1),
            "maximum_leader_resets": authority_integer_schema(),
            "maximum_epoch_restarts": authority_integer_schema(),
            "run_deadline_steps": authority_integer_schema(minimum=1),
            "reset_rules": {
                "type": "array",
                "items": {"enum": sorted(REQUIRED_COMMIT_RESET_RULES)},
                "minItems": len(REQUIRED_COMMIT_RESET_RULES),
                "maxItems": len(REQUIRED_COMMIT_RESET_RULES),
                "uniqueItems": True,
            },
            "extensions": extensions_schema(),
        },
        required=[
            "minimum_stability_steps",
            "deliberation_deadline_steps",
            "maximum_leader_resets",
            "maximum_epoch_restarts",
            "run_deadline_steps",
            "reset_rules",
        ],
    )


def terminal_outcome_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "safe_fallback_candidate": canonical_text_schema(),
            "deadline_outcome": {"enum": sorted(SUPPORTED_DEADLINE_OUTCOMES)},
            "policy_incomplete_outcome": {"const": "invalid"},
            "finality_unavailable_outcome": {"const": "finality_unavailable"},
            "deliverable_outcomes": canonical_text_set_schema(
                allowed_values=SUPPORTED_TERMINAL_OUTCOMES,
                minimum_items=len(SUPPORTED_TERMINAL_OUTCOMES),
            ),
            "publishable_outcomes": canonical_text_set_schema(
                allowed_values=SUPPORTED_TERMINAL_OUTCOMES
            ),
            "executable_outcomes": canonical_text_set_schema(
                allowed_values=SUPPORTED_TERMINAL_OUTCOMES
            ),
            "extensions": extensions_schema(),
        },
        required=[
            "safe_fallback_candidate",
            "deadline_outcome",
            "policy_incomplete_outcome",
            "finality_unavailable_outcome",
            "deliverable_outcomes",
            "publishable_outcomes",
            "executable_outcomes",
        ],
    )


def certificate_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "mode": {"enum": sorted(SUPPORTED_CERTIFICATE_MODES)},
            "wire_version": {"const": COMMIT_WIRE_VERSION},
            "canonicalization": {"const": COMMIT_CANONICAL_VERSION},
            "hash_algorithm": {"const": "sha256"},
            "issuer_attestation_required": {"type": "boolean"},
            "independent_verification_required": {"type": "boolean"},
            "extensions": extensions_schema(),
        },
        required=[
            "mode",
            "wire_version",
            "canonicalization",
            "hash_algorithm",
            "issuer_attestation_required",
            "independent_verification_required",
        ],
    )


def distributed_commit_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "fault_model": {"const": "byzantine_static_v1"},
            "membership_mode": {"const": "static_epoch_verified_clusters_v1"},
            "membership_size": authority_integer_schema(minimum=1),
            "max_byzantine_faults": authority_integer_schema(),
            "witness_quorum": authority_integer_schema(minimum=1),
            "witness_ttl_steps": authority_integer_schema(minimum=1),
            "minimum_failure_domain_diversity": authority_integer_schema(minimum=1),
            "epoch_transition_rule": canonical_text_schema(),
            "conflict_rule": {"const": "freeze_v1"},
            "extensions": extensions_schema(),
        },
        required=[
            "fault_model",
            "membership_mode",
            "membership_size",
            "max_byzantine_faults",
            "witness_quorum",
            "witness_ttl_steps",
            "minimum_failure_domain_diversity",
            "epoch_transition_rule",
            "conflict_rule",
        ],
    )


def collective_commit_policy_schema() -> dict[str, Any]:
    return object_schema(
        {
            "policy_version": {"const": COMMIT_POLICY_VERSION},
            "model": {"const": COMMIT_MODEL},
            "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "target": canonical_text_schema(),
            "evidence_qualification": evidence_qualification_policy_schema(),
            "support_lease": support_lease_policy_schema(),
            "risk_bands": risk_bands_schema(),
            "commit_window": commit_window_policy_schema(),
            "terminal_outcome": terminal_outcome_policy_schema(),
            "certificate": certificate_policy_schema(),
            "distributed": {
                "oneOf": [distributed_commit_policy_schema(), {"const": None}]
            },
            "extensions": extensions_schema(),
        },
        required=[
            "policy_version",
            "model",
            "assurance",
            "target",
            "evidence_qualification",
            "support_lease",
            "risk_bands",
            "commit_window",
            "terminal_outcome",
            "certificate",
            "distributed",
        ],
    )


def protocol_schema() -> dict[str, Any]:
    """Return the byte-frozen legacy v1 schema document.

    The original unversioned ``$id`` is a de-facto v1 compatibility surface.
    Runtime readers still reject unsupported protocol versions; the stricter
    standalone schema is published separately by :func:`protocol_schema_v2`.
    """

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
                    "pheromone_evaporation_rate": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "pheromone_decay_model": {
                        "enum": ["linear", "exponential", "step"]
                    },
                    "pheromone_min_strength": {"type": "number", "minimum": 0},
                    "pheromone_max_strength": {"type": "number", "minimum": 0},
                    "pheromone_positive_weight": {"type": "number", "minimum": 0},
                    "pheromone_negative_weight": {"type": "number", "minimum": 0},
                    "pheromone_cautionary_weight": {"type": "number", "minimum": 0},
                    "pheromone_cautionary_override_threshold": {
                        "type": "number",
                        "minimum": 0,
                    },
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
                    "pheromone_response_model": {
                        "enum": ["linear", "saturating", "threshold", "competitive"]
                    },
                    "pheromone_activation_threshold": {"type": "number", "minimum": 0},
                    "pheromone_saturation_threshold": {"type": "number", "minimum": 0},
                    "pheromone_competition_mode": {"enum": ["none", "normalize"]},
                    "pheromone_exploration_floor": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "pheromone_diffusion_enabled": {"type": "boolean"},
                    "pheromone_diffusion_max_hops": {"type": "integer", "minimum": 0},
                    "pheromone_diffusion_attenuation": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "pheromone_feedback_enabled": {"type": "boolean"},
                    "exploration_enabled": {"type": "boolean"},
                    "exploration_floor": {"type": "number", "minimum": 0, "maximum": 1},
                    "novelty_decay_rate": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "stale_route_reopen_threshold": {"type": "number", "minimum": 0},
                    "layer_coordination_enabled": {"type": "boolean"},
                    "layer_weight_bounds": layer_bounds_map_schema(),
                    "layer_default_weights": layer_number_map_schema(maximum=10),
                    "layer_confidence_thresholds": layer_number_map_schema(maximum=1),
                    "layer_conflict_threshold": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "layer_emergency_override_threshold": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "layer_min_provenance": {"type": "integer", "minimum": 1},
                    "layer_fallback_on_unresolved_conflict": {"type": "boolean"},
                    "policy_adjustment_bounds": policy_adjustment_bounds_schema(),
                    "fallback_candidate": {"type": "string"},
                    "extensions": extensions_schema(),
                }
            ),
            "collective_commit_policy": collective_commit_policy_schema(),
            "recovery_protocols": {
                "type": "array",
                "items": object_schema(
                    {
                        "id": {"type": "string"},
                        "trigger_targets": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "allowed_roles": {"type": "array", "items": {"type": "string"}},
                        "allowed_tags": {"type": "array", "items": {"type": "string"}},
                        "required_tools": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
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
                    "requires_publication_permission": {
                        "type": "boolean",
                        "const": True,
                    },
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
        required=[
            "protocol_version",
            "id",
            "targets",
            "candidates",
            "quorum_policy",
            "output_policy",
            "trace_policy",
        ],
    ) | {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROTOCOL_SCHEMA_V1_ID,
    }


def capability_schema() -> dict[str, Any]:
    """Return the byte-frozen legacy v1 capability schema document."""

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
        "$id": CAPABILITY_SCHEMA_V1_ID,
    }


def protocol_schema_v2() -> dict[str, Any]:
    """Return the versioned strict schema for supported protocol payloads."""

    schema = protocol_schema()
    schema["$id"] = PROTOCOL_SCHEMA_V2_ID
    schema["properties"]["protocol_version"] = {
        "type": "string",
        # This published schema-document version is permanently scoped to the
        # legacy semantic profile.  Scoped authority uses protocol schema v3.
        "enum": ["pheroos.protocol.v1"],
    }
    return schema


def capability_schema_v2() -> dict[str, Any]:
    """Return the versioned strict capability schema document."""

    schema = capability_schema()
    schema["$id"] = CAPABILITY_SCHEMA_V2_ID
    schema["properties"]["protocol"] = protocol_schema_v2()
    return schema


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
