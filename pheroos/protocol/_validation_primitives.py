from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import math
from numbers import Real
from typing import cast
import unicodedata

from pheroos.protocol.models import (
    SUPPORTED_PHEROMONE_RESPONSE_MODELS,
    CollectiveDecisionPolicy,
    ValidationDiagnostic,
)


SAFETY_CRITICAL_POLICY_ADJUSTMENT_FIELDS = frozenset(
    {
        "fallback_candidate",
        "safe_fallback",
        "declared_candidates",
        "candidate_declaration",
        "trace_policy.required_events",
        "pheromone_require_trace",
        "pheromone_require_provenance",
        "evidence_policy.require_provenance",
        "output_policy.requires_committed_candidate",
        "output_policy.requires_evidence_contract",
        "output_policy.requires_stop_resolution",
        "output_policy.requires_publication_permission",
    }
)

POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS = {
    "pheromone_evaporation_rate": (0.0, 1.0),
    "pheromone_positive_weight": (0.0, 10.0),
    "pheromone_negative_weight": (0.0, 10.0),
    "pheromone_cautionary_weight": (0.0, 10.0),
    "pheromone_alarm_weight": (0.0, 10.0),
    "pheromone_novelty_weight": (0.0, 10.0),
    "pheromone_exploration_floor": (0.0, 1.0),
    "pheromone_cautionary_override_threshold": (0.0, 10.0),
    "layer_emergency_override_threshold": (0.0, 1.0),
    "layer_learned_weight": (0.0, 10.0),
    "layer_evolutionary_weight": (0.0, 10.0),
    "layer_metacognitive_weight": (0.0, 10.0),
}
POLICY_ADJUSTMENT_ENUM_FIELDS = {
    "pheromone_response_model": SUPPORTED_PHEROMONE_RESPONSE_MODELS,
}
ALLOWED_POLICY_ADJUSTMENT_FIELDS = frozenset(
    POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS | POLICY_ADJUSTMENT_ENUM_FIELDS
)
MAX_LAYER_WEIGHT = 10.0


def validation_error(code: str, message: str, path: str) -> ValidationDiagnostic:
    return ValidationDiagnostic(code=code, message=message, path=path)


def duplicate_values(values: object) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in cast(Iterable[object], values):
        text = str(value)
        if text in seen:
            duplicates.add(text)
        seen.add(text)
    return sorted(duplicates)


def canonical_nonblank_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and value == unicodedata.normalize("NFC", value)
    )


def canonical_string_set(value: object, *, require_nonempty: bool = False) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    if require_nonempty and not value:
        return False
    values = list(value)
    return all(canonical_nonblank_text(item) for item in values) and len(values) == len(
        set(values)
    )


def collective_kind_weight(policy: CollectiveDecisionPolicy, kind: str) -> float:
    value: object
    if kind == "positive":
        value = policy.pheromone_positive_weight
    elif kind == "negative":
        value = policy.pheromone_negative_weight
    elif kind in {"cautionary", "alarm"}:
        value = policy.pheromone_cautionary_weight
    elif kind == "novelty":
        value = policy.pheromone_novelty_weight
    else:
        return 0.0
    return float((value)) if finite_non_negative(value) else 0.0


def valid_policy_adjustment_bound(
    field_name: object,
    bounds: object,
    policy: object,
) -> bool:
    if not isinstance(field_name, str):
        return False
    allowed_values = POLICY_ADJUSTMENT_ENUM_FIELDS.get(field_name)
    if allowed_values is not None:
        if not isinstance(bounds, Mapping) or set(bounds) != {"allowed_values"}:
            return False
        values = bounds["allowed_values"]
        return (
            isinstance(values, Sequence)
            and not isinstance(values, (str, bytes, bytearray))
            and bool(values)
            and all(
                isinstance(value, str) and value in allowed_values for value in values
            )
        )

    absolute_bounds = POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS.get(field_name)
    if absolute_bounds is None or not valid_absolute_bounds(bounds, *absolute_bounds):
        return False
    lower, upper = normalized_bounds(bounds)
    collective_policy = cast(CollectiveDecisionPolicy, policy)
    if field_name == "pheromone_cautionary_override_threshold" and finite_number(
        collective_policy.pheromone_max_strength
    ):
        if upper > collective_policy.pheromone_max_strength:
            return False
    if field_name.startswith("layer_") and field_name.endswith("_weight"):
        layer_id = field_name.removeprefix("layer_").removesuffix("_weight")
        declared_bounds = collective_policy.layer_weight_bounds.get(layer_id)
        if declared_bounds is None or not valid_absolute_bounds(
            declared_bounds, 0, MAX_LAYER_WEIGHT
        ):
            return False
        declared_lower, declared_upper = normalized_bounds(declared_bounds)
        if lower < declared_lower or upper > declared_upper:
            return False
    return True


def normalized_bounds(bounds: object) -> tuple[float, float]:
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        return float(bounds[0]), float(bounds[1])
    if isinstance(bounds, Mapping) and set(bounds) == {"min", "max"}:
        return float(bounds["min"]), float(bounds["max"])
    raise ValueError("invalid bounds")


def valid_absolute_bounds(
    bounds: object,
    absolute_minimum: float,
    absolute_maximum: float,
) -> bool:
    try:
        lower, upper = normalized_bounds(bounds)
    except (TypeError, ValueError):
        return False
    return (
        finite_number(lower)
        and finite_number(upper)
        and absolute_minimum <= lower <= upper <= absolute_maximum
    )


def valid_non_negative_bounds(lower: object, upper: object) -> bool:
    return (
        finite_non_negative(lower)
        and finite_non_negative(upper)
        and float(cast(float, lower)) <= float(cast(float, upper))
    )


def finite_number(value: object) -> bool:
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(cast(float, value)))
    )


def finite_non_negative(value: object) -> bool:
    return finite_number(value) and float(cast(float, value)) >= 0


def finite_in_range(
    value: object,
    minimum: float,
    maximum: float,
    *,
    lower_inclusive: bool = True,
) -> bool:
    if not finite_number(value):
        return False
    if lower_inclusive:
        return minimum <= float(cast(float, value)) <= maximum
    return minimum < float(cast(float, value)) <= maximum


def positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def non_negative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
