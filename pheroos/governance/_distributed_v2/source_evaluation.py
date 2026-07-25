"""Small pure checks used by distributed source builders."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._distributed_v2.authority_context import (
    _DistributedAuthorityContextV2,
)
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedWitnessStateV2,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitProposalV2,
)
from pheroos.governance._distributed_v2.state_contracts import (
    DistributedLaneSnapshotV2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedQuorumWitnessV2,
    DistributedWitnessAttestationVerifierV2,
    verify_distributed_witness_v2,
)
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.membership_records import (
    MembershipClusterV2,
    MembershipPrincipalV2,
)


def _verified_witnesses_v2(
    *,
    context: _DistributedAuthorityContextV2,
    proposals: dict[str, DistributedCommitProposalV2],
    witness_state: DistributedWitnessStateV2,
    current_step: int,
    trusted_verifier: DistributedWitnessAttestationVerifierV2,
) -> tuple[DistributedQuorumWitnessV2, ...]:
    by_principal: dict[str, DistributedQuorumWitnessV2] = {}
    for witness in witness_state.witnesses:
        proposal = proposals.get(witness.proposal_digest)
        if proposal is None:
            continue
        cluster_ref, member = _member_v2(
            context.membership.clusters, witness.principal_ref
        )
        if verify_distributed_witness_v2(
            witness,
            proposal=proposal,
            member=member,
            cluster_ref=cluster_ref,
            current_step=current_step,
            witness_ttl_steps=context.policy_binding.witness_ttl_steps,
            trusted_verifier=trusted_verifier,
        ):
            prior = by_principal.get(witness.principal_ref)
            if prior is None or witness.witness_root < prior.witness_root:
                by_principal[witness.principal_ref] = witness
    return tuple(
        sorted(
            by_principal.values(),
            key=lambda item: item.witness_root.encode("utf-8"),
        )
    )


def _validate_epoch_v2(
    snapshot: DistributedLaneSnapshotV2,
    membership: MembershipSnapshotV2,
) -> None:
    if (
        type(membership) is not MembershipSnapshotV2
        or type(snapshot.state) is not DistributedEpochStateV2
    ):
        raise TypeError("distributed current epoch binding is invalid")
    certificate = snapshot.state.transition_certificate
    if (
        certificate.to_epoch != membership.epoch
        or certificate.membership_root != membership.membership_root
        or certificate.verification_set_root != membership.verification_set_root
        or certificate.manifest_root != membership.manifest_root
        or certificate.commit_policy_root != membership.commit_policy_root
    ):
        raise ValueError("distributed current epoch authority is mismatched")


def _epoch_conflicts_v2(
    parent: DistributedLaneSnapshotV2 | None,
    witness: DistributedLaneSnapshotV2 | None,
    certificate: DistributedLaneSnapshotV2 | None,
) -> tuple[str, ...]:
    roots: set[str] = set()
    if parent is not None:
        if type(parent.state) is not DistributedEpochStateV2:
            raise TypeError("distributed epoch parent state is invalid")
        roots.update(parent.state.conflict_history_roots)
    if witness is not None and type(witness.state) is DistributedWitnessStateV2:
        roots.update(item.finding_root for item in witness.state.equivocations)
    if (
        certificate is not None
        and type(certificate.state) is DistributedCertificateStateV2
    ):
        roots.update(certificate.state.conflict_roots)
    return tuple(sorted(roots, key=lambda item: item.encode("utf-8")))


def _member_v2(
    clusters: Sequence[MembershipClusterV2],
    principal_ref: str,
) -> tuple[str, MembershipPrincipalV2]:
    for cluster in clusters:
        if type(cluster) is not MembershipClusterV2:
            raise TypeError("distributed membership cluster is invalid")
        for principal in cluster.principals:
            if principal.principal_ref == principal_ref:
                return cluster.cluster_ref, principal
    raise ValueError("distributed witness principal is not eligible")


__all__: tuple[str, ...] = ()
