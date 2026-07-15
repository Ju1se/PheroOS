from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from threading import RLock
from typing import Any

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_bool,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.certificate import (
    EVIDENCE_COMMIT_CERTIFICATE_VERSION,
    LOCAL_COMMIT_RECEIPT_VERSION,
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    evidence_commit_certificate_fingerprint,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    verify_evidence_commit_certificate,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    DecisionOutcome,
    DecisionOutcomeKind,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
    action_permission_matches,
)
from pheroos.governance.principal import (
    PrincipalVerification,
    principal_verification_fingerprint,
    principal_verification_is_authoritative,
    principal_verification_matches,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
    stop_resolution_verification_matches,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    eligible_membership_epoch_state_fingerprint,
    eligible_membership_epoch_state_is_current,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_is_authoritative,
    eligible_principal_snapshot_matches,
)
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CollectiveCommitPolicy,
    CommitAction,
    CommitAssurance,
    DistributedCommitPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import validate_distributed_commit_policy


DISTRIBUTED_PROPOSAL_VERSION = "pheroos-distributed-commit-proposal-v1"
DISTRIBUTED_COMMIT_VALUE_VERSION = "pheroos-distributed-commit-value-v1"
QUORUM_WITNESS_VERSION = "pheroos-quorum-witness-v1"
WITNESS_VERIFICATION_VERSION = "pheroos-witness-verification-v1"
DISTRIBUTED_STATE_VERSION = "pheroos-distributed-commit-state-v1"
DISTRIBUTED_COMMIT_CERTIFICATE_VERSION = (
    "pheroos-distributed-commit-certificate-v1"
)
EPOCH_TRANSITION_CERTIFICATE_VERSION = (
    "pheroos-epoch-transition-certificate-v1"
)
DISTRIBUTED_FINALITY_DECISION_VERSION = (
    "pheroos-distributed-finality-decision-v1"
)
DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR = (
    "distributed_commit_certificate"
)
EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR = (
    "epoch_transition_certificate"
)


class DistributedCertificateStatus(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"


class DistributedFinalityKind(StrEnum):
    PENDING = "pending"
    PROVISIONAL = "provisional"
    FINAL = "final"
    NON_COMMIT_TERMINAL = "non_commit_terminal"
    FINALITY_UNAVAILABLE = "finality_unavailable"
    SAFETY_VIOLATION = "safety_violation"


@dataclass(frozen=True)
class PortableEligiblePrincipal:
    principal_id: str
    principal_verification_fingerprint: str
    verified_issuer_id: str
    verified_method: str
    failure_domain: str

    def __post_init__(self) -> None:
        require_commit_text(self.principal_id, "portable member principal_id")
        require_commit_fingerprint(
            self.principal_verification_fingerprint,
            "portable member principal_verification_fingerprint",
        )
        require_commit_text(
            self.verified_issuer_id,
            "portable member verified_issuer_id",
        )
        require_commit_text(self.verified_method, "portable member verified_method")
        require_commit_text(self.failure_domain, "portable member failure_domain")


@dataclass(frozen=True)
class PortableEligibleCluster:
    cluster_id: str
    principals: tuple[PortableEligiblePrincipal, ...]

    def __post_init__(self) -> None:
        require_commit_text(self.cluster_id, "portable membership cluster_id")
        values = tuple(self.principals)
        if not values or any(type(item) is not PortableEligiblePrincipal for item in values):
            raise GovernanceError(
                "portable membership cluster requires canonical principals"
            )
        values = tuple(
            sorted(
                values,
                key=lambda item: (
                    item.principal_id,
                    item.principal_verification_fingerprint,
                ),
            )
        )
        if len({item.principal_id for item in values}) != len(values):
            raise GovernanceError("portable membership repeats a principal")
        if len(
            {item.principal_verification_fingerprint for item in values}
        ) != len(values):
            raise GovernanceError("portable membership repeats a verification")
        object.__setattr__(self, "principals", values)


@dataclass(frozen=True)
class PortableMembershipSnapshot:
    snapshot_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    eligible_clusters: tuple[PortableEligibleCluster, ...]
    membership_root: str
    issuer_id: str
    membership_method: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    snapshot_fingerprint: str

    def __post_init__(self) -> None:
        values = tuple(self.eligible_clusters)
        if any(type(item) is not PortableEligibleCluster for item in values):
            raise GovernanceError(
                "portable membership requires canonical cluster records"
            )
        values = tuple(sorted(values, key=lambda item: item.cluster_id))
        if not values:
            raise GovernanceError("portable distributed membership must not be empty")
        if len({item.cluster_id for item in values}) != len(values):
            raise GovernanceError("portable membership repeats a cluster")
        principal_ids = tuple(
            principal.principal_id
            for cluster in values
            for principal in cluster.principals
        )
        if len(principal_ids) != len(set(principal_ids)):
            raise GovernanceError(
                "portable membership principal belongs to multiple clusters"
            )
        object.__setattr__(self, "eligible_clusters", values)
        _validate_portable_membership_snapshot(self)


@dataclass(frozen=True)
class DistributedCommitProposal:
    proposal_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    proposal_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    claim_fingerprint: str
    output_payload_fingerprint: str
    risk_chain_state_root: str
    risk_assessment_root: str
    risk_policy_root: str
    membership_snapshot_root: str
    membership_epoch_state_root: str
    membership_root: str
    replay_state_root: str
    replay_root: str
    support_replay_state_root: str
    support_replay_root: str
    candidate_evidence_root: str
    candidate_challenge_root: str
    candidate_lease_root: str
    evidence_root: str
    challenge_root: str
    lease_root: str
    window_state_root: str
    window_root: str
    threshold_root: str
    stop_resolution_root: str
    permission_root: str
    context_root: str
    assessment_root: str
    local_receipt_version: str
    local_receipt_ref: str
    portable_certificate_version: str
    portable_certificate_ref: str
    proposed_at_step: int
    commit_value_root: str
    proposal_digest: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_distributed_commit_proposal(self)


@dataclass(frozen=True)
class QuorumWitness:
    witness_version: str
    witness_id: str
    profile: str
    assurance: CommitAssurance
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    membership_root: str
    commit_value_root: str
    proposal_digest: str
    principal_id: str
    principal_cluster_id: str
    failure_domain: str
    nonce: str
    witnessed_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    attestation_ref: str

    def __post_init__(self) -> None:
        _validate_quorum_witness(self)


@dataclass(frozen=True)
class WitnessVerification:
    verification_version: str
    verification_id: str
    witness: QuorumWitness
    witness_fingerprint: str
    witness_signing_root: str
    principal_verification_ref: str
    verified_at_step: int
    expires_at_step: int
    verifier_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_witness_verification(self)


@dataclass(frozen=True)
class WitnessReplayReceipt:
    verification_id: str
    witness_id: str
    nonce: str
    witness_fingerprint: str
    commit_value_root: str
    proposal_digest: str
    target: str
    candidate_id: str
    epoch: int
    principal_id: str
    principal_cluster_id: str

    def __post_init__(self) -> None:
        for name in (
            "verification_id",
            "witness_id",
            "nonce",
            "target",
            "candidate_id",
            "principal_id",
            "principal_cluster_id",
        ):
            require_commit_text(
                getattr(self, name),
                f"witness replay receipt {name}",
            )
        for name in (
            "witness_fingerprint",
            "commit_value_root",
            "proposal_digest",
        ):
            require_commit_fingerprint(
                getattr(self, name),
                f"witness replay receipt {name}",
            )
        require_commit_step(self.epoch, "witness replay receipt epoch")


@dataclass(frozen=True)
class WitnessEquivocationFinding:
    finding_id: str
    target: str
    epoch: int
    principal_cluster_id: str
    commit_value_roots: tuple[str, ...]
    proposal_digests: tuple[str, ...]
    witness_fingerprints: tuple[str, ...]

    def __post_init__(self) -> None:
        require_commit_fingerprint(self.finding_id, "witness equivocation finding_id")
        require_commit_text(self.target, "witness equivocation target")
        require_commit_step(self.epoch, "witness equivocation epoch")
        require_commit_text(
            self.principal_cluster_id,
            "witness equivocation principal_cluster_id",
        )
        object.__setattr__(
            self,
            "commit_value_roots",
            _canonical_fingerprints(
                self.commit_value_roots,
                "witness equivocation commit value roots",
            ),
        )
        object.__setattr__(
            self,
            "proposal_digests",
            _canonical_fingerprints(
                self.proposal_digests,
                "witness equivocation proposal digests",
            ),
        )
        object.__setattr__(
            self,
            "witness_fingerprints",
            _canonical_fingerprints(
                self.witness_fingerprints,
                "witness equivocation fingerprints",
            ),
        )
        if len(self.commit_value_roots) < 2:
            raise GovernanceError(
                "witness equivocation requires conflicting commit values"
            )


@dataclass(frozen=True)
class FinalCertificateRegistration:
    certificate_ref: str
    commit_value_root: str
    proposal_digest: str
    candidate_id: str
    registered_at_step: int

    def __post_init__(self) -> None:
        require_commit_fingerprint(
            self.certificate_ref,
            "distributed registration certificate_ref",
        )
        require_commit_fingerprint(
            self.commit_value_root,
            "distributed registration commit_value_root",
        )
        require_commit_fingerprint(
            self.proposal_digest,
            "distributed registration proposal_digest",
        )
        require_commit_text(
            self.candidate_id,
            "distributed registration candidate_id",
        )
        require_commit_step(
            self.registered_at_step,
            "distributed registration registered_at_step",
        )


@dataclass(frozen=True)
class CertificateConflictFinding:
    finding_id: str
    target: str
    epoch: int
    certificate_refs: tuple[str, ...]
    commit_value_roots: tuple[str, ...]
    proposal_digests: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    detected_at_step: int

    def __post_init__(self) -> None:
        require_commit_fingerprint(self.finding_id, "certificate conflict finding_id")
        require_commit_text(self.target, "certificate conflict target")
        require_commit_step(self.epoch, "certificate conflict epoch")
        object.__setattr__(
            self,
            "certificate_refs",
            _canonical_fingerprints(
                self.certificate_refs,
                "certificate conflict refs",
            ),
        )
        object.__setattr__(
            self,
            "commit_value_roots",
            _canonical_fingerprints(
                self.commit_value_roots,
                "certificate conflict commit value roots",
            ),
        )
        object.__setattr__(
            self,
            "proposal_digests",
            _canonical_fingerprints(
                self.proposal_digests,
                "certificate conflict proposal digests",
            ),
        )
        object.__setattr__(
            self,
            "candidate_ids",
            require_commit_labels(
                self.candidate_ids,
                "certificate conflict candidate ids",
            ),
        )
        require_commit_step(
            self.detected_at_step,
            "certificate conflict detected_at_step",
        )
        if len(self.certificate_refs) < 2 or len(self.commit_value_roots) < 2:
            raise GovernanceError("certificate conflict requires two final proofs")


@dataclass(frozen=True)
class DistributedCommitState:
    chain_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    membership_snapshot: PortableMembershipSnapshot
    membership_snapshot_root: str
    membership_epoch_state_root: str
    membership_root: str
    membership_size: int
    max_byzantine_faults: int
    witness_quorum: int
    witness_ttl_steps: int
    minimum_failure_domain_diversity: int
    revision: int
    initialized_at_step: int
    current_step: int
    previous_state_fingerprint: str
    witness_verifications: tuple[WitnessVerification, ...]
    witness_receipt_root: str
    equivocation_findings: tuple[WitnessEquivocationFinding, ...]
    excluded_cluster_ids: tuple[str, ...]
    final_registrations: tuple[FinalCertificateRegistration, ...]
    conflict_findings: tuple[CertificateConflictFinding, ...]
    frozen: bool
    transitioned: bool
    epoch_transition_certificate_ref: str
    issuer_id: str
    authority: AuthorityLevel
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
            "witness_verifications",
            _canonical_witness_verifications(self.witness_verifications),
        )
        object.__setattr__(
            self,
            "equivocation_findings",
            tuple(sorted(self.equivocation_findings, key=lambda item: item.finding_id)),
        )
        object.__setattr__(
            self,
            "excluded_cluster_ids",
            require_commit_labels(
                self.excluded_cluster_ids,
                "distributed state excluded clusters",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "final_registrations",
            tuple(
                sorted(
                    self.final_registrations,
                    key=lambda item: item.certificate_ref,
                )
            ),
        )
        object.__setattr__(
            self,
            "conflict_findings",
            tuple(sorted(self.conflict_findings, key=lambda item: item.finding_id)),
        )
        _validate_distributed_commit_state(self)


@dataclass(frozen=True)
class DistributedCommitCertificate:
    schema_discriminator: str
    certificate_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    certificate_id: str
    status: DistributedCertificateStatus
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    commit_value_root: str
    proposal_digest: str
    proposal: DistributedCommitProposal
    membership_snapshot: PortableMembershipSnapshot
    membership_snapshot_root: str
    membership_root: str
    membership_size: int
    max_byzantine_faults: int
    witness_quorum: int
    minimum_failure_domain_diversity: int
    witnesses: tuple[WitnessVerification, ...]
    witness_root: str
    excluded_cluster_ids: tuple[str, ...]
    portable_certificate_ref: str
    portable_certificate_version: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str
    certificate_body_root: str
    certificate_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "witnesses",
            _canonical_witness_verifications(self.witnesses),
        )
        object.__setattr__(
            self,
            "excluded_cluster_ids",
            require_commit_labels(
                self.excluded_cluster_ids,
                "distributed certificate excluded clusters",
                allow_empty=True,
            ),
        )
        _validate_distributed_commit_certificate(self)


@dataclass(frozen=True)
class EpochTransitionCertificate:
    schema_discriminator: str
    certificate_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    certificate_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    previous_epoch: int
    new_epoch: int
    previous_membership_root: str
    new_membership_snapshot: PortableMembershipSnapshot
    new_membership_snapshot_root: str
    new_membership_epoch_state_root: str
    new_membership_root: str
    prior_state_ref: str
    declared_transition_rule: str
    declared_recovery_ref: str
    recovery_required: bool
    transition_stop_root: str
    transition_permission_root: str
    recovery_stop_root: str
    recovery_permission_root: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str
    issuer_attestation_refs: tuple[str, ...]
    certificate_body_root: str
    certificate_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issuer_attestation_refs",
            require_commit_labels(
                self.issuer_attestation_refs,
                "epoch transition issuer attestations",
            ),
        )
        _validate_epoch_transition_certificate(self)


@dataclass(frozen=True)
class DistributedFinalityDecision:
    decision_version: str
    kind: DistributedFinalityKind
    terminal: bool
    authoritative_commit: bool
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    state_ref: str
    local_receipt_ref: str
    distributed_certificate_ref: str
    outcome_ref: str
    reason_codes: tuple[str, ...]
    current_step: int
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
                "distributed finality reason codes",
            ),
        )
        _validate_distributed_finality_decision(self)


class _DistributedStateCursor:
    __slots__ = (
        "authority_key",
        "base_fingerprint",
        "current_state",
        "current_state_fingerprint",
        "transitions",
        "lock",
    )

    def __init__(self, *, authority_key: str, base_fingerprint: str) -> None:
        self.authority_key = authority_key
        self.base_fingerprint = base_fingerprint
        self.current_state: DistributedCommitState | None = None
        self.current_state_fingerprint = ""
        self.transitions: dict[
            str,
            tuple[str, DistributedCommitState],
        ] = {}
        self.lock = RLock()


_PROPOSAL_ISSUANCE = object()
_WITNESS_VERIFICATION_ISSUANCE = object()
_DISTRIBUTED_STATE_ISSUANCE = object()
_FINALITY_DECISION_ISSUANCE = object()
_DISTRIBUTED_STATE_REGISTRY_LOCK = RLock()
_DISTRIBUTED_STATE_CURSORS: dict[str, _DistributedStateCursor] = {}
_WITNESS_REGISTRY_LOCK = RLock()
_WITNESS_VERIFICATIONS_BY_ID: dict[
    tuple[str, str, str], WitnessVerification
] = {}
_WITNESS_VERIFICATIONS_BY_NONCE: dict[
    tuple[str, str, str], WitnessVerification
] = {}
_PROPOSAL_REGISTRY_LOCK = RLock()
_PROPOSALS_BY_ID: dict[
    tuple[str, str, str, int, str], DistributedCommitProposal
] = {}
_DISTRIBUTED_CERTIFICATE_REGISTRY_LOCK = RLock()
_DISTRIBUTED_CERTIFICATES_BY_ID: dict[
    tuple[str, str, str, int, str], DistributedCommitCertificate
] = {}
_EPOCH_CERTIFICATE_REGISTRY_LOCK = RLock()
_EPOCH_CERTIFICATES_BY_ID: dict[
    tuple[str, str, str, int, str], EpochTransitionCertificate
] = {}


def portable_membership_snapshot_from_eligible(
    snapshot: EligiblePrincipalSnapshot,
) -> PortableMembershipSnapshot:
    if not eligible_principal_snapshot_is_authoritative(snapshot):
        raise GovernanceError(
            "portable distributed membership requires an authoritative snapshot"
        )
    clusters = tuple(
        PortableEligibleCluster(
            cluster_id=cluster.cluster_id,
            principals=tuple(
                PortableEligiblePrincipal(
                    principal_id=principal.principal_id,
                    principal_verification_fingerprint=(
                        principal.principal_verification_fingerprint
                    ),
                    verified_issuer_id=principal.verified_issuer_id,
                    verified_method=principal.verified_method,
                    failure_domain=principal.failure_domain,
                )
                for principal in cluster.principals
            ),
        )
        for cluster in snapshot.eligible_clusters
    )
    return PortableMembershipSnapshot(
        snapshot_id=snapshot.snapshot_id,
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        protocol_id=snapshot.protocol_id,
        run_id=snapshot.run_id,
        target=snapshot.target,
        epoch=snapshot.epoch,
        eligible_clusters=clusters,
        membership_root=snapshot.membership_root,
        issuer_id=snapshot.issuer_id,
        membership_method=snapshot.membership_method,
        authority=snapshot.authority,
        issued_at_step=snapshot.issued_at_step,
        expires_at_step=snapshot.expires_at_step,
        provenance=snapshot.provenance,
        trace_event_id=snapshot.trace_event_id,
        snapshot_fingerprint=eligible_principal_snapshot_fingerprint(snapshot),
    )


def portable_membership_snapshot_payload(
    snapshot: PortableMembershipSnapshot,
    *,
    include_snapshot_fingerprint: bool = True,
) -> dict[str, object]:
    if type(snapshot) is not PortableMembershipSnapshot:
        raise GovernanceError(
            "portable membership must use the canonical distributed record"
        )
    _validate_portable_membership_snapshot(snapshot)
    payload: dict[str, object] = {
        "assurance": snapshot.assurance,
        "authority": snapshot.authority,
        "commit_policy_root": snapshot.commit_policy_root,
        "eligible_clusters": tuple(
            {
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
            for cluster in snapshot.eligible_clusters
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
    if include_snapshot_fingerprint:
        payload["snapshot_fingerprint"] = snapshot.snapshot_fingerprint
    return payload


def portable_membership_snapshot_fingerprint(
    snapshot: PortableMembershipSnapshot,
) -> str:
    return commit_payload_fingerprint(
        portable_membership_snapshot_payload(
            snapshot,
            include_snapshot_fingerprint=False,
        ),
        schema="pheroos-eligible-principal-snapshot-v1",
        profile=snapshot.profile,
    )


def portable_membership_root(snapshot: PortableMembershipSnapshot) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": snapshot.assurance,
            "commit_policy_root": snapshot.commit_policy_root,
            "eligible_clusters": portable_membership_snapshot_payload(
                snapshot,
                include_snapshot_fingerprint=False,
            )["eligible_clusters"],
            "epoch": snapshot.epoch,
            "manifest_root": snapshot.manifest_root,
            "protocol_id": snapshot.protocol_id,
            "run_id": snapshot.run_id,
            "target": snapshot.target,
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=snapshot.profile,
    )


def portable_membership_snapshot_from_payload(
    payload: Mapping[str, object],
) -> PortableMembershipSnapshot:
    values = _strict_mapping(
        payload,
        {
            "assurance",
            "authority",
            "commit_policy_root",
            "eligible_clusters",
            "epoch",
            "expires_at_step",
            "issued_at_step",
            "issuer_id",
            "manifest_root",
            "membership_method",
            "membership_root",
            "profile",
            "protocol_id",
            "provenance",
            "run_id",
            "snapshot_fingerprint",
            "snapshot_id",
            "target",
            "trace_event_id",
        },
        "portable membership payload",
    )
    raw_clusters = _require_sequence(
        values["eligible_clusters"],
        "portable membership eligible_clusters",
    )
    clusters: list[PortableEligibleCluster] = []
    for raw_cluster in raw_clusters:
        cluster = _strict_mapping(
            raw_cluster,
            {"cluster_id", "principals"},
            "portable membership cluster",
        )
        raw_principals = _require_sequence(
            cluster["principals"],
            "portable membership principals",
        )
        principals = tuple(
            PortableEligiblePrincipal(
                **_strict_mapping(
                    raw_principal,
                    {
                        "failure_domain",
                        "principal_id",
                        "principal_verification_fingerprint",
                        "verified_issuer_id",
                        "verified_method",
                    },
                    "portable membership principal",
                )
            )
            for raw_principal in raw_principals
        )
        clusters.append(
            PortableEligibleCluster(
                cluster_id=cluster["cluster_id"],
                principals=principals,
            )
        )
    return PortableMembershipSnapshot(
        snapshot_id=values["snapshot_id"],
        profile=values["profile"],
        assurance=_coerce_assurance(values["assurance"]),
        manifest_root=values["manifest_root"],
        commit_policy_root=values["commit_policy_root"],
        protocol_id=values["protocol_id"],
        run_id=values["run_id"],
        target=values["target"],
        epoch=values["epoch"],
        eligible_clusters=tuple(clusters),
        membership_root=values["membership_root"],
        issuer_id=values["issuer_id"],
        membership_method=values["membership_method"],
        authority=_coerce_authority(values["authority"]),
        issued_at_step=values["issued_at_step"],
        expires_at_step=values["expires_at_step"],
        provenance=values["provenance"],
        trace_event_id=values["trace_event_id"],
        snapshot_fingerprint=values["snapshot_fingerprint"],
    )


def issue_distributed_commit_proposal(
    receipt: LocalCommitReceipt,
    portable_certificate: EvidenceCommitCertificate,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_issuer_attestations: Mapping[str, str],
    proposal_id: str,
    proposed_at_step: int,
) -> DistributedCommitProposal:
    """Build the exact digest witnesses sign from authoritative central leaves.

    The final bounded-liveness outcome is intentionally not an input: finality
    must be established first, after which its certificate fingerprint is
    passed to liveness. The proposal instead binds the stable window,
    assessment, local receipt, and independently verified portable central
    certificate.
    """

    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError(
            "distributed proposal requires an authoritative local receipt"
        )
    if receipt.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed proposal requires distributed assurance")
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=receipt.profile,
        assurance=receipt.assurance,
        target=receipt.target,
        commit_policy_root=receipt.commit_policy_root,
    )
    current = require_commit_step(
        proposed_at_step,
        "distributed proposal proposed_at_step",
    )
    if not verify_evidence_commit_certificate(
        portable_certificate,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError(
            "distributed proposal portable certificate verification failed"
        )
    _validate_receipt_certificate_lineage(receipt, portable_certificate)
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=receipt.profile,
        assurance=receipt.assurance,
        manifest_root=receipt.manifest_root,
        commit_policy_root=receipt.commit_policy_root,
        protocol_id=receipt.protocol_id,
        run_id=receipt.run_id,
        target=receipt.target,
        epoch=receipt.epoch,
        current_step=current,
    ):
        raise GovernanceError(
            "distributed proposal membership snapshot is not authoritative and fresh"
        )
    portable_membership = portable_membership_snapshot_from_eligible(
        membership_snapshot
    )
    _validate_membership_policy(portable_membership, distributed)
    membership_epoch_ref = eligible_membership_epoch_state_fingerprint(
        membership_epoch_state
    )
    if (
        receipt.membership_snapshot_root
        != portable_membership.snapshot_fingerprint
        or receipt.membership_epoch_state_root != membership_epoch_ref
        or receipt.membership_root != portable_membership.membership_root
    ):
        raise GovernanceError(
            "distributed proposal central receipt membership lineage mismatch"
        )
    body = _distributed_proposal_body_from_receipt(
        receipt,
        portable_certificate=portable_certificate,
        proposal_id=proposal_id,
        proposed_at_step=current,
    )
    body["commit_value_root"] = _distributed_commit_value_root_from_mapping(
        body
    )
    digest = commit_payload_fingerprint(
        body,
        schema=DISTRIBUTED_PROPOSAL_VERSION,
        profile=receipt.profile,
    )
    proposal = DistributedCommitProposal(**body, proposal_digest=digest)
    object.__setattr__(
        proposal,
        "_issuance",
        (_PROPOSAL_ISSUANCE, distributed_commit_proposal_fingerprint(proposal)),
    )
    key = (
        proposal.profile,
        proposal.run_id,
        proposal.target,
        proposal.epoch,
        proposal.proposal_id,
    )
    with _PROPOSAL_REGISTRY_LOCK:
        existing = _PROPOSALS_BY_ID.get(key)
        if existing is not None:
            if distributed_commit_proposal_fingerprint(existing) != (
                distributed_commit_proposal_fingerprint(proposal)
            ):
                raise GovernanceError(
                    "distributed proposal id replay has a different body"
                )
            return existing
        _PROPOSALS_BY_ID[key] = proposal
        return proposal


def distributed_commit_proposal_payload(
    proposal: DistributedCommitProposal,
) -> dict[str, object]:
    if type(proposal) is not DistributedCommitProposal:
        raise GovernanceError("distributed proposal must use the canonical record")
    _validate_distributed_commit_proposal(proposal)
    return _public_dataclass_payload(proposal)


def distributed_commit_value_payload(
    proposal: DistributedCommitProposal,
) -> dict[str, object]:
    """Return the canonical semantic value carried by a proposal.

    Proposal, receipt, certificate, witness, and transport identities are proof
    envelope metadata.  They remain covered by the full proposal digest, but
    are deliberately absent here so an exact semantic retry cannot manufacture
    a Byzantine safety conflict.
    """

    if type(proposal) is not DistributedCommitProposal:
        raise GovernanceError("distributed commit value requires canonical proposal")
    _validate_distributed_commit_proposal(proposal)
    return _distributed_commit_value_payload_from_mapping(
        _public_dataclass_payload(proposal)
    )


def distributed_commit_value_root(
    value: DistributedCommitProposal | Mapping[str, object],
) -> str:
    if type(value) is DistributedCommitProposal:
        payload = distributed_commit_value_payload(value)
        profile = value.profile
    else:
        payload = _validate_distributed_commit_value_payload(value)
        profile = payload["profile"]
        assert type(profile) is str
    return commit_payload_fingerprint(
        payload,
        schema=DISTRIBUTED_COMMIT_VALUE_VERSION,
        profile=profile,
    )


def distributed_commit_proposal_fingerprint(
    proposal: DistributedCommitProposal,
) -> str:
    return commit_payload_fingerprint(
        distributed_commit_proposal_payload(proposal),
        schema="pheroos-distributed-commit-proposal-envelope-v1",
        profile=proposal.profile,
    )


def distributed_commit_proposal_is_authoritative(proposal: object) -> bool:
    if type(proposal) is not DistributedCommitProposal:
        return False
    try:
        issuance = proposal._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _PROPOSAL_ISSUANCE
            and issuance[1] == distributed_commit_proposal_fingerprint(proposal)
        )
    except Exception:
        return False


def distributed_commit_proposal_from_payload(
    payload: Mapping[str, object],
) -> DistributedCommitProposal:
    values = _strict_dataclass_payload(
        payload,
        DistributedCommitProposal,
        "distributed proposal payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    try:
        return DistributedCommitProposal(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(f"distributed proposal payload is invalid: {exc}") from exc


def verify_distributed_commit_proposal(
    proposal_or_payload: DistributedCommitProposal | Mapping[str, object],
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    membership_snapshot: PortableMembershipSnapshot | EligiblePrincipalSnapshot,
    trusted_issuer_attestations: Mapping[str, str],
    expected_proposal_digest: str = "",
    expected_commit_value_root: str = "",
) -> bool:
    try:
        proposal = (
            proposal_or_payload
            if type(proposal_or_payload) is DistributedCommitProposal
            else distributed_commit_proposal_from_payload(proposal_or_payload)
        )
        assert type(proposal) is DistributedCommitProposal
        distributed = _validate_distributed_policy(
            commit_policy,
            profile=proposal.profile,
            assurance=proposal.assurance,
            target=proposal.target,
            commit_policy_root=proposal.commit_policy_root,
        )
        portable = _coerce_portable_membership(membership_snapshot)
        _validate_membership_policy(portable, distributed)
        _validate_proposal_membership(proposal, portable)
        if not verify_evidence_commit_certificate(
            portable_certificate,
            trusted_issuer_attestations=trusted_issuer_attestations,
            expected_certificate_ref=proposal.portable_certificate_ref,
            expected_claim_fingerprint=proposal.claim_fingerprint,
            expected_output_payload_fingerprint=(
                proposal.output_payload_fingerprint
            ),
        ):
            return False
        _validate_proposal_certificate_lineage(proposal, portable_certificate)
        if expected_proposal_digest and proposal.proposal_digest != (
            require_commit_fingerprint(
                expected_proposal_digest,
                "expected distributed proposal digest",
            )
        ):
            return False
        if expected_commit_value_root and proposal.commit_value_root != (
            require_commit_fingerprint(
                expected_commit_value_root,
                "expected distributed commit value root",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def quorum_witness_signing_payload(witness: QuorumWitness) -> dict[str, object]:
    if type(witness) is not QuorumWitness:
        raise GovernanceError("quorum witness must use the canonical record")
    _validate_quorum_witness(witness)
    payload = _public_dataclass_payload(witness)
    payload.pop("attestation_ref")
    return payload


def quorum_witness_signing_root(witness: QuorumWitness) -> str:
    return commit_payload_fingerprint(
        quorum_witness_signing_payload(witness),
        schema="pheroos-quorum-witness-signing-v1",
        profile=witness.profile,
    )


def quorum_witness_payload(witness: QuorumWitness) -> dict[str, object]:
    if type(witness) is not QuorumWitness:
        raise GovernanceError("quorum witness must use the canonical record")
    _validate_quorum_witness(witness)
    return _public_dataclass_payload(witness)


def quorum_witness_fingerprint(witness: QuorumWitness) -> str:
    return commit_payload_fingerprint(
        quorum_witness_payload(witness),
        schema=QUORUM_WITNESS_VERSION,
        profile=witness.profile,
    )


def quorum_witness_from_payload(payload: Mapping[str, object]) -> QuorumWitness:
    values = _strict_dataclass_payload(
        payload,
        QuorumWitness,
        "quorum witness payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    try:
        return QuorumWitness(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(f"quorum witness payload is invalid: {exc}") from exc


def verify_quorum_witness(
    witness: QuorumWitness,
    proposal: DistributedCommitProposal,
    principal_verification: PrincipalVerification,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_witness_attestations: Mapping[str, str],
    verification_id: str,
    verifier_id: str,
    authority: AuthorityLevel,
    verified_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> WitnessVerification:
    """Turn an untrusted witness proposal into governance-issued authority."""

    if type(witness) is not QuorumWitness:
        raise GovernanceError("witness proposal must use QuorumWitness")
    if not distributed_commit_proposal_is_authoritative(proposal):
        raise GovernanceError(
            "witness verification requires a governance-issued proposal"
        )
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("witness verification requires governance authority")
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=proposal.profile,
        assurance=proposal.assurance,
        target=proposal.target,
        commit_policy_root=proposal.commit_policy_root,
    )
    current = require_commit_step(
        verified_at_step,
        "witness verification verified_at_step",
    )
    _validate_witness_proposal_binding(witness, proposal)
    if witness.expires_at_step - witness.witnessed_at_step > (
        distributed.witness_ttl_steps
    ):
        raise GovernanceError("quorum witness exceeds the declared witness TTL")
    if not (witness.witnessed_at_step <= current < witness.expires_at_step):
        raise GovernanceError("quorum witness is stale at verification")
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
        raise GovernanceError("witness membership is not authoritative and fresh")
    portable = portable_membership_snapshot_from_eligible(membership_snapshot)
    _validate_membership_policy(portable, distributed)
    member = _portable_member(portable, witness.principal_id)
    if member is None:
        raise GovernanceError("quorum witness principal is outside membership")
    cluster_id, portable_principal = member
    if (
        cluster_id != witness.principal_cluster_id
        or portable_principal.failure_domain != witness.failure_domain
    ):
        raise GovernanceError("quorum witness cluster/failure-domain mismatch")
    if not principal_verification_is_authoritative(principal_verification):
        raise GovernanceError("quorum witness principal verification is forged")
    principal_ref = principal_verification_fingerprint(principal_verification)
    if (
        principal_ref
        != portable_principal.principal_verification_fingerprint
        or not principal_verification_matches(
            principal_verification,
            profile=proposal.profile,
            assurance=proposal.assurance,
            manifest_root=proposal.manifest_root,
            commit_policy_root=proposal.commit_policy_root,
            protocol_id=proposal.protocol_id,
            run_id=proposal.run_id,
            target=proposal.target,
            epoch=proposal.epoch,
            principal_id=witness.principal_id,
            current_step=current,
        )
    ):
        raise GovernanceError("quorum witness principal verification mismatch")
    signing_root = quorum_witness_signing_root(witness)
    if not _attestation_matches(
        witness.attestation_ref,
        trusted_witness_attestations,
        signing_root,
    ):
        raise GovernanceError("quorum witness attestation verification failed")
    expires = min(
        witness.expires_at_step,
        principal_verification.expires_at_step,
        membership_snapshot.expires_at_step,
    )
    if expires <= current:
        raise GovernanceError("quorum witness verification has no fresh interval")
    verification = WitnessVerification(
        verification_version=WITNESS_VERIFICATION_VERSION,
        verification_id=require_commit_text(
            verification_id,
            "witness verification verification_id",
        ),
        witness=witness,
        witness_fingerprint=quorum_witness_fingerprint(witness),
        witness_signing_root=signing_root,
        principal_verification_ref=principal_ref,
        verified_at_step=current,
        expires_at_step=expires,
        verifier_id=require_commit_text(
            verifier_id,
            "witness verification verifier_id",
        ),
        authority=authority,
        provenance=require_commit_text(
            provenance,
            "witness verification provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "witness verification trace_event_id",
        ),
    )
    fingerprint = witness_verification_fingerprint(verification)
    id_key = (witness.profile, witness.run_id, verification.verification_id)
    nonce_key = (witness.profile, witness.run_id, witness.nonce)
    with _WITNESS_REGISTRY_LOCK:
        by_id = _WITNESS_VERIFICATIONS_BY_ID.get(id_key)
        by_nonce = _WITNESS_VERIFICATIONS_BY_NONCE.get(nonce_key)
        for existing in (by_id, by_nonce):
            if existing is None:
                continue
            if witness_verification_fingerprint(existing) != fingerprint:
                raise GovernanceError(
                    "witness id/nonce replay collision is a safety violation"
                )
            return existing
        object.__setattr__(
            verification,
            "_issuance",
            (_WITNESS_VERIFICATION_ISSUANCE, fingerprint),
        )
        _WITNESS_VERIFICATIONS_BY_ID[id_key] = verification
        _WITNESS_VERIFICATIONS_BY_NONCE[nonce_key] = verification
        return verification


def witness_verification_payload(
    verification: WitnessVerification,
) -> dict[str, object]:
    if type(verification) is not WitnessVerification:
        raise GovernanceError("witness verification must use the canonical record")
    _validate_witness_verification(verification)
    payload = _public_dataclass_payload(verification)
    payload["witness"] = quorum_witness_payload(verification.witness)
    return payload


def witness_verification_fingerprint(
    verification: WitnessVerification,
) -> str:
    return commit_payload_fingerprint(
        witness_verification_payload(verification),
        schema=WITNESS_VERIFICATION_VERSION,
        profile=verification.witness.profile,
    )


def witness_verification_is_authoritative(verification: object) -> bool:
    if type(verification) is not WitnessVerification:
        return False
    try:
        issuance = verification._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _WITNESS_VERIFICATION_ISSUANCE
            and issuance[1] == witness_verification_fingerprint(verification)
        )
    except Exception:
        return False


def witness_verification_from_payload(
    payload: Mapping[str, object],
) -> WitnessVerification:
    values = _strict_dataclass_payload(
        payload,
        WitnessVerification,
        "witness verification payload",
    )
    values["witness"] = quorum_witness_from_payload(values["witness"])
    values["authority"] = _coerce_authority(values["authority"])
    try:
        return WitnessVerification(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"witness verification payload is invalid: {exc}"
        ) from exc


def verify_portable_witness_verification(
    verification_or_payload: WitnessVerification | Mapping[str, object],
    *,
    membership_snapshot: PortableMembershipSnapshot,
    trusted_witness_attestations: Mapping[str, str],
    issued_at_step: int,
) -> bool:
    try:
        verification = (
            verification_or_payload
            if type(verification_or_payload) is WitnessVerification
            else witness_verification_from_payload(verification_or_payload)
        )
        assert type(verification) is WitnessVerification
        current = require_commit_step(
            issued_at_step,
            "portable witness certificate issuance step",
        )
        witness = verification.witness
        if not (
            verification.verified_at_step <= current < verification.expires_at_step
            and witness.witnessed_at_step <= current < witness.expires_at_step
        ):
            return False
        member = _portable_member(membership_snapshot, witness.principal_id)
        if member is None:
            return False
        cluster_id, principal = member
        if (
            cluster_id != witness.principal_cluster_id
            or principal.failure_domain != witness.failure_domain
            or principal.principal_verification_fingerprint
            != verification.principal_verification_ref
        ):
            return False
        if quorum_witness_fingerprint(witness) != verification.witness_fingerprint:
            return False
        signing_root = quorum_witness_signing_root(witness)
        if signing_root != verification.witness_signing_root:
            return False
        return _attestation_matches(
            witness.attestation_ref,
            trusted_witness_attestations,
            signing_root,
        )
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def witness_replay_receipt(
    verification: WitnessVerification,
) -> WitnessReplayReceipt:
    if not witness_verification_is_authoritative(verification):
        raise GovernanceError(
            "witness replay receipt requires authoritative verification"
        )
    witness = verification.witness
    return WitnessReplayReceipt(
        verification_id=verification.verification_id,
        witness_id=witness.witness_id,
        nonce=witness.nonce,
        witness_fingerprint=verification.witness_fingerprint,
        commit_value_root=witness.commit_value_root,
        proposal_digest=witness.proposal_digest,
        target=witness.target,
        candidate_id=witness.candidate_id,
        epoch=witness.epoch,
        principal_id=witness.principal_id,
        principal_cluster_id=witness.principal_cluster_id,
    )


def witness_replay_receipt_payload(
    receipt: WitnessReplayReceipt,
) -> dict[str, object]:
    if type(receipt) is not WitnessReplayReceipt:
        raise GovernanceError("witness replay receipt must use canonical record")
    return _public_dataclass_payload(receipt)


def witness_replay_receipt_from_payload(
    payload: Mapping[str, object],
) -> WitnessReplayReceipt:
    values = _strict_dataclass_payload(
        payload,
        WitnessReplayReceipt,
        "witness replay receipt payload",
    )
    try:
        return WitnessReplayReceipt(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"witness replay receipt payload is invalid: {exc}"
        ) from exc


def witness_replay_receipt_fingerprint(
    receipt: WitnessReplayReceipt,
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        witness_replay_receipt_payload(receipt),
        schema="pheroos-witness-replay-receipt-v1",
        profile=require_commit_profile(profile, "witness replay profile"),
    )


def initialize_distributed_commit_state(
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    current_step: int,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> DistributedCommitState:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "distributed state initialization requires governance authority"
        )
    current = require_commit_step(
        current_step,
        "distributed state current_step",
    )
    if not eligible_membership_epoch_state_is_current(membership_epoch_state):
        raise GovernanceError("distributed state membership epoch is not current")
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
        raise GovernanceError("distributed state membership is not authoritative")
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=membership_snapshot.profile,
        assurance=membership_snapshot.assurance,
        target=membership_snapshot.target,
        commit_policy_root=membership_snapshot.commit_policy_root,
    )
    portable = portable_membership_snapshot_from_eligible(membership_snapshot)
    _validate_membership_policy(portable, distributed)
    membership_epoch_ref = eligible_membership_epoch_state_fingerprint(
        membership_epoch_state
    )
    authority_key = commit_payload_fingerprint(
        {
            "commit_policy_root": portable.commit_policy_root,
            "epoch": portable.epoch,
            "manifest_root": portable.manifest_root,
            "membership_root": portable.membership_root,
            "profile": portable.profile,
            "protocol_id": portable.protocol_id,
            "run_id": portable.run_id,
            "target": portable.target,
        },
        schema="pheroos-distributed-state-authority-key-v1",
        profile=portable.profile,
    )
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority": authority,
            "authority_key": authority_key,
            "initialized_at_step": current,
            "issuer_id": require_commit_text(
                issuer_id,
                "distributed state issuer_id",
            ),
            "membership_epoch_state_root": membership_epoch_ref,
            "membership_snapshot_root": portable.snapshot_fingerprint,
            "provenance": require_commit_text(
                provenance,
                "distributed state provenance",
            ),
            "trace_event_id": require_commit_text(
                trace_event_id,
                "distributed state trace_event_id",
            ),
        },
        schema="pheroos-distributed-state-base-v1",
        profile=portable.profile,
    )
    with _DISTRIBUTED_STATE_REGISTRY_LOCK:
        cursor = _DISTRIBUTED_STATE_CURSORS.get(authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "distributed state authority already has a different base"
                )
            if not distributed_commit_state_is_current(cursor.current_state):
                raise GovernanceError("distributed state current head is unavailable")
            assert cursor.current_state is not None
            return cursor.current_state
        cursor = _DistributedStateCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
        )
        state = DistributedCommitState(
            chain_id=authority_key,
            profile=portable.profile,
            assurance=portable.assurance,
            manifest_root=portable.manifest_root,
            commit_policy_root=portable.commit_policy_root,
            protocol_id=portable.protocol_id,
            run_id=portable.run_id,
            target=portable.target,
            epoch=portable.epoch,
            membership_snapshot=portable,
            membership_snapshot_root=portable.snapshot_fingerprint,
            membership_epoch_state_root=membership_epoch_ref,
            membership_root=portable.membership_root,
            membership_size=distributed.membership_size,
            max_byzantine_faults=distributed.max_byzantine_faults,
            witness_quorum=distributed.witness_quorum,
            witness_ttl_steps=distributed.witness_ttl_steps,
            minimum_failure_domain_diversity=(
                distributed.minimum_failure_domain_diversity
            ),
            revision=0,
            initialized_at_step=current,
            current_step=current,
            previous_state_fingerprint="",
            witness_verifications=(),
            witness_receipt_root=_witness_receipt_root(
                (),
                profile=portable.profile,
            ),
            equivocation_findings=(),
            excluded_cluster_ids=(),
            final_registrations=(),
            conflict_findings=(),
            frozen=False,
            transitioned=False,
            epoch_transition_certificate_ref="",
            issuer_id=issuer_id,
            authority=authority,
            provenance=provenance,
            trace_event_id=trace_event_id,
        )
        state = _issue_distributed_state(state, cursor)
        cursor.current_state = state
        cursor.current_state_fingerprint = distributed_commit_state_fingerprint(
            state
        )
        _DISTRIBUTED_STATE_CURSORS[authority_key] = cursor
        return state


def record_witness_verifications(
    state: DistributedCommitState,
    verifications: Sequence[WitnessVerification],
    *,
    current_step: int,
) -> DistributedCommitState:
    if not distributed_commit_state_is_authoritative(state):
        raise GovernanceError("distributed witness state is not governance-issued")
    if state.frozen:
        raise GovernanceError("distributed epoch is frozen after certificate conflict")
    if state.transitioned:
        raise GovernanceError("distributed epoch has already transitioned")
    current = require_commit_step(
        current_step,
        "distributed witness state current_step",
    )
    if current < state.current_step:
        raise GovernanceError("distributed witness state cannot move backwards")
    incoming = _canonical_witness_verifications(verifications)
    if not incoming:
        return _current_distributed_state_head(state)
    for verification in incoming:
        if not witness_verification_is_authoritative(verification):
            raise GovernanceError(
                "distributed state cannot record a forged witness verification"
            )
        _validate_verification_state_binding(verification, state)
        if not (
            verification.verified_at_step <= current < verification.expires_at_step
        ):
            raise GovernanceError(
                "distributed state cannot record a stale witness verification"
            )

    existing_by_fingerprint = {
        witness_verification_fingerprint(item): item
        for item in state.witness_verifications
    }
    existing_by_id = {
        item.verification_id: item for item in state.witness_verifications
    }
    existing_by_nonce = {
        item.witness.nonce: item for item in state.witness_verifications
    }
    additions: list[WitnessVerification] = []
    for verification in incoming:
        fingerprint = witness_verification_fingerprint(verification)
        collisions = tuple(
            item
            for item in (
                existing_by_id.get(verification.verification_id),
                existing_by_nonce.get(verification.witness.nonce),
            )
            if item is not None
        )
        if collisions:
            if any(
                witness_verification_fingerprint(item) != fingerprint
                for item in collisions
            ):
                raise GovernanceError(
                    "witness verification id/nonce collision is a safety violation"
                )
            continue
        if fingerprint in existing_by_fingerprint:
            continue
        additions.append(verification)
        existing_by_fingerprint[fingerprint] = verification
        existing_by_id[verification.verification_id] = verification
        existing_by_nonce[verification.witness.nonce] = verification
    if not additions:
        return _current_distributed_state_head(state)

    combined = _canonical_witness_verifications(
        (*state.witness_verifications, *additions)
    )
    findings = _witness_equivocation_findings(
        combined,
        profile=state.profile,
        target=state.target,
        epoch=state.epoch,
    )
    excluded = tuple(item.principal_cluster_id for item in findings)
    parent_ref = distributed_commit_state_fingerprint(state)
    request_ref = commit_payload_fingerprint(
        {
            "current_step": current,
            "parent_state_ref": parent_ref,
            "verification_refs": tuple(
                witness_verification_fingerprint(item) for item in additions
            ),
        },
        schema="pheroos-distributed-witness-record-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed state cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_ref:
            prior = cursor.transitions.get(parent_ref)
            if prior is not None and prior[0] == request_ref:
                return prior[1]
            raise GovernanceError("distributed witness state is stale or would fork")
        next_state = _replace_distributed_state(
            state,
            revision=state.revision + 1,
            current_step=current,
            previous_state_fingerprint=parent_ref,
            witness_verifications=combined,
            witness_receipt_root=_witness_receipt_root(
                tuple(witness_replay_receipt(item) for item in combined),
                profile=state.profile,
            ),
            equivocation_findings=findings,
            excluded_cluster_ids=excluded,
        )
        next_state = _issue_distributed_state(next_state, cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = distributed_commit_state_fingerprint(
            next_state
        )
        cursor.transitions[parent_ref] = (request_ref, next_state)
        return next_state


def distributed_commit_state_payload(
    state: DistributedCommitState,
) -> dict[str, object]:
    if type(state) is not DistributedCommitState:
        raise GovernanceError("distributed state must use the canonical record")
    _validate_distributed_commit_state(state)
    payload = _public_dataclass_payload(state)
    payload["membership_snapshot"] = portable_membership_snapshot_payload(
        state.membership_snapshot
    )
    payload["witness_verifications"] = tuple(
        witness_verification_payload(item) for item in state.witness_verifications
    )
    payload["equivocation_findings"] = tuple(
        _public_dataclass_payload(item) for item in state.equivocation_findings
    )
    payload["final_registrations"] = tuple(
        _public_dataclass_payload(item) for item in state.final_registrations
    )
    payload["conflict_findings"] = tuple(
        _public_dataclass_payload(item) for item in state.conflict_findings
    )
    return payload


def distributed_commit_state_fingerprint(state: DistributedCommitState) -> str:
    return commit_payload_fingerprint(
        distributed_commit_state_payload(state),
        schema=DISTRIBUTED_STATE_VERSION,
        profile=state.profile,
    )


def distributed_commit_state_from_payload(
    payload: Mapping[str, object],
) -> DistributedCommitState:
    values = _strict_dataclass_payload(
        payload,
        DistributedCommitState,
        "distributed state payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority"] = _coerce_authority(values["authority"])
    values["membership_snapshot"] = portable_membership_snapshot_from_payload(
        values["membership_snapshot"]
    )
    values["witness_verifications"] = tuple(
        witness_verification_from_payload(item)
        for item in _require_sequence(
            values["witness_verifications"],
            "distributed state witness verifications",
        )
    )
    values["equivocation_findings"] = tuple(
        _equivocation_finding_from_payload(item)
        for item in _require_sequence(
            values["equivocation_findings"],
            "distributed state equivocation findings",
        )
    )
    values["excluded_cluster_ids"] = tuple(
        _require_sequence(
            values["excluded_cluster_ids"],
            "distributed state excluded clusters",
        )
    )
    values["final_registrations"] = tuple(
        FinalCertificateRegistration(
            **_strict_dataclass_payload(
                item,
                FinalCertificateRegistration,
                "distributed final registration payload",
            )
        )
        for item in _require_sequence(
            values["final_registrations"],
            "distributed state final registrations",
        )
    )
    values["conflict_findings"] = tuple(
        _conflict_finding_from_payload(item)
        for item in _require_sequence(
            values["conflict_findings"],
            "distributed state conflict findings",
        )
    )
    try:
        return DistributedCommitState(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(f"distributed state payload is invalid: {exc}") from exc


def distributed_commit_state_is_authoritative(state: object) -> bool:
    if type(state) is not DistributedCommitState:
        return False
    try:
        issuance = state._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _DISTRIBUTED_STATE_ISSUANCE
            and issuance[1] == distributed_commit_state_fingerprint(state)
            and type(state._cursor) is _DistributedStateCursor
        )
    except Exception:
        return False


def distributed_commit_state_is_current(state: object) -> bool:
    if not distributed_commit_state_is_authoritative(state):
        return False
    assert type(state) is DistributedCommitState
    cursor = state._cursor
    assert type(cursor) is _DistributedStateCursor
    try:
        with cursor.lock:
            return (
                cursor.current_state is state
                and cursor.current_state_fingerprint
                == distributed_commit_state_fingerprint(state)
            )
    except Exception:
        return False


def issue_distributed_commit_certificate(
    state: DistributedCommitState,
    proposal: DistributedCommitProposal,
    *,
    verifications: Sequence[WitnessVerification],
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    certificate_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> DistributedCommitCertificate:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError(
            "distributed certificate requires the current authoritative state"
        )
    if state.frozen:
        raise GovernanceError("frozen distributed epoch cannot issue certificates")
    if state.transitioned:
        raise GovernanceError("transitioned distributed epoch cannot issue certificates")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "distributed certificate issuance requires governance authority"
        )
    current = require_commit_step(
        issued_at_step,
        "distributed certificate issued_at_step",
    )
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=state.profile,
        assurance=state.assurance,
        target=state.target,
        commit_policy_root=state.commit_policy_root,
    )
    if not verify_distributed_commit_proposal(
        proposal,
        commit_policy=commit_policy,
        portable_certificate=portable_certificate,
        membership_snapshot=state.membership_snapshot,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError("distributed proposal verification failed")
    _validate_proposal_state_binding(proposal, state)
    requested = _canonical_witness_verifications(verifications)
    if not requested:
        raise GovernanceError(
            "distributed certificate requires at least one verified witness"
        )
    recorded = {
        witness_verification_fingerprint(item): item
        for item in state.witness_verifications
    }
    excluded = set(state.excluded_cluster_ids)
    by_cluster: dict[str, WitnessVerification] = {}
    for verification in requested:
        fingerprint = witness_verification_fingerprint(verification)
        if (
            not witness_verification_is_authoritative(verification)
            or fingerprint not in recorded
        ):
            raise GovernanceError(
                "distributed certificate contains an unrecorded witness"
            )
        witness = verification.witness
        if (
            witness.proposal_digest != proposal.proposal_digest
            or witness.commit_value_root != proposal.commit_value_root
        ):
            raise GovernanceError(
                "distributed certificate witness signed another proposal"
            )
        if witness.principal_cluster_id in excluded:
            continue
        if not verify_portable_witness_verification(
            verification,
            membership_snapshot=state.membership_snapshot,
            trusted_witness_attestations=trusted_witness_attestations,
            issued_at_step=current,
        ):
            raise GovernanceError(
                "distributed certificate witness verification is not portable/fresh"
            )
        prior = by_cluster.get(witness.principal_cluster_id)
        if prior is None or witness_verification_fingerprint(verification) < (
            witness_verification_fingerprint(prior)
        ):
            by_cluster[witness.principal_cluster_id] = verification
    included = _canonical_witness_verifications(tuple(by_cluster.values()))
    if not included:
        raise GovernanceError(
            "all distributed certificate witnesses were excluded for equivocation"
        )
    failure_domains = {
        item.witness.failure_domain for item in included
    }
    status = (
        DistributedCertificateStatus.FINAL
        if (
            len(included) >= distributed.witness_quorum
            and len(failure_domains)
            >= distributed.minimum_failure_domain_diversity
        )
        else DistributedCertificateStatus.PROVISIONAL
    )
    body = {
        "schema_discriminator": (
            DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR
        ),
        "certificate_version": DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "certificate_id": require_commit_text(
            certificate_id,
            "distributed certificate certificate_id",
        ),
        "status": status,
        "profile": state.profile,
        "assurance": state.assurance,
        "manifest_root": state.manifest_root,
        "commit_policy_root": state.commit_policy_root,
        "protocol_id": state.protocol_id,
        "run_id": state.run_id,
        "target": state.target,
        "epoch": state.epoch,
        "candidate_id": proposal.candidate_id,
        "commit_value_root": proposal.commit_value_root,
        "proposal_digest": proposal.proposal_digest,
        "proposal": proposal,
        "membership_snapshot": state.membership_snapshot,
        "membership_snapshot_root": state.membership_snapshot_root,
        "membership_root": state.membership_root,
        "membership_size": state.membership_size,
        "max_byzantine_faults": state.max_byzantine_faults,
        "witness_quorum": state.witness_quorum,
        "minimum_failure_domain_diversity": (
            state.minimum_failure_domain_diversity
        ),
        "witnesses": included,
        "witness_root": _witness_verification_root(
            included,
            profile=state.profile,
            commit_value_root=proposal.commit_value_root,
            proposal_digest=proposal.proposal_digest,
        ),
        "excluded_cluster_ids": state.excluded_cluster_ids,
        "portable_certificate_ref": proposal.portable_certificate_ref,
        "portable_certificate_version": proposal.portable_certificate_version,
        "issuer_id": require_commit_text(
            issuer_id,
            "distributed certificate issuer_id",
        ),
        "authority": authority,
        "issued_at_step": current,
        "provenance": require_commit_text(
            provenance,
            "distributed certificate provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "distributed certificate trace_event_id",
        ),
    }
    body_root = _distributed_certificate_body_root(body, profile=state.profile)
    certificate_root = commit_payload_fingerprint(
        {
            "certificate_body_root": body_root,
            "commit_value_root": proposal.commit_value_root,
            "proposal_digest": proposal.proposal_digest,
            "witness_root": body["witness_root"],
        },
        schema="pheroos-distributed-commit-certificate-envelope-v1",
        profile=state.profile,
    )
    certificate = DistributedCommitCertificate(
        **body,
        certificate_body_root=body_root,
        certificate_root=certificate_root,
    )
    return _register_distributed_certificate_identity(certificate)


def assemble_portable_distributed_commit_certificate(
    proposal: DistributedCommitProposal | Mapping[str, object],
    membership_snapshot: PortableMembershipSnapshot,
    verifications: Sequence[WitnessVerification | Mapping[str, object]],
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    certificate_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> DistributedCommitCertificate:
    """Aggregate a portable peer proof without process-local state authority.

    This is required for independent verification and conflict ingestion.  It
    never mutates or authorizes a local epoch; callers must register a FINAL
    result in the strong local state before using it as current authority.
    """

    canonical_proposal = (
        proposal
        if type(proposal) is DistributedCommitProposal
        else distributed_commit_proposal_from_payload(proposal)
    )
    assert type(canonical_proposal) is DistributedCommitProposal
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "portable distributed certificate requires governance issuer metadata"
        )
    current = require_commit_step(
        issued_at_step,
        "portable distributed certificate issued_at_step",
    )
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=canonical_proposal.profile,
        assurance=canonical_proposal.assurance,
        target=canonical_proposal.target,
        commit_policy_root=canonical_proposal.commit_policy_root,
    )
    _validate_membership_policy(membership_snapshot, distributed)
    if not verify_distributed_commit_proposal(
        canonical_proposal,
        commit_policy=commit_policy,
        portable_certificate=portable_certificate,
        membership_snapshot=membership_snapshot,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError("portable distributed proposal verification failed")
    parsed = tuple(
        item
        if type(item) is WitnessVerification
        else witness_verification_from_payload(item)
        for item in verifications
    )
    canonical = _canonical_witness_verifications(parsed)
    if not canonical:
        raise GovernanceError("portable distributed certificate needs witnesses")
    by_cluster: dict[str, WitnessVerification] = {}
    for verification in canonical:
        witness = verification.witness
        if (
            witness.proposal_digest != canonical_proposal.proposal_digest
            or witness.commit_value_root != canonical_proposal.commit_value_root
        ):
            raise GovernanceError("portable witness signed another proposal")
        if not verify_portable_witness_verification(
            verification,
            membership_snapshot=membership_snapshot,
            trusted_witness_attestations=trusted_witness_attestations,
            issued_at_step=current,
        ):
            raise GovernanceError("portable witness verification failed")
        if witness.principal_cluster_id in by_cluster:
            raise GovernanceError("portable certificate repeats a witness cluster")
        by_cluster[witness.principal_cluster_id] = verification
    included = _canonical_witness_verifications(tuple(by_cluster.values()))
    status = (
        DistributedCertificateStatus.FINAL
        if (
            len(included) >= distributed.witness_quorum
            and len({item.witness.failure_domain for item in included})
            >= distributed.minimum_failure_domain_diversity
        )
        else DistributedCertificateStatus.PROVISIONAL
    )
    body = {
        "schema_discriminator": DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR,
        "certificate_version": DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "certificate_id": require_commit_text(
            certificate_id,
            "portable distributed certificate_id",
        ),
        "status": status,
        "profile": canonical_proposal.profile,
        "assurance": canonical_proposal.assurance,
        "manifest_root": canonical_proposal.manifest_root,
        "commit_policy_root": canonical_proposal.commit_policy_root,
        "protocol_id": canonical_proposal.protocol_id,
        "run_id": canonical_proposal.run_id,
        "target": canonical_proposal.target,
        "epoch": canonical_proposal.epoch,
        "candidate_id": canonical_proposal.candidate_id,
        "commit_value_root": canonical_proposal.commit_value_root,
        "proposal_digest": canonical_proposal.proposal_digest,
        "proposal": canonical_proposal,
        "membership_snapshot": membership_snapshot,
        "membership_snapshot_root": membership_snapshot.snapshot_fingerprint,
        "membership_root": membership_snapshot.membership_root,
        "membership_size": distributed.membership_size,
        "max_byzantine_faults": distributed.max_byzantine_faults,
        "witness_quorum": distributed.witness_quorum,
        "minimum_failure_domain_diversity": (
            distributed.minimum_failure_domain_diversity
        ),
        "witnesses": included,
        "witness_root": _witness_verification_root(
            included,
            profile=canonical_proposal.profile,
            commit_value_root=canonical_proposal.commit_value_root,
            proposal_digest=canonical_proposal.proposal_digest,
        ),
        "excluded_cluster_ids": (),
        "portable_certificate_ref": canonical_proposal.portable_certificate_ref,
        "portable_certificate_version": (
            canonical_proposal.portable_certificate_version
        ),
        "issuer_id": require_commit_text(
            issuer_id,
            "portable distributed issuer_id",
        ),
        "authority": authority,
        "issued_at_step": current,
        "provenance": require_commit_text(
            provenance,
            "portable distributed provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "portable distributed trace_event_id",
        ),
    }
    body_root = _distributed_certificate_body_root(
        body,
        profile=canonical_proposal.profile,
    )
    root = commit_payload_fingerprint(
        {
            "certificate_body_root": body_root,
            "commit_value_root": canonical_proposal.commit_value_root,
            "proposal_digest": canonical_proposal.proposal_digest,
            "witness_root": body["witness_root"],
        },
        schema="pheroos-distributed-commit-certificate-envelope-v1",
        profile=canonical_proposal.profile,
    )
    certificate = DistributedCommitCertificate(
        **body,
        certificate_body_root=body_root,
        certificate_root=root,
    )
    return _register_distributed_certificate_identity(certificate)


def distributed_commit_certificate_payload(
    certificate: DistributedCommitCertificate,
) -> dict[str, object]:
    if type(certificate) is not DistributedCommitCertificate:
        raise GovernanceError(
            "distributed certificate must use the canonical record"
        )
    _validate_distributed_commit_certificate(certificate)
    payload = _public_dataclass_payload(certificate)
    payload["proposal"] = distributed_commit_proposal_payload(
        certificate.proposal
    )
    payload["membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.membership_snapshot
    )
    payload["witnesses"] = tuple(
        witness_verification_payload(item) for item in certificate.witnesses
    )
    return payload


def distributed_commit_certificate_fingerprint(
    certificate: DistributedCommitCertificate,
) -> str:
    return commit_payload_fingerprint(
        distributed_commit_certificate_payload(certificate),
        schema=DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
        profile=certificate.profile,
    )


def distributed_commit_certificate_from_payload(
    payload: Mapping[str, object],
) -> DistributedCommitCertificate:
    values = _strict_dataclass_payload(
        payload,
        DistributedCommitCertificate,
        "distributed certificate payload",
    )
    values["status"] = _coerce_certificate_status(values["status"])
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority"] = _coerce_authority(values["authority"])
    values["proposal"] = distributed_commit_proposal_from_payload(
        values["proposal"]
    )
    values["membership_snapshot"] = portable_membership_snapshot_from_payload(
        values["membership_snapshot"]
    )
    values["witnesses"] = tuple(
        witness_verification_from_payload(item)
        for item in _require_sequence(
            values["witnesses"],
            "distributed certificate witnesses",
        )
    )
    values["excluded_cluster_ids"] = tuple(
        _require_sequence(
            values["excluded_cluster_ids"],
            "distributed certificate excluded clusters",
        )
    )
    try:
        return DistributedCommitCertificate(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"distributed certificate payload is invalid: {exc}"
        ) from exc


def verify_distributed_commit_certificate(
    certificate_or_payload: DistributedCommitCertificate | Mapping[str, object],
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    expected_certificate_ref: str = "",
    expected_proposal_digest: str = "",
    expected_commit_value_root: str = "",
    require_final: bool = True,
) -> bool:
    """Independently verify proposal, membership, witnesses and q intersection."""

    try:
        if type(require_final) is not bool:
            return False
        certificate = (
            certificate_or_payload
            if type(certificate_or_payload) is DistributedCommitCertificate
            else distributed_commit_certificate_from_payload(certificate_or_payload)
        )
        assert type(certificate) is DistributedCommitCertificate
        distributed = _validate_distributed_policy(
            commit_policy,
            profile=certificate.profile,
            assurance=certificate.assurance,
            target=certificate.target,
            commit_policy_root=certificate.commit_policy_root,
        )
        if not verify_distributed_commit_proposal(
            certificate.proposal,
            commit_policy=commit_policy,
            portable_certificate=portable_certificate,
            membership_snapshot=certificate.membership_snapshot,
            trusted_issuer_attestations=trusted_issuer_attestations,
            expected_proposal_digest=certificate.proposal_digest,
            expected_commit_value_root=certificate.commit_value_root,
        ):
            return False
        if certificate.membership_size != distributed.membership_size:
            return False
        if certificate.max_byzantine_faults != distributed.max_byzantine_faults:
            return False
        if certificate.witness_quorum != distributed.witness_quorum:
            return False
        if certificate.minimum_failure_domain_diversity != (
            distributed.minimum_failure_domain_diversity
        ):
            return False
        if not _quorum_intersection_is_safe(
            certificate.membership_size,
            certificate.max_byzantine_faults,
            certificate.witness_quorum,
        ):
            return False
        excluded = set(certificate.excluded_cluster_ids)
        cluster_ids: set[str] = set()
        failure_domains: set[str] = set()
        for verification in certificate.witnesses:
            witness = verification.witness
            if (
                witness.proposal_digest != certificate.proposal_digest
                or witness.commit_value_root != certificate.commit_value_root
                or witness.target != certificate.target
                or witness.candidate_id != certificate.candidate_id
                or witness.epoch != certificate.epoch
                or witness.membership_root != certificate.membership_root
                or witness.principal_cluster_id in excluded
                or witness.principal_cluster_id in cluster_ids
            ):
                return False
            if not verify_portable_witness_verification(
                verification,
                membership_snapshot=certificate.membership_snapshot,
                trusted_witness_attestations=trusted_witness_attestations,
                issued_at_step=certificate.issued_at_step,
            ):
                return False
            cluster_ids.add(witness.principal_cluster_id)
            failure_domains.add(witness.failure_domain)
        meets_finality = bool(
            len(cluster_ids) >= certificate.witness_quorum
            and len(failure_domains)
            >= certificate.minimum_failure_domain_diversity
        )
        if certificate.status is DistributedCertificateStatus.FINAL:
            if not meets_finality:
                return False
        elif meets_finality:
            # A fully qualified proof cannot be mislabeled provisional.
            return False
        if require_final and certificate.status is not DistributedCertificateStatus.FINAL:
            return False
        if expected_certificate_ref and (
            distributed_commit_certificate_fingerprint(certificate)
            != require_commit_fingerprint(
                expected_certificate_ref,
                "expected distributed certificate ref",
            )
        ):
            return False
        if expected_proposal_digest and certificate.proposal_digest != (
            require_commit_fingerprint(
                expected_proposal_digest,
                "expected distributed proposal digest",
            )
        ):
            return False
        if expected_commit_value_root and certificate.commit_value_root != (
            require_commit_fingerprint(
                expected_commit_value_root,
                "expected distributed commit value root",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def register_distributed_commit_certificate(
    state: DistributedCommitState,
    certificate: DistributedCommitCertificate,
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    current_step: int,
) -> DistributedCommitState:
    """Register final proofs and freeze on any same-epoch conflicting proof."""

    if not distributed_commit_state_is_authoritative(state):
        raise GovernanceError("distributed certificate registry state is forged")
    current = require_commit_step(
        current_step,
        "distributed certificate registration current_step",
    )
    if current < state.current_step:
        raise GovernanceError("distributed certificate registration moves backwards")
    if state.transitioned:
        raise GovernanceError("transitioned epoch cannot register final certificates")
    if not verify_distributed_commit_certificate(
        certificate,
        commit_policy=commit_policy,
        portable_certificate=portable_certificate,
        trusted_issuer_attestations=trusted_issuer_attestations,
        trusted_witness_attestations=trusted_witness_attestations,
        require_final=True,
    ):
        raise GovernanceError("distributed final certificate verification failed")
    _validate_certificate_state_binding(certificate, state)
    certificate_ref = distributed_commit_certificate_fingerprint(certificate)
    registration = FinalCertificateRegistration(
        certificate_ref=certificate_ref,
        commit_value_root=certificate.commit_value_root,
        proposal_digest=certificate.proposal_digest,
        candidate_id=certificate.candidate_id,
        registered_at_step=current,
    )
    existing = {item.certificate_ref: item for item in state.final_registrations}
    if certificate_ref in existing:
        current_head = _current_distributed_state_head(state)
        if not any(
            item.certificate_ref == certificate_ref
            and item.commit_value_root == certificate.commit_value_root
            and item.proposal_digest == certificate.proposal_digest
            for item in current_head.final_registrations
        ):
            raise GovernanceError(
                "distributed certificate replay is absent from the current head"
            )
        return current_head
    registrations = tuple((*state.final_registrations, registration))
    commit_value_roots = {item.commit_value_root for item in registrations}
    conflict_findings = state.conflict_findings
    frozen = state.frozen
    if len(commit_value_roots) > 1:
        frozen = True
        finding = _certificate_conflict_finding(
            registrations,
            profile=state.profile,
            target=state.target,
            epoch=state.epoch,
            current_step=current,
        )
        conflict_findings = tuple(
            sorted(
                {item.finding_id: item for item in (*conflict_findings, finding)}.values(),
                key=lambda item: item.finding_id,
            )
        )
    parent_ref = distributed_commit_state_fingerprint(state)
    request_ref = commit_payload_fingerprint(
        {
            "certificate_ref": certificate_ref,
            "current_step": current,
            "parent_state_ref": parent_ref,
        },
        schema="pheroos-distributed-certificate-registration-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed certificate state cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_ref:
            prior = cursor.transitions.get(parent_ref)
            if prior is not None and prior[0] == request_ref:
                return prior[1]
            raise GovernanceError("distributed certificate state is stale or would fork")
        next_state = _replace_distributed_state(
            state,
            revision=state.revision + 1,
            current_step=current,
            previous_state_fingerprint=parent_ref,
            final_registrations=registrations,
            conflict_findings=conflict_findings,
            frozen=frozen,
        )
        next_state = _issue_distributed_state(next_state, cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = distributed_commit_state_fingerprint(
            next_state
        )
        cursor.transitions[parent_ref] = (request_ref, next_state)
        return next_state


def distributed_commit_certificate_is_current_final(
    certificate: object,
    state: object,
) -> bool:
    if (
        type(certificate) is not DistributedCommitCertificate
        or type(state) is not DistributedCommitState
    ):
        return False
    try:
        certificate_ref = distributed_commit_certificate_fingerprint(certificate)
        return bool(
            certificate.status is DistributedCertificateStatus.FINAL
            and distributed_commit_state_is_current(state)
            and not state.frozen
            and not state.transitioned
            and any(
                item.certificate_ref == certificate_ref
                and item.commit_value_root == certificate.commit_value_root
                and item.proposal_digest == certificate.proposal_digest
                for item in state.final_registrations
            )
        )
    except GovernanceError:
        return False


def verify_distributed_commit_finality(
    certificate: DistributedCommitCertificate,
    state: DistributedCommitState,
    receipt: LocalCommitReceipt,
    *,
    current_step: int,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
):
    """Issue typed finality from a current registered FINAL proof."""

    if not distributed_commit_certificate_is_current_final(certificate, state):
        raise GovernanceError(
            "distributed finality verification requires current registered FINAL proof"
        )
    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError("distributed finality receipt is not authoritative")
    _validate_receipt_state_binding(receipt, state)
    proposal = certificate.proposal
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    if proposal.local_receipt_ref != receipt_ref:
        raise GovernanceError("distributed finality local receipt lineage mismatch")
    current = require_commit_step(
        current_step,
        "distributed finality verified_at_step",
    )
    if current < certificate.issued_at_step:
        raise GovernanceError("distributed finality certificate is from the future")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("distributed finality verifier lacks authority")
    from pheroos.governance.commit_state import (
        CommitFinalityStatus,
        _issue_commit_finality_verification,
    )

    return _issue_commit_finality_verification(
        status=CommitFinalityStatus.VERIFIED,
        certificate_kind=DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR,
        certificate_ref=distributed_commit_certificate_fingerprint(certificate),
        profile=proposal.profile,
        assurance=proposal.assurance,
        manifest_root=proposal.manifest_root,
        commit_policy_root=proposal.commit_policy_root,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        candidate_id=proposal.candidate_id,
        context_ref=proposal.context_root,
        assessment_ref=proposal.assessment_root,
        window_state_ref=proposal.window_state_root,
        window_root=proposal.window_root,
        risk_assessment_root=proposal.risk_assessment_root,
        risk_chain_state_root=proposal.risk_chain_state_root,
        risk_policy_root=proposal.risk_policy_root,
        membership_root=proposal.membership_root,
        membership_snapshot_root=proposal.membership_snapshot_root,
        membership_epoch_state_root=proposal.membership_epoch_state_root,
        threshold_root=proposal.threshold_root,
        replay_state_ref=proposal.replay_state_root,
        replay_root=proposal.replay_root,
        support_replay_state_root=proposal.support_replay_state_root,
        support_replay_root=proposal.support_replay_root,
        collective_evidence_root=proposal.evidence_root,
        collective_challenge_root=proposal.challenge_root,
        collective_lease_root=proposal.lease_root,
        candidate_evidence_root=proposal.candidate_evidence_root,
        candidate_challenge_root=proposal.candidate_challenge_root,
        candidate_lease_root=proposal.candidate_lease_root,
        stop_resolution_root=proposal.stop_resolution_root,
        permission_root=proposal.permission_root,
        verified_at_step=current,
        verifier_id=require_commit_text(
            verifier_id,
            "distributed finality verifier_id",
        ),
        authority=authority,
        provenance=require_commit_text(
            provenance,
            "distributed finality provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "distributed finality trace_event_id",
        ),
    )


def epoch_transition_decision_ref(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    declared_recovery_ref: str = "",
) -> str:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError("epoch transition requires the current state")
    _validate_new_epoch_membership(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        current_step=new_membership_snapshot.issued_at_step,
    )
    recovery_ref = (
        require_commit_fingerprint(
            declared_recovery_ref,
            "epoch transition declared_recovery_ref",
        )
        if declared_recovery_ref
        else ""
    )
    if state.frozen and not recovery_ref:
        raise GovernanceError(
            "frozen epoch transition requires a declared recovery reference"
        )
    return commit_payload_fingerprint(
        {
            "declared_recovery_ref": recovery_ref,
            "new_epoch": new_membership_snapshot.epoch,
            "new_membership_epoch_state_root": (
                eligible_membership_epoch_state_fingerprint(
                    new_membership_epoch_state
                )
            ),
            "new_membership_snapshot_root": (
                eligible_principal_snapshot_fingerprint(new_membership_snapshot)
            ),
            "previous_state_ref": distributed_commit_state_fingerprint(state),
            "recovery_required": state.frozen,
            "target": state.target,
        },
        schema="pheroos-epoch-transition-decision-v1",
        profile=state.profile,
    )


def epoch_transition_certificate_body_root(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    transition_stop: StopResolutionVerification,
    transition_permission: ActionPermission,
    *,
    commit_policy: CollectiveCommitPolicy,
    certificate_id: str,
    declared_recovery_ref: str = "",
    recovery_stop: StopResolutionVerification | None = None,
    recovery_permission: ActionPermission | None = None,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> str:
    body = _epoch_transition_body_from_inputs(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=commit_policy,
        certificate_id=certificate_id,
        declared_recovery_ref=declared_recovery_ref,
        recovery_stop=recovery_stop,
        recovery_permission=recovery_permission,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    return _epoch_transition_body_root(body, profile=state.profile)


def issue_epoch_transition_certificate(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    transition_stop: StopResolutionVerification,
    transition_permission: ActionPermission,
    *,
    commit_policy: CollectiveCommitPolicy,
    certificate_id: str,
    declared_recovery_ref: str = "",
    recovery_stop: StopResolutionVerification | None = None,
    recovery_permission: ActionPermission | None = None,
    issuer_attestation_refs: Sequence[str],
    trusted_issuer_attestations: Mapping[str, str],
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> EpochTransitionCertificate:
    body = _epoch_transition_body_from_inputs(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=commit_policy,
        certificate_id=certificate_id,
        declared_recovery_ref=declared_recovery_ref,
        recovery_stop=recovery_stop,
        recovery_permission=recovery_permission,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    body_root = _epoch_transition_body_root(body, profile=state.profile)
    attestations = _require_attestation_bindings(
        issuer_attestation_refs,
        trusted_issuer_attestations,
        body_root,
        field_name="epoch transition certificate",
    )
    certificate_root = commit_payload_fingerprint(
        {
            "certificate_body_root": body_root,
            "issuer_attestation_refs": attestations,
        },
        schema="pheroos-epoch-transition-certificate-envelope-v1",
        profile=state.profile,
    )
    certificate = EpochTransitionCertificate(
        **body,
        issuer_attestation_refs=attestations,
        certificate_body_root=body_root,
        certificate_root=certificate_root,
    )
    return _register_epoch_transition_certificate_identity(certificate)


def epoch_transition_certificate_payload(
    certificate: EpochTransitionCertificate,
) -> dict[str, object]:
    if type(certificate) is not EpochTransitionCertificate:
        raise GovernanceError(
            "epoch transition certificate must use the canonical record"
        )
    _validate_epoch_transition_certificate(certificate)
    payload = _public_dataclass_payload(certificate)
    payload["new_membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.new_membership_snapshot
    )
    return payload


def epoch_transition_certificate_fingerprint(
    certificate: EpochTransitionCertificate,
) -> str:
    return commit_payload_fingerprint(
        epoch_transition_certificate_payload(certificate),
        schema=EPOCH_TRANSITION_CERTIFICATE_VERSION,
        profile=certificate.profile,
    )


def epoch_transition_certificate_from_payload(
    payload: Mapping[str, object],
) -> EpochTransitionCertificate:
    values = _strict_dataclass_payload(
        payload,
        EpochTransitionCertificate,
        "epoch transition certificate payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority"] = _coerce_authority(values["authority"])
    values["new_membership_snapshot"] = (
        portable_membership_snapshot_from_payload(
            values["new_membership_snapshot"]
        )
    )
    values["issuer_attestation_refs"] = tuple(
        _require_sequence(
            values["issuer_attestation_refs"],
            "epoch transition issuer attestations",
        )
    )
    try:
        return EpochTransitionCertificate(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"epoch transition certificate payload is invalid: {exc}"
        ) from exc


def verify_epoch_transition_certificate(
    certificate_or_payload: EpochTransitionCertificate | Mapping[str, object],
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_issuer_attestations: Mapping[str, str],
    expected_certificate_ref: str = "",
) -> bool:
    try:
        certificate = (
            certificate_or_payload
            if type(certificate_or_payload) is EpochTransitionCertificate
            else epoch_transition_certificate_from_payload(certificate_or_payload)
        )
        assert type(certificate) is EpochTransitionCertificate
        distributed = _validate_distributed_policy(
            commit_policy,
            profile=certificate.profile,
            assurance=certificate.assurance,
            target=certificate.target,
            commit_policy_root=certificate.commit_policy_root,
        )
        _validate_membership_policy(
            certificate.new_membership_snapshot,
            distributed,
        )
        if certificate.declared_transition_rule != distributed.epoch_transition_rule:
            return False
        if not all(
            trusted_issuer_attestations.get(reference)
            == certificate.certificate_body_root
            for reference in certificate.issuer_attestation_refs
        ):
            return False
        if expected_certificate_ref and (
            epoch_transition_certificate_fingerprint(certificate)
            != require_commit_fingerprint(
                expected_certificate_ref,
                "expected epoch transition certificate ref",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def transition_distributed_commit_epoch(
    state: DistributedCommitState,
    certificate: EpochTransitionCertificate,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_issuer_attestations: Mapping[str, str],
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> tuple[DistributedCommitState, DistributedCommitState]:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError("epoch transition state is not current")
    if not verify_epoch_transition_certificate(
        certificate,
        commit_policy=commit_policy,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError("epoch transition certificate verification failed")
    certificate_ref = epoch_transition_certificate_fingerprint(certificate)
    if (
        certificate.prior_state_ref != distributed_commit_state_fingerprint(state)
        or certificate.previous_epoch != state.epoch
        or certificate.previous_membership_root != state.membership_root
        or certificate.recovery_required is not state.frozen
        or certificate.new_membership_snapshot_root
        != eligible_principal_snapshot_fingerprint(new_membership_snapshot)
        or certificate.new_membership_epoch_state_root
        != eligible_membership_epoch_state_fingerprint(new_membership_epoch_state)
    ):
        raise GovernanceError("epoch transition lineage mismatch")
    parent_ref = distributed_commit_state_fingerprint(state)
    request_ref = commit_payload_fingerprint(
        {
            "certificate_ref": certificate_ref,
            "parent_state_ref": parent_ref,
        },
        schema="pheroos-distributed-epoch-transition-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed epoch state cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_ref:
            prior = cursor.transitions.get(parent_ref)
            if prior is not None and prior[0] == request_ref:
                transitioned = prior[1]
            else:
                raise GovernanceError("distributed epoch state is stale or would fork")
        else:
            transitioned = _replace_distributed_state(
                state,
                revision=state.revision + 1,
                current_step=certificate.issued_at_step,
                previous_state_fingerprint=parent_ref,
                transitioned=True,
                epoch_transition_certificate_ref=certificate_ref,
            )
            transitioned = _issue_distributed_state(transitioned, cursor)
            cursor.current_state = transitioned
            cursor.current_state_fingerprint = distributed_commit_state_fingerprint(
                transitioned
            )
            cursor.transitions[parent_ref] = (request_ref, transitioned)
    new_state = initialize_distributed_commit_state(
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        current_step=certificate.issued_at_step,
        issuer_id=issuer_id,
        authority=authority,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    return transitioned, new_state


def evaluate_distributed_finality(
    state: DistributedCommitState,
    receipt: LocalCommitReceipt,
    *,
    certificate: DistributedCommitCertificate | None,
    current_step: int,
    outcome: DecisionOutcome | None = None,
) -> DistributedFinalityDecision:
    """Bridge distributed proof ordering into bounded liveness without a truth cycle.

    Pre-terminal ordering is receipt -> distributed certificate -> liveness
    input. A later authoritative outcome can be supplied to verify that liveness
    used the exact final certificate, or that a deadline terminal remained a
    non-commit.
    """

    if not distributed_commit_state_is_current(state):
        raise GovernanceError("distributed finality requires current state")
    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError("distributed finality requires local receipt")
    _validate_receipt_state_binding(receipt, state)
    current = require_commit_step(
        current_step,
        "distributed finality current_step",
    )
    if current < state.current_step:
        raise GovernanceError("distributed finality cannot move backwards")
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    certificate_ref = ""
    candidate_id = receipt.candidate_id
    reasons: tuple[str, ...]
    if state.frozen:
        kind = DistributedFinalityKind.SAFETY_VIOLATION
        terminal = outcome is not None
        authoritative_commit = False
        reasons = ("distributed_epoch_frozen",)
    elif certificate is None:
        kind = DistributedFinalityKind.PENDING
        terminal = False
        authoritative_commit = False
        reasons = ("distributed_witness_quorum_pending",)
    else:
        certificate_ref = distributed_commit_certificate_fingerprint(certificate)
        _validate_certificate_state_binding(certificate, state)
        if certificate.proposal.local_receipt_ref != receipt_ref:
            raise GovernanceError(
                "distributed certificate does not bind the supplied local receipt"
            )
        if certificate.status is DistributedCertificateStatus.PROVISIONAL:
            kind = DistributedFinalityKind.PROVISIONAL
            terminal = False
            authoritative_commit = False
            reasons = ("distributed_certificate_provisional",)
        elif distributed_commit_certificate_is_current_final(certificate, state):
            kind = DistributedFinalityKind.FINAL
            terminal = False
            authoritative_commit = True
            reasons = ("distributed_finality_verified",)
        else:
            raise GovernanceError(
                "distributed final certificate is not registered/current"
            )

    outcome_ref = ""
    if outcome is not None:
        if not decision_outcome_is_authoritative(outcome):
            raise GovernanceError(
                "distributed finality outcome is not governance-issued"
            )
        _validate_outcome_state_binding(outcome, state)
        outcome_ref = decision_outcome_fingerprint(outcome)
        terminal = True
        if outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
            if (
                kind is not DistributedFinalityKind.FINAL
                or not certificate_ref
                or outcome.certificate_ref != certificate_ref
                or outcome.candidate_id != candidate_id
                or not outcome.authoritative_commit
                or not outcome.epistemically_committed
            ):
                raise GovernanceError(
                    "distributed evidence outcome lacks exact final certificate lineage"
                )
            authoritative_commit = True
            reasons = ("distributed_evidence_outcome_verified",)
        elif outcome.kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE:
            if current < min(
                outcome.absolute_deadline_step,
                outcome.absolute_run_deadline_step,
            ):
                raise GovernanceError(
                    "finality_unavailable cannot be terminal before the deadline"
                )
            if certificate is not None and (
                certificate.status is DistributedCertificateStatus.FINAL
            ):
                raise GovernanceError(
                    "finality_unavailable cannot hide a final certificate"
                )
            if outcome.authoritative_commit or outcome.epistemically_committed:
                raise GovernanceError(
                    "finality_unavailable cannot claim commit authority"
                )
            kind = DistributedFinalityKind.FINALITY_UNAVAILABLE
            authoritative_commit = False
            certificate_ref = ""
            reasons = ("distributed_finality_deadline_unavailable",)
        elif outcome.kind is DecisionOutcomeKind.SAFETY_VIOLATION:
            kind = DistributedFinalityKind.SAFETY_VIOLATION
            authoritative_commit = False
            reasons = ("distributed_safety_outcome_verified",)
        else:
            if outcome.authoritative_commit or outcome.epistemically_committed:
                raise GovernanceError(
                    "non-evidence distributed outcome cannot claim commit"
                )
            kind = DistributedFinalityKind.NON_COMMIT_TERMINAL
            authoritative_commit = False
            certificate_ref = ""
            reasons = (f"distributed_non_commit_{outcome.kind.value}",)

    decision = DistributedFinalityDecision(
        decision_version=DISTRIBUTED_FINALITY_DECISION_VERSION,
        kind=kind,
        terminal=terminal,
        authoritative_commit=authoritative_commit,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        candidate_id=candidate_id,
        state_ref=distributed_commit_state_fingerprint(state),
        local_receipt_ref=receipt_ref,
        distributed_certificate_ref=certificate_ref,
        outcome_ref=outcome_ref,
        reason_codes=reasons,
        current_step=current,
    )
    object.__setattr__(
        decision,
        "_issuance",
        (_FINALITY_DECISION_ISSUANCE, distributed_finality_decision_fingerprint(decision)),
    )
    return decision


def distributed_finality_decision_payload(
    decision: DistributedFinalityDecision,
) -> dict[str, object]:
    if type(decision) is not DistributedFinalityDecision:
        raise GovernanceError("distributed finality decision must be canonical")
    _validate_distributed_finality_decision(decision)
    return _public_dataclass_payload(decision)


def distributed_finality_decision_fingerprint(
    decision: DistributedFinalityDecision,
) -> str:
    return commit_payload_fingerprint(
        distributed_finality_decision_payload(decision),
        schema=DISTRIBUTED_FINALITY_DECISION_VERSION,
        profile=decision.profile,
    )


def distributed_finality_decision_from_payload(
    payload: Mapping[str, object],
) -> DistributedFinalityDecision:
    values = _strict_dataclass_payload(
        payload,
        DistributedFinalityDecision,
        "distributed finality decision payload",
    )
    values["kind"] = _coerce_finality_kind(values["kind"])
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["reason_codes"] = tuple(
        _require_sequence(
            values["reason_codes"],
            "distributed finality reason codes",
        )
    )
    try:
        return DistributedFinalityDecision(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"distributed finality decision payload is invalid: {exc}"
        ) from exc


def distributed_finality_decision_is_authoritative(decision: object) -> bool:
    if type(decision) is not DistributedFinalityDecision:
        return False
    try:
        issuance = decision._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _FINALITY_DECISION_ISSUANCE
            and issuance[1] == distributed_finality_decision_fingerprint(decision)
        )
    except Exception:
        return False


def _validate_portable_membership_snapshot(
    snapshot: PortableMembershipSnapshot,
) -> None:
    if snapshot.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("portable membership profile is not distributed")
    if snapshot.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("portable membership assurance is not distributed")
    for name in (
        "snapshot_id",
        "protocol_id",
        "run_id",
        "target",
        "issuer_id",
        "membership_method",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(snapshot, name),
            f"portable membership {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "membership_root",
        "snapshot_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(snapshot, name),
            f"portable membership {name}",
        )
    require_commit_step(snapshot.epoch, "portable membership epoch")
    issued = require_commit_step(
        snapshot.issued_at_step,
        "portable membership issued_at_step",
    )
    expires = require_commit_step(
        snapshot.expires_at_step,
        "portable membership expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("portable membership expiry must follow issuance")
    if type(snapshot.authority) is not AuthorityLevel or not can_verify(
        snapshot.authority
    ):
        raise GovernanceError("portable membership issuer lacks authority")
    expected_snapshot = commit_payload_fingerprint(
        _portable_snapshot_payload_unchecked(snapshot),
        schema="pheroos-eligible-principal-snapshot-v1",
        profile=snapshot.profile,
    )
    if snapshot.snapshot_fingerprint != expected_snapshot:
        raise GovernanceError("portable membership snapshot root is invalid")
    expected_membership = commit_payload_fingerprint(
        {
            "assurance": snapshot.assurance,
            "commit_policy_root": snapshot.commit_policy_root,
            "eligible_clusters": _portable_clusters_payload(snapshot),
            "epoch": snapshot.epoch,
            "manifest_root": snapshot.manifest_root,
            "protocol_id": snapshot.protocol_id,
            "run_id": snapshot.run_id,
            "target": snapshot.target,
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=snapshot.profile,
    )
    if snapshot.membership_root != expected_membership:
        raise GovernanceError("portable membership root is invalid")


def _portable_clusters_payload(
    snapshot: PortableMembershipSnapshot,
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
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
        for cluster in snapshot.eligible_clusters
    )


def _portable_snapshot_payload_unchecked(
    snapshot: PortableMembershipSnapshot,
) -> dict[str, object]:
    return {
        "assurance": snapshot.assurance,
        "authority": snapshot.authority,
        "commit_policy_root": snapshot.commit_policy_root,
        "eligible_clusters": _portable_clusters_payload(snapshot),
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


def _validate_distributed_commit_proposal(
    proposal: DistributedCommitProposal,
) -> None:
    if proposal.proposal_version != DISTRIBUTED_PROPOSAL_VERSION:
        raise GovernanceError("distributed proposal version is unsupported")
    if proposal.wire_version != COMMIT_WIRE_VERSION:
        raise GovernanceError("distributed proposal wire version is unsupported")
    if proposal.canonicalization != COMMIT_CANONICAL_VERSION:
        raise GovernanceError(
            "distributed proposal canonicalization is unsupported"
        )
    if proposal.hash_algorithm != "sha256":
        raise GovernanceError("distributed proposal hash algorithm is unsupported")
    if proposal.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed proposal profile is invalid")
    if proposal.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed proposal assurance is invalid")
    for name in (
        "proposal_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
    ):
        require_commit_text(
            getattr(proposal, name),
            f"distributed proposal {name}",
        )
    for name in _PROPOSAL_ROOT_FIELDS:
        require_commit_fingerprint(
            getattr(proposal, name),
            f"distributed proposal {name}",
        )
    require_commit_step(proposal.epoch, "distributed proposal epoch")
    require_commit_step(
        proposal.proposed_at_step,
        "distributed proposal proposed_at_step",
    )
    if proposal.portable_certificate_version != EVIDENCE_COMMIT_CERTIFICATE_VERSION:
        raise GovernanceError(
            "distributed proposal portable certificate version is unsupported"
        )
    if proposal.local_receipt_version != LOCAL_COMMIT_RECEIPT_VERSION:
        raise GovernanceError(
            "distributed proposal local receipt version is unsupported"
        )
    expected_value_root = _distributed_commit_value_root_from_mapping(
        _public_dataclass_payload(proposal)
    )
    if proposal.commit_value_root != expected_value_root:
        raise GovernanceError("distributed proposal commit value root is invalid")
    expected = commit_payload_fingerprint(
        _distributed_proposal_body_payload(proposal),
        schema=DISTRIBUTED_PROPOSAL_VERSION,
        profile=proposal.profile,
    )
    if proposal.proposal_digest != expected:
        raise GovernanceError("distributed proposal digest is invalid")


_PROPOSAL_ROOT_FIELDS = (
    "manifest_root",
    "commit_policy_root",
    "claim_fingerprint",
    "output_payload_fingerprint",
    "risk_chain_state_root",
    "risk_assessment_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "membership_root",
    "replay_state_root",
    "replay_root",
    "support_replay_state_root",
    "support_replay_root",
    "candidate_evidence_root",
    "candidate_challenge_root",
    "candidate_lease_root",
    "evidence_root",
    "challenge_root",
    "lease_root",
    "window_state_root",
    "window_root",
    "threshold_root",
    "stop_resolution_root",
    "permission_root",
    "context_root",
    "assessment_root",
    "local_receipt_ref",
    "portable_certificate_ref",
    "commit_value_root",
    "proposal_digest",
)


_DISTRIBUTED_COMMIT_VALUE_FIELDS = (
    "wire_version",
    "canonicalization",
    "hash_algorithm",
    "profile",
    "assurance",
    "manifest_root",
    "commit_policy_root",
    "protocol_id",
    "run_id",
    "target",
    "epoch",
    "candidate_id",
    "claim_fingerprint",
    "output_payload_fingerprint",
    "risk_chain_state_root",
    "risk_assessment_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "membership_root",
    "replay_state_root",
    "replay_root",
    "support_replay_state_root",
    "support_replay_root",
    "candidate_evidence_root",
    "candidate_challenge_root",
    "candidate_lease_root",
    "evidence_root",
    "challenge_root",
    "lease_root",
    "window_state_root",
    "window_root",
    "threshold_root",
    "stop_resolution_root",
    "permission_root",
    "context_root",
    "assessment_root",
    "local_receipt_version",
    "portable_certificate_version",
)


def _distributed_commit_value_payload_from_mapping(
    values: Mapping[str, object],
) -> dict[str, object]:
    try:
        return {
            "value_version": DISTRIBUTED_COMMIT_VALUE_VERSION,
            **{name: values[name] for name in _DISTRIBUTED_COMMIT_VALUE_FIELDS},
        }
    except KeyError as exc:
        raise GovernanceError(
            f"distributed commit value is missing {exc.args[0]}"
        ) from exc


def _validate_distributed_commit_value_payload(
    value: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise GovernanceError("distributed commit value payload must be a mapping")
    expected = {"value_version", *_DISTRIBUTED_COMMIT_VALUE_FIELDS}
    observed = set(value)
    if observed != expected:
        raise GovernanceError(
            "distributed commit value payload keys mismatch; "
            f"missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )
    payload = dict(value)
    if payload["value_version"] != DISTRIBUTED_COMMIT_VALUE_VERSION:
        raise GovernanceError("distributed commit value version is unsupported")
    if payload["wire_version"] != COMMIT_WIRE_VERSION:
        raise GovernanceError("distributed commit value wire version is unsupported")
    if payload["canonicalization"] != COMMIT_CANONICAL_VERSION:
        raise GovernanceError(
            "distributed commit value canonicalization is unsupported"
        )
    if payload["hash_algorithm"] != "sha256":
        raise GovernanceError("distributed commit value hash algorithm is unsupported")
    require_commit_profile(payload["profile"], "distributed commit value profile")
    if payload["profile"] != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed commit value profile is invalid")
    assurance = _coerce_assurance(payload["assurance"])
    if assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed commit value assurance is invalid")
    payload["assurance"] = assurance
    for name in ("protocol_id", "run_id", "target", "candidate_id"):
        require_commit_text(payload[name], f"distributed commit value {name}")
    require_commit_step(payload["epoch"], "distributed commit value epoch")
    fingerprint_fields = {
        name
        for name in _DISTRIBUTED_COMMIT_VALUE_FIELDS
        if name.endswith("_root")
        or name in {"claim_fingerprint", "output_payload_fingerprint"}
    }
    for name in sorted(fingerprint_fields):
        require_commit_fingerprint(
            payload[name],
            f"distributed commit value {name}",
        )
    if payload["local_receipt_version"] != LOCAL_COMMIT_RECEIPT_VERSION:
        raise GovernanceError(
            "distributed commit value local receipt version is unsupported"
        )
    if payload["portable_certificate_version"] != (
        EVIDENCE_COMMIT_CERTIFICATE_VERSION
    ):
        raise GovernanceError(
            "distributed commit value portable certificate version is unsupported"
        )
    return payload


def _distributed_commit_value_root_from_mapping(
    values: Mapping[str, object],
) -> str:
    payload = _validate_distributed_commit_value_payload(
        _distributed_commit_value_payload_from_mapping(values)
    )
    profile = payload["profile"]
    if type(profile) is not str:
        raise GovernanceError("distributed commit value profile is invalid")
    return commit_payload_fingerprint(
        payload,
        schema=DISTRIBUTED_COMMIT_VALUE_VERSION,
        profile=profile,
    )


def _distributed_proposal_body_payload(
    proposal: DistributedCommitProposal,
) -> dict[str, object]:
    payload = _public_dataclass_payload(proposal)
    payload.pop("proposal_digest")
    return payload


def _distributed_proposal_body_from_receipt(
    receipt: LocalCommitReceipt,
    *,
    portable_certificate: EvidenceCommitCertificate,
    proposal_id: str,
    proposed_at_step: int,
) -> dict[str, object]:
    return {
        "proposal_version": DISTRIBUTED_PROPOSAL_VERSION,
        "wire_version": receipt.wire_version,
        "canonicalization": receipt.canonicalization,
        "hash_algorithm": receipt.hash_algorithm,
        "proposal_id": require_commit_text(
            proposal_id,
            "distributed proposal proposal_id",
        ),
        "profile": receipt.profile,
        "assurance": receipt.assurance,
        "manifest_root": receipt.manifest_root,
        "commit_policy_root": receipt.commit_policy_root,
        "protocol_id": receipt.protocol_id,
        "run_id": receipt.run_id,
        "target": receipt.target,
        "epoch": receipt.epoch,
        "candidate_id": receipt.candidate_id,
        "claim_fingerprint": receipt.claim_fingerprint,
        "output_payload_fingerprint": receipt.output_payload_fingerprint,
        "risk_chain_state_root": receipt.risk_chain_state_root,
        "risk_assessment_root": receipt.risk_assessment_root,
        "risk_policy_root": receipt.risk_policy_root,
        "membership_snapshot_root": receipt.membership_snapshot_root,
        "membership_epoch_state_root": receipt.membership_epoch_state_root,
        "membership_root": receipt.membership_root,
        "replay_state_root": receipt.replay_state_root,
        "replay_root": receipt.replay_root,
        "support_replay_state_root": receipt.support_replay_state_root,
        "support_replay_root": receipt.support_replay_root,
        "candidate_evidence_root": receipt.candidate_evidence_root,
        "candidate_challenge_root": receipt.candidate_challenge_root,
        "candidate_lease_root": receipt.candidate_lease_root,
        "evidence_root": receipt.evidence_root,
        "challenge_root": receipt.challenge_root,
        "lease_root": receipt.lease_root,
        "window_state_root": receipt.window_state_root,
        "window_root": receipt.window_root,
        "threshold_root": receipt.threshold_root,
        "stop_resolution_root": receipt.stop_resolution_root,
        "permission_root": receipt.permission_root,
        "context_root": receipt.context_root,
        "assessment_root": receipt.assessment_root,
        "local_receipt_version": receipt.receipt_version,
        "local_receipt_ref": local_commit_receipt_fingerprint(receipt),
        "portable_certificate_version": portable_certificate.certificate_version,
        "portable_certificate_ref": evidence_commit_certificate_fingerprint(
            portable_certificate
        ),
        "proposed_at_step": proposed_at_step,
    }


def _validate_quorum_witness(witness: QuorumWitness) -> None:
    if witness.witness_version != QUORUM_WITNESS_VERSION:
        raise GovernanceError("quorum witness version is unsupported")
    if witness.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("quorum witness profile is invalid")
    if witness.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("quorum witness assurance is invalid")
    for name in (
        "witness_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "principal_id",
        "principal_cluster_id",
        "failure_domain",
        "nonce",
        "provenance",
        "trace_event_id",
        "attestation_ref",
    ):
        require_commit_text(getattr(witness, name), f"quorum witness {name}")
    for name in (
        "membership_root",
        "commit_value_root",
        "proposal_digest",
    ):
        require_commit_fingerprint(
            getattr(witness, name),
            f"quorum witness {name}",
        )
    require_commit_step(witness.epoch, "quorum witness epoch")
    witnessed = require_commit_step(
        witness.witnessed_at_step,
        "quorum witness witnessed_at_step",
    )
    expires = require_commit_step(
        witness.expires_at_step,
        "quorum witness expires_at_step",
    )
    if expires <= witnessed:
        raise GovernanceError("quorum witness expiry must follow signing")


def _validate_witness_verification(verification: WitnessVerification) -> None:
    if verification.verification_version != WITNESS_VERIFICATION_VERSION:
        raise GovernanceError("witness verification version is unsupported")
    if type(verification.witness) is not QuorumWitness:
        raise GovernanceError("witness verification lacks canonical witness")
    _validate_quorum_witness(verification.witness)
    for name in (
        "verification_id",
        "verifier_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(verification, name),
            f"witness verification {name}",
        )
    for name in (
        "witness_fingerprint",
        "witness_signing_root",
        "principal_verification_ref",
    ):
        require_commit_fingerprint(
            getattr(verification, name),
            f"witness verification {name}",
        )
    if verification.witness_fingerprint != quorum_witness_fingerprint(
        verification.witness
    ):
        raise GovernanceError("witness verification witness root mismatch")
    if verification.witness_signing_root != quorum_witness_signing_root(
        verification.witness
    ):
        raise GovernanceError("witness verification signing root mismatch")
    verified = require_commit_step(
        verification.verified_at_step,
        "witness verification verified_at_step",
    )
    expires = require_commit_step(
        verification.expires_at_step,
        "witness verification expires_at_step",
    )
    if expires <= verified or expires > verification.witness.expires_at_step:
        raise GovernanceError("witness verification freshness interval is invalid")
    if type(verification.authority) is not AuthorityLevel or not can_verify(
        verification.authority
    ):
        raise GovernanceError("witness verification lacks governance authority")


def _validate_distributed_commit_state(state: DistributedCommitState) -> None:
    if state.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed state profile is invalid")
    if state.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed state assurance is invalid")
    for name in (
        "chain_id",
        "protocol_id",
        "run_id",
        "target",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(state, name), f"distributed state {name}")
    for name in (
        "manifest_root",
        "commit_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "membership_root",
        "witness_receipt_root",
    ):
        require_commit_fingerprint(
            getattr(state, name),
            f"distributed state {name}",
        )
    if state.previous_state_fingerprint:
        require_commit_fingerprint(
            state.previous_state_fingerprint,
            "distributed state previous_state_fingerprint",
        )
    if state.epoch_transition_certificate_ref:
        require_commit_fingerprint(
            state.epoch_transition_certificate_ref,
            "distributed state epoch transition certificate ref",
        )
    for name in (
        "epoch",
        "membership_size",
        "max_byzantine_faults",
        "witness_quorum",
        "witness_ttl_steps",
        "minimum_failure_domain_diversity",
        "revision",
        "initialized_at_step",
        "current_step",
    ):
        require_commit_step(getattr(state, name), f"distributed state {name}")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("distributed state lacks governance authority")
    for name in ("frozen", "transitioned"):
        require_commit_bool(getattr(state, name), f"distributed state {name}")
    if not _quorum_intersection_is_safe(
        state.membership_size,
        state.max_byzantine_faults,
        state.witness_quorum,
    ):
        raise GovernanceError("distributed state quorum intersection is unsafe")
    if state.minimum_failure_domain_diversity > state.witness_quorum:
        raise GovernanceError("distributed state failure diversity is unreachable")
    if state.membership_snapshot.snapshot_fingerprint != (
        state.membership_snapshot_root
    ) or state.membership_snapshot.membership_root != state.membership_root:
        raise GovernanceError("distributed state membership lineage mismatch")
    if state.membership_size != len(state.membership_snapshot.eligible_clusters):
        raise GovernanceError("distributed state membership size mismatch")
    expected_receipt_root = _witness_receipt_root(
        tuple(witness_replay_receipt_portable(item) for item in state.witness_verifications),
        profile=state.profile,
    )
    if state.witness_receipt_root != expected_receipt_root:
        raise GovernanceError("distributed state witness receipt root is invalid")
    expected_findings = _witness_equivocation_findings(
        state.witness_verifications,
        profile=state.profile,
        target=state.target,
        epoch=state.epoch,
    )
    if state.equivocation_findings != expected_findings:
        raise GovernanceError("distributed state equivocation findings are incomplete")
    if set(state.excluded_cluster_ids) != {
        item.principal_cluster_id for item in state.equivocation_findings
    }:
        raise GovernanceError("distributed state equivocation exclusions are invalid")
    semantic_conflict = len(
        {item.commit_value_root for item in state.final_registrations}
    ) > 1
    if (
        state.frozen is not bool(state.conflict_findings)
        or state.frozen is not semantic_conflict
    ):
        raise GovernanceError("distributed state freeze/conflict invariant is invalid")
    registered_refs = {item.certificate_ref for item in state.final_registrations}
    registered_values = {
        item.commit_value_root for item in state.final_registrations
    }
    for finding in state.conflict_findings:
        if not set(finding.certificate_refs).issubset(registered_refs) or not set(
            finding.commit_value_roots
        ).issubset(registered_values):
            raise GovernanceError(
                "distributed state conflict lineage is not registered"
            )
    if state.transitioned is not bool(state.epoch_transition_certificate_ref):
        raise GovernanceError("distributed state transition invariant is invalid")
    for item in state.witness_verifications:
        _validate_verification_state_binding(item, state)


def witness_replay_receipt_portable(
    verification: WitnessVerification,
) -> WitnessReplayReceipt:
    """Build a replay leaf without requiring process-local issuance."""

    _validate_witness_verification(verification)
    witness = verification.witness
    return WitnessReplayReceipt(
        verification_id=verification.verification_id,
        witness_id=witness.witness_id,
        nonce=witness.nonce,
        witness_fingerprint=verification.witness_fingerprint,
        commit_value_root=witness.commit_value_root,
        proposal_digest=witness.proposal_digest,
        target=witness.target,
        candidate_id=witness.candidate_id,
        epoch=witness.epoch,
        principal_id=witness.principal_id,
        principal_cluster_id=witness.principal_cluster_id,
    )


def _validate_distributed_commit_certificate(
    certificate: DistributedCommitCertificate,
) -> None:
    if certificate.schema_discriminator != (
        DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR
    ):
        raise GovernanceError("distributed certificate discriminator is invalid")
    if certificate.certificate_version != DISTRIBUTED_COMMIT_CERTIFICATE_VERSION:
        raise GovernanceError("distributed certificate version is unsupported")
    if certificate.wire_version != COMMIT_WIRE_VERSION:
        raise GovernanceError("distributed certificate wire version is unsupported")
    if certificate.canonicalization != COMMIT_CANONICAL_VERSION:
        raise GovernanceError(
            "distributed certificate canonicalization is unsupported"
        )
    if certificate.hash_algorithm != "sha256":
        raise GovernanceError("distributed certificate hash algorithm is unsupported")
    if certificate.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed certificate profile is invalid")
    if certificate.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed certificate assurance is invalid")
    if type(certificate.status) is not DistributedCertificateStatus:
        raise GovernanceError("distributed certificate status is invalid")
    for name in (
        "certificate_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "portable_certificate_version",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(certificate, name),
            f"distributed certificate {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "commit_value_root",
        "proposal_digest",
        "membership_snapshot_root",
        "membership_root",
        "witness_root",
        "portable_certificate_ref",
        "certificate_body_root",
        "certificate_root",
    ):
        require_commit_fingerprint(
            getattr(certificate, name),
            f"distributed certificate {name}",
        )
    for name in (
        "epoch",
        "membership_size",
        "max_byzantine_faults",
        "witness_quorum",
        "minimum_failure_domain_diversity",
        "issued_at_step",
    ):
        require_commit_step(
            getattr(certificate, name),
            f"distributed certificate {name}",
        )
    if type(certificate.authority) is not AuthorityLevel or not can_verify(
        certificate.authority
    ):
        raise GovernanceError("distributed certificate lacks issuer authority")
    if type(certificate.proposal) is not DistributedCommitProposal:
        raise GovernanceError("distributed certificate proposal is invalid")
    if type(certificate.membership_snapshot) is not PortableMembershipSnapshot:
        raise GovernanceError("distributed certificate membership is invalid")
    _validate_distributed_commit_proposal(certificate.proposal)
    _validate_portable_membership_snapshot(certificate.membership_snapshot)
    _validate_certificate_proposal_binding(certificate)
    if not _quorum_intersection_is_safe(
        certificate.membership_size,
        certificate.max_byzantine_faults,
        certificate.witness_quorum,
    ):
        raise GovernanceError("distributed certificate quorum intersection is unsafe")
    if certificate.membership_size != len(
        certificate.membership_snapshot.eligible_clusters
    ):
        raise GovernanceError("distributed certificate membership size mismatch")
    if not (
        certificate.membership_snapshot.issued_at_step
        <= certificate.issued_at_step
        < certificate.membership_snapshot.expires_at_step
    ):
        raise GovernanceError(
            "distributed certificate membership was not fresh at issuance"
        )
    if certificate.minimum_failure_domain_diversity > certificate.witness_quorum:
        raise GovernanceError("distributed certificate diversity is unreachable")
    if not certificate.witnesses:
        raise GovernanceError("distributed certificate requires witnesses")
    cluster_ids = tuple(
        item.witness.principal_cluster_id for item in certificate.witnesses
    )
    if len(cluster_ids) != len(set(cluster_ids)):
        raise GovernanceError("distributed certificate counts a cluster twice")
    if set(cluster_ids).intersection(certificate.excluded_cluster_ids):
        raise GovernanceError("distributed certificate counts equivocated clusters")
    for verification in certificate.witnesses:
        if (
            verification.witness.proposal_digest != certificate.proposal_digest
            or verification.witness.commit_value_root
            != certificate.commit_value_root
        ):
            raise GovernanceError("distributed certificate witness proposal mismatch")
    expected_witness_root = _witness_verification_root(
        certificate.witnesses,
        profile=certificate.profile,
        commit_value_root=certificate.commit_value_root,
        proposal_digest=certificate.proposal_digest,
    )
    if certificate.witness_root != expected_witness_root:
        raise GovernanceError("distributed certificate witness root is invalid")
    meets_finality = bool(
        len(cluster_ids) >= certificate.witness_quorum
        and len({item.witness.failure_domain for item in certificate.witnesses})
        >= certificate.minimum_failure_domain_diversity
    )
    if (
        certificate.status is DistributedCertificateStatus.FINAL
    ) is not meets_finality:
        raise GovernanceError("distributed certificate status misrepresents quorum")
    expected_body = _distributed_certificate_body_root(
        _distributed_certificate_body_payload(certificate),
        profile=certificate.profile,
    )
    if certificate.certificate_body_root != expected_body:
        raise GovernanceError("distributed certificate body root is invalid")
    expected_root = commit_payload_fingerprint(
        {
            "certificate_body_root": expected_body,
            "commit_value_root": certificate.commit_value_root,
            "proposal_digest": certificate.proposal_digest,
            "witness_root": certificate.witness_root,
        },
        schema="pheroos-distributed-commit-certificate-envelope-v1",
        profile=certificate.profile,
    )
    if certificate.certificate_root != expected_root:
        raise GovernanceError("distributed certificate envelope root is invalid")


def _distributed_certificate_body_payload(
    certificate: DistributedCommitCertificate,
) -> dict[str, object]:
    payload = _public_dataclass_payload(certificate)
    payload.pop("certificate_body_root")
    payload.pop("certificate_root")
    payload["proposal"] = distributed_commit_proposal_payload(
        certificate.proposal
    )
    payload["membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.membership_snapshot
    )
    payload["witnesses"] = tuple(
        witness_verification_payload(item) for item in certificate.witnesses
    )
    return payload


def _distributed_certificate_body_root(
    body: Mapping[str, object],
    *,
    profile: str,
) -> str:
    normalized = dict(body)
    proposal = normalized.get("proposal")
    if type(proposal) is DistributedCommitProposal:
        normalized["proposal"] = distributed_commit_proposal_payload(proposal)
    membership = normalized.get("membership_snapshot")
    if type(membership) is PortableMembershipSnapshot:
        normalized["membership_snapshot"] = portable_membership_snapshot_payload(
            membership
        )
    witness_values = normalized.get("witnesses")
    if witness_values is not None:
        normalized["witnesses"] = tuple(
            witness_verification_payload(item)
            if type(item) is WitnessVerification
            else item
            for item in _require_sequence(
                witness_values,
                "distributed certificate body witnesses",
            )
        )
    return commit_payload_fingerprint(
        normalized,
        schema="pheroos-distributed-commit-certificate-body-v1",
        profile=profile,
    )


def _validate_epoch_transition_certificate(
    certificate: EpochTransitionCertificate,
) -> None:
    if certificate.schema_discriminator != EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR:
        raise GovernanceError("epoch transition discriminator is invalid")
    if certificate.certificate_version != EPOCH_TRANSITION_CERTIFICATE_VERSION:
        raise GovernanceError("epoch transition version is unsupported")
    if certificate.wire_version != COMMIT_WIRE_VERSION:
        raise GovernanceError("epoch transition wire version is unsupported")
    if certificate.canonicalization != COMMIT_CANONICAL_VERSION:
        raise GovernanceError("epoch transition canonicalization is unsupported")
    if certificate.hash_algorithm != "sha256":
        raise GovernanceError("epoch transition hash algorithm is unsupported")
    if certificate.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("epoch transition profile is invalid")
    if certificate.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("epoch transition assurance is invalid")
    for name in (
        "certificate_id",
        "protocol_id",
        "run_id",
        "target",
        "declared_transition_rule",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(certificate, name),
            f"epoch transition {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "previous_membership_root",
        "new_membership_snapshot_root",
        "new_membership_epoch_state_root",
        "new_membership_root",
        "prior_state_ref",
        "transition_stop_root",
        "transition_permission_root",
        "certificate_body_root",
        "certificate_root",
    ):
        require_commit_fingerprint(
            getattr(certificate, name),
            f"epoch transition {name}",
        )
    for name in ("previous_epoch", "new_epoch", "issued_at_step"):
        require_commit_step(
            getattr(certificate, name),
            f"epoch transition {name}",
        )
    if certificate.new_epoch <= certificate.previous_epoch:
        raise GovernanceError("epoch transition must advance the epoch")
    require_commit_bool(
        certificate.recovery_required,
        "epoch transition recovery_required",
    )
    if type(certificate.authority) is not AuthorityLevel or not can_verify(
        certificate.authority
    ):
        raise GovernanceError("epoch transition issuer lacks governance authority")
    if certificate.recovery_required:
        for name in (
            "declared_recovery_ref",
            "recovery_stop_root",
            "recovery_permission_root",
        ):
            require_commit_fingerprint(
                getattr(certificate, name),
                f"epoch transition {name}",
            )
    elif any(
        (
            certificate.declared_recovery_ref,
            certificate.recovery_stop_root,
            certificate.recovery_permission_root,
        )
    ):
        raise GovernanceError(
            "non-recovery epoch certificate contains recovery authority"
        )
    membership = certificate.new_membership_snapshot
    if (
        membership.profile != certificate.profile
        or membership.assurance is not certificate.assurance
        or membership.manifest_root != certificate.manifest_root
        or membership.commit_policy_root != certificate.commit_policy_root
        or membership.protocol_id != certificate.protocol_id
        or membership.run_id != certificate.run_id
        or membership.target != certificate.target
        or membership.epoch != certificate.new_epoch
        or membership.snapshot_fingerprint
        != certificate.new_membership_snapshot_root
        or membership.membership_root != certificate.new_membership_root
    ):
        raise GovernanceError("epoch transition new membership lineage mismatch")
    expected_body = _epoch_transition_body_root(
        _epoch_transition_body_payload(certificate),
        profile=certificate.profile,
    )
    if certificate.certificate_body_root != expected_body:
        raise GovernanceError("epoch transition body root is invalid")
    expected_root = commit_payload_fingerprint(
        {
            "certificate_body_root": expected_body,
            "issuer_attestation_refs": certificate.issuer_attestation_refs,
        },
        schema="pheroos-epoch-transition-certificate-envelope-v1",
        profile=certificate.profile,
    )
    if certificate.certificate_root != expected_root:
        raise GovernanceError("epoch transition envelope root is invalid")


def _epoch_transition_body_payload(
    certificate: EpochTransitionCertificate,
) -> dict[str, object]:
    payload = _public_dataclass_payload(certificate)
    for name in (
        "issuer_attestation_refs",
        "certificate_body_root",
        "certificate_root",
    ):
        payload.pop(name)
    payload["new_membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.new_membership_snapshot
    )
    return payload


def _epoch_transition_body_root(
    body: Mapping[str, object],
    *,
    profile: str,
) -> str:
    normalized = dict(body)
    membership = normalized.get("new_membership_snapshot")
    if type(membership) is PortableMembershipSnapshot:
        normalized["new_membership_snapshot"] = (
            portable_membership_snapshot_payload(membership)
        )
    return commit_payload_fingerprint(
        normalized,
        schema="pheroos-epoch-transition-certificate-body-v1",
        profile=profile,
    )


def _validate_distributed_finality_decision(
    decision: DistributedFinalityDecision,
) -> None:
    if decision.decision_version != DISTRIBUTED_FINALITY_DECISION_VERSION:
        raise GovernanceError("distributed finality decision version is unsupported")
    if type(decision.kind) is not DistributedFinalityKind:
        raise GovernanceError("distributed finality decision kind is invalid")
    require_commit_bool(decision.terminal, "distributed finality terminal")
    require_commit_bool(
        decision.authoritative_commit,
        "distributed finality authoritative_commit",
    )
    if decision.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed finality profile is invalid")
    if decision.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed finality assurance is invalid")
    for name in ("protocol_id", "run_id", "target", "candidate_id"):
        require_commit_text(
            getattr(decision, name),
            f"distributed finality {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "state_ref",
        "local_receipt_ref",
    ):
        require_commit_fingerprint(
            getattr(decision, name),
            f"distributed finality {name}",
        )
    if decision.distributed_certificate_ref:
        require_commit_fingerprint(
            decision.distributed_certificate_ref,
            "distributed finality certificate ref",
        )
    if decision.outcome_ref:
        require_commit_fingerprint(
            decision.outcome_ref,
            "distributed finality outcome ref",
        )
    require_commit_step(decision.epoch, "distributed finality epoch")
    require_commit_step(
        decision.current_step,
        "distributed finality current_step",
    )
    if decision.kind in {
        DistributedFinalityKind.PENDING,
        DistributedFinalityKind.PROVISIONAL,
    }:
        if decision.terminal or decision.authoritative_commit or decision.outcome_ref:
            raise GovernanceError("pending/provisional finality cannot be terminal")
    if decision.kind is DistributedFinalityKind.PENDING and (
        decision.distributed_certificate_ref
    ):
        raise GovernanceError("pending finality cannot carry a certificate")
    if decision.kind is DistributedFinalityKind.PROVISIONAL and not (
        decision.distributed_certificate_ref
    ):
        raise GovernanceError("provisional finality requires its proof reference")
    if decision.kind is DistributedFinalityKind.FINAL:
        if not decision.authoritative_commit or not (
            decision.distributed_certificate_ref
        ):
            raise GovernanceError("final distributed decision lacks authority")
    elif decision.authoritative_commit:
        raise GovernanceError("non-final distributed decision claims commit")
    if decision.terminal is not bool(decision.outcome_ref):
        raise GovernanceError("terminal distributed finality must bind an outcome")
    if decision.kind in {
        DistributedFinalityKind.FINALITY_UNAVAILABLE,
        DistributedFinalityKind.NON_COMMIT_TERMINAL,
    } and not decision.terminal:
        raise GovernanceError("non-commit terminal finality requires an outcome")


def _validate_distributed_policy(
    commit_policy: CollectiveCommitPolicy,
    *,
    profile: str,
    assurance: CommitAssurance,
    target: str,
    commit_policy_root: str,
) -> DistributedCommitPolicy:
    if type(commit_policy) is not CollectiveCommitPolicy:
        raise GovernanceError("distributed commit requires canonical commit policy")
    if profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed commit profile is invalid")
    if assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed commit assurance is invalid")
    if commit_policy.assurance != assurance.value or commit_policy.target != target:
        raise GovernanceError("distributed commit policy binding mismatch")
    if commit_policy_fingerprint(commit_policy, profile=profile) != require_commit_fingerprint(
        commit_policy_root,
        "distributed commit policy root",
    ):
        raise GovernanceError("distributed commit policy root mismatch")
    diagnostics = validate_distributed_commit_policy(
        commit_policy.distributed,
        assurance=assurance.value,
        path="collective_commit_policy.distributed",
    )
    if diagnostics:
        raise GovernanceError(
            "distributed commit policy violates the static Byzantine model"
        )
    distributed = commit_policy.distributed
    assert type(distributed) is DistributedCommitPolicy
    if not _quorum_intersection_is_safe(
        distributed.membership_size,
        distributed.max_byzantine_faults,
        distributed.witness_quorum,
    ):
        raise GovernanceError("distributed quorum intersection is unsafe")
    return distributed


def _validate_membership_policy(
    membership: PortableMembershipSnapshot,
    policy: DistributedCommitPolicy,
) -> None:
    _validate_portable_membership_snapshot(membership)
    if len(membership.eligible_clusters) != policy.membership_size:
        raise GovernanceError(
            "distributed membership size does not match the declared fault model"
        )
    failure_domains = {
        principal.failure_domain
        for cluster in membership.eligible_clusters
        for principal in cluster.principals
    }
    if len(failure_domains) < policy.minimum_failure_domain_diversity:
        raise GovernanceError(
            "distributed membership cannot satisfy failure-domain diversity"
        )


def _quorum_intersection_is_safe(n: int, f: int, q: int) -> bool:
    return bool(n >= 3 * f + 1 and q <= n - f and 2 * q - n > f)


def _validate_receipt_certificate_lineage(
    receipt: LocalCommitReceipt,
    certificate: EvidenceCommitCertificate,
) -> None:
    for name in _CENTRAL_LINEAGE_FIELDS:
        if getattr(certificate, name) != getattr(receipt, name):
            raise GovernanceError(
                f"portable central certificate {name} does not match receipt"
            )
    if certificate.local_receipt_ref != local_commit_receipt_fingerprint(receipt):
        raise GovernanceError("portable certificate local receipt ref mismatch")


def _validate_proposal_certificate_lineage(
    proposal: DistributedCommitProposal,
    certificate: EvidenceCommitCertificate,
) -> None:
    for name in _CENTRAL_LINEAGE_FIELDS:
        if getattr(proposal, name) != getattr(certificate, name):
            raise GovernanceError(
                f"distributed proposal {name} does not match portable certificate"
            )
    if (
        proposal.local_receipt_ref != certificate.local_receipt_ref
        or proposal.portable_certificate_version != certificate.certificate_version
        or proposal.portable_certificate_ref
        != evidence_commit_certificate_fingerprint(certificate)
    ):
        raise GovernanceError("distributed proposal portable certificate mismatch")


_CENTRAL_LINEAGE_FIELDS = (
    "profile",
    "assurance",
    "manifest_root",
    "commit_policy_root",
    "protocol_id",
    "run_id",
    "target",
    "epoch",
    "candidate_id",
    "claim_fingerprint",
    "output_payload_fingerprint",
    "risk_chain_state_root",
    "risk_assessment_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "membership_root",
    "replay_state_root",
    "replay_root",
    "support_replay_state_root",
    "support_replay_root",
    "candidate_evidence_root",
    "candidate_challenge_root",
    "candidate_lease_root",
    "evidence_root",
    "challenge_root",
    "lease_root",
    "window_state_root",
    "window_root",
    "threshold_root",
    "stop_resolution_root",
    "permission_root",
    "context_root",
    "assessment_root",
)


def _validate_proposal_membership(
    proposal: DistributedCommitProposal,
    membership: PortableMembershipSnapshot,
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
        if getattr(proposal, name) != getattr(membership, name):
            raise GovernanceError(
                f"distributed proposal membership {name} mismatch"
            )
    if (
        proposal.membership_snapshot_root != membership.snapshot_fingerprint
        or proposal.membership_root != membership.membership_root
    ):
        raise GovernanceError("distributed proposal membership root mismatch")


def _validate_witness_proposal_binding(
    witness: QuorumWitness,
    proposal: DistributedCommitProposal,
) -> None:
    for name in (
        "profile",
        "assurance",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
        "candidate_id",
    ):
        if getattr(witness, name) != getattr(proposal, name):
            raise GovernanceError(f"quorum witness {name} binding mismatch")
    if (
        witness.membership_root != proposal.membership_root
        or witness.commit_value_root != proposal.commit_value_root
        or witness.proposal_digest != proposal.proposal_digest
    ):
        raise GovernanceError("quorum witness proposal/root binding mismatch")


def _validate_verification_state_binding(
    verification: WitnessVerification,
    state: DistributedCommitState,
) -> None:
    witness = verification.witness
    for name in (
        "profile",
        "assurance",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if getattr(witness, name) != getattr(state, name):
            raise GovernanceError(f"witness verification state {name} mismatch")
    if witness.membership_root != state.membership_root:
        raise GovernanceError("witness verification state membership mismatch")


def _validate_proposal_state_binding(
    proposal: DistributedCommitProposal,
    state: DistributedCommitState,
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
        "membership_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
    ):
        if getattr(proposal, name) != getattr(state, name):
            raise GovernanceError(f"distributed proposal state {name} mismatch")


def _validate_certificate_proposal_binding(
    certificate: DistributedCommitCertificate,
) -> None:
    proposal = certificate.proposal
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
        "candidate_id",
        "commit_value_root",
        "proposal_digest",
        "membership_snapshot_root",
        "membership_root",
        "portable_certificate_ref",
        "portable_certificate_version",
    ):
        if getattr(certificate, name) != getattr(proposal, name):
            raise GovernanceError(
                f"distributed certificate proposal {name} mismatch"
            )
    if certificate.membership_snapshot.snapshot_fingerprint != (
        certificate.membership_snapshot_root
    ) or certificate.membership_snapshot.membership_root != (
        certificate.membership_root
    ):
        raise GovernanceError("distributed certificate membership root mismatch")


def _validate_certificate_state_binding(
    certificate: DistributedCommitCertificate,
    state: DistributedCommitState,
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
        "membership_snapshot_root",
        "membership_root",
        "membership_size",
        "max_byzantine_faults",
        "witness_quorum",
        "minimum_failure_domain_diversity",
    ):
        if getattr(certificate, name) != getattr(state, name):
            raise GovernanceError(
                f"distributed certificate state {name} mismatch"
            )


def _validate_receipt_state_binding(
    receipt: LocalCommitReceipt,
    state: DistributedCommitState,
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
        "membership_root",
    ):
        if getattr(receipt, name) != getattr(state, name):
            raise GovernanceError(f"distributed receipt state {name} mismatch")
    if receipt.membership_snapshot_root != state.membership_snapshot_root:
        raise GovernanceError("distributed receipt membership snapshot mismatch")
    if receipt.membership_epoch_state_root != state.membership_epoch_state_root:
        raise GovernanceError("distributed receipt membership epoch mismatch")


def _validate_outcome_state_binding(
    outcome: DecisionOutcome,
    state: DistributedCommitState,
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
        "membership_root",
    ):
        if getattr(outcome, name) != getattr(state, name):
            raise GovernanceError(f"distributed outcome state {name} mismatch")


def _portable_member(
    membership: PortableMembershipSnapshot,
    principal_id: str,
) -> tuple[str, PortableEligiblePrincipal] | None:
    for cluster in membership.eligible_clusters:
        for principal in cluster.principals:
            if principal.principal_id == principal_id:
                return cluster.cluster_id, principal
    return None


def _coerce_portable_membership(
    membership: PortableMembershipSnapshot | EligiblePrincipalSnapshot,
) -> PortableMembershipSnapshot:
    if type(membership) is PortableMembershipSnapshot:
        _validate_portable_membership_snapshot(membership)
        return membership
    if type(membership) is EligiblePrincipalSnapshot:
        return portable_membership_snapshot_from_eligible(membership)
    raise GovernanceError("distributed membership snapshot type is invalid")


def _canonical_witness_verifications(
    values: Sequence[WitnessVerification],
) -> tuple[WitnessVerification, ...]:
    normalized = tuple(values)
    if any(type(item) is not WitnessVerification for item in normalized):
        raise GovernanceError(
            "distributed witnesses must use canonical verification records"
        )
    fingerprints = tuple(
        witness_verification_fingerprint(item) for item in normalized
    )
    if len(fingerprints) != len(set(fingerprints)):
        raise GovernanceError("distributed witnesses contain a duplicate")
    return tuple(
        item
        for _, item in sorted(
            zip(fingerprints, normalized, strict=True),
            key=lambda pair: pair[0],
        )
    )


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(values)
    if not normalized and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    for value in normalized:
        require_commit_fingerprint(value, field_name)
    if len(normalized) != len(set(normalized)):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(normalized))


def _witness_receipt_root(
    receipts: Sequence[WitnessReplayReceipt],
    *,
    profile: str,
) -> str:
    fingerprints = tuple(
        sorted(
            witness_replay_receipt_fingerprint(item, profile=profile)
            for item in receipts
        )
    )
    return commit_payload_fingerprint(
        {"receipt_fingerprints": fingerprints},
        schema="pheroos-witness-replay-root-v1",
        profile=profile,
    )


def _witness_verification_root(
    verifications: Sequence[WitnessVerification],
    *,
    profile: str,
    commit_value_root: str,
    proposal_digest: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "commit_value_root": commit_value_root,
            "proposal_digest": proposal_digest,
            "witness_verification_fingerprints": tuple(
                sorted(
                    witness_verification_fingerprint(item)
                    for item in verifications
                )
            ),
        },
        schema="pheroos-distributed-witness-root-v1",
        profile=profile,
    )


def _witness_equivocation_findings(
    verifications: Sequence[WitnessVerification],
    *,
    profile: str,
    target: str,
    epoch: int,
) -> tuple[WitnessEquivocationFinding, ...]:
    by_cluster: dict[str, list[WitnessVerification]] = {}
    for verification in verifications:
        by_cluster.setdefault(
            verification.witness.principal_cluster_id,
            [],
        ).append(verification)
    findings: list[WitnessEquivocationFinding] = []
    for cluster_id, items in sorted(by_cluster.items()):
        commit_value_roots = tuple(
            sorted({item.witness.commit_value_root for item in items})
        )
        proposal_digests = tuple(
            sorted({item.witness.proposal_digest for item in items})
        )
        if len(commit_value_roots) < 2:
            continue
        witness_refs = tuple(
            sorted(witness_verification_fingerprint(item) for item in items)
        )
        finding_id = commit_payload_fingerprint(
            {
                "epoch": epoch,
                "commit_value_roots": commit_value_roots,
                "principal_cluster_id": cluster_id,
                "proposal_digests": proposal_digests,
                "target": target,
                "witness_fingerprints": witness_refs,
            },
            schema="pheroos-witness-equivocation-finding-v1",
            profile=profile,
        )
        findings.append(
            WitnessEquivocationFinding(
                finding_id=finding_id,
                target=target,
                epoch=epoch,
                principal_cluster_id=cluster_id,
                commit_value_roots=commit_value_roots,
                proposal_digests=proposal_digests,
                witness_fingerprints=witness_refs,
            )
        )
    return tuple(findings)


def _certificate_conflict_finding(
    registrations: Sequence[FinalCertificateRegistration],
    *,
    profile: str,
    target: str,
    epoch: int,
    current_step: int,
) -> CertificateConflictFinding:
    certificate_refs = tuple(
        sorted({item.certificate_ref for item in registrations})
    )
    commit_value_roots = tuple(
        sorted({item.commit_value_root for item in registrations})
    )
    proposal_digests = tuple(
        sorted({item.proposal_digest for item in registrations})
    )
    candidate_ids = tuple(sorted({item.candidate_id for item in registrations}))
    finding_id = commit_payload_fingerprint(
        {
            "certificate_refs": certificate_refs,
            "commit_value_roots": commit_value_roots,
            "epoch": epoch,
            "proposal_digests": proposal_digests,
            "target": target,
        },
        schema="pheroos-distributed-certificate-conflict-v1",
        profile=profile,
    )
    return CertificateConflictFinding(
        finding_id=finding_id,
        target=target,
        epoch=epoch,
        certificate_refs=certificate_refs,
        commit_value_roots=commit_value_roots,
        proposal_digests=proposal_digests,
        candidate_ids=candidate_ids,
        detected_at_step=current_step,
    )


def _issue_distributed_state(
    state: DistributedCommitState,
    cursor: _DistributedStateCursor,
) -> DistributedCommitState:
    object.__setattr__(state, "_cursor", cursor)
    object.__setattr__(
        state,
        "_issuance",
        (_DISTRIBUTED_STATE_ISSUANCE, distributed_commit_state_fingerprint(state)),
    )
    return state


def _current_distributed_state_head(
    state: DistributedCommitState,
) -> DistributedCommitState:
    if not distributed_commit_state_is_authoritative(state):
        raise GovernanceError("distributed state is not authoritative")
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed state cursor is invalid")
    with cursor.lock:
        current = cursor.current_state
        if (
            type(current) is not DistributedCommitState
            or cursor.current_state_fingerprint
            != distributed_commit_state_fingerprint(current)
        ):
            raise GovernanceError("distributed state current head is unavailable")
        return current


def _register_distributed_certificate_identity(
    certificate: DistributedCommitCertificate,
) -> DistributedCommitCertificate:
    key = (
        certificate.profile,
        certificate.run_id,
        certificate.target,
        certificate.epoch,
        certificate.certificate_id,
    )
    fingerprint = distributed_commit_certificate_fingerprint(certificate)
    with _DISTRIBUTED_CERTIFICATE_REGISTRY_LOCK:
        existing = _DISTRIBUTED_CERTIFICATES_BY_ID.get(key)
        if existing is not None:
            if distributed_commit_certificate_fingerprint(existing) != fingerprint:
                raise GovernanceError(
                    "distributed certificate id replay has a different body"
                )
            return existing
        _DISTRIBUTED_CERTIFICATES_BY_ID[key] = certificate
        return certificate


def _register_epoch_transition_certificate_identity(
    certificate: EpochTransitionCertificate,
) -> EpochTransitionCertificate:
    key = (
        certificate.profile,
        certificate.run_id,
        certificate.target,
        certificate.previous_epoch,
        certificate.certificate_id,
    )
    fingerprint = epoch_transition_certificate_fingerprint(certificate)
    with _EPOCH_CERTIFICATE_REGISTRY_LOCK:
        existing = _EPOCH_CERTIFICATES_BY_ID.get(key)
        if existing is not None:
            if epoch_transition_certificate_fingerprint(existing) != fingerprint:
                raise GovernanceError(
                    "epoch transition certificate id replay has a different body"
                )
            return existing
        _EPOCH_CERTIFICATES_BY_ID[key] = certificate
        return certificate


def _replace_distributed_state(
    state: DistributedCommitState,
    **changes: object,
) -> DistributedCommitState:
    return replace(state, **changes)


def _validate_new_epoch_membership(
    state: DistributedCommitState,
    new_snapshot: EligiblePrincipalSnapshot,
    new_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    current_step: int,
) -> DistributedCommitPolicy:
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=state.profile,
        assurance=state.assurance,
        target=state.target,
        commit_policy_root=state.commit_policy_root,
    )
    if new_snapshot.epoch <= state.epoch:
        raise GovernanceError("new distributed membership must advance epoch")
    if not eligible_principal_snapshot_matches(
        new_snapshot,
        epoch_state=new_epoch_state,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=new_snapshot.epoch,
        current_step=current_step,
    ):
        raise GovernanceError("new distributed membership is not authoritative")
    _validate_membership_policy(
        portable_membership_snapshot_from_eligible(new_snapshot),
        distributed,
    )
    return distributed


def _epoch_transition_body_from_inputs(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    transition_stop: StopResolutionVerification,
    transition_permission: ActionPermission,
    *,
    commit_policy: CollectiveCommitPolicy,
    certificate_id: str,
    declared_recovery_ref: str,
    recovery_stop: StopResolutionVerification | None,
    recovery_permission: ActionPermission | None,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> dict[str, object]:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError("epoch transition requires the current state")
    if state.transitioned:
        raise GovernanceError("distributed epoch already transitioned")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("epoch transition requires governance authority")
    current = require_commit_step(
        issued_at_step,
        "epoch transition issued_at_step",
    )
    distributed = _validate_new_epoch_membership(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        current_step=current,
    )
    decision_ref = epoch_transition_decision_ref(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        declared_recovery_ref=declared_recovery_ref,
    )
    _require_action_gate(
        stop=transition_stop,
        permission=transition_permission,
        state=state,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
        current_step=current,
    )
    recovery_ref = (
        require_commit_fingerprint(
            declared_recovery_ref,
            "epoch transition declared_recovery_ref",
        )
        if declared_recovery_ref
        else ""
    )
    if state.frozen:
        if recovery_stop is None or recovery_permission is None:
            raise GovernanceError(
                "conflict recovery requires explicit recovery stop and permission"
            )
        _require_action_gate(
            stop=recovery_stop,
            permission=recovery_permission,
            state=state,
            action=CommitAction.RECOVERY,
            decision_ref=decision_ref,
            current_step=current,
        )
    elif recovery_stop is not None or recovery_permission is not None or recovery_ref:
        raise GovernanceError(
            "non-conflict epoch transition cannot claim recovery authority"
        )
    new_portable = portable_membership_snapshot_from_eligible(
        new_membership_snapshot
    )
    _validate_membership_policy(new_portable, distributed)
    return {
        "schema_discriminator": EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR,
        "certificate_version": EPOCH_TRANSITION_CERTIFICATE_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "certificate_id": require_commit_text(
            certificate_id,
            "epoch transition certificate_id",
        ),
        "profile": state.profile,
        "assurance": state.assurance,
        "manifest_root": state.manifest_root,
        "commit_policy_root": state.commit_policy_root,
        "protocol_id": state.protocol_id,
        "run_id": state.run_id,
        "target": state.target,
        "previous_epoch": state.epoch,
        "new_epoch": new_portable.epoch,
        "previous_membership_root": state.membership_root,
        "new_membership_snapshot": new_portable,
        "new_membership_snapshot_root": new_portable.snapshot_fingerprint,
        "new_membership_epoch_state_root": (
            eligible_membership_epoch_state_fingerprint(
                new_membership_epoch_state
            )
        ),
        "new_membership_root": new_portable.membership_root,
        "prior_state_ref": distributed_commit_state_fingerprint(state),
        "declared_transition_rule": distributed.epoch_transition_rule,
        "declared_recovery_ref": recovery_ref,
        "recovery_required": state.frozen,
        "transition_stop_root": stop_resolution_verification_fingerprint(
            transition_stop
        ),
        "transition_permission_root": action_permission_fingerprint(
            transition_permission
        ),
        "recovery_stop_root": (
            stop_resolution_verification_fingerprint(recovery_stop)
            if recovery_stop is not None
            else ""
        ),
        "recovery_permission_root": (
            action_permission_fingerprint(recovery_permission)
            if recovery_permission is not None
            else ""
        ),
        "issuer_id": require_commit_text(
            issuer_id,
            "epoch transition issuer_id",
        ),
        "authority": authority,
        "issued_at_step": current,
        "provenance": require_commit_text(
            provenance,
            "epoch transition provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "epoch transition trace_event_id",
        ),
    }


def _require_action_gate(
    *,
    stop: StopResolutionVerification,
    permission: ActionPermission,
    state: DistributedCommitState,
    action: CommitAction,
    decision_ref: str,
    current_step: int,
) -> None:
    if not stop_resolution_verification_matches(
        stop,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        action=action,
        epoch=state.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        current_step=current_step,
        require_unblocked=True,
    ):
        raise GovernanceError(f"{action.value} stop gate is not resolved")
    if not action_permission_matches(
        permission,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        action=action,
        epoch=state.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        current_step=current_step,
        require_allowed=True,
    ):
        raise GovernanceError(f"{action.value} permission gate is denied")


def _attestation_matches(
    attestation_ref: str,
    trusted_attestations: Mapping[str, str],
    body_root: str,
) -> bool:
    if not isinstance(trusted_attestations, Mapping):
        return False
    return trusted_attestations.get(attestation_ref) == body_root


def _require_attestation_bindings(
    references: Sequence[str],
    trusted_attestations: Mapping[str, str],
    body_root: str,
    *,
    field_name: str,
) -> tuple[str, ...]:
    normalized = require_commit_labels(references, f"{field_name} attestations")
    if not all(
        _attestation_matches(reference, trusted_attestations, body_root)
        for reference in normalized
    ):
        raise GovernanceError(f"{field_name} attestation verification failed")
    return normalized


def _public_dataclass_payload(value: object) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if not item.name.startswith("_")
    }


def _strict_dataclass_payload(
    payload: Mapping[str, object],
    cls: type,
    field_name: str,
) -> dict[str, object]:
    names = {
        item.name
        for item in fields(cls)
        if item.init and not item.name.startswith("_")
    }
    return _strict_mapping(payload, names, field_name)


def _strict_mapping(
    payload: object,
    expected_keys: set[str],
    field_name: str,
) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise GovernanceError(f"{field_name} must be a mapping")
    if any(not isinstance(key, str) for key in payload):
        raise GovernanceError(f"{field_name} keys must be strings")
    actual = set(payload)
    if actual != expected_keys:
        missing = sorted(expected_keys - actual)
        unknown = sorted(actual - expected_keys)
        raise GovernanceError(
            f"{field_name} fields mismatch; missing={missing}, unknown={unknown}"
        )
    return dict(payload)


def _require_sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise GovernanceError(f"{field_name} must be a sequence")
    return tuple(value)


def _coerce_assurance(value: object) -> CommitAssurance:
    if type(value) is CommitAssurance:
        return value
    try:
        return CommitAssurance(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("distributed assurance is invalid") from exc


def _coerce_authority(value: object) -> AuthorityLevel:
    if type(value) is AuthorityLevel:
        return value
    if isinstance(value, bool):
        raise GovernanceError("distributed authority is invalid")
    try:
        return AuthorityLevel(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("distributed authority is invalid") from exc


def _coerce_certificate_status(value: object) -> DistributedCertificateStatus:
    if type(value) is DistributedCertificateStatus:
        return value
    try:
        return DistributedCertificateStatus(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("distributed certificate status is invalid") from exc


def _coerce_finality_kind(value: object) -> DistributedFinalityKind:
    if type(value) is DistributedFinalityKind:
        return value
    try:
        return DistributedFinalityKind(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("distributed finality kind is invalid") from exc


def _equivocation_finding_from_payload(
    payload: object,
) -> WitnessEquivocationFinding:
    values = _strict_dataclass_payload(
        payload,
        WitnessEquivocationFinding,
        "witness equivocation finding payload",
    )
    for name in ("commit_value_roots", "proposal_digests"):
        values[name] = tuple(
            _require_sequence(
                values[name],
                f"witness equivocation {name}",
            )
        )
    values["witness_fingerprints"] = tuple(
        _require_sequence(
            values["witness_fingerprints"],
            "witness equivocation witness fingerprints",
        )
    )
    return WitnessEquivocationFinding(**values)


def _conflict_finding_from_payload(
    payload: object,
) -> CertificateConflictFinding:
    values = _strict_dataclass_payload(
        payload,
        CertificateConflictFinding,
        "certificate conflict finding payload",
    )
    for name in (
        "certificate_refs",
        "commit_value_roots",
        "proposal_digests",
        "candidate_ids",
    ):
        values[name] = tuple(
            _require_sequence(values[name], f"certificate conflict {name}")
        )
    return CertificateConflictFinding(**values)


__all__ = [
    "DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR",
    "DISTRIBUTED_COMMIT_CERTIFICATE_VERSION",
    "DISTRIBUTED_COMMIT_VALUE_VERSION",
    "DISTRIBUTED_FINALITY_DECISION_VERSION",
    "DISTRIBUTED_PROPOSAL_VERSION",
    "DISTRIBUTED_STATE_VERSION",
    "EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR",
    "EPOCH_TRANSITION_CERTIFICATE_VERSION",
    "QUORUM_WITNESS_VERSION",
    "WITNESS_VERIFICATION_VERSION",
    "CertificateConflictFinding",
    "DistributedCertificateStatus",
    "DistributedCommitCertificate",
    "DistributedCommitProposal",
    "DistributedCommitState",
    "DistributedFinalityDecision",
    "DistributedFinalityKind",
    "EpochTransitionCertificate",
    "FinalCertificateRegistration",
    "PortableEligibleCluster",
    "PortableEligiblePrincipal",
    "PortableMembershipSnapshot",
    "QuorumWitness",
    "WitnessEquivocationFinding",
    "WitnessReplayReceipt",
    "WitnessVerification",
    "assemble_portable_distributed_commit_certificate",
    "distributed_commit_certificate_fingerprint",
    "distributed_commit_certificate_from_payload",
    "distributed_commit_certificate_is_current_final",
    "distributed_commit_certificate_payload",
    "distributed_commit_value_payload",
    "distributed_commit_value_root",
    "distributed_commit_proposal_fingerprint",
    "distributed_commit_proposal_from_payload",
    "distributed_commit_proposal_is_authoritative",
    "distributed_commit_proposal_payload",
    "distributed_commit_state_fingerprint",
    "distributed_commit_state_from_payload",
    "distributed_commit_state_is_authoritative",
    "distributed_commit_state_is_current",
    "distributed_commit_state_payload",
    "distributed_finality_decision_fingerprint",
    "distributed_finality_decision_from_payload",
    "distributed_finality_decision_is_authoritative",
    "distributed_finality_decision_payload",
    "epoch_transition_certificate_fingerprint",
    "epoch_transition_certificate_body_root",
    "epoch_transition_certificate_from_payload",
    "epoch_transition_certificate_payload",
    "epoch_transition_decision_ref",
    "evaluate_distributed_finality",
    "initialize_distributed_commit_state",
    "issue_distributed_commit_certificate",
    "issue_distributed_commit_proposal",
    "issue_epoch_transition_certificate",
    "portable_membership_root",
    "portable_membership_snapshot_fingerprint",
    "portable_membership_snapshot_from_eligible",
    "portable_membership_snapshot_from_payload",
    "portable_membership_snapshot_payload",
    "quorum_witness_fingerprint",
    "quorum_witness_from_payload",
    "quorum_witness_payload",
    "quorum_witness_signing_payload",
    "quorum_witness_signing_root",
    "record_witness_verifications",
    "register_distributed_commit_certificate",
    "transition_distributed_commit_epoch",
    "verify_distributed_commit_certificate",
    "verify_distributed_commit_finality",
    "verify_distributed_commit_proposal",
    "verify_epoch_transition_certificate",
    "verify_portable_witness_verification",
    "verify_quorum_witness",
    "witness_replay_receipt",
    "witness_replay_receipt_fingerprint",
    "witness_replay_receipt_from_payload",
    "witness_replay_receipt_payload",
    "witness_verification_fingerprint",
    "witness_verification_from_payload",
    "witness_verification_is_authoritative",
    "witness_verification_payload",
]
