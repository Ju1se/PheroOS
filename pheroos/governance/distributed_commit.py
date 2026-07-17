"""Canonical Distributed Commit ABI facade backed by static lifecycle owners."""

from __future__ import annotations

from collections.abc import Mapping

from pheroos.governance.certificate import EvidenceCommitCertificate
from pheroos.protocol.commit_models import CollectiveCommitPolicy

DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR = "distributed_commit_certificate"
DISTRIBUTED_COMMIT_CERTIFICATE_VERSION = "pheroos-distributed-commit-certificate-v1"
DISTRIBUTED_COMMIT_VALUE_VERSION = "pheroos-distributed-commit-value-v1"
DISTRIBUTED_FINALITY_DECISION_VERSION = "pheroos-distributed-finality-decision-v1"
DISTRIBUTED_PROPOSAL_VERSION = "pheroos-distributed-commit-proposal-v1"
DISTRIBUTED_STATE_VERSION = "pheroos-distributed-commit-state-v1"
EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR = "epoch_transition_certificate"
EPOCH_TRANSITION_CERTIFICATE_VERSION = "pheroos-epoch-transition-certificate-v1"
QUORUM_WITNESS_VERSION = "pheroos-quorum-witness-v1"
WITNESS_VERIFICATION_VERSION = "pheroos-witness-verification-v1"

from pheroos.governance._distributed.membership import (
    PortableEligiblePrincipal as _owner_membership_0,
)
from pheroos.governance._distributed.membership import (
    PortableEligibleCluster as _owner_membership_1,
)
from pheroos.governance._distributed.membership import (
    PortableMembershipSnapshot as _owner_membership_2,
)
from pheroos.governance._distributed.membership import (
    portable_membership_snapshot_from_eligible as _owner_membership_3,
)
from pheroos.governance._distributed.membership import (
    portable_membership_snapshot_payload as _owner_membership_4,
)
from pheroos.governance._distributed.membership import (
    portable_membership_snapshot_fingerprint as _owner_membership_5,
)
from pheroos.governance._distributed.membership import (
    portable_membership_root as _owner_membership_6,
)
from pheroos.governance._distributed.membership import (
    portable_membership_snapshot_from_payload as _owner_membership_7,
)
from pheroos.governance._distributed.proposal import (
    DistributedCommitProposal as _owner_proposal_0,
)
from pheroos.governance._distributed.proposal import (
    issue_distributed_commit_proposal as _owner_proposal_1,
)
from pheroos.governance._distributed.proposal import (
    distributed_commit_proposal_payload as _owner_proposal_2,
)
from pheroos.governance._distributed.proposal import (
    distributed_commit_value_payload as _owner_proposal_3,
)
from pheroos.governance._distributed.proposal import (
    distributed_commit_value_root as _owner_proposal_4,
)
from pheroos.governance._distributed.proposal import (
    distributed_commit_proposal_fingerprint as _owner_proposal_5,
)
from pheroos.governance._distributed.proposal import (
    distributed_commit_proposal_is_authoritative as _owner_proposal_6,
)
from pheroos.governance._distributed.proposal import (
    distributed_commit_proposal_from_payload as _owner_proposal_7,
)
from pheroos.governance._distributed.proposal import (
    verify_distributed_commit_proposal as _owner_proposal_8,
)
from pheroos.governance._distributed.witness import QuorumWitness as _owner_witness_0
from pheroos.governance._distributed.witness import (
    WitnessVerification as _owner_witness_1,
)
from pheroos.governance._distributed.witness import (
    WitnessReplayReceipt as _owner_witness_2,
)
from pheroos.governance._distributed.witness import (
    WitnessEquivocationFinding as _owner_witness_3,
)
from pheroos.governance._distributed.witness import (
    quorum_witness_signing_payload as _owner_witness_4,
)
from pheroos.governance._distributed.witness import (
    quorum_witness_signing_root as _owner_witness_5,
)
from pheroos.governance._distributed.witness import (
    quorum_witness_payload as _owner_witness_6,
)
from pheroos.governance._distributed.witness import (
    quorum_witness_fingerprint as _owner_witness_7,
)
from pheroos.governance._distributed.witness import (
    quorum_witness_from_payload as _owner_witness_8,
)
from pheroos.governance._distributed.witness import (
    verify_quorum_witness as _owner_witness_9,
)
from pheroos.governance._distributed.witness import (
    witness_verification_payload as _owner_witness_10,
)
from pheroos.governance._distributed.witness import (
    witness_verification_fingerprint as _owner_witness_11,
)
from pheroos.governance._distributed.witness import (
    witness_verification_is_authoritative as _owner_witness_12,
)
from pheroos.governance._distributed.witness import (
    witness_verification_from_payload as _owner_witness_13,
)
from pheroos.governance._distributed.witness import (
    verify_portable_witness_verification as _owner_witness_14,
)
from pheroos.governance._distributed.witness import (
    witness_replay_receipt as _owner_witness_15,
)
from pheroos.governance._distributed.witness import (
    witness_replay_receipt_payload as _owner_witness_16,
)
from pheroos.governance._distributed.witness import (
    witness_replay_receipt_from_payload as _owner_witness_17,
)
from pheroos.governance._distributed.witness import (
    witness_replay_receipt_fingerprint as _owner_witness_18,
)
from pheroos.governance._distributed.state import (
    FinalCertificateRegistration as _owner_state_0,
)
from pheroos.governance._distributed.state import (
    CertificateConflictFinding as _owner_state_1,
)
from pheroos.governance._distributed.state import (
    DistributedCommitState as _owner_state_2,
)
from pheroos.governance._distributed.state import (
    initialize_distributed_commit_state as _owner_state_3,
)
from pheroos.governance._distributed.state import (
    record_witness_verifications as _owner_state_4,
)
from pheroos.governance._distributed.state import (
    distributed_commit_state_payload as _owner_state_5,
)
from pheroos.governance._distributed.state import (
    distributed_commit_state_fingerprint as _owner_state_6,
)
from pheroos.governance._distributed.state import (
    distributed_commit_state_from_payload as _owner_state_7,
)
from pheroos.governance._distributed.state import (
    distributed_commit_state_is_authoritative as _owner_state_8,
)
from pheroos.governance._distributed.state import (
    distributed_commit_state_is_current as _owner_state_9,
)
from pheroos.governance._distributed.certificate import (
    DistributedCertificateStatus as _owner_certificate_0,
)
from pheroos.governance._distributed.certificate import (
    DistributedCommitCertificate as _owner_certificate_1,
)
from pheroos.governance._distributed.certificate import (
    issue_distributed_commit_certificate as _owner_certificate_2,
)
from pheroos.governance._distributed.certificate import (
    assemble_portable_distributed_commit_certificate as _owner_certificate_3,
)
from pheroos.governance._distributed.certificate import (
    distributed_commit_certificate_payload as _owner_certificate_4,
)
from pheroos.governance._distributed.certificate import (
    distributed_commit_certificate_fingerprint as _owner_certificate_5,
)
from pheroos.governance._distributed.certificate import (
    distributed_commit_certificate_from_payload as _owner_certificate_6,
)
from pheroos.governance._distributed.certificate import (
    verify_distributed_commit_certificate as _owner_certificate_7,
)
from pheroos.governance._distributed.certificate import (
    record_distributed_commit_certificate as _owner_certificate_8,
)
from pheroos.governance._distributed.certificate import (
    distributed_commit_certificate_is_current_final as _owner_certificate_9,
)
from pheroos.governance._distributed.certificate import (
    verify_distributed_commit_finality as _owner_certificate_10,
)
from pheroos.governance._distributed.epoch import (
    EpochTransitionCertificate as _owner_epoch_0,
)
from pheroos.governance._distributed.epoch import (
    epoch_transition_decision_ref as _owner_epoch_1,
)
from pheroos.governance._distributed.epoch import (
    epoch_transition_certificate_body_root as _owner_epoch_2,
)
from pheroos.governance._distributed.epoch import (
    issue_epoch_transition_certificate as _owner_epoch_3,
)
from pheroos.governance._distributed.epoch import (
    epoch_transition_certificate_payload as _owner_epoch_4,
)
from pheroos.governance._distributed.epoch import (
    epoch_transition_certificate_fingerprint as _owner_epoch_5,
)
from pheroos.governance._distributed.epoch import (
    epoch_transition_certificate_from_payload as _owner_epoch_6,
)
from pheroos.governance._distributed.epoch import (
    verify_epoch_transition_certificate as _owner_epoch_7,
)
from pheroos.governance._distributed.epoch import (
    transition_distributed_commit_epoch as _owner_epoch_8,
)
from pheroos.governance._distributed.finality import (
    DistributedFinalityKind as _owner_finality_0,
)
from pheroos.governance._distributed.finality import (
    DistributedFinalityDecision as _owner_finality_1,
)
from pheroos.governance._distributed.finality import (
    evaluate_distributed_finality as _owner_finality_2,
)
from pheroos.governance._distributed.finality import (
    distributed_finality_decision_payload as _owner_finality_3,
)
from pheroos.governance._distributed.finality import (
    distributed_finality_decision_fingerprint as _owner_finality_4,
)
from pheroos.governance._distributed.finality import (
    distributed_finality_decision_from_payload as _owner_finality_5,
)
from pheroos.governance._distributed.finality import (
    distributed_finality_decision_is_authoritative as _owner_finality_6,
)

PortableEligiblePrincipal = _owner_membership_0
PortableEligibleCluster = _owner_membership_1
PortableMembershipSnapshot = _owner_membership_2
portable_membership_snapshot_from_eligible = _owner_membership_3
portable_membership_snapshot_payload = _owner_membership_4
portable_membership_snapshot_fingerprint = _owner_membership_5
portable_membership_root = _owner_membership_6
portable_membership_snapshot_from_payload = _owner_membership_7
DistributedCommitProposal = _owner_proposal_0
issue_distributed_commit_proposal = _owner_proposal_1
distributed_commit_proposal_payload = _owner_proposal_2
distributed_commit_value_payload = _owner_proposal_3
distributed_commit_value_root = _owner_proposal_4
distributed_commit_proposal_fingerprint = _owner_proposal_5
distributed_commit_proposal_is_authoritative = _owner_proposal_6
distributed_commit_proposal_from_payload = _owner_proposal_7
verify_distributed_commit_proposal = _owner_proposal_8
QuorumWitness = _owner_witness_0
WitnessVerification = _owner_witness_1
WitnessReplayReceipt = _owner_witness_2
WitnessEquivocationFinding = _owner_witness_3
quorum_witness_signing_payload = _owner_witness_4
quorum_witness_signing_root = _owner_witness_5
quorum_witness_payload = _owner_witness_6
quorum_witness_fingerprint = _owner_witness_7
quorum_witness_from_payload = _owner_witness_8
verify_quorum_witness = _owner_witness_9
witness_verification_payload = _owner_witness_10
witness_verification_fingerprint = _owner_witness_11
witness_verification_is_authoritative = _owner_witness_12
witness_verification_from_payload = _owner_witness_13
verify_portable_witness_verification = _owner_witness_14
witness_replay_receipt = _owner_witness_15
witness_replay_receipt_payload = _owner_witness_16
witness_replay_receipt_from_payload = _owner_witness_17
witness_replay_receipt_fingerprint = _owner_witness_18
FinalCertificateRegistration = _owner_state_0
CertificateConflictFinding = _owner_state_1
DistributedCommitState = _owner_state_2
initialize_distributed_commit_state = _owner_state_3
record_witness_verifications = _owner_state_4
distributed_commit_state_payload = _owner_state_5
distributed_commit_state_fingerprint = _owner_state_6
distributed_commit_state_from_payload = _owner_state_7
distributed_commit_state_is_authoritative = _owner_state_8
distributed_commit_state_is_current = _owner_state_9
DistributedCertificateStatus = _owner_certificate_0
DistributedCommitCertificate = _owner_certificate_1
issue_distributed_commit_certificate = _owner_certificate_2
assemble_portable_distributed_commit_certificate = _owner_certificate_3
distributed_commit_certificate_payload = _owner_certificate_4
distributed_commit_certificate_fingerprint = _owner_certificate_5
distributed_commit_certificate_from_payload = _owner_certificate_6
verify_distributed_commit_certificate = _owner_certificate_7


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
    """Compatibility entry point for the static certificate state transition."""

    return _owner_certificate_8(
        state,
        certificate,
        commit_policy=commit_policy,
        portable_certificate=portable_certificate,
        trusted_issuer_attestations=trusted_issuer_attestations,
        trusted_witness_attestations=trusted_witness_attestations,
        current_step=current_step,
    )


distributed_commit_certificate_is_current_final = _owner_certificate_9
verify_distributed_commit_finality = _owner_certificate_10
EpochTransitionCertificate = _owner_epoch_0
epoch_transition_decision_ref = _owner_epoch_1
epoch_transition_certificate_body_root = _owner_epoch_2
issue_epoch_transition_certificate = _owner_epoch_3
epoch_transition_certificate_payload = _owner_epoch_4
epoch_transition_certificate_fingerprint = _owner_epoch_5
epoch_transition_certificate_from_payload = _owner_epoch_6
verify_epoch_transition_certificate = _owner_epoch_7
transition_distributed_commit_epoch = _owner_epoch_8
DistributedFinalityKind = _owner_finality_0
DistributedFinalityDecision = _owner_finality_1
evaluate_distributed_finality = _owner_finality_2
distributed_finality_decision_payload = _owner_finality_3
distributed_finality_decision_fingerprint = _owner_finality_4
distributed_finality_decision_from_payload = _owner_finality_5
distributed_finality_decision_is_authoritative = _owner_finality_6

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
