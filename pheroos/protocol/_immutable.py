from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import is_dataclass
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


def snapshot_fields(
    value: object,
    *,
    sequences: tuple[str, ...] = (),
    mappings: tuple[str, ...] = (),
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


__all__ = ["deep_freeze", "snapshot_fields"]
