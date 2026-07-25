from __future__ import annotations
from collections.abc import Callable, Sequence
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._legacy.authority_registry import LEGACY_AUTHORITY_REGISTRY
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.governance._support.invariants import (
    _same_commit_scope,
)
from pheroos.governance._support.records import (
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseReplayReceipt,
    SupportLeaseReplayState,
    _LEGACY_SUPPORT_REPLAY_CURSORS,
    _SUPPORT_LEASE_REPLAY_STATE_ISSUANCE,
    _SupportLeaseReplayCursor,
    _canonical_support_replay_receipts,
    _support_replay_root,
    _support_replay_state_snapshot,
    _validate_support_replay_state_shape,
    support_lease_fingerprint,
    support_lease_replay_receipt_payload,
    support_lease_replay_state_fingerprint,
)


def _support_lease_replay_request_payload(lease: SupportLease) -> dict[str, object]:
    return {
        "assurance": lease.assurance,
        "authority": lease.authority,
        "candidate_id": lease.candidate_id,
        "claim_fingerprint": lease.claim_fingerprint,
        "commit_policy_root": lease.commit_policy_root,
        "epoch": lease.epoch,
        "expires_at_step": lease.expires_at_step,
        "issuance_provenance": lease.issuance_provenance,
        "issuance_trace_event_id": lease.issuance_trace_event_id,
        "issued_at_step": lease.issued_at_step,
        "issuer_id": lease.issuer_id,
        "lease_id": lease.lease_id,
        "manifest_root": lease.manifest_root,
        "membership_epoch_state_fingerprint": (
            lease.membership_epoch_state_fingerprint
        ),
        "membership_root": lease.membership_root,
        "nonce": lease.nonce,
        "positive_observation_fingerprints": (lease.positive_observation_fingerprints),
        "principal_cluster_id": lease.principal_cluster_id,
        "principal_id": lease.principal_id,
        "principal_verification_fingerprint": (
            lease.principal_verification_fingerprint
        ),
        "prior_lease_fingerprint": lease.prior_lease_fingerprint,
        "profile": lease.profile,
        "proposal_fingerprint": lease.proposal_fingerprint,
        "proposal_provenance": lease.proposal_provenance,
        "proposal_trace_event_id": lease.proposal_trace_event_id,
        "protocol_id": lease.protocol_id,
        "replay_authority_key": lease.replay_authority_key,
        "run_id": lease.run_id,
        "target": lease.target,
    }


def _support_replay_collision_by_keys(
    state: SupportLeaseReplayState,
    *,
    lease_id: str,
    proposal_fingerprint: str,
    nonce: str,
) -> SupportLeaseReplayReceipt | None:
    normalized_lease_id = require_commit_text(lease_id, "support replay lease_id")
    normalized_proposal = require_commit_fingerprint(
        proposal_fingerprint,
        "support replay proposal_fingerprint",
    )
    normalized_nonce = require_commit_text(nonce, "support replay nonce")
    collisions = tuple(
        receipt
        for receipt in state.receipts
        if (
            receipt.lease_id == normalized_lease_id
            or receipt.proposal_fingerprint == normalized_proposal
            or receipt.nonce == normalized_nonce
        )
    )
    if not collisions:
        return None
    fingerprints = {receipt.replay_receipt_fingerprint for receipt in collisions}
    if len(fingerprints) != 1:
        raise GovernanceError("support replay keys resolve to conflicting receipts")
    receipt = collisions[0]
    if not (
        receipt.lease_id == normalized_lease_id
        and receipt.proposal_fingerprint == normalized_proposal
        and receipt.nonce == normalized_nonce
    ):
        raise GovernanceError("support lease replay is a safety violation")
    return receipt


def _support_replay_collision_receipt(
    state: SupportLeaseReplayState,
    lease: SupportLease,
) -> SupportLeaseReplayReceipt | None:
    collisions = tuple(
        receipt
        for receipt in state.receipts
        if (
            receipt.lease_id == lease.lease_id
            or receipt.proposal_fingerprint == lease.proposal_fingerprint
            or receipt.nonce == lease.nonce
        )
    )
    if not collisions:
        return None
    fingerprints = {receipt.replay_receipt_fingerprint for receipt in collisions}
    if len(fingerprints) != 1:
        raise GovernanceError("support replay keys resolve to conflicting receipts")
    receipt = collisions[0]
    if not (
        receipt.lease_id == lease.lease_id
        and receipt.proposal_fingerprint == lease.proposal_fingerprint
        and receipt.nonce == lease.nonce
        and receipt.replay_receipt_fingerprint == lease.replay_receipt_fingerprint
    ):
        raise GovernanceError("support lease replay is a safety violation")
    return receipt


def _support_lease_replay_result_engine(
    candidate: SupportLease,
    *,
    prior_leases: Sequence[SupportLease],
    current_step: int,
    is_authoritative: Callable[[object], bool],
) -> SupportLease | None:
    if isinstance(prior_leases, (str, bytes, bytearray)):
        raise GovernanceError("prior support leases must be a sequence")
    current = require_commit_step(current_step, "support lease replay current_step")
    seen_lease_ids: set[str] = set()
    seen_proposals: set[str] = set()
    seen_nonces: set[str] = set()
    idempotent: SupportLease | None = None
    for prior in prior_leases:
        if not is_authoritative(prior):
            raise GovernanceError("prior support lease is not authoritative")
        if (
            prior.lease_id in seen_lease_ids
            or prior.proposal_fingerprint in seen_proposals
            or prior.nonce in seen_nonces
        ):
            raise GovernanceError(
                "prior support lease replay state contains a duplicate"
            )
        seen_lease_ids.add(prior.lease_id)
        seen_proposals.add(prior.proposal_fingerprint)
        seen_nonces.add(prior.nonce)
        collision = bool(
            prior.lease_id == candidate.lease_id
            or prior.proposal_fingerprint == candidate.proposal_fingerprint
            or prior.nonce == candidate.nonce
        )
        if not collision:
            continue
        exact_replay = bool(
            prior.lease_id == candidate.lease_id
            and prior.proposal_fingerprint == candidate.proposal_fingerprint
            and (prior.nonce == candidate.nonce)
            and (prior.profile == candidate.profile)
            and (prior.assurance is candidate.assurance)
            and (prior.manifest_root == candidate.manifest_root)
            and (prior.commit_policy_root == candidate.commit_policy_root)
            and (prior.protocol_id == candidate.protocol_id)
            and (prior.run_id == candidate.run_id)
            and (prior.target == candidate.target)
            and (prior.candidate_id == candidate.candidate_id)
            and (prior.claim_fingerprint == candidate.claim_fingerprint)
            and (prior.epoch == candidate.epoch)
            and (prior.principal_id == candidate.principal_id)
            and (prior.principal_cluster_id == candidate.principal_cluster_id)
            and (
                prior.principal_verification_fingerprint
                == candidate.principal_verification_fingerprint
            )
            and (prior.membership_root == candidate.membership_root)
            and (
                prior.membership_epoch_state_fingerprint
                == candidate.membership_epoch_state_fingerprint
            )
            and (
                prior.positive_observation_fingerprints
                == candidate.positive_observation_fingerprints
            )
            and (prior.prior_lease_fingerprint == candidate.prior_lease_fingerprint)
            and (prior.replay_authority_key == candidate.replay_authority_key)
            and (
                prior.replay_receipt_fingerprint == candidate.replay_receipt_fingerprint
            )
            and (prior.issuer_id == candidate.issuer_id)
            and (prior.authority is candidate.authority)
            and (prior.proposal_provenance == candidate.proposal_provenance)
            and (prior.proposal_trace_event_id == candidate.proposal_trace_event_id)
            and (prior.issuance_provenance == candidate.issuance_provenance)
            and (prior.issuance_trace_event_id == candidate.issuance_trace_event_id)
            and (prior.issued_at_step <= current < prior.expires_at_step)
        )
        if not exact_replay:
            raise GovernanceError("support lease replay is a safety violation")
        idempotent = prior
    return idempotent


def initialize_support_lease_replay_state(
    *,
    profile: str,
    protocol_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    initialized_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> SupportLeaseReplayState:
    normalized_profile = require_commit_profile(
        profile,
        "support replay state profile",
    )
    normalized_protocol = require_commit_text(
        protocol_id,
        "support replay state protocol_id",
    )
    normalized_issuer = require_commit_text(
        issuer_id,
        "support replay state issuer_id",
    )
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "support replay state initialization requires governance authority"
        )
    initialized = require_commit_step(
        initialized_at_step,
        "support replay state initialized_at_step",
    )
    normalized_provenance = require_commit_text(
        provenance,
        "support replay state provenance",
    )
    normalized_trace = require_commit_text(
        trace_event_id,
        "support replay state trace_event_id",
    )
    authority_key = commit_payload_fingerprint(
        {
            "issuer_id": normalized_issuer,
            "profile": normalized_profile,
            "protocol_id": normalized_protocol,
        },
        schema="pheroos-support-lease-replay-authority-key-v1",
        profile=normalized_profile,
    )
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority": authority,
            "authority_key": authority_key,
            "initialized_at_step": initialized,
            "provenance": normalized_provenance,
            "trace_event_id": normalized_trace,
        },
        schema="pheroos-support-lease-replay-base-v1",
        profile=normalized_profile,
    )
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        cursor = registry.get(_LEGACY_SUPPORT_REPLAY_CURSORS, authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "support replay authority already has a different immutable base"
                )
            state = cursor.current_state
            if (
                type(state) is not SupportLeaseReplayState
                or not support_lease_replay_state_is_current(state)
            ):
                raise GovernanceError(
                    "support replay authority exists but its current state is unavailable"
                )
            return state

        cursor = _SupportLeaseReplayCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
        )
        state = SupportLeaseReplayState(
            authority_key=authority_key,
            profile=normalized_profile,
            protocol_id=normalized_protocol,
            issuer_id=normalized_issuer,
            authority=authority,
            revision=0,
            receipts=(),
            replay_root=_support_replay_root((), profile=normalized_profile),
            previous_state_fingerprint="",
            initialized_at_step=initialized,
            last_issued_at_step=initialized,
            provenance=normalized_provenance,
            trace_event_id=normalized_trace,
        )
        state = _issue_support_replay_state(state, cursor)
        cursor.current_state_fingerprint = support_lease_replay_state_fingerprint(state)
        cursor.current_state = state
        registry.set(_LEGACY_SUPPORT_REPLAY_CURSORS, authority_key, cursor)
        return state


def support_lease_replay_state_is_authoritative(state: object) -> bool:
    if type(state) is not SupportLeaseReplayState:
        return False
    try:
        _validate_support_replay_state_shape(state)
        issuance = state._issuance
        cursor = state._cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _SUPPORT_LEASE_REPLAY_STATE_ISSUANCE
            and issuance[1] == _support_replay_state_snapshot(state)
            and type(cursor) is _SupportLeaseReplayCursor
            and cursor.authority_key == state.authority_key
        )
    except Exception:
        return False


def support_lease_replay_state_is_current(state: object) -> bool:
    if not support_lease_replay_state_is_authoritative(state):
        return False
    assert type(state) is SupportLeaseReplayState
    cursor = state._cursor
    assert type(cursor) is _SupportLeaseReplayCursor
    try:
        with cursor.lock:
            return (
                cursor.current_state is state
                and cursor.current_state_fingerprint
                == support_lease_replay_state_fingerprint(state)
            )
    except Exception:
        return False


def _issue_support_replay_state(
    state: SupportLeaseReplayState,
    cursor: _SupportLeaseReplayCursor,
) -> SupportLeaseReplayState:
    object.__setattr__(state, "_cursor", cursor)
    object.__setattr__(
        state,
        "_issuance",
        (
            _SUPPORT_LEASE_REPLAY_STATE_ISSUANCE,
            _support_replay_state_snapshot(state),
        ),
    )
    return state


def _support_lease_replay_request_fingerprint(lease: SupportLease) -> str:
    return commit_payload_fingerprint(
        _support_lease_replay_request_payload(lease),
        schema="pheroos-support-lease-replay-receipt-v1",
        profile=lease.profile,
    )


def _support_replay_receipt_from_lease(
    lease: SupportLease,
) -> SupportLeaseReplayReceipt:
    return SupportLeaseReplayReceipt(
        replay_receipt_fingerprint=lease.replay_receipt_fingerprint,
        lease_fingerprint=support_lease_fingerprint(lease),
        lease_id=lease.lease_id,
        proposal_fingerprint=lease.proposal_fingerprint,
        nonce=lease.nonce,
        profile=lease.profile,
        assurance=lease.assurance,
        manifest_root=lease.manifest_root,
        commit_policy_root=lease.commit_policy_root,
        protocol_id=lease.protocol_id,
        run_id=lease.run_id,
        target=lease.target,
        candidate_id=lease.candidate_id,
        claim_fingerprint=lease.claim_fingerprint,
        epoch=lease.epoch,
        principal_id=lease.principal_id,
        principal_cluster_id=lease.principal_cluster_id,
        membership_root=lease.membership_root,
        membership_epoch_state_fingerprint=(lease.membership_epoch_state_fingerprint),
        issued_at_step=lease.issued_at_step,
        expires_at_step=lease.expires_at_step,
    )


def _advance_support_replay_state(
    state: SupportLeaseReplayState,
    lease: SupportLease,
    *,
    cursor: _SupportLeaseReplayCursor,
) -> SupportLeaseReplayState:
    if lease.issued_at_step < state.last_issued_at_step:
        raise GovernanceError(
            "support replay state cannot move backward in logical time"
        )
    receipt = _support_replay_receipt_from_lease(lease)
    receipts = _canonical_support_replay_receipts((*state.receipts, receipt))
    next_state = SupportLeaseReplayState(
        authority_key=state.authority_key,
        profile=state.profile,
        protocol_id=state.protocol_id,
        issuer_id=state.issuer_id,
        authority=state.authority,
        revision=state.revision + 1,
        receipts=receipts,
        replay_root=_support_replay_root(receipts, profile=state.profile),
        previous_state_fingerprint=support_lease_replay_state_fingerprint(state),
        initialized_at_step=state.initialized_at_step,
        last_issued_at_step=lease.issued_at_step,
        provenance=lease.issuance_provenance,
        trace_event_id=lease.issuance_trace_event_id,
    )
    return _issue_support_replay_state(next_state, cursor)


def _support_replay_receipt_matches_scope(
    receipt: SupportLeaseReplayReceipt,
    *,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state_fingerprint: str,
) -> bool:
    return bool(
        _same_commit_scope(receipt, membership_snapshot)
        and receipt.membership_root == membership_snapshot.membership_root
        and receipt.membership_epoch_state_fingerprint
        == membership_epoch_state_fingerprint
    )


def _support_replay_scope_root(
    receipts: Sequence[SupportLeaseReplayReceipt],
    *,
    profile: str,
) -> str:
    canonical = _canonical_support_replay_receipts(receipts)
    return commit_payload_fingerprint(
        {
            "receipts": tuple(
                support_lease_replay_receipt_payload(receipt) for receipt in canonical
            )
        },
        schema="pheroos-support-lease-scope-replay-root-v1",
        profile=profile,
    )


for _name in (
    "initialize_support_lease_replay_state",
    "support_lease_replay_state_is_authoritative",
    "support_lease_replay_state_is_current",
):
    globals()[_name].__module__ = "pheroos.governance.support_lease"
del _name
