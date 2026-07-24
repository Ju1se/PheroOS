from __future__ import annotations

from collections.abc import Sequence
from typing import cast


from pheroos.governance._commit_state.invariants import (
    _validate_profile_assurance,
)


from pheroos.governance._commit_state.records import (
    _LEGACY_COMMIT_REPLAY_CURSORS,
    _CommitReplayCursor,
)


from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)


from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)

from pheroos.governance.commit_numeric import (
    commit_payload_fingerprint,
)

from pheroos.governance.authority import AuthorityLevel, can_verify

from pheroos.governance.errors import GovernanceError

from pheroos.protocol.commit_models import (
    CommitAssurance,
)

from pheroos.governance._commit_state.records import (
    ReplayReceipt,
    CommitReplayState,
    _issue_commit_replay_state,
    commit_replay_state_is_authoritative,
    commit_replay_state_is_current,
    replay_receipt_fingerprint,
    commit_replay_state_fingerprint,
    _canonical_replay_receipts,
    _commit_replay_receipt_root,
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
            return cast(CommitReplayState, cursor.current_state)
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
    additions = _collect_new_commit_replay_receipts(state, incoming)
    if not additions:
        return state

    combined = _canonical_replay_receipts((*state.receipts, *additions))
    parent_fingerprint = commit_replay_state_fingerprint(state)
    request_fingerprint = _commit_replay_request_fingerprint(
        state,
        current=current,
        parent_fingerprint=parent_fingerprint,
        additions=additions,
    )
    cursor = _require_commit_replay_cursor(state)
    with cursor.lock:
        cached = _cached_commit_replay_transition(
            cursor,
            parent_fingerprint=parent_fingerprint,
            request_fingerprint=request_fingerprint,
        )
        if cached is not None:
            return cached
    next_state = _next_commit_replay_state(
        state,
        current=current,
        parent_fingerprint=parent_fingerprint,
        receipts=combined,
    )
    with cursor.lock:
        cached = _cached_commit_replay_transition(
            cursor,
            parent_fingerprint=parent_fingerprint,
            request_fingerprint=request_fingerprint,
        )
        if cached is not None:
            return cached
        next_state = _issue_commit_replay_state(next_state, cursor=cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = commit_replay_state_fingerprint(next_state)
        cursor.transitions[parent_fingerprint] = (request_fingerprint, next_state)
        return next_state


def _collect_new_commit_replay_receipts(
    state: CommitReplayState,
    incoming: Sequence[ReplayReceipt],
) -> tuple[ReplayReceipt, ...]:
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
    return tuple(additions)


def _commit_replay_request_fingerprint(
    state: CommitReplayState,
    *,
    current: int,
    parent_fingerprint: str,
    additions: Sequence[ReplayReceipt],
) -> str:
    return commit_payload_fingerprint(
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


def _require_commit_replay_cursor(state: CommitReplayState) -> _CommitReplayCursor:
    cursor = state._cursor
    if type(cursor) is not _CommitReplayCursor:
        raise GovernanceError("commit replay cursor is invalid")
    return cursor


def _cached_commit_replay_transition(
    cursor: _CommitReplayCursor,
    *,
    parent_fingerprint: str,
    request_fingerprint: str,
) -> CommitReplayState | None:
    if cursor.current_state_fingerprint == parent_fingerprint:
        return None
    cached = cursor.transitions.get(parent_fingerprint)
    if cached is not None and cached[0] == request_fingerprint:
        return cached[1]
    raise GovernanceError("commit replay state is stale or would fork")


def _next_commit_replay_state(
    state: CommitReplayState,
    *,
    current: int,
    parent_fingerprint: str,
    receipts: Sequence[ReplayReceipt],
) -> CommitReplayState:
    return CommitReplayState(
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
        receipts=tuple(receipts),
        receipt_root=_commit_replay_receipt_root(
            receipts,
            profile=state.profile,
        ),
        issuer_id=state.issuer_id,
        authority=state.authority,
        provenance=state.provenance,
        trace_event_id=state.trace_event_id,
    )


for _name in ("initialize_commit_replay_state", "record_commit_replay_receipts"):
    globals()[_name].__module__ = "pheroos.governance.commit_state"
del _name
