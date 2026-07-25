"""Portable principal-verification proposals; these records are not authority."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _canonical_utf8_order_v2,
    _require_bounded_text_v2,
    _require_canonical_wire_v2,
    _require_count_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)


PRINCIPAL_VERIFICATION_RECORD_SCHEMA_V2 = "pheroos-principal-verification-record-v2"
MAX_PRINCIPAL_VERIFICATIONS_V2 = 4096
MAX_VERIFICATION_EVIDENCE_ROOTS_V2 = 256
MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2 = 256


def _canonical_roots(
    values: Sequence[str], label: str, *, limit: int
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    roots = tuple(values)
    if not roots or len(roots) > limit:
        raise ValueError(f"{label} count is outside its bound")
    for value in roots:
        _require_root(value, label)
    if len(roots) != len(set(roots)):
        raise ValueError(f"{label} contains duplicates")
    return _canonical_utf8_order_v2(roots)


@dataclass(frozen=True, slots=True)
class PrincipalVerificationRecordV2:
    """Canonical verification meaning without Store inclusion or authority."""

    principal_ref: str
    cluster_ref: str
    failure_domain_ref: str
    verification_method: str
    verification_issuer_ref: str
    attestation_root: str
    evidence_roots: Sequence[str]
    issued_at_step: int
    expires_at_step: int
    provenance_ref: str
    source_trace_roots: Sequence[str]
    schema: str = PRINCIPAL_VERIFICATION_RECORD_SCHEMA_V2
    verification_root: str = ""

    _root_field: ClassVar[str] = "verification_root"

    def __post_init__(self) -> None:
        if self.schema != PRINCIPAL_VERIFICATION_RECORD_SCHEMA_V2:
            raise ValueError("principal verification record schema is unsupported")
        for field in (
            "principal_ref",
            "cluster_ref",
            "verification_method",
            "verification_issuer_ref",
            "provenance_ref",
        ):
            _require_bounded_text_v2(
                getattr(self, field), f"principal verification {field}"
            )
        _require_bounded_text_v2(
            self.failure_domain_ref,
            "principal verification failure_domain_ref",
            allow_empty=True,
        )
        _require_root(self.attestation_root, "principal verification attestation_root")
        object.__setattr__(
            self,
            "evidence_roots",
            _canonical_roots(
                self.evidence_roots,
                "principal verification evidence_roots",
                limit=MAX_VERIFICATION_EVIDENCE_ROOTS_V2,
            ),
        )
        object.__setattr__(
            self,
            "source_trace_roots",
            _canonical_roots(
                self.source_trace_roots,
                "principal verification source_trace_roots",
                limit=MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2,
            ),
        )
        issued = _require_count_v2(
            self.issued_at_step, "principal verification issued_at_step"
        )
        expires = _require_count_v2(
            self.expires_at_step, "principal verification expires_at_step"
        )
        if expires <= issued:
            raise ValueError("principal verification expiry must follow issuance")
        expected = _compute_root("principal-verification-v2:record", self._body())
        if self.verification_root not in ("", expected):
            raise ValueError("principal verification_root is mismatched")
        object.__setattr__(self, "verification_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "principal_ref": self.principal_ref,
            "cluster_ref": self.cluster_ref,
            "failure_domain_ref": self.failure_domain_ref,
            "verification_method": self.verification_method,
            "verification_issuer_ref": self.verification_issuer_ref,
            "attestation_root": self.attestation_root,
            "evidence_roots": list(self.evidence_roots),
            "issued_at_step": self.issued_at_step,
            "expires_at_step": self.expires_at_step,
            "provenance_ref": self.provenance_ref,
            "source_trace_roots": list(self.source_trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "verification_root": self.verification_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.verification_root

    @classmethod
    def from_dict(cls, payload: object) -> PrincipalVerificationRecordV2:
        value = _require_exact_mapping_v2(
            payload,
            frozenset(
                {
                    "schema",
                    "principal_ref",
                    "cluster_ref",
                    "failure_domain_ref",
                    "verification_method",
                    "verification_issuer_ref",
                    "attestation_root",
                    "evidence_roots",
                    "issued_at_step",
                    "expires_at_step",
                    "provenance_ref",
                    "source_trace_roots",
                    "verification_root",
                }
            ),
            "principal verification record v2",
        )
        for field, limit in (
            ("evidence_roots", MAX_VERIFICATION_EVIDENCE_ROOTS_V2),
            ("source_trace_roots", MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2),
        ):
            value[field] = tuple(
                _require_exact_array_v2(
                    value[field], f"principal verification {field}", limit=limit
                )
            )
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "principal verification record v2",
        )
        return decoded


def canonical_verification_records_v2(
    records: Sequence[PrincipalVerificationRecordV2],
) -> tuple[PrincipalVerificationRecordV2, ...]:
    if type(records) not in (list, tuple):
        raise TypeError("principal verification records require exact array or tuple")
    values = tuple(records)
    if len(values) > MAX_PRINCIPAL_VERIFICATIONS_V2:
        raise ValueError("principal verification record count exceeds its bound")
    if any(type(item) is not PrincipalVerificationRecordV2 for item in values):
        raise TypeError("principal verification set contains a non-exact record")
    principals = tuple(item.principal_ref for item in values)
    roots = tuple(item.verification_root for item in values)
    attestations = tuple(item.attestation_root for item in values)
    if len(principals) != len(set(principals)):
        raise ValueError("principal verification set repeats a principal")
    if len(roots) != len(set(roots)):
        raise ValueError("principal verification set repeats a record root")
    if len(attestations) != len(set(attestations)):
        raise ValueError("principal verification set reuses an attestation")
    return tuple(
        sorted(
            values,
            key=lambda item: (
                item.principal_ref.encode("utf-8"),
                item.verification_root.encode("utf-8"),
            ),
        )
    )


__all__ = [
    "MAX_PRINCIPAL_VERIFICATIONS_V2",
    "MAX_VERIFICATION_EVIDENCE_ROOTS_V2",
    "MAX_VERIFICATION_SOURCE_TRACE_ROOTS_V2",
    "PRINCIPAL_VERIFICATION_RECORD_SCHEMA_V2",
    "PrincipalVerificationRecordV2",
    "canonical_verification_records_v2",
]
