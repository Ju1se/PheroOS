from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
import math
from typing import Any
import unicodedata

from pheroos.protocol.commit_models import (
    COMMIT_WIRE_VERSION,
    MAX_AUTHORITY_INTEGER,
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_COMMIT_PROFILES,
    SUPPORTED_TERMINAL_OUTCOMES,
    WEIGHT_SCALE,
    CommitAction,
)
from pheroos.protocol.commit_wire import (
    CommitWireError,
    canonical_commit_set,
)

AUTHORITY_PROFILE = "pheroos-commit-authority-v1"
FINGERPRINT_PATTERN = r"^sha256:[0-9a-f]{64}$"
EVIDENCE_BINDING_VERSION = "pheroos-evidence-binding-v1"
NONCRITICAL_EXTENSION_PATTERN = (
    r"^(?:x-(?![cC][rR][iI][tT][iI][cC][aA][lL](?:[.\-]|$))|"
    r"ext\.(?![cC][rR][iI][tT][iI][cC][aA][lL](?:\.|$))).+"
)


class CommitWireBinding(str, Enum):
    """How an envelope profile binds to its authoritative payload."""

    UNBOUND = "unbound"
    PROFILE = "profile"
    PROFILE_AND_ASSURANCE = "profile_and_assurance"


PayloadSchemaFactory = Callable[[], dict[str, Any]]
SemanticValidator = Callable[[Mapping[str, Any], str], list[str]]
ProfileAgnosticValidator = Callable[[Mapping[str, Any]], list[str]]


@dataclass(frozen=True, slots=True)
class CommitWireContract:
    """One immutable, built-in Commit Wire branch.

    The tuple of these records is the sole registry used to build both the
    JSON Schema discriminator and semantic dispatch.  There is deliberately
    no runtime registration API: authority-relevant extensions require a new
    wire/profile version instead of mutating v1 in process.
    """

    schema_name: str
    payload_schema: PayloadSchemaFactory
    validator: SemanticValidator
    binding: CommitWireBinding = CommitWireBinding.PROFILE_AND_ASSURANCE
    profiles: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.schema_name or not isinstance(self.schema_name, str):
            raise ValueError("commit wire contract schema must be non-empty text")
        if not callable(self.payload_schema):
            raise TypeError("commit wire contract requires one payload schema factory")
        if not callable(self.validator):
            raise TypeError("commit wire contract requires exactly one validator")
        if self.profiles is not None and (
            not self.profiles
            or any(
                not isinstance(profile, str) or not profile for profile in self.profiles
            )
        ):
            raise TypeError("commit wire contract profiles must be non-empty text")


def no_semantic_authority(
    payload: Mapping[str, Any],
    profile: str,
) -> list[str]:
    """Explicit validator for branches whose JSON shape is their semantics."""

    del payload, profile
    return []


def profile_agnostic(
    validator: ProfileAgnosticValidator,
) -> SemanticValidator:
    """Adapt a deterministic payload validator to the static contract ABI."""

    def adapted(payload: Mapping[str, Any], profile: str) -> list[str]:
        del profile
        return validator(payload)

    adapted.__name__ = validator.__name__
    adapted.__qualname__ = validator.__qualname__
    return adapted


def _validate_noncritical_envelope_extensions(
    record: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    for key, value in record.items():
        if key in {"payload", "profile", "schema", "version"}:
            continue
        _validate_non_authoritative_json_value(
            value,
            path=f"$.{key}",
            errors=errors,
        )
    return errors


def _validate_non_authoritative_json_value(
    value: Any,
    *,
    path: str,
    errors: list[str],
) -> None:
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        _validate_non_authoritative_integer(value, path=path, errors=errors)
        return
    if type(value) is float:
        _validate_non_authoritative_float(value, path=path, errors=errors)
        return
    if type(value) is str:
        _validate_non_authoritative_text(value, path=path, errors=errors)
        return
    if type(value) is list:
        _validate_non_authoritative_list(value, path=path, errors=errors)
        return
    if type(value) is dict:
        _validate_non_authoritative_object(value, path=path, errors=errors)
        return
    errors.append(f"{path}: metadata contains a non-JSON value")


def _validate_non_authoritative_integer(
    value: int,
    *,
    path: str,
    errors: list[str],
) -> None:
    if abs(value) > MAX_AUTHORITY_INTEGER:
        errors.append(f"{path}: integer exceeds portable Commit bound")


def _validate_non_authoritative_float(
    value: float,
    *,
    path: str,
    errors: list[str],
) -> None:
    if not math.isfinite(value):
        errors.append(f"{path}: non-authoritative metadata must be finite JSON")


def _validate_non_authoritative_text(
    value: str,
    *,
    path: str,
    errors: list[str],
) -> None:
    if value != unicodedata.normalize("NFC", value):
        errors.append(f"{path}: metadata string must use NFC normalization")


def _validate_non_authoritative_list(
    value: list[Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    for index, item in enumerate(value):
        _validate_non_authoritative_json_value(
            item,
            path=f"{path}[{index}]",
            errors=errors,
        )


def _validate_non_authoritative_object(
    value: dict[Any, Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    for key, item in value.items():
        if (
            type(key) is not str
            or not key
            or key != key.strip()
            or key != unicodedata.normalize("NFC", key)
        ):
            errors.append(f"{path}: metadata object keys must be canonical strings")
            continue
        _validate_non_authoritative_json_value(
            item,
            path=f"{path}.{key}",
            errors=errors,
        )


def _validate_sealed_heartbeat_semantics(
    payload: Mapping[str, Any],
    *,
    require_continuous: bool = False,
) -> list[str]:
    errors: list[str] = []
    sealed = payload["sealed_window"]
    seal_ref = payload["seal_ref"]
    sealed_at = payload["sealed_at_step"]
    previous_ref = payload["previous_progress_ref"]
    sequence = payload["heartbeat_sequence"]
    if sealed:
        if not seal_ref:
            errors.append("$.payload.seal_ref: sealed record requires a seal")
        if sealed_at > payload["current_step"]:
            errors.append("$.payload.sealed_at_step: seal is from the future")
    elif seal_ref or sealed_at or previous_ref or sequence:
        errors.append("$.payload: unsealed record carries seal lineage")
    if previous_ref:
        if not sealed or sequence == 0:
            errors.append(
                "$.payload.previous_progress_ref: predecessor requires sealed heartbeat"
            )
    elif sequence != 0:
        errors.append("$.payload.heartbeat_sequence: initial sequence must be zero")
    if require_continuous and not payload["heartbeat_continuous"]:
        errors.append("$.payload.heartbeat_continuous: progress must be continuous")
    return errors


_ASSESSMENT_LINEAGE_ROOTS = (
    "risk_chain_state_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "support_replay_state_root",
    "support_replay_root",
    "collective_evidence_root",
    "collective_challenge_root",
    "collective_lease_root",
    "stop_resolution_root",
    "permission_root",
)

_CANDIDATE_LINEAGE_ROOTS = (
    "candidate_evidence_root",
    "candidate_challenge_root",
    "candidate_lease_root",
)


def _validate_assessment_lineage_semantics(
    payload: Mapping[str, Any],
    *,
    path: str = "$.payload",
) -> list[str]:
    errors: list[str] = []
    has_assessment = bool(payload["assessment_ref"])
    if bool(payload["context_ref"]) is not has_assessment:
        errors.append(f"{path}: assessment and context lineage must co-exist")
    assessment_roots = [payload[name] for name in _ASSESSMENT_LINEAGE_ROOTS]
    candidate_roots = [payload[name] for name in _CANDIDATE_LINEAGE_ROOTS]
    if has_assessment:
        for name, value in zip(_ASSESSMENT_LINEAGE_ROOTS, assessment_roots):
            if not value:
                errors.append(f"{path}.{name}: assessment lineage is incomplete")
        if any(candidate_roots) and not all(candidate_roots):
            errors.append(f"{path}: candidate lineage roots must be complete")
    elif any(assessment_roots) or any(candidate_roots):
        errors.append(f"{path}: metadata exists without an assessment")
    return errors


def _validate_canonical_set(
    values: list[Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    try:
        canonical = list(canonical_commit_set(values))
    except CommitWireError as exc:
        errors.append(f"{path}: {exc}")
    else:
        if canonical != values:
            errors.append(f"{path}: set-like array is not canonical")


def _validate_lexical_set(
    values: list[Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    if values != sorted(values):
        errors.append(f"{path}: fingerprint set is not lexically canonical")


def _validate_interval(
    payload: Mapping[str, Any],
    *,
    start: str,
    end: str,
    path: str = "$.payload",
) -> list[str]:
    if payload[end] <= payload[start]:
        return [f"{path}: {end} must be after {start}"]
    return []


def envelope_schema(
    schema_name: str,
    payload_schema: dict[str, Any],
    *,
    profiles: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    schema = strict_object_schema(
        {
            "schema": {"const": schema_name},
            "profile": {"enum": sorted(profiles or SUPPORTED_COMMIT_PROFILES)},
            "version": {"const": COMMIT_WIRE_VERSION},
            "payload": payload_schema,
        },
        required=("schema", "profile", "version", "payload"),
    )
    # Extensions live beside, never inside, the authority payload.  The
    # canonical Commit fingerprint API projects only the four required fields,
    # so accepted metadata cannot silently acquire authority.  Critical
    # namespaces deliberately do not match and are rejected by
    # additionalProperties=false.
    schema["patternProperties"] = {NONCRITICAL_EXTENSION_PATTERN: {}}
    return schema


def commit_binding_properties() -> dict[str, Any]:
    return {
        "assurance": {"enum": sorted(SUPPORTED_COMMIT_ASSURANCES)},
        "commit_policy_root": fingerprint_schema(),
        "epoch": authority_integer_schema(),
        "manifest_root": fingerprint_schema(),
        "profile": {"enum": sorted(SUPPORTED_COMMIT_PROFILES)},
        "protocol_id": canonical_text_schema(),
        "run_id": canonical_text_schema(),
        "target": canonical_text_schema(),
    }


def strict_object_schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(required or properties),
        "properties": properties,
        "additionalProperties": False,
    }


def canonical_text_schema() -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "pattern": r"^\S(?:.*\S)?$"}


def optional_text_schema() -> dict[str, Any]:
    return {"oneOf": [{"const": ""}, canonical_text_schema()]}


def authority_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 0,
        "maximum": MAX_AUTHORITY_INTEGER,
        "x-pheroos-exact-integer": True,
    }


def positive_authority_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_AUTHORITY_INTEGER,
        "x-pheroos-exact-integer": True,
    }


def signed_authority_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": -MAX_AUTHORITY_INTEGER,
        "maximum": MAX_AUTHORITY_INTEGER,
        "x-pheroos-exact-integer": True,
    }


def scaled_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 0,
        "maximum": WEIGHT_SCALE,
        "x-pheroos-exact-integer": True,
    }


def positive_scaled_integer_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": WEIGHT_SCALE,
        "x-pheroos-exact-integer": True,
    }


def fingerprint_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": FINGERPRINT_PATTERN}


def optional_fingerprint_schema() -> dict[str, Any]:
    return {"oneOf": [{"const": ""}, fingerprint_schema()]}


def optional_enum_schema(values: tuple[str, ...]) -> dict[str, Any]:
    return {"enum": ["", *sorted(values)]}


def governance_authority_schema() -> dict[str, Any]:
    return {"type": "integer", "enum": [4, 5], "x-pheroos-exact-integer": True}


def action_schema() -> dict[str, Any]:
    return {"enum": sorted(item.value for item in CommitAction)}


def canonical_text_set_schema(*, minimum: int = 0) -> dict[str, Any]:
    return {
        "type": "array",
        "items": canonical_text_schema(),
        "minItems": minimum,
        "uniqueItems": True,
    }


def fingerprint_set_schema(*, minimum: int = 0) -> dict[str, Any]:
    return {
        "type": "array",
        "items": fingerprint_schema(),
        "minItems": minimum,
        "uniqueItems": True,
    }


def terminal_outcome_set_schema(
    *,
    allowed: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"enum": sorted(allowed or SUPPORTED_TERMINAL_OUTCOMES)},
        "uniqueItems": True,
    }


__all__: tuple[str, ...] = ()
