"""Canonical helpers for authority-neutral Commit Evidence v2 data."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
import json
from typing import Any, cast

from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2

MAX_COMMIT_EVIDENCE_TEXT_BYTES_V2 = 4_096
MAX_COMMIT_EVIDENCE_ROOTS_V2 = 1_024
MAX_COMMIT_EVIDENCE_RECORDS_V2 = 16_384
MAX_COMMIT_EVIDENCE_REASON_CODES_V2 = 128


def evidence_root_v2(kind: str, body: object) -> str:
    encoded = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    prefix = b"pheroos-commit-evidence-v2:" + kind.encode("ascii") + b"\x00"
    return "sha256:" + sha256(prefix + encoded).hexdigest()


def require_text_v2(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value):
        raise TypeError(f"{label} must be an exact string")
    result = value
    if "\x00" in result or result != result.strip():
        raise ValueError(f"{label} is not canonical text")
    if len(result.encode("utf-8")) > MAX_COMMIT_EVIDENCE_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds its text bound")
    return result


def require_root_v2(value: object, label: str, *, allow_empty: bool = False) -> str:
    result = require_text_v2(value, label, allow_empty=allow_empty)
    if allow_empty and not result:
        return result
    if (
        len(result) != 71
        or not result.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in result[7:])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 root")
    return result


def require_count_v2(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} is outside its integer bound")
    return value


def canonical_texts_v2(
    values: Sequence[str],
    label: str,
    *,
    limit: int,
    allow_empty: bool,
) -> tuple[str, ...]:
    if type(values) not in (list, tuple) or len(values) > limit:
        raise TypeError(f"{label} must be a bounded exact array or tuple")
    result = tuple(require_text_v2(item, label) for item in values)
    if not allow_empty and not result:
        raise ValueError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return tuple(sorted(result, key=lambda item: item.encode("utf-8")))


def canonical_roots_v2(
    values: Sequence[str],
    label: str,
    *,
    limit: int = MAX_COMMIT_EVIDENCE_ROOTS_V2,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if type(values) not in (list, tuple) or len(values) > limit:
        raise TypeError(f"{label} must be a bounded exact array or tuple")
    roots = tuple(require_root_v2(item, label) for item in values)
    if not allow_empty and not roots:
        raise ValueError(f"{label} must not be empty")
    if len(roots) != len(set(roots)):
        raise ValueError(f"{label} contains duplicates")
    return tuple(sorted(roots))


def exact_object_v2(
    value: object, fields: frozenset[str], label: str
) -> dict[str, Any]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    result = cast(dict[str, Any], value).copy()
    if any(type(key) is not str for key in result) or set(result) != fields:
        raise ValueError(f"{label} fields are invalid")
    return result


def exact_array_v2(value: object, label: str, *, limit: int) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"{label} must be an exact array")
    result = cast(list[object], value)
    if len(result) > limit:
        raise ValueError(f"{label} exceeds its item bound")
    return result


def require_canonical_wire_v2(
    supplied: object, canonical: dict[str, object], label: str
) -> None:
    if type(supplied) is not dict or supplied != canonical:
        raise ValueError(f"{label} is not canonical wire")


__all__: tuple[str, ...] = ()
