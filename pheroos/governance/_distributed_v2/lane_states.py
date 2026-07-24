"""Complete replacement payloads for the four fixed distributed lanes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypeVar, cast

from pheroos.governance._distributed_v2.certificate_contracts import (
    DistributedCommitCertificateV2,
)
from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_CERTIFICATES_V2,
    MAX_DISTRIBUTED_PROPOSALS_V2,
    MAX_DISTRIBUTED_ROOTS_V2,
    MAX_DISTRIBUTED_WITNESSES_V2,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.governance._distributed_v2.conflict_contracts import (
    DistributedWitnessConflictObservationV2,
)
from pheroos.governance._distributed_v2.epoch_contracts import (
    DistributedEpochTransitionCertificateV2,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitProposalV2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedQuorumWitnessV2,
)


@dataclass(frozen=True, slots=True)
class DistributedEquivocationFindingV2:
    principal_ref: str
    epoch: int
    first_semantic_value_root: str
    second_semantic_value_root: str
    first_witness_root: str
    second_witness_root: str
    finding_root: str = ""
    conflict_observation: DistributedWitnessConflictObservationV2 | None = None

    _root_field: ClassVar[str] = "finding_root"

    def __post_init__(self) -> None:
        _require_text(self.principal_ref, "distributed finding principal_ref")
        _require_count(self.epoch, "distributed finding epoch")
        for field in (
            "first_semantic_value_root",
            "second_semantic_value_root",
            "first_witness_root",
            "second_witness_root",
        ):
            _require_root(getattr(self, field), f"distributed finding {field}")
        if self.first_semantic_value_root == self.second_semantic_value_root:
            raise ValueError("distributed finding does not prove equivocation")
        ordered = sorted(
            (
                (self.first_semantic_value_root, self.first_witness_root),
                (self.second_semantic_value_root, self.second_witness_root),
            )
        )
        object.__setattr__(self, "first_semantic_value_root", ordered[0][0])
        object.__setattr__(self, "first_witness_root", ordered[0][1])
        object.__setattr__(self, "second_semantic_value_root", ordered[1][0])
        object.__setattr__(self, "second_witness_root", ordered[1][1])
        observation = self.conflict_observation
        if observation is not None and type(observation) is not (
            DistributedWitnessConflictObservationV2
        ):
            raise TypeError("distributed finding observation has wrong exact type")
        if observation is not None and (
            observation.witness.principal_ref != self.principal_ref
            or observation.witness.epoch != self.epoch
            or (
                observation.witness.semantic_value_root,
                observation.witness.witness_root,
            )
            not in set(ordered)
        ):
            raise ValueError("distributed finding observation is cross-bound")
        _install_root(
            self, "finding_root", self.finding_root, "equivocation", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "principal_ref": self.principal_ref,
            "epoch": self.epoch,
            "first_semantic_value_root": self.first_semantic_value_root,
            "second_semantic_value_root": self.second_semantic_value_root,
            "first_witness_root": self.first_witness_root,
            "second_witness_root": self.second_witness_root,
            "conflict_observation_root": (
                ""
                if self.conflict_observation is None
                else self.conflict_observation.observation_root
            ),
        }

    def to_dict(self) -> dict[str, object]:
        body = self._body()
        body.pop("conflict_observation_root")
        return {
            **body,
            "conflict_observation": (
                None
                if self.conflict_observation is None
                else self.conflict_observation.to_dict()
            ),
            "finding_root": self.finding_root,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DistributedEquivocationFindingV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "principal_ref",
                    "epoch",
                    "first_semantic_value_root",
                    "second_semantic_value_root",
                    "first_witness_root",
                    "second_witness_root",
                    "conflict_observation",
                    "finding_root",
                }
            ),
            "distributed equivocation finding v2",
        )
        decoded = cls(
            principal_ref=cast(str, value["principal_ref"]),
            epoch=cast(int, value["epoch"]),
            first_semantic_value_root=cast(str, value["first_semantic_value_root"]),
            second_semantic_value_root=cast(str, value["second_semantic_value_root"]),
            first_witness_root=cast(str, value["first_witness_root"]),
            second_witness_root=cast(str, value["second_witness_root"]),
            finding_root=cast(str, value["finding_root"]),
            conflict_observation=(
                None
                if value["conflict_observation"] is None
                else DistributedWitnessConflictObservationV2.from_dict(
                    value["conflict_observation"]
                )
            ),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "distributed finding v2")
        return decoded


@dataclass(frozen=True, slots=True)
class DistributedEpochStateV2:
    transition_certificate: DistributedEpochTransitionCertificateV2
    conflict_history_roots: Sequence[str]
    state_root: str = ""

    _root_field: ClassVar[str] = "state_root"

    def __post_init__(self) -> None:
        if (
            type(self.transition_certificate)
            is not DistributedEpochTransitionCertificateV2
        ):
            raise TypeError("distributed epoch state requires exact certificate")
        history = _canonical_texts(
            self.conflict_history_roots,
            "distributed epoch conflict history",
            maximum=MAX_DISTRIBUTED_ROOTS_V2,
            roots=True,
        )
        if history != tuple(self.transition_certificate.conflict_history_roots):
            raise ValueError("distributed epoch conflict history is mismatched")
        object.__setattr__(self, "conflict_history_roots", history)
        _install_root(
            self, "state_root", self.state_root, "epoch-state", self._root_body()
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "transition_certificate_root": self.transition_certificate.certificate_root,
            "conflict_history_roots": list(self.conflict_history_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "transition_certificate": self.transition_certificate.to_dict(),
            "conflict_history_roots": list(self.conflict_history_roots),
            "state_root": self.state_root,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DistributedEpochStateV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {"transition_certificate", "conflict_history_roots", "state_root"}
            ),
            "distributed epoch state v2",
        )
        decoded = cls(
            transition_certificate=DistributedEpochTransitionCertificateV2.from_dict(
                value["transition_certificate"]
            ),
            conflict_history_roots=cast(
                Sequence[str],
                _exact_array(
                    value["conflict_history_roots"], "distributed epoch history"
                ),
            ),
            state_root=cast(str, value["state_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "distributed epoch state v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class DistributedProposalStateV2:
    epoch: int
    proposals: Sequence[DistributedCommitProposalV2]
    state_root: str = ""

    _root_field: ClassVar[str] = "state_root"

    def __post_init__(self) -> None:
        _require_count(self.epoch, "distributed proposal state epoch")
        values = _canonical_proposals(self.proposals)
        if any(item.value.epoch != self.epoch for item in values):
            raise ValueError("distributed proposal state is cross-epoch")
        object.__setattr__(self, "proposals", values)
        _install_root(
            self, "state_root", self.state_root, "proposal-state", self._root_body()
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "proposal_digests": [item.proposal_digest for item in self.proposals],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "proposals": [item.to_dict() for item in self.proposals],
            "state_root": self.state_root,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DistributedProposalStateV2:
        value = _exact_mapping(
            payload,
            frozenset({"epoch", "proposals", "state_root"}),
            "distributed proposal state v2",
        )
        decoded = cls(
            epoch=cast(int, value["epoch"]),
            proposals=tuple(
                DistributedCommitProposalV2.from_dict(item)
                for item in _exact_array(
                    value["proposals"],
                    "distributed proposals",
                    maximum=MAX_DISTRIBUTED_PROPOSALS_V2,
                    allow_empty=False,
                )
            ),
            state_root=cast(str, value["state_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "distributed proposal state v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class DistributedWitnessStateV2:
    epoch: int
    witnesses: Sequence[DistributedQuorumWitnessV2]
    equivocations: Sequence[DistributedEquivocationFindingV2]
    state_root: str = ""

    _root_field: ClassVar[str] = "state_root"

    def __post_init__(self) -> None:
        _require_count(self.epoch, "distributed witness state epoch")
        witnesses = _canonical_witnesses(self.witnesses)
        findings = _canonical_findings(self.equivocations)
        if any(item.epoch != self.epoch for item in witnesses) or any(
            item.epoch != self.epoch for item in findings
        ):
            raise ValueError("distributed witness state is cross-epoch")
        object.__setattr__(self, "witnesses", witnesses)
        object.__setattr__(self, "equivocations", findings)
        _validate_finding_observations(witnesses, findings)
        _install_root(
            self, "state_root", self.state_root, "witness-state", self._root_body()
        )

    @property
    def frozen(self) -> bool:
        return bool(self.equivocations)

    def _root_body(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "witness_roots": [item.witness_root for item in self.witnesses],
            "finding_roots": [item.finding_root for item in self.equivocations],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "witnesses": [item.to_dict() for item in self.witnesses],
            "equivocations": [item.to_dict() for item in self.equivocations],
            "state_root": self.state_root,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DistributedWitnessStateV2:
        value = _exact_mapping(
            payload,
            frozenset({"epoch", "witnesses", "equivocations", "state_root"}),
            "distributed witness state v2",
        )
        decoded = cls(
            epoch=cast(int, value["epoch"]),
            witnesses=tuple(
                DistributedQuorumWitnessV2.from_dict(item)
                for item in _exact_array(
                    value["witnesses"],
                    "distributed witnesses",
                    maximum=MAX_DISTRIBUTED_WITNESSES_V2,
                    allow_empty=False,
                )
            ),
            equivocations=tuple(
                DistributedEquivocationFindingV2.from_dict(item)
                for item in _exact_array(
                    value["equivocations"],
                    "distributed findings",
                    maximum=MAX_DISTRIBUTED_ROOTS_V2,
                )
            ),
            state_root=cast(str, value["state_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "distributed witness state v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class DistributedCertificateStateV2:
    epoch: int
    certificates: Sequence[DistributedCommitCertificateV2]
    conflict_roots: Sequence[str]
    state_root: str = ""

    _root_field: ClassVar[str] = "state_root"

    def __post_init__(self) -> None:
        _require_count(self.epoch, "distributed certificate state epoch")
        certificates = _canonical_certificates(self.certificates)
        conflicts = _canonical_texts(
            self.conflict_roots,
            "distributed certificate conflicts",
            maximum=MAX_DISTRIBUTED_ROOTS_V2,
            roots=True,
        )
        if any(item.value.epoch != self.epoch for item in certificates):
            raise ValueError("distributed certificate state is cross-epoch")
        semantic_values = {item.value.semantic_value_root for item in certificates}
        if len(semantic_values) > 1 and not conflicts:
            raise ValueError("distributed certificate conflict is not frozen")
        if conflicts and len(semantic_values) < 2:
            raise ValueError("distributed certificate conflict lacks distinct values")
        object.__setattr__(self, "certificates", certificates)
        object.__setattr__(self, "conflict_roots", conflicts)
        _install_root(
            self, "state_root", self.state_root, "certificate-state", self._root_body()
        )

    @property
    def frozen(self) -> bool:
        return bool(self.conflict_roots)

    def _root_body(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "certificate_roots": [item.certificate_root for item in self.certificates],
            "conflict_roots": list(self.conflict_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "certificates": [item.to_dict() for item in self.certificates],
            "conflict_roots": list(self.conflict_roots),
            "state_root": self.state_root,
        }

    @classmethod
    def from_dict(cls, payload: object) -> DistributedCertificateStateV2:
        value = _exact_mapping(
            payload,
            frozenset({"epoch", "certificates", "conflict_roots", "state_root"}),
            "distributed certificate state v2",
        )
        decoded = cls(
            epoch=cast(int, value["epoch"]),
            certificates=tuple(
                DistributedCommitCertificateV2.from_dict(item)
                for item in _exact_array(
                    value["certificates"],
                    "distributed certificates",
                    maximum=MAX_DISTRIBUTED_CERTIFICATES_V2,
                    allow_empty=False,
                )
            ),
            conflict_roots=cast(
                Sequence[str],
                _exact_array(
                    value["conflict_roots"], "distributed certificate conflicts"
                ),
            ),
            state_root=cast(str, value["state_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "distributed certificate state v2"
        )
        return decoded


def _canonical_proposals(
    values: Sequence[DistributedCommitProposalV2],
) -> tuple[DistributedCommitProposalV2, ...]:
    return _canonical_records(
        values,
        DistributedCommitProposalV2,
        MAX_DISTRIBUTED_PROPOSALS_V2,
        "proposal_digest",
        "proposals",
    )


def _canonical_witnesses(
    values: Sequence[DistributedQuorumWitnessV2],
) -> tuple[DistributedQuorumWitnessV2, ...]:
    return _canonical_records(
        values,
        DistributedQuorumWitnessV2,
        MAX_DISTRIBUTED_WITNESSES_V2,
        "witness_root",
        "witnesses",
    )


def _canonical_findings(
    values: Sequence[DistributedEquivocationFindingV2],
) -> tuple[DistributedEquivocationFindingV2, ...]:
    if type(values) not in (list, tuple):
        raise TypeError("distributed findings require exact sequence")
    if not values:
        return ()
    return _canonical_records(
        values,
        DistributedEquivocationFindingV2,
        MAX_DISTRIBUTED_ROOTS_V2,
        "finding_root",
        "findings",
    )


def _validate_finding_observations(
    witnesses: tuple[DistributedQuorumWitnessV2, ...],
    findings: tuple[DistributedEquivocationFindingV2, ...],
) -> None:
    roots = {item.witness_root for item in witnesses}
    for finding in findings:
        observation = finding.conflict_observation
        if observation is not None and observation.witness.witness_root not in roots:
            raise ValueError("distributed finding observation witness is not durable")


def _canonical_certificates(
    values: Sequence[DistributedCommitCertificateV2],
) -> tuple[DistributedCommitCertificateV2, ...]:
    return _canonical_records(
        values,
        DistributedCommitCertificateV2,
        MAX_DISTRIBUTED_CERTIFICATES_V2,
        "certificate_root",
        "certificates",
    )


_RecordT = TypeVar("_RecordT")


def _canonical_records(
    values: Sequence[_RecordT],
    expected: type[_RecordT],
    maximum: int,
    root_field: str,
    label: str,
) -> tuple[_RecordT, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"distributed {label} require exact sequence")
    records = tuple(values)
    if (
        not records
        or len(records) > maximum
        or any(type(item) is not expected for item in records)
    ):
        raise ValueError(f"distributed {label} count or type is invalid")
    roots = tuple(cast(str, getattr(item, root_field)) for item in records)
    if len(roots) != len(set(roots)):
        raise ValueError(f"distributed {label} repeat roots")
    return tuple(
        item
        for _, item in sorted(
            zip(roots, records, strict=True), key=lambda pair: pair[0].encode("utf-8")
        )
    )


__all__ = [
    "DistributedCertificateStateV2",
    "DistributedEpochStateV2",
    "DistributedEquivocationFindingV2",
    "DistributedProposalStateV2",
    "DistributedWitnessStateV2",
]
