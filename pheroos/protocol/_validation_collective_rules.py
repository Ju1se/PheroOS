from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from pheroos.protocol._validation_hybrid_rules import validate_hybrid_rules
from pheroos.protocol._validation_primitives import (
    ALLOWED_POLICY_ADJUSTMENT_FIELDS,
    MAX_LAYER_WEIGHT,
    SAFETY_CRITICAL_POLICY_ADJUSTMENT_FIELDS,
    finite_in_range,
    finite_non_negative,
    finite_number,
    non_negative_integer,
    positive_integer,
    valid_absolute_bounds,
    valid_non_negative_bounds,
    valid_policy_adjustment_bound,
    validation_error,
)
from pheroos.protocol.models import (
    SUPPORTED_COLLECTIVE_MODES,
    SUPPORTED_LAYER_IDS,
    SUPPORTED_PHEROMONE_COMPETITION_MODES,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    SUPPORTED_PHEROMONE_RESPONSE_MODELS,
    CandidateSpec,
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    ProtocolManifest,
    ValidationDiagnostic,
    is_scored_pheromone_subject_type,
    is_supported_pheromone_kind,
)


_CollectiveRule = Callable[
    [CollectiveDecisionPolicy],
    list[ValidationDiagnostic],
]


def validate_collective_rules(
    protocol: ProtocolManifest,
    policy: CollectiveDecisionPolicy,
    *,
    candidate_ids: frozenset[str],
    candidates_by_id: Mapping[str, CandidateSpec],
    safe_candidates: frozenset[str],
) -> list[ValidationDiagnostic]:
    diagnostics = [
        diagnostic for rule in _COLLECTIVE_RULES for diagnostic in rule(policy)
    ]
    diagnostics.extend(
        validate_hybrid_rules(
            protocol,
            policy,
            candidate_ids=candidate_ids,
            candidates_by_id=candidates_by_id,
            safe_candidates=safe_candidates,
        )
    )
    return diagnostics


def _validate_collective_authority(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if policy.mode not in SUPPORTED_COLLECTIVE_MODES:
        diagnostics.append(
            validation_error(
                "collective_mode_unsupported",
                "collective decision mode is unsupported",
                "protocol.collective_decision_policy.mode",
            )
        )
    if not positive_integer(policy.min_independent_scouts):
        diagnostics.append(
            validation_error(
                "collective_min_scouts_invalid",
                "min_independent_scouts must be positive",
                "protocol.collective_decision_policy.min_independent_scouts",
            )
        )
    if not positive_integer(policy.quorum_threshold):
        diagnostics.append(
            validation_error(
                "collective_quorum_threshold_invalid",
                "quorum_threshold must be positive",
                "protocol.collective_decision_policy.quorum_threshold",
            )
        )
    return diagnostics


def _validate_pheromone_memory(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if not finite_in_range(policy.pheromone_evaporation_rate, 0, 1):
        diagnostics.append(
            validation_error(
                "collective_pheromone_evaporation_invalid",
                "pheromone evaporation rate must be between 0 and 1",
                "protocol.collective_decision_policy.pheromone_evaporation_rate",
            )
        )
    if policy.pheromone_decay_model not in SUPPORTED_PHEROMONE_DECAY_MODELS:
        diagnostics.append(
            validation_error(
                "collective_pheromone_decay_model_invalid",
                "pheromone decay model is unsupported",
                "protocol.collective_decision_policy.pheromone_decay_model",
            )
        )
    if not valid_non_negative_bounds(
        policy.pheromone_min_strength,
        policy.pheromone_max_strength,
    ):
        diagnostics.append(
            validation_error(
                "collective_pheromone_strength_bounds_invalid",
                "pheromone strength bounds must be finite, non-negative, and ordered",
                "protocol.collective_decision_policy",
            )
        )
    if any(
        not finite_non_negative(value)
        for value in (
            policy.pheromone_positive_weight,
            policy.pheromone_negative_weight,
            policy.pheromone_cautionary_weight,
            policy.pheromone_novelty_weight,
        )
    ):
        diagnostics.append(
            validation_error(
                "collective_pheromone_weight_invalid",
                "pheromone weights must be non-negative",
                "protocol.collective_decision_policy",
            )
        )
    if not finite_non_negative(policy.pheromone_cautionary_override_threshold):
        diagnostics.append(
            validation_error(
                "collective_pheromone_cautionary_threshold_invalid",
                "pheromone cautionary override threshold must be non-negative",
                "protocol.collective_decision_policy.pheromone_cautionary_override_threshold",
            )
        )
    if not finite_non_negative(
        policy.pheromone_per_source_cap
    ) or not finite_non_negative(policy.pheromone_per_round_deposit_cap):
        diagnostics.append(
            validation_error(
                "collective_pheromone_cap_invalid",
                "pheromone caps must be non-negative",
                "protocol.collective_decision_policy",
            )
        )
    if not positive_integer(policy.pheromone_min_source_diversity):
        diagnostics.append(
            validation_error(
                "collective_pheromone_source_diversity_invalid",
                "pheromone min source diversity must be positive",
                "protocol.collective_decision_policy.pheromone_min_source_diversity",
            )
        )
    return diagnostics


def _validate_pheromone_response(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if not policy.pheromone_scored_subject_types:
        diagnostics.append(
            validation_error(
                "collective_pheromone_subject_types_empty",
                "pheromone scored subject types must not be empty",
                "protocol.collective_decision_policy.pheromone_scored_subject_types",
            )
        )
    diagnostics.extend(
        validation_error(
            "collective_pheromone_subject_type_invalid",
            "pheromone scored subject type is unsupported or non-scoring",
            "protocol.collective_decision_policy.pheromone_scored_subject_types",
        )
        for subject_type in policy.pheromone_scored_subject_types
        if not isinstance(subject_type, str)
        or not is_scored_pheromone_subject_type(subject_type)
    )
    if policy.pheromone_response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
        diagnostics.append(
            validation_error(
                "collective_pheromone_response_model_invalid",
                "pheromone response model is unsupported",
                "protocol.collective_decision_policy.pheromone_response_model",
            )
        )
    if policy.pheromone_competition_mode not in SUPPORTED_PHEROMONE_COMPETITION_MODES:
        diagnostics.append(
            validation_error(
                "collective_pheromone_competition_mode_invalid",
                "pheromone competition mode is unsupported",
                "protocol.collective_decision_policy.pheromone_competition_mode",
            )
        )
    if any(
        not finite_non_negative(value)
        for value in (
            policy.pheromone_activation_threshold,
            policy.pheromone_saturation_threshold,
            policy.stale_route_reopen_threshold,
        )
    ) or any(
        not finite_in_range(value, 0, 1)
        for value in (
            policy.pheromone_exploration_floor,
            policy.exploration_floor,
        )
    ):
        diagnostics.append(
            validation_error(
                "collective_pheromone_threshold_invalid",
                "pheromone thresholds must be non-negative and exploration floors must be between 0 and 1",
                "protocol.collective_decision_policy",
            )
        )
    if not finite_in_range(policy.pheromone_diffusion_attenuation, 0, 1):
        diagnostics.append(
            validation_error(
                "collective_pheromone_diffusion_attenuation_invalid",
                "pheromone diffusion attenuation must be between 0 and 1",
                "protocol.collective_decision_policy.pheromone_diffusion_attenuation",
            )
        )
    if not non_negative_integer(policy.pheromone_diffusion_max_hops):
        diagnostics.append(
            validation_error(
                "collective_pheromone_diffusion_hops_invalid",
                "pheromone diffusion max hops must be non-negative",
                "protocol.collective_decision_policy.pheromone_diffusion_max_hops",
            )
        )
    if not finite_in_range(policy.novelty_decay_rate, 0, 1):
        diagnostics.append(
            validation_error(
                "collective_pheromone_novelty_decay_invalid",
                "novelty decay rate must be between 0 and 1",
                "protocol.collective_decision_policy.novelty_decay_rate",
            )
        )
    return diagnostics


def _validate_pheromone_profiles(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for kind, profile in policy.pheromone_kind_profiles.items():
        if not isinstance(kind, str) or not is_supported_pheromone_kind(kind):
            diagnostics.append(
                validation_error(
                    "collective_pheromone_kind_invalid",
                    "pheromone kind must be built-in or namespaced",
                    "protocol.collective_decision_policy.pheromone_kind_profiles",
                )
            )
        if not isinstance(profile, PheromoneKindProfile):
            diagnostics.append(
                validation_error(
                    "collective_pheromone_kind_profile_invalid",
                    "pheromone kind profile must use the canonical protocol declaration",
                    "protocol.collective_decision_policy.pheromone_kind_profiles",
                )
            )
            continue
        diagnostics.extend(_validate_pheromone_profile(kind, profile))
    return diagnostics


def _validate_pheromone_profile(
    kind: str,
    profile: PheromoneKindProfile,
) -> list[ValidationDiagnostic]:
    path = "protocol.collective_decision_policy.pheromone_kind_profiles"
    code = "collective_pheromone_kind_profile_invalid"
    diagnostics: list[ValidationDiagnostic] = []
    if not finite_non_negative(profile.weight):
        diagnostics.append(
            validation_error(
                code, "pheromone kind profile weights must be non-negative", path
            )
        )
    if profile.evaporation_rate is not None and not finite_in_range(
        profile.evaporation_rate, 0, 1
    ):
        diagnostics.append(
            validation_error(
                code,
                "pheromone kind profile evaporation rates must be between 0 and 1",
                path,
            )
        )
    if profile.ttl_steps is not None and not non_negative_integer(profile.ttl_steps):
        diagnostics.append(
            validation_error(
                code,
                "pheromone kind profile ttl values must be non-negative",
                path,
            )
        )
    if profile.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
        diagnostics.append(
            validation_error(
                code,
                "pheromone kind profile response model is unsupported",
                path,
            )
        )
    if not non_negative_integer(profile.priority):
        diagnostics.append(
            validation_error(
                code,
                "pheromone kind profile priority must be a non-negative integer",
                path,
            )
        )
    if not isinstance(profile.can_suppress_positive, bool):
        diagnostics.append(
            validation_error(code, "pheromone suppression flag must be boolean", path)
        )
    diagnostics.extend(
        validation_error(
            code,
            "pheromone kind profile subject type is unsupported or non-scoring",
            path,
        )
        for subject_type in profile.scored_subject_types
        if not isinstance(subject_type, str)
        or not is_scored_pheromone_subject_type(subject_type)
    )
    if kind == "stale" and (profile.weight != 0 or profile.scored_subject_types):
        diagnostics.append(
            validation_error(
                "collective_pheromone_stale_scores_invalid",
                "stale pheromone must remain no-score",
                f"{path}.stale",
            )
        )
    return diagnostics


def _validate_layer_policy(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if not positive_integer(policy.layer_min_provenance):
        diagnostics.append(
            validation_error(
                "collective_layer_provenance_invalid",
                "layer_min_provenance must be positive",
                "protocol.collective_decision_policy.layer_min_provenance",
            )
        )
    if not finite_in_range(
        policy.layer_conflict_threshold, 0, 1
    ) or not finite_in_range(policy.layer_emergency_override_threshold, 0, 1):
        diagnostics.append(
            validation_error(
                "collective_layer_threshold_invalid",
                "layer coordination thresholds must be finite and between 0 and 1",
                "protocol.collective_decision_policy",
            )
        )
    diagnostics.extend(_validate_layer_default_weights(policy))
    diagnostics.extend(_validate_layer_confidence_thresholds(policy))
    diagnostics.extend(_validate_layer_weight_bounds(policy))
    return diagnostics


def _validate_layer_default_weights(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for layer_id, weight in policy.layer_default_weights.items():
        if layer_id not in SUPPORTED_LAYER_IDS:
            diagnostics.append(
                validation_error(
                    "collective_layer_id_invalid",
                    "layer default weight references an unsupported layer",
                    "protocol.collective_decision_policy.layer_default_weights",
                )
            )
        if not finite_in_range(weight, 0, MAX_LAYER_WEIGHT):
            diagnostics.append(
                validation_error(
                    "collective_layer_weight_invalid",
                    "layer weights must be finite and within absolute bounds",
                    "protocol.collective_decision_policy.layer_default_weights",
                )
            )
    return diagnostics


def _validate_layer_confidence_thresholds(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for layer_id, threshold in policy.layer_confidence_thresholds.items():
        if layer_id not in SUPPORTED_LAYER_IDS:
            diagnostics.append(
                validation_error(
                    "collective_layer_id_invalid",
                    "layer confidence threshold references an unsupported layer",
                    "protocol.collective_decision_policy.layer_confidence_thresholds",
                )
            )
        if not finite_in_range(threshold, 0, 1):
            diagnostics.append(
                validation_error(
                    "collective_layer_threshold_invalid",
                    "layer confidence thresholds must be finite and between 0 and 1",
                    "protocol.collective_decision_policy.layer_confidence_thresholds",
                )
            )
    return diagnostics


def _validate_layer_weight_bounds(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for layer_id, bounds in policy.layer_weight_bounds.items():
        if layer_id not in SUPPORTED_LAYER_IDS:
            diagnostics.append(
                validation_error(
                    "collective_layer_id_invalid",
                    "layer weight bounds reference an unsupported layer",
                    "protocol.collective_decision_policy.layer_weight_bounds",
                )
            )
        if not valid_absolute_bounds(bounds, 0, MAX_LAYER_WEIGHT):
            diagnostics.append(
                validation_error(
                    "collective_layer_bounds_invalid",
                    "layer weight bounds must be finite, ordered, and within absolute bounds",
                    "protocol.collective_decision_policy.layer_weight_bounds",
                )
            )
            continue
        lower, upper = bounds
        default_weight = policy.layer_default_weights.get(layer_id)
        if (
            finite_number(default_weight)
            and not lower <= cast(float, default_weight) <= upper
        ):
            diagnostics.append(
                validation_error(
                    "collective_layer_default_weight_out_of_bounds",
                    "layer default weight must stay inside declared bounds",
                    "protocol.collective_decision_policy.layer_default_weights",
                )
            )
    return diagnostics


def _validate_policy_adjustment_bounds(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    path = "protocol.collective_decision_policy.policy_adjustment_bounds"
    for field_name, bounds in policy.policy_adjustment_bounds.items():
        if field_name in SAFETY_CRITICAL_POLICY_ADJUSTMENT_FIELDS:
            diagnostics.append(
                validation_error(
                    "collective_policy_adjustment_unsafe",
                    "policy adjustment bounds must not permit safety-critical invariant changes",
                    path,
                )
            )
        if field_name not in ALLOWED_POLICY_ADJUSTMENT_FIELDS:
            diagnostics.append(
                validation_error(
                    "collective_policy_adjustment_unknown",
                    "policy adjustment field is not allowlisted",
                    path,
                )
            )
        if not valid_policy_adjustment_bound(field_name, bounds, policy):
            diagnostics.append(
                validation_error(
                    "collective_policy_adjustment_bounds_invalid",
                    "policy adjustment bounds must declare ordered numeric bounds or allowed values",
                    path,
                )
            )
    return diagnostics


_COLLECTIVE_RULES: tuple[_CollectiveRule, ...] = (
    _validate_collective_authority,
    _validate_pheromone_memory,
    _validate_pheromone_response,
    _validate_pheromone_profiles,
    _validate_layer_policy,
    _validate_policy_adjustment_bounds,
)
