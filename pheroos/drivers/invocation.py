from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from numbers import Real
import re
from threading import RLock
from types import MappingProxyType
from typing import Any

from pheroos.drivers.base import DriverResult
from pheroos.drivers.errors import DriverError
from pheroos.drivers._versions import (
    DRIVER_INVOCATION_RECEIPT_VERSION,
    DRIVER_INVOCATION_VERSION,
)


_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def driver_request_digest(
    *,
    scope_ref: str,
    invocation_id: str,
    driver_id: str,
    operation: str,
    capability: str,
    idempotency_key: str,
    payload: Mapping[str, Any],
) -> str:
    """Bind one invocation to its scope, operation, capability and payload."""

    values = {
        "scope_ref": scope_ref,
        "invocation_id": invocation_id,
        "driver_id": driver_id,
        "operation": operation,
        "capability": capability,
        "idempotency_key": idempotency_key,
    }
    if not all(isinstance(value, str) and value.strip() for value in values.values()):
        raise ValueError("driver invocation identities must be nonblank strings")
    canonical = json.dumps(
        {
            **values,
            "payload": _canonical_value(payload, path="payload"),
            "version": DRIVER_INVOCATION_VERSION,
        },
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def driver_result_digest(result: DriverResult) -> str:
    """Bind one canonical result to the request identity it echoes."""

    if not isinstance(result, DriverResult):
        raise ValueError("driver result must be canonical")
    canonical = json.dumps(
        {
            "driver_id": result.driver_id,
            "invocation_id": result.invocation_id,
            "invocation_version": result.invocation_version,
            "ok": result.ok,
            "operation": result.operation,
            "payload": _canonical_value(result.payload, path="result.payload"),
            "provenance": result.provenance,
            "request_digest": result.request_digest,
            "scope_ref": result.scope_ref,
            "version": DRIVER_INVOCATION_RECEIPT_VERSION,
        },
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DriverInvocationReceipt:
    scope_ref: str
    driver_id: str
    idempotency_key: str
    request_digest: str
    result_digest: str
    version: str = DRIVER_INVOCATION_RECEIPT_VERSION

    def __post_init__(self) -> None:
        if self.version != DRIVER_INVOCATION_RECEIPT_VERSION:
            raise ValueError("unsupported driver invocation receipt version")
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (self.scope_ref, self.driver_id, self.idempotency_key)
        ):
            raise ValueError("driver invocation receipt identities must be nonblank")
        if not all(
            isinstance(value, str) and _DIGEST_PATTERN.fullmatch(value)
            for value in (self.request_digest, self.result_digest)
        ):
            raise ValueError("driver invocation receipt digests must be canonical sha256")


class DriverInvocationLedger:
    """Explicit run-scoped idempotency ledger for a Kernel/runtime boundary."""

    def __init__(self) -> None:
        self.__receipts: dict[
            tuple[str, str, str],
            DriverInvocationReceipt,
        ] = {}
        self.__lock = RLock()

    def record(
        self,
        *,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
        request_digest: str,
        result_digest: str,
    ) -> DriverInvocationReceipt:
        values = (scope_ref, driver_id, idempotency_key, request_digest, result_digest)
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise DriverError("driver invocation receipt identities must be nonblank")
        if not (
            _DIGEST_PATTERN.fullmatch(request_digest)
            and _DIGEST_PATTERN.fullmatch(result_digest)
        ):
            raise DriverError("driver invocation receipt digests must be canonical sha256")
        key = (scope_ref, driver_id, idempotency_key)
        receipt = DriverInvocationReceipt(
            scope_ref=scope_ref,
            driver_id=driver_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            result_digest=result_digest,
        )
        with self.__lock:
            existing = self.__receipts.get(key)
            if existing is not None:
                if existing != receipt:
                    raise DriverError(
                        "driver idempotency key was reused with a conflicting request or result"
                    )
                return existing
            self.__receipts[key] = receipt
            return receipt

    def get(
        self,
        *,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceipt | None:
        with self.__lock:
            return self.__receipts.get((scope_ref, driver_id, idempotency_key))

    def retire_scope(self, scope_ref: str) -> int:
        if not isinstance(scope_ref, str) or not scope_ref.strip():
            raise DriverError("driver invocation scope_ref is required")
        with self.__lock:
            keys = [key for key in self.__receipts if key[0] == scope_ref]
            for key in keys:
                del self.__receipts[key]
            return len(keys)

    @property
    def receipts(self) -> Mapping[tuple[str, str, str], DriverInvocationReceipt]:
        with self.__lock:
            return MappingProxyType(dict(self.__receipts))


def _canonical_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Real):
        if not isfinite(float(value)):
            raise ValueError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{path} keys must be non-empty strings")
            result[key] = _canonical_value(item, path=f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _canonical_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ValueError(f"{path} contains unsupported value type: {type(value).__name__}")


__all__ = [
    "DRIVER_INVOCATION_RECEIPT_VERSION",
    "DRIVER_INVOCATION_VERSION",
    "DriverInvocationLedger",
    "DriverInvocationReceipt",
    "driver_request_digest",
    "driver_result_digest",
]
