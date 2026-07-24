from __future__ import annotations

from collections.abc import Iterable

from pheroos.governance._commit.records import (
    CommitEvaluationError,
    CommitReasonCode,
)
from pheroos.governance._commit_state.records import (
    CommitReplayState,
    commit_replay_state_matches,
)
from pheroos.governance._risk.chain import risk_assessment_matches
from pheroos.governance._risk.records import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
)
from pheroos.governance._risk.thresholds import (
    commit_threshold_snapshot_matches,
)
from pheroos.governance._support.membership import (
    eligible_principal_snapshot_matches,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
)
from pheroos.governance._support.replay import (
    support_lease_replay_state_is_current,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
)
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
)


def _require_authoritative_heads(
    *,
    policy: CollectiveCommitPolicy,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    current_step: int,
) -> None:
    if not risk_assessment_matches(
        risk_assessment,
        chain_state=risk_chain_state,
        commit_policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.RISK_HEAD_MISMATCH,
            "risk assessment is not the authoritative current chain head",
        )
    if not commit_threshold_snapshot_matches(
        threshold_snapshot,
        assessment=risk_assessment,
        chain_state=risk_chain_state,
        commit_policy=policy,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.THRESHOLD_MISMATCH,
            "commit threshold is not authoritative, active, and risk-bound",
        )
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.MEMBERSHIP_HEAD_MISMATCH,
            "membership snapshot is not the immutable authoritative epoch head",
        )
    if not commit_replay_state_matches(
        replay_state,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.REPLAY_HEAD_MISMATCH,
            "commit replay state is not the authoritative current run head",
        )
    if not support_lease_replay_state_is_current(support_replay_state) or (
        support_replay_state.profile != profile
        or support_replay_state.protocol_id != protocol_id
    ):
        raise CommitEvaluationError(
            CommitReasonCode.SUPPORT_REPLAY_HEAD_MISMATCH,
            "support replay state is not the authoritative current head",
        )


def _collective_root(
    values: Iterable[tuple[str, str]],
    *,
    schema: str,
    profile: str,
) -> str:
    normalized = tuple(sorted(tuple(values)))
    return commit_payload_fingerprint(
        {"candidate_roots": normalized},
        schema=schema,
        profile=profile,
    )


def _canonical_stop_fingerprint(value: object) -> str:
    if type(value) is not StopResolutionVerification:
        raise CommitEvaluationError(
            CommitReasonCode.STOP_RESOLUTION_UNRESOLVED,
            "commit stop resolution must use the canonical verification record",
        )
    try:
        return stop_resolution_verification_fingerprint(value)
    except GovernanceError as exc:
        raise CommitEvaluationError(
            CommitReasonCode.STOP_RESOLUTION_UNRESOLVED,
            f"commit stop resolution is malformed: {exc}",
        ) from exc


def _canonical_permission_fingerprint(value: object) -> str:
    if type(value) is not ActionPermission:
        raise CommitEvaluationError(
            CommitReasonCode.COMMIT_PERMISSION_UNRESOLVED,
            "commit permission must use the canonical permission record",
        )
    try:
        return action_permission_fingerprint(value)
    except GovernanceError as exc:
        raise CommitEvaluationError(
            CommitReasonCode.COMMIT_PERMISSION_UNRESOLVED,
            f"commit permission is malformed: {exc}",
        ) from exc
