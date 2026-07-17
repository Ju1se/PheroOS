from __future__ import annotations

from collections.abc import Sequence
import unicodedata

from pheroos._digest import is_canonical_sha256_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    MAX_AUTHORITY_INTEGER,
    SUPPORTED_COMMIT_PROFILES,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import (
    CommitWireError,
    canonical_commit_set,
)


def require_commit_text(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value != unicodedata.normalize("NFC", value)
    ):
        raise GovernanceError(
            f"{field_name} must be a non-blank NFC string without surrounding whitespace"
        )
    return value


def require_commit_step(value: object, field_name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_AUTHORITY_INTEGER
    ):
        raise GovernanceError(
            f"{field_name} must be a non-negative authority-bounded integer"
        )
    return value


def require_commit_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise GovernanceError(f"{field_name} must be a boolean")
    return value


def require_commit_assurance(
    value: object,
    field_name: str,
) -> CommitAssurance:
    if type(value) is not CommitAssurance:
        raise GovernanceError(f"{field_name} is not a supported commit assurance")
    return value


def require_commit_profile(value: object, field_name: str) -> str:
    text = require_commit_text(value, field_name)
    if type(text) is not str or text not in SUPPORTED_COMMIT_PROFILES:
        raise GovernanceError(f"{field_name} is not a supported commit profile")
    return text


def require_commit_fingerprint(value: object, field_name: str) -> str:
    text = require_commit_text(value, field_name)
    if not is_canonical_sha256_fingerprint(text):
        raise GovernanceError(
            f"{field_name} must be a lowercase sha256 authority fingerprint"
        )
    return text


def require_commit_labels(
    values: object,
    field_name: str,
    *,
    allow_empty: bool = False,
    ordered: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(
        values,
        (str, bytes, bytearray),
    ):
        raise GovernanceError(f"{field_name} must be a sequence")
    labels: list[str] = []
    for value in values:
        label = require_commit_text(value, field_name)
        if label in labels:
            raise GovernanceError(f"{field_name} contains a duplicate value: {label}")
        labels.append(label)
    if not labels and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    if ordered:
        return tuple(labels)
    try:
        return tuple(canonical_commit_set(labels))
    except CommitWireError as exc:  # duplicate check above keeps detail local
        raise GovernanceError(str(exc)) from exc


def require_fresh_interval(
    *,
    issued_at_step: object,
    expires_at_step: object,
    current_step: object,
    field_name: str,
) -> tuple[int, int, int]:
    issued = require_commit_step(issued_at_step, f"{field_name} issued_at_step")
    expires = require_commit_step(expires_at_step, f"{field_name} expires_at_step")
    current = require_commit_step(current_step, f"{field_name} current_step")
    if expires <= issued:
        raise GovernanceError(f"{field_name} expiry must be after issuance")
    if current < issued or current >= expires:
        raise GovernanceError(f"{field_name} is not fresh at the current step")
    return issued, expires, current


__all__ = [
    "require_commit_assurance",
    "require_commit_bool",
    "require_commit_fingerprint",
    "require_commit_labels",
    "require_commit_profile",
    "require_commit_step",
    "require_commit_text",
    "require_fresh_interval",
]
