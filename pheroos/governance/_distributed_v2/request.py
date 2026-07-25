"""Portable complete-replacement request for every distributed lane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._distributed_v2.common import (
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.governance._distributed_v2.state_contracts import (
    DistributedLaneSnapshotV2,
    distributed_lane_stream_ref_v2,
    distributed_lane_transition_id_v2,
)


DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2 = "pheroos-distributed-advance-request-v2"


@dataclass(frozen=True, slots=True)
class DistributedAdvanceRequestV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    mutation_ref: str
    mutation_issuer_ref: str
    current_step: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    snapshot: DistributedLaneSnapshotV2
    schema: str = DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    stream_ref: str = ""
    transition_id: str = ""
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        if (
            self.schema != DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed request version is unsupported")
        for field in (
            "scope_ref",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "mutation_ref",
            "mutation_issuer_ref",
            "parent_transition_id",
        ):
            _require_text(getattr(self, field), f"distributed request {field}")
        for field in ("domain_root", "parent_snapshot_root"):
            _require_root(getattr(self, field), f"distributed request {field}")
        for field in ("observed_epoch", "current_step", "parent_revision"):
            _require_count(getattr(self, field), f"distributed request {field}")
        if type(self.snapshot) is not DistributedLaneSnapshotV2:
            raise TypeError("distributed request requires exact snapshot")
        stream = distributed_lane_stream_ref_v2(
            self.scope_ref,
            self.protocol_ref,
            self.run_ref,
            self.target_ref,
            self.snapshot.lane,
        )
        transition = distributed_lane_transition_id_v2(stream, self.mutation_ref)
        if self.stream_ref not in ("", stream) or self.transition_id not in (
            "",
            transition,
        ):
            raise ValueError("distributed request identity is mismatched")
        object.__setattr__(self, "stream_ref", stream)
        object.__setattr__(self, "transition_id", transition)
        observed = (
            self.snapshot.domain_root,
            self.snapshot.scope_ref,
            self.snapshot.protocol_ref,
            self.snapshot.run_ref,
            self.snapshot.target_ref,
            self.snapshot.current_epoch,
            self.snapshot.mutation_ref,
            self.snapshot.mutation_issuer_ref,
            self.snapshot.current_step,
            self.snapshot.parent_revision,
            self.snapshot.parent_transition_id,
            self.snapshot.parent_snapshot_root,
            self.snapshot.stream_ref,
            self.snapshot.transition_id,
        )
        expected = (
            self.domain_root,
            self.scope_ref,
            self.protocol_ref,
            self.run_ref,
            self.target_ref,
            self.observed_epoch,
            self.mutation_ref,
            self.mutation_issuer_ref,
            self.current_step,
            self.parent_revision,
            self.parent_transition_id,
            self.parent_snapshot_root,
            stream,
            transition,
        )
        if observed != expected:
            raise ValueError("distributed request snapshot is cross-bound")
        _install_root(
            self,
            "request_root",
            self.request_root,
            "advance-request",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "mutation_ref": self.mutation_ref,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "current_step": self.current_step,
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "snapshot_root": self.snapshot.snapshot_root,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
        }

    def to_dict(self) -> dict[str, object]:
        body = self._root_body()
        body.pop("snapshot_root")
        body["snapshot"] = self.snapshot.to_dict()
        return {**body, "request_root": self.request_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedAdvanceRequestV2:
        value = _exact_mapping(payload, _REQUEST_FIELDS, "distributed request v2")
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            observed_epoch=cast(int, value["observed_epoch"]),
            mutation_ref=cast(str, value["mutation_ref"]),
            mutation_issuer_ref=cast(str, value["mutation_issuer_ref"]),
            current_step=cast(int, value["current_step"]),
            parent_revision=cast(int, value["parent_revision"]),
            parent_transition_id=cast(str, value["parent_transition_id"]),
            parent_snapshot_root=cast(str, value["parent_snapshot_root"]),
            snapshot=DistributedLaneSnapshotV2.from_dict(value["snapshot"]),
            stream_ref=cast(str, value["stream_ref"]),
            transition_id=cast(str, value["transition_id"]),
            request_root=cast(str, value["request_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "distributed request v2")
        return decoded


_REQUEST_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "observed_epoch",
        "mutation_ref",
        "mutation_issuer_ref",
        "current_step",
        "parent_revision",
        "parent_transition_id",
        "parent_snapshot_root",
        "snapshot",
        "stream_ref",
        "transition_id",
        "request_root",
    }
)


__all__ = ["DISTRIBUTED_ADVANCE_REQUEST_SCHEMA_V2", "DistributedAdvanceRequestV2"]
