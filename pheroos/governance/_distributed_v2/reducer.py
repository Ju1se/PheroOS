"""Pure deterministic reducers for durable Distributed Commit v2 lanes."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._distributed_v2.certificate_contracts import (
    DistributedCommitCertificateV2,
)
from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_CERTIFICATES_V2,
    MAX_DISTRIBUTED_PROPOSALS_V2,
    MAX_DISTRIBUTED_WITNESSES_V2,
    _root,
)
from pheroos.governance._distributed_v2.conflict_contracts import (
    DistributedWitnessConflictObservationV2,
)
from pheroos.governance._distributed_v2.dependency_contracts import (
    DistributedDependencyV2,
    distributed_dependency_set_root_v2,
)
from pheroos.governance._distributed_v2.enums import (
    DistributedLaneStatusV2,
    DistributedLaneV2,
    DistributedMutationKindV2,
)
from pheroos.governance._distributed_v2.epoch_contracts import (
    DistributedEpochTransitionCertificateV2,
)
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedEquivocationFindingV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitProposalV2,
)
from pheroos.governance._distributed_v2.state_contracts import (
    DistributedLaneSnapshotV2,
    DistributedLaneStatePayloadV2,
    distributed_genesis_history_root_v2,
    distributed_genesis_snapshot_root_v2,
    distributed_lane_stream_ref_v2,
    distributed_lane_transition_id_v2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedQuorumWitnessV2,
)


def reduce_epoch_v2(
    *,
    certificate: DistributedEpochTransitionCertificateV2,
    parent: DistributedLaneSnapshotV2 | None,
    dependencies: Sequence[DistributedDependencyV2],
    mutation_ref: str,
    mutation_issuer_ref: str,
) -> DistributedLaneSnapshotV2:
    if parent is None:
        if certificate.from_epoch is not None:
            raise ValueError("distributed epoch initialization has a prior epoch")
        mutation = DistributedMutationKindV2.EPOCH_INITIALIZED
        previous_history: tuple[str, ...] = ()
    else:
        _require_parent_lane(parent, DistributedLaneV2.EPOCH)
        previous = parent.state
        if type(previous) is not DistributedEpochStateV2:
            raise TypeError("distributed epoch parent state is invalid")
        if certificate.from_epoch != previous.transition_certificate.to_epoch:
            raise ValueError("distributed epoch transition parent is mismatched")
        previous_history = tuple(previous.conflict_history_roots)
        mutation = DistributedMutationKindV2.EPOCH_TRANSITIONED
    if not set(previous_history).issubset(certificate.conflict_history_roots):
        raise ValueError("distributed epoch transition erased conflict history")
    state = DistributedEpochStateV2(
        transition_certificate=certificate,
        conflict_history_roots=certificate.conflict_history_roots,
    )
    return _snapshot(
        lane=DistributedLaneV2.EPOCH,
        mutation_kind=mutation,
        status=DistributedLaneStatusV2.ACTIVE,
        state=state,
        dependencies=dependencies,
        parent=parent,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=certificate.issued_at_step,
        reason_codes=(mutation.value,),
    )


def reduce_proposal_v2(
    *,
    proposal: DistributedCommitProposalV2,
    parent: DistributedLaneSnapshotV2 | None,
    dependencies: Sequence[DistributedDependencyV2],
    mutation_ref: str,
    mutation_issuer_ref: str,
) -> DistributedLaneSnapshotV2:
    previous = _proposal_records(parent, proposal.value.epoch)
    exact = any(item.proposal_digest == proposal.proposal_digest for item in previous)
    semantic = any(
        item.value.semantic_value_root == proposal.value.semantic_value_root
        for item in previous
    )
    records = previous if exact else (*previous, proposal)
    if len(records) > MAX_DISTRIBUTED_PROPOSALS_V2:
        raise ValueError("distributed proposal state exceeds its bound")
    mutation = (
        DistributedMutationKindV2.PROPOSAL_SEMANTIC_RETRY
        if exact or semantic
        else DistributedMutationKindV2.PROPOSAL_RECORDED
    )
    state = DistributedProposalStateV2(epoch=proposal.value.epoch, proposals=records)
    return _snapshot(
        lane=DistributedLaneV2.PROPOSAL,
        mutation_kind=mutation,
        status=DistributedLaneStatusV2.ACTIVE,
        state=state,
        dependencies=dependencies,
        parent=parent,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=proposal.proposed_at_step,
        reason_codes=(mutation.value,),
    )


def reduce_witness_v2(
    *,
    witness: DistributedQuorumWitnessV2,
    parent: DistributedLaneSnapshotV2 | None,
    dependencies: Sequence[DistributedDependencyV2],
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
) -> DistributedLaneSnapshotV2:
    return _reduce_witness_v2(
        witness=witness,
        conflict_observation=None,
        parent=parent,
        dependencies=dependencies,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
    )


def reduce_witness_conflict_observation_v2(
    *,
    observation: DistributedWitnessConflictObservationV2,
    parent: DistributedLaneSnapshotV2,
    dependencies: Sequence[DistributedDependencyV2],
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
) -> DistributedLaneSnapshotV2:
    if type(observation) is not DistributedWitnessConflictObservationV2:
        raise TypeError("distributed conflict reducer requires exact observation")
    snapshot = _reduce_witness_v2(
        witness=observation.witness,
        conflict_observation=observation,
        parent=parent,
        dependencies=dependencies,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
    )
    if snapshot.mutation_kind is not DistributedMutationKindV2.EQUIVOCATION_FROZEN:
        raise ValueError("distributed conflict observation may only freeze witnesses")
    return snapshot


def _reduce_witness_v2(
    *,
    witness: DistributedQuorumWitnessV2,
    conflict_observation: DistributedWitnessConflictObservationV2 | None,
    parent: DistributedLaneSnapshotV2 | None,
    dependencies: Sequence[DistributedDependencyV2],
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
) -> DistributedLaneSnapshotV2:
    previous, findings = _witness_records(parent, witness.epoch)
    exact = any(item.witness_root == witness.witness_root for item in previous)
    same_value = tuple(
        item
        for item in previous
        if item.principal_ref == witness.principal_ref
        and item.semantic_value_root == witness.semantic_value_root
    )
    conflicting = tuple(
        item
        for item in previous
        if item.principal_ref == witness.principal_ref
        and item.semantic_value_root != witness.semantic_value_root
    )
    records = previous if exact else (*previous, witness)
    if len(records) > MAX_DISTRIBUTED_WITNESSES_V2:
        raise ValueError("distributed witness state exceeds its bound")
    new_findings = list(findings)
    for other in conflicting:
        finding = DistributedEquivocationFindingV2(
            principal_ref=witness.principal_ref,
            epoch=witness.epoch,
            first_semantic_value_root=other.semantic_value_root,
            second_semantic_value_root=witness.semantic_value_root,
            first_witness_root=other.witness_root,
            second_witness_root=witness.witness_root,
            conflict_observation=conflict_observation,
        )
        if all(item.finding_root != finding.finding_root for item in new_findings):
            new_findings.append(finding)
    mutation = (
        DistributedMutationKindV2.EQUIVOCATION_FROZEN
        if new_findings
        else DistributedMutationKindV2.WITNESS_RETRY
        if exact or same_value
        else DistributedMutationKindV2.WITNESS_RECORDED
    )
    state = DistributedWitnessStateV2(
        epoch=witness.epoch,
        witnesses=records,
        equivocations=tuple(new_findings),
    )
    return _snapshot(
        lane=DistributedLaneV2.WITNESS,
        mutation_kind=mutation,
        status=(
            DistributedLaneStatusV2.FROZEN
            if state.frozen
            else DistributedLaneStatusV2.ACTIVE
        ),
        state=state,
        dependencies=dependencies,
        parent=parent,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
        reason_codes=(mutation.value,),
    )


def reduce_certificate_v2(
    *,
    certificate: DistributedCommitCertificateV2,
    parent: DistributedLaneSnapshotV2 | None,
    dependencies: Sequence[DistributedDependencyV2],
    mutation_ref: str,
    mutation_issuer_ref: str,
) -> DistributedLaneSnapshotV2:
    previous, prior_conflicts = _certificate_records(parent, certificate.value.epoch)
    exact = any(
        item.certificate_root == certificate.certificate_root for item in previous
    )
    semantic = any(
        item.value.semantic_value_root == certificate.value.semantic_value_root
        for item in previous
    )
    records = previous if exact else (*previous, certificate)
    if len(records) > MAX_DISTRIBUTED_CERTIFICATES_V2:
        raise ValueError("distributed certificate state exceeds its bound")
    conflicts = set(prior_conflicts)
    values = sorted({item.value.semantic_value_root for item in records})
    if len(values) > 1:
        conflicts.add(
            _root(
                "certificate-conflict",
                {"epoch": certificate.value.epoch, "semantic_value_roots": values},
            )
        )
    mutation = (
        DistributedMutationKindV2.CERTIFICATE_CONFLICT_FROZEN
        if conflicts
        else DistributedMutationKindV2.CERTIFICATE_RETRY
        if exact or semantic
        else DistributedMutationKindV2.CERTIFICATE_VERIFIED
    )
    state = DistributedCertificateStateV2(
        epoch=certificate.value.epoch,
        certificates=records,
        conflict_roots=tuple(conflicts),
    )
    return _snapshot(
        lane=DistributedLaneV2.CERTIFICATE,
        mutation_kind=mutation,
        status=(
            DistributedLaneStatusV2.FROZEN
            if state.frozen
            else DistributedLaneStatusV2.VERIFIED
        ),
        state=state,
        dependencies=dependencies,
        parent=parent,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=certificate.issued_at_step,
        reason_codes=(mutation.value,),
    )


def _snapshot(
    *,
    lane: DistributedLaneV2,
    mutation_kind: DistributedMutationKindV2,
    status: DistributedLaneStatusV2,
    state: DistributedLaneStatePayloadV2,
    dependencies: Sequence[DistributedDependencyV2],
    parent: DistributedLaneSnapshotV2 | None,
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
    reason_codes: Sequence[str],
) -> DistributedLaneSnapshotV2:
    context = _state_context(state)
    stream = distributed_lane_stream_ref_v2(*context[1:], lane)
    transition = distributed_lane_transition_id_v2(stream, mutation_ref)
    revision = 1 if parent is None else parent.revision + 1
    parent_revision = 0 if parent is None else parent.revision
    parent_transition = "genesis" if parent is None else parent.transition_id
    parent_snapshot = (
        distributed_genesis_snapshot_root_v2(lane)
        if parent is None
        else parent.snapshot_root
    )
    parent_history = (
        distributed_genesis_history_root_v2(lane)
        if parent is None
        else parent.history_root
    )
    parent_history_count = 0 if parent is None else parent.history_count
    dependency_root = distributed_dependency_set_root_v2(dependencies)
    source_root = _root(
        "source-context",
        {
            "lane": lane.value,
            "mutation_ref": mutation_ref,
            "current_epoch": _state_epoch(state),
            "current_step": current_step,
            "lane_state_root": state.state_root,
            "dependency_set_root": dependency_root,
        },
    )
    return DistributedLaneSnapshotV2(
        domain_root=context[0],
        scope_ref=context[1],
        protocol_ref=context[2],
        run_ref=context[3],
        target_ref=context[4],
        lane=lane,
        stream_ref=stream,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        mutation_kind=mutation_kind,
        transition_id=transition,
        revision=revision,
        parent_revision=parent_revision,
        parent_transition_id=parent_transition,
        parent_snapshot_root=parent_snapshot,
        current_epoch=_state_epoch(state),
        current_step=current_step,
        status=status,
        state=state,
        dependencies=dependencies,
        dependency_set_root=dependency_root,
        reason_codes=reason_codes,
        source_context_root=source_root,
        parent_history_root=parent_history,
        parent_history_count=parent_history_count,
        history_root="",
        history_count=parent_history_count + 1,
    )


def _state_context(
    state: DistributedLaneStatePayloadV2,
) -> tuple[str, str, str, str, str]:
    if type(state) is DistributedEpochStateV2:
        epoch = state.transition_certificate
        return (
            epoch.domain_root,
            epoch.scope_ref,
            epoch.protocol_ref,
            epoch.run_ref,
            epoch.target_ref,
        )
    if type(state) is DistributedProposalStateV2:
        value = state.proposals[0].value
        return (
            value.domain_root,
            value.scope_ref,
            value.protocol_ref,
            value.run_ref,
            value.target_ref,
        )
    if type(state) is DistributedWitnessStateV2:
        witness = state.witnesses[0]
        return (
            witness.domain_root,
            witness.scope_ref,
            witness.protocol_ref,
            witness.run_ref,
            witness.target_ref,
        )
    if type(state) is DistributedCertificateStateV2:
        value = state.certificates[0].value
        return (
            value.domain_root,
            value.scope_ref,
            value.protocol_ref,
            value.run_ref,
            value.target_ref,
        )
    raise TypeError("distributed reducer state context is unsupported")


def _state_epoch(state: DistributedLaneStatePayloadV2) -> int:
    if type(state) is DistributedEpochStateV2:
        return state.transition_certificate.to_epoch
    if type(state) is DistributedProposalStateV2:
        return state.epoch
    if type(state) is DistributedWitnessStateV2:
        return state.epoch
    if type(state) is DistributedCertificateStateV2:
        return state.epoch
    raise TypeError("distributed reducer state epoch is unsupported")


def _require_parent_lane(
    parent: DistributedLaneSnapshotV2, lane: DistributedLaneV2
) -> None:
    if type(parent) is not DistributedLaneSnapshotV2 or parent.lane is not lane:
        raise TypeError("distributed reducer parent lane is invalid")


def _proposal_records(
    parent: DistributedLaneSnapshotV2 | None, epoch: int
) -> tuple[DistributedCommitProposalV2, ...]:
    if parent is None:
        return ()
    _require_parent_lane(parent, DistributedLaneV2.PROPOSAL)
    state = parent.state
    if type(state) is not DistributedProposalStateV2:
        raise TypeError("distributed proposal parent state is invalid")
    return tuple(state.proposals) if state.epoch == epoch else ()


def _witness_records(
    parent: DistributedLaneSnapshotV2 | None, epoch: int
) -> tuple[
    tuple[DistributedQuorumWitnessV2, ...], tuple[DistributedEquivocationFindingV2, ...]
]:
    if parent is None:
        return (), ()
    _require_parent_lane(parent, DistributedLaneV2.WITNESS)
    state = parent.state
    if type(state) is not DistributedWitnessStateV2:
        raise TypeError("distributed witness parent state is invalid")
    return (
        (tuple(state.witnesses), tuple(state.equivocations))
        if state.epoch == epoch
        else ((), ())
    )


def _certificate_records(
    parent: DistributedLaneSnapshotV2 | None, epoch: int
) -> tuple[tuple[DistributedCommitCertificateV2, ...], tuple[str, ...]]:
    if parent is None:
        return (), ()
    _require_parent_lane(parent, DistributedLaneV2.CERTIFICATE)
    state = parent.state
    if type(state) is not DistributedCertificateStateV2:
        raise TypeError("distributed certificate parent state is invalid")
    return (
        (tuple(state.certificates), tuple(state.conflict_roots))
        if state.epoch == epoch
        else ((), ())
    )


__all__: tuple[str, ...] = ()
