"""Portable proposal, lease, revocation, and equivocation records for Support v2."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, TypeVar, TypedDict, cast

from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_canonical_wire_v2,
    _require_count_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)
from pheroos.governance._support_v2.support_evidence_contracts import (
    MAX_SUPPORT_OBSERVATIONS_V2,
    MAX_SUPPORT_TRACE_ROOTS_V2,
    SupportLeaseProposalV2,
    SupportObservationV2,
    _assurance,
    _bound_context_body,
    _bounded_root_tuple,
    _bounded_text_tuple,
    _exact_version,
    _install_root,
    _validate_bound_context,
    canonical_support_observations_v2,
)
from pheroos.governance._support_v2.support_stream_contracts import (
    support_lease_ref_v2,
    support_revocation_ref_v2,
)


SUPPORT_LEASE_SCHEMA_V2 = "pheroos-support-lease-v2"
SUPPORT_REVOCATION_SCHEMA_V2 = "pheroos-support-revocation-v2"
SUPPORT_EQUIVOCATION_SCHEMA_V2 = "pheroos-support-equivocation-v2"

MAX_SUPPORT_LEASES_V2 = 16_384
MAX_SUPPORT_REASON_CODES_V2 = 128

_IndexKeyV2 = TypeVar("_IndexKeyV2", bound=Hashable)


class _SupportLeaseDecodedV2(TypedDict):
    lease_ref: str
    mutation_transition_id: str
    proposal_root: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    principal_cluster_ref: str
    membership_principal_root: str
    principal_verification_root: str
    membership_stream_ref: str
    membership_transition_id: str
    membership_snapshot_root: str
    membership_root: str
    positive_observations: tuple[SupportObservationV2, ...]
    positive_observation_roots: tuple[str, ...]
    positive_observation_set_root: str
    prior_lease_root: str
    nonce: str
    issuance_issuer_ref: str
    issued_at_step: int
    expires_at_step: int
    proposal_provenance_root: str
    proposal_trace_roots: tuple[str, ...]
    issuance_provenance_root: str
    issuance_trace_roots: tuple[str, ...]
    schema: str
    lease_root: str


class _SupportRevocationDecodedV2(TypedDict):
    revocation_ref: str
    mutation_transition_id: str
    lease_root: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    principal_cluster_ref: str
    reason_codes: tuple[str, ...]
    lease_issuance_issuer_ref: str
    revocation_issuer_ref: str
    revoked_at_step: int
    provenance_root: str
    source_trace_roots: tuple[str, ...]
    schema: str
    revocation_root: str


class SupportLeaseStatusV2(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    EQUIVOCATED = "equivocated"


@dataclass(frozen=True, slots=True)
class SupportLeaseV2:
    lease_ref: str
    mutation_transition_id: str
    proposal_root: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    principal_cluster_ref: str
    membership_principal_root: str
    principal_verification_root: str
    membership_stream_ref: str
    membership_transition_id: str
    membership_snapshot_root: str
    membership_root: str
    positive_observations: Sequence[SupportObservationV2]
    positive_observation_roots: Sequence[str]
    positive_observation_set_root: str
    prior_lease_root: str
    nonce: str
    issuance_issuer_ref: str
    issued_at_step: int
    expires_at_step: int
    proposal_provenance_root: str
    proposal_trace_roots: Sequence[str]
    issuance_provenance_root: str
    issuance_trace_roots: Sequence[str]
    schema: str = SUPPORT_LEASE_SCHEMA_V2
    lease_root: str = ""

    _root_field: ClassVar[str] = "lease_root"

    def __post_init__(self) -> None:
        _exact_version(self.schema, SUPPORT_LEASE_SCHEMA_V2, "support lease schema")
        _validate_bound_context(self, "support lease")
        for field in (
            "lease_ref",
            "mutation_transition_id",
            "candidate_ref",
            "principal_ref",
            "principal_cluster_ref",
            "membership_stream_ref",
            "membership_transition_id",
            "nonce",
            "issuance_issuer_ref",
        ):
            _require_bounded_text_v2(getattr(self, field), f"support lease {field}")
        for field in (
            "proposal_root",
            "claim_root",
            "membership_principal_root",
            "principal_verification_root",
            "membership_snapshot_root",
            "membership_root",
            "proposal_provenance_root",
            "issuance_provenance_root",
        ):
            _require_root(getattr(self, field), f"support lease {field}")
        expected_ref = support_lease_ref_v2(
            self.mutation_transition_id,
            self.proposal_root,
        )
        if self.lease_ref != expected_ref:
            raise ValueError("support lease_ref is not transition-derived")
        if self.prior_lease_root:
            _require_root(self.prior_lease_root, "support lease prior_lease_root")
        issued = _require_count_v2(self.issued_at_step, "support lease issued_at_step")
        expires = _require_count_v2(
            self.expires_at_step, "support lease expires_at_step"
        )
        if expires <= issued:
            raise ValueError("support lease expiry must be after issuance")
        observations = canonical_support_observations_v2(self.positive_observations)
        object.__setattr__(self, "positive_observations", observations)
        roots = _bounded_root_tuple(
            self.positive_observation_roots,
            "support lease positive observations",
            limit=MAX_SUPPORT_OBSERVATIONS_V2,
        )
        expected_roots = tuple(item.observation_root for item in observations)
        if roots != expected_roots:
            raise ValueError(
                "support lease observation records and roots are mismatched"
            )
        object.__setattr__(self, "positive_observation_roots", roots)
        _install_root(
            self,
            "positive_observation_set_root",
            self.positive_observation_set_root,
            "observation-set",
            {"observation_roots": list(roots)},
        )
        for field in ("proposal_trace_roots", "issuance_trace_roots"):
            object.__setattr__(
                self,
                field,
                _bounded_root_tuple(
                    getattr(self, field),
                    f"support lease {field}",
                    limit=MAX_SUPPORT_TRACE_ROOTS_V2,
                ),
            )
        _install_root(self, "lease_root", self.lease_root, "lease", self._body())

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "lease_ref": self.lease_ref,
            "mutation_transition_id": self.mutation_transition_id,
            "proposal_root": self.proposal_root,
            **_bound_context_body(self),
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "principal_ref": self.principal_ref,
            "principal_cluster_ref": self.principal_cluster_ref,
            "membership_principal_root": self.membership_principal_root,
            "principal_verification_root": self.principal_verification_root,
            "membership_stream_ref": self.membership_stream_ref,
            "membership_transition_id": self.membership_transition_id,
            "membership_snapshot_root": self.membership_snapshot_root,
            "membership_root": self.membership_root,
            "positive_observations": [
                item.to_dict() for item in self.positive_observations
            ],
            "positive_observation_roots": list(self.positive_observation_roots),
            "positive_observation_set_root": self.positive_observation_set_root,
            "prior_lease_root": self.prior_lease_root,
            "nonce": self.nonce,
            "issuance_issuer_ref": self.issuance_issuer_ref,
            "issued_at_step": self.issued_at_step,
            "expires_at_step": self.expires_at_step,
            "proposal_provenance_root": self.proposal_provenance_root,
            "proposal_trace_roots": list(self.proposal_trace_roots),
            "issuance_provenance_root": self.issuance_provenance_root,
            "issuance_trace_roots": list(self.issuance_trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "lease_root": self.lease_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> SupportLeaseV2:
        fields = frozenset(
            {
                "schema",
                "lease_ref",
                "mutation_transition_id",
                "proposal_root",
                "profile",
                "assurance",
                "manifest_root",
                "commit_policy_root",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "candidate_ref",
                "claim_root",
                "epoch",
                "principal_ref",
                "principal_cluster_ref",
                "membership_principal_root",
                "principal_verification_root",
                "membership_stream_ref",
                "membership_transition_id",
                "membership_snapshot_root",
                "membership_root",
                "positive_observations",
                "positive_observation_roots",
                "positive_observation_set_root",
                "prior_lease_root",
                "nonce",
                "issuance_issuer_ref",
                "issued_at_step",
                "expires_at_step",
                "proposal_provenance_root",
                "proposal_trace_roots",
                "issuance_provenance_root",
                "issuance_trace_roots",
                "lease_root",
            }
        )
        value = _require_exact_mapping_v2(payload, fields, "support lease v2")
        value["assurance"] = _assurance(value["assurance"], "support lease")
        raw_observations = _require_exact_array_v2(
            value["positive_observations"],
            "support lease observations",
            limit=MAX_SUPPORT_OBSERVATIONS_V2,
        )
        value["positive_observations"] = tuple(
            SupportObservationV2.from_dict(item) for item in raw_observations
        )
        raw = _require_exact_array_v2(
            value["positive_observation_roots"],
            "support lease observations",
            limit=MAX_SUPPORT_OBSERVATIONS_V2,
        )
        value["positive_observation_roots"] = tuple(raw)
        for field in ("proposal_trace_roots", "issuance_trace_roots"):
            value[field] = tuple(
                _require_exact_array_v2(
                    value[field],
                    f"support lease {field}",
                    limit=MAX_SUPPORT_TRACE_ROOTS_V2,
                )
            )
        decoded = cls(**cast(_SupportLeaseDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support lease v2",
        )
        return decoded


@dataclass(frozen=True, slots=True)
class SupportRevocationV2:
    revocation_ref: str
    mutation_transition_id: str
    lease_root: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    principal_cluster_ref: str
    reason_codes: Sequence[str]
    lease_issuance_issuer_ref: str
    revocation_issuer_ref: str
    revoked_at_step: int
    provenance_root: str
    source_trace_roots: Sequence[str]
    schema: str = SUPPORT_REVOCATION_SCHEMA_V2
    revocation_root: str = ""

    _root_field: ClassVar[str] = "revocation_root"

    def __post_init__(self) -> None:
        _exact_version(
            self.schema, SUPPORT_REVOCATION_SCHEMA_V2, "support revocation schema"
        )
        _validate_bound_context(self, "support revocation")
        for field in (
            "revocation_ref",
            "mutation_transition_id",
            "candidate_ref",
            "principal_ref",
            "principal_cluster_ref",
            "lease_issuance_issuer_ref",
            "revocation_issuer_ref",
        ):
            _require_bounded_text_v2(
                getattr(self, field), f"support revocation {field}"
            )
        for field in ("lease_root", "claim_root", "provenance_root"):
            _require_root(getattr(self, field), f"support revocation {field}")
        expected_ref = support_revocation_ref_v2(
            self.mutation_transition_id,
            self.lease_root,
        )
        if self.revocation_ref != expected_ref:
            raise ValueError("support revocation_ref is not transition-derived")
        _require_count_v2(self.revoked_at_step, "support revocation revoked_at_step")
        reasons = _bounded_text_tuple(
            self.reason_codes,
            "support revocation reason codes",
            limit=MAX_SUPPORT_REASON_CODES_V2,
        )
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(
            self,
            "source_trace_roots",
            _bounded_root_tuple(
                self.source_trace_roots,
                "support revocation source trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            ),
        )
        _install_root(
            self, "revocation_root", self.revocation_root, "revocation", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "revocation_ref": self.revocation_ref,
            "mutation_transition_id": self.mutation_transition_id,
            "lease_root": self.lease_root,
            **_bound_context_body(self),
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "principal_ref": self.principal_ref,
            "principal_cluster_ref": self.principal_cluster_ref,
            "reason_codes": list(self.reason_codes),
            "lease_issuance_issuer_ref": self.lease_issuance_issuer_ref,
            "revocation_issuer_ref": self.revocation_issuer_ref,
            "revoked_at_step": self.revoked_at_step,
            "provenance_root": self.provenance_root,
            "source_trace_roots": list(self.source_trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "revocation_root": self.revocation_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> SupportRevocationV2:
        fields = frozenset(
            {
                "schema",
                "revocation_ref",
                "mutation_transition_id",
                "lease_root",
                "profile",
                "assurance",
                "manifest_root",
                "commit_policy_root",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "candidate_ref",
                "claim_root",
                "epoch",
                "principal_ref",
                "principal_cluster_ref",
                "reason_codes",
                "lease_issuance_issuer_ref",
                "revocation_issuer_ref",
                "revoked_at_step",
                "provenance_root",
                "source_trace_roots",
                "revocation_root",
            }
        )
        value = _require_exact_mapping_v2(payload, fields, "support revocation v2")
        value["assurance"] = _assurance(value["assurance"], "support revocation")
        raw = _require_exact_array_v2(
            value["reason_codes"],
            "support revocation reason codes",
            limit=MAX_SUPPORT_REASON_CODES_V2,
        )
        value["reason_codes"] = tuple(raw)
        value["source_trace_roots"] = tuple(
            _require_exact_array_v2(
                value["source_trace_roots"],
                "support revocation source trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            )
        )
        decoded = cls(**cast(_SupportRevocationDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support revocation v2",
        )
        return decoded


def canonical_support_leases_v2(
    leases: Sequence[SupportLeaseV2],
) -> tuple[SupportLeaseV2, ...]:
    if type(leases) not in (list, tuple):
        raise TypeError("support leases must be an exact array or tuple")
    values = tuple(leases)
    if len(values) > MAX_SUPPORT_LEASES_V2:
        raise ValueError("support active lease projection exceeds its bound")
    if any(type(item) is not SupportLeaseV2 for item in values):
        raise TypeError("support leases contain a non-canonical record")
    ordered = tuple(sorted(values, key=lambda item: item.lease_root.encode()))
    by_id: dict[str, str] = {}
    by_proposal: dict[str, str] = {}
    by_nonce: dict[tuple[str, str], str] = {}
    seen_roots: set[str] = set()
    for lease in ordered:
        if lease.lease_root in seen_roots:
            raise ValueError("support snapshot repeats a lease root")
        seen_roots.add(lease.lease_root)
        _index_collision(by_id, lease.lease_ref, lease.lease_root, "lease_ref")
        _index_collision(
            by_proposal, lease.proposal_root, lease.lease_root, "proposal_root"
        )
        _index_collision(
            by_nonce,
            (lease.principal_cluster_ref, lease.nonce),
            lease.lease_root,
            "cluster nonce",
        )
    return ordered


def _index_collision(
    index: dict[_IndexKeyV2, str],
    key: _IndexKeyV2,
    record_root: str,
    axis: str,
) -> None:
    if key in index:
        raise ValueError(f"support {axis} replay collision is a safety violation")
    index[key] = record_root


__all__ = [
    "MAX_SUPPORT_LEASES_V2",
    "MAX_SUPPORT_OBSERVATIONS_V2",
    "MAX_SUPPORT_REASON_CODES_V2",
    "MAX_SUPPORT_TRACE_ROOTS_V2",
    "SupportLeaseProposalV2",
    "SupportLeaseStatusV2",
    "SupportLeaseV2",
    "SupportObservationV2",
    "SupportRevocationV2",
    "canonical_support_leases_v2",
    "canonical_support_observations_v2",
]
