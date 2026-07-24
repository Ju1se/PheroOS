from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, TypeGuard, cast
import unicodedata

from pheroos.protocol.commit_models import (
    COMMIT_WIRE_VERSION,
    CollectiveCommitPolicy,
    MAX_AUTHORITY_INTEGER,
)


_SET_LIKE_POLICY_FIELDS = frozenset(
    {
        "required_challenge_categories",
        "publishable_outcomes",
        "executable_outcomes",
        "deliverable_outcomes",
        "reset_rules",
    }
)


class CommitWireError(ValueError):
    """Raised when an authority payload cannot use the Commit wire ABI."""


def canonical_commit_payload(
    payload: Mapping[str, Any],
    *,
    schema: str,
    profile: str,
    version: str = COMMIT_WIRE_VERSION,
) -> str:
    normalized_bindings: dict[str, str] = {}
    for field_name, value in (
        ("schema", schema),
        ("profile", profile),
        ("version", version),
    ):
        if not isinstance(value, str) or not value or value != value.strip():
            raise CommitWireError(
                f"commit canonical {field_name} must be a canonical non-blank string"
            )
        normalized = unicodedata.normalize("NFC", value)
        if normalized != value:
            raise CommitWireError(
                f"commit canonical {field_name} must already use NFC normalization"
            )
        normalized_bindings[field_name] = normalized
    normalized_payload = _canonical_commit_value(payload, path="payload")
    if not isinstance(normalized_payload, dict):
        raise CommitWireError("commit canonical payload must be an object")
    return json.dumps(
        {
            "payload": normalized_payload,
            "profile": normalized_bindings["profile"],
            "schema": normalized_bindings["schema"],
            "version": normalized_bindings["version"],
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def commit_payload_fingerprint(
    payload: Mapping[str, Any],
    *,
    schema: str,
    profile: str,
    version: str = COMMIT_WIRE_VERSION,
) -> str:
    canonical = canonical_commit_payload(
        payload,
        schema=schema,
        profile=profile,
        version=version,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def canonical_commit_set(values: Sequence[Any]) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise CommitWireError("commit canonical set must be a sequence")
    normalized: list[tuple[str, str, Any]] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        item = _canonical_commit_value(value, path=f"set[{index}]")
        canonical_item = json.dumps(
            item,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if canonical_item in seen:
            raise CommitWireError("commit canonical set contains a duplicate item")
        seen.add(canonical_item)
        fingerprint = sha256(canonical_item.encode("utf-8")).hexdigest()
        normalized.append((fingerprint, canonical_item, item))
    return tuple(
        item
        for _, _, item in sorted(
            normalized,
            key=lambda record: (record[0], record[1]),
        )
    )


def commit_policy_authority_payload(
    policy: CollectiveCommitPolicy,
) -> dict[str, Any]:
    if type(policy) is not CollectiveCommitPolicy:
        raise CommitWireError(
            "commit policy authority projection requires CollectiveCommitPolicy"
        )
    return cast(
        dict[str, Any],
        _authority_projection(policy, field_name="collective_commit_policy"),
    )


def commit_policy_fingerprint(
    policy: CollectiveCommitPolicy,
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        commit_policy_authority_payload(policy),
        schema="pheroos-collective-commit-policy-authority-v1",
        profile=profile,
    )


def commit_manifest_authority_payload(manifest: object) -> dict[str, Any]:
    from pheroos.protocol.models import CapabilityManifest

    if type(manifest) is not CapabilityManifest:
        raise CommitWireError(
            "commit manifest authority projection requires CapabilityManifest"
        )
    policy = manifest.protocol.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise CommitWireError(
            "commit manifest authority projection requires an active commit policy"
        )
    targets = canonical_commit_set(
        tuple({"id": target.id} for target in manifest.protocol.targets)
    )
    candidates = canonical_commit_set(
        tuple(
            {
                "id": candidate.id,
                "safe_fallback": candidate.safe_fallback,
                "target": candidate.target,
            }
            for candidate in manifest.protocol.candidates
        )
    )
    recovery = canonical_commit_set(
        tuple(
            {
                "allowed_roles": canonical_commit_set(item.allowed_roles),
                "allowed_tags": canonical_commit_set(item.allowed_tags),
                "failure_candidate": item.failure_candidate,
                "id": item.id,
                "required_tools": canonical_commit_set(item.required_tools),
                "trigger_targets": canonical_commit_set(item.trigger_targets),
            }
            for item in manifest.protocol.recovery_protocols
        )
    )
    signals = canonical_commit_set(
        tuple(
            {
                "authority_required": signal.authority_required,
                "target": signal.target,
                "type": signal.type,
            }
            for signal in manifest.protocol.signals
        )
    )
    return {
        "capability_id": manifest.id,
        "capability_version": manifest.version,
        "candidates": candidates,
        "collective_commit_policy": commit_policy_authority_payload(policy),
        "evidence_policy": {
            "allow_agent_fact_creation": (
                manifest.protocol.evidence_policy.allow_agent_fact_creation
            ),
            "require_provenance": manifest.protocol.evidence_policy.require_provenance,
        },
        "output_policy": {
            "requires_committed_candidate": (
                manifest.protocol.output_policy.requires_committed_candidate
            ),
            "requires_evidence_contract": (
                manifest.protocol.output_policy.requires_evidence_contract
            ),
            "requires_publication_permission": (
                manifest.protocol.output_policy.requires_publication_permission
            ),
            "requires_stop_resolution": (
                manifest.protocol.output_policy.requires_stop_resolution
            ),
            "writer_may_create_facts": (
                manifest.protocol.output_policy.writer_may_create_facts
            ),
        },
        "protocol_id": manifest.protocol.id,
        "protocol_version": manifest.protocol.protocol_version,
        "quorum_authority_bridge": {
            "fallback_candidate": manifest.protocol.quorum_policy.fallback_candidate,
            "target": manifest.protocol.quorum_policy.target,
        },
        "recovery_protocols": recovery,
        "signals": signals,
        "targets": targets,
        "trace_policy": {
            "required_events": canonical_commit_set(
                manifest.protocol.trace_policy.required_events
            )
        },
    }


def commit_manifest_fingerprint(manifest: object, *, profile: str) -> str:
    return commit_payload_fingerprint(
        commit_manifest_authority_payload(manifest),
        schema="pheroos-commit-manifest-authority-v1",
        profile=profile,
    )


def _authority_projection(value: Any, *, field_name: str) -> Any:
    if is_dataclass(value):
        return {
            item.name: _authority_projection(
                getattr(value, item.name),
                field_name=item.name,
            )
            for item in fields(value)
            if item.name != "extensions"
        }
    if isinstance(value, Mapping):
        return {
            key: _authority_projection(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        projected = tuple(
            _authority_projection(item, field_name=field_name) for item in value
        )
        if field_name in _SET_LIKE_POLICY_FIELDS:
            return canonical_commit_set(projected)
        return projected
    return value


def _canonical_commit_value(value: Any, *, path: str) -> Any:
    handled, canonical = _canonical_exact_value(value, path=path)
    if handled:
        return canonical
    if isinstance(value, Enum):
        return _canonical_commit_value(value.value, path=path)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return _canonical_text(value, path=path)
    if isinstance(value, int):
        return _canonical_integer(value, path=path)
    if isinstance(value, float):
        raise CommitWireError(f"{path} must not contain floating-point values")
    if isinstance(value, Mapping):
        return _canonical_mapping(value, path=path)
    if isinstance(value, (set, frozenset)):
        return list(canonical_commit_set(tuple(value)))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _canonical_sequence(value, path=path)
    raise CommitWireError(
        f"{path} contains unsupported value type: {type(value).__name__}"
    )


def _canonical_exact_value(value: Any, *, path: str) -> tuple[bool, Any]:
    """Handle exact JSON-native containers without changing subclass semantics."""

    value_type = type(value)
    if value is None or value_type is bool:
        return True, value
    if value_type is str:
        return True, _canonical_text(value, path=path)
    if value_type is int:
        return True, _canonical_integer(value, path=path)
    if value_type is float:
        raise CommitWireError(f"{path} must not contain floating-point values")
    if value_type is dict:
        return True, _canonical_mapping(value, path=path)
    if value_type is list or value_type is tuple:
        return True, _canonical_sequence(value, path=path)
    if value_type is set or value_type is frozenset:
        return True, list(canonical_commit_set(tuple(value)))
    return False, None


def _canonical_text(value: str, *, path: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if normalized != value:
        raise CommitWireError(f"{path} must already use NFC normalization")
    return value


def _canonical_integer(value: int, *, path: str) -> int:
    if abs(value) > MAX_AUTHORITY_INTEGER:
        raise CommitWireError(f"{path} exceeds the authority integer bound")
    return value


def _canonical_mapping(value: Mapping[object, Any], *, path: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not _canonical_mapping_key(key):
            raise CommitWireError(
                f"{path} keys must be canonical non-blank NFC strings"
            )
        if key in normalized:
            raise CommitWireError(f"{path} contains duplicate keys")
        normalized[key] = _canonical_commit_value(item, path=f"{path}.{key}")
    return normalized


def _canonical_mapping_key(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and value == unicodedata.normalize("NFC", value)
    )


def _canonical_sequence(value: Sequence[Any], *, path: str) -> list[Any]:
    return [
        _canonical_commit_value(item, path=f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


__all__ = [
    "CommitWireError",
    "canonical_commit_payload",
    "canonical_commit_set",
    "commit_manifest_authority_payload",
    "commit_manifest_fingerprint",
    "commit_policy_authority_payload",
    "commit_policy_fingerprint",
    "commit_payload_fingerprint",
]
