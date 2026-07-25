"""Canonical, bounded helpers shared by Distributed Commit v2 owners."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import cast

from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2


MAX_DISTRIBUTED_TEXT_BYTES_V2 = 4_096
MAX_DISTRIBUTED_PRINCIPALS_V2 = 4_096
MAX_DISTRIBUTED_PROPOSALS_V2 = 256
MAX_DISTRIBUTED_WITNESSES_V2 = 8_192
MAX_DISTRIBUTED_CERTIFICATES_V2 = 64
MAX_DISTRIBUTED_ROOTS_V2 = 8_192
MAX_DISTRIBUTED_SNAPSHOT_BYTES_V2 = 32 * 1024 * 1024


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
    if len(encoded) > MAX_DISTRIBUTED_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds its text bound")
    return result


def _require_root(value: object, label: str, *, allow_empty: bool = False) -> str:
    root = _require_text(value, label, allow_empty=allow_empty)
    if allow_empty and not root:
        return root
    if (
        len(root) != 71
        or not root.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in root[7:])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 root")
    return root


def _require_count(
    value: object,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = MAX_AUTHORITY_REVISION_V2,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} is outside its integer bound")
    return value


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


def _exact_array(
    payload: object,
    label: str,
    *,
    maximum: int = MAX_DISTRIBUTED_ROOTS_V2,
    allow_empty: bool = True,
) -> tuple[object, ...]:
    if type(payload) is not list:
        raise TypeError(f"{label} must be an exact wire array")
    values = tuple(cast(list[object], payload))
    if len(values) > maximum or (not allow_empty and not values):
        raise ValueError(f"{label} count is outside its bound")
    return values


def _canonical_texts(
    values: Sequence[str],
    label: str,
    *,
    maximum: int,
    allow_empty: bool = True,
    roots: bool = False,
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact sequence")
    items = tuple(values)
    if len(items) > maximum or (not allow_empty and not items):
        raise ValueError(f"{label} count is outside its bound")
    validator = _require_root if roots else _require_text
    canonical = tuple(validator(item, label) for item in items)
    if len(canonical) != len(set(canonical)):
        raise ValueError(f"{label} contains duplicates")
    return tuple(sorted(canonical, key=lambda item: item.encode("utf-8")))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _root(label: str, body: object) -> str:
    domain = b"pheroos-distributed-commit-v2\x00" + label.encode("utf-8")
    return "sha256:" + sha256(domain + b"\x00" + _canonical_bytes(body)).hexdigest()


def _install_root(
    instance: object,
    field: str,
    supplied: object,
    label: str,
    body: object,
) -> str:
    expected = _root(label, body)
    if supplied not in ("", expected):
        raise ValueError(f"distributed commit {field} is mismatched")
    object.__setattr__(instance, field, expected)
    return expected


def _require_canonical_wire(
    supplied: object,
    expected: Mapping[str, object],
    label: str,
) -> None:
    if supplied != expected:
        raise ValueError(f"{label} is not canonical wire")


__all__: tuple[str, ...] = ()
