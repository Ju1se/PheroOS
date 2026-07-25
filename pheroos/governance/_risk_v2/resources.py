"""Portable resource limits and canonical helpers for Risk v2 contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
    _require_text,
)


MAX_RISK_INPUT_ROOTS_V2 = 1024
MAX_RISK_SOURCE_TRACE_ROOTS_V2 = 1024
MAX_RISK_RATIONALE_CODES_V2 = 128
MAX_RISK_THRESHOLD_LABELS_V2 = 128
MAX_RISK_TEXT_BYTES_V2 = 4096
MAX_RISK_SNAPSHOT_BYTES_V2 = 2 * 1024 * 1024
MAX_RISK_RESOURCE_DEPTH_V2 = 64
MAX_RISK_RESOURCE_NODES_V2 = 262_144
MAX_RISK_RESOURCE_TEXT_BYTES_V2 = 12 * 1024 * 1024


def _root(kind: str, body: object) -> str:
    return _compute_root(f"risk-v2:{kind}", body)


@dataclass(slots=True)
class _ResourceUsageV2:
    nodes: int = 0
    text_bytes: int = 0


def _preflight_portable_resources_v2(value: object) -> None:
    """Bound hostile portable trees before recursive decoding or hashing."""

    usage = _ResourceUsageV2()
    _walk_portable_resource_v2(
        value,
        depth=0,
        active_containers=set(),
        usage=usage,
    )


def _walk_portable_resource_v2(
    value: object,
    *,
    depth: int,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    if depth > MAX_RISK_RESOURCE_DEPTH_V2:
        raise ValueError("risk v2 portable input exceeds its depth bound")
    usage.nodes += 1
    if usage.nodes > MAX_RISK_RESOURCE_NODES_V2:
        raise ValueError("risk v2 portable input exceeds its node bound")
    if type(value) is str:
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError("risk v2 portable text must be valid UTF-8") from exc
        usage.text_bytes += size
        if usage.text_bytes > MAX_RISK_RESOURCE_TEXT_BYTES_V2:
            raise ValueError("risk v2 aggregate text exceeds its resource bound")
        return
    if isinstance(value, Mapping):
        _walk_portable_mapping_v2(
            value,
            depth=depth,
            active_containers=active_containers,
            usage=usage,
        )
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        _walk_portable_sequence_v2(
            value,
            depth=depth,
            active_containers=active_containers,
            usage=usage,
        )


def _walk_portable_mapping_v2(
    value: Mapping[object, object],
    *,
    depth: int,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    identity = id(value)
    if identity in active_containers:
        raise ValueError("risk v2 portable input contains a cycle")
    active_containers.add(identity)
    try:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("risk v2 portable object keys must be exact text")
            _walk_portable_resource_v2(
                key,
                depth=depth + 1,
                active_containers=active_containers,
                usage=usage,
            )
            _walk_portable_resource_v2(
                item,
                depth=depth + 1,
                active_containers=active_containers,
                usage=usage,
            )
    finally:
        active_containers.remove(identity)


def _walk_portable_sequence_v2(
    value: Sequence[object],
    *,
    depth: int,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    identity = id(value)
    if identity in active_containers:
        raise ValueError("risk v2 portable input contains a cycle")
    active_containers.add(identity)
    try:
        for item in value:
            _walk_portable_resource_v2(
                item,
                depth=depth + 1,
                active_containers=active_containers,
                usage=usage,
            )
    finally:
        active_containers.remove(identity)


def _require_bounded_text(
    value: object, label: str, *, allow_empty: bool = False
) -> str:
    if allow_empty and type(value) is str and value == "":
        return ""
    text = _require_text(value, label)
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8") from exc
    if size > MAX_RISK_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds the Risk v2 text bound")
    return text


def _require_count(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} is outside the authority integer bound")
    return value


def _require_exact_mapping(
    value: object, fields: frozenset[str], label: str
) -> dict[str, object]:
    _preflight_portable_resources_v2(value)
    _require_exact_json_wire_v2(value, label)
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact JSON object")
    result = cast(dict[str, object], value).copy()
    if any(type(key) is not str for key in result) or set(result) != fields:
        raise ValueError(f"{label} fields are invalid")
    return result


def _require_exact_json_wire_v2(value: object, label: str) -> None:
    """Reject Python containers that cannot be produced by exact JSON decode."""

    if type(value) is dict:
        for key, item in cast(dict[object, object], value).items():
            if type(key) is not str:
                raise TypeError(f"{label} object keys must be exact text")
            _require_exact_json_wire_v2(item, label)
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _require_exact_json_wire_v2(item, label)
        return
    if value is None or type(value) in (str, bool, int, float):
        return
    raise TypeError(f"{label} contains a non-JSON wire value")


def _require_canonical_wire_v2(
    payload: object,
    canonical: dict[str, object],
    label: str,
) -> None:
    """Require wire input to equal its canonical re-encoding exactly."""

    if type(payload) is not dict or payload != canonical:
        raise ValueError(f"{label} is not canonical wire")


def _require_exact_version(value: object, expected: str, label: str) -> None:
    if type(value) is not str or value != expected:
        raise ValueError(f"{label} is unsupported")


def _install_exact_root(
    instance: object,
    attribute: str,
    supplied: object,
    kind: str,
    body: object,
) -> None:
    expected = _root(kind, body)
    if supplied not in ("", expected):
        raise ValueError(f"{attribute} is mismatched")
    object.__setattr__(instance, attribute, expected)


def _canonical_texts(
    values: object,
    label: str,
    *,
    limit: int,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(
        values, (str, bytes, bytearray, memoryview)
    ):
        raise TypeError(f"{label} must be an array")
    if len(values) > limit:
        raise ValueError(f"{label} count exceeds its bound")
    result = tuple(_require_bounded_text(item, label) for item in values)
    if not result and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains a duplicate")
    return tuple(sorted(result, key=lambda item: item.encode("utf-8")))


def _canonical_roots(
    values: object,
    label: str,
    *,
    limit: int = MAX_RISK_INPUT_ROOTS_V2,
) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(
        values, (str, bytes, bytearray, memoryview)
    ):
        raise TypeError(f"{label} must be an array")
    if not 1 <= len(values) <= limit:
        raise ValueError(f"{label} count is outside its bound")
    roots = tuple(values)
    for root in roots:
        _require_root(root, label)
    if len(roots) != len(set(roots)):
        raise ValueError(f"{label} contains a duplicate")
    return tuple(
        sorted(cast(tuple[str, ...], roots), key=lambda item: item.encode("utf-8"))
    )
