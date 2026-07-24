"""Ordered validation rules for the canonical pheromone policy."""

from __future__ import annotations

from collections.abc import Callable

from pheroos.governance._pheromone.records import (
    PHEROMONE_EXTENSION_PREFIXES,
    PheromonePolicy,
    SUPPORTED_PHEROMONE_COMPETITION_MODES,
    SUPPORTED_PHEROMONE_KINDS,
    SUPPORTED_PHEROMONE_RESPONSE_MODELS,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import (
    PheromoneKindProfile,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    effective_pheromone_scored_subject_types,
    is_scored_pheromone_subject_type,
)


FiniteNumber = Callable[[object, str], float]
NonNegativeStep = Callable[[object, str], int]


def validate_pheromone_policy_rules(
    policy: PheromonePolicy,
    *,
    finite_number: FiniteNumber,
    non_negative_number: FiniteNumber,
    non_negative_step: NonNegativeStep,
) -> None:
    """Run policy rules in the historical fail-fast diagnostic order."""

    _validate_boolean_fields(policy)
    _validate_evaporation(policy, finite_number)
    minimum, maximum = _validate_strength_bounds(policy, non_negative_number)
    _validate_non_negative_fields(policy, non_negative_number)
    _validate_exploration_floors(policy)
    _validate_enabled_strength_bounds(policy, minimum, maximum)
    _validate_novelty_decay(policy, finite_number)
    _validate_source_diversity(policy)
    _validate_response_and_competition(policy)
    _validate_policy_subject_types(policy)
    _validate_kind_profiles(
        policy, finite_number, non_negative_number, non_negative_step
    )
    _validate_reachable_activation_threshold(policy)


def _validate_boolean_fields(policy: PheromonePolicy) -> None:
    if not isinstance(policy.enabled, bool):
        raise GovernanceError("pheromone enabled must be boolean")
    if not isinstance(policy.feedback_enabled, bool):
        raise GovernanceError("pheromone feedback_enabled must be boolean")
    if not isinstance(policy.exploration_enabled, bool):
        raise GovernanceError("pheromone exploration_enabled must be boolean")
    if not isinstance(policy.require_provenance, bool) or not isinstance(
        policy.require_trace, bool
    ):
        raise GovernanceError(
            "pheromone provenance and trace requirements must be boolean"
        )


def _validate_evaporation(
    policy: PheromonePolicy,
    finite_number: FiniteNumber,
) -> None:
    evaporation_rate = finite_number(
        policy.evaporation_rate,
        "pheromone evaporation_rate",
    )
    if not 0 <= evaporation_rate <= 1:
        raise GovernanceError("pheromone evaporation_rate must be between 0 and 1")
    if not isinstance(policy.decay_model, str) or (
        policy.decay_model not in SUPPORTED_PHEROMONE_DECAY_MODELS
    ):
        raise GovernanceError(
            f"unsupported pheromone decay model: {policy.decay_model}"
        )


def _validate_strength_bounds(
    policy: PheromonePolicy,
    non_negative_number: FiniteNumber,
) -> tuple[float, float]:
    minimum = non_negative_number(policy.min_strength, "pheromone min_strength")
    maximum = non_negative_number(policy.max_strength, "pheromone max_strength")
    if minimum > maximum:
        raise GovernanceError("pheromone min_strength must not exceed max_strength")
    return minimum, maximum


def _validate_non_negative_fields(
    policy: PheromonePolicy,
    non_negative_number: FiniteNumber,
) -> None:
    for name in (
        "positive_weight",
        "negative_weight",
        "cautionary_weight",
        "cautionary_override_threshold",
        "novelty_weight",
        "per_source_cap",
        "per_round_deposit_cap",
        "activation_threshold",
        "saturation_threshold",
        "exploration_floor",
        "stale_route_reopen_threshold",
        "response_exploration_floor",
    ):
        non_negative_number(getattr(policy, name), f"pheromone {name}")


def _validate_exploration_floors(policy: PheromonePolicy) -> None:
    for name in ("exploration_floor", "response_exploration_floor"):
        if getattr(policy, name) > 1:
            raise GovernanceError(f"pheromone {name} must be between 0 and 1")


def _validate_enabled_strength_bounds(
    policy: PheromonePolicy,
    minimum: float,
    maximum: float,
) -> None:
    if policy.enabled and any(
        minimum > bound
        for bound in (maximum, policy.per_source_cap, policy.per_round_deposit_cap)
    ):
        raise GovernanceError(
            "pheromone minimum strength must fit max/source/round bounds"
        )


def _validate_novelty_decay(
    policy: PheromonePolicy,
    finite_number: FiniteNumber,
) -> None:
    novelty_decay_rate = finite_number(
        policy.novelty_decay_rate,
        "pheromone novelty_decay_rate",
    )
    if not 0 <= novelty_decay_rate <= 1:
        raise GovernanceError("pheromone novelty_decay_rate must be between 0 and 1")


def _validate_source_diversity(policy: PheromonePolicy) -> None:
    if isinstance(policy.min_source_diversity, bool) or not isinstance(
        policy.min_source_diversity, int
    ):
        raise GovernanceError(
            "pheromone min_source_diversity must be a positive integer"
        )
    if policy.min_source_diversity <= 0:
        raise GovernanceError(
            "pheromone min_source_diversity must be a positive integer"
        )


def _validate_response_and_competition(policy: PheromonePolicy) -> None:
    if not isinstance(policy.response_model, str) or (
        policy.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS
    ):
        raise GovernanceError(
            f"unsupported pheromone response model: {policy.response_model}"
        )
    if not isinstance(policy.competition_mode, str) or (
        policy.competition_mode not in SUPPORTED_PHEROMONE_COMPETITION_MODES
    ):
        raise GovernanceError(
            f"unsupported pheromone competition mode: {policy.competition_mode}"
        )


def _validate_policy_subject_types(policy: PheromonePolicy) -> None:
    if not policy.scored_subject_types:
        raise GovernanceError("pheromone scored_subject_types must not be empty")
    for subject_type in policy.scored_subject_types:
        if not isinstance(subject_type, str) or not is_scored_pheromone_subject_type(
            subject_type
        ):
            raise GovernanceError(
                f"unsupported or non-scoring pheromone subject type: {subject_type}"
            )
    if len(set(policy.scored_subject_types)) != len(policy.scored_subject_types):
        raise GovernanceError(
            "pheromone scored_subject_types must not contain duplicates"
        )


def _validate_kind_profiles(
    policy: PheromonePolicy,
    finite_number: FiniteNumber,
    non_negative_number: FiniteNumber,
    non_negative_step: NonNegativeStep,
) -> None:
    for kind, profile in policy.kind_profiles.items():
        _validate_kind_name_and_type(kind, profile)
        _validate_kind_numeric_fields(
            kind,
            profile,
            finite_number,
            non_negative_number,
            non_negative_step,
        )
        _validate_kind_response_fields(kind, profile)
        _validate_kind_subject_types(kind, profile)
        if kind == "stale" and (profile.weight != 0 or profile.scored_subject_types):
            raise GovernanceError("stale pheromone kind profile must remain no-score")


def _validate_kind_name_and_type(kind: object, profile: object) -> None:
    if not isinstance(kind, str) or (
        kind not in SUPPORTED_PHEROMONE_KINDS and not _is_extension_value(kind)
    ):
        raise GovernanceError(f"unsupported pheromone kind profile: {kind}")
    if not isinstance(profile, PheromoneKindProfile):
        raise GovernanceError(f"pheromone kind profile has invalid type: {kind}")


def _validate_kind_numeric_fields(
    kind: str,
    profile: PheromoneKindProfile,
    finite_number: FiniteNumber,
    non_negative_number: FiniteNumber,
    non_negative_step: NonNegativeStep,
) -> None:
    non_negative_number(profile.weight, f"pheromone kind profile {kind} weight")
    if profile.evaporation_rate is not None:
        rate = finite_number(
            profile.evaporation_rate,
            f"pheromone kind profile {kind} evaporation_rate",
        )
        if not 0 <= rate <= 1:
            raise GovernanceError(
                f"pheromone kind profile {kind} evaporation_rate must be between 0 and 1"
            )
    if profile.ttl_steps is not None:
        non_negative_step(
            profile.ttl_steps,
            f"pheromone kind profile {kind} ttl_steps",
        )


def _validate_kind_response_fields(
    kind: str,
    profile: PheromoneKindProfile,
) -> None:
    if not isinstance(profile.response_model, str) or (
        profile.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS
    ):
        raise GovernanceError(
            "unsupported pheromone kind profile response model: "
            f"{profile.response_model}"
        )
    if (
        isinstance(profile.priority, bool)
        or not isinstance(profile.priority, int)
        or (profile.priority < 0)
    ):
        raise GovernanceError(
            f"pheromone kind profile {kind} priority must be a non-negative integer"
        )
    if not isinstance(profile.can_suppress_positive, bool):
        raise GovernanceError(
            f"pheromone kind profile {kind} can_suppress_positive must be boolean"
        )


def _validate_kind_subject_types(
    kind: str,
    profile: PheromoneKindProfile,
) -> None:
    for subject_type in profile.scored_subject_types:
        if not isinstance(subject_type, str) or not is_scored_pheromone_subject_type(
            subject_type
        ):
            raise GovernanceError(
                f"unsupported or non-scoring pheromone subject type: {subject_type}"
            )
    if len(set(profile.scored_subject_types)) != len(profile.scored_subject_types):
        raise GovernanceError(
            f"pheromone kind profile {kind} subject types must not contain duplicates"
        )


def _validate_reachable_activation_threshold(policy: PheromonePolicy) -> None:
    if policy.activation_threshold <= 0:
        return
    threshold_weights = _threshold_response_weights(policy)
    maximum_delta = policy.max_strength * max(threshold_weights, default=0.0)
    if threshold_weights and (
        maximum_delta <= 0 or policy.activation_threshold > maximum_delta
    ):
        raise GovernanceError(
            "pheromone activation_threshold cannot be reached by any declared threshold response"
        )


def _threshold_response_weights(policy: PheromonePolicy) -> list[float]:
    weights: list[float] = []
    for kind in set(SUPPORTED_PHEROMONE_KINDS) | set(policy.kind_profiles):
        if kind != "stale":
            _append_threshold_weight(weights, kind, policy)
    return weights


def _append_threshold_weight(
    weights: list[float],
    kind: str,
    policy: PheromonePolicy,
) -> None:
    profile = policy.kind_profiles.get(kind)
    if not effective_pheromone_scored_subject_types(
        kind,
        profile,
        policy.scored_subject_types,
    ):
        return
    response_model = profile.response_model if profile else policy.response_model
    if response_model != "threshold":
        return
    weights.append(float(profile.weight if profile else _legacy_weight(kind, policy)))


def _legacy_weight(kind: str, policy: PheromonePolicy) -> float:
    return {
        "positive": policy.positive_weight,
        "negative": policy.negative_weight,
        "cautionary": policy.cautionary_weight,
        "alarm": policy.cautionary_weight,
        "novelty": policy.novelty_weight,
    }.get(kind, 0.0)


def _is_extension_value(value: str) -> bool:
    return any(
        value.startswith(prefix) and len(value) > len(prefix)
        for prefix in PHEROMONE_EXTENSION_PREFIXES
    )


__all__: list[str] = []
