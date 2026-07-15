from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math
from typing import Any
import unicodedata

from pheroos.protocol.commit_models import (
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
    COMMIT_CANONICAL_VERSION,
    COMMIT_PROFILES_BY_ASSURANCE,
    COMMIT_WIRE_VERSION,
    MAX_AUTHORITY_INTEGER,
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_COMMIT_PROFILES,
    SUPPORTED_TERMINAL_OUTCOMES,
    WEIGHT_SCALE,
    CommitAction,
)
from pheroos.protocol.commit_wire import (
    CommitWireError,
    canonical_commit_payload,
    canonical_commit_set,
    commit_payload_fingerprint,
)
from pheroos.protocol.schema_validation import validate_json_schema
from pheroos.governance.errors import GovernanceError


AUTHORITY_PROFILE = "pheroos-commit-authority-v1"
FINGERPRINT_PATTERN = r"^sha256:[0-9a-f]{64}$"
EVIDENCE_BINDING_VERSION = "pheroos-evidence-binding-v1"
NONCRITICAL_EXTENSION_PATTERN = (
    r"^(?:x-(?![cC][rR][iI][tT][iI][cC][aA][lL](?:[.\-]|$))|"
    r"ext\.(?![cC][rR][iI][tT][iI][cC][aA][lL](?:\.|$))).+"
)

_UNBOUND_PAYLOAD_SCHEMAS = frozenset(
    {
        "pheroos-principal-attestation-v1",
        "pheroos-observation-attestation-v1",
        "pheroos-challenge-attestation-v1",
        "pheroos-challenge-coverage-v1",
        "pheroos-candidate-commit-metrics-v1",
        "pheroos-commit-replay-receipt-v1",
        "pheroos-evidence-summary-v1",
        "pheroos-hybrid-commit-step-v1",
        "pheroos-witness-replay-receipt-v1",
        "pheroos-witness-verification-v1",
    }
)
_PROFILE_ONLY_PAYLOAD_SCHEMAS = frozenset(
    {
        "pheroos-commit-output-authorization-v1",
        "pheroos-support-lease-replay-state-v1",
    }
)


def commit_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/commit.schema.json",
        "title": "PheroOS Commit Wire ABI v1",
        "description": (
            "Strict authority envelopes are selected by schema. Namespaced "
            "non-critical envelope metadata is explicitly non-authoritative; "
            "critical or unnamespaced additions fail closed."
        ),
        "discriminator": {"propertyName": "schema"},
        "oneOf": [
            envelope_schema(
                "pheroos-principal-attestation-v1",
                principal_attestation_payload_schema(),
                profiles=(AUTHORITY_PROFILE,),
            ),
            envelope_schema(
                "pheroos-principal-verification-v1",
                principal_verification_payload_schema(),
            ),
            envelope_schema(
                "pheroos-stop-resolution-verification-v1",
                stop_verification_payload_schema(),
            ),
            envelope_schema(
                "pheroos-action-permission-v1",
                action_permission_payload_schema(),
            ),
            envelope_schema(
                "pheroos-decision-progress-v1",
                decision_progress_payload_schema(),
            ),
            envelope_schema(
                "pheroos-decision-outcome-v1",
                decision_outcome_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-evaluation-context-v1",
                commit_evaluation_context_payload_schema(),
            ),
            envelope_schema(
                "pheroos-candidate-commit-metrics-v1",
                candidate_commit_metrics_payload_schema(),
            ),
            envelope_schema(
                "pheroos-optimal-commit-assessment-v1",
                commit_assessment_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-window-state-v1",
                commit_window_state_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-window-seal-v1",
                commit_window_seal_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-liveness-input-v1",
                commit_liveness_input_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-finality-verification-v1",
                commit_finality_verification_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-replay-state-v1",
                commit_replay_state_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-replay-receipt-v1",
                replay_receipt_payload_schema(),
            ),
            envelope_schema(
                "pheroos-observation-attestation-v1",
                observation_attestation_payload_schema(),
                profiles=(AUTHORITY_PROFILE,),
            ),
            envelope_schema(
                "pheroos-verified-observation-v1",
                verified_observation_payload_schema(),
            ),
            envelope_schema(
                "pheroos-counterevidence-disposition-v1",
                counterevidence_disposition_payload_schema(),
            ),
            envelope_schema(
                "pheroos-challenge-attestation-v1",
                challenge_attestation_payload_schema(),
                profiles=(AUTHORITY_PROFILE,),
            ),
            envelope_schema(
                "pheroos-verified-challenge-v1",
                verified_challenge_payload_schema(),
            ),
            envelope_schema(
                "pheroos-challenge-coverage-v1",
                challenge_coverage_payload_schema(),
            ),
            envelope_schema(
                "pheroos-evidence-binding-authority-v1",
                evidence_binding_payload_schema(),
            ),
            envelope_schema(
                "pheroos-evidence-summary-v1",
                evidence_summary_payload_schema(),
            ),
            envelope_schema(
                "pheroos-eligible-principal-snapshot-v1",
                eligible_principal_snapshot_payload_schema(),
            ),
            envelope_schema(
                "pheroos-eligible-membership-epoch-state-v1",
                eligible_membership_epoch_state_payload_schema(),
            ),
            envelope_schema(
                "pheroos-support-lease-proposal-v1",
                support_lease_proposal_payload_schema(),
            ),
            envelope_schema(
                "pheroos-support-lease-replay-receipt-v1",
                support_lease_replay_receipt_payload_schema(),
            ),
            envelope_schema(
                "pheroos-support-lease-replay-state-v1",
                support_lease_replay_state_payload_schema(),
            ),
            envelope_schema(
                "pheroos-support-lease-v1",
                support_lease_payload_schema(),
            ),
            envelope_schema(
                "pheroos-support-lease-revocation-v1",
                support_lease_revocation_payload_schema(),
            ),
            envelope_schema(
                "pheroos-support-lease-evaluation-v1",
                support_lease_evaluation_payload_schema(),
            ),
            envelope_schema(
                "pheroos-support-equivocation-finding-v1",
                support_equivocation_finding_payload_schema(),
            ),
            envelope_schema(
                "pheroos-risk-assessment-chain-state-v1",
                risk_assessment_chain_state_payload_schema(),
            ),
            envelope_schema(
                "pheroos-risk-assessment-v1",
                risk_assessment_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-threshold-snapshot-v1",
                commit_threshold_snapshot_payload_schema(),
            ),
            envelope_schema(
                "pheroos-hybrid-commit-step-v1",
                hybrid_commit_step_payload_schema(),
            ),
            envelope_schema(
                "pheroos-hybrid-commit-evaluation-v1",
                hybrid_commit_evaluation_payload_schema(),
            ),
            envelope_schema(
                "pheroos-local-commit-receipt-v1",
                local_commit_receipt_payload_schema(),
            ),
            envelope_schema(
                "pheroos-evidence-commit-certificate-v1",
                evidence_commit_certificate_payload_schema(),
            ),
            envelope_schema(
                "pheroos-outcome-certificate-v1",
                outcome_certificate_payload_schema(),
            ),
            envelope_schema(
                "pheroos-commit-output-authorization-v1",
                commit_output_authorization_payload_schema(),
            ),
            envelope_schema(
                "pheroos-portable-membership-snapshot-v1",
                portable_membership_snapshot_payload_schema(),
            ),
            envelope_schema(
                "pheroos-distributed-commit-proposal-v1",
                distributed_commit_proposal_payload_schema(),
            ),
            envelope_schema(
                "pheroos-distributed-commit-value-v1",
                distributed_commit_value_payload_schema(),
            ),
            envelope_schema(
                "pheroos-quorum-witness-v1",
                quorum_witness_payload_schema(),
            ),
            envelope_schema(
                "pheroos-witness-verification-v1",
                witness_verification_payload_schema(),
                profiles=("pheroos-distributed-commit-v1",),
            ),
            envelope_schema(
                "pheroos-witness-replay-receipt-v1",
                witness_replay_receipt_payload_schema(),
                profiles=("pheroos-distributed-commit-v1",),
            ),
            envelope_schema(
                "pheroos-distributed-commit-state-v1",
                distributed_commit_state_payload_schema(),
            ),
            envelope_schema(
                "pheroos-distributed-commit-certificate-v1",
                distributed_commit_certificate_payload_schema(),
            ),
            envelope_schema(
                "pheroos-epoch-transition-certificate-v1",
                epoch_transition_certificate_payload_schema(),
            ),
            envelope_schema(
                "pheroos-distributed-finality-decision-v1",
                distributed_finality_decision_payload_schema(),
            ),
        ],
    }


def validate_commit_wire_record(record: object) -> list[str]:
    errors = validate_json_schema(record, commit_schema())
    if errors:
        return errors
    if not isinstance(record, Mapping):  # pragma: no cover - schema above
        return ["$: expected commit wire object"]
    metadata_errors = _validate_noncritical_envelope_extensions(record)
    if metadata_errors:
        return metadata_errors
    payload = record.get("payload")
    schema_name = record.get("schema")
    profile = record.get("profile")
    version = record.get("version")
    if not isinstance(payload, Mapping):  # pragma: no cover - schema above
        return ["$.payload: expected object"]
    try:
        canonical_commit_payload(
            payload,
            schema=str(schema_name),
            profile=str(profile),
            version=str(version),
        )
    except CommitWireError as exc:
        return [f"$: {exc}"]

    semantic: list[str] = []
    if schema_name not in _UNBOUND_PAYLOAD_SCHEMAS:
        if payload.get("profile") != profile:
            semantic.append("$.payload.profile: envelope profile mismatch")
        if schema_name not in _PROFILE_ONLY_PAYLOAD_SCHEMAS:
            assurance = payload.get("assurance")
            allowed_profiles = COMMIT_PROFILES_BY_ASSURANCE.get(str(assurance))
            if allowed_profiles is None or profile not in allowed_profiles:
                semantic.append("$.payload.assurance: profile/assurance mismatch")

    for field_name in (
        "reason_codes",
        "next_required_inputs",
        "unmet_gates",
        "rationale_codes",
        "required_categories",
        "covered_categories",
        "missing_categories",
        "active_support_clusters",
        "conflicting_candidates",
        "required_challenge_categories",
        "publishable_outcomes",
        "executable_outcomes",
        "substantive_candidate_ids",
        "tied_candidate_ids",
        "assessment_reason_codes",
        "blocked_reason_codes",
        "finality_reason_codes",
        "invalid_reason_codes",
        "safety_violation_reason_codes",
        "last_assessment_reason_codes",
        "issuer_attestation_refs",
    ):
        values = payload.get(field_name)
        if isinstance(values, list):
            _validate_canonical_set(
                values,
                path=f"$.payload.{field_name}",
                errors=semantic,
            )

    for field_name in (
        "rebuttal_observation_fingerprints",
        "result_observation_fingerprints",
        "challenge_fingerprints",
        "positive_observation_fingerprints",
        "counter_observation_fingerprints",
        "disposition_fingerprints",
        "active_counter_observation_fingerprints",
        "resolved_counter_observation_fingerprints",
        "blocking_critical_counter_observation_fingerprints",
        "risk_input_fingerprints",
        "included_lease_fingerprints",
        "excluded_lease_fingerprints",
        "conflicting_lease_fingerprints",
        "blocker_references",
        "equivocation_finding_ids",
        "replay_conflict_references",
    ):
        values = payload.get(field_name)
        if isinstance(values, list):
            _validate_lexical_set(
                values,
                path=f"$.payload.{field_name}",
                errors=semantic,
            )

    if schema_name == "pheroos-decision-progress-v1":
        if payload.get("terminal") is not False:
            semantic.append("$.payload.terminal: progress must be non-terminal")
        if not payload.get("next_required_inputs") and not payload.get("unmet_gates"):
            semantic.append("$.payload: progress must identify an input or unmet gate")
        semantic.extend(
            _validate_sealed_heartbeat_semantics(
                payload,
                require_continuous=True,
            )
        )
    elif schema_name == "pheroos-decision-outcome-v1":
        semantic.extend(_validate_outcome_semantics(payload))
    elif schema_name == "pheroos-commit-evaluation-context-v1":
        semantic.extend(_validate_commit_context_semantics(payload))
    elif schema_name == "pheroos-candidate-commit-metrics-v1":
        semantic.extend(_validate_candidate_metrics_semantics(payload))
    elif schema_name == "pheroos-optimal-commit-assessment-v1":
        semantic.extend(_validate_commit_assessment_semantics(payload, str(profile)))
    elif schema_name == "pheroos-commit-window-state-v1":
        semantic.extend(_validate_commit_window_semantics(payload, str(profile)))
    elif schema_name == "pheroos-commit-window-seal-v1":
        semantic.extend(_validate_commit_window_seal_semantics(payload))
    elif schema_name == "pheroos-commit-liveness-input-v1":
        semantic.extend(_validate_commit_liveness_input_semantics(payload))
    elif schema_name == "pheroos-commit-finality-verification-v1":
        semantic.extend(_validate_commit_finality_verification_semantics(payload))
    elif schema_name == "pheroos-commit-replay-state-v1":
        semantic.extend(_validate_commit_replay_state_semantics(payload, str(profile)))
    elif schema_name in {
        "pheroos-stop-resolution-verification-v1",
        "pheroos-action-permission-v1",
    }:
        action = payload.get("action")
        if action in {CommitAction.PUBLISH.value, CommitAction.EXECUTE.value} and not payload.get(
            "certificate_ref"
        ):
            semantic.append(
                "$.payload.certificate_ref: publish/execute requires certificate binding"
            )
    elif schema_name == "pheroos-observation-attestation-v1":
        semantic.extend(_validate_observation_attestation_semantics(payload))
    elif schema_name == "pheroos-verified-observation-v1":
        semantic.extend(_validate_verified_observation_semantics(payload))
    elif schema_name == "pheroos-counterevidence-disposition-v1":
        semantic.extend(_validate_counterevidence_disposition_semantics(payload))
    elif schema_name == "pheroos-challenge-attestation-v1":
        semantic.extend(_validate_challenge_attestation_semantics(payload))
    elif schema_name == "pheroos-verified-challenge-v1":
        semantic.extend(_validate_verified_challenge_semantics(payload))
    elif schema_name == "pheroos-challenge-coverage-v1":
        semantic.extend(_validate_challenge_coverage_semantics(payload))
    elif schema_name == "pheroos-evidence-binding-authority-v1":
        semantic.extend(_validate_evidence_binding_semantics(payload, str(profile)))
    elif schema_name == "pheroos-evidence-summary-v1":
        semantic.extend(_validate_evidence_summary_semantics(payload))
    elif schema_name == "pheroos-eligible-principal-snapshot-v1":
        semantic.extend(_validate_membership_semantics(payload, str(profile)))
    elif schema_name == "pheroos-eligible-membership-epoch-state-v1":
        semantic.extend(_validate_membership_epoch_semantics(payload, str(profile)))
    elif schema_name == "pheroos-support-lease-replay-receipt-v1":
        semantic.extend(_validate_support_replay_receipt_semantics(payload))
    elif schema_name == "pheroos-support-lease-replay-state-v1":
        semantic.extend(_validate_support_replay_state_semantics(payload, str(profile)))
    elif schema_name == "pheroos-support-lease-v1":
        semantic.extend(_validate_support_lease_semantics(payload, str(profile)))
    elif schema_name == "pheroos-support-lease-evaluation-v1":
        semantic.extend(_validate_support_evaluation_semantics(payload, str(profile)))
    elif schema_name == "pheroos-support-equivocation-finding-v1":
        semantic.extend(_validate_equivocation_semantics(payload, str(profile)))
    elif schema_name == "pheroos-risk-assessment-chain-state-v1":
        semantic.extend(_validate_risk_chain_state_semantics(payload, str(profile)))
    elif schema_name == "pheroos-risk-assessment-v1":
        semantic.extend(_validate_risk_assessment_semantics(payload, str(profile)))
    elif schema_name == "pheroos-commit-threshold-snapshot-v1":
        semantic.extend(_validate_threshold_snapshot_semantics(payload, str(profile)))
    elif schema_name == "pheroos-hybrid-commit-step-v1":
        semantic.extend(_validate_hybrid_commit_step_semantics(payload, str(profile)))
    elif schema_name == "pheroos-hybrid-commit-evaluation-v1":
        semantic.extend(_validate_hybrid_commit_evaluation_semantics(payload))
    elif schema_name == "pheroos-local-commit-receipt-v1":
        semantic.extend(_validate_local_commit_receipt_semantics(payload))
    elif schema_name == "pheroos-evidence-commit-certificate-v1":
        semantic.extend(_validate_evidence_certificate_semantics(payload))
    elif schema_name == "pheroos-outcome-certificate-v1":
        semantic.extend(_validate_outcome_certificate_semantics(payload))
    elif schema_name == "pheroos-commit-output-authorization-v1":
        semantic.extend(_validate_commit_output_authorization_semantics(payload))
    elif schema_name == "pheroos-portable-membership-snapshot-v1":
        semantic.extend(_validate_portable_membership_semantics(payload, str(profile)))
    elif schema_name == "pheroos-distributed-commit-proposal-v1":
        semantic.extend(_validate_distributed_proposal_semantics(payload, str(profile)))
    elif schema_name == "pheroos-distributed-commit-value-v1":
        semantic.extend(_validate_distributed_commit_value_semantics(payload, str(profile)))
    elif schema_name == "pheroos-quorum-witness-v1":
        semantic.extend(_validate_quorum_witness_semantics(payload, str(profile)))
    elif schema_name == "pheroos-witness-verification-v1":
        semantic.extend(_validate_witness_verification_semantics(payload, str(profile)))
    elif schema_name == "pheroos-distributed-commit-state-v1":
        semantic.extend(_validate_distributed_state_semantics(payload, str(profile)))
    elif schema_name == "pheroos-distributed-commit-certificate-v1":
        semantic.extend(_validate_distributed_certificate_semantics(payload, str(profile)))
    elif schema_name == "pheroos-epoch-transition-certificate-v1":
        semantic.extend(_validate_epoch_transition_semantics(payload, str(profile)))
    elif schema_name == "pheroos-distributed-finality-decision-v1":
        semantic.extend(_validate_distributed_finality_semantics(payload))
    return semantic


def _validate_noncritical_envelope_extensions(
    record: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for key, value in record.items():
        if key in {"payload", "profile", "schema", "version"}:
            continue
        _validate_non_authoritative_json_value(
            value,
            path=f"$.{key}",
            errors=errors,
        )
    return errors


def _validate_non_authoritative_json_value(
    value: Any,
    *,
    path: str,
    errors: list[str],
) -> None:
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if abs(value) > MAX_AUTHORITY_INTEGER:
            errors.append(f"{path}: integer exceeds portable Commit bound")
        return
    if type(value) is float:
        if not math.isfinite(value):
            errors.append(f"{path}: non-authoritative metadata must be finite JSON")
        return
    if type(value) is str:
        if value != unicodedata.normalize("NFC", value):
            errors.append(f"{path}: metadata string must use NFC normalization")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_non_authoritative_json_value(
                item,
                path=f"{path}[{index}]",
                errors=errors,
            )
        return
    if type(value) is dict:
        for key, item in value.items():
            if (
                type(key) is not str
                or not key
                or key != key.strip()
                or key != unicodedata.normalize("NFC", key)
            ):
                errors.append(f"{path}: metadata object keys must be canonical strings")
                continue
            _validate_non_authoritative_json_value(
                item,
                path=f"{path}.{key}",
                errors=errors,
            )
        return
    errors.append(f"{path}: metadata contains a non-JSON value")


def _validate_outcome_semantics(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    kind = payload.get("kind")
    assurance = str(payload.get("assurance"))
    authority_scope = payload.get("authority_scope")
    committed = payload.get("authoritative_commit")
    epistemic = payload.get("epistemically_committed")
    if payload.get("terminal") is not True:
        errors.append("$.payload.terminal: outcome must be terminal")
    if payload.get("delivery_eligible") is not True:
        errors.append("$.payload.delivery_eligible: outcome must be deliverable")
    if kind == "evidence_commit":
        if assurance == "advisory":
            errors.append("$.payload.assurance: advisory cannot evidence-commit")
        expected_scope = COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE.get(assurance)
        if authority_scope != expected_scope:
            errors.append("$.payload.authority_scope: assurance scope mismatch")
        if committed is not True or epistemic is not True:
            errors.append("$.payload: evidence commit lacks commit authority")
        if not payload.get("candidate_id") or not payload.get("assessment_ref"):
            errors.append("$.payload: evidence commit lacks candidate or assessment")
        if not payload.get("certificate_ref"):
            errors.append("$.payload.certificate_ref: evidence commit requires proof")
        if not payload.get("sealed_window") or not payload.get(
            "heartbeat_continuous"
        ):
            errors.append("$.payload: evidence commit requires continuous seal authority")
    else:
        if committed is not False or epistemic is not False:
            errors.append("$.payload: non-commit outcome claims commit authority")
        if payload.get("execution_eligible") is not False:
            errors.append("$.payload.execution_eligible: non-commit cannot execute")
    if kind == "blocked" and authority_scope != "denial":
        errors.append("$.payload.authority_scope: blocked outcome requires denial")
    elif kind != "evidence_commit" and authority_scope != "none":
        errors.append("$.payload.authority_scope: non-commit outcome requires none")
    errors.extend(_validate_assessment_lineage_semantics(payload))
    errors.extend(_validate_sealed_heartbeat_semantics(payload))
    return errors


def _validate_sealed_heartbeat_semantics(
    payload: Mapping[str, Any],
    *,
    require_continuous: bool = False,
) -> list[str]:
    errors: list[str] = []
    sealed = payload["sealed_window"]
    seal_ref = payload["seal_ref"]
    sealed_at = payload["sealed_at_step"]
    previous_ref = payload["previous_progress_ref"]
    sequence = payload["heartbeat_sequence"]
    if sealed:
        if not seal_ref:
            errors.append("$.payload.seal_ref: sealed record requires a seal")
        if sealed_at > payload["current_step"]:
            errors.append("$.payload.sealed_at_step: seal is from the future")
    elif seal_ref or sealed_at or previous_ref or sequence:
        errors.append("$.payload: unsealed record carries seal lineage")
    if previous_ref:
        if not sealed or sequence == 0:
            errors.append(
                "$.payload.previous_progress_ref: predecessor requires sealed heartbeat"
            )
    elif sequence != 0:
        errors.append("$.payload.heartbeat_sequence: initial sequence must be zero")
    if require_continuous and not payload["heartbeat_continuous"]:
        errors.append("$.payload.heartbeat_continuous: progress must be continuous")
    return errors


def _validate_commit_context_semantics(payload: Mapping[str, Any]) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    claims = payload["candidate_claims"]
    candidate_ids = [item["candidate_id"] for item in claims]
    if candidate_ids != sorted(candidate_ids):
        errors.append("$.payload.candidate_claims: candidate order is not lexical")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("$.payload.candidate_claims: duplicate candidate binding")
    fallback_id = payload["fallback_candidate_id"]
    fallback = [item for item in claims if item["candidate_id"] == fallback_id]
    if len(fallback) != 1 or fallback[0]["safe_fallback"] is not True:
        errors.append("$.payload.fallback_candidate_id: fallback binding is invalid")
    expected_substantive = list(
        canonical_commit_set(
            tuple(
                candidate_id
                for candidate_id in candidate_ids
                if candidate_id != fallback_id
            )
        )
    )
    if payload["substantive_candidate_ids"] != expected_substantive:
        errors.append(
            "$.payload.substantive_candidate_ids: candidate projection mismatch"
        )
    return errors


_CANDIDATE_READY_GATES = (
    "roots_valid",
    "positive_threshold_satisfied",
    "counter_limit_satisfied",
    "counter_ratio_satisfied",
    "critical_counterevidence_clear",
    "challenge_coverage_satisfied",
    "support_cluster_satisfied",
    "support_ratio_satisfied",
    "source_diversity_satisfied",
    "minimum_assurance_satisfied",
    "margin_satisfied",
    "unique_leader",
    "stop_resolution_satisfied",
    "commit_permission_satisfied",
    "replay_clear",
    "equivocation_clear",
)


def _validate_candidate_metrics_semantics(
    payload: Mapping[str, Any],
    *,
    path: str = "$.payload",
) -> list[str]:
    errors: list[str] = []
    if payload["ready_for_stability"] is not all(
        payload[name] is True for name in _CANDIDATE_READY_GATES
    ):
        errors.append(f"{path}.ready_for_stability: gate conjunction mismatch")
    combined_support = bool(
        payload["support_cluster_satisfied"]
        and payload["support_ratio_satisfied"]
    )
    if combined_support is not (
        payload["active_support_clusters"]
        >= payload["support_threshold_clusters"]
    ):
        errors.append(f"{path}: support threshold gate mismatch")
    for field_name in (
        "missing_challenge_categories",
        "reason_codes",
    ):
        _validate_canonical_set(
            payload[field_name],
            path=f"{path}.{field_name}",
            errors=errors,
        )
    for field_name in (
        "blocker_references",
        "equivocation_finding_ids",
        "replay_conflict_references",
    ):
        _validate_lexical_set(
            payload[field_name],
            path=f"{path}.{field_name}",
            errors=errors,
        )
    return errors


def _collective_metrics_root(
    metrics: list[Mapping[str, Any]],
    *,
    field_name: str,
    item_root_name: str,
    schema: str,
    profile: str,
) -> tuple[str, str]:
    root = commit_payload_fingerprint(
        {
            "candidate_roots": sorted(
                (item["candidate_id"], item[item_root_name])
                for item in metrics
            )
        },
        schema=schema,
        profile=profile,
    )
    return field_name, root


def _validate_commit_assessment_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    metrics = payload["candidate_metrics"]
    ids = [item["candidate_id"] for item in metrics]
    if ids != sorted(ids):
        errors.append("$.payload.candidate_metrics: candidate order is not lexical")
    if len(ids) != len(set(ids)):
        errors.append("$.payload.candidate_metrics: duplicate candidate")
    for index, item in enumerate(metrics):
        errors.extend(
            _validate_candidate_metrics_semantics(
                item,
                path=f"$.payload.candidate_metrics[{index}]",
            )
        )
    for field_name, expected in (
        _collective_metrics_root(
            metrics,
            field_name="collective_evidence_root",
            item_root_name="evidence_root",
            schema="pheroos-collective-evidence-root-v1",
            profile=profile,
        ),
        _collective_metrics_root(
            metrics,
            field_name="collective_challenge_root",
            item_root_name="challenge_root",
            schema="pheroos-collective-challenge-root-v1",
            profile=profile,
        ),
        _collective_metrics_root(
            metrics,
            field_name="collective_lease_root",
            item_root_name="lease_root",
            schema="pheroos-collective-lease-root-v1",
            profile=profile,
        ),
    ):
        if payload[field_name] != expected:
            errors.append(f"$.payload.{field_name}: reconstructable root mismatch")
    scores = {item["candidate_id"]: item["net_evidence"] for item in metrics}
    expected_leader = ""
    expected_ties: list[str] = []
    if scores:
        maximum = max(scores.values())
        maxima = sorted(name for name, score in scores.items() if score == maximum)
        if len(maxima) == 1:
            expected_leader = maxima[0]
        else:
            expected_ties = maxima
        for index, item in enumerate(metrics):
            other_best = max(
                (score for name, score in scores.items() if name != item["candidate_id"]),
                default=0,
            )
            expected_margin = item["net_evidence"] - max(other_best, 0)
            if item["margin"] != expected_margin:
                errors.append(
                    f"$.payload.candidate_metrics[{index}].margin: argmax margin mismatch"
                )
            if item["unique_leader"] is not (
                item["candidate_id"] == expected_leader
            ):
                errors.append(
                    f"$.payload.candidate_metrics[{index}].unique_leader: argmax mismatch"
                )
    if payload["leader_candidate_id"] != expected_leader:
        errors.append("$.payload.leader_candidate_id: unique argmax mismatch")
    if payload["tied_candidate_ids"] != expected_ties:
        errors.append("$.payload.tied_candidate_ids: tie projection mismatch")
    expected_unique = bool(expected_leader)
    if payload["unique_leader"] is not expected_unique:
        errors.append("$.payload.unique_leader: leader projection mismatch")
    leader = next(
        (item for item in metrics if item["candidate_id"] == expected_leader),
        None,
    )
    expected_margin = leader["margin"] if leader is not None else 0
    if payload["leader_margin"] != expected_margin:
        errors.append("$.payload.leader_margin: leader metric mismatch")
    expected_ready = bool(leader and leader["ready_for_stability"])
    if payload["leader_ready_for_stability"] is not expected_ready:
        errors.append("$.payload.leader_ready_for_stability: leader gate mismatch")
    if payload["status"] == "ready" and not (expected_unique and expected_ready):
        errors.append("$.payload.status: ready requires one fully gated leader")
    if payload["status"] == "safety_violation" and not (
        payload["equivocation_finding_ids"]
        or payload["replay_conflict_references"]
    ):
        errors.append("$.payload.status: safety violation lacks concrete finding")
    return errors


_ASSESSMENT_LINEAGE_ROOTS = (
    "risk_chain_state_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "support_replay_state_root",
    "support_replay_root",
    "collective_evidence_root",
    "collective_challenge_root",
    "collective_lease_root",
    "stop_resolution_root",
    "permission_root",
)
_CANDIDATE_LINEAGE_ROOTS = (
    "candidate_evidence_root",
    "candidate_challenge_root",
    "candidate_lease_root",
)


def _validate_assessment_lineage_semantics(
    payload: Mapping[str, Any],
    *,
    path: str = "$.payload",
) -> list[str]:
    errors: list[str] = []
    has_assessment = bool(payload["assessment_ref"])
    if bool(payload["context_ref"]) is not has_assessment:
        errors.append(f"{path}: assessment and context lineage must co-exist")
    assessment_roots = [payload[name] for name in _ASSESSMENT_LINEAGE_ROOTS]
    candidate_roots = [payload[name] for name in _CANDIDATE_LINEAGE_ROOTS]
    if has_assessment:
        for name, value in zip(_ASSESSMENT_LINEAGE_ROOTS, assessment_roots):
            if not value:
                errors.append(f"{path}.{name}: assessment lineage is incomplete")
        if any(candidate_roots) and not all(candidate_roots):
            errors.append(f"{path}: candidate lineage roots must be complete")
    elif any(assessment_roots) or any(candidate_roots):
        errors.append(f"{path}: metadata exists without an assessment")
    return errors


def _validate_commit_window_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    expected_chain_id = commit_payload_fingerprint(
        {
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-commit-window-authority-key-v1",
        profile="pheroos-commit-integrity-v1",
    )
    if payload["chain_id"] != expected_chain_id:
        errors.append("$.payload.chain_id: window authority scope mismatch")
    expected_window_root = commit_payload_fingerprint(
        {
            "epoch": payload["epoch"],
            "ordered_assessment_refs": payload["ordered_assessment_refs"],
            "run_id": payload["run_id"],
        },
        schema="pheroos-commit-window-root-v1",
        profile=profile,
    )
    if payload["window_root"] != expected_window_root:
        errors.append("$.payload.window_root: ordered lineage mismatch")
    if payload["revision"] == 0:
        if payload["previous_state_fingerprint"]:
            errors.append("$.payload.previous_state_fingerprint: initial state has predecessor")
    elif not payload["previous_state_fingerprint"]:
        errors.append("$.payload.previous_state_fingerprint: advanced state lacks predecessor")
    if payload["last_evaluated_step"] < payload["initialized_at_step"]:
        errors.append("$.payload.last_evaluated_step: predates initialization")
    if payload["last_evaluated_step"] >= payload["absolute_deadline_step"]:
        errors.append("$.payload: window survived its deadline")
    if payload["absolute_deadline_step"] > payload["absolute_run_deadline_step"]:
        errors.append("$.payload: deadline exceeds run deadline")
    if payload["absolute_deadline_step"] <= payload["initialized_at_step"]:
        errors.append("$.payload.absolute_deadline_step: deadline must follow initialization")
    has_assessment = bool(payload["last_assessment_ref"])
    window_lineage = {
        "assessment_ref": payload["last_assessment_ref"],
        "context_ref": payload["last_context_ref"],
        **{name: payload[name] for name in _ASSESSMENT_LINEAGE_ROOTS},
        **{name: payload[name] for name in _CANDIDATE_LINEAGE_ROOTS},
    }
    errors.extend(_validate_assessment_lineage_semantics(window_lineage))
    if has_assessment:
        if not payload["last_assessment_status"]:
            errors.append("$.payload.last_assessment_status: assessment status is absent")
        for name in ("assessment_replay_state_ref", "assessment_replay_root"):
            if not payload[name]:
                errors.append(f"$.payload.{name}: assessment replay lineage is absent")
    elif (
        payload["last_assessment_status"]
        or payload["last_assessment_reason_codes"]
        or payload["assessment_replay_state_ref"]
        or payload["assessment_replay_root"]
    ):
        errors.append("$.payload: empty assessment carries assessment metadata")
    references = payload["ordered_assessment_refs"]
    if payload["last_ready"]:
        if not payload["leader_candidate_id"]:
            errors.append("$.payload.leader_candidate_id: ready window lacks leader")
        if payload["window_count"] <= 0 or len(references) != payload["window_count"]:
            errors.append("$.payload.window_count: ready assessment count mismatch")
        if (
            not has_assessment
            or payload["last_assessment_status"] != "ready"
            or not references
            or references[-1] != payload["last_assessment_ref"]
        ):
            errors.append("$.payload: ready window does not end at latest ready assessment")
    elif payload["leader_candidate_id"] or payload["window_count"] != 0 or references:
        errors.append("$.payload: non-ready window must be empty")
    if payload["reset_budget_exhausted"] and payload["last_ready"]:
        errors.append("$.payload: exhausted reset budget retained a ready window")
    return errors


def _validate_commit_window_seal_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    from pheroos.governance.authority import AuthorityLevel
    from pheroos.governance.commit_state import CommitWindowSeal
    from pheroos.protocol.commit_models import CommitAssurance

    values = dict(payload)
    try:
        values["assurance"] = CommitAssurance(values["assurance"])
        values["authority"] = AuthorityLevel(values["authority"])
        CommitWindowSeal(**values)
    except (GovernanceError, TypeError, ValueError):
        return ["$.payload: commit window seal typed lineage is invalid"]
    return []


def _validate_commit_liveness_input_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors = _validate_assessment_lineage_semantics(payload)
    errors.extend(_validate_sealed_heartbeat_semantics(payload))
    has_assessment = bool(payload["assessment_ref"])
    if has_assessment and not payload["assessment_status"]:
        errors.append("$.payload.assessment_status: assessment status is absent")
    if not has_assessment and (
        payload["assessment_status"]
        or payload["leader_candidate_id"]
        or payload["leader_ready_for_stability"]
        or payload["assessment_reason_codes"]
    ):
        errors.append("$.payload: empty assessment carries assessment metadata")
    if payload["leader_ready_for_stability"] and not payload["leader_candidate_id"]:
        errors.append("$.payload.leader_candidate_id: ready leader is absent")
    if payload["finality_status"] == "verified":
        if not payload["certificate_ref"] or not payload["finality_verification_ref"]:
            errors.append("$.payload: verified finality lacks typed verification")
        if not payload["sealed_window"] or not payload["heartbeat_continuous"]:
            errors.append("$.payload: verified finality requires continuous seal")
    elif payload["certificate_ref"] or payload["finality_verification_ref"]:
        errors.append("$.payload: non-verified finality carries certificate authority")
    if not payload["heartbeat_continuous"] and not payload["sealed_window"]:
        errors.append("$.payload: only sealed finality may report heartbeat loss")
    return errors


def _validate_commit_finality_verification_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    expected_kind = {
        "evidence_bound": "local_commit_receipt",
        "certified": "evidence_commit_certificate",
        "distributed": "distributed_commit_certificate",
    }.get(payload["assurance"])
    if payload["certificate_kind"] != expected_kind:
        return [
            "$.payload.certificate_kind: kind does not match assurance"
        ]
    return []


def _validate_hybrid_commit_step_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    commit = payload["commit"]
    if commit["profile"] != profile:
        errors.append("$.payload.commit.profile: envelope profile mismatch")
    allowed_profiles = COMMIT_PROFILES_BY_ASSURANCE.get(commit["assurance"])
    if allowed_profiles is None or profile not in allowed_profiles:
        errors.append("$.payload.commit.assurance: profile/assurance mismatch")
    if commit["commit_truth_root"] != commit["commit_assessment_fingerprint"]:
        errors.append("$.payload.commit.commit_truth_root: assessment binding mismatch")
    if commit["assessment_status"] == "ready" and not (
        commit["unique_leader"]
        and commit["leader_ready_for_stability"]
        and commit["leader_candidate_id"]
    ):
        errors.append("$.payload.commit.assessment_status: ready leader is incomplete")
    if not commit["unique_leader"] and commit["leader_candidate_id"]:
        errors.append("$.payload.commit.leader_candidate_id: non-unique step names leader")
    expected_composition = commit_payload_fingerprint(
        {
            "attention": payload["attention"],
            "binding_profile": payload["binding_profile"],
            "commit": commit,
        },
        schema="pheroos-hybrid-commit-composition-v1",
        profile=profile,
    )
    if payload["composition_root"] != expected_composition:
        errors.append("$.payload.composition_root: reconstructable root mismatch")
    return errors


def _validate_hybrid_commit_evaluation_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    authoritative = payload["authoritative"]
    status = payload["status"]
    terminal = payload["terminal"]
    progress_ref = payload["progress_ref"]
    outcome_ref = payload["outcome_ref"]
    if authoritative:
        for field_name in (
            "assessment_ref",
            "context_ref",
            "window_state_ref",
            "replay_state_ref",
        ):
            if not payload[field_name]:
                errors.append(
                    f"$.payload.{field_name}: authoritative evaluation lacks authority ref"
                )
        if status == "progress":
            if terminal or not progress_ref or outcome_ref:
                errors.append("$.payload: authoritative progress is inconsistent")
            if payload["deliver_authorization_ref"]:
                errors.append(
                    "$.payload.deliver_authorization_ref: progress cannot deliver"
                )
        elif not terminal or progress_ref or not outcome_ref:
            errors.append("$.payload: authoritative terminal outcome is inconsistent")
        elif not payload["deliver_authorization_ref"]:
            errors.append(
                "$.payload.deliver_authorization_ref: terminal evaluation must deliver"
            )
        if not payload["trace_event_ids"]:
            errors.append("$.payload.trace_event_ids: authority trace is empty")
    elif (
        status != "invalid"
        or terminal is not True
        or progress_ref
        or outcome_ref
    ):
        errors.append("$.payload: non-authoritative evaluation must be terminal invalid")
    for index, diagnostic in enumerate(payload["diagnostics"]):
        _validate_canonical_set(
            diagnostic["references"],
            path=f"$.payload.diagnostics[{index}].references",
            errors=errors,
        )
    expected_trace_root = commit_payload_fingerprint(
        {"event_ids": tuple(payload["trace_event_ids"])},
        schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
        profile=str(payload["profile"]),
    )
    if payload["trace_root"] != expected_trace_root:
        errors.append("$.payload.trace_root: chronology root mismatch")
    expected_root = commit_payload_fingerprint(
        {
            key: value
            for key, value in payload.items()
            if key != "evaluation_root"
        },
        schema="pheroos-hybrid-commit-evaluation-v1",
        profile=str(payload["profile"]),
    )
    if payload["evaluation_root"] != expected_root:
        errors.append("$.payload.evaluation_root: reconstructable root mismatch")
    return errors


def _validate_local_commit_receipt_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    from pheroos.governance.authority import AuthorityLevel
    from pheroos.governance.certificate import LocalCommitReceipt
    from pheroos.governance.commit_state import AuthorityScope
    from pheroos.protocol.commit_models import CommitAssurance

    values = dict(payload)
    try:
        values["assurance"] = CommitAssurance(values["assurance"])
        values["authority_scope"] = AuthorityScope(values["authority_scope"])
        values["authority"] = AuthorityLevel(values["authority"])
        LocalCommitReceipt(**values)
    except (GovernanceError, TypeError, ValueError):
        return ["$.payload: local receipt typed lineage is invalid"]
    return []


def _validate_evidence_certificate_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    # The public portable decoder reconstructs both roots and validates every
    # typed leaf without trusting an in-process issuance sentinel.
    from pheroos.governance.certificate import (
        evidence_commit_certificate_from_payload,
    )

    try:
        evidence_commit_certificate_from_payload(payload)
    except (GovernanceError, TypeError, ValueError):
        return ["$.payload: evidence certificate roots or typed lineage are invalid"]
    return []


def _validate_outcome_certificate_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    # OutcomeCertificate has a different discriminator and decoder from an
    # evidence certificate.  Its decoder also enforces non-commit authority
    # semantics and reconstructs its body/envelope roots.
    from pheroos.governance.certificate import outcome_certificate_from_payload

    try:
        outcome_certificate_from_payload(payload)
    except (GovernanceError, TypeError, ValueError):
        return ["$.payload: outcome certificate roots or typed lineage are invalid"]
    return []


def _validate_commit_output_authorization_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    gates = payload["gates"]
    if not gates:
        errors.append("$.payload.gates: at least one authority gate is required")
    elif payload["authorized"] is not all(gates.values()):
        errors.append("$.payload.authorized: gate conjunction mismatch")
    if bool(payload["distributed_state_ref"]) is not bool(
        payload["distributed_conflict_root"]
    ):
        errors.append("$.payload: distributed state/conflict roots must co-exist")
    authority_refs = (
        payload["certificate_ref"],
        payload["policy_ref"],
        payload["threshold_ref"],
        payload["stop_resolution_ref"],
        payload["permission_ref"],
    )
    if payload["action"] == "deliver":
        if any((*authority_refs, payload["distributed_state_ref"])):
            errors.append("$.payload: delivery cannot claim action authority refs")
    elif payload["authorized"] and not all(authority_refs):
        errors.append(
            "$.payload: authorized publish/execute requires every authority ref"
        )
    return errors


def _validate_portable_membership_semantics(
    payload: Mapping[str, Any],
    profile: str,
    *,
    path: str = "$.payload",
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
        path=path,
    )
    clusters = payload["eligible_clusters"]
    cluster_ids = [item["cluster_id"] for item in clusters]
    if cluster_ids != sorted(cluster_ids) or len(cluster_ids) != len(set(cluster_ids)):
        errors.append(f"{path}.eligible_clusters: cluster order/uniqueness mismatch")
    all_principal_ids: list[str] = []
    all_verification_refs: list[str] = []
    for index, cluster in enumerate(clusters):
        principals = cluster["principals"]
        order = [
            (item["principal_id"], item["principal_verification_fingerprint"])
            for item in principals
        ]
        if order != sorted(order):
            errors.append(
                f"{path}.eligible_clusters[{index}].principals: principal order mismatch"
            )
        all_principal_ids.extend(item["principal_id"] for item in principals)
        all_verification_refs.extend(
            item["principal_verification_fingerprint"] for item in principals
        )
    if len(all_principal_ids) != len(set(all_principal_ids)):
        errors.append(f"{path}.eligible_clusters: principal belongs to multiple clusters")
    if len(all_verification_refs) != len(set(all_verification_refs)):
        errors.append(f"{path}.eligible_clusters: verification is reused")
    snapshot_body = dict(payload)
    snapshot_body.pop("snapshot_fingerprint")
    expected_snapshot = commit_payload_fingerprint(
        snapshot_body,
        schema="pheroos-eligible-principal-snapshot-v1",
        profile=profile,
    )
    if payload["snapshot_fingerprint"] != expected_snapshot:
        errors.append(f"{path}.snapshot_fingerprint: reconstructable root mismatch")
    expected_membership = commit_payload_fingerprint(
        {
            "assurance": payload["assurance"],
            "commit_policy_root": payload["commit_policy_root"],
            "eligible_clusters": clusters,
            "epoch": payload["epoch"],
            "manifest_root": payload["manifest_root"],
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=profile,
    )
    if payload["membership_root"] != expected_membership:
        errors.append(f"{path}.membership_root: reconstructable root mismatch")
    return errors


def _validate_distributed_proposal_semantics(
    payload: Mapping[str, Any],
    profile: str,
    *,
    path: str = "$.payload",
) -> list[str]:
    errors: list[str] = []
    value_payload = _distributed_commit_value_from_proposal(payload)
    expected_value = commit_payload_fingerprint(
        value_payload,
        schema="pheroos-distributed-commit-value-v1",
        profile=profile,
    )
    if payload["commit_value_root"] != expected_value:
        errors.append(
            f"{path}.commit_value_root: reconstructable semantic value mismatch"
        )
    body = dict(payload)
    body.pop("proposal_digest")
    expected = commit_payload_fingerprint(
        body,
        schema="pheroos-distributed-commit-proposal-v1",
        profile=profile,
    )
    if payload["proposal_digest"] != expected:
        errors.append(f"{path}.proposal_digest: reconstructable digest mismatch")
    return errors


def _distributed_commit_value_from_proposal(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    excluded = {
        "commit_value_root",
        "local_receipt_ref",
        "portable_certificate_ref",
        "proposal_digest",
        "proposal_id",
        "proposal_version",
        "proposed_at_step",
    }
    return {
        "value_version": "pheroos-distributed-commit-value-v1",
        **{name: value for name, value in payload.items() if name not in excluded},
    }


def _validate_distributed_commit_value_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    if payload["profile"] != profile:
        return ["$.payload.profile: envelope profile mismatch"]
    return []


def _quorum_witness_fingerprint(payload: Mapping[str, Any], *, profile: str) -> str:
    return commit_payload_fingerprint(
        payload,
        schema="pheroos-quorum-witness-v1",
        profile=profile,
    )


def _quorum_witness_signing_root(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> str:
    signing = dict(payload)
    signing.pop("attestation_ref")
    return commit_payload_fingerprint(
        signing,
        schema="pheroos-quorum-witness-signing-v1",
        profile=profile,
    )


def _validate_quorum_witness_semantics(
    payload: Mapping[str, Any],
    profile: str,
    *,
    path: str = "$.payload",
) -> list[str]:
    errors: list[str] = []
    if payload["profile"] != profile:
        errors.append(f"{path}.profile: envelope profile mismatch")
    errors.extend(
        _validate_interval(
            payload,
            start="witnessed_at_step",
            end="expires_at_step",
            path=path,
        )
    )
    return errors


def _witness_verification_fingerprint(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        payload,
        schema="pheroos-witness-verification-v1",
        profile=profile,
    )


def _validate_witness_verification_semantics(
    payload: Mapping[str, Any],
    profile: str,
    *,
    path: str = "$.payload",
) -> list[str]:
    witness = payload["witness"]
    errors = _validate_quorum_witness_semantics(
        witness,
        profile,
        path=f"{path}.witness",
    )
    expected_witness = _quorum_witness_fingerprint(witness, profile=profile)
    if payload["witness_fingerprint"] != expected_witness:
        errors.append(f"{path}.witness_fingerprint: reconstructable root mismatch")
    expected_signing = _quorum_witness_signing_root(witness, profile=profile)
    if payload["witness_signing_root"] != expected_signing:
        errors.append(f"{path}.witness_signing_root: reconstructable root mismatch")
    if payload["expires_at_step"] <= payload["verified_at_step"]:
        errors.append(f"{path}: verification expiry must follow verification")
    if payload["expires_at_step"] > witness["expires_at_step"]:
        errors.append(f"{path}.expires_at_step: exceeds witness expiry")
    return errors


def _witness_receipt_from_verification(
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    witness = verification["witness"]
    return {
        "candidate_id": witness["candidate_id"],
        "commit_value_root": witness["commit_value_root"],
        "epoch": witness["epoch"],
        "nonce": witness["nonce"],
        "principal_cluster_id": witness["principal_cluster_id"],
        "principal_id": witness["principal_id"],
        "proposal_digest": witness["proposal_digest"],
        "target": witness["target"],
        "verification_id": verification["verification_id"],
        "witness_fingerprint": verification["witness_fingerprint"],
        "witness_id": witness["witness_id"],
    }


def _witness_receipt_root(
    verifications: list[Mapping[str, Any]],
    *,
    profile: str,
) -> str:
    fingerprints = sorted(
        commit_payload_fingerprint(
            _witness_receipt_from_verification(item),
            schema="pheroos-witness-replay-receipt-v1",
            profile=profile,
        )
        for item in verifications
    )
    return commit_payload_fingerprint(
        {"receipt_fingerprints": fingerprints},
        schema="pheroos-witness-replay-root-v1",
        profile=profile,
    )


def _quorum_intersection_is_safe(n: int, f: int, q: int) -> bool:
    return bool(n >= 3 * f + 1 and q <= n - f and 2 * q - n > f)


def _validate_distributed_state_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_portable_membership_semantics(
        payload["membership_snapshot"],
        profile,
        path="$.payload.membership_snapshot",
    )
    expected_chain = commit_payload_fingerprint(
        {
            "commit_policy_root": payload["commit_policy_root"],
            "epoch": payload["epoch"],
            "manifest_root": payload["manifest_root"],
            "membership_root": payload["membership_root"],
            "profile": payload["profile"],
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-distributed-state-authority-key-v1",
        profile=profile,
    )
    if payload["chain_id"] != expected_chain:
        errors.append("$.payload.chain_id: distributed authority scope mismatch")
    if payload["revision"] == 0:
        if payload["previous_state_fingerprint"]:
            errors.append("$.payload.previous_state_fingerprint: initial state has predecessor")
    elif not payload["previous_state_fingerprint"]:
        errors.append("$.payload.previous_state_fingerprint: advanced state lacks predecessor")
    if payload["current_step"] < payload["initialized_at_step"]:
        errors.append("$.payload.current_step: predates initialization")
    if not _quorum_intersection_is_safe(
        payload["membership_size"],
        payload["max_byzantine_faults"],
        payload["witness_quorum"],
    ):
        errors.append("$.payload: Byzantine quorum intersection is unsafe")
    if payload["minimum_failure_domain_diversity"] > payload["witness_quorum"]:
        errors.append("$.payload.minimum_failure_domain_diversity: unreachable")
    membership = payload["membership_snapshot"]
    for field_name, expected in (
        ("membership_snapshot_root", membership["snapshot_fingerprint"]),
        ("membership_root", membership["membership_root"]),
    ):
        if payload[field_name] != expected:
            errors.append(f"$.payload.{field_name}: membership lineage mismatch")
    if payload["membership_size"] != len(membership["eligible_clusters"]):
        errors.append("$.payload.membership_size: snapshot cardinality mismatch")
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if payload[name] != membership[name]:
            errors.append(f"$.payload.membership_snapshot.{name}: state binding mismatch")
    verifications = payload["witness_verifications"]
    verification_refs = [
        _witness_verification_fingerprint(item, profile=profile)
        for item in verifications
    ]
    if verification_refs != sorted(verification_refs):
        errors.append("$.payload.witness_verifications: order is not canonical")
    for index, verification in enumerate(verifications):
        errors.extend(
            _validate_witness_verification_semantics(
                verification,
                profile,
                path=f"$.payload.witness_verifications[{index}]",
            )
        )
        witness = verification["witness"]
        for name in ("profile", "assurance", "protocol_id", "run_id", "target", "epoch"):
            if witness[name] != payload[name]:
                errors.append(
                    f"$.payload.witness_verifications[{index}].witness.{name}: state binding mismatch"
                )
        if witness["membership_root"] != payload["membership_root"]:
            errors.append(
                f"$.payload.witness_verifications[{index}].witness.membership_root: state binding mismatch"
            )
    expected_receipt_root = _witness_receipt_root(verifications, profile=profile)
    if payload["witness_receipt_root"] != expected_receipt_root:
        errors.append("$.payload.witness_receipt_root: reconstructable root mismatch")
    finding_clusters = {
        item["principal_cluster_id"] for item in payload["equivocation_findings"]
    }
    by_cluster: dict[str, list[Mapping[str, Any]]] = {}
    for verification in verifications:
        by_cluster.setdefault(
            verification["witness"]["principal_cluster_id"], []
        ).append(verification)
    expected_equivocation_clusters = {
        cluster_id
        for cluster_id, items in by_cluster.items()
        if len({item["witness"]["commit_value_root"] for item in items}) > 1
    }
    if finding_clusters != expected_equivocation_clusters:
        errors.append(
            "$.payload.equivocation_findings: semantic equivocation projection mismatch"
        )
    if set(payload["excluded_cluster_ids"]) != finding_clusters:
        errors.append("$.payload.excluded_cluster_ids: equivocation projection mismatch")
    registration_values = {
        item["commit_value_root"] for item in payload["final_registrations"]
    }
    semantic_conflict = len(registration_values) > 1
    if (
        payload["frozen"] is not bool(payload["conflict_findings"])
        or payload["frozen"] is not semantic_conflict
    ):
        errors.append("$.payload.frozen: conflict projection mismatch")
    if payload["transitioned"] is not bool(payload["epoch_transition_certificate_ref"]):
        errors.append("$.payload.transitioned: epoch proof projection mismatch")
    return errors


def _witness_verification_root(
    verifications: list[Mapping[str, Any]],
    *,
    profile: str,
    commit_value_root: str,
    proposal_digest: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "commit_value_root": commit_value_root,
            "proposal_digest": proposal_digest,
            "witness_verification_fingerprints": sorted(
                _witness_verification_fingerprint(item, profile=profile)
                for item in verifications
            ),
        },
        schema="pheroos-distributed-witness-root-v1",
        profile=profile,
    )


def _validate_distributed_certificate_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_distributed_proposal_semantics(
        payload["proposal"],
        profile,
        path="$.payload.proposal",
    )
    errors.extend(
        _validate_portable_membership_semantics(
            payload["membership_snapshot"],
            profile,
            path="$.payload.membership_snapshot",
        )
    )
    if not _quorum_intersection_is_safe(
        payload["membership_size"],
        payload["max_byzantine_faults"],
        payload["witness_quorum"],
    ):
        errors.append("$.payload: Byzantine quorum intersection is unsafe")
    if payload["minimum_failure_domain_diversity"] > payload["witness_quorum"]:
        errors.append("$.payload.minimum_failure_domain_diversity: unreachable")
    membership = payload["membership_snapshot"]
    if payload["membership_size"] != len(membership["eligible_clusters"]):
        errors.append("$.payload.membership_size: snapshot cardinality mismatch")
    if payload["membership_snapshot_root"] != membership["snapshot_fingerprint"]:
        errors.append("$.payload.membership_snapshot_root: lineage mismatch")
    if payload["membership_root"] != membership["membership_root"]:
        errors.append("$.payload.membership_root: lineage mismatch")
    if not (
        membership["issued_at_step"]
        <= payload["issued_at_step"]
        < membership["expires_at_step"]
    ):
        errors.append("$.payload.issued_at_step: membership is not fresh")
    proposal = payload["proposal"]
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
        "candidate_id",
        "commit_value_root",
        "proposal_digest",
        "membership_snapshot_root",
        "membership_root",
        "portable_certificate_ref",
        "portable_certificate_version",
    ):
        if payload[name] != proposal[name]:
            errors.append(f"$.payload.{name}: proposal binding mismatch")
    verifications = payload["witnesses"]
    refs = [_witness_verification_fingerprint(item, profile=profile) for item in verifications]
    if refs != sorted(refs):
        errors.append("$.payload.witnesses: order is not canonical")
    clusters: list[str] = []
    domains: set[str] = set()
    for index, verification in enumerate(verifications):
        errors.extend(
            _validate_witness_verification_semantics(
                verification,
                profile,
                path=f"$.payload.witnesses[{index}]",
            )
        )
        witness = verification["witness"]
        clusters.append(witness["principal_cluster_id"])
        domains.add(witness["failure_domain"])
        if (
            witness["proposal_digest"] != payload["proposal_digest"]
            or witness["commit_value_root"] != payload["commit_value_root"]
        ):
            errors.append(
                f"$.payload.witnesses[{index}].witness.proposal_digest: certificate binding mismatch"
            )
    if len(clusters) != len(set(clusters)):
        errors.append("$.payload.witnesses: cluster counted twice")
    if set(clusters).intersection(payload["excluded_cluster_ids"]):
        errors.append("$.payload.witnesses: excluded cluster was counted")
    expected_witness_root = _witness_verification_root(
        verifications,
        profile=profile,
        commit_value_root=payload["commit_value_root"],
        proposal_digest=payload["proposal_digest"],
    )
    if payload["witness_root"] != expected_witness_root:
        errors.append("$.payload.witness_root: reconstructable root mismatch")
    meets_finality = bool(
        len(set(clusters)) >= payload["witness_quorum"]
        and len(domains) >= payload["minimum_failure_domain_diversity"]
    )
    if (payload["status"] == "final") is not meets_finality:
        errors.append("$.payload.status: quorum/finality mismatch")
    body = dict(payload)
    body.pop("certificate_body_root")
    body.pop("certificate_root")
    expected_body = commit_payload_fingerprint(
        body,
        schema="pheroos-distributed-commit-certificate-body-v1",
        profile=profile,
    )
    if payload["certificate_body_root"] != expected_body:
        errors.append("$.payload.certificate_body_root: reconstructable root mismatch")
    expected_root = commit_payload_fingerprint(
        {
            "certificate_body_root": expected_body,
            "commit_value_root": payload["commit_value_root"],
            "proposal_digest": payload["proposal_digest"],
            "witness_root": payload["witness_root"],
        },
        schema="pheroos-distributed-commit-certificate-envelope-v1",
        profile=profile,
    )
    if payload["certificate_root"] != expected_root:
        errors.append("$.payload.certificate_root: reconstructable root mismatch")
    return errors


def _validate_epoch_transition_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_portable_membership_semantics(
        payload["new_membership_snapshot"],
        profile,
        path="$.payload.new_membership_snapshot",
    )
    if payload["new_epoch"] <= payload["previous_epoch"]:
        errors.append("$.payload.new_epoch: transition does not advance epoch")
    recovery_fields = (
        payload["declared_recovery_ref"],
        payload["recovery_stop_root"],
        payload["recovery_permission_root"],
    )
    if payload["recovery_required"]:
        if not all(recovery_fields):
            errors.append("$.payload: recovery authority lineage is incomplete")
    elif any(recovery_fields):
        errors.append("$.payload: non-recovery transition carries recovery authority")
    membership = payload["new_membership_snapshot"]
    for name, expected in (
        ("profile", payload["profile"]),
        ("assurance", payload["assurance"]),
        ("manifest_root", payload["manifest_root"]),
        ("commit_policy_root", payload["commit_policy_root"]),
        ("protocol_id", payload["protocol_id"]),
        ("run_id", payload["run_id"]),
        ("target", payload["target"]),
        ("epoch", payload["new_epoch"]),
        ("snapshot_fingerprint", payload["new_membership_snapshot_root"]),
        ("membership_root", payload["new_membership_root"]),
    ):
        if membership[name] != expected:
            errors.append(f"$.payload.new_membership_snapshot.{name}: transition binding mismatch")
    body = dict(payload)
    attestations = body.pop("issuer_attestation_refs")
    body.pop("certificate_body_root")
    body.pop("certificate_root")
    expected_body = commit_payload_fingerprint(
        body,
        schema="pheroos-epoch-transition-certificate-body-v1",
        profile=profile,
    )
    if payload["certificate_body_root"] != expected_body:
        errors.append("$.payload.certificate_body_root: reconstructable root mismatch")
    expected_root = commit_payload_fingerprint(
        {
            "certificate_body_root": expected_body,
            "issuer_attestation_refs": attestations,
        },
        schema="pheroos-epoch-transition-certificate-envelope-v1",
        profile=profile,
    )
    if payload["certificate_root"] != expected_root:
        errors.append("$.payload.certificate_root: reconstructable root mismatch")
    return errors


def _validate_distributed_finality_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    kind = payload["kind"]
    if kind in {"pending", "provisional"} and (
        payload["terminal"]
        or payload["authoritative_commit"]
        or payload["outcome_ref"]
    ):
        errors.append("$.payload: pending/provisional finality cannot be terminal")
    if kind == "pending" and payload["distributed_certificate_ref"]:
        errors.append("$.payload.distributed_certificate_ref: pending finality has proof")
    if kind == "provisional" and not payload["distributed_certificate_ref"]:
        errors.append("$.payload.distributed_certificate_ref: provisional proof is absent")
    if kind == "final":
        if not payload["authoritative_commit"] or not payload["distributed_certificate_ref"]:
            errors.append("$.payload: final distributed decision lacks authority")
    elif payload["authoritative_commit"]:
        errors.append("$.payload.authoritative_commit: non-final decision claims commit")
    if payload["terminal"] is not bool(payload["outcome_ref"]):
        errors.append("$.payload.outcome_ref: terminal/outcome binding mismatch")
    if kind in {"finality_unavailable", "non_commit_terminal"} and not payload["terminal"]:
        errors.append("$.payload.terminal: non-commit finality must be terminal")
    return errors


def _validate_commit_replay_state_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    expected_chain_id = commit_payload_fingerprint(
        {
            "assurance": payload["assurance"],
            "commit_policy_root": payload["commit_policy_root"],
            "manifest_root": payload["manifest_root"],
            "profile": payload["profile"],
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
        },
        schema="pheroos-commit-replay-authority-key-v1",
        profile=profile,
    )
    if payload["chain_id"] != expected_chain_id:
        errors.append("$.payload.chain_id: replay authority scope root mismatch")
    if payload["current_step"] < payload["initialized_at_step"]:
        errors.append("$.payload.current_step: predates replay initialization")

    receipts = payload["receipts"]
    authority_order = sorted(
        receipts,
        key=lambda item: _replay_receipt_fingerprint(
            item,
            profile=AUTHORITY_PROFILE,
        ),
    )
    if receipts != authority_order:
        errors.append("$.payload.receipts: receipt order is not canonical")
    for key_name, key in (
        ("nonce", lambda item: item["nonce"]),
        ("namespace/record_id", lambda item: (item["namespace"], item["record_id"])),
        ("payload_fingerprint", lambda item: item["payload_fingerprint"]),
    ):
        values = [key(item) for item in receipts]
        if len(values) != len(set(values)):
            errors.append(f"$.payload.receipts: {key_name} safety collision")

    expected_root = commit_payload_fingerprint(
        {
            "receipt_fingerprints": [
                _replay_receipt_fingerprint(item, profile=profile)
                for item in receipts
            ]
        },
        schema="pheroos-commit-replay-receipt-root-v1",
        profile=profile,
    )
    if payload["receipt_root"] != expected_root:
        errors.append("$.payload.receipt_root: reconstructable root mismatch")
    if payload["revision"] == 0:
        if payload["previous_state_fingerprint"] or receipts:
            errors.append("$.payload: initial replay state must be empty")
    else:
        if not payload["previous_state_fingerprint"]:
            errors.append(
                "$.payload.previous_state_fingerprint: advanced replay state requires predecessor"
            )
        if not receipts:
            errors.append("$.payload.receipts: advanced replay state requires receipts")
    return errors


def _replay_receipt_fingerprint(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        payload,
        schema="pheroos-commit-replay-receipt-v1",
        profile=profile,
    )


def _validate_canonical_set(
    values: list[Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    try:
        canonical = list(canonical_commit_set(values))
    except CommitWireError as exc:
        errors.append(f"{path}: {exc}")
    else:
        if canonical != values:
            errors.append(f"{path}: set-like array is not canonical")


def _validate_lexical_set(
    values: list[Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    if values != sorted(values):
        errors.append(f"{path}: fingerprint set is not lexically canonical")


def _validate_interval(
    payload: Mapping[str, Any],
    *,
    start: str,
    end: str,
    path: str = "$.payload",
) -> list[str]:
    if payload[end] <= payload[start]:
        return [f"{path}: {end} must be after {start}"]
    return []


def _validate_observation_attestation_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    return _validate_interval(
        payload,
        start="observed_at_step",
        end="expires_at_step",
    )


def _validate_verified_observation_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="verified_at_step",
        end="expires_at_step",
    )
    if payload["verified_at_step"] < payload["observed_at_step"]:
        errors.append(
            "$.payload.verified_at_step: verification precedes observation"
        )
    return errors


def _validate_counterevidence_disposition_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    kind = payload["kind"]
    rebuttals = payload["rebuttal_observation_fingerprints"]
    resolution = payload["resolution_ref"]
    if kind == "rebutted":
        if not rebuttals:
            errors.append(
                "$.payload.rebuttal_observation_fingerprints: rebutted disposition requires evidence"
            )
        if not resolution:
            errors.append(
                "$.payload.resolution_ref: rebutted disposition requires governance resolution"
            )
    elif rebuttals:
        errors.append(
            "$.payload.rebuttal_observation_fingerprints: only rebutted disposition may reference rebuttals"
        )
    if kind == "unresolved":
        if resolution:
            errors.append(
                "$.payload.resolution_ref: unresolved disposition cannot claim resolution"
            )
    elif not resolution:
        errors.append(
            "$.payload.resolution_ref: resolved disposition requires governance resolution"
        )
    return errors


def _validate_challenge_attestation_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="executed_at_step",
        end="expires_at_step",
    )
    errors.extend(_validate_challenge_result_semantics(payload))
    return errors


def _validate_verified_challenge_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="verified_at_step",
        end="expires_at_step",
    )
    if payload["verified_at_step"] < payload["executed_at_step"]:
        errors.append(
            "$.payload.verified_at_step: verification precedes challenge execution"
        )
    errors.extend(_validate_challenge_result_semantics(payload))
    return errors


def _validate_challenge_result_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    result = payload["result"]
    references = payload["result_observation_fingerprints"]
    if result == "counterevidence_found" and not references:
        return [
            "$.payload.result_observation_fingerprints: counterevidence result requires observations"
        ]
    if result != "counterevidence_found" and references:
        return [
            "$.payload.result_observation_fingerprints: non-counterevidence result cannot reference observations"
        ]
    return []


def _validate_challenge_coverage_semantics(
    payload: Mapping[str, Any],
    *,
    path: str = "$.payload",
) -> list[str]:
    errors: list[str] = []
    for field_name in (
        "required_categories",
        "covered_categories",
        "missing_categories",
    ):
        values = payload[field_name]
        if isinstance(values, list):
            _validate_canonical_set(
                values,
                path=f"{path}.{field_name}",
                errors=errors,
            )
    fingerprints = payload["challenge_fingerprints"]
    if isinstance(fingerprints, list):
        _validate_lexical_set(
            fingerprints,
            path=f"{path}.challenge_fingerprints",
            errors=errors,
        )
    required = set(payload["required_categories"])
    covered = set(payload["covered_categories"])
    missing = set(payload["missing_categories"])
    if not covered.issubset(required):
        errors.append(f"{path}.covered_categories: contains undeclared category")
    if missing != required - covered:
        errors.append(f"{path}.missing_categories: coverage difference mismatch")
    if payload["complete"] is not (not missing):
        errors.append(f"{path}.complete: completion flag mismatch")
    if len(payload["challenge_fingerprints"]) < len(covered):
        errors.append(
            f"{path}.challenge_fingerprints: fewer challenges than covered categories"
        )
    return errors


def _validate_evidence_binding_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    positive = payload["positive_observation_fingerprints"]
    counter = payload["counter_observation_fingerprints"]
    if not positive and not counter:
        errors.append("$.payload: evidence binding requires an observation")
    if set(positive).intersection(counter):
        errors.append("$.payload: positive and counter evidence leaves overlap")
    expected = _evidence_binding_roots(payload, profile=profile)
    for field_name, root in expected.items():
        if payload[field_name] != root:
            errors.append(f"$.payload.{field_name}: reconstructable root mismatch")
    return errors


def _evidence_binding_roots(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> dict[str, str]:
    positive_root = commit_payload_fingerprint(
        {
            "observation_fingerprints": payload[
                "positive_observation_fingerprints"
            ]
        },
        schema="pheroos-positive-evidence-leaves-v1",
        profile=profile,
    )
    counter_root = commit_payload_fingerprint(
        {
            "observation_fingerprints": payload[
                "counter_observation_fingerprints"
            ]
        },
        schema="pheroos-counterevidence-leaves-v1",
        profile=profile,
    )
    disposition_root = commit_payload_fingerprint(
        {"disposition_fingerprints": payload["disposition_fingerprints"]},
        schema="pheroos-counterevidence-disposition-leaves-v1",
        profile=profile,
    )
    challenge_root = commit_payload_fingerprint(
        {"challenge_fingerprints": payload["challenge_fingerprints"]},
        schema="pheroos-challenge-leaves-v1",
        profile=profile,
    )
    evidence_root = commit_payload_fingerprint(
        {
            "assurance": payload["assurance"],
            "binding_version": payload["binding_version"],
            "candidate_id": payload["candidate_id"],
            "challenge_root": challenge_root,
            "claim_fingerprint": payload["claim_fingerprint"],
            "commit_policy_root": payload["commit_policy_root"],
            "counter_root": counter_root,
            "disposition_root": disposition_root,
            "epoch": payload["epoch"],
            "evidence_id": payload["evidence_id"],
            "manifest_root": payload["manifest_root"],
            "positive_root": positive_root,
            "profile": payload["profile"],
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-evidence-root-v1",
        profile=profile,
    )
    return {
        "positive_root": positive_root,
        "counter_root": counter_root,
        "disposition_root": disposition_root,
        "challenge_root": challenge_root,
        "evidence_root": evidence_root,
    }


def _validate_evidence_summary_semantics(
    payload: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    coverage = payload["challenge_coverage"]
    errors.extend(
        _validate_challenge_coverage_semantics(
            coverage,
            path="$.payload.challenge_coverage",
        )
    )
    for field_name in (
        "active_counter_observation_fingerprints",
        "resolved_counter_observation_fingerprints",
        "blocking_critical_counter_observation_fingerprints",
    ):
        _validate_lexical_set(
            payload[field_name],
            path=f"$.payload.{field_name}",
            errors=errors,
        )
    positive_sum, positive_refs = _validate_group_contributions(
        payload["positive_groups"],
        path="$.payload.positive_groups",
        errors=errors,
    )
    counter_sum, active_group_refs = _validate_group_contributions(
        payload["counter_groups"],
        path="$.payload.counter_groups",
        errors=errors,
    )
    qualifying_domains, source_refs = _validate_source_domains(
        payload["source_domains"],
        errors=errors,
    )
    active_refs = set(payload["active_counter_observation_fingerprints"])
    resolved_refs = set(payload["resolved_counter_observation_fingerprints"])
    blocking_refs = set(
        payload["blocking_critical_counter_observation_fingerprints"]
    )
    if active_refs != active_group_refs:
        errors.append(
            "$.payload.active_counter_observation_fingerprints: counter group lineage mismatch"
        )
    if active_refs.intersection(resolved_refs):
        errors.append("$.payload: active and resolved counterevidence overlap")
    if positive_refs.intersection(active_refs | resolved_refs):
        errors.append("$.payload: positive and counter observation lineage overlap")
    if not blocking_refs.issubset(active_refs):
        errors.append(
            "$.payload.blocking_critical_counter_observation_fingerprints: blocking evidence is not active"
        )
    if source_refs != positive_refs:
        errors.append("$.payload.source_domains: positive evidence lineage mismatch")
    if payload["positive_evidence"] != positive_sum:
        errors.append("$.payload.positive_evidence: group contribution mismatch")
    if payload["counterevidence"] != counter_sum:
        errors.append("$.payload.counterevidence: group contribution mismatch")
    if payload["net_evidence"] != (
        payload["positive_evidence"] - payload["weighted_counterevidence"]
    ):
        errors.append("$.payload.net_evidence: weighted subtraction mismatch")
    if payload["weighted_counterevidence"] > payload["counterevidence"]:
        errors.append(
            "$.payload.weighted_counterevidence: exceeds declared counterevidence"
        )
    denominator = payload["positive_evidence"] + payload["counterevidence"]
    expected_ratio = (
        WEIGHT_SCALE
        if denominator == 0
        else (payload["counterevidence"] * WEIGHT_SCALE) // denominator
    )
    if payload["counterevidence_ratio_ppm"] != expected_ratio:
        errors.append("$.payload.counterevidence_ratio_ppm: exact ratio mismatch")
    if payload["source_diversity"] != qualifying_domains:
        errors.append("$.payload.source_diversity: qualified domain count mismatch")

    derived = {
        "positive_threshold_satisfied": (
            payload["positive_evidence"] >= payload["minimum_positive_evidence"]
        ),
        "counter_limit_satisfied": (
            payload["counterevidence"] <= payload["maximum_counterevidence"]
        ),
        "counter_ratio_satisfied": (
            payload["counterevidence_ratio_ppm"]
            <= payload["maximum_counterevidence_ratio_ppm"]
        ),
        "source_diversity_satisfied": (
            payload["source_diversity"] >= payload["minimum_source_diversity"]
        ),
        "critical_counterevidence_clear": (
            not payload["blocking_critical_counter_observation_fingerprints"]
        ),
    }
    for field_name, expected in derived.items():
        if payload[field_name] is not expected:
            errors.append(f"$.payload.{field_name}: derived gate mismatch")
    expected_gates = all(derived.values()) and coverage["complete"]
    if payload["evidence_gates_satisfied"] is not expected_gates:
        errors.append("$.payload.evidence_gates_satisfied: gate conjunction mismatch")
    return errors


def _validate_group_contributions(
    values: list[Mapping[str, Any]],
    *,
    path: str,
    errors: list[str],
) -> tuple[int, set[str]]:
    keys = [item["independence_group"] for item in values]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        errors.append(f"{path}: group order is not canonical")
    total = 0
    observation_refs: set[str] = set()
    for index, item in enumerate(values):
        _validate_lexical_set(
            item["observation_fingerprints"],
            path=f"{path}[{index}].observation_fingerprints",
            errors=errors,
        )
        expected = min(item["raw_contribution"], item["group_cap"])
        if item["counted_contribution"] != expected:
            errors.append(f"{path}[{index}].counted_contribution: cap mismatch")
        item_refs = set(item["observation_fingerprints"])
        if observation_refs.intersection(item_refs):
            errors.append(f"{path}[{index}]: observation appears in multiple groups")
        observation_refs.update(item_refs)
        total += item["counted_contribution"]
    return total, observation_refs


def _validate_source_domains(
    values: list[Mapping[str, Any]],
    *,
    errors: list[str],
) -> tuple[int, set[str]]:
    path = "$.payload.source_domains"
    keys = [item["source_domain"] for item in values]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        errors.append(f"{path}: domain order is not canonical")
    qualifying = 0
    observation_refs: set[str] = set()
    for index, item in enumerate(values):
        _validate_lexical_set(
            item["observation_fingerprints"],
            path=f"{path}[{index}].observation_fingerprints",
            errors=errors,
        )
        expected = item["contribution"] >= item["contribution_floor"]
        if item["qualifies"] is not expected:
            errors.append(f"{path}[{index}].qualifies: contribution floor mismatch")
        item_refs = set(item["observation_fingerprints"])
        if observation_refs.intersection(item_refs):
            errors.append(f"{path}[{index}]: observation appears in multiple domains")
        observation_refs.update(item_refs)
        qualifying += int(expected)
    return qualifying, observation_refs


def _validate_membership_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    clusters = payload["eligible_clusters"]
    cluster_ids = [item["cluster_id"] for item in clusters]
    if cluster_ids != sorted(cluster_ids) or len(cluster_ids) != len(
        set(cluster_ids)
    ):
        errors.append("$.payload.eligible_clusters: cluster order is not canonical")
    principal_ids: list[str] = []
    verification_refs: list[str] = []
    for index, cluster in enumerate(clusters):
        principals = cluster["principals"]
        keys = [
            (item["principal_id"], item["principal_verification_fingerprint"])
            for item in principals
        ]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            errors.append(
                f"$.payload.eligible_clusters[{index}].principals: principal order is not canonical"
            )
        principal_ids.extend(item["principal_id"] for item in principals)
        verification_refs.extend(
            item["principal_verification_fingerprint"] for item in principals
        )
    if len(principal_ids) != len(set(principal_ids)):
        errors.append("$.payload.eligible_clusters: principal appears in multiple clusters")
    if len(verification_refs) != len(set(verification_refs)):
        errors.append("$.payload.eligible_clusters: verification is duplicated")
    expected_root = commit_payload_fingerprint(
        {
            "assurance": payload["assurance"],
            "commit_policy_root": payload["commit_policy_root"],
            "eligible_clusters": clusters,
            "epoch": payload["epoch"],
            "manifest_root": payload["manifest_root"],
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=profile,
    )
    if payload["membership_root"] != expected_root:
        errors.append("$.payload.membership_root: reconstructable root mismatch")
    return errors


def _membership_epoch_authority_key(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": payload["assurance"],
            "commit_policy_root": payload["commit_policy_root"],
            "epoch": payload["epoch"],
            "manifest_root": payload["manifest_root"],
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-eligible-membership-epoch-authority-key-v1",
        profile=profile,
    )


def _validate_membership_epoch_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    expected = _membership_epoch_authority_key(payload, profile=profile)
    if payload["authority_key"] != expected:
        errors.append("$.payload.authority_key: membership epoch scope mismatch")
    return errors


def _validate_support_replay_receipt_semantics(
    payload: Mapping[str, Any],
    *,
    path: str = "$.payload",
) -> list[str]:
    return _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
        path=path,
    )


def _support_replay_authority_key(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "issuer_id": payload["issuer_id"],
            "profile": payload["profile"],
            "protocol_id": payload["protocol_id"],
        },
        schema="pheroos-support-lease-replay-authority-key-v1",
        profile=profile,
    )


def _validate_support_replay_state_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    expected_authority = _support_replay_authority_key(payload, profile=profile)
    if payload["authority_key"] != expected_authority:
        errors.append("$.payload.authority_key: support replay authority mismatch")
    if payload["last_issued_at_step"] < payload["initialized_at_step"]:
        errors.append(
            "$.payload.last_issued_at_step: predates replay initialization"
        )
    receipts = payload["receipts"]
    fingerprints = [item["replay_receipt_fingerprint"] for item in receipts]
    if fingerprints != sorted(fingerprints) or len(fingerprints) != len(
        set(fingerprints)
    ):
        errors.append("$.payload.receipts: receipt order is not canonical")
    for index, receipt in enumerate(receipts):
        path = f"$.payload.receipts[{index}]"
        errors.extend(_validate_support_replay_receipt_semantics(receipt, path=path))
        if receipt["profile"] != payload["profile"]:
            errors.append(f"{path}.profile: replay state profile mismatch")
        if receipt["protocol_id"] != payload["protocol_id"]:
            errors.append(f"{path}.protocol_id: replay state protocol mismatch")
        allowed_profiles = COMMIT_PROFILES_BY_ASSURANCE.get(
            str(receipt["assurance"])
        )
        if allowed_profiles is None or receipt["profile"] not in allowed_profiles:
            errors.append(f"{path}.assurance: profile/assurance mismatch")
    for key_name in ("lease_id", "proposal_fingerprint", "nonce"):
        values = [item[key_name] for item in receipts]
        if len(values) != len(set(values)):
            errors.append(f"$.payload.receipts: duplicate {key_name}")
    if payload["revision"] != len(receipts):
        errors.append("$.payload.revision: receipt count mismatch")
    expected_root = commit_payload_fingerprint(
        {"receipts": receipts},
        schema="pheroos-support-lease-replay-root-v1",
        profile=profile,
    )
    if payload["replay_root"] != expected_root:
        errors.append("$.payload.replay_root: reconstructable root mismatch")
    if payload["revision"] == 0:
        if payload["previous_state_fingerprint"]:
            errors.append("$.payload: initial support replay state has predecessor")
        if payload["last_issued_at_step"] != payload["initialized_at_step"]:
            errors.append(
                "$.payload.last_issued_at_step: initial replay step mismatch"
            )
    elif not payload["previous_state_fingerprint"]:
        errors.append(
            "$.payload.previous_state_fingerprint: advanced replay state requires predecessor"
        )
    return errors


def _validate_support_lease_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    expected_authority = _support_replay_authority_key(payload, profile=profile)
    if payload["replay_authority_key"] != expected_authority:
        errors.append("$.payload.replay_authority_key: authority scope mismatch")
    request_payload = {
        key: payload[key]
        for key in (
            "assurance",
            "authority",
            "candidate_id",
            "claim_fingerprint",
            "commit_policy_root",
            "epoch",
            "expires_at_step",
            "issuance_provenance",
            "issuance_trace_event_id",
            "issued_at_step",
            "issuer_id",
            "lease_id",
            "manifest_root",
            "membership_epoch_state_fingerprint",
            "membership_root",
            "nonce",
            "positive_observation_fingerprints",
            "principal_cluster_id",
            "principal_id",
            "principal_verification_fingerprint",
            "prior_lease_fingerprint",
            "profile",
            "proposal_fingerprint",
            "proposal_provenance",
            "proposal_trace_event_id",
            "protocol_id",
            "replay_authority_key",
            "run_id",
            "target",
        )
    }
    expected_receipt = commit_payload_fingerprint(
        request_payload,
        schema="pheroos-support-lease-replay-receipt-v1",
        profile=profile,
    )
    if payload["replay_receipt_fingerprint"] != expected_receipt:
        errors.append(
            "$.payload.replay_receipt_fingerprint: lease request lineage mismatch"
        )
    return errors


def _validate_equivocation_semantics(
    payload: Mapping[str, Any],
    profile: str,
    *,
    path: str = "$.payload",
) -> list[str]:
    errors: list[str] = []
    _validate_canonical_set(
        payload["conflicting_candidates"],
        path=f"{path}.conflicting_candidates",
        errors=errors,
    )
    _validate_lexical_set(
        payload["conflicting_lease_fingerprints"],
        path=f"{path}.conflicting_lease_fingerprints",
        errors=errors,
    )
    expected = commit_payload_fingerprint(
        {
            "assurance": payload["assurance"],
            "commit_policy_root": payload["commit_policy_root"],
            "conflicting_candidates": payload["conflicting_candidates"],
            "conflicting_lease_fingerprints": payload[
                "conflicting_lease_fingerprints"
            ],
            "epoch": payload["epoch"],
            "first_overlap_step": payload["first_overlap_step"],
            "manifest_root": payload["manifest_root"],
            "principal_cluster_id": payload["principal_cluster_id"],
            "protocol_id": payload["protocol_id"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-support-equivocation-finding-v1",
        profile=profile,
    )
    if payload["finding_id"] != expected:
        errors.append(f"{path}.finding_id: deterministic finding mismatch")
    return errors


def _validate_support_evaluation_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    findings = payload["equivocation_findings"]
    cluster_ids = [item["principal_cluster_id"] for item in findings]
    if cluster_ids != sorted(cluster_ids) or len(cluster_ids) != len(
        set(cluster_ids)
    ):
        errors.append("$.payload.equivocation_findings: order is not canonical")
    conflict_refs: set[str] = set()
    for index, finding in enumerate(findings):
        path = f"$.payload.equivocation_findings[{index}]"
        errors.extend(
            _validate_equivocation_semantics(
                finding,
                profile,
                path=path,
            )
        )
        for field_name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
            "target",
            "epoch",
        ):
            if finding[field_name] != payload[field_name]:
                errors.append(f"{path}.{field_name}: evaluation scope mismatch")
        conflict_refs.update(finding["conflicting_lease_fingerprints"])

    active_count = payload["active_support_cluster_count"]
    eligible_count = payload["eligible_cluster_count"]
    if active_count != len(payload["active_support_clusters"]):
        errors.append("$.payload.active_support_cluster_count: cluster count mismatch")
    if active_count > eligible_count:
        errors.append("$.payload.active_support_cluster_count: exceeds membership")
    expected_ratio = (active_count * WEIGHT_SCALE) // eligible_count
    if payload["support_ratio_ppm"] != expected_ratio:
        errors.append("$.payload.support_ratio_ppm: exact ratio mismatch")
    expected_met = active_count >= payload["policy_support_threshold_clusters"]
    if payload["policy_support_met"] is not expected_met:
        errors.append("$.payload.policy_support_met: threshold result mismatch")
    included = set(payload["included_lease_fingerprints"])
    excluded = set(payload["excluded_lease_fingerprints"])
    if included.intersection(excluded):
        errors.append("$.payload: included and excluded lease sets overlap")
    if not conflict_refs.issubset(excluded):
        errors.append("$.payload.excluded_lease_fingerprints: conflicts not excluded")
    if set(cluster_ids).intersection(payload["active_support_clusters"]):
        errors.append("$.payload.active_support_clusters: equivocated cluster is active")

    expected_root = commit_payload_fingerprint(
        {
            "candidate_id": payload["candidate_id"],
            "claim_fingerprint": payload["claim_fingerprint"],
            "commit_policy_root": payload["commit_policy_root"],
            "current_step": payload["current_step"],
            "epoch": payload["epoch"],
            "equivocation_finding_ids": [
                item["finding_id"] for item in findings
            ],
            "excluded_lease_fingerprints": payload[
                "excluded_lease_fingerprints"
            ],
            "included_lease_fingerprints": payload[
                "included_lease_fingerprints"
            ],
            "membership_root": payload["membership_root"],
            "membership_epoch_state_fingerprint": payload[
                "membership_epoch_state_fingerprint"
            ],
            "run_id": payload["run_id"],
            "support_replay_scope_root": payload["support_replay_scope_root"],
            "target": payload["target"],
        },
        schema="pheroos-support-lease-evaluation-root-v1",
        profile=profile,
    )
    if payload["lease_root"] != expected_root:
        errors.append("$.payload.lease_root: reconstructable root mismatch")
    return errors


def _risk_chain_authority_key(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": payload["assurance"],
            "commit_policy_root": payload["commit_policy_root"],
            "epoch": payload["epoch"],
            "manifest_root": payload["manifest_root"],
            "profile": payload["profile"],
            "protocol_id": payload["protocol_id"],
            "risk_policy_root": payload["risk_policy_root"],
            "run_id": payload["run_id"],
            "target": payload["target"],
        },
        schema="pheroos-risk-assessment-chain-authority-key-v1",
        profile=profile,
    )


def _validate_risk_chain_state_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="initialized_at_step",
        end="expires_at_step",
    )
    if not (
        payload["initialized_at_step"]
        <= payload["last_issued_at_step"]
        < payload["expires_at_step"]
    ):
        errors.append(
            "$.payload.last_issued_at_step: issuance step is outside chain interval"
        )
    expected_chain_id = _risk_chain_authority_key(payload, profile=profile)
    if payload["chain_id"] != expected_chain_id:
        errors.append("$.payload.chain_id: authority scope root mismatch")
    revision = payload["revision"]
    if revision == 0:
        if (
            payload["latest_assessment_fingerprint"]
            or payload["latest_risk_band"]
            or payload["previous_state_fingerprint"]
        ):
            errors.append("$.payload: empty risk chain has a forged head")
        if payload["last_issued_at_step"] != payload["initialized_at_step"]:
            errors.append(
                "$.payload.last_issued_at_step: empty chain must remain at initialization"
            )
    elif (
        not payload["latest_assessment_fingerprint"]
        or not payload["latest_risk_band"]
        or not payload["previous_state_fingerprint"]
    ):
        errors.append("$.payload: non-empty risk chain is missing head lineage")
    return errors


def _validate_risk_assessment_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    expected_chain_id = _risk_chain_authority_key(payload, profile=profile)
    if payload["risk_chain_id"] != expected_chain_id:
        errors.append("$.payload.risk_chain_id: authority scope root mismatch")
    revision = payload["risk_chain_revision"]
    predecessor = payload["previous_assessment_fingerprint"]
    if revision == 1 and predecessor:
        errors.append(
            "$.payload.previous_assessment_fingerprint: initial assessment cannot name a predecessor"
        )
    if revision > 1 and not predecessor:
        errors.append(
            "$.payload.previous_assessment_fingerprint: reassessment requires predecessor"
        )
    if (
        not predecessor
        and payload["window_reset_required"]
    ):
        errors.append(
            "$.payload.window_reset_required: initial assessment cannot require reset"
        )
    return errors


def _validate_threshold_snapshot_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors = _validate_interval(
        payload,
        start="issued_at_step",
        end="expires_at_step",
    )
    expected_chain_id = _risk_chain_authority_key(payload, profile=profile)
    if payload["risk_chain_id"] != expected_chain_id:
        errors.append("$.payload.risk_chain_id: authority scope root mismatch")
    return errors


def envelope_schema(
    schema_name: str,
    payload_schema: dict[str, Any],
    *,
    profiles: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    schema = strict_object_schema(
        {
            "schema": {"const": schema_name},
            "profile": {"enum": sorted(profiles or SUPPORTED_COMMIT_PROFILES)},
            "version": {"const": COMMIT_WIRE_VERSION},
            "payload": payload_schema,
        },
        required=("schema", "profile", "version", "payload"),
    )
    # Extensions live beside, never inside, the authority payload.  The
    # canonical Commit fingerprint API projects only the four required fields,
    # so accepted metadata cannot silently acquire authority.  Critical
    # namespaces deliberately do not match and are rejected by
    # additionalProperties=false.
    schema["patternProperties"] = {NONCRITICAL_EXTENSION_PATTERN: {}}
    return schema


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
                "enum": ["none", "governance_local", "certified", "distributed", "denial"]
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


def commit_evaluation_context_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "candidate_claims": {
                "type": "array",
                "items": candidate_claim_binding_schema(),
                "minItems": 1,
                "uniqueItems": True,
            },
            "context_id": canonical_text_schema(),
            "expires_at_step": authority_integer_schema(),
            "fallback_candidate_id": canonical_text_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "membership_epoch_state_fingerprint": fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "membership_snapshot_fingerprint": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "replay_receipt_root": fingerprint_schema(),
            "replay_state_fingerprint": fingerprint_schema(),
            "risk_assessment_fingerprint": fingerprint_schema(),
            "risk_chain_state_fingerprint": fingerprint_schema(),
            "risk_policy_root": fingerprint_schema(),
            "substantive_candidate_ids": canonical_text_set_schema(),
            "support_replay_root": fingerprint_schema(),
            "support_replay_state_fingerprint": fingerprint_schema(),
            "threshold_fingerprint": fingerprint_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def candidate_commit_metrics_payload_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "candidate_id": canonical_text_schema(),
        "claim_fingerprint": fingerprint_schema(),
        "evidence_binding_fingerprint": fingerprint_schema(),
        "evidence_summary_fingerprint": fingerprint_schema(),
        "positive_root": fingerprint_schema(),
        "counter_root": fingerprint_schema(),
        "disposition_root": fingerprint_schema(),
        "evidence_root": fingerprint_schema(),
        "challenge_root": fingerprint_schema(),
        "challenge_coverage_fingerprint": fingerprint_schema(),
        "lease_root": fingerprint_schema(),
        "support_replay_scope_root": fingerprint_schema(),
        "positive_evidence": authority_integer_schema(),
        "counterevidence": authority_integer_schema(),
        "weighted_counterevidence": authority_integer_schema(),
        "net_evidence": signed_authority_integer_schema(),
        "counterevidence_ratio_ppm": scaled_integer_schema(),
        "active_support_clusters": authority_integer_schema(),
        "eligible_support_clusters": authority_integer_schema(),
        "support_threshold_clusters": authority_integer_schema(),
        "support_ratio_ppm": scaled_integer_schema(),
        "source_diversity": authority_integer_schema(),
        "margin": signed_authority_integer_schema(),
        "missing_challenge_categories": canonical_text_set_schema(),
        "blocker_references": fingerprint_set_schema(),
        "equivocation_finding_ids": fingerprint_set_schema(),
        "replay_conflict_references": fingerprint_set_schema(),
        "reason_codes": canonical_text_set_schema(),
    }
    for name in (
        "roots_valid",
        "positive_threshold_satisfied",
        "counter_limit_satisfied",
        "counter_ratio_satisfied",
        "critical_counterevidence_clear",
        "challenge_coverage_satisfied",
        "support_cluster_satisfied",
        "support_ratio_satisfied",
        "source_diversity_satisfied",
        "minimum_assurance_satisfied",
        "margin_satisfied",
        "unique_leader",
        "stop_resolution_satisfied",
        "commit_permission_satisfied",
        "replay_clear",
        "equivocation_clear",
        "ready_for_stability",
    ):
        properties[name] = {"type": "boolean"}
    return strict_object_schema(properties)


def commit_assessment_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "assessment_id": canonical_text_schema(),
            "authority": governance_authority_schema(),
            "blocker_references": fingerprint_set_schema(),
            "candidate_metrics": {
                "type": "array",
                "items": candidate_commit_metrics_payload_schema(),
                "uniqueItems": True,
            },
            "collective_challenge_root": fingerprint_schema(),
            "collective_evidence_root": fingerprint_schema(),
            "collective_lease_root": fingerprint_schema(),
            "context_fingerprint": fingerprint_schema(),
            "equivocation_finding_ids": fingerprint_set_schema(),
            "evaluated_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "leader_candidate_id": optional_text_schema(),
            "leader_margin": signed_authority_integer_schema(),
            "leader_ready_for_stability": {"type": "boolean"},
            "membership_epoch_state_fingerprint": fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "membership_snapshot_fingerprint": fingerprint_schema(),
            "permission_fingerprint": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "reason_codes": canonical_text_set_schema(),
            "replay_conflict_references": fingerprint_set_schema(),
            "replay_receipt_root": fingerprint_schema(),
            "replay_state_fingerprint": fingerprint_schema(),
            "risk_assessment_fingerprint": fingerprint_schema(),
            "risk_chain_state_fingerprint": fingerprint_schema(),
            "risk_policy_root": fingerprint_schema(),
            "status": {"enum": ["not_ready", "ready", "safety_violation"]},
            "stop_resolution_fingerprint": fingerprint_schema(),
            "support_replay_root": fingerprint_schema(),
            "support_replay_state_fingerprint": fingerprint_schema(),
            "threshold_fingerprint": fingerprint_schema(),
            "tied_candidate_ids": canonical_text_set_schema(),
            "trace_event_id": canonical_text_schema(),
            "unique_leader": {"type": "boolean"},
        }
    )


def commit_window_state_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "absolute_deadline_step": authority_integer_schema(),
            "absolute_run_deadline_step": authority_integer_schema(),
            "assessment_replay_root": optional_fingerprint_schema(),
            "assessment_replay_state_ref": optional_fingerprint_schema(),
            "authority": governance_authority_schema(),
            "candidate_challenge_root": optional_fingerprint_schema(),
            "candidate_evidence_root": optional_fingerprint_schema(),
            "candidate_lease_root": optional_fingerprint_schema(),
            "chain_id": fingerprint_schema(),
            "collective_challenge_root": optional_fingerprint_schema(),
            "collective_evidence_root": optional_fingerprint_schema(),
            "collective_lease_root": optional_fingerprint_schema(),
            "initialized_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "last_assessment_reason_codes": canonical_text_set_schema(),
            "last_assessment_ref": optional_fingerprint_schema(),
            "last_assessment_status": optional_enum_schema(
                ("not_ready", "ready", "safety_violation")
            ),
            "last_context_ref": optional_fingerprint_schema(),
            "last_evaluated_step": authority_integer_schema(),
            "last_ready": {"type": "boolean"},
            "leader_candidate_id": optional_text_schema(),
            "membership_root": fingerprint_schema(),
            "membership_epoch_state_root": optional_fingerprint_schema(),
            "membership_snapshot_root": optional_fingerprint_schema(),
            "minimum_stability_steps": positive_authority_integer_schema(),
            "ordered_assessment_refs": {
                "type": "array",
                "items": fingerprint_schema(),
                "uniqueItems": True,
            },
            "permission_root": optional_fingerprint_schema(),
            "previous_state_fingerprint": optional_fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "remaining_epoch_restart_budget": authority_integer_schema(),
            "remaining_reset_budget": authority_integer_schema(),
            "reset_budget_exhausted": {"type": "boolean"},
            "reset_reason": canonical_text_schema(),
            "revision": authority_integer_schema(),
            "risk_assessment_root": fingerprint_schema(),
            "risk_chain_state_root": optional_fingerprint_schema(),
            "risk_policy_root": optional_fingerprint_schema(),
            "stop_resolution_root": optional_fingerprint_schema(),
            "support_replay_root": optional_fingerprint_schema(),
            "support_replay_state_root": optional_fingerprint_schema(),
            "threshold_root": fingerprint_schema(),
            "trace_event_id": canonical_text_schema(),
            "window_count": authority_integer_schema(),
            "window_root": fingerprint_schema(),
        }
    )


def commit_window_seal_payload_schema() -> dict[str, Any]:
    roots = {
        name: fingerprint_schema()
        for name in (
            "assessment_ref",
            "candidate_challenge_root",
            "candidate_evidence_root",
            "candidate_lease_root",
            "chain_id",
            "claim_fingerprint",
            "collective_challenge_root",
            "collective_evidence_root",
            "collective_lease_root",
            "context_ref",
            "membership_epoch_state_root",
            "membership_root",
            "membership_snapshot_root",
            "output_payload_fingerprint",
            "permission_root",
            "receipt_ref",
            "replay_root",
            "replay_state_ref",
            "risk_assessment_root",
            "risk_chain_state_root",
            "risk_policy_root",
            "stop_resolution_root",
            "support_replay_root",
            "support_replay_state_root",
            "threshold_root",
            "window_root",
            "window_state_ref",
        )
    }
    return strict_object_schema(
        {
            **commit_binding_properties(),
            **roots,
            "absolute_deadline_step": authority_integer_schema(),
            "absolute_run_deadline_step": authority_integer_schema(),
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "generation": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "remaining_epoch_restart_budget": authority_integer_schema(),
            "remaining_reset_budget": authority_integer_schema(),
            "sealed_at_step": authority_integer_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def commit_liveness_input_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "assessment_reason_codes": canonical_text_set_schema(),
            "assessment_ref": optional_fingerprint_schema(),
            "assessment_status": optional_enum_schema(
                ("not_ready", "ready", "safety_violation")
            ),
            "authority": governance_authority_schema(),
            "blocked_reason_codes": canonical_text_set_schema(),
            "certificate_ref": optional_fingerprint_schema(),
            "candidate_challenge_root": optional_fingerprint_schema(),
            "candidate_evidence_root": optional_fingerprint_schema(),
            "candidate_lease_root": optional_fingerprint_schema(),
            "collective_challenge_root": optional_fingerprint_schema(),
            "collective_evidence_root": optional_fingerprint_schema(),
            "collective_lease_root": optional_fingerprint_schema(),
            "context_ref": optional_fingerprint_schema(),
            "current_step": authority_integer_schema(),
            "deadline_reached": {"type": "boolean"},
            "finality_reason_codes": canonical_text_set_schema(),
            "finality_status": {
                "enum": [
                    "conflict",
                    "not_required",
                    "pending",
                    "provisional",
                    "unavailable",
                    "verified",
                ]
            },
            "finality_verification_ref": optional_fingerprint_schema(),
            "heartbeat_continuous": {"type": "boolean"},
            "heartbeat_sequence": authority_integer_schema(),
            "input_id": canonical_text_schema(),
            "invalid_reason_codes": canonical_text_set_schema(),
            "issuer_id": canonical_text_schema(),
            "leader_candidate_id": optional_text_schema(),
            "leader_ready_for_stability": {"type": "boolean"},
            "membership_root": fingerprint_schema(),
            "membership_epoch_state_root": optional_fingerprint_schema(),
            "membership_snapshot_root": optional_fingerprint_schema(),
            "next_required_inputs": canonical_text_set_schema(),
            "permission_root": optional_fingerprint_schema(),
            "previous_progress_ref": optional_fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "replay_root": fingerprint_schema(),
            "replay_state_ref": fingerprint_schema(),
            "risk_assessment_root": fingerprint_schema(),
            "risk_chain_state_root": optional_fingerprint_schema(),
            "risk_policy_root": optional_fingerprint_schema(),
            "safety_violation_reason_codes": canonical_text_set_schema(),
            "seal_ref": optional_fingerprint_schema(),
            "sealed_at_step": authority_integer_schema(),
            "sealed_window": {"type": "boolean"},
            "stop_resolution_root": optional_fingerprint_schema(),
            "support_replay_root": optional_fingerprint_schema(),
            "support_replay_state_root": optional_fingerprint_schema(),
            "threshold_root": fingerprint_schema(),
            "trace_event_id": canonical_text_schema(),
            "window_state_ref": fingerprint_schema(),
        }
    )


def commit_finality_verification_payload_schema() -> dict[str, Any]:
    lineage = {
        name: fingerprint_schema()
        for name in (
            "assessment_ref",
            "candidate_challenge_root",
            "candidate_evidence_root",
            "candidate_lease_root",
            "certificate_ref",
            "collective_challenge_root",
            "collective_evidence_root",
            "collective_lease_root",
            "context_ref",
            "membership_epoch_state_root",
            "membership_root",
            "membership_snapshot_root",
            "permission_root",
            "replay_root",
            "replay_state_ref",
            "risk_assessment_root",
            "risk_chain_state_root",
            "risk_policy_root",
            "stop_resolution_root",
            "support_replay_root",
            "support_replay_state_root",
            "threshold_root",
            "window_root",
            "window_state_ref",
        )
    }
    return strict_object_schema(
        {
            **commit_binding_properties(),
            **lineage,
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "certificate_kind": {
                "enum": [
                    "distributed_commit_certificate",
                    "evidence_commit_certificate",
                    "local_commit_receipt",
                ]
            },
            "provenance": canonical_text_schema(),
            "status": {"const": "verified"},
            "trace_event_id": canonical_text_schema(),
            "verified_at_step": authority_integer_schema(),
            "verifier_id": canonical_text_schema(),
        }
    )


def commit_replay_state_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "authority": governance_authority_schema(),
            "chain_id": fingerprint_schema(),
            "commit_policy_root": fingerprint_schema(),
            "current_step": authority_integer_schema(),
            "initialized_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "manifest_root": fingerprint_schema(),
            "previous_state_fingerprint": optional_fingerprint_schema(),
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "protocol_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "receipt_root": fingerprint_schema(),
            "receipts": {
                "type": "array",
                "items": replay_receipt_payload_schema(),
                "uniqueItems": True,
            },
            "revision": authority_integer_schema(),
            "run_id": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def replay_receipt_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "candidate_id": optional_text_schema(),
            "epoch": authority_integer_schema(),
            "namespace": {
                "enum": [
                    "action_permission",
                    "assessment",
                    "challenge",
                    "counterevidence_disposition",
                    "membership",
                    "observation",
                    "principal",
                    "risk_assessment",
                    "stop_resolution",
                    "support_lease",
                    "support_revocation",
                    "threshold",
                    "witness",
                ]
            },
            "nonce": canonical_text_schema(),
            "payload_fingerprint": fingerprint_schema(),
            "principal_id": optional_text_schema(),
            "record_id": canonical_text_schema(),
            "target": canonical_text_schema(),
        }
    )


def observation_attestation_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "independence_group": canonical_text_schema(),
            "nonce": canonical_text_schema(),
            "observation_id": canonical_text_schema(),
            "observed_at_step": authority_integer_schema(),
            "payload_fingerprint": fingerprint_schema(),
            "polarity": {"enum": ["contradict", "support"]},
            "principal_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "reported_criticality_ppm": scaled_integer_schema(),
            "reported_materiality_ppm": scaled_integer_schema(),
            "reported_quality_ppm": scaled_integer_schema(),
            "reported_relevance_ppm": scaled_integer_schema(),
            "source_domain": canonical_text_schema(),
            "target": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def verified_observation_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "attestation_fingerprint": fingerprint_schema(),
            "attestation_provenance": canonical_text_schema(),
            "attestation_trace_event_id": canonical_text_schema(),
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "criticality_ppm": scaled_integer_schema(),
            "expires_at_step": authority_integer_schema(),
            "independence_group": canonical_text_schema(),
            "materiality_ppm": scaled_integer_schema(),
            "nonce": canonical_text_schema(),
            "observation_id": canonical_text_schema(),
            "observed_at_step": authority_integer_schema(),
            "payload_fingerprint": fingerprint_schema(),
            "polarity": {"enum": ["contradict", "support"]},
            "principal_cluster_id": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "principal_verification_fingerprint": fingerprint_schema(),
            "quality_ppm": scaled_integer_schema(),
            "relevance_ppm": scaled_integer_schema(),
            "source_domain": canonical_text_schema(),
            "verification_provenance": canonical_text_schema(),
            "verification_trace_event_id": canonical_text_schema(),
            "verified_at_step": authority_integer_schema(),
            "verifier_id": canonical_text_schema(),
        }
    )


def counterevidence_disposition_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "counter_observation_fingerprint": fingerprint_schema(),
            "disposition_id": canonical_text_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "kind": {
                "enum": ["accepted", "immaterial", "rebutted", "unresolved"]
            },
            "provenance": canonical_text_schema(),
            "reason_codes": canonical_text_set_schema(minimum=1),
            "rebuttal_observation_fingerprints": fingerprint_set_schema(),
            "resolution_ref": optional_fingerprint_schema(),
            "trace_event_id": canonical_text_schema(),
            "verifier_id": canonical_text_schema(),
        }
    )


def challenge_attestation_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "candidate_id": canonical_text_schema(),
            "category": canonical_text_schema(),
            "challenge_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "executed_at_step": authority_integer_schema(),
            "execution_attestation_ref": canonical_text_schema(),
            "execution_fingerprint": fingerprint_schema(),
            "execution_method": canonical_text_schema(),
            "expires_at_step": authority_integer_schema(),
            "nonce": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "result": {
                "enum": [
                    "counterevidence_found",
                    "inconclusive",
                    "no_counterevidence",
                ]
            },
            "result_fingerprint": fingerprint_schema(),
            "result_observation_fingerprints": fingerprint_set_schema(),
            "target": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def verified_challenge_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "attestation_fingerprint": fingerprint_schema(),
            "attestation_provenance": canonical_text_schema(),
            "attestation_trace_event_id": canonical_text_schema(),
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "category": canonical_text_schema(),
            "challenge_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "executed_at_step": authority_integer_schema(),
            "execution_attestation_ref": canonical_text_schema(),
            "execution_fingerprint": fingerprint_schema(),
            "execution_method": canonical_text_schema(),
            "expires_at_step": authority_integer_schema(),
            "nonce": canonical_text_schema(),
            "principal_cluster_id": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "principal_verification_fingerprint": fingerprint_schema(),
            "result": {
                "enum": [
                    "counterevidence_found",
                    "inconclusive",
                    "no_counterevidence",
                ]
            },
            "result_fingerprint": fingerprint_schema(),
            "result_observation_fingerprints": fingerprint_set_schema(),
            "verification_provenance": canonical_text_schema(),
            "verification_trace_event_id": canonical_text_schema(),
            "verified_at_step": authority_integer_schema(),
            "verifier_id": canonical_text_schema(),
        }
    )


def challenge_coverage_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "challenge_fingerprints": fingerprint_set_schema(),
            "complete": {"type": "boolean"},
            "covered_categories": canonical_text_set_schema(),
            "missing_categories": canonical_text_set_schema(),
            "required_categories": canonical_text_set_schema(),
        }
    )


def evidence_binding_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "binding_version": {"const": EVIDENCE_BINDING_VERSION},
            "candidate_id": canonical_text_schema(),
            "challenge_fingerprints": fingerprint_set_schema(),
            "challenge_root": fingerprint_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "counter_observation_fingerprints": fingerprint_set_schema(),
            "counter_root": fingerprint_schema(),
            "disposition_fingerprints": fingerprint_set_schema(),
            "disposition_root": fingerprint_schema(),
            "evidence_id": canonical_text_schema(),
            "evidence_root": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "positive_observation_fingerprints": fingerprint_set_schema(),
            "positive_root": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def evidence_group_contribution_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "counted_contribution": authority_integer_schema(),
            "group_cap": positive_authority_integer_schema(),
            "independence_group": canonical_text_schema(),
            "observation_fingerprints": fingerprint_set_schema(minimum=1),
            "raw_contribution": authority_integer_schema(),
        }
    )


def source_domain_contribution_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "contribution": authority_integer_schema(),
            "contribution_floor": positive_authority_integer_schema(),
            "observation_fingerprints": fingerprint_set_schema(minimum=1),
            "qualifies": {"type": "boolean"},
            "source_domain": canonical_text_schema(),
        }
    )


def evidence_summary_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "active_counter_observation_fingerprints": fingerprint_set_schema(),
            "blocking_critical_counter_observation_fingerprints": (
                fingerprint_set_schema()
            ),
            "challenge_coverage": challenge_coverage_payload_schema(),
            "counter_groups": {
                "type": "array",
                "items": evidence_group_contribution_schema(),
            },
            "counter_limit_satisfied": {"type": "boolean"},
            "counter_ratio_satisfied": {"type": "boolean"},
            "counterevidence": authority_integer_schema(),
            "counterevidence_ratio_ppm": scaled_integer_schema(),
            "critical_counterevidence_clear": {"type": "boolean"},
            "evidence_binding_fingerprint": fingerprint_schema(),
            "evidence_gates_satisfied": {"type": "boolean"},
            "maximum_counterevidence": authority_integer_schema(),
            "maximum_counterevidence_ratio_ppm": scaled_integer_schema(),
            "minimum_positive_evidence": positive_authority_integer_schema(),
            "minimum_source_diversity": positive_authority_integer_schema(),
            "net_evidence": signed_authority_integer_schema(),
            "positive_evidence": authority_integer_schema(),
            "positive_groups": {
                "type": "array",
                "items": evidence_group_contribution_schema(),
            },
            "positive_threshold_satisfied": {"type": "boolean"},
            "resolved_counter_observation_fingerprints": fingerprint_set_schema(),
            "source_diversity": authority_integer_schema(),
            "source_diversity_satisfied": {"type": "boolean"},
            "source_domains": {
                "type": "array",
                "items": source_domain_contribution_schema(),
            },
            "weighted_counterevidence": authority_integer_schema(),
        }
    )


def eligible_principal_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "failure_domain": optional_text_schema(),
            "principal_id": canonical_text_schema(),
            "principal_verification_fingerprint": fingerprint_schema(),
            "verified_issuer_id": canonical_text_schema(),
            "verified_method": canonical_text_schema(),
        }
    )


def eligible_cluster_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "cluster_id": canonical_text_schema(),
            "principals": {
                "type": "array",
                "items": eligible_principal_schema(),
                "minItems": 1,
            },
        }
    )


def eligible_principal_snapshot_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "eligible_clusters": {
                "type": "array",
                "items": eligible_cluster_schema(),
            },
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "membership_method": canonical_text_schema(),
            "membership_root": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "snapshot_id": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def eligible_membership_epoch_state_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "authority_key": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "membership_method": canonical_text_schema(),
            "membership_root": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "snapshot_fingerprint": fingerprint_schema(),
            "snapshot_id": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def support_lease_proposal_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "nonce": canonical_text_schema(),
            "positive_observation_fingerprints": fingerprint_set_schema(minimum=1),
            "principal_id": canonical_text_schema(),
            "proposal_id": canonical_text_schema(),
            "proposed_at_step": authority_integer_schema(),
            "provenance": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def support_lease_replay_receipt_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "lease_fingerprint": fingerprint_schema(),
            "lease_id": canonical_text_schema(),
            "membership_epoch_state_fingerprint": fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "nonce": canonical_text_schema(),
            "principal_cluster_id": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "proposal_fingerprint": fingerprint_schema(),
            "replay_receipt_fingerprint": fingerprint_schema(),
        }
    )


def support_lease_replay_state_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "authority": governance_authority_schema(),
            "authority_key": fingerprint_schema(),
            "initialized_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "last_issued_at_step": authority_integer_schema(),
            "previous_state_fingerprint": optional_fingerprint_schema(),
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "protocol_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "receipts": {
                "type": "array",
                "items": support_lease_replay_receipt_payload_schema(),
                "uniqueItems": True,
            },
            "replay_root": fingerprint_schema(),
            "revision": authority_integer_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def support_lease_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "issuance_provenance": canonical_text_schema(),
            "issuance_trace_event_id": canonical_text_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "lease_id": canonical_text_schema(),
            "membership_epoch_state_fingerprint": fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "nonce": canonical_text_schema(),
            "positive_observation_fingerprints": fingerprint_set_schema(minimum=1),
            "principal_cluster_id": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "principal_verification_fingerprint": fingerprint_schema(),
            "prior_lease_fingerprint": optional_fingerprint_schema(),
            "proposal_fingerprint": fingerprint_schema(),
            "proposal_provenance": canonical_text_schema(),
            "proposal_trace_event_id": canonical_text_schema(),
            "replay_authority_key": fingerprint_schema(),
            "replay_receipt_fingerprint": fingerprint_schema(),
        }
    )


def support_lease_revocation_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "issuer_id": canonical_text_schema(),
            "lease_fingerprint": fingerprint_schema(),
            "principal_cluster_id": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "reason_codes": canonical_text_set_schema(minimum=1),
            "revocation_id": canonical_text_schema(),
            "revoked_at_step": authority_integer_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def support_equivocation_finding_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "conflicting_candidates": canonical_text_set_schema(minimum=2),
            "conflicting_lease_fingerprints": fingerprint_set_schema(minimum=2),
            "finding_id": fingerprint_schema(),
            "first_overlap_step": authority_integer_schema(),
            "principal_cluster_id": canonical_text_schema(),
        }
    )


def support_lease_evaluation_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "active_support_cluster_count": authority_integer_schema(),
            "active_support_clusters": canonical_text_set_schema(),
            "candidate_id": canonical_text_schema(),
            "claim_fingerprint": fingerprint_schema(),
            "current_step": authority_integer_schema(),
            "eligible_cluster_count": positive_authority_integer_schema(),
            "equivocation_findings": {
                "type": "array",
                "items": support_equivocation_finding_payload_schema(),
            },
            "excluded_lease_fingerprints": fingerprint_set_schema(),
            "included_lease_fingerprints": fingerprint_set_schema(),
            "lease_root": fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "membership_epoch_state_fingerprint": fingerprint_schema(),
            "policy_support_met": {"type": "boolean"},
            "policy_support_threshold_clusters": positive_authority_integer_schema(),
            "support_ratio_ppm": scaled_integer_schema(),
            "support_replay_scope_root": fingerprint_schema(),
        }
    )


def risk_assessment_chain_state_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "chain_id": fingerprint_schema(),
            "expires_at_step": authority_integer_schema(),
            "initialized_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "last_issued_at_step": authority_integer_schema(),
            "latest_assessment_fingerprint": optional_fingerprint_schema(),
            "latest_risk_band": optional_enum_schema(
                ("CRITICAL", "HIGH", "LOW", "MODERATE")
            ),
            "previous_state_fingerprint": optional_fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "revision": authority_integer_schema(),
            "risk_policy_root": fingerprint_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def risk_assessment_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "assessment_id": canonical_text_schema(),
            "assessment_method": canonical_text_schema(),
            "authority": governance_authority_schema(),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "previous_assessment_fingerprint": optional_fingerprint_schema(),
            "previous_chain_state_fingerprint": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "rationale_codes": canonical_text_set_schema(minimum=1),
            "risk_band": {"enum": ["CRITICAL", "HIGH", "LOW", "MODERATE"]},
            "risk_chain_id": fingerprint_schema(),
            "risk_chain_revision": positive_authority_integer_schema(),
            "risk_input_fingerprints": fingerprint_set_schema(minimum=1),
            "risk_policy_root": fingerprint_schema(),
            "trace_event_id": canonical_text_schema(),
            "window_reset_required": {"type": "boolean"},
        }
    )


def commit_threshold_snapshot_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            "authority": governance_authority_schema(),
            "executable_outcomes": terminal_outcome_set_schema(
                allowed=("evidence_commit",)
            ),
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "maximum_counterevidence": authority_integer_schema(),
            "maximum_counterevidence_ratio_ppm": scaled_integer_schema(),
            "minimum_assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "minimum_margin": positive_authority_integer_schema(),
            "minimum_positive_evidence": positive_authority_integer_schema(),
            "minimum_source_diversity": positive_authority_integer_schema(),
            "minimum_support_clusters": positive_authority_integer_schema(),
            "minimum_support_ratio_ppm": positive_scaled_integer_schema(),
            "provenance": canonical_text_schema(),
            "publishable_outcomes": terminal_outcome_set_schema(),
            "required_challenge_categories": canonical_text_set_schema(minimum=1),
            "risk_assessment_fingerprint": fingerprint_schema(),
            "risk_band": {"enum": ["CRITICAL", "HIGH", "LOW", "MODERATE"]},
            "risk_chain_id": fingerprint_schema(),
            "risk_chain_revision": positive_authority_integer_schema(),
            "risk_chain_state_fingerprint": fingerprint_schema(),
            "risk_policy_root": fingerprint_schema(),
            "stability_steps": positive_authority_integer_schema(),
            "threshold_id": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def hybrid_commit_truth_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "assessment_status": {
                "enum": ["not_ready", "ready", "safety_violation"]
            },
            "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "commit_assessment_fingerprint": fingerprint_schema(),
            "commit_authority_source": {"const": "optimal_commit_assessment_only"},
            "commit_challenge_root": fingerprint_schema(),
            "commit_context_root": fingerprint_schema(),
            "commit_evidence_root": fingerprint_schema(),
            "commit_lease_root": fingerprint_schema(),
            "commit_metrics_root": fingerprint_schema(),
            "commit_truth_root": fingerprint_schema(),
            "current_step": authority_integer_schema(),
            "epoch": authority_integer_schema(),
            "leader_candidate_id": optional_text_schema(),
            "leader_margin": signed_authority_integer_schema(),
            "leader_ready_for_stability": {"type": "boolean"},
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "protocol_id": canonical_text_schema(),
            "run_id": canonical_text_schema(),
            "target": canonical_text_schema(),
            "unique_leader": {"type": "boolean"},
        }
    )


def hybrid_attention_binding_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "attention_fingerprint": fingerprint_schema(),
            "authority_scope": {"const": "none"},
            "commit_authority": {"const": False},
            "exploration_directive_fingerprint": fingerprint_schema(),
            "memory_root": fingerprint_schema(),
            "replay_root": fingerprint_schema(),
            "source_step_root": fingerprint_schema(),
            "trace_root": fingerprint_schema(),
        }
    )


def hybrid_commit_step_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "attention": hybrid_attention_binding_payload_schema(),
            "binding_profile": {"const": "pheroos-hybrid-commit-binding-v1"},
            "commit": hybrid_commit_truth_payload_schema(),
            "composition_root": fingerprint_schema(),
        }
    )


def hybrid_commit_diagnostic_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "code": canonical_text_schema(),
            "severity": {"enum": ["error", "info", "warning"]},
            "stage": canonical_text_schema(),
            "message": canonical_text_schema(),
            "fatal": {"type": "boolean"},
            "references": fingerprint_set_schema(),
        }
    )


def hybrid_commit_evaluation_payload_schema() -> dict[str, Any]:
    optional_root_names = (
        "assessment_ref",
        "attention_ref",
        "binding_step_ref",
        "context_ref",
        "deliver_authorization_ref",
        "distributed_certificate_ref",
        "distributed_state_ref",
        "evidence_certificate_ref",
        "execute_authorization_ref",
        "exploration_directive_ref",
        "finality_verification_ref",
        "local_receipt_ref",
        "outcome_certificate_ref",
        "outcome_ref",
        "progress_ref",
        "publish_authorization_ref",
        "replay_root",
        "replay_state_ref",
        "window_root",
        "window_state_ref",
    )
    schema = strict_object_schema(
        {
            "evaluation_version": {
                "const": "pheroos-hybrid-commit-evaluation-v1"
            },
            "request_ref": fingerprint_schema(),
            "status": {"enum": ["invalid", "outcome", "progress"]},
            "authoritative": {"type": "boolean"},
            "terminal": {"type": "boolean"},
            "assurance_downgraded": {"const": False},
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
            "protocol_id": canonical_text_schema(),
            "run_id": canonical_text_schema(),
            "target": canonical_text_schema(),
            "epoch": authority_integer_schema(),
            "current_step": authority_integer_schema(),
            "attention_status": {"enum": ["unavailable", "verified"]},
            **{
                name: optional_fingerprint_schema()
                for name in optional_root_names
            },
            "trace_event_ids": fingerprint_set_schema(),
            "trace_root": fingerprint_schema(),
            "diagnostics": {
                "type": "array",
                "items": hybrid_commit_diagnostic_schema(),
            },
            "evaluation_root": fingerprint_schema(),
        }
    )
    schema["allOf"] = [
        {
            "oneOf": [
                {
                    "properties": {
                        "authoritative": {"const": True},
                        "status": {"const": "progress"},
                        "terminal": {"const": False},
                        "progress_ref": fingerprint_schema(),
                        "outcome_ref": {"const": ""},
                    }
                },
                {
                    "properties": {
                        "authoritative": {"const": True},
                        "status": {"enum": ["invalid", "outcome"]},
                        "terminal": {"const": True},
                        "progress_ref": {"const": ""},
                        "outcome_ref": fingerprint_schema(),
                    }
                },
                {
                    "properties": {
                        "authoritative": {"const": False},
                        "status": {"const": "invalid"},
                        "terminal": {"const": True},
                        "progress_ref": {"const": ""},
                        "outcome_ref": {"const": ""},
                    }
                },
            ]
        },
        {
            "if": {
                "properties": {"authoritative": {"const": True}},
                "required": ["authoritative"],
            },
            "then": {
                "properties": {
                    "assessment_ref": fingerprint_schema(),
                    "context_ref": fingerprint_schema(),
                    "window_state_ref": fingerprint_schema(),
                    "replay_state_ref": fingerprint_schema(),
                }
            },
        },
        {
            "oneOf": [
                {
                    "properties": {
                        "attention_status": {"const": "verified"},
                        "binding_step_ref": fingerprint_schema(),
                        "attention_ref": fingerprint_schema(),
                        "exploration_directive_ref": fingerprint_schema(),
                        "diagnostics": {
                            "not": {
                                "contains": {
                                    "properties": {
                                        "code": {
                                            "const": "attention_channel_unavailable"
                                        }
                                    },
                                    "required": ["code"],
                                }
                            }
                        },
                    }
                },
                {
                    "properties": {
                        "attention_status": {"const": "unavailable"},
                        "binding_step_ref": {"const": ""},
                        "attention_ref": {"const": ""},
                        "exploration_directive_ref": {"const": ""},
                        "diagnostics": {
                            "contains": {
                                "oneOf": [
                                    {
                                        "properties": {
                                            "code": {
                                                "const": "attention_channel_unavailable"
                                            },
                                            "severity": {"const": "warning"},
                                            "stage": {"const": "attention"},
                                            "message": {
                                                "const": (
                                                    "Hybrid attention input is missing "
                                                    "or non-authoritative"
                                                )
                                            },
                                            "fatal": {"const": False},
                                        },
                                        "required": [
                                            "code",
                                            "severity",
                                            "stage",
                                            "message",
                                            "fatal",
                                        ],
                                    },
                                    {
                                        "properties": {
                                            "code": {
                                                "const": "attention_channel_unavailable"
                                            },
                                            "severity": {"const": "warning"},
                                            "stage": {
                                                "const": "exploration_directive"
                                            },
                                            "message": {
                                                "const": (
                                                    "Hybrid exploration directive is "
                                                    "missing, non-authoritative, or does "
                                                    "not match attention"
                                                )
                                            },
                                            "fatal": {"const": False},
                                        },
                                        "required": [
                                            "code",
                                            "severity",
                                            "stage",
                                            "message",
                                            "fatal",
                                        ],
                                    },
                                    {
                                        "properties": {
                                            "code": {
                                                "const": "attention_channel_unavailable"
                                            },
                                            "severity": {"const": "warning"},
                                            "stage": {"const": "channel_binding"},
                                            "message": {
                                                "const": (
                                                    "Hybrid attention cannot be bound "
                                                    "to the authoritative "
                                                    "CommitAssessment"
                                                )
                                            },
                                            "fatal": {"const": False},
                                        },
                                        "required": [
                                            "code",
                                            "severity",
                                            "stage",
                                            "message",
                                            "fatal",
                                        ],
                                    },
                                ]
                            },
                            "minContains": 1,
                            "maxContains": 1,
                        },
                    }
                },
            ]
        },
    ]
    return schema


def _certificate_lineage_properties(
    *,
    allow_empty_contextual_roots: bool = False,
) -> dict[str, Any]:
    contextual_root = (
        optional_fingerprint_schema()
        if allow_empty_contextual_roots
        else fingerprint_schema()
    )
    return {
        "assessment_root": contextual_root,
        "candidate_challenge_root": contextual_root,
        "candidate_evidence_root": contextual_root,
        "candidate_lease_root": contextual_root,
        "challenge_root": contextual_root,
        "claim_fingerprint": contextual_root,
        "context_root": contextual_root,
        "evidence_root": contextual_root,
        "lease_root": contextual_root,
        "membership_epoch_state_root": contextual_root,
        "membership_root": fingerprint_schema(),
        "membership_snapshot_root": contextual_root,
        "output_payload_fingerprint": fingerprint_schema(),
        "permission_root": contextual_root,
        "replay_root": fingerprint_schema(),
        "replay_state_root": fingerprint_schema(),
        "risk_assessment_root": fingerprint_schema(),
        "risk_chain_state_root": contextual_root,
        "risk_policy_root": contextual_root,
        "stop_resolution_root": contextual_root,
        "support_replay_root": contextual_root,
        "support_replay_state_root": contextual_root,
        "threshold_root": fingerprint_schema(),
        "window_root": fingerprint_schema(),
        "window_state_root": fingerprint_schema(),
    }


def _certificate_header_properties() -> dict[str, Any]:
    return {
        "canonicalization": {"const": COMMIT_CANONICAL_VERSION},
        "hash_algorithm": {"const": "sha256"},
        "wire_version": {"const": COMMIT_WIRE_VERSION},
    }


def _certificate_issuer_properties() -> dict[str, Any]:
    return {
        "authority": governance_authority_schema(),
        "issued_at_step": authority_integer_schema(),
        "issuer_id": canonical_text_schema(),
        "provenance": canonical_text_schema(),
        "trace_event_id": canonical_text_schema(),
    }


def local_commit_receipt_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            **_certificate_header_properties(),
            **_certificate_lineage_properties(),
            **_certificate_issuer_properties(),
            "assurance": {
                "enum": ["certified", "distributed", "evidence_bound"]
            },
            "authority_scope": {"const": "governance_local"},
            "candidate_id": canonical_text_schema(),
            "receipt_id": canonical_text_schema(),
            "receipt_version": {"const": "pheroos-local-commit-receipt-v1"},
            "schema_discriminator": {"const": "local_commit_receipt"},
        }
    )


def evidence_commit_certificate_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **commit_binding_properties(),
            **_certificate_header_properties(),
            **_certificate_lineage_properties(),
            **_certificate_issuer_properties(),
            "assurance": {"enum": ["certified", "distributed"]},
            "authority_scope": {"const": "certified"},
            "candidate_id": canonical_text_schema(),
            "certificate_body_root": fingerprint_schema(),
            "certificate_id": canonical_text_schema(),
            "certificate_root": fingerprint_schema(),
            "certificate_version": {
                "const": "pheroos-evidence-commit-certificate-v1"
            },
            "issuer_attestation_refs": canonical_text_set_schema(minimum=1),
            "local_receipt_ref": fingerprint_schema(),
            "schema_discriminator": {"const": "evidence_commit_certificate"},
        }
    )


def outcome_certificate_payload_schema() -> dict[str, Any]:
    schema = strict_object_schema(
        {
            **commit_binding_properties(),
            **_certificate_header_properties(),
            **_certificate_lineage_properties(
                allow_empty_contextual_roots=True,
            ),
            **_certificate_issuer_properties(),
            "authoritative_commit": {"type": "boolean"},
            "authority_scope": {
                "enum": [
                    "certified",
                    "denial",
                    "distributed",
                    "governance_local",
                    "none",
                ]
            },
            "candidate_id": optional_text_schema(),
            "certificate_body_root": fingerprint_schema(),
            "certificate_id": canonical_text_schema(),
            "certificate_root": fingerprint_schema(),
            "certificate_version": {"const": "pheroos-outcome-certificate-v1"},
            "commit_certificate_ref": optional_fingerprint_schema(),
            "epistemically_committed": {"type": "boolean"},
            "issuer_attestation_refs": canonical_text_set_schema(),
            "outcome_kind": {
                "enum": [
                    "advisory",
                    "blocked",
                    "evidence_commit",
                    "finality_unavailable",
                    "invalid",
                    "safe_fallback",
                    "safety_violation",
                ]
            },
            "outcome_ref": fingerprint_schema(),
            "schema_discriminator": {"const": "outcome_certificate"},
        }
    )
    schema["allOf"] = [
        {
            "if": {
                "properties": {"outcome_kind": {"const": "evidence_commit"}},
                "required": ["outcome_kind"],
            },
            "then": {
                "properties": {
                    "authoritative_commit": {"const": True},
                    "candidate_id": canonical_text_schema(),
                    "claim_fingerprint": fingerprint_schema(),
                    "commit_certificate_ref": fingerprint_schema(),
                    "epistemically_committed": {"const": True},
                },
                "oneOf": [
                    {
                        "properties": {
                            "assurance": {"const": "evidence_bound"},
                            "authority_scope": {"const": "governance_local"},
                        },
                        "required": ["assurance", "authority_scope"],
                    },
                    {
                        "properties": {
                            "assurance": {"const": "certified"},
                            "authority_scope": {"const": "certified"},
                        },
                        "required": ["assurance", "authority_scope"],
                    },
                    {
                        "properties": {
                            "assurance": {"const": "distributed"},
                            "authority_scope": {"const": "distributed"},
                        },
                        "required": ["assurance", "authority_scope"],
                    },
                ],
            },
            "else": {
                "properties": {
                    "authoritative_commit": {"const": False},
                    "commit_certificate_ref": {"const": ""},
                    "epistemically_committed": {"const": False},
                },
                "oneOf": [
                    {
                        "properties": {
                            "authority_scope": {"const": "denial"},
                            "outcome_kind": {"const": "blocked"},
                        },
                        "required": ["authority_scope", "outcome_kind"],
                    },
                    {
                        "properties": {
                            "authority_scope": {"const": "none"},
                            "outcome_kind": {
                                "enum": [
                                    "advisory",
                                    "finality_unavailable",
                                    "invalid",
                                    "safe_fallback",
                                    "safety_violation",
                                ]
                            },
                        },
                        "required": ["authority_scope", "outcome_kind"],
                    },
                ],
            },
        },
        {
            "if": {
                "properties": {
                    "assurance": {"enum": ["certified", "distributed"]}
                },
                "required": ["assurance"],
            },
            "then": {
                "properties": {
                    "issuer_attestation_refs": canonical_text_set_schema(
                        minimum=1
                    )
                }
            },
            "else": {
                "properties": {
                    "issuer_attestation_refs": {
                        **canonical_text_set_schema(),
                        "maxItems": 0,
                    }
                }
            },
        },
        {
            "if": {
                "properties": {"outcome_kind": {"const": "safe_fallback"}},
                "required": ["outcome_kind"],
            },
            "then": {
                "properties": {
                    "candidate_id": canonical_text_schema(),
                    "claim_fingerprint": fingerprint_schema(),
                }
            },
        },
    ]
    return schema


def commit_output_authorization_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "action": {"enum": ["deliver", "execute", "publish"]},
            "authorized": {"type": "boolean"},
            "certificate_ref": optional_fingerprint_schema(),
            "distributed_conflict_root": optional_fingerprint_schema(),
            "distributed_state_ref": optional_fingerprint_schema(),
            "gates": {
                "type": "object",
                "minProperties": 1,
                "patternProperties": {
                    r"^[a-z][a-z0-9_]*$": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "outcome_ref": optional_fingerprint_schema(),
            "output_payload_fingerprint": optional_fingerprint_schema(),
            "permission_ref": optional_fingerprint_schema(),
            "policy_ref": optional_fingerprint_schema(),
            "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
            "reason_codes": canonical_text_set_schema(minimum=1),
            "stop_resolution_ref": optional_fingerprint_schema(),
            "threshold_ref": optional_fingerprint_schema(),
        }
    )


def distributed_binding_properties() -> dict[str, Any]:
    return {
        "assurance": {"const": "distributed"},
        "commit_policy_root": fingerprint_schema(),
        "epoch": authority_integer_schema(),
        "manifest_root": fingerprint_schema(),
        "profile": {"const": "pheroos-distributed-commit-v1"},
        "protocol_id": canonical_text_schema(),
        "run_id": canonical_text_schema(),
        "target": canonical_text_schema(),
    }


def portable_eligible_principal_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "failure_domain": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "principal_verification_fingerprint": fingerprint_schema(),
            "verified_issuer_id": canonical_text_schema(),
            "verified_method": canonical_text_schema(),
        }
    )


def portable_eligible_cluster_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "cluster_id": canonical_text_schema(),
            "principals": {
                "type": "array",
                "items": portable_eligible_principal_schema(),
                "minItems": 1,
                "uniqueItems": True,
            },
        }
    )


def portable_membership_snapshot_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **distributed_binding_properties(),
            "authority": governance_authority_schema(),
            "eligible_clusters": {
                "type": "array",
                "items": portable_eligible_cluster_schema(),
                "minItems": 1,
                "uniqueItems": True,
            },
            "expires_at_step": authority_integer_schema(),
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "membership_method": canonical_text_schema(),
            "membership_root": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "snapshot_fingerprint": fingerprint_schema(),
            "snapshot_id": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
        }
    )


def distributed_commit_proposal_payload_schema() -> dict[str, Any]:
    roots = {
        name: fingerprint_schema()
        for name in (
            "assessment_root",
            "candidate_challenge_root",
            "candidate_evidence_root",
            "candidate_lease_root",
            "challenge_root",
            "claim_fingerprint",
            "commit_value_root",
            "context_root",
            "evidence_root",
            "lease_root",
            "local_receipt_ref",
            "membership_epoch_state_root",
            "membership_root",
            "membership_snapshot_root",
            "output_payload_fingerprint",
            "permission_root",
            "portable_certificate_ref",
            "proposal_digest",
            "replay_root",
            "replay_state_root",
            "risk_assessment_root",
            "risk_chain_state_root",
            "risk_policy_root",
            "stop_resolution_root",
            "support_replay_root",
            "support_replay_state_root",
            "threshold_root",
            "window_root",
            "window_state_root",
        )
    }
    return strict_object_schema(
        {
            **distributed_binding_properties(),
            **roots,
            "candidate_id": canonical_text_schema(),
            "canonicalization": {"const": "pheroos-commit-canonical-v1"},
            "hash_algorithm": {"const": "sha256"},
            "local_receipt_version": {
                "const": "pheroos-local-commit-receipt-v1"
            },
            "portable_certificate_version": {
                "const": "pheroos-evidence-commit-certificate-v1"
            },
            "proposal_id": canonical_text_schema(),
            "proposal_version": {"const": "pheroos-distributed-commit-proposal-v1"},
            "proposed_at_step": authority_integer_schema(),
            "wire_version": {"const": COMMIT_WIRE_VERSION},
        }
    )


def distributed_commit_value_payload_schema() -> dict[str, Any]:
    proposal = distributed_commit_proposal_payload_schema()["properties"]
    excluded = {
        "local_receipt_ref",
        "portable_certificate_ref",
        "proposal_digest",
        "proposal_id",
        "proposal_version",
        "proposed_at_step",
        "commit_value_root",
    }
    properties = {
        name: deepcopy(schema)
        for name, schema in proposal.items()
        if name not in excluded
    }
    properties["value_version"] = {
        "const": "pheroos-distributed-commit-value-v1"
    }
    return strict_object_schema(properties)


def quorum_witness_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "assurance": {"const": "distributed"},
            "attestation_ref": canonical_text_schema(),
            "candidate_id": canonical_text_schema(),
            "epoch": authority_integer_schema(),
            "expires_at_step": authority_integer_schema(),
            "failure_domain": canonical_text_schema(),
            "commit_value_root": fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "nonce": canonical_text_schema(),
            "principal_cluster_id": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "profile": {"const": "pheroos-distributed-commit-v1"},
            "proposal_digest": fingerprint_schema(),
            "protocol_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "run_id": canonical_text_schema(),
            "target": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
            "witness_id": canonical_text_schema(),
            "witness_version": {"const": "pheroos-quorum-witness-v1"},
            "witnessed_at_step": authority_integer_schema(),
        }
    )


def witness_verification_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "authority": governance_authority_schema(),
            "expires_at_step": authority_integer_schema(),
            "principal_verification_ref": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
            "verification_id": canonical_text_schema(),
            "verification_version": {"const": "pheroos-witness-verification-v1"},
            "verified_at_step": authority_integer_schema(),
            "verifier_id": canonical_text_schema(),
            "witness": quorum_witness_payload_schema(),
            "witness_fingerprint": fingerprint_schema(),
            "witness_signing_root": fingerprint_schema(),
        }
    )


def witness_replay_receipt_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "candidate_id": canonical_text_schema(),
            "commit_value_root": fingerprint_schema(),
            "epoch": authority_integer_schema(),
            "nonce": canonical_text_schema(),
            "principal_cluster_id": canonical_text_schema(),
            "principal_id": canonical_text_schema(),
            "proposal_digest": fingerprint_schema(),
            "target": canonical_text_schema(),
            "verification_id": canonical_text_schema(),
            "witness_fingerprint": fingerprint_schema(),
            "witness_id": canonical_text_schema(),
        }
    )


def witness_equivocation_finding_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "epoch": authority_integer_schema(),
            "finding_id": fingerprint_schema(),
            "commit_value_roots": fingerprint_set_schema(minimum=2),
            "principal_cluster_id": canonical_text_schema(),
            "proposal_digests": fingerprint_set_schema(minimum=1),
            "target": canonical_text_schema(),
            "witness_fingerprints": fingerprint_set_schema(minimum=2),
        }
    )


def final_certificate_registration_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "candidate_id": canonical_text_schema(),
            "certificate_ref": fingerprint_schema(),
            "commit_value_root": fingerprint_schema(),
            "proposal_digest": fingerprint_schema(),
            "registered_at_step": authority_integer_schema(),
        }
    )


def certificate_conflict_finding_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "candidate_ids": canonical_text_set_schema(),
            "certificate_refs": fingerprint_set_schema(minimum=2),
            "commit_value_roots": fingerprint_set_schema(minimum=2),
            "detected_at_step": authority_integer_schema(),
            "epoch": authority_integer_schema(),
            "finding_id": fingerprint_schema(),
            "proposal_digests": fingerprint_set_schema(minimum=1),
            "target": canonical_text_schema(),
        }
    )


def distributed_commit_state_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **distributed_binding_properties(),
            "authority": governance_authority_schema(),
            "chain_id": fingerprint_schema(),
            "conflict_findings": {
                "type": "array",
                "items": certificate_conflict_finding_schema(),
                "uniqueItems": True,
            },
            "current_step": authority_integer_schema(),
            "epoch_transition_certificate_ref": optional_fingerprint_schema(),
            "equivocation_findings": {
                "type": "array",
                "items": witness_equivocation_finding_schema(),
                "uniqueItems": True,
            },
            "excluded_cluster_ids": canonical_text_set_schema(),
            "final_registrations": {
                "type": "array",
                "items": final_certificate_registration_schema(),
                "uniqueItems": True,
            },
            "frozen": {"type": "boolean"},
            "initialized_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "max_byzantine_faults": authority_integer_schema(),
            "membership_epoch_state_root": fingerprint_schema(),
            "membership_root": fingerprint_schema(),
            "membership_size": positive_authority_integer_schema(),
            "membership_snapshot": portable_membership_snapshot_payload_schema(),
            "membership_snapshot_root": fingerprint_schema(),
            "minimum_failure_domain_diversity": positive_authority_integer_schema(),
            "previous_state_fingerprint": optional_fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "revision": authority_integer_schema(),
            "trace_event_id": canonical_text_schema(),
            "transitioned": {"type": "boolean"},
            "witness_quorum": positive_authority_integer_schema(),
            "witness_receipt_root": fingerprint_schema(),
            "witness_ttl_steps": positive_authority_integer_schema(),
            "witness_verifications": {
                "type": "array",
                "items": witness_verification_payload_schema(),
                "uniqueItems": True,
            },
        }
    )


def distributed_commit_certificate_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **distributed_binding_properties(),
            "authority": governance_authority_schema(),
            "candidate_id": canonical_text_schema(),
            "canonicalization": {"const": "pheroos-commit-canonical-v1"},
            "certificate_body_root": fingerprint_schema(),
            "certificate_id": canonical_text_schema(),
            "certificate_root": fingerprint_schema(),
            "commit_value_root": fingerprint_schema(),
            "certificate_version": {
                "const": "pheroos-distributed-commit-certificate-v1"
            },
            "excluded_cluster_ids": canonical_text_set_schema(),
            "hash_algorithm": {"const": "sha256"},
            "issued_at_step": authority_integer_schema(),
            "issuer_id": canonical_text_schema(),
            "max_byzantine_faults": authority_integer_schema(),
            "membership_root": fingerprint_schema(),
            "membership_size": positive_authority_integer_schema(),
            "membership_snapshot": portable_membership_snapshot_payload_schema(),
            "membership_snapshot_root": fingerprint_schema(),
            "minimum_failure_domain_diversity": positive_authority_integer_schema(),
            "portable_certificate_ref": fingerprint_schema(),
            "portable_certificate_version": {
                "const": "pheroos-evidence-commit-certificate-v1"
            },
            "proposal": distributed_commit_proposal_payload_schema(),
            "proposal_digest": fingerprint_schema(),
            "provenance": canonical_text_schema(),
            "schema_discriminator": {"const": "distributed_commit_certificate"},
            "status": {"enum": ["final", "provisional"]},
            "trace_event_id": canonical_text_schema(),
            "wire_version": {"const": COMMIT_WIRE_VERSION},
            "witness_quorum": positive_authority_integer_schema(),
            "witness_root": fingerprint_schema(),
            "witnesses": {
                "type": "array",
                "items": witness_verification_payload_schema(),
                "minItems": 1,
                "uniqueItems": True,
            },
        }
    )


def epoch_transition_certificate_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            "assurance": {"const": "distributed"},
            "authority": governance_authority_schema(),
            "canonicalization": {"const": "pheroos-commit-canonical-v1"},
            "certificate_body_root": fingerprint_schema(),
            "certificate_id": canonical_text_schema(),
            "certificate_root": fingerprint_schema(),
            "certificate_version": {
                "const": "pheroos-epoch-transition-certificate-v1"
            },
            "commit_policy_root": fingerprint_schema(),
            "declared_recovery_ref": optional_fingerprint_schema(),
            "declared_transition_rule": canonical_text_schema(),
            "hash_algorithm": {"const": "sha256"},
            "issued_at_step": authority_integer_schema(),
            "issuer_attestation_refs": canonical_text_set_schema(minimum=1),
            "issuer_id": canonical_text_schema(),
            "manifest_root": fingerprint_schema(),
            "new_epoch": positive_authority_integer_schema(),
            "new_membership_epoch_state_root": fingerprint_schema(),
            "new_membership_root": fingerprint_schema(),
            "new_membership_snapshot": portable_membership_snapshot_payload_schema(),
            "new_membership_snapshot_root": fingerprint_schema(),
            "previous_epoch": authority_integer_schema(),
            "previous_membership_root": fingerprint_schema(),
            "prior_state_ref": fingerprint_schema(),
            "profile": {"const": "pheroos-distributed-commit-v1"},
            "protocol_id": canonical_text_schema(),
            "provenance": canonical_text_schema(),
            "recovery_permission_root": optional_fingerprint_schema(),
            "recovery_required": {"type": "boolean"},
            "recovery_stop_root": optional_fingerprint_schema(),
            "run_id": canonical_text_schema(),
            "schema_discriminator": {"const": "epoch_transition_certificate"},
            "target": canonical_text_schema(),
            "trace_event_id": canonical_text_schema(),
            "transition_permission_root": fingerprint_schema(),
            "transition_stop_root": fingerprint_schema(),
            "wire_version": {"const": COMMIT_WIRE_VERSION},
        }
    )


def distributed_finality_decision_payload_schema() -> dict[str, Any]:
    return strict_object_schema(
        {
            **distributed_binding_properties(),
            "authoritative_commit": {"type": "boolean"},
            "candidate_id": canonical_text_schema(),
            "current_step": authority_integer_schema(),
            "decision_version": {"const": "pheroos-distributed-finality-decision-v1"},
            "distributed_certificate_ref": optional_fingerprint_schema(),
            "kind": {
                "enum": [
                    "final",
                    "finality_unavailable",
                    "non_commit_terminal",
                    "pending",
                    "provisional",
                    "safety_violation",
                ]
            },
            "local_receipt_ref": fingerprint_schema(),
            "outcome_ref": optional_fingerprint_schema(),
            "reason_codes": canonical_text_set_schema(minimum=1),
            "state_ref": fingerprint_schema(),
            "terminal": {"type": "boolean"},
        }
    )


def commit_binding_properties() -> dict[str, Any]:
    return {
        "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
        "commit_policy_root": fingerprint_schema(),
        "epoch": authority_integer_schema(),
        "manifest_root": fingerprint_schema(),
        "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
        "protocol_id": canonical_text_schema(),
        "run_id": canonical_text_schema(),
        "target": canonical_text_schema(),
    }


def strict_object_schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(required or properties),
        "properties": properties,
        "additionalProperties": False,
    }


def canonical_text_schema() -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "pattern": r"^\S(?:.*\S)?$"}


def optional_text_schema() -> dict[str, Any]:
    return {"oneOf": [{"const": ""}, canonical_text_schema()]}


def authority_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 0,
        "maximum": MAX_AUTHORITY_INTEGER,
        "x-pheroos-exact-integer": True,
    }


def positive_authority_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_AUTHORITY_INTEGER,
        "x-pheroos-exact-integer": True,
    }


def signed_authority_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": -MAX_AUTHORITY_INTEGER,
        "maximum": MAX_AUTHORITY_INTEGER,
        "x-pheroos-exact-integer": True,
    }


def scaled_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 0,
        "maximum": WEIGHT_SCALE,
        "x-pheroos-exact-integer": True,
    }


def positive_scaled_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": WEIGHT_SCALE,
        "x-pheroos-exact-integer": True,
    }


def fingerprint_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": FINGERPRINT_PATTERN}


def optional_fingerprint_schema() -> dict[str, Any]:
    return {"oneOf": [{"const": ""}, fingerprint_schema()]}


def optional_enum_schema(values: tuple[str, ...]) -> dict[str, Any]:
    return {"enum": ["", *sorted(values)]}


def governance_authority_schema() -> dict[str, Any]:
    return {"type": "integer", "enum": [4, 5], "x-pheroos-exact-integer": True}


def action_schema() -> dict[str, Any]:
    return {"enum": sorted(item.value for item in CommitAction)}


def canonical_text_set_schema(*, minimum: int = 0) -> dict[str, Any]:
    return {
        "type": "array",
        "items": canonical_text_schema(),
        "minItems": minimum,
        "uniqueItems": True,
    }


def fingerprint_set_schema(*, minimum: int = 0) -> dict[str, Any]:
    return {
        "type": "array",
        "items": fingerprint_schema(),
        "minItems": minimum,
        "uniqueItems": True,
    }


def terminal_outcome_set_schema(
    *,
    allowed: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"enum": sorted(allowed or SUPPORTED_TERMINAL_OUTCOMES)},
        "uniqueItems": True,
    }


__all__ = ["commit_schema", "validate_commit_wire_record"]
