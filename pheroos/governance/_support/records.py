from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._support.invariants import (
    _canonical_fingerprints,
    _eligible_cluster_payload,
    _equivocation_finding_id,
    _membership_epoch_authority_key,
    _membership_root,
    _support_replay_authority_key,
    _validate_bound_record,
    _validate_eligible_principal,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    commit_payload_fingerprint,
    require_scaled_integer,
    scaled_ratio,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CommitAssurance

_MEMBERSHIP_SNAPSHOT_ISSUANCE = object()
_MEMBERSHIP_EPOCH_STATE_ISSUANCE = object()
_SUPPORT_LEASE_ISSUANCE = object()
_SUPPORT_LEASE_REPLAY_STATE_ISSUANCE = object()
_SUPPORT_REVOCATION_ISSUANCE = object()
_LEGACY_MEMBERSHIP_EPOCH_CURSORS = "legacy.support.membership_epoch_cursors"
_LEGACY_SUPPORT_REPLAY_CURSORS = "legacy.support.replay_cursors"


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
        if not normalized or any(
            type(item) is not EligiblePrincipal for item in normalized
        ):
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
            support_lease_replay_receipt_payload(receipt) for receipt in state.receipts
        ),
        "replay_root": state.replay_root,
        "revision": state.revision,
        "trace_event_id": state.trace_event_id,
    }


def support_lease_replay_state_fingerprint(
    state: SupportLeaseReplayState,
) -> str:
    return _support_replay_state_snapshot(state)


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
        "replay_receipt_fingerprint": lease.replay_receipt_fingerprint,
        "run_id": lease.run_id,
        "target": lease.target,
    }


def support_lease_fingerprint(lease: SupportLease) -> str:
    return _support_lease_snapshot(lease)


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
    profile, revision, initialized, last_issued = _validate_support_replay_header(state)
    receipts = _validate_support_replay_receipts(state, revision=revision)
    _validate_support_replay_root(state, receipts=receipts, profile=profile)
    _validate_support_replay_predecessor(
        state,
        revision=revision,
        initialized=initialized,
        last_issued=last_issued,
    )


def _validate_support_replay_header(
    state: SupportLeaseReplayState,
) -> tuple[str, int, int, int]:
    profile = require_commit_profile(state.profile, "support replay state profile")
    protocol_id = require_commit_text(
        state.protocol_id,
        "support replay state protocol_id",
    )
    issuer_id = require_commit_text(state.issuer_id, "support replay state issuer_id")
    require_commit_fingerprint(
        state.authority_key, "support replay state authority_key"
    )
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
        raise GovernanceError(
            "support replay state issuance step predates initialization"
        )
    require_commit_text(state.provenance, "support replay state provenance")
    require_commit_text(state.trace_event_id, "support replay state trace_event_id")
    return profile, revision, initialized, last_issued


def _validate_support_replay_receipts(
    state: SupportLeaseReplayState,
    *,
    revision: int,
) -> tuple[SupportLeaseReplayReceipt, ...]:
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
    return receipts


def _validate_support_replay_root(
    state: SupportLeaseReplayState,
    *,
    receipts: Sequence[SupportLeaseReplayReceipt],
    profile: str,
) -> None:
    require_commit_fingerprint(state.replay_root, "support replay state replay_root")
    if state.replay_root != _support_replay_root(receipts, profile=profile):
        raise GovernanceError("support replay state root does not match its receipts")


def _validate_support_replay_predecessor(
    state: SupportLeaseReplayState,
    *,
    revision: int,
    initialized: int,
    last_issued: int,
) -> None:
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


def _membership_epoch_state_snapshot(state: EligibleMembershipEpochState) -> str:
    return commit_payload_fingerprint(
        eligible_membership_epoch_state_payload(state),
        schema="pheroos-eligible-membership-epoch-state-v1",
        profile=state.profile,
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
    fingerprints = tuple(receipt.replay_receipt_fingerprint for receipt in normalized)
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
                support_lease_replay_receipt_payload(receipt) for receipt in canonical
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


for _name in (
    "SupportLeaseStatus",
    "EligiblePrincipal",
    "EligiblePrincipalCluster",
    "EligibleMembershipEpochState",
    "EligiblePrincipalSnapshot",
    "SupportLeaseProposal",
    "SupportLeaseReplayReceipt",
    "SupportLeaseReplayState",
    "SupportLease",
    "SupportLeaseRevocation",
    "SupportLeaseExpiration",
    "SupportLeaseSwitch",
    "SupportEquivocationFinding",
    "SupportLeaseEvaluation",
    "eligible_membership_epoch_state_payload",
    "eligible_membership_epoch_state_fingerprint",
    "eligible_principal_snapshot_payload",
    "eligible_principal_snapshot_fingerprint",
    "support_lease_proposal_payload",
    "support_lease_proposal_fingerprint",
    "support_lease_replay_receipt_payload",
    "support_lease_replay_state_payload",
    "support_lease_replay_state_fingerprint",
    "support_lease_payload",
    "support_lease_fingerprint",
    "support_lease_revocation_payload",
    "support_lease_revocation_fingerprint",
):
    globals()[_name].__module__ = "pheroos.governance.support_lease"
del _name
