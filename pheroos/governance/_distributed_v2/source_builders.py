"""Deterministic rebuilders behind opaque distributed source recipes."""

from __future__ import annotations

from pheroos.governance._distributed_v2.authority_context import (
    _distributed_authority_context_v2,
    _distributed_value_v2,
)
from pheroos.governance._distributed_v2.certificate_contracts import (
    DistributedCommitCertificateV2,
)
from pheroos.governance._distributed_v2.conflict_contracts import (
    _validate_conflicting_value_binding_v2,
)
from pheroos.governance._distributed_v2.enums import (
    DistributedDependencyRoleV2,
    DistributedLaneV2,
)
from pheroos.governance._distributed_v2.epoch_contracts import (
    DistributedEpochTransitionCertificateV2,
)
from pheroos.governance._distributed_v2.lane_states import (
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitProposalV2,
)
from pheroos.governance._distributed_v2.reducer import (
    reduce_certificate_v2,
    reduce_epoch_v2,
    reduce_proposal_v2,
    reduce_witness_conflict_observation_v2,
    reduce_witness_v2,
)
from pheroos.governance._distributed_v2.request import DistributedAdvanceRequestV2
from pheroos.governance._distributed_v2.source_evaluation import (
    _epoch_conflicts_v2,
    _member_v2,
    _validate_epoch_v2,
    _verified_witnesses_v2,
)
from pheroos.governance._distributed_v2.source_recipes import (
    _CertificateRecipeV2,
    _EpochRecipeV2,
    _ProposalRecipeV2,
    _RecipeV2,
    _WitnessConflictObservationRecipeV2,
    _WitnessRecipeV2,
)
from pheroos.governance._distributed_v2.source_support import (
    _current_lane_dependency_v2,
    _epoch_authority_context_v2,
    _lane_dependency_from_reader_v2,
    _parent_snapshot_v2,
    _request_v2,
)
from pheroos.governance._distributed_v2.state_contracts import (
    distributed_lane_stream_ref_v2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    verify_distributed_witness_v2,
)


def _build_recipe_v2(recipe: _RecipeV2) -> DistributedAdvanceRequestV2:
    if type(recipe) is _EpochRecipeV2:
        return _build_epoch(recipe)
    if type(recipe) is _ProposalRecipeV2:
        return _build_proposal(recipe)
    if type(recipe) is _WitnessRecipeV2:
        return _build_witness(recipe)
    if type(recipe) is _WitnessConflictObservationRecipeV2:
        return _build_witness_conflict_observation(recipe)
    if type(recipe) is _CertificateRecipeV2:
        return _build_certificate(recipe)
    raise TypeError("distributed source recipe is invalid")


def _build_epoch(recipe: _EpochRecipeV2) -> DistributedAdvanceRequestV2:
    context = _epoch_authority_context_v2(
        membership_state=recipe.membership_state,
        manifest=recipe.manifest,
        current_step=recipe.current_step,
    )
    parent = _parent_snapshot_v2(recipe.parent_state, DistributedLaneV2.EPOCH)
    epoch_stream = distributed_lane_stream_ref_v2(
        context.membership.scope_ref,
        context.membership.protocol_ref,
        context.membership.run_ref,
        context.membership.target_ref,
        DistributedLaneV2.EPOCH,
    )
    epoch_head = context.reader.load_head_v2(context.membership.scope_ref, epoch_stream)
    if parent is None and epoch_head.revision != 0:
        raise ValueError("distributed epoch parent state is required")
    if parent is not None and (
        epoch_head.revision != parent.revision
        or epoch_head.transition_id != parent.transition_id
    ):
        raise ValueError("distributed epoch parent is stale")
    lane_values = tuple(
        _lane_dependency_from_reader_v2(context, role=role, lane=lane)
        for role, lane in (
            (DistributedDependencyRoleV2.PROPOSAL, DistributedLaneV2.PROPOSAL),
            (DistributedDependencyRoleV2.WITNESS, DistributedLaneV2.WITNESS),
            (DistributedDependencyRoleV2.CERTIFICATE, DistributedLaneV2.CERTIFICATE),
        )
    )
    proposal_state, proposal_dependency = lane_values[0]
    witness_state, witness_dependency = lane_values[1]
    certificate_state, certificate_dependency = lane_values[2]
    conflicts = _epoch_conflicts_v2(parent, witness_state, certificate_state)
    actions = ("epoch_transition", "recovery") if conflicts else ("epoch_transition",)
    membership = context.membership
    certificate = DistributedEpochTransitionCertificateV2(
        domain_root=membership.domain_root,
        scope_ref=membership.scope_ref,
        protocol_ref=membership.protocol_ref,
        run_ref=membership.run_ref,
        target_ref=membership.target_ref,
        transition_certificate_ref=recipe.transition_certificate_ref,
        from_epoch=None if parent is None else parent.current_epoch,
        to_epoch=membership.epoch,
        transition_rule=context.policy_binding.epoch_transition_rule,
        policy_binding=context.policy_binding,
        manifest_root=membership.manifest_root,
        commit_policy_root=membership.commit_policy_root,
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
        prior_epoch_snapshot_root="" if parent is None else parent.snapshot_root,
        prior_proposal_head_root=proposal_dependency.head_root,
        prior_witness_head_root=witness_dependency.head_root,
        prior_certificate_head_root=certificate_dependency.head_root,
        conflict_history_roots=conflicts,
        required_action_refs=actions,
        issued_at_step=recipe.current_step,
        issuer_ref=recipe.mutation_issuer_ref,
        provenance_ref=recipe.provenance_ref,
        source_trace_roots=recipe.source_trace_roots,
    )
    snapshot = reduce_epoch_v2(
        certificate=certificate,
        parent=parent,
        dependencies=(
            context.membership_dependency,
            context.verification_dependency,
            proposal_dependency,
            witness_dependency,
            certificate_dependency,
        ),
        mutation_ref=recipe.mutation_ref,
        mutation_issuer_ref=recipe.mutation_issuer_ref,
    )
    return _request_v2(snapshot)


def _build_proposal(recipe: _ProposalRecipeV2) -> DistributedAdvanceRequestV2:
    context = _distributed_authority_context_v2(
        decision_state=recipe.decision_state,
        central_certificate_state=recipe.central_certificate_state,
        membership_state=recipe.membership_state,
        manifest=recipe.manifest,
        current_step=recipe.current_step,
    )
    epoch, epoch_dependency = _current_lane_dependency_v2(
        recipe.epoch_state, DistributedDependencyRoleV2.EPOCH, DistributedLaneV2.EPOCH
    )
    _validate_epoch_v2(epoch, context.membership)
    proposal = DistributedCommitProposalV2(
        proposal_ref=recipe.proposal_ref,
        proposer_ref=recipe.proposer_ref,
        proposal_nonce=recipe.proposal_nonce,
        proposed_at_step=recipe.current_step,
        provenance_ref=recipe.provenance_ref,
        source_trace_roots=recipe.source_trace_roots,
        value=_distributed_value_v2(context),
    )
    parent = _parent_snapshot_v2(recipe.parent_state, DistributedLaneV2.PROPOSAL)
    snapshot = reduce_proposal_v2(
        proposal=proposal,
        parent=parent,
        dependencies=(
            epoch_dependency,
            context.decision_dependency,
            context.central_dependency,
            context.membership_dependency,
            context.verification_dependency,
        ),
        mutation_ref=recipe.mutation_ref,
        mutation_issuer_ref=recipe.mutation_issuer_ref,
    )
    return _request_v2(snapshot)


def _build_witness(recipe: _WitnessRecipeV2) -> DistributedAdvanceRequestV2:
    context = _distributed_authority_context_v2(
        decision_state=recipe.decision_state,
        central_certificate_state=recipe.central_certificate_state,
        membership_state=recipe.membership_state,
        manifest=recipe.manifest,
        current_step=recipe.current_step,
    )
    epoch, epoch_dependency = _current_lane_dependency_v2(
        recipe.epoch_state, DistributedDependencyRoleV2.EPOCH, DistributedLaneV2.EPOCH
    )
    proposal, proposal_dependency = _current_lane_dependency_v2(
        recipe.proposal_state,
        DistributedDependencyRoleV2.PROPOSAL,
        DistributedLaneV2.PROPOSAL,
    )
    _validate_epoch_v2(epoch, context.membership)
    proposal_state = proposal.state
    if type(proposal_state) is not DistributedProposalStateV2:
        raise TypeError("distributed witness proposal state is invalid")
    candidates = tuple(
        item
        for item in proposal_state.proposals
        if item.proposal_digest == recipe.witness.proposal_digest
        and item.value.semantic_value_root == recipe.witness.semantic_value_root
    )
    if len(candidates) != 1:
        raise ValueError("distributed witness proposal is not current and unique")
    cluster_ref, member = _member_v2(
        context.membership.clusters, recipe.witness.principal_ref
    )
    if not verify_distributed_witness_v2(
        recipe.witness,
        proposal=candidates[0],
        member=member,
        cluster_ref=cluster_ref,
        current_step=recipe.current_step,
        witness_ttl_steps=context.policy_binding.witness_ttl_steps,
        trusted_verifier=recipe.trusted_verifier,
    ):
        raise ValueError("distributed witness attestation is not trusted")
    parent = _parent_snapshot_v2(recipe.parent_state, DistributedLaneV2.WITNESS)
    snapshot = reduce_witness_v2(
        witness=recipe.witness,
        parent=parent,
        dependencies=(
            proposal_dependency,
            epoch_dependency,
            context.decision_dependency,
            context.central_dependency,
            context.membership_dependency,
            context.verification_dependency,
        ),
        mutation_ref=recipe.mutation_ref,
        mutation_issuer_ref=recipe.mutation_issuer_ref,
        current_step=recipe.current_step,
    )
    return _request_v2(snapshot)


def _build_witness_conflict_observation(
    recipe: _WitnessConflictObservationRecipeV2,
) -> DistributedAdvanceRequestV2:
    observation = recipe.observation
    if observation.observed_at_step != recipe.current_step:
        raise ValueError("distributed conflict observation step is mismatched")
    context = _distributed_authority_context_v2(
        decision_state=recipe.decision_state,
        central_certificate_state=recipe.central_certificate_state,
        membership_state=recipe.membership_state,
        manifest=recipe.manifest,
        current_step=recipe.current_step,
    )
    epoch, epoch_dependency = _current_lane_dependency_v2(
        recipe.epoch_state, DistributedDependencyRoleV2.EPOCH, DistributedLaneV2.EPOCH
    )
    proposal, proposal_dependency = _current_lane_dependency_v2(
        recipe.proposal_state,
        DistributedDependencyRoleV2.PROPOSAL,
        DistributedLaneV2.PROPOSAL,
    )
    _validate_epoch_v2(epoch, context.membership)
    proposal_state = proposal.state
    if type(proposal_state) is not DistributedProposalStateV2:
        raise TypeError("distributed conflict proposal state is invalid")
    current_value = _distributed_value_v2(context)
    if not any(
        item.value.semantic_value_root == current_value.semantic_value_root
        for item in proposal_state.proposals
    ):
        raise ValueError("distributed conflict lacks the current local proposal")
    _validate_conflicting_value_binding_v2(observation.proposal.value, current_value)
    cluster_ref, member = _member_v2(
        context.membership.clusters, observation.witness.principal_ref
    )
    if not verify_distributed_witness_v2(
        observation.witness,
        proposal=observation.proposal,
        member=member,
        cluster_ref=cluster_ref,
        current_step=recipe.current_step,
        witness_ttl_steps=context.policy_binding.witness_ttl_steps,
        trusted_verifier=recipe.trusted_verifier,
    ):
        raise ValueError("distributed conflict witness attestation is not trusted")
    parent = _parent_snapshot_v2(recipe.parent_state, DistributedLaneV2.WITNESS)
    if parent is None or type(parent.state) is not DistributedWitnessStateV2:
        raise ValueError("distributed conflict requires a durable witness parent")
    if not any(
        item.principal_ref == observation.witness.principal_ref
        and item.semantic_value_root == current_value.semantic_value_root
        for item in parent.state.witnesses
    ):
        raise ValueError("distributed conflict lacks prior current-value witness")
    snapshot = reduce_witness_conflict_observation_v2(
        observation=observation,
        parent=parent,
        dependencies=(
            proposal_dependency,
            epoch_dependency,
            context.decision_dependency,
            context.central_dependency,
            context.membership_dependency,
            context.verification_dependency,
        ),
        mutation_ref=recipe.mutation_ref,
        mutation_issuer_ref=recipe.mutation_issuer_ref,
        current_step=recipe.current_step,
    )
    return _request_v2(snapshot)


def _build_certificate(recipe: _CertificateRecipeV2) -> DistributedAdvanceRequestV2:
    context = _distributed_authority_context_v2(
        decision_state=recipe.decision_state,
        central_certificate_state=recipe.central_certificate_state,
        membership_state=recipe.membership_state,
        manifest=recipe.manifest,
        current_step=recipe.current_step,
    )
    epoch, epoch_dependency = _current_lane_dependency_v2(
        recipe.epoch_state, DistributedDependencyRoleV2.EPOCH, DistributedLaneV2.EPOCH
    )
    proposal, proposal_dependency = _current_lane_dependency_v2(
        recipe.proposal_state,
        DistributedDependencyRoleV2.PROPOSAL,
        DistributedLaneV2.PROPOSAL,
    )
    witness, witness_dependency = _current_lane_dependency_v2(
        recipe.witness_state,
        DistributedDependencyRoleV2.WITNESS,
        DistributedLaneV2.WITNESS,
    )
    _validate_epoch_v2(epoch, context.membership)
    proposal_state = proposal.state
    witness_state = witness.state
    if (
        type(proposal_state) is not DistributedProposalStateV2
        or type(witness_state) is not DistributedWitnessStateV2
    ):
        raise TypeError("distributed certificate input state is invalid")
    if witness_state.frozen:
        raise ValueError("distributed certificate cannot issue from frozen witnesses")
    value = _distributed_value_v2(context)
    proposals = {
        item.proposal_digest: item
        for item in proposal_state.proposals
        if item.value.semantic_value_root == value.semantic_value_root
    }
    selected = _verified_witnesses_v2(
        context=context,
        proposals=proposals,
        witness_state=witness_state,
        current_step=recipe.current_step,
        trusted_verifier=recipe.trusted_verifier,
    )
    certificate = DistributedCommitCertificateV2(
        certificate_ref=recipe.certificate_ref,
        issuer_ref=recipe.mutation_issuer_ref,
        issued_at_step=recipe.current_step,
        provenance_ref=recipe.provenance_ref,
        value=value,
        proposal_digests=tuple({item.proposal_digest for item in selected}),
        witnesses=selected,
        membership_size=context.policy_binding.membership_size,
        max_byzantine_faults=context.policy_binding.max_byzantine_faults,
        witness_quorum=context.policy_binding.witness_quorum,
        minimum_failure_domain_diversity=(
            context.policy_binding.minimum_failure_domain_diversity
        ),
    )
    parent = _parent_snapshot_v2(recipe.parent_state, DistributedLaneV2.CERTIFICATE)
    snapshot = reduce_certificate_v2(
        certificate=certificate,
        parent=parent,
        dependencies=(
            proposal_dependency,
            witness_dependency,
            epoch_dependency,
            context.decision_dependency,
            context.central_dependency,
            context.membership_dependency,
            context.verification_dependency,
        ),
        mutation_ref=recipe.mutation_ref,
        mutation_issuer_ref=recipe.mutation_issuer_ref,
    )
    return _request_v2(snapshot)


__all__: tuple[str, ...] = ()
