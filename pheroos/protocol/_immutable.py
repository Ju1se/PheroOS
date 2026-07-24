from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any


def deep_freeze(value: Any) -> Any:
    """Recursively freeze caller-owned containers at the Protocol ABI edge."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {deepcopy(key): deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    if is_dataclass(value):
        # Protocol dataclasses are frozen and recursively snapshot themselves.
        return value
    return deepcopy(value)


def canonical_json_snapshot(value: Any) -> Any:
    """Snapshot one extension value into immutable canonical JSON structure.

    Declaration-valued mappings such as risk bands must retain their runtime
    types, so this projection is deliberately separate from ``deep_freeze`` and
    is used only for extension mappings.
    """

    if isinstance(value, Enum):
        return canonical_json_snapshot(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return MappingProxyType(
            {
                item.name: canonical_json_snapshot(getattr(value, item.name))
                for item in fields(value)
            }
        )
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                deepcopy(key): canonical_json_snapshot(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(canonical_json_snapshot(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(canonical_json_snapshot(item) for item in value)
    return deepcopy(value)


def snapshot_fields(
    value: object,
    *,
    sequences: tuple[str, ...] = (),
    mappings: tuple[str, ...] = (),
    canonical_mappings: tuple[str, ...] = (),
) -> None:
    for name in sequences:
        object.__setattr__(
            value,
            name,
            tuple(deep_freeze(item) for item in getattr(value, name)),
        )
    for name in mappings:
        source = getattr(value, name)
        object.__setattr__(
            value,
            name,
            MappingProxyType(
                {deepcopy(key): deep_freeze(item) for key, item in source.items()}
            ),
        )
    for name in canonical_mappings:
        source = getattr(value, name)
        object.__setattr__(
            value,
            name,
            MappingProxyType(
                {
                    deepcopy(key): canonical_json_snapshot(item)
                    for key, item in source.items()
                }
            ),
        )


__all__ = ["canonical_json_snapshot", "deep_freeze", "snapshot_fields"]
