"""Shared deterministic primitives for scoped Governance Authority v2 records.

This private dependency leaf owns only byte/root/text mechanics whose wire and
failure semantics are identical across the StateStore and authority-session
contracts.  Bounds, object parsing, and business-specific validation remain
with their owning contracts.
"""

from __future__ import annotations

from hashlib import sha256
from hmac import compare_digest
import json
import re
from typing import cast
import unicodedata


_ROOT_PREFIX = "pheroos-governance-authority-v2:"
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _compute_root(kind: str, body: object) -> str:
    prefix = (_ROOT_PREFIX + kind).encode("utf-8")
    return "sha256:" + sha256(prefix + b"\x00" + _canonical_bytes(body)).hexdigest()


def _install_root(
    instance: object,
    attribute: str,
    supplied: object,
    kind: str,
    body: object,
) -> None:
    computed = _compute_root(kind, body)
    if type(supplied) is str and supplied == "":
        object.__setattr__(instance, attribute, computed)
        return
    _require_root(supplied, attribute)
    if not compare_digest(cast(str, supplied), computed):
        raise ValueError(f"{attribute} is mismatched")
    object.__setattr__(instance, attribute, computed)


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be canonical non-blank text")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{label} must already use Unicode NFC")
    if "\x00" in value:
        raise ValueError(f"{label} must not contain U+0000")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must encode as UTF-8") from exc
    return value


def _require_root(value: object, label: str) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase sha256 root")
    return value
