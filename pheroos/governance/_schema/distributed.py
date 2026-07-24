from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pheroos.protocol.commit_models import COMMIT_WIRE_VERSION
from pheroos.protocol.commit_wire import commit_payload_fingerprint

from pheroos.governance._schema.common import (
    CommitWireBinding,
    CommitWireContract,
    _validate_interval,
    authority_integer_schema,
    canonical_text_schema,
    canonical_text_set_schema,
    fingerprint_schema,
    fingerprint_set_schema,
    governance_authority_schema,
    optional_fingerprint_schema,
    no_semantic_authority,
    positive_authority_integer_schema,
    profile_agnostic,
    strict_object_schema,
)


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
        errors.append(
            f"{path}.eligible_clusters: principal belongs to multiple clusters"
        )
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
    _validate_distributed_state_authority(payload, profile=profile, errors=errors)
    membership = payload["membership_snapshot"]
    _validate_distributed_state_membership(payload, membership, errors=errors)
    verifications = payload["witness_verifications"]
    _validate_distributed_state_verifications(
        payload,
        verifications,
        profile=profile,
        errors=errors,
    )
    expected_receipt_root = _witness_receipt_root(verifications, profile=profile)
    if payload["witness_receipt_root"] != expected_receipt_root:
        errors.append("$.payload.witness_receipt_root: reconstructable root mismatch")
    _validate_distributed_state_equivocation(
        payload,
        verifications,
        errors=errors,
    )
    _validate_distributed_state_finality(payload, errors=errors)
    return errors


def _validate_distributed_state_authority(
    payload: Mapping[str, Any],
    *,
    profile: str,
    errors: list[str],
) -> None:
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
            errors.append(
                "$.payload.previous_state_fingerprint: initial state has predecessor"
            )
    elif not payload["previous_state_fingerprint"]:
        errors.append(
            "$.payload.previous_state_fingerprint: advanced state lacks predecessor"
        )
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


def _validate_distributed_state_membership(
    payload: Mapping[str, Any],
    membership: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
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
            errors.append(
                f"$.payload.membership_snapshot.{name}: state binding mismatch"
            )


def _validate_distributed_state_verifications(
    payload: Mapping[str, Any],
    verifications: list[Mapping[str, Any]],
    *,
    profile: str,
    errors: list[str],
) -> None:
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
        for name in (
            "profile",
            "assurance",
            "protocol_id",
            "run_id",
            "target",
            "epoch",
        ):
            if witness[name] != payload[name]:
                errors.append(
                    f"$.payload.witness_verifications[{index}].witness.{name}: state binding mismatch"
                )
        if witness["membership_root"] != payload["membership_root"]:
            errors.append(
                f"$.payload.witness_verifications[{index}].witness.membership_root: state binding mismatch"
            )


def _validate_distributed_state_equivocation(
    payload: Mapping[str, Any],
    verifications: list[Mapping[str, Any]],
    *,
    errors: list[str],
) -> None:
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
        errors.append(
            "$.payload.excluded_cluster_ids: equivocation projection mismatch"
        )


def _validate_distributed_state_finality(
    payload: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
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
    membership = payload["membership_snapshot"]
    _validate_distributed_certificate_membership(
        payload,
        membership,
        errors=errors,
    )
    proposal = payload["proposal"]
    _validate_distributed_certificate_proposal_binding(
        payload,
        proposal,
        errors=errors,
    )
    verifications = payload["witnesses"]
    clusters, domains = _validate_distributed_certificate_witnesses(
        payload,
        verifications,
        profile=profile,
        errors=errors,
    )
    _validate_distributed_certificate_roots(
        payload,
        verifications=verifications,
        clusters=clusters,
        domains=domains,
        profile=profile,
        errors=errors,
    )
    return errors


def _validate_distributed_certificate_membership(
    payload: Mapping[str, Any],
    membership: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
    if not _quorum_intersection_is_safe(
        payload["membership_size"],
        payload["max_byzantine_faults"],
        payload["witness_quorum"],
    ):
        errors.append("$.payload: Byzantine quorum intersection is unsafe")
    if payload["minimum_failure_domain_diversity"] > payload["witness_quorum"]:
        errors.append("$.payload.minimum_failure_domain_diversity: unreachable")
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


def _validate_distributed_certificate_proposal_binding(
    payload: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    errors: list[str],
) -> None:
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


def _validate_distributed_certificate_witnesses(
    payload: Mapping[str, Any],
    verifications: list[Mapping[str, Any]],
    *,
    profile: str,
    errors: list[str],
) -> tuple[list[str], set[str]]:
    refs = [
        _witness_verification_fingerprint(item, profile=profile)
        for item in verifications
    ]
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
    return clusters, domains


def _validate_distributed_certificate_roots(
    payload: Mapping[str, Any],
    *,
    verifications: list[Mapping[str, Any]],
    clusters: list[str],
    domains: set[str],
    profile: str,
    errors: list[str],
) -> None:
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
            errors.append(
                f"$.payload.new_membership_snapshot.{name}: transition binding mismatch"
            )
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
        payload["terminal"] or payload["authoritative_commit"] or payload["outcome_ref"]
    ):
        errors.append("$.payload: pending/provisional finality cannot be terminal")
    if kind == "pending" and payload["distributed_certificate_ref"]:
        errors.append(
            "$.payload.distributed_certificate_ref: pending finality has proof"
        )
    if kind == "provisional" and not payload["distributed_certificate_ref"]:
        errors.append(
            "$.payload.distributed_certificate_ref: provisional proof is absent"
        )
    if kind == "final":
        if (
            not payload["authoritative_commit"]
            or not payload["distributed_certificate_ref"]
        ):
            errors.append("$.payload: final distributed decision lacks authority")
    elif payload["authoritative_commit"]:
        errors.append(
            "$.payload.authoritative_commit: non-final decision claims commit"
        )
    if payload["terminal"] is not bool(payload["outcome_ref"]):
        errors.append("$.payload.outcome_ref: terminal/outcome binding mismatch")
    if (
        kind in {"finality_unavailable", "non_commit_terminal"}
        and not payload["terminal"]
    ):
        errors.append("$.payload.terminal: non-commit finality must be terminal")
    return errors


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
            "local_receipt_version": {"const": "pheroos-local-commit-receipt-v1"},
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
    properties["value_version"] = {"const": "pheroos-distributed-commit-value-v1"}
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
            "certificate_version": {"const": "pheroos-epoch-transition-certificate-v1"},
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


DISTRIBUTED_CONTRACTS: tuple[CommitWireContract, ...] = (
    CommitWireContract(
        "pheroos-portable-membership-snapshot-v1",
        portable_membership_snapshot_payload_schema,
        _validate_portable_membership_semantics,
    ),
    CommitWireContract(
        "pheroos-distributed-commit-proposal-v1",
        distributed_commit_proposal_payload_schema,
        _validate_distributed_proposal_semantics,
    ),
    CommitWireContract(
        "pheroos-distributed-commit-value-v1",
        distributed_commit_value_payload_schema,
        _validate_distributed_commit_value_semantics,
    ),
    CommitWireContract(
        "pheroos-quorum-witness-v1",
        quorum_witness_payload_schema,
        _validate_quorum_witness_semantics,
    ),
    CommitWireContract(
        "pheroos-witness-verification-v1",
        witness_verification_payload_schema,
        _validate_witness_verification_semantics,
        binding=CommitWireBinding.UNBOUND,
        profiles=("pheroos-distributed-commit-v1",),
    ),
    CommitWireContract(
        "pheroos-witness-replay-receipt-v1",
        witness_replay_receipt_payload_schema,
        no_semantic_authority,
        binding=CommitWireBinding.UNBOUND,
        profiles=("pheroos-distributed-commit-v1",),
    ),
    CommitWireContract(
        "pheroos-distributed-commit-state-v1",
        distributed_commit_state_payload_schema,
        _validate_distributed_state_semantics,
    ),
    CommitWireContract(
        "pheroos-distributed-commit-certificate-v1",
        distributed_commit_certificate_payload_schema,
        _validate_distributed_certificate_semantics,
    ),
    CommitWireContract(
        "pheroos-epoch-transition-certificate-v1",
        epoch_transition_certificate_payload_schema,
        _validate_epoch_transition_semantics,
    ),
    CommitWireContract(
        "pheroos-distributed-finality-decision-v1",
        distributed_finality_decision_payload_schema,
        profile_agnostic(_validate_distributed_finality_semantics),
    ),
)

__all__: tuple[str, ...] = ()
