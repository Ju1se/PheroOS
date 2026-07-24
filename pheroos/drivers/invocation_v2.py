"""Portable, provider-neutral Driver Invocation ABI v2 values.

These values describe and bind an invocation performed by an outer runtime.
They do not call a provider and do not grant governance or output authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
import json
from math import isfinite
import re
from typing import ClassVar, Self, cast
import unicodedata

from pheroos._immutable import freeze_abi_value
from pheroos._unicode import contains_surrogate_code_point


DRIVER_INVOCATION_REQUEST_VERSION_V2 = "pheroos-driver-invocation-request-v2"
DRIVER_INVOCATION_RESULT_VERSION_V2 = "pheroos-driver-invocation-result-v2"
DRIVER_INVOCATION_REPLY_VERSION_V2 = "pheroos-driver-invocation-reply-v2"
DRIVER_INVOCATION_RECEIPT_VERSION_V2 = "pheroos-driver-invocation-receipt-v2"
DRIVER_INVOCATION_WIRE_MAX_BYTES_V2 = 65_536

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_MAX_LENGTH = 1024


class DriverInvocationWireErrorV2(ValueError):
    """Raised when portable Driver Invocation v2 wire is not canonical."""


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > _IDENTITY_MAX_LENGTH
        or "\x00" in value
        or contains_surrogate_code_point(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise DriverInvocationWireErrorV2(f"{name} must be canonical nonblank text")
    return value


def _scope_ref(value: object) -> str:
    scope = _text(value, "scope_ref")
    if _DIGEST_PATTERN.fullmatch(scope) is None:
        raise DriverInvocationWireErrorV2(
            "scope_ref must be a canonical RuntimeScope sha256 reference"
        )
    return scope


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise DriverInvocationWireErrorV2(f"{name} must be canonical sha256")
    return value


def _canonical_value(value: object, path: str = "payload") -> object:
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        if (
            "\x00" in value
            or contains_surrogate_code_point(value)
            or unicodedata.normalize("NFC", value) != value
        ):
            raise DriverInvocationWireErrorV2(f"{path} contains noncanonical text")
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        return _canonical_real(value, path)
    if type(value) is dict:
        return _canonical_mapping(value, path)
    if type(value) is list:
        return [
            _canonical_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise DriverInvocationWireErrorV2(
        f"{path} contains unsupported value type: {type(value).__name__}"
    )


def _canonical_real(value: object, path: str) -> float:
    number = cast(float, value)
    if not isfinite(number) or number == 0.0 and str(value).startswith("-"):
        raise DriverInvocationWireErrorV2(
            f"{path} contains a non-finite or noncanonical number"
        )
    return number


def _canonical_mapping(value: object, path: str) -> dict[str, object]:
    mapping = cast(dict[object, object], value)
    result: dict[str, object] = {}
    for key, item in mapping.items():
        if (
            not isinstance(key, str)
            or not key
            or len(key) > _IDENTITY_MAX_LENGTH
            or "\x00" in key
            or contains_surrogate_code_point(key)
            or unicodedata.normalize("NFC", key) != key
        ):
            raise DriverInvocationWireErrorV2(
                f"{path} keys must be bounded non-empty canonical strings"
            )
        # Exact ``dict`` inputs cannot yield a key twice; duplicate JSON keys
        # are rejected earlier by _reject_duplicate_pairs while decoding.
        result[key] = _canonical_value(item, f"{path}.{key}")
    return result


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    # _canonical_value has already reduced the payload to the exact JSON
    # scalar/container set and rejected non-finite numbers and invalid keys.
    encoded = json.dumps(
        _canonical_value(payload, "wire"),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if len(encoded) > DRIVER_INVOCATION_WIRE_MAX_BYTES_V2:
        raise DriverInvocationWireErrorV2("driver invocation wire exceeds size limit")
    return encoded


def _fingerprint(payload: Mapping[str, object]) -> str:
    return "sha256:" + sha256(_canonical_bytes(payload)).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DriverInvocationWireErrorV2(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _read_wire(data: bytes, *, name: str) -> dict[str, object]:
    if (
        not isinstance(data, bytes)
        or not data
        or len(data) > DRIVER_INVOCATION_WIRE_MAX_BYTES_V2
    ):
        raise DriverInvocationWireErrorV2(f"{name} wire bytes are invalid")
    try:
        text = data.decode("ascii")
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                DriverInvocationWireErrorV2(f"non-finite JSON number: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DriverInvocationWireErrorV2(f"{name} wire is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise DriverInvocationWireErrorV2(f"{name} wire must be an object")
    if _canonical_bytes(payload) != data:
        raise DriverInvocationWireErrorV2(f"{name} wire is not canonical JSON")
    return payload


def _exact(payload: Mapping[str, object], fields: frozenset[str], name: str) -> None:
    if type(payload) is not dict or set(payload) != fields:
        raise DriverInvocationWireErrorV2(f"{name} fields are invalid")


@dataclass(frozen=True)
class DriverInvocationRequestV2:
    scope_ref: str
    driver_id: str
    invocation_id: str
    operation: str
    capability: str
    idempotency_key: str
    payload: Mapping[str, object] = field(default_factory=dict)
    request_digest: str = ""
    version: str = DRIVER_INVOCATION_REQUEST_VERSION_V2

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "version",
            "scope_ref",
            "driver_id",
            "invocation_id",
            "operation",
            "capability",
            "idempotency_key",
            "payload",
            "request_digest",
        }
    )

    def __post_init__(self) -> None:
        if self.version != DRIVER_INVOCATION_REQUEST_VERSION_V2:
            raise DriverInvocationWireErrorV2("unsupported request version")
        for name in (
            "driver_id",
            "invocation_id",
            "operation",
            "capability",
            "idempotency_key",
        ):
            _text(getattr(self, name), name)
        _scope_ref(self.scope_ref)
        canonical = _canonical_value(self.payload)
        if not isinstance(canonical, dict):
            raise DriverInvocationWireErrorV2("request payload must be an object")
        object.__setattr__(self, "payload", freeze_abi_value(canonical))
        expected = _fingerprint(self._unsigned_dict())
        if (
            self.request_digest
            and _digest(self.request_digest, "request_digest") != expected
        ):
            raise DriverInvocationWireErrorV2("request digest does not match request")
        object.__setattr__(self, "request_digest", expected)

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "driver_id": self.driver_id,
            "invocation_id": self.invocation_id,
            "operation": self.operation,
            "capability": self.capability,
            "idempotency_key": self.idempotency_key,
            "payload": _thaw(self.payload),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "request_digest": self.request_digest}

    def to_wire(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _exact(payload, cls._FIELDS, "request")
        raw_payload = payload["payload"]
        if type(raw_payload) is not dict:
            raise DriverInvocationWireErrorV2("request payload must be an object")
        return cls(
            scope_ref=_scope_ref(payload["scope_ref"]),
            driver_id=_text(payload["driver_id"], "driver_id"),
            invocation_id=_text(payload["invocation_id"], "invocation_id"),
            operation=_text(payload["operation"], "operation"),
            capability=_text(payload["capability"], "capability"),
            idempotency_key=_text(payload["idempotency_key"], "idempotency_key"),
            payload=raw_payload,
            request_digest=_digest(payload["request_digest"], "request_digest"),
            version=_text(payload["version"], "version"),
        )

    @classmethod
    def from_wire(cls, data: bytes) -> Self:
        return cls.from_dict(_read_wire(data, name="request"))


@dataclass(frozen=True)
class DriverInvocationResultV2:
    scope_ref: str
    driver_id: str
    invocation_id: str
    operation: str
    capability: str
    idempotency_key: str
    request_digest: str
    ok: bool
    payload: Mapping[str, object]
    provenance: str
    result_digest: str = ""
    version: str = DRIVER_INVOCATION_RESULT_VERSION_V2

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "version",
            "scope_ref",
            "driver_id",
            "invocation_id",
            "operation",
            "capability",
            "idempotency_key",
            "request_digest",
            "ok",
            "payload",
            "provenance",
            "result_digest",
        }
    )

    def __post_init__(self) -> None:
        if self.version != DRIVER_INVOCATION_RESULT_VERSION_V2:
            raise DriverInvocationWireErrorV2("unsupported result version")
        for name in (
            "driver_id",
            "invocation_id",
            "operation",
            "capability",
            "idempotency_key",
            "provenance",
        ):
            _text(getattr(self, name), name)
        _scope_ref(self.scope_ref)
        _digest(self.request_digest, "request_digest")
        if type(self.ok) is not bool:
            raise DriverInvocationWireErrorV2("result ok must be boolean")
        canonical = _canonical_value(self.payload)
        if not isinstance(canonical, dict):
            raise DriverInvocationWireErrorV2("result payload must be an object")
        object.__setattr__(self, "payload", freeze_abi_value(canonical))
        expected = _fingerprint(self._unsigned_dict())
        if (
            self.result_digest
            and _digest(self.result_digest, "result_digest") != expected
        ):
            raise DriverInvocationWireErrorV2("result digest does not match result")
        object.__setattr__(self, "result_digest", expected)

    @classmethod
    def for_request(
        cls,
        request: DriverInvocationRequestV2,
        *,
        ok: bool,
        payload: Mapping[str, object],
        provenance: str,
    ) -> Self:
        if type(request) is not DriverInvocationRequestV2:
            raise DriverInvocationWireErrorV2("result requires canonical request")
        return cls(
            scope_ref=request.scope_ref,
            driver_id=request.driver_id,
            invocation_id=request.invocation_id,
            operation=request.operation,
            capability=request.capability,
            idempotency_key=request.idempotency_key,
            request_digest=request.request_digest,
            ok=ok,
            payload=payload,
            provenance=provenance,
        )

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "driver_id": self.driver_id,
            "invocation_id": self.invocation_id,
            "operation": self.operation,
            "capability": self.capability,
            "idempotency_key": self.idempotency_key,
            "request_digest": self.request_digest,
            "ok": self.ok,
            "payload": _thaw(self.payload),
            "provenance": self.provenance,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "result_digest": self.result_digest}

    def to_wire(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _exact(payload, cls._FIELDS, "result")
        raw_payload = payload["payload"]
        if type(raw_payload) is not dict:
            raise DriverInvocationWireErrorV2("result payload must be an object")
        raw_ok = payload["ok"]
        if type(raw_ok) is not bool:
            raise DriverInvocationWireErrorV2("result ok must be boolean")
        return cls(
            scope_ref=_scope_ref(payload["scope_ref"]),
            driver_id=_text(payload["driver_id"], "driver_id"),
            invocation_id=_text(payload["invocation_id"], "invocation_id"),
            operation=_text(payload["operation"], "operation"),
            capability=_text(payload["capability"], "capability"),
            idempotency_key=_text(payload["idempotency_key"], "idempotency_key"),
            request_digest=_digest(payload["request_digest"], "request_digest"),
            ok=raw_ok,
            payload=raw_payload,
            provenance=_text(payload["provenance"], "provenance"),
            result_digest=_digest(payload["result_digest"], "result_digest"),
            version=_text(payload["version"], "version"),
        )

    @classmethod
    def from_wire(cls, data: bytes) -> Self:
        return cls.from_dict(_read_wire(data, name="result"))


def validate_driver_invocation_binding_v2(
    request: DriverInvocationRequestV2,
    result: DriverInvocationResultV2,
) -> None:
    if (
        type(request) is not DriverInvocationRequestV2
        or type(result) is not DriverInvocationResultV2
    ):
        raise DriverInvocationWireErrorV2(
            "invocation binding requires canonical values"
        )
    fields = (
        "scope_ref",
        "driver_id",
        "invocation_id",
        "operation",
        "capability",
        "idempotency_key",
        "request_digest",
    )
    if any(getattr(request, name) != getattr(result, name) for name in fields):
        raise DriverInvocationWireErrorV2("result does not bind the exact request")


@dataclass(frozen=True)
class DriverInvocationReceiptV2:
    scope_ref: str
    driver_id: str
    invocation_id: str
    operation: str
    capability: str
    idempotency_key: str
    provenance: str
    request_digest: str
    result_digest: str
    receipt_digest: str = ""
    version: str = DRIVER_INVOCATION_RECEIPT_VERSION_V2

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "version",
            "scope_ref",
            "driver_id",
            "invocation_id",
            "operation",
            "capability",
            "idempotency_key",
            "provenance",
            "request_digest",
            "result_digest",
            "receipt_digest",
        }
    )

    def __post_init__(self) -> None:
        if self.version != DRIVER_INVOCATION_RECEIPT_VERSION_V2:
            raise DriverInvocationWireErrorV2("unsupported receipt version")
        for name in (
            "driver_id",
            "invocation_id",
            "operation",
            "capability",
            "idempotency_key",
            "provenance",
        ):
            _text(getattr(self, name), name)
        _scope_ref(self.scope_ref)
        _digest(self.request_digest, "request_digest")
        _digest(self.result_digest, "result_digest")
        expected = _fingerprint(self._unsigned_dict())
        if (
            self.receipt_digest
            and _digest(self.receipt_digest, "receipt_digest") != expected
        ):
            raise DriverInvocationWireErrorV2("receipt digest does not match receipt")
        object.__setattr__(self, "receipt_digest", expected)

    @classmethod
    def for_result(cls, result: DriverInvocationResultV2) -> Self:
        if type(result) is not DriverInvocationResultV2:
            raise DriverInvocationWireErrorV2("receipt requires canonical result")
        return cls(
            scope_ref=result.scope_ref,
            driver_id=result.driver_id,
            invocation_id=result.invocation_id,
            operation=result.operation,
            capability=result.capability,
            idempotency_key=result.idempotency_key,
            provenance=result.provenance,
            request_digest=result.request_digest,
            result_digest=result.result_digest,
        )

    def _unsigned_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "driver_id": self.driver_id,
            "invocation_id": self.invocation_id,
            "operation": self.operation,
            "capability": self.capability,
            "idempotency_key": self.idempotency_key,
            "provenance": self.provenance,
            "request_digest": self.request_digest,
            "result_digest": self.result_digest,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._unsigned_dict(), "receipt_digest": self.receipt_digest}

    def to_wire(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _exact(payload, cls._FIELDS, "receipt")
        return cls(
            scope_ref=_scope_ref(payload["scope_ref"]),
            driver_id=_text(payload["driver_id"], "driver_id"),
            invocation_id=_text(payload["invocation_id"], "invocation_id"),
            operation=_text(payload["operation"], "operation"),
            capability=_text(payload["capability"], "capability"),
            idempotency_key=_text(payload["idempotency_key"], "idempotency_key"),
            provenance=_text(payload["provenance"], "provenance"),
            request_digest=_digest(payload["request_digest"], "request_digest"),
            result_digest=_digest(payload["result_digest"], "result_digest"),
            receipt_digest=_digest(payload["receipt_digest"], "receipt_digest"),
            version=_text(payload["version"], "version"),
        )

    @classmethod
    def from_wire(cls, data: bytes) -> Self:
        return cls.from_dict(_read_wire(data, name="receipt"))


@dataclass(frozen=True)
class DriverInvocationReplyV2:
    request: DriverInvocationRequestV2
    result: DriverInvocationResultV2
    receipt: DriverInvocationReceiptV2
    version: str = DRIVER_INVOCATION_REPLY_VERSION_V2

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"version", "request", "result", "receipt"}
    )

    def __post_init__(self) -> None:
        if self.version != DRIVER_INVOCATION_REPLY_VERSION_V2:
            raise DriverInvocationWireErrorV2("unsupported reply version")
        validate_driver_invocation_binding_v2(self.request, self.result)
        expected = DriverInvocationReceiptV2.for_result(self.result)
        if self.receipt != expected:
            raise DriverInvocationWireErrorV2("reply receipt does not bind result")

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "request": self.request.to_dict(),
            "result": self.result.to_dict(),
            "receipt": self.receipt.to_dict(),
        }

    def to_wire(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Self:
        _exact(payload, cls._FIELDS, "reply")
        if any(
            type(payload[name]) is not dict for name in ("request", "result", "receipt")
        ):
            raise DriverInvocationWireErrorV2("reply members must be objects")
        return cls(
            request=DriverInvocationRequestV2.from_dict(
                cast(Mapping[str, object], payload["request"])
            ),
            result=DriverInvocationResultV2.from_dict(
                cast(Mapping[str, object], payload["result"])
            ),
            receipt=DriverInvocationReceiptV2.from_dict(
                cast(Mapping[str, object], payload["receipt"])
            ),
            version=_text(payload["version"], "version"),
        )

    @classmethod
    def from_wire(cls, data: bytes) -> Self:
        return cls.from_dict(_read_wire(data, name="reply"))


__all__ = [
    "DRIVER_INVOCATION_RECEIPT_VERSION_V2",
    "DRIVER_INVOCATION_REPLY_VERSION_V2",
    "DRIVER_INVOCATION_REQUEST_VERSION_V2",
    "DRIVER_INVOCATION_RESULT_VERSION_V2",
    "DRIVER_INVOCATION_WIRE_MAX_BYTES_V2",
    "DriverInvocationReceiptV2",
    "DriverInvocationReplyV2",
    "DriverInvocationRequestV2",
    "DriverInvocationResultV2",
    "DriverInvocationWireErrorV2",
    "validate_driver_invocation_binding_v2",
]
