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


def initialize_commit_window_state(
    *,
    commit_policy: CollectiveCommitPolicy,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    risk_assessment_root: str,
    membership_root: str,
    threshold_snapshot: object,
    current_step: int,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitWindowState:
    """Initialize the sole process-local window head for a run target.

    Every temporal parameter is derived from the bound policy.  There is no raw
    deadline, reset-budget, or stability-threshold initialization path.
    """

    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "commit window initialization requires governance authority"
        )
    current = require_commit_step(current_step, "commit window current_step")
    bindings = _normalized_window_bindings(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        field_name="commit window",
    )
    normalized_risk = require_commit_fingerprint(
        risk_assessment_root,
        "commit window risk_assessment_root",
    )
    _validate_bound_commit_policy(commit_policy, bindings)
    threshold_ref, threshold_stability = _validate_window_threshold_snapshot(
        threshold_snapshot,
        commit_policy=commit_policy,
        bindings=bindings,
        risk_assessment_root=risk_assessment_root,
        current_step=current,
    )
    normalized_membership = require_commit_fingerprint(
        membership_root,
        "commit window membership_root",
    )
    window_policy = commit_policy.commit_window
    absolute_deadline = checked_add(
        current,
        window_policy.deliberation_deadline_steps,
    )
    absolute_run_deadline = checked_add(
        current,
        window_policy.run_deadline_steps,
    )
    normalized_issuer = require_commit_text(
        issuer_id,
        "commit window issuer_id",
    )
    normalized_provenance = require_commit_text(
        provenance,
        "commit window provenance",
    )
    normalized_trace = require_commit_text(
        trace_event_id,
        "commit window trace_event_id",
    )
    authority_key = _commit_window_authority_key(bindings)
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority": authority,
            "authority_key": authority_key,
            "initialized_at_step": current,
            "issuer_id": normalized_issuer,
            "membership_root": normalized_membership,
            "provenance": normalized_provenance,
            "risk_assessment_root": normalized_risk,
            "threshold_root": threshold_ref,
            "trace_event_id": normalized_trace,
        },
        schema="pheroos-commit-window-base-v1",
        profile=str(bindings["profile"]),
    )
    assessment_refs: tuple[str, ...] = ()
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        cursor = registry.get(_LEGACY_COMMIT_WINDOW_CURSORS, authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "commit window authority already has a different base"
                )
            current_state = cursor.current_state
            if type(
                current_state
            ) is not CommitWindowState or not commit_window_state_is_current(
                current_state
            ):
                raise GovernanceError(
                    "commit window current state is unavailable; "
                    "reinitialization is forbidden"
                )
            return current_state

        cursor = _CommitWindowCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
            chain_id=authority_key,
        )
        state = CommitWindowState(
            chain_id=authority_key,
            profile=str(bindings["profile"]),
            assurance=bindings["assurance"],
            manifest_root=str(bindings["manifest_root"]),
            commit_policy_root=str(bindings["commit_policy_root"]),
            protocol_id=str(bindings["protocol_id"]),
            run_id=str(bindings["run_id"]),
            target=str(bindings["target"]),
            epoch=int(bindings["epoch"]),
            revision=0,
            previous_state_fingerprint="",
            risk_assessment_root=normalized_risk,
            membership_root=normalized_membership,
            threshold_root=threshold_ref,
            minimum_stability_steps=max(
                window_policy.minimum_stability_steps,
                threshold_stability,
            ),
            risk_chain_state_root="",
            risk_policy_root="",
            membership_snapshot_root="",
            membership_epoch_state_root="",
            support_replay_state_root="",
            support_replay_root="",
            collective_evidence_root="",
            collective_challenge_root="",
            collective_lease_root="",
            candidate_evidence_root="",
            candidate_challenge_root="",
            candidate_lease_root="",
            stop_resolution_root="",
            permission_root="",
            assessment_replay_state_ref="",
            assessment_replay_root="",
            initialized_at_step=current,
            last_evaluated_step=current,
            absolute_deadline_step=absolute_deadline,
            absolute_run_deadline_step=absolute_run_deadline,
            remaining_reset_budget=window_policy.maximum_leader_resets,
            remaining_epoch_restart_budget=window_policy.maximum_epoch_restarts,
            ordered_assessment_refs=assessment_refs,
            window_root=_window_root(
                assessment_refs,
                profile=str(bindings["profile"]),
                run_id=str(bindings["run_id"]),
                epoch=int(bindings["epoch"]),
            ),
            issuer_id=normalized_issuer,
            authority=authority,
            provenance=normalized_provenance,
            trace_event_id=normalized_trace,
        )
        state = _issue_commit_window_state(state, cursor=cursor)
        cursor.current_state = state
        cursor.current_state_fingerprint = commit_window_state_fingerprint(state)
        registry.set(_LEGACY_COMMIT_WINDOW_CURSORS, authority_key, cursor)
        return state


def advance_commit_window_state(
    state: CommitWindowState,
    *,
    assessment: object,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    current_step: int,
) -> CommitWindowState:
    """Advance an unsealed assessment window.

    Once a local receipt has sealed a stable head, ordinary advance is
    forbidden.  Callers must use :func:`reset_commit_window_state`, making the
    loss of a proof-visible seal explicit and budgeted.
    """

    return _transition_commit_window_state(
        state,
        assessment=assessment,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        current_step=current_step,
        explicit_unseal=False,
    )


def reset_commit_window_state(
    state: CommitWindowState,
    *,
    assessment: object,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    current_step: int,
) -> CommitWindowState:
    """Explicitly invalidate a sealed window and begin a fresh stability run.

    This transition always consumes one leader-reset unit, even when the next
    assessment happens to reproduce the old roots.  It is the only non-epoch
    route out of a current sealed window and therefore prevents a late proof
    from being silently reused after heartbeat, head, leader or gate changes.
    """

    return _transition_commit_window_state(
        state,
        assessment=assessment,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        current_step=current_step,
        explicit_unseal=True,
    )


def _transition_commit_window_state(
    state: CommitWindowState,
    *,
    assessment: object,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    current_step: int,
    explicit_unseal: bool,
) -> CommitWindowState:
    if not commit_window_state_is_authoritative(state):
        raise GovernanceError("commit window state is not governance-issued")
    current = require_commit_step(current_step, "commit window current_step")
    if current <= state.last_evaluated_step:
        raise GovernanceError("commit window step must advance monotonically")
    if current >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError("commit window cannot advance at or after its deadline")
    view = _authoritative_commit_assessment_view(
        assessment,
        current_step=current,
    )
    bindings = _normalized_window_bindings(
        profile=view["profile"],
        assurance=view["assurance"],
        manifest_root=view["manifest_root"],
        commit_policy_root=view["commit_policy_root"],
        protocol_id=view["protocol_id"],
        run_id=view["run_id"],
        target=view["target"],
        epoch=view["epoch"],
        field_name="commit assessment window",
    )
    _validate_window_chain_scope(state, bindings)
    _validate_bound_commit_policy(commit_policy, bindings)
    threshold_ref, threshold_stability = _validate_window_threshold_snapshot(
        threshold_snapshot,
        commit_policy=commit_policy,
        bindings=bindings,
        risk_assessment_root=view["risk_assessment_root"],
        current_step=current,
    )
    if threshold_ref != view["threshold_root"]:
        raise GovernanceError(
            "commit assessment threshold does not match the canonical snapshot"
        )
    ready = bool(view["ready"])
    leader = str(view["leader_candidate_id"]) if ready else ""
    assessment_ref = str(view["assessment_ref"])

    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window cursor is invalid")
    state_is_current = commit_window_state_is_current(state)
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        has_current_seal = bool(
            cursor.current_seal is not None
            and commit_window_seal_is_current(cursor.current_seal)
        )
    if has_current_seal and not explicit_unseal:
        raise GovernanceError(
            "sealed commit window requires an explicit reset/unseal transition"
        )
    if explicit_unseal and state_is_current and not has_current_seal:
        raise GovernanceError("explicit reset/unseal requires a current sealed window")

    reset_reason = _window_reset_reason(
        state,
        current_step=current,
        ready=ready,
        leader_candidate_id=leader,
        manifest_root=str(bindings["manifest_root"]),
        commit_policy_root=str(bindings["commit_policy_root"]),
        risk_assessment_root=str(view["risk_assessment_root"]),
        membership_root=str(view["membership_root"]),
        threshold_root=threshold_ref,
    )
    if explicit_unseal and reset_reason == "none":
        reset_reason = "explicit_unseal"
    consumes_reset = bool(
        explicit_unseal or (reset_reason != "none" and state.window_count > 0)
    )
    remaining_reset_budget = state.remaining_reset_budget
    exhausted = state.reset_budget_exhausted
    if consumes_reset:
        if remaining_reset_budget == 0:
            exhausted = True
        else:
            remaining_reset_budget -= 1

    if not ready or exhausted:
        next_count = 0
        next_leader = ""
        assessment_refs: tuple[str, ...] = ()
        next_ready = False
    elif reset_reason != "none" or not state.last_ready:
        next_count = 1
        next_leader = leader
        assessment_refs = (assessment_ref,)
        next_ready = True
    else:
        next_count = state.window_count + 1
        next_leader = leader
        assessment_refs = (*state.ordered_assessment_refs, assessment_ref)
        next_ready = True

    parent_fingerprint = commit_window_state_fingerprint(state)
    request_fingerprint = commit_payload_fingerprint(
        {
            "assessment_ref": assessment_ref,
            "current_step": current,
            "explicit_unseal": explicit_unseal,
            "parent_state_fingerprint": parent_fingerprint,
            "policy_root": bindings["commit_policy_root"],
            "threshold_root": threshold_ref,
        },
        schema="pheroos-commit-window-advance-request-v1",
        profile=state.profile,
    )
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        locked_seal = cursor.current_seal
        locked_sealed = bool(
            locked_seal is not None and commit_window_seal_is_current(locked_seal)
        )
        if locked_sealed and not explicit_unseal:
            raise GovernanceError(
                "sealed commit window requires an explicit reset/unseal transition"
            )
        if explicit_unseal and not locked_sealed:
            raise GovernanceError(
                "explicit reset/unseal lost its current seal authority"
            )
    next_state = CommitWindowState(
        chain_id=state.chain_id,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=str(bindings["manifest_root"]),
        commit_policy_root=str(bindings["commit_policy_root"]),
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        revision=state.revision + 1,
        previous_state_fingerprint=parent_fingerprint,
        risk_assessment_root=str(view["risk_assessment_root"]),
        membership_root=str(view["membership_root"]),
        threshold_root=threshold_ref,
        minimum_stability_steps=max(
            state.minimum_stability_steps,
            commit_policy.commit_window.minimum_stability_steps,
            threshold_stability,
        ),
        risk_chain_state_root=str(view["risk_chain_state_root"]),
        risk_policy_root=str(view["risk_policy_root"]),
        membership_snapshot_root=str(view["membership_snapshot_root"]),
        membership_epoch_state_root=str(view["membership_epoch_state_root"]),
        support_replay_state_root=str(view["support_replay_state_root"]),
        support_replay_root=str(view["support_replay_root"]),
        collective_evidence_root=str(view["collective_evidence_root"]),
        collective_challenge_root=str(view["collective_challenge_root"]),
        collective_lease_root=str(view["collective_lease_root"]),
        candidate_evidence_root=str(view["candidate_evidence_root"]),
        candidate_challenge_root=str(view["candidate_challenge_root"]),
        candidate_lease_root=str(view["candidate_lease_root"]),
        stop_resolution_root=str(view["stop_resolution_root"]),
        permission_root=str(view["permission_root"]),
        assessment_replay_state_ref=str(view["replay_state_ref"]),
        assessment_replay_root=str(view["replay_root"]),
        initialized_at_step=state.initialized_at_step,
        last_evaluated_step=current,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        remaining_reset_budget=remaining_reset_budget,
        remaining_epoch_restart_budget=state.remaining_epoch_restart_budget,
        leader_candidate_id=next_leader,
        window_count=next_count,
        ordered_assessment_refs=assessment_refs,
        window_root=_window_root(
            assessment_refs,
            profile=state.profile,
            run_id=state.run_id,
            epoch=state.epoch,
        ),
        last_ready=next_ready,
        last_assessment_ref=assessment_ref,
        last_context_ref=str(view["context_ref"]),
        last_assessment_status=str(view["status"]),
        last_assessment_reason_codes=tuple(view["reason_codes"]),
        reset_reason=("reset_budget_exhausted" if exhausted else reset_reason),
        reset_budget_exhausted=exhausted,
        issuer_id=state.issuer_id,
        authority=state.authority,
        provenance=state.provenance,
        trace_event_id=state.trace_event_id,
    )
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        locked_seal = cursor.current_seal
        locked_sealed = bool(
            locked_seal is not None and commit_window_seal_is_current(locked_seal)
        )
        if locked_sealed and not explicit_unseal:
            raise GovernanceError(
                "sealed commit window requires an explicit reset/unseal transition"
            )
        if explicit_unseal and not locked_sealed:
            raise GovernanceError(
                "explicit reset/unseal lost its current seal authority"
            )
        next_state = _issue_commit_window_state(next_state, cursor=cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = commit_window_state_fingerprint(next_state)
        if explicit_unseal:
            cursor.current_seal = None
            cursor.current_seal_fingerprint = ""
            cursor.seal_generation += 1
        cursor.current_progress = None
        cursor.current_progress_fingerprint = ""
        cursor.transitions[parent_fingerprint] = (
            request_fingerprint,
            next_state,
        )
        return next_state


def restart_commit_window_epoch(
    state: CommitWindowState,
    *,
    new_epoch: int,
    current_step: int,
    commit_policy: CollectiveCommitPolicy,
    threshold_snapshot: object,
    membership_root: str,
) -> CommitWindowState:
    if not commit_window_state_is_authoritative(state):
        raise GovernanceError("commit window state is not governance-issued")
    current = require_commit_step(current_step, "epoch restart current_step")
    epoch = require_commit_step(new_epoch, "epoch restart new_epoch")
    if epoch <= state.epoch:
        raise GovernanceError("epoch restart must advance the epoch")
    if current <= state.last_evaluated_step:
        raise GovernanceError("epoch restart step must advance monotonically")
    if current >= min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    ):
        raise GovernanceError("epoch restart cannot extend the deliberation deadline")
    if state.remaining_epoch_restart_budget == 0:
        raise GovernanceError("epoch restart budget is exhausted")
    snapshot_bindings = _threshold_snapshot_bindings(threshold_snapshot)
    bindings = _normalized_window_bindings(
        profile=snapshot_bindings["profile"],
        assurance=snapshot_bindings["assurance"],
        manifest_root=snapshot_bindings["manifest_root"],
        commit_policy_root=snapshot_bindings["commit_policy_root"],
        protocol_id=snapshot_bindings["protocol_id"],
        run_id=snapshot_bindings["run_id"],
        target=snapshot_bindings["target"],
        epoch=snapshot_bindings["epoch"],
        field_name="commit window epoch restart",
    )
    if int(bindings["epoch"]) != epoch:
        raise GovernanceError("epoch restart threshold epoch mismatch")
    _validate_window_chain_scope(state, bindings, allow_epoch_change=True)
    _validate_bound_commit_policy(commit_policy, bindings)
    threshold_ref, threshold_stability = _validate_window_threshold_snapshot(
        threshold_snapshot,
        commit_policy=commit_policy,
        bindings=bindings,
        risk_assessment_root=snapshot_bindings["risk_assessment_root"],
        current_step=current,
    )
    normalized_membership = require_commit_fingerprint(
        membership_root,
        "epoch restart membership_root",
    )
    parent_fingerprint = commit_window_state_fingerprint(state)
    request_fingerprint = commit_payload_fingerprint(
        {
            "current_step": current,
            "epoch": epoch,
            "membership_root": normalized_membership,
            "parent_state_fingerprint": parent_fingerprint,
            "policy_root": bindings["commit_policy_root"],
            "threshold_root": threshold_ref,
        },
        schema="pheroos-commit-window-epoch-restart-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window cursor is invalid")
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        invalidates_seal = bool(
            cursor.current_seal is not None
            and commit_window_seal_is_current(cursor.current_seal)
        )
        if invalidates_seal and state.remaining_reset_budget == 0:
            raise GovernanceError(
                "sealed epoch restart requires remaining reset budget"
            )
    assessment_refs: tuple[str, ...] = ()
    restarted = CommitWindowState(
        chain_id=state.chain_id,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=str(bindings["manifest_root"]),
        commit_policy_root=str(bindings["commit_policy_root"]),
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=epoch,
        revision=state.revision + 1,
        previous_state_fingerprint=parent_fingerprint,
        risk_assessment_root=str(snapshot_bindings["risk_assessment_root"]),
        membership_root=normalized_membership,
        threshold_root=threshold_ref,
        minimum_stability_steps=max(
            state.minimum_stability_steps,
            commit_policy.commit_window.minimum_stability_steps,
            threshold_stability,
        ),
        risk_chain_state_root="",
        risk_policy_root="",
        membership_snapshot_root="",
        membership_epoch_state_root="",
        support_replay_state_root="",
        support_replay_root="",
        collective_evidence_root="",
        collective_challenge_root="",
        collective_lease_root="",
        candidate_evidence_root="",
        candidate_challenge_root="",
        candidate_lease_root="",
        stop_resolution_root="",
        permission_root="",
        assessment_replay_state_ref="",
        assessment_replay_root="",
        initialized_at_step=state.initialized_at_step,
        last_evaluated_step=current,
        absolute_deadline_step=state.absolute_deadline_step,
        absolute_run_deadline_step=state.absolute_run_deadline_step,
        remaining_reset_budget=(
            state.remaining_reset_budget - 1
            if invalidates_seal
            else state.remaining_reset_budget
        ),
        remaining_epoch_restart_budget=(state.remaining_epoch_restart_budget - 1),
        ordered_assessment_refs=assessment_refs,
        window_root=_window_root(
            assessment_refs,
            profile=state.profile,
            run_id=state.run_id,
            epoch=epoch,
        ),
        reset_reason="epoch_change",
        issuer_id=state.issuer_id,
        authority=state.authority,
        provenance=state.provenance,
        trace_event_id=state.trace_event_id,
    )
    with cursor.lock:
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        if cursor.current_state_fingerprint != parent_fingerprint:
            prior = cursor.transitions.get(parent_fingerprint)
            if prior is not None and prior[0] == request_fingerprint:
                return prior[1]
            raise GovernanceError("commit window state is stale or would fork")
        restarted = _issue_commit_window_state(restarted, cursor=cursor)
        cursor.current_state = restarted
        cursor.current_state_fingerprint = commit_window_state_fingerprint(restarted)
        if invalidates_seal:
            cursor.current_seal = None
            cursor.current_seal_fingerprint = ""
            cursor.seal_generation += 1
        cursor.current_progress = None
        cursor.current_progress_fingerprint = ""
        cursor.transitions[parent_fingerprint] = (
            request_fingerprint,
            restarted,
        )
        return restarted


def commit_window_ready(
    state: CommitWindowState,
) -> bool:
    if not commit_window_state_is_current(state):
        return False
    try:
        return bool(
            state.last_ready
            and not state.reset_budget_exhausted
            and state.window_count >= state.minimum_stability_steps
            and state.last_evaluated_step
            < min(state.absolute_deadline_step, state.absolute_run_deadline_step)
        )
    except (GovernanceError, AttributeError):
        return False


def _seal_commit_window_from_local_receipt(
    state: CommitWindowState,
    receipt: object,
) -> CommitWindowSeal:
    """Atomically register the one receipt-backed seal for a window head.

    This is the window-side adapter used after the certificate owner has
    registered an authoritative ``LocalCommitReceipt``.  Receipt authority is
    resolved through the sealed private contract, so neither owner imports the
    other.
    """

    if not commit_window_state_is_current(state):
        raise GovernanceError("commit window seal requires the current window head")
    if not commit_window_ready(state):
        raise GovernanceError("commit window seal requires a stable ready window")
    if type(
        receipt
    ) is not LocalCommitReceipt or not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError("commit window seal requires an authoritative receipt")
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    state_ref = commit_window_state_fingerprint(state)
    common = (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    )
    for name in common:
        if getattr(receipt, name) != getattr(state, name):
            raise GovernanceError(f"commit window seal receipt {name} mismatch")
    expected = {
        "candidate_id": state.leader_candidate_id,
        "context_root": state.last_context_ref,
        "assessment_root": state.last_assessment_ref,
        "window_state_root": state_ref,
        "window_root": state.window_root,
        "risk_assessment_root": state.risk_assessment_root,
        "risk_chain_state_root": state.risk_chain_state_root,
        "risk_policy_root": state.risk_policy_root,
        "membership_root": state.membership_root,
        "membership_snapshot_root": state.membership_snapshot_root,
        "membership_epoch_state_root": state.membership_epoch_state_root,
        "threshold_root": state.threshold_root,
        "replay_state_root": state.assessment_replay_state_ref,
        "replay_root": state.assessment_replay_root,
        "support_replay_state_root": state.support_replay_state_root,
        "support_replay_root": state.support_replay_root,
        "evidence_root": state.collective_evidence_root,
        "challenge_root": state.collective_challenge_root,
        "lease_root": state.collective_lease_root,
        "candidate_evidence_root": state.candidate_evidence_root,
        "candidate_challenge_root": state.candidate_challenge_root,
        "candidate_lease_root": state.candidate_lease_root,
        "stop_resolution_root": state.stop_resolution_root,
        "permission_root": state.permission_root,
        "issued_at_step": state.last_evaluated_step,
    }
    for name, expected_value in expected.items():
        if getattr(receipt, name) != expected_value:
            raise GovernanceError(f"commit window seal receipt {name} lineage mismatch")

    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        raise GovernanceError("commit window seal cursor is invalid")
    request_ref = commit_payload_fingerprint(
        {
            "receipt_ref": receipt_ref,
            "window_state_ref": state_ref,
        },
        schema="pheroos-commit-window-seal-request-v1",
        profile=state.profile,
    )
    with cursor.lock:
        if (
            cursor.current_state is not state
            or cursor.current_state_fingerprint != state_ref
        ):
            raise GovernanceError("commit window seal state became stale")
        existing = cursor.current_seal
        if existing is not None:
            cached = cursor.seal_requests.get(receipt_ref)
            if (
                cached is not None
                and cached[0] == request_ref
                and cached[1] is existing
                and commit_window_seal_is_current(existing)
            ):
                return existing
            raise GovernanceError(
                "commit window is already sealed by a different local receipt"
            )
        if cursor.terminal_result is not None:
            raise GovernanceError("commit window is already terminal")
        seal = CommitWindowSeal(
            chain_id=state.chain_id,
            generation=cursor.seal_generation,
            profile=state.profile,
            assurance=state.assurance,
            manifest_root=state.manifest_root,
            commit_policy_root=state.commit_policy_root,
            protocol_id=state.protocol_id,
            run_id=state.run_id,
            target=state.target,
            epoch=state.epoch,
            receipt_ref=receipt_ref,
            candidate_id=receipt.candidate_id,
            claim_fingerprint=receipt.claim_fingerprint,
            output_payload_fingerprint=receipt.output_payload_fingerprint,
            context_ref=receipt.context_root,
            assessment_ref=receipt.assessment_root,
            window_state_ref=receipt.window_state_root,
            window_root=receipt.window_root,
            risk_assessment_root=receipt.risk_assessment_root,
            risk_chain_state_root=receipt.risk_chain_state_root,
            risk_policy_root=receipt.risk_policy_root,
            membership_root=receipt.membership_root,
            membership_snapshot_root=receipt.membership_snapshot_root,
            membership_epoch_state_root=receipt.membership_epoch_state_root,
            threshold_root=receipt.threshold_root,
            replay_state_ref=receipt.replay_state_root,
            replay_root=receipt.replay_root,
            support_replay_state_root=receipt.support_replay_state_root,
            support_replay_root=receipt.support_replay_root,
            collective_evidence_root=receipt.evidence_root,
            collective_challenge_root=receipt.challenge_root,
            collective_lease_root=receipt.lease_root,
            candidate_evidence_root=receipt.candidate_evidence_root,
            candidate_challenge_root=receipt.candidate_challenge_root,
            candidate_lease_root=receipt.candidate_lease_root,
            stop_resolution_root=receipt.stop_resolution_root,
            permission_root=receipt.permission_root,
            sealed_at_step=receipt.issued_at_step,
            absolute_deadline_step=state.absolute_deadline_step,
            absolute_run_deadline_step=state.absolute_run_deadline_step,
            remaining_reset_budget=state.remaining_reset_budget,
            remaining_epoch_restart_budget=state.remaining_epoch_restart_budget,
            issuer_id=receipt.issuer_id,
            authority=receipt.authority,
            provenance=receipt.provenance,
            trace_event_id=receipt.trace_event_id,
        )
        object.__setattr__(
            seal,
            "_issuance",
            (
                _COMMIT_WINDOW_SEAL_ISSUANCE,
                commit_window_seal_fingerprint(seal),
            ),
        )
        object.__setattr__(seal, "_cursor", cursor)
        cursor.current_seal = seal
        cursor.current_seal_fingerprint = commit_window_seal_fingerprint(seal)
        cursor.seal_requests[receipt_ref] = (request_ref, seal)
        return seal


def commit_window_seal_for_state(
    state: CommitWindowState,
) -> CommitWindowSeal | None:
    if not commit_window_state_is_current(state):
        return None
    cursor = state._cursor
    if type(cursor) is not _CommitWindowCursor:
        return None
    with cursor.lock:
        seal = cursor.current_seal
        return seal if commit_window_seal_is_current(seal) else None


def commit_window_seal_is_authoritative(seal: object) -> bool:
    if type(seal) is not CommitWindowSeal:
        return False
    try:
        _validate_commit_window_seal(seal)
        issuance = seal._issuance
        cursor = seal._cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_WINDOW_SEAL_ISSUANCE
            and issuance[1] == commit_window_seal_fingerprint(seal)
            and type(cursor) is _CommitWindowCursor
            and cursor.chain_id == seal.chain_id
        )
    except Exception:
        return False


def commit_window_seal_is_current(seal: object) -> bool:
    if not commit_window_seal_is_authoritative(seal):
        return False
    assert type(seal) is CommitWindowSeal
    cursor = seal._cursor
    assert type(cursor) is _CommitWindowCursor
    try:
        with cursor.lock:
            return bool(
                cursor.current_seal is seal
                and cursor.current_seal_fingerprint
                == commit_window_seal_fingerprint(seal)
                and cursor.current_state_fingerprint == seal.window_state_ref
                and cursor.seal_generation == seal.generation
            )
    except Exception:
        return False


def commit_window_seal_matches_receipt(
    state: CommitWindowState,
    receipt: object,
) -> bool:
    """Return whether ``receipt`` is the unique current seal authority."""

    try:
        seal = commit_window_seal_for_state(state)
        return bool(
            seal is not None
            and type(receipt) is LocalCommitReceipt
            and local_commit_receipt_is_authoritative(receipt)
            and seal.receipt_ref == local_commit_receipt_fingerprint(receipt)
            and seal.output_payload_fingerprint == receipt.output_payload_fingerprint
            and seal.claim_fingerprint == receipt.claim_fingerprint
        )
    except Exception:
        return False


def commit_window_seal_payload(seal: CommitWindowSeal) -> dict[str, object]:
    if type(seal) is not CommitWindowSeal:
        raise GovernanceError("commit window seal must use the canonical record")
    _validate_commit_window_seal(seal)
    return {
        name: getattr(seal, name)
        for name in seal.__dataclass_fields__
        if not name.startswith("_")
    }


def commit_window_seal_fingerprint(seal: CommitWindowSeal) -> str:
    return commit_payload_fingerprint(
        commit_window_seal_payload(seal),
        schema="pheroos-commit-window-seal-v1",
        profile=seal.profile,
    )


for _name in (
    "initialize_commit_window_state",
    "advance_commit_window_state",
    "reset_commit_window_state",
    "_transition_commit_window_state",
    "restart_commit_window_epoch",
    "commit_window_ready",
    "_seal_commit_window_from_local_receipt",
    "commit_window_seal_for_state",
    "commit_window_seal_is_authoritative",
    "commit_window_seal_is_current",
    "commit_window_seal_matches_receipt",
    "commit_window_seal_payload",
    "commit_window_seal_fingerprint",
):
    globals()[_name].__module__ = "pheroos.governance.commit_state"
del _name
