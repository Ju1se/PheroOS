from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest, SUPPORTED_PHEROMONE_DECAY_MODELS


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
    return CheckResult("pheromone_policy", not problems, ", ".join(problems))
