"""Authority-head and lineage validation for commit liveness."""

from __future__ import annotations

from typing import cast

from pheroos.governance._commit_state.invariants import (
    _normalized_window_bindings,
    _validate_bound_commit_policy,
)
from pheroos.governance._commit_state.records import (
    CommitFinalityVerification,
    CommitLivenessInput,
    CommitReplayState,
    CommitWindowSeal,
    CommitWindowState,
    commit_replay_state_fingerprint,
    commit_replay_state_is_current,
    commit_window_state_fingerprint,
)
from pheroos.governance._commit_state.window import (
    commit_window_seal_fingerprint,
    commit_window_seal_for_state,
    commit_window_seal_is_current,
)
from pheroos.governance._risk.chain import (
    risk_assessment_chain_state_is_current,
)
from pheroos.governance._risk.payloads import (
    commit_threshold_snapshot_fingerprint,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance._risk.records import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
)
from pheroos.governance._risk.thresholds import commit_threshold_snapshot_matches
from pheroos.governance._support.membership import (
    eligible_membership_epoch_state_is_current,
    eligible_principal_snapshot_matches,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    support_lease_replay_state_fingerprint,
)
from pheroos.governance._support.replay import (
    support_lease_replay_state_is_current,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CollectiveCommitPolicy


_SCOPE_FIELDS = (
    "profile",
    "assurance",
    "manifest_root",
    "commit_policy_root",
    "protocol_id",
    "run_id",
    "target",
    "epoch",
)

_AUTHORITY_ROOT_FIELDS = (
    "risk_assessment_root",
    "risk_chain_state_root",
    "risk_policy_root",
    "membership_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "threshold_root",
    "support_replay_state_root",
    "support_replay_root",
    "collective_evidence_root",
    "collective_challenge_root",
    "collective_lease_root",
    "candidate_evidence_root",
    "candidate_challenge_root",
    "candidate_lease_root",
    "stop_resolution_root",
    "permission_root",
)


def validate_liveness_input_matches_window_impl(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> None:
    _require_matching_fields(state, value, _SCOPE_FIELDS, binding=True)
    if value.window_state_ref != commit_window_state_fingerprint(state):
        raise GovernanceError("commit liveness window head binding mismatch")
    if value.current_step < state.last_evaluated_step:
        raise GovernanceError("commit liveness step predates the window head")
    expected_deadline = value.current_step >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    )
    if value.deadline_reached is not expected_deadline:
        raise GovernanceError("commit liveness deadline state mismatch")
    _validate_assessment_head(state, value)
    _require_matching_fields(
        state,
        value,
        _AUTHORITY_ROOT_FIELDS,
        binding=False,
    )
    if state.last_ready and value.leader_candidate_id != state.leader_candidate_id:
        raise GovernanceError("commit liveness leader candidate mismatch")
    _validate_seal_lineage(state, value)
    if not value.heartbeat_continuous and value.current_step < min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError(
            "commit liveness heartbeat loss requires a terminal deadline"
        )


def _require_matching_fields(
    state: CommitWindowState,
    value: CommitLivenessInput,
    names: tuple[str, ...],
    *,
    binding: bool,
) -> None:
    suffix = " binding mismatch" if binding else " mismatch"
    for name in names:
        if getattr(state, name) != getattr(value, name):
            raise GovernanceError(f"commit liveness {name}{suffix}")


def _validate_assessment_head(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> None:
    if value.assessment_ref != state.last_assessment_ref:
        raise GovernanceError("commit liveness assessment head mismatch")
    if value.context_ref != state.last_context_ref:
        raise GovernanceError("commit liveness context head mismatch")
    if value.assessment_status != state.last_assessment_status:
        raise GovernanceError("commit liveness assessment status mismatch")
    if value.assessment_reason_codes != state.last_assessment_reason_codes:
        raise GovernanceError("commit liveness assessment reasons mismatch")


def _validate_seal_lineage(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> None:
    seal = commit_window_seal_for_state(state)
    if value.sealed_window is not (seal is not None):
        raise GovernanceError("commit liveness sealed-window state mismatch")
    if seal is not None and (
        value.seal_ref != commit_window_seal_fingerprint(seal)
        or value.sealed_at_step != seal.sealed_at_step
        or value.window_state_ref != seal.window_state_ref
    ):
        raise GovernanceError("commit liveness seal lineage mismatch")


def validate_liveness_current_authority_heads_impl(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy | None,
    risk_chain_state: object | None,
    risk_assessment: object | None,
    threshold_snapshot: object | None,
    membership_snapshot: object | None,
    membership_epoch_state: object | None,
    support_replay_state: object | None,
    current_step: int,
    require_fresh_snapshot: bool,
) -> None:
    risk_state = cast(RiskAssessmentChainState, risk_chain_state)
    risk_value = cast(RiskAssessment, risk_assessment)
    threshold = cast(CommitThresholdSnapshot, threshold_snapshot)
    membership = cast(EligiblePrincipalSnapshot, membership_snapshot)
    membership_state = cast(
        EligibleMembershipEpochState,
        membership_epoch_state,
    )
    support_state = cast(SupportLeaseReplayState, support_replay_state)
    _validate_current_chain_heads(
        state,
        risk_state=risk_state,
        membership_state=membership_state,
        support_state=support_state,
    )
    policy = _require_bound_policy(state, commit_policy)
    _validate_bound_snapshot_roots(
        state,
        risk_assessment=risk_value,
        threshold_snapshot=threshold,
        membership_snapshot=membership,
    )
    if not require_fresh_snapshot:
        return
    _validate_fresh_risk_snapshot(
        state,
        risk_state=risk_state,
        risk_assessment=risk_value,
        threshold_snapshot=threshold,
        commit_policy=policy,
        current_step=current_step,
    )
    _validate_fresh_membership_snapshot(
        state,
        membership_snapshot=membership,
        membership_state=membership_state,
        current_step=current_step,
    )


def _validate_current_chain_heads(
    state: CommitWindowState,
    *,
    risk_state: RiskAssessmentChainState,
    membership_state: EligibleMembershipEpochState,
    support_state: SupportLeaseReplayState,
) -> None:
    if (
        not risk_assessment_chain_state_is_current(risk_state)
        or risk_assessment_chain_state_fingerprint(risk_state)
        != state.risk_chain_state_root
    ):
        raise GovernanceError(
            "commit liveness risk authority head changed after assessment"
        )
    if (
        not eligible_membership_epoch_state_is_current(membership_state)
        or eligible_membership_epoch_state_fingerprint(membership_state)
        != state.membership_epoch_state_root
    ):
        raise GovernanceError(
            "commit liveness membership authority head changed after assessment"
        )
    if (
        not support_lease_replay_state_is_current(support_state)
        or support_lease_replay_state_fingerprint(support_state)
        != state.support_replay_state_root
    ):
        raise GovernanceError(
            "commit liveness support replay head changed after assessment"
        )


def _require_bound_policy(
    state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy | None,
) -> CollectiveCommitPolicy:
    if commit_policy is None:
        raise GovernanceError("commit liveness requires the bound commit policy")
    bindings = _normalized_window_bindings(
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        field_name="commit liveness authority heads",
    )
    _validate_bound_commit_policy(commit_policy, bindings)
    return commit_policy


def _validate_bound_snapshot_roots(
    state: CommitWindowState,
    *,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
) -> None:
    if (
        risk_assessment_fingerprint(risk_assessment) != state.risk_assessment_root
        or commit_threshold_snapshot_fingerprint(threshold_snapshot)
        != state.threshold_root
    ):
        raise GovernanceError(
            "commit liveness risk or threshold root changed after assessment"
        )
    if (
        eligible_principal_snapshot_fingerprint(membership_snapshot)
        != state.membership_snapshot_root
        or membership_snapshot.membership_root != state.membership_root
    ):
        raise GovernanceError(
            "commit liveness membership root changed after assessment"
        )


def _validate_fresh_risk_snapshot(
    state: CommitWindowState,
    *,
    risk_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    commit_policy: CollectiveCommitPolicy,
    current_step: int,
) -> None:
    if not commit_threshold_snapshot_matches(
        threshold_snapshot,
        assessment=risk_assessment,
        chain_state=risk_state,
        commit_policy=commit_policy,
        current_step=current_step,
    ):
        raise GovernanceError("late finality risk assessment or threshold is stale")
    if (
        risk_assessment_fingerprint(risk_assessment) != state.risk_assessment_root
        or commit_threshold_snapshot_fingerprint(threshold_snapshot)
        != state.threshold_root
    ):
        raise GovernanceError(
            "late finality risk or threshold root changed after sealing"
        )


def _validate_fresh_membership_snapshot(
    state: CommitWindowState,
    *,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_state: EligibleMembershipEpochState,
    current_step: int,
) -> None:
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_state,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=current_step,
    ):
        raise GovernanceError("late finality eligible-principal snapshot is stale")
    if (
        eligible_principal_snapshot_fingerprint(membership_snapshot)
        != state.membership_snapshot_root
        or membership_snapshot.membership_root != state.membership_root
    ):
        raise GovernanceError("late finality membership root changed after sealing")


def liveness_authority_heads_are_current_impl(value: CommitLivenessInput) -> bool:
    try:
        return _liveness_authority_heads_are_current(value)
    except Exception:
        return False


def _liveness_authority_heads_are_current(value: CommitLivenessInput) -> bool:
    heads = value._authority_heads
    if not isinstance(heads, tuple) or len(heads) != 8:
        return False
    replay_state = cast(CommitReplayState, heads[0])
    if not _replay_head_is_current(value, replay_state):
        return False
    if not value.assessment_ref:
        return True
    return _assessment_heads_are_current(value, heads)


def _replay_head_is_current(
    value: CommitLivenessInput,
    replay_state: CommitReplayState,
) -> bool:
    return bool(
        commit_replay_state_is_current(replay_state)
        and commit_replay_state_fingerprint(replay_state) == value.replay_state_ref
        and replay_state.receipt_root == value.replay_root
    )


def _assessment_heads_are_current(
    value: CommitLivenessInput,
    heads: tuple[object, ...],
) -> bool:
    risk_state = cast(RiskAssessmentChainState, heads[1])
    risk_assessment = cast(RiskAssessment, heads[2])
    threshold_snapshot = cast(CommitThresholdSnapshot, heads[3])
    membership_snapshot = cast(EligiblePrincipalSnapshot, heads[4])
    membership_state = cast(EligibleMembershipEpochState, heads[5])
    support_state = cast(SupportLeaseReplayState, heads[6])
    commit_policy = cast(CollectiveCommitPolicy, heads[7])
    if not _base_assessment_heads_are_current(
        value,
        risk_state=risk_state,
        membership_state=membership_state,
        support_state=support_state,
    ):
        return False
    _validate_liveness_value_policy(value, commit_policy)
    if not _assessment_snapshot_roots_match(
        value,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
    ):
        return False
    if not _requires_fresh_snapshot(value):
        return True
    return bool(
        commit_threshold_snapshot_matches(
            threshold_snapshot,
            assessment=risk_assessment,
            chain_state=risk_state,
            commit_policy=commit_policy,
            current_step=value.current_step,
        )
        and eligible_principal_snapshot_matches(
            membership_snapshot,
            epoch_state=membership_state,
            profile=value.profile,
            assurance=value.assurance,
            manifest_root=value.manifest_root,
            commit_policy_root=value.commit_policy_root,
            protocol_id=value.protocol_id,
            run_id=value.run_id,
            target=value.target,
            epoch=value.epoch,
            current_step=value.current_step,
        )
    )


def _base_assessment_heads_are_current(
    value: CommitLivenessInput,
    *,
    risk_state: RiskAssessmentChainState,
    membership_state: EligibleMembershipEpochState,
    support_state: SupportLeaseReplayState,
) -> bool:
    return bool(
        risk_assessment_chain_state_is_current(risk_state)
        and risk_assessment_chain_state_fingerprint(risk_state)
        == value.risk_chain_state_root
        and eligible_membership_epoch_state_is_current(membership_state)
        and eligible_membership_epoch_state_fingerprint(membership_state)
        == value.membership_epoch_state_root
        and support_lease_replay_state_is_current(support_state)
        and support_lease_replay_state_fingerprint(support_state)
        == value.support_replay_state_root
    )


def _validate_liveness_value_policy(
    value: CommitLivenessInput,
    commit_policy: CollectiveCommitPolicy,
) -> None:
    bindings = _normalized_window_bindings(
        profile=value.profile,
        assurance=value.assurance,
        manifest_root=value.manifest_root,
        commit_policy_root=value.commit_policy_root,
        protocol_id=value.protocol_id,
        run_id=value.run_id,
        target=value.target,
        epoch=value.epoch,
        field_name="commit liveness authority heads",
    )
    _validate_bound_commit_policy(commit_policy, bindings)


def _assessment_snapshot_roots_match(
    value: CommitLivenessInput,
    *,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
) -> bool:
    return bool(
        risk_assessment_fingerprint(risk_assessment) == value.risk_assessment_root
        and commit_threshold_snapshot_fingerprint(threshold_snapshot)
        == value.threshold_root
        and eligible_principal_snapshot_fingerprint(membership_snapshot)
        == value.membership_snapshot_root
        and membership_snapshot.membership_root == value.membership_root
    )


def _requires_fresh_snapshot(value: CommitLivenessInput) -> bool:
    return bool(
        value.sealed_window
        and value.current_step > value.sealed_at_step
        and not value.deadline_reached
    )


def validate_finality_verification_matches_window_impl(
    verification: CommitFinalityVerification,
    *,
    state: CommitWindowState,
    seal: CommitWindowSeal | None,
    current_step: int,
) -> None:
    if verification.verified_at_step != current_step:
        raise GovernanceError(
            "commit finality must be freshly verified at the liveness step"
        )
    if seal is None or not commit_window_seal_is_current(seal):
        raise GovernanceError(
            "commit finality requires the current receipt-backed seal"
        )
    if current_step >= min(
        seal.absolute_deadline_step,
        seal.absolute_run_deadline_step,
    ):
        raise GovernanceError("commit finality cannot be verified at its deadline")
    _validate_finality_scope(verification, state)
    _validate_finality_lineage(verification, seal)


def _validate_finality_scope(
    verification: CommitFinalityVerification,
    state: CommitWindowState,
) -> None:
    for name in _SCOPE_FIELDS:
        if getattr(verification, name) != getattr(state, name):
            raise GovernanceError(f"commit finality {name} binding mismatch")


def _validate_finality_lineage(
    verification: CommitFinalityVerification,
    seal: CommitWindowSeal,
) -> None:
    expected = {
        "candidate_id": seal.candidate_id,
        "context_ref": seal.context_ref,
        "assessment_ref": seal.assessment_ref,
        "window_state_ref": seal.window_state_ref,
        "window_root": seal.window_root,
        "risk_assessment_root": seal.risk_assessment_root,
        "risk_chain_state_root": seal.risk_chain_state_root,
        "risk_policy_root": seal.risk_policy_root,
        "membership_root": seal.membership_root,
        "membership_snapshot_root": seal.membership_snapshot_root,
        "membership_epoch_state_root": seal.membership_epoch_state_root,
        "threshold_root": seal.threshold_root,
        "replay_state_ref": seal.replay_state_ref,
        "replay_root": seal.replay_root,
        "support_replay_state_root": seal.support_replay_state_root,
        "support_replay_root": seal.support_replay_root,
        "collective_evidence_root": seal.collective_evidence_root,
        "collective_challenge_root": seal.collective_challenge_root,
        "collective_lease_root": seal.collective_lease_root,
        "candidate_evidence_root": seal.candidate_evidence_root,
        "candidate_challenge_root": seal.candidate_challenge_root,
        "candidate_lease_root": seal.candidate_lease_root,
        "stop_resolution_root": seal.stop_resolution_root,
        "permission_root": seal.permission_root,
    }
    for name, value in expected.items():
        if getattr(verification, name) != value:
            raise GovernanceError(f"commit finality {name} lineage mismatch")


__all__: list[str] = []
