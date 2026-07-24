"""Pure complete-replacement reducer for durable certificate state."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._commit_certificate_v2.enums import (
    CommitCertificateMutationKindV2,
    CommitCertificateStatusV2,
)
from pheroos.governance._commit_certificate_v2.portable_envelope import (
    PortableCommitCertificateV2,
)
from pheroos.governance._commit_certificate_v2.request import CommitCertificateRequestV2
from pheroos.governance._commit_certificate_v2.state_contracts import (
    COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2,
    CommitCertificateIdentityBindingV2,
    CommitCertificateSnapshotV2,
)


def _reduce_snapshot(
    request: CommitCertificateRequestV2,
    *,
    parent: CommitCertificateSnapshotV2 | None,
    source_context_root: str,
) -> CommitCertificateSnapshotV2:
    certificate = request.certificate
    binding = CommitCertificateIdentityBindingV2(
        certificate_id=certificate.certificate_id,
        body_root=certificate.body.body_root,
        first_envelope_root=certificate.envelope_root,
    )
    identities: tuple[CommitCertificateIdentityBindingV2, ...] = (
        () if parent is None else tuple(parent.identity_bindings)
    )
    envelopes: tuple[str, ...]
    matching = tuple(
        item for item in identities if item.certificate_id == certificate.certificate_id
    )
    reasons: tuple[str, ...] = ("certificate_verified",)
    mutation = CommitCertificateMutationKindV2.VERIFIED
    status = CommitCertificateStatusV2.VERIFIED
    conflicts: tuple[str, ...] = ()
    if parent is None:
        identities = (binding,)
        envelopes = (certificate.envelope_root,)
    else:
        envelopes = tuple(
            sorted(set(parent.envelope_roots) | {certificate.envelope_root})
        )
        if not matching:
            identities = (*identities, binding)
        conflict_reason = _conflict_reason(parent, certificate, matching)
        if conflict_reason:
            mutation = CommitCertificateMutationKindV2.CONFLICT
            status = CommitCertificateStatusV2.CONFLICT
            reasons = (conflict_reason,)
            conflicts = tuple(
                sorted(
                    set(parent.conflicting_body_roots)
                    | {parent.certificate.body.body_root, certificate.body.body_root}
                )
            )
        elif certificate.body.body_root == parent.certificate.body.body_root:
            mutation = CommitCertificateMutationKindV2.SEMANTIC_RETRY
            reasons = ("certificate_semantic_retry",)
        else:
            reasons = ("certificate_new_epoch_verified",)
    return CommitCertificateSnapshotV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        protocol_ref=request.protocol_ref,
        run_ref=request.run_ref,
        target_ref=request.target_ref,
        stream_ref=request.stream_ref,
        mutation_ref=request.mutation_ref,
        mutation_issuer_ref=request.mutation_issuer_ref,
        transition_id=request.transition_id,
        revision=1 if parent is None else parent.revision + 1,
        parent_revision=0 if parent is None else parent.revision,
        parent_transition_id=(
            COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2
            if parent is None
            else parent.transition_id
        ),
        parent_snapshot_root=(
            COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
            if parent is None
            else parent.snapshot_root
        ),
        current_step=request.current_step,
        mutation_kind=mutation,
        status=status,
        certificate=certificate,
        identity_bindings=identities,
        envelope_roots=envelopes,
        conflicting_body_roots=conflicts,
        reason_codes=reasons,
        parent_history_root=(
            COMMIT_CERTIFICATE_GENESIS_HISTORY_ROOT_V2
            if parent is None
            else parent.history_root
        ),
        parent_history_count=0 if parent is None else parent.history_count,
        history_root="",
        history_count=1 if parent is None else parent.history_count + 1,
        source_context_root=source_context_root,
    )


def _conflict_reason(
    parent: CommitCertificateSnapshotV2,
    certificate: PortableCommitCertificateV2,
    matching: Sequence[CommitCertificateIdentityBindingV2],
) -> str:
    if parent.status is CommitCertificateStatusV2.CONFLICT:
        return "certificate_conflict_sticky"
    if matching and matching[0].body_root != certificate.body.body_root:
        return "certificate_identity_body_conflict"
    old = parent.certificate.body
    new = certificate.body
    if old.seal_root == new.seal_root and old.body_root != new.body_root:
        return "certificate_semantic_conflict"
    if old.seal_root != new.seal_root and new.epoch <= old.epoch:
        return "certificate_seal_conflict"
    return ""


__all__: tuple[str, ...] = ()
