"""Portable Commit Permission v2 snapshot and mutation request."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypedDict, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import _canonical_bytes
from pheroos.governance._commit_gate_v2.common import (
    COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_PERMISSION_REQUEST_SCHEMA_V2,
    COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2,
    COMMIT_PERMISSION_STATE_SCHEMA_V2,
    _canonical_roots,
    _canonical_size,
    _canonical_texts,
    _install_root,
    _require_bool,
    _require_canonical_wire,
    _require_exact_array,
    _require_exact_mapping,
    commit_permission_stream_ref_v2,
    commit_permission_transition_id_v2,
)
from pheroos.governance._commit_gate_v2.contract_support import (
    _common_snapshot_body,
    _validate_common_snapshot,
)
from pheroos.governance._commit_gate_v2.dependency_contracts import (
    CommitGateDependenciesV2,
    commit_gate_candidate_set_root_v2,
    commit_gate_claims_root_v2,
    commit_permission_policy_root_v2,
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
        "permission_ref",
        "transition_id",
        "revision",
        "parent_revision",
        "parent_transition_id",
        "parent_snapshot_root",
        "mutation_issuer_ref",
        "allowed",
        "candidate_refs",
        "candidate_set_root",
        "claim_roots",
        "claims_root",
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
        "permission_ref",
        "stream_ref",
        "transition_id",
        "snapshot",
        "request_root",
    }
)


class _CommitPermissionSnapshotDecodedV2(TypedDict):
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
    permission_ref: str
    transition_id: str
    revision: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    mutation_issuer_ref: str
    allowed: bool
    candidate_refs: tuple[str, ...]
    candidate_set_root: str
    claim_roots: tuple[str, ...]
    claims_root: str
    issued_at_step: int
    expires_at_step: int
    dependencies: CommitGateDependenciesV2
    evaluation_context_root: str
    schema: str
    state_schema: str
    canonical_version: str
    snapshot_root: str


class _CommitPermissionRequestDecodedV2(TypedDict):
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    permission_ref: str
    stream_ref: str
    transition_id: str
    snapshot: CommitPermissionSnapshotV2
    schema: str
    canonical_version: str
    request_root: str


@dataclass(frozen=True, slots=True)
class CommitPermissionSnapshotV2:
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
    permission_ref: str
    transition_id: str
    revision: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    mutation_issuer_ref: str
    allowed: bool
    candidate_refs: Sequence[str]
    candidate_set_root: str
    claim_roots: Sequence[str]
    claims_root: str
    issued_at_step: int
    expires_at_step: int
    dependencies: CommitGateDependenciesV2
    evaluation_context_root: str
    schema: str = COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2
    state_schema: str = COMMIT_PERMISSION_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2:
            raise ValueError("commit permission snapshot schema is unsupported")
        if self.state_schema != COMMIT_PERMISSION_STATE_SCHEMA_V2:
            raise ValueError("commit permission state schema is unsupported")
        if type(self.assurance) is not CommitAssurance:
            raise TypeError("commit permission assurance is invalid")
        allowed = _require_bool(self.allowed, "commit permission allowed")
        candidates = _canonical_texts(
            self.candidate_refs,
            "commit permission candidate_refs",
            allow_empty=False,
        )
        claims = _canonical_roots(
            self.claim_roots,
            "commit permission claim_roots",
            allow_empty=not allowed,
        )
        object.__setattr__(self, "candidate_refs", candidates)
        object.__setattr__(self, "claim_roots", claims)
        expected_candidates = commit_gate_candidate_set_root_v2(candidates)
        expected_claims = commit_gate_claims_root_v2(claims)
        if self.candidate_set_root not in ("", expected_candidates):
            raise ValueError("commit permission candidate_set_root is mismatched")
        if self.claims_root not in ("", expected_claims):
            raise ValueError("commit permission claims_root is mismatched")
        object.__setattr__(self, "candidate_set_root", expected_candidates)
        object.__setattr__(self, "claims_root", expected_claims)
        expected_policy = commit_permission_policy_root_v2(
            manifest_root=self.manifest_root,
            commit_policy_root=self.commit_policy_root,
            protocol_ref=self.protocol_ref,
            target_ref=self.target_ref,
        )
        stream = commit_permission_stream_ref_v2(
            self.scope_ref, self.protocol_ref, self.run_ref, self.target_ref
        )
        transition = commit_permission_transition_id_v2(stream, self.permission_ref)
        _validate_common_snapshot(
            self,
            expected_policy_root=expected_policy,
            expected_stream_ref=stream,
            expected_transition_id=transition,
            genesis_snapshot_root=COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2,
        )
        _install_root(
            self,
            "snapshot_root",
            self.snapshot_root,
            "permission-snapshot",
            self._body(),
        )
        _canonical_size(self.to_dict(), "commit permission snapshot")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            **_common_snapshot_body(self),
            "permission_ref": self.permission_ref,
            "allowed": self.allowed,
            "candidate_refs": list(self.candidate_refs),
            "candidate_set_root": self.candidate_set_root,
            "claim_roots": list(self.claim_roots),
            "claims_root": self.claims_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitPermissionSnapshotV2:
        value = _require_exact_mapping(
            payload, _SNAPSHOT_FIELDS, "commit permission snapshot v2"
        )
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit permission assurance is unsupported") from exc
        value["candidate_refs"] = tuple(
            _require_exact_array(
                value["candidate_refs"], "commit permission candidate_refs"
            )
        )
        value["claim_roots"] = tuple(
            _require_exact_array(value["claim_roots"], "commit permission claim_roots")
        )
        value["dependencies"] = CommitGateDependenciesV2.from_dict(
            value["dependencies"]
        )
        decoded = cls(**cast(_CommitPermissionSnapshotDecodedV2, value))
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit permission snapshot v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CommitPermissionRequestV2:
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    permission_ref: str
    stream_ref: str
    transition_id: str
    snapshot: CommitPermissionSnapshotV2
    schema: str = COMMIT_PERMISSION_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_PERMISSION_REQUEST_SCHEMA_V2:
            raise ValueError("commit permission request schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError(
                "commit permission request canonical version is unsupported"
            )
        if type(self.snapshot) is not CommitPermissionSnapshotV2:
            raise TypeError("commit permission request requires exact snapshot v2")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "observed_epoch",
            "permission_ref",
            "stream_ref",
            "transition_id",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(f"commit permission request {field} is cross-bound")
        _install_root(
            self,
            "request_root",
            self.request_root,
            "permission-request",
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
            "permission_ref": self.permission_ref,
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
    def from_dict(cls, payload: object) -> CommitPermissionRequestV2:
        value = _require_exact_mapping(
            payload, _REQUEST_FIELDS, "commit permission request v2"
        )
        value["snapshot"] = CommitPermissionSnapshotV2.from_dict(value["snapshot"])
        decoded = cls(**cast(_CommitPermissionRequestDecodedV2, value))
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit permission request v2"
        )
        return decoded


__all__: tuple[str, ...] = ()
