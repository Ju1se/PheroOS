from __future__ import annotations
from collections import defaultdict
from collections.abc import Sequence
from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._legacy.authority_registry import LEGACY_AUTHORITY_REGISTRY
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.governance.principal import (
    PrincipalVerification,
    principal_verification_fingerprint,
    principal_verification_is_authoritative,
    principal_verification_matches,
)
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.governance._support.invariants import (
    _canonical_fingerprints,
    _eligible_cluster_payload,
    _equivocation_finding_id,
    _membership_epoch_authority_key,
    _membership_root,
    _normalized_bindings,
    _record_bindings_equal,
    _same_commit_scope,
    _support_replay_authority_key,
    _validate_bound_record,
    _validate_commit_policy_binding,
    _validate_eligible_principal,
    _validate_support_policy,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipal,
    EligiblePrincipalCluster,
    EligiblePrincipalSnapshot,
    SupportEquivocationFinding,
    SupportLease,
    SupportLeaseEvaluation,
    SupportLeaseExpiration,
    SupportLeaseProposal,
    SupportLeaseReplayReceipt,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
    SupportLeaseStatus,
    SupportLeaseSwitch,
    _LEGACY_MEMBERSHIP_EPOCH_CURSORS,
    _LEGACY_SUPPORT_REPLAY_CURSORS,
    _MEMBERSHIP_EPOCH_STATE_ISSUANCE,
    _MEMBERSHIP_SNAPSHOT_ISSUANCE,
    _MembershipEpochCursor,
    _SUPPORT_LEASE_ISSUANCE,
    _SUPPORT_LEASE_REPLAY_STATE_ISSUANCE,
    _SUPPORT_REVOCATION_ISSUANCE,
    _SupportLeaseReplayCursor,
    _canonical_support_replay_receipts,
    _membership_epoch_state_snapshot,
    _membership_snapshot,
    _support_lease_snapshot,
    _support_replay_root,
    _support_replay_state_snapshot,
    _support_revocation_snapshot,
    _validate_equivocation_finding,
    _validate_membership_epoch_state_shape,
    _validate_membership_snapshot_shape,
    _validate_support_evaluation,
    _validate_support_lease_shape,
    _validate_support_proposal,
    _validate_support_replay_receipt,
    _validate_support_replay_state_shape,
    _validate_support_revocation_shape,
    eligible_membership_epoch_state_fingerprint,
    eligible_membership_epoch_state_payload,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_payload,
    support_lease_fingerprint,
    support_lease_payload,
    support_lease_proposal_fingerprint,
    support_lease_proposal_payload,
    support_lease_replay_receipt_payload,
    support_lease_replay_state_fingerprint,
    support_lease_replay_state_payload,
    support_lease_revocation_fingerprint,
    support_lease_revocation_payload,
)


def issue_eligible_principal_snapshot(
    verifications: Sequence[PrincipalVerification],
    *,
    snapshot_id: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    issuer_id: str,
    membership_method: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    expires_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> tuple[EligiblePrincipalSnapshot, EligibleMembershipEpochState]:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "eligible membership issuance requires governance authority"
        )
    normalized = _normalized_bindings(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        field_name="eligible membership",
    )
    issued = require_commit_step(issued_at_step, "eligible membership issued_at_step")
    expires = require_commit_step(
        expires_at_step,
        "eligible membership expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("eligible membership expiry must be after issuance")

    by_cluster: dict[str, list[EligiblePrincipal]] = defaultdict(list)
    seen_principals: set[str] = set()
    seen_verifications: set[str] = set()
    for verification in tuple(verifications):
        if type(verification) is not PrincipalVerification:
            raise GovernanceError(
                "eligible membership requires canonical principal verifications"
            )
        if not principal_verification_is_authoritative(verification):
            raise GovernanceError(
                "eligible membership contains a forged principal verification"
            )
        if not principal_verification_matches(
            verification,
            profile=normalized["profile"],
            assurance=normalized["assurance"],
            manifest_root=normalized["manifest_root"],
            commit_policy_root=normalized["commit_policy_root"],
            protocol_id=normalized["protocol_id"],
            run_id=normalized["run_id"],
            target=normalized["target"],
            epoch=normalized["epoch"],
            principal_id=verification.principal_id,
            current_step=issued,
        ):
            raise GovernanceError(
                "eligible principal verification is stale or has a binding mismatch"
            )
        if verification.expires_at_step < expires:
            raise GovernanceError(
                "eligible membership cannot outlive a principal verification"
            )
        fingerprint = principal_verification_fingerprint(verification)
        if verification.principal_id in seen_principals:
            raise GovernanceError("eligible membership repeats a principal")
        if fingerprint in seen_verifications:
            raise GovernanceError("eligible membership repeats a verification")
        seen_principals.add(verification.principal_id)
        seen_verifications.add(fingerprint)
        by_cluster[verification.cluster_id].append(
            EligiblePrincipal(
                principal_id=verification.principal_id,
                principal_verification_fingerprint=fingerprint,
                verified_issuer_id=verification.verified_issuer_id,
                verified_method=verification.verified_method,
                failure_domain=verification.failure_domain,
            )
        )

    clusters = tuple(
        EligiblePrincipalCluster(cluster_id=cluster_id, principals=tuple(principals))
        for cluster_id, principals in sorted(by_cluster.items())
    )
    membership_root = _membership_root(
        profile=normalized["profile"],
        assurance=normalized["assurance"],
        manifest_root=normalized["manifest_root"],
        commit_policy_root=normalized["commit_policy_root"],
        protocol_id=normalized["protocol_id"],
        run_id=normalized["run_id"],
        target=normalized["target"],
        epoch=normalized["epoch"],
        clusters=clusters,
    )
    snapshot = EligiblePrincipalSnapshot(
        snapshot_id=require_commit_text(snapshot_id, "eligible membership snapshot_id"),
        profile=normalized["profile"],
        assurance=normalized["assurance"],
        manifest_root=normalized["manifest_root"],
        commit_policy_root=normalized["commit_policy_root"],
        protocol_id=normalized["protocol_id"],
        run_id=normalized["run_id"],
        target=normalized["target"],
        epoch=normalized["epoch"],
        eligible_clusters=clusters,
        membership_root=membership_root,
        issuer_id=require_commit_text(issuer_id, "eligible membership issuer_id"),
        membership_method=require_commit_text(
            membership_method,
            "eligible membership method",
        ),
        authority=authority,
        issued_at_step=issued,
        expires_at_step=expires,
        provenance=require_commit_text(provenance, "eligible membership provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "eligible membership trace_event_id",
        ),
    )
    snapshot_fingerprint = _membership_snapshot(snapshot)
    authority_key = _membership_epoch_authority_key(snapshot)
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        cursor = registry.get(_LEGACY_MEMBERSHIP_EPOCH_CURSORS, authority_key)
        if cursor is not None:
            if cursor.request_fingerprint != snapshot_fingerprint:
                raise GovernanceError(
                    "eligible membership epoch already has a conflicting immutable snapshot"
                )
            existing_snapshot = cursor.snapshot
            existing_state = cursor.state
            if not (
                type(existing_snapshot) is EligiblePrincipalSnapshot
                and type(existing_state) is EligibleMembershipEpochState
                and eligible_principal_snapshot_is_authoritative(existing_snapshot)
                and eligible_membership_epoch_state_is_current(existing_state)
            ):
                raise GovernanceError(
                    "eligible membership epoch authority exists but its current state is unavailable"
                )
            return existing_snapshot, existing_state

        cursor = _MembershipEpochCursor(
            authority_key=authority_key,
            request_fingerprint=snapshot_fingerprint,
        )
        object.__setattr__(snapshot, "_epoch_cursor", cursor)
        object.__setattr__(
            snapshot,
            "_issuance",
            (_MEMBERSHIP_SNAPSHOT_ISSUANCE, snapshot_fingerprint),
        )
        state = EligibleMembershipEpochState(
            authority_key=authority_key,
            profile=snapshot.profile,
            assurance=snapshot.assurance,
            manifest_root=snapshot.manifest_root,
            commit_policy_root=snapshot.commit_policy_root,
            protocol_id=snapshot.protocol_id,
            run_id=snapshot.run_id,
            target=snapshot.target,
            epoch=snapshot.epoch,
            snapshot_id=snapshot.snapshot_id,
            snapshot_fingerprint=snapshot_fingerprint,
            membership_root=snapshot.membership_root,
            issuer_id=snapshot.issuer_id,
            membership_method=snapshot.membership_method,
            authority=snapshot.authority,
            issued_at_step=snapshot.issued_at_step,
            expires_at_step=snapshot.expires_at_step,
            provenance=snapshot.provenance,
            trace_event_id=snapshot.trace_event_id,
        )
        object.__setattr__(state, "_cursor", cursor)
        object.__setattr__(
            state,
            "_issuance",
            (
                _MEMBERSHIP_EPOCH_STATE_ISSUANCE,
                _membership_epoch_state_snapshot(state),
            ),
        )
        cursor.snapshot = snapshot
        cursor.state = state
        registry.set(_LEGACY_MEMBERSHIP_EPOCH_CURSORS, authority_key, cursor)
        return snapshot, state


def eligible_principal_snapshot_is_authoritative(snapshot: object) -> bool:
    if type(snapshot) is not EligiblePrincipalSnapshot:
        return False
    try:
        _validate_membership_snapshot_shape(snapshot)
        issuance = snapshot._issuance
        cursor = snapshot._epoch_cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _MEMBERSHIP_SNAPSHOT_ISSUANCE
            and issuance[1] == _membership_snapshot(snapshot)
            and type(cursor) is _MembershipEpochCursor
            and cursor.authority_key == _membership_epoch_authority_key(snapshot)
        )
    except Exception:
        return False


def eligible_membership_epoch_state_is_authoritative(state: object) -> bool:
    if type(state) is not EligibleMembershipEpochState:
        return False
    try:
        _validate_membership_epoch_state_shape(state)
        issuance = state._issuance
        cursor = state._cursor
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _MEMBERSHIP_EPOCH_STATE_ISSUANCE
            and issuance[1] == _membership_epoch_state_snapshot(state)
            and type(cursor) is _MembershipEpochCursor
            and cursor.authority_key == state.authority_key
        )
    except Exception:
        return False


def eligible_membership_epoch_state_is_current(state: object) -> bool:
    if not eligible_membership_epoch_state_is_authoritative(state):
        return False
    assert type(state) is EligibleMembershipEpochState
    cursor = state._cursor
    assert type(cursor) is _MembershipEpochCursor
    try:
        with cursor.lock:
            return cursor.state is state
    except Exception:
        return False


def eligible_principal_snapshot_matches(
    snapshot: EligiblePrincipalSnapshot | None,
    *,
    epoch_state: EligibleMembershipEpochState | None,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    current_step: int,
) -> bool:
    try:
        expected = _normalized_bindings(
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=commit_policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            field_name="expected membership",
        )
        current = require_commit_step(current_step, "membership current_step")
        return bool(
            eligible_principal_snapshot_is_authoritative(snapshot)
            and snapshot is not None
            and eligible_membership_epoch_state_is_current(epoch_state)
            and epoch_state is not None
            and _record_bindings_equal(snapshot, expected)
            and _record_bindings_equal(epoch_state, expected)
            and epoch_state.snapshot_fingerprint == _membership_snapshot(snapshot)
            and epoch_state.membership_root == snapshot.membership_root
            and epoch_state.snapshot_id == snapshot.snapshot_id
            and epoch_state.issued_at_step == snapshot.issued_at_step
            and epoch_state.expires_at_step == snapshot.expires_at_step
            and snapshot.issued_at_step <= current < snapshot.expires_at_step
        )
    except GovernanceError:
        return False


def _membership_contains_principal(
    snapshot: EligiblePrincipalSnapshot,
    *,
    principal_id: str,
    cluster_id: str,
    verification_fingerprint: str,
) -> bool:
    return any(
        cluster.cluster_id == cluster_id
        and any(
            principal.principal_id == principal_id
            and principal.principal_verification_fingerprint == verification_fingerprint
            for principal in cluster.principals
        )
        for cluster in snapshot.eligible_clusters
    )


for _name in (
    "issue_eligible_principal_snapshot",
    "eligible_principal_snapshot_is_authoritative",
    "eligible_membership_epoch_state_is_authoritative",
    "eligible_membership_epoch_state_is_current",
    "eligible_principal_snapshot_matches",
):
    globals()[_name].__module__ = "pheroos.governance.support_lease"
del _name
