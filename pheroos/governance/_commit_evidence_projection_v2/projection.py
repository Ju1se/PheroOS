"""Portable Decision-facing projection of one verified Evidence head."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE, CommitAssurance

from pheroos.governance._commit_evidence_projection_v2.common import (
    MAX_COMMIT_EVIDENCE_RECORDS_V2,
    canonical_roots_v2,
    evidence_root_v2,
    exact_array_v2,
    exact_object_v2,
    require_canonical_wire_v2,
    require_count_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceDispositionV2,
    CommitEvidenceKindV2,
    CommitEvidencePolicySnapshotV2,
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
    canonical_qualified_evidence_v2,
)


COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2 = "pheroos-commit-evidence-projection-v2"


@dataclass(frozen=True, slots=True)
class CommitEvidenceProjectionV2:
    domain_root: str
    scope_ref: str
    manifest_root: str
    commit_policy_root: str
    evidence_policy: CommitEvidencePolicySnapshotV2
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    current_step: int
    stream_ref: str
    revision: int
    transition_id: str
    snapshot_root: str
    head_root: str
    receipt_root: str
    membership_stream_ref: str
    membership_transition_id: str
    membership_head_root: str
    membership_snapshot_root: str
    membership_root: str
    verification_stream_ref: str
    verification_transition_id: str
    verification_head_root: str
    verification_snapshot_root: str
    verification_set_root: str
    records: Sequence[QualifiedCommitEvidenceV2]
    schema: str = COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    record_set_root: str = ""
    conflict_roots: Sequence[str] = ()
    projection_root: str = ""

    _root_field: ClassVar[str] = "projection_root"

    def __post_init__(self) -> None:
        _validate_projection_context(self)
        records = canonical_qualified_evidence_v2(self.records)
        _validate_projection_records(self, records)
        object.__setattr__(self, "records", records)
        record_set_root = evidence_root_v2(
            "projection-record-set", {"records": [item.record_root for item in records]}
        )
        if self.record_set_root not in ("", record_set_root):
            raise ValueError("commit evidence projection record_set_root is mismatched")
        object.__setattr__(self, "record_set_root", record_set_root)
        conflicts = tuple(
            sorted(
                item.record_root
                for item in records
                if item.kind is CommitEvidenceKindV2.COUNTER
                and item.materiality_ppm > 0
                and item.criticality_ppm > 0
                and item.disposition
                in {
                    CommitEvidenceDispositionV2.UNRESOLVED,
                    CommitEvidenceDispositionV2.ACCEPTED,
                }
            )
        )
        supplied = canonical_roots_v2(
            self.conflict_roots, "commit evidence projection conflict_roots"
        )
        if supplied not in ((), conflicts):
            raise ValueError("commit evidence projection conflict_roots are mismatched")
        object.__setattr__(self, "conflict_roots", conflicts)
        expected = evidence_root_v2("projection", self._body())
        if self.projection_root not in ("", expected):
            raise ValueError("commit evidence projection_root is mismatched")
        object.__setattr__(self, "projection_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "evidence_policy": self.evidence_policy.to_dict(),
            "profile": self.profile,
            "assurance": self.assurance.value,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "epoch": self.epoch,
            "current_step": self.current_step,
            "stream_ref": self.stream_ref,
            "revision": self.revision,
            "transition_id": self.transition_id,
            "snapshot_root": self.snapshot_root,
            "head_root": self.head_root,
            "receipt_root": self.receipt_root,
            "membership_stream_ref": self.membership_stream_ref,
            "membership_transition_id": self.membership_transition_id,
            "membership_head_root": self.membership_head_root,
            "membership_snapshot_root": self.membership_snapshot_root,
            "membership_root": self.membership_root,
            "verification_stream_ref": self.verification_stream_ref,
            "verification_transition_id": self.verification_transition_id,
            "verification_head_root": self.verification_head_root,
            "verification_snapshot_root": self.verification_snapshot_root,
            "verification_set_root": self.verification_set_root,
            "records": [item.to_dict() for item in self.records],
            "record_set_root": self.record_set_root,
            "conflict_roots": list(self.conflict_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "projection_root": self.projection_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitEvidenceProjectionV2:
        value = exact_object_v2(
            payload, _PROJECTION_FIELDS, "commit evidence projection v2"
        )
        try:
            value["assurance"] = CommitAssurance(value["assurance"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "commit evidence projection assurance is unsupported"
            ) from exc
        value["evidence_policy"] = CommitEvidencePolicySnapshotV2.from_dict(
            value["evidence_policy"]
        )
        value["records"] = tuple(
            QualifiedCommitEvidenceV2.from_dict(item)
            for item in exact_array_v2(
                value["records"],
                "commit evidence projection records",
                limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
            )
        )
        value["conflict_roots"] = tuple(
            exact_array_v2(
                value["conflict_roots"],
                "commit evidence projection conflicts",
                limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
            )
        )
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload, decoded.to_dict(), "commit evidence projection v2"
        )
        return decoded


def _validate_projection_context(projection: CommitEvidenceProjectionV2) -> None:
    if (
        projection.schema != COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2
        or projection.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
    ):
        raise ValueError("commit evidence projection version is unsupported")
    if type(projection.evidence_policy) is not CommitEvidencePolicySnapshotV2:
        raise TypeError("commit evidence projection policy is invalid")
    if (
        type(projection.assurance) is not CommitAssurance
        or projection.profile
        not in COMMIT_PROFILES_BY_ASSURANCE.get(projection.assurance.value, frozenset())
    ):
        raise ValueError("commit evidence projection profile is mismatched")
    for field in (
        "domain_root",
        "manifest_root",
        "commit_policy_root",
        "snapshot_root",
        "head_root",
        "receipt_root",
        "membership_head_root",
        "membership_snapshot_root",
        "membership_root",
        "verification_head_root",
        "verification_snapshot_root",
        "verification_set_root",
    ):
        require_root_v2(
            getattr(projection, field), f"commit evidence projection {field}"
        )
    for field in (
        "scope_ref",
        "profile",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
        "transition_id",
        "membership_stream_ref",
        "membership_transition_id",
        "verification_stream_ref",
        "verification_transition_id",
    ):
        require_text_v2(
            getattr(projection, field), f"commit evidence projection {field}"
        )
    require_count_v2(projection.epoch, "commit evidence projection epoch")
    require_count_v2(projection.current_step, "commit evidence projection current_step")
    require_count_v2(
        projection.revision, "commit evidence projection revision", minimum=1
    )


def _validate_projection_records(
    projection: CommitEvidenceProjectionV2,
    records: tuple[QualifiedCommitEvidenceV2, ...],
) -> None:
    policy = projection.evidence_policy
    for item in records:
        if (
            item.status is not CommitEvidenceStatusV2.ACTIVE
            or item.epoch != projection.epoch
            or item.qualification_policy_root != projection.evidence_policy.policy_root
            or item.membership_root != projection.membership_root
            or item.verification_set_root != projection.verification_set_root
            or not item.observed_at_step
            <= projection.current_step
            < item.expires_at_step
        ):
            raise ValueError(
                "commit evidence projection contains inactive or cross-bound evidence"
            )
        if item.expires_at_step - item.observed_at_step > policy.observation_ttl_steps:
            raise ValueError("commit evidence projection record exceeds policy TTL")
        if item.kind is not CommitEvidenceKindV2.CHALLENGE and (
            item.quality_ppm < policy.minimum_quality_ppm
            or item.relevance_ppm < policy.minimum_relevance_ppm
        ):
            raise ValueError(
                "commit evidence projection record is below policy quality"
            )
    _validate_projection_relations(records)


def _validate_projection_relations(
    records: tuple[QualifiedCommitEvidenceV2, ...],
) -> None:
    by_root = {item.attestation_root: item for item in records}
    challenges = tuple(
        item for item in records if item.kind is CommitEvidenceKindV2.CHALLENGE
    )
    execution_roots = tuple(item.execution_root for item in challenges)
    execution_attestations = tuple(
        item.execution_attestation_root for item in challenges
    )
    if len(execution_roots) != len(set(execution_roots)) or len(
        execution_attestations
    ) != len(set(execution_attestations)):
        raise ValueError("commit evidence projection reuses a challenge execution")
    for item in records:
        if item.kind is CommitEvidenceKindV2.CHALLENGE:
            _require_related_roots(
                item,
                item.result_observation_roots,
                by_root,
                expected_kind=CommitEvidenceKindV2.COUNTER,
            )
        elif item.kind is CommitEvidenceKindV2.COUNTER:
            rebuttals = _require_related_roots(
                item,
                item.rebuttal_observation_roots,
                by_root,
                expected_kind=CommitEvidenceKindV2.POSITIVE,
            )
            _require_independent_rebuttals(item, rebuttals)


def _require_related_roots(
    owner: QualifiedCommitEvidenceV2,
    roots: Sequence[str],
    records: dict[str, QualifiedCommitEvidenceV2],
    *,
    expected_kind: CommitEvidenceKindV2,
) -> tuple[QualifiedCommitEvidenceV2, ...]:
    related = tuple(records.get(root) for root in roots)
    if any(item is None for item in related):
        raise ValueError("commit evidence projection relation is unresolved")
    exact = tuple(item for item in related if item is not None)
    if any(
        item.kind is not expected_kind
        or item.candidate_ref != owner.candidate_ref
        or item.claim_root != owner.claim_root
        or item.epoch != owner.epoch
        for item in exact
    ):
        raise ValueError(
            "commit evidence projection relation crosses candidate or claim"
        )
    return exact


def _require_independent_rebuttals(
    counter: QualifiedCommitEvidenceV2,
    rebuttals: tuple[QualifiedCommitEvidenceV2, ...],
) -> None:
    principals = {counter.principal_ref}
    clusters = {counter.cluster_ref}
    domains = {counter.failure_domain_ref}
    for item in rebuttals:
        if (
            item.principal_ref in principals
            or item.cluster_ref in clusters
            or item.failure_domain_ref in domains
        ):
            raise ValueError("commit evidence projection rebuttal is not independent")
        principals.add(item.principal_ref)
        clusters.add(item.cluster_ref)
        domains.add(item.failure_domain_ref)


_PROJECTION_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "manifest_root",
        "commit_policy_root",
        "evidence_policy",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "epoch",
        "current_step",
        "stream_ref",
        "revision",
        "transition_id",
        "snapshot_root",
        "head_root",
        "receipt_root",
        "membership_stream_ref",
        "membership_transition_id",
        "membership_head_root",
        "membership_snapshot_root",
        "membership_root",
        "verification_stream_ref",
        "verification_transition_id",
        "verification_head_root",
        "verification_snapshot_root",
        "verification_set_root",
        "records",
        "record_set_root",
        "conflict_roots",
        "projection_root",
    }
)


__all__ = ["COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2", "CommitEvidenceProjectionV2"]
