from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from pheroos.protocol._immutable import (
    deep_freeze as _deep_freeze,
    snapshot_fields as _snapshot_fields,
)


COMMIT_POLICY_VERSION = "pheroos-collective-commit-policy-v1"
COMMIT_MODEL = "optimal_evidence_v1"
COMMIT_WIRE_VERSION = "pheroos-commit-wire-v1"
COMMIT_CANONICAL_VERSION = "pheroos-commit-canonical-v1"
COMMIT_INTEGRITY_PROFILE_VERSION = "pheroos-commit-integrity-v1"
HYBRID_COMMIT_PROFILE_VERSION = "pheroos-hybrid-commit-v1"
CERTIFIED_COMMIT_PROFILE_VERSION = "pheroos-certified-commit-v1"
DISTRIBUTED_COMMIT_PROFILE_VERSION = "pheroos-distributed-commit-v1"
WEIGHT_SCALE = 1_000_000
MAX_AUTHORITY_INTEGER = (2**53) - 1



class CommitAssurance(StrEnum):
    ADVISORY = "advisory"
    EVIDENCE_BOUND = "evidence_bound"
    CERTIFIED = "certified"
    DISTRIBUTED = "distributed"


class CommitAction(StrEnum):
    COMMIT = "commit"
    PUBLISH = "publish"
    EXECUTE = "execute"
    EPOCH_TRANSITION = "epoch_transition"
    RECOVERY = "recovery"


SUPPORTED_COMMIT_ASSURANCES = frozenset(item.value for item in CommitAssurance)
SUPPORTED_COMMIT_PROFILES = frozenset(
    {
        COMMIT_INTEGRITY_PROFILE_VERSION,
        HYBRID_COMMIT_PROFILE_VERSION,
        CERTIFIED_COMMIT_PROFILE_VERSION,
        DISTRIBUTED_COMMIT_PROFILE_VERSION,
    }
)
COMMIT_PROFILES_BY_ASSURANCE = MappingProxyType(
    {
        CommitAssurance.ADVISORY.value: frozenset(
            {COMMIT_INTEGRITY_PROFILE_VERSION}
        ),
        CommitAssurance.EVIDENCE_BOUND.value: frozenset(
            {COMMIT_INTEGRITY_PROFILE_VERSION, HYBRID_COMMIT_PROFILE_VERSION}
        ),
        CommitAssurance.CERTIFIED.value: frozenset(
            {CERTIFIED_COMMIT_PROFILE_VERSION}
        ),
        CommitAssurance.DISTRIBUTED.value: frozenset(
            {DISTRIBUTED_COMMIT_PROFILE_VERSION}
        ),
    }
)
COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE = MappingProxyType(
    {
        CommitAssurance.EVIDENCE_BOUND.value: "governance_local",
        CommitAssurance.CERTIFIED.value: "certified",
        CommitAssurance.DISTRIBUTED.value: "distributed",
    }
)
SUPPORTED_RISK_BANDS = ("LOW", "MODERATE", "HIGH", "CRITICAL")
SUPPORTED_TERMINAL_OUTCOMES = frozenset(
    {
        "evidence_commit",
        "safe_fallback",
        "advisory",
        "blocked",
        "invalid",
        "finality_unavailable",
        "safety_violation",
    }
)
SUPPORTED_DEADLINE_OUTCOMES = frozenset({"safe_fallback", "advisory"})
SUPPORTED_CERTIFICATE_MODES = frozenset(
    {"none", "local_receipt", "portable", "distributed"}
)
REQUIRED_COMMIT_RESET_RULES = frozenset(
    {
        "leader_change",
        "gate_failure",
        "step_gap",
        "policy_change",
        "risk_change",
        "membership_change",
        "epoch_change",
    }
)


@dataclass(frozen=True)
class EvidenceQualificationPolicy:
    numeric_scale: int
    minimum_quality_ppm: int
    minimum_relevance_ppm: int
    positive_group_cap: int
    counter_group_cap: int
    counter_weight_ppm: int
    minimum_positive_evidence: int
    maximum_counterevidence: int
    maximum_counterevidence_ratio_ppm: int
    domain_contribution_floor: int
    minimum_source_diversity: int
    required_challenge_categories: list[str]
    observation_ttl_steps: int
    require_provenance: bool
    require_trace: bool
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(
            self,
            sequences=("required_challenge_categories",),
            mappings=("extensions",),
        )


@dataclass(frozen=True)
class SupportLeasePolicy:
    minimum_support_clusters: int
    support_ratio_ppm: int
    lease_ttl_steps: int
    membership_mode: str
    switch_mode: str
    equivocation_mode: str
    evidence_reference_required: bool
    cluster_verification_required: bool
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class RiskBandPolicy:
    minimum_positive_evidence: int
    maximum_counterevidence: int
    maximum_counterevidence_ratio_ppm: int
    minimum_support_clusters: int
    minimum_support_ratio_ppm: int
    minimum_source_diversity: int
    minimum_margin: int
    stability_steps: int
    required_challenge_categories: list[str]
    minimum_assurance: str
    publishable_outcomes: list[str]
    executable_outcomes: list[str]
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(
            self,
            sequences=(
                "required_challenge_categories",
                "publishable_outcomes",
                "executable_outcomes",
            ),
            mappings=("extensions",),
        )


@dataclass(frozen=True)
class CommitWindowPolicy:
    minimum_stability_steps: int
    deliberation_deadline_steps: int
    maximum_leader_resets: int
    maximum_epoch_restarts: int
    run_deadline_steps: int
    reset_rules: list[str]
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(
            self,
            sequences=("reset_rules",),
            mappings=("extensions",),
        )


@dataclass(frozen=True)
class TerminalOutcomePolicy:
    safe_fallback_candidate: str
    deadline_outcome: str
    policy_incomplete_outcome: str
    finality_unavailable_outcome: str
    deliverable_outcomes: list[str]
    publishable_outcomes: list[str]
    executable_outcomes: list[str]
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(
            self,
            sequences=(
                "deliverable_outcomes",
                "publishable_outcomes",
                "executable_outcomes",
            ),
            mappings=("extensions",),
        )


@dataclass(frozen=True)
class CertificatePolicy:
    mode: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    issuer_attestation_required: bool
    independent_verification_required: bool
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class DistributedCommitPolicy:
    fault_model: str
    membership_mode: str
    membership_size: int
    max_byzantine_faults: int
    witness_quorum: int
    witness_ttl_steps: int
    minimum_failure_domain_diversity: int
    epoch_transition_rule: str
    conflict_rule: str
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class CollectiveCommitPolicy:
    policy_version: str
    model: str
    assurance: str
    target: str
    evidence_qualification: EvidenceQualificationPolicy
    support_lease: SupportLeasePolicy
    risk_bands: dict[str, RiskBandPolicy]
    commit_window: CommitWindowPolicy
    terminal_outcome: TerminalOutcomePolicy
    certificate: CertificatePolicy
    distributed: DistributedCommitPolicy | None
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _snapshot_fields(
            self,
            mappings=("risk_bands", "extensions"),
        )


__all__ = [
    "COMMIT_CANONICAL_VERSION",
    "COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE",
    "COMMIT_PROFILES_BY_ASSURANCE",
    "CERTIFIED_COMMIT_PROFILE_VERSION",
    "COMMIT_MODEL",
    "COMMIT_POLICY_VERSION",
    "COMMIT_WIRE_VERSION",
    "COMMIT_INTEGRITY_PROFILE_VERSION",
    "DISTRIBUTED_COMMIT_PROFILE_VERSION",
    "HYBRID_COMMIT_PROFILE_VERSION",
    "MAX_AUTHORITY_INTEGER",
    "REQUIRED_COMMIT_RESET_RULES",
    "SUPPORTED_CERTIFICATE_MODES",
    "SUPPORTED_COMMIT_ASSURANCES",
    "SUPPORTED_COMMIT_PROFILES",
    "SUPPORTED_DEADLINE_OUTCOMES",
    "SUPPORTED_RISK_BANDS",
    "SUPPORTED_TERMINAL_OUTCOMES",
    "WEIGHT_SCALE",
    "CertificatePolicy",
    "CommitAction",
    "CommitAssurance",
    "CollectiveCommitPolicy",
    "CommitWindowPolicy",
    "DistributedCommitPolicy",
    "EvidenceQualificationPolicy",
    "RiskBandPolicy",
    "SupportLeasePolicy",
    "TerminalOutcomePolicy",
]
