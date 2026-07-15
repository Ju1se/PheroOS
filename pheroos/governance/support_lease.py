from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    ceil_scaled_count,
    checked_add,
    commit_payload_fingerprint,
    require_scaled_integer,
    scaled_ratio,
)
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
    principal_verification_is_authoritative,
    principal_verification_matches,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
    SupportLeasePolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


_MEMBERSHIP_SNAPSHOT_ISSUANCE = object()
_MEMBERSHIP_EPOCH_STATE_ISSUANCE = object()
_SUPPORT_LEASE_ISSUANCE = object()
_SUPPORT_LEASE_REPLAY_STATE_ISSUANCE = object()
_SUPPORT_REVOCATION_ISSUANCE = object()


class _MembershipEpochCursor:
    __slots__ = (
        "authority_key",
        "request_fingerprint",
        "snapshot",
        "state",
        "lock",
        "__weakref__",
    )

    def __init__(self, *, authority_key: str, request_fingerprint: str) -> None:
        self.authority_key = authority_key
        self.request_fingerprint = request_fingerprint
        self.snapshot: EligiblePrincipalSnapshot | None = None
        self.state: EligibleMembershipEpochState | None = None
        self.lock = RLock()


class _SupportLeaseReplayCursor:
    __slots__ = (
        "authority_key",
        "base_fingerprint",
        "current_state_fingerprint",
        "current_state",
        "leases_by_fingerprint",
        "transitions",
        "lock",
        "__weakref__",
    )

    def __init__(self, *, authority_key: str, base_fingerprint: str) -> None:
        self.authority_key = authority_key
        self.base_fingerprint = base_fingerprint
        self.current_state_fingerprint = ""
        self.current_state: SupportLeaseReplayState | None = None
        self.leases_by_fingerprint: dict[str, SupportLease] = {}
        self.transitions: dict[
            str,
            tuple[str, SupportLease, SupportLeaseReplayState],
        ] = {}
        self.lock = RLock()


_MEMBERSHIP_EPOCH_REGISTRY_LOCK = RLock()
_MEMBERSHIP_EPOCH_CURSORS: dict[str, _MembershipEpochCursor] = {}
_SUPPORT_REPLAY_REGISTRY_LOCK = RLock()
_SUPPORT_REPLAY_CURSORS: dict[str, _SupportLeaseReplayCursor] = {}


class SupportLeaseStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    EQUIVOCATED = "equivocated"


@dataclass(frozen=True)
class EligiblePrincipal:
    principal_id: str
    principal_verification_fingerprint: str
    verified_issuer_id: str
    verified_method: str
    failure_domain: str

    def __post_init__(self) -> None:
        _validate_eligible_principal(self)


@dataclass(frozen=True)
class EligiblePrincipalCluster:
    cluster_id: str
    principals: tuple[EligiblePrincipal, ...]

    def __post_init__(self) -> None:
        normalized = tuple(self.principals)
        if not normalized or any(type(item) is not EligiblePrincipal for item in normalized):
            raise GovernanceError(
                "eligible principal cluster requires canonical principal records"
            )
        normalized = tuple(
            sorted(
                normalized,
                key=lambda item: (
                    item.principal_id,
                    item.principal_verification_fingerprint,
                ),
            )
        )
        principal_ids = tuple(item.principal_id for item in normalized)
        fingerprints = tuple(
            item.principal_verification_fingerprint for item in normalized
        )
        if len(principal_ids) != len(set(principal_ids)):
            raise GovernanceError(
                "eligible principal cluster contains a duplicate principal"
            )
        if len(fingerprints) != len(set(fingerprints)):
            raise GovernanceError(
                "eligible principal cluster contains a duplicate verification"
            )
        object.__setattr__(self, "principals", normalized)
        require_commit_text(self.cluster_id, "eligible principal cluster_id")


@dataclass(frozen=True)
class EligibleMembershipEpochState:
    authority_key: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    snapshot_id: str
    snapshot_fingerprint: str
    membership_root: str
    issuer_id: str
    membership_method: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_membership_epoch_state_shape(self)


@dataclass(frozen=True)
class EligiblePrincipalSnapshot:
    snapshot_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    eligible_clusters: tuple[EligiblePrincipalCluster, ...]
    membership_root: str
    issuer_id: str
    membership_method: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _epoch_cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        normalized = tuple(self.eligible_clusters)
        if any(type(item) is not EligiblePrincipalCluster for item in normalized):
            raise GovernanceError(
                "eligible membership requires canonical cluster records"
            )
        normalized = tuple(sorted(normalized, key=lambda item: item.cluster_id))
        cluster_ids = tuple(item.cluster_id for item in normalized)
        if len(cluster_ids) != len(set(cluster_ids)):
            raise GovernanceError("eligible membership contains a duplicate cluster")
        all_principals = tuple(
            principal.principal_id
            for cluster in normalized
            for principal in cluster.principals
        )
        if len(all_principals) != len(set(all_principals)):
            raise GovernanceError(
                "an eligible principal cannot belong to multiple clusters"
            )
        object.__setattr__(self, "eligible_clusters", normalized)
        _validate_membership_snapshot_shape(self)


@dataclass(frozen=True)
class SupportLeaseProposal:
    proposal_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int
    principal_id: str
    positive_observation_fingerprints: tuple[str, ...]
    nonce: str
    proposed_at_step: int
    provenance: str
    trace_event_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "positive_observation_fingerprints",
            _canonical_fingerprints(
                self.positive_observation_fingerprints,
                "support lease proposal positive observation fingerprints",
            ),
        )
        _validate_support_proposal(self)


@dataclass(frozen=True)
class SupportLeaseReplayReceipt:
    replay_receipt_fingerprint: str
    lease_fingerprint: str
    lease_id: str
    proposal_fingerprint: str
    nonce: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int
    principal_id: str
    principal_cluster_id: str
    membership_root: str
    membership_epoch_state_fingerprint: str
    issued_at_step: int
    expires_at_step: int

    def __post_init__(self) -> None:
        _validate_support_replay_receipt(self)


@dataclass(frozen=True)
class SupportLeaseReplayState:
    authority_key: str
    profile: str
    protocol_id: str
    issuer_id: str
    authority: AuthorityLevel
    revision: int
    receipts: tuple[SupportLeaseReplayReceipt, ...]
    replay_root: str
    previous_state_fingerprint: str
    initialized_at_step: int
    last_issued_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "receipts",
            _canonical_support_replay_receipts(self.receipts),
        )
        _validate_support_replay_state_shape(self)


@dataclass(frozen=True)
class SupportLease:
    lease_id: str
    proposal_fingerprint: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int
    principal_id: str
    principal_cluster_id: str
    principal_verification_fingerprint: str
    membership_root: str
    membership_epoch_state_fingerprint: str
    positive_observation_fingerprints: tuple[str, ...]
    prior_lease_fingerprint: str
    nonce: str
    replay_authority_key: str
    replay_receipt_fingerprint: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    proposal_provenance: str
    proposal_trace_event_id: str
    issuance_provenance: str
    issuance_trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _replay_cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "positive_observation_fingerprints",
            _canonical_fingerprints(
                self.positive_observation_fingerprints,
                "support lease positive observation fingerprints",
            ),
        )
        _validate_support_lease_shape(self)


@dataclass(frozen=True)
class SupportLeaseRevocation:
    revocation_id: str
    lease_fingerprint: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int
    principal_id: str
    principal_cluster_id: str
    reason_codes: tuple[str, ...]
    issuer_id: str
    authority: AuthorityLevel
    revoked_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason_codes",
            require_commit_labels(
                self.reason_codes,
                "support lease revocation reason_codes",
            ),
        )
        _validate_support_revocation_shape(self)


@dataclass(frozen=True)
class SupportLeaseExpiration:
    lease_fingerprint: str
    expired_at_step: int

    def __post_init__(self) -> None:
        require_commit_fingerprint(
            self.lease_fingerprint,
            "support lease expiration lease_fingerprint",
        )
        require_commit_step(
            self.expired_at_step,
            "support lease expiration expired_at_step",
        )


@dataclass(frozen=True)
class SupportLeaseSwitch:
    revocation: SupportLeaseRevocation
    lease: SupportLease

    def __post_init__(self) -> None:
        if (
            type(self.revocation) is not SupportLeaseRevocation
            or type(self.lease) is not SupportLease
        ):
            raise GovernanceError(
                "support lease switch requires canonical lifecycle records"
            )
        if self.lease.prior_lease_fingerprint != self.revocation.lease_fingerprint:
            raise GovernanceError("support lease switch lineage is inconsistent")
        if self.revocation.revoked_at_step != self.lease.issued_at_step:
            raise GovernanceError(
                "support lease switch must revoke before issuing at one logical step"
            )


@dataclass(frozen=True)
class SupportEquivocationFinding:
    finding_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    principal_cluster_id: str
    conflicting_candidates: tuple[str, ...]
    conflicting_lease_fingerprints: tuple[str, ...]
    first_overlap_step: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "conflicting_candidates",
            require_commit_labels(
                self.conflicting_candidates,
                "support equivocation candidates",
            ),
        )
        object.__setattr__(
            self,
            "conflicting_lease_fingerprints",
            _canonical_fingerprints(
                self.conflicting_lease_fingerprints,
                "support equivocation lease fingerprints",
            ),
        )
        _validate_equivocation_finding(self)


@dataclass(frozen=True)
class SupportLeaseEvaluation:
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int
    current_step: int
    membership_root: str
    membership_epoch_state_fingerprint: str
    support_replay_scope_root: str
    eligible_cluster_count: int
    active_support_cluster_count: int
    support_ratio_ppm: int
    policy_support_threshold_clusters: int
    policy_support_met: bool
    active_support_clusters: tuple[str, ...]
    included_lease_fingerprints: tuple[str, ...]
    excluded_lease_fingerprints: tuple[str, ...]
    equivocation_findings: tuple[SupportEquivocationFinding, ...]
    lease_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "active_support_clusters",
            require_commit_labels(
                self.active_support_clusters,
                "support evaluation active clusters",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "included_lease_fingerprints",
            _canonical_fingerprints(
                self.included_lease_fingerprints,
                "support evaluation included leases",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "excluded_lease_fingerprints",
            _canonical_fingerprints(
                self.excluded_lease_fingerprints,
                "support evaluation excluded leases",
                allow_empty=True,
            ),
        )
        if any(
            type(item) is not SupportEquivocationFinding
            for item in self.equivocation_findings
        ):
            raise GovernanceError(
                "support evaluation findings must use canonical records"
            )
        object.__setattr__(
            self,
            "equivocation_findings",
            tuple(
                sorted(
                    self.equivocation_findings,
                    key=lambda item: item.principal_cluster_id,
                )
            ),
        )
        _validate_support_evaluation(self)


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
        raise GovernanceError("eligible membership issuance requires governance authority")
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
    with _MEMBERSHIP_EPOCH_REGISTRY_LOCK:
        cursor = _MEMBERSHIP_EPOCH_CURSORS.get(authority_key)
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
        _MEMBERSHIP_EPOCH_CURSORS[authority_key] = cursor
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


def eligible_membership_epoch_state_payload(
    state: EligibleMembershipEpochState,
) -> dict[str, object]:
    if type(state) is not EligibleMembershipEpochState:
        raise GovernanceError("membership epoch state must use the canonical record")
    _validate_membership_epoch_state_shape(state)
    return {
        "assurance": state.assurance,
        "authority": state.authority,
        "authority_key": state.authority_key,
        "commit_policy_root": state.commit_policy_root,
        "epoch": state.epoch,
        "expires_at_step": state.expires_at_step,
        "issued_at_step": state.issued_at_step,
        "issuer_id": state.issuer_id,
        "manifest_root": state.manifest_root,
        "membership_method": state.membership_method,
        "membership_root": state.membership_root,
        "profile": state.profile,
        "protocol_id": state.protocol_id,
        "provenance": state.provenance,
        "run_id": state.run_id,
        "snapshot_fingerprint": state.snapshot_fingerprint,
        "snapshot_id": state.snapshot_id,
        "target": state.target,
        "trace_event_id": state.trace_event_id,
    }


def eligible_membership_epoch_state_fingerprint(
    state: EligibleMembershipEpochState,
) -> str:
    return _membership_epoch_state_snapshot(state)


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


def eligible_principal_snapshot_payload(
    snapshot: EligiblePrincipalSnapshot,
) -> dict[str, object]:
    if type(snapshot) is not EligiblePrincipalSnapshot:
        raise GovernanceError("membership snapshot must use the canonical record")
    _validate_membership_snapshot_shape(snapshot)
    return {
        "assurance": snapshot.assurance,
        "authority": snapshot.authority,
        "commit_policy_root": snapshot.commit_policy_root,
        "eligible_clusters": tuple(
            _eligible_cluster_payload(cluster) for cluster in snapshot.eligible_clusters
        ),
        "epoch": snapshot.epoch,
        "expires_at_step": snapshot.expires_at_step,
        "issued_at_step": snapshot.issued_at_step,
        "issuer_id": snapshot.issuer_id,
        "manifest_root": snapshot.manifest_root,
        "membership_method": snapshot.membership_method,
        "membership_root": snapshot.membership_root,
        "profile": snapshot.profile,
        "protocol_id": snapshot.protocol_id,
        "provenance": snapshot.provenance,
        "run_id": snapshot.run_id,
        "snapshot_id": snapshot.snapshot_id,
        "target": snapshot.target,
        "trace_event_id": snapshot.trace_event_id,
    }


def eligible_principal_snapshot_fingerprint(
    snapshot: EligiblePrincipalSnapshot,
) -> str:
    return _membership_snapshot(snapshot)


def support_lease_proposal_payload(
    proposal: SupportLeaseProposal,
) -> dict[str, object]:
    if type(proposal) is not SupportLeaseProposal:
        raise GovernanceError("support lease proposal must use the canonical record")
    _validate_support_proposal(proposal)
    return {
        "assurance": proposal.assurance,
        "candidate_id": proposal.candidate_id,
        "claim_fingerprint": proposal.claim_fingerprint,
        "commit_policy_root": proposal.commit_policy_root,
        "epoch": proposal.epoch,
        "manifest_root": proposal.manifest_root,
        "nonce": proposal.nonce,
        "positive_observation_fingerprints": (
            proposal.positive_observation_fingerprints
        ),
        "principal_id": proposal.principal_id,
        "profile": proposal.profile,
        "proposal_id": proposal.proposal_id,
        "proposed_at_step": proposal.proposed_at_step,
        "protocol_id": proposal.protocol_id,
        "provenance": proposal.provenance,
        "run_id": proposal.run_id,
        "target": proposal.target,
        "trace_event_id": proposal.trace_event_id,
    }


def support_lease_proposal_fingerprint(proposal: SupportLeaseProposal) -> str:
    return commit_payload_fingerprint(
        support_lease_proposal_payload(proposal),
        schema="pheroos-support-lease-proposal-v1",
        profile=proposal.profile,
    )


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
    with _SUPPORT_REPLAY_REGISTRY_LOCK:
        cursor = _SUPPORT_REPLAY_CURSORS.get(authority_key)
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
        cursor.current_state_fingerprint = support_lease_replay_state_fingerprint(
            state
        )
        cursor.current_state = state
        _SUPPORT_REPLAY_CURSORS[authority_key] = cursor
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
                and
                cursor.current_state_fingerprint
                == support_lease_replay_state_fingerprint(state)
            )
    except Exception:
        return False


def support_lease_replay_receipt_payload(
    receipt: SupportLeaseReplayReceipt,
) -> dict[str, object]:
    if type(receipt) is not SupportLeaseReplayReceipt:
        raise GovernanceError("support replay receipt must use the canonical record")
    _validate_support_replay_receipt(receipt)
    return {
        "assurance": receipt.assurance,
        "candidate_id": receipt.candidate_id,
        "claim_fingerprint": receipt.claim_fingerprint,
        "commit_policy_root": receipt.commit_policy_root,
        "epoch": receipt.epoch,
        "expires_at_step": receipt.expires_at_step,
        "issued_at_step": receipt.issued_at_step,
        "lease_fingerprint": receipt.lease_fingerprint,
        "lease_id": receipt.lease_id,
        "manifest_root": receipt.manifest_root,
        "membership_epoch_state_fingerprint": (
            receipt.membership_epoch_state_fingerprint
        ),
        "membership_root": receipt.membership_root,
        "nonce": receipt.nonce,
        "principal_cluster_id": receipt.principal_cluster_id,
        "principal_id": receipt.principal_id,
        "profile": receipt.profile,
        "proposal_fingerprint": receipt.proposal_fingerprint,
        "protocol_id": receipt.protocol_id,
        "replay_receipt_fingerprint": receipt.replay_receipt_fingerprint,
        "run_id": receipt.run_id,
        "target": receipt.target,
    }


def support_lease_replay_state_payload(
    state: SupportLeaseReplayState,
) -> dict[str, object]:
    if type(state) is not SupportLeaseReplayState:
        raise GovernanceError("support replay state must use the canonical record")
    _validate_support_replay_state_shape(state)
    return {
        "authority": state.authority,
        "authority_key": state.authority_key,
        "initialized_at_step": state.initialized_at_step,
        "issuer_id": state.issuer_id,
        "last_issued_at_step": state.last_issued_at_step,
        "previous_state_fingerprint": state.previous_state_fingerprint,
        "profile": state.profile,
        "protocol_id": state.protocol_id,
        "provenance": state.provenance,
        "receipts": tuple(
            support_lease_replay_receipt_payload(receipt)
            for receipt in state.receipts
        ),
        "replay_root": state.replay_root,
        "revision": state.revision,
        "trace_event_id": state.trace_event_id,
    }


def support_lease_replay_state_fingerprint(
    state: SupportLeaseReplayState,
) -> str:
    return _support_replay_state_snapshot(state)


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
        current_step=current,
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
        current_step=current,
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
            current_step=current,
            polarity=ObservationPolarity.SUPPORT,
        ):
            raise GovernanceError(
                "support lease evidence is not authoritative, positive, fresh, and bound"
            )
        observation_fingerprints.append(
            verified_observation_fingerprint(observation)
        )
        observation_expiries.append(observation.expires_at_step)
    normalized_observations = _canonical_fingerprints(
        observation_fingerprints,
        "support lease evidence fingerprints",
    )
    if normalized_observations != proposal.positive_observation_fingerprints:
        raise GovernanceError(
            "support lease proposal evidence references do not match verified evidence"
        )

    expires = checked_add(current, lease_policy.lease_ttl_steps)
    if principal_verification.expires_at_step < expires:
        raise GovernanceError(
            "support lease TTL exceeds principal verification freshness"
        )
    if membership_snapshot.expires_at_step < expires:
        raise GovernanceError("support lease TTL exceeds membership freshness")
    if min(observation_expiries) < expires:
        raise GovernanceError("support lease TTL exceeds referenced evidence freshness")

    normalized_prior_lease_fingerprint = ""
    if (prior_lease is None) != (prior_revocation is None):
        raise GovernanceError(
            "support lease switch requires both prior lease and revocation"
        )
    if prior_lease is not None and prior_revocation is not None:
        if not support_lease_is_authoritative(prior_lease):
            raise GovernanceError("support lease switch prior lease is not authoritative")
        if not support_lease_revocation_matches(
            prior_revocation,
            lease=prior_lease,
            current_step=current,
        ):
            raise GovernanceError(
                "support lease switch revocation is forged or mismatched"
            )
        if prior_revocation.revoked_at_step != current:
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
            raise GovernanceError(
                "support lease switch requires a different candidate"
            )
        normalized_prior_lease_fingerprint = support_lease_fingerprint(prior_lease)

    proposal_fingerprint = support_lease_proposal_fingerprint(proposal)
    replay_collision = _support_replay_collision_by_keys(
        replay_state,
        lease_id=require_commit_text(lease_id, "support lease lease_id"),
        proposal_fingerprint=proposal_fingerprint,
        nonce=proposal.nonce,
    )
    if replay_collision is not None:
        cursor = replay_state._cursor
        if type(cursor) is not _SupportLeaseReplayCursor:
            raise GovernanceError("support lease replay cursor is invalid")
        stored = cursor.leases_by_fingerprint.get(
            replay_collision.lease_fingerprint
        )
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
            and stored.prior_lease_fingerprint
            == normalized_prior_lease_fingerprint
            and stored.issuer_id == normalized_issuer
            and stored.authority is authority
            and stored.proposal_provenance == proposal.provenance
            and stored.proposal_trace_event_id == proposal.trace_event_id
            and stored.issuance_provenance == issuance_provenance
            and stored.issuance_trace_event_id == issuance_trace_event_id
            and stored.issued_at_step <= current < stored.expires_at_step
        ):
            raise GovernanceError("support lease replay is a safety violation")
        return stored, current_replay_state

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
    replayed_from_history = _support_lease_replay_result(
        lease,
        prior_leases=tuple(prior_leases),
        current_step=current,
    )
    parent_state_fingerprint = support_lease_replay_state_fingerprint(replay_state)
    request_fingerprint = _support_lease_snapshot(lease)
    cursor = replay_state._cursor
    if type(cursor) is not _SupportLeaseReplayCursor:
        raise GovernanceError("support lease replay cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_state_fingerprint:
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
                raise GovernanceError(
                    "support lease replay result is no longer available"
                )
            raise GovernanceError(
                "support lease replay state is stale or would fork"
            )

        collision_receipt = _support_replay_collision_receipt(replay_state, lease)
        if collision_receipt is not None:
            stored = cursor.leases_by_fingerprint.get(
                collision_receipt.lease_fingerprint
            )
            if (
                stored is None
                or not support_lease_is_authoritative(stored)
                or _support_lease_replay_result(
                    lease,
                    prior_leases=(stored,),
                    current_step=current,
                )
                is not stored
            ):
                raise GovernanceError(
                    "support lease replay receipt conflicts with local authority state"
                )
            return stored, replay_state
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


def support_lease_payload(lease: SupportLease) -> dict[str, object]:
    if type(lease) is not SupportLease:
        raise GovernanceError("support lease must use the canonical record")
    _validate_support_lease_shape(lease)
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
        "positive_observation_fingerprints": (
            lease.positive_observation_fingerprints
        ),
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
        "replay_receipt_fingerprint": lease.replay_receipt_fingerprint,
        "run_id": lease.run_id,
        "target": lease.target,
    }


def support_lease_fingerprint(lease: SupportLease) -> str:
    return _support_lease_snapshot(lease)


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
        raise GovernanceError("support lease revocation requires an authoritative lease")
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
            and lease.issued_at_step <= revocation.revoked_at_step < lease.expires_at_step
            and revocation.revoked_at_step <= current
        )
    except GovernanceError:
        return False


def support_lease_revocation_payload(
    revocation: SupportLeaseRevocation,
) -> dict[str, object]:
    if type(revocation) is not SupportLeaseRevocation:
        raise GovernanceError("support revocation must use the canonical record")
    _validate_support_revocation_shape(revocation)
    return {
        "assurance": revocation.assurance,
        "authority": revocation.authority,
        "candidate_id": revocation.candidate_id,
        "claim_fingerprint": revocation.claim_fingerprint,
        "commit_policy_root": revocation.commit_policy_root,
        "epoch": revocation.epoch,
        "issuer_id": revocation.issuer_id,
        "lease_fingerprint": revocation.lease_fingerprint,
        "manifest_root": revocation.manifest_root,
        "principal_cluster_id": revocation.principal_cluster_id,
        "principal_id": revocation.principal_id,
        "profile": revocation.profile,
        "protocol_id": revocation.protocol_id,
        "provenance": revocation.provenance,
        "reason_codes": revocation.reason_codes,
        "revocation_id": revocation.revocation_id,
        "revoked_at_step": revocation.revoked_at_step,
        "run_id": revocation.run_id,
        "target": revocation.target,
        "trace_event_id": revocation.trace_event_id,
    }


def support_lease_revocation_fingerprint(
    revocation: SupportLeaseRevocation,
) -> str:
    return _support_revocation_snapshot(revocation)


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
        raise GovernanceError("support lease expiration requires an authoritative lease")
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
    if not support_lease_is_authoritative(lease):
        raise GovernanceError("support lease status requires an authoritative lease")
    current = require_commit_step(current_step, "support lease status current_step")
    conflicts = _canonical_fingerprints(
        equivocated_lease_fingerprints,
        "support lease status equivocated fingerprints",
        allow_empty=True,
    )
    fingerprint = support_lease_fingerprint(lease)
    if fingerprint in conflicts:
        return SupportLeaseStatus.EQUIVOCATED
    effective_revocation = _effective_revocation(
        lease,
        tuple(revocations),
        current_step=current,
    )
    if effective_revocation is not None:
        return SupportLeaseStatus.REVOKED
    if current >= lease.expires_at_step:
        return SupportLeaseStatus.EXPIRED
    if current < lease.issued_at_step:
        raise GovernanceError("support lease is not yet active")
    return SupportLeaseStatus.ACTIVE


def evaluate_support_leases(
    leases: Sequence[SupportLease],
    *,
    revocations: Sequence[SupportLeaseRevocation],
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    commit_policy: CollectiveCommitPolicy,
    candidate_id: str,
    claim_fingerprint: str,
    current_step: int,
) -> SupportLeaseEvaluation:
    if type(membership_snapshot) is not EligiblePrincipalSnapshot:
        raise GovernanceError("support evaluation requires a membership snapshot")
    current = require_commit_step(current_step, "support evaluation current_step")
    candidate = require_commit_text(candidate_id, "support evaluation candidate_id")
    claim = require_commit_fingerprint(
        claim_fingerprint,
        "support evaluation claim_fingerprint",
    )
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=membership_snapshot.profile,
        assurance=membership_snapshot.assurance,
        manifest_root=membership_snapshot.manifest_root,
        commit_policy_root=membership_snapshot.commit_policy_root,
        protocol_id=membership_snapshot.protocol_id,
        run_id=membership_snapshot.run_id,
        target=membership_snapshot.target,
        epoch=membership_snapshot.epoch,
        current_step=current,
    ):
        raise GovernanceError(
            "support evaluation membership is forged, stale, or mismatched"
        )
    if not support_lease_replay_state_is_current(replay_state):
        raise GovernanceError(
            "support evaluation requires the authoritative current replay state"
        )
    if (
        replay_state.profile != membership_snapshot.profile
        or replay_state.protocol_id != membership_snapshot.protocol_id
    ):
        raise GovernanceError("support evaluation replay authority binding mismatch")
    _validate_commit_policy_binding(commit_policy, membership_snapshot)
    policy = commit_policy.support_lease
    _validate_support_policy(policy)
    eligible_count = len(membership_snapshot.eligible_clusters)
    if eligible_count == 0:
        raise GovernanceError(
            "eligible membership is empty; support policy is incomplete"
        )

    normalized_leases = tuple(leases)
    membership_state_fingerprint = eligible_membership_epoch_state_fingerprint(
        membership_epoch_state
    )
    expected_receipts = tuple(
        receipt
        for receipt in replay_state.receipts
        if _support_replay_receipt_matches_scope(
            receipt,
            membership_snapshot=membership_snapshot,
            membership_epoch_state_fingerprint=membership_state_fingerprint,
        )
        and receipt.issued_at_step <= current
    )
    expected_lease_fingerprints = {
        receipt.lease_fingerprint for receipt in expected_receipts
    }
    claims_by_candidate: dict[str, str] = {}
    fingerprints: dict[str, SupportLease] = {}
    lease_ids: set[str] = set()
    nonces: set[str] = set()
    for lease in normalized_leases:
        if not support_lease_is_authoritative(lease):
            raise GovernanceError("support evaluation contains a forged lease")
        if not _same_commit_scope(lease, membership_snapshot):
            raise GovernanceError("support evaluation lease binding mismatch")
        if lease.membership_root != membership_snapshot.membership_root:
            raise GovernanceError("support evaluation lease membership root mismatch")
        if lease.membership_epoch_state_fingerprint != membership_state_fingerprint:
            raise GovernanceError(
                "support evaluation lease membership epoch state mismatch"
            )
        if lease.replay_authority_key != replay_state.authority_key:
            raise GovernanceError("support evaluation lease replay authority mismatch")
        existing_claim = claims_by_candidate.setdefault(
            lease.candidate_id,
            lease.claim_fingerprint,
        )
        if existing_claim != lease.claim_fingerprint:
            raise GovernanceError(
                "support evaluation detected one candidate bound to conflicting claims"
            )
        if not _membership_contains_principal(
            membership_snapshot,
            principal_id=lease.principal_id,
            cluster_id=lease.principal_cluster_id,
            verification_fingerprint=lease.principal_verification_fingerprint,
        ):
            raise GovernanceError("support evaluation lease principal is not eligible")
        fingerprint = support_lease_fingerprint(lease)
        if fingerprint in fingerprints or lease.lease_id in lease_ids:
            raise GovernanceError("support evaluation contains a duplicate lease")
        replay_key = f"{lease.principal_cluster_id}\x00{lease.nonce}"
        if replay_key in nonces:
            raise GovernanceError("support evaluation contains a replayed lease nonce")
        fingerprints[fingerprint] = lease
        lease_ids.add(lease.lease_id)
        nonces.add(replay_key)

    if set(fingerprints) != expected_lease_fingerprints:
        raise GovernanceError(
            "support evaluation lease set is incomplete or absent from the authoritative replay state"
        )

    revocations_by_lease = _validated_revocation_map(
        tuple(revocations),
        leases_by_fingerprint=fingerprints,
        current_step=current,
    )
    findings = _find_equivocations(
        normalized_leases,
        revocations_by_lease=revocations_by_lease,
    )
    equivocated = {
        fingerprint
        for finding in findings
        for fingerprint in finding.conflicting_lease_fingerprints
    }

    active_by_cluster: dict[str, list[str]] = defaultdict(list)
    excluded: set[str] = set()
    for fingerprint, lease in fingerprints.items():
        if lease.candidate_id != candidate or lease.claim_fingerprint != claim:
            continue
        status = support_lease_status(
            lease,
            current_step=current,
            revocations=tuple(revocations),
            equivocated_lease_fingerprints=tuple(equivocated),
        )
        if status is SupportLeaseStatus.ACTIVE:
            active_by_cluster[lease.principal_cluster_id].append(fingerprint)
        else:
            excluded.add(fingerprint)

    active_clusters = tuple(sorted(active_by_cluster))
    included = tuple(
        fingerprint
        for cluster_id in active_clusters
        for fingerprint in sorted(active_by_cluster[cluster_id])
    )
    active_count = len(active_clusters)
    ratio_ppm = scaled_ratio(active_count, eligible_count, scale=WEIGHT_SCALE)
    threshold = max(
        policy.minimum_support_clusters,
        ceil_scaled_count(
            eligible_count,
            policy.support_ratio_ppm,
            scale=WEIGHT_SCALE,
        ),
    )
    lease_root = commit_payload_fingerprint(
        {
            "candidate_id": candidate,
            "claim_fingerprint": claim,
            "commit_policy_root": membership_snapshot.commit_policy_root,
            "current_step": current,
            "epoch": membership_snapshot.epoch,
            "equivocation_finding_ids": tuple(
                finding.finding_id for finding in findings
            ),
            "excluded_lease_fingerprints": tuple(sorted(excluded | equivocated)),
            "included_lease_fingerprints": included,
            "membership_root": membership_snapshot.membership_root,
            "membership_epoch_state_fingerprint": membership_state_fingerprint,
            "run_id": membership_snapshot.run_id,
            "support_replay_scope_root": _support_replay_scope_root(
                expected_receipts,
                profile=membership_snapshot.profile,
            ),
            "target": membership_snapshot.target,
        },
        schema="pheroos-support-lease-evaluation-root-v1",
        profile=membership_snapshot.profile,
    )
    return SupportLeaseEvaluation(
        profile=membership_snapshot.profile,
        assurance=membership_snapshot.assurance,
        manifest_root=membership_snapshot.manifest_root,
        commit_policy_root=membership_snapshot.commit_policy_root,
        protocol_id=membership_snapshot.protocol_id,
        run_id=membership_snapshot.run_id,
        target=membership_snapshot.target,
        candidate_id=candidate,
        claim_fingerprint=claim,
        epoch=membership_snapshot.epoch,
        current_step=current,
        membership_root=membership_snapshot.membership_root,
        membership_epoch_state_fingerprint=membership_state_fingerprint,
        support_replay_scope_root=_support_replay_scope_root(
            expected_receipts,
            profile=membership_snapshot.profile,
        ),
        eligible_cluster_count=eligible_count,
        active_support_cluster_count=active_count,
        support_ratio_ppm=ratio_ppm,
        policy_support_threshold_clusters=threshold,
        policy_support_met=active_count >= threshold,
        active_support_clusters=active_clusters,
        included_lease_fingerprints=included,
        excluded_lease_fingerprints=tuple(sorted(excluded | equivocated)),
        equivocation_findings=findings,
        lease_root=lease_root,
    )


def _validate_eligible_principal(principal: EligiblePrincipal) -> None:
    for name in ("principal_id", "verified_issuer_id", "verified_method"):
        require_commit_text(
            getattr(principal, name),
            f"eligible principal {name}",
        )
    require_commit_fingerprint(
        principal.principal_verification_fingerprint,
        "eligible principal verification fingerprint",
    )
    if principal.failure_domain:
        require_commit_text(
            principal.failure_domain,
            "eligible principal failure_domain",
        )


def _validate_membership_snapshot_shape(snapshot: EligiblePrincipalSnapshot) -> None:
    _validate_bound_record(snapshot, "eligible membership")
    for name in (
        "snapshot_id",
        "issuer_id",
        "membership_method",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(snapshot, name), f"eligible membership {name}")
    if type(snapshot.authority) is not AuthorityLevel or not can_verify(
        snapshot.authority
    ):
        raise GovernanceError("eligible membership authority is invalid")
    issued = require_commit_step(
        snapshot.issued_at_step,
        "eligible membership issued_at_step",
    )
    expires = require_commit_step(
        snapshot.expires_at_step,
        "eligible membership expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("eligible membership expiry must be after issuance")
    expected_root = _membership_root(
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        protocol_id=snapshot.protocol_id,
        run_id=snapshot.run_id,
        target=snapshot.target,
        epoch=snapshot.epoch,
        clusters=snapshot.eligible_clusters,
    )
    require_commit_fingerprint(snapshot.membership_root, "membership root")
    if snapshot.membership_root != expected_root:
        raise GovernanceError("eligible membership root does not match its members")


def _validate_membership_epoch_state_shape(
    state: EligibleMembershipEpochState,
) -> None:
    _validate_bound_record(state, "eligible membership epoch state")
    for name in (
        "snapshot_id",
        "issuer_id",
        "membership_method",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(state, name),
            f"eligible membership epoch state {name}",
        )
    for name in (
        "authority_key",
        "snapshot_fingerprint",
        "membership_root",
    ):
        require_commit_fingerprint(
            getattr(state, name),
            f"eligible membership epoch state {name}",
        )
    if state.authority_key != _membership_epoch_authority_key(state):
        raise GovernanceError("eligible membership epoch authority key is invalid")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("eligible membership epoch authority is invalid")
    issued = require_commit_step(
        state.issued_at_step,
        "eligible membership epoch state issued_at_step",
    )
    expires = require_commit_step(
        state.expires_at_step,
        "eligible membership epoch state expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("eligible membership epoch state interval is invalid")


def _validate_support_proposal(proposal: SupportLeaseProposal) -> None:
    _validate_bound_record(proposal, "support lease proposal")
    for name in (
        "proposal_id",
        "candidate_id",
        "principal_id",
        "nonce",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(proposal, name), f"support lease proposal {name}")
    require_commit_fingerprint(
        proposal.claim_fingerprint,
        "support lease proposal claim_fingerprint",
    )
    _canonical_fingerprints(
        proposal.positive_observation_fingerprints,
        "support lease proposal positive observation fingerprints",
    )
    require_commit_step(
        proposal.proposed_at_step,
        "support lease proposal proposed_at_step",
    )


def _validate_support_lease_shape(lease: SupportLease) -> None:
    _validate_bound_record(lease, "support lease")
    for name in (
        "lease_id",
        "candidate_id",
        "principal_id",
        "principal_cluster_id",
        "nonce",
        "issuer_id",
        "proposal_provenance",
        "proposal_trace_event_id",
        "issuance_provenance",
        "issuance_trace_event_id",
    ):
        require_commit_text(getattr(lease, name), f"support lease {name}")
    for name in (
        "proposal_fingerprint",
        "claim_fingerprint",
        "principal_verification_fingerprint",
        "membership_root",
        "membership_epoch_state_fingerprint",
        "replay_authority_key",
        "replay_receipt_fingerprint",
    ):
        require_commit_fingerprint(getattr(lease, name), f"support lease {name}")
    if lease.prior_lease_fingerprint:
        require_commit_fingerprint(
            lease.prior_lease_fingerprint,
            "support lease prior_lease_fingerprint",
        )
    _canonical_fingerprints(
        lease.positive_observation_fingerprints,
        "support lease positive observation fingerprints",
    )
    if type(lease.authority) is not AuthorityLevel or not can_verify(lease.authority):
        raise GovernanceError("support lease authority is invalid")
    issued = require_commit_step(lease.issued_at_step, "support lease issued_at_step")
    expires = require_commit_step(
        lease.expires_at_step,
        "support lease expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("support lease expiry must be after issuance")


def _validate_support_revocation_shape(
    revocation: SupportLeaseRevocation,
) -> None:
    _validate_bound_record(revocation, "support lease revocation")
    for name in (
        "revocation_id",
        "candidate_id",
        "principal_id",
        "principal_cluster_id",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(revocation, name),
            f"support lease revocation {name}",
        )
    require_commit_fingerprint(
        revocation.lease_fingerprint,
        "support lease revocation lease_fingerprint",
    )
    require_commit_fingerprint(
        revocation.claim_fingerprint,
        "support lease revocation claim_fingerprint",
    )
    require_commit_labels(
        revocation.reason_codes,
        "support lease revocation reason_codes",
    )
    if type(revocation.authority) is not AuthorityLevel or not can_verify(
        revocation.authority
    ):
        raise GovernanceError("support lease revocation authority is invalid")
    require_commit_step(
        revocation.revoked_at_step,
        "support lease revocation revoked_at_step",
    )


def _validate_equivocation_finding(finding: SupportEquivocationFinding) -> None:
    _validate_bound_record(finding, "support equivocation finding")
    require_commit_text(
        finding.principal_cluster_id,
        "support equivocation cluster_id",
    )
    if len(finding.conflicting_candidates) < 2:
        raise GovernanceError(
            "support equivocation requires at least two conflicting candidates"
        )
    if len(finding.conflicting_lease_fingerprints) < 2:
        raise GovernanceError(
            "support equivocation requires at least two conflicting leases"
        )
    require_commit_step(
        finding.first_overlap_step,
        "support equivocation first_overlap_step",
    )
    expected = _equivocation_finding_id(
        profile=finding.profile,
        assurance=finding.assurance,
        manifest_root=finding.manifest_root,
        commit_policy_root=finding.commit_policy_root,
        protocol_id=finding.protocol_id,
        run_id=finding.run_id,
        target=finding.target,
        epoch=finding.epoch,
        cluster_id=finding.principal_cluster_id,
        candidates=finding.conflicting_candidates,
        lease_fingerprints=finding.conflicting_lease_fingerprints,
        first_overlap_step=finding.first_overlap_step,
    )
    require_commit_fingerprint(finding.finding_id, "support equivocation finding_id")
    if finding.finding_id != expected:
        raise GovernanceError("support equivocation finding is not deterministic")


def _validate_support_evaluation(evaluation: SupportLeaseEvaluation) -> None:
    _validate_bound_record(evaluation, "support evaluation")
    require_commit_text(evaluation.candidate_id, "support evaluation candidate_id")
    require_commit_fingerprint(
        evaluation.claim_fingerprint,
        "support evaluation claim_fingerprint",
    )
    require_commit_fingerprint(
        evaluation.membership_root,
        "support evaluation membership_root",
    )
    require_commit_fingerprint(
        evaluation.membership_epoch_state_fingerprint,
        "support evaluation membership_epoch_state_fingerprint",
    )
    require_commit_fingerprint(
        evaluation.support_replay_scope_root,
        "support evaluation support_replay_scope_root",
    )
    require_commit_fingerprint(evaluation.lease_root, "support evaluation lease_root")
    for name in (
        "current_step",
        "eligible_cluster_count",
        "active_support_cluster_count",
        "policy_support_threshold_clusters",
    ):
        require_commit_step(
            getattr(evaluation, name),
            f"support evaluation {name}",
        )
    require_scaled_integer(
        evaluation.support_ratio_ppm,
        "support evaluation support_ratio_ppm",
        maximum=WEIGHT_SCALE,
    )
    if type(evaluation.policy_support_met) is not bool:
        raise GovernanceError("support evaluation policy_support_met must be boolean")
    if evaluation.eligible_cluster_count <= 0:
        raise GovernanceError("support evaluation requires eligible clusters")
    if evaluation.active_support_cluster_count != len(
        evaluation.active_support_clusters
    ):
        raise GovernanceError("support evaluation cluster count mismatch")
    if evaluation.active_support_cluster_count > evaluation.eligible_cluster_count:
        raise GovernanceError("support evaluation exceeds eligible membership")
    expected_ratio = scaled_ratio(
        evaluation.active_support_cluster_count,
        evaluation.eligible_cluster_count,
        scale=WEIGHT_SCALE,
    )
    if evaluation.support_ratio_ppm != expected_ratio:
        raise GovernanceError("support evaluation ratio is not derived exactly")
    if evaluation.policy_support_met != (
        evaluation.active_support_cluster_count
        >= evaluation.policy_support_threshold_clusters
    ):
        raise GovernanceError("support evaluation threshold result mismatch")


def _validate_support_replay_receipt(
    receipt: SupportLeaseReplayReceipt,
) -> None:
    _validate_bound_record(receipt, "support replay receipt")
    for name in (
        "lease_id",
        "nonce",
        "candidate_id",
        "principal_id",
        "principal_cluster_id",
    ):
        require_commit_text(
            getattr(receipt, name),
            f"support replay receipt {name}",
        )
    for name in (
        "replay_receipt_fingerprint",
        "lease_fingerprint",
        "proposal_fingerprint",
        "claim_fingerprint",
        "membership_root",
        "membership_epoch_state_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(receipt, name),
            f"support replay receipt {name}",
        )
    issued = require_commit_step(
        receipt.issued_at_step,
        "support replay receipt issued_at_step",
    )
    expires = require_commit_step(
        receipt.expires_at_step,
        "support replay receipt expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("support replay receipt interval is invalid")


def _validate_support_replay_state_shape(
    state: SupportLeaseReplayState,
) -> None:
    profile = require_commit_profile(state.profile, "support replay state profile")
    protocol_id = require_commit_text(
        state.protocol_id,
        "support replay state protocol_id",
    )
    issuer_id = require_commit_text(state.issuer_id, "support replay state issuer_id")
    require_commit_fingerprint(state.authority_key, "support replay state authority_key")
    if state.authority_key != _support_replay_authority_key(
        profile=profile,
        protocol_id=protocol_id,
        issuer_id=issuer_id,
    ):
        raise GovernanceError("support replay state authority key is invalid")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("support replay state authority is invalid")
    revision = require_commit_step(state.revision, "support replay state revision")
    initialized = require_commit_step(
        state.initialized_at_step,
        "support replay state initialized_at_step",
    )
    last_issued = require_commit_step(
        state.last_issued_at_step,
        "support replay state last_issued_at_step",
    )
    if last_issued < initialized:
        raise GovernanceError("support replay state issuance step predates initialization")
    require_commit_text(state.provenance, "support replay state provenance")
    require_commit_text(state.trace_event_id, "support replay state trace_event_id")
    receipts = _canonical_support_replay_receipts(state.receipts)
    if receipts != state.receipts:
        raise GovernanceError("support replay state receipts are not canonical")
    if revision != len(receipts):
        raise GovernanceError("support replay state revision does not match receipts")
    for field_name in ("lease_id", "proposal_fingerprint", "nonce"):
        values = tuple(getattr(receipt, field_name) for receipt in receipts)
        if len(values) != len(set(values)):
            raise GovernanceError(
                f"support replay state contains duplicate {field_name} receipts"
            )
    require_commit_fingerprint(state.replay_root, "support replay state replay_root")
    if state.replay_root != _support_replay_root(receipts, profile=profile):
        raise GovernanceError("support replay state root does not match its receipts")
    if revision == 0:
        if state.previous_state_fingerprint:
            raise GovernanceError("empty support replay state has a predecessor")
        if last_issued != initialized:
            raise GovernanceError("empty support replay state issuance step is invalid")
    else:
        require_commit_fingerprint(
            state.previous_state_fingerprint,
            "support replay state previous_state_fingerprint",
        )


def _validate_bound_record(record: object, field_name: str) -> None:
    profile = require_commit_profile(getattr(record, "profile"), f"{field_name} profile")
    assurance = require_commit_assurance(
        getattr(record, "assurance"),
        f"{field_name} assurance",
    )
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    require_commit_fingerprint(
        getattr(record, "manifest_root"),
        f"{field_name} manifest_root",
    )
    require_commit_fingerprint(
        getattr(record, "commit_policy_root"),
        f"{field_name} commit_policy_root",
    )
    for name in ("protocol_id", "run_id", "target"):
        require_commit_text(getattr(record, name), f"{field_name} {name}")
    require_commit_step(getattr(record, "epoch"), f"{field_name} epoch")


def _normalized_bindings(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    field_name: str,
) -> dict[str, object]:
    normalized_profile = require_commit_profile(profile, f"{field_name} profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        f"{field_name} assurance",
    )
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[
        normalized_assurance.value
    ]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    return {
        "profile": normalized_profile,
        "assurance": normalized_assurance,
        "manifest_root": require_commit_fingerprint(
            manifest_root,
            f"{field_name} manifest_root",
        ),
        "commit_policy_root": require_commit_fingerprint(
            commit_policy_root,
            f"{field_name} commit_policy_root",
        ),
        "protocol_id": require_commit_text(
            protocol_id,
            f"{field_name} protocol_id",
        ),
        "run_id": require_commit_text(run_id, f"{field_name} run_id"),
        "target": require_commit_text(target, f"{field_name} target"),
        "epoch": require_commit_step(epoch, f"{field_name} epoch"),
    }


def _record_bindings_equal(record: object, expected: dict[str, object]) -> bool:
    return all(getattr(record, name) == value for name, value in expected.items())


def _same_commit_scope(left: object, right: object) -> bool:
    return all(
        getattr(left, name) == getattr(right, name)
        for name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
            "target",
            "epoch",
        )
    )


def _validate_support_policy(policy: object) -> None:
    if type(policy) is not SupportLeasePolicy:
        raise GovernanceError("support policy must use the Protocol ABI record")
    if (
        policy.membership_mode != "verified_snapshot_v1"
        or policy.switch_mode != "revoke_then_issue_v1"
        or policy.equivocation_mode != "exclude_conflicts_v1"
        or policy.evidence_reference_required is not True
        or policy.cluster_verification_required is not True
    ):
        raise GovernanceError("support policy does not use normative v1 semantics")
    if (
        require_commit_step(
            policy.minimum_support_clusters,
            "support policy minimum_support_clusters",
        )
        <= 0
    ):
        raise GovernanceError("support policy minimum clusters must be positive")
    ratio = require_scaled_integer(
        policy.support_ratio_ppm,
        "support policy ratio",
        maximum=WEIGHT_SCALE,
    )
    if ratio <= 0:
        raise GovernanceError("support policy ratio must be positive")
    if require_commit_step(policy.lease_ttl_steps, "support policy lease TTL") <= 0:
        raise GovernanceError("support policy lease TTL must be positive")


def _validate_commit_policy_binding(
    policy: object,
    bound_record: object,
) -> None:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("support evaluation requires a collective commit policy")
    if policy.target != getattr(bound_record, "target"):
        raise GovernanceError("support policy target binding mismatch")
    if policy.assurance != getattr(bound_record, "assurance").value:
        raise GovernanceError("support policy assurance binding mismatch")
    observed_root = commit_policy_fingerprint(
        policy,
        profile=getattr(bound_record, "profile"),
    )
    if observed_root != getattr(bound_record, "commit_policy_root"):
        raise GovernanceError("support policy root binding mismatch")


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
            and principal.principal_verification_fingerprint
            == verification_fingerprint
            for principal in cluster.principals
        )
        for cluster in snapshot.eligible_clusters
    )


def _membership_epoch_authority_key(record: object) -> str:
    profile = require_commit_profile(
        getattr(record, "profile"),
        "membership epoch authority profile",
    )
    return commit_payload_fingerprint(
        {
            "assurance": require_commit_assurance(
                getattr(record, "assurance"),
                "membership epoch authority assurance",
            ),
            "commit_policy_root": require_commit_fingerprint(
                getattr(record, "commit_policy_root"),
                "membership epoch authority commit_policy_root",
            ),
            "epoch": require_commit_step(
                getattr(record, "epoch"),
                "membership epoch authority epoch",
            ),
            "manifest_root": require_commit_fingerprint(
                getattr(record, "manifest_root"),
                "membership epoch authority manifest_root",
            ),
            "protocol_id": require_commit_text(
                getattr(record, "protocol_id"),
                "membership epoch authority protocol_id",
            ),
            "run_id": require_commit_text(
                getattr(record, "run_id"),
                "membership epoch authority run_id",
            ),
            "target": require_commit_text(
                getattr(record, "target"),
                "membership epoch authority target",
            ),
        },
        schema="pheroos-eligible-membership-epoch-authority-key-v1",
        profile=profile,
    )


def _membership_epoch_state_snapshot(state: EligibleMembershipEpochState) -> str:
    return commit_payload_fingerprint(
        eligible_membership_epoch_state_payload(state),
        schema="pheroos-eligible-membership-epoch-state-v1",
        profile=state.profile,
    )


def _support_replay_authority_key(
    *,
    profile: str,
    protocol_id: str,
    issuer_id: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "issuer_id": issuer_id,
            "profile": profile,
            "protocol_id": protocol_id,
        },
        schema="pheroos-support-lease-replay-authority-key-v1",
        profile=profile,
    )


def _canonical_support_replay_receipts(
    receipts: Sequence[SupportLeaseReplayReceipt],
) -> tuple[SupportLeaseReplayReceipt, ...]:
    if isinstance(receipts, (str, bytes, bytearray)):
        raise GovernanceError("support replay receipts must be a sequence")
    normalized = tuple(receipts)
    if any(type(receipt) is not SupportLeaseReplayReceipt for receipt in normalized):
        raise GovernanceError("support replay state contains a non-canonical receipt")
    for receipt in normalized:
        _validate_support_replay_receipt(receipt)
    fingerprints = tuple(
        receipt.replay_receipt_fingerprint for receipt in normalized
    )
    if len(fingerprints) != len(set(fingerprints)):
        raise GovernanceError("support replay state contains a duplicate receipt")
    return tuple(
        sorted(normalized, key=lambda receipt: receipt.replay_receipt_fingerprint)
    )


def _support_replay_root(
    receipts: Sequence[SupportLeaseReplayReceipt],
    *,
    profile: str,
) -> str:
    canonical = _canonical_support_replay_receipts(receipts)
    return commit_payload_fingerprint(
        {
            "receipts": tuple(
                support_lease_replay_receipt_payload(receipt)
                for receipt in canonical
            )
        },
        schema="pheroos-support-lease-replay-root-v1",
        profile=profile,
    )


def _support_replay_state_snapshot(state: SupportLeaseReplayState) -> str:
    return commit_payload_fingerprint(
        support_lease_replay_state_payload(state),
        schema="pheroos-support-lease-replay-state-v1",
        profile=state.profile,
    )


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
        "positive_observation_fingerprints": (
            lease.positive_observation_fingerprints
        ),
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
        membership_epoch_state_fingerprint=(
            lease.membership_epoch_state_fingerprint
        ),
        issued_at_step=lease.issued_at_step,
        expires_at_step=lease.expires_at_step,
    )


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
        and receipt.replay_receipt_fingerprint
        == lease.replay_receipt_fingerprint
    ):
        raise GovernanceError("support lease replay is a safety violation")
    return receipt


def _advance_support_replay_state(
    state: SupportLeaseReplayState,
    lease: SupportLease,
    *,
    cursor: _SupportLeaseReplayCursor,
) -> SupportLeaseReplayState:
    if lease.issued_at_step < state.last_issued_at_step:
        raise GovernanceError("support replay state cannot move backward in logical time")
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
                support_lease_replay_receipt_payload(receipt)
                for receipt in canonical
            )
        },
        schema="pheroos-support-lease-scope-replay-root-v1",
        profile=profile,
    )


def _support_lease_replay_result(
    candidate: SupportLease,
    *,
    prior_leases: Sequence[SupportLease],
    current_step: int,
) -> SupportLease | None:
    if isinstance(prior_leases, (str, bytes, bytearray)):
        raise GovernanceError("prior support leases must be a sequence")
    current = require_commit_step(current_step, "support lease replay current_step")
    seen_lease_ids: set[str] = set()
    seen_proposals: set[str] = set()
    seen_nonces: set[str] = set()
    idempotent: SupportLease | None = None
    for prior in prior_leases:
        if not support_lease_is_authoritative(prior):
            raise GovernanceError("prior support lease is not authoritative")
        if (
            prior.lease_id in seen_lease_ids
            or prior.proposal_fingerprint in seen_proposals
            or prior.nonce in seen_nonces
        ):
            raise GovernanceError("prior support lease replay state contains a duplicate")
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
            and prior.nonce == candidate.nonce
            and prior.profile == candidate.profile
            and prior.assurance is candidate.assurance
            and prior.manifest_root == candidate.manifest_root
            and prior.commit_policy_root == candidate.commit_policy_root
            and prior.protocol_id == candidate.protocol_id
            and prior.run_id == candidate.run_id
            and prior.target == candidate.target
            and prior.candidate_id == candidate.candidate_id
            and prior.claim_fingerprint == candidate.claim_fingerprint
            and prior.epoch == candidate.epoch
            and prior.principal_id == candidate.principal_id
            and prior.principal_cluster_id == candidate.principal_cluster_id
            and prior.principal_verification_fingerprint
            == candidate.principal_verification_fingerprint
            and prior.membership_root == candidate.membership_root
            and prior.membership_epoch_state_fingerprint
            == candidate.membership_epoch_state_fingerprint
            and prior.positive_observation_fingerprints
            == candidate.positive_observation_fingerprints
            and prior.prior_lease_fingerprint == candidate.prior_lease_fingerprint
            and prior.replay_authority_key == candidate.replay_authority_key
            and prior.replay_receipt_fingerprint
            == candidate.replay_receipt_fingerprint
            and prior.issuer_id == candidate.issuer_id
            and prior.authority is candidate.authority
            and prior.proposal_provenance == candidate.proposal_provenance
            and prior.proposal_trace_event_id == candidate.proposal_trace_event_id
            and prior.issuance_provenance == candidate.issuance_provenance
            and prior.issuance_trace_event_id
            == candidate.issuance_trace_event_id
            and prior.issued_at_step <= current < prior.expires_at_step
        )
        if not exact_replay:
            raise GovernanceError("support lease replay is a safety violation")
        idempotent = prior
    return idempotent


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


def _validated_revocation_map(
    revocations: Sequence[SupportLeaseRevocation],
    *,
    leases_by_fingerprint: dict[str, SupportLease],
    current_step: int,
) -> dict[str, SupportLeaseRevocation]:
    result: dict[str, SupportLeaseRevocation] = {}
    revocation_ids: set[str] = set()
    for revocation in revocations:
        if not support_lease_revocation_is_authoritative(revocation):
            raise GovernanceError("support evaluation contains a forged revocation")
        if revocation.revocation_id in revocation_ids:
            raise GovernanceError("support evaluation repeats a revocation id")
        lease = leases_by_fingerprint.get(revocation.lease_fingerprint)
        if lease is None:
            raise GovernanceError("support evaluation contains an orphan revocation")
        if not support_lease_revocation_matches(
            revocation,
            lease=lease,
            current_step=max(current_step, revocation.revoked_at_step),
        ):
            raise GovernanceError("support evaluation revocation binding mismatch")
        if revocation.lease_fingerprint in result:
            raise GovernanceError("support lease has multiple revocations")
        revocation_ids.add(revocation.revocation_id)
        result[revocation.lease_fingerprint] = revocation
    return result


def _find_equivocations(
    leases: Sequence[SupportLease],
    *,
    revocations_by_lease: dict[str, SupportLeaseRevocation],
) -> tuple[SupportEquivocationFinding, ...]:
    by_cluster: dict[str, list[tuple[SupportLease, str, int]]] = defaultdict(list)
    for lease in leases:
        fingerprint = support_lease_fingerprint(lease)
        revocation = revocations_by_lease.get(fingerprint)
        end = (
            revocation.revoked_at_step
            if revocation is not None
            else lease.expires_at_step
        )
        by_cluster[lease.principal_cluster_id].append((lease, fingerprint, end))

    findings: list[SupportEquivocationFinding] = []
    for cluster_id, records in sorted(by_cluster.items()):
        conflicts: set[str] = set()
        candidates: set[str] = set()
        overlap_steps: list[int] = []
        for index, (left, left_fingerprint, left_end) in enumerate(records):
            for right, right_fingerprint, right_end in records[index + 1 :]:
                if left.candidate_id == right.candidate_id:
                    continue
                overlap_start = max(left.issued_at_step, right.issued_at_step)
                overlap_end = min(left_end, right_end)
                if overlap_start < overlap_end:
                    conflicts.update((left_fingerprint, right_fingerprint))
                    candidates.update((left.candidate_id, right.candidate_id))
                    overlap_steps.append(overlap_start)
        if not conflicts:
            continue
        prototype = records[0][0]
        normalized_candidates = require_commit_labels(
            tuple(candidates),
            "support equivocation candidates",
        )
        normalized_conflicts = _canonical_fingerprints(
            tuple(conflicts),
            "support equivocation lease fingerprints",
        )
        first_overlap = min(overlap_steps)
        finding_id = _equivocation_finding_id(
            profile=prototype.profile,
            assurance=prototype.assurance,
            manifest_root=prototype.manifest_root,
            commit_policy_root=prototype.commit_policy_root,
            protocol_id=prototype.protocol_id,
            run_id=prototype.run_id,
            target=prototype.target,
            epoch=prototype.epoch,
            cluster_id=cluster_id,
            candidates=normalized_candidates,
            lease_fingerprints=normalized_conflicts,
            first_overlap_step=first_overlap,
        )
        findings.append(
            SupportEquivocationFinding(
                finding_id=finding_id,
                profile=prototype.profile,
                assurance=prototype.assurance,
                manifest_root=prototype.manifest_root,
                commit_policy_root=prototype.commit_policy_root,
                protocol_id=prototype.protocol_id,
                run_id=prototype.run_id,
                target=prototype.target,
                epoch=prototype.epoch,
                principal_cluster_id=cluster_id,
                conflicting_candidates=normalized_candidates,
                conflicting_lease_fingerprints=normalized_conflicts,
                first_overlap_step=first_overlap,
            )
        )
    return tuple(findings)


def _equivocation_finding_id(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    cluster_id: str,
    candidates: Sequence[str],
    lease_fingerprints: Sequence[str],
    first_overlap_step: int,
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": assurance,
            "commit_policy_root": commit_policy_root,
            "conflicting_candidates": tuple(candidates),
            "conflicting_lease_fingerprints": tuple(lease_fingerprints),
            "epoch": epoch,
            "first_overlap_step": first_overlap_step,
            "manifest_root": manifest_root,
            "principal_cluster_id": cluster_id,
            "protocol_id": protocol_id,
            "run_id": run_id,
            "target": target,
        },
        schema="pheroos-support-equivocation-finding-v1",
        profile=profile,
    )


def _eligible_cluster_payload(cluster: EligiblePrincipalCluster) -> dict[str, object]:
    return {
        "cluster_id": cluster.cluster_id,
        "principals": tuple(
            {
                "failure_domain": principal.failure_domain,
                "principal_id": principal.principal_id,
                "principal_verification_fingerprint": (
                    principal.principal_verification_fingerprint
                ),
                "verified_issuer_id": principal.verified_issuer_id,
                "verified_method": principal.verified_method,
            }
            for principal in cluster.principals
        ),
    }


def _membership_root(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    clusters: Sequence[EligiblePrincipalCluster],
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": assurance,
            "commit_policy_root": commit_policy_root,
            "eligible_clusters": tuple(
                _eligible_cluster_payload(cluster) for cluster in clusters
            ),
            "epoch": epoch,
            "manifest_root": manifest_root,
            "protocol_id": protocol_id,
            "run_id": run_id,
            "target": target,
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=profile,
    )


def _membership_snapshot(snapshot: EligiblePrincipalSnapshot) -> str:
    return commit_payload_fingerprint(
        eligible_principal_snapshot_payload(snapshot),
        schema="pheroos-eligible-principal-snapshot-v1",
        profile=snapshot.profile,
    )


def _support_lease_snapshot(lease: SupportLease) -> str:
    return commit_payload_fingerprint(
        support_lease_payload(lease),
        schema="pheroos-support-lease-v1",
        profile=lease.profile,
    )


def _support_revocation_snapshot(revocation: SupportLeaseRevocation) -> str:
    return commit_payload_fingerprint(
        support_lease_revocation_payload(revocation),
        schema="pheroos-support-lease-revocation-v1",
        profile=revocation.profile,
    )


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    fingerprints = tuple(values)
    if not fingerprints and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    for value in fingerprints:
        require_commit_fingerprint(value, field_name)
    if len(fingerprints) != len(set(fingerprints)):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(fingerprints))


__all__ = [
    "EligibleMembershipEpochState",
    "EligiblePrincipal",
    "EligiblePrincipalCluster",
    "EligiblePrincipalSnapshot",
    "SupportEquivocationFinding",
    "SupportLease",
    "SupportLeaseEvaluation",
    "SupportLeaseExpiration",
    "SupportLeaseProposal",
    "SupportLeaseReplayReceipt",
    "SupportLeaseReplayState",
    "SupportLeaseRevocation",
    "SupportLeaseStatus",
    "SupportLeaseSwitch",
    "eligible_membership_epoch_state_fingerprint",
    "eligible_membership_epoch_state_is_authoritative",
    "eligible_membership_epoch_state_is_current",
    "eligible_membership_epoch_state_payload",
    "eligible_principal_snapshot_fingerprint",
    "eligible_principal_snapshot_is_authoritative",
    "eligible_principal_snapshot_matches",
    "eligible_principal_snapshot_payload",
    "evaluate_support_leases",
    "expire_support_lease",
    "issue_eligible_principal_snapshot",
    "issue_support_lease",
    "initialize_support_lease_replay_state",
    "revoke_support_lease",
    "support_lease_fingerprint",
    "support_lease_is_authoritative",
    "support_lease_payload",
    "support_lease_proposal_fingerprint",
    "support_lease_proposal_payload",
    "support_lease_replay_receipt_payload",
    "support_lease_replay_state_fingerprint",
    "support_lease_replay_state_is_authoritative",
    "support_lease_replay_state_is_current",
    "support_lease_replay_state_payload",
    "support_lease_revocation_fingerprint",
    "support_lease_revocation_is_authoritative",
    "support_lease_revocation_matches",
    "support_lease_revocation_payload",
    "support_lease_status",
    "switch_support_lease",
]
