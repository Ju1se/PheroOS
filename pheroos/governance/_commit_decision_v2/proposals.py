"""Portable caller proposals consumed by the Commit Decision v2 reducer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, cast

from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2,
    COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2,
    COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2,
    _canonical_bytes,
    _exact_array,
    _exact_mapping,
    _freeze_json,
    _install_root,
    _portable_json,
    _require_canonical_wire,
    _require_root,
    _require_text,
)


@dataclass(frozen=True, slots=True)
class CommitDecisionEvidenceProposalV2:
    qualified_record_root: str
    schema: str = COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2
    proposal_root: str = ""

    _root_field: ClassVar[str] = "proposal_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2:
            raise ValueError("commit evidence proposal schema is unsupported")
        _require_root(
            self.qualified_record_root,
            "commit evidence proposal qualified_record_root",
        )
        _install_root(
            self, "proposal_root", self.proposal_root, "evidence-proposal", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "qualified_record_root": self.qualified_record_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "proposal_root": self.proposal_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionEvidenceProposalV2:
        value = _exact_mapping(
            payload,
            frozenset({"schema", "qualified_record_root", "proposal_root"}),
            "commit evidence proposal v2",
        )
        decoded = cls(
            qualified_record_root=cast(str, value["qualified_record_root"]),
            schema=cast(str, value["schema"]),
            proposal_root=cast(str, value["proposal_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit evidence proposal v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CommitDecisionCandidateProposalV2:
    candidate_ref: str
    claim_root: str
    evidence: Sequence[CommitDecisionEvidenceProposalV2]
    schema: str = COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2
    evidence_set_root: str = ""
    proposal_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2:
            raise ValueError("commit candidate proposal schema is unsupported")
        _require_text(self.candidate_ref, "commit candidate proposal candidate_ref")
        _require_root(self.claim_root, "commit candidate proposal claim_root")
        if type(self.evidence) not in (list, tuple):
            raise TypeError("commit candidate evidence must be an exact array or tuple")
        records = tuple(self.evidence)
        if any(type(item) is not CommitDecisionEvidenceProposalV2 for item in records):
            raise TypeError("commit candidate evidence contains a noncanonical record")
        ordered = tuple(sorted(records, key=lambda item: item.proposal_root))
        roots = tuple(item.qualified_record_root for item in ordered)
        if len(roots) != len(set(roots)):
            raise ValueError("commit candidate proposal repeats an evidence payload")
        object.__setattr__(self, "evidence", ordered)
        _install_root(
            self,
            "evidence_set_root",
            self.evidence_set_root,
            "evidence-set",
            {"evidence": [item.proposal_root for item in ordered]},
        )
        _install_root(
            self,
            "proposal_root",
            self.proposal_root,
            "candidate-proposal",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "evidence": [item.to_dict() for item in self.evidence],
            "evidence_set_root": self.evidence_set_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "proposal_root": self.proposal_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionCandidateProposalV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "candidate_ref",
                    "claim_root",
                    "evidence",
                    "evidence_set_root",
                    "proposal_root",
                }
            ),
            "commit candidate proposal v2",
        )
        raw = _exact_array(value["evidence"], "commit candidate evidence")
        evidence = tuple(
            CommitDecisionEvidenceProposalV2.from_dict(item) for item in raw
        )
        decoded = cls(
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            evidence=evidence,
            schema=cast(str, value["schema"]),
            evidence_set_root=cast(str, value["evidence_set_root"]),
            proposal_root=cast(str, value["proposal_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit candidate proposal v2"
        )
        return decoded


def canonical_candidate_proposals_v2(
    values: Sequence[CommitDecisionCandidateProposalV2],
) -> tuple[CommitDecisionCandidateProposalV2, ...]:
    if type(values) not in (list, tuple):
        raise TypeError("commit candidate proposals must be an exact array or tuple")
    records = tuple(values)
    if any(type(item) is not CommitDecisionCandidateProposalV2 for item in records):
        raise TypeError("commit candidate proposals contain a noncanonical record")
    ordered = tuple(
        sorted(records, key=lambda item: item.candidate_ref.encode("utf-8"))
    )
    refs = tuple(item.candidate_ref for item in ordered)
    if len(refs) != len(set(refs)):
        raise ValueError("commit candidate proposals repeat a candidate")
    return ordered


@dataclass(frozen=True, slots=True)
class CommitDecisionOutputProposalV2:
    candidate_ref: str
    claim_root: str
    output_contract_root: str
    payload: Mapping[str, object]
    schema: str = COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2
    payload_root: str = ""
    proposal_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2:
            raise ValueError("commit output proposal schema is unsupported")
        _require_text(self.candidate_ref, "commit output candidate_ref")
        _require_root(self.claim_root, "commit output claim_root")
        _require_root(self.output_contract_root, "commit output contract root")
        if not isinstance(self.payload, Mapping):
            raise TypeError("commit output payload must be an object")
        frozen = _freeze_json(dict(self.payload))
        if not isinstance(frozen, MappingProxyType):
            raise TypeError("commit output payload must be an object")
        object.__setattr__(self, "payload", frozen)
        _install_root(
            self,
            "payload_root",
            self.payload_root,
            "output-payload",
            _portable_json(frozen),
        )
        _install_root(
            self, "proposal_root", self.proposal_root, "output-proposal", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "output_contract_root": self.output_contract_root,
            "payload": _portable_json(self.payload),
            "payload_root": self.payload_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "proposal_root": self.proposal_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionOutputProposalV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "candidate_ref",
                    "claim_root",
                    "output_contract_root",
                    "payload",
                    "payload_root",
                    "proposal_root",
                }
            ),
            "commit output proposal v2",
        )
        if type(value["payload"]) is not dict:
            raise TypeError("commit output payload must be an exact object")
        decoded = cls(
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            output_contract_root=cast(str, value["output_contract_root"]),
            payload=cast(dict[str, object], value["payload"]),
            schema=cast(str, value["schema"]),
            payload_root=cast(str, value["payload_root"]),
            proposal_root=cast(str, value["proposal_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "commit output proposal v2")
        return decoded


__all__ = (
    "CommitDecisionCandidateProposalV2",
    "CommitDecisionEvidenceProposalV2",
    "CommitDecisionOutputProposalV2",
    "canonical_candidate_proposals_v2",
)
