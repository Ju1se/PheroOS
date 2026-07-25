"""Portable Commit Evidence v2 attestations and governance proposals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

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
from pheroos.governance._commit_evidence_projection_v2.records import (
    ChallengeResultV2,
    CommitEvidenceDispositionV2,
    CommitEvidenceKindV2,
)


COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2 = "pheroos-commit-evidence-attestation-v2"
COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2 = (
    "pheroos-counterevidence-disposition-proposal-v2"
)
COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2 = "pheroos-commit-evidence-revocation-v2"


@dataclass(frozen=True, slots=True)
class CommitEvidenceAttestationV2:
    evidence_ref: str
    kind: CommitEvidenceKindV2
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    payload_root: str
    source_ref: str
    independence_ref: str
    reported_quality_ppm: int
    reported_relevance_ppm: int
    reported_materiality_ppm: int
    reported_criticality_ppm: int
    category_ref: str
    execution_method: str
    execution_attestation_root: str
    execution_root: str
    challenge_result: ChallengeResultV2
    result_root: str
    result_observation_roots: Sequence[str]
    nonce: str
    observed_at_step: int
    expires_at_step: int
    provenance_root: str
    trace_roots: Sequence[str]
    schema: str = COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2
    attestation_root: str = ""

    _root_field: ClassVar[str] = "attestation_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2:
            raise ValueError("commit evidence attestation schema is unsupported")
        if type(self.kind) is not CommitEvidenceKindV2:
            raise TypeError("commit evidence attestation kind is invalid")
        if type(self.challenge_result) is not ChallengeResultV2:
            raise TypeError("commit evidence challenge result is invalid")
        for field in ("evidence_ref", "candidate_ref", "principal_ref", "nonce"):
            require_text_v2(getattr(self, field), f"evidence attestation {field}")
        for field in ("claim_root", "payload_root", "provenance_root"):
            require_root_v2(getattr(self, field), f"evidence attestation {field}")
        require_count_v2(self.epoch, "evidence attestation epoch")
        _validate_reported_metrics(self)
        _validate_attestation_kind(self)
        observed = require_count_v2(
            self.observed_at_step, "evidence attestation observed_at_step"
        )
        expires = require_count_v2(
            self.expires_at_step, "evidence attestation expires_at_step"
        )
        if expires <= observed:
            raise ValueError("evidence attestation expiry must follow observation")
        object.__setattr__(
            self,
            "result_observation_roots",
            canonical_roots_v2(
                self.result_observation_roots,
                "evidence attestation result_observation_roots",
            ),
        )
        object.__setattr__(
            self,
            "trace_roots",
            canonical_roots_v2(
                self.trace_roots,
                "evidence attestation trace_roots",
                allow_empty=False,
            ),
        )
        _validate_challenge_result_roots(self)
        expected = evidence_root_v2("attestation", self._body())
        if self.attestation_root not in ("", expected):
            raise ValueError("commit evidence attestation_root is mismatched")
        object.__setattr__(self, "attestation_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "evidence_ref": self.evidence_ref,
            "kind": self.kind.value,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "epoch": self.epoch,
            "principal_ref": self.principal_ref,
            "payload_root": self.payload_root,
            "source_ref": self.source_ref,
            "independence_ref": self.independence_ref,
            "reported_quality_ppm": self.reported_quality_ppm,
            "reported_relevance_ppm": self.reported_relevance_ppm,
            "reported_materiality_ppm": self.reported_materiality_ppm,
            "reported_criticality_ppm": self.reported_criticality_ppm,
            "category_ref": self.category_ref,
            "execution_method": self.execution_method,
            "execution_attestation_root": self.execution_attestation_root,
            "execution_root": self.execution_root,
            "challenge_result": self.challenge_result.value,
            "result_root": self.result_root,
            "result_observation_roots": list(self.result_observation_roots),
            "nonce": self.nonce,
            "observed_at_step": self.observed_at_step,
            "expires_at_step": self.expires_at_step,
            "provenance_root": self.provenance_root,
            "trace_roots": list(self.trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "attestation_root": self.attestation_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitEvidenceAttestationV2:
        value = exact_object_v2(
            payload, _ATTESTATION_FIELDS, "commit evidence attestation v2"
        )
        try:
            value["kind"] = CommitEvidenceKindV2(value["kind"])
            value["challenge_result"] = ChallengeResultV2(value["challenge_result"])
        except (TypeError, ValueError) as exc:
            raise ValueError("commit evidence attestation enum is unsupported") from exc
        for field in ("result_observation_roots", "trace_roots"):
            value[field] = tuple(
                exact_array_v2(
                    value[field],
                    f"commit evidence attestation {field}",
                    limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
                )
            )
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload, decoded.to_dict(), "commit evidence attestation v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CounterevidenceDispositionProposalV2:
    disposition_ref: str
    counter_attestation_root: str
    disposition: CommitEvidenceDispositionV2
    rebuttal_observation_roots: Sequence[str]
    resolution_root: str
    reason_codes: Sequence[str]
    nonce: str
    issued_at_step: int
    expires_at_step: int
    provenance_root: str
    trace_roots: Sequence[str]
    schema: str = COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2
    disposition_root: str = ""

    _root_field: ClassVar[str] = "disposition_root"

    def __post_init__(self) -> None:
        if self.schema != COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2:
            raise ValueError(
                "counterevidence disposition proposal schema is unsupported"
            )
        if (
            self.disposition
            in {
                CommitEvidenceDispositionV2.NONE,
            }
            or type(self.disposition) is not CommitEvidenceDispositionV2
        ):
            raise ValueError("counterevidence disposition proposal kind is invalid")
        for field in ("disposition_ref", "nonce"):
            require_text_v2(
                getattr(self, field), f"counterevidence disposition {field}"
            )
        for field in ("counter_attestation_root", "provenance_root"):
            require_root_v2(
                getattr(self, field), f"counterevidence disposition {field}"
            )
        rebuttals = canonical_roots_v2(
            self.rebuttal_observation_roots,
            "counterevidence disposition rebuttal_observation_roots",
        )
        object.__setattr__(self, "rebuttal_observation_roots", rebuttals)
        reasons = canonical_texts_v2(
            self.reason_codes,
            "counterevidence disposition reason_codes",
            limit=MAX_COMMIT_EVIDENCE_REASON_CODES_V2,
            allow_empty=False,
        )
        object.__setattr__(self, "reason_codes", reasons)
        traces = canonical_roots_v2(
            self.trace_roots,
            "counterevidence disposition trace_roots",
            allow_empty=False,
        )
        object.__setattr__(self, "trace_roots", traces)
        _validate_disposition_resolution(self)
        issued = require_count_v2(
            self.issued_at_step, "counterevidence disposition issued_at_step"
        )
        expires = require_count_v2(
            self.expires_at_step, "counterevidence disposition expires_at_step"
        )
        if expires <= issued:
            raise ValueError("counterevidence disposition expiry must follow issuance")
        expected = evidence_root_v2("counter-disposition", self._body())
        if self.disposition_root not in ("", expected):
            raise ValueError("counterevidence disposition_root is mismatched")
        object.__setattr__(self, "disposition_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "disposition_ref": self.disposition_ref,
            "counter_attestation_root": self.counter_attestation_root,
            "disposition": self.disposition.value,
            "rebuttal_observation_roots": list(self.rebuttal_observation_roots),
            "resolution_root": self.resolution_root,
            "reason_codes": list(self.reason_codes),
            "nonce": self.nonce,
            "issued_at_step": self.issued_at_step,
            "expires_at_step": self.expires_at_step,
            "provenance_root": self.provenance_root,
            "trace_roots": list(self.trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "disposition_root": self.disposition_root}

    @classmethod
    def from_dict(cls, payload: object) -> CounterevidenceDispositionProposalV2:
        value = exact_object_v2(
            payload, _DISPOSITION_FIELDS, "counterevidence disposition v2"
        )
        try:
            value["disposition"] = CommitEvidenceDispositionV2(value["disposition"])
        except (TypeError, ValueError) as exc:
            raise ValueError("counterevidence disposition is unsupported") from exc
        for field in ("rebuttal_observation_roots", "reason_codes", "trace_roots"):
            value[field] = tuple(
                exact_array_v2(
                    value[field],
                    f"counterevidence disposition {field}",
                    limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
                )
            )
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload, decoded.to_dict(), "counterevidence disposition v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CommitEvidenceRevocationV2:
    revocation_ref: str
    record_ref: str
    record_root: str
    revoked_at_step: int
    reason_codes: Sequence[str]
    provenance_root: str
    trace_roots: Sequence[str]
    schema: str = COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2
    revocation_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2:
            raise ValueError("commit evidence revocation schema is unsupported")
        for field in ("revocation_ref", "record_ref"):
            require_text_v2(getattr(self, field), f"evidence revocation {field}")
        for field in ("record_root", "provenance_root"):
            require_root_v2(getattr(self, field), f"evidence revocation {field}")
        require_count_v2(self.revoked_at_step, "evidence revocation revoked_at_step")
        object.__setattr__(
            self,
            "reason_codes",
            canonical_texts_v2(
                self.reason_codes,
                "evidence revocation reason_codes",
                limit=MAX_COMMIT_EVIDENCE_REASON_CODES_V2,
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "trace_roots",
            canonical_roots_v2(
                self.trace_roots, "evidence revocation trace_roots", allow_empty=False
            ),
        )
        expected = evidence_root_v2("revocation", self._body())
        if self.revocation_root not in ("", expected):
            raise ValueError("commit evidence revocation_root is mismatched")
        object.__setattr__(self, "revocation_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "revocation_ref": self.revocation_ref,
            "record_ref": self.record_ref,
            "record_root": self.record_root,
            "revoked_at_step": self.revoked_at_step,
            "reason_codes": list(self.reason_codes),
            "provenance_root": self.provenance_root,
            "trace_roots": list(self.trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "revocation_root": self.revocation_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitEvidenceRevocationV2:
        value = exact_object_v2(
            payload, _REVOCATION_FIELDS, "commit evidence revocation v2"
        )
        for field in ("reason_codes", "trace_roots"):
            value[field] = tuple(
                exact_array_v2(
                    value[field],
                    f"commit evidence revocation {field}",
                    limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
                )
            )
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload, decoded.to_dict(), "commit evidence revocation v2"
        )
        return decoded


def canonical_attestations_v2(
    values: Sequence[CommitEvidenceAttestationV2],
) -> tuple[CommitEvidenceAttestationV2, ...]:
    if (
        type(values) not in (list, tuple)
        or len(values) > MAX_COMMIT_EVIDENCE_RECORDS_V2
    ):
        raise TypeError("commit evidence attestations require a bounded array or tuple")
    items = tuple(values)
    if any(type(item) is not CommitEvidenceAttestationV2 for item in items):
        raise TypeError("commit evidence attestations contain a non-exact record")
    for identities in (
        tuple(item.evidence_ref for item in items),
        tuple(item.nonce for item in items),
        tuple(item.attestation_root for item in items),
    ):
        if len(identities) != len(set(identities)):
            raise ValueError("commit evidence attestations repeat an identity")
    return tuple(sorted(items, key=lambda item: item.evidence_ref.encode("utf-8")))


def canonical_dispositions_v2(
    values: Sequence[CounterevidenceDispositionProposalV2],
) -> tuple[CounterevidenceDispositionProposalV2, ...]:
    if (
        type(values) not in (list, tuple)
        or len(values) > MAX_COMMIT_EVIDENCE_RECORDS_V2
    ):
        raise TypeError("counterevidence dispositions require a bounded array or tuple")
    items = tuple(values)
    if any(type(item) is not CounterevidenceDispositionProposalV2 for item in items):
        raise TypeError("counterevidence dispositions contain a non-exact record")
    for identities in (
        tuple(item.disposition_ref for item in items),
        tuple(item.nonce for item in items),
        tuple(item.counter_attestation_root for item in items),
    ):
        if len(identities) != len(set(identities)):
            raise ValueError("counterevidence dispositions repeat an identity")
    return tuple(sorted(items, key=lambda item: item.disposition_ref.encode("utf-8")))


def canonical_revocations_v2(
    values: Sequence[CommitEvidenceRevocationV2],
) -> tuple[CommitEvidenceRevocationV2, ...]:
    if (
        type(values) not in (list, tuple)
        or len(values) > MAX_COMMIT_EVIDENCE_RECORDS_V2
    ):
        raise TypeError("commit evidence revocations require a bounded array or tuple")
    items = tuple(values)
    if any(type(item) is not CommitEvidenceRevocationV2 for item in items):
        raise TypeError("commit evidence revocations contain a non-exact record")
    refs = tuple(item.record_ref for item in items)
    roots = tuple(item.revocation_root for item in items)
    if len(refs) != len(set(refs)) or len(roots) != len(set(roots)):
        raise ValueError("commit evidence revocations repeat an identity")
    return tuple(sorted(items, key=lambda item: item.record_ref.encode("utf-8")))


def _validate_reported_metrics(attestation: CommitEvidenceAttestationV2) -> None:
    for field in (
        "reported_quality_ppm",
        "reported_relevance_ppm",
        "reported_materiality_ppm",
        "reported_criticality_ppm",
    ):
        value = require_count_v2(
            getattr(attestation, field), f"evidence attestation {field}"
        )
        if value > WEIGHT_SCALE:
            raise ValueError(f"evidence attestation {field} exceeds its scale")


def _validate_attestation_kind(attestation: CommitEvidenceAttestationV2) -> None:
    if attestation.kind is CommitEvidenceKindV2.CHALLENGE:
        for field in ("category_ref", "execution_method"):
            require_text_v2(
                getattr(attestation, field), f"challenge attestation {field}"
            )
        for field in ("execution_attestation_root", "execution_root", "result_root"):
            require_root_v2(
                getattr(attestation, field), f"challenge attestation {field}"
            )
        if any(
            (
                attestation.source_ref,
                attestation.independence_ref,
                attestation.reported_quality_ppm,
                attestation.reported_relevance_ppm,
                attestation.reported_materiality_ppm,
                attestation.reported_criticality_ppm,
            )
        ):
            raise ValueError("challenge attestation cannot claim observation fields")
    else:
        require_text_v2(attestation.source_ref, "observation attestation source_ref")
        require_text_v2(
            attestation.independence_ref, "observation attestation independence_ref"
        )
        if any(
            (
                attestation.category_ref,
                attestation.execution_method,
                attestation.execution_attestation_root,
                attestation.execution_root,
                attestation.challenge_result is not ChallengeResultV2.NONE,
                attestation.result_root,
                attestation.result_observation_roots,
            )
        ):
            raise ValueError("observation attestation cannot claim challenge fields")


def _validate_challenge_result_roots(attestation: CommitEvidenceAttestationV2) -> None:
    if attestation.kind is not CommitEvidenceKindV2.CHALLENGE:
        return
    if attestation.challenge_result is ChallengeResultV2.NONE:
        raise ValueError("challenge attestation requires a result")
    has_results = bool(attestation.result_observation_roots)
    if (
        attestation.challenge_result is ChallengeResultV2.COUNTEREVIDENCE_FOUND
    ) != has_results:
        raise ValueError("challenge result observation coverage is invalid")


def _validate_disposition_resolution(
    proposal: CounterevidenceDispositionProposalV2,
) -> None:
    if proposal.disposition is CommitEvidenceDispositionV2.REBUTTED:
        if not proposal.rebuttal_observation_roots:
            raise ValueError("rebutted counterevidence requires rebuttal observations")
    elif proposal.rebuttal_observation_roots:
        raise ValueError("only rebutted counterevidence may reference rebuttals")
    if proposal.disposition is CommitEvidenceDispositionV2.UNRESOLVED:
        if proposal.resolution_root:
            raise ValueError("unresolved counterevidence cannot claim resolution")
    else:
        require_root_v2(proposal.resolution_root, "counterevidence resolution_root")


_ATTESTATION_FIELDS = frozenset(
    {
        "schema",
        "evidence_ref",
        "kind",
        "candidate_ref",
        "claim_root",
        "epoch",
        "principal_ref",
        "payload_root",
        "source_ref",
        "independence_ref",
        "reported_quality_ppm",
        "reported_relevance_ppm",
        "reported_materiality_ppm",
        "reported_criticality_ppm",
        "category_ref",
        "execution_method",
        "execution_attestation_root",
        "execution_root",
        "challenge_result",
        "result_root",
        "result_observation_roots",
        "nonce",
        "observed_at_step",
        "expires_at_step",
        "provenance_root",
        "trace_roots",
        "attestation_root",
    }
)
_DISPOSITION_FIELDS = frozenset(
    {
        "schema",
        "disposition_ref",
        "counter_attestation_root",
        "disposition",
        "rebuttal_observation_roots",
        "resolution_root",
        "reason_codes",
        "nonce",
        "issued_at_step",
        "expires_at_step",
        "provenance_root",
        "trace_roots",
        "disposition_root",
    }
)
_REVOCATION_FIELDS = frozenset(
    {
        "schema",
        "revocation_ref",
        "record_ref",
        "record_root",
        "revoked_at_step",
        "reason_codes",
        "provenance_root",
        "trace_roots",
        "revocation_root",
    }
)


__all__ = [
    "COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2",
    "COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2",
    "COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2",
    "CommitEvidenceAttestationV2",
    "CommitEvidenceRevocationV2",
    "CounterevidenceDispositionProposalV2",
    "canonical_attestations_v2",
    "canonical_dispositions_v2",
    "canonical_revocations_v2",
]
