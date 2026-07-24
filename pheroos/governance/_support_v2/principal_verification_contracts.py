"""Portable ABI for the durable PrincipalVerificationSet v2 lineage."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE, CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_canonical_wire_v2,
    _require_count_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)
from pheroos.governance._support_v2.principal_verification_records import (
    MAX_PRINCIPAL_VERIFICATIONS_V2,
    PrincipalVerificationRecordV2,
    canonical_verification_records_v2,
)


PRINCIPAL_VERIFICATION_SET_SNAPSHOT_SCHEMA_V2 = (
    "pheroos-principal-verification-set-snapshot-v2"
)
PRINCIPAL_VERIFICATION_SET_REQUEST_SCHEMA_V2 = (
    "pheroos-principal-verification-set-advance-request-v2"
)
PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2 = (
    "pheroos-principal-verification-set-state-v2"
)
MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2 = 8 * 1024 * 1024


def _root(kind: str, body: object) -> str:
    return _compute_root(f"principal-verification-v2:{kind}", body)


PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "genesis-parent",
    {
        "schema": PRINCIPAL_VERIFICATION_SET_SNAPSHOT_SCHEMA_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
    },
)
PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2 = "genesis"


def principal_verification_stream_ref_v2(
    scope_ref: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    verification_policy_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return one fixed stream for an exact target/run/policy binding."""

    texts = tuple(
        _require_bounded_text_v2(value, f"principal verification stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("profile", profile),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    if type(assurance) is not CommitAssurance:
        raise TypeError("principal verification stream assurance is invalid")
    for label, value in (
        ("manifest_root", manifest_root),
        ("commit_policy_root", commit_policy_root),
        ("verification_policy_root", verification_policy_root),
    ):
        _require_root(value, f"principal verification stream {label}")
    material = (
        texts[0],
        texts[1],
        assurance.value,
        manifest_root,
        commit_policy_root,
        verification_policy_root,
        texts[2],
        texts[3],
        texts[4],
    )
    digest = sha256("\x00".join(material).encode("utf-8")).hexdigest()
    return f"authority:principal-verification-v2:{digest}"


def principal_verification_transition_id_v2(stream_ref: str, advance_ref: str) -> str:
    stream = _require_bounded_text_v2(
        stream_ref, "principal verification transition stream_ref"
    )
    advance = _require_bounded_text_v2(
        advance_ref, "principal verification transition advance_ref"
    )
    digest = sha256(f"{stream}\x00{advance}".encode("utf-8")).hexdigest()
    return f"transition:principal-verification-v2:{digest}"


@dataclass(frozen=True, slots=True)
class PrincipalVerificationSetSnapshotV2:
    """Complete replacement state for one verification-set revision."""

    domain_root: str
    scope_ref: str
    profile: str
    assurance: CommitAssurance
    authority_policy_root: str
    manifest_root: str
    commit_policy_root: str
    verification_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    observed_epoch: int
    advance_ref: str
    stream_ref: str
    transition_id: str
    snapshot_ref: str
    revision: int
    parent_revision: int
    parent_epoch: int | None
    parent_transition_id: str
    parent_snapshot_root: str
    current_step: int
    expires_at_step: int
    mutation_issuer_ref: str
    records: Sequence[PrincipalVerificationRecordV2]
    record_count: int
    verification_set_root: str = ""
    schema: str = PRINCIPAL_VERIFICATION_SET_SNAPSHOT_SCHEMA_V2
    state_schema: str = PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        _validate_snapshot_context(self)
        canonical = canonical_verification_records_v2(self.records)
        object.__setattr__(self, "records", canonical)
        if self.record_count != len(canonical):
            raise ValueError("principal verification record_count is mismatched")
        if any(
            item.issued_at_step > self.current_step
            or item.expires_at_step < self.expires_at_step
            for item in canonical
        ):
            raise ValueError("principal verification record is stale or future-dated")
        expected_set_root = _root(
            "set",
            {
                "verification_policy_root": self.verification_policy_root,
                "protocol_ref": self.protocol_ref,
                "run_ref": self.run_ref,
                "target_ref": self.target_ref,
                "epoch": self.epoch,
                "records": [item.to_dict() for item in canonical],
            },
        )
        if self.verification_set_root not in ("", expected_set_root):
            raise ValueError("principal verification_set_root is mismatched")
        object.__setattr__(self, "verification_set_root", expected_set_root)
        expected_snapshot_root = _root("snapshot", self._body())
        if self.snapshot_root not in ("", expected_snapshot_root):
            raise ValueError("principal verification snapshot_root is mismatched")
        object.__setattr__(self, "snapshot_root", expected_snapshot_root)
        if len(self.canonical_bytes()) > MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2:
            raise ValueError("principal verification snapshot exceeds its byte bound")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "profile": self.profile,
            "assurance": self.assurance.value,
            "authority_policy_root": self.authority_policy_root,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "verification_policy_root": self.verification_policy_root,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "observed_epoch": self.observed_epoch,
            "advance_ref": self.advance_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "snapshot_ref": self.snapshot_ref,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "parent_epoch": self.parent_epoch,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "current_step": self.current_step,
            "expires_at_step": self.expires_at_step,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "records": [item.to_dict() for item in self.records],
            "record_count": self.record_count,
            "verification_set_root": self.verification_set_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> PrincipalVerificationSetSnapshotV2:
        value = _require_exact_mapping_v2(
            payload, _SNAPSHOT_FIELDS, "principal verification set snapshot v2"
        )
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("principal verification assurance is unsupported") from exc
        raw = _require_exact_array_v2(
            value["records"],
            "principal verification records",
            limit=MAX_PRINCIPAL_VERIFICATIONS_V2,
        )
        value["records"] = tuple(
            PrincipalVerificationRecordV2.from_dict(item) for item in raw
        )
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "principal verification set snapshot v2",
        )
        return decoded


@dataclass(frozen=True, slots=True)
class PrincipalVerificationSetAdvanceRequestV2:
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    observed_epoch: int
    advance_ref: str
    stream_ref: str
    transition_id: str
    snapshot: PrincipalVerificationSetSnapshotV2
    schema: str = PRINCIPAL_VERIFICATION_SET_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != PRINCIPAL_VERIFICATION_SET_REQUEST_SCHEMA_V2:
            raise ValueError("principal verification request schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError("principal verification canonical version is unsupported")
        if type(self.snapshot) is not PrincipalVerificationSetSnapshotV2:
            raise TypeError("principal verification request requires exact snapshot")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "epoch",
            "observed_epoch",
            "advance_ref",
            "stream_ref",
            "transition_id",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(
                    f"principal verification request {field} is cross-bound"
                )
        expected = _root("advance-request", self._body())
        if self.request_root not in ("", expected):
            raise ValueError("principal verification request_root is mismatched")
        object.__setattr__(self, "request_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "observed_epoch": self.observed_epoch,
            "advance_ref": self.advance_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "snapshot": self.snapshot.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> PrincipalVerificationSetAdvanceRequestV2:
        value = _require_exact_mapping_v2(
            payload, _REQUEST_FIELDS, "principal verification set request v2"
        )
        value["snapshot"] = PrincipalVerificationSetSnapshotV2.from_dict(
            value["snapshot"]
        )
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "principal verification set request v2",
        )
        return decoded


def _validate_snapshot_context(snapshot: PrincipalVerificationSetSnapshotV2) -> None:
    _validate_snapshot_versions(snapshot)
    _validate_snapshot_roots_and_text(snapshot)
    _validate_snapshot_counts(snapshot)
    _validate_snapshot_identity(snapshot)


def _validate_snapshot_versions(snapshot: PrincipalVerificationSetSnapshotV2) -> None:
    if (
        snapshot.schema != PRINCIPAL_VERIFICATION_SET_SNAPSHOT_SCHEMA_V2
        or snapshot.state_schema != PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2
        or snapshot.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
    ):
        raise ValueError("principal verification snapshot version is unsupported")


def _validate_snapshot_roots_and_text(
    snapshot: PrincipalVerificationSetSnapshotV2,
) -> None:
    for label, value in (
        ("domain_root", snapshot.domain_root),
        ("authority_policy_root", snapshot.authority_policy_root),
        ("manifest_root", snapshot.manifest_root),
        ("commit_policy_root", snapshot.commit_policy_root),
        ("verification_policy_root", snapshot.verification_policy_root),
        ("parent_snapshot_root", snapshot.parent_snapshot_root),
    ):
        _require_root(value, f"principal verification {label}")
    for field in (
        "scope_ref",
        "profile",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "advance_ref",
        "stream_ref",
        "transition_id",
        "snapshot_ref",
        "parent_transition_id",
        "mutation_issuer_ref",
    ):
        _require_bounded_text_v2(
            getattr(snapshot, field), f"principal verification {field}"
        )


def _validate_snapshot_counts(snapshot: PrincipalVerificationSetSnapshotV2) -> None:
    if type(snapshot.assurance) is not CommitAssurance:
        raise TypeError("principal verification assurance is invalid")
    if snapshot.profile not in COMMIT_PROFILES_BY_ASSURANCE.get(
        snapshot.assurance.value, frozenset()
    ):
        raise ValueError("principal verification profile is mismatched")
    for field in (
        "epoch",
        "observed_epoch",
        "revision",
        "parent_revision",
        "current_step",
        "expires_at_step",
        "record_count",
    ):
        _require_count_v2(getattr(snapshot, field), f"principal verification {field}")
    if snapshot.parent_epoch is not None:
        _require_count_v2(snapshot.parent_epoch, "principal verification parent_epoch")
    if snapshot.expires_at_step <= snapshot.current_step:
        raise ValueError("principal verification set expiry must follow current_step")


def _validate_snapshot_identity(snapshot: PrincipalVerificationSetSnapshotV2) -> None:
    expected_stream = principal_verification_stream_ref_v2(
        snapshot.scope_ref,
        snapshot.profile,
        snapshot.assurance,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.verification_policy_root,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
    )
    expected_transition = principal_verification_transition_id_v2(
        expected_stream, snapshot.advance_ref
    )
    if (
        snapshot.stream_ref != expected_stream
        or snapshot.transition_id != expected_transition
    ):
        raise ValueError("principal verification lineage identity is mismatched")
    if snapshot.parent_revision == 0:
        if (
            snapshot.revision != 1
            or snapshot.parent_epoch is not None
            or snapshot.parent_transition_id
            != PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2
            or snapshot.parent_snapshot_root
            != PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2
        ):
            raise ValueError("principal verification genesis lineage is invalid")
    elif (
        snapshot.revision != snapshot.parent_revision + 1
        or snapshot.parent_epoch is None
        or snapshot.epoch <= snapshot.parent_epoch
        or snapshot.parent_transition_id
        == PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2
    ):
        raise ValueError("principal verification revision continuity is invalid")


_SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "state_schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "profile",
        "assurance",
        "authority_policy_root",
        "manifest_root",
        "commit_policy_root",
        "verification_policy_root",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "epoch",
        "observed_epoch",
        "advance_ref",
        "stream_ref",
        "transition_id",
        "snapshot_ref",
        "revision",
        "parent_revision",
        "parent_epoch",
        "parent_transition_id",
        "parent_snapshot_root",
        "current_step",
        "expires_at_step",
        "mutation_issuer_ref",
        "records",
        "record_count",
        "verification_set_root",
        "snapshot_root",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "run_ref",
        "target_ref",
        "epoch",
        "observed_epoch",
        "advance_ref",
        "stream_ref",
        "transition_id",
        "snapshot",
        "request_root",
    }
)


__all__ = [
    "MAX_PRINCIPAL_VERIFICATION_SET_BYTES_V2",
    "PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2",
    "PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2",
    "PRINCIPAL_VERIFICATION_SET_REQUEST_SCHEMA_V2",
    "PRINCIPAL_VERIFICATION_SET_SNAPSHOT_SCHEMA_V2",
    "PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2",
    "PrincipalVerificationSetAdvanceRequestV2",
    "PrincipalVerificationSetSnapshotV2",
    "principal_verification_stream_ref_v2",
    "principal_verification_transition_id_v2",
]
