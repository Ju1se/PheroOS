"""Portable, non-authoritative external witness conflict observations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_ROOTS_V2,
    MAX_DISTRIBUTED_SNAPSHOT_BYTES_V2,
    _canonical_bytes,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_text,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitProposalV2,
    DistributedCommitValueV2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedQuorumWitnessV2,
)


DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2 = (
    "pheroos-distributed-witness-conflict-observation-v2"
)


@dataclass(frozen=True, slots=True)
class DistributedWitnessConflictObservationV2:
    """Complete portable evidence; trusted verification remains source-local."""

    observation_ref: str
    proposal: DistributedCommitProposalV2
    witness: DistributedQuorumWitnessV2
    observed_at_step: int
    provenance_ref: str
    source_trace_roots: Sequence[str]
    schema: str = DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    observation_root: str = ""

    _root_field: ClassVar[str] = "observation_root"

    def __post_init__(self) -> None:
        if (
            self.schema != DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed witness observation version is unsupported")
        for field in ("observation_ref", "provenance_ref"):
            _require_text(getattr(self, field), f"distributed observation {field}")
        if type(self.proposal) is not DistributedCommitProposalV2:
            raise TypeError("distributed observation requires exact proposal")
        if type(self.witness) is not DistributedQuorumWitnessV2:
            raise TypeError("distributed observation requires exact witness")
        observed = _require_count(
            self.observed_at_step, "distributed observation observed_at_step"
        )
        if (
            self.proposal.proposed_at_step > observed
            or self.witness.witnessed_at_step > observed
            or observed >= self.witness.expires_at_step
        ):
            raise ValueError("distributed observation timing is invalid")
        if (
            self.witness.proposal_digest != self.proposal.proposal_digest
            or self.witness.semantic_value_root
            != self.proposal.value.semantic_value_root
        ):
            raise ValueError("distributed observation proposal/witness is cross-bound")
        traces = _canonical_texts(
            self.source_trace_roots,
            "distributed observation trace roots",
            maximum=MAX_DISTRIBUTED_ROOTS_V2,
            allow_empty=False,
            roots=True,
        )
        object.__setattr__(self, "source_trace_roots", traces)
        _install_root(
            self,
            "observation_root",
            self.observation_root,
            "witness-conflict-observation",
            self._body(),
        )
        if len(_canonical_bytes(self.to_dict())) > MAX_DISTRIBUTED_SNAPSHOT_BYTES_V2:
            raise ValueError("distributed observation exceeds its byte bound")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "observation_ref": self.observation_ref,
            "proposal": self.proposal.to_dict(),
            "witness": self.witness.to_dict(),
            "observed_at_step": self.observed_at_step,
            "provenance_ref": self.provenance_ref,
            "source_trace_roots": list(self.source_trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "observation_root": self.observation_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedWitnessConflictObservationV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "observation_ref",
                    "proposal",
                    "witness",
                    "observed_at_step",
                    "provenance_ref",
                    "source_trace_roots",
                    "observation_root",
                }
            ),
            "distributed witness conflict observation v2",
        )
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            observation_ref=cast(str, value["observation_ref"]),
            proposal=DistributedCommitProposalV2.from_dict(value["proposal"]),
            witness=DistributedQuorumWitnessV2.from_dict(value["witness"]),
            observed_at_step=cast(int, value["observed_at_step"]),
            provenance_ref=cast(str, value["provenance_ref"]),
            source_trace_roots=cast(
                Sequence[str],
                _exact_array(
                    value["source_trace_roots"],
                    "distributed observation trace roots",
                    allow_empty=False,
                ),
            ),
            observation_root=cast(str, value["observation_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "distributed witness observation v2"
        )
        return decoded


def _validate_conflicting_value_binding_v2(
    observed: DistributedCommitValueV2,
    current: DistributedCommitValueV2,
) -> None:
    """Allow only a distinct current-Decision observation of one sealed value."""

    if (
        type(observed) is not DistributedCommitValueV2
        or type(current) is not DistributedCommitValueV2
    ):
        raise TypeError("distributed conflict value binding requires exact values")
    if observed.semantic_value_root == current.semantic_value_root:
        raise ValueError(
            "distributed conflict observation is not semantically distinct"
        )
    observed_body = observed.to_dict()
    current_body = current.to_dict()
    for field in _OBSERVABLE_DECISION_FIELDS:
        observed_body.pop(field)
        current_body.pop(field)
    if observed_body != current_body:
        raise ValueError("distributed conflict observation changes sealed authority")


_OBSERVABLE_DECISION_FIELDS = frozenset(
    {
        "decision_current_revision",
        "decision_current_transition_id",
        "decision_current_snapshot_root",
        "decision_current_head_root",
        "decision_current_receipt_root",
        "decision_current_inclusion_root",
        "semantic_value_root",
    }
)


__all__ = [
    "DISTRIBUTED_WITNESS_CONFLICT_OBSERVATION_SCHEMA_V2",
    "DistributedWitnessConflictObservationV2",
]
