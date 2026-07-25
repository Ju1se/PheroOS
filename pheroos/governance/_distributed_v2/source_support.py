"""StateStore-current dependency helpers for distributed source preparation."""

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
from pheroos.governance._distributed_v2.authority_context import _dependency
from pheroos.governance._distributed_v2.dependency_contracts import (
    DistributedDependencyV2,
)
from pheroos.governance._distributed_v2.enums import (
    DistributedDependencyRoleV2,
    DistributedLaneV2,
)
from pheroos.governance._distributed_v2.policy import (
    DistributedPolicyBindingV2,
    distributed_policy_binding_v2,
    validate_distributed_membership_v2,
)
from pheroos.governance._distributed_v2.request import DistributedAdvanceRequestV2
from pheroos.governance._distributed_v2.state_contracts import (
    DistributedLaneSnapshotV2,
    distributed_lane_stream_ref_v2,
)
from pheroos.governance._distributed_v2.state_handle import (
    _verified_distributed_state_material_v2,
)
from pheroos.governance._distributed_v2.state_records import (
    _decode_committed_distributed_view_v2,
)
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.membership_operations import (
    VerifiedMembershipStateV2,
)
from pheroos.governance._support_v2.support_state_access import (
    _membership_handle_fields,
    _membership_parent_authority_material_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _EpochAuthorityContextV2:
    manifest: ScopedProtocolManifestV2
    policy: DistributedCommitPolicy
    policy_binding: DistributedPolicyBindingV2
    membership: MembershipSnapshotV2
    membership_dependency: DistributedDependencyV2
    verification_dependency: DistributedDependencyV2
    reader: GovernanceStateReaderV2
    domain: AuthorityDomainV2


def _epoch_authority_context_v2(
    *,
    membership_state: object,
    manifest: ScopedProtocolManifestV2,
    current_step: int,
) -> _EpochAuthorityContextV2:
    if type(membership_state) is not VerifiedMembershipStateV2:
        raise TypeError("distributed epoch requires verified Membership state")
    reader, domain, _ = _membership_handle_fields(membership_state)
    membership, membership_precondition, verification_precondition = (
        _membership_parent_authority_material_v2(membership_state)
    )
    detached, policy, binding = _manifest_for_membership(manifest, membership)
    validate_distributed_membership_v2(membership, binding, current_step=current_step)
    if not (
        membership.verification_current_step
        <= current_step
        < membership.verification_expires_at_step
    ):
        raise ValueError("distributed epoch principal verification is stale")
    membership_view = _canonical_commit_view_v2(
        reader.load_commit_view_v2(
            membership.scope_ref,
            membership.stream_ref,
            membership.transition_id,
        )
    )
    verification_view = _canonical_commit_view_v2(
        reader.load_commit_view_v2(
            membership.scope_ref,
            membership.verification_stream_ref,
            membership.verification_transition_id,
        )
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
        raise ValueError("distributed epoch Membership/PV changed during preparation")
    return _EpochAuthorityContextV2(
        manifest=detached,
        policy=policy,
        policy_binding=binding,
        membership=membership,
        membership_dependency=membership_dependency,
        verification_dependency=verification_dependency,
        reader=reader,
        domain=domain,
    )


def _manifest_for_membership(
    manifest: ScopedProtocolManifestV2,
    membership: MembershipSnapshotV2,
) -> tuple[
    ScopedProtocolManifestV2, DistributedCommitPolicy, DistributedPolicyBindingV2
]:
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("distributed epoch requires exact scoped manifest")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    policy = detached.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("distributed epoch manifest lacks commit policy")
    distributed = policy.distributed
    if type(distributed) is not DistributedCommitPolicy:
        raise ValueError("distributed epoch manifest lacks distributed policy")
    if (
        membership.assurance is not CommitAssurance.DISTRIBUTED
        or detached.manifest_root != membership.manifest_root
        or detached.id != membership.protocol_ref
        or policy.assurance != CommitAssurance.DISTRIBUTED.value
        or policy.target != membership.target_ref
        or policy.certificate.mode != "distributed"
        or commit_policy_fingerprint(policy, profile=membership.profile)
        != membership.commit_policy_root
    ):
        raise ValueError("distributed epoch manifest is cross-bound")
    binding = distributed_policy_binding_v2(
        distributed, policy_root=membership.commit_policy_root
    )
    return detached, distributed, binding


def _current_lane_dependency_v2(
    state: object,
    role: DistributedDependencyRoleV2,
    lane: DistributedLaneV2,
) -> tuple[DistributedLaneSnapshotV2, DistributedDependencyV2]:
    material = _verified_distributed_state_material_v2(state)
    if material.snapshot.lane is not lane or material.view.position_observation is None:
        raise ValueError("distributed lane dependency is cross-bound")
    from pheroos.governance.authority_store_v2 import GovernanceCommitPositionV2

    if (
        material.view.position_observation.position
        is not GovernanceCommitPositionV2.CURRENT
    ):
        raise ValueError("distributed lane dependency is stale")
    assert material.view.committed_transition is not None
    receipt = material.view.committed_transition.receipt
    inclusion = material.view.committed_transition.inclusion_proof
    return (
        DistributedLaneSnapshotV2.from_dict(material.snapshot.to_dict()),
        DistributedDependencyV2(
            role=role,
            stream_ref=material.snapshot.stream_ref,
            revision=material.snapshot.revision,
            transition_id=material.snapshot.transition_id,
            snapshot_root=material.snapshot.snapshot_root,
            head_root=material.head.head_root,
            receipt_root=receipt.receipt_root,
            inclusion_root=inclusion.inclusion_root,
        ),
    )


def _lane_dependency_from_reader_v2(
    context: _EpochAuthorityContextV2,
    *,
    role: DistributedDependencyRoleV2,
    lane: DistributedLaneV2,
) -> tuple[DistributedLaneSnapshotV2 | None, DistributedDependencyV2]:
    membership = context.membership
    stream = distributed_lane_stream_ref_v2(
        membership.scope_ref,
        membership.protocol_ref,
        membership.run_ref,
        membership.target_ref,
        lane,
    )
    head = context.reader.load_head_v2(membership.scope_ref, stream)
    if type(head) is not GovernanceHeadV2:
        raise TypeError("distributed lane head is invalid")
    if head.revision == 0:
        return None, DistributedDependencyV2(
            role=role,
            stream_ref=stream,
            revision=0,
            transition_id="",
            snapshot_root="",
            head_root=head.head_root,
            receipt_root="",
            inclusion_root="",
        )
    view = _canonical_commit_view_v2(
        context.reader.load_commit_view_v2(
            membership.scope_ref, stream, head.transition_id
        )
    )
    _, snapshot, _ = _decode_committed_distributed_view_v2(
        view, context.domain, reader=context.reader
    )
    if snapshot.lane is not lane or view.committed_transition is None:
        raise ValueError("distributed current lane dependency is mismatched")
    receipt = view.committed_transition.receipt
    inclusion = view.committed_transition.inclusion_proof
    if receipt.head_root != head.head_root or receipt.revision != head.revision:
        raise ValueError("distributed lane head changed during preparation")
    return snapshot, DistributedDependencyV2(
        role=role,
        stream_ref=stream,
        revision=snapshot.revision,
        transition_id=snapshot.transition_id,
        snapshot_root=snapshot.snapshot_root,
        head_root=head.head_root,
        receipt_root=receipt.receipt_root,
        inclusion_root=inclusion.inclusion_root,
    )


def _parent_snapshot_v2(
    state: object | None,
    lane: DistributedLaneV2,
) -> DistributedLaneSnapshotV2 | None:
    if state is None:
        return None
    snapshot, _ = _current_lane_dependency_v2(
        state,
        DistributedDependencyRoleV2(lane.value),
        lane,
    )
    return snapshot


def _request_v2(snapshot: DistributedLaneSnapshotV2) -> DistributedAdvanceRequestV2:
    return DistributedAdvanceRequestV2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        observed_epoch=snapshot.current_epoch,
        mutation_ref=snapshot.mutation_ref,
        mutation_issuer_ref=snapshot.mutation_issuer_ref,
        current_step=snapshot.current_step,
        parent_revision=snapshot.parent_revision,
        parent_transition_id=snapshot.parent_transition_id,
        parent_snapshot_root=snapshot.parent_snapshot_root,
        snapshot=snapshot,
    )


__all__: tuple[str, ...] = ()
