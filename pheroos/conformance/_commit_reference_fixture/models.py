"""Dependency-leaf records and deterministic identifiers for Commit fixtures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import re

from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
)
from pheroos.governance.challenge import VerifiedChallenge
from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitAssessment,
    CommitEvaluationContext,
)
from pheroos.governance.commit_state import CommitReplayState, CommitWindowState
from pheroos.governance.distributed_commit import (
    DistributedCommitProposal,
    DistributedCommitState,
    WitnessVerification,
)
from pheroos.governance.evidence_binding import EvidenceBinding
from pheroos.governance.observation import VerifiedObservation
from pheroos.governance.permission import ActionPermission
from pheroos.governance.principal import PrincipalVerification
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
)
from pheroos.governance.stop_signal import StopResolutionVerification
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseReplayState,
)
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.models import CapabilityManifest


REFERENCE_TARGET = "decision:optimal"
REFERENCE_PROTOCOL_ID = "protocol:tck:optimal-commit"
REFERENCE_EPOCH = 3
REFERENCE_CHALLENGE_CATEGORY = "independent_replication"
REFERENCE_LEADER = "candidate:alpha"
REFERENCE_OTHER = "candidate:beta"
REFERENCE_FALLBACK = "candidate:fallback"


def reference_fingerprint(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def reference_namespace(vector_id: str, variant: str = "base") -> str:
    """Return a deterministic, JSON/text-safe strong-authority namespace."""

    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", f"{vector_id}:{variant}")
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"tck:{normalized}:{digest}"


@dataclass(frozen=True)
class ReferenceScenario:
    namespace: str
    manifest: CapabilityManifest
    policy: object
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    leader_id: str
    other_id: str
    fallback_id: str
    claims: Mapping[str, str]
    principals: tuple[PrincipalVerification, ...]
    membership_snapshot: EligiblePrincipalSnapshot
    membership_state: EligibleMembershipEpochState
    observations: Mapping[str, tuple[VerifiedObservation, ...]]
    challenges: Mapping[str, VerifiedChallenge]
    bindings: Mapping[str, EvidenceBinding]
    candidate_inputs: tuple[CandidateCommitInput, ...]
    leases: tuple[SupportLease, ...]
    support_replay_state: SupportLeaseReplayState
    risk_chain_state: RiskAssessmentChainState
    risk_assessment: RiskAssessment
    threshold: CommitThresholdSnapshot
    replay_state: CommitReplayState
    context: CommitEvaluationContext
    stop_resolution: StopResolutionVerification
    permission: ActionPermission


@dataclass(frozen=True)
class ReferenceStableCommit:
    scenario: ReferenceScenario
    assessments: tuple[CommitAssessment, ...]
    window: CommitWindowState
    output_fingerprint: str
    receipt: LocalCommitReceipt


@dataclass(frozen=True)
class ReferencePortableCommit:
    stable: ReferenceStableCommit
    certificate: EvidenceCommitCertificate
    trusted_issuer_attestations: Mapping[str, str]


@dataclass(frozen=True)
class ReferenceDistributedCommit:
    portable: ReferencePortableCommit
    proposal: DistributedCommitProposal
    state: DistributedCommitState
    verifications: tuple[WitnessVerification, ...]
    trusted_witness_attestations: Mapping[str, str]


# These records remain facade-owned ABI fixtures for introspection and pickle.
for _record in (
    ReferenceScenario,
    ReferenceStableCommit,
    ReferencePortableCommit,
    ReferenceDistributedCommit,
):
    _record.__module__ = "pheroos.conformance._commit_reference"


__all__ = [
    "REFERENCE_CHALLENGE_CATEGORY",
    "REFERENCE_EPOCH",
    "REFERENCE_FALLBACK",
    "REFERENCE_LEADER",
    "REFERENCE_OTHER",
    "REFERENCE_PROTOCOL_ID",
    "REFERENCE_TARGET",
    "ReferenceDistributedCommit",
    "ReferencePortableCommit",
    "ReferenceScenario",
    "ReferenceStableCommit",
    "reference_fingerprint",
    "reference_namespace",
]
