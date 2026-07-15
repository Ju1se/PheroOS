from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    MAX_AUTHORITY_INTEGER,
    WEIGHT_SCALE,
)
from pheroos.protocol.commit_wire import (
    CommitWireError,
    canonical_commit_payload as _canonical_commit_payload,
    canonical_commit_set as _canonical_commit_set,
    commit_payload_fingerprint as _commit_payload_fingerprint,
)


def require_scaled_integer(
    value: object,
    field_name: str,
    *,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GovernanceError(f"{field_name} must be an integer")
    if value < 0:
        raise GovernanceError(f"{field_name} must be non-negative")
    effective_maximum = (
        MAX_AUTHORITY_INTEGER
        if maximum is None
        else min(maximum, MAX_AUTHORITY_INTEGER)
    )
    if value > effective_maximum:
        raise GovernanceError(f"{field_name} exceeds the maximum")
    return value


def require_authority_integer(
    value: object,
    field_name: str,
    *,
    allow_negative: bool = False,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GovernanceError(f"{field_name} must be an integer")
    if not allow_negative and value < 0:
        raise GovernanceError(f"{field_name} must be non-negative")
    if abs(value) > MAX_AUTHORITY_INTEGER:
        raise GovernanceError(f"{field_name} exceeds the authority integer bound")
    return value


def checked_add(*values: object) -> int:
    operands = tuple(
        require_authority_integer(
            value,
            "checked addition operand",
            allow_negative=True,
        )
        for value in values
    )
    # Python integers are arbitrary precision.  Evaluate the whole mathematical
    # sum before applying the authority-leaf bound so equivalent permutations
    # cannot produce different overflow behavior.
    return require_authority_integer(
        sum(operands),
        "checked addition result",
        allow_negative=True,
    )


def checked_subtract(left: object, right: object) -> int:
    left_value = require_authority_integer(
        left,
        "checked subtraction left operand",
        allow_negative=True,
    )
    right_value = require_authority_integer(
        right,
        "checked subtraction right operand",
        allow_negative=True,
    )
    result = left_value - right_value
    return require_authority_integer(
        result,
        "checked subtraction result",
        allow_negative=True,
    )


def checked_multiply(left: object, right: object) -> int:
    left_value = require_authority_integer(
        left,
        "checked multiplication left operand",
        allow_negative=True,
    )
    right_value = require_authority_integer(
        right,
        "checked multiplication right operand",
        allow_negative=True,
    )
    return require_authority_integer(
        left_value * right_value,
        "checked multiplication result",
        allow_negative=True,
    )


def multiply_scaled(
    left: object,
    right: object,
    *,
    scale: int = WEIGHT_SCALE,
) -> int:
    normalized_scale = require_scaled_integer(scale, "fixed-point scale")
    if normalized_scale <= 0:
        raise GovernanceError("fixed-point scale must be positive")
    left_value = require_scaled_integer(left, "fixed-point left operand")
    right_value = require_scaled_integer(right, "fixed-point right operand")
    result = (left_value * right_value) // normalized_scale
    return require_scaled_integer(result, "fixed-point product")


def ceil_scaled_count(
    count: object,
    ratio: object,
    *,
    scale: int = WEIGHT_SCALE,
) -> int:
    normalized_scale = require_scaled_integer(scale, "fixed-point scale")
    if normalized_scale <= 0:
        raise GovernanceError("fixed-point scale must be positive")
    count_value = require_scaled_integer(count, "fixed-point count")
    ratio_value = require_scaled_integer(
        ratio,
        "fixed-point ratio",
        maximum=normalized_scale,
    )
    return (count_value * ratio_value + normalized_scale - 1) // normalized_scale


def scaled_ratio(
    numerator: object,
    denominator: object,
    *,
    scale: int = WEIGHT_SCALE,
) -> int:
    normalized_scale = require_scaled_integer(scale, "fixed-point scale")
    if normalized_scale <= 0:
        raise GovernanceError("fixed-point scale must be positive")
    numerator_value = _require_nonnegative_mathematical_integer(
        numerator,
        "ratio numerator",
    )
    denominator_value = _require_nonnegative_mathematical_integer(
        denominator,
        "ratio denominator",
    )
    if denominator_value == 0:
        return normalized_scale
    if numerator_value > denominator_value:
        raise GovernanceError("ratio numerator cannot exceed denominator")
    return require_scaled_integer(
        (numerator_value * normalized_scale) // denominator_value,
        "ratio result",
        maximum=normalized_scale,
    )


def _require_nonnegative_mathematical_integer(
    value: object,
    field_name: str,
) -> int:
    """Validate an unbounded derived integer, not a canonical authority leaf."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise GovernanceError(f"{field_name} must be an integer")
    if value < 0:
        raise GovernanceError(f"{field_name} must be non-negative")
    return value


def canonical_commit_payload(
    payload: Mapping[str, Any],
    *,
    schema: str,
    profile: str,
    version: str = COMMIT_WIRE_VERSION,
) -> str:
    try:
        return _canonical_commit_payload(
            payload,
            schema=schema,
            profile=profile,
            version=version,
        )
    except CommitWireError as exc:
        raise GovernanceError(str(exc)) from exc


def commit_payload_fingerprint(
    payload: Mapping[str, Any],
    *,
    schema: str,
    profile: str,
    version: str = COMMIT_WIRE_VERSION,
) -> str:
    try:
        return _commit_payload_fingerprint(
            payload,
            schema=schema,
            profile=profile,
            version=version,
        )
    except CommitWireError as exc:
        raise GovernanceError(str(exc)) from exc


def canonical_commit_set(values: Sequence[Any]) -> tuple[Any, ...]:
    try:
        return _canonical_commit_set(values)
    except CommitWireError as exc:
        raise GovernanceError(str(exc)) from exc


__all__ = [
    "COMMIT_CANONICAL_VERSION",
    "COMMIT_WIRE_VERSION",
    "MAX_AUTHORITY_INTEGER",
    "WEIGHT_SCALE",
    "canonical_commit_payload",
    "canonical_commit_set",
    "checked_add",
    "checked_multiply",
    "checked_subtract",
    "ceil_scaled_count",
    "commit_payload_fingerprint",
    "multiply_scaled",
    "require_authority_integer",
    "require_scaled_integer",
    "scaled_ratio",
]
