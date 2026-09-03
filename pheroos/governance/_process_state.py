"""Small process-local state table for Draft internal records.

This is an implementation detail only.  Public authority comes from the
StateStore-backed v2 contracts; the table exists solely for internal immutable
record issuance paths that still need a short-lived identity cursor.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from threading import RLock
from typing import Any


class _StateTransaction:
    __slots__ = ("__namespaces",)

    def __init__(self, namespaces: dict[str, dict[Hashable, Any]]) -> None:
        self.__namespaces = namespaces

    def get(self, namespace: str, key: Hashable) -> Any | None:
        return self.__namespaces.get(namespace, {}).get(key)

    def set(self, namespace: str, key: Hashable, value: Any) -> None:
        self.__namespaces.setdefault(namespace, {})[key] = value

    def delete(self, namespace: str, key: Hashable) -> None:
        values = self.__namespaces.get(namespace)
        if values is None:
            return
        values.pop(key, None)
        if not values:
            self.__namespaces.pop(namespace, None)


class _ProcessState:
    __slots__ = ("__lock", "__namespaces")

    def __init__(self) -> None:
        self.__lock = RLock()
        self.__namespaces: dict[str, dict[Hashable, Any]] = {}

    @contextmanager
    def transaction(self) -> Iterator[_StateTransaction]:
        with self.__lock:
            yield _StateTransaction(self.__namespaces)

    def get(self, namespace: str, key: Hashable) -> Any | None:
        with self.transaction() as transaction:
            return transaction.get(namespace, key)


PROCESS_STATE = _ProcessState()
