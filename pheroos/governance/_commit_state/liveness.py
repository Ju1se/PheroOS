"""Static public owner for governed commit liveness semantics."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._commit_state.records import (
    CommitFinalityStatus,
    CommitFinalityVerification,
    CommitLivenessInput,
    CommitReplayState,
    CommitWindowSeal,
    CommitWindowState,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionProgress,
)
from pheroos.governance._commit_terminal import (
    select_terminal_outcome_kind as _select_terminal_outcome_kind,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.protocol.commit_models import CollectiveCommitPolicy, CommitAssurance


def select_terminal_outcome_kind(
    *,
    invalid: bool,
    safety_violation: bool,
    blocked: bool,
    evidence_commit_ready: bool,
    finality_unavailable: bool,
    deadline_reached: bool,
    deadline_outcome: str,
) -> DecisionOutcomeKind | None:
    """Select the first declared terminal condition in canonical priority order."""

    return _select_terminal_outcome_kind(
        invalid=invalid,
        safety_violation=safety_violation,
        blocked=blocked,
        evidence_commit_ready=evidence_commit_ready,
        finality_unavailable=finality_unavailable,
        deadline_reached=deadline_reached,
        deadline_outcome=deadline_outcome,
    )


def issue_commit_liveness_input(
    state: CommitWindowState,
    *,
    assessment: object | None,
    replay_state: CommitReplayState,
    risk_chain_state: object | None,
    risk_assessment: object | None = None,
    threshold_snapshot: object | None = None,
    membership_snapshot: object | None = None,
    membership_epoch_state: object | None,
    support_replay_state: object | None,
    commit_policy: CollectiveCommitPolicy | None = None,
    previous_progress: DecisionProgress | None = None,
    current_step: int,
    finality_status: CommitFinalityStatus,
    finality_verification: CommitFinalityVerification | None = None,
    certificate_ref: str = "",
    invalid_reason_codes: Sequence[str] = (),
    safety_violation_reason_codes: Sequence[str] = (),
    blocked_reason_codes: Sequence[str] = (),
    finality_reason_codes: Sequence[str] = (),
    next_required_inputs: Sequence[str] = (),
    input_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitLivenessInput:
    """Qualify temporal facts without accepting a caller readiness boolean."""

    from pheroos.governance._commit_state.liveness_input import (
        CommitLivenessInputRequest,
        issue_commit_liveness_input_impl,
    )

    return issue_commit_liveness_input_impl(
        CommitLivenessInputRequest(
            state=state,
            assessment=assessment,
            replay_state=replay_state,
            risk_chain_state=risk_chain_state,
            risk_assessment=risk_assessment,
            threshold_snapshot=threshold_snapshot,
            membership_snapshot=membership_snapshot,
            membership_epoch_state=membership_epoch_state,
            support_replay_state=support_replay_state,
            commit_policy=commit_policy,
            previous_progress=previous_progress,
            current_step=current_step,
            finality_status=finality_status,
            finality_verification=finality_verification,
            certificate_ref=certificate_ref,
            invalid_reason_codes=invalid_reason_codes,
            safety_violation_reason_codes=safety_violation_reason_codes,
            blocked_reason_codes=blocked_reason_codes,
            finality_reason_codes=finality_reason_codes,
            next_required_inputs=next_required_inputs,
            input_id=input_id,
            issuer_id=issuer_id,
            authority=authority,
            provenance=provenance,
            trace_event_id=trace_event_id,
        )
    )


def reduce_commit_liveness(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
) -> DecisionProgress | DecisionOutcome:
    """Reduce one logical step to issued progress or a deliverable terminal outcome."""

    from pheroos.governance._commit_state.liveness_reduction import (
        reduce_commit_liveness_impl,
    )

    return reduce_commit_liveness_impl(
        state,
        commit_policy=commit_policy,
        liveness_input=liveness_input,
    )


def commit_liveness_input_is_authoritative(value: object) -> bool:
    if type(value) is not CommitLivenessInput:
        return False
    return bool(
        _commit_liveness_input_was_issued(value)
        and _liveness_authority_heads_are_current(value)
    )


def _commit_liveness_input_was_issued(value: object) -> bool:
    from pheroos.governance._commit_state.liveness_input import (
        commit_liveness_input_was_issued_impl,
    )

    return commit_liveness_input_was_issued_impl(value)


def commit_liveness_input_payload(
    value: CommitLivenessInput,
) -> dict[str, object]:
    from pheroos.governance._commit_state.liveness_input import (
        commit_liveness_input_payload_impl,
    )

    return commit_liveness_input_payload_impl(value)


def commit_liveness_input_fingerprint(value: CommitLivenessInput) -> str:
    from pheroos.governance._commit_state.liveness_input import (
        commit_liveness_input_fingerprint_impl,
    )

    return commit_liveness_input_fingerprint_impl(value)


def _validate_liveness_input_matches_window(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> None:
    from pheroos.governance._commit_state.liveness_authority import (
        validate_liveness_input_matches_window_impl,
    )

    validate_liveness_input_matches_window_impl(state, value)


def _validate_liveness_current_authority_heads(
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
    from pheroos.governance._commit_state.liveness_authority import (
        validate_liveness_current_authority_heads_impl,
    )

    validate_liveness_current_authority_heads_impl(
        state,
        commit_policy=commit_policy,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        support_replay_state=support_replay_state,
        current_step=current_step,
        require_fresh_snapshot=require_fresh_snapshot,
    )


def _liveness_authority_heads_are_current(value: CommitLivenessInput) -> bool:
    from pheroos.governance._commit_state.liveness_authority import (
        liveness_authority_heads_are_current_impl,
    )

    return liveness_authority_heads_are_current_impl(value)


def _validate_finality_verification_matches_window(
    verification: CommitFinalityVerification,
    *,
    state: CommitWindowState,
    seal: CommitWindowSeal | None,
    current_step: int,
) -> None:
    from pheroos.governance._commit_state.liveness_authority import (
        validate_finality_verification_matches_window_impl,
    )

    validate_finality_verification_matches_window_impl(
        verification,
        state=state,
        seal=seal,
        current_step=current_step,
    )


def _finality_satisfied(value: CommitLivenessInput) -> bool:
    from pheroos.governance._commit_state.liveness_reduction import (
        finality_satisfied_impl,
    )

    return finality_satisfied_impl(value)


def _finality_unavailable_at_deadline(
    *,
    assurance: CommitAssurance,
    finality_status: CommitFinalityStatus,
    stability_satisfied: bool,
    deadline_reached: bool,
) -> bool:
    from pheroos.governance._commit_state.liveness_reduction import (
        finality_unavailable_at_deadline_impl,
    )

    return finality_unavailable_at_deadline_impl(
        assurance=assurance,
        finality_status=finality_status,
        stability_satisfied=stability_satisfied,
        deadline_reached=deadline_reached,
    )


def _progress_from_liveness(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> DecisionProgress:
    from pheroos.governance._commit_state.liveness_reduction import (
        progress_from_liveness_impl,
    )

    return progress_from_liveness_impl(state, value)


def _outcome_from_liveness(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
    kind: DecisionOutcomeKind,
    deadline_reached: bool,
    run_deadline_reached: bool,
    derived_blocked: bool,
) -> DecisionOutcome:
    from pheroos.governance._commit_state.liveness_reduction import (
        outcome_from_liveness_impl,
    )

    return outcome_from_liveness_impl(
        state,
        commit_policy=commit_policy,
        liveness_input=liveness_input,
        kind=kind,
        deadline_reached=deadline_reached,
        run_deadline_reached=run_deadline_reached,
        derived_blocked=derived_blocked,
    )


for _name in (
    "select_terminal_outcome_kind",
    "issue_commit_liveness_input",
    "reduce_commit_liveness",
    "commit_liveness_input_is_authoritative",
    "_commit_liveness_input_was_issued",
    "commit_liveness_input_payload",
    "commit_liveness_input_fingerprint",
    "_validate_liveness_input_matches_window",
    "_validate_liveness_current_authority_heads",
    "_liveness_authority_heads_are_current",
    "_validate_finality_verification_matches_window",
    "_finality_satisfied",
    "_finality_unavailable_at_deadline",
    "_progress_from_liveness",
    "_outcome_from_liveness",
):
    globals()[_name].__module__ = "pheroos.governance.commit_state"
del _name


__all__ = [
    "select_terminal_outcome_kind",
    "issue_commit_liveness_input",
    "reduce_commit_liveness",
    "commit_liveness_input_is_authoritative",
    "_commit_liveness_input_was_issued",
    "commit_liveness_input_payload",
    "commit_liveness_input_fingerprint",
    "_validate_liveness_input_matches_window",
    "_validate_liveness_current_authority_heads",
    "_liveness_authority_heads_are_current",
    "_validate_finality_verification_matches_window",
    "_finality_satisfied",
    "_finality_unavailable_at_deadline",
    "_progress_from_liveness",
    "_outcome_from_liveness",
]
