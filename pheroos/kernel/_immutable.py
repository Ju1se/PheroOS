from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any


def freeze_abi_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {deepcopy(key): freeze_abi_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze_abi_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze_abi_value(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return deepcopy(value)


def freeze_abi_sequence(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(freeze_abi_value(item) for item in value)
    return freeze_abi_value(value)


def abi_value_is_frozen(value: Any) -> bool:
    if isinstance(value, MappingProxyType):
        return all(
            abi_value_is_frozen(key) and abi_value_is_frozen(item)
            for key, item in value.items()
        )
    if isinstance(value, tuple):
        return all(abi_value_is_frozen(item) for item in value)
    if isinstance(value, frozenset):
        return all(abi_value_is_frozen(item) for item in value)
    return not isinstance(value, (Mapping, list, set, bytearray))


__all__ = ["abi_value_is_frozen", "freeze_abi_sequence", "freeze_abi_value"]
