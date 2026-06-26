from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.protocol.models import CapabilityManifest, is_swarm_policy


CORE_PROFILE_VERSION = "pheroos-core-v1"
SWARM_PROFILE_VERSION = "pheroos-swarm-v1"
MANIFEST_PROFILE_VERSION = "pheroos-manifest-v1"


@dataclass(frozen=True)
class ConformanceProfile:
    name: str = "core"
    version: str = CORE_PROFILE_VERSION
    required_checks: list[str] = field(default_factory=list)


CORE_PROFILE = ConformanceProfile(
    name="core",
    version=CORE_PROFILE_VERSION,
    required_checks=[
        "manifest_schema",
        "candidate_declaration",
        "quorum_policy",
        "recovery_policy",
        "output_contract",
        "trace_contract",
        "driver_contract",
        "extension_contract",
        "domain_neutrality_public_core",
        "kernel_import_boundary",
    ],
)

SWARM_PROFILE = ConformanceProfile(
    name="swarm",
    version=SWARM_PROFILE_VERSION,
    required_checks=[
        *CORE_PROFILE.required_checks,
        "collective_policy",
        "safe_fallback_collective",
        "pheromone_policy",
        "pheromone_behavior",
        "swarm_trace_contract",
    ],
)

MANIFEST_PROFILE = ConformanceProfile(
    name="manifest",
    version=MANIFEST_PROFILE_VERSION,
    required_checks=["manifest_schema"],
)


def profile_for_manifest(manifest: CapabilityManifest) -> ConformanceProfile:
    if is_swarm_policy(manifest.protocol.collective_decision_policy):
        return SWARM_PROFILE
    return CORE_PROFILE
