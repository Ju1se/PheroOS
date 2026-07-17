from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_COMMIT_PROFILES,
    WEIGHT_SCALE,
)
from pheroos.protocol.commit_wire import commit_payload_fingerprint

from pheroos.governance._schema.common import (
    AUTHORITY_PROFILE,
    CommitWireBinding,
    CommitWireContract,
    EVIDENCE_BINDING_VERSION,
    _validate_canonical_set,
    _validate_interval,
    _validate_lexical_set,
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
    positive_scaled_integer_schema,
    scaled_integer_schema,
    signed_authority_integer_schema,
    strict_object_schema,
    terminal_outcome_set_schema,
)


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


SUPPORT_CONTRACTS: tuple[CommitWireContract, ...] = (
    CommitWireContract(
        "pheroos-observation-attestation-v1",
        observation_attestation_payload_schema,
        profile_agnostic(_validate_observation_attestation_semantics),
        binding=CommitWireBinding.UNBOUND,
        profiles=(AUTHORITY_PROFILE,),
    ),
    CommitWireContract(
        "pheroos-verified-observation-v1",
        verified_observation_payload_schema,
        profile_agnostic(_validate_verified_observation_semantics),
    ),
    CommitWireContract(
        "pheroos-counterevidence-disposition-v1",
        counterevidence_disposition_payload_schema,
        profile_agnostic(_validate_counterevidence_disposition_semantics),
    ),
    CommitWireContract(
        "pheroos-challenge-attestation-v1",
        challenge_attestation_payload_schema,
        profile_agnostic(_validate_challenge_attestation_semantics),
        binding=CommitWireBinding.UNBOUND,
        profiles=(AUTHORITY_PROFILE,),
    ),
    CommitWireContract(
        "pheroos-verified-challenge-v1",
        verified_challenge_payload_schema,
        profile_agnostic(_validate_verified_challenge_semantics),
    ),
    CommitWireContract(
        "pheroos-challenge-coverage-v1",
        challenge_coverage_payload_schema,
        profile_agnostic(_validate_challenge_coverage_semantics),
        binding=CommitWireBinding.UNBOUND,
    ),
    CommitWireContract(
        "pheroos-evidence-binding-authority-v1",
        evidence_binding_payload_schema,
        _validate_evidence_binding_semantics,
    ),
    CommitWireContract(
        "pheroos-evidence-summary-v1",
        evidence_summary_payload_schema,
        profile_agnostic(_validate_evidence_summary_semantics),
        binding=CommitWireBinding.UNBOUND,
    ),
    CommitWireContract(
        "pheroos-eligible-principal-snapshot-v1",
        eligible_principal_snapshot_payload_schema,
        _validate_membership_semantics,
    ),
    CommitWireContract(
        "pheroos-eligible-membership-epoch-state-v1",
        eligible_membership_epoch_state_payload_schema,
        _validate_membership_epoch_semantics,
    ),
    CommitWireContract(
        "pheroos-support-lease-proposal-v1",
        support_lease_proposal_payload_schema,
        no_semantic_authority,
    ),
    CommitWireContract(
        "pheroos-support-lease-replay-receipt-v1",
        support_lease_replay_receipt_payload_schema,
        profile_agnostic(_validate_support_replay_receipt_semantics),
    ),
    CommitWireContract(
        "pheroos-support-lease-replay-state-v1",
        support_lease_replay_state_payload_schema,
        _validate_support_replay_state_semantics,
        binding=CommitWireBinding.PROFILE,
    ),
    CommitWireContract(
        "pheroos-support-lease-v1",
        support_lease_payload_schema,
        _validate_support_lease_semantics,
    ),
    CommitWireContract(
        "pheroos-support-lease-revocation-v1",
        support_lease_revocation_payload_schema,
        no_semantic_authority,
    ),
    CommitWireContract(
        "pheroos-support-lease-evaluation-v1",
        support_lease_evaluation_payload_schema,
        _validate_support_evaluation_semantics,
    ),
    CommitWireContract(
        "pheroos-support-equivocation-finding-v1",
        support_equivocation_finding_payload_schema,
        _validate_equivocation_semantics,
    ),
    CommitWireContract(
        "pheroos-risk-assessment-chain-state-v1",
        risk_assessment_chain_state_payload_schema,
        _validate_risk_chain_state_semantics,
    ),
    CommitWireContract(
        "pheroos-risk-assessment-v1",
        risk_assessment_payload_schema,
        _validate_risk_assessment_semantics,
    ),
    CommitWireContract(
        "pheroos-commit-threshold-snapshot-v1",
        commit_threshold_snapshot_payload_schema,
        _validate_threshold_snapshot_semantics,
    ),
)

__all__: tuple[str, ...] = ()
