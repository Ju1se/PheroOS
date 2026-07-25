"""Static public owner for optimal commit evaluation."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._commit.assessment import CommitAssessment
from pheroos.governance._commit.evaluation_engine import (
    CommitEvaluationRequest,
    assess_optimal_commit_impl,
)
from pheroos.governance._commit.records import (
    CandidateCommitInput,
    CommitEvaluationContext,
)
from pheroos.governance._commit_state.records import CommitReplayState
from pheroos.governance._risk.records import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.permission import ActionPermission
from pheroos.governance.stop_signal import StopResolutionVerification
from pheroos.protocol.models import CapabilityManifest


def assess_optimal_commit(
    context: CommitEvaluationContext,
    *,
    manifest: CapabilityManifest,
    candidate_inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation],
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    stop_resolution: StopResolutionVerification,
    commit_permission: ActionPermission,
    assessment_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> CommitAssessment:
    return assess_optimal_commit_impl(
        CommitEvaluationRequest(
            context=context,
            manifest=manifest,
            candidate_inputs=candidate_inputs,
            leases=leases,
            revocations=revocations,
            risk_chain_state=risk_chain_state,
            risk_assessment=risk_assessment,
            threshold_snapshot=threshold_snapshot,
            membership_snapshot=membership_snapshot,
            membership_epoch_state=membership_epoch_state,
            replay_state=replay_state,
            support_replay_state=support_replay_state,
            stop_resolution=stop_resolution,
            commit_permission=commit_permission,
            assessment_id=assessment_id,
            issuer_id=issuer_id,
            authority=authority,
            current_step=current_step,
            provenance=provenance,
            trace_event_id=trace_event_id,
        )
    )


assess_optimal_commit.__module__ = "pheroos.governance.commit"


__all__ = ["assess_optimal_commit"]
