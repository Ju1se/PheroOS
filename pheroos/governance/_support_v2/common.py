"""Small resource and canonical helpers shared by durable Support v2 owners."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _require_text,
)


MAX_SUPPORT_TEXT_BYTES_V2 = 4096
MAX_SUPPORT_RESOURCE_DEPTH_V2 = 64
MAX_SUPPORT_RESOURCE_NODES_V2 = 262_144
MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2 = 12 * 1024 * 1024


@dataclass(slots=True)
class _ResourceUsageV2:
    nodes: int = 0
    text_bytes: int = 0


def _preflight_support_resources_v2(value: object) -> None:
    """Bound an exact portable tree before recursive decoding or hashing."""

    usage = _ResourceUsageV2()
    _walk_support_resource_v2(
        value,
        depth=0,
        active_containers=set(),
        usage=usage,
    )


def _walk_support_resource_v2(
    value: object,
    *,
    depth: int,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    if depth > MAX_SUPPORT_RESOURCE_DEPTH_V2:
        raise ValueError("Support v2 portable input exceeds its depth bound")
    usage.nodes += 1
    if usage.nodes > MAX_SUPPORT_RESOURCE_NODES_V2:
        raise ValueError("Support v2 portable input exceeds its node bound")
    if type(value) is str:
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError("Support v2 portable text must be valid UTF-8") from exc
        usage.text_bytes += size
        if usage.text_bytes > MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2:
            raise ValueError("Support v2 aggregate text exceeds its resource bound")
        return
    if type(value) is dict:
        _walk_support_object_v2(
            cast(dict[object, object], value),
            depth=depth,
            active_containers=active_containers,
            usage=usage,
        )
        return
    if type(value) is list:
        _walk_support_array_v2(
            cast(list[object], value),
            depth=depth,
            active_containers=active_containers,
            usage=usage,
        )
        return
    if value is None or type(value) in (bool, int, float):
        return
    raise TypeError("Support v2 portable input contains a non-JSON value")


def _walk_support_object_v2(
    value: dict[object, object],
    *,
    depth: int,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    identity = id(value)
    if identity in active_containers:
        raise ValueError("Support v2 portable input contains a cycle")
    active_containers.add(identity)
    try:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("Support v2 portable object keys must be exact text")
            for member in (key, item):
                _walk_support_resource_v2(
                    member,
                    depth=depth + 1,
                    active_containers=active_containers,
                    usage=usage,
                )
    finally:
        active_containers.remove(identity)


def _walk_support_array_v2(
    value: list[object],
    *,
    depth: int,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    identity = id(value)
    if identity in active_containers:
        raise ValueError("Support v2 portable input contains a cycle")
    active_containers.add(identity)
    try:
        for item in value:
            _walk_support_resource_v2(
                item,
                depth=depth + 1,
                active_containers=active_containers,
                usage=usage,
            )
    finally:
        active_containers.remove(identity)


def _require_bounded_text_v2(
    value: object,
    label: str,
    *,
    allow_empty: bool = False,
) -> str:
    if allow_empty and type(value) is str and value == "":
        return ""
    text = _require_text(value, label)
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8") from exc
    if size > MAX_SUPPORT_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds the Support v2 text bound")
    return text


def _require_count_v2(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} is outside the authority integer bound")
    return value


def _require_exact_mapping_v2(
    value: object,
    fields: frozenset[str],
    label: str,
) -> dict[str, object]:
    _preflight_support_resources_v2(value)
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    result = cast(dict[str, object], value).copy()
    if any(type(key) is not str for key in result) or set(result) != fields:
        raise ValueError(f"{label} fields are invalid")
    return result


def _require_exact_array_v2(
    value: object,
    label: str,
    *,
    limit: int,
) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"{label} must be an exact array")
    values = cast(list[object], value)
    if len(values) > limit:
        raise ValueError(f"{label} count exceeds its bound")
    return values


def _require_canonical_wire_v2(
    payload: object,
    canonical: dict[str, object],
    label: str,
) -> None:
    """Reject wire values that constructors would otherwise silently repair."""

    if type(payload) is not dict or payload != canonical:
        raise ValueError(f"{label} is not canonical wire")


def _canonical_utf8_order_v2(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(values, key=lambda item: item.encode("utf-8")))


__all__: tuple[str, ...] = ()
