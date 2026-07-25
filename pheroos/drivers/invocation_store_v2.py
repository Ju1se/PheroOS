"""Durable reference store contract for Driver Invocation ABI v2 receipts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from typing import Protocol, runtime_checkable
import unicodedata

from pheroos.drivers.invocation_v2 import (
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    DriverInvocationWireErrorV2,
    validate_driver_invocation_binding_v2,
)
from pheroos._unicode import contains_surrogate_code_point


DRIVER_INVOCATION_STORE_VERSION_V2 = "pheroos-driver-invocation-store-v2"
DRIVER_INVOCATION_CHECKPOINT_VERSION_V2 = (
    "pheroos-driver-invocation-store-checkpoint-v2"
)
DRIVER_INVOCATION_CHECKPOINT_MAX_BYTES_V2 = 4_194_304

_CHECKPOINT_FIELDS = frozenset(
    {"version", "store_version", "receipts", "retired_scopes", "checkpoint_digest"}
)


class DriverInvocationStoreErrorV2(RuntimeError):
    """Fail-closed store conflict, retirement, or checkpoint error."""


@runtime_checkable
class DriverInvocationStoreV2(Protocol):
    """Small persistence boundary for non-authoritative idempotency receipts."""

    store_version: str

    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2: ...

    def get(
        self,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None: ...

    def retire(self, scope_ref: str) -> int: ...

    def checkpoint(self) -> bytes: ...


@dataclass(frozen=True)
class _StoreImageV2:
    receipts: tuple[DriverInvocationReceiptV2, ...]
    retired_scopes: tuple[str, ...]


def _key(receipt: DriverInvocationReceiptV2) -> tuple[str, str, str]:
    return receipt.scope_ref, receipt.driver_id, receipt.idempotency_key


def _validate_identity(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 1024
        or "\x00" in value
        or contains_surrogate_code_point(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise DriverInvocationStoreErrorV2(f"{name} must be canonical nonblank text")
    return value


def _validate_scope_ref(value: object) -> str:
    scope = _validate_identity(value, "scope_ref")
    if len(scope) != 71 or not scope.startswith("sha256:"):
        raise DriverInvocationStoreErrorV2(
            "scope_ref must be a canonical RuntimeScope sha256 reference"
        )
    try:
        int(scope[7:], 16)
    except ValueError as exc:
        raise DriverInvocationStoreErrorV2(
            "scope_ref must be a canonical RuntimeScope sha256 reference"
        ) from exc
    if scope[7:] != scope[7:].lower():
        raise DriverInvocationStoreErrorV2(
            "scope_ref must be a canonical RuntimeScope sha256 reference"
        )
    return scope


def _checkpoint_unsigned(image: _StoreImageV2) -> dict[str, object]:
    return {
        "version": DRIVER_INVOCATION_CHECKPOINT_VERSION_V2,
        "store_version": DRIVER_INVOCATION_STORE_VERSION_V2,
        "receipts": [receipt.to_dict() for receipt in image.receipts],
        "retired_scopes": list(image.retired_scopes),
    }


def _checkpoint_bytes(payload: Mapping[str, object]) -> bytes:
    # Both call sites supply either internal canonical records or values that
    # have already passed the strict JSON decoder, so serialization errors are
    # structurally unreachable here.
    data = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if len(data) > DRIVER_INVOCATION_CHECKPOINT_MAX_BYTES_V2:
        raise DriverInvocationStoreErrorV2("checkpoint exceeds size limit")
    return data


def _checkpoint_digest(image: _StoreImageV2) -> str:
    return (
        "sha256:" + sha256(_checkpoint_bytes(_checkpoint_unsigned(image))).hexdigest()
    )


def _reject_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DriverInvocationStoreErrorV2(f"duplicate checkpoint key: {key}")
        result[key] = value
    return result


def _read_checkpoint_object(data: bytes) -> dict[str, object]:
    if (
        not isinstance(data, bytes)
        or not data
        or len(data) > DRIVER_INVOCATION_CHECKPOINT_MAX_BYTES_V2
    ):
        raise DriverInvocationStoreErrorV2("checkpoint bytes are invalid")
    try:
        payload = json.loads(
            data.decode("ascii"),
            object_pairs_hook=_reject_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                DriverInvocationStoreErrorV2(f"non-finite checkpoint value: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DriverInvocationStoreErrorV2("checkpoint JSON is invalid") from exc
    if type(payload) is not dict or set(payload) != _CHECKPOINT_FIELDS:
        raise DriverInvocationStoreErrorV2("checkpoint fields are invalid")
    if _checkpoint_bytes(payload) != data:
        raise DriverInvocationStoreErrorV2("checkpoint is not canonical JSON")
    return payload


def _checkpoint_collections(
    payload: Mapping[str, object],
) -> tuple[list[object], list[object]]:
    if payload["version"] != DRIVER_INVOCATION_CHECKPOINT_VERSION_V2:
        raise DriverInvocationStoreErrorV2("unsupported checkpoint version")
    if payload["store_version"] != DRIVER_INVOCATION_STORE_VERSION_V2:
        raise DriverInvocationStoreErrorV2("unsupported checkpoint store version")
    raw_receipts = payload["receipts"]
    raw_retired = payload["retired_scopes"]
    if type(raw_receipts) is not list or type(raw_retired) is not list:
        raise DriverInvocationStoreErrorV2("checkpoint collections are invalid")
    return raw_receipts, raw_retired


def _decode_checkpoint(data: bytes) -> _StoreImageV2:
    payload = _read_checkpoint_object(data)
    raw_receipts, raw_retired = _checkpoint_collections(payload)
    try:
        receipt_payloads: list[Mapping[str, object]] = []
        for item in raw_receipts:
            if type(item) is not dict:
                raise DriverInvocationStoreErrorV2(
                    "checkpoint receipt must be an object"
                )
            receipt_payloads.append(item)
        receipts = tuple(
            DriverInvocationReceiptV2.from_dict(item) for item in receipt_payloads
        )
    except (DriverInvocationWireErrorV2, TypeError) as exc:
        raise DriverInvocationStoreErrorV2("checkpoint receipt is invalid") from exc
    if any(type(item) is not str for item in raw_retired):
        raise DriverInvocationStoreErrorV2("checkpoint retired scope is invalid")
    retired = tuple(_validate_scope_ref(item) for item in raw_retired)
    image = _StoreImageV2(receipts=receipts, retired_scopes=retired)
    if len({_key(item) for item in receipts}) != len(receipts):
        raise DriverInvocationStoreErrorV2("checkpoint contains duplicate receipt keys")
    if (
        tuple(sorted(receipts, key=_key)) != receipts
        or tuple(sorted(set(retired))) != retired
    ):
        raise DriverInvocationStoreErrorV2("checkpoint collections are not canonical")
    if any(item.scope_ref in retired for item in receipts):
        raise DriverInvocationStoreErrorV2("retired scope contains active receipt")
    if payload["checkpoint_digest"] != _checkpoint_digest(image):
        raise DriverInvocationStoreErrorV2("checkpoint digest does not match image")
    return image


class InMemoryDriverInvocationStoreV2:
    """Deterministic, thread-safe reference store with restartable tombstones."""

    store_version = DRIVER_INVOCATION_STORE_VERSION_V2

    def __init__(
        self,
        *,
        failure_hook: Callable[[str], None] | None = None,
    ) -> None:
        self._receipts: dict[tuple[str, str, str], DriverInvocationReceiptV2] = {}
        self._retired_scopes: set[str] = set()
        self._failure_hook = failure_hook
        self._lock = RLock()

    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        try:
            validate_driver_invocation_binding_v2(request, result)
        except DriverInvocationWireErrorV2 as exc:
            raise DriverInvocationStoreErrorV2(
                "request/result binding is invalid"
            ) from exc
        receipt = DriverInvocationReceiptV2.for_result(result)
        key = _key(receipt)
        with self._lock:
            if receipt.scope_ref in self._retired_scopes:
                raise DriverInvocationStoreErrorV2("invocation scope is retired")
            existing = self._receipts.get(key)
            if existing is not None:
                if existing != receipt:
                    raise DriverInvocationStoreErrorV2(
                        "idempotency key conflicts with persisted invocation"
                    )
                return existing
            if self._failure_hook is not None:
                self._failure_hook("before_commit")
            self._receipts[key] = receipt
            return receipt

    def get(
        self,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        key = (
            _validate_scope_ref(scope_ref),
            _validate_identity(driver_id, "driver_id"),
            _validate_identity(idempotency_key, "idempotency_key"),
        )
        with self._lock:
            if scope_ref in self._retired_scopes:
                return None
            return self._receipts.get(key)

    def retire(self, scope_ref: str) -> int:
        scope = _validate_scope_ref(scope_ref)
        with self._lock:
            if scope in self._retired_scopes:
                return 0
            keys = tuple(key for key in self._receipts if key[0] == scope)
            if self._failure_hook is not None:
                self._failure_hook("before_retire")
            for key in keys:
                del self._receipts[key]
            self._retired_scopes.add(scope)
            return len(keys)

    def checkpoint(self) -> bytes:
        with self._lock:
            image = _StoreImageV2(
                receipts=tuple(sorted(self._receipts.values(), key=_key)),
                retired_scopes=tuple(sorted(self._retired_scopes)),
            )
        payload = {
            **_checkpoint_unsigned(image),
            "checkpoint_digest": _checkpoint_digest(image),
        }
        return _checkpoint_bytes(payload)

    @classmethod
    def from_checkpoint(
        cls,
        data: bytes,
        *,
        failure_hook: Callable[[str], None] | None = None,
    ) -> InMemoryDriverInvocationStoreV2:
        image = _decode_checkpoint(data)
        store = cls(failure_hook=failure_hook)
        store._receipts = {_key(receipt): receipt for receipt in image.receipts}
        store._retired_scopes = set(image.retired_scopes)
        return store


__all__ = [
    "DRIVER_INVOCATION_CHECKPOINT_MAX_BYTES_V2",
    "DRIVER_INVOCATION_CHECKPOINT_VERSION_V2",
    "DRIVER_INVOCATION_STORE_VERSION_V2",
    "DriverInvocationStoreErrorV2",
    "DriverInvocationStoreV2",
    "InMemoryDriverInvocationStoreV2",
]
