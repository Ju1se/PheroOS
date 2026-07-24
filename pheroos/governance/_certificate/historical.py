"""Registry-free reader for historical portable v1 certificate proofs.

These functions validate frozen ``pheroos-evidence-commit-certificate-v1``
bytes and caller-supplied attestation bindings.  They do not establish current
StateStore inclusion, session authority, publication authority, or finality.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pheroos.governance._certificate.invariants import (
    _attestations_match,
    _coerce_assurance,
    _coerce_authority,
    _coerce_authority_scope,
    _dataclass_public_payload,
    _require_sequence,
    _strict_payload_values,
)
from pheroos.governance._certificate.records import (
    EVIDENCE_COMMIT_CERTIFICATE_VERSION,
    EvidenceCommitCertificate,
    _validate_evidence_commit_certificate,
)
from pheroos.governance._commit_validation import require_commit_fingerprint
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError


def evidence_commit_certificate_payload(
    certificate: EvidenceCommitCertificate,
) -> dict[str, object]:
    if type(certificate) is not EvidenceCommitCertificate:
        raise GovernanceError(
            "evidence commit certificate must use the canonical record"
        )
    _validate_evidence_commit_certificate(certificate)
    return _dataclass_public_payload(certificate)


def evidence_commit_certificate_fingerprint(
    certificate: EvidenceCommitCertificate,
) -> str:
    return commit_payload_fingerprint(
        evidence_commit_certificate_payload(certificate),
        schema=EVIDENCE_COMMIT_CERTIFICATE_VERSION,
        profile=certificate.profile,
    )


def evidence_commit_certificate_from_payload(
    payload: Mapping[str, object],
) -> EvidenceCommitCertificate:
    values = _strict_payload_values(
        payload,
        EvidenceCommitCertificate,
        field_name="evidence commit certificate payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority_scope"] = _coerce_authority_scope(values["authority_scope"])
    values["authority"] = _coerce_authority(values["authority"])
    values["issuer_attestation_refs"] = tuple(
        _require_sequence(values["issuer_attestation_refs"], "issuer attestations")
    )
    try:
        # The strict decoder above verifies the complete dataclass field set and
        # coerces every non-text field before this dynamic ABI reconstruction.
        return EvidenceCommitCertificate(**values)  # type: ignore[arg-type]
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"evidence commit certificate payload is invalid: {exc}"
        ) from exc


def verify_evidence_commit_certificate(
    certificate_or_payload: EvidenceCommitCertificate | Mapping[str, object],
    *,
    trusted_issuer_attestations: Mapping[str, str],
    expected_certificate_ref: str = "",
    expected_claim_fingerprint: str = "",
    expected_output_payload_fingerprint: str = "",
) -> bool:
    """Validate historical v1 proof bytes without issuing runtime authority."""

    try:
        certificate = (
            certificate_or_payload
            if type(certificate_or_payload) is EvidenceCommitCertificate
            else evidence_commit_certificate_from_payload(
                cast(Mapping[str, object], certificate_or_payload)
            )
        )
        assert type(certificate) is EvidenceCommitCertificate
        _validate_evidence_commit_certificate(certificate)
        if not _attestations_match(
            certificate.issuer_attestation_refs,
            trusted_issuer_attestations,
            body_root=certificate.certificate_body_root,
        ):
            return False
        if expected_certificate_ref and (
            evidence_commit_certificate_fingerprint(certificate)
            != require_commit_fingerprint(
                expected_certificate_ref,
                "expected evidence certificate ref",
            )
        ):
            return False
        if expected_claim_fingerprint and (
            certificate.claim_fingerprint
            != require_commit_fingerprint(
                expected_claim_fingerprint,
                "expected evidence certificate claim",
            )
        ):
            return False
        if expected_output_payload_fingerprint and (
            certificate.output_payload_fingerprint
            != require_commit_fingerprint(
                expected_output_payload_fingerprint,
                "expected evidence certificate output",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


__all__ = [
    "evidence_commit_certificate_fingerprint",
    "evidence_commit_certificate_from_payload",
    "evidence_commit_certificate_payload",
    "verify_evidence_commit_certificate",
]
