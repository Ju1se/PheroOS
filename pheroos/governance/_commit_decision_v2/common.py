"""Canonical and resource primitives for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from types import MappingProxyType
from typing import cast

from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2


MAX_COMMIT_DECISION_TEXT_BYTES_V2 = 4_096
MAX_COMMIT_DECISION_ITEMS_V2 = 4_096
MAX_COMMIT_DECISION_RESOURCE_DEPTH_V2 = 24
MAX_COMMIT_DECISION_RESOURCE_NODES_V2 = 65_536
MAX_COMMIT_DECISION_RESOURCE_TEXT_BYTES_V2 = 4 * 1024 * 1024
MAX_COMMIT_DECISION_SNAPSHOT_BYTES_V2 = 8 * 1024 * 1024

COMMIT_DECISION_CANONICAL_VERSION_V2 = "pheroos-authority-canonical-v2"
COMMIT_DECISION_DEPENDENCY_SCHEMA_V2 = "pheroos-commit-decision-dependency-v2"
COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2 = (
    "pheroos-commit-decision-evidence-proposal-v2"
)
COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2 = (
    "pheroos-commit-decision-candidate-proposal-v2"
)
COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2 = "pheroos-commit-decision-output-proposal-v2"
COMMIT_DECISION_ASSESSMENT_SCHEMA_V2 = "pheroos-commit-assessment-v2"
COMMIT_DECISION_WINDOW_SCHEMA_V2 = "pheroos-commit-window-v2"
COMMIT_DECISION_SEAL_SCHEMA_V2 = "pheroos-commit-window-seal-v2"
COMMIT_DECISION_PROGRESS_SCHEMA_V2 = "pheroos-commit-decision-progress-v2"
COMMIT_DECISION_OUTCOME_SCHEMA_V2 = "pheroos-commit-decision-outcome-v2"
COMMIT_DECISION_SNAPSHOT_SCHEMA_V2 = "pheroos-commit-decision-snapshot-v2"
COMMIT_DECISION_REQUEST_SCHEMA_V2 = "pheroos-commit-decision-request-v2"
COMMIT_DECISION_STATE_SCHEMA_V2 = "pheroos-commit-decision-state-v2"


def _canonical_bytes(value: object) -> bytes:
    _preflight_resource(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _root(kind: str, body: object) -> str:
    digest = sha256(
        b"pheroos-commit-decision-v2:"
        + kind.encode("ascii")
        + b"\x00"
        + _canonical_bytes(body)
    ).hexdigest()
    return f"sha256:{digest}"


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value):
        raise TypeError(f"{label} must be an exact string")
    result = value
    if "\x00" in result:
        raise ValueError(f"{label} contains U+0000")
    try:
        encoded = result.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must encode as UTF-8") from exc
    if len(encoded) > MAX_COMMIT_DECISION_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds the Commit Decision v2 text bound")
    return result


def _require_root(value: object, label: str, *, allow_empty: bool = False) -> str:
    result = _require_text(value, label, allow_empty=allow_empty)
    if result or not allow_empty:
        if len(result) != 71 or not result.startswith("sha256:"):
            raise ValueError(f"{label} must be a lowercase sha256 root")
        if any(char not in "0123456789abcdef" for char in result[7:]):
            raise ValueError(f"{label} must be a lowercase sha256 root")
    return result


def _require_count(
    value: object, label: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    upper = MAX_AUTHORITY_REVISION_V2 if maximum is None else maximum
    if type(value) is not int or not minimum <= (value) <= upper:
        raise ValueError(f"{label} is outside its integer bound")
    return value


def _saturating_future_step(start: object, distance: object, label: str) -> int:
    """Add a positive logical distance without leaving the canonical range.

    Saturation is part of the Decision ABI, not an accidental consequence of
    a later dataclass validator.  The terminal canonical step itself cannot
    initialize a future deadline and therefore fails with one explicit error.
    """

    current = _require_count(start, f"{label} start")
    delta = _require_count(distance, f"{label} distance", minimum=1)
    if current == MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} has no representable future step")
    return min(MAX_AUTHORITY_REVISION_V2, current + delta)


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must be an exact bool")
    return value


def _exact_mapping(
    value: object, fields: frozenset[str], label: str
) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    result = cast(dict[str, object], value).copy()
    if any(type(key) is not str for key in result) or set(result) != fields:
        raise ValueError(f"{label} fields are invalid")
    return result


def _exact_array(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"{label} must be an exact array")
    result = cast(list[object], value)
    if len(result) > MAX_COMMIT_DECISION_ITEMS_V2:
        raise ValueError(f"{label} exceeds its item bound")
    return result


def _canonical_texts(
    values: Sequence[str], label: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    if len(values) > MAX_COMMIT_DECISION_ITEMS_V2:
        raise ValueError(f"{label} exceeds its item bound")
    result = tuple(_require_text(item, label) for item in values)
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique values")
    return tuple(sorted(result, key=lambda item: item.encode("utf-8")))


def _canonical_roots(
    values: Sequence[str], label: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    if len(values) > MAX_COMMIT_DECISION_ITEMS_V2:
        raise ValueError(f"{label} exceeds its item bound")
    result = tuple(_require_root(item, label) for item in values)
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique roots")
    return tuple(sorted(result))


def _install_root(
    instance: object, attribute: str, supplied: object, kind: str, body: object
) -> None:
    expected = _root(kind, body)
    if supplied not in ("", expected):
        raise ValueError(f"{attribute} is mismatched")
    object.__setattr__(instance, attribute, expected)


def _require_canonical_wire(
    supplied: object, canonical: dict[str, object], label: str
) -> None:
    if type(supplied) is not dict or supplied != canonical:
        raise ValueError(f"{label} is not canonical wire")


def _freeze_json(value: object, path: str = "$") -> object:
    _preflight_resource(value)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is list or type(value) is tuple:
        return tuple(
            _freeze_json(item, f"{path}[]") for item in cast(Sequence[object], value)
        )
    if type(value) is dict or type(value) is MappingProxyType:
        mapping = cast(Mapping[str, object], value)
        if any(type(key) is not str for key in mapping):
            raise TypeError(f"{path} contains a non-string key")
        return MappingProxyType(
            {
                key: _freeze_json(mapping[key], f"{path}.{key}")
                for key in sorted(mapping, key=lambda item: item.encode("utf-8"))
            }
        )
    raise TypeError(f"{path} contains a non-portable value")


def _portable_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _portable_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_portable_json(item) for item in value]
    return value


def _preflight_resource(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    text_bytes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_COMMIT_DECISION_RESOURCE_NODES_V2:
            raise ValueError("Commit Decision v2 resource exceeds its node bound")
        if depth > MAX_COMMIT_DECISION_RESOURCE_DEPTH_V2:
            raise ValueError("Commit Decision v2 resource exceeds its depth bound")
        increment, children = _resource_node(current, depth)
        text_bytes += increment
        stack.extend(children)
        if text_bytes > MAX_COMMIT_DECISION_RESOURCE_TEXT_BYTES_V2:
            raise ValueError("Commit Decision v2 resource exceeds its text-byte bound")


def _resource_node(value: object, depth: int) -> tuple[int, list[tuple[object, int]]]:
    if value is None or type(value) in (bool, int):
        return 0, []
    if type(value) is str:
        text = _require_text(
            value, "Commit Decision v2 resource text", allow_empty=True
        )
        return len(text.encode("utf-8")), []
    if type(value) in (list, tuple):
        return 0, [(item, depth + 1) for item in cast(Sequence[object], value)]
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        if any(type(key) is not str for key in mapping):
            raise TypeError("Commit Decision v2 resource contains a non-string key")
        text_bytes = sum(
            len(_require_text(key, "Commit Decision v2 resource key").encode("utf-8"))
            for key in mapping
        )
        return text_bytes, [(item, depth + 1) for item in mapping.values()]
    raise TypeError("Commit Decision v2 resource contains a non-portable value")


__all__: tuple[str, ...] = ()
