"""Current-dependency qualification and source proof for Commit Evidence v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import cast

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2

from pheroos.governance._commit_evidence_owner_v2.context import (
    CommitEvidenceContextV2,
    commit_evidence_context_v2,
)
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2,
    COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2,
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceSnapshotV2,
    commit_evidence_stream_ref_v2,
    commit_evidence_transition_id_v2,
)
from pheroos.governance._commit_evidence_owner_v2.dependencies import (
    _DependencyMaterialV2,
    _dependency_material,
    _validate_dependency_context,
    _validate_replay_coverage,
)
from pheroos.governance._commit_evidence_owner_v2.proposals import (
    CommitEvidenceAttestationV2,
    CommitEvidenceRevocationV2,
    CounterevidenceDispositionProposalV2,
    canonical_attestations_v2,
    canonical_dispositions_v2,
    canonical_revocations_v2,
)
from pheroos.governance._commit_evidence_owner_v2.qualification import (
    qualify_commit_evidence_v2,
)
from pheroos.governance._commit_evidence_owner_v2.source_proof import (
    VerifiedCommitEvidenceSourceV2,
    _issue_source,
    _verified_source,
)
from pheroos.governance._commit_evidence_projection_v2.common import (
    canonical_roots_v2,
    require_count_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
    canonical_qualified_evidence_v2,
)


@dataclass(frozen=True, slots=True)
class _ParentLineageV2:
    parent_revision: int
    parent_epoch: int | None
    parent_transition_id: str
    parent_snapshot_root: str
    parent_history_root: str
    parent_history_count: int
    initialized_at_step: int


def prepare_commit_evidence_advance_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    epoch: int,
    observed_epoch: int,
    advance_ref: str,
    current_step: int,
    mutation_issuer_ref: str,
    mutation_provenance_root: str,
    mutation_trace_roots: Sequence[str],
    principal_verification_state: object,
    membership_state: object,
    commit_replay_state: object,
    attestations: Sequence[CommitEvidenceAttestationV2],
    dispositions: Sequence[CounterevidenceDispositionProposalV2],
    revocations: Sequence[CommitEvidenceRevocationV2] = (),
    parent_snapshot: CommitEvidenceSnapshotV2 | None = None,
) -> tuple[CommitEvidenceAdvanceRequestV2, VerifiedCommitEvidenceSourceV2]:
    """Prepare a complete replacement from current verified dependencies."""

    _validate_prepare_scalars(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        advance_ref=advance_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        mutation_provenance_root=mutation_provenance_root,
        epoch=epoch,
        observed_epoch=observed_epoch,
        current_step=current_step,
    )
    context = commit_evidence_context_v2(
        manifest, profile=profile, target_ref=target_ref
    )
    dependency = _dependency_material(
        principal_verification_state,
        membership_state,
        commit_replay_state,
    )
    _validate_dependency_context(
        dependency,
        context=context,
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        epoch=epoch,
        current_step=current_step,
    )
    parent = _validated_parent(
        parent_snapshot,
        domain_root=domain_root,
        scope_ref=scope_ref,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        current_step=current_step,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
    )
    attestation_values = canonical_attestations_v2(attestations)
    disposition_values = canonical_dispositions_v2(dispositions)
    revocation_values = canonical_revocations_v2(revocations)
    parent_records = () if parent is None else tuple(parent.records)
    retained, removed_roots, revoked_records = _apply_revocations(
        parent_records, revocation_values, current_step=current_step
    )
    qualification_traces = canonical_roots_v2(
        mutation_trace_roots,
        "commit evidence mutation_trace_roots",
        allow_empty=False,
    )
    additions = qualify_commit_evidence_v2(
        context=context,
        membership=dependency.membership,
        verification=dependency.verification,
        epoch=epoch,
        current_step=current_step,
        qualification_issuer_ref=mutation_issuer_ref,
        qualification_provenance_root=mutation_provenance_root,
        qualification_trace_roots=qualification_traces,
        attestations=attestation_values,
        dispositions=disposition_values,
        existing_records=retained,
    )
    records = canonical_qualified_evidence_v2((*retained, *additions))
    _validate_replay_coverage(
        records,
        dependency,
        context=context,
        epoch=epoch,
        current_step=current_step,
    )
    lineage = _parent_lineage(parent, current_step=current_step)
    stream_ref = commit_evidence_stream_ref_v2(
        scope_ref, context.protocol_ref, run_ref, target_ref
    )
    transition_id = commit_evidence_transition_id_v2(stream_ref, advance_ref)
    mutation_records = tuple(
        sorted((*[item.record_root for item in additions], *revoked_records))
    )
    snapshot = CommitEvidenceSnapshotV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        profile=profile,
        assurance=context.assurance,
        authority_policy_root=context.authority_policy_root,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        evidence_policy=context.evidence_policy,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        revision=lineage.parent_revision + 1,
        initialized_at_step=lineage.initialized_at_step,
        current_step=current_step,
        expires_at_step=min(
            dependency.membership.expires_at_step,
            dependency.verification.expires_at_step,
        ),
        parent_revision=lineage.parent_revision,
        parent_epoch=lineage.parent_epoch,
        parent_transition_id=lineage.parent_transition_id,
        parent_snapshot_root=lineage.parent_snapshot_root,
        parent_history_root=lineage.parent_history_root,
        parent_history_count=lineage.parent_history_count,
        mutation_issuer_ref=mutation_issuer_ref,
        mutation_provenance_root=mutation_provenance_root,
        mutation_trace_roots=qualification_traces,
        membership_stream_ref=dependency.membership.stream_ref,
        membership_transition_id=dependency.membership.transition_id,
        membership_revision=dependency.membership.revision,
        membership_head_root=dependency.membership_head_root,
        membership_snapshot_root=dependency.membership.snapshot_root,
        membership_root=dependency.membership.membership_root,
        membership_current_step=dependency.membership.issued_at_step,
        membership_expires_at_step=dependency.membership.expires_at_step,
        verification_stream_ref=dependency.verification.stream_ref,
        verification_transition_id=dependency.verification.transition_id,
        verification_revision=dependency.verification.revision,
        verification_head_root=dependency.verification_head_root,
        verification_snapshot_root=dependency.verification.snapshot_root,
        verification_set_root=dependency.verification.verification_set_root,
        verification_current_step=dependency.verification.current_step,
        verification_expires_at_step=dependency.verification.expires_at_step,
        replay_stream_ref=dependency.replay.stream_ref,
        replay_transition_id=dependency.replay.transition_id,
        replay_revision=dependency.replay.revision,
        replay_head_root=dependency.replay_head_root,
        replay_snapshot_root=dependency.replay.snapshot_root,
        replay_receipt_root=dependency.replay.receipt_root,
        replay_current_step=dependency.replay.current_step,
        records=records,
        mutation_record_roots=mutation_records,
        removed_record_roots=removed_roots,
        revocation_roots=tuple(item.revocation_root for item in revocation_values),
        record_count=len(records),
        active_record_count=_active_count(
            records, context, dependency, epoch, current_step
        ),
        history_count=lineage.parent_history_count + 1,
    )
    request = CommitEvidenceAdvanceRequestV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        snapshot=snapshot,
    )
    source = _issue_source(
        request,
        context,
        dependency,
        principal_verification_state,
        membership_state,
        commit_replay_state,
        attestations=attestation_values,
        dispositions=disposition_values,
        revocations=revocation_values,
    )
    return request, source


def verify_commit_evidence_request_source_v2(
    request: CommitEvidenceAdvanceRequestV2,
    *,
    source: object,
) -> None:
    if type(request) is not CommitEvidenceAdvanceRequestV2:
        raise TypeError("commit evidence source requires exact request v2")
    source_request, _ = _verified_source(source)
    if source_request.to_dict() != request.to_dict():
        raise ValueError("commit evidence source belongs to another request")


def _apply_revocations(
    records: Sequence[QualifiedCommitEvidenceV2],
    revocations: Sequence[CommitEvidenceRevocationV2],
    *,
    current_step: int,
) -> tuple[tuple[QualifiedCommitEvidenceV2, ...], tuple[str, ...], tuple[str, ...]]:
    by_ref = {item.record_ref: item for item in records}
    removed: list[str] = []
    replacements: list[str] = []
    for revocation in revocations:
        record = by_ref.get(revocation.record_ref)
        if (
            record is None
            or record.status is not CommitEvidenceStatusV2.ACTIVE
            or record.record_root != revocation.record_root
            or revocation.revoked_at_step != current_step
        ):
            raise ValueError("commit evidence revocation is stale or cross-bound")
        revoked = replace(
            record,
            status=CommitEvidenceStatusV2.REVOKED,
            revoked_at_step=revocation.revoked_at_step,
            revocation_root=revocation.revocation_root,
            revocation_provenance_root=revocation.provenance_root,
            revocation_trace_roots=tuple(revocation.trace_roots),
            record_root="",
        )
        by_ref[record.record_ref] = revoked
        removed.append(record.record_root)
        replacements.append(revoked.record_root)
    return (
        canonical_qualified_evidence_v2(tuple(by_ref.values())),
        tuple(sorted(removed)),
        tuple(sorted(replacements)),
    )


def _validated_parent(
    parent: CommitEvidenceSnapshotV2 | None, **context: object
) -> CommitEvidenceSnapshotV2 | None:
    if parent is None:
        return None
    if type(parent) is not CommitEvidenceSnapshotV2:
        raise TypeError("commit evidence parent must be exact snapshot v2")
    detached = CommitEvidenceSnapshotV2.from_dict(parent.to_dict())
    for field in ("domain_root", "scope_ref", "protocol_ref", "run_ref", "target_ref"):
        if getattr(detached, field) != context[field]:
            raise ValueError("commit evidence parent fixed lineage is cross-bound")
    epoch = cast(int, context["epoch"])
    current_step = cast(int, context["current_step"])
    if epoch < detached.epoch or current_step <= detached.current_step:
        raise ValueError("commit evidence epoch or current_step moves backwards")
    policy_changed = (
        detached.manifest_root != context["manifest_root"]
        or detached.commit_policy_root != context["commit_policy_root"]
    )
    if policy_changed and epoch <= detached.epoch:
        raise ValueError("commit evidence policy rotation requires a new epoch")
    return detached


def _parent_lineage(
    parent: CommitEvidenceSnapshotV2 | None, *, current_step: int
) -> _ParentLineageV2:
    if parent is None:
        return _ParentLineageV2(
            parent_revision=0,
            parent_epoch=None,
            parent_transition_id=COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2,
            parent_snapshot_root=COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2,
            parent_history_root=COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2,
            parent_history_count=0,
            initialized_at_step=current_step,
        )
    return _ParentLineageV2(
        parent_revision=parent.revision,
        parent_epoch=parent.epoch,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        initialized_at_step=parent.initialized_at_step,
    )


def _validate_prepare_scalars(**values: object) -> None:
    for field in ("domain_root", "mutation_provenance_root"):
        require_root_v2(values[field], f"commit evidence source {field}")
    for field in (
        "scope_ref",
        "run_ref",
        "target_ref",
        "advance_ref",
        "mutation_issuer_ref",
    ):
        require_text_v2(values[field], f"commit evidence source {field}")
    for field in ("epoch", "observed_epoch", "current_step"):
        require_count_v2(values[field], f"commit evidence source {field}")


def _active_count(
    records: Sequence[QualifiedCommitEvidenceV2],
    context: CommitEvidenceContextV2,
    dependency: _DependencyMaterialV2,
    epoch: int,
    current_step: int,
) -> int:
    return sum(
        1
        for item in records
        if item.status is CommitEvidenceStatusV2.ACTIVE
        and item.epoch == epoch
        and item.qualification_policy_root == context.evidence_policy.policy_root
        and item.membership_root == dependency.membership.membership_root
        and item.verification_set_root == dependency.verification.verification_set_root
        and item.observed_at_step <= current_step < item.expires_at_step
    )


__all__ = [
    "VerifiedCommitEvidenceSourceV2",
    "prepare_commit_evidence_advance_v2",
    "verify_commit_evidence_request_source_v2",
]
