"""Typed certificate selection for terminal output authorization."""

from __future__ import annotations

from pheroos.governance._certificate.local import LocalCommitReceipt
from pheroos.governance._certificate.outcome import OutcomeCertificate
from pheroos.governance._certificate.portable import EvidenceCommitCertificate
from pheroos.governance.commit_state import DecisionOutcome, DecisionOutcomeKind
from pheroos.governance.distributed_commit import DistributedCommitCertificate
from pheroos.protocol.commit_models import CommitAssurance


def _certificate_for_outcome(
    outcome: DecisionOutcome,
    *,
    local_receipt: LocalCommitReceipt | None,
    evidence_certificate: EvidenceCommitCertificate | None,
    distributed_certificate: DistributedCommitCertificate | None,
    outcome_certificate: OutcomeCertificate | None,
) -> (
    LocalCommitReceipt
    | EvidenceCommitCertificate
    | DistributedCommitCertificate
    | OutcomeCertificate
    | None
):
    if outcome.kind is not DecisionOutcomeKind.EVIDENCE_COMMIT:
        return outcome_certificate
    if outcome.assurance is CommitAssurance.EVIDENCE_BOUND:
        return local_receipt
    if outcome.assurance is CommitAssurance.CERTIFIED:
        return evidence_certificate
    if outcome.assurance is CommitAssurance.DISTRIBUTED:
        return distributed_certificate
    return None


__all__: list[str] = []
