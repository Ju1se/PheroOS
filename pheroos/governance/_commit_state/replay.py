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


def initialize_commit_replay_state(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    current_step: int,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitReplayState:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "commit replay initialization requires governance authority"
        )
    normalized_profile = require_commit_profile(profile, "commit replay profile")
    if type(assurance) is not CommitAssurance:
        raise GovernanceError("commit replay assurance is invalid")
    _validate_profile_assurance(
        normalized_profile,
        assurance,
        field_name="commit replay",
    )
    normalized_manifest = require_commit_fingerprint(
        manifest_root,
        "commit replay manifest_root",
    )
    normalized_policy = require_commit_fingerprint(
        commit_policy_root,
        "commit replay commit_policy_root",
    )
    normalized_protocol = require_commit_text(
        protocol_id,
        "commit replay protocol_id",
    )
    normalized_run = require_commit_text(run_id, "commit replay run_id")
    current = require_commit_step(current_step, "commit replay current_step")
    normalized_issuer = require_commit_text(issuer_id, "commit replay issuer_id")
    normalized_provenance = require_commit_text(
        provenance,
        "commit replay provenance",
    )
    normalized_trace = require_commit_text(
        trace_event_id,
        "commit replay trace_event_id",
    )
    authority_key = commit_payload_fingerprint(
        {
            "assurance": assurance,
            "commit_policy_root": normalized_policy,
            "manifest_root": normalized_manifest,
            "profile": normalized_profile,
            "protocol_id": normalized_protocol,
            "run_id": normalized_run,
        },
        schema="pheroos-commit-replay-authority-key-v1",
        profile=normalized_profile,
    )
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority": authority,
            "authority_key": authority_key,
            "initialized_at_step": current,
            "issuer_id": normalized_issuer,
            "provenance": normalized_provenance,
            "trace_event_id": normalized_trace,
        },
        schema="pheroos-commit-replay-base-v1",
        profile=normalized_profile,
    )
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        cursor = registry.get(_LEGACY_COMMIT_REPLAY_CURSORS, authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "commit replay authority already has a different base"
                )
            if not commit_replay_state_is_current(cursor.current_state):
                raise GovernanceError("commit replay current state is unavailable")
            assert cursor.current_state is not None
            return cursor.current_state
        cursor = _CommitReplayCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
        )
        state = CommitReplayState(
            chain_id=authority_key,
            profile=normalized_profile,
            assurance=assurance,
            manifest_root=normalized_manifest,
            commit_policy_root=normalized_policy,
            protocol_id=normalized_protocol,
            run_id=normalized_run,
            revision=0,
            initialized_at_step=current,
            current_step=current,
            previous_state_fingerprint="",
            receipts=(),
            receipt_root=_commit_replay_receipt_root(
                (),
                profile=normalized_profile,
            ),
            issuer_id=normalized_issuer,
            authority=authority,
            provenance=normalized_provenance,
            trace_event_id=normalized_trace,
        )
        state = _issue_commit_replay_state(state, cursor=cursor)
        cursor.current_state = state
        cursor.current_state_fingerprint = commit_replay_state_fingerprint(state)
        registry.set(_LEGACY_COMMIT_REPLAY_CURSORS, authority_key, cursor)
        return state


def record_commit_replay_receipts(
    state: CommitReplayState,
    *,
    current_step: int,
    receipts: Sequence[ReplayReceipt],
) -> CommitReplayState:
    if not commit_replay_state_is_authoritative(state):
        raise GovernanceError("commit replay state is not governance-issued")
    current = require_commit_step(current_step, "commit replay current_step")
    if current < state.current_step:
        raise GovernanceError("commit replay step cannot move backwards")
    incoming = _canonical_replay_receipts(receipts)
    if not incoming:
        return state
    existing_by_nonce = {item.nonce: item for item in state.receipts}
    existing_by_id = {(item.namespace, item.record_id): item for item in state.receipts}
    existing_by_payload = {item.payload_fingerprint: item for item in state.receipts}
    additions: list[ReplayReceipt] = []
    for receipt in incoming:
        collisions = tuple(
            item
            for item in (
                existing_by_nonce.get(receipt.nonce),
                existing_by_id.get((receipt.namespace, receipt.record_id)),
                existing_by_payload.get(receipt.payload_fingerprint),
            )
            if item is not None
        )
        if collisions:
            if any(item != receipt for item in collisions):
                raise GovernanceError(
                    "commit replay receipt collision is a safety violation"
                )
            continue
        additions.append(receipt)
        existing_by_nonce[receipt.nonce] = receipt
        existing_by_id[(receipt.namespace, receipt.record_id)] = receipt
        existing_by_payload[receipt.payload_fingerprint] = receipt
    if not additions:
        return state

    combined = _canonical_replay_receipts((*state.receipts, *additions))
    parent_fingerprint = commit_replay_state_fingerprint(state)
    request_fingerprint = commit_payload_fingerprint(
        {
            "current_step": current,
            "parent_state_fingerprint": parent_fingerprint,
            "receipt_fingerprints": tuple(
                replay_receipt_fingerprint(item, profile=state.profile)
                for item in additions
            ),
        },
        schema="pheroos-commit-replay-transition-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _CommitReplayCursor:
        raise GovernanceError("commit replay cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_fingerprint:
            cached = cursor.transitions.get(parent_fingerprint)
            if cached is not None and cached[0] == request_fingerprint:
                return cached[1]
            raise GovernanceError("commit replay state is stale or would fork")
    next_state = CommitReplayState(
        chain_id=state.chain_id,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        revision=state.revision + 1,
        initialized_at_step=state.initialized_at_step,
        current_step=current,
        previous_state_fingerprint=parent_fingerprint,
        receipts=combined,
        receipt_root=_commit_replay_receipt_root(
            combined,
            profile=state.profile,
        ),
        issuer_id=state.issuer_id,
        authority=state.authority,
        provenance=state.provenance,
        trace_event_id=state.trace_event_id,
    )
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_fingerprint:
            cached = cursor.transitions.get(parent_fingerprint)
            if cached is not None and cached[0] == request_fingerprint:
                return cached[1]
            raise GovernanceError("commit replay state is stale or would fork")
        next_state = _issue_commit_replay_state(next_state, cursor=cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = commit_replay_state_fingerprint(next_state)
        cursor.transitions[parent_fingerprint] = (request_fingerprint, next_state)
        return next_state


for _name in ("initialize_commit_replay_state", "record_commit_replay_receipts"):
    globals()[_name].__module__ = "pheroos.governance.commit_state"
del _name
