from __future__ import annotations

from typing import Any

from pheroos.trace._contracts.distributed_authority import (
    DISTRIBUTED_AUTHORITY_EVENT_TYPES,
)
from pheroos.trace.commit_contracts import (
    COMMIT_EVENT_TYPES,
    commit_trace_lineage_schema,
)
from pheroos.trace.validation import (
    DECLARED_COORDINATION_LAYER_IDS,
    EVENT_LINEAGE_CONTRACTS,
    VALID_EVENT_TYPES,
)


_AUTHORITY_PROTOCOL_ID = "pheroos.protocol.v2"
_AUTHORITY_LOCAL_PROFILE = "pheroos-scoped-authority-local-v2"
_AUTHORITY_AUTHENTICATED_PROFILE = "pheroos-scoped-authority-authenticated-v2"
_AUTHORITY_EVENT_TYPES = frozenset(
    {
        "baseline_action_permission_issued",
        "baseline_decision_evaluated",
        "baseline_evidence_qualified",
        "baseline_manifest_activated",
        "baseline_output_committed",
        "baseline_stop_resolved",
        "domain_retired",
        "issuer_grant_activated",
        "issuer_grant_revoked",
        "hybrid_replay_advanced",
        "commit_replay_advanced",
        "commit_stop_resolved_v2",
        "commit_permission_issued_v2",
        "commit_decision_initialized_v2",
        "commit_assessment_evaluated_v2",
        "commit_window_advanced_v2",
        "commit_window_reset_v2",
        "commit_epoch_restarted_v2",
        "commit_window_sealed_v2",
        "commit_decision_progressed_v2",
        "commit_decision_outcome_committed_v2",
        "commit_evidence_qualified_v2",
        "commit_certificate_verified_v2",
        "commit_certificate_conflict_v2",
        *DISTRIBUTED_AUTHORITY_EVENT_TYPES,
        "risk_state_advanced",
        "risk_assessed_v2",
        "principal_verification_set_advanced",
        "membership_epoch_committed",
        "support_state_advanced",
        "support_lease_issued_v2",
        "support_lease_revoked_v2",
        "signal_verified",
    }
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


def event_lineage_condition(
    event_type: str, lineage_schema: dict[str, Any]
) -> dict[str, Any]:
    event_properties: dict[str, Any] = {"lineage": lineage_schema}
    if event_type in _AUTHORITY_EVENT_TYPES:
        event_properties["protocol_id"] = {"const": _AUTHORITY_PROTOCOL_ID}
    return {
        "if": {
            "properties": {"event_type": {"const": event_type}},
            "required": ["event_type"],
        },
        "then": {
            "properties": event_properties,
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
        "additionalProperties": event_type
        not in {
            "hybrid_replay_advanced",
            "commit_replay_advanced",
            "commit_stop_resolved_v2",
            "commit_permission_issued_v2",
            "commit_decision_initialized_v2",
            "commit_assessment_evaluated_v2",
            "commit_window_advanced_v2",
            "commit_window_reset_v2",
            "commit_epoch_restarted_v2",
            "commit_window_sealed_v2",
            "commit_decision_progressed_v2",
            "commit_decision_outcome_committed_v2",
            "commit_evidence_qualified_v2",
            "commit_certificate_verified_v2",
            "commit_certificate_conflict_v2",
            *DISTRIBUTED_AUTHORITY_EVENT_TYPES,
            "risk_state_advanced",
            "risk_assessed_v2",
            "principal_verification_set_advanced",
            "membership_epoch_committed",
            "support_state_advanced",
            "support_lease_issued_v2",
            "support_lease_revoked_v2",
        },
        **authority_lineage_constraints(event_type),
        **baseline_output_lineage_constraints(event_type),
        **hybrid_replay_lineage_constraints(event_type),
        **commit_replay_lineage_constraints(event_type),
        **risk_v2_lineage_constraints(event_type),
        **membership_authority_lineage_constraints(event_type),
        **support_v2_lineage_constraints(event_type),
        **commit_evidence_v2_lineage_constraints(event_type),
        **commit_decision_v2_lineage_constraints(event_type),
        **commit_certificate_v2_lineage_constraints(event_type),
        **distributed_commit_v2_lineage_constraints(event_type),
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
        "issuer_grant_activated": {
            **authority_common_lineage_properties(
                stream_ref=authority_stream_ref_schema("issuer-grant")
            ),
            **authority_grant_lineage_properties(),
            "verification_root": {
                "oneOf": [receipt_fingerprint_schema(), {"type": "null"}]
            },
        },
        "issuer_grant_revoked": {
            **authority_common_lineage_properties(
                stream_ref=authority_stream_ref_schema("issuer-grant")
            ),
            **authority_grant_lineage_properties(),
            "revocation_generation": {
                **authority_integer_schema(),
                "minimum": 1,
            },
        },
        "signal_verified": {
            **authority_common_lineage_properties(
                stream_ref=authority_stream_ref_schema("verified-signal")
            ),
            **authority_session_lineage_properties(
                operation="verify_signal",
                target_count=1,
            ),
            "target_ref": authority_text_schema(),
            "signal_ref": authority_text_schema(),
            "signal_root": receipt_fingerprint_schema(),
            "evidence_root": receipt_fingerprint_schema(),
        },
        "domain_retired": {
            **authority_common_lineage_properties(
                stream_ref={"const": "authority:domain-lifecycle"}
            ),
            **authority_session_lineage_properties(
                operation="retire_domain",
                target_count=0,
            ),
            "reason_ref": authority_text_schema(),
            "final_heads_root": receipt_fingerprint_schema(),
            "seal_root": receipt_fingerprint_schema(),
        },
        "baseline_manifest_activated": {
            **baseline_output_common_lineage_properties(
                operation="issue_action_permission"
            ),
            "protocol_ref": authority_text_schema(),
        },
        "baseline_evidence_qualified": {
            **baseline_output_common_lineage_properties(
                operation="issue_action_permission"
            ),
            "evidence_root": receipt_fingerprint_schema(),
            "qualified_signal_count": authority_integer_schema(),
        },
        "baseline_stop_resolved": {
            **baseline_output_common_lineage_properties(
                operation="issue_action_permission"
            ),
            "stop_root": receipt_fingerprint_schema(),
        },
        "baseline_decision_evaluated": {
            **baseline_output_common_lineage_properties(
                operation="issue_action_permission"
            ),
            **baseline_output_decision_lineage_properties(),
        },
        "baseline_action_permission_issued": {
            **baseline_output_common_lineage_properties(
                operation="issue_action_permission"
            ),
            **baseline_output_decision_lineage_properties(),
            "effect": baseline_output_effect_schema(),
            "output_payload_root": receipt_fingerprint_schema(),
            "permission_root": receipt_fingerprint_schema(),
            "permission_disposition": baseline_output_action_disposition_schema(),
            "expires_at_epoch": authority_integer_schema(),
        },
        "baseline_output_committed": {
            **baseline_output_common_lineage_properties(operation="authorize_output"),
            **baseline_output_decision_lineage_properties(),
            "effect": baseline_output_effect_schema(),
            "output_payload_root": receipt_fingerprint_schema(),
            "permission_root": receipt_fingerprint_schema(),
            "result_root": receipt_fingerprint_schema(),
            "delivery_disposition": {"const": "deliverable"},
            "action_disposition": baseline_output_action_disposition_schema(),
            "read_set_root": receipt_fingerprint_schema(),
        },
        "hybrid_replay_advanced": {
            **authority_common_lineage_properties(
                stream_ref=authority_stream_ref_schema("hybrid-replay-v2")
            ),
            "transition_id": {
                "type": "string",
                "pattern": r"^transition:hybrid-replay-v2:[0-9a-f]{64}$",
            },
            **authority_session_lineage_properties(
                operation="advance_replay",
                target_count=1,
            ),
            "target_ref": authority_text_schema(),
            "advance_ref": authority_text_schema(),
            "protocol_ref": authority_text_schema(),
            "manifest_root": receipt_fingerprint_schema(),
            "candidate_set_root": receipt_fingerprint_schema(),
            "hybrid_policy_root": receipt_fingerprint_schema(),
            "effective_policy_root": receipt_fingerprint_schema(),
            "topology_root": receipt_fingerprint_schema(),
            "revision": {
                **authority_integer_schema(),
                "minimum": 1,
            },
            "current_step": authority_integer_schema(),
            "parent_transition_id": {
                "oneOf": [authority_text_schema(), {"type": "null"}]
            },
            "parent_snapshot_root": {
                "oneOf": [receipt_fingerprint_schema(), {"type": "null"}]
            },
            "parent_head_root": receipt_fingerprint_schema(),
            "snapshot_root": receipt_fingerprint_schema(),
            "memory_root": receipt_fingerprint_schema(),
            "replay_receipt_root": receipt_fingerprint_schema(),
            "source_step_root": receipt_fingerprint_schema(),
            "source_trace_root": receipt_fingerprint_schema(),
            "read_set_root": receipt_fingerprint_schema(),
        },
        "commit_replay_advanced": {
            **authority_common_lineage_properties(
                stream_ref=authority_stream_ref_schema("commit-replay-v2")
            ),
            "transition_id": {
                "type": "string",
                "pattern": r"^transition:commit-replay-v2:[0-9a-f]{64}$",
            },
            **authority_session_lineage_properties(
                operation="advance_replay",
                target_count=1,
            ),
            "target_ref": authority_text_schema(),
            "advance_ref": authority_text_schema(),
            "protocol_ref": authority_text_schema(),
            "manifest_root": receipt_fingerprint_schema(),
            "commit_policy_root": receipt_fingerprint_schema(),
            "profile": {
                "enum": [
                    "pheroos-certified-commit-v1",
                    "pheroos-commit-integrity-v1",
                    "pheroos-distributed-commit-v1",
                    "pheroos-hybrid-commit-v1",
                ]
            },
            "assurance": {
                "enum": ["advisory", "certified", "distributed", "evidence_bound"]
            },
            "revision": {**authority_integer_schema(), "minimum": 1},
            "current_step": authority_integer_schema(),
            "parent_transition_id": authority_text_schema(),
            "parent_snapshot_root": receipt_fingerprint_schema(),
            "parent_head_root": receipt_fingerprint_schema(),
            "snapshot_root": receipt_fingerprint_schema(),
            "replay_receipt_root": receipt_fingerprint_schema(),
            "receipt_addition_root": receipt_fingerprint_schema(),
            "source_context_root": receipt_fingerprint_schema(),
            "read_set_root": receipt_fingerprint_schema(),
        },
        "commit_stop_resolved_v2": {
            **commit_gate_common_lineage_properties(
                kind="stop",
                operation="resolve_stop",
                action_count=0,
            ),
            "resolution_ref": commit_gate_text_schema(),
            "blocked": {"type": "boolean"},
            "reason_codes": commit_gate_text_array_schema(min_items=0),
            "reason_root": receipt_fingerprint_schema(),
        },
        "commit_permission_issued_v2": {
            **commit_gate_common_lineage_properties(
                kind="permission",
                operation="issue_action_permission",
                action_count=1,
            ),
            "permission_ref": commit_gate_text_schema(),
            "allowed": {"type": "boolean"},
            "candidate_refs": commit_gate_text_array_schema(min_items=1),
            "candidate_set_root": receipt_fingerprint_schema(),
            "claim_roots": authority_root_array_schema(
                min_items=0,
                max_items=4096,
            ),
            "claims_root": receipt_fingerprint_schema(),
        },
        **{
            event_type: commit_decision_v2_lineage_properties()
            for event_type in (
                "commit_decision_initialized_v2",
                "commit_assessment_evaluated_v2",
                "commit_window_advanced_v2",
                "commit_window_reset_v2",
                "commit_epoch_restarted_v2",
                "commit_window_sealed_v2",
                "commit_decision_progressed_v2",
                "commit_decision_outcome_committed_v2",
            )
        },
        "commit_evidence_qualified_v2": commit_evidence_v2_lineage_properties(),
        **{
            event_type: commit_certificate_v2_lineage_properties()
            for event_type in (
                "commit_certificate_conflict_v2",
                "commit_certificate_verified_v2",
            )
        },
        **{
            event_type: distributed_commit_v2_lineage_properties()
            for event_type in DISTRIBUTED_AUTHORITY_EVENT_TYPES
        },
        "risk_state_advanced": risk_v2_common_lineage_properties(),
        "risk_assessed_v2": {
            **risk_v2_common_lineage_properties(),
            "assessment_ref": risk_v2_text_schema(),
            "issuer_ref": risk_v2_text_schema(),
            "risk_band": {"enum": ["CRITICAL", "HIGH", "LOW", "MODERATE"]},
            "risk_input_roots": authority_root_array_schema(
                min_items=1,
                max_items=1024,
            ),
            "rationale_codes": risk_v2_text_array_schema(
                min_items=1,
                max_items=128,
            ),
            "assessment_method": risk_v2_text_schema(),
            "issued_at_step": authority_integer_schema(),
            "expires_at_step": authority_integer_schema(),
            "previous_assessment_root": {
                "oneOf": [
                    {"const": ""},
                    receipt_fingerprint_schema(),
                ]
            },
            "window_reset_required": {"type": "boolean"},
            "provenance_ref": risk_v2_text_schema(),
            "source_trace_roots": authority_root_array_schema(
                min_items=1,
                max_items=1024,
            ),
        },
        "principal_verification_set_advanced": {
            **durable_membership_common_lineage_properties(
                stream_kind="principal-verification-v2",
                operation="qualify_evidence",
                policy_field="verification_policy_root",
            ),
            "verification_policy_root": receipt_fingerprint_schema(),
            "verification_set_root": receipt_fingerprint_schema(),
            "record_count": {
                **authority_integer_schema(),
                "maximum": 4096,
            },
            "current_step": authority_integer_schema(),
            "expires_at_step": authority_integer_schema(),
            "verification_roots": authority_root_array_schema(
                min_items=0,
                max_items=4096,
            ),
        },
        "membership_epoch_committed": {
            **durable_membership_common_lineage_properties(
                stream_kind="membership-v2",
                operation="evaluate_quorum",
                policy_field="membership_policy_root",
            ),
            "membership_policy_root": receipt_fingerprint_schema(),
            "membership_root": receipt_fingerprint_schema(),
            "cluster_count": {
                **authority_integer_schema(),
                "maximum": 1024,
            },
            "principal_count": {
                **authority_integer_schema(),
                "maximum": 4096,
            },
            "issued_at_step": authority_integer_schema(),
            "expires_at_step": authority_integer_schema(),
            "verification_stream_ref": authority_stream_ref_schema(
                "principal-verification-v2"
            ),
            "verification_transition_id": {
                "type": "string",
                "pattern": (r"^transition:principal-verification-v2:[0-9a-f]{64}$"),
            },
            "verification_policy_root": receipt_fingerprint_schema(),
            "verification_request_ref": membership_v2_text_schema(),
            "verification_revision": {
                **authority_integer_schema(),
                "minimum": 1,
            },
            "verification_head_root": receipt_fingerprint_schema(),
            "verification_snapshot_root": receipt_fingerprint_schema(),
            "verification_set_root": receipt_fingerprint_schema(),
            "verification_current_step": authority_integer_schema(),
            "verification_expires_at_step": authority_integer_schema(),
            "verification_record_count": {
                **authority_integer_schema(),
                "maximum": 4096,
            },
            "source_trace_roots": authority_root_array_schema(
                min_items=1,
                max_items=256,
            ),
        },
        "support_state_advanced": {
            **support_v2_common_lineage_properties(),
            "mutation_kind": {"enum": ["initialize", "issue", "revoke", "switch"]},
            "revision": {**authority_integer_schema(), "minimum": 1},
            "initialized_at_step": authority_integer_schema(),
            "current_step": authority_integer_schema(),
            "mutation_provenance_root": receipt_fingerprint_schema(),
            "mutation_trace_roots": authority_root_array_schema(
                min_items=1,
                max_items=1024,
            ),
            "mutation_delta_root": receipt_fingerprint_schema(),
            "evicted_lease_roots": authority_root_array_schema(
                min_items=0,
                max_items=16384,
            ),
            "parent_revision": authority_integer_schema(),
            "parent_transition_id": support_v2_text_schema(),
            "parent_snapshot_root": receipt_fingerprint_schema(),
            "parent_history_root": receipt_fingerprint_schema(),
            "parent_history_count": authority_integer_schema(),
            "history_root": receipt_fingerprint_schema(),
            "history_count": {**authority_integer_schema(), "minimum": 1},
            "parent_head_root": receipt_fingerprint_schema(),
            "snapshot_root": receipt_fingerprint_schema(),
            "lease_set_root": receipt_fingerprint_schema(),
            "active_lease_count": {
                **authority_integer_schema(),
                "maximum": 16384,
            },
            "issued_lease_root": optional_authority_root_schema(),
            "revoked_lease_root": optional_authority_root_schema(),
            "revocation_root": optional_authority_root_schema(),
            "membership_stream_ref": optional_authority_ref_schema("membership-v2"),
            "membership_transition_id": optional_transition_ref_schema("membership-v2"),
            "membership_snapshot_root": optional_authority_root_schema(),
            "source_context_root": receipt_fingerprint_schema(),
            "source_verification_root": receipt_fingerprint_schema(),
            "read_set_root": receipt_fingerprint_schema(),
        },
        "support_lease_issued_v2": {
            **support_v2_common_lineage_properties(),
            "lease_root": receipt_fingerprint_schema(),
            "lease_ref": {
                "type": "string",
                "pattern": r"^lease:support-v2:[0-9a-f]{64}$",
            },
            "mutation_transition_id": support_transition_ref_schema(),
            "proposal_root": receipt_fingerprint_schema(),
            "candidate_ref": support_v2_text_schema(),
            "claim_root": receipt_fingerprint_schema(),
            "epoch": authority_integer_schema(),
            "principal_ref": support_v2_text_schema(),
            "principal_cluster_ref": support_v2_text_schema(),
            "membership_principal_root": receipt_fingerprint_schema(),
            "principal_verification_root": receipt_fingerprint_schema(),
            "membership_stream_ref": authority_stream_ref_schema("membership-v2"),
            "membership_transition_id": {
                "type": "string",
                "pattern": r"^transition:membership-v2:[0-9a-f]{64}$",
            },
            "membership_snapshot_root": receipt_fingerprint_schema(),
            "membership_root": receipt_fingerprint_schema(),
            "positive_observation_set_root": receipt_fingerprint_schema(),
            "prior_lease_root": optional_authority_root_schema(),
            "issuance_issuer_ref": support_v2_text_schema(),
            "issued_at_step": authority_integer_schema(),
            "expires_at_step": authority_integer_schema(),
            "proposal_provenance_root": receipt_fingerprint_schema(),
            "proposal_trace_roots": authority_root_array_schema(
                min_items=1,
                max_items=1024,
            ),
            "issuance_provenance_root": receipt_fingerprint_schema(),
            "issuance_trace_roots": authority_root_array_schema(
                min_items=1,
                max_items=1024,
            ),
            "read_set_root": receipt_fingerprint_schema(),
        },
        "support_lease_revoked_v2": {
            **support_v2_common_lineage_properties(),
            "revocation_root": receipt_fingerprint_schema(),
            "revocation_ref": {
                "type": "string",
                "pattern": r"^revocation:support-v2:[0-9a-f]{64}$",
            },
            "mutation_transition_id": support_transition_ref_schema(),
            "lease_root": receipt_fingerprint_schema(),
            "candidate_ref": support_v2_text_schema(),
            "claim_root": receipt_fingerprint_schema(),
            "epoch": authority_integer_schema(),
            "principal_ref": support_v2_text_schema(),
            "principal_cluster_ref": support_v2_text_schema(),
            "lease_issuance_issuer_ref": support_v2_text_schema(),
            "revocation_issuer_ref": support_v2_text_schema(),
            "reason_codes": support_v2_text_array_schema(
                min_items=1,
                max_items=128,
            ),
            "revoked_at_step": authority_integer_schema(),
            "provenance_root": receipt_fingerprint_schema(),
            "source_trace_roots": authority_root_array_schema(
                min_items=1,
                max_items=1024,
            ),
            "read_set_root": receipt_fingerprint_schema(),
        },
    }


def authority_common_lineage_properties(
    *,
    stream_ref: dict[str, Any],
) -> dict[str, Any]:
    return {
        "domain_root": receipt_fingerprint_schema(),
        "scope_ref": authority_text_schema(),
        "stream_ref": stream_ref,
        "transition_id": {
            **authority_text_schema(),
            "not": {"const": "genesis"},
        },
    }


def authority_grant_lineage_properties() -> dict[str, Any]:
    return {
        "profile": {
            "enum": [
                "pheroos-scoped-authority-authenticated-v2",
                "pheroos-scoped-authority-local-v2",
            ]
        },
        "grant_ref": authority_text_schema(),
        "grant_root": receipt_fingerprint_schema(),
        "grant_binding_ref": receipt_fingerprint_schema(),
        "observed_epoch": authority_integer_schema(),
        "revocation_generation": authority_integer_schema(),
    }


def authority_session_lineage_properties(
    *,
    operation: str,
    target_count: int,
    action_count: int = 0,
) -> dict[str, Any]:
    return {
        "run_ref": authority_text_schema(),
        "request_ref": authority_text_schema(),
        "request_root": receipt_fingerprint_schema(),
        "grant_ref": authority_text_schema(),
        "grant_root": receipt_fingerprint_schema(),
        "grant_binding_ref": receipt_fingerprint_schema(),
        "operation": {"const": operation},
        "observed_epoch": authority_integer_schema(),
        "session_binding": authority_session_binding_schema(
            operation=operation,
            target_count=target_count,
            action_count=action_count,
        ),
    }


def authority_session_binding_schema(
    *,
    operation: str,
    target_count: int,
    action_count: int = 0,
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "action_refs",
            "domain_root",
            "grant_binding_ref",
            "grant_expected_revision",
            "grant_expected_root",
            "grant_ref",
            "grant_root",
            "lifecycle_expected_revision",
            "lifecycle_expected_root",
            "observed_epoch",
            "operation",
            "request_ref",
            "request_root",
            "run_ref",
            "scope_ref",
            "target_refs",
        ],
        "properties": {
            "domain_root": receipt_fingerprint_schema(),
            "scope_ref": authority_text_schema(),
            "run_ref": authority_text_schema(),
            "request_ref": authority_text_schema(),
            "request_root": receipt_fingerprint_schema(),
            "operation": {"const": operation},
            "observed_epoch": authority_integer_schema(),
            "grant_ref": authority_text_schema(),
            "grant_root": receipt_fingerprint_schema(),
            "grant_binding_ref": receipt_fingerprint_schema(),
            "grant_expected_revision": authority_integer_schema(),
            "grant_expected_root": receipt_fingerprint_schema(),
            "lifecycle_expected_revision": authority_integer_schema(),
            "lifecycle_expected_root": receipt_fingerprint_schema(),
            "target_refs": authority_ref_array_schema(
                min_items=target_count,
                max_items=target_count,
            ),
            "action_refs": authority_ref_array_schema(
                min_items=action_count,
                max_items=action_count,
            ),
        },
        "additionalProperties": False,
    }


def baseline_output_common_lineage_properties(
    *,
    operation: str,
) -> dict[str, Any]:
    return {
        **authority_common_lineage_properties(stream_ref=authority_text_schema()),
        **authority_session_lineage_properties(
            operation=operation,
            target_count=1,
            action_count=1,
        ),
        "target_ref": authority_text_schema(),
        "action_ref": authority_text_schema(),
        "manifest_root": receipt_fingerprint_schema(),
        "output_policy_root": receipt_fingerprint_schema(),
    }


def baseline_output_decision_lineage_properties() -> dict[str, Any]:
    return {
        "evidence_root": receipt_fingerprint_schema(),
        "stop_root": receipt_fingerprint_schema(),
        "decision_root": receipt_fingerprint_schema(),
        "candidate_ref": authority_text_schema(),
        "terminal_status": {"enum": ["blocked", "evidence_commit", "safe_fallback"]},
    }


def commit_gate_text_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "maxLength": 4096,
    }


def commit_gate_text_array_schema(*, min_items: int) -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": min_items,
        "maxItems": 4096,
        "uniqueItems": True,
        "items": commit_gate_text_schema(),
    }


def commit_gate_common_lineage_properties(
    *,
    kind: str,
    operation: str,
    action_count: int,
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        **authority_common_lineage_properties(
            stream_ref=authority_stream_ref_schema(f"commit-{kind}-v2")
        ),
        "transition_id": {
            "type": "string",
            "pattern": rf"^transition:commit-{kind}-v2:[0-9a-f]{{64}}$",
        },
        **authority_session_lineage_properties(
            operation=operation,
            target_count=1,
            action_count=action_count,
        ),
        "target_ref": commit_gate_text_schema(),
        "protocol_ref": commit_gate_text_schema(),
        "manifest_root": receipt_fingerprint_schema(),
        "commit_policy_root": receipt_fingerprint_schema(),
        "policy_root": receipt_fingerprint_schema(),
        "profile": {
            "enum": [
                "pheroos-certified-commit-v1",
                "pheroos-commit-integrity-v1",
                "pheroos-distributed-commit-v1",
                "pheroos-hybrid-commit-v1",
            ]
        },
        "assurance": {
            "enum": ["advisory", "certified", "distributed", "evidence_bound"]
        },
        "revision": {**authority_integer_schema(), "minimum": 1},
        "current_step": authority_integer_schema(),
        "parent_revision": authority_integer_schema(),
        "parent_transition_id": commit_gate_text_schema(),
        "parent_snapshot_root": receipt_fingerprint_schema(),
        "parent_head_root": receipt_fingerprint_schema(),
        "snapshot_root": receipt_fingerprint_schema(),
        "mutation_issuer_ref": commit_gate_text_schema(),
        "grant_issuer_ref": commit_gate_text_schema(),
        "issued_at_step": authority_integer_schema(),
        "expires_at_step": authority_integer_schema(),
        "dependency_root": receipt_fingerprint_schema(),
        "evaluation_context_root": receipt_fingerprint_schema(),
        "source_context_root": receipt_fingerprint_schema(),
        "read_set_root": receipt_fingerprint_schema(),
    }
    for name in ("replay", "risk", "verification", "membership", "support"):
        properties.update(
            {
                f"{name}_stream_ref": commit_gate_text_schema(),
                f"{name}_revision": {
                    **authority_integer_schema(),
                    "minimum": 1,
                },
                f"{name}_transition_id": commit_gate_text_schema(),
                f"{name}_snapshot_root": receipt_fingerprint_schema(),
                f"{name}_head_root": receipt_fingerprint_schema(),
            }
        )
    return properties


def commit_decision_v2_lineage_properties() -> dict[str, Any]:
    optional_root = optional_authority_root_schema()
    dependency = {
        "type": "object",
        "required": [
            "dependency_root",
            "head_root",
            "observed_position",
            "receipt_root",
            "revision",
            "role",
            "schema",
            "snapshot_root",
            "stream_ref",
            "transition_id",
        ],
        "properties": {
            "schema": {"const": "pheroos-commit-decision-dependency-v2"},
            "role": {
                "enum": [
                    "certificate",
                    "distributed",
                    "evidence",
                    "membership",
                    "parent",
                    "permission",
                    "principal_verification",
                    "replay",
                    "risk",
                    "stop",
                    "support",
                ]
            },
            "stream_ref": authority_text_schema(),
            "revision": authority_integer_schema(),
            "transition_id": authority_text_schema(),
            "snapshot_root": receipt_fingerprint_schema(),
            "head_root": receipt_fingerprint_schema(),
            "receipt_root": receipt_fingerprint_schema(),
            "observed_position": {"const": "current"},
            "dependency_root": receipt_fingerprint_schema(),
        },
        "additionalProperties": False,
    }
    return {
        **authority_common_lineage_properties(
            stream_ref=authority_stream_ref_schema("commit-decision-v2")
        ),
        "transition_id": {
            "type": "string",
            "pattern": r"^transition:commit-decision-v2:[0-9a-f]{64}$",
        },
        **authority_session_lineage_properties(
            operation="evaluate_quorum",
            target_count=1,
        ),
        "mutation_ref": authority_text_schema(),
        "command": {
            "enum": [
                "epoch_restart",
                "evaluate",
                "explicit_unseal",
                "initialize",
                "seal",
            ]
        },
        "mutation_kind": {
            "enum": [
                "assessed",
                "deadline_terminated",
                "epoch_restarted",
                "finalized",
                "heartbeat",
                "initialized",
                "sealed",
                "window_reset",
            ]
        },
        "revision": {**authority_integer_schema(), "minimum": 1},
        "parent_revision": authority_integer_schema(),
        "parent_transition_id": authority_text_schema(),
        "parent_snapshot_root": receipt_fingerprint_schema(),
        "parent_head_root": receipt_fingerprint_schema(),
        "snapshot_root": receipt_fingerprint_schema(),
        "state_root": receipt_fingerprint_schema(),
        "history_root": receipt_fingerprint_schema(),
        "history_count": {**authority_integer_schema(), "minimum": 1},
        "protocol_ref": authority_text_schema(),
        "target_ref": authority_text_schema(),
        "profile": {
            "enum": [
                "pheroos-certified-commit-v1",
                "pheroos-commit-integrity-v1",
                "pheroos-distributed-commit-v1",
                "pheroos-hybrid-commit-v1",
            ]
        },
        "assurance": {
            "enum": ["advisory", "certified", "distributed", "evidence_bound"]
        },
        "manifest_root": receipt_fingerprint_schema(),
        "commit_policy_root": receipt_fingerprint_schema(),
        "epoch": authority_integer_schema(),
        "current_step": authority_integer_schema(),
        "evidence_deadline_step": authority_integer_schema(),
        "finality_deadline_step": authority_integer_schema(),
        "dependency_set_root": receipt_fingerprint_schema(),
        "source_context_root": receipt_fingerprint_schema(),
        "assessment_root": optional_root,
        "window_root": receipt_fingerprint_schema(),
        "seal_root": optional_root,
        "progress_root": optional_root,
        "outcome_root": optional_root,
        "mutation_issuer_ref": authority_text_schema(),
        "read_set_root": receipt_fingerprint_schema(),
        "dependencies": {
            "type": "array",
            "items": dependency,
            "minItems": 1,
            "maxItems": 11,
            "uniqueItems": True,
        },
    }


def commit_evidence_v2_lineage_properties() -> dict[str, Any]:
    properties = {
        **authority_common_lineage_properties(
            stream_ref=authority_stream_ref_schema("commit-evidence-v2")
        ),
        "transition_id": {
            "type": "string",
            "pattern": r"^transition:commit-evidence-v2:[0-9a-f]{64}$",
        },
        **authority_session_lineage_properties(
            operation="qualify_evidence",
            target_count=1,
        ),
        "target_ref": authority_text_schema(),
        "advance_ref": authority_text_schema(),
        "protocol_ref": authority_text_schema(),
        "profile": authority_text_schema(),
        "assurance": {
            "enum": ["advisory", "certified", "distributed", "evidence_bound"]
        },
        "parent_epoch": {"oneOf": [authority_integer_schema(), {"type": "null"}]},
    }
    for field in (
        "manifest_root",
        "authority_policy_root",
        "commit_policy_root",
        "evidence_policy_root",
        "parent_snapshot_root",
        "parent_history_root",
        "parent_head_root",
        "snapshot_root",
        "history_root",
        "mutation_provenance_root",
        "record_set_root",
        "active_record_set_root",
        "mutation_delta_root",
        "membership_head_root",
        "membership_snapshot_root",
        "membership_root",
        "verification_head_root",
        "verification_snapshot_root",
        "verification_set_root",
        "replay_head_root",
        "replay_snapshot_root",
        "replay_receipt_root",
        "source_context_root",
        "read_set_root",
    ):
        properties[field] = receipt_fingerprint_schema()
    for field in (
        "parent_transition_id",
        "mutation_issuer_ref",
        "membership_stream_ref",
        "membership_transition_id",
        "verification_stream_ref",
        "verification_transition_id",
        "replay_stream_ref",
        "replay_transition_id",
    ):
        properties[field] = authority_text_schema()
    for field in (
        "epoch",
        "revision",
        "current_step",
        "expires_at_step",
        "parent_revision",
        "parent_history_count",
        "history_count",
        "record_count",
        "active_record_count",
        "membership_revision",
        "membership_current_step",
        "membership_expires_at_step",
        "verification_revision",
        "verification_current_step",
        "verification_expires_at_step",
        "replay_revision",
        "replay_current_step",
    ):
        properties[field] = authority_integer_schema()
    for field in (
        "mutation_trace_roots",
        "mutation_record_roots",
        "removed_record_roots",
        "revocation_roots",
        "attestation_roots",
        "disposition_roots",
    ):
        properties[field] = authority_root_array_schema(min_items=0, max_items=4096)
    return properties


def commit_certificate_v2_lineage_properties() -> dict[str, Any]:
    authority_leaf = {
        "type": "object",
        "required": [
            "head_root",
            "leaf_root",
            "receipt_root",
            "revision",
            "role",
            "schema",
            "snapshot_root",
            "stream_ref",
            "transition_id",
        ],
        "properties": {
            "schema": {"const": "pheroos-commit-certificate-authority-leaf-v2"},
            "role": {
                "enum": [
                    "evidence",
                    "membership",
                    "permission",
                    "principal_verification",
                    "replay",
                    "risk",
                    "stop",
                    "support",
                ]
            },
            "stream_ref": authority_text_schema(),
            "revision": {**authority_integer_schema(), "minimum": 1},
            "transition_id": authority_text_schema(),
            "snapshot_root": receipt_fingerprint_schema(),
            "head_root": receipt_fingerprint_schema(),
            "receipt_root": receipt_fingerprint_schema(),
            "leaf_root": receipt_fingerprint_schema(),
        },
        "additionalProperties": False,
    }
    properties: dict[str, Any] = {
        **authority_common_lineage_properties(
            stream_ref=authority_stream_ref_schema("commit-certificate-v2")
        ),
        "transition_id": {
            "type": "string",
            "pattern": r"^transition:commit-certificate-v2:[0-9a-f]{64}$",
        },
        **authority_session_lineage_properties(
            operation="evaluate_quorum",
            target_count=1,
        ),
        "profile": {
            "enum": [
                "pheroos-certified-commit-v1",
                "pheroos-distributed-commit-v1",
            ]
        },
        "assurance": {"enum": ["certified", "distributed"]},
        "mutation_kind": {"enum": ["conflict", "semantic_retry", "verified"]},
        "status": {"enum": ["conflict", "verified"]},
        "authority_leaves": {
            "type": "array",
            "items": authority_leaf,
            "minItems": 8,
            "maxItems": 8,
            "uniqueItems": True,
        },
        "attestation_refs": authority_ref_array_schema(
            min_items=1,
            max_items=32,
        ),
        "reason_codes": authority_ref_array_schema(
            min_items=1,
            max_items=64,
        ),
    }
    for field in (
        "parent_snapshot_root",
        "parent_head_root",
        "snapshot_root",
        "state_root",
        "history_root",
        "manifest_root",
        "commit_policy_root",
        "decision_snapshot_root",
        "decision_head_root",
        "decision_receipt_root",
        "decision_inclusion_root",
        "seal_snapshot_root",
        "seal_receipt_root",
        "seal_head_root",
        "seal_inclusion_root",
        "seal_root",
        "window_root",
        "frozen_dependency_root",
        "assessment_root",
        "claim_root",
        "evidence_root",
        "challenge_root",
        "lease_root",
        "output_contract_root",
        "output_payload_root",
        "authority_leaf_set_root",
        "certificate_body_root",
        "certificate_envelope_root",
        "source_context_root",
        "read_set_root",
    ):
        properties[field] = receipt_fingerprint_schema()
    for field in (
        "parent_transition_id",
        "protocol_ref",
        "target_ref",
        "decision_stream_ref",
        "decision_transition_id",
        "seal_transition_id",
        "candidate_ref",
        "certificate_id",
        "issuer_ref",
        "provenance_ref",
        "mutation_issuer_ref",
    ):
        properties[field] = {**authority_text_schema(), "maxLength": 4096}
    for field in (
        "revision",
        "parent_revision",
        "history_count",
        "epoch",
        "current_step",
        "decision_revision",
        "seal_revision",
        "issued_at_step",
    ):
        properties[field] = authority_integer_schema()
    for field in ("revision", "history_count", "decision_revision", "seal_revision"):
        properties[field] = {**properties[field], "minimum": 1}
    return properties


def distributed_commit_v2_lineage_properties() -> dict[str, Any]:
    """Return the closed portable shape for every Distributed v2 lane event."""

    session = authority_session_lineage_properties(
        operation="evaluate_quorum",
        target_count=1,
    )
    session_binding = session["session_binding"]
    session_binding["properties"]["action_refs"] = {
        "type": "array",
        "items": {**authority_text_schema(), "maxLength": 4096},
        "minItems": 0,
        "maxItems": 2,
        "uniqueItems": True,
    }
    optional_text = {"oneOf": [{"const": ""}, authority_text_schema()]}
    optional_root = optional_authority_root_schema()
    dependency = {
        "type": "object",
        "required": [
            "dependency_root",
            "head_root",
            "inclusion_root",
            "receipt_root",
            "revision",
            "role",
            "schema",
            "snapshot_root",
            "stream_ref",
            "transition_id",
        ],
        "properties": {
            "schema": {"const": "pheroos-distributed-dependency-v2"},
            "role": {
                "enum": [
                    "central_certificate",
                    "certificate",
                    "decision",
                    "epoch",
                    "membership",
                    "principal_verification",
                    "proposal",
                    "witness",
                ]
            },
            "stream_ref": {**authority_text_schema(), "maxLength": 4096},
            "revision": authority_integer_schema(),
            "transition_id": optional_text,
            "snapshot_root": optional_root,
            "head_root": receipt_fingerprint_schema(),
            "receipt_root": optional_root,
            "inclusion_root": optional_root,
            "dependency_root": receipt_fingerprint_schema(),
        },
        "additionalProperties": False,
        "allOf": [
            {
                "if": {
                    "properties": {"revision": {"const": 0}},
                    "required": ["revision"],
                },
                "then": {
                    "properties": {
                        "transition_id": {"const": ""},
                        "snapshot_root": {"const": ""},
                        "receipt_root": {"const": ""},
                        "inclusion_root": {"const": ""},
                    }
                },
                "else": {
                    "properties": {
                        "revision": {**authority_integer_schema(), "minimum": 1},
                        "transition_id": authority_text_schema(),
                        "snapshot_root": receipt_fingerprint_schema(),
                        "receipt_root": receipt_fingerprint_schema(),
                        "inclusion_root": receipt_fingerprint_schema(),
                    }
                },
            }
        ],
    }
    properties: dict[str, Any] = {
        **authority_common_lineage_properties(
            stream_ref={
                "type": "string",
                "pattern": (
                    r"^authority:distributed-(epoch|proposal|witness|certificate)-"
                    r"v2:[0-9a-f]{64}$"
                ),
            }
        ),
        "transition_id": {
            "type": "string",
            "pattern": r"^transition:distributed-v2:[0-9a-f]{64}$",
        },
        **session,
        "protocol_ref": {**authority_text_schema(), "maxLength": 4096},
        "target_ref": {**authority_text_schema(), "maxLength": 4096},
        "lane": {"enum": ["certificate", "epoch", "proposal", "witness"]},
        "mutation_kind": {
            "enum": [
                "certificate_conflict_frozen",
                "certificate_retry",
                "certificate_verified",
                "epoch_initialized",
                "epoch_transitioned",
                "equivocation_frozen",
                "proposal_recorded",
                "proposal_semantic_retry",
                "witness_recorded",
                "witness_retry",
            ]
        },
        "status": {"enum": ["active", "frozen", "verified"]},
        "revision": {**authority_integer_schema(), "minimum": 1},
        "parent_revision": authority_integer_schema(),
        "parent_transition_id": authority_text_schema(),
        "parent_snapshot_root": receipt_fingerprint_schema(),
        "parent_head_root": receipt_fingerprint_schema(),
        "current_epoch": authority_integer_schema(),
        "current_step": authority_integer_schema(),
        "lane_state_root": receipt_fingerprint_schema(),
        "lane_state_material": {"type": "object"},
        "dependencies": {
            "type": "array",
            "items": dependency,
            "minItems": 5,
            "maxItems": 7,
            "uniqueItems": True,
        },
        "dependency_set_root": receipt_fingerprint_schema(),
        "reason_codes": authority_ref_array_schema(
            min_items=1,
            max_items=128,
        ),
        "source_context_root": receipt_fingerprint_schema(),
        "snapshot_state_root": receipt_fingerprint_schema(),
        "snapshot_root": receipt_fingerprint_schema(),
        "parent_history_root": receipt_fingerprint_schema(),
        "parent_history_count": authority_integer_schema(),
        "history_root": receipt_fingerprint_schema(),
        "history_count": {**authority_integer_schema(), "minimum": 1},
        "read_set_root": receipt_fingerprint_schema(),
        "mutation_issuer_ref": {**authority_text_schema(), "maxLength": 4096},
    }
    return properties


def baseline_output_effect_schema() -> dict[str, Any]:
    return {"enum": ["execute", "publish"]}


def baseline_output_action_disposition_schema() -> dict[str, Any]:
    return {"enum": ["authorized", "denied"]}


def authority_integer_schema() -> dict[str, Any]:
    return {"type": "integer", "minimum": 0, "maximum": (2**53) - 1}


def authority_text_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "pattern": r"^(?![\s\S]*\u0000)\S(?:[\s\S]*\S)?$",
    }


def risk_v2_text_schema() -> dict[str, Any]:
    """Approximate the exact 4096 UTF-8-byte runtime bound in JSON Schema."""

    return {**authority_text_schema(), "maxLength": 4096}


def risk_v2_text_array_schema(
    *,
    min_items: int,
    max_items: int,
) -> dict[str, Any]:
    return {
        "type": "array",
        "items": risk_v2_text_schema(),
        "minItems": min_items,
        "maxItems": max_items,
        "uniqueItems": True,
    }


def support_v2_text_schema() -> dict[str, Any]:
    """Approximate the exact 4096 UTF-8-byte runtime bound in JSON Schema."""

    return {**authority_text_schema(), "maxLength": 4096}


def membership_v2_text_schema() -> dict[str, Any]:
    """Approximate the exact 4096 UTF-8-byte runtime bound in JSON Schema."""

    return {**authority_text_schema(), "maxLength": 4096}


def support_v2_text_array_schema(
    *,
    min_items: int,
    max_items: int,
) -> dict[str, Any]:
    return {
        "type": "array",
        "items": support_v2_text_schema(),
        "minItems": min_items,
        "maxItems": max_items,
        "uniqueItems": True,
    }


def authority_stream_ref_schema(kind: str) -> dict[str, Any]:
    return {
        "type": "string",
        "pattern": rf"^authority:{kind}:[0-9a-f]{{64}}$",
    }


def authority_ref_array_schema(
    *,
    min_items: int,
    max_items: int,
) -> dict[str, Any]:
    return {
        "type": "array",
        "items": authority_text_schema(),
        "minItems": min_items,
        "maxItems": max_items,
        "uniqueItems": True,
    }


def authority_root_array_schema(
    *,
    min_items: int,
    max_items: int,
) -> dict[str, Any]:
    return {
        "type": "array",
        "items": receipt_fingerprint_schema(),
        "minItems": min_items,
        "maxItems": max_items,
        "uniqueItems": True,
    }


def optional_authority_root_schema() -> dict[str, Any]:
    return {"oneOf": [{"const": ""}, receipt_fingerprint_schema()]}


def optional_authority_ref_schema(kind: str) -> dict[str, Any]:
    return {"oneOf": [{"const": ""}, authority_stream_ref_schema(kind)]}


def optional_transition_ref_schema(kind: str) -> dict[str, Any]:
    return {
        "oneOf": [
            {"const": ""},
            {"type": "string", "pattern": rf"^transition:{kind}:[0-9a-f]{{64}}$"},
        ]
    }


def support_transition_ref_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "pattern": r"^transition:support-v2:[0-9a-f]{64}$",
    }


def risk_v2_common_lineage_properties() -> dict[str, Any]:
    return {
        **authority_common_lineage_properties(
            stream_ref=authority_stream_ref_schema("risk-v2")
        ),
        "transition_id": {
            "type": "string",
            "pattern": r"^transition:risk-v2:[0-9a-f]{64}$",
        },
        **authority_session_lineage_properties(
            operation="qualify_evidence",
            target_count=1,
        ),
        "target_ref": risk_v2_text_schema(),
        "advance_ref": risk_v2_text_schema(),
        "protocol_ref": risk_v2_text_schema(),
        "manifest_root": receipt_fingerprint_schema(),
        "commit_policy_root": receipt_fingerprint_schema(),
        "risk_policy_root": receipt_fingerprint_schema(),
        "profile": {
            "enum": [
                "pheroos-certified-commit-v1",
                "pheroos-commit-integrity-v1",
                "pheroos-distributed-commit-v1",
                "pheroos-hybrid-commit-v1",
            ]
        },
        "assurance": {
            "enum": ["advisory", "certified", "distributed", "evidence_bound"]
        },
        "revision": {**authority_integer_schema(), "minimum": 1},
        "epoch": authority_integer_schema(),
        "parent_epoch": {
            "oneOf": [
                {"type": "null"},
                authority_integer_schema(),
            ]
        },
        "current_step": authority_integer_schema(),
        "parent_transition_id": authority_text_schema(),
        "parent_snapshot_root": receipt_fingerprint_schema(),
        "parent_head_root": receipt_fingerprint_schema(),
        "snapshot_root": receipt_fingerprint_schema(),
        "assessment_root": receipt_fingerprint_schema(),
        "threshold_root": receipt_fingerprint_schema(),
        "source_context_root": receipt_fingerprint_schema(),
        "read_set_root": receipt_fingerprint_schema(),
    }


def support_v2_common_lineage_properties() -> dict[str, Any]:
    session = authority_session_lineage_properties(
        operation="qualify_evidence",
        target_count=1,
    )
    binding = session["session_binding"]
    binding_properties = binding["properties"]
    for field in ("scope_ref", "run_ref", "request_ref", "grant_ref"):
        binding_properties[field] = support_v2_text_schema()
    binding_properties["operation"] = {
        **support_v2_text_schema(),
        "const": "qualify_evidence",
    }
    for field in ("target_refs", "action_refs"):
        binding_properties[field]["items"] = support_v2_text_schema()
    return {
        **authority_common_lineage_properties(
            stream_ref=authority_stream_ref_schema("support-v2")
        ),
        "transition_id": support_transition_ref_schema(),
        **session,
        "scope_ref": support_v2_text_schema(),
        "run_ref": support_v2_text_schema(),
        "request_ref": support_v2_text_schema(),
        "grant_ref": support_v2_text_schema(),
        "profile": {
            "enum": [
                "pheroos-certified-commit-v1",
                "pheroos-commit-integrity-v1",
                "pheroos-distributed-commit-v1",
                "pheroos-hybrid-commit-v1",
            ]
        },
        "assurance": {
            "enum": ["advisory", "certified", "distributed", "evidence_bound"]
        },
        "manifest_root": receipt_fingerprint_schema(),
        "commit_policy_root": receipt_fingerprint_schema(),
        "authority_policy_root": receipt_fingerprint_schema(),
        "protocol_ref": support_v2_text_schema(),
        "target_ref": support_v2_text_schema(),
        "mutation_issuer_ref": support_v2_text_schema(),
    }


def durable_membership_common_lineage_properties(
    *,
    stream_kind: str,
    operation: str,
    policy_field: str,
) -> dict[str, Any]:
    """Return the exact shared fields for verification and membership state."""

    session = authority_session_lineage_properties(
        operation=operation,
        target_count=1,
    )
    binding_properties = session["session_binding"]["properties"]
    for field in ("scope_ref", "run_ref", "request_ref", "grant_ref"):
        binding_properties[field] = membership_v2_text_schema()
    binding_properties["operation"] = {
        **membership_v2_text_schema(),
        "const": operation,
    }
    for field in ("target_refs", "action_refs"):
        binding_properties[field]["items"] = membership_v2_text_schema()
    return {
        **authority_common_lineage_properties(
            stream_ref=authority_stream_ref_schema(stream_kind)
        ),
        "transition_id": {
            "type": "string",
            "pattern": rf"^transition:{stream_kind}:[0-9a-f]{{64}}$",
        },
        **session,
        "scope_ref": membership_v2_text_schema(),
        "run_ref": membership_v2_text_schema(),
        "request_ref": membership_v2_text_schema(),
        "grant_ref": membership_v2_text_schema(),
        "target_ref": membership_v2_text_schema(),
        "protocol_ref": membership_v2_text_schema(),
        "profile": {
            "enum": [
                "pheroos-certified-commit-v1",
                "pheroos-commit-integrity-v1",
                "pheroos-distributed-commit-v1",
                "pheroos-hybrid-commit-v1",
            ]
        },
        "assurance": {
            "enum": ["advisory", "certified", "distributed", "evidence_bound"]
        },
        "authority_policy_root": receipt_fingerprint_schema(),
        "manifest_root": receipt_fingerprint_schema(),
        "commit_policy_root": receipt_fingerprint_schema(),
        policy_field: receipt_fingerprint_schema(),
        "epoch": authority_integer_schema(),
        "revision": {**authority_integer_schema(), "minimum": 1},
        "parent_revision": authority_integer_schema(),
        "parent_epoch": {"oneOf": [{"type": "null"}, authority_integer_schema()]},
        "parent_transition_id": membership_v2_text_schema(),
        "parent_snapshot_root": receipt_fingerprint_schema(),
        "parent_head_root": receipt_fingerprint_schema(),
        "snapshot_root": receipt_fingerprint_schema(),
        "mutation_issuer_ref": membership_v2_text_schema(),
        "grant_issuer_ref": membership_v2_text_schema(),
        "source_context_root": receipt_fingerprint_schema(),
        "read_set_root": receipt_fingerprint_schema(),
    }


def authority_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type != "issuer_grant_activated":
        return {}
    return {
        "allOf": [
            {
                "if": {
                    "properties": {"profile": {"const": _AUTHORITY_LOCAL_PROFILE}},
                    "required": ["profile"],
                },
                "then": {"properties": {"verification_root": {"type": "null"}}},
                "else": {
                    "properties": {
                        "profile": {"const": _AUTHORITY_AUTHENTICATED_PROFILE},
                        "verification_root": receipt_fingerprint_schema(),
                    }
                },
            }
        ]
    }


def baseline_output_lineage_constraints(event_type: str) -> dict[str, Any]:
    disposition_field = {
        "baseline_action_permission_issued": "permission_disposition",
        "baseline_output_committed": "action_disposition",
    }.get(event_type)
    if disposition_field is None:
        return {}
    return {
        "allOf": [
            {
                "if": {
                    "properties": {"terminal_status": {"const": "blocked"}},
                    "required": ["terminal_status"],
                },
                "then": {"properties": {disposition_field: {"const": "denied"}}},
            }
        ]
    }


def hybrid_replay_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type != "hybrid_replay_advanced":
        return {}
    return {
        "allOf": [
            {
                "if": {
                    "properties": {"revision": {"const": 1}},
                    "required": ["revision"],
                },
                "then": {
                    "properties": {
                        "parent_transition_id": {"type": "null"},
                        "parent_snapshot_root": {"type": "null"},
                    }
                },
                "else": {
                    "properties": {
                        "revision": {"type": "integer", "minimum": 2},
                        "parent_transition_id": {
                            "type": "string",
                            "pattern": (r"^transition:hybrid-replay-v2:[0-9a-f]{64}$"),
                        },
                        "parent_snapshot_root": receipt_fingerprint_schema(),
                    }
                },
            }
        ]
    }


def commit_replay_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type != "commit_replay_advanced":
        return {}
    profile_by_assurance = {
        "advisory": ["pheroos-commit-integrity-v1"],
        "evidence_bound": [
            "pheroos-commit-integrity-v1",
            "pheroos-hybrid-commit-v1",
        ],
        "certified": ["pheroos-certified-commit-v1"],
        "distributed": ["pheroos-distributed-commit-v1"],
    }
    assurance_cases = [
        {
            "if": {
                "properties": {"assurance": {"const": assurance}},
                "required": ["assurance"],
            },
            "then": {"properties": {"profile": {"enum": profiles}}},
        }
        for assurance, profiles in profile_by_assurance.items()
    ]
    return {
        "allOf": [
            {
                "if": {
                    "properties": {"revision": {"const": 1}},
                    "required": ["revision"],
                },
                "then": {"properties": {"parent_transition_id": {"const": "genesis"}}},
                "else": {
                    "properties": {
                        "revision": {"type": "integer", "minimum": 2},
                        "parent_transition_id": {
                            "type": "string",
                            "pattern": (r"^transition:commit-replay-v2:[0-9a-f]{64}$"),
                        },
                    }
                },
            },
            *assurance_cases,
        ]
    }


def risk_v2_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type not in {"risk_state_advanced", "risk_assessed_v2"}:
        return {}
    profile_by_assurance = {
        "advisory": ["pheroos-commit-integrity-v1"],
        "evidence_bound": [
            "pheroos-commit-integrity-v1",
            "pheroos-hybrid-commit-v1",
        ],
        "certified": ["pheroos-certified-commit-v1"],
        "distributed": ["pheroos-distributed-commit-v1"],
    }
    constraints: list[dict[str, Any]] = [
        {
            "if": {
                "properties": {"revision": {"const": 1}},
                "required": ["revision"],
            },
            "then": {
                "properties": {
                    "parent_transition_id": {"const": "genesis"},
                    "parent_epoch": {"type": "null"},
                    "parent_snapshot_root": {
                        "const": (
                            "sha256:c5a27a1c3b2313e09395f6fec7602b17"
                            "e30e58334bc9a33b335a2135c1a55ec2"
                        )
                    },
                }
            },
            "else": {
                "properties": {
                    "revision": {"type": "integer", "minimum": 2},
                    "parent_epoch": authority_integer_schema(),
                    "parent_transition_id": {
                        "type": "string",
                        "pattern": r"^transition:risk-v2:[0-9a-f]{64}$",
                    },
                }
            },
        },
        *[
            {
                "if": {
                    "properties": {"assurance": {"const": assurance}},
                    "required": ["assurance"],
                },
                "then": {"properties": {"profile": {"enum": profiles}}},
            }
            for assurance, profiles in profile_by_assurance.items()
        ],
    ]
    if event_type == "risk_assessed_v2":
        constraints.append(
            {
                "if": {
                    "properties": {"revision": {"const": 1}},
                    "required": ["revision"],
                },
                "then": {
                    "properties": {
                        "previous_assessment_root": {"const": ""},
                        "window_reset_required": {"const": False},
                    }
                },
                "else": {
                    "properties": {
                        "previous_assessment_root": receipt_fingerprint_schema()
                    }
                },
            }
        )
    return {"allOf": constraints}


def membership_authority_lineage_constraints(event_type: str) -> dict[str, Any]:
    configuration = {
        "principal_verification_set_advanced": (
            "principal-verification-v2",
            ("sha256:250b6db081d9b7bd133f06b6c3192bb409c2f97e2bb462d2c0302d81bbda7ec5"),
        ),
        "membership_epoch_committed": (
            "membership-v2",
            ("sha256:442d957d649f827ae3be2c4389d9ca281f25c86355f54fb1efc0895c61f3c797"),
        ),
    }
    selected = configuration.get(event_type)
    if selected is None:
        return {}
    kind, genesis_root = selected
    profile_by_assurance = {
        "advisory": ["pheroos-commit-integrity-v1"],
        "evidence_bound": [
            "pheroos-commit-integrity-v1",
            "pheroos-hybrid-commit-v1",
        ],
        "certified": ["pheroos-certified-commit-v1"],
        "distributed": ["pheroos-distributed-commit-v1"],
    }
    constraints: list[dict[str, Any]] = [
        {
            "if": {
                "properties": {"revision": {"const": 1}},
                "required": ["revision"],
            },
            "then": {
                "properties": {
                    "parent_revision": {"const": 0},
                    "parent_transition_id": {"const": "genesis"},
                    "parent_epoch": {"type": "null"},
                    "parent_snapshot_root": {"const": genesis_root},
                }
            },
            "else": {
                "properties": {
                    "revision": {"type": "integer", "minimum": 2},
                    "parent_revision": {
                        **authority_integer_schema(),
                        "minimum": 1,
                    },
                    "parent_epoch": authority_integer_schema(),
                    "parent_transition_id": {
                        "type": "string",
                        "pattern": rf"^transition:{kind}:[0-9a-f]{{64}}$",
                    },
                }
            },
        },
        *[
            {
                "if": {
                    "properties": {"assurance": {"const": assurance}},
                    "required": ["assurance"],
                },
                "then": {"properties": {"profile": {"enum": profiles}}},
            }
            for assurance, profiles in profile_by_assurance.items()
        ],
    ]
    if event_type == "membership_epoch_committed":
        constraints.extend(
            (
                {
                    "if": {
                        "properties": {"cluster_count": {"const": 0}},
                        "required": ["cluster_count"],
                    },
                    "then": {"properties": {"principal_count": {"const": 0}}},
                },
                {
                    "if": {
                        "properties": {"principal_count": {"const": 0}},
                        "required": ["principal_count"],
                    },
                    "then": {"properties": {"cluster_count": {"const": 0}}},
                },
            )
        )
    return {"allOf": constraints}


def support_v2_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type not in {
        "support_state_advanced",
        "support_lease_issued_v2",
        "support_lease_revoked_v2",
    }:
        return {}
    profile_by_assurance = {
        "advisory": ["pheroos-commit-integrity-v1"],
        "evidence_bound": [
            "pheroos-commit-integrity-v1",
            "pheroos-hybrid-commit-v1",
        ],
        "certified": ["pheroos-certified-commit-v1"],
        "distributed": ["pheroos-distributed-commit-v1"],
    }
    constraints: list[dict[str, Any]] = [
        *[
            {
                "if": {
                    "properties": {"assurance": {"const": assurance}},
                    "required": ["assurance"],
                },
                "then": {"properties": {"profile": {"enum": profiles}}},
            }
            for assurance, profiles in profile_by_assurance.items()
        ]
    ]
    if event_type != "support_state_advanced":
        return {"allOf": constraints}
    constraints.extend(
        (
            {
                "if": {
                    "properties": {"revision": {"const": 1}},
                    "required": ["revision"],
                },
                "then": {
                    "properties": {
                        "mutation_kind": {"const": "initialize"},
                        "parent_revision": {"const": 0},
                        "parent_transition_id": {"const": "genesis"},
                        "parent_snapshot_root": {
                            "const": (
                                "sha256:14ba7b83f873a31cf2a77df89c1a6c060f0b3db69"
                                "c1991b0d11a4630bd7fde3a"
                            )
                        },
                        "parent_history_root": {
                            "const": (
                                "sha256:b59daa9f35cdad62195ecc31ee2ca1f9b3ab0991f73"
                                "a95f171a6b41b4c8d856d"
                            )
                        },
                        "parent_history_count": {"const": 0},
                    }
                },
                "else": {
                    "properties": {
                        "revision": {"type": "integer", "minimum": 2},
                        "mutation_kind": {"not": {"const": "initialize"}},
                        "parent_transition_id": support_transition_ref_schema(),
                    }
                },
            },
            {
                "if": {
                    "properties": {"active_lease_count": {"const": 0}},
                    "required": ["active_lease_count"],
                },
                "then": {
                    "properties": {
                        "lease_set_root": {
                            "const": (
                                "sha256:23c99380d8b87c91dc9c69d963d0089a2b17f2a1db"
                                "0b0cb2bb108f3023c35fb7"
                            )
                        }
                    }
                },
            },
            *_support_mutation_schema_cases(),
        )
    )
    return {"allOf": constraints}


def commit_evidence_v2_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type != "commit_evidence_qualified_v2":
        return {}
    profile_by_assurance = {
        "advisory": ["pheroos-commit-integrity-v1"],
        "evidence_bound": [
            "pheroos-commit-integrity-v1",
            "pheroos-hybrid-commit-v1",
        ],
        "certified": ["pheroos-certified-commit-v1"],
        "distributed": ["pheroos-distributed-commit-v1"],
    }
    return {
        "allOf": [
            *[
                {
                    "if": {
                        "properties": {"assurance": {"const": assurance}},
                        "required": ["assurance"],
                    },
                    "then": {"properties": {"profile": {"enum": profiles}}},
                }
                for assurance, profiles in profile_by_assurance.items()
            ],
            {
                "if": {
                    "properties": {"revision": {"const": 1}},
                    "required": ["revision"],
                },
                "then": {
                    "properties": {
                        "parent_revision": {"const": 0},
                        "parent_epoch": {"type": "null"},
                        "parent_transition_id": {"const": "genesis"},
                        "parent_snapshot_root": {
                            "const": (
                                "sha256:d11df8688ad1077ef5249a5ab7afb387a7b6d920a"
                                "5e5f939574ae2291d29e85d"
                            )
                        },
                        "parent_history_root": {
                            "const": (
                                "sha256:07492eee5e2fcf631da3fb4b851b9898864410c29"
                                "e0a06e913f89fb3d782a838"
                            )
                        },
                        "parent_history_count": {"const": 0},
                        "history_count": {"const": 1},
                    }
                },
                "else": {
                    "properties": {
                        "revision": {"type": "integer", "minimum": 2},
                        "parent_revision": {
                            **authority_integer_schema(),
                            "minimum": 1,
                        },
                        "parent_epoch": authority_integer_schema(),
                        "parent_transition_id": {
                            "type": "string",
                            "pattern": (
                                r"^transition:commit-evidence-v2:[0-9a-f]{64}$"
                            ),
                        },
                        "parent_history_count": {
                            **authority_integer_schema(),
                            "minimum": 1,
                        },
                        "history_count": {
                            **authority_integer_schema(),
                            "minimum": 2,
                        },
                    }
                },
            },
        ]
    }


def commit_decision_v2_lineage_constraints(event_type: str) -> dict[str, Any]:
    mutations_by_event = {
        "commit_decision_initialized_v2": ["initialized"],
        "commit_assessment_evaluated_v2": ["assessed", "window_reset"],
        "commit_window_advanced_v2": ["assessed"],
        "commit_window_reset_v2": ["window_reset"],
        "commit_epoch_restarted_v2": ["epoch_restarted"],
        "commit_window_sealed_v2": ["sealed"],
        "commit_decision_progressed_v2": [
            "assessed",
            "epoch_restarted",
            "heartbeat",
            "initialized",
            "sealed",
            "window_reset",
        ],
        "commit_decision_outcome_committed_v2": [
            "deadline_terminated",
            "finalized",
        ],
    }
    event_mutations = mutations_by_event.get(event_type)
    if event_mutations is None:
        return {}
    mutations_by_command = {
        "initialize": ["initialized"],
        "evaluate": [
            "assessed",
            "deadline_terminated",
            "finalized",
            "heartbeat",
            "window_reset",
        ],
        "seal": ["deadline_terminated", "sealed", "window_reset"],
        "explicit_unseal": ["deadline_terminated", "window_reset"],
        "epoch_restart": [
            "deadline_terminated",
            "epoch_restarted",
            "window_reset",
        ],
    }
    profile_by_assurance = {
        "advisory": ["pheroos-commit-integrity-v1"],
        "evidence_bound": [
            "pheroos-commit-integrity-v1",
            "pheroos-hybrid-commit-v1",
        ],
        "certified": ["pheroos-certified-commit-v1"],
        "distributed": ["pheroos-distributed-commit-v1"],
    }
    constraints: list[dict[str, Any]] = [
        {"properties": {"mutation_kind": {"enum": event_mutations}}},
        {
            "oneOf": [
                {
                    "properties": {
                        "progress_root": receipt_fingerprint_schema(),
                        "outcome_root": {"const": ""},
                    }
                },
                {
                    "properties": {
                        "progress_root": {"const": ""},
                        "outcome_root": receipt_fingerprint_schema(),
                    }
                },
            ]
        },
        *[
            {
                "if": {
                    "properties": {"command": {"const": command}},
                    "required": ["command"],
                },
                "then": {"properties": {"mutation_kind": {"enum": mutations}}},
            }
            for command, mutations in mutations_by_command.items()
        ],
        *[
            {
                "if": {
                    "properties": {"assurance": {"const": assurance}},
                    "required": ["assurance"],
                },
                "then": {"properties": {"profile": {"enum": profiles}}},
            }
            for assurance, profiles in profile_by_assurance.items()
        ],
    ]
    required_root = {
        "commit_assessment_evaluated_v2": "assessment_root",
        "commit_window_sealed_v2": "seal_root",
        "commit_decision_progressed_v2": "progress_root",
        "commit_decision_outcome_committed_v2": "outcome_root",
    }.get(event_type)
    if required_root is not None:
        constraints.append(
            {"properties": {required_root: receipt_fingerprint_schema()}}
        )
    return {"allOf": constraints}


def commit_certificate_v2_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type not in {
        "commit_certificate_conflict_v2",
        "commit_certificate_verified_v2",
    }:
        return {}
    status_properties: dict[str, Any]
    if event_type == "commit_certificate_conflict_v2":
        status_properties = {
            "mutation_kind": {"const": "conflict"},
            "status": {"const": "conflict"},
        }
    else:
        status_properties = {
            "mutation_kind": {"enum": ["semantic_retry", "verified"]},
            "status": {"const": "verified"},
        }
    return {
        "allOf": [
            {"properties": status_properties},
            *[
                {
                    "properties": {
                        "authority_leaves": {
                            "contains": {
                                "type": "object",
                                "properties": {"role": {"const": role}},
                                "required": ["role"],
                            },
                            "minContains": 1,
                            "maxContains": 1,
                        }
                    }
                }
                for role in (
                    "evidence",
                    "membership",
                    "permission",
                    "principal_verification",
                    "replay",
                    "risk",
                    "stop",
                    "support",
                )
            ],
            {
                "if": {
                    "properties": {"assurance": {"const": "certified"}},
                    "required": ["assurance"],
                },
                "then": {
                    "properties": {"profile": {"const": "pheroos-certified-commit-v1"}}
                },
                "else": {
                    "properties": {
                        "assurance": {"const": "distributed"},
                        "profile": {"const": "pheroos-distributed-commit-v1"},
                    }
                },
            },
            {
                "if": {
                    "properties": {"revision": {"const": 1}},
                    "required": ["revision"],
                },
                "then": {
                    "properties": {
                        "parent_revision": {"const": 0},
                        "parent_transition_id": {"const": "genesis"},
                    }
                },
                "else": {
                    "properties": {
                        "revision": {"type": "integer", "minimum": 2},
                        "parent_revision": {
                            **authority_integer_schema(),
                            "minimum": 1,
                        },
                        "parent_transition_id": {
                            "type": "string",
                            "pattern": (
                                r"^transition:commit-certificate-v2:[0-9a-f]{64}$"
                            ),
                        },
                    }
                },
            },
        ]
    }


def distributed_commit_v2_lineage_constraints(event_type: str) -> dict[str, Any]:
    if event_type not in DISTRIBUTED_AUTHORITY_EVENT_TYPES:
        return {}
    event_shapes = {
        "distributed_epoch_advanced_v2": (
            "epoch",
            ["epoch_initialized", "epoch_transitioned"],
            "active",
        ),
        "distributed_proposal_advanced_v2": (
            "proposal",
            ["proposal_recorded", "proposal_semantic_retry"],
            "active",
        ),
        "distributed_witness_advanced_v2": (
            "witness",
            ["witness_recorded", "witness_retry"],
            "active",
        ),
        "distributed_witness_conflict_v2": (
            "witness",
            ["equivocation_frozen"],
            "frozen",
        ),
        "distributed_certificate_advanced_v2": (
            "certificate",
            ["certificate_retry", "certificate_verified"],
            "verified",
        ),
        "distributed_certificate_conflict_v2": (
            "certificate",
            ["certificate_conflict_frozen"],
            "frozen",
        ),
    }
    lane, mutations, status = event_shapes[event_type]
    roles_by_lane = {
        "epoch": [
            "certificate",
            "membership",
            "principal_verification",
            "proposal",
            "witness",
        ],
        "proposal": [
            "central_certificate",
            "decision",
            "epoch",
            "membership",
            "principal_verification",
        ],
        "witness": [
            "central_certificate",
            "decision",
            "epoch",
            "membership",
            "principal_verification",
            "proposal",
        ],
        "certificate": [
            "central_certificate",
            "decision",
            "epoch",
            "membership",
            "principal_verification",
            "proposal",
            "witness",
        ],
    }
    genesis_roots = {
        "epoch": (
            "sha256:0c5c14a140acc445aa8fc6bc43cd2abf726b75ff8f58ed0a5adb147b795b9029",
            "sha256:5da156d4dd06ecb2f74ac5cfea8a5b4595eedfe74d702269b4bd032180e2e6b8",
        ),
        "proposal": (
            "sha256:414f0476c6b3e9f729f63f92132462dc1299fde48f135665563c0d1d9ed6fcd9",
            "sha256:3bc89c78f328abb89632785dcb010d84396136b2340bc1ea7bda163d3c572672",
        ),
        "witness": (
            "sha256:7a162e6c2340b86f1fdd6bb348ede319c5e2ab9f3dbd19ae14c37a462e2343a7",
            "sha256:aed7a2a8e531cffd4ecda89e889cf7dff2829a3d7578eaf10e9d537c79122366",
        ),
        "certificate": (
            "sha256:a36ac3ad9b2530871169055252a130dc71b1fe22e569a3837d512d4ff3e2e1ec",
            "sha256:516c3fc0b27f46546ab21190dec97b80c1e20bc5d7767c35e83b8b88f1bdbe0a",
        ),
    }
    roles = roles_by_lane[lane]
    parent_snapshot_root, parent_history_root = genesis_roots[lane]
    constraints: list[dict[str, Any]] = [
        {
            "properties": {
                "lane": {"const": lane},
                "mutation_kind": {"enum": mutations},
                "status": {"const": status},
                "stream_ref": {
                    "type": "string",
                    "pattern": (rf"^authority:distributed-{lane}-v2:[0-9a-f]{{64}}$"),
                },
                "lane_state_material": _distributed_lane_material_schema(
                    event_type,
                    lane,
                ),
                "dependencies": {
                    "minItems": len(roles),
                    "maxItems": len(roles),
                },
            }
        },
        *[
            {
                "properties": {
                    "dependencies": {
                        "contains": {
                            "type": "object",
                            "properties": {"role": {"const": role}},
                            "required": ["role"],
                        },
                        "minContains": 1,
                        "maxContains": 1,
                    }
                }
            }
            for role in roles
        ],
        *[
            {
                "if": {
                    "properties": {"mutation_kind": {"const": mutation}},
                    "required": ["mutation_kind"],
                },
                "then": {"properties": {"reason_codes": {"const": [mutation]}}},
            }
            for mutation in mutations
        ],
        {
            "if": {
                "properties": {"revision": {"const": 1}},
                "required": ["revision"],
            },
            "then": {
                "properties": {
                    "parent_revision": {"const": 0},
                    "parent_transition_id": {"const": "genesis"},
                    "parent_snapshot_root": {"const": parent_snapshot_root},
                    "parent_history_root": {"const": parent_history_root},
                    "parent_history_count": {"const": 0},
                    "history_count": {"const": 1},
                }
            },
            "else": {
                "properties": {
                    "revision": {**authority_integer_schema(), "minimum": 2},
                    "parent_revision": {
                        **authority_integer_schema(),
                        "minimum": 1,
                    },
                    "parent_transition_id": {
                        "type": "string",
                        "pattern": r"^transition:distributed-v2:[0-9a-f]{64}$",
                    },
                    "parent_history_count": {
                        **authority_integer_schema(),
                        "minimum": 1,
                    },
                    "history_count": {
                        **authority_integer_schema(),
                        "minimum": 2,
                    },
                }
            },
        },
        _distributed_session_action_constraints(lane),
    ]
    if lane == "epoch":
        constraints.append(
            {
                "if": {
                    "properties": {"revision": {"const": 1}},
                    "required": ["revision"],
                },
                "then": {
                    "properties": {"mutation_kind": {"const": "epoch_initialized"}}
                },
                "else": {
                    "properties": {"mutation_kind": {"const": "epoch_transitioned"}}
                },
            }
        )
    return {"allOf": constraints}


def _distributed_lane_material_schema(
    event_type: str,
    lane: str,
) -> dict[str, Any]:
    root = receipt_fingerprint_schema()
    if lane == "epoch":
        return {
            "type": "object",
            "required": ["conflict_history_roots", "transition_certificate_root"],
            "properties": {
                "transition_certificate_root": root,
                "conflict_history_roots": authority_root_array_schema(
                    min_items=0,
                    max_items=8192,
                ),
            },
            "additionalProperties": False,
        }
    if lane == "proposal":
        return {
            "type": "object",
            "required": ["epoch", "proposal_digests"],
            "properties": {
                "epoch": authority_integer_schema(),
                "proposal_digests": authority_root_array_schema(
                    min_items=1,
                    max_items=256,
                ),
            },
            "additionalProperties": False,
        }
    if lane == "witness":
        conflict = event_type == "distributed_witness_conflict_v2"
        return {
            "type": "object",
            "required": ["epoch", "finding_roots", "witness_roots"],
            "properties": {
                "epoch": authority_integer_schema(),
                "witness_roots": authority_root_array_schema(
                    min_items=1,
                    max_items=8192,
                ),
                "finding_roots": authority_root_array_schema(
                    min_items=1 if conflict else 0,
                    max_items=8192 if conflict else 0,
                ),
            },
            "additionalProperties": False,
        }
    conflict = event_type == "distributed_certificate_conflict_v2"
    return {
        "type": "object",
        "required": ["certificate_roots", "conflict_roots", "epoch"],
        "properties": {
            "epoch": authority_integer_schema(),
            "certificate_roots": authority_root_array_schema(
                min_items=1,
                max_items=64,
            ),
            "conflict_roots": authority_root_array_schema(
                min_items=1 if conflict else 0,
                max_items=8192 if conflict else 0,
            ),
        },
        "additionalProperties": False,
    }


def _distributed_session_action_constraints(lane: str) -> dict[str, Any]:
    if lane != "epoch":
        return {
            "properties": {
                "session_binding": {"properties": {"action_refs": {"const": []}}}
            }
        }
    return {
        "if": {
            "properties": {
                "lane_state_material": {
                    "type": "object",
                    "properties": {"conflict_history_roots": {"maxItems": 0}},
                    "required": ["conflict_history_roots"],
                }
            },
            "required": ["lane_state_material"],
        },
        "then": {
            "properties": {
                "session_binding": {
                    "properties": {"action_refs": {"const": ["epoch_transition"]}}
                }
            }
        },
        "else": {
            "properties": {
                "session_binding": {
                    "properties": {
                        "action_refs": {"const": ["epoch_transition", "recovery"]}
                    }
                }
            }
        },
    }


def _support_mutation_schema_cases() -> list[dict[str, Any]]:
    root = receipt_fingerprint_schema()
    membership_stream = authority_stream_ref_schema("membership-v2")
    membership_transition = {
        "type": "string",
        "pattern": r"^transition:membership-v2:[0-9a-f]{64}$",
    }
    cases = {
        "initialize": {
            "issued_lease_root": {"const": ""},
            "revoked_lease_root": {"const": ""},
            "revocation_root": {"const": ""},
            "membership_stream_ref": {"const": ""},
            "membership_transition_id": {"const": ""},
            "membership_snapshot_root": {"const": ""},
            "evicted_lease_roots": {"maxItems": 0},
            "active_lease_count": {"const": 0},
        },
        "issue": {
            "issued_lease_root": root,
            "revoked_lease_root": {"const": ""},
            "revocation_root": {"const": ""},
            "membership_stream_ref": membership_stream,
            "membership_transition_id": membership_transition,
            "membership_snapshot_root": root,
            "active_lease_count": {"type": "integer", "minimum": 1},
        },
        "revoke": {
            "issued_lease_root": {"const": ""},
            "revoked_lease_root": root,
            "revocation_root": root,
            "membership_stream_ref": {"const": ""},
            "membership_transition_id": {"const": ""},
            "membership_snapshot_root": {"const": ""},
        },
        "switch": {
            "issued_lease_root": root,
            "revoked_lease_root": root,
            "revocation_root": root,
            "membership_stream_ref": membership_stream,
            "membership_transition_id": membership_transition,
            "membership_snapshot_root": root,
            "active_lease_count": {"type": "integer", "minimum": 1},
        },
    }
    return [
        {
            "if": {
                "properties": {"mutation_kind": {"const": kind}},
                "required": ["mutation_kind"],
            },
            "then": {"properties": properties},
        }
        for kind, properties in cases.items()
    ]


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
    gates = (
        "committed_candidate",
        "evidence_provenance",
        "stop_resolution",
        "publication_permission",
    )
    return {
        "allOf": [
            {
                "if": {
                    "properties": {"authorized": {"const": True}},
                    "required": ["authorized"],
                },
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
                        "proposed_strength": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "maximum": 10,
                        },
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
    return {
        "type": "object",
        "minProperties": 1,
        "additionalProperties": finite_number(),
    }


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
        "properties": {lifecycle: dict(receipt_map) for lifecycle in lifecycles},
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
