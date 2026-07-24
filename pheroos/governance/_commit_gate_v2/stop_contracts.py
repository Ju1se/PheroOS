"""Portable Commit Stop v2 snapshot and mutation request."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypedDict, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import _canonical_bytes
from pheroos.governance._commit_gate_v2.common import (
    COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_STOP_REQUEST_SCHEMA_V2,
    COMMIT_STOP_SNAPSHOT_SCHEMA_V2,
    COMMIT_STOP_STATE_SCHEMA_V2,
    _canonical_size,
    _canonical_texts,
    _install_root,
    _require_bool,
    _require_canonical_wire,
    _require_exact_array,
    _require_exact_mapping,
    commit_stop_stream_ref_v2,
    commit_stop_transition_id_v2,
)
from pheroos.governance._commit_gate_v2.contract_support import (
    _common_snapshot_body,
    _validate_common_snapshot,
)
from pheroos.governance._commit_gate_v2.dependency_contracts import (
    CommitGateDependenciesV2,
    commit_stop_policy_root_v2,
    commit_stop_reasons_root_v2,
)


_SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "state_schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "manifest_root",
        "commit_policy_root",
        "policy_root",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "observed_epoch",
        "current_step",
        "stream_ref",
        "resolution_ref",
        "transition_id",
        "revision",
        "parent_revision",
        "parent_transition_id",
        "parent_snapshot_root",
        "mutation_issuer_ref",
        "blocked",
        "reason_codes",
        "reason_root",
        "issued_at_step",
        "expires_at_step",
        "dependencies",
        "evaluation_context_root",
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
        "observed_epoch",
        "resolution_ref",
        "stream_ref",
        "transition_id",
        "snapshot",
        "request_root",
    }
)


class _CommitStopSnapshotDecodedV2(TypedDict):
    domain_root: str
    scope_ref: str
    manifest_root: str
    commit_policy_root: str
    policy_root: str
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    current_step: int
    stream_ref: str
    resolution_ref: str
    transition_id: str
    revision: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    mutation_issuer_ref: str
    blocked: bool
    reason_codes: tuple[str, ...]
    reason_root: str
    issued_at_step: int
    expires_at_step: int
    dependencies: CommitGateDependenciesV2
    evaluation_context_root: str
    schema: str
    state_schema: str
    canonical_version: str
    snapshot_root: str


class _CommitStopRequestDecodedV2(TypedDict):
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    resolution_ref: str
    stream_ref: str
    transition_id: str
    snapshot: CommitStopSnapshotV2
    schema: str
    canonical_version: str
    request_root: str


@dataclass(frozen=True, slots=True)
class CommitStopSnapshotV2:
    domain_root: str
    scope_ref: str
    manifest_root: str
    commit_policy_root: str
    policy_root: str
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    current_step: int
    stream_ref: str
    resolution_ref: str
    transition_id: str
    revision: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    mutation_issuer_ref: str
    blocked: bool
    reason_codes: Sequence[str]
    reason_root: str
    issued_at_step: int
    expires_at_step: int
    dependencies: CommitGateDependenciesV2
    evaluation_context_root: str
    schema: str = COMMIT_STOP_SNAPSHOT_SCHEMA_V2
    state_schema: str = COMMIT_STOP_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_STOP_SNAPSHOT_SCHEMA_V2:
            raise ValueError("commit stop snapshot schema is unsupported")
        if self.state_schema != COMMIT_STOP_STATE_SCHEMA_V2:
            raise ValueError("commit stop state schema is unsupported")
        if type(self.assurance) is not CommitAssurance:
            raise TypeError("commit stop assurance is invalid")
        canonical_reasons = _canonical_texts(
            self.reason_codes, "commit stop reason_codes", allow_empty=True
        )
        object.__setattr__(self, "reason_codes", canonical_reasons)
        blocked = _require_bool(self.blocked, "commit stop blocked")
        if blocked and not canonical_reasons:
            raise ValueError("blocked commit stop requires at least one reason")
        expected_reason_root = commit_stop_reasons_root_v2(canonical_reasons)
        if self.reason_root not in ("", expected_reason_root):
            raise ValueError("commit stop reason_root is mismatched")
        object.__setattr__(self, "reason_root", expected_reason_root)
        expected_policy = commit_stop_policy_root_v2(
            manifest_root=self.manifest_root,
            commit_policy_root=self.commit_policy_root,
            protocol_ref=self.protocol_ref,
            target_ref=self.target_ref,
        )
        stream = commit_stop_stream_ref_v2(
            self.scope_ref, self.protocol_ref, self.run_ref, self.target_ref
        )
        transition = commit_stop_transition_id_v2(stream, self.resolution_ref)
        _validate_common_snapshot(
            self,
            expected_policy_root=expected_policy,
            expected_stream_ref=stream,
            expected_transition_id=transition,
            genesis_snapshot_root=COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2,
        )
        _install_root(
            self,
            "snapshot_root",
            self.snapshot_root,
            "stop-snapshot",
            self._body(),
        )
        _canonical_size(self.to_dict(), "commit stop snapshot")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            **_common_snapshot_body(self),
            "resolution_ref": self.resolution_ref,
            "blocked": self.blocked,
            "reason_codes": list(self.reason_codes),
            "reason_root": self.reason_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitStopSnapshotV2:
        value = _require_exact_mapping(
            payload, _SNAPSHOT_FIELDS, "commit stop snapshot v2"
        )
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit stop assurance is unsupported") from exc
        reasons = _require_exact_array(value["reason_codes"], "commit stop reasons")
        value["reason_codes"] = tuple(reasons)
        value["dependencies"] = CommitGateDependenciesV2.from_dict(
            value["dependencies"]
        )
        decoded = cls(**cast(_CommitStopSnapshotDecodedV2, value))
        _require_canonical_wire(payload, decoded.to_dict(), "commit stop snapshot v2")
        return decoded


@dataclass(frozen=True, slots=True)
class CommitStopRequestV2:
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    resolution_ref: str
    stream_ref: str
    transition_id: str
    snapshot: CommitStopSnapshotV2
    schema: str = COMMIT_STOP_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_STOP_REQUEST_SCHEMA_V2:
            raise ValueError("commit stop request schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError("commit stop request canonical version is unsupported")
        if type(self.snapshot) is not CommitStopSnapshotV2:
            raise TypeError("commit stop request requires exact snapshot v2")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "observed_epoch",
            "resolution_ref",
            "stream_ref",
            "transition_id",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(f"commit stop request {field} is cross-bound")
        _install_root(
            self,
            "request_root",
            self.request_root,
            "stop-request",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "resolution_ref": self.resolution_ref,
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
    def from_dict(cls, payload: object) -> CommitStopRequestV2:
        value = _require_exact_mapping(
            payload, _REQUEST_FIELDS, "commit stop request v2"
        )
        value["snapshot"] = CommitStopSnapshotV2.from_dict(value["snapshot"])
        decoded = cls(**cast(_CommitStopRequestDecodedV2, value))
        _require_canonical_wire(payload, decoded.to_dict(), "commit stop request v2")
        return decoded


__all__: tuple[str, ...] = ()
