from __future__ import annotations

from dataclasses import dataclass

from pheroos.protocol.commit_models import (
    CERTIFIED_COMMIT_PROFILE_VERSION as CERTIFIED_COMMIT_PROFILE_VERSION,
    COMMIT_INTEGRITY_PROFILE_VERSION as COMMIT_INTEGRITY_PROFILE_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION as DISTRIBUTED_COMMIT_PROFILE_VERSION,
    HYBRID_COMMIT_PROFILE_VERSION as HYBRID_COMMIT_PROFILE_VERSION,
    SUPPORTED_COMMIT_ASSURANCES,
    CollectiveCommitPolicy,
)
from pheroos.protocol.models import (
    SUPPORTED_PROTOCOL_VERSIONS,
    CapabilityManifest,
    has_hybrid_pheromone_features,
)

CORE_PROFILE_VERSION = "pheroos-core-v1"
MANIFEST_PROFILE_VERSION = "pheroos-manifest-v1"
SOURCE_PROFILE_VERSION = "pheroos-source-v3"


@dataclass(frozen=True)
class ConformanceProfile:
    name: str = "core"
    version: str = CORE_PROFILE_VERSION
    required_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        checks = tuple(self.required_checks)
        if not self.name or not self.version:
            raise ValueError("conformance profile identity must be non-empty")
        if any(not isinstance(item, str) or not item for item in checks):
            raise ValueError("conformance profile checks must be non-empty strings")
        if len(checks) != len(set(checks)):
            raise ValueError("conformance profile checks must be unique")
        object.__setattr__(self, "required_checks", checks)


CORE_PROFILE = ConformanceProfile(
    name="core",
    version=CORE_PROFILE_VERSION,
    required_checks=(
        "manifest_schema",
        "candidate_declaration",
        "quorum_policy",
        "recovery_policy",
        "output_contract",
        "trace_contract",
        "driver_contract",
        "kernel_contract",
        "extension_contract",
    ),
)

COMMIT_AUTHORITY_CHECKS = (
    "commit_policy_contract",
    "commit_numeric_contract",
    "principal_attestation_contract",
    "risk_monotonicity_contract",
    "membership_snapshot_contract",
    "observation_binding_contract",
    "counterevidence_contract",
    "challenge_coverage_contract",
    "support_lease_contract",
    "commit_metrics_contract",
    "commit_window_contract",
    "commit_liveness_contract",
    "commit_authority_boundary",
    "commit_trace_contract",
    "commit_certificate_contract",
    "certificate_output_contract",
    "no_assurance_downgrade",
)

COMMIT_STRUCTURAL_CHECKS = (
    "manifest_schema",
    "candidate_declaration",
    "quorum_policy",
    "recovery_policy",
    "driver_contract",
    "kernel_contract",
    "extension_contract",
)

HYBRID_ATTENTION_CHECKS = (
    "collective_policy",
    "layer_coordination_policy",
    "policy_adjustment_bounds",
)

COMMIT_INTEGRITY_PROFILE = ConformanceProfile(
    name="commit-integrity",
    version=COMMIT_INTEGRITY_PROFILE_VERSION,
    required_checks=(*COMMIT_STRUCTURAL_CHECKS, *COMMIT_AUTHORITY_CHECKS),
)

HYBRID_COMMIT_PROFILE = ConformanceProfile(
    name="hybrid-commit",
    version=HYBRID_COMMIT_PROFILE_VERSION,
    required_checks=(
        *COMMIT_STRUCTURAL_CHECKS,
        *HYBRID_ATTENTION_CHECKS,
        *COMMIT_AUTHORITY_CHECKS,
        "commit_channel_separation",
    ),
)

CERTIFIED_COMMIT_PROFILE = ConformanceProfile(
    name="certified-commit",
    version=CERTIFIED_COMMIT_PROFILE_VERSION,
    required_checks=(
        *COMMIT_STRUCTURAL_CHECKS,
        *COMMIT_AUTHORITY_CHECKS,
    ),
)

DISTRIBUTED_COMMIT_PROFILE = ConformanceProfile(
    name="distributed-commit",
    version=DISTRIBUTED_COMMIT_PROFILE_VERSION,
    required_checks=(
        *CERTIFIED_COMMIT_PROFILE.required_checks,
        "distributed_finality_contract",
        "certificate_conflict_contract",
    ),
)

MANIFEST_PROFILE = ConformanceProfile(
    name="manifest",
    version=MANIFEST_PROFILE_VERSION,
    required_checks=("manifest_schema",),
)

SOURCE_PROFILE = ConformanceProfile(
    name="source",
    version=SOURCE_PROFILE_VERSION,
    required_checks=(
        "source_surface",
        "domain_neutrality_public_core",
        "package_import_boundary",
        "driver_lifecycle_boundary",
        "runtime_scope_contract",
        "authority_ledger_contract",
        "trace_store_contract",
        "public_abi_boundary",
    ),
)


def profile_for_manifest(manifest: CapabilityManifest) -> ConformanceProfile:
    if manifest.protocol.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise ValueError("protocol version is unsupported")
    commit_policy = manifest.protocol.collective_commit_policy
    if commit_policy is not None:
        return _commit_profile(manifest, commit_policy)
    return CORE_PROFILE


def _commit_profile(
    manifest: CapabilityManifest,
    commit_policy: CollectiveCommitPolicy,
) -> ConformanceProfile:
    if commit_policy.policy_version != COMMIT_POLICY_VERSION:
        raise ValueError("collective commit policy version is unsupported")
    if commit_policy.model != COMMIT_MODEL:
        raise ValueError("collective commit model is unsupported")
    if commit_policy.assurance not in SUPPORTED_COMMIT_ASSURANCES:
        raise ValueError("collective commit assurance is unsupported")
    hybrid_attention = has_hybrid_pheromone_features(
        manifest.protocol.collective_decision_policy
    )
    profile = _base_commit_profile(commit_policy.assurance, hybrid_attention)
    if not hybrid_attention or profile is HYBRID_COMMIT_PROFILE:
        return profile
    return ConformanceProfile(
        name=profile.name,
        version=profile.version,
        required_checks=(
            *profile.required_checks,
            *(
                check
                for check in HYBRID_ATTENTION_CHECKS
                if check not in profile.required_checks
            ),
            "commit_channel_separation",
        ),
    )


def _base_commit_profile(
    assurance: str,
    hybrid_attention: bool,
) -> ConformanceProfile:
    if assurance == "distributed":
        return DISTRIBUTED_COMMIT_PROFILE
    if assurance == "certified":
        return CERTIFIED_COMMIT_PROFILE
    if assurance == "evidence_bound" and hybrid_attention:
        return HYBRID_COMMIT_PROFILE
    return COMMIT_INTEGRITY_PROFILE
