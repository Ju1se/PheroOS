"""Authority-neutral Commit Replay projections for Evidence v2 records."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._commit_evidence_owner_v2.proposals import (
    CommitEvidenceAttestationV2,
    CounterevidenceDispositionProposalV2,
    canonical_attestations_v2,
    canonical_dispositions_v2,
)
from pheroos.governance._commit_evidence_projection_v2.common import require_text_v2
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceKindV2,
    QualifiedCommitEvidenceV2,
)
from pheroos.governance._commit_replay_namespace import ReplayNamespace
from pheroos.governance._commit_state_v2.contracts import CommitReplayReceiptV2


def commit_evidence_replay_receipts_for_proposals_v2(
    attestations: Sequence[CommitEvidenceAttestationV2],
    dispositions: Sequence[CounterevidenceDispositionProposalV2],
    *,
    target_ref: str,
) -> tuple[CommitReplayReceiptV2, ...]:
    """Project anti-replay data before qualification; it grants no authority."""

    target = require_text_v2(target_ref, "commit evidence replay target_ref")
    proposals = canonical_attestations_v2(attestations)
    disposition_values = canonical_dispositions_v2(dispositions)
    by_counter = {item.counter_attestation_root: item for item in disposition_values}
    counters = {
        item.attestation_root
        for item in proposals
        if item.kind is CommitEvidenceKindV2.COUNTER
    }
    if set(by_counter) != counters:
        raise ValueError("replay projection requires every counter disposition")
    receipts: list[CommitReplayReceiptV2] = []
    for item in proposals:
        namespace = (
            ReplayNamespace.CHALLENGE
            if item.kind is CommitEvidenceKindV2.CHALLENGE
            else ReplayNamespace.OBSERVATION
        )
        receipts.append(
            CommitReplayReceiptV2(
                namespace=namespace,
                record_id=item.evidence_ref,
                nonce=item.nonce,
                payload_fingerprint=item.attestation_root,
                target_ref=target,
                candidate_ref=item.candidate_ref,
                epoch=item.epoch,
                principal_ref=item.principal_ref,
            )
        )
        disposition = by_counter.get(item.attestation_root)
        if disposition is not None:
            receipts.append(
                CommitReplayReceiptV2(
                    namespace=ReplayNamespace.COUNTEREVIDENCE_DISPOSITION,
                    record_id=disposition.disposition_ref,
                    nonce=disposition.nonce,
                    payload_fingerprint=disposition.disposition_root,
                    target_ref=target,
                    candidate_ref=item.candidate_ref,
                    epoch=item.epoch,
                    principal_ref=item.principal_ref,
                )
            )
    return tuple(sorted(receipts, key=lambda item: item.receipt_root))


def commit_evidence_replay_receipts_for_target_v2(
    record: QualifiedCommitEvidenceV2,
    *,
    target_ref: str,
) -> tuple[CommitReplayReceiptV2, ...]:
    """Derive exact target-bound replay receipts for one qualified record."""

    require_text_v2(target_ref, "commit evidence replay target_ref")
    namespace = (
        ReplayNamespace.CHALLENGE
        if record.kind is CommitEvidenceKindV2.CHALLENGE
        else ReplayNamespace.OBSERVATION
    )
    values = [
        CommitReplayReceiptV2(
            namespace=namespace,
            record_id=record.record_ref,
            nonce=record.nonce,
            payload_fingerprint=record.attestation_root,
            target_ref=target_ref,
            candidate_ref=record.candidate_ref,
            epoch=record.epoch,
            principal_ref=record.principal_ref,
        )
    ]
    if record.kind is CommitEvidenceKindV2.COUNTER:
        values.append(
            CommitReplayReceiptV2(
                namespace=ReplayNamespace.COUNTEREVIDENCE_DISPOSITION,
                record_id=record.disposition_ref,
                nonce=record.disposition_nonce,
                payload_fingerprint=record.disposition_root,
                target_ref=target_ref,
                candidate_ref=record.candidate_ref,
                epoch=record.epoch,
                principal_ref=record.principal_ref,
            )
        )
    receipts = tuple(values)
    if tuple(sorted(item.receipt_root for item in receipts)) != tuple(
        record.replay_receipt_roots
    ):
        raise ValueError("qualified evidence replay roots are not reconstructable")
    return receipts


__all__: tuple[str, ...] = ()
