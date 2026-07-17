from __future__ import annotations

"""Stable public facade for certificate authority records and engines."""

from pheroos.governance._certificate.invariants import output_payload_fingerprint
from pheroos.governance._certificate.local import (
    LocalCommitReceipt,
    issue_local_commit_receipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    local_commit_receipt_matches,
    local_commit_receipt_payload,
    verify_local_commit_finality,
)
from pheroos.governance._certificate.outcome import (
    OutcomeCertificate,
    issue_outcome_certificate,
    outcome_certificate_body_root,
    outcome_certificate_fingerprint,
    outcome_certificate_from_payload,
    outcome_certificate_is_authoritative,
    outcome_certificate_payload,
    verify_outcome_certificate,
)
from pheroos.governance._certificate.portable import (
    EvidenceCommitCertificate,
    evidence_commit_certificate_body_root,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
    issue_evidence_commit_certificate,
    verify_evidence_commit_certificate,
    verify_evidence_commit_finality,
)
from pheroos.governance._commit.certificate_contracts import (
    CERTIFICATE_HASH_ALGORITHM as _ENGINE_CERTIFICATE_HASH_ALGORITHM,
    LOCAL_COMMIT_RECEIPT_DISCRIMINATOR as _ENGINE_LOCAL_RECEIPT_DISCRIMINATOR,
    LOCAL_COMMIT_RECEIPT_VERSION as _ENGINE_LOCAL_RECEIPT_VERSION,
)


# These direct declarations preserve the frozen public owner in ABI inventory.
LOCAL_COMMIT_RECEIPT_VERSION = "pheroos-local-commit-receipt-v1"
EVIDENCE_COMMIT_CERTIFICATE_VERSION = (
    "pheroos-evidence-commit-certificate-v1"
)
OUTCOME_CERTIFICATE_VERSION = "pheroos-outcome-certificate-v1"
LOCAL_COMMIT_RECEIPT_DISCRIMINATOR = "local_commit_receipt"
EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR = "evidence_commit_certificate"
OUTCOME_CERTIFICATE_DISCRIMINATOR = "outcome_certificate"
CERTIFICATE_HASH_ALGORITHM = "sha256"

if (
    LOCAL_COMMIT_RECEIPT_VERSION != _ENGINE_LOCAL_RECEIPT_VERSION
    or LOCAL_COMMIT_RECEIPT_DISCRIMINATOR
    != _ENGINE_LOCAL_RECEIPT_DISCRIMINATOR
    or CERTIFICATE_HASH_ALGORITHM != _ENGINE_CERTIFICATE_HASH_ALGORITHM
):
    raise RuntimeError("certificate facade constants do not match private contracts")


_PUBLIC_MODULE = __name__
for _public_object in (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    OutcomeCertificate,
    evidence_commit_certificate_body_root,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
    issue_evidence_commit_certificate,
    issue_local_commit_receipt,
    issue_outcome_certificate,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    local_commit_receipt_matches,
    local_commit_receipt_payload,
    outcome_certificate_body_root,
    outcome_certificate_fingerprint,
    outcome_certificate_from_payload,
    outcome_certificate_is_authoritative,
    outcome_certificate_payload,
    output_payload_fingerprint,
    verify_evidence_commit_certificate,
    verify_evidence_commit_finality,
    verify_local_commit_finality,
    verify_outcome_certificate,
):
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "CERTIFICATE_HASH_ALGORITHM",
    "EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR",
    "EVIDENCE_COMMIT_CERTIFICATE_VERSION",
    "LOCAL_COMMIT_RECEIPT_DISCRIMINATOR",
    "LOCAL_COMMIT_RECEIPT_VERSION",
    "OUTCOME_CERTIFICATE_DISCRIMINATOR",
    "OUTCOME_CERTIFICATE_VERSION",
    "EvidenceCommitCertificate",
    "LocalCommitReceipt",
    "OutcomeCertificate",
    "evidence_commit_certificate_body_root",
    "evidence_commit_certificate_fingerprint",
    "evidence_commit_certificate_from_payload",
    "evidence_commit_certificate_payload",
    "issue_evidence_commit_certificate",
    "issue_local_commit_receipt",
    "issue_outcome_certificate",
    "local_commit_receipt_fingerprint",
    "local_commit_receipt_is_authoritative",
    "local_commit_receipt_matches",
    "local_commit_receipt_payload",
    "outcome_certificate_body_root",
    "outcome_certificate_fingerprint",
    "outcome_certificate_from_payload",
    "outcome_certificate_is_authoritative",
    "outcome_certificate_payload",
    "output_payload_fingerprint",
    "verify_evidence_commit_certificate",
    "verify_evidence_commit_finality",
    "verify_local_commit_finality",
    "verify_outcome_certificate",
]
