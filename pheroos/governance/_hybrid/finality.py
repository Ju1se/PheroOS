from __future__ import annotations

"""Declared-assurance finality and terminal certificate resolution."""

from pheroos.governance._certificate.local import (
    LocalCommitReceipt,
    issue_local_commit_receipt,
    local_commit_receipt_is_authoritative,
    verify_local_commit_finality,
)
from pheroos.governance._certificate.outcome import (
    OutcomeCertificate,
    issue_outcome_certificate,
    outcome_certificate_fingerprint,
    verify_outcome_certificate,
)
from pheroos.governance._certificate.portable import (
    EvidenceCommitCertificate,
    evidence_commit_certificate_fingerprint,
    issue_evidence_commit_certificate,
    verify_evidence_commit_certificate,
    verify_evidence_commit_finality,
)
from pheroos.governance._hybrid.request import HybridCommitEvaluationRequest
from pheroos.governance.commit import CommitAssessment, CommitEvaluationContext
from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    CommitFinalityVerification,
    CommitReplayState,
    CommitWindowState,
    DecisionOutcome,
    commit_window_ready,
    decision_outcome_fingerprint,
)
from pheroos.governance.distributed_commit import (
    DistributedCommitCertificate,
    DistributedCommitState,
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_is_current_final,
    distributed_commit_state_is_current,
    verify_distributed_commit_certificate,
    verify_distributed_commit_finality,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CollectiveCommitPolicy, CommitAssurance


def _resolve_declared_finality(
    request: HybridCommitEvaluationRequest,
    *,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    replay_state: CommitReplayState,
    commit_policy: CollectiveCommitPolicy,
) -> tuple[
    LocalCommitReceipt | None,
    EvidenceCommitCertificate | None,
    DistributedCommitState | None,
    DistributedCommitCertificate | None,
    CommitFinalityVerification | None,
    CommitFinalityStatus,
    tuple[str, ...],
    tuple[str, ...],
]:
    assurance = assessment.assurance
    if assurance is CommitAssurance.ADVISORY:
        if any(
            item is not None
            for item in (
                request.local_receipt,
                request.evidence_certificate,
                request.distributed_certificate,
            )
        ):
            raise GovernanceError("advisory assurance cannot carry commit certificates")
        return None, None, None, None, None, CommitFinalityStatus.NOT_REQUIRED, (), ()

    stable = commit_window_ready(window_state)
    local_receipt: LocalCommitReceipt | None = None
    if request.local_receipt is not None:
        if type(request.local_receipt) is not LocalCommitReceipt or not (
            local_commit_receipt_is_authoritative(request.local_receipt)
        ):
            raise GovernanceError("supplied local receipt is malformed or forged")
        local_receipt = request.local_receipt
    elif stable and request.current_step == window_state.last_evaluated_step:
        local_receipt = issue_local_commit_receipt(
            context,
            assessment,
            window_state,
            commit_policy=commit_policy,
            risk_chain_state=request.risk_chain_state,  # type: ignore[arg-type]
            risk_assessment=request.risk_assessment,  # type: ignore[arg-type]
            threshold_snapshot=request.threshold_snapshot,  # type: ignore[arg-type]
            membership_snapshot=request.membership_snapshot,  # type: ignore[arg-type]
            membership_epoch_state=request.membership_epoch_state,  # type: ignore[arg-type]
            replay_state=replay_state,
            support_replay_state=request.support_replay_state,  # type: ignore[arg-type]
            output_payload_fingerprint=request.output_payload_fingerprint,
            receipt_id=f"{request.request_id}:local-receipt",
            issuer_id=request.issuer_id,
            authority=request.authority,
            current_step=request.current_step,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:local-receipt",
        )

    if local_receipt is None:
        if request.evidence_certificate is not None or request.distributed_certificate is not None:
            raise GovernanceError("higher-assurance certificate lacks a local receipt")
        return (
            None,
            None,
            None,
            None,
            None,
            CommitFinalityStatus.PENDING,
            (),
            ("local_commit_receipt",),
        )

    if assurance is CommitAssurance.EVIDENCE_BOUND:
        if request.evidence_certificate is not None or request.distributed_certificate is not None:
            raise GovernanceError("evidence-bound assurance cannot accept a higher proof")
        verification = verify_local_commit_finality(
            local_receipt,
            context,
            assessment,
            window_state,
            commit_policy=commit_policy,
            risk_chain_state=request.risk_chain_state,  # type: ignore[arg-type]
            risk_assessment=request.risk_assessment,  # type: ignore[arg-type]
            threshold_snapshot=request.threshold_snapshot,  # type: ignore[arg-type]
            membership_snapshot=request.membership_snapshot,  # type: ignore[arg-type]
            membership_epoch_state=request.membership_epoch_state,  # type: ignore[arg-type]
            replay_state=replay_state,
            support_replay_state=request.support_replay_state,  # type: ignore[arg-type]
            current_step=request.current_step,
            verifier_id=request.issuer_id,
            authority=request.authority,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:local-finality",
        )
        return (
            local_receipt,
            None,
            None,
            None,
            verification,
            CommitFinalityStatus.VERIFIED,
            (),
            (),
        )

    evidence_certificate: EvidenceCommitCertificate | None = None
    if request.evidence_certificate is not None:
        if type(request.evidence_certificate) is not EvidenceCommitCertificate:
            raise GovernanceError("portable evidence certificate is not canonical")
        evidence_certificate = request.evidence_certificate
    elif request.issuer_attestation_refs:
        evidence_certificate = issue_evidence_commit_certificate(
            local_receipt,
            commit_policy=commit_policy,
            certificate_id=f"{request.request_id}:evidence-certificate",
            issuer_attestation_refs=request.issuer_attestation_refs,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            issuer_id=request.issuer_id,
            authority=request.authority,
            issued_at_step=request.current_step,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:evidence-certificate",
        )
    if evidence_certificate is None:
        if request.distributed_certificate is not None:
            raise GovernanceError("distributed certificate lacks its portable proof")
        return (
            local_receipt,
            None,
            None,
            None,
            None,
            CommitFinalityStatus.PROVISIONAL,
            ("portable_certificate_pending",),
            ("evidence_commit_certificate",),
        )
    evidence_ref = evidence_commit_certificate_fingerprint(evidence_certificate)
    if not verify_evidence_commit_certificate(
        evidence_certificate,
        trusted_issuer_attestations=request.trusted_issuer_attestations,
        expected_certificate_ref=evidence_ref,
        expected_output_payload_fingerprint=request.output_payload_fingerprint,
    ):
        raise GovernanceError("portable evidence certificate verification failed")

    if assurance is CommitAssurance.CERTIFIED:
        if request.distributed_state is not None or request.distributed_certificate is not None:
            raise GovernanceError("certified assurance cannot accept distributed finality")
        verification = verify_evidence_commit_finality(
            evidence_certificate,
            local_receipt,
            context,
            assessment,
            window_state,
            commit_policy=commit_policy,
            risk_chain_state=request.risk_chain_state,  # type: ignore[arg-type]
            risk_assessment=request.risk_assessment,  # type: ignore[arg-type]
            threshold_snapshot=request.threshold_snapshot,  # type: ignore[arg-type]
            membership_snapshot=request.membership_snapshot,  # type: ignore[arg-type]
            membership_epoch_state=request.membership_epoch_state,  # type: ignore[arg-type]
            replay_state=replay_state,
            support_replay_state=request.support_replay_state,  # type: ignore[arg-type]
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            current_step=request.current_step,
            verifier_id=request.issuer_id,
            authority=request.authority,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:certified-finality",
        )
        return (
            local_receipt,
            evidence_certificate,
            None,
            None,
            verification,
            CommitFinalityStatus.VERIFIED,
            (),
            (),
        )

    distributed_state = request.distributed_state
    distributed_certificate = request.distributed_certificate
    if distributed_state is None:
        if distributed_certificate is not None:
            raise GovernanceError("distributed certificate lacks its state head")
        return (
            local_receipt,
            evidence_certificate,
            None,
            None,
            None,
            CommitFinalityStatus.PROVISIONAL,
            ("distributed_state_pending",),
            ("distributed_commit_state",),
        )
    if type(distributed_state) is not DistributedCommitState or not (
        distributed_commit_state_is_current(distributed_state)
    ):
        raise GovernanceError("distributed state is malformed, forged, or stale")
    if distributed_state.frozen:
        return (
            local_receipt,
            evidence_certificate,
            distributed_state,
            None,
            None,
            CommitFinalityStatus.CONFLICT,
            ("distributed_epoch_frozen",),
            (),
        )
    if distributed_certificate is None:
        return (
            local_receipt,
            evidence_certificate,
            distributed_state,
            None,
            None,
            CommitFinalityStatus.PROVISIONAL,
            ("distributed_witness_quorum_pending",),
            ("distributed_commit_certificate",),
        )
    if type(distributed_certificate) is not DistributedCommitCertificate:
        raise GovernanceError("distributed certificate is not canonical")
    distributed_ref = distributed_commit_certificate_fingerprint(
        distributed_certificate
    )
    if not verify_distributed_commit_certificate(
        distributed_certificate,
        commit_policy=commit_policy,
        portable_certificate=evidence_certificate,
        trusted_issuer_attestations=request.trusted_issuer_attestations,
        trusted_witness_attestations=request.trusted_witness_attestations,
        expected_certificate_ref=distributed_ref,
        require_final=True,
    ):
        raise GovernanceError("distributed commit certificate verification failed")
    if not distributed_commit_certificate_is_current_final(
        distributed_certificate,
        distributed_state,
    ):
        raise GovernanceError("distributed final certificate is not current")
    verification = verify_distributed_commit_finality(
        distributed_certificate,
        distributed_state,
        local_receipt,
        current_step=request.current_step,
        verifier_id=request.issuer_id,
        authority=request.authority,
        provenance=request.provenance,
        trace_event_id=f"{request.trace_event_id}:distributed-finality",
    )
    return (
        local_receipt,
        evidence_certificate,
        distributed_state,
        distributed_certificate,
        verification,
        CommitFinalityStatus.VERIFIED,
        (),
        (),
    )

def _resolve_outcome_certificate(
    request: HybridCommitEvaluationRequest,
    *,
    outcome: DecisionOutcome,
    window_state: CommitWindowState,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    commit_policy: CollectiveCommitPolicy,
) -> OutcomeCertificate | None:
    supplied = request.outcome_certificate
    if supplied is not None:
        if type(supplied) is not OutcomeCertificate:
            raise GovernanceError("outcome certificate is not canonical")
        certificate_ref = outcome_certificate_fingerprint(supplied)
        if (
            supplied.outcome_ref != decision_outcome_fingerprint(outcome)
            or supplied.outcome_kind is not outcome.kind
            or not verify_outcome_certificate(
                supplied,
                trusted_issuer_attestations=request.trusted_issuer_attestations,
                expected_certificate_ref=certificate_ref,
                expected_output_payload_fingerprint=(
                    request.output_payload_fingerprint
                ),
            )
        ):
            raise GovernanceError("outcome certificate verification failed")
        return supplied
    # Local outcome certificates need no external signer.  Portable outcome
    # certificates can also be issued here when the caller supplied exact
    # body-root-bound attestations; otherwise delivery remains available while
    # publication/execute are independently denied.
    try:
        return issue_outcome_certificate(
            outcome,
            window_state,
            commit_policy=commit_policy,
            output_payload_fingerprint=request.output_payload_fingerprint,
            certificate_id=f"{request.request_id}:outcome-certificate",
            context=context,
            assessment=assessment,
            issuer_attestation_refs=request.issuer_attestation_refs,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            issuer_id=request.issuer_id,
            authority=request.authority,
            issued_at_step=request.current_step,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:outcome-certificate",
        )
    except GovernanceError:
        if commit_policy.certificate.issuer_attestation_required:
            return None
        raise



__all__: list[str] = []
