from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.protocol.commit_models import (
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
    CommitAction,
)

from pheroos.governance._schema.common import (
    AUTHORITY_PROFILE,
    CommitWireBinding,
    CommitWireContract,
    _validate_assessment_lineage_semantics,
    _validate_sealed_heartbeat_semantics,
    action_schema,
    authority_integer_schema,
    canonical_text_schema,
    canonical_text_set_schema,
    commit_binding_properties,
    fingerprint_schema,
    governance_authority_schema,
    optional_fingerprint_schema,
    optional_text_schema,
    no_semantic_authority,
    positive_authority_integer_schema,
    profile_agnostic,
    strict_object_schema,
)


def _validate_action_certificate_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    action = payload.get("action")
    if action in {
        CommitAction.PUBLISH.value,
        CommitAction.EXECUTE.value,
    } and not payload.get("certificate_ref"):
        return [
            "$.payload.certificate_ref: publish/execute requires certificate binding"
        ]
    return []


def _validate_progress_semantics(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("terminal") is not False:
        errors.append("$.payload.terminal: progress must be non-terminal")
    if not payload.get("next_required_inputs") and not payload.get("unmet_gates"):
        errors.append("$.payload: progress must identify an input or unmet gate")
    errors.extend(
        _validate_sealed_heartbeat_semantics(
            payload,
            require_continuous=True,
        )
    )
    return errors


def _validate_outcome_semantics(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    kind = payload.get("kind")
    authority_scope = payload.get("authority_scope")
    _validate_outcome_delivery(payload, errors=errors)
    if kind == "evidence_commit":
        _validate_evidence_commit_outcome(payload, errors=errors)
    else:
        _validate_noncommit_outcome(payload, errors=errors)
    _validate_outcome_authority_scope(
        kind=kind,
        authority_scope=authority_scope,
        errors=errors,
    )
    errors.extend(_validate_assessment_lineage_semantics(payload))
    errors.extend(_validate_sealed_heartbeat_semantics(payload))
    return errors


def _validate_outcome_delivery(
    payload: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    if payload.get("terminal") is not True:
        errors.append("$.payload.terminal: outcome must be terminal")
    if payload.get("delivery_eligible") is not True:
        errors.append("$.payload.delivery_eligible: outcome must be deliverable")


def _validate_evidence_commit_outcome(
    payload: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    assurance = str(payload.get("assurance"))
    if assurance == "advisory":
        errors.append("$.payload.assurance: advisory cannot evidence-commit")
    expected_scope = COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE.get(assurance)
    if payload.get("authority_scope") != expected_scope:
        errors.append("$.payload.authority_scope: assurance scope mismatch")
    if (
        payload.get("authoritative_commit") is not True
        or payload.get("epistemically_committed") is not True
    ):
        errors.append("$.payload: evidence commit lacks commit authority")
    if not payload.get("candidate_id") or not payload.get("assessment_ref"):
        errors.append("$.payload: evidence commit lacks candidate or assessment")
    if not payload.get("certificate_ref"):
        errors.append("$.payload.certificate_ref: evidence commit requires proof")
    if not payload.get("sealed_window") or not payload.get("heartbeat_continuous"):
        errors.append("$.payload: evidence commit requires continuous seal authority")


def _validate_noncommit_outcome(
    payload: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    if (
        payload.get("authoritative_commit") is not False
        or payload.get("epistemically_committed") is not False
    ):
        errors.append("$.payload: non-commit outcome claims commit authority")
    if payload.get("execution_eligible") is not False:
        errors.append("$.payload.execution_eligible: non-commit cannot execute")


def _validate_outcome_authority_scope(
    *,
    kind: Any,
    authority_scope: Any,
    errors: list[str],
) -> None:
    if kind == "blocked" and authority_scope != "denial":
        errors.append("$.payload.authority_scope: blocked outcome requires denial")
    elif kind != "evidence_commit" and authority_scope != "none":
        errors.append("$.payload.authority_scope: non-commit outcome requires none")


def principal_attestation_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "attestation_ref": canonical_text_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "method": canonical_text_schema(),
            "nonce": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def principal_verification_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "attestation_fingerprint": fingerprint_schema(),
            "authority": governance_authority_schema(),
            "cluster_id": canonical_text_schema(),
            "expires_at_step": authority_integer_schema(),
            "failure_domain": optional_text_schema(),
            "issued_at_step": authority_integer_schema(),
            "principal_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
            "verified_issuer_id": canonical_text_schema(),
            "verified_method": canonical_text_schema(),
            "verifier_id": canonical_text_schema(),
        }
    )


def stop_verification_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "action": action_schema(),
            "authority": governance_authority_schema(),
            "blocked": {"type": "boolean"},
            "certificate_ref": optional_fingerprint_schema(),
            "decision_ref": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "provenance": canonical_text_schema(),
            "reason": canonical_text_schema(),
            "resolution_fingerprint": fingerprint_schema(),
            "resolution_id": canonical_text_schema(),
            "resolved_stop_root": fingerprint_schema(),
            "trace_event_id": canonical_text_schema(),
            "verifier_id": canonical_text_schema(),
        }
    )


def action_permission_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "action": action_schema(),
            "allowed": {"type": "boolean"},
            "authority": governance_authority_schema(),
            "certificate_ref": optional_fingerprint_schema(),
            "decision_ref": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "permission_id": canonical_text_schema(),
            "policy_ref": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "reason_codes": canonical_text_set_schema(minimum=1),
            "trace_event_id": canonical_text_schema(),
        }
    )


def decision_progress_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "absolute_deadline_step": authority_integer_schema(),
            "absolute_run_deadline_step": authority_integer_schema(),
            "assessment_ref": optional_fingerprint_schema(),
            "candidate_challenge_root": optional_fingerprint_schema(),
            "candidate_evidence_root": optional_fingerprint_schema(),
            "candidate_lease_root": optional_fingerprint_schema(),
            "collective_challenge_root": optional_fingerprint_schema(),
            "collective_evidence_root": optional_fingerprint_schema(),
            "collective_lease_root": optional_fingerprint_schema(),
            "context_ref": optional_fingerprint_schema(),
            "current_step": authority_integer_schema(),
            "heartbeat_continuous": {"type": "boolean"},
            "heartbeat_sequence": authority_integer_schema(),
            "leader_candidate_id": optional_text_schema(),
            "membership_epoch_state_root": optional_fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "membership_snapshot_root": optional_fingerprint_schema(),
            "minimum_stability_steps": positive_authority_integer_schema(),
            "next_required_inputs": canonical_text_set_schema(),
            "permission_root": optional_fingerprint_schema(),
            "phase": {
                "enum": ["search", "deliberate", "quorum_pending", "provisional"]
            },
            "previous_progress_ref": optional_fingerprint_schema(),
            "remaining_epoch_restart_budget": authority_integer_schema(),
            "remaining_reset_budget": authority_integer_schema(),
            "replay_root": fingerprint_schema(),
            "replay_state_ref": fingerprint_schema(),
            "risk_assessment_root": fingerprint_schema(),
            "risk_chain_state_root": optional_fingerprint_schema(),
            "risk_policy_root": optional_fingerprint_schema(),
            "seal_ref": optional_fingerprint_schema(),
            "sealed_at_step": authority_integer_schema(),
            "sealed_window": {"type": "boolean"},
            "stop_resolution_root": optional_fingerprint_schema(),
            "support_replay_root": optional_fingerprint_schema(),
            "support_replay_state_root": optional_fingerprint_schema(),
            "terminal": {"const": False},
            "threshold_root": fingerprint_schema(),
            "unmet_gates": canonical_text_set_schema(),
            "window_count": authority_integer_schema(),
            "window_root": fingerprint_schema(),
            "window_state_ref": fingerprint_schema(),
        }
    )


def decision_outcome_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "absolute_deadline_step": authority_integer_schema(),
            "absolute_run_deadline_step": authority_integer_schema(),
            "assessment_ref": optional_fingerprint_schema(),
            "authoritative_commit": {"type": "boolean"},
            "authority_scope": {
                "enum": [
                    "none",
                    "governance_local",
                    "certified",
                    "distributed",
                    "denial",
                ]
            },
            "candidate_id": optional_text_schema(),
            "candidate_challenge_root": optional_fingerprint_schema(),
            "candidate_evidence_root": optional_fingerprint_schema(),
            "candidate_lease_root": optional_fingerprint_schema(),
            "certificate_ref": optional_fingerprint_schema(),
            "collective_challenge_root": optional_fingerprint_schema(),
            "collective_evidence_root": optional_fingerprint_schema(),
            "collective_lease_root": optional_fingerprint_schema(),
            "context_ref": optional_fingerprint_schema(),
            "current_step": authority_integer_schema(),
            "delivery_eligible": {"const": True},
            "epistemically_committed": {"type": "boolean"},
            "execution_eligible": {"type": "boolean"},
            "heartbeat_continuous": {"type": "boolean"},
            "heartbeat_sequence": authority_integer_schema(),
            "kind": {
                "enum": [
                    "evidence_commit",
                    "safe_fallback",
                    "advisory",
                    "blocked",
                    "invalid",
                    "finality_unavailable",
                    "safety_violation",
                ]
            },
            "membership_epoch_state_root": optional_fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "membership_snapshot_root": optional_fingerprint_schema(),
            "permission_root": optional_fingerprint_schema(),
            "previous_progress_ref": optional_fingerprint_schema(),
            "publication_eligible": {"type": "boolean"},
            "reason_codes": canonical_text_set_schema(minimum=1),
            "replay_root": fingerprint_schema(),
            "replay_state_ref": fingerprint_schema(),
            "risk_assessment_root": fingerprint_schema(),
            "risk_chain_state_root": optional_fingerprint_schema(),
            "risk_policy_root": optional_fingerprint_schema(),
            "seal_ref": optional_fingerprint_schema(),
            "sealed_at_step": authority_integer_schema(),
            "sealed_window": {"type": "boolean"},
            "stop_resolution_root": optional_fingerprint_schema(),
            "support_replay_root": optional_fingerprint_schema(),
            "support_replay_state_root": optional_fingerprint_schema(),
            "terminal": {"const": True},
            "threshold_root": fingerprint_schema(),
            "window_root": fingerprint_schema(),
            "window_state_ref": fingerprint_schema(),
        }
    )


def candidate_claim_binding_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "safe_fallback": {"type": "boolean"},
        }
    )


FOUNDATION_CONTRACTS: tuple[CommitWireContract, ...] = (
    CommitWireContract(
        "pheroos-principal-attestation-v1",
        principal_attestation_payload_schema,
        no_semantic_authority,
        binding=CommitWireBinding.UNBOUND,
        profiles=(AUTHORITY_PROFILE,),
    ),
    CommitWireContract(
        "pheroos-principal-verification-v1",
        principal_verification_payload_schema,
        no_semantic_authority,
    ),
    CommitWireContract(
        "pheroos-stop-resolution-verification-v1",
        stop_verification_payload_schema,
        profile_agnostic(_validate_action_certificate_semantics),
    ),
    CommitWireContract(
        "pheroos-action-permission-v1",
        action_permission_payload_schema,
        profile_agnostic(_validate_action_certificate_semantics),
    ),
    CommitWireContract(
        "pheroos-decision-progress-v1",
        decision_progress_payload_schema,
        profile_agnostic(_validate_progress_semantics),
    ),
    CommitWireContract(
        "pheroos-decision-outcome-v1",
        decision_outcome_payload_schema,
        profile_agnostic(_validate_outcome_semantics),
    ),
)

__all__: tuple[str, ...] = ()
