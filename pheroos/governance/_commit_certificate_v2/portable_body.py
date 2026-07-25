"""Authority-neutral semantic body of a portable Commit Certificate v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._commit_certificate_v2.authority_leaves import (
    CommitCertificateAuthorityLeafV2,
    canonical_commit_certificate_authority_leaves_v2,
    commit_certificate_authority_leaf_set_root_v2,
)
from pheroos.governance._commit_certificate_v2.common import (
    _canonical_bytes,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)


COMMIT_CERTIFICATE_BODY_SCHEMA_V2 = "pheroos-commit-certificate-body-v2"


@dataclass(frozen=True, slots=True)
class CommitCertificateBodyV2:
    """Semantic final value; envelope and transport identifiers are excluded."""

    wire_version: str
    canonicalization: str
    hash_algorithm: str
    domain_root: str
    scope_ref: str
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    manifest_root: str
    commit_policy_root: str
    decision_stream_ref: str
    decision_revision: int
    decision_transition_id: str
    decision_snapshot_root: str
    decision_head_root: str
    decision_receipt_root: str
    decision_inclusion_root: str
    seal_transition_id: str
    seal_revision: int
    seal_snapshot_root: str
    seal_receipt_root: str
    seal_head_root: str
    seal_inclusion_root: str
    seal_root: str
    window_root: str
    frozen_dependency_root: str
    assessment_root: str
    candidate_ref: str
    claim_root: str
    evidence_root: str
    challenge_root: str
    lease_root: str
    output_contract_root: str
    output_payload_root: str
    authority_leaves: Sequence[CommitCertificateAuthorityLeafV2]
    authority_leaf_set_root: str = ""
    schema: str = COMMIT_CERTIFICATE_BODY_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    body_root: str = ""

    _root_field: ClassVar[str] = "body_root"

    def __post_init__(self) -> None:
        self._validate_header()
        self._validate_lineage()
        leaves = canonical_commit_certificate_authority_leaves_v2(self.authority_leaves)
        object.__setattr__(self, "authority_leaves", leaves)
        expected = commit_certificate_authority_leaf_set_root_v2(leaves)
        if self.authority_leaf_set_root not in ("", expected):
            raise ValueError("commit certificate authority leaf set root is mismatched")
        object.__setattr__(self, "authority_leaf_set_root", expected)
        _install_root(self, "body_root", self.body_root, "body", self._body())
        if len(_canonical_bytes(self.to_dict())) > 524_288:
            raise ValueError("commit certificate body exceeds its byte bound")

    def _validate_header(self) -> None:
        if self.schema != COMMIT_CERTIFICATE_BODY_SCHEMA_V2:
            raise ValueError("commit certificate body schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError("commit certificate canonical version is unsupported")
        for field in (
            "wire_version",
            "canonicalization",
            "hash_algorithm",
            "scope_ref",
            "profile",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "decision_stream_ref",
            "decision_transition_id",
            "seal_transition_id",
            "candidate_ref",
        ):
            _require_text(getattr(self, field), f"commit certificate body {field}")
        if self.hash_algorithm != "sha256":
            raise ValueError("commit certificate hash algorithm is unsupported")
        if type(self.assurance) is not CommitAssurance or self.assurance not in {
            CommitAssurance.CERTIFIED,
            CommitAssurance.DISTRIBUTED,
        }:
            raise ValueError("commit certificate assurance is unsupported")
        _require_count(self.epoch, "commit certificate epoch")
        _require_count(
            self.decision_revision,
            "commit certificate decision revision",
            minimum=1,
        )
        _require_count(
            self.seal_revision,
            "commit certificate seal revision",
            minimum=1,
        )

    def _validate_lineage(self) -> None:
        for field in (
            "domain_root",
            "manifest_root",
            "commit_policy_root",
            "decision_snapshot_root",
            "decision_head_root",
            "decision_receipt_root",
            "decision_inclusion_root",
            "seal_snapshot_root",
            "seal_receipt_root",
            "seal_head_root",
            "seal_inclusion_root",
            "seal_root",
            "window_root",
            "frozen_dependency_root",
            "assessment_root",
            "claim_root",
            "evidence_root",
            "challenge_root",
            "lease_root",
            "output_contract_root",
            "output_payload_root",
        ):
            _require_root(getattr(self, field), f"commit certificate body {field}")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "wire_version": self.wire_version,
            "canonicalization": self.canonicalization,
            "hash_algorithm": self.hash_algorithm,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "profile": self.profile,
            "assurance": self.assurance.value,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "decision_stream_ref": self.decision_stream_ref,
            "decision_revision": self.decision_revision,
            "decision_transition_id": self.decision_transition_id,
            "decision_snapshot_root": self.decision_snapshot_root,
            "decision_head_root": self.decision_head_root,
            "decision_receipt_root": self.decision_receipt_root,
            "decision_inclusion_root": self.decision_inclusion_root,
            "seal_transition_id": self.seal_transition_id,
            "seal_revision": self.seal_revision,
            "seal_snapshot_root": self.seal_snapshot_root,
            "seal_receipt_root": self.seal_receipt_root,
            "seal_head_root": self.seal_head_root,
            "seal_inclusion_root": self.seal_inclusion_root,
            "seal_root": self.seal_root,
            "window_root": self.window_root,
            "frozen_dependency_root": self.frozen_dependency_root,
            "assessment_root": self.assessment_root,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "evidence_root": self.evidence_root,
            "challenge_root": self.challenge_root,
            "lease_root": self.lease_root,
            "output_contract_root": self.output_contract_root,
            "output_payload_root": self.output_payload_root,
            "authority_leaves": [item.to_dict() for item in self.authority_leaves],
            "authority_leaf_set_root": self.authority_leaf_set_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "body_root": self.body_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitCertificateBodyV2:
        value = _exact_mapping(payload, _BODY_FIELDS, "commit certificate body v2")
        try:
            assurance = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit certificate assurance is unsupported") from exc
        leaves = tuple(
            CommitCertificateAuthorityLeafV2.from_dict(item)
            for item in _exact_array(
                value["authority_leaves"], "commit certificate authority leaves"
            )
        )
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            wire_version=cast(str, value["wire_version"]),
            canonicalization=cast(str, value["canonicalization"]),
            hash_algorithm=cast(str, value["hash_algorithm"]),
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            profile=cast(str, value["profile"]),
            assurance=assurance,
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            epoch=cast(int, value["epoch"]),
            manifest_root=cast(str, value["manifest_root"]),
            commit_policy_root=cast(str, value["commit_policy_root"]),
            decision_stream_ref=cast(str, value["decision_stream_ref"]),
            decision_revision=cast(int, value["decision_revision"]),
            decision_transition_id=cast(str, value["decision_transition_id"]),
            decision_snapshot_root=cast(str, value["decision_snapshot_root"]),
            decision_head_root=cast(str, value["decision_head_root"]),
            decision_receipt_root=cast(str, value["decision_receipt_root"]),
            decision_inclusion_root=cast(str, value["decision_inclusion_root"]),
            seal_transition_id=cast(str, value["seal_transition_id"]),
            seal_revision=cast(int, value["seal_revision"]),
            seal_snapshot_root=cast(str, value["seal_snapshot_root"]),
            seal_receipt_root=cast(str, value["seal_receipt_root"]),
            seal_head_root=cast(str, value["seal_head_root"]),
            seal_inclusion_root=cast(str, value["seal_inclusion_root"]),
            seal_root=cast(str, value["seal_root"]),
            window_root=cast(str, value["window_root"]),
            frozen_dependency_root=cast(str, value["frozen_dependency_root"]),
            assessment_root=cast(str, value["assessment_root"]),
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            evidence_root=cast(str, value["evidence_root"]),
            challenge_root=cast(str, value["challenge_root"]),
            lease_root=cast(str, value["lease_root"]),
            output_contract_root=cast(str, value["output_contract_root"]),
            output_payload_root=cast(str, value["output_payload_root"]),
            authority_leaves=leaves,
            authority_leaf_set_root=cast(str, value["authority_leaf_set_root"]),
            body_root=cast(str, value["body_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit certificate body v2"
        )
        return decoded


_BODY_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "wire_version",
        "canonicalization",
        "hash_algorithm",
        "domain_root",
        "scope_ref",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "epoch",
        "manifest_root",
        "commit_policy_root",
        "decision_stream_ref",
        "decision_revision",
        "decision_transition_id",
        "decision_snapshot_root",
        "decision_head_root",
        "decision_receipt_root",
        "decision_inclusion_root",
        "seal_transition_id",
        "seal_revision",
        "seal_snapshot_root",
        "seal_receipt_root",
        "seal_head_root",
        "seal_inclusion_root",
        "seal_root",
        "window_root",
        "frozen_dependency_root",
        "assessment_root",
        "candidate_ref",
        "claim_root",
        "evidence_root",
        "challenge_root",
        "lease_root",
        "output_contract_root",
        "output_payload_root",
        "authority_leaves",
        "authority_leaf_set_root",
        "body_root",
    }
)


__all__ = ["COMMIT_CERTIFICATE_BODY_SCHEMA_V2", "CommitCertificateBodyV2"]
