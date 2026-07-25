"""Type-aware canonical values for Hybrid Replay v2 source commitments.

The representation deliberately excludes legacy process-local issuance fields.
Hybrid Replay v2 binds deterministic evaluation content here; durable authority
still comes only from StateStore inclusion and currentness.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from enum import Enum
from typing import Any

from pheroos.governance.policy_adjustment import RunScopedPolicyOverlay


def _canonical_hybrid_value_v2(value: Any) -> Any:
    value_type = type(value)
    type_id = (value_type.__module__, value_type.__qualname__)
    scalar_handled, scalar = _canonical_hybrid_scalar_v2(value, type_id)
    if scalar_handled:
        return scalar
    structured_handled, structured = _canonical_hybrid_structured_v2(value, type_id)
    if structured_handled:
        return structured
    raise TypeError(f"unsupported Hybrid Replay v2 value: {type_id[0]}.{type_id[1]}")


def _canonical_hybrid_scalar_v2(
    value: Any,
    type_id: tuple[str, str],
) -> tuple[bool, Any]:
    if isinstance(value, Enum):
        return True, ("enum", type_id, _canonical_hybrid_value_v2(value.value))
    if value is None:
        return True, ("none",)
    if isinstance(value, bool):
        return True, ("bool", value)
    if isinstance(value, int):
        return True, ("int", value)
    if isinstance(value, float):
        return True, ("float", value.hex())
    if isinstance(value, str):
        return True, ("str", value)
    return False, None


def _canonical_hybrid_structured_v2(
    value: Any,
    type_id: tuple[str, str],
) -> tuple[bool, Any]:
    if isinstance(value, RunScopedPolicyOverlay):
        return True, (
            "run_scoped_policy_overlay",
            type_id,
            _canonical_hybrid_value_v2(dict(value)),
            _canonical_hybrid_value_v2(object.__getattribute__(value, "source_ids")),
            _canonical_hybrid_value_v2(
                object.__getattribute__(value, "trace_event_ids")
            ),
        )
    if is_dataclass(value) and not isinstance(value, type):
        return True, (
            "dataclass",
            type_id,
            tuple(
                (item.name, _canonical_hybrid_value_v2(getattr(value, item.name)))
                for item in dataclass_fields(value)
                if item.name != "_issuance"
            ),
        )
    if isinstance(value, Mapping):
        entries = [
            (
                _canonical_hybrid_value_v2(key),
                _canonical_hybrid_value_v2(item),
            )
            for key, item in value.items()
        ]
        return True, ("mapping", type_id, tuple(sorted(entries, key=repr)))
    if isinstance(value, tuple):
        return True, (
            "tuple",
            type_id,
            tuple(_canonical_hybrid_value_v2(item) for item in value),
        )
    if isinstance(value, list):
        return True, (
            "list",
            type_id,
            tuple(_canonical_hybrid_value_v2(item) for item in value),
        )
    if isinstance(value, (set, frozenset)):
        items = [_canonical_hybrid_value_v2(item) for item in value]
        return True, ("set", type_id, tuple(sorted(items, key=repr)))
    return False, None


__all__: tuple[str, ...] = ()
