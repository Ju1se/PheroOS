"""Portable semantic value and full-envelope proposal contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._commit_certificate_v2.portable_body import (
    CommitCertificateBodyV2,
)
from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_ROOTS_V2,
    _canonical_bytes,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)


DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2 = "pheroos-distributed-commit-value-v2"
DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2 = "pheroos-distributed-commit-proposal-v2"


@dataclass(frozen=True, slots=True)
class DistributedCommitValueV2:
    """Exact semantic authority value; envelope identities are excluded."""

    domain_root: str
    scope_ref: str
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    candidate_ref: str
    claim_root: str
    output_contract_root: str
    output_payload_root: str
    decision_stream_ref: str
    decision_revision: int
    decision_transition_id: str
    decision_snapshot_root: str
    decision_head_root: str
    decision_receipt_root: str
    decision_inclusion_root: str
    decision_current_revision: int
    decision_current_transition_id: str
    decision_current_snapshot_root: str
    decision_current_head_root: str
    decision_current_receipt_root: str
    decision_current_inclusion_root: str
    seal_transition_id: str
    seal_snapshot_root: str
    seal_receipt_root: str
    seal_inclusion_root: str
    seal_root: str
    frozen_dependency_root: str
    manifest_root: str
    commit_policy_root: str
    authority_leaf_set_root: str
    membership_stream_ref: str
    membership_revision: int
    membership_transition_id: str
    membership_snapshot_root: str
    membership_head_root: str
    membership_root: str
    verification_stream_ref: str
    verification_revision: int
    verification_transition_id: str
    verification_snapshot_root: str
    verification_head_root: str
    verification_set_root: str
    central_certificate_stream_ref: str
    central_certificate_revision: int
    central_certificate_transition_id: str
    central_certificate_snapshot_root: str
    central_certificate_head_root: str
    central_certificate_receipt_root: str
    central_certificate_inclusion_root: str
    central_certificate_body: CommitCertificateBodyV2
    schema: str = DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    semantic_value_root: str = ""

    _root_field: ClassVar[str] = "semantic_value_root"

    def __post_init__(self) -> None:
        if (
            self.schema != DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed semantic value version is unsupported")
        for field in (
            "scope_ref",
            "profile",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "candidate_ref",
            "decision_stream_ref",
            "decision_transition_id",
            "seal_transition_id",
            "membership_stream_ref",
            "membership_transition_id",
            "verification_stream_ref",
            "verification_transition_id",
            "central_certificate_stream_ref",
            "central_certificate_transition_id",
        ):
            _require_text(getattr(self, field), f"distributed value {field}")
        if type(self.assurance) is not CommitAssurance:
            raise TypeError("distributed value assurance has the wrong enum type")
        if self.assurance is not CommitAssurance.DISTRIBUTED:
            raise ValueError("distributed value requires distributed assurance")
        for field in (
            "epoch",
            "decision_revision",
            "membership_revision",
            "verification_revision",
            "central_certificate_revision",
        ):
            _require_count(
                getattr(self, field),
                f"distributed value {field}",
                minimum=1 if field != "epoch" else 0,
            )
        for field in _VALUE_ROOT_FIELDS:
            _require_root(getattr(self, field), f"distributed value {field}")
        if type(self.central_certificate_body) is not CommitCertificateBodyV2:
            raise TypeError("distributed value requires an exact central body")
        self._validate_central_binding()
        _install_root(
            self,
            "semantic_value_root",
            self.semantic_value_root,
            "semantic-value",
            self._body(),
        )
        if len(_canonical_bytes(self.to_dict())) > 1_048_576:
            raise ValueError("distributed semantic value exceeds its byte bound")

    def _validate_central_binding(self) -> None:
        body = self.central_certificate_body
        observed = (
            body.domain_root,
            body.scope_ref,
            body.profile,
            body.assurance,
            body.protocol_ref,
            body.run_ref,
            body.target_ref,
            body.epoch,
            body.candidate_ref,
            body.claim_root,
            body.output_contract_root,
            body.output_payload_root,
            body.decision_stream_ref,
            body.decision_revision,
            body.decision_transition_id,
            body.decision_snapshot_root,
            body.decision_head_root,
            body.decision_receipt_root,
            body.decision_inclusion_root,
            body.seal_transition_id,
            body.seal_snapshot_root,
            body.seal_receipt_root,
            body.seal_inclusion_root,
            body.seal_root,
            body.frozen_dependency_root,
            body.manifest_root,
            body.commit_policy_root,
            body.authority_leaf_set_root,
        )
        expected = (
            self.domain_root,
            self.scope_ref,
            self.profile,
            self.assurance,
            self.protocol_ref,
            self.run_ref,
            self.target_ref,
            self.epoch,
            self.candidate_ref,
            self.claim_root,
            self.output_contract_root,
            self.output_payload_root,
            self.decision_stream_ref,
            self.decision_revision,
            self.decision_transition_id,
            self.decision_snapshot_root,
            self.decision_head_root,
            self.decision_receipt_root,
            self.decision_inclusion_root,
            self.seal_transition_id,
            self.seal_snapshot_root,
            self.seal_receipt_root,
            self.seal_inclusion_root,
            self.seal_root,
            self.frozen_dependency_root,
            self.manifest_root,
            self.commit_policy_root,
            self.authority_leaf_set_root,
        )
        if observed != expected:
            raise ValueError("distributed value central certificate is cross-bound")

    def _body(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "assurance": self.assurance.value,
            "central_certificate_body": self.central_certificate_body.to_dict(),
        }
        for field in _VALUE_TEXT_FIELDS + _VALUE_ROOT_FIELDS + _VALUE_COUNT_FIELDS:
            body[field] = getattr(self, field)
        return body

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "semantic_value_root": self.semantic_value_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedCommitValueV2:
        value = _exact_mapping(payload, _VALUE_FIELDS, "distributed value v2")
        try:
            assurance = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("distributed value assurance is unsupported") from exc
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            assurance=assurance,
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            profile=cast(str, value["profile"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            epoch=cast(int, value["epoch"]),
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            output_contract_root=cast(str, value["output_contract_root"]),
            output_payload_root=cast(str, value["output_payload_root"]),
            decision_stream_ref=cast(str, value["decision_stream_ref"]),
            decision_revision=cast(int, value["decision_revision"]),
            decision_transition_id=cast(str, value["decision_transition_id"]),
            decision_snapshot_root=cast(str, value["decision_snapshot_root"]),
            decision_head_root=cast(str, value["decision_head_root"]),
            decision_receipt_root=cast(str, value["decision_receipt_root"]),
            decision_inclusion_root=cast(str, value["decision_inclusion_root"]),
            decision_current_revision=cast(int, value["decision_current_revision"]),
            decision_current_transition_id=cast(
                str, value["decision_current_transition_id"]
            ),
            decision_current_snapshot_root=cast(
                str, value["decision_current_snapshot_root"]
            ),
            decision_current_head_root=cast(str, value["decision_current_head_root"]),
            decision_current_receipt_root=cast(
                str, value["decision_current_receipt_root"]
            ),
            decision_current_inclusion_root=cast(
                str, value["decision_current_inclusion_root"]
            ),
            seal_transition_id=cast(str, value["seal_transition_id"]),
            seal_snapshot_root=cast(str, value["seal_snapshot_root"]),
            seal_receipt_root=cast(str, value["seal_receipt_root"]),
            seal_inclusion_root=cast(str, value["seal_inclusion_root"]),
            seal_root=cast(str, value["seal_root"]),
            frozen_dependency_root=cast(str, value["frozen_dependency_root"]),
            manifest_root=cast(str, value["manifest_root"]),
            commit_policy_root=cast(str, value["commit_policy_root"]),
            authority_leaf_set_root=cast(str, value["authority_leaf_set_root"]),
            membership_stream_ref=cast(str, value["membership_stream_ref"]),
            membership_revision=cast(int, value["membership_revision"]),
            membership_transition_id=cast(str, value["membership_transition_id"]),
            membership_snapshot_root=cast(str, value["membership_snapshot_root"]),
            membership_head_root=cast(str, value["membership_head_root"]),
            membership_root=cast(str, value["membership_root"]),
            verification_stream_ref=cast(str, value["verification_stream_ref"]),
            verification_revision=cast(int, value["verification_revision"]),
            verification_transition_id=cast(str, value["verification_transition_id"]),
            verification_snapshot_root=cast(str, value["verification_snapshot_root"]),
            verification_head_root=cast(str, value["verification_head_root"]),
            verification_set_root=cast(str, value["verification_set_root"]),
            central_certificate_stream_ref=cast(
                str, value["central_certificate_stream_ref"]
            ),
            central_certificate_revision=cast(
                int, value["central_certificate_revision"]
            ),
            central_certificate_transition_id=cast(
                str, value["central_certificate_transition_id"]
            ),
            central_certificate_snapshot_root=cast(
                str, value["central_certificate_snapshot_root"]
            ),
            central_certificate_head_root=cast(
                str, value["central_certificate_head_root"]
            ),
            central_certificate_receipt_root=cast(
                str, value["central_certificate_receipt_root"]
            ),
            central_certificate_inclusion_root=cast(
                str, value["central_certificate_inclusion_root"]
            ),
            central_certificate_body=CommitCertificateBodyV2.from_dict(
                value["central_certificate_body"]
            ),
            semantic_value_root=cast(str, value["semantic_value_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "distributed value v2")
        return decoded


@dataclass(frozen=True, slots=True)
class DistributedCommitProposalV2:
    proposal_ref: str
    proposer_ref: str
    proposal_nonce: str
    proposed_at_step: int
    provenance_ref: str
    source_trace_roots: Sequence[str]
    value: DistributedCommitValueV2
    schema: str = DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    proposal_digest: str = ""

    _root_field: ClassVar[str] = "proposal_digest"

    def __post_init__(self) -> None:
        if (
            self.schema != DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed proposal version is unsupported")
        for field in (
            "proposal_ref",
            "proposer_ref",
            "proposal_nonce",
            "provenance_ref",
        ):
            _require_text(getattr(self, field), f"distributed proposal {field}")
        _require_count(self.proposed_at_step, "distributed proposal step")
        if type(self.value) is not DistributedCommitValueV2:
            raise TypeError("distributed proposal requires exact semantic value")
        traces = _canonical_texts(
            self.source_trace_roots,
            "distributed proposal trace roots",
            maximum=MAX_DISTRIBUTED_ROOTS_V2,
            allow_empty=False,
            roots=True,
        )
        object.__setattr__(self, "source_trace_roots", traces)
        _install_root(
            self,
            "proposal_digest",
            self.proposal_digest,
            "proposal-envelope",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "proposal_ref": self.proposal_ref,
            "proposer_ref": self.proposer_ref,
            "proposal_nonce": self.proposal_nonce,
            "proposed_at_step": self.proposed_at_step,
            "provenance_ref": self.provenance_ref,
            "source_trace_roots": list(self.source_trace_roots),
            "value": self.value.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "proposal_digest": self.proposal_digest}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedCommitProposalV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "proposal_ref",
                    "proposer_ref",
                    "proposal_nonce",
                    "proposed_at_step",
                    "provenance_ref",
                    "source_trace_roots",
                    "value",
                    "proposal_digest",
                }
            ),
            "distributed proposal v2",
        )
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            proposal_ref=cast(str, value["proposal_ref"]),
            proposer_ref=cast(str, value["proposer_ref"]),
            proposal_nonce=cast(str, value["proposal_nonce"]),
            proposed_at_step=cast(int, value["proposed_at_step"]),
            provenance_ref=cast(str, value["provenance_ref"]),
            source_trace_roots=cast(
                Sequence[str],
                _exact_array(
                    value["source_trace_roots"],
                    "distributed proposal trace roots",
                    allow_empty=False,
                ),
            ),
            value=DistributedCommitValueV2.from_dict(value["value"]),
            proposal_digest=cast(str, value["proposal_digest"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "distributed proposal v2")
        return decoded


_VALUE_TEXT_FIELDS = (
    "scope_ref",
    "profile",
    "protocol_ref",
    "run_ref",
    "target_ref",
    "candidate_ref",
    "decision_stream_ref",
    "decision_transition_id",
    "decision_current_transition_id",
    "seal_transition_id",
    "membership_stream_ref",
    "membership_transition_id",
    "verification_stream_ref",
    "verification_transition_id",
    "central_certificate_stream_ref",
    "central_certificate_transition_id",
)
_VALUE_COUNT_FIELDS = (
    "epoch",
    "decision_revision",
    "decision_current_revision",
    "membership_revision",
    "verification_revision",
    "central_certificate_revision",
)
_VALUE_ROOT_FIELDS = (
    "domain_root",
    "claim_root",
    "output_contract_root",
    "output_payload_root",
    "decision_snapshot_root",
    "decision_head_root",
    "decision_receipt_root",
    "decision_inclusion_root",
    "decision_current_snapshot_root",
    "decision_current_head_root",
    "decision_current_receipt_root",
    "decision_current_inclusion_root",
    "seal_snapshot_root",
    "seal_receipt_root",
    "seal_inclusion_root",
    "seal_root",
    "frozen_dependency_root",
    "manifest_root",
    "commit_policy_root",
    "authority_leaf_set_root",
    "membership_snapshot_root",
    "membership_head_root",
    "membership_root",
    "verification_snapshot_root",
    "verification_head_root",
    "verification_set_root",
    "central_certificate_snapshot_root",
    "central_certificate_head_root",
    "central_certificate_receipt_root",
    "central_certificate_inclusion_root",
)
_VALUE_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "assurance",
        "central_certificate_body",
        "semantic_value_root",
        *_VALUE_TEXT_FIELDS,
        *_VALUE_COUNT_FIELDS,
        *_VALUE_ROOT_FIELDS,
    }
)


__all__ = [
    "DISTRIBUTED_COMMIT_PROPOSAL_SCHEMA_V2",
    "DISTRIBUTED_COMMIT_VALUE_SCHEMA_V2",
    "DistributedCommitProposalV2",
    "DistributedCommitValueV2",
]
