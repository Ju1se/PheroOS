from __future__ import annotations

from typing import Any

from pheroos.trace.commit_contracts import (
    COMMIT_EVENT_TYPES,
    commit_trace_lineage_schema,
)
from pheroos.trace.validation import (
    DECLARED_COORDINATION_LAYER_IDS,
    EVENT_LINEAGE_CONTRACTS,
    VALID_EVENT_TYPES,
)


def trace_schema() -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/trace.schema.json",
        "type": "object",
        "required": ["event_type", "protocol_id", "target", "reason"],
        "additionalProperties": False,
        "properties": {
            "event_type": {
                "description": "Built-in trace event type or namespaced extension event using x-* or ext.*.",
                "oneOf": [
                    {"enum": sorted(VALID_EVENT_TYPES)},
                    {"type": "string", "pattern": "^(x-.+|ext\\..+)$"},
                ],
            },
            "protocol_id": nonempty_string(),
            "target": nonempty_string(),
            "reason": nonempty_string(),
            "lineage": {"type": "object"},
        },
        "$defs": {
            "coverageValue": {
                "oneOf": [
                    {"type": "number", "minimum": 0, "maximum": 1},
                    {
                        "type": "object",
                        "additionalProperties": {"$ref": "#/$defs/coverageValue"},
                    },
                ]
            }
        },
    }
    schema["allOf"] = [
        event_lineage_condition(event_type, event_lineage_schema(event_type))
        for event_type in sorted(EVENT_LINEAGE_CONTRACTS)
    ]
    return schema


def event_lineage_condition(event_type: str, lineage_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "if": {
            "properties": {"event_type": {"const": event_type}},
            "required": ["event_type"],
        },
        "then": {
            "properties": {"lineage": lineage_schema},
            "required": ["lineage"],
        },
    }


def event_lineage_schema(event_type: str) -> dict[str, Any]:
    if event_type in COMMIT_EVENT_TYPES:
        return commit_trace_lineage_schema(event_type)
    if event_type == "pheromone_observe":
        return pheromone_observation_schema()
    if event_type == "pheromone_clip":
        return pheromone_clip_schema()
    properties = lineage_properties()[event_type]
    return {
        "type": "object",
        "required": sorted(EVENT_LINEAGE_CONTRACTS[event_type]),
        "properties": properties,
        "additionalProperties": True,
        **output_gate_constraints(event_type),
        **layer_proposal_constraints(event_type),
        **policy_adjustment_replay_constraints(event_type),
    }


def lineage_properties() -> dict[str, dict[str, Any]]:
    strength_fields = {
        "old_strength": nonnegative_number(),
        "new_strength": nonnegative_number(),
    }
    collective_signal = {
        "source_id": nonempty_string(),
        "candidate_id": nonempty_string(),
        "strength": nonnegative_number(),
        "provenance": nonempty_string(),
        "source_trace_event_id": nonempty_string(),
        "verification_trace_event_id": nonempty_string(),
    }
    return {
        "explore": {"scout_count": {"type": "integer", "minimum": 1}},
        "scout_report": {
            "scout_id": nonempty_string(),
            "candidate_id": nonempty_string(),
            "evidence_id": nonempty_string(),
            "provenance": nonempty_string(),
            "support": nonnegative_number(),
            "source_trace_event_id": nonempty_string(),
            "verification_trace_event_id": nonempty_string(),
        },
        "recruit": dict(collective_signal),
        "inhibit": dict(collective_signal),
        "pheromone_deposit": {
            "source_id": nonempty_string(),
            "provenance": nonempty_string(),
            "subject_type": nonempty_string(),
            "subject_id": nonempty_string(),
            "candidate_id": nonempty_string(),
            "kind": nonempty_string(),
            "source_kind": nonempty_string(),
            "source_strength": nonnegative_number(),
            **strength_fields,
            "requested_strength": nonnegative_number(),
            "applied_strength": nonnegative_number(),
            "round_budget_remaining": nonnegative_number(),
            "source_budget_remaining": nonnegative_number(),
            "step": {"type": "integer", "minimum": 0},
            "deposited_at_step": {"type": "integer", "minimum": 0},
            "updated_at_step": {"type": "integer", "minimum": 0},
            "source_trace_event_id": nonempty_string(),
            "trace_event_id": nonempty_string(),
        },
        "pheromone_evaporate": {
            "source_id": nonempty_string(),
            "provenance": nonempty_string(),
            "subject_type": nonempty_string(),
            "subject_id": nonempty_string(),
            "kind": nonempty_string(),
            "source_kind": nonempty_string(),
            "source_strength": nonnegative_number(),
            **strength_fields,
            "requested_strength": nonnegative_number(),
            "applied_strength": nonnegative_number(),
            "strength_delta": finite_number(),
            "elapsed_steps": {"type": "integer", "minimum": 1},
            "step": {"type": "integer", "minimum": 0},
            "source_updated_at_step": {"type": "integer", "minimum": 0},
            "deposited_at_step": {"type": "integer", "minimum": 0},
            "profile": nonempty_string(),
            "candidate_id": nonempty_string(),
            "source_trace_event_id": nonempty_string(),
            "trace_event_id": nonempty_string(),
        },
        "pheromone_diffuse": {
            "source_subject": subject_schema(),
            "target_subject": subject_schema(),
            "hop": {"type": "integer", "minimum": 1},
            "attenuation": {"type": "number", "minimum": 0, "maximum": 1},
            "policy_attenuation": {"type": "number", "minimum": 0, "maximum": 1},
            "edge_attenuation": {"type": "number", "minimum": 0, "maximum": 1},
            "root_trace_event_id": nonempty_string(),
            "source_strength": nonnegative_number(),
            "requested_strength": nonnegative_number(),
            "applied_strength": nonnegative_number(),
            "new_strength": nonnegative_number(),
            "round_budget_remaining": nonnegative_number(),
            "source_budget_remaining": nonnegative_number(),
            "source_id": nonempty_string(),
            "candidate_id": nonempty_string(),
            "source_kind": nonempty_string(),
            "kind": nonempty_string(),
            "provenance": nonempty_string(),
            "source_trace_event_id": nonempty_string(),
            "trace_event_id": nonempty_string(),
        },
        "pheromone_reinforce": {
            "feedback_source": nonempty_string(),
            "source_id": nonempty_string(),
            "provenance": nonempty_string(),
            "outcome": nonempty_string(),
            "reward": finite_number(),
            "delta": finite_number(),
            "source_strength": nonnegative_number(),
            "requested_strength": nonnegative_number(),
            "applied_strength": nonnegative_number(),
            **strength_fields,
            "candidate_id": nonempty_string(),
            "subject_type": nonempty_string(),
            "subject_id": nonempty_string(),
            "source_kind": nonempty_string(),
            "kind": nonempty_string(),
            "budget_result": budget_result_schema(),
            "step": {"type": "integer", "minimum": 0},
            "source_trace_event_id": nonempty_string(),
            "feedback_trace_event_id": nonempty_string(),
            "trace_event_id": nonempty_string(),
        },
        "pheromone_score": {
            "scores": score_map(),
            "score_breakdown": dimension_breakdown(),
            "kind_breakdown": dimension_breakdown(),
            "subject_breakdown": dimension_breakdown(),
            "active_trails": active_trail_array(),
            "current_step": {"type": "integer", "minimum": 0},
            "processed_replay_receipts": processed_replay_receipts_schema(),
        },
        "pheromone_clip": {
            "lifecycle": {"enum": ["deposit", "diffusion", "feedback"]},
            "result": {"enum": ["applied", "rejected"]},
            "source_id": nonempty_string(),
            "provenance": nonempty_string(),
            "candidate_id": nonempty_string(),
            "subject_type": nonempty_string(),
            "subject_id": nonempty_string(),
            "kind": nonempty_string(),
            "source_kind": nonempty_string(),
            "source_strength": nonnegative_number(),
            "new_strength": nonnegative_number(),
            "step": {"type": "integer", "minimum": 0},
            "source_trace_event_id": nonempty_string(),
            "trace_event_id": nonempty_string(),
            "requested_strength": nonnegative_number(),
            "applied_strength": nonnegative_number(),
            "round_budget_remaining": nonnegative_number(),
            "source_budget_remaining": nonnegative_number(),
        },
        "pheromone_expire": {
            "action": {"const": "expire"},
            "target": nonempty_string(),
            "candidate_id": nonempty_string(),
            "subject_type": nonempty_string(),
            "subject_id": nonempty_string(),
            "kind": {"const": "stale"},
            "source_kind": nonempty_string(),
            "source_id": nonempty_string(),
            "provenance": nonempty_string(),
            "source_trace_event_id": nonempty_string(),
            "trace_event_id": nonempty_string(),
            "source_strength": nonnegative_number(),
            **strength_fields,
            "requested_strength": nonnegative_number(),
            "applied_strength": nonnegative_number(),
            "strength_delta": finite_number(),
            "step": {"type": "integer", "minimum": 0},
            "source_updated_at_step": {"type": "integer", "minimum": 0},
            "deposited_at_step": {"type": "integer", "minimum": 0},
            "ttl_steps": {"type": "integer", "minimum": 0},
            "elapsed_steps": {"type": "integer", "minimum": 0},
        },
        "pheromone_observe": {},
        "pheromone_normalize": {
            "candidates": nonempty_string_array(),
            "pre_scores": score_map(),
            "post_scores": score_map(),
            "response_model": nonempty_string(),
            "competition_mode": nonempty_string(),
        },
        "layer_proposal": {
            "layer_id": {
                "enum": ["reactive", "learned", "evolutionary", "metacognitive"]
            },
            "source_id": nonempty_string(),
            "action": nonempty_string(),
            "effect": nonempty_string(),
            "candidate_id": nonempty_string(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "support": {"type": "number", "minimum": 0, "maximum": 10},
            "risk": {"type": "number", "minimum": 0, "maximum": 10},
            "proposed_strength": {"type": "number", "minimum": 0, "maximum": 10},
            "proposed_pheromone_kind": {"type": "string"},
            "subject_type": nonempty_string(),
            "subject_id": nonempty_string(),
            "evidence_id": nonempty_string(),
            "provenance": nonempty_string(),
            "source_trace_event_id": nonempty_string(),
        },
        "coordination_assess": {
            "confidences": declared_layer_score_map(minimum=0, maximum=1),
            "weights": declared_layer_score_map(minimum=0),
            "snapshots": layer_snapshots_schema(),
            "coverage": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": {"$ref": "#/$defs/coverageValue"},
            },
            "action_effects": {
                "type": "object",
                "additionalProperties": nonempty_string(),
            },
            "trace_coverage_confirmations": bounded_score_map(
                minimum=0,
                maximum=1,
                allow_empty=True,
            ),
            "proposal_lineage": string_array(),
        },
        "coordination_resolve": {
            "conflicts": string_array(),
            "resolution": nonempty_string(),
            "selected_candidate": nonempty_string(),
            "fallback_used": {"type": "boolean"},
            "reason": nonempty_string(),
            "proposal_lineage": string_array(),
        },
        "policy_adjustment": {
            "proposed_values": adjustment_values_schema(),
            "declared_bounds": adjustment_bounds_schema(),
            "result": {"enum": ["accepted", "rejected", "replay_ignored"]},
            "source_id": nonempty_string(),
            "layer_id": {
                "enum": ["reactive", "learned", "evolutionary", "metacognitive"]
            },
            "provenance": nonempty_string(),
            "source_trace_event_id": nonempty_string(),
            "replayed": {"type": "boolean"},
            "replay_payload": replay_payload_schema(),
            "replay_payload_fingerprint": receipt_fingerprint_schema(),
            "processed_payload_fingerprint": receipt_fingerprint_schema(),
        },
        "candidate_score": {
            "scores": score_map(),
            "score_breakdown": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": score_map(),
                "description": "Each candidate's categories must sum to its value in scores; enforced by Trace ABI validation.",
            },
            "scout_diversity": count_map(),
            "pheromone_source_diversity": count_map(),
        },
        "consensus_check": {
            "quorum_threshold": {"type": "number", "exclusiveMinimum": 0},
            "min_independent_scouts": {"type": "integer", "minimum": 1},
        },
        "commit": decision_lineage_properties(),
        "fallback": decision_lineage_properties(),
        "output": {
            "committed_candidate": {"type": "boolean"},
            "evidence_provenance": {"type": "boolean"},
            "stop_resolution": {"type": "boolean"},
            "publication_permission": {"type": "boolean"},
            "authorized": {"type": "boolean"},
        },
    }


def decision_lineage_properties() -> dict[str, Any]:
    return {
        "target": nonempty_string(),
        "candidate_id": nonempty_string(),
        "decision_reason": nonempty_string(),
        "upstream_score_lineage": nonempty_string_array(),
    }


def active_trail_array() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "required": [
                "trace_event_id",
                "source_id",
                "candidate_id",
                "subject_type",
                "subject_id",
                "kind",
                "source_kind",
                "strength",
                "provenance",
                "deposited_at_step",
                "updated_at_step",
                "ttl_steps",
            ],
            "properties": {
                "trace_event_id": nonempty_string(),
                "source_id": nonempty_string(),
                "candidate_id": nonempty_string(),
                "subject_type": nonempty_string(),
                "subject_id": nonempty_string(),
                "kind": nonempty_string(),
                "source_kind": nonempty_string(),
                "strength": nonnegative_number(),
                "provenance": nonempty_string(),
                "deposited_at_step": {"type": "integer", "minimum": 0},
                "updated_at_step": {"type": "integer", "minimum": 0},
                "ttl_steps": {
                    "oneOf": [
                        {"type": "integer", "minimum": 0},
                        {"type": "null"},
                    ]
                },
            },
            "additionalProperties": False,
        },
    }


def output_gate_constraints(event_type: str) -> dict[str, Any]:
    if event_type != "output":
        return {}
    gates = ("committed_candidate", "evidence_provenance", "stop_resolution", "publication_permission")
    return {
        "allOf": [
            {
                "if": {"properties": {"authorized": {"const": True}}, "required": ["authorized"]},
                "then": {"properties": {gate: {"const": True} for gate in gates}},
            },
            {
                "if": {
                    "properties": {gate: {"const": True} for gate in gates},
                    "required": list(gates),
                },
                "then": {"properties": {"authorized": {"const": True}}},
            },
        ]
    }


def layer_proposal_constraints(event_type: str) -> dict[str, Any]:
    if event_type != "layer_proposal":
        return {}
    return {
        "allOf": [
            {
                "if": {
                    "properties": {"action": {"const": "propose_pheromone"}},
                    "required": ["action"],
                },
                "then": {
                    "properties": {
                        "effect": {"const": "bounded_pheromone_deposit_proposed"},
                        "proposed_pheromone_kind": nonempty_string(),
                        "proposed_strength": {"type": "number", "exclusiveMinimum": 0, "maximum": 10},
                    }
                },
            }
        ]
    }


def policy_adjustment_replay_constraints(event_type: str) -> dict[str, Any]:
    if event_type != "policy_adjustment":
        return {}
    return {
        "allOf": [
            {
                "if": {
                    "properties": {"result": {"const": "replay_ignored"}},
                    "required": ["result"],
                },
                "then": {
                    "required": [
                        "replayed",
                        "replay_payload",
                        "replay_payload_fingerprint",
                        "processed_payload_fingerprint",
                    ],
                    "properties": {
                        "replayed": {"const": True},
                    },
                },
            }
        ]
    }


def pheromone_observation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "oneOf": [
            {
                "required": [
                    "lifecycle",
                    "source_trace_event_id",
                    "result",
                    "replay_payload",
                    "replay_payload_fingerprint",
                    "processed_payload_fingerprint",
                ],
                "properties": {
                    "lifecycle": {"enum": ["deposit", "diffusion", "feedback"]},
                    "source_trace_event_id": nonempty_string(),
                    "result": {"const": "replay_ignored"},
                    "replay_payload": replay_payload_schema(),
                    "replay_payload_fingerprint": receipt_fingerprint_schema(),
                    "processed_payload_fingerprint": receipt_fingerprint_schema(),
                },
                "additionalProperties": False,
            },
            {
                "required": [
                    "candidate_id",
                    "subject_type",
                    "subject_id",
                    "novelty_pressure",
                    "reopen_eligible",
                    "source_trace_event_id",
                ],
                "properties": {
                    "candidate_id": nonempty_string(),
                    "subject_type": nonempty_string(),
                    "subject_id": nonempty_string(),
                    "novelty_pressure": nonnegative_number(),
                    "reopen_eligible": {"type": "boolean"},
                    "source_trace_event_id": nonempty_string(),
                },
                "additionalProperties": False,
            },
            {
                "required": ["exploration_floor", "candidate_ids"],
                "properties": {
                    "exploration_floor": nonnegative_number(),
                    "candidate_ids": nonempty_string_array(),
                },
                "additionalProperties": False,
            },
        ],
    }


def pheromone_clip_schema() -> dict[str, Any]:
    properties = {
        **lineage_properties()["pheromone_clip"],
        "source_subject": subject_schema(),
        "target_subject": subject_schema(),
        "hop": {"type": "integer", "minimum": 1},
        "attenuation": {"type": "number", "minimum": 0, "maximum": 1},
        "policy_attenuation": {"type": "number", "minimum": 0, "maximum": 1},
        "edge_attenuation": {"type": "number", "minimum": 0, "maximum": 1},
        "root_trace_event_id": nonempty_string(),
        "outcome": nonempty_string(),
        "reward": finite_number(),
        "feedback_trace_event_id": nonempty_string(),
        "strength_delta": nonnegative_number(),
        "causal_payload": pheromone_clip_causal_payload_schema(),
        "causal_fingerprint": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$",
        },
    }
    transition_fields = ["source_kind", "source_strength", "new_strength", "step"]
    return {
        "type": "object",
        "required": sorted(EVENT_LINEAGE_CONTRACTS["pheromone_clip"]),
        "properties": properties,
        "additionalProperties": True,
        "allOf": [
            {
                "if": {
                    "properties": {"result": {"const": "rejected"}},
                    "required": ["result"],
                },
                "then": {
                    "required": ["causal_payload", "causal_fingerprint"],
                },
            },
            {
                "if": {
                    "properties": {"lifecycle": {"const": "deposit"}},
                    "required": ["lifecycle"],
                },
                "then": {"required": transition_fields},
            },
            {
                "if": {
                    "properties": {"lifecycle": {"const": "diffusion"}},
                    "required": ["lifecycle"],
                },
                "then": {
                    "required": [
                        *transition_fields,
                        "source_subject",
                        "target_subject",
                        "hop",
                        "attenuation",
                        "policy_attenuation",
                        "edge_attenuation",
                        "root_trace_event_id",
                    ],
                    "properties": {
                        "result": {"const": "rejected"},
                        "applied_strength": {"const": 0},
                        "new_strength": {"const": 0},
                    },
                },
            },
            {
                "if": {
                    "properties": {"lifecycle": {"const": "feedback"}},
                    "required": ["lifecycle"],
                },
                "then": {
                    "required": [
                        *transition_fields,
                        "outcome",
                        "reward",
                        "strength_delta",
                        "feedback_trace_event_id",
                    ],
                    "properties": {
                        "result": {"const": "rejected"},
                        "applied_strength": {"const": 0},
                    },
                },
            },
        ],
    }


def pheromone_clip_causal_payload_schema() -> dict[str, Any]:
    return {
        "oneOf": [
            {
                "type": "object",
                "required": ["lifecycle", "input", "effective"],
                "properties": {
                    "lifecycle": {"const": "deposit"},
                    "input": pheromone_trail_payload_schema(),
                    "effective": {
                        "type": "object",
                        "required": [
                            "target",
                            "candidate_id",
                            "subject_type",
                            "subject_id",
                            "source_id",
                        ],
                        "properties": {
                            field_name: nonempty_string()
                            for field_name in (
                                "target",
                                "candidate_id",
                                "subject_type",
                                "subject_id",
                                "source_id",
                            )
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["lifecycle", "input", "source_state"],
                "properties": {
                    "lifecycle": {"const": "feedback"},
                    "input": {
                        "type": "object",
                        "required": [
                            "source_id",
                            "subject_type",
                            "subject_id",
                            "candidate_id",
                            "target",
                            "outcome",
                            "reward",
                            "strength_delta",
                            "evidence_id",
                            "provenance",
                            "trace_event_id",
                            "step",
                        ],
                        "properties": {
                            **{
                                field_name: nonempty_string()
                                for field_name in (
                                    "source_id",
                                    "subject_type",
                                    "subject_id",
                                    "candidate_id",
                                    "target",
                                    "outcome",
                                    "provenance",
                                    "trace_event_id",
                                )
                            },
                            "evidence_id": {"type": "string"},
                            "reward": finite_number(),
                            "strength_delta": nonnegative_number(),
                            "step": {"type": "integer", "minimum": 0},
                        },
                        "additionalProperties": False,
                    },
                    "source_state": {
                        "type": "object",
                        "required": [
                            "trace_event_id",
                            "strength",
                            "kind",
                            "provenance",
                        ],
                        "properties": {
                            "trace_event_id": nonempty_string(),
                            "strength": nonnegative_number(),
                            "kind": nonempty_string(),
                            "provenance": nonempty_string(),
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["lifecycle", "input", "effective"],
                "properties": {
                    "lifecycle": {"const": "diffusion"},
                    "input": {
                        "type": "object",
                        "required": [
                            "source_trail",
                            "target_subject",
                            "edge",
                            "policy_attenuation",
                            "hop",
                            "parent_trace_event_id",
                            "derived_trace_event_id",
                        ],
                        "properties": {
                            "source_trail": pheromone_trail_payload_schema(),
                            "target_subject": {
                                "type": "object",
                                "required": [
                                    "subject_type",
                                    "subject_id",
                                    "candidate_id",
                                    "target",
                                ],
                                "properties": {
                                    field_name: nonempty_string()
                                    for field_name in (
                                        "subject_type",
                                        "subject_id",
                                        "candidate_id",
                                        "target",
                                    )
                                },
                                "additionalProperties": False,
                            },
                            "edge": {
                                "type": "object",
                                "required": [
                                    "source_subject_type",
                                    "source_subject_id",
                                    "target_subject_type",
                                    "target_subject_id",
                                    "attenuation",
                                ],
                                "properties": {
                                    **{
                                        field_name: nonempty_string()
                                        for field_name in (
                                            "source_subject_type",
                                            "source_subject_id",
                                            "target_subject_type",
                                            "target_subject_id",
                                        )
                                    },
                                    "attenuation": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                                "additionalProperties": False,
                            },
                            "policy_attenuation": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "hop": {"type": "integer", "minimum": 1},
                            "parent_trace_event_id": nonempty_string(),
                            "derived_trace_event_id": nonempty_string(),
                        },
                        "additionalProperties": False,
                    },
                    "effective": {
                        "type": "object",
                        "required": [
                            "target",
                            "candidate_id",
                            "subject_type",
                            "subject_id",
                            "source_id",
                            "source_kind",
                            "source_strength",
                            "root_trace_event_id",
                        ],
                        "properties": {
                            **{
                                field_name: nonempty_string()
                                for field_name in (
                                    "target",
                                    "candidate_id",
                                    "subject_type",
                                    "subject_id",
                                    "source_id",
                                    "source_kind",
                                    "root_trace_event_id",
                                )
                            },
                            "source_strength": nonnegative_number(),
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
        ]
    }


def pheromone_trail_payload_schema() -> dict[str, Any]:
    text_fields = (
        "candidate_id",
        "subject_type",
        "subject_id",
        "target",
        "route_id",
        "tool_id",
        "kind",
        "source_id",
        "source_role",
        "evidence_id",
        "provenance",
        "trace_event_id",
        "diffusion_root_trace_event_id",
        "diffusion_parent_trace_event_id",
    )
    required = [
        *text_fields,
        "strength",
        "deposited_at_step",
        "updated_at_step",
        "ttl_steps",
        "lineage_event_ids",
        "diffusion_hop",
    ]
    return {
        "type": "object",
        "required": required,
        "properties": {
            **{field_name: {"type": "string"} for field_name in text_fields},
            "strength": nonnegative_number(),
            "deposited_at_step": {"type": "integer", "minimum": 0},
            "updated_at_step": {"type": "integer", "minimum": 0},
            "ttl_steps": {
                "oneOf": [
                    {"type": "integer", "minimum": 0},
                    {"type": "null"},
                ]
            },
            "lineage_event_ids": {"type": "array", "items": nonempty_string()},
            "diffusion_hop": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": False,
    }


def budget_result_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["round_remaining", "source_remaining", "status"],
        "properties": {
            "round_remaining": nonnegative_number(),
            "source_remaining": nonnegative_number(),
            "status": {"enum": ["applied", "rejected"]},
        },
        "additionalProperties": True,
    }


def subject_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["type", "id"],
        "properties": {"type": nonempty_string(), "id": nonempty_string()},
        "additionalProperties": True,
    }


def nonempty_string() -> dict[str, Any]:
    return {"type": "string", "minLength": 1}


def finite_number() -> dict[str, Any]:
    return {"type": "number"}


def nonnegative_number() -> dict[str, Any]:
    return {"type": "number", "minimum": 0}


def nonempty_object() -> dict[str, Any]:
    return {"type": "object", "minProperties": 1}


def nonempty_string_array() -> dict[str, Any]:
    return {"type": "array", "minItems": 1, "items": nonempty_string()}


def string_array() -> dict[str, Any]:
    return {"type": "array", "items": nonempty_string()}


def score_map() -> dict[str, Any]:
    return {"type": "object", "minProperties": 1, "additionalProperties": finite_number()}


def receipt_fingerprint_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}


def replay_payload_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": 1,
        "description": (
            "Complete canonical replay receipt; its SHA-256 binding is "
            "recomputed by Trace ABI validation."
        ),
    }


def processed_replay_receipts_schema() -> dict[str, Any]:
    lifecycles = ("deposit", "diffusion", "feedback", "adjustment")
    receipt_map = {
        "type": "object",
        "additionalProperties": receipt_fingerprint_schema(),
    }
    return {
        "type": "object",
        "required": list(lifecycles),
        "properties": {
            lifecycle: dict(receipt_map)
            for lifecycle in lifecycles
        },
        "additionalProperties": False,
    }


def bounded_score_map(
    *,
    minimum: float,
    maximum: float | None = None,
    allow_empty: bool = False,
) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "number", "minimum": minimum}
    if maximum is not None:
        value["maximum"] = maximum
    result: dict[str, Any] = {"type": "object", "additionalProperties": value}
    if not allow_empty:
        result["minProperties"] = 1
    return result


def declared_layer_score_map(
    *,
    minimum: float,
    maximum: float | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "number", "minimum": minimum}
    if maximum is not None:
        value["maximum"] = maximum
    layer_ids = sorted(DECLARED_COORDINATION_LAYER_IDS)
    return {
        "type": "object",
        "required": layer_ids,
        "properties": {layer_id: dict(value) for layer_id in layer_ids},
        "additionalProperties": False,
    }


def layer_snapshots_schema() -> dict[str, Any]:
    rate_fields = (
        "recent_success_rate",
        "recent_conflict_rate",
        "recent_fallback_rate",
        "mean_confidence",
        "evidence_coverage",
        "trace_coverage",
    )
    snapshot = {
        "type": "object",
        "required": ["present", *rate_fields],
        "properties": {
            "present": {"type": "boolean"},
            **{
                field_name: {"type": "number", "minimum": 0, "maximum": 1}
                for field_name in rate_fields
            },
        },
        "additionalProperties": False,
    }
    layer_ids = sorted(DECLARED_COORDINATION_LAYER_IDS)
    return {
        "type": "object",
        "required": layer_ids,
        "properties": {layer_id: snapshot for layer_id in layer_ids},
        "additionalProperties": False,
    }


def adjustment_scalar_schema() -> dict[str, Any]:
    return {
        "oneOf": [
            {"type": "number"},
            {"type": "string", "minLength": 1},
        ]
    }


def adjustment_values_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "minProperties": 1,
        "additionalProperties": adjustment_scalar_schema(),
    }


def adjustment_bounds_schema() -> dict[str, Any]:
    scalar = adjustment_scalar_schema()
    bound = {
        "oneOf": [
            {
                "type": "array",
                "minItems": 2,
                "maxItems": 2,
                "items": {"type": "number"},
            },
            {
                "type": "object",
                "required": ["min", "max"],
                "properties": {"min": {"type": "number"}, "max": {"type": "number"}},
                "additionalProperties": False,
            },
            {
                "type": "object",
                "required": ["allowed_values"],
                "properties": {
                    "allowed_values": {
                        "type": "array",
                        "minItems": 1,
                        "items": scalar,
                    }
                },
                "additionalProperties": False,
            },
        ]
    }
    return {"type": "object", "minProperties": 1, "additionalProperties": bound}


def count_map() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": {"type": "integer", "minimum": 0},
    }


def dimension_breakdown() -> dict[str, Any]:
    return {
        "type": "object",
        "minProperties": 1,
        "additionalProperties": {
            "type": "object",
            "additionalProperties": finite_number(),
        },
        "description": "Each candidate dimension must reconstruct its score; enforced by Trace ABI validation.",
    }
