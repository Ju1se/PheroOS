"""Registry-free reader for historical portable Commit v1 certificates.

This surface validates archived bytes and supplied attestation bindings only.
It does not establish StateStore inclusion, currentness, session authority,
publication authority, or finality.
"""

from __future__ import annotations

from pheroos.governance._certificate.historical import (
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
    verify_evidence_commit_certificate,
)
from pheroos.governance._certificate.records import EvidenceCommitCertificate


# These are the exact legacy public objects.  Preserve their established owner
# for introspection and pickle compatibility without importing the authority-
# bearing ``certificate`` facade.
for _public_object in (
    EvidenceCommitCertificate,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
    verify_evidence_commit_certificate,
):
    _public_object.__module__ = "pheroos.governance.certificate"
del _public_object


__all__ = [
    "EvidenceCommitCertificate",
    "evidence_commit_certificate_fingerprint",
    "evidence_commit_certificate_from_payload",
    "evidence_commit_certificate_payload",
    "verify_evidence_commit_certificate",
]
