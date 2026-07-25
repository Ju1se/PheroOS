"""Opaque-owner composition for current distributed proposal authority."""

from __future__ import annotations

from dataclasses import dataclass
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import (
    CommitAssurance,
    CollectiveCommitPolicy,
    DistributedCommitPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint

from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._commit_certificate_v2.state_contracts import (
    CommitCertificateSnapshotV2,
)
from pheroos.governance._commit_certificate_v2.state_handle import (
    VerifiedCommitCertificateStateV2,
    _verified_commit_certificate_finality_context_material_v2,
    _verified_commit_certificate_finality_context_v2,
    _verified_commit_certificate_state_material_v2,
)
from pheroos.governance._commit_decision_v2.seal_context import (
    _CommitDecisionSealContextMaterialV2,
    _verified_commit_decision_seal_context_material_v2,
    _verified_commit_decision_seal_context_v2,
)
from pheroos.governance._commit_decision_v2.state_handle import (
    VerifiedCommitDecisionStateV2,
)
from pheroos.governance._distributed_v2.dependency_contracts import (
    DistributedDependencyV2,
)
from pheroos.governance._distributed_v2.enums import DistributedDependencyRoleV2
from pheroos.governance._distributed_v2.policy import (
    DistributedPolicyBindingV2,
    distributed_policy_binding_v2,
    validate_distributed_membership_v2,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitValueV2,
)
from pheroos.governance._support_v2.membership_contracts import (
    MembershipSnapshotV2,
)
from pheroos.governance._support_v2.membership_operations import (
    VerifiedMembershipStateV2,
)
from pheroos.governance._support_v2.support_state_access import (
    _membership_parent_authority_material_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitViewV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _DistributedAuthorityContextV2:
    manifest: ScopedProtocolManifestV2
    policy: DistributedCommitPolicy
    policy_binding: DistributedPolicyBindingV2
    decision: _CommitDecisionSealContextMaterialV2
    central_snapshot: CommitCertificateSnapshotV2
    membership: MembershipSnapshotV2
    decision_dependency: DistributedDependencyV2
    central_dependency: DistributedDependencyV2
    membership_dependency: DistributedDependencyV2
    verification_dependency: DistributedDependencyV2


def _distributed_authority_context_v2(
    *,
    decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    manifest: ScopedProtocolManifestV2,
    current_step: int,
) -> _DistributedAuthorityContextV2:
    if type(decision_state) is not VerifiedCommitDecisionStateV2:
        raise TypeError("distributed authority requires verified Decision state")
    if type(central_certificate_state) is not VerifiedCommitCertificateStateV2:
        raise TypeError("distributed authority requires verified central certificate")
    if type(membership_state) is not VerifiedMembershipStateV2:
        raise TypeError("distributed authority requires verified Membership state")
    decision = _verified_commit_decision_seal_context_material_v2(
        _verified_commit_decision_seal_context_v2(decision_state)
    )
    finality = _verified_commit_certificate_finality_context_material_v2(
        _verified_commit_certificate_finality_context_v2(
            central_certificate_state,
            sealed_decision_state=decision_state,
            current_step=current_step,
        )
    )
    central = _verified_commit_certificate_state_material_v2(central_certificate_state)
    if finality.projection.status.value != "verified":
        raise ValueError("distributed authority requires verified central certificate")
    detached, policy, binding = _validated_manifest(manifest, decision)
    membership, membership_precondition, verification_precondition = (
        _membership_parent_authority_material_v2(membership_state)
    )
    _validate_membership_context(
        membership,
        decision=decision,
        binding=binding,
        current_step=current_step,
    )
    membership_view = _dependency_view(
        decision.reader,
        membership.scope_ref,
        membership.stream_ref,
        membership.transition_id,
    )
    verification_view = _dependency_view(
        decision.reader,
        membership.scope_ref,
        membership.verification_stream_ref,
        membership.verification_transition_id,
    )
    membership_dependency = _dependency(
        DistributedDependencyRoleV2.MEMBERSHIP,
        membership_view,
        snapshot_root=membership.snapshot_root,
    )
    verification_dependency = _dependency(
        DistributedDependencyRoleV2.PRINCIPAL_VERIFICATION,
        verification_view,
        snapshot_root=membership.verification_snapshot_root,
    )
    if (
        membership_dependency.revision != membership_precondition.expected_revision
        or membership_dependency.head_root != membership_precondition.expected_root
        or verification_dependency.revision
        != verification_precondition.expected_revision
        or verification_dependency.head_root != verification_precondition.expected_root
    ):
        raise ValueError("distributed Membership/PV heads changed during preparation")
    assert central.view.committed_transition is not None
    central_dependency = DistributedDependencyV2(
        role=DistributedDependencyRoleV2.CENTRAL_CERTIFICATE,
        stream_ref=central.snapshot.stream_ref,
        revision=central.snapshot.revision,
        transition_id=central.snapshot.transition_id,
        snapshot_root=central.snapshot.snapshot_root,
        head_root=central.head.head_root,
        receipt_root=central.view.committed_transition.receipt.receipt_root,
        inclusion_root=(
            central.view.committed_transition.inclusion_proof.inclusion_root
        ),
    )
    decision_dependency = DistributedDependencyV2(
        role=DistributedDependencyRoleV2.DECISION,
        stream_ref=decision.snapshot.stream_ref,
        revision=decision.snapshot.revision,
        transition_id=decision.snapshot.transition_id,
        snapshot_root=decision.snapshot.snapshot_root,
        head_root=decision.decision_head.head_root,
        receipt_root=decision.current_inclusion.receipt_root,
        inclusion_root=decision.current_inclusion.inclusion_root,
    )
    return _DistributedAuthorityContextV2(
        manifest=detached,
        policy=policy,
        policy_binding=binding,
        decision=decision,
        central_snapshot=CommitCertificateSnapshotV2.from_dict(
            central.snapshot.to_dict()
        ),
        membership=MembershipSnapshotV2.from_dict(membership.to_dict()),
        decision_dependency=decision_dependency,
        central_dependency=central_dependency,
        membership_dependency=membership_dependency,
        verification_dependency=verification_dependency,
    )


def _distributed_value_v2(
    context: _DistributedAuthorityContextV2,
) -> DistributedCommitValueV2:
    decision = context.decision
    central = context.central_snapshot
    body = central.certificate.body
    membership = context.membership
    return DistributedCommitValueV2(
        domain_root=body.domain_root,
        scope_ref=body.scope_ref,
        profile=body.profile,
        assurance=body.assurance,
        protocol_ref=body.protocol_ref,
        run_ref=body.run_ref,
        target_ref=body.target_ref,
        epoch=body.epoch,
        candidate_ref=body.candidate_ref,
        claim_root=body.claim_root,
        output_contract_root=body.output_contract_root,
        output_payload_root=body.output_payload_root,
        decision_stream_ref=body.decision_stream_ref,
        decision_revision=body.decision_revision,
        decision_transition_id=body.decision_transition_id,
        decision_snapshot_root=body.decision_snapshot_root,
        decision_head_root=body.decision_head_root,
        decision_receipt_root=body.decision_receipt_root,
        decision_inclusion_root=body.decision_inclusion_root,
        decision_current_revision=decision.snapshot.revision,
        decision_current_transition_id=decision.snapshot.transition_id,
        decision_current_snapshot_root=decision.snapshot.snapshot_root,
        decision_current_head_root=decision.decision_head.head_root,
        decision_current_receipt_root=decision.current_inclusion.receipt_root,
        decision_current_inclusion_root=decision.current_inclusion.inclusion_root,
        seal_transition_id=decision.seal_inclusion.transition_id,
        seal_snapshot_root=decision.seal_inclusion.snapshot_root,
        seal_receipt_root=decision.seal_inclusion.receipt_root,
        seal_inclusion_root=decision.seal_inclusion.inclusion_root,
        seal_root=decision.seal_inclusion.seal_root,
        frozen_dependency_root=decision.seal_inclusion.frozen_dependency_root,
        manifest_root=body.manifest_root,
        commit_policy_root=body.commit_policy_root,
        authority_leaf_set_root=body.authority_leaf_set_root,
        membership_stream_ref=membership.stream_ref,
        membership_revision=membership.revision,
        membership_transition_id=membership.transition_id,
        membership_snapshot_root=membership.snapshot_root,
        membership_head_root=context.membership_dependency.head_root,
        membership_root=membership.membership_root,
        verification_stream_ref=membership.verification_stream_ref,
        verification_revision=membership.verification_revision,
        verification_transition_id=membership.verification_transition_id,
        verification_snapshot_root=membership.verification_snapshot_root,
        verification_head_root=context.verification_dependency.head_root,
        verification_set_root=membership.verification_set_root,
        central_certificate_stream_ref=central.stream_ref,
        central_certificate_revision=central.revision,
        central_certificate_transition_id=central.transition_id,
        central_certificate_snapshot_root=central.snapshot_root,
        central_certificate_head_root=context.central_dependency.head_root,
        central_certificate_receipt_root=context.central_dependency.receipt_root,
        central_certificate_inclusion_root=context.central_dependency.inclusion_root,
        central_certificate_body=body,
    )


def _validated_manifest(
    manifest: ScopedProtocolManifestV2,
    decision: _CommitDecisionSealContextMaterialV2,
) -> tuple[
    ScopedProtocolManifestV2, DistributedCommitPolicy, DistributedPolicyBindingV2
]:
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("distributed authority requires exact scoped manifest")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    policy = detached.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("distributed manifest lacks collective commit policy")
    distributed = policy.distributed
    if type(distributed) is not DistributedCommitPolicy:
        raise ValueError("distributed manifest lacks static epoch policy")
    snapshot = decision.snapshot
    if (
        snapshot.assurance is not CommitAssurance.DISTRIBUTED
        or detached.manifest_root != snapshot.manifest_root
        or detached.id != snapshot.protocol_ref
        or policy.assurance != CommitAssurance.DISTRIBUTED.value
        or policy.target != snapshot.target_ref
        or policy.certificate.mode != "distributed"
        or commit_policy_fingerprint(policy, profile=snapshot.profile)
        != snapshot.commit_policy_root
    ):
        raise ValueError("distributed manifest is cross-bound")
    binding = distributed_policy_binding_v2(
        distributed,
        policy_root=snapshot.commit_policy_root,
    )
    return detached, distributed, binding


def _validate_membership_context(
    membership: MembershipSnapshotV2,
    *,
    decision: _CommitDecisionSealContextMaterialV2,
    binding: DistributedPolicyBindingV2,
    current_step: int,
) -> None:
    snapshot = decision.snapshot
    expected = (
        snapshot.domain_root,
        snapshot.scope_ref,
        snapshot.profile,
        snapshot.assurance,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
        snapshot.epoch,
    )
    observed = (
        membership.domain_root,
        membership.scope_ref,
        membership.profile,
        membership.assurance,
        membership.manifest_root,
        membership.commit_policy_root,
        membership.protocol_ref,
        membership.run_ref,
        membership.target_ref,
        membership.epoch,
    )
    if observed != expected:
        raise ValueError("distributed membership is cross-bound")
    validate_distributed_membership_v2(membership, binding, current_step=current_step)
    if not (
        membership.verification_current_step
        <= current_step
        < membership.verification_expires_at_step
    ):
        raise ValueError("distributed principal verification is stale")


def _dependency_view(
    reader: GovernanceStateReaderV2,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
) -> GovernanceCommitViewV2:
    return _canonical_commit_view_v2(
        reader.load_commit_view_v2(scope_ref, stream_ref, transition_id)
    )


def _dependency(
    role: DistributedDependencyRoleV2,
    view: GovernanceCommitViewV2,
    *,
    snapshot_root: str,
) -> DistributedDependencyV2:
    if view.committed_transition is None:
        raise ValueError("distributed dependency has no committed transition")
    receipt = view.committed_transition.receipt
    inclusion = view.committed_transition.inclusion_proof
    return DistributedDependencyV2(
        role=role,
        stream_ref=receipt.stream_ref,
        revision=receipt.revision,
        transition_id=receipt.transition_id,
        snapshot_root=snapshot_root,
        head_root=receipt.head_root,
        receipt_root=receipt.receipt_root,
        inclusion_root=inclusion.inclusion_root,
    )


__all__: tuple[str, ...] = ()
