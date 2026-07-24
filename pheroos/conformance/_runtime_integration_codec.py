"""Strict canonical helpers for Runtime Integration transcript v1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import base64
import binascii
from hashlib import sha256
import json
import math
import re
from typing import Any
import unicodedata

from pheroos._unicode import contains_surrogate_code_point


RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1 = (
    "pheroos-runtime-integration-transcript-request-v1"
)
RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1 = (
    "pheroos-runtime-integration-transcript-result-v1"
)
RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1 = (
    "pheroos-runtime-integration-transcript-step-v1"
)
RUNTIME_INTEGRATION_CONTROL_VERSION_V1 = "pheroos-runtime-integration-control-v1"
RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1 = (
    "pheroos-runtime-integration-commit-observation-v1"
)
RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1 = (
    "pheroos-runtime-integration-conformance-v1"
)
RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1 = 4_194_304

_ROOT = re.compile(r"^sha256:[0-9a-f]{64}$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000


class RuntimeIntegrationTranscriptErrorV1(ValueError):
    """A transcript is malformed, unbound, or uses an unsupported version."""


def text_value(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise RuntimeIntegrationTranscriptErrorV1(f"{label} must be text")
    if (
        (not value and not allow_empty)
        or value != value.strip()
        or "\x00" in value
        or contains_surrogate_code_point(value)
        or len(value) > 1024
        or unicodedata.normalize("NFC", value) != value
    ):
        raise RuntimeIntegrationTranscriptErrorV1(f"{label} is not canonical text")
    return value


def root_value(value: object, label: str, *, allow_empty: bool = False) -> str:
    if value == "" and allow_empty:
        return ""
    if type(value) is not str or _ROOT.fullmatch(value) is None:
        raise RuntimeIntegrationTranscriptErrorV1(f"{label} must be canonical sha256")
    return value


def exact_mapping(
    payload: object,
    fields: set[str] | frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    if (
        type(payload) is not dict
        or any(type(key) is not str for key in payload)
        or set(payload) != set(fields)
    ):
        raise RuntimeIntegrationTranscriptErrorV1(f"{label} fields are invalid")
    return payload


def canonical_bytes(payload: Mapping[str, object]) -> bytes:
    _portable_json(payload)
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript is not portable canonical JSON"
        ) from exc
    if len(encoded) > RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript exceeds its wire size bound"
        )
    return encoded


def checkpoint_to_wire(checkpoint: bytes) -> str:
    """Encode opaque Store checkpoint bytes without prescribing their format."""

    if (
        type(checkpoint) is not bytes
        or not checkpoint
        or len(checkpoint) > RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1
    ):
        raise RuntimeIntegrationTranscriptErrorV1("driver checkpoint bytes are invalid")
    return base64.urlsafe_b64encode(checkpoint).decode("ascii")


def checkpoint_from_wire(value: object) -> bytes:
    """Decode exact canonical base64url checkpoint bytes."""

    if (
        type(value) is not str
        or not value
        or len(value) > (RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1 * 4 // 3 + 4)
        or _BASE64URL.fullmatch(value) is None
    ):
        raise RuntimeIntegrationTranscriptErrorV1("driver checkpoint wire is invalid")
    try:
        decoded = base64.b64decode(value, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeIntegrationTranscriptErrorV1(
            "driver checkpoint wire is invalid"
        ) from exc
    if checkpoint_to_wire(decoded) != value:
        raise RuntimeIntegrationTranscriptErrorV1(
            "driver checkpoint wire is not canonical"
        )
    return decoded


def _portable_json(value: object) -> None:
    nodes = 0
    stack: list[tuple[object, int, str]] = [(value, 0, "$")]
    while stack:
        item, depth, path = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript JSON exceeds its resource bound"
            )
        stack.extend(_portable_json_children(item, depth, path))


def _portable_json_children(
    item: object,
    depth: int,
    path: str,
) -> tuple[tuple[object, int, str], ...]:
    if item is None or type(item) in {bool, int}:
        return ()
    if type(item) is float:
        _validate_portable_number(item, path)
        return ()
    if type(item) is str:
        _validate_portable_text(item, path, "text")
        return ()
    if type(item) is list:
        return tuple(
            (child, depth + 1, f"{path}[{index}]") for index, child in enumerate(item)
        )
    if type(item) is dict:
        return _portable_mapping_children(item, depth, path)
    raise RuntimeIntegrationTranscriptErrorV1(
        f"{path} contains unsupported type {type(item).__name__}"
    )


def _validate_portable_number(item: float, path: str) -> None:
    if not math.isfinite(item) or (item == 0.0 and str(item).startswith("-")):
        raise RuntimeIntegrationTranscriptErrorV1(
            f"{path} contains a noncanonical number"
        )


def _validate_portable_text(item: str, path: str, label: str) -> None:
    if (
        "\x00" in item
        or contains_surrogate_code_point(item)
        or unicodedata.normalize("NFC", item) != item
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            f"{path} contains noncanonical {label}"
        )


def _portable_mapping_children(
    item: dict[object, object],
    depth: int,
    path: str,
) -> tuple[tuple[object, int, str], ...]:
    children: list[tuple[object, int, str]] = []
    for key, child in item.items():
        if type(key) is not str or not key:
            raise RuntimeIntegrationTranscriptErrorV1(
                f"{path} contains a noncanonical key"
            )
        _validate_portable_text(key, path, "key")
        children.append((child, depth + 1, f"{path}.{key}"))
    return tuple(children)


def document_root(kind: str, payload: Mapping[str, object]) -> str:
    text_value(kind, "runtime transcript root kind")
    prefix = b"pheroos-runtime-integration-v1\x00" + kind.encode("ascii") + b"\x00"
    return "sha256:" + sha256(prefix + canonical_bytes(payload)).hexdigest()


def collection_root(kind: str, values: Sequence[str]) -> str:
    for item in values:
        root_value(item, f"{kind} member root")
    return document_root(kind, {"roots": list(values)})


__all__ = [
    "RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1",
    "RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1",
    "RUNTIME_INTEGRATION_CONTROL_VERSION_V1",
    "RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1",
    "RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1",
    "RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1",
    "RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1",
    "RuntimeIntegrationTranscriptErrorV1",
    "canonical_bytes",
    "checkpoint_from_wire",
    "checkpoint_to_wire",
    "collection_root",
    "document_root",
    "exact_mapping",
    "root_value",
    "text_value",
]
