"""Shared strict wire primitives for runtime compatibility v1 documents."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any
import unicodedata


RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1 = "pheroos-runtime-compatibility-manifest-v1"
RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1 = "pheroos-runtime-compatibility-claim-v1"
RUNTIME_COMPATIBILITY_REPORT_VERSION_V1 = "pheroos-runtime-compatibility-report-v1"
RUNTIME_BASELINE_PROFILE_VERSION_V1 = "pheroos-runtime-scoped-baseline-profile-v1"
RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1 = 65_536

TEXT_MAX_LENGTH = 512
MAX_REQUIREMENTS = 256
MAX_OPTIONAL_PROFILES = 32
MAX_OPTIONAL_CAPABILITIES = 128
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MANIFEST_ROOT_PREFIX = b"pheroos-runtime-compatibility-manifest-v1\x00"
CLAIM_ROOT_PREFIX = b"pheroos-runtime-compatibility-claim-v1\x00"


class RuntimeCompatibilityErrorV1(ValueError):
    """A runtime compatibility document is malformed or noncanonical."""


def text_value(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise RuntimeCompatibilityErrorV1(f"{label} must be a string")
    if (
        not value
        or value != value.strip()
        or "\x00" in value
        or len(value) > TEXT_MAX_LENGTH
        or unicodedata.normalize("NFC", value) != value
    ):
        raise RuntimeCompatibilityErrorV1(
            f"{label} must be a bounded nonblank NFC string without NUL"
        )
    return value


def canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def document_root(prefix: bytes, payload: Mapping[str, object]) -> str:
    return "sha256:" + sha256(prefix + canonical_bytes(payload)).hexdigest()


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        text_value(key, label="runtime compatibility JSON object key")
        if key in result:
            raise RuntimeCompatibilityErrorV1(
                f"runtime compatibility JSON contains duplicate key: {key}"
            )
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise RuntimeCompatibilityErrorV1(
        f"runtime compatibility JSON contains non-finite number: {value}"
    )


def load_canonical_json(data: bytes, *, label: str) -> dict[str, Any]:
    if (
        type(data) is not bytes
        or not data
        or len(data) > RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1
    ):
        raise RuntimeCompatibilityErrorV1(f"{label} wire bytes are invalid")
    try:
        payload = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_pairs,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeCompatibilityErrorV1(f"{label} is not strict UTF-8 JSON") from exc
    if type(payload) is not dict:
        raise RuntimeCompatibilityErrorV1(f"{label} must be a JSON object")
    return payload


__all__ = [
    "CLAIM_ROOT_PREFIX",
    "DIGEST_PATTERN",
    "MANIFEST_ROOT_PREFIX",
    "MAX_OPTIONAL_CAPABILITIES",
    "MAX_OPTIONAL_PROFILES",
    "MAX_REQUIREMENTS",
    "RUNTIME_BASELINE_PROFILE_VERSION_V1",
    "RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1",
    "RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1",
    "RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1",
    "RUNTIME_COMPATIBILITY_REPORT_VERSION_V1",
    "RuntimeCompatibilityErrorV1",
    "canonical_bytes",
    "document_root",
    "load_canonical_json",
    "text_value",
]
