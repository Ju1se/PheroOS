"""Pure conflict/recovery proof plus closed Trace events for distributed tests."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.governance._commit_certificate_v2_store_support import _capability, _root

from pheroos.governance._authority_session_v2.contracts import (
    _governance_authority_session_state_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _read_set,
    _session_binding,
    _session_grant_precondition,
    _session_lifecycle_precondition,
)
from pheroos.governance._distributed_v2.certificate_contracts import (
    DistributedCommitCertificateV2,
)
from pheroos.governance._distributed_v2.events import _distributed_event_v2
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
)
from pheroos.governance._distributed_v2.reducer import (
    reduce_certificate_v2,
    reduce_epoch_v2,
    reduce_witness_v2,
)
from pheroos.governance._distributed_v2.source_support import _request_v2
from pheroos.governance.authority_store_v2 import GovernanceHeadV2
from pheroos.governance.distributed_commit_v2 import (
    DistributedCommitProposalV2,
    DistributedLaneStatusV2,
    DistributedMutationKindV2,
    DistributedQuorumWitnessV2,
    open_distributed_authority_session_v2,
)
from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2
from pheroos.trace import TraceEvent


def assert_conflict_recovery_and_trace_v2(
    vertical: object,
) -> tuple[TraceEvent, TraceEvent]:
    context = object.__getattribute__(vertical, "context")
    inputs = object.__getattribute__(vertical, "inputs")
    proposal_handle = object.__getattribute__(vertical, "proposal")
    witness_handle = object.__getattribute__(vertical, "witness")
    certificate_handle = object.__getattribute__(vertical, "certificate")
    epoch_handle = object.__getattribute__(vertical, "epoch")
    verifier = object.__getattribute__(vertical, "verifier")

    proposal_snapshot = proposal_handle.snapshot
    proposal_state = cast(DistributedProposalStateV2, proposal_snapshot.state)
    baseline_proposal = proposal_state.proposals[0]
    alternate_value = replace(
        baseline_proposal.value,
        decision_current_transition_id="transition:distributed:alternate",
        decision_current_snapshot_root=_root("distributed:alternate:snapshot"),
        decision_current_head_root=_root("distributed:alternate:head"),
        decision_current_receipt_root=_root("distributed:alternate:receipt"),
        decision_current_inclusion_root=_root("distributed:alternate:inclusion"),
        semantic_value_root="",
    )
    alternate_proposal = DistributedCommitProposalV2(
        proposal_ref="proposal:distributed:alternate",
        proposer_ref="principal:alpha",
        proposal_nonce="nonce:distributed:alternate",
        proposed_at_step=10,
        provenance_ref="urn:test:distributed:alternate",
        source_trace_roots=(_root("trace:distributed:alternate"),),
        value=alternate_value,
    )
    cluster = inputs.membership.snapshot.clusters[0]
    member = cluster.principals[0]
    alternate_witness = DistributedQuorumWitnessV2(
        domain_root=alternate_value.domain_root,
        scope_ref=alternate_value.scope_ref,
        protocol_ref=alternate_value.protocol_ref,
        run_ref=alternate_value.run_ref,
        target_ref=alternate_value.target_ref,
        epoch=alternate_value.epoch,
        proposal_digest=alternate_proposal.proposal_digest,
        semantic_value_root=alternate_value.semantic_value_root,
        candidate_ref=alternate_value.candidate_ref,
        claim_root=alternate_value.claim_root,
        membership_root=alternate_value.membership_root,
        verification_set_root=alternate_value.verification_set_root,
        principal_ref=member.principal_ref,
        verification_root=member.verification_root,
        cluster_ref=cluster.cluster_ref,
        failure_domain_ref=member.failure_domain_ref,
        witness_nonce="nonce:distributed:alternate:witness",
        witnessed_at_step=10,
        expires_at_step=30,
        provenance_ref="urn:test:distributed:alternate:witness",
        source_trace_roots=(_root("trace:distributed:alternate:witness"),),
        attestation_ref="attestation:discovery",
    )
    alternate_witness = replace(
        alternate_witness,
        attestation_ref=verifier.attestation_ref(
            member.principal_ref,
            member.verification_root,
            alternate_witness.signing_root,
        ),
        witness_root="",
    )

    witness_snapshot = witness_handle.snapshot
    frozen_witness = reduce_witness_v2(
        witness=alternate_witness,
        parent=witness_snapshot,
        dependencies=witness_snapshot.dependencies,
        mutation_ref="mutation:distributed:witness:conflict",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
    )
    frozen_witness_state = cast(DistributedWitnessStateV2, frozen_witness.state)
    assert frozen_witness.status is DistributedLaneStatusV2.FROZEN
    assert frozen_witness.mutation_kind is (
        DistributedMutationKindV2.EQUIVOCATION_FROZEN
    )
    assert len(frozen_witness_state.equivocations) == 1

    alternate_certificate = DistributedCommitCertificateV2(
        certificate_ref="certificate:distributed:alternate",
        issuer_ref=context.grant.issuer_ref,
        issued_at_step=10,
        provenance_ref="urn:test:distributed:alternate:certificate",
        value=alternate_value,
        proposal_digests=(alternate_proposal.proposal_digest,),
        witnesses=(alternate_witness,),
        membership_size=1,
        max_byzantine_faults=0,
        witness_quorum=1,
        minimum_failure_domain_diversity=1,
    )
    certificate_snapshot = certificate_handle.snapshot
    frozen_certificate = reduce_certificate_v2(
        certificate=alternate_certificate,
        parent=certificate_snapshot,
        dependencies=certificate_snapshot.dependencies,
        mutation_ref="mutation:distributed:certificate:conflict",
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    frozen_certificate_state = cast(
        DistributedCertificateStateV2, frozen_certificate.state
    )
    assert frozen_certificate.status is DistributedLaneStatusV2.FROZEN
    assert frozen_certificate.mutation_kind is (
        DistributedMutationKindV2.CERTIFICATE_CONFLICT_FROZEN
    )
    assert len(frozen_certificate_state.conflict_roots) == 1
    assert (
        len(
            {
                item.value.semantic_value_root
                for item in frozen_certificate_state.certificates
            }
        )
        == 2
    )

    witness_event = _event_for_snapshot(context, frozen_witness)
    certificate_event = _event_for_snapshot(context, frozen_certificate)

    epoch_snapshot = epoch_handle.snapshot
    epoch_state = cast(DistributedEpochStateV2, epoch_snapshot.state)
    conflict_roots = (
        frozen_witness_state.equivocations[0].finding_root,
        frozen_certificate_state.conflict_roots[0],
    )
    recovery_certificate = replace(
        epoch_state.transition_certificate,
        transition_certificate_ref="certificate:distributed:epoch:recovery",
        from_epoch=epoch_snapshot.current_epoch,
        to_epoch=epoch_snapshot.current_epoch + 1,
        prior_epoch_snapshot_root=epoch_snapshot.snapshot_root,
        conflict_history_roots=conflict_roots,
        required_action_refs=("epoch_transition", "recovery"),
        issued_at_step=11,
        provenance_ref="urn:test:distributed:epoch:recovery",
        source_trace_roots=(_root("trace:distributed:epoch:recovery"),),
        certificate_root="",
    )
    recovery = reduce_epoch_v2(
        certificate=recovery_certificate,
        parent=epoch_snapshot,
        dependencies=epoch_snapshot.dependencies,
        mutation_ref="mutation:distributed:epoch:recovery",
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    assert recovery.current_epoch == epoch_snapshot.current_epoch + 1
    assert recovery_certificate.required_action_refs == (
        "epoch_transition",
        "recovery",
    )
    with pytest.raises(ValueError, match="recovery authority"):
        replace(
            recovery_certificate,
            required_action_refs=("epoch_transition",),
            certificate_root="",
        )
    erased = replace(
        recovery_certificate,
        transition_certificate_ref="certificate:distributed:epoch:erased",
        from_epoch=recovery.current_epoch,
        to_epoch=recovery.current_epoch + 1,
        prior_epoch_snapshot_root=recovery.snapshot_root,
        conflict_history_roots=(),
        required_action_refs=("epoch_transition",),
        certificate_root="",
    )
    with pytest.raises(ValueError, match="erased conflict history"):
        reduce_epoch_v2(
            certificate=erased,
            parent=recovery,
            dependencies=recovery.dependencies,
            mutation_ref="mutation:distributed:epoch:erase",
            mutation_issuer_ref=context.grant.issuer_ref,
        )
    return witness_event, certificate_event


def _event_for_snapshot(context, snapshot):
    request = _request_v2(snapshot)
    session = open_distributed_authority_session_v2(
        _capability(context, request.observed_epoch), request
    )
    session_state = _governance_authority_session_state_v2(session)
    parent_head = context.store.load_head_v2(snapshot.scope_ref, snapshot.stream_ref)
    if parent_head.revision != snapshot.parent_revision:
        raise AssertionError("conflict event parent is not the current Store head")
    observed = (
        GovernanceReadPreconditionV2(
            stream_ref=snapshot.stream_ref,
            expected_revision=snapshot.parent_revision,
            expected_root=parent_head.head_root,
        ),
        *(
            GovernanceReadPreconditionV2(
                stream_ref=item.stream_ref,
                expected_revision=item.revision,
                expected_root=item.head_root,
            )
            for item in snapshot.dependencies
        ),
        _session_grant_precondition(session_state),
        _session_lifecycle_precondition(session_state),
    )
    return _distributed_event_v2(
        request,
        _session_binding(session_state),
        parent_head_root=cast(GovernanceHeadV2, parent_head).head_root,
        read_set_root=_read_set(observed).root(),
    )


__all__: tuple[str, ...] = ()
