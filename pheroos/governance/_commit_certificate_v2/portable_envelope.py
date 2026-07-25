"""Portable certificate envelope and external trust-adapter boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol, cast, runtime_checkable

from pheroos.governance._commit_certificate_v2.common import (
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
from pheroos.governance._commit_certificate_v2.portable_body import (
    CommitCertificateBodyV2,
)


COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2 = "pheroos-commit-certificate-envelope-v2"


@runtime_checkable
class CommitCertificateIssuerAttestationVerifierV2(Protocol):
    """Provider-neutral adapter supplied by the trusted coordinator boundary."""

    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class PortableCommitCertificateV2:
    """Independently verifiable envelope; portable bytes are not authority."""

    certificate_id: str
    issuer_ref: str
    issued_at_step: int
    provenance_ref: str
    envelope_nonce: str
    body: CommitCertificateBodyV2
    issuer_attestation_refs: Sequence[str]
    schema: str = COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2
    envelope_root: str = ""

    _root_field: ClassVar[str] = "envelope_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2:
            raise ValueError("commit certificate envelope schema is unsupported")
        for field in (
            "certificate_id",
            "issuer_ref",
            "provenance_ref",
            "envelope_nonce",
        ):
            _require_text(getattr(self, field), f"commit certificate envelope {field}")
        _require_count(self.issued_at_step, "commit certificate issued_at_step")
        if type(self.body) is not CommitCertificateBodyV2:
            raise TypeError("commit certificate envelope requires an exact body")
        refs = _canonical_texts(
            self.issuer_attestation_refs,
            "commit certificate issuer attestation refs",
        )
        object.__setattr__(self, "issuer_attestation_refs", refs)
        _install_root(
            self,
            "envelope_root",
            self.envelope_root,
            "envelope",
            self._body(),
        )
        if len(_canonical_bytes(self.to_dict())) > 524_288:
            raise ValueError("commit certificate envelope exceeds its byte bound")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "certificate_id": self.certificate_id,
            "issuer_ref": self.issuer_ref,
            "issued_at_step": self.issued_at_step,
            "provenance_ref": self.provenance_ref,
            "envelope_nonce": self.envelope_nonce,
            "body": self.body.to_dict(),
            "issuer_attestation_refs": list(self.issuer_attestation_refs),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "envelope_root": self.envelope_root}

    @classmethod
    def from_dict(cls, payload: object) -> PortableCommitCertificateV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "certificate_id",
                    "issuer_ref",
                    "issued_at_step",
                    "provenance_ref",
                    "envelope_nonce",
                    "body",
                    "issuer_attestation_refs",
                    "envelope_root",
                }
            ),
            "portable commit certificate v2",
        )
        refs = tuple(
            cast(str, item)
            for item in _exact_array(
                value["issuer_attestation_refs"],
                "commit certificate issuer attestation refs",
            )
        )
        decoded = cls(
            schema=cast(str, value["schema"]),
            certificate_id=cast(str, value["certificate_id"]),
            issuer_ref=cast(str, value["issuer_ref"]),
            issued_at_step=cast(int, value["issued_at_step"]),
            provenance_ref=cast(str, value["provenance_ref"]),
            envelope_nonce=cast(str, value["envelope_nonce"]),
            body=CommitCertificateBodyV2.from_dict(value["body"]),
            issuer_attestation_refs=refs,
            envelope_root=cast(str, value["envelope_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "portable commit certificate v2"
        )
        return decoded


def verify_portable_commit_certificate_v2(
    certificate_or_payload: object,
    *,
    trusted_verifier: CommitCertificateIssuerAttestationVerifierV2,
    expected_body_root: str = "",
    expected_target_ref: str = "",
    expected_candidate_ref: str = "",
    expected_claim_root: str = "",
    expected_epoch: int | None = None,
) -> bool:
    """Rebuild all roots and consult an explicitly trusted attestation adapter."""

    try:
        certificate = _certificate_from_portable(certificate_or_payload)
        if not isinstance(
            trusted_verifier, CommitCertificateIssuerAttestationVerifierV2
        ):
            return False
        body = certificate.body
        if expected_body_root and body.body_root != _require_root(
            expected_body_root, "expected commit certificate body_root"
        ):
            return False
        if expected_target_ref and body.target_ref != _require_text(
            expected_target_ref, "expected commit certificate target_ref"
        ):
            return False
        if expected_candidate_ref and body.candidate_ref != _require_text(
            expected_candidate_ref, "expected commit certificate candidate_ref"
        ):
            return False
        if expected_claim_root and body.claim_root != _require_root(
            expected_claim_root, "expected commit certificate claim_root"
        ):
            return False
        if expected_epoch is not None and body.epoch != _require_count(
            expected_epoch, "expected commit certificate epoch"
        ):
            return False
        for attestation_ref in certificate.issuer_attestation_refs:
            accepted = trusted_verifier.verify_commit_certificate_attestation_v2(
                issuer_ref=certificate.issuer_ref,
                attestation_ref=attestation_ref,
                body_root=body.body_root,
            )
            if type(accepted) is not bool or not accepted:
                return False
        return True
    except (AttributeError, TypeError, ValueError):
        return False


def _certificate_from_portable(value: object) -> PortableCommitCertificateV2:
    if type(value) is PortableCommitCertificateV2:
        certificate = value
        return PortableCommitCertificateV2.from_dict(certificate.to_dict())
    return PortableCommitCertificateV2.from_dict(value)


__all__ = [
    "COMMIT_CERTIFICATE_ENVELOPE_SCHEMA_V2",
    "CommitCertificateIssuerAttestationVerifierV2",
    "PortableCommitCertificateV2",
    "verify_portable_commit_certificate_v2",
]
