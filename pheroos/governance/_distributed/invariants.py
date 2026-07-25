from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from typing import TypeVar

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CollectiveCommitPolicy,
    CommitAssurance,
    DistributedCommitPolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import validate_distributed_commit_policy


_DataclassT = TypeVar("_DataclassT")


def _validate_distributed_policy(
    commit_policy: CollectiveCommitPolicy,
    *,
    profile: str,
    assurance: CommitAssurance,
    target: str,
    commit_policy_root: str,
) -> DistributedCommitPolicy:
    if type(commit_policy) is not CollectiveCommitPolicy:
        raise GovernanceError("distributed commit requires canonical commit policy")
    if profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed commit profile is invalid")
    if assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed commit assurance is invalid")
    if commit_policy.assurance != assurance.value or commit_policy.target != target:
        raise GovernanceError("distributed commit policy binding mismatch")
    if commit_policy_fingerprint(
        commit_policy, profile=profile
    ) != require_commit_fingerprint(
        commit_policy_root,
        "distributed commit policy root",
    ):
        raise GovernanceError("distributed commit policy root mismatch")
    diagnostics = validate_distributed_commit_policy(
        commit_policy.distributed,
        assurance=assurance.value,
        path="collective_commit_policy.distributed",
    )
    if diagnostics:
        raise GovernanceError(
            "distributed commit policy violates the static Byzantine model"
        )
    distributed = commit_policy.distributed
    assert type(distributed) is DistributedCommitPolicy
    if not _quorum_intersection_is_safe(
        distributed.membership_size,
        distributed.max_byzantine_faults,
        distributed.witness_quorum,
    ):
        raise GovernanceError("distributed quorum intersection is unsafe")
    return distributed


def _quorum_intersection_is_safe(n: int, f: int, q: int) -> bool:
    return bool(n >= 3 * f + 1 and q <= n - f and 2 * q - n > f)


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(values)
    if not normalized and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    for value in normalized:
        require_commit_fingerprint(value, field_name)
    if len(normalized) != len(set(normalized)):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(normalized))


def _public_dataclass_payload(value: object) -> dict[str, object]:
    if not is_dataclass(value) or isinstance(value, type):
        raise GovernanceError("distributed payload source must be a dataclass instance")
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if not item.name.startswith("_")
    }


def _strict_dataclass_payload(
    payload: object,
    cls: type[object],
    field_name: str,
) -> dict[str, object]:
    if not is_dataclass(cls):
        raise GovernanceError(f"{field_name} target must be a dataclass type")
    names = {
        item.name for item in fields(cls) if item.init and not item.name.startswith("_")
    }
    return _strict_mapping(payload, names, field_name)


def _construct_dataclass(
    cls: type[_DataclassT],
    payload: Mapping[str, object],
) -> _DataclassT:
    """Construct a known dataclass at the validated payload/reflection boundary."""

    return cls(**payload)


def _require_mapping(
    value: object,
    field_name: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GovernanceError(f"{field_name} must be a mapping")
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise GovernanceError(f"{field_name} keys must be strings")
        normalized[key] = item
    return normalized


def _strict_mapping(
    payload: object,
    expected_keys: set[str],
    field_name: str,
) -> dict[str, object]:
    normalized = _require_mapping(payload, field_name)
    actual = set(normalized)
    if actual != expected_keys:
        missing = sorted(expected_keys - actual)
        unknown = sorted(actual - expected_keys)
        raise GovernanceError(
            f"{field_name} fields mismatch; missing={missing}, unknown={unknown}"
        )
    return dict(normalized)


def _require_sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise GovernanceError(f"{field_name} must be a sequence")
    return tuple(value)


def _coerce_assurance(value: object) -> CommitAssurance:
    if type(value) is CommitAssurance:
        return value
    for assurance in CommitAssurance:
        if value == assurance.value:
            return assurance
    raise GovernanceError("distributed assurance is invalid")


def _coerce_authority(value: object) -> AuthorityLevel:
    if type(value) is AuthorityLevel:
        return value
    if isinstance(value, bool):
        raise GovernanceError("distributed authority is invalid")
    for authority in AuthorityLevel:
        if value == authority.value:
            return authority
    raise GovernanceError("distributed authority is invalid")
