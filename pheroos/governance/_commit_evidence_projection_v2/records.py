"""Portable qualified Evidence records; canonical data never confers authority."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, cast

from pheroos.governance.commit_numeric import WEIGHT_SCALE

from pheroos.governance._commit_evidence_projection_v2.common import (
    MAX_COMMIT_EVIDENCE_REASON_CODES_V2,
    MAX_COMMIT_EVIDENCE_RECORDS_V2,
    canonical_roots_v2,
    canonical_texts_v2,
    evidence_root_v2,
    exact_array_v2,
    exact_object_v2,
    require_canonical_wire_v2,
    require_count_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.record_fields import (
    _POLICY_FIELDS,
    _RECORD_ARRAY_FIELDS,
    _RECORD_BODY_FIELDS,
    _RECORD_FIELDS,
)


COMMIT_EVIDENCE_POLICY_SCHEMA_V2 = "pheroos-commit-evidence-policy-v2"
COMMIT_EVIDENCE_RECORD_SCHEMA_V2 = "pheroos-qualified-commit-evidence-v2"


class CommitEvidenceKindV2(StrEnum):
    POSITIVE = "positive"
    COUNTER = "counter"
    CHALLENGE = "challenge"


class CommitEvidenceStatusV2(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class CommitEvidenceDispositionV2(StrEnum):
    NONE = "none"
    UNRESOLVED = "unresolved"
    REBUTTED = "rebutted"
    ACCEPTED = "accepted"
    IMMATERIAL = "immaterial"


class ChallengeResultV2(StrEnum):
    NONE = "none"
    NO_COUNTEREVIDENCE = "no_counterevidence"
    COUNTEREVIDENCE_FOUND = "counterevidence_found"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class CommitEvidencePolicySnapshotV2:
    numeric_scale: int
    minimum_quality_ppm: int
    minimum_relevance_ppm: int
    positive_group_cap: int
    counter_group_cap: int
    counter_weight_ppm: int
    minimum_positive_evidence: int
    maximum_counterevidence: int
    maximum_counterevidence_ratio_ppm: int
    domain_contribution_floor: int
    minimum_source_diversity: int
    required_challenge_categories: Sequence[str]
    observation_ttl_steps: int
    require_provenance: bool
    require_trace: bool
    extensions_root: str
    schema: str = COMMIT_EVIDENCE_POLICY_SCHEMA_V2
    policy_root: str = ""

    _root_field: ClassVar[str] = "policy_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_EVIDENCE_POLICY_SCHEMA_V2:
            raise ValueError("commit evidence policy schema is unsupported")
        if self.numeric_scale != WEIGHT_SCALE:
            raise ValueError("commit evidence policy numeric scale is unsupported")
        for field in (
            "minimum_quality_ppm",
            "minimum_relevance_ppm",
            "maximum_counterevidence_ratio_ppm",
        ):
            value = require_count_v2(getattr(self, field), f"evidence policy {field}")
            if value > WEIGHT_SCALE:
                raise ValueError(f"commit evidence policy {field} exceeds its scale")
        for field in (
            "positive_group_cap",
            "counter_group_cap",
            "counter_weight_ppm",
            "minimum_positive_evidence",
            "domain_contribution_floor",
            "minimum_source_diversity",
            "observation_ttl_steps",
        ):
            require_count_v2(
                getattr(self, field), f"evidence policy {field}", minimum=1
            )
        require_count_v2(
            self.maximum_counterevidence,
            "evidence policy maximum_counterevidence",
        )
        categories = canonical_texts_v2(
            self.required_challenge_categories,
            "evidence policy challenge categories",
            limit=MAX_COMMIT_EVIDENCE_REASON_CODES_V2,
            allow_empty=False,
        )
        object.__setattr__(self, "required_challenge_categories", categories)
        if self.require_provenance is not True or self.require_trace is not True:
            raise ValueError("commit evidence policy must require provenance and trace")
        require_root_v2(self.extensions_root, "evidence policy extensions_root")
        expected = evidence_root_v2("policy", self._body())
        if self.policy_root not in ("", expected):
            raise ValueError("commit evidence policy_root is mismatched")
        object.__setattr__(self, "policy_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "numeric_scale": self.numeric_scale,
            "minimum_quality_ppm": self.minimum_quality_ppm,
            "minimum_relevance_ppm": self.minimum_relevance_ppm,
            "positive_group_cap": self.positive_group_cap,
            "counter_group_cap": self.counter_group_cap,
            "counter_weight_ppm": self.counter_weight_ppm,
            "minimum_positive_evidence": self.minimum_positive_evidence,
            "maximum_counterevidence": self.maximum_counterevidence,
            "maximum_counterevidence_ratio_ppm": self.maximum_counterevidence_ratio_ppm,
            "domain_contribution_floor": self.domain_contribution_floor,
            "minimum_source_diversity": self.minimum_source_diversity,
            "required_challenge_categories": list(self.required_challenge_categories),
            "observation_ttl_steps": self.observation_ttl_steps,
            "require_provenance": self.require_provenance,
            "require_trace": self.require_trace,
            "extensions_root": self.extensions_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "policy_root": self.policy_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitEvidencePolicySnapshotV2:
        value = exact_object_v2(payload, _POLICY_FIELDS, "commit evidence policy v2")
        value["required_challenge_categories"] = tuple(
            exact_array_v2(
                value["required_challenge_categories"],
                "commit evidence policy challenge categories",
                limit=MAX_COMMIT_EVIDENCE_REASON_CODES_V2,
            )
        )
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload, decoded.to_dict(), "commit evidence policy v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class QualifiedCommitEvidenceV2:
    record_ref: str
    kind: CommitEvidenceKindV2
    status: CommitEvidenceStatusV2
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    cluster_ref: str
    failure_domain_ref: str
    membership_principal_root: str
    principal_verification_root: str
    attestation_root: str
    payload_root: str
    source_ref: str
    independence_ref: str
    quality_ppm: int
    relevance_ppm: int
    materiality_ppm: int
    criticality_ppm: int
    weight_ppm: int
    category_ref: str
    execution_method: str
    execution_attestation_root: str
    execution_root: str
    challenge_result: ChallengeResultV2
    result_root: str
    result_observation_roots: Sequence[str]
    disposition: CommitEvidenceDispositionV2
    disposition_ref: str
    disposition_nonce: str
    disposition_root: str
    rebuttal_observation_roots: Sequence[str]
    resolution_root: str
    reason_codes: Sequence[str]
    nonce: str
    observed_at_step: int
    qualified_at_step: int
    expires_at_step: int
    qualification_issuer_ref: str
    qualification_root: str
    qualification_policy_root: str
    membership_root: str
    verification_set_root: str
    attestation_provenance_root: str
    attestation_trace_roots: Sequence[str]
    qualification_provenance_root: str
    qualification_trace_roots: Sequence[str]
    revoked_at_step: int | None
    revocation_root: str
    revocation_provenance_root: str
    revocation_trace_roots: Sequence[str]
    replay_receipt_roots: Sequence[str]
    schema: str = COMMIT_EVIDENCE_RECORD_SCHEMA_V2
    record_root: str = ""

    _root_field: ClassVar[str] = "record_root"

    def __post_init__(self) -> None:
        _validate_record(self)
        _canonicalize_record_arrays(self)
        _validate_kind_fields(self)
        _validate_record_time_and_status(self)
        expected = evidence_root_v2("record", self._body())
        if self.record_root not in ("", expected):
            raise ValueError("qualified evidence record_root is mismatched")
        object.__setattr__(self, "record_root", expected)

    def _body(self) -> dict[str, object]:
        body = {field: getattr(self, field) for field in _RECORD_BODY_FIELDS}
        body["kind"] = self.kind.value
        body["status"] = self.status.value
        body["challenge_result"] = self.challenge_result.value
        body["disposition"] = self.disposition.value
        for field in _RECORD_ARRAY_FIELDS:
            body[field] = list(cast(Sequence[str], getattr(self, field)))
        return body

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "record_root": self.record_root}

    @classmethod
    def from_dict(cls, payload: object) -> QualifiedCommitEvidenceV2:
        value = exact_object_v2(payload, _RECORD_FIELDS, "qualified evidence v2")
        try:
            value["kind"] = CommitEvidenceKindV2(value["kind"])
            value["status"] = CommitEvidenceStatusV2(value["status"])
            value["challenge_result"] = ChallengeResultV2(value["challenge_result"])
            value["disposition"] = CommitEvidenceDispositionV2(value["disposition"])
        except (TypeError, ValueError) as exc:
            raise ValueError("qualified evidence enum is unsupported") from exc
        for field in _RECORD_ARRAY_FIELDS:
            value[field] = tuple(
                exact_array_v2(
                    value[field],
                    f"qualified evidence {field}",
                    limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
                )
            )
        decoded = cls(**value)
        require_canonical_wire_v2(payload, decoded.to_dict(), "qualified evidence v2")
        return decoded


def canonical_qualified_evidence_v2(
    records: Sequence[QualifiedCommitEvidenceV2],
) -> tuple[QualifiedCommitEvidenceV2, ...]:
    if (
        type(records) not in (list, tuple)
        or len(records) > MAX_COMMIT_EVIDENCE_RECORDS_V2
    ):
        raise TypeError("qualified evidence records must be a bounded array or tuple")
    values = tuple(records)
    if any(type(item) is not QualifiedCommitEvidenceV2 for item in values):
        raise TypeError("qualified evidence set contains a non-exact record")
    refs = tuple(item.record_ref for item in values)
    nonces = tuple(item.nonce for item in values)
    attestation_roots = tuple(item.attestation_root for item in values)
    if (
        len(refs) != len(set(refs))
        or len(nonces) != len(set(nonces))
        or len(attestation_roots) != len(set(attestation_roots))
    ):
        raise ValueError("qualified evidence set repeats an identity")
    disposition_nonces = tuple(
        item.disposition_nonce for item in values if item.disposition_nonce
    )
    disposition_roots = tuple(
        item.disposition_root for item in values if item.disposition_root
    )
    if (
        len(disposition_nonces) != len(set(disposition_nonces))
        or len(disposition_roots) != len(set(disposition_roots))
        or set(disposition_nonces).intersection(nonces)
    ):
        raise ValueError("qualified evidence set repeats a disposition identity")
    return tuple(sorted(values, key=lambda item: item.record_ref.encode("utf-8")))


def _validate_record(record: QualifiedCommitEvidenceV2) -> None:
    if record.schema != COMMIT_EVIDENCE_RECORD_SCHEMA_V2:
        raise ValueError("qualified evidence schema is unsupported")
    if (
        type(record.kind) is not CommitEvidenceKindV2
        or type(record.status) is not CommitEvidenceStatusV2
        or type(record.challenge_result) is not ChallengeResultV2
        or type(record.disposition) is not CommitEvidenceDispositionV2
    ):
        raise TypeError("qualified evidence enum is invalid")
    for field in (
        "record_ref",
        "candidate_ref",
        "principal_ref",
        "cluster_ref",
        "failure_domain_ref",
        "qualification_issuer_ref",
    ):
        require_text_v2(getattr(record, field), f"qualified evidence {field}")
    for field in (
        "claim_root",
        "membership_principal_root",
        "principal_verification_root",
        "attestation_root",
        "payload_root",
        "qualification_root",
        "qualification_policy_root",
        "membership_root",
        "verification_set_root",
        "attestation_provenance_root",
        "qualification_provenance_root",
    ):
        require_root_v2(getattr(record, field), f"qualified evidence {field}")
    require_count_v2(record.epoch, "qualified evidence epoch")
    for field in (
        "quality_ppm",
        "relevance_ppm",
        "materiality_ppm",
        "criticality_ppm",
        "weight_ppm",
    ):
        value = require_count_v2(getattr(record, field), f"qualified evidence {field}")
        if value > WEIGHT_SCALE:
            raise ValueError(f"qualified evidence {field} exceeds its scale")


def _canonicalize_record_arrays(record: QualifiedCommitEvidenceV2) -> None:
    for field in (
        "result_observation_roots",
        "rebuttal_observation_roots",
        "attestation_trace_roots",
        "qualification_trace_roots",
        "revocation_trace_roots",
        "replay_receipt_roots",
    ):
        allow_empty = field in {
            "result_observation_roots",
            "rebuttal_observation_roots",
            "revocation_trace_roots",
        }
        roots = canonical_roots_v2(
            getattr(record, field),
            f"qualified evidence {field}",
            allow_empty=allow_empty,
        )
        object.__setattr__(record, field, roots)
    reasons = canonical_texts_v2(
        record.reason_codes,
        "qualified evidence reason_codes",
        limit=MAX_COMMIT_EVIDENCE_REASON_CODES_V2,
        allow_empty=True,
    )
    object.__setattr__(record, "reason_codes", reasons)


def _validate_kind_fields(record: QualifiedCommitEvidenceV2) -> None:
    expected_weight = (record.quality_ppm * record.relevance_ppm) // WEIGHT_SCALE
    if record.weight_ppm != expected_weight:
        raise ValueError("qualified evidence weight is not reconstructable")
    if record.kind is CommitEvidenceKindV2.CHALLENGE:
        _validate_challenge_fields(record)
    else:
        _validate_observation_fields(record)
    if record.kind is CommitEvidenceKindV2.COUNTER:
        _validate_counter_fields(record)
    elif any(
        (
            record.disposition is not CommitEvidenceDispositionV2.NONE,
            record.disposition_ref,
            record.disposition_nonce,
            record.disposition_root,
            record.rebuttal_observation_roots,
            record.resolution_root,
            record.reason_codes,
        )
    ):
        raise ValueError("only counter evidence may carry a disposition")
    expected_receipts = 2 if record.kind is CommitEvidenceKindV2.COUNTER else 1
    if len(record.replay_receipt_roots) != expected_receipts:
        raise ValueError("qualified evidence replay receipt coverage is incomplete")


def _validate_challenge_fields(record: QualifiedCommitEvidenceV2) -> None:
    for field in ("category_ref", "execution_method"):
        require_text_v2(getattr(record, field), f"challenge evidence {field}")
    for field in ("execution_attestation_root", "execution_root", "result_root"):
        require_root_v2(getattr(record, field), f"challenge evidence {field}")
    if record.challenge_result is ChallengeResultV2.NONE:
        raise ValueError("challenge evidence requires a result")
    if any((record.source_ref, record.independence_ref)):
        raise ValueError("challenge evidence cannot claim observation source fields")
    if any(
        (
            record.quality_ppm,
            record.relevance_ppm,
            record.materiality_ppm,
            record.criticality_ppm,
            record.weight_ppm,
        )
    ):
        raise ValueError("challenge evidence cannot claim observation weight")
    has_results = bool(record.result_observation_roots)
    if (
        record.challenge_result is ChallengeResultV2.COUNTEREVIDENCE_FOUND
    ) != has_results:
        raise ValueError("challenge result observation coverage is invalid")


def _validate_observation_fields(record: QualifiedCommitEvidenceV2) -> None:
    require_text_v2(record.source_ref, "observation evidence source_ref")
    require_text_v2(record.independence_ref, "observation evidence independence_ref")
    if any(
        (
            record.category_ref,
            record.execution_method,
            record.execution_attestation_root,
            record.execution_root,
            record.challenge_result is not ChallengeResultV2.NONE,
            record.result_root,
            record.result_observation_roots,
        )
    ):
        raise ValueError("observation evidence cannot claim challenge fields")


def _validate_counter_fields(record: QualifiedCommitEvidenceV2) -> None:
    if record.disposition is CommitEvidenceDispositionV2.NONE:
        raise ValueError("counter evidence requires a disposition")
    for field in ("disposition_ref", "disposition_nonce"):
        require_text_v2(getattr(record, field), f"counter evidence {field}")
    require_root_v2(record.disposition_root, "counter evidence disposition_root")
    if not record.reason_codes:
        raise ValueError("counter evidence disposition requires reason codes")
    if record.disposition is CommitEvidenceDispositionV2.REBUTTED:
        if not record.rebuttal_observation_roots:
            raise ValueError("rebutted counterevidence requires rebuttal records")
    elif record.rebuttal_observation_roots:
        raise ValueError("only rebutted counterevidence may reference rebuttals")
    if record.disposition is CommitEvidenceDispositionV2.UNRESOLVED:
        if record.resolution_root:
            raise ValueError("unresolved counterevidence cannot claim resolution")
    else:
        require_root_v2(record.resolution_root, "counter evidence resolution_root")


def _validate_record_time_and_status(record: QualifiedCommitEvidenceV2) -> None:
    observed = require_count_v2(
        record.observed_at_step, "qualified evidence observed_at_step"
    )
    qualified = require_count_v2(
        record.qualified_at_step, "qualified evidence qualified_at_step"
    )
    expires = require_count_v2(
        record.expires_at_step, "qualified evidence expires_at_step"
    )
    if qualified < observed or expires <= qualified:
        raise ValueError("qualified evidence interval is invalid")
    if record.status is CommitEvidenceStatusV2.ACTIVE:
        if any(
            (
                record.revoked_at_step is not None,
                record.revocation_root,
                record.revocation_provenance_root,
                record.revocation_trace_roots,
            )
        ):
            raise ValueError("active evidence cannot carry revocation meaning")
    else:
        revoked = require_count_v2(
            record.revoked_at_step, "qualified evidence revoked_at_step"
        )
        if revoked < qualified:
            raise ValueError("evidence revocation predates qualification")
        for field in ("revocation_root", "revocation_provenance_root"):
            require_root_v2(getattr(record, field), f"qualified evidence {field}")
        if not record.revocation_trace_roots:
            raise ValueError("evidence revocation requires trace lineage")


__all__ = [
    "COMMIT_EVIDENCE_POLICY_SCHEMA_V2",
    "COMMIT_EVIDENCE_RECORD_SCHEMA_V2",
    "ChallengeResultV2",
    "CommitEvidenceDispositionV2",
    "CommitEvidenceKindV2",
    "CommitEvidencePolicySnapshotV2",
    "CommitEvidenceStatusV2",
    "QualifiedCommitEvidenceV2",
    "canonical_qualified_evidence_v2",
]
