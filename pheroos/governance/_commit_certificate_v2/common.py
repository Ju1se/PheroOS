"""Bounded canonical helpers for Commit Certificate v2.

This module deliberately owns no authority.  It only defines the exact wire
canonicalization used by portable certificate records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import cast

from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2


MAX_COMMIT_CERTIFICATE_TEXT_BYTES_V2 = 4_096
MAX_COMMIT_CERTIFICATE_ATTESTATIONS_V2 = 32
MAX_COMMIT_CERTIFICATE_LEAVES_V2 = 16
MAX_COMMIT_CERTIFICATE_SNAPSHOT_BYTES_V2 = 524_288


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be an exact string")
    result = value
    if not result and not allow_empty:
        raise ValueError(f"{label} must be non-empty")
    if "\x00" in result:
        raise ValueError(f"{label} contains U+0000")
    try:
        encoded = result.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must encode as UTF-8") from exc
    if len(encoded) > MAX_COMMIT_CERTIFICATE_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds its text bound")
    return result


def _require_root(value: object, label: str, *, allow_empty: bool = False) -> str:
    result = _require_text(value, label, allow_empty=allow_empty)
    if allow_empty and not result:
        return result
    if (
        len(result) != 71
        or not result.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in result[7:])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 root")
    return result


def _require_count(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} is outside its integer bound")
    return value


def _canonical_texts(
    values: Sequence[str],
    label: str,
    *,
    maximum: int = MAX_COMMIT_CERTIFICATE_ATTESTATIONS_V2,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    items = tuple(values)
    if len(items) > maximum or (not items and not allow_empty):
        raise ValueError(f"{label} has an invalid item count")
    result = tuple(_require_text(item, label) for item in items)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique values")
    return tuple(sorted(result, key=lambda item: item.encode("utf-8")))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _root(label: str, body: object) -> str:
    material = b"pheroos-commit-certificate-v2\x00" + label.encode("utf-8")
    return "sha256:" + sha256(material + b"\x00" + _canonical_bytes(body)).hexdigest()


def _install_root(
    instance: object,
    field: str,
    supplied: object,
    label: str,
    body: object,
) -> str:
    expected = _root(label, body)
    if supplied not in ("", expected):
        raise ValueError(f"commit certificate {field} is mismatched")
    object.__setattr__(instance, field, expected)
    return expected


def _exact_mapping(
    payload: object,
    fields: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(payload) is not dict:
        raise TypeError(f"{label} must be an exact object")
    value = cast(dict[object, object], payload)
    if any(type(key) is not str for key in value) or set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
    return cast(dict[str, object], value.copy())


def _exact_array(payload: object, label: str) -> tuple[object, ...]:
    if type(payload) is not list:
        raise TypeError(f"{label} must be an exact wire array")
    return tuple(cast(list[object], payload))


def _require_canonical_wire(
    supplied: object,
    expected: Mapping[str, object],
    label: str,
) -> None:
    if supplied != expected:
        raise ValueError(f"{label} is not canonical wire")


__all__: tuple[str, ...] = ()
