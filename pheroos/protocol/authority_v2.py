from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Any, NoReturn
import unicodedata


AUTHORITY_CANONICAL_VERSION_V2 = "pheroos-authority-canonical-v2"
GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2 = "pheroos-governance-authority-read-set-v2"
MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2 = 128
MAX_AUTHORITY_REVISION_V2 = (2**53) - 1

_READ_PRECONDITION_FIELDS = frozenset(
    {"stream_ref", "expected_revision", "expected_root"}
)
_READ_SET_FIELDS = frozenset({"canonical_version", "entries", "schema"})
_SHA256_ROOT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class AuthorityV2ProtocolError(ValueError):
    """An invalid scoped-authority v2 Protocol value or encoding."""


class AuthorityDiagnosticCodeV2(StrEnum):
    """Closed diagnostic namespace shared by scoped-authority v2 surfaces."""

    AUTHORITY_PROFILE_UNSUPPORTED = "authority_profile_unsupported"
    AUTHORITY_SESSION_REQUIRED = "authority_session_required"
    AUTHORITY_SESSION_STORE_MISMATCH = "authority_session_store_mismatch"
    AUTHORITY_SCOPE_MISMATCH = "authority_scope_mismatch"
    AUTHORITY_OPERATION_DENIED = "authority_operation_denied"
    AUTHORITY_BINDING_MISMATCH = "authority_binding_mismatch"
    AUTHORITY_GRANT_UNVERIFIED = "authority_grant_unverified"
    AUTHORITY_GRANT_EXPIRED = "authority_grant_expired"
    AUTHORITY_GRANT_REVOKED = "authority_grant_revoked"
    GOVERNANCE_READ_SET_INVALID = "governance_read_set_invalid"
    GOVERNANCE_READ_SET_STALE = "governance_read_set_stale"
    GOVERNANCE_TRANSITION_CONFLICT = "governance_transition_conflict"
    GOVERNANCE_DOMAIN_SEALED = "governance_domain_sealed"
    GOVERNANCE_FINALITY_UNAVAILABLE = "governance_finality_unavailable"
    GOVERNANCE_COMMITTED_TRANSITION_INVALID = "governance_committed_transition_invalid"
    GOVERNANCE_ACTION_NOT_AUTHORIZED = "governance_action_not_authorized"
    GOVERNANCE_TRACE_LINEAGE_INVALID = "governance_trace_lineage_invalid"


@dataclass(frozen=True, slots=True)
class GovernanceReadPreconditionV2:
    """One exact authority stream head required by an atomic v2 commit."""

    stream_ref: str
    expected_revision: int
    expected_root: str

    def __post_init__(self) -> None:
        _require_canonical_stream_ref(self.stream_ref)
        if (
            type(self.expected_revision) is not int
            or self.expected_revision < 0
            or self.expected_revision > MAX_AUTHORITY_REVISION_V2
        ):
            raise AuthorityV2ProtocolError(
                "authority read precondition expected_revision must be an exact "
                "JSON-safe non-negative integer"
            )
        if (
            type(self.expected_root) is not str
            or _SHA256_ROOT_PATTERN.fullmatch(self.expected_root) is None
        ):
            raise AuthorityV2ProtocolError(
                "authority read precondition expected_root must be a lowercase "
                "sha256 root"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_revision": self.expected_revision,
            "expected_root": self.expected_root,
            "stream_ref": self.stream_ref,
        }

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceReadPreconditionV2:
        value = _exact_object(
            payload,
            expected_fields=_READ_PRECONDITION_FIELDS,
            label="authority read precondition",
        )
        return cls(
            stream_ref=value["stream_ref"],
            expected_revision=value["expected_revision"],
            expected_root=value["expected_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceAuthorityReadSetV2:
    """Complete, canonical authority head snapshot for one atomic commit."""

    entries: tuple[GovernanceReadPreconditionV2, ...]
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    schema: str = GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2

    def __post_init__(self) -> None:
        if (
            type(self.canonical_version) is not str
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise AuthorityV2ProtocolError(
                "authority read-set canonical_version is unsupported"
            )
        if (
            type(self.schema) is not str
            or self.schema != GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2
        ):
            raise AuthorityV2ProtocolError("authority read-set schema is unsupported")
        if type(self.entries) is not tuple:
            raise AuthorityV2ProtocolError(
                "authority read-set entries must be an immutable tuple"
            )
        if not 1 <= len(self.entries) <= MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2:
            raise AuthorityV2ProtocolError(
                "authority read-set must contain from 1 through 128 entries"
            )
        if any(type(item) is not GovernanceReadPreconditionV2 for item in self.entries):
            raise AuthorityV2ProtocolError(
                "authority read-set entries must be read preconditions"
            )
        stream_keys = tuple(item.stream_ref.encode("utf-8") for item in self.entries)
        if len(set(stream_keys)) != len(stream_keys):
            raise AuthorityV2ProtocolError(
                "authority read-set stream_ref values must be unique"
            )
        if stream_keys != tuple(sorted(stream_keys)):
            raise AuthorityV2ProtocolError(
                "authority read-set entries must use unsigned UTF-8 stream_ref order"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "canonical_version": self.canonical_version,
            "entries": [item.to_dict() for item in self.entries],
            "schema": self.schema,
        }

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceAuthorityReadSetV2:
        value = _exact_object(
            payload,
            expected_fields=_READ_SET_FIELDS,
            label="authority read-set",
        )
        entries = value["entries"]
        if type(entries) is not list:
            raise AuthorityV2ProtocolError(
                "authority read-set entries must be a JSON array"
            )
        return cls(
            entries=tuple(
                GovernanceReadPreconditionV2.from_dict(item) for item in entries
            ),
            canonical_version=value["canonical_version"],
            schema=value["schema"],
        )

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def root(self) -> str:
        return "sha256:" + sha256(self.canonical_bytes()).hexdigest()


def loads_governance_authority_read_set_v2(
    value: str | bytes | bytearray,
) -> GovernanceAuthorityReadSetV2:
    """Strictly decode one authority v2 read-set JSON document."""

    text = _require_utf8_json_text(value)
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_number,
            parse_float=_reject_json_number,
        )
    except AuthorityV2ProtocolError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuthorityV2ProtocolError("authority read-set JSON is invalid") from exc
    return GovernanceAuthorityReadSetV2.from_dict(payload)


def _exact_object(
    value: object,
    *,
    expected_fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AuthorityV2ProtocolError(f"{label} must be an exact JSON object")
    if set(value) != expected_fields:
        missing = sorted(expected_fields - set(value))
        unknown = sorted(set(value) - expected_fields)
        raise AuthorityV2ProtocolError(
            f"{label} fields are invalid: missing={missing}, unknown={unknown}"
        )
    return value


def _require_canonical_stream_ref(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise AuthorityV2ProtocolError(
            "authority read precondition stream_ref must be a canonical "
            "non-blank string"
        )
    if unicodedata.normalize("NFC", value) != value:
        raise AuthorityV2ProtocolError(
            "authority read precondition stream_ref must already use NFC"
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AuthorityV2ProtocolError(
            "authority read precondition stream_ref must encode as UTF-8"
        ) from exc
    return value


def _require_utf8_json_text(value: object) -> str:
    if type(value) is str:
        text = value
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise AuthorityV2ProtocolError("authority read-set JSON must not use a BOM")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuthorityV2ProtocolError(
                "authority read-set JSON must use UTF-8"
            ) from exc
    else:
        raise AuthorityV2ProtocolError(
            "authority read-set JSON must be text, bytes, or bytearray"
        )
    if text.startswith("\ufeff"):
        raise AuthorityV2ProtocolError("authority read-set JSON must not use a BOM")
    return text


def _reject_duplicate_object_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if unicodedata.normalize("NFC", key) != key:
            raise AuthorityV2ProtocolError(
                "authority read-set JSON object keys must already use NFC"
            )
        if key in value:
            raise AuthorityV2ProtocolError(
                "authority read-set JSON contains a duplicate object key"
            )
        value[key] = item
    return value


def _reject_json_number(_value: str) -> NoReturn:
    raise AuthorityV2ProtocolError(
        "authority read-set JSON does not permit floating-point numbers"
    )


__all__ = [
    "AUTHORITY_CANONICAL_VERSION_V2",
    "GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2",
    "MAX_AUTHORITY_REVISION_V2",
    "MAX_GOVERNANCE_AUTHORITY_READ_SET_ENTRIES_V2",
    "AuthorityDiagnosticCodeV2",
    "AuthorityV2ProtocolError",
    "GovernanceAuthorityReadSetV2",
    "GovernanceReadPreconditionV2",
    "loads_governance_authority_read_set_v2",
]
