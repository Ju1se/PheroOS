from __future__ import annotations

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import (
    layer_coordination_policy_from_collective,
    validate_layer_coordination_policy,
)
from pheroos.governance.pheromone import (
    diffusion_policy_from_collective,
    pheromone_policy_from_collective,
    validate_pheromone_diffusion_policy,
    validate_pheromone_policy,
)
from pheroos.governance.policy_adjustment import validate_policy_adjustment_bounds
from pheroos.protocol.models import (
    SUPPORTED_COLLECTIVE_MODES,
    SUPPORTED_LAYER_IDS,
    CollectiveDecisionPolicy,
    has_hybrid_pheromone_features,
)


def validate_collective_runtime_policy(policy: CollectiveDecisionPolicy) -> None:
    """Fail closed for a policy object constructed directly by a runtime."""

    if not isinstance(policy, CollectiveDecisionPolicy):
        raise GovernanceError("collective policy must use the canonical protocol declaration")
    if policy.mode not in SUPPORTED_COLLECTIVE_MODES:
        raise GovernanceError(f"collective policy mode is unsupported: {policy.mode}")
    for field_name in ("min_independent_scouts", "quorum_threshold"):
        value = getattr(policy, field_name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise GovernanceError(f"collective policy {field_name} must be a positive integer")
    for field_name in (
        "recruitment_enabled",
        "inhibition_enabled",
        "pheromone_enabled",
        "pheromone_diffusion_enabled",
        "pheromone_feedback_enabled",
        "exploration_enabled",
        "layer_coordination_enabled",
        "layer_fallback_on_unresolved_conflict",
    ):
        if not isinstance(getattr(policy, field_name), bool):
            raise GovernanceError(f"collective policy {field_name} must be boolean")
    if not isinstance(policy.fallback_candidate, str):
        raise GovernanceError("collective policy fallback_candidate must be a string")

    validate_pheromone_policy(pheromone_policy_from_collective(policy))
    validate_pheromone_diffusion_policy(diffusion_policy_from_collective(policy))
    validate_layer_coordination_policy(layer_coordination_policy_from_collective(policy))
    validate_policy_adjustment_bounds(policy)

    if has_hybrid_pheromone_features(policy) and policy.mode != "hybrid":
        raise GovernanceError("collective policy Hybrid features require mode='hybrid'")
    if policy.mode == "hybrid" and not (
        policy.pheromone_enabled
        and policy.pheromone_diffusion_enabled
        and policy.pheromone_feedback_enabled
        and policy.layer_coordination_enabled
        and bool(policy.pheromone_kind_profiles)
        and bool(policy.policy_adjustment_bounds)
        and policy.pheromone_require_provenance
        and policy.pheromone_require_trace
    ):
        raise GovernanceError("collective policy mode='hybrid' requires the complete Hybrid path")
    if policy.mode == "hybrid" and any(
        value <= 0
        for value in (
            policy.pheromone_max_strength,
            policy.pheromone_per_source_cap,
            policy.pheromone_per_round_deposit_cap,
        )
    ):
        raise GovernanceError(
            "collective policy mode='hybrid' requires positive pheromone strength and budgets"
        )
    if policy.mode == "hybrid" and any(
        policy.pheromone_min_strength > bound
        for bound in (
            policy.pheromone_max_strength,
            policy.pheromone_per_source_cap,
            policy.pheromone_per_round_deposit_cap,
        )
    ):
        raise GovernanceError(
            "collective policy minimum pheromone strength must fit max/source/round bounds"
        )
    if policy.layer_coordination_enabled:
        expected_layers = set(SUPPORTED_LAYER_IDS)
        for field_name, declared in (
            ("layer_weight_bounds", set(policy.layer_weight_bounds)),
            ("layer_default_weights", set(policy.layer_default_weights)),
            ("layer_confidence_thresholds", set(policy.layer_confidence_thresholds)),
        ):
            if declared != expected_layers:
                raise GovernanceError(
                    f"collective policy {field_name} must cover every supported layer"
                )


def resolve_collective_fallback_id(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    fallback_candidate_id: str | None,
) -> str:
    """Resolve fallback without allowing a caller to override policy authority."""

    if not isinstance(candidate_set, CandidateSet):
        raise GovernanceError("collective fallback resolution requires a candidate set")
    if policy.fallback_candidate:
        if fallback_candidate_id is not None and fallback_candidate_id != policy.fallback_candidate:
            raise GovernanceError("runtime fallback cannot override the declared collective fallback")
        return policy.fallback_candidate
    safe_candidates = sorted(
        candidate.id
        for candidate in candidate_set.candidates
        if candidate.target == target and candidate.safe_fallback
    )
    if len(safe_candidates) != 1:
        raise GovernanceError(
            "collective policy without an explicit fallback requires exactly one safe fallback"
        )
    if fallback_candidate_id is not None and fallback_candidate_id != safe_candidates[0]:
        raise GovernanceError("runtime fallback does not match the unique declared safe fallback")
    return safe_candidates[0]
