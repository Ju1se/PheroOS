from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.protocol.commit_models import (
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_COMMIT_PROFILES,
)
from pheroos.protocol.commit_wire import (
    canonical_commit_set,
    commit_payload_fingerprint,
)
from pheroos.governance.errors import GovernanceError

from pheroos.governance._schema.common import (
    AUTHORITY_PROFILE,
    CommitWireBinding,
    CommitWireContract,
    _ASSESSMENT_LINEAGE_ROOTS,
    _CANDIDATE_LINEAGE_ROOTS,
    _validate_assessment_lineage_semantics,
    _validate_canonical_set,
    _validate_interval,
    _validate_lexical_set,
    _validate_sealed_heartbeat_semantics,
    authority_integer_schema,
    canonical_text_schema,
    canonical_text_set_schema,
    commit_binding_properties,
    fingerprint_schema,
    fingerprint_set_schema,
    governance_authority_schema,
    optional_enum_schema,
    optional_fingerprint_schema,
    optional_text_schema,
    no_semantic_authority,
    positive_authority_integer_schema,
    profile_agnostic,
    scaled_integer_schema,
    signed_authority_integer_schema,
    strict_object_schema,
)

from pheroos.governance._schema.foundation import candidate_claim_binding_schema


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
                dict.fromkeys(
                    candidate_id
                    for candidate_id in candidate_ids
                    if candidate_id != fallback_id
                )
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
        payload["support_cluster_satisfied"] and payload["support_ratio_satisfied"]
    )
    if combined_support is not (
        payload["active_support_clusters"] >= payload["support_threshold_clusters"]
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
                (item["candidate_id"], item[item_root_name]) for item in metrics
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
    _validate_commit_assessment_metrics(
        metrics,
        errors=errors,
    )
    _validate_commit_assessment_roots(
        payload,
        metrics,
        profile=profile,
        errors=errors,
    )
    expected_leader, expected_ties = _commit_assessment_argmax(
        metrics,
        errors=errors,
    )
    expected_unique, expected_ready = _validate_commit_assessment_leader_fields(
        payload,
        metrics=metrics,
        expected_leader=expected_leader,
        expected_ties=expected_ties,
        errors=errors,
    )
    _validate_commit_assessment_status(
        payload,
        expected_unique=expected_unique,
        expected_ready=expected_ready,
        errors=errors,
    )
    return errors


def _validate_commit_assessment_metrics(
    metrics: list[Mapping[str, Any]],
    *,
    errors: list[str],
) -> None:
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


def _validate_commit_assessment_roots(
    payload: Mapping[str, Any],
    metrics: list[Mapping[str, Any]],
    *,
    profile: str,
    errors: list[str],
) -> None:
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


def _commit_assessment_argmax(
    metrics: list[Mapping[str, Any]],
    *,
    errors: list[str],
) -> tuple[str, list[str]]:
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
                (
                    score
                    for name, score in scores.items()
                    if name != item["candidate_id"]
                ),
                default=0,
            )
            expected_margin = item["net_evidence"] - max(other_best, 0)
            if item["margin"] != expected_margin:
                errors.append(
                    f"$.payload.candidate_metrics[{index}].margin: argmax margin mismatch"
                )
            if item["unique_leader"] is not (item["candidate_id"] == expected_leader):
                errors.append(
                    f"$.payload.candidate_metrics[{index}].unique_leader: argmax mismatch"
                )
    return expected_leader, expected_ties


def _validate_commit_assessment_leader_fields(
    payload: Mapping[str, Any],
    *,
    metrics: list[Mapping[str, Any]],
    expected_leader: str,
    expected_ties: list[str],
    errors: list[str],
) -> tuple[bool, bool]:
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
    return expected_unique, expected_ready


def _validate_commit_assessment_status(
    payload: Mapping[str, Any],
    *,
    expected_unique: bool,
    expected_ready: bool,
    errors: list[str],
) -> None:
    if payload["status"] == "ready" and not (expected_unique and expected_ready):
        errors.append("$.payload.status: ready requires one fully gated leader")
    if payload["status"] == "safety_violation" and not (
        payload["equivocation_finding_ids"] or payload["replay_conflict_references"]
    ):
        errors.append("$.payload.status: safety violation lacks concrete finding")


def _validate_commit_window_semantics(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    errors: list[str] = []
    _validate_commit_window_roots(payload, profile=profile, errors=errors)
    _validate_commit_window_progress(payload, errors=errors)
    has_assessment = bool(payload["last_assessment_ref"])
    window_lineage = {
        "assessment_ref": payload["last_assessment_ref"],
        "context_ref": payload["last_context_ref"],
        **{name: payload[name] for name in _ASSESSMENT_LINEAGE_ROOTS},
        **{name: payload[name] for name in _CANDIDATE_LINEAGE_ROOTS},
    }
    errors.extend(_validate_assessment_lineage_semantics(window_lineage))
    _validate_commit_window_assessment_metadata(
        payload,
        has_assessment=has_assessment,
        errors=errors,
    )
    _validate_commit_window_ready_state(
        payload,
        has_assessment=has_assessment,
        errors=errors,
    )
    if payload["reset_budget_exhausted"] and payload["last_ready"]:
        errors.append("$.payload: exhausted reset budget retained a ready window")
    return errors


def _validate_commit_window_roots(
    payload: Mapping[str, Any],
    *,
    profile: str,
    errors: list[str],
) -> None:
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


def _validate_commit_window_progress(
    payload: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    if payload["revision"] == 0:
        if payload["previous_state_fingerprint"]:
            errors.append(
                "$.payload.previous_state_fingerprint: initial state has predecessor"
            )
    elif not payload["previous_state_fingerprint"]:
        errors.append(
            "$.payload.previous_state_fingerprint: advanced state lacks predecessor"
        )
    if payload["last_evaluated_step"] < payload["initialized_at_step"]:
        errors.append("$.payload.last_evaluated_step: predates initialization")
    if payload["last_evaluated_step"] >= payload["absolute_deadline_step"]:
        errors.append("$.payload: window survived its deadline")
    if payload["absolute_deadline_step"] > payload["absolute_run_deadline_step"]:
        errors.append("$.payload: deadline exceeds run deadline")
    if payload["absolute_deadline_step"] <= payload["initialized_at_step"]:
        errors.append(
            "$.payload.absolute_deadline_step: deadline must follow initialization"
        )


def _validate_commit_window_assessment_metadata(
    payload: Mapping[str, Any],
    *,
    has_assessment: bool,
    errors: list[str],
) -> None:
    if has_assessment:
        if not payload["last_assessment_status"]:
            errors.append(
                "$.payload.last_assessment_status: assessment status is absent"
            )
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


def _validate_commit_window_ready_state(
    payload: Mapping[str, Any],
    *,
    has_assessment: bool,
    errors: list[str],
) -> None:
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
            errors.append(
                "$.payload: ready window does not end at latest ready assessment"
            )
    elif payload["leader_candidate_id"] or payload["window_count"] != 0 or references:
        errors.append("$.payload: non-ready window must be empty")


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
        return ["$.payload.certificate_kind: kind does not match assurance"]
    return []


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
    _validate_commit_replay_receipts(receipts, errors=errors)
    expected_root = commit_payload_fingerprint(
        {
            "receipt_fingerprints": [
                _replay_receipt_fingerprint(item, profile=profile) for item in receipts
            ]
        },
        schema="pheroos-commit-replay-receipt-root-v1",
        profile=profile,
    )
    if payload["receipt_root"] != expected_root:
        errors.append("$.payload.receipt_root: reconstructable root mismatch")
    _validate_commit_replay_revision(payload, receipts=receipts, errors=errors)
    return errors


def _validate_commit_replay_receipts(
    receipts: list[Mapping[str, Any]],
    *,
    errors: list[str],
) -> None:
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


def _validate_commit_replay_revision(
    payload: Mapping[str, Any],
    *,
    receipts: list[Mapping[str, Any]],
    errors: list[str],
) -> None:
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


COMMIT_CONTRACTS: tuple[CommitWireContract, ...] = (
    CommitWireContract(
        "pheroos-commit-evaluation-context-v1",
        commit_evaluation_context_payload_schema,
        profile_agnostic(_validate_commit_context_semantics),
    ),
    CommitWireContract(
        "pheroos-candidate-commit-metrics-v1",
        candidate_commit_metrics_payload_schema,
        profile_agnostic(_validate_candidate_metrics_semantics),
        binding=CommitWireBinding.UNBOUND,
    ),
    CommitWireContract(
        "pheroos-optimal-commit-assessment-v1",
        commit_assessment_payload_schema,
        _validate_commit_assessment_semantics,
    ),
    CommitWireContract(
        "pheroos-commit-window-state-v1",
        commit_window_state_payload_schema,
        _validate_commit_window_semantics,
    ),
    CommitWireContract(
        "pheroos-commit-window-seal-v1",
        commit_window_seal_payload_schema,
        profile_agnostic(_validate_commit_window_seal_semantics),
    ),
    CommitWireContract(
        "pheroos-commit-liveness-input-v1",
        commit_liveness_input_payload_schema,
        profile_agnostic(_validate_commit_liveness_input_semantics),
    ),
    CommitWireContract(
        "pheroos-commit-finality-verification-v1",
        commit_finality_verification_payload_schema,
        profile_agnostic(_validate_commit_finality_verification_semantics),
    ),
    CommitWireContract(
        "pheroos-commit-replay-state-v1",
        commit_replay_state_payload_schema,
        _validate_commit_replay_state_semantics,
    ),
    CommitWireContract(
        "pheroos-commit-replay-receipt-v1",
        replay_receipt_payload_schema,
        no_semantic_authority,
        binding=CommitWireBinding.UNBOUND,
    ),
)

__all__: tuple[str, ...] = ()
