from __future__ import annotations

from dataclasses import dataclass

from pheroos.protocol.models import CapabilityManifest, has_hybrid_pheromone_features, is_swarm_policy


CORE_PROFILE_VERSION = "pheroos-core-v1"
SWARM_PROFILE_VERSION = "pheroos-swarm-v1"
HYBRID_SWARM_PROFILE_VERSION = "pheroos-hybrid-swarm-v1"
MANIFEST_PROFILE_VERSION = "pheroos-manifest-v1"
SOURCE_PROFILE_VERSION = "pheroos-source-v1"


@dataclass(frozen=True)
class ConformanceProfile:
    name: str = "core"
    version: str = CORE_PROFILE_VERSION
    required_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_checks", tuple(self.required_checks))


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

SWARM_PROFILE = ConformanceProfile(
    name="swarm",
    version=SWARM_PROFILE_VERSION,
    required_checks=(
        *CORE_PROFILE.required_checks,
        "collective_policy",
        "safe_fallback_collective",
        "score_breakdown_contract",
        "pheromone_policy",
        "pheromone_behavior",
        "swarm_trace_contract",
    ),
)

HYBRID_SWARM_PROFILE = ConformanceProfile(
    name="hybrid-swarm",
    version=HYBRID_SWARM_PROFILE_VERSION,
    required_checks=(
        *SWARM_PROFILE.required_checks,
        "pheromone_subject_scoring",
        "pheromone_kind_profile",
        "pheromone_diffusion",
        "pheromone_reinforcement",
        "pheromone_response_model",
        "layer_coordination_policy",
        "policy_adjustment_bounds",
        "hybrid_trace_contract",
        "hybrid_authority_boundary",
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
        "public_abi_boundary",
    ),
)


def profile_for_manifest(manifest: CapabilityManifest) -> ConformanceProfile:
    if has_hybrid_pheromone_features(manifest.protocol.collective_decision_policy):
        return HYBRID_SWARM_PROFILE
    if is_swarm_policy(manifest.protocol.collective_decision_policy):
        return SWARM_PROFILE
    return CORE_PROFILE
