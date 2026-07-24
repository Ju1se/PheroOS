"""Governance issuance path for canonical commit liveness inputs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pheroos.governance._commit_state._window_contract import (
    _authoritative_commit_assessment_view,
    _validate_assessment_matches_window_head,
)
from pheroos.governance._commit_state.liveness_authority import (
    validate_finality_verification_matches_window_impl,
    validate_liveness_current_authority_heads_impl,
)
from pheroos.governance._commit_state.payloads import (
    build_commit_liveness_input_payload,
)
from pheroos.governance._commit_state.records import (
    _COMMIT_LIVENESS_INPUT_ISSUANCE,
    _CommitWindowCursor,
    CommitFinalityStatus,
    CommitFinalityVerification,
    CommitLivenessInput,
    CommitReplayState,
    CommitWindowSeal,
    CommitWindowState,
    DecisionProgress,
    _validate_commit_liveness_input,
    commit_finality_verification_fingerprint,
    commit_finality_verification_is_authoritative,
    commit_replay_state_fingerprint,
    commit_replay_state_matches,
    decision_progress_fingerprint,
    decision_progress_is_authoritative,
)
from pheroos.governance._commit_state.window import (
    commit_window_ready,
    commit_window_seal_fingerprint,
    commit_window_seal_for_state,
    commit_window_state_fingerprint,
    commit_window_state_is_current,
)
from pheroos.governance._commit_validation import (
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CollectiveCommitPolicy, CommitAssurance


@dataclass(frozen=True)
class CommitLivenessInputRequest:
    state: CommitWindowState
    assessment: object | None
    replay_state: CommitReplayState
    risk_chain_state: object | None
    risk_assessment: object | None
    threshold_snapshot: object | None
    membership_snapshot: object | None
    membership_epoch_state: object | None
    support_replay_state: object | None
    commit_policy: CollectiveCommitPolicy | None
    previous_progress: DecisionProgress | None
    current_step: int
    finality_status: CommitFinalityStatus
    finality_verification: CommitFinalityVerification | None
    certificate_ref: str
    invalid_reason_codes: Sequence[str]
    safety_violation_reason_codes: Sequence[str]
    blocked_reason_codes: Sequence[str]
    finality_reason_codes: Sequence[str]
    next_required_inputs: Sequence[str]
    input_id: str
    issuer_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str


@dataclass(frozen=True)
class HeartbeatFacts:
    seal: CommitWindowSeal | None
    seal_ref: str
    sealed_at_step: int
    previous_progress_ref: str
    heartbeat_sequence: int
    heartbeat_continuous: bool


@dataclass(frozen=True)
class AssessmentFacts:
    assessment_ref: str
    context_ref: str
    status: str
    leader_candidate_id: str
    ready: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class FinalityFacts:
    certificate_ref: str
    verification_ref: str


def issue_commit_liveness_input_impl(
    request: CommitLivenessInputRequest,
) -> CommitLivenessInput:
    current, cursor, deadline_reached = _validate_issuance_request(request)
    heartbeat = _heartbeat_facts(
        request,
        cursor=cursor,
        current=current,
        deadline_reached=deadline_reached,
    )
    _validate_replay_head(request, current=current)
    assessment = _assessment_facts(
        request,
        heartbeat=heartbeat,
        current=current,
        deadline_reached=deadline_reached,
    )
    finality = _finality_facts(
        request,
        heartbeat=heartbeat,
        current=current,
    )
    value = _build_liveness_input(
        request,
        heartbeat=heartbeat,
        assessment=assessment,
        finality=finality,
        current=current,
        deadline_reached=deadline_reached,
    )
    _bind_private_authority(value, request)
    return _cache_liveness_input(value, cursor)


def _validate_issuance_request(
    request: CommitLivenessInputRequest,
) -> tuple[int, _CommitWindowCursor, bool]:
    state = request.state
    if not commit_window_state_is_current(state):
        raise GovernanceError("commit liveness requires the current window head")
    if type(request.authority) is not AuthorityLevel or not can_verify(
        request.authority
    ):
        raise GovernanceError("commit liveness input requires governance authority")
    current = require_commit_step(
        request.current_step,
        "commit liveness current_step",
    )
    if current < state.last_evaluated_step:
        raise GovernanceError("commit liveness step cannot precede the window head")
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit liveness window cursor is invalid")
    deadline_reached = current >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    )
    return current, cursor, deadline_reached


def _heartbeat_facts(
    request: CommitLivenessInputRequest,
    *,
    cursor: _CommitWindowCursor,
    current: int,
    deadline_reached: bool,
) -> HeartbeatFacts:
    state = request.state
    seal = commit_window_seal_for_state(state)
    defaults = HeartbeatFacts(
        seal=seal,
        seal_ref=commit_window_seal_fingerprint(seal) if seal is not None else "",
        sealed_at_step=seal.sealed_at_step if seal is not None else 0,
        previous_progress_ref="",
        heartbeat_sequence=0,
        heartbeat_continuous=True,
    )
    if current == state.last_evaluated_step:
        if request.previous_progress is not None:
            raise GovernanceError(
                "initial liveness step cannot consume a previous heartbeat"
            )
        return defaults
    if seal is not None:
        return _sealed_heartbeat_facts(
            request,
            defaults=defaults,
            cursor=cursor,
            current=current,
            deadline_reached=deadline_reached,
        )
    if commit_window_ready(state) and not deadline_reached:
        raise GovernanceError("stable window requires a same-step local receipt seal")
    if request.previous_progress is not None:
        raise GovernanceError(
            "unsealed liveness cannot consume a sealed-window heartbeat"
        )
    return defaults


def _sealed_heartbeat_facts(
    request: CommitLivenessInputRequest,
    *,
    defaults: HeartbeatFacts,
    cursor: _CommitWindowCursor,
    current: int,
    deadline_reached: bool,
) -> HeartbeatFacts:
    previous = request.previous_progress
    if previous is None:
        if not deadline_reached:
            raise GovernanceError(
                "late finality requires the authoritative previous heartbeat"
            )
        return HeartbeatFacts(
            seal=defaults.seal,
            seal_ref=defaults.seal_ref,
            sealed_at_step=defaults.sealed_at_step,
            previous_progress_ref="",
            heartbeat_sequence=0,
            heartbeat_continuous=False,
        )
    _validate_previous_heartbeat(
        previous,
        defaults=defaults,
        cursor=cursor,
        current=current,
    )
    return HeartbeatFacts(
        seal=defaults.seal,
        seal_ref=defaults.seal_ref,
        sealed_at_step=defaults.sealed_at_step,
        previous_progress_ref=decision_progress_fingerprint(previous),
        heartbeat_sequence=previous.heartbeat_sequence + 1,
        heartbeat_continuous=True,
    )


def _validate_previous_heartbeat(
    previous: DecisionProgress,
    *,
    defaults: HeartbeatFacts,
    cursor: _CommitWindowCursor,
    current: int,
) -> None:
    seal = defaults.seal
    assert seal is not None
    if not decision_progress_is_authoritative(previous):
        raise GovernanceError("late finality previous heartbeat is not authoritative")
    with cursor.lock:
        if cursor.current_progress is not previous:
            raise GovernanceError(
                "late finality previous heartbeat is not the current head"
            )
    if previous.current_step + 1 != current:
        raise GovernanceError(
            "late finality heartbeat must advance exactly one logical step"
        )
    if not all(
        (
            previous.sealed_window,
            previous.heartbeat_continuous,
            previous.seal_ref == defaults.seal_ref,
            previous.sealed_at_step == seal.sealed_at_step,
            previous.window_state_ref == seal.window_state_ref,
            previous.window_root == seal.window_root,
        )
    ):
        raise GovernanceError(
            "late finality previous heartbeat does not preserve the seal"
        )


def _validate_replay_head(
    request: CommitLivenessInputRequest,
    *,
    current: int,
) -> None:
    state = request.state
    if not commit_replay_state_matches(
        request.replay_state,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        current_step=current,
    ):
        raise GovernanceError("commit liveness replay head is not authoritative")


def _assessment_facts(
    request: CommitLivenessInputRequest,
    *,
    heartbeat: HeartbeatFacts,
    current: int,
    deadline_reached: bool,
) -> AssessmentFacts:
    state = request.state
    if request.assessment is None:
        if state.last_assessment_ref:
            raise GovernanceError(
                "commit liveness must consume the window head assessment"
            )
        return AssessmentFacts("", "", "", "", False, ())
    view = _authoritative_commit_assessment_view(request.assessment)
    _validate_assessment_matches_window_head(state, view)
    if (
        commit_replay_state_fingerprint(request.replay_state)
        != state.assessment_replay_state_ref
        or request.replay_state.receipt_root != state.assessment_replay_root
    ):
        raise GovernanceError(
            "commit liveness replay head changed after the assessment"
        )
    validate_liveness_current_authority_heads_impl(
        state,
        commit_policy=request.commit_policy,
        risk_chain_state=request.risk_chain_state,
        risk_assessment=request.risk_assessment,
        threshold_snapshot=request.threshold_snapshot,
        membership_snapshot=request.membership_snapshot,
        membership_epoch_state=request.membership_epoch_state,
        support_replay_state=request.support_replay_state,
        current_step=current,
        require_fresh_snapshot=bool(
            heartbeat.seal is not None
            and current > heartbeat.seal.sealed_at_step
            and not deadline_reached
        ),
    )
    return AssessmentFacts(
        assessment_ref=str(view["assessment_ref"]),
        context_ref=str(view["context_ref"]),
        status=str(view["status"]),
        leader_candidate_id=str(view["leader_candidate_id"]),
        ready=bool(view["ready"]),
        reason_codes=tuple(view["reason_codes"]),
    )


def _finality_facts(
    request: CommitLivenessInputRequest,
    *,
    heartbeat: HeartbeatFacts,
    current: int,
) -> FinalityFacts:
    status = request.finality_status
    verification = request.finality_verification
    if type(status) is not CommitFinalityStatus:
        raise GovernanceError("commit liveness finality status is invalid")
    if status is CommitFinalityStatus.VERIFIED:
        return _verified_finality_facts(
            request,
            heartbeat=heartbeat,
            current=current,
        )
    if verification is not None:
        raise GovernanceError(
            "non-verified finality cannot carry a finality verification"
        )
    if request.certificate_ref:
        raise GovernanceError(
            "commit liveness cannot accept a bare certificate reference"
        )
    return FinalityFacts("", "")


def _verified_finality_facts(
    request: CommitLivenessInputRequest,
    *,
    heartbeat: HeartbeatFacts,
    current: int,
) -> FinalityFacts:
    verification = request.finality_verification
    if not commit_finality_verification_is_authoritative(verification):
        raise GovernanceError(
            "verified finality requires an authoritative typed verification"
        )
    assert verification is not None
    validate_finality_verification_matches_window_impl(
        verification,
        state=request.state,
        seal=heartbeat.seal,
        current_step=current,
    )
    if heartbeat.seal is None:
        raise GovernanceError(
            "verified finality requires the current receipt-backed seal"
        )
    if request.state.assurance is CommitAssurance.EVIDENCE_BOUND and (
        current != heartbeat.seal.sealed_at_step
        or verification.certificate_ref != heartbeat.seal.receipt_ref
    ):
        raise GovernanceError(
            "evidence-bound finality requires its same-step local receipt"
        )
    if request.certificate_ref:
        raise GovernanceError(
            "verified finality cannot accept a bare certificate reference"
        )
    return FinalityFacts(
        verification.certificate_ref,
        commit_finality_verification_fingerprint(verification),
    )


def _build_liveness_input(
    request: CommitLivenessInputRequest,
    *,
    heartbeat: HeartbeatFacts,
    assessment: AssessmentFacts,
    finality: FinalityFacts,
    current: int,
    deadline_reached: bool,
) -> CommitLivenessInput:
    state = request.state
    return CommitLivenessInput(
        input_id=require_commit_text(request.input_id, "commit liveness input_id"),
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
        context_ref=assessment.context_ref,
        assessment_ref=assessment.assessment_ref,
        assessment_status=assessment.status,
        leader_candidate_id=assessment.leader_candidate_id,
        leader_ready_for_stability=assessment.ready,
        assessment_reason_codes=assessment.reason_codes,
        replay_state_ref=commit_replay_state_fingerprint(request.replay_state),
        replay_root=request.replay_state.receipt_root,
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
        sealed_window=heartbeat.seal is not None,
        seal_ref=heartbeat.seal_ref,
        sealed_at_step=heartbeat.sealed_at_step,
        heartbeat_continuous=heartbeat.heartbeat_continuous,
        heartbeat_sequence=heartbeat.heartbeat_sequence,
        previous_progress_ref=heartbeat.previous_progress_ref,
        finality_status=request.finality_status,
        certificate_ref=finality.certificate_ref,
        finality_verification_ref=finality.verification_ref,
        invalid_reason_codes=tuple(request.invalid_reason_codes),
        safety_violation_reason_codes=tuple(request.safety_violation_reason_codes),
        blocked_reason_codes=tuple(request.blocked_reason_codes),
        finality_reason_codes=tuple(request.finality_reason_codes),
        next_required_inputs=tuple(request.next_required_inputs),
        issuer_id=require_commit_text(
            request.issuer_id,
            "commit liveness issuer_id",
        ),
        authority=request.authority,
        provenance=require_commit_text(
            request.provenance,
            "commit liveness provenance",
        ),
        trace_event_id=require_commit_text(
            request.trace_event_id,
            "commit liveness trace_event_id",
        ),
    )


def _bind_private_authority(
    value: CommitLivenessInput,
    request: CommitLivenessInputRequest,
) -> None:
    object.__setattr__(
        value,
        "_issuance",
        (
            _COMMIT_LIVENESS_INPUT_ISSUANCE,
            commit_liveness_input_fingerprint_impl(value),
        ),
    )
    object.__setattr__(
        value,
        "_authority_heads",
        (
            request.replay_state,
            request.risk_chain_state,
            request.risk_assessment,
            request.threshold_snapshot,
            request.membership_snapshot,
            request.membership_epoch_state,
            request.support_replay_state,
            request.commit_policy,
        ),
    )


def _cache_liveness_input(
    value: CommitLivenessInput,
    cursor: _CommitWindowCursor,
) -> CommitLivenessInput:
    request_ref = commit_liveness_input_fingerprint_impl(value)
    cache_key = value.input_id
    with cursor.lock:
        cached = cursor.liveness_inputs.get(cache_key)
        if cached is not None:
            if cached[0] == request_ref:
                return cached[1]
            raise GovernanceError("commit liveness input id would fork")
        cursor.liveness_inputs[cache_key] = (request_ref, value)
        return value


def commit_liveness_input_was_issued_impl(value: object) -> bool:
    if type(value) is not CommitLivenessInput:
        return False
    try:
        _validate_commit_liveness_input(value)
        issuance = value._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_LIVENESS_INPUT_ISSUANCE
            and issuance[1] == commit_liveness_input_fingerprint_impl(value)
        )
    except Exception:
        return False


def commit_liveness_input_payload_impl(
    value: CommitLivenessInput,
) -> dict[str, object]:
    if type(value) is not CommitLivenessInput:
        raise GovernanceError("commit liveness input must use the canonical record")
    _validate_commit_liveness_input(value)
    return build_commit_liveness_input_payload(value)


def commit_liveness_input_fingerprint_impl(value: CommitLivenessInput) -> str:
    return commit_payload_fingerprint(
        commit_liveness_input_payload_impl(value),
        schema="pheroos-commit-liveness-input-v1",
        profile=value.profile,
    )


__all__: list[str] = []
