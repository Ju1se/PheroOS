"""Public-only Distributed owner composition for finality Conformance."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from pheroos.conformance.checks._distributed_v2_context_support import (
    CANDIDATE_REF,
    PROFILE,
    capability_v2,
)
from pheroos.conformance.checks._distributed_v2_vertical_support import (
    DistributedV2ConflictVertical,
    DistributedV2Vertical,
)
from pheroos.conformance.checks._support_v2_manifest_support import root_v2
from pheroos.governance.authority_store_v2 import GovernanceCommitAttemptV2
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionCommandV2,
    CommitDecisionRequestV2,
    VerifiedCommitDecisionSourceV2,
    VerifiedCommitDecisionStateV2,
    advance_commit_decision_v2,
    open_commit_decision_authority_session_v2,
    prepare_commit_decision_successor_v2,
    rehydrate_commit_decision_state_v2,
)
from pheroos.governance.commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    VerifiedCommitFinalityInputV2,
)
from pheroos.governance.distributed_commit_v2 import (
    VerifiedDistributedCertificateStateV2,
    advance_distributed_commit_v2,
    open_distributed_authority_session_v2,
    prepare_distributed_certificate_v2,
    rehydrate_distributed_state_v2,
    verified_distributed_commit_finality_input_v2,
)


def prepare_distributed_finalization_v2(
    vertical: DistributedV2Vertical,
    *,
    parent_state: VerifiedCommitDecisionStateV2 | None = None,
    verified_finality_input: object,
    label: str,
    current_step: int,
) -> tuple[CommitDecisionRequestV2, VerifiedCommitDecisionSourceV2]:
    parent = vertical.decision if parent_state is None else parent_state
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=vertical.claim_root,
        evidence=(),
    )
    return prepare_commit_decision_successor_v2(
        parent_state=parent,
        manifest=vertical.context.manifest,
        profile=PROFILE,
        mutation_ref=f"mutation:finality:distributed:decision:{label}",
        current_step=current_step,
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=vertical.inputs.replay,
        risk_state=vertical.inputs.risk,
        membership_state=vertical.inputs.membership,
        support_state=vertical.inputs.support,
        evidence_state=vertical.inputs.evidence,
        stop_state=vertical.inputs.stop,
        permission_state=vertical.inputs.permission,
        verified_finality_input=verified_finality_input,
    )


def advance_distributed_decision_v2(
    vertical: DistributedV2Vertical,
    request: CommitDecisionRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    return advance_commit_decision_v2(
        request,
        source=source,
        authority_session=open_commit_decision_authority_session_v2(
            capability_v2(vertical.context, request.observed_epoch),
            request,
        ),
    )


def distributed_decision_state_v2(
    vertical: DistributedV2Vertical,
    request: CommitDecisionRequestV2,
) -> VerifiedCommitDecisionStateV2:
    return rehydrate_commit_decision_state_v2(
        request.to_dict(),
        domain=vertical.context.domain,
        state_reader=vertical.context.store,
    )


def advance_distributed_owner_successor_v2(
    vertical: DistributedV2Vertical,
    label: str,
) -> DistributedV2Vertical:
    request, source = prepare_distributed_certificate_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        witness_state=vertical.witness,
        manifest=vertical.context.manifest,
        trusted_verifier=vertical.verifier,
        certificate_ref=f"certificate:distributed:{label}:successor",
        provenance_ref=f"urn:pheroos:conformance:distributed:{label}:successor",
        mutation_ref=f"mutation:distributed:{label}:certificate-successor",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.certificate,
    )
    attempt = advance_distributed_commit_v2(
        request,
        source=source,
        authority_session=open_distributed_authority_session_v2(
            capability_v2(vertical.context, request.observed_epoch),
            request,
        ),
    )
    if attempt.committed_transition is None:
        detail = "" if attempt.failure is None else str(attempt.failure.to_dict())
        raise RuntimeError(f"Distributed owner successor failed: {detail}")
    state = cast(
        VerifiedDistributedCertificateStateV2,
        rehydrate_distributed_state_v2(
            request.to_dict(),
            domain=vertical.context.domain,
            state_reader=vertical.context.store,
        ),
    )
    return replace(
        vertical,
        certificate_request=(request),
        certificate=state,
    )


def distributed_conflict_finality_v2(
    conflict: DistributedV2ConflictVertical,
    *,
    current_step: int,
) -> VerifiedCommitFinalityInputV2:
    """Verify the current frozen witness lane through the public owner facade."""

    baseline = conflict.baseline
    return verified_distributed_commit_finality_input_v2(
        baseline.certificate,
        proposal_state=baseline.proposal,
        witness_state=conflict.witness,
        epoch_state=baseline.epoch,
        sealed_decision_state=baseline.decision,
        central_certificate_state=baseline.central,
        membership_state=baseline.identity.membership,
        manifest=baseline.context.manifest,
        current_step=current_step,
    )


def portable_finality_projection_v2() -> CommitFinalityProjectionV2:
    return CommitFinalityProjectionV2(
        owner=CommitFinalityOwnerV2.DISTRIBUTED,
        status=CommitFinalityStatusV2.VERIFIED,
        stream_ref="authority:distributed:portable-substitute",
        revision=1,
        transition_id="transition:distributed:portable-substitute",
        snapshot_root=root_v2("distributed-portable-snapshot"),
        head_root=root_v2("distributed-portable-head"),
        receipt_root=root_v2("distributed-portable-receipt"),
        seal_transition_id="transition:decision:portable-seal",
        seal_root=root_v2("distributed-portable-seal"),
        frozen_dependency_root=root_v2("distributed-portable-dependencies"),
        verified_at_step=10,
        reason_codes=("portable_only",),
    )


__all__: tuple[str, ...] = ()
