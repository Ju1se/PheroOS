from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import (
    CapabilityManifest,
    SUPPORTED_PHEROMONE_COMPETITION_MODES,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    SUPPORTED_PHEROMONE_RESPONSE_MODELS,
    is_scored_pheromone_subject_type,
)


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return CheckResult("pheromone_policy", True)
    problems: list[str] = []
    if not 0 <= policy.pheromone_evaporation_rate <= 1:
        problems.append("evaporation_rate")
    if policy.pheromone_decay_model not in SUPPORTED_PHEROMONE_DECAY_MODELS:
        problems.append("decay_model")
    if policy.pheromone_min_strength > policy.pheromone_max_strength:
        problems.append("strength_bounds")
    if (
        policy.pheromone_positive_weight < 0
        or policy.pheromone_negative_weight < 0
        or policy.pheromone_cautionary_weight < 0
        or policy.pheromone_novelty_weight < 0
    ):
        problems.append("weights")
    if policy.pheromone_cautionary_override_threshold < 0:
        problems.append("cautionary_threshold")
    if policy.pheromone_per_source_cap < 0 or policy.pheromone_per_round_deposit_cap < 0:
        problems.append("caps")
    if policy.pheromone_min_source_diversity <= 0:
        problems.append("min_source_diversity")
    if any(
        not isinstance(subject_type, str)
        or not is_scored_pheromone_subject_type(subject_type)
        for subject_type in policy.pheromone_scored_subject_types
    ):
        problems.append("scored_subject_types")
    if policy.pheromone_response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
        problems.append("response_model")
    if policy.pheromone_competition_mode not in SUPPORTED_PHEROMONE_COMPETITION_MODES:
        problems.append("competition_mode")
    if (
        policy.pheromone_activation_threshold < 0
        or policy.pheromone_saturation_threshold < 0
        or policy.pheromone_exploration_floor < 0
        or policy.exploration_floor < 0
        or policy.stale_route_reopen_threshold < 0
    ):
        problems.append("thresholds")
    if policy.pheromone_diffusion_max_hops < 0 or not 0 <= policy.pheromone_diffusion_attenuation <= 1:
        problems.append("diffusion")
    if not 0 <= policy.novelty_decay_rate <= 1:
        problems.append("novelty_decay")
    for kind, profile in policy.pheromone_kind_profiles.items():
        if (
            profile.weight < 0
            or (profile.evaporation_rate is not None and not 0 <= profile.evaporation_rate <= 1)
            or (profile.ttl_steps is not None and profile.ttl_steps < 0)
            or profile.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS
            or any(
                not isinstance(subject_type, str)
                or not is_scored_pheromone_subject_type(subject_type)
                for subject_type in profile.scored_subject_types
            )
        ):
            problems.append("kind_profiles")
            break
        if kind == "stale" and (profile.weight != 0 or profile.scored_subject_types):
            problems.append("stale_profile")
            break
    return CheckResult("pheromone_policy", not problems, ", ".join(problems))
