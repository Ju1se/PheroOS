"""Canonical value helpers for the scoped Trace store ABI."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from copy import deepcopy
from hashlib import sha256
from typing import Any, Mapping

from pheroos._unicode import contains_surrogate_code_point
from pheroos.trace.scoped import ScopedTraceEvent

_ROOT = re.compile(r"^sha256:[0-9a-f]{64}$")


def _text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
        or contains_surrogate_code_point(value)
        or unicodedata.normalize("NFC", value) != value
    ):
        raise ValueError(f"{name} must be canonical nonblank text")
    return value


def _root(value: object, name: str) -> str:
    if type(value) is not str or not _ROOT.fullmatch(value):
        raise ValueError(f"{name} must be canonical sha256")
    return value


def _integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _computed_root(value: object, computed: str, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be canonical text")
    if value and value != computed:
        raise ValueError(f"{name} does not match its payload")
    return computed


def _portable(value: object, path: str = "payload") -> None:
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is str:
        if (
            "\x00" in value
            or contains_surrogate_code_point(value)
            or unicodedata.normalize("NFC", value) != value
        ):
            raise ValueError(f"{path} must be canonical nonblank text")
        return
    if type(value) is float:
        if math.isfinite(value):
            return
        raise ValueError(f"{path} contains a nonfinite number")
    if type(value) is list:
        _portable_list(value, path=path)
        return
    if type(value) is dict:
        _portable_mapping(value, path=path)
        return
    raise ValueError(f"{path} contains a non-portable value")


def _portable_list(value: list[object], *, path: str) -> None:
    for index, item in enumerate(value):
        _portable(item, f"{path}[{index}]")


def _portable_mapping(value: dict[object, object], *, path: str) -> None:
    for key, item in value.items():
        if type(key) is not str:
            raise ValueError(f"{path} contains a non-text key")
        if (
            not key
            or "\x00" in key
            or contains_surrogate_code_point(key)
            or unicodedata.normalize("NFC", key) != key
        ):
            raise ValueError(f"{path} keys must be canonical nonblank text")
        _portable(item, f"{path}.{key}")


def _closed(payload: object, fields: frozenset[str], name: str) -> Mapping[str, Any]:
    if type(payload) is not dict or set(payload) != fields:
        raise ValueError(f"{name} fields are invalid")
    _portable(payload, name)
    return payload


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _canonical_event(event: ScopedTraceEvent) -> ScopedTraceEvent:
    if not isinstance(event, ScopedTraceEvent):
        raise TypeError("scoped trace append requires ScopedTraceEvent v1")
    portable = event.to_dict()
    _portable(portable, "scoped_trace_event")
    canonical = ScopedTraceEvent.from_dict(deepcopy(portable))
    _text(canonical.stream, "scoped trace stream")
    _text(canonical.trace_id, "scoped trace trace_id")
    _text(canonical.transition_id, "scoped trace transition_id")
    return canonical


__all__ = [
    "_canonical_event",
    "_closed",
    "_computed_root",
    "_digest",
    "_integer",
    "_portable",
    "_root",
    "_text",
]
