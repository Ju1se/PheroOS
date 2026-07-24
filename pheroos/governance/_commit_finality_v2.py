"""Authority-neutral finality projection shared by v2 governance owners.

The record is canonical portable data, never authority.  A Decision source may
consume it only when a later StateStore-backed Certificate or Distributed
owner supplies its matching non-portable verified handle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import ClassVar, NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import (
    MAX_AUTHORITY_REVISION_V2,
    GovernanceReadPreconditionV2,
)


COMMIT_FINALITY_PROJECTION_SCHEMA_V2 = "pheroos-commit-finality-projection-v2"
MAX_COMMIT_FINALITY_TEXT_BYTES_V2 = 4_096
MAX_COMMIT_FINALITY_REASONS_V2 = 128
COMMIT_FINALITY_INPUT_SCHEMA_V2 = "pheroos-verified-commit-finality-input-v2"
_FINALITY_INPUT_TOKEN_V2 = object()
_CERTIFICATE_SNAPSHOT_SCHEMA_V2 = "pheroos-commit-certificate-snapshot-v2"
_DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2 = "pheroos-distributed-lane-snapshot-v2"


class CommitFinalityOwnerV2(StrEnum):
    CERTIFICATE = "certificate"
    DISTRIBUTED = "distributed"


class CommitFinalityStatusV2(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"


def commit_finality_owner_stream_ref_v2(
    owner: CommitFinalityOwnerV2,
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return the canonical durable stream owned by one finality mechanism."""

    if type(owner) is not CommitFinalityOwnerV2:
        raise TypeError("commit finality stream owner is invalid")
    values = tuple(
        _require_text(value, f"commit finality stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    if owner is CommitFinalityOwnerV2.CERTIFICATE:
        material = b"\x00".join(item.encode("utf-8") for item in values)
        prefix = "authority:commit-certificate-v2:"
    else:
        material = b"\x00".join(
            item.encode("utf-8") for item in (*values, "certificate")
        )
        prefix = "authority:distributed-certificate-v2:"
    return prefix + sha256(material).hexdigest()


def commit_finality_owner_genesis_snapshot_root_v2(
    owner: CommitFinalityOwnerV2,
) -> str:
    """Return the byte-identical genesis root defined by the selected owner."""

    if type(owner) is not CommitFinalityOwnerV2:
        raise TypeError("commit finality genesis owner is invalid")
    if owner is CommitFinalityOwnerV2.CERTIFICATE:
        return _owner_root(
            b"pheroos-commit-certificate-v2",
            "genesis-snapshot",
            {"schema": _CERTIFICATE_SNAPSHOT_SCHEMA_V2},
        )
    return _owner_root(
        b"pheroos-distributed-commit-v2",
        "genesis-snapshot",
        {
            "schema": _DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2,
            "lane": "certificate",
        },
    )


@dataclass(frozen=True, slots=True)
class CommitFinalityProjectionV2:
    owner: CommitFinalityOwnerV2
    status: CommitFinalityStatusV2
    stream_ref: str
    revision: int
    transition_id: str
    snapshot_root: str
    head_root: str
    receipt_root: str
    seal_transition_id: str
    seal_root: str
    frozen_dependency_root: str
    verified_at_step: int
    reason_codes: Sequence[str]
    schema: str = COMMIT_FINALITY_PROJECTION_SCHEMA_V2
    projection_root: str = ""

    _root_field: ClassVar[str] = "projection_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_FINALITY_PROJECTION_SCHEMA_V2:
            raise ValueError("commit finality projection schema is unsupported")
        if type(self.owner) is not CommitFinalityOwnerV2:
            raise TypeError("commit finality owner is invalid")
        if type(self.status) is not CommitFinalityStatusV2:
            raise TypeError("commit finality status is invalid")
        for field in ("stream_ref", "transition_id", "seal_transition_id"):
            _require_text(getattr(self, field), f"commit finality {field}")
        _require_count(self.revision, "commit finality revision", minimum=1)
        _require_count(self.verified_at_step, "commit finality verified_at_step")
        for field in (
            "snapshot_root",
            "head_root",
            "receipt_root",
            "seal_root",
            "frozen_dependency_root",
        ):
            _require_root(getattr(self, field), f"commit finality {field}")
        reasons = _canonical_texts(self.reason_codes, "commit finality reason_codes")
        object.__setattr__(self, "reason_codes", reasons)
        expected = _root(self._body())
        if self.projection_root not in ("", expected):
            raise ValueError("commit finality projection_root is mismatched")
        object.__setattr__(self, "projection_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "owner": self.owner.value,
            "status": self.status.value,
            "stream_ref": self.stream_ref,
            "revision": self.revision,
            "transition_id": self.transition_id,
            "snapshot_root": self.snapshot_root,
            "head_root": self.head_root,
            "receipt_root": self.receipt_root,
            "seal_transition_id": self.seal_transition_id,
            "seal_root": self.seal_root,
            "frozen_dependency_root": self.frozen_dependency_root,
            "verified_at_step": self.verified_at_step,
            "reason_codes": list(self.reason_codes),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "projection_root": self.projection_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitFinalityProjectionV2:
        if type(payload) is not dict:
            raise TypeError("commit finality projection must be an exact object")
        value = cast(dict[str, object], payload).copy()
        fields = frozenset(
            {
                "schema",
                "owner",
                "status",
                "stream_ref",
                "revision",
                "transition_id",
                "snapshot_root",
                "head_root",
                "receipt_root",
                "seal_transition_id",
                "seal_root",
                "frozen_dependency_root",
                "verified_at_step",
                "reason_codes",
                "projection_root",
            }
        )
        if set(value) != fields or any(type(key) is not str for key in value):
            raise ValueError("commit finality projection fields are invalid")
        try:
            value["owner"] = CommitFinalityOwnerV2(cast(str, value["owner"]))
            value["status"] = CommitFinalityStatusV2(cast(str, value["status"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit finality projection enum is unsupported") from exc
        if type(value["reason_codes"]) is not list:
            raise TypeError("commit finality reasons must be an exact array")
        value["reason_codes"] = tuple(cast(list[object], value["reason_codes"]))
        decoded = cls(
            schema=cast(str, value["schema"]),
            owner=cast(CommitFinalityOwnerV2, value["owner"]),
            status=cast(CommitFinalityStatusV2, value["status"]),
            stream_ref=cast(str, value["stream_ref"]),
            revision=cast(int, value["revision"]),
            transition_id=cast(str, value["transition_id"]),
            snapshot_root=cast(str, value["snapshot_root"]),
            head_root=cast(str, value["head_root"]),
            receipt_root=cast(str, value["receipt_root"]),
            seal_transition_id=cast(str, value["seal_transition_id"]),
            seal_root=cast(str, value["seal_root"]),
            frozen_dependency_root=cast(
                str,
                value["frozen_dependency_root"],
            ),
            verified_at_step=cast(int, value["verified_at_step"]),
            reason_codes=cast(Sequence[str], value["reason_codes"]),
            projection_root=cast(str, value["projection_root"]),
        )
        if payload != decoded.to_dict():
            raise ValueError("commit finality projection is not canonical wire")
        return decoded


@dataclass(frozen=True, slots=True)
class _CommitFinalityInputMaterialV2:
    projection: CommitFinalityProjectionV2
    owner_precondition: GovernanceReadPreconditionV2
    owner_receipt_root: str
    owner_inclusion_root: str
    input_root: str


@final
class VerifiedCommitFinalityInputV2:
    """Opaque proof that a finality owner verified one exact projection."""

    __slots__ = (
        "_anchor_root",
        "_owner_inclusion_root",
        "_owner_precondition",
        "_owner_receipt_root",
        "_projection",
        "_token",
    )

    def __new__(
        cls,
        *_args: object,
        **_kwargs: object,
    ) -> VerifiedCommitFinalityInputV2:
        raise TypeError("VerifiedCommitFinalityInputV2 cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitFinalityInputV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitFinalityInputV2 is immutable")

    def __copy__(self) -> VerifiedCommitFinalityInputV2:
        _verified_commit_finality_input_material_v2(self)
        return self

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> VerifiedCommitFinalityInputV2:
        _verified_commit_finality_input_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitFinalityInputV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitFinalityInputV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitFinalityInputV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitFinalityInputV2 redacted>"


def _issue_verified_commit_finality_input_v2(
    *,
    projection: CommitFinalityProjectionV2,
    owner_precondition: GovernanceReadPreconditionV2,
    owner_receipt_root: str,
    owner_inclusion_root: str,
) -> VerifiedCommitFinalityInputV2:
    material = _commit_finality_input_material_v2(
        projection=projection,
        owner_precondition=owner_precondition,
        owner_receipt_root=owner_receipt_root,
        owner_inclusion_root=owner_inclusion_root,
    )
    value = object.__new__(VerifiedCommitFinalityInputV2)
    object.__setattr__(value, "_token", _FINALITY_INPUT_TOKEN_V2)
    object.__setattr__(value, "_projection", material.projection)
    object.__setattr__(value, "_owner_precondition", material.owner_precondition)
    object.__setattr__(value, "_owner_receipt_root", material.owner_receipt_root)
    object.__setattr__(value, "_owner_inclusion_root", material.owner_inclusion_root)
    object.__setattr__(value, "_anchor_root", material.input_root)
    return value


def _verified_commit_finality_input_material_v2(
    value: object,
) -> _CommitFinalityInputMaterialV2:
    if type(value) is not VerifiedCommitFinalityInputV2:
        raise TypeError("verified commit finality input has the wrong exact type")
    try:
        token = object.__getattribute__(value, "_token")
        projection = object.__getattribute__(value, "_projection")
        precondition = object.__getattribute__(value, "_owner_precondition")
        receipt_root = object.__getattribute__(value, "_owner_receipt_root")
        inclusion_root = object.__getattribute__(value, "_owner_inclusion_root")
        anchor_root = object.__getattribute__(value, "_anchor_root")
    except AttributeError as exc:
        raise TypeError("verified commit finality input is incomplete") from exc
    if token is not _FINALITY_INPUT_TOKEN_V2 or type(anchor_root) is not str:
        raise TypeError("verified commit finality input token is invalid")
    material = _commit_finality_input_material_v2(
        projection=projection,
        owner_precondition=precondition,
        owner_receipt_root=receipt_root,
        owner_inclusion_root=inclusion_root,
    )
    if material.input_root != anchor_root:
        raise ValueError("verified commit finality input anchor is mismatched")
    return material


def _commit_finality_input_material_v2(
    *,
    projection: object,
    owner_precondition: object,
    owner_receipt_root: object,
    owner_inclusion_root: object,
) -> _CommitFinalityInputMaterialV2:
    if type(projection) is not CommitFinalityProjectionV2:
        raise TypeError("verified commit finality projection is invalid")
    if type(owner_precondition) is not GovernanceReadPreconditionV2:
        raise TypeError("verified commit finality precondition is invalid")
    receipt_root = _require_root(
        owner_receipt_root,
        "verified commit finality owner receipt_root",
    )
    inclusion_root = _require_root(
        owner_inclusion_root,
        "verified commit finality owner inclusion_root",
    )
    detached_projection = CommitFinalityProjectionV2.from_dict(projection.to_dict())
    detached_precondition = GovernanceReadPreconditionV2.from_dict(
        owner_precondition.to_dict()
    )
    if (
        detached_projection.stream_ref,
        detached_projection.revision,
        detached_projection.head_root,
        detached_projection.receipt_root,
    ) != (
        detached_precondition.stream_ref,
        detached_precondition.expected_revision,
        detached_precondition.expected_root,
        receipt_root,
    ):
        raise ValueError("verified commit finality owner head is mismatched")
    input_root = _root(
        {
            "schema": COMMIT_FINALITY_INPUT_SCHEMA_V2,
            "projection_root": detached_projection.projection_root,
            "owner_precondition": detached_precondition.to_dict(),
            "owner_receipt_root": receipt_root,
            "owner_inclusion_root": inclusion_root,
        }
    )
    return _CommitFinalityInputMaterialV2(
        projection=detached_projection,
        owner_precondition=detached_precondition,
        owner_receipt_root=receipt_root,
        owner_inclusion_root=inclusion_root,
        input_root=input_root,
    )


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise TypeError(f"{label} must be an exact non-empty string")
    result = value
    if "\x00" in result:
        raise ValueError(f"{label} contains U+0000")
    try:
        encoded = result.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must encode as UTF-8") from exc
    if len(encoded) > MAX_COMMIT_FINALITY_TEXT_BYTES_V2:
        raise ValueError(f"{label} exceeds its text bound")
    return result


def _require_root(value: object, label: str) -> str:
    result = _require_text(value, label)
    if (
        len(result) != 71
        or not result.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in result[7:])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 root")
    return result


def _require_count(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} is outside its integer bound")
    return value


def _canonical_texts(values: Sequence[str], label: str) -> tuple[str, ...]:
    if (
        type(values) not in (list, tuple)
        or len(values) > MAX_COMMIT_FINALITY_REASONS_V2
    ):
        raise TypeError(f"{label} must be a bounded array or tuple")
    result = tuple(_require_text(item, label) for item in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must contain unique values")
    return tuple(sorted(result, key=lambda item: item.encode("utf-8")))


def _root(body: object) -> str:
    encoded = json.dumps(
        body, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return "sha256:" + sha256(b"pheroos-commit-finality-v2\x00" + encoded).hexdigest()


def _owner_root(domain: bytes, label: str, body: object) -> str:
    encoded = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    material = domain + b"\x00" + label.encode("utf-8")
    return "sha256:" + sha256(material + b"\x00" + encoded).hexdigest()


__all__ = [
    "COMMIT_FINALITY_PROJECTION_SCHEMA_V2",
    "CommitFinalityOwnerV2",
    "CommitFinalityProjectionV2",
    "CommitFinalityStatusV2",
    "commit_finality_owner_genesis_snapshot_root_v2",
    "commit_finality_owner_stream_ref_v2",
]
