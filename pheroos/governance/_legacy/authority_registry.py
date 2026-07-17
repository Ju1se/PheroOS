from __future__ import annotations

"""Single quarantined adapter for v1 process-local authority identity.

The adapter is intentionally private and non-extensible.  It is not consulted
by the scoped ``GovernanceStateStore`` path.  Centralizing the old registries
makes their compatibility lifetime, cardinality, and eventual deletion
observable while preserving v1's object-identity checks byte-for-byte.
"""

from collections.abc import Hashable, Iterator, Mapping
from contextlib import contextmanager
from threading import RLock
from types import MappingProxyType
from typing import Any


LEGACY_AUTHORITY_ADAPTER_VERSION = "pheroos-legacy-authority-adapter-v1"


class _LegacyAuthorityTransaction:
    __slots__ = ("__namespaces",)

    def __init__(self, namespaces: dict[str, dict[Hashable, Any]]) -> None:
        self.__namespaces = namespaces

    def get(self, namespace: str, key: Hashable) -> Any | None:
        _require_namespace(namespace)
        return self.__namespaces.get(namespace, {}).get(key)

    def set(self, namespace: str, key: Hashable, value: Any) -> None:
        _require_namespace(namespace)
        if not isinstance(key, Hashable):
            raise TypeError("legacy authority key must be hashable")
        self.__namespaces.setdefault(namespace, {})[key] = value

    def delete(self, namespace: str, key: Hashable) -> None:
        _require_namespace(namespace)
        values = self.__namespaces.get(namespace)
        if values is None:
            return
        values.pop(key, None)
        if not values:
            self.__namespaces.pop(namespace, None)


class LegacyAuthorityRegistry:
    """Thread-safe, fixed-shape quarantine for legacy v1 state only."""

    __slots__ = ("__lock", "__namespaces")

    def __init__(self) -> None:
        self.__lock = RLock()
        self.__namespaces: dict[str, dict[Hashable, Any]] = {}

    @contextmanager
    def transaction(self) -> Iterator[_LegacyAuthorityTransaction]:
        """Serialize a complete legacy identity claim or cursor install."""

        with self.__lock:
            yield _LegacyAuthorityTransaction(self.__namespaces)

    def get(self, namespace: str, key: Hashable) -> Any | None:
        with self.transaction() as transaction:
            return transaction.get(namespace, key)

    def cardinalities(self) -> Mapping[str, int]:
        """Expose bounded diagnostic counts without exposing mutable values."""

        with self.__lock:
            return MappingProxyType(
                {
                    namespace: len(self.__namespaces[namespace])
                    for namespace in sorted(self.__namespaces)
                }
            )

    def total_record_count(self) -> int:
        with self.__lock:
            return sum(len(values) for values in self.__namespaces.values())

    def clear_for_conformance(self) -> None:
        """Reset isolated fixtures; never use this as an authority transition."""

        with self.__lock:
            self.__namespaces.clear()


def _require_namespace(namespace: object) -> str:
    if (
        not isinstance(namespace, str)
        or not namespace
        or namespace != namespace.strip()
        or not namespace.startswith("legacy.")
    ):
        raise ValueError("legacy authority namespace is invalid")
    return namespace


LEGACY_AUTHORITY_REGISTRY = LegacyAuthorityRegistry()


__all__ = [
    "LEGACY_AUTHORITY_ADAPTER_VERSION",
    "LEGACY_AUTHORITY_REGISTRY",
    "LegacyAuthorityRegistry",
]
