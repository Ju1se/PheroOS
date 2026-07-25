from __future__ import annotations
from collections.abc import Callable, Sequence
from typing import Any, cast
from pheroos.governance._commit_validation import (
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import checked_add
from pheroos.governance.errors import GovernanceError
from pheroos.governance.observation import (
    ObservationPolarity,
    VerifiedObservation,
    verified_observation_fingerprint,
    verified_observation_matches,
)
from pheroos.governance.principal import (
    PrincipalVerification,
    principal_verification_fingerprint,
    principal_verification_matches,
)
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    SupportLeasePolicy,
)
from pheroos.governance._support.invariants import (
    _canonical_fingerprints,
    _same_commit_scope,
    _validate_commit_policy_binding,
    _validate_support_policy,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseExpiration,
    SupportLeaseProposal,
    SupportLeaseReplayReceipt,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
    SupportLeaseStatus,
    SupportLeaseSwitch,
    _SUPPORT_LEASE_ISSUANCE,
    _SUPPORT_REVOCATION_ISSUANCE,
    _SupportLeaseReplayCursor,
    _support_lease_snapshot,
    _support_revocation_snapshot,
    _validate_support_lease_shape,
    _validate_support_proposal,
    _validate_support_revocation_shape,
    eligible_membership_epoch_state_fingerprint,
    support_lease_fingerprint,
    support_lease_proposal_fingerprint,
    support_lease_replay_state_fingerprint,
)
from pheroos.governance._support.membership import (
    _membership_contains_principal,
    eligible_principal_snapshot_matches,
)
from pheroos.governance._support.replay import (
    _advance_support_replay_state,
    _support_lease_replay_request_fingerprint,
    _support_lease_replay_result_engine,
    _support_replay_collision_by_keys,
    _support_replay_collision_receipt,
    support_lease_replay_state_is_authoritative,
    support_lease_replay_state_is_current,
)


def _support_lease_replay_result(
    candidate: SupportLease,
    *,
    prior_leases: Sequence[SupportLease],
    current_step: int,
) -> SupportLease | None:
    return _support_lease_replay_result_engine(
        candidate,
        prior_leases=prior_leases,
        current_step=current_step,
        is_authoritative=support_lease_is_authoritative,
    )


def evaluate_lease_status(
    lease: Any,
    *,
    current_step: int,
    revocations: Sequence[Any],
    equivocated_lease_fingerprints: Sequence[str],
    is_authoritative: Callable[[object], bool],
    canonical_fingerprints: Callable[..., tuple[str, ...]],
    lease_fingerprint: Callable[[Any], str],
    effective_revocation: Callable[..., Any | None],
    status_type: Any,
) -> Any:
    if not is_authoritative(lease):
        raise GovernanceError("support lease status requires an authoritative lease")
    current = require_commit_step(current_step, "support lease status current_step")
    conflicts = canonical_fingerprints(
        equivocated_lease_fingerprints,
        "support lease status equivocated fingerprints",
        allow_empty=True,
    )
    fingerprint = lease_fingerprint(lease)
    if fingerprint in conflicts:
        return status_type.EQUIVOCATED
    revoked = effective_revocation(
        lease,
        tuple(revocations),
        current_step=current,
    )
    if revoked is not None:
        return status_type.REVOKED
    if current >= lease.expires_at_step:
        return status_type.EXPIRED
    if current < lease.issued_at_step:
        raise GovernanceError("support lease is not yet active")
    return status_type.ACTIVE


def issue_support_lease(
    proposal: SupportLeaseProposal,
    *,
    principal_verification: PrincipalVerification,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    positive_observations: Sequence[VerifiedObservation],
    commit_policy: CollectiveCommitPolicy,
    lease_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    issuance_provenance: str,
    issuance_trace_event_id: str,
    prior_leases: Sequence[SupportLease] = (),
    prior_lease: SupportLease | None = None,
    prior_revocation: SupportLeaseRevocation | None = None,
) -> tuple[SupportLease, SupportLeaseReplayState]:
    current, lease_policy, normalized_issuer = _validate_support_lease_request(
        proposal,
        replay_state=replay_state,
        commit_policy=commit_policy,
        issuer_id=issuer_id,
        authority=authority,
        current_step=current_step,
    )
    _validate_support_lease_principal(
        proposal,
        principal_verification=principal_verification,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        current_step=current,
    )
    normalized_observations, observation_expiries = (
        _validated_support_lease_observations(
            proposal,
            positive_observations=positive_observations,
            current_step=current,
        )
    )
    expires = checked_add(current, lease_policy.lease_ttl_steps)
    _validate_support_lease_expiration(
        principal_verification=principal_verification,
        membership_snapshot=membership_snapshot,
        observation_expiries=observation_expiries,
        expires_at_step=expires,
    )
    normalized_prior_lease_fingerprint = _validate_support_lease_switch(
        proposal,
        principal_verification=principal_verification,
        prior_lease=prior_lease,
        prior_revocation=prior_revocation,
        current_step=current,
    )
    proposal_fingerprint = support_lease_proposal_fingerprint(proposal)
    replay_collision = _support_replay_collision_by_keys(
        replay_state,
        lease_id=require_commit_text(lease_id, "support lease lease_id"),
        proposal_fingerprint=proposal_fingerprint,
        nonce=proposal.nonce,
    )
    replay_result = _support_lease_key_replay_result(
        replay_collision,
        replay_state=replay_state,
        proposal=proposal,
        principal_verification=principal_verification,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        normalized_observations=normalized_observations,
        normalized_prior_lease_fingerprint=normalized_prior_lease_fingerprint,
        lease_id=lease_id,
        normalized_issuer=normalized_issuer,
        authority=authority,
        current_step=current,
        issuance_provenance=issuance_provenance,
        issuance_trace_event_id=issuance_trace_event_id,
    )
    if replay_result is not None:
        return replay_result

    lease = SupportLease(
        lease_id=require_commit_text(lease_id, "support lease lease_id"),
        proposal_fingerprint=proposal_fingerprint,
        profile=proposal.profile,
        assurance=proposal.assurance,
        manifest_root=proposal.manifest_root,
        commit_policy_root=proposal.commit_policy_root,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        candidate_id=proposal.candidate_id,
        claim_fingerprint=proposal.claim_fingerprint,
        epoch=proposal.epoch,
        principal_id=proposal.principal_id,
        principal_cluster_id=principal_verification.cluster_id,
        principal_verification_fingerprint=principal_verification_fingerprint(
            principal_verification
        ),
        membership_root=membership_snapshot.membership_root,
        membership_epoch_state_fingerprint=(
            eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        ),
        positive_observation_fingerprints=normalized_observations,
        prior_lease_fingerprint=normalized_prior_lease_fingerprint,
        nonce=proposal.nonce,
        replay_authority_key=replay_state.authority_key,
        replay_receipt_fingerprint="sha256:" + ("0" * 64),
        issuer_id=normalized_issuer,
        authority=authority,
        issued_at_step=current,
        expires_at_step=expires,
        proposal_provenance=proposal.provenance,
        proposal_trace_event_id=proposal.trace_event_id,
        issuance_provenance=require_commit_text(
            issuance_provenance,
            "support lease issuance provenance",
        ),
        issuance_trace_event_id=require_commit_text(
            issuance_trace_event_id,
            "support lease issuance trace_event_id",
        ),
    )
    object.__setattr__(
        lease,
        "replay_receipt_fingerprint",
        _support_lease_replay_request_fingerprint(lease),
    )
    return _record_support_lease(
        lease,
        replay_state=replay_state,
        prior_leases=prior_leases,
        current_step=current,
    )


def _validate_support_lease_request(
    proposal: SupportLeaseProposal,
    *,
    replay_state: SupportLeaseReplayState,
    commit_policy: CollectiveCommitPolicy,
    issuer_id: str,
    authority: object,
    current_step: int,
) -> tuple[int, SupportLeasePolicy, str]:
    if type(proposal) is not SupportLeaseProposal:
        raise GovernanceError("support lease issuance requires a canonical proposal")
    _validate_support_proposal(proposal)
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("support lease issuance requires governance authority")
    current = require_commit_step(current_step, "support lease current_step")
    if proposal.proposed_at_step > current:
        raise GovernanceError("support lease proposal is from a future step")
    _validate_commit_policy_binding(commit_policy, proposal)
    lease_policy = commit_policy.support_lease
    _validate_support_policy(lease_policy)
    normalized_issuer = require_commit_text(issuer_id, "support lease issuer_id")
    if not support_lease_replay_state_is_authoritative(replay_state):
        raise GovernanceError(
            "support lease issuance requires an authoritative replay state"
        )
    if (
        replay_state.profile != proposal.profile
        or replay_state.protocol_id != proposal.protocol_id
        or replay_state.issuer_id != normalized_issuer
        or replay_state.authority is not authority
    ):
        raise GovernanceError("support lease replay authority binding mismatch")
    return current, lease_policy, normalized_issuer


def _validate_support_lease_principal(
    proposal: SupportLeaseProposal,
    *,
    principal_verification: PrincipalVerification,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    current_step: int,
) -> None:
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=proposal.profile,
        assurance=proposal.assurance,
        manifest_root=proposal.manifest_root,
        commit_policy_root=proposal.commit_policy_root,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        current_step=current_step,
    ):
        raise GovernanceError(
            "support lease membership is forged, stale, or has a binding mismatch"
        )
    if not principal_verification_matches(
        principal_verification,
        profile=proposal.profile,
        assurance=proposal.assurance,
        manifest_root=proposal.manifest_root,
        commit_policy_root=proposal.commit_policy_root,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        principal_id=proposal.principal_id,
        current_step=current_step,
    ):
        raise GovernanceError(
            "support lease principal verification is forged, stale, or mismatched"
        )
    if not _membership_contains_principal(
        membership_snapshot,
        principal_id=proposal.principal_id,
        cluster_id=principal_verification.cluster_id,
        verification_fingerprint=principal_verification_fingerprint(
            principal_verification
        ),
    ):
        raise GovernanceError(
            "support lease principal is not in the eligible membership snapshot"
        )


def _validated_support_lease_observations(
    proposal: SupportLeaseProposal,
    *,
    positive_observations: Sequence[VerifiedObservation],
    current_step: int,
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    observations = tuple(positive_observations)
    if not observations:
        raise GovernanceError("support lease requires positive evidence")
    observation_fingerprints: list[str] = []
    observation_expiries: list[int] = []
    for observation in observations:
        if not verified_observation_matches(
            observation,
            profile=proposal.profile,
            assurance=proposal.assurance,
            manifest_root=proposal.manifest_root,
            commit_policy_root=proposal.commit_policy_root,
            protocol_id=proposal.protocol_id,
            run_id=proposal.run_id,
            target=proposal.target,
            candidate_id=proposal.candidate_id,
            claim_fingerprint=proposal.claim_fingerprint,
            epoch=proposal.epoch,
            current_step=current_step,
            polarity=ObservationPolarity.SUPPORT,
        ):
            raise GovernanceError(
                "support lease evidence is not authoritative, positive, fresh, "
                "and bound"
            )
        observation_fingerprints.append(verified_observation_fingerprint(observation))
        observation_expiries.append(observation.expires_at_step)
    normalized_observations = _canonical_fingerprints(
        observation_fingerprints,
        "support lease evidence fingerprints",
    )
    if normalized_observations != proposal.positive_observation_fingerprints:
        raise GovernanceError(
            "support lease proposal evidence references do not match verified evidence"
        )
    return normalized_observations, tuple(observation_expiries)


def _validate_support_lease_expiration(
    *,
    principal_verification: PrincipalVerification,
    membership_snapshot: EligiblePrincipalSnapshot,
    observation_expiries: Sequence[int],
    expires_at_step: int,
) -> None:
    expires = expires_at_step
    if principal_verification.expires_at_step < expires:
        raise GovernanceError(
            "support lease TTL exceeds principal verification freshness"
        )
    if membership_snapshot.expires_at_step < expires:
        raise GovernanceError("support lease TTL exceeds membership freshness")
    if min(observation_expiries) < expires:
        raise GovernanceError("support lease TTL exceeds referenced evidence freshness")


def _validate_support_lease_switch(
    proposal: SupportLeaseProposal,
    *,
    principal_verification: PrincipalVerification,
    prior_lease: SupportLease | None,
    prior_revocation: SupportLeaseRevocation | None,
    current_step: int,
) -> str:
    normalized_prior_lease_fingerprint = ""
    if (prior_lease is None) != (prior_revocation is None):
        raise GovernanceError(
            "support lease switch requires both prior lease and revocation"
        )
    if prior_lease is not None and prior_revocation is not None:
        if not support_lease_is_authoritative(prior_lease):
            raise GovernanceError(
                "support lease switch prior lease is not authoritative"
            )
        if not support_lease_revocation_matches(
            prior_revocation,
            lease=prior_lease,
            current_step=current_step,
        ):
            raise GovernanceError(
                "support lease switch revocation is forged or mismatched"
            )
        if prior_revocation.revoked_at_step != current_step:
            raise GovernanceError(
                "support lease switch must revoke and issue at the same step"
            )
        if not _same_commit_scope(prior_lease, proposal):
            raise GovernanceError("support lease switch scope mismatch")
        if (
            prior_lease.principal_id != proposal.principal_id
            or prior_lease.principal_cluster_id != principal_verification.cluster_id
        ):
            raise GovernanceError(
                "support lease switch must preserve principal and cluster identity"
            )
        if prior_lease.candidate_id == proposal.candidate_id:
            raise GovernanceError("support lease switch requires a different candidate")
        normalized_prior_lease_fingerprint = support_lease_fingerprint(prior_lease)
    return normalized_prior_lease_fingerprint


def _support_lease_key_replay_result(
    replay_collision: SupportLeaseReplayReceipt | None,
    *,
    replay_state: SupportLeaseReplayState,
    proposal: SupportLeaseProposal,
    principal_verification: PrincipalVerification,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    normalized_observations: tuple[str, ...],
    normalized_prior_lease_fingerprint: str,
    lease_id: str,
    normalized_issuer: str,
    authority: object,
    current_step: int,
    issuance_provenance: str,
    issuance_trace_event_id: str,
) -> tuple[SupportLease, SupportLeaseReplayState] | None:
    if replay_collision is None:
        return None
    proposal_fingerprint = support_lease_proposal_fingerprint(proposal)
    cursor = replay_state._cursor
    if type(cursor) is not _SupportLeaseReplayCursor:
        raise GovernanceError("support lease replay cursor is invalid")
    stored = cursor.leases_by_fingerprint.get(replay_collision.lease_fingerprint)
    current_replay_state = cursor.current_state
    if not (
        type(stored) is SupportLease
        and support_lease_is_authoritative(stored)
        and type(current_replay_state) is SupportLeaseReplayState
        and support_lease_replay_state_is_current(current_replay_state)
        and stored.proposal_fingerprint == proposal_fingerprint
        and stored.lease_id == lease_id
        and stored.nonce == proposal.nonce
        and stored.profile == proposal.profile
        and stored.assurance is proposal.assurance
        and stored.manifest_root == proposal.manifest_root
        and stored.commit_policy_root == proposal.commit_policy_root
        and stored.protocol_id == proposal.protocol_id
        and stored.run_id == proposal.run_id
        and stored.target == proposal.target
        and stored.candidate_id == proposal.candidate_id
        and stored.claim_fingerprint == proposal.claim_fingerprint
        and stored.epoch == proposal.epoch
        and stored.principal_id == proposal.principal_id
        and stored.principal_cluster_id == principal_verification.cluster_id
        and stored.principal_verification_fingerprint
        == principal_verification_fingerprint(principal_verification)
        and stored.membership_root == membership_snapshot.membership_root
        and stored.membership_epoch_state_fingerprint
        == eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        and stored.positive_observation_fingerprints == normalized_observations
        and stored.prior_lease_fingerprint == normalized_prior_lease_fingerprint
        and stored.issuer_id == normalized_issuer
        and stored.authority is authority
        and stored.proposal_provenance == proposal.provenance
        and stored.proposal_trace_event_id == proposal.trace_event_id
        and stored.issuance_provenance == issuance_provenance
        and stored.issuance_trace_event_id == issuance_trace_event_id
        and stored.issued_at_step <= current_step < stored.expires_at_step
    ):
        raise GovernanceError("support lease replay is a safety violation")
    return stored, current_replay_state


def _record_support_lease(
    lease: SupportLease,
    *,
    replay_state: SupportLeaseReplayState,
    prior_leases: Sequence[SupportLease],
    current_step: int,
) -> tuple[SupportLease, SupportLeaseReplayState]:
    replayed_from_history = _support_lease_replay_result(
        lease,
        prior_leases=tuple(prior_leases),
        current_step=current_step,
    )
    parent_state_fingerprint = support_lease_replay_state_fingerprint(replay_state)
    request_fingerprint = _support_lease_snapshot(lease)
    cursor = replay_state._cursor
    if type(cursor) is not _SupportLeaseReplayCursor:
        raise GovernanceError("support lease replay cursor is invalid")
    with cursor.lock:
        stale_result = _support_lease_stale_transition_result(
            cursor,
            parent_state_fingerprint=parent_state_fingerprint,
            request_fingerprint=request_fingerprint,
        )
        if stale_result is not None:
            return stale_result
        collision_result = _support_lease_receipt_collision_result(
            cursor,
            lease=lease,
            replay_state=replay_state,
            current_step=current_step,
        )
        if collision_result is not None:
            return collision_result
        if replayed_from_history is not None:
            raise GovernanceError(
                "caller lease history is not present in the authoritative replay state"
            )

        object.__setattr__(lease, "_replay_cursor", cursor)
        object.__setattr__(
            lease,
            "_issuance",
            (_SUPPORT_LEASE_ISSUANCE, request_fingerprint),
        )
        next_state = _advance_support_replay_state(
            replay_state,
            lease,
            cursor=cursor,
        )
        next_state_fingerprint = support_lease_replay_state_fingerprint(next_state)
        cursor.current_state_fingerprint = next_state_fingerprint
        cursor.current_state = next_state
        cursor.leases_by_fingerprint[support_lease_fingerprint(lease)] = lease
        cursor.transitions[parent_state_fingerprint] = (
            request_fingerprint,
            lease,
            next_state,
        )
        return lease, next_state


def _support_lease_stale_transition_result(
    cursor: _SupportLeaseReplayCursor,
    *,
    parent_state_fingerprint: str,
    request_fingerprint: str,
) -> tuple[SupportLease, SupportLeaseReplayState] | None:
    if cursor.current_state_fingerprint == parent_state_fingerprint:
        return None
    transition = cursor.transitions.get(parent_state_fingerprint)
    if transition is not None and transition[0] == request_fingerprint:
        prior_lease_result = transition[1]
        prior_state_result = transition[2]
        if (
            type(prior_lease_result) is SupportLease
            and type(prior_state_result) is SupportLeaseReplayState
            and support_lease_is_authoritative(prior_lease_result)
            and support_lease_replay_state_is_current(prior_state_result)
        ):
            return prior_lease_result, prior_state_result
        raise GovernanceError("support lease replay result is no longer available")
    raise GovernanceError("support lease replay state is stale or would fork")


def _support_lease_receipt_collision_result(
    cursor: _SupportLeaseReplayCursor,
    *,
    lease: SupportLease,
    replay_state: SupportLeaseReplayState,
    current_step: int,
) -> tuple[SupportLease, SupportLeaseReplayState] | None:
    collision_receipt = _support_replay_collision_receipt(replay_state, lease)
    if collision_receipt is None:
        return None
    stored = cursor.leases_by_fingerprint.get(collision_receipt.lease_fingerprint)
    if (
        stored is None
        or not support_lease_is_authoritative(stored)
        or _support_lease_replay_result(
            lease,
            prior_leases=(stored,),
            current_step=current_step,
        )
        is not stored
    ):
        raise GovernanceError(
            "support lease replay receipt conflicts with local authority state"
        )
    return stored, replay_state


def support_lease_is_authoritative(lease: object) -> bool:
    if type(lease) is not SupportLease:
        return False
    try:
        _validate_support_lease_shape(lease)
        issuance = lease._issuance
        cursor = lease._replay_cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _SUPPORT_LEASE_ISSUANCE
            and issuance[1] == _support_lease_snapshot(lease)
            and type(cursor) is _SupportLeaseReplayCursor
            and cursor.authority_key == lease.replay_authority_key
            and lease.replay_receipt_fingerprint
            == _support_lease_replay_request_fingerprint(lease)
        )
    except Exception:
        return False


def revoke_support_lease(
    lease: SupportLease,
    *,
    revocation_id: str,
    reason_codes: Sequence[str],
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
    prior_revocations: Sequence[SupportLeaseRevocation] = (),
) -> SupportLeaseRevocation:
    if not support_lease_is_authoritative(lease):
        raise GovernanceError(
            "support lease revocation requires an authoritative lease"
        )
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("support lease revocation requires governance authority")
    current = require_commit_step(current_step, "support lease revoked_at_step")
    if current < lease.issued_at_step or current >= lease.expires_at_step:
        raise GovernanceError("only an active support lease may be revoked")
    fingerprint = support_lease_fingerprint(lease)
    for revocation in tuple(prior_revocations):
        if not support_lease_revocation_is_authoritative(revocation):
            raise GovernanceError("prior support revocation is not authoritative")
        if revocation.lease_fingerprint == fingerprint:
            raise GovernanceError("support lease is already revoked")
    revocation = SupportLeaseRevocation(
        revocation_id=require_commit_text(
            revocation_id,
            "support lease revocation_id",
        ),
        lease_fingerprint=fingerprint,
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
        reason_codes=tuple(reason_codes),
        issuer_id=require_commit_text(
            issuer_id,
            "support lease revocation issuer_id",
        ),
        authority=authority,
        revoked_at_step=current,
        provenance=require_commit_text(
            provenance,
            "support lease revocation provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "support lease revocation trace_event_id",
        ),
    )
    object.__setattr__(
        revocation,
        "_issuance",
        (_SUPPORT_REVOCATION_ISSUANCE, _support_revocation_snapshot(revocation)),
    )
    return revocation


def support_lease_revocation_is_authoritative(revocation: object) -> bool:
    if type(revocation) is not SupportLeaseRevocation:
        return False
    try:
        _validate_support_revocation_shape(revocation)
        issuance = revocation._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _SUPPORT_REVOCATION_ISSUANCE
            and issuance[1] == _support_revocation_snapshot(revocation)
        )
    except Exception:
        return False


def support_lease_revocation_matches(
    revocation: SupportLeaseRevocation | None,
    *,
    lease: SupportLease,
    current_step: int,
) -> bool:
    try:
        current = require_commit_step(current_step, "support revocation current_step")
        return bool(
            support_lease_is_authoritative(lease)
            and support_lease_revocation_is_authoritative(revocation)
            and revocation is not None
            and revocation.lease_fingerprint == support_lease_fingerprint(lease)
            and _same_commit_scope(revocation, lease)
            and revocation.candidate_id == lease.candidate_id
            and revocation.claim_fingerprint == lease.claim_fingerprint
            and revocation.principal_id == lease.principal_id
            and revocation.principal_cluster_id == lease.principal_cluster_id
            and lease.issued_at_step
            <= revocation.revoked_at_step
            < lease.expires_at_step
            and revocation.revoked_at_step <= current
        )
    except GovernanceError:
        return False


def switch_support_lease(
    lease: SupportLease,
    proposal: SupportLeaseProposal,
    *,
    principal_verification: PrincipalVerification,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    positive_observations: Sequence[VerifiedObservation],
    commit_policy: CollectiveCommitPolicy,
    revocation_id: str,
    revocation_reason_codes: Sequence[str],
    lease_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    revocation_provenance: str,
    revocation_trace_event_id: str,
    issuance_provenance: str,
    issuance_trace_event_id: str,
    prior_leases: Sequence[SupportLease] = (),
    prior_revocations: Sequence[SupportLeaseRevocation] = (),
) -> tuple[SupportLeaseSwitch, SupportLeaseReplayState]:
    revocation = revoke_support_lease(
        lease,
        revocation_id=revocation_id,
        reason_codes=revocation_reason_codes,
        issuer_id=issuer_id,
        authority=authority,
        current_step=current_step,
        provenance=revocation_provenance,
        trace_event_id=revocation_trace_event_id,
        prior_revocations=prior_revocations,
    )
    replacement, next_replay_state = issue_support_lease(
        proposal,
        principal_verification=principal_verification,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        positive_observations=positive_observations,
        commit_policy=commit_policy,
        lease_id=lease_id,
        issuer_id=issuer_id,
        authority=authority,
        current_step=current_step,
        issuance_provenance=issuance_provenance,
        issuance_trace_event_id=issuance_trace_event_id,
        prior_leases=prior_leases,
        prior_lease=lease,
        prior_revocation=revocation,
    )
    return (
        SupportLeaseSwitch(revocation=revocation, lease=replacement),
        next_replay_state,
    )


def expire_support_lease(
    lease: SupportLease,
    *,
    current_step: int,
) -> SupportLeaseExpiration:
    if not support_lease_is_authoritative(lease):
        raise GovernanceError(
            "support lease expiration requires an authoritative lease"
        )
    current = require_commit_step(current_step, "support lease expiration current_step")
    if current < lease.expires_at_step:
        raise GovernanceError("support lease has not expired")
    return SupportLeaseExpiration(
        lease_fingerprint=support_lease_fingerprint(lease),
        expired_at_step=lease.expires_at_step,
    )


def support_lease_status(
    lease: SupportLease,
    *,
    current_step: int,
    revocations: Sequence[SupportLeaseRevocation] = (),
    equivocated_lease_fingerprints: Sequence[str] = (),
) -> SupportLeaseStatus:
    return cast(
        SupportLeaseStatus,
        evaluate_lease_status(
            lease,
            current_step=current_step,
            revocations=revocations,
            equivocated_lease_fingerprints=equivocated_lease_fingerprints,
            is_authoritative=support_lease_is_authoritative,
            canonical_fingerprints=_canonical_fingerprints,
            lease_fingerprint=support_lease_fingerprint,
            effective_revocation=_effective_revocation,
            status_type=SupportLeaseStatus,
        ),
    )


def _effective_revocation(
    lease: SupportLease,
    revocations: Sequence[SupportLeaseRevocation],
    *,
    current_step: int,
) -> SupportLeaseRevocation | None:
    matches = [
        item
        for item in revocations
        if support_lease_revocation_matches(
            item,
            lease=lease,
            current_step=current_step,
        )
    ]
    if len(matches) > 1:
        raise GovernanceError("support lease has multiple effective revocations")
    return matches[0] if matches else None


for _name in (
    "issue_support_lease",
    "support_lease_is_authoritative",
    "revoke_support_lease",
    "support_lease_revocation_is_authoritative",
    "support_lease_revocation_matches",
    "switch_support_lease",
    "expire_support_lease",
    "support_lease_status",
):
    globals()[_name].__module__ = "pheroos.governance.support_lease"
del _name
