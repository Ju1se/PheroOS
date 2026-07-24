from __future__ import annotations

from collections.abc import Iterable
from math import isfinite
from numbers import Real
from typing import Any

from pheroos.trace._lineage_types import (
    DECLARED_COORDINATION_LAYER_IDS,
    LAYER_SNAPSHOT_FIELDS,
)


def require_text_fields(
    event_type: str,
    lineage: dict[str, Any],
    fields: Iterable[str],
) -> None:
    for field_name in fields:
        value = lineage[field_name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{event_type} trace lineage {field_name} must be a non-empty string"
            )


def finite_number(event_type: str, field_name: str, value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not isfinite(float(value))
    ):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a finite number"
        )
    return float(value)


def require_finite_fields(
    event_type: str,
    lineage: dict[str, Any],
    fields: Iterable[str],
) -> None:
    for field_name in fields:
        finite_number(event_type, field_name, lineage[field_name])


def require_nonnegative_number(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> float:
    value = finite_number(event_type, field_name, lineage[field_name])
    if value < 0:
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be non-negative"
        )
    return value


def require_nonnegative_integer(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a non-negative integer"
        )


def require_positive_integer(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a positive integer"
        )


def require_boolean(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    if not isinstance(lineage[field_name], bool):
        raise ValueError(f"{event_type} trace lineage {field_name} must be a boolean")


def require_nonempty_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a non-empty object"
        )


def validate_budget_result(event_type: str, value: Any) -> None:
    required = {"round_remaining", "source_remaining", "status"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise ValueError(
            f"{event_type} trace lineage budget_result must contain round_remaining, "
            "source_remaining, and status"
        )
    require_nonnegative_number(event_type, value, "round_remaining")
    require_nonnegative_number(event_type, value, "source_remaining")
    if value["status"] not in {"applied", "rejected"}:
        raise ValueError(
            f"{event_type} trace lineage budget_result status is unsupported"
        )


def require_score_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a non-empty score object"
        )
    for key, score in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(
                f"{event_type} trace lineage {field_name} keys must be non-empty strings"
            )
        finite_number(event_type, f"{field_name}.{key}", score)


def require_bounded_score_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    minimum: float,
    maximum: float | None = None,
) -> None:
    """Validate a numeric map whose values carry field-specific ABI bounds."""

    require_score_mapping(event_type, lineage, field_name)
    for key, raw_value in lineage[field_name].items():
        value = float(raw_value)
        if value < minimum or (maximum is not None and value > maximum):
            bounds = (
                f"between {minimum:g} and {maximum:g}"
                if maximum is not None
                else f"at least {minimum:g}"
            )
            raise ValueError(
                f"{event_type} trace lineage {field_name}.{key} must be {bounds}"
            )


def require_declared_layer_score_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    minimum: float,
    maximum: float | None = None,
) -> None:
    require_bounded_score_mapping(
        event_type,
        lineage,
        field_name,
        minimum=minimum,
        maximum=maximum,
    )
    observed = set(lineage[field_name])
    if observed != set(DECLARED_COORDINATION_LAYER_IDS):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain exactly the declared layer ids"
        )


def require_layer_snapshots(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    snapshots = lineage[field_name]
    if not isinstance(snapshots, dict) or set(snapshots) != set(
        DECLARED_COORDINATION_LAYER_IDS
    ):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain exactly the declared layer ids"
        )
    rate_fields = LAYER_SNAPSHOT_FIELDS - {"present"}
    for layer_id, snapshot in snapshots.items():
        _validate_layer_snapshot(
            event_type,
            field_name,
            layer_id,
            snapshot,
            rate_fields,
        )


def _validate_layer_snapshot(
    event_type: str,
    field_name: str,
    layer_id: str,
    snapshot: Any,
    rate_fields: frozenset[str],
) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != set(LAYER_SNAPSHOT_FIELDS):
        raise ValueError(
            f"{event_type} trace lineage {field_name}.{layer_id} must contain the complete snapshot"
        )
    if not isinstance(snapshot["present"], bool):
        raise ValueError(
            f"{event_type} trace lineage {field_name}.{layer_id}.present must be a boolean"
        )
    for metric in rate_fields:
        _validate_layer_snapshot_metric(
            event_type,
            field_name,
            layer_id,
            snapshot,
            metric,
        )


def _validate_layer_snapshot_metric(
    event_type: str,
    field_name: str,
    layer_id: str,
    snapshot: dict[str, Any],
    metric: str,
) -> None:
    value = finite_number(
        event_type,
        f"{field_name}.{layer_id}.{metric}",
        snapshot[metric],
    )
    if not 0 <= value <= 1:
        raise ValueError(
            f"{event_type} trace lineage {field_name}.{layer_id}.{metric} "
            "must be between 0 and 1"
        )
    if not snapshot["present"] and value != 0:
        raise ValueError(
            f"{event_type} trace lineage {field_name}.{layer_id}.{metric} "
            "must be zero when the snapshot is absent"
        )


def require_text_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict):
        raise ValueError(f"{event_type} trace lineage {field_name} must be an object")
    if any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(item, str)
        or not item.strip()
        for key, item in value.items()
    ):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain non-empty string entries"
        )


def require_bounded_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict):
        raise ValueError(f"{event_type} trace lineage {field_name} must be an object")
    for key, raw_value in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                f"{event_type} trace lineage {field_name} keys must be non-empty strings"
            )
        number = finite_number(event_type, f"{field_name}.{key}", raw_value)
        if not minimum <= number <= maximum:
            raise ValueError(
                f"{event_type} trace lineage {field_name}.{key} must be between "
                f"{minimum:g} and {maximum:g}"
            )


def require_recursive_coverage(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    """Validate arbitrarily grouped coverage leaves as finite ratios."""

    value = lineage[field_name]
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a non-empty coverage object"
        )
    _validate_coverage_node(event_type, value, field_name)


def _validate_coverage_node(
    event_type: str,
    node: dict[str, Any],
    path: str,
) -> None:
    for key, child in node.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                f"{event_type} trace lineage {path} keys must be non-empty strings"
            )
        child_path = f"{path}.{key}"
        if isinstance(child, dict):
            _validate_coverage_node(event_type, child, child_path)
            continue
        ratio = finite_number(event_type, child_path, child)
        if not 0 <= ratio <= 1:
            raise ValueError(
                f"{event_type} trace lineage {child_path} must be between 0 and 1"
            )


def require_count_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict):
        raise ValueError(f"{event_type} trace lineage {field_name} must be an object")
    for key, count in value.items():
        if (
            not isinstance(key, str)
            or not key
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise ValueError(
                f"{event_type} trace lineage {field_name} must contain non-negative integer counts"
            )


def require_nonempty_text_sequence(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    require_text_sequence(event_type, lineage, field_name, allow_empty=False)


def require_text_sequence(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    allow_empty: bool,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise ValueError(f"{event_type} trace lineage {field_name} must be {qualifier}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain non-empty strings"
        )


def require_subject(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict) or not {"type", "id"}.issubset(value):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain type and id"
        )
    require_text_fields(event_type, value, {"type", "id"})


__all__: tuple[str, ...] = ()
