"""Current verified dependency material for Commit Evidence v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pheroos.governance._commit_evidence_owner_v2.context import (
    CommitEvidenceContextV2,
)
from pheroos.governance._commit_evidence_owner_v2.replay_projection import (
    commit_evidence_replay_receipts_for_target_v2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
)
from pheroos.governance._commit_state_v2.contracts import CommitReplaySnapshotV2
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.principal_verification_contracts import (
    PrincipalVerificationSetSnapshotV2,
)


@dataclass(frozen=True, slots=True)
class _DependencyMaterialV2:
    membership: MembershipSnapshotV2
    membership_head_root: str
    verification: PrincipalVerificationSetSnapshotV2
    verification_head_root: str
    replay: CommitReplaySnapshotV2
    replay_head_root: str


def _dependency_material(
    verification_state: object,
    membership_state: object,
    replay_state: object,
) -> _DependencyMaterialV2:
    from pheroos.governance._commit_state_v2.operations import (
        VerifiedCommitReplayStateV2,
        _verified_state_view as _replay_view,
        require_current_commit_replay_state_v2,
    )
    from pheroos.governance._support_v2.membership_operations import (
        VerifiedMembershipStateV2,
        _verified_state_view as _membership_view,
        require_current_membership_state_v2,
    )
    from pheroos.governance._support_v2.principal_verification_operations import (
        VerifiedPrincipalVerificationSetStateV2,
        _verified_state_view as _verification_view,
        require_current_principal_verification_set_v2,
    )

    if type(verification_state) is not VerifiedPrincipalVerificationSetStateV2:
        raise TypeError("commit evidence requires verified principal state v2")
    if type(membership_state) is not VerifiedMembershipStateV2:
        raise TypeError("commit evidence requires verified membership state v2")
    if type(replay_state) is not VerifiedCommitReplayStateV2:
        raise TypeError("commit evidence requires verified commit replay state v2")
    verification = require_current_principal_verification_set_v2(verification_state)
    membership = require_current_membership_state_v2(membership_state)
    replay = require_current_commit_replay_state_v2(replay_state)
    _, verification_view = _verification_view(verification_state)
    _, membership_view = _membership_view(membership_state)
    _, replay_view = _replay_view(replay_state)
    assert verification_view.committed_transition is not None
    assert membership_view.committed_transition is not None
    assert replay_view.committed_transition is not None
    return _DependencyMaterialV2(
        membership=membership,
        membership_head_root=membership_view.committed_transition.receipt.head_root,
        verification=verification,
        verification_head_root=verification_view.committed_transition.receipt.head_root,
        replay=replay,
        replay_head_root=replay_view.committed_transition.receipt.head_root,
    )


def _validate_dependency_context(
    dependency: _DependencyMaterialV2,
    *,
    context: CommitEvidenceContextV2,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    epoch: int,
    current_step: int,
) -> None:
    membership = dependency.membership
    verification = dependency.verification
    expected = (
        domain_root,
        scope_ref,
        context.profile,
        context.assurance,
        context.authority_policy_root,
        context.manifest_root,
        context.commit_policy_root,
        context.protocol_ref,
        run_ref,
        context.target_ref,
        epoch,
    )
    fields = (
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
    if tuple(getattr(membership, field) for field in fields) != expected:
        raise ValueError("commit evidence membership dependency is cross-bound")
    if tuple(getattr(verification, field) for field in fields) != expected:
        raise ValueError("commit evidence verification dependency is cross-bound")
    if not (
        membership.issued_at_step <= current_step < membership.expires_at_step
        and verification.current_step <= current_step < verification.expires_at_step
    ):
        raise ValueError("commit evidence dependencies are stale")
    relation = (
        membership.verification_stream_ref,
        membership.verification_transition_id,
        membership.verification_revision,
        membership.verification_head_root,
        membership.verification_snapshot_root,
        membership.verification_set_root,
    )
    actual = (
        verification.stream_ref,
        verification.transition_id,
        verification.revision,
        dependency.verification_head_root,
        verification.snapshot_root,
        verification.verification_set_root,
    )
    if relation != actual:
        raise ValueError("commit evidence membership does not bind verification")
    _validate_replay_context(
        dependency.replay,
        context=context,
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        epoch=epoch,
        current_step=current_step,
    )


def _validate_replay_context(
    replay: CommitReplaySnapshotV2,
    *,
    context: CommitEvidenceContextV2,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    epoch: int,
    current_step: int,
) -> None:
    fields = (
        "domain_root",
        "scope_ref",
        "manifest_root",
        "commit_policy_root",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
    )
    expected = (
        domain_root,
        scope_ref,
        context.manifest_root,
        context.commit_policy_root,
        context.profile,
        context.assurance,
        context.protocol_ref,
        run_ref,
        context.target_ref,
    )
    if tuple(getattr(replay, field) for field in fields) != expected:
        raise ValueError("commit evidence replay dependency is cross-bound")
    if replay.observed_epoch != epoch or replay.current_step > current_step:
        raise ValueError("commit evidence replay dependency is stale or cross-epoch")


def _validate_replay_coverage(
    records: Sequence[QualifiedCommitEvidenceV2],
    dependency: _DependencyMaterialV2,
    *,
    context: CommitEvidenceContextV2,
    epoch: int,
    current_step: int,
) -> None:
    available = {item.receipt_root for item in dependency.replay.receipts}
    for record in records:
        current = (
            record.status is CommitEvidenceStatusV2.ACTIVE
            and record.epoch == epoch
            and record.qualification_policy_root == context.evidence_policy.policy_root
            and record.membership_root == dependency.membership.membership_root
            and record.verification_set_root
            == dependency.verification.verification_set_root
            and record.observed_at_step <= current_step < record.expires_at_step
        )
        if not current:
            continue
        receipts = commit_evidence_replay_receipts_for_target_v2(
            record,
            target_ref=context.target_ref,
        )
        if any(item.receipt_root not in available for item in receipts):
            raise ValueError("qualified evidence is absent from current replay state")


__all__: tuple[str, ...] = ()
