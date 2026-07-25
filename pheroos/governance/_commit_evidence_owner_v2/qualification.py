"""Deterministic, policy-bound qualification of Evidence v2 proposals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.membership_records import MembershipPrincipalV2
from pheroos.governance._support_v2.principal_verification_contracts import (
    PrincipalVerificationSetSnapshotV2,
)
from pheroos.governance._support_v2.principal_verification_records import (
    PrincipalVerificationRecordV2,
)
from pheroos.governance._commit_replay_namespace import ReplayNamespace
from pheroos.governance._commit_state_v2.contracts import CommitReplayReceiptV2

from pheroos.governance._commit_evidence_owner_v2.context import (
    CommitEvidenceContextV2,
)
from pheroos.governance._commit_evidence_owner_v2.proposals import (
    CommitEvidenceAttestationV2,
    CounterevidenceDispositionProposalV2,
    canonical_attestations_v2,
    canonical_dispositions_v2,
)
from pheroos.governance._commit_evidence_projection_v2.common import (
    canonical_roots_v2,
    evidence_root_v2,
    require_count_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceDispositionV2,
    CommitEvidenceKindV2,
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
)


@dataclass(frozen=True, slots=True)
class _PrincipalMaterialV2:
    membership: MembershipPrincipalV2
    verification: PrincipalVerificationRecordV2
    cluster_ref: str


def qualify_commit_evidence_v2(
    *,
    context: CommitEvidenceContextV2,
    membership: MembershipSnapshotV2,
    verification: PrincipalVerificationSetSnapshotV2,
    epoch: int,
    current_step: int,
    qualification_issuer_ref: str,
    qualification_provenance_root: str,
    qualification_trace_roots: Sequence[str],
    attestations: Sequence[CommitEvidenceAttestationV2],
    dispositions: Sequence[CounterevidenceDispositionProposalV2],
    existing_records: Sequence[QualifiedCommitEvidenceV2],
) -> tuple[QualifiedCommitEvidenceV2, ...]:
    """Qualify additions against exact current membership and policy material."""

    step = require_count_v2(current_step, "commit evidence qualification current_step")
    subject_epoch = require_count_v2(epoch, "commit evidence qualification epoch")
    issuer = require_text_v2(
        qualification_issuer_ref, "commit evidence qualification issuer"
    )
    provenance = require_root_v2(
        qualification_provenance_root,
        "commit evidence qualification provenance_root",
    )
    traces = canonical_roots_v2(
        qualification_trace_roots,
        "commit evidence qualification trace_roots",
        allow_empty=False,
    )
    proposals = canonical_attestations_v2(attestations)
    disposition_values = canonical_dispositions_v2(dispositions)
    _validate_context_dependencies(
        context, membership, verification, epoch=subject_epoch, current_step=step
    )
    principals = _principal_material(membership, verification)
    by_counter = {item.counter_attestation_root: item for item in disposition_values}
    counter_roots = {
        item.attestation_root
        for item in proposals
        if item.kind is CommitEvidenceKindV2.COUNTER
    }
    if set(by_counter) != counter_roots:
        raise ValueError(
            "each new counter attestation requires exactly one disposition"
        )
    additions = tuple(
        _qualify_one(
            item,
            disposition=by_counter.get(item.attestation_root),
            context=context,
            principal=principals.get(item.principal_ref),
            membership=membership,
            verification=verification,
            epoch=subject_epoch,
            current_step=step,
            issuer=issuer,
            provenance=provenance,
            traces=traces,
        )
        for item in proposals
    )
    _validate_identity_additions(existing_records, additions)
    combined = (*tuple(existing_records), *additions)
    _validate_relational_evidence(combined, additions, current_step=step)
    return additions


def _qualify_one(
    attestation: CommitEvidenceAttestationV2,
    *,
    disposition: CounterevidenceDispositionProposalV2 | None,
    context: CommitEvidenceContextV2,
    principal: _PrincipalMaterialV2 | None,
    membership: MembershipSnapshotV2,
    verification: PrincipalVerificationSetSnapshotV2,
    epoch: int,
    current_step: int,
    issuer: str,
    provenance: str,
    traces: tuple[str, ...],
) -> QualifiedCommitEvidenceV2:
    if principal is None:
        raise ValueError(
            "evidence principal is absent from current verified membership"
        )
    _validate_attestation_binding(attestation, context, epoch, current_step)
    if attestation.kind is CommitEvidenceKindV2.CHALLENGE:
        quality = relevance = materiality = criticality = 0
    else:
        quality = attestation.reported_quality_ppm
        relevance = attestation.reported_relevance_ppm
        materiality = attestation.reported_materiality_ppm
        criticality = attestation.reported_criticality_ppm
        if quality < context.evidence_policy.minimum_quality_ppm:
            raise ValueError("evidence quality is below the declared policy floor")
        if relevance < context.evidence_policy.minimum_relevance_ppm:
            raise ValueError("evidence relevance is below the declared policy floor")
    expiry = min(
        attestation.expires_at_step,
        membership.expires_at_step,
        verification.expires_at_step,
    )
    if disposition is not None:
        if not disposition.issued_at_step <= current_step < disposition.expires_at_step:
            raise ValueError("counterevidence disposition is not fresh")
        expiry = min(expiry, disposition.expires_at_step)
    qualification_root = evidence_root_v2(
        "qualification",
        {
            "attestation_root": attestation.attestation_root,
            "disposition_root": ""
            if disposition is None
            else disposition.disposition_root,
            "manifest_root": context.manifest_root,
            "commit_policy_root": context.commit_policy_root,
            "evidence_policy_root": context.evidence_policy.policy_root,
            "membership_root": membership.membership_root,
            "verification_set_root": verification.verification_set_root,
            "epoch": epoch,
            "current_step": current_step,
            "qualification_issuer_ref": issuer,
            "qualification_provenance_root": provenance,
            "qualification_trace_roots": list(traces),
        },
    )
    replay_roots = _receipt_roots(
        attestation, disposition, target_ref=context.target_ref
    )
    return QualifiedCommitEvidenceV2(
        record_ref=attestation.evidence_ref,
        kind=attestation.kind,
        status=CommitEvidenceStatusV2.ACTIVE,
        candidate_ref=attestation.candidate_ref,
        claim_root=attestation.claim_root,
        epoch=attestation.epoch,
        principal_ref=attestation.principal_ref,
        cluster_ref=principal.cluster_ref,
        failure_domain_ref=principal.membership.failure_domain_ref,
        membership_principal_root=principal.membership.principal_root,
        principal_verification_root=principal.verification.verification_root,
        attestation_root=attestation.attestation_root,
        payload_root=attestation.payload_root,
        source_ref=attestation.source_ref,
        independence_ref=attestation.independence_ref,
        quality_ppm=quality,
        relevance_ppm=relevance,
        materiality_ppm=materiality,
        criticality_ppm=criticality,
        weight_ppm=(quality * relevance) // context.evidence_policy.numeric_scale,
        category_ref=attestation.category_ref,
        execution_method=attestation.execution_method,
        execution_attestation_root=attestation.execution_attestation_root,
        execution_root=attestation.execution_root,
        challenge_result=attestation.challenge_result,
        result_root=attestation.result_root,
        result_observation_roots=tuple(attestation.result_observation_roots),
        disposition=(
            CommitEvidenceDispositionV2.NONE
            if disposition is None
            else disposition.disposition
        ),
        disposition_ref="" if disposition is None else disposition.disposition_ref,
        disposition_nonce="" if disposition is None else disposition.nonce,
        disposition_root="" if disposition is None else disposition.disposition_root,
        rebuttal_observation_roots=(
            () if disposition is None else tuple(disposition.rebuttal_observation_roots)
        ),
        resolution_root="" if disposition is None else disposition.resolution_root,
        reason_codes=() if disposition is None else tuple(disposition.reason_codes),
        nonce=attestation.nonce,
        observed_at_step=attestation.observed_at_step,
        qualified_at_step=current_step,
        expires_at_step=expiry,
        qualification_issuer_ref=issuer,
        qualification_root=qualification_root,
        qualification_policy_root=context.evidence_policy.policy_root,
        membership_root=membership.membership_root,
        verification_set_root=verification.verification_set_root,
        attestation_provenance_root=attestation.provenance_root,
        attestation_trace_roots=tuple(attestation.trace_roots),
        qualification_provenance_root=provenance,
        qualification_trace_roots=traces,
        revoked_at_step=None,
        revocation_root="",
        revocation_provenance_root="",
        revocation_trace_roots=(),
        replay_receipt_roots=replay_roots,
    )


def _principal_material(
    membership: MembershipSnapshotV2,
    verification: PrincipalVerificationSetSnapshotV2,
) -> dict[str, _PrincipalMaterialV2]:
    verified = {item.principal_ref: item for item in verification.records}
    result: dict[str, _PrincipalMaterialV2] = {}
    for cluster in membership.clusters:
        for principal in cluster.principals:
            record = verified.get(principal.principal_ref)
            if (
                record is None
                or principal.verification_root != record.verification_root
            ):
                raise ValueError(
                    "membership principal lacks its verified source record"
                )
            if (
                principal.failure_domain_ref != record.failure_domain_ref
                or principal.verified_issuer_ref != record.verification_issuer_ref
                or not principal.failure_domain_ref
            ):
                raise ValueError("evidence membership source identity is unverified")
            result[principal.principal_ref] = _PrincipalMaterialV2(
                membership=principal,
                verification=record,
                cluster_ref=cluster.cluster_ref,
            )
    return result


def _validate_context_dependencies(
    context: CommitEvidenceContextV2,
    membership: MembershipSnapshotV2,
    verification: PrincipalVerificationSetSnapshotV2,
    *,
    epoch: int,
    current_step: int,
) -> None:
    shared = (
        "domain_root",
        "scope_ref",
        "profile",
        "assurance",
        "authority_policy_root",
        "manifest_root",
        "commit_policy_root",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "epoch",
    )
    if any(
        getattr(membership, field) != getattr(verification, field) for field in shared
    ):
        raise ValueError("evidence membership and verification dependencies diverge")
    expected = (
        context.profile,
        context.assurance,
        context.authority_policy_root,
        context.manifest_root,
        context.commit_policy_root,
        context.protocol_ref,
        context.target_ref,
        epoch,
    )
    observed = (
        membership.profile,
        membership.assurance,
        membership.authority_policy_root,
        membership.manifest_root,
        membership.commit_policy_root,
        membership.protocol_ref,
        membership.target_ref,
        membership.epoch,
    )
    if observed != expected or verification.epoch != epoch:
        raise ValueError("evidence dependencies are cross-bound")
    if not (
        membership.issued_at_step <= current_step < membership.expires_at_step
        and verification.current_step <= current_step < verification.expires_at_step
    ):
        raise ValueError("evidence dependencies are not fresh")
    verification_binding = (
        membership.verification_stream_ref,
        membership.verification_transition_id,
        membership.verification_revision,
        membership.verification_snapshot_root,
        membership.verification_set_root,
    )
    actual = (
        verification.stream_ref,
        verification.transition_id,
        verification.revision,
        verification.snapshot_root,
        verification.verification_set_root,
    )
    if verification_binding != actual:
        raise ValueError("current membership does not bind current verification")


def _validate_attestation_binding(
    attestation: CommitEvidenceAttestationV2,
    context: CommitEvidenceContextV2,
    epoch: int,
    current_step: int,
) -> None:
    if (
        attestation.candidate_ref not in context.declared_candidate_refs
        or attestation.epoch != epoch
    ):
        raise ValueError("evidence attestation candidate or epoch is undeclared")
    if not attestation.observed_at_step <= current_step < attestation.expires_at_step:
        raise ValueError("evidence attestation is not fresh")
    if (
        attestation.expires_at_step - attestation.observed_at_step
        > context.evidence_policy.observation_ttl_steps
    ):
        raise ValueError("evidence attestation exceeds the declared TTL")


def _receipt_roots(
    attestation: CommitEvidenceAttestationV2,
    disposition: CounterevidenceDispositionProposalV2 | None,
    *,
    target_ref: str,
) -> tuple[str, ...]:
    namespace = (
        ReplayNamespace.CHALLENGE
        if attestation.kind is CommitEvidenceKindV2.CHALLENGE
        else ReplayNamespace.OBSERVATION
    )
    receipts = [
        CommitReplayReceiptV2(
            namespace=namespace,
            record_id=attestation.evidence_ref,
            nonce=attestation.nonce,
            payload_fingerprint=attestation.attestation_root,
            target_ref=target_ref,
            candidate_ref=attestation.candidate_ref,
            epoch=attestation.epoch,
            principal_ref=attestation.principal_ref,
        )
    ]
    if disposition is not None:
        receipts.append(
            CommitReplayReceiptV2(
                namespace=ReplayNamespace.COUNTEREVIDENCE_DISPOSITION,
                record_id=disposition.disposition_ref,
                nonce=disposition.nonce,
                payload_fingerprint=disposition.disposition_root,
                target_ref=target_ref,
                candidate_ref=attestation.candidate_ref,
                epoch=attestation.epoch,
                principal_ref=attestation.principal_ref,
            )
        )
    return tuple(sorted(item.receipt_root for item in receipts))


def _validate_identity_additions(
    existing: Sequence[QualifiedCommitEvidenceV2],
    additions: Sequence[QualifiedCommitEvidenceV2],
) -> None:
    identities = {
        "record_ref": {item.record_ref for item in existing},
        "nonce": {item.nonce for item in existing},
        "attestation_root": {item.attestation_root for item in existing},
        "disposition_nonce": {
            item.disposition_nonce for item in existing if item.disposition_nonce
        },
        "disposition_root": {
            item.disposition_root for item in existing if item.disposition_root
        },
    }
    for item in additions:
        for field, seen in identities.items():
            value = getattr(item, field)
            if value and value in seen:
                raise ValueError(f"commit evidence addition replays {field}")
            if value:
                seen.add(value)
        if item.disposition_nonce and item.disposition_nonce in identities["nonce"]:
            raise ValueError("counterevidence disposition replays an attestation nonce")


def _validate_relational_evidence(
    combined: Sequence[QualifiedCommitEvidenceV2],
    additions: Sequence[QualifiedCommitEvidenceV2],
    *,
    current_step: int,
) -> None:
    active = tuple(
        item
        for item in combined
        if item.status is CommitEvidenceStatusV2.ACTIVE
        and item.observed_at_step <= current_step < item.expires_at_step
    )
    positives = {
        item.attestation_root: item
        for item in active
        if item.kind is CommitEvidenceKindV2.POSITIVE
    }
    counters = {
        item.attestation_root: item
        for item in active
        if item.kind is CommitEvidenceKindV2.COUNTER
    }
    for item in additions:
        if item.kind is CommitEvidenceKindV2.CHALLENGE:
            results = tuple(
                counters.get(root) for root in item.result_observation_roots
            )
            if any(value is None for value in results) or any(
                not _same_subject(item, value) for value in results if value is not None
            ):
                raise ValueError("challenge result omits committed counter evidence")
        elif item.kind is CommitEvidenceKindV2.COUNTER:
            rebuttals = tuple(
                positives.get(root) for root in item.rebuttal_observation_roots
            )
            if any(value is None for value in rebuttals):
                raise ValueError("counter disposition refers to unavailable rebuttal")
            exact = tuple(value for value in rebuttals if value is not None)
            if any(not _same_subject(item, value) for value in exact):
                raise ValueError("counter rebuttal crosses candidate, claim, or epoch")
            _validate_rebuttal_independence(item, exact)


def _same_subject(
    owner: QualifiedCommitEvidenceV2,
    related: QualifiedCommitEvidenceV2,
) -> bool:
    return bool(
        related.candidate_ref == owner.candidate_ref
        and related.claim_root == owner.claim_root
        and related.epoch == owner.epoch
        and related.qualification_policy_root == owner.qualification_policy_root
        and related.membership_root == owner.membership_root
        and related.verification_set_root == owner.verification_set_root
    )


def _validate_rebuttal_independence(
    counter: QualifiedCommitEvidenceV2,
    rebuttals: Sequence[QualifiedCommitEvidenceV2],
) -> None:
    principals: set[str] = {counter.principal_ref}
    clusters: set[str] = {counter.cluster_ref}
    domains: set[str] = {counter.failure_domain_ref}
    for item in rebuttals:
        if (
            item.principal_ref in principals
            or item.cluster_ref in clusters
            or item.failure_domain_ref in domains
        ):
            raise ValueError(
                "counter rebuttal is not principal/cluster/domain independent"
            )
        principals.add(item.principal_ref)
        clusters.add(item.cluster_ref)
        domains.add(item.failure_domain_ref)


__all__ = [
    "qualify_commit_evidence_v2",
]
