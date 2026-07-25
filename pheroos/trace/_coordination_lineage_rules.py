from __future__ import annotations

from collections.abc import Callable
from numbers import Real
from typing import Any

from pheroos.trace._lineage_primitives import (
    finite_number,
    require_boolean,
    require_bounded_mapping,
    require_declared_layer_score_mapping,
    require_layer_snapshots,
    require_nonempty_mapping,
    require_recursive_coverage,
    require_text_fields,
    require_text_mapping,
    require_text_sequence,
)
from pheroos.trace._lineage_types import TraceEventView
from pheroos.trace._pheromone_receipts import (
    require_matching_replay_fingerprints,
)


LineageRule = Callable[[TraceEventView, frozenset[str]], None]


def apply_coordination_lineage_rule(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> bool:
    """Apply the one declared coordination rule in immutable ABI order."""

    for event_types, rule in _COORDINATION_LINEAGE_RULES:
        if event.event_type in event_types:
            rule(event, required_fields)
            return True
    return False


def _validate_layer_proposal(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_text_fields(
        event_type,
        lineage,
        {
            "layer_id",
            "source_id",
            "action",
            "effect",
            "candidate_id",
            "evidence_id",
            "provenance",
            "source_trace_event_id",
            "subject_type",
            "subject_id",
        },
    )
    if lineage["layer_id"] not in {
        "reactive",
        "learned",
        "evolutionary",
        "metacognitive",
    }:
        raise ValueError("layer_proposal trace lineage layer_id is unsupported")
    confidence = finite_number(event_type, "confidence", lineage["confidence"])
    if not 0 <= confidence <= 1:
        raise ValueError(
            "layer_proposal trace lineage confidence must be between 0 and 1"
        )
    _validate_layer_support_and_risk(lineage)
    proposed_strength = finite_number(
        event_type,
        "proposed_strength",
        lineage["proposed_strength"],
    )
    if not 0 <= proposed_strength <= 10:
        raise ValueError(
            "layer_proposal trace lineage proposed_strength must be between 0 and 10"
        )
    if not isinstance(lineage["proposed_pheromone_kind"], str):
        raise ValueError(
            "layer_proposal trace lineage proposed_pheromone_kind must be a string"
        )
    if lineage["action"] == "propose_pheromone":
        _validate_pheromone_proposal(lineage, proposed_strength)


def _validate_layer_support_and_risk(lineage: dict[str, Any]) -> None:
    event_type = "layer_proposal"
    for field_name in ("support", "risk"):
        value = finite_number(event_type, field_name, lineage[field_name])
        if not 0 <= value <= 10:
            raise ValueError(
                f"layer_proposal trace lineage {field_name} must be between 0 and 10"
            )


def _validate_pheromone_proposal(
    lineage: dict[str, Any],
    proposed_strength: float,
) -> None:
    if lineage["effect"] != "bounded_pheromone_deposit_proposed":
        raise ValueError(
            "layer pheromone proposal trace must declare its bounded deposit effect"
        )
    if not lineage["proposed_pheromone_kind"] or proposed_strength <= 0:
        raise ValueError(
            "layer pheromone proposal trace requires kind and positive strength"
        )


def _validate_coordination_assess(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_declared_layer_score_mapping(
        event_type,
        lineage,
        "confidences",
        minimum=0.0,
        maximum=1.0,
    )
    require_declared_layer_score_mapping(
        event_type,
        lineage,
        "weights",
        minimum=0.0,
    )
    require_layer_snapshots(event_type, lineage, "snapshots")
    require_recursive_coverage(event_type, lineage, "coverage")
    require_text_mapping(event_type, lineage, "action_effects")
    require_bounded_mapping(
        event_type,
        lineage,
        "trace_coverage_confirmations",
        minimum=0.0,
        maximum=1.0,
    )
    require_text_sequence(
        event_type,
        lineage,
        "proposal_lineage",
        allow_empty=True,
    )


def _validate_coordination_resolve(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_text_sequence(
        event_type,
        lineage,
        "conflicts",
        allow_empty=True,
    )
    require_text_fields(
        event_type,
        lineage,
        {"resolution", "selected_candidate", "reason"},
    )
    require_boolean(event_type, lineage, "fallback_used")
    require_text_sequence(
        event_type,
        lineage,
        "proposal_lineage",
        allow_empty=True,
    )
    if lineage["reason"] != lineage["resolution"]:
        raise ValueError(
            "coordination_resolve trace lineage reason must equal resolution"
        )


def _validate_policy_adjustment(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_nonempty_mapping(event_type, lineage, "proposed_values")
    require_nonempty_mapping(event_type, lineage, "declared_bounds")
    require_text_fields(
        event_type,
        lineage,
        {"result", "source_id", "layer_id", "provenance", "source_trace_event_id"},
    )
    if lineage["result"] not in {"accepted", "rejected", "replay_ignored"}:
        raise ValueError(
            "policy_adjustment trace lineage result must be accepted, rejected, or replay_ignored"
        )
    _validate_policy_adjustment_lineage(lineage)
    if lineage["result"] == "replay_ignored":
        _validate_replayed_adjustment(event_type, lineage)


def _validate_replayed_adjustment(
    event_type: str,
    lineage: dict[str, Any],
) -> None:
    if lineage.get("replayed") is not True:
        raise ValueError("replayed policy_adjustment trace must set replayed=true")
    require_matching_replay_fingerprints(event_type, lineage)


def _validate_policy_adjustment_lineage(lineage: dict[str, Any]) -> None:
    """Validate adjustment values and their declared authority envelope."""

    proposed = lineage["proposed_values"]
    declared = lineage["declared_bounds"]
    if set(proposed) != set(declared):
        raise ValueError(
            "policy_adjustment trace proposed values and declared bounds must cover the same fields"
        )
    for field_name, value in proposed.items():
        _validate_adjustment_field(lineage, declared, field_name, value)


def _validate_adjustment_field(
    lineage: dict[str, Any],
    declared: dict[Any, Any],
    field_name: Any,
    value: Any,
) -> None:
    if not isinstance(field_name, str) or not field_name.strip():
        raise ValueError(
            "policy_adjustment trace lineage proposed_values keys must be non-empty strings"
        )
    _validate_adjustment_scalar(
        "policy_adjustment",
        f"proposed_values.{field_name}",
        value,
    )
    bound = _validate_adjustment_bound(field_name, declared[field_name])
    if lineage["result"] in {
        "accepted",
        "replay_ignored",
    } and not _adjustment_value_within_bound(value, bound):
        raise ValueError(
            "policy_adjustment trace accepted or replayed value is outside "
            f"declared bounds: {field_name}"
        )


def _validate_adjustment_bound(
    field_name: str,
    raw_bound: Any,
) -> tuple[str, tuple[Any, ...]]:
    path = f"declared_bounds.{field_name}"
    if isinstance(raw_bound, (list, tuple)) and len(raw_bound) == 2:
        return _validate_numeric_bound(
            path,
            raw_bound[0],
            raw_bound[1],
            lower_suffix="[0]",
            upper_suffix="[1]",
        )
    if isinstance(raw_bound, dict) and set(raw_bound) == {"min", "max"}:
        return _validate_numeric_bound(
            path,
            raw_bound["min"],
            raw_bound["max"],
            lower_suffix=".min",
            upper_suffix=".max",
        )
    if isinstance(raw_bound, dict) and set(raw_bound) == {"allowed_values"}:
        return _validate_allowed_values_bound(path, raw_bound["allowed_values"])
    raise ValueError(
        f"policy_adjustment trace lineage {path} must declare numeric bounds or allowed_values"
    )


def _validate_numeric_bound(
    path: str,
    raw_lower: Any,
    raw_upper: Any,
    *,
    lower_suffix: str,
    upper_suffix: str,
) -> tuple[str, tuple[Any, ...]]:
    event_type = "policy_adjustment"
    lower = finite_number(event_type, f"{path}{lower_suffix}", raw_lower)
    upper = finite_number(event_type, f"{path}{upper_suffix}", raw_upper)
    if lower > upper:
        raise ValueError(
            f"policy_adjustment trace lineage {path} numeric bounds must be ordered"
        )
    return "numeric", (lower, upper)


def _validate_allowed_values_bound(
    path: str,
    allowed: Any,
) -> tuple[str, tuple[Any, ...]]:
    if not isinstance(allowed, (list, tuple)) or not allowed:
        raise ValueError(
            f"policy_adjustment trace lineage {path}.allowed_values must be a non-empty array"
        )
    for index, item in enumerate(allowed):
        _validate_adjustment_scalar(
            "policy_adjustment",
            f"{path}.allowed_values[{index}]",
            item,
        )
    return "allowed_values", tuple(allowed)


def _validate_adjustment_scalar(
    event_type: str,
    path: str,
    value: Any,
) -> None:
    if isinstance(value, bool):
        raise ValueError(
            f"{event_type} trace lineage {path} must be a finite number or string"
        )
    if isinstance(value, Real):
        finite_number(event_type, path, value)
        return
    if isinstance(value, str) and value.strip():
        return
    raise ValueError(
        f"{event_type} trace lineage {path} must be a finite number or string"
    )


def _adjustment_value_within_bound(
    value: Any,
    bound: tuple[str, tuple[Any, ...]],
) -> bool:
    kind, values = bound
    if kind == "numeric":
        if isinstance(value, bool) or not isinstance(value, Real):
            return False
        lower, upper = values
        return float(lower) <= float(value) <= float(upper)
    return any(type(value) is type(allowed) and value == allowed for allowed in values)


_COORDINATION_LINEAGE_RULES: tuple[tuple[frozenset[str], LineageRule], ...] = (
    (frozenset({"layer_proposal"}), _validate_layer_proposal),
    (frozenset({"coordination_assess"}), _validate_coordination_assess),
    (frozenset({"coordination_resolve"}), _validate_coordination_resolve),
    (frozenset({"policy_adjustment"}), _validate_policy_adjustment),
)


__all__: tuple[str, ...] = ()
