"""Generic lineage envelope over the four fixed distributed lane states."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from hashlib import sha256
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_SNAPSHOT_BYTES_V2,
    _canonical_bytes,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._distributed_v2.dependency_contracts import (
    DistributedDependencyV2,
    canonical_distributed_dependencies_v2,
    distributed_dependency_set_root_v2,
)
from pheroos.governance._distributed_v2.enums import (
    DistributedDependencyRoleV2,
    DistributedLaneStatusV2,
    DistributedLaneV2,
    DistributedMutationKindV2,
)
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
)


DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2 = "pheroos-distributed-lane-snapshot-v2"
DISTRIBUTED_LANE_STATE_SCHEMA_V2 = "pheroos-distributed-lane-state-v2"
DISTRIBUTED_GENESIS_TRANSITION_ID_V2 = "genesis"


DistributedLaneStatePayloadV2 = (
    DistributedEpochStateV2
    | DistributedProposalStateV2
    | DistributedWitnessStateV2
    | DistributedCertificateStateV2
)


def distributed_lane_stream_ref_v2(
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
    lane: DistributedLaneV2,
) -> str:
    if type(lane) is not DistributedLaneV2:
        raise TypeError("distributed stream lane is invalid")
    values = tuple(
        _require_text(value, f"distributed stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    digest = sha256(
        b"\x00".join(item.encode("utf-8") for item in (*values, lane.value))
    ).hexdigest()
    return f"authority:distributed-{lane.value}-v2:{digest}"


def distributed_lane_transition_id_v2(
    stream_ref: str,
    mutation_ref: str,
) -> str:
    stream = _require_text(stream_ref, "distributed transition stream_ref")
    mutation = _require_text(mutation_ref, "distributed transition mutation_ref")
    digest = sha256(stream.encode() + b"\x00" + mutation.encode()).hexdigest()
    return f"transition:distributed-v2:{digest}"


def distributed_genesis_snapshot_root_v2(lane: DistributedLaneV2) -> str:
    if type(lane) is not DistributedLaneV2:
        raise TypeError("distributed genesis lane is invalid")
    return _root(
        "genesis-snapshot",
        {"schema": DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2, "lane": lane.value},
    )


def distributed_genesis_history_root_v2(lane: DistributedLaneV2) -> str:
    if type(lane) is not DistributedLaneV2:
        raise TypeError("distributed genesis lane is invalid")
    return _root(
        "genesis-history",
        {"schema": DISTRIBUTED_LANE_STATE_SCHEMA_V2, "lane": lane.value},
    )


@dataclass(frozen=True, slots=True)
class DistributedLaneSnapshotV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    lane: DistributedLaneV2
    stream_ref: str
    mutation_ref: str
    mutation_issuer_ref: str
    mutation_kind: DistributedMutationKindV2
    transition_id: str
    revision: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    current_epoch: int
    current_step: int
    status: DistributedLaneStatusV2
    state: DistributedLaneStatePayloadV2
    dependencies: Sequence[DistributedDependencyV2]
    dependency_set_root: str
    reason_codes: Sequence[str]
    source_context_root: str
    parent_history_root: str
    parent_history_count: int
    history_root: str
    history_count: int
    schema: str = DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2
    state_schema: str = DISTRIBUTED_LANE_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_state_root: str = ""
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        self._validate_header()
        self._validate_lineage()
        dependencies = canonical_distributed_dependencies_v2(self.dependencies)
        object.__setattr__(self, "dependencies", dependencies)
        expected_set = distributed_dependency_set_root_v2(dependencies)
        if self.dependency_set_root not in ("", expected_set):
            raise ValueError("distributed dependency_set_root is mismatched")
        object.__setattr__(self, "dependency_set_root", expected_set)
        reasons = _canonical_texts(
            self.reason_codes,
            "distributed snapshot reason codes",
            maximum=128,
            allow_empty=False,
        )
        object.__setattr__(self, "reason_codes", reasons)
        self._validate_state()
        _install_root(
            self,
            "snapshot_state_root",
            self.snapshot_state_root,
            "snapshot-state",
            self._state_body(),
        )
        expected_history = _root(
            "history",
            {
                "lane": self.lane.value,
                "parent_history_root": self.parent_history_root,
                "parent_history_count": self.parent_history_count,
                "transition_id": self.transition_id,
                "snapshot_state_root": self.snapshot_state_root,
            },
        )
        if self.history_root not in ("", expected_history):
            raise ValueError("distributed history_root is mismatched")
        object.__setattr__(self, "history_root", expected_history)
        _install_root(
            self,
            "snapshot_root",
            self.snapshot_root,
            "snapshot",
            self._root_body(),
        )
        if len(_canonical_bytes(self.to_dict())) > MAX_DISTRIBUTED_SNAPSHOT_BYTES_V2:
            raise ValueError("distributed snapshot exceeds its byte bound")

    def _validate_header(self) -> None:
        if (
            self.schema != DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2
            or self.state_schema != DISTRIBUTED_LANE_STATE_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed snapshot version is unsupported")
        if type(self.lane) is not DistributedLaneV2:
            raise TypeError("distributed snapshot lane is invalid")
        if type(self.mutation_kind) is not DistributedMutationKindV2:
            raise TypeError("distributed snapshot mutation kind is invalid")
        if type(self.status) is not DistributedLaneStatusV2:
            raise TypeError("distributed snapshot status is invalid")
        for field in (
            "scope_ref",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "stream_ref",
            "mutation_ref",
            "mutation_issuer_ref",
            "transition_id",
            "parent_transition_id",
        ):
            _require_text(getattr(self, field), f"distributed snapshot {field}")
        for field in (
            "domain_root",
            "parent_snapshot_root",
            "source_context_root",
            "parent_history_root",
        ):
            _require_root(getattr(self, field), f"distributed snapshot {field}")
        for field in (
            "revision",
            "parent_revision",
            "current_epoch",
            "current_step",
            "parent_history_count",
            "history_count",
        ):
            _require_count(getattr(self, field), f"distributed snapshot {field}")

    def _validate_lineage(self) -> None:
        if self.stream_ref != distributed_lane_stream_ref_v2(
            self.scope_ref, self.protocol_ref, self.run_ref, self.target_ref, self.lane
        ):
            raise ValueError("distributed snapshot stream is mismatched")
        if self.transition_id != distributed_lane_transition_id_v2(
            self.stream_ref, self.mutation_ref
        ):
            raise ValueError("distributed snapshot transition is mismatched")
        if self.revision < 1 or self.parent_revision != self.revision - 1:
            raise ValueError("distributed snapshot revision is not contiguous")
        if self.history_count != self.parent_history_count + 1:
            raise ValueError("distributed snapshot history count is not contiguous")
        if self.revision == 1 and (
            self.parent_transition_id != DISTRIBUTED_GENESIS_TRANSITION_ID_V2
            or self.parent_snapshot_root
            != distributed_genesis_snapshot_root_v2(self.lane)
            or self.parent_history_root
            != distributed_genesis_history_root_v2(self.lane)
            or self.parent_history_count != 0
        ):
            raise ValueError("distributed snapshot genesis lineage is mismatched")

    def _validate_state(self) -> None:
        expected_type = _STATE_TYPE_BY_LANE[self.lane]
        if type(self.state) is not expected_type:
            raise TypeError("distributed snapshot lane state has wrong exact type")
        state = self.state
        state_epoch = _lane_state_epoch(state)
        if state_epoch != self.current_epoch:
            raise ValueError("distributed snapshot state epoch is mismatched")
        required = _DEPENDENCIES_BY_LANE[self.lane]
        if frozenset(item.role for item in self.dependencies) != required:
            raise ValueError("distributed snapshot dependency set is incomplete")
        allowed = _MUTATIONS_BY_LANE[self.lane]
        if self.mutation_kind not in allowed:
            raise ValueError("distributed snapshot mutation is cross-lane")
        frozen = _lane_state_frozen(state)
        expected_status = (
            DistributedLaneStatusV2.FROZEN
            if frozen
            else DistributedLaneStatusV2.VERIFIED
            if type(state) is DistributedCertificateStateV2
            else DistributedLaneStatusV2.ACTIVE
        )
        if self.status is not expected_status:
            raise ValueError("distributed snapshot status is inconsistent")

    def _state_body(self) -> dict[str, object]:
        return {
            "lane": self.lane.value,
            "mutation_kind": self.mutation_kind.value,
            "current_epoch": self.current_epoch,
            "current_step": self.current_step,
            "status": self.status.value,
            "lane_state_root": self.state.state_root,
            "dependency_set_root": self.dependency_set_root,
            "reason_codes": list(self.reason_codes),
            "source_context_root": self.source_context_root,
        }

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "lane": self.lane.value,
            "stream_ref": self.stream_ref,
            "mutation_ref": self.mutation_ref,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "mutation_kind": self.mutation_kind.value,
            "transition_id": self.transition_id,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "current_epoch": self.current_epoch,
            "current_step": self.current_step,
            "status": self.status.value,
            "lane_state_root": self.state.state_root,
            "dependency_roots": [item.dependency_root for item in self.dependencies],
            "dependency_set_root": self.dependency_set_root,
            "reason_codes": list(self.reason_codes),
            "source_context_root": self.source_context_root,
            "parent_history_root": self.parent_history_root,
            "parent_history_count": self.parent_history_count,
            "history_root": self.history_root,
            "history_count": self.history_count,
            "snapshot_state_root": self.snapshot_state_root,
        }

    def to_dict(self) -> dict[str, object]:
        body = self._root_body()
        body.pop("lane_state_root")
        body.pop("dependency_roots")
        body["state"] = self.state.to_dict()
        body["dependencies"] = [item.to_dict() for item in self.dependencies]
        return {**body, "snapshot_root": self.snapshot_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedLaneSnapshotV2:
        value = _exact_mapping(payload, _SNAPSHOT_FIELDS, "distributed snapshot v2")
        try:
            lane = DistributedLaneV2(cast(str, value["lane"]))
            mutation = DistributedMutationKindV2(cast(str, value["mutation_kind"]))
            status = DistributedLaneStatusV2(cast(str, value["status"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("distributed snapshot enum is unsupported") from exc
        state = _decode_lane_state(lane, value["state"])
        decoded = cls(
            schema=cast(str, value["schema"]),
            state_schema=cast(str, value["state_schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            lane=lane,
            stream_ref=cast(str, value["stream_ref"]),
            mutation_ref=cast(str, value["mutation_ref"]),
            mutation_issuer_ref=cast(str, value["mutation_issuer_ref"]),
            mutation_kind=mutation,
            transition_id=cast(str, value["transition_id"]),
            revision=cast(int, value["revision"]),
            parent_revision=cast(int, value["parent_revision"]),
            parent_transition_id=cast(str, value["parent_transition_id"]),
            parent_snapshot_root=cast(str, value["parent_snapshot_root"]),
            current_epoch=cast(int, value["current_epoch"]),
            current_step=cast(int, value["current_step"]),
            status=status,
            state=state,
            dependencies=tuple(
                DistributedDependencyV2.from_dict(item)
                for item in _exact_array(
                    value["dependencies"],
                    "distributed dependencies",
                    maximum=len(DistributedDependencyRoleV2),
                )
            ),
            dependency_set_root=cast(str, value["dependency_set_root"]),
            reason_codes=cast(
                Sequence[str],
                _exact_array(
                    value["reason_codes"],
                    "distributed reason codes",
                    maximum=128,
                    allow_empty=False,
                ),
            ),
            source_context_root=cast(str, value["source_context_root"]),
            parent_history_root=cast(str, value["parent_history_root"]),
            parent_history_count=cast(int, value["parent_history_count"]),
            history_root=cast(str, value["history_root"]),
            history_count=cast(int, value["history_count"]),
            snapshot_state_root=cast(str, value["snapshot_state_root"]),
            snapshot_root=cast(str, value["snapshot_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "distributed snapshot v2")
        return decoded


def _decode_lane_state(
    lane: DistributedLaneV2, value: object
) -> DistributedLaneStatePayloadV2:
    if lane is DistributedLaneV2.EPOCH:
        return DistributedEpochStateV2.from_dict(value)
    if lane is DistributedLaneV2.PROPOSAL:
        return DistributedProposalStateV2.from_dict(value)
    if lane is DistributedLaneV2.WITNESS:
        return DistributedWitnessStateV2.from_dict(value)
    return DistributedCertificateStateV2.from_dict(value)


def _lane_state_epoch(state: DistributedLaneStatePayloadV2) -> int:
    if type(state) is DistributedEpochStateV2:
        return state.transition_certificate.to_epoch
    if type(state) is DistributedProposalStateV2:
        return state.epoch
    if type(state) is DistributedWitnessStateV2:
        return state.epoch
    if type(state) is DistributedCertificateStateV2:
        return state.epoch
    raise TypeError("distributed snapshot state is unsupported")


def _lane_state_frozen(state: DistributedLaneStatePayloadV2) -> bool:
    if type(state) is DistributedWitnessStateV2:
        return state.frozen
    if type(state) is DistributedCertificateStateV2:
        return state.frozen
    return False


_STATE_TYPE_BY_LANE: Mapping[DistributedLaneV2, type[DistributedLaneStatePayloadV2]] = (
    MappingProxyType(
        {
            DistributedLaneV2.EPOCH: DistributedEpochStateV2,
            DistributedLaneV2.PROPOSAL: DistributedProposalStateV2,
            DistributedLaneV2.WITNESS: DistributedWitnessStateV2,
            DistributedLaneV2.CERTIFICATE: DistributedCertificateStateV2,
        }
    )
)
_DEPENDENCIES_BY_LANE: Mapping[
    DistributedLaneV2, frozenset[DistributedDependencyRoleV2]
] = MappingProxyType(
    {
        DistributedLaneV2.EPOCH: frozenset(
            {
                DistributedDependencyRoleV2.MEMBERSHIP,
                DistributedDependencyRoleV2.PRINCIPAL_VERIFICATION,
                DistributedDependencyRoleV2.PROPOSAL,
                DistributedDependencyRoleV2.WITNESS,
                DistributedDependencyRoleV2.CERTIFICATE,
            }
        ),
        DistributedLaneV2.PROPOSAL: frozenset(
            {
                DistributedDependencyRoleV2.EPOCH,
                DistributedDependencyRoleV2.DECISION,
                DistributedDependencyRoleV2.CENTRAL_CERTIFICATE,
                DistributedDependencyRoleV2.MEMBERSHIP,
                DistributedDependencyRoleV2.PRINCIPAL_VERIFICATION,
            }
        ),
        DistributedLaneV2.WITNESS: frozenset(
            {
                DistributedDependencyRoleV2.PROPOSAL,
                DistributedDependencyRoleV2.EPOCH,
                DistributedDependencyRoleV2.DECISION,
                DistributedDependencyRoleV2.CENTRAL_CERTIFICATE,
                DistributedDependencyRoleV2.MEMBERSHIP,
                DistributedDependencyRoleV2.PRINCIPAL_VERIFICATION,
            }
        ),
        DistributedLaneV2.CERTIFICATE: frozenset(
            {
                DistributedDependencyRoleV2.PROPOSAL,
                DistributedDependencyRoleV2.WITNESS,
                DistributedDependencyRoleV2.EPOCH,
                DistributedDependencyRoleV2.DECISION,
                DistributedDependencyRoleV2.CENTRAL_CERTIFICATE,
                DistributedDependencyRoleV2.MEMBERSHIP,
                DistributedDependencyRoleV2.PRINCIPAL_VERIFICATION,
            }
        ),
    }
)
_MUTATIONS_BY_LANE: Mapping[DistributedLaneV2, frozenset[DistributedMutationKindV2]] = (
    MappingProxyType(
        {
            DistributedLaneV2.EPOCH: frozenset(
                {
                    DistributedMutationKindV2.EPOCH_INITIALIZED,
                    DistributedMutationKindV2.EPOCH_TRANSITIONED,
                }
            ),
            DistributedLaneV2.PROPOSAL: frozenset(
                {
                    DistributedMutationKindV2.PROPOSAL_RECORDED,
                    DistributedMutationKindV2.PROPOSAL_SEMANTIC_RETRY,
                }
            ),
            DistributedLaneV2.WITNESS: frozenset(
                {
                    DistributedMutationKindV2.WITNESS_RECORDED,
                    DistributedMutationKindV2.WITNESS_RETRY,
                    DistributedMutationKindV2.EQUIVOCATION_FROZEN,
                }
            ),
            DistributedLaneV2.CERTIFICATE: frozenset(
                {
                    DistributedMutationKindV2.CERTIFICATE_VERIFIED,
                    DistributedMutationKindV2.CERTIFICATE_RETRY,
                    DistributedMutationKindV2.CERTIFICATE_CONFLICT_FROZEN,
                }
            ),
        }
    )
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "state_schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "lane",
        "stream_ref",
        "mutation_ref",
        "mutation_issuer_ref",
        "mutation_kind",
        "transition_id",
        "revision",
        "parent_revision",
        "parent_transition_id",
        "parent_snapshot_root",
        "current_epoch",
        "current_step",
        "status",
        "state",
        "dependencies",
        "dependency_set_root",
        "reason_codes",
        "source_context_root",
        "parent_history_root",
        "parent_history_count",
        "history_root",
        "history_count",
        "snapshot_state_root",
        "snapshot_root",
    }
)


__all__ = [
    "DISTRIBUTED_GENESIS_TRANSITION_ID_V2",
    "DISTRIBUTED_LANE_SNAPSHOT_SCHEMA_V2",
    "DISTRIBUTED_LANE_STATE_SCHEMA_V2",
    "DistributedLaneSnapshotV2",
    "DistributedLaneStatePayloadV2",
    "distributed_genesis_history_root_v2",
    "distributed_genesis_snapshot_root_v2",
    "distributed_lane_stream_ref_v2",
    "distributed_lane_transition_id_v2",
]
