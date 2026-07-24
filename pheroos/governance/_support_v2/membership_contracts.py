"""Portable ABI for a fixed-lineage durable Membership v2 owner."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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
from pheroos.governance._support_v2.membership_records import (
    MAX_MEMBERSHIP_CLUSTERS_V2,
    MAX_MEMBERSHIP_PRINCIPALS_V2,
    MEMBERSHIP_CLUSTER_SCHEMA_V2,
    MEMBERSHIP_PRINCIPAL_SCHEMA_V2,
    MembershipClusterV2,
    MembershipPrincipalV2,
    canonical_membership_clusters_v2,
)
from pheroos.governance._support_v2.membership_stream_contracts import (
    MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2,
    MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2,
    MEMBERSHIP_GENESIS_TRANSITION_ID_V2,
    MEMBERSHIP_SNAPSHOT_SCHEMA_V2,
    MEMBERSHIP_STATE_SCHEMA_V2,
    membership_projection_root_v2,
    membership_stream_ref_v2,
    membership_transition_id_v2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    principal_verification_stream_ref_v2,
    principal_verification_transition_id_v2,
)


MAX_MEMBERSHIP_SNAPSHOT_BYTES_V2 = 8 * 1024 * 1024


def _root(kind: str, body: object) -> str:
    return _compute_root(f"membership-v2:{kind}", body)


@dataclass(frozen=True, slots=True)
class MembershipSnapshotV2:
    domain_root: str
    scope_ref: str
    profile: str
    assurance: CommitAssurance
    authority_policy_root: str
    manifest_root: str
    commit_policy_root: str
    membership_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    observed_epoch: int
    request_ref: str
    stream_ref: str
    transition_id: str
    snapshot_ref: str
    revision: int
    parent_revision: int
    parent_epoch: int | None
    parent_transition_id: str
    parent_snapshot_root: str
    issued_at_step: int
    expires_at_step: int
    mutation_issuer_ref: str
    membership_method: str
    provenance_ref: str
    source_trace_roots: Sequence[str]
    verification_stream_ref: str
    verification_transition_id: str
    verification_policy_root: str
    verification_request_ref: str
    verification_revision: int
    verification_head_root: str
    verification_snapshot_root: str
    verification_set_root: str
    verification_current_step: int
    verification_expires_at_step: int
    verification_record_count: int
    clusters: Sequence[MembershipClusterV2]
    cluster_count: int
    principal_count: int
    membership_root: str = ""
    schema: str = MEMBERSHIP_SNAPSHOT_SCHEMA_V2
    state_schema: str = MEMBERSHIP_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        _validate_snapshot_context(self)
        canonical = canonical_membership_clusters_v2(self.clusters)
        object.__setattr__(self, "clusters", canonical)
        cluster_count = len(canonical)
        principal_count = sum(len(item.principals) for item in canonical)
        if (
            self.cluster_count != cluster_count
            or self.principal_count != principal_count
        ):
            raise ValueError("membership projection counts are mismatched")
        expected_membership_root = membership_projection_root_v2(
            membership_policy_root=self.membership_policy_root,
            verification_set_root=self.verification_set_root,
            protocol_ref=self.protocol_ref,
            run_ref=self.run_ref,
            target_ref=self.target_ref,
            epoch=self.epoch,
            clusters=canonical,
        )
        if self.membership_root not in ("", expected_membership_root):
            raise ValueError("membership_root is mismatched")
        object.__setattr__(self, "membership_root", expected_membership_root)
        expected_snapshot_root = _root("snapshot", self._body())
        if self.snapshot_root not in ("", expected_snapshot_root):
            raise ValueError("membership snapshot_root is mismatched")
        object.__setattr__(self, "snapshot_root", expected_snapshot_root)
        if len(self.canonical_bytes()) > MAX_MEMBERSHIP_SNAPSHOT_BYTES_V2:
            raise ValueError("membership snapshot exceeds its byte bound")

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
            "membership_policy_root": self.membership_policy_root,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "observed_epoch": self.observed_epoch,
            "request_ref": self.request_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "snapshot_ref": self.snapshot_ref,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "parent_epoch": self.parent_epoch,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "issued_at_step": self.issued_at_step,
            "expires_at_step": self.expires_at_step,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "membership_method": self.membership_method,
            "provenance_ref": self.provenance_ref,
            "source_trace_roots": list(self.source_trace_roots),
            "verification_stream_ref": self.verification_stream_ref,
            "verification_transition_id": self.verification_transition_id,
            "verification_policy_root": self.verification_policy_root,
            "verification_request_ref": self.verification_request_ref,
            "verification_revision": self.verification_revision,
            "verification_head_root": self.verification_head_root,
            "verification_snapshot_root": self.verification_snapshot_root,
            "verification_set_root": self.verification_set_root,
            "verification_current_step": self.verification_current_step,
            "verification_expires_at_step": self.verification_expires_at_step,
            "verification_record_count": self.verification_record_count,
            "clusters": [item.to_dict() for item in self.clusters],
            "cluster_count": self.cluster_count,
            "principal_count": self.principal_count,
            "membership_root": self.membership_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> MembershipSnapshotV2:
        value = _require_exact_mapping_v2(
            payload, _SNAPSHOT_FIELDS, "membership snapshot v2"
        )
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("membership assurance is unsupported") from exc
        raw = _require_exact_array_v2(
            value["clusters"], "membership clusters", limit=MAX_MEMBERSHIP_CLUSTERS_V2
        )
        value["clusters"] = tuple(MembershipClusterV2.from_dict(item) for item in raw)
        value["source_trace_roots"] = tuple(
            _require_exact_array_v2(
                value["source_trace_roots"], "membership source_trace_roots", limit=256
            )
        )
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "membership snapshot v2",
        )
        return decoded


@dataclass(frozen=True, slots=True)
class MembershipCommitRequestV2:
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    observed_epoch: int
    request_ref: str
    stream_ref: str
    transition_id: str
    snapshot: MembershipSnapshotV2
    schema: str = MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2:
            raise ValueError("membership request schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError("membership request canonical version is unsupported")
        if type(self.snapshot) is not MembershipSnapshotV2:
            raise TypeError("membership request requires exact snapshot")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "epoch",
            "observed_epoch",
            "request_ref",
            "stream_ref",
            "transition_id",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(f"membership request {field} is cross-bound")
        expected = _root("commit-request", self._body())
        if self.request_root not in ("", expected):
            raise ValueError("membership request_root is mismatched")
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
            "request_ref": self.request_ref,
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
    def from_dict(cls, payload: object) -> MembershipCommitRequestV2:
        value = _require_exact_mapping_v2(
            payload, _REQUEST_FIELDS, "membership request v2"
        )
        value["snapshot"] = MembershipSnapshotV2.from_dict(value["snapshot"])
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "membership request v2",
        )
        return decoded


def _validate_snapshot_context(snapshot: MembershipSnapshotV2) -> None:
    _validate_snapshot_versions(snapshot)
    _validate_snapshot_roots_and_text(snapshot)
    _validate_snapshot_traces_and_counts(snapshot)
    _validate_snapshot_identity(snapshot)


def _validate_snapshot_versions(snapshot: MembershipSnapshotV2) -> None:
    if (
        snapshot.schema != MEMBERSHIP_SNAPSHOT_SCHEMA_V2
        or snapshot.state_schema != MEMBERSHIP_STATE_SCHEMA_V2
        or snapshot.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
    ):
        raise ValueError("membership snapshot version is unsupported")


def _validate_snapshot_roots_and_text(snapshot: MembershipSnapshotV2) -> None:
    for label, value in (
        ("domain_root", snapshot.domain_root),
        ("authority_policy_root", snapshot.authority_policy_root),
        ("manifest_root", snapshot.manifest_root),
        ("commit_policy_root", snapshot.commit_policy_root),
        ("membership_policy_root", snapshot.membership_policy_root),
        ("parent_snapshot_root", snapshot.parent_snapshot_root),
        ("verification_policy_root", snapshot.verification_policy_root),
        ("verification_head_root", snapshot.verification_head_root),
        ("verification_snapshot_root", snapshot.verification_snapshot_root),
        ("verification_set_root", snapshot.verification_set_root),
    ):
        _require_root(value, f"membership {label}")
    for field in (
        "scope_ref",
        "profile",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "request_ref",
        "stream_ref",
        "transition_id",
        "snapshot_ref",
        "parent_transition_id",
        "mutation_issuer_ref",
        "membership_method",
        "provenance_ref",
        "verification_stream_ref",
        "verification_transition_id",
        "verification_request_ref",
    ):
        _require_bounded_text_v2(getattr(snapshot, field), f"membership {field}")


def _validate_snapshot_traces_and_counts(snapshot: MembershipSnapshotV2) -> None:
    if type(snapshot.assurance) is not CommitAssurance:
        raise TypeError("membership assurance is invalid")
    if snapshot.profile not in COMMIT_PROFILES_BY_ASSURANCE.get(
        snapshot.assurance.value, frozenset()
    ):
        raise ValueError("membership profile and assurance are mismatched")
    object.__setattr__(
        snapshot,
        "source_trace_roots",
        _validated_membership_trace_roots(snapshot.source_trace_roots),
    )
    _validate_membership_snapshot_counts(snapshot)
    _validate_membership_snapshot_timeline(snapshot)


def _validated_membership_trace_roots(value: object) -> tuple[str, ...]:
    """Return the exact canonical non-empty trace-root set."""

    if type(value) not in (list, tuple):
        raise TypeError("membership source_trace_roots require exact array or tuple")
    trace_roots = tuple(cast(Sequence[str], value))
    if (
        not trace_roots
        or len(trace_roots) > 256
        or len(trace_roots) != len(set(trace_roots))
    ):
        raise ValueError("membership source_trace_roots count is invalid")
    for root in trace_roots:
        _require_root(root, "membership source_trace_roots")
    return tuple(sorted(trace_roots))


def _validate_membership_snapshot_counts(snapshot: MembershipSnapshotV2) -> None:
    for field in (
        "epoch",
        "observed_epoch",
        "revision",
        "parent_revision",
        "issued_at_step",
        "expires_at_step",
        "verification_revision",
        "verification_current_step",
        "verification_expires_at_step",
        "verification_record_count",
        "cluster_count",
        "principal_count",
    ):
        _require_count_v2(getattr(snapshot, field), f"membership {field}")
    if snapshot.parent_epoch is not None:
        _require_count_v2(snapshot.parent_epoch, "membership parent_epoch")


def _validate_membership_snapshot_timeline(snapshot: MembershipSnapshotV2) -> None:
    if snapshot.expires_at_step <= snapshot.issued_at_step:
        raise ValueError("membership expiry must follow issuance")
    if snapshot.verification_revision == 0:
        raise ValueError("membership verification revision must be positive")
    if (
        snapshot.verification_current_step > snapshot.issued_at_step
        or snapshot.expires_at_step > snapshot.verification_expires_at_step
        or snapshot.verification_current_step >= snapshot.verification_expires_at_step
        or snapshot.verification_record_count != snapshot.principal_count
    ):
        raise ValueError("membership verification timeline or count is cross-bound")


def _validate_snapshot_identity(snapshot: MembershipSnapshotV2) -> None:
    expected_stream = membership_stream_ref_v2(
        snapshot.scope_ref,
        snapshot.profile,
        snapshot.assurance,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.membership_policy_root,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
    )
    expected_transition = membership_transition_id_v2(
        expected_stream, snapshot.request_ref
    )
    if (
        snapshot.stream_ref != expected_stream
        or snapshot.transition_id != expected_transition
    ):
        raise ValueError("membership lineage identity is mismatched")
    expected_verification_stream = principal_verification_stream_ref_v2(
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
    expected_verification_transition = principal_verification_transition_id_v2(
        expected_verification_stream,
        snapshot.verification_request_ref,
    )
    if (
        snapshot.verification_stream_ref != expected_verification_stream
        or snapshot.verification_transition_id != expected_verification_transition
    ):
        raise ValueError("membership verification lineage identity is mismatched")
    if snapshot.parent_revision == 0:
        if (
            snapshot.revision != 1
            or snapshot.parent_epoch is not None
            or snapshot.parent_transition_id != MEMBERSHIP_GENESIS_TRANSITION_ID_V2
            or snapshot.parent_snapshot_root != MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2
        ):
            raise ValueError("membership genesis lineage is invalid")
    elif (
        snapshot.revision != snapshot.parent_revision + 1
        or snapshot.parent_epoch is None
        or snapshot.epoch <= snapshot.parent_epoch
        or snapshot.parent_transition_id == MEMBERSHIP_GENESIS_TRANSITION_ID_V2
    ):
        raise ValueError("membership revision continuity is invalid")


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
        "membership_policy_root",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "epoch",
        "observed_epoch",
        "request_ref",
        "stream_ref",
        "transition_id",
        "snapshot_ref",
        "revision",
        "parent_revision",
        "parent_epoch",
        "parent_transition_id",
        "parent_snapshot_root",
        "issued_at_step",
        "expires_at_step",
        "mutation_issuer_ref",
        "membership_method",
        "provenance_ref",
        "source_trace_roots",
        "verification_stream_ref",
        "verification_transition_id",
        "verification_policy_root",
        "verification_request_ref",
        "verification_revision",
        "verification_head_root",
        "verification_snapshot_root",
        "verification_set_root",
        "verification_current_step",
        "verification_expires_at_step",
        "verification_record_count",
        "clusters",
        "cluster_count",
        "principal_count",
        "membership_root",
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
        "request_ref",
        "stream_ref",
        "transition_id",
        "snapshot",
        "request_root",
    }
)


__all__ = [
    "MAX_MEMBERSHIP_CLUSTERS_V2",
    "MAX_MEMBERSHIP_PRINCIPALS_V2",
    "MAX_MEMBERSHIP_SNAPSHOT_BYTES_V2",
    "MEMBERSHIP_CLUSTER_SCHEMA_V2",
    "MEMBERSHIP_COMMIT_REQUEST_SCHEMA_V2",
    "MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2",
    "MEMBERSHIP_GENESIS_TRANSITION_ID_V2",
    "MEMBERSHIP_PRINCIPAL_SCHEMA_V2",
    "MEMBERSHIP_SNAPSHOT_SCHEMA_V2",
    "MEMBERSHIP_STATE_SCHEMA_V2",
    "MembershipClusterV2",
    "MembershipCommitRequestV2",
    "MembershipPrincipalV2",
    "MembershipSnapshotV2",
    "canonical_membership_clusters_v2",
    "membership_projection_root_v2",
    "membership_stream_ref_v2",
    "membership_transition_id_v2",
]
