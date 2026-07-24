"""Private foundations for the Governance StateStore v2 contract.

Dependency leaf: constants, closed enums, canonical JSON/root helpers, and
primitive validation only.  This module must not import higher Governance
contract layers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from hmac import compare_digest
from types import MappingProxyType
from typing import Any, ClassVar, cast
import unicodedata

from pheroos.governance._scoped_authority_primitives_v2 import (
    _canonical_bytes as _canonical_bytes,
    _compute_root as _compute_root,
    _install_root as _install_root,
    _require_root as _require_root,
    _require_text as _require_text,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
)


AUTHORITY_POLICY_VERSION_V2 = "pheroos-scoped-authority-policy-v2"
AUTHORITY_LOCAL_PROFILE_V2 = "pheroos-scoped-authority-local-v2"
AUTHORITY_AUTHENTICATED_PROFILE_V2 = "pheroos-scoped-authority-authenticated-v2"
AUTHORITY_WIRE_VERSION_V2 = "pheroos-authority-wire-v2"
AUTHORITY_LEDGER_VERSION_V2 = "pheroos-governance-authority-ledger-v2"
GOVERNANCE_STATE_STORE_VERSION_V2 = "pheroos-governance-state-store-v2"
GOVERNANCE_TRACE_BATCH_VERSION_V2 = "pheroos-governance-trace-batch-v2"

AUTHORITY_DOMAIN_SCHEMA_V2 = "pheroos-governance-authority-domain-v2"
GOVERNANCE_HEAD_SCHEMA_V2 = "pheroos-governance-authority-head-v2"
GOVERNANCE_STATE_SCHEMA_V2 = "pheroos-governance-authority-state-v2"
PREPARED_GOVERNANCE_TRANSITION_SCHEMA_V2 = "pheroos-governance-prepared-transition-v2"
GOVERNANCE_COMMIT_BATCH_SCHEMA_V2 = "pheroos-governance-commit-batch-v2"
GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2 = "pheroos-governance-commit-receipt-v2"
GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2 = (
    "pheroos-governance-commit-inclusion-proof-v2"
)
GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2 = "pheroos-governance-committed-transition-v2"
GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2 = (
    "pheroos-governance-commit-position-observation-v2"
)
GOVERNANCE_FAILURE_SCHEMA_V2 = "pheroos-governance-failure-v2"
GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2 = "pheroos-governance-commit-attempt-v2"
GOVERNANCE_COMMIT_VIEW_SCHEMA_V2 = "pheroos-governance-commit-view-v2"
GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2 = "pheroos-governance-domain-seal-v2"

GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2 = "authority:domain-lifecycle"
MAX_GOVERNANCE_TRACE_EVENTS_V2 = 128
MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2 = 127

_FAILURE_STAGES = frozenset(
    {
        "validation",
        "reconciliation",
        "precondition",
        "trace",
        "commit",
        "finality",
        "load",
        "seal",
    }
)
_BATCH_KINDS = frozenset({"transition", "seal"})
_DOMAIN_PROFILES = frozenset(
    {AUTHORITY_LOCAL_PROFILE_V2, AUTHORITY_AUTHENTICATED_PROFILE_V2}
)


class GovernanceCommitDispositionV2(StrEnum):
    """Closed total-result disposition with exact lowercase wire values."""

    COMMITTED = "committed"
    DENIED = "denied"
    RETRY_REQUIRED = "retry_required"
    FINALITY_UNAVAILABLE = "finality_unavailable"
    INVALID = "invalid"


class GovernanceCommitPositionV2(StrEnum):
    """Verified historical position of an included v2 transition."""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    SEALED = "sealed"


class GovernanceFailureStageV2(StrEnum):
    """Closed stage at which one typed Governance failure was observed."""

    VALIDATION = "validation"
    RECONCILIATION = "reconciliation"
    PRECONDITION = "precondition"
    TRACE = "trace"
    COMMIT = "commit"
    FINALITY = "finality"
    LOAD = "load"
    SEAL = "seal"


class _CanonicalRootRecordV2:
    __slots__ = ()
    _root_field: ClassVar[str]

    def to_dict(self) -> dict[str, object]:
        raise NotImplementedError

    def canonical_bytes(self) -> bytes:
        """Return exact canonical UTF-8 bytes for the complete wire record."""

        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        """Return the root recomputed and verified during construction."""

        return cast(str, getattr(self, self._root_field))


def _install_exact_computed(
    instance: object,
    attribute: str,
    supplied: object,
    computed: str,
    label: str,
) -> None:
    if type(supplied) is str and supplied == "":
        object.__setattr__(instance, attribute, computed)
        return
    _require_root(supplied, label)
    if not compare_digest(cast(str, supplied), computed):
        raise ValueError(f"{label} is mismatched")
    object.__setattr__(instance, attribute, computed)


def _install_optional_exact(
    instance: object,
    attribute: str,
    supplied: object,
    computed: str,
    label: str,
) -> None:
    if supplied is None:
        object.__setattr__(instance, attribute, computed)
        return
    _require_root(supplied, label)
    if not compare_digest(cast(str, supplied), computed):
        raise ValueError(f"{label} is mismatched")
    object.__setattr__(instance, attribute, computed)


def _validate_common_binding(
    *,
    canonical_version: str,
    ledger_version: str,
    domain_root: str,
    scope_ref: str,
) -> None:
    _require_exact_version(
        canonical_version,
        AUTHORITY_CANONICAL_VERSION_V2,
        "governance canonical_version",
    )
    _require_exact_version(
        ledger_version,
        AUTHORITY_LEDGER_VERSION_V2,
        "governance ledger_version",
    )
    _require_root(domain_root, "governance domain_root")
    _require_text(scope_ref, "governance scope_ref")


def _validate_nested_binding(
    value: object,
    *,
    domain_root: str,
    scope_ref: str,
    stream_ref: str | None,
    transition_id: str,
    label: str,
) -> None:
    if getattr(value, "domain_root", None) != domain_root:
        raise ValueError(f"{label} domain_root is mismatched")
    if getattr(value, "scope_ref", None) != scope_ref:
        raise ValueError(f"{label} scope_ref is mismatched")
    if stream_ref is not None and getattr(value, "stream_ref", None) != stream_ref:
        raise ValueError(f"{label} stream_ref is mismatched")
    if getattr(value, "transition_id", None) != transition_id:
        raise ValueError(f"{label} transition_id is mismatched")


def _read_precondition(
    read_set: GovernanceAuthorityReadSetV2,
    stream_ref: str,
) -> Any | None:
    return next(
        (entry for entry in read_set.entries if entry.stream_ref == stream_ref),
        None,
    )


def _require_exact_version(value: object, expected: str, label: str) -> None:
    if type(value) is not str or value != expected:
        raise ValueError(f"{label} is unsupported")


def _require_revision(value: object, label: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} must be a JSON-safe non-negative integer")
    return value


def _require_json_pointer(value: object) -> str:
    if type(value) is not str or (value and not value.startswith("/")):
        raise ValueError("governance failure path must be an RFC 6901 JSON pointer")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("governance failure path must already use Unicode NFC")
    for token in value.split("/")[1:]:
        index = 0
        decoded = ""
        while index < len(token):
            if token[index] == "~":
                if index + 1 >= len(token) or token[index + 1] not in "01":
                    raise ValueError(
                        "governance failure path contains invalid RFC 6901 escape"
                    )
                decoded += "~" if token[index + 1] == "0" else "/"
                index += 2
            else:
                decoded += token[index]
                index += 1
        if decoded.isdigit() and len(decoded) > 1 and decoded.startswith("0"):
            raise ValueError(
                "governance failure path array indexes must be canonical base-10"
            )
    return value


def _exact_object(
    payload: object,
    expected_fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if type(payload) is not dict:
        raise TypeError(f"{label} must be an exact JSON object")
    if set(payload) != expected_fields:
        missing = sorted(expected_fields - set(payload))
        unknown = sorted(set(payload) - expected_fields)
        raise ValueError(
            f"{label} fields invalid: missing={missing}, unknown={unknown}"
        )
    for key, value in payload.items():
        if key.endswith("_root") and value is not None:
            _require_root(value, f"{label} {key}")
    return payload


def _freeze_json_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be a mapping")
    return cast(Mapping[str, Any], _freeze_json(value, path))


def _freeze_json(value: object, path: str) -> Any:
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        return _freeze_json_text(value, path)
    if type(value) is int:
        return _freeze_json_integer(value, path)
    if type(value) is float:
        raise TypeError(f"{path} does not permit floating-point numbers")
    if isinstance(value, Mapping):
        return _freeze_json_object(value, path)
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return _freeze_json_sequence(value, path)
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}")


def _freeze_json_text(value: str, path: str) -> str:
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{path} strings must already use Unicode NFC")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{path} strings must encode as UTF-8") from exc
    return value


def _freeze_json_integer(value: int, path: str) -> int:
    if not -(2**53 - 1) <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{path} integer exceeds canonical JSON-safe range")
    return value


def _freeze_json_object(value: Mapping[object, object], path: str) -> object:
    if any(type(key) is not str for key in value):
        raise TypeError(f"{path} keys must be strings")
    result: dict[str, Any] = {}
    for key in sorted(cast(Mapping[str, object], value)):
        normalized_key = _freeze_json_text(key, f"{path} key")
        result[normalized_key] = _freeze_json(value[key], f"{path}.{key}")
    return MappingProxyType(result)


def _freeze_json_sequence(value: Sequence[object], path: str) -> tuple[Any, ...]:
    return tuple(
        _freeze_json(item, f"{path}[{index}]") for index, item in enumerate(value)
    )


def _portable_json(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _portable_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_portable_json(item) for item in value]
    return value


def _diagnostic_from_wire(value: object) -> AuthorityDiagnosticCodeV2:
    if type(value) is not str:
        raise TypeError("governance diagnostic code must be a string")
    try:
        return AuthorityDiagnosticCodeV2(value)
    except ValueError as exc:
        raise ValueError("governance diagnostic code is unsupported") from exc


def _failure_stage_from_wire(value: object) -> GovernanceFailureStageV2:
    if type(value) is not str:
        raise TypeError("governance failure stage must be a string")
    try:
        return GovernanceFailureStageV2(value)
    except ValueError as exc:
        raise ValueError("governance failure stage is unsupported") from exc


def _disposition_from_wire(value: object) -> GovernanceCommitDispositionV2:
    if type(value) is not str:
        raise TypeError("governance commit disposition must be a string")
    try:
        return GovernanceCommitDispositionV2(value)
    except ValueError as exc:
        raise ValueError("governance commit disposition is unsupported") from exc


def _position_from_wire(value: object) -> GovernanceCommitPositionV2:
    if type(value) is not str:
        raise TypeError("governance commit position must be a string")
    try:
        return GovernanceCommitPositionV2(value)
    except ValueError as exc:
        raise ValueError("governance commit position is unsupported") from exc
