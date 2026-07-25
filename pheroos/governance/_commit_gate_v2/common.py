"""Shared canonical primitives for durable Commit Gate v2 authority."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from typing import cast

from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE, CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
)


MAX_COMMIT_GATE_TEXT_BYTES_V2 = 4096
MAX_COMMIT_GATE_ITEMS_V2 = 4096
MAX_COMMIT_GATE_SNAPSHOT_BYTES_V2 = 4 * 1024 * 1024

COMMIT_STOP_SNAPSHOT_SCHEMA_V2 = "pheroos-commit-stop-snapshot-v2"
COMMIT_STOP_REQUEST_SCHEMA_V2 = "pheroos-commit-stop-request-v2"
COMMIT_STOP_STATE_SCHEMA_V2 = "pheroos-commit-stop-state-v2"
COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2 = "pheroos-commit-permission-snapshot-v2"
COMMIT_PERMISSION_REQUEST_SCHEMA_V2 = "pheroos-commit-permission-request-v2"
COMMIT_PERMISSION_STATE_SCHEMA_V2 = "pheroos-commit-permission-state-v2"
COMMIT_GATE_DEPENDENCIES_SCHEMA_V2 = "pheroos-commit-gate-dependencies-v2"

COMMIT_STOP_POLICY_VERSION_V2 = "pheroos-commit-stop-policy-v2"
COMMIT_PERMISSION_POLICY_VERSION_V2 = "pheroos-commit-permission-policy-v2"
COMMIT_GATE_CONTEXT_VERSION_V2 = "pheroos-commit-gate-context-v2"


def _root(kind: str, body: object) -> str:
    value: object = _compute_root(f"commit-gate-v2:{kind}", body)
    if type(value) is not str:
        raise TypeError("commit gate root helper returned a non-string value")
    return value


COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "stop-genesis-parent", {"schema": COMMIT_STOP_SNAPSHOT_SCHEMA_V2}
)
COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "permission-genesis-parent", {"schema": COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2}
)
COMMIT_GATE_GENESIS_TRANSITION_ID_V2 = "genesis"


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value):
        raise TypeError(f"{label} must be an exact non-empty string")
    result = value
    try:
        encoded = result.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must encode as UTF-8") from exc
    if len(encoded) > MAX_COMMIT_GATE_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds the Commit Gate v2 text bound")
    return result


def _require_count(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} is outside the authority integer bound")
    return value


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must be an exact bool")
    return value


def _require_exact_mapping(
    value: object, fields: frozenset[str], label: str
) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    result = cast(dict[str, object], value).copy()
    if any(type(key) is not str for key in result) or set(result) != fields:
        raise ValueError(f"{label} fields are invalid")
    return result


def _require_exact_array(
    value: object, label: str, *, maximum: int = MAX_COMMIT_GATE_ITEMS_V2
) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"{label} must be an exact array")
    result = cast(list[object], value)
    if len(result) > maximum:
        raise ValueError(f"{label} exceeds its item bound")
    return result


def _canonical_texts(
    value: Sequence[str],
    label: str,
    *,
    allow_empty: bool,
    maximum: int = MAX_COMMIT_GATE_ITEMS_V2,
) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds its item bound")
    result = tuple(_require_text(item, label) for item in value)
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique values")
    return tuple(sorted(result, key=lambda item: item.encode("utf-8")))


def _canonical_roots(
    value: Sequence[str],
    label: str,
    *,
    allow_empty: bool,
    maximum: int = MAX_COMMIT_GATE_ITEMS_V2,
) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds its item bound")
    result = tuple(_require_root(item, label) for item in value)
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique roots")
    return tuple(sorted(result, key=lambda item: item.encode("utf-8")))


def _install_root(
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


def _require_canonical_wire(
    supplied: object, canonical: dict[str, object], label: str
) -> None:
    if type(supplied) is not dict or supplied != canonical:
        raise ValueError(f"{label} is not canonical wire")


def _require_profile(profile: object, assurance: object, label: str) -> None:
    _require_text(profile, f"{label} profile")
    if type(assurance) is not CommitAssurance:
        raise TypeError(f"{label} assurance is invalid")
    if cast(str, profile) not in COMMIT_PROFILES_BY_ASSURANCE.get(
        (assurance).value, frozenset()
    ):
        raise ValueError(f"{label} profile and assurance are mismatched")


def _fixed_stream_ref(
    kind: str,
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    values = tuple(
        _require_text(value, f"commit {kind} stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    material = (*values, "commit")
    digest = sha256("\x00".join(material).encode("utf-8")).hexdigest()
    return f"authority:commit-{kind}-v2:{digest}"


def commit_stop_stream_ref_v2(
    scope_ref: str, protocol_ref: str, run_ref: str, target_ref: str
) -> str:
    return _fixed_stream_ref("stop", scope_ref, protocol_ref, run_ref, target_ref)


def commit_permission_stream_ref_v2(
    scope_ref: str, protocol_ref: str, run_ref: str, target_ref: str
) -> str:
    return _fixed_stream_ref("permission", scope_ref, protocol_ref, run_ref, target_ref)


def _transition_id(kind: str, stream_ref: str, request_ref: str) -> str:
    stream = _require_text(stream_ref, f"commit {kind} transition stream_ref")
    request = _require_text(request_ref, f"commit {kind} transition request_ref")
    digest = sha256(
        stream.encode("utf-8") + b"\x00" + request.encode("utf-8")
    ).hexdigest()
    return f"transition:commit-{kind}-v2:{digest}"


def commit_stop_transition_id_v2(stream_ref: str, resolution_ref: str) -> str:
    return _transition_id("stop", stream_ref, resolution_ref)


def commit_permission_transition_id_v2(stream_ref: str, permission_ref: str) -> str:
    return _transition_id("permission", stream_ref, permission_ref)


def _canonical_size(value: object, label: str) -> None:
    if len(_canonical_bytes(value)) > MAX_COMMIT_GATE_SNAPSHOT_BYTES_V2:
        raise ValueError(f"{label} exceeds its canonical byte bound")


__all__: tuple[str, ...] = ()
