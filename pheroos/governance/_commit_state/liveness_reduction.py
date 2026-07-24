"""Deterministic reduction of issued commit liveness inputs."""

from __future__ import annotations

from dataclasses import dataclass

from pheroos.governance._commit.common import AuthorityScope
from pheroos.governance._commit_state.invariants import (
    _normalized_window_bindings,
    _validate_bound_commit_policy,
)
from pheroos.governance._commit_state.liveness_authority import (
    liveness_authority_heads_are_current_impl,
    validate_liveness_input_matches_window_impl,
)
from pheroos.governance._commit_state.liveness_input import (
    commit_liveness_input_fingerprint_impl,
    commit_liveness_input_was_issued_impl,
)
from pheroos.governance._commit_state.records import (
    _CommitWindowCursor,
    CommitFinalityStatus,
    CommitLivenessInput,
    CommitWindowState,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionPhase,
    DecisionProgress,
    _issue_decision_outcome,
    _issue_decision_progress,
    decision_progress_fingerprint,
)
from pheroos.governance._commit_state.window import (
    commit_window_ready,
    commit_window_state_is_current,
)
from pheroos.governance._commit_terminal import select_terminal_outcome_kind
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)


@dataclass(frozen=True)
class ReductionFacts:
    current_step: int
    deadline_reached: bool
    run_deadline_reached: bool
    effective_deadline_reached: bool
    derived_blocked: bool
    outcome_kind: DecisionOutcomeKind | None


@dataclass(frozen=True)
class OutcomeAuthority:
    candidate_id: str
    scope: AuthorityScope
    authoritative: bool
    epistemically_committed: bool
    certificate_ref: str


def reduce_commit_liveness_impl(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
) -> DecisionProgress | DecisionOutcome:
    if not commit_window_state_is_current(state):
        raise GovernanceError("commit liveness requires the current window head")
    if not commit_liveness_input_was_issued_impl(liveness_input):
        raise GovernanceError("commit liveness input is not governance-issued")
    validate_liveness_input_matches_window_impl(state, liveness_input)
    _validate_policy(state, commit_policy)
    facts = _reduction_facts(state, commit_policy, liveness_input)
    request_fingerprint = _reduction_request_fingerprint(
        state,
        liveness_input,
        facts.outcome_kind,
    )
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window cursor is invalid")
    return _reduce_under_lock(
        state,
        commit_policy=commit_policy,
        liveness_input=liveness_input,
        facts=facts,
        cursor=cursor,
        request_fingerprint=request_fingerprint,
    )


def _validate_policy(
    state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy,
) -> None:
    bindings = _normalized_window_bindings(
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        field_name="commit liveness",
    )
    _validate_bound_commit_policy(commit_policy, bindings)


def _reduction_facts(
    state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy,
    value: CommitLivenessInput,
) -> ReductionFacts:
    current = value.current_step
    deadline_reached = current >= state.absolute_deadline_step
    run_deadline_reached = current >= state.absolute_run_deadline_step
    effective_deadline = deadline_reached or run_deadline_reached
    derived_blocked = _derived_blocked(value, effective_deadline)
    evidence_ready = _evidence_commit_ready(state, value, effective_deadline)
    finality_unavailable = finality_unavailable_at_deadline_impl(
        assurance=state.assurance,
        finality_status=value.finality_status,
        stability_satisfied=bool(
            commit_window_ready(state)
            and value.sealed_window
            and value.heartbeat_continuous
            and value.leader_ready_for_stability
        ),
        deadline_reached=effective_deadline,
    )
    outcome_kind = select_terminal_outcome_kind(
        invalid=bool(value.invalid_reason_codes),
        safety_violation=bool(
            value.safety_violation_reason_codes
            or value.assessment_status == "safety_violation"
            or value.finality_status is CommitFinalityStatus.CONFLICT
        ),
        blocked=bool(value.blocked_reason_codes or derived_blocked),
        evidence_commit_ready=evidence_ready,
        finality_unavailable=finality_unavailable,
        deadline_reached=effective_deadline,
        deadline_outcome=commit_policy.terminal_outcome.deadline_outcome,
    )
    return ReductionFacts(
        current_step=current,
        deadline_reached=deadline_reached,
        run_deadline_reached=run_deadline_reached,
        effective_deadline_reached=effective_deadline,
        derived_blocked=derived_blocked,
        outcome_kind=outcome_kind,
    )


def _derived_blocked(value: CommitLivenessInput, deadline_reached: bool) -> bool:
    hard_denial_codes = {"stop_blocked", "commit_permission_denied"}
    unresolved_authority_codes = {
        "stop_resolution_unresolved",
        "commit_permission_unresolved",
    }
    reasons = set(value.assessment_reason_codes)
    return bool(
        hard_denial_codes.intersection(reasons)
        or (deadline_reached and unresolved_authority_codes.intersection(reasons))
    )


def _evidence_commit_ready(
    state: CommitWindowState,
    value: CommitLivenessInput,
    deadline_reached: bool,
) -> bool:
    assurance_step_valid = bool(
        (
            state.assurance is CommitAssurance.EVIDENCE_BOUND
            and value.current_step == state.last_evaluated_step
            and value.current_step == value.sealed_at_step
        )
        or (
            state.assurance in {CommitAssurance.CERTIFIED, CommitAssurance.DISTRIBUTED}
            and value.current_step >= value.sealed_at_step
        )
    )
    return all(
        (
            state.assurance is not CommitAssurance.ADVISORY,
            not deadline_reached,
            commit_window_ready(state),
            value.sealed_window,
            value.heartbeat_continuous,
            assurance_step_valid,
            value.leader_ready_for_stability,
            finality_satisfied_impl(value),
        )
    )


def _reduction_request_fingerprint(
    state: CommitWindowState,
    value: CommitLivenessInput,
    outcome_kind: DecisionOutcomeKind | None,
) -> str:
    return commit_payload_fingerprint(
        {
            "liveness_input": commit_liveness_input_fingerprint_impl(value),
            "outcome_kind": outcome_kind.value if outcome_kind is not None else "",
            "window_state": value.window_state_ref,
        },
        schema="pheroos-commit-liveness-reduction-request-v1",
        profile=state.profile,
    )


def _reduce_under_lock(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
    facts: ReductionFacts,
    cursor: _CommitWindowCursor,
    request_fingerprint: str,
) -> DecisionProgress | DecisionOutcome:
    cache_key = (liveness_input.window_state_ref, facts.current_step)
    with cursor.lock:
        cached = cursor.liveness_results.get(cache_key)
        if cached is not None:
            if cached[0] == request_fingerprint:
                return cached[1]
            raise GovernanceError("commit liveness decision would fork")
        _require_live_authority_and_open_window(liveness_input, cursor)
        result = _issue_reduction_result(
            state,
            commit_policy=commit_policy,
            liveness_input=liveness_input,
            facts=facts,
        )
        _record_reduction_result(cursor, cache_key, request_fingerprint, result)
        return result


def _require_live_authority_and_open_window(
    value: CommitLivenessInput,
    cursor: _CommitWindowCursor,
) -> None:
    if not liveness_authority_heads_are_current_impl(value):
        raise GovernanceError("commit liveness authority heads are no longer current")
    if cursor.terminal_result is not None:
        raise GovernanceError("commit window already has a terminal outcome")


def _issue_reduction_result(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
    facts: ReductionFacts,
) -> DecisionProgress | DecisionOutcome:
    if facts.outcome_kind is None:
        return progress_from_liveness_impl(state, liveness_input)
    return outcome_from_liveness_impl(
        state,
        commit_policy=commit_policy,
        liveness_input=liveness_input,
        kind=facts.outcome_kind,
        deadline_reached=facts.effective_deadline_reached,
        run_deadline_reached=facts.run_deadline_reached,
        derived_blocked=facts.derived_blocked,
    )


def _record_reduction_result(
    cursor: _CommitWindowCursor,
    cache_key: tuple[str, int],
    request_fingerprint: str,
    result: DecisionProgress | DecisionOutcome,
) -> None:
    if isinstance(result, DecisionProgress):
        cursor.current_progress = result
        cursor.current_progress_fingerprint = decision_progress_fingerprint(result)
    else:
        cursor.terminal_result = result
        cursor.current_progress = None
        cursor.current_progress_fingerprint = ""
    cursor.liveness_results[cache_key] = (request_fingerprint, result)


def finality_satisfied_impl(value: CommitLivenessInput) -> bool:
    if value.assurance in {
        CommitAssurance.EVIDENCE_BOUND,
        CommitAssurance.CERTIFIED,
        CommitAssurance.DISTRIBUTED,
    }:
        return bool(
            value.finality_status is CommitFinalityStatus.VERIFIED
            and value.certificate_ref
            and value.finality_verification_ref
        )
    return False


def finality_unavailable_at_deadline_impl(
    *,
    assurance: CommitAssurance,
    finality_status: CommitFinalityStatus,
    stability_satisfied: bool,
    deadline_reached: bool,
) -> bool:
    return bool(
        assurance in {CommitAssurance.CERTIFIED, CommitAssurance.DISTRIBUTED}
        and stability_satisfied
        and deadline_reached
        and finality_status
        in {
            CommitFinalityStatus.PENDING,
            CommitFinalityStatus.PROVISIONAL,
            CommitFinalityStatus.UNAVAILABLE,
        }
    )


def progress_from_liveness_impl(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> DecisionProgress:
    if value.current_step >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError("decision progress cannot survive a deadline")
    phase = _progress_phase(state, value)
    requirements, unmet = _progress_requirements(state, value)
    return _issue_decision_progress(
        phase=phase,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=value.current_step,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        remaining_reset_budget=state.remaining_reset_budget,
        remaining_epoch_restart_budget=state.remaining_epoch_restart_budget,
        minimum_stability_steps=state.minimum_stability_steps,
        context_ref=value.context_ref,
        risk_assessment_root=state.risk_assessment_root,
        risk_chain_state_root=state.risk_chain_state_root,
        risk_policy_root=state.risk_policy_root,
        membership_root=state.membership_root,
        membership_snapshot_root=state.membership_snapshot_root,
        membership_epoch_state_root=state.membership_epoch_state_root,
        threshold_root=state.threshold_root,
        replay_state_ref=value.replay_state_ref,
        replay_root=value.replay_root,
        support_replay_state_root=state.support_replay_state_root,
        support_replay_root=state.support_replay_root,
        collective_evidence_root=state.collective_evidence_root,
        collective_challenge_root=state.collective_challenge_root,
        collective_lease_root=state.collective_lease_root,
        candidate_evidence_root=state.candidate_evidence_root,
        candidate_challenge_root=state.candidate_challenge_root,
        candidate_lease_root=state.candidate_lease_root,
        stop_resolution_root=state.stop_resolution_root,
        permission_root=state.permission_root,
        window_state_ref=value.window_state_ref,
        window_root=state.window_root,
        sealed_window=value.sealed_window,
        seal_ref=value.seal_ref,
        sealed_at_step=value.sealed_at_step,
        heartbeat_continuous=value.heartbeat_continuous,
        heartbeat_sequence=value.heartbeat_sequence,
        previous_progress_ref=value.previous_progress_ref,
        next_required_inputs=tuple(requirements),
        unmet_gates=tuple(unmet),
        leader_candidate_id=(
            state.leader_candidate_id if state.last_ready else value.leader_candidate_id
        ),
        window_count=state.window_count,
        assessment_ref=value.assessment_ref,
    )


def _progress_phase(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> DecisionPhase:
    if not value.assessment_ref:
        return DecisionPhase.SEARCH
    if (
        commit_window_ready(state)
        and value.sealed_window
        and not finality_satisfied_impl(value)
    ):
        return DecisionPhase.PROVISIONAL
    if state.last_ready:
        return DecisionPhase.QUORUM_PENDING
    return DecisionPhase.DELIBERATE


def _progress_requirements(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> tuple[set[str], set[str]]:
    requirements = set(value.next_required_inputs)
    unmet = set(value.assessment_reason_codes)
    if not value.assessment_ref:
        requirements.add("commit_assessment")
    elif state.last_ready and not commit_window_ready(state):
        requirements.add("consecutive_stability_assessment")
    elif commit_window_ready(state) and not value.sealed_window:
        requirements.add("local_commit_receipt")
    elif commit_window_ready(state) and not finality_satisfied_impl(value):
        requirements.add("verified_finality")
    if not requirements and not unmet:
        requirements.add("next_commit_assessment")
    return requirements, unmet


def outcome_from_liveness_impl(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
    kind: DecisionOutcomeKind,
    deadline_reached: bool,
    run_deadline_reached: bool,
    derived_blocked: bool,
) -> DecisionOutcome:
    reasons = _outcome_reasons(
        kind,
        liveness_input,
        deadline_reached=deadline_reached,
        run_deadline_reached=run_deadline_reached,
        derived_blocked=derived_blocked,
    )
    authority = _outcome_authority(state, commit_policy, liveness_input, kind)
    return _issue_decision_outcome(
        kind=kind,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=liveness_input.current_step,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        authority_scope=authority.scope,
        authoritative_commit=authority.authoritative,
        epistemically_committed=authority.epistemically_committed,
        context_ref=liveness_input.context_ref,
        risk_assessment_root=state.risk_assessment_root,
        risk_chain_state_root=state.risk_chain_state_root,
        risk_policy_root=state.risk_policy_root,
        membership_root=state.membership_root,
        membership_snapshot_root=state.membership_snapshot_root,
        membership_epoch_state_root=state.membership_epoch_state_root,
        threshold_root=state.threshold_root,
        replay_state_ref=liveness_input.replay_state_ref,
        replay_root=liveness_input.replay_root,
        support_replay_state_root=state.support_replay_state_root,
        support_replay_root=state.support_replay_root,
        collective_evidence_root=state.collective_evidence_root,
        collective_challenge_root=state.collective_challenge_root,
        collective_lease_root=state.collective_lease_root,
        candidate_evidence_root=state.candidate_evidence_root,
        candidate_challenge_root=state.candidate_challenge_root,
        candidate_lease_root=state.candidate_lease_root,
        stop_resolution_root=state.stop_resolution_root,
        permission_root=state.permission_root,
        window_state_ref=liveness_input.window_state_ref,
        window_root=state.window_root,
        sealed_window=liveness_input.sealed_window,
        seal_ref=liveness_input.seal_ref,
        sealed_at_step=liveness_input.sealed_at_step,
        heartbeat_continuous=liveness_input.heartbeat_continuous,
        heartbeat_sequence=liveness_input.heartbeat_sequence,
        previous_progress_ref=liveness_input.previous_progress_ref,
        candidate_id=authority.candidate_id,
        reason_codes=tuple(reasons),
        assessment_ref=liveness_input.assessment_ref,
        certificate_ref=authority.certificate_ref,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
    )


def _outcome_reasons(
    kind: DecisionOutcomeKind,
    value: CommitLivenessInput,
    *,
    deadline_reached: bool,
    run_deadline_reached: bool,
    derived_blocked: bool,
) -> set[str]:
    reasons: set[str] = set()
    if kind is DecisionOutcomeKind.INVALID:
        reasons.update(value.invalid_reason_codes)
        reasons.add("invalid")
    elif kind is DecisionOutcomeKind.SAFETY_VIOLATION:
        reasons.update(value.safety_violation_reason_codes)
        reasons.update(value.assessment_reason_codes)
        reasons.update(value.finality_reason_codes)
        reasons.add("safety_violation")
    elif kind is DecisionOutcomeKind.BLOCKED:
        reasons.update(value.blocked_reason_codes)
        if derived_blocked:
            reasons.update(value.assessment_reason_codes)
        reasons.add("blocked")
    elif kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        reasons.update(("evidence_commit", "stability_satisfied"))
        if value.current_step > value.sealed_at_step:
            reasons.add("late_finality_verified")
    elif kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE:
        reasons.update(value.finality_reason_codes)
        reasons.add("finality_unavailable")
    else:
        reasons.add(kind.value)
    if deadline_reached:
        reasons.add("deadline_reached")
    if run_deadline_reached:
        reasons.add("run_deadline_reached")
    return reasons


def _outcome_authority(
    state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy,
    value: CommitLivenessInput,
    kind: DecisionOutcomeKind,
) -> OutcomeAuthority:
    if kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        return OutcomeAuthority(
            state.leader_candidate_id,
            AuthorityScope(COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE[state.assurance.value]),
            True,
            True,
            value.certificate_ref,
        )
    if kind is DecisionOutcomeKind.SAFE_FALLBACK:
        return OutcomeAuthority(
            commit_policy.terminal_outcome.safe_fallback_candidate,
            AuthorityScope.NONE,
            False,
            False,
            "",
        )
    if kind is DecisionOutcomeKind.ADVISORY:
        return OutcomeAuthority(
            value.leader_candidate_id,
            AuthorityScope.NONE,
            False,
            False,
            "",
        )
    if kind is DecisionOutcomeKind.BLOCKED:
        return OutcomeAuthority("", AuthorityScope.DENIAL, False, False, "")
    return OutcomeAuthority("", AuthorityScope.NONE, False, False, "")


__all__: list[str] = []
