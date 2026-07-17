from __future__ import annotations

from collections.abc import Sequence

from dataclasses import dataclass, field

from enum import StrEnum

from pheroos.governance._commit_state.invariants import (
    _normalized_labels,
    _normalized_window_bindings,
    _require_binding,
    _require_non_negative_integer,
    _validate_bound_commit_policy,
    _validate_commit_binding_values,
    _validate_profile_assurance,
)

from pheroos.governance._commit_state._liveness_contract import (
    _validate_assessment_lineage_roots,
    _validate_sealed_heartbeat_lineage,
)

from pheroos.governance._commit_state.payloads import (
    build_commit_liveness_input_payload,
    build_commit_window_state_payload,
    build_decision_outcome_payload,
    build_decision_progress_payload,
)

from pheroos.governance._commit_state.records import (
    _COMMIT_FINALITY_VERIFICATION_ISSUANCE,
    _COMMIT_LIVENESS_INPUT_ISSUANCE,
    _COMMIT_REPLAY_STATE_ISSUANCE,
    _COMMIT_WINDOW_SEAL_ISSUANCE,
    _COMMIT_WINDOW_STATE_ISSUANCE,
    _DECISION_OUTCOME_ISSUANCE,
    _DECISION_PROGRESS_ISSUANCE,
    _LEGACY_COMMIT_REPLAY_CURSORS,
    _LEGACY_COMMIT_WINDOW_CURSORS,
    _CommitReplayCursor,
    _CommitWindowCursor,
)

from pheroos.governance._commit_state._replay_contract import (
    canonical_replay_receipts as _canonical_replay_receipts_engine,
)

from pheroos.governance._commit_state._window_contract import (
    _authoritative_commit_assessment_view,
    _commit_window_authority_key,
    _threshold_snapshot_bindings,
    _validate_assessment_matches_window_head,
    _validate_window_chain_scope,
    _validate_window_threshold_snapshot,
    _window_reset_reason,
    _window_root,
)

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)

from pheroos.governance._commit.common import AuthorityScope

from pheroos.governance._commit.local_receipt import (
    LocalCommitReceipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
)

from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)

from pheroos.governance.commit_numeric import (
    checked_add,
    commit_payload_fingerprint,
)

from pheroos.governance.authority import AuthorityLevel, can_verify

from pheroos.governance.errors import GovernanceError

from pheroos.protocol.commit_models import (
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)

from pheroos.governance._commit_state.records import (
    _DECISION_PROGRESS_ISSUANCE,
    _DECISION_OUTCOME_ISSUANCE,
    _COMMIT_WINDOW_STATE_ISSUANCE,
    _COMMIT_WINDOW_SEAL_ISSUANCE,
    _COMMIT_REPLAY_STATE_ISSUANCE,
    _COMMIT_LIVENESS_INPUT_ISSUANCE,
    _COMMIT_FINALITY_VERIFICATION_ISSUANCE,
    _LEGACY_COMMIT_WINDOW_CURSORS,
    _LEGACY_COMMIT_REPLAY_CURSORS,
    _CommitWindowCursor,
    _CommitReplayCursor,
    DecisionPhase,
    DecisionOutcomeKind,
    CommitFinalityStatus,
    ReplayNamespace,
    DecisionProgress,
    DecisionOutcome,
    CommitWindowState,
    CommitWindowSeal,
    CommitLivenessInput,
    CommitFinalityVerification,
    ReplayReceipt,
    CommitReplayState,
    decision_progress_is_authoritative,
    decision_outcome_is_authoritative,
    _issue_commit_finality_verification,
    commit_finality_verification_payload,
    commit_finality_verification_fingerprint,
    commit_finality_verification_is_authoritative,
    _issue_decision_progress,
    _issue_decision_outcome,
    _issue_commit_window_state,
    _issue_commit_replay_state,
    commit_window_state_is_authoritative,
    commit_window_state_is_current,
    commit_replay_state_is_authoritative,
    commit_replay_state_is_current,
    commit_window_state_payload,
    commit_window_state_fingerprint,
    replay_receipt_payload,
    replay_receipt_fingerprint,
    commit_replay_state_contains,
    commit_replay_state_matches,
    commit_replay_state_payload,
    commit_replay_state_fingerprint,
    _validate_commit_window_state,
    _validate_commit_window_seal,
    _validate_commit_liveness_input,
    _validate_commit_finality_verification,
    _validate_commit_replay_state,
    _validate_replay_receipt,
    _canonical_replay_receipts,
    _commit_replay_receipt_root,
    _validate_decision_progress,
    _validate_decision_outcome,
    _progress_snapshot,
    _outcome_snapshot,
    decision_progress_payload,
    decision_outcome_payload,
    decision_progress_fingerprint,
    decision_outcome_fingerprint,
)

from pheroos.governance._commit_state.window import (
    initialize_commit_window_state,
    advance_commit_window_state,
    reset_commit_window_state,
    _transition_commit_window_state,
    restart_commit_window_epoch,
    commit_window_ready,
    _seal_commit_window_from_local_receipt,
    commit_window_seal_for_state,
    commit_window_seal_is_authoritative,
    commit_window_seal_is_current,
    commit_window_seal_matches_receipt,
    commit_window_seal_payload,
    commit_window_seal_fingerprint,
)

from pheroos.governance._commit_state.replay import (
    initialize_commit_replay_state,
    record_commit_replay_receipts,
)


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
    for field_name, value in (
        ("invalid", invalid),
        ("safety_violation", safety_violation),
        ("blocked", blocked),
        ("evidence_commit_ready", evidence_commit_ready),
        ("finality_unavailable", finality_unavailable),
        ("deadline_reached", deadline_reached),
    ):
        if type(value) is not bool:
            raise GovernanceError(f"terminal condition {field_name} must be boolean")
    if deadline_outcome not in {
        DecisionOutcomeKind.SAFE_FALLBACK.value,
        DecisionOutcomeKind.ADVISORY.value,
    }:
        raise GovernanceError("terminal deadline outcome is unsupported")
    if invalid:
        return DecisionOutcomeKind.INVALID
    if safety_violation:
        return DecisionOutcomeKind.SAFETY_VIOLATION
    if blocked:
        return DecisionOutcomeKind.BLOCKED
    if evidence_commit_ready:
        return DecisionOutcomeKind.EVIDENCE_COMMIT
    if finality_unavailable:
        return DecisionOutcomeKind.FINALITY_UNAVAILABLE
    if deadline_reached:
        return DecisionOutcomeKind(deadline_outcome)
    return None


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

    if not commit_window_state_is_current(state):
        raise GovernanceError("commit liveness requires the current window head")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("commit liveness input requires governance authority")
    current = require_commit_step(current_step, "commit liveness current_step")
    if current < state.last_evaluated_step:
        raise GovernanceError("commit liveness step cannot precede the window head")
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit liveness window cursor is invalid")
    deadline_reached = current >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    )
    seal = commit_window_seal_for_state(state)
    seal_ref = commit_window_seal_fingerprint(seal) if seal is not None else ""
    sealed_at_step = seal.sealed_at_step if seal is not None else 0
    previous_progress_ref = ""
    heartbeat_sequence = 0
    heartbeat_continuous = True
    if current == state.last_evaluated_step:
        if previous_progress is not None:
            raise GovernanceError(
                "initial liveness step cannot consume a previous heartbeat"
            )
    elif seal is not None:
        if previous_progress is None:
            if not deadline_reached:
                raise GovernanceError(
                    "late finality requires the authoritative previous heartbeat"
                )
            heartbeat_continuous = False
        else:
            if not decision_progress_is_authoritative(previous_progress):
                raise GovernanceError(
                    "late finality previous heartbeat is not authoritative"
                )
            with cursor.lock:
                if cursor.current_progress is not previous_progress:
                    raise GovernanceError(
                        "late finality previous heartbeat is not the current head"
                    )
            if previous_progress.current_step + 1 != current:
                raise GovernanceError(
                    "late finality heartbeat must advance exactly one logical step"
                )
            if (
                not previous_progress.sealed_window
                or not previous_progress.heartbeat_continuous
                or previous_progress.seal_ref != seal_ref
                or previous_progress.sealed_at_step != seal.sealed_at_step
                or previous_progress.window_state_ref != seal.window_state_ref
                or previous_progress.window_root != seal.window_root
            ):
                raise GovernanceError(
                    "late finality previous heartbeat does not preserve the seal"
                )
            previous_progress_ref = decision_progress_fingerprint(previous_progress)
            heartbeat_sequence = previous_progress.heartbeat_sequence + 1
    elif (
        current > state.last_evaluated_step
        and commit_window_ready(state)
        and not deadline_reached
    ):
        raise GovernanceError("stable window requires a same-step local receipt seal")
    elif previous_progress is not None:
        raise GovernanceError(
            "unsealed liveness cannot consume a sealed-window heartbeat"
        )
    if not commit_replay_state_matches(
        replay_state,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        current_step=current,
    ):
        raise GovernanceError("commit liveness replay head is not authoritative")

    if assessment is None:
        if state.last_assessment_ref:
            raise GovernanceError(
                "commit liveness must consume the window head assessment"
            )
        assessment_ref = ""
        context_ref = ""
        assessment_status = ""
        leader = ""
        ready = False
        assessment_reasons: tuple[str, ...] = ()
    else:
        view = _authoritative_commit_assessment_view(assessment)
        _validate_assessment_matches_window_head(state, view)
        if (
            commit_replay_state_fingerprint(replay_state)
            != state.assessment_replay_state_ref
            or replay_state.receipt_root != state.assessment_replay_root
        ):
            raise GovernanceError(
                "commit liveness replay head changed after the assessment"
            )
        _validate_liveness_current_authority_heads(
            state,
            commit_policy=commit_policy,
            risk_chain_state=risk_chain_state,
            risk_assessment=risk_assessment,
            threshold_snapshot=threshold_snapshot,
            membership_snapshot=membership_snapshot,
            membership_epoch_state=membership_epoch_state,
            support_replay_state=support_replay_state,
            current_step=current,
            require_fresh_snapshot=bool(
                seal is not None
                and current > seal.sealed_at_step
                and not deadline_reached
            ),
        )
        assessment_ref = str(view["assessment_ref"])
        context_ref = str(view["context_ref"])
        assessment_status = str(view["status"])
        leader = str(view["leader_candidate_id"])
        ready = bool(view["ready"])
        assessment_reasons = tuple(view["reason_codes"])

    if type(finality_status) is not CommitFinalityStatus:
        raise GovernanceError("commit liveness finality status is invalid")
    if finality_status is CommitFinalityStatus.VERIFIED:
        if not commit_finality_verification_is_authoritative(finality_verification):
            raise GovernanceError(
                "verified finality requires an authoritative typed verification"
            )
        assert finality_verification is not None
        _validate_finality_verification_matches_window(
            finality_verification,
            state=state,
            seal=seal,
            current_step=current,
        )
        if seal is None:
            raise GovernanceError(
                "verified finality requires the current receipt-backed seal"
            )
        if state.assurance is CommitAssurance.EVIDENCE_BOUND and (
            current != seal.sealed_at_step
            or finality_verification.certificate_ref != seal.receipt_ref
        ):
            raise GovernanceError(
                "evidence-bound finality requires its same-step local receipt"
            )
        if certificate_ref:
            raise GovernanceError(
                "verified finality cannot accept a bare certificate reference"
            )
        certificate = finality_verification.certificate_ref
        finality_verification_ref = commit_finality_verification_fingerprint(
            finality_verification
        )
    elif finality_verification is not None:
        raise GovernanceError(
            "non-verified finality cannot carry a finality verification"
        )
    elif certificate_ref:
        raise GovernanceError(
            "commit liveness cannot accept a bare certificate reference"
        )
    else:
        certificate = ""
        finality_verification_ref = ""

    value = CommitLivenessInput(
        input_id=require_commit_text(input_id, "commit liveness input_id"),
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        current_step=current,
        deadline_reached=deadline_reached,
        context_ref=context_ref,
        assessment_ref=assessment_ref,
        assessment_status=assessment_status,
        leader_candidate_id=leader,
        leader_ready_for_stability=ready,
        assessment_reason_codes=assessment_reasons,
        replay_state_ref=commit_replay_state_fingerprint(replay_state),
        replay_root=replay_state.receipt_root,
        risk_assessment_root=state.risk_assessment_root,
        risk_chain_state_root=state.risk_chain_state_root,
        risk_policy_root=state.risk_policy_root,
        membership_root=state.membership_root,
        membership_snapshot_root=state.membership_snapshot_root,
        membership_epoch_state_root=state.membership_epoch_state_root,
        threshold_root=state.threshold_root,
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
        window_state_ref=commit_window_state_fingerprint(state),
        sealed_window=seal is not None,
        seal_ref=seal_ref,
        sealed_at_step=sealed_at_step,
        heartbeat_continuous=heartbeat_continuous,
        heartbeat_sequence=heartbeat_sequence,
        previous_progress_ref=previous_progress_ref,
        finality_status=finality_status,
        certificate_ref=certificate,
        finality_verification_ref=finality_verification_ref,
        invalid_reason_codes=tuple(invalid_reason_codes),
        safety_violation_reason_codes=tuple(safety_violation_reason_codes),
        blocked_reason_codes=tuple(blocked_reason_codes),
        finality_reason_codes=tuple(finality_reason_codes),
        next_required_inputs=tuple(next_required_inputs),
        issuer_id=require_commit_text(issuer_id, "commit liveness issuer_id"),
        authority=authority,
        provenance=require_commit_text(
            provenance,
            "commit liveness provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit liveness trace_event_id",
        ),
    )
    object.__setattr__(
        value,
        "_issuance",
        (_COMMIT_LIVENESS_INPUT_ISSUANCE, commit_liveness_input_fingerprint(value)),
    )
    object.__setattr__(
        value,
        "_authority_heads",
        (
            replay_state,
            risk_chain_state,
            risk_assessment,
            threshold_snapshot,
            membership_snapshot,
            membership_epoch_state,
            support_replay_state,
            commit_policy,
        ),
    )
    request_ref = commit_liveness_input_fingerprint(value)
    cache_key = value.input_id
    with cursor.lock:
        cached = cursor.liveness_inputs.get(cache_key)
        if cached is not None:
            if cached[0] == request_ref:
                return cached[1]
            raise GovernanceError("commit liveness input id would fork")
        cursor.liveness_inputs[cache_key] = (request_ref, value)
        return value


def reduce_commit_liveness(
    state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    liveness_input: CommitLivenessInput,
) -> DecisionProgress | DecisionOutcome:
    """Reduce one logical step to issued progress or a deliverable terminal outcome."""

    if not commit_window_state_is_current(state):
        raise GovernanceError("commit liveness requires the current window head")
    if not _commit_liveness_input_was_issued(liveness_input):
        raise GovernanceError("commit liveness input is not governance-issued")
    _validate_liveness_input_matches_window(state, liveness_input)
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

    current = liveness_input.current_step
    deadline_reached = current >= state.absolute_deadline_step
    run_deadline_reached = current >= state.absolute_run_deadline_step
    effective_deadline_reached = deadline_reached or run_deadline_reached
    assessment_safety = liveness_input.assessment_status == "safety_violation"
    hard_denial_codes = {
        "stop_blocked",
        "commit_permission_denied",
    }
    unresolved_authority_codes = {
        "stop_resolution_unresolved",
        "commit_permission_unresolved",
    }
    derived_blocked = bool(
        hard_denial_codes.intersection(liveness_input.assessment_reason_codes)
        or (
            effective_deadline_reached
            and unresolved_authority_codes.intersection(
                liveness_input.assessment_reason_codes
            )
        )
    )
    finality_satisfied = _finality_satisfied(liveness_input)
    before_deadline = not effective_deadline_reached
    assurance_step_valid = bool(
        (
            state.assurance is CommitAssurance.EVIDENCE_BOUND
            and current == state.last_evaluated_step
            and current == liveness_input.sealed_at_step
        )
        or (
            state.assurance in {CommitAssurance.CERTIFIED, CommitAssurance.DISTRIBUTED}
            and current >= liveness_input.sealed_at_step
        )
    )
    evidence_ready = bool(
        state.assurance is not CommitAssurance.ADVISORY
        and before_deadline
        and commit_window_ready(state)
        and liveness_input.sealed_window
        and liveness_input.heartbeat_continuous
        and assurance_step_valid
        and liveness_input.leader_ready_for_stability
        and finality_satisfied
    )
    finality_deadline_unavailable = _finality_unavailable_at_deadline(
        assurance=state.assurance,
        finality_status=liveness_input.finality_status,
        stability_satisfied=bool(
            commit_window_ready(state)
            and liveness_input.sealed_window
            and liveness_input.heartbeat_continuous
            and liveness_input.leader_ready_for_stability
        ),
        deadline_reached=effective_deadline_reached,
    )
    outcome_kind = select_terminal_outcome_kind(
        invalid=bool(liveness_input.invalid_reason_codes),
        safety_violation=bool(
            liveness_input.safety_violation_reason_codes
            or assessment_safety
            or liveness_input.finality_status is CommitFinalityStatus.CONFLICT
        ),
        blocked=bool(liveness_input.blocked_reason_codes or derived_blocked),
        evidence_commit_ready=evidence_ready,
        finality_unavailable=finality_deadline_unavailable,
        deadline_reached=effective_deadline_reached,
        deadline_outcome=commit_policy.terminal_outcome.deadline_outcome,
    )

    request_fingerprint = commit_payload_fingerprint(
        {
            "liveness_input": commit_liveness_input_fingerprint(liveness_input),
            "outcome_kind": outcome_kind.value if outcome_kind is not None else "",
            "window_state": liveness_input.window_state_ref,
        },
        schema="pheroos-commit-liveness-reduction-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window cursor is invalid")
    cache_key = (liveness_input.window_state_ref, current)
    with cursor.lock:
        cached = cursor.liveness_results.get(cache_key)
        if cached is not None:
            if cached[0] == request_fingerprint:
                return cached[1]
            raise GovernanceError("commit liveness decision would fork")
        if not _liveness_authority_heads_are_current(liveness_input):
            raise GovernanceError(
                "commit liveness authority heads are no longer current"
            )
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window already has a terminal outcome")

        if outcome_kind is None:
            result: DecisionProgress | DecisionOutcome = _progress_from_liveness(
                state,
                liveness_input,
            )
            cursor.current_progress = result
            cursor.current_progress_fingerprint = decision_progress_fingerprint(result)
        else:
            result = _outcome_from_liveness(
                state,
                commit_policy=commit_policy,
                liveness_input=liveness_input,
                kind=outcome_kind,
                deadline_reached=effective_deadline_reached,
                run_deadline_reached=run_deadline_reached,
                derived_blocked=derived_blocked,
            )
            cursor.terminal_result = result
            cursor.current_progress = None
            cursor.current_progress_fingerprint = ""
        cursor.liveness_results[cache_key] = (request_fingerprint, result)
        return result


def commit_liveness_input_is_authoritative(value: object) -> bool:
    return bool(
        _commit_liveness_input_was_issued(value)
        and _liveness_authority_heads_are_current(value)
    )


def _commit_liveness_input_was_issued(value: object) -> bool:
    if type(value) is not CommitLivenessInput:
        return False
    try:
        _validate_commit_liveness_input(value)
        issuance = value._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_LIVENESS_INPUT_ISSUANCE
            and issuance[1] == commit_liveness_input_fingerprint(value)
        )
    except Exception:
        return False


def commit_liveness_input_payload(
    value: CommitLivenessInput,
) -> dict[str, object]:
    if type(value) is not CommitLivenessInput:
        raise GovernanceError("commit liveness input must use the canonical record")
    _validate_commit_liveness_input(value)
    return build_commit_liveness_input_payload(value)


def commit_liveness_input_fingerprint(value: CommitLivenessInput) -> str:
    return commit_payload_fingerprint(
        commit_liveness_input_payload(value),
        schema="pheroos-commit-liveness-input-v1",
        profile=value.profile,
    )


def _validate_liveness_input_matches_window(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> None:
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if getattr(state, name) != getattr(value, name):
            raise GovernanceError(f"commit liveness {name} binding mismatch")
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
    if value.assessment_ref != state.last_assessment_ref:
        raise GovernanceError("commit liveness assessment head mismatch")
    if value.context_ref != state.last_context_ref:
        raise GovernanceError("commit liveness context head mismatch")
    if value.assessment_status != state.last_assessment_status:
        raise GovernanceError("commit liveness assessment status mismatch")
    if value.assessment_reason_codes != state.last_assessment_reason_codes:
        raise GovernanceError("commit liveness assessment reasons mismatch")
    for name in (
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
    ):
        if getattr(value, name) != getattr(state, name):
            raise GovernanceError(f"commit liveness {name} mismatch")
    if state.last_ready and value.leader_candidate_id != state.leader_candidate_id:
        raise GovernanceError("commit liveness leader candidate mismatch")
    seal = commit_window_seal_for_state(state)
    if value.sealed_window is not (seal is not None):
        raise GovernanceError("commit liveness sealed-window state mismatch")
    if seal is not None:
        if (
            value.seal_ref != commit_window_seal_fingerprint(seal)
            or value.sealed_at_step != seal.sealed_at_step
            or value.window_state_ref != seal.window_state_ref
        ):
            raise GovernanceError("commit liveness seal lineage mismatch")
    if not value.heartbeat_continuous and value.current_step < min(
        state.absolute_deadline_step, state.absolute_run_deadline_step
    ):
        raise GovernanceError(
            "commit liveness heartbeat loss requires a terminal deadline"
        )


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
    from pheroos.governance.risk import (
        commit_threshold_snapshot_fingerprint,
        commit_threshold_snapshot_matches,
        risk_assessment_fingerprint,
        risk_assessment_chain_state_fingerprint,
        risk_assessment_chain_state_is_current,
    )
    from pheroos.governance._support.records import (
        eligible_membership_epoch_state_fingerprint,
        eligible_principal_snapshot_fingerprint,
        support_lease_replay_state_fingerprint,
    )
    from pheroos.governance._support.membership import (
        eligible_membership_epoch_state_is_current,
        eligible_principal_snapshot_matches,
    )
    from pheroos.governance._support.replay import (
        support_lease_replay_state_is_current,
    )

    if (
        not risk_assessment_chain_state_is_current(risk_chain_state)
        or risk_assessment_chain_state_fingerprint(risk_chain_state)
        != state.risk_chain_state_root
    ):
        raise GovernanceError(
            "commit liveness risk authority head changed after assessment"
        )
    if (
        not eligible_membership_epoch_state_is_current(membership_epoch_state)
        or eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        != state.membership_epoch_state_root
    ):
        raise GovernanceError(
            "commit liveness membership authority head changed after assessment"
        )
    if (
        not support_lease_replay_state_is_current(support_replay_state)
        or support_lease_replay_state_fingerprint(support_replay_state)
        != state.support_replay_state_root
    ):
        raise GovernanceError(
            "commit liveness support replay head changed after assessment"
        )
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
        or getattr(membership_snapshot, "membership_root", None)
        != state.membership_root
    ):
        raise GovernanceError(
            "commit liveness membership root changed after assessment"
        )
    if not require_fresh_snapshot:
        return
    if not commit_threshold_snapshot_matches(
        threshold_snapshot,
        assessment=risk_assessment,
        chain_state=risk_chain_state,
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
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
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
        or getattr(membership_snapshot, "membership_root", None)
        != state.membership_root
    ):
        raise GovernanceError("late finality membership root changed after sealing")


def _liveness_authority_heads_are_current(value: CommitLivenessInput) -> bool:
    try:
        heads = value._authority_heads
        if not isinstance(heads, tuple) or len(heads) != 8:
            return False
        (
            replay_state,
            risk_state,
            risk_assessment,
            threshold_snapshot,
            membership_snapshot,
            membership_state,
            support_state,
            commit_policy,
        ) = heads
        if not (
            commit_replay_state_is_current(replay_state)
            and commit_replay_state_fingerprint(replay_state) == value.replay_state_ref
            and replay_state.receipt_root == value.replay_root
        ):
            return False
        if not value.assessment_ref:
            return True
        from pheroos.governance.risk import (
            commit_threshold_snapshot_fingerprint,
            commit_threshold_snapshot_matches,
            risk_assessment_fingerprint,
            risk_assessment_chain_state_fingerprint,
            risk_assessment_chain_state_is_current,
        )
        from pheroos.governance._support.records import (
            eligible_membership_epoch_state_fingerprint,
            eligible_principal_snapshot_fingerprint,
            support_lease_replay_state_fingerprint,
        )
        from pheroos.governance._support.membership import (
            eligible_membership_epoch_state_is_current,
            eligible_principal_snapshot_matches,
        )
        from pheroos.governance._support.replay import (
            support_lease_replay_state_is_current,
        )

        base_current = bool(
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
        if not base_current:
            return False
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
        if not (
            risk_assessment_fingerprint(risk_assessment) == value.risk_assessment_root
            and commit_threshold_snapshot_fingerprint(threshold_snapshot)
            == value.threshold_root
            and eligible_principal_snapshot_fingerprint(membership_snapshot)
            == value.membership_snapshot_root
            and getattr(membership_snapshot, "membership_root", None)
            == value.membership_root
        ):
            return False
        if not (
            value.sealed_window
            and value.current_step > value.sealed_at_step
            and not value.deadline_reached
        ):
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
    except Exception:
        return False


def _validate_finality_verification_matches_window(
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
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if getattr(verification, name) != getattr(state, name):
            raise GovernanceError(f"commit finality {name} binding mismatch")
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


def _finality_satisfied(value: CommitLivenessInput) -> bool:
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


def _finality_unavailable_at_deadline(
    *,
    assurance: CommitAssurance,
    finality_status: CommitFinalityStatus,
    stability_satisfied: bool,
    deadline_reached: bool,
) -> bool:
    return bool(
        assurance
        in {
            CommitAssurance.CERTIFIED,
            CommitAssurance.DISTRIBUTED,
        }
        and stability_satisfied
        and deadline_reached
        and finality_status
        in {
            CommitFinalityStatus.PENDING,
            CommitFinalityStatus.PROVISIONAL,
            CommitFinalityStatus.UNAVAILABLE,
        }
    )


def _progress_from_liveness(
    state: CommitWindowState,
    value: CommitLivenessInput,
) -> DecisionProgress:
    if value.current_step >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError("decision progress cannot survive a deadline")
    if not value.assessment_ref:
        phase = DecisionPhase.SEARCH
    elif (
        commit_window_ready(state)
        and value.sealed_window
        and not _finality_satisfied(value)
    ):
        phase = DecisionPhase.PROVISIONAL
    elif state.last_ready:
        phase = DecisionPhase.QUORUM_PENDING
    else:
        phase = DecisionPhase.DELIBERATE

    requirements = set(value.next_required_inputs)
    unmet = set(value.assessment_reason_codes)
    if not value.assessment_ref:
        requirements.add("commit_assessment")
    elif state.last_ready and not commit_window_ready(state):
        requirements.add("consecutive_stability_assessment")
    elif commit_window_ready(state) and not value.sealed_window:
        requirements.add("local_commit_receipt")
    elif commit_window_ready(state) and not _finality_satisfied(value):
        requirements.add("verified_finality")
    if not requirements and not unmet:
        requirements.add("next_commit_assessment")
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
    reasons: set[str] = set()
    if kind is DecisionOutcomeKind.INVALID:
        reasons.update(liveness_input.invalid_reason_codes)
        reasons.add("invalid")
    elif kind is DecisionOutcomeKind.SAFETY_VIOLATION:
        reasons.update(liveness_input.safety_violation_reason_codes)
        reasons.update(liveness_input.assessment_reason_codes)
        reasons.update(liveness_input.finality_reason_codes)
        reasons.add("safety_violation")
    elif kind is DecisionOutcomeKind.BLOCKED:
        reasons.update(liveness_input.blocked_reason_codes)
        if derived_blocked:
            reasons.update(liveness_input.assessment_reason_codes)
        reasons.add("blocked")
    elif kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        reasons.update(("evidence_commit", "stability_satisfied"))
        if liveness_input.current_step > liveness_input.sealed_at_step:
            reasons.add("late_finality_verified")
    elif kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE:
        reasons.update(liveness_input.finality_reason_codes)
        reasons.add("finality_unavailable")
    else:
        reasons.add(kind.value)
    if deadline_reached:
        reasons.add("deadline_reached")
    if run_deadline_reached:
        reasons.add("run_deadline_reached")

    if kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        candidate = state.leader_candidate_id
        scope = AuthorityScope(
            COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE[state.assurance.value]
        )
        authoritative = True
        epistemic = True
        certificate = liveness_input.certificate_ref
    elif kind is DecisionOutcomeKind.SAFE_FALLBACK:
        candidate = commit_policy.terminal_outcome.safe_fallback_candidate
        scope = AuthorityScope.NONE
        authoritative = False
        epistemic = False
        certificate = ""
    elif kind is DecisionOutcomeKind.ADVISORY:
        candidate = liveness_input.leader_candidate_id
        scope = AuthorityScope.NONE
        authoritative = False
        epistemic = False
        certificate = ""
    elif kind is DecisionOutcomeKind.BLOCKED:
        candidate = ""
        scope = AuthorityScope.DENIAL
        authoritative = False
        epistemic = False
        certificate = ""
    else:
        candidate = ""
        scope = AuthorityScope.NONE
        authoritative = False
        epistemic = False
        certificate = ""

    # Certificate verification and current publish/execute permission remain
    # independent. Bounded liveness never pre-authorizes either action.
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
        authority_scope=scope,
        authoritative_commit=authoritative,
        epistemically_committed=epistemic,
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
        candidate_id=candidate,
        reason_codes=tuple(reasons),
        assessment_ref=liveness_input.assessment_ref,
        certificate_ref=certificate,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
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
