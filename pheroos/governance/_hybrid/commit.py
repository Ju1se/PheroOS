"""Commit-window progression and issued evaluation authority verification."""

from __future__ import annotations

from pheroos.governance._certificate.local import (
    LocalCommitReceipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
)
from pheroos.governance._certificate.outcome import (
    OutcomeCertificate,
    outcome_certificate_fingerprint,
)
from pheroos.governance._certificate.portable import (
    EvidenceCommitCertificate,
    evidence_commit_certificate_fingerprint,
)
from pheroos.governance._hybrid.binding import (
    hybrid_commit_step_fingerprint,
    hybrid_commit_step_is_authoritative,
)
from pheroos.governance._hybrid.evaluation_records import (
    _ATTENTION_CHANNEL_DIAGNOSTIC_CODE,
    _HYBRID_COMMIT_EVALUATION_ISSUANCE,
    HybridCommitAttentionStatus,
    HybridCommitEvaluation,
    HybridCommitEvaluationStatus,
    _has_exact_attention_channel_diagnostic,
    hybrid_commit_evaluation_fingerprint,
)
from pheroos.governance._hybrid.request import HybridCommitEvaluationRequest
from pheroos.governance.attention import (
    attention_breakdown_fingerprint,
    attention_breakdown_is_authoritative,
    exploration_directive_fingerprint,
    exploration_directive_is_authoritative,
)
from pheroos.governance.commit import (
    CommitAssessment,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    CommitFinalityVerification,
    CommitWindowState,
    advance_commit_window_state,
    commit_finality_verification_fingerprint,
    commit_finality_verification_is_authoritative,
    commit_replay_state_fingerprint,
    commit_replay_state_is_authoritative,
    commit_window_seal_for_state,
    commit_window_state_fingerprint,
    commit_window_state_is_authoritative,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
    decision_progress_fingerprint,
    decision_progress_is_authoritative,
)
from pheroos.governance.distributed_commit import (
    DistributedCommitCertificate,
    DistributedCommitState,
    distributed_commit_certificate_fingerprint,
    distributed_commit_state_fingerprint,
    distributed_commit_state_is_authoritative,
    distributed_commit_value_root,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.output import (
    commit_output_authorization_fingerprint,
    commit_output_authorization_is_authoritative,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy
from pheroos.trace.commit_contracts import replay_commit_trace


def _advance_window_if_required(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy,
) -> CommitWindowState:
    seal = commit_window_seal_for_state(window_state)
    deadline_reached = request.current_step >= min(
        window_state.absolute_deadline_step,
        window_state.absolute_run_deadline_step,
    )
    if (
        request.current_step > window_state.last_evaluated_step
        and seal is None
        and not deadline_reached
    ):
        if assessment.evaluated_at_step != request.current_step:
            raise GovernanceError(
                "unsealed window advance requires the current-step assessment"
            )
        return advance_commit_window_state(
            window_state,
            assessment=assessment,
            commit_policy=commit_policy,
            threshold_snapshot=request.threshold_snapshot,
            current_step=request.current_step,
        )
    if window_state.last_assessment_ref and (
        window_state.last_assessment_ref != commit_assessment_fingerprint(assessment)
    ):
        raise GovernanceError("window head does not bind the supplied assessment")
    if seal is not None and assessment.evaluated_at_step != seal.sealed_at_step:
        raise GovernanceError("sealed window assessment step changed")
    return window_state

def hybrid_commit_evaluation_is_authoritative(value: object) -> bool:
    if type(value) is not HybridCommitEvaluation or not value.authoritative:
        return False
    try:
        issuance = value._issuance
        if not (
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _HYBRID_COMMIT_EVALUATION_ISSUANCE
            and issuance[1] == hybrid_commit_evaluation_fingerprint(value)
        ):
            return False
        if not (
            commit_assessment_is_authoritative(value.commit_assessment)
            and commit_assessment_fingerprint(value.commit_assessment)
            == value.assessment_ref
        ):
            return False
        if not (
            commit_window_state_is_authoritative(value.commit_window_state)
            and commit_window_state_fingerprint(value.commit_window_state)
            == value.window_state_ref
            and value.commit_window_state.window_root == value.window_root
        ):
            return False
        if not (
            commit_replay_state_is_authoritative(value.commit_replay_state)
            and commit_replay_state_fingerprint(value.commit_replay_state)
            == value.replay_state_ref
            and value.commit_replay_state.receipt_root == value.replay_root
        ):
            return False
        if value.attention_status is HybridCommitAttentionStatus.UNAVAILABLE:
            if any(
                (
                    value.binding_step is not None,
                    bool(value.binding_step_ref),
                    value.attention is not None,
                    bool(value.attention_ref),
                    value.exploration_directive is not None,
                    bool(value.exploration_directive_ref),
                )
            ):
                return False
            if not _has_exact_attention_channel_diagnostic(value.diagnostics):
                return False
        elif value.attention_status is HybridCommitAttentionStatus.VERIFIED:
            if not (
                value.binding_step_ref
                and hybrid_commit_step_is_authoritative(value.binding_step)
                and hybrid_commit_step_fingerprint(value.binding_step)
                == value.binding_step_ref
                and value.attention_ref
                and value.attention is not None
                and attention_breakdown_is_authoritative(value.attention)
                and attention_breakdown_fingerprint(value.attention)
                == value.attention_ref
                and value.exploration_directive_ref
                and value.exploration_directive is not None
                and exploration_directive_is_authoritative(
                    value.exploration_directive
                )
                and exploration_directive_fingerprint(
                    value.exploration_directive
                )
                == value.exploration_directive_ref
                and value.exploration_directive.source_attention_fingerprint
                == value.attention_ref
                and value.exploration_directive.protocol_id
                == value.attention.protocol_id
                and value.exploration_directive.target == value.attention.target
                and value.exploration_directive.current_step
                == value.attention.current_step
                and not any(
                    item.code == _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
                    for item in value.diagnostics
                )
            ):
                return False
        else:
            return False
        if value.status is HybridCommitEvaluationStatus.PROGRESS:
            if not (
                decision_progress_is_authoritative(value.decision_progress)
                and decision_progress_fingerprint(value.decision_progress)
                == value.progress_ref
                and value.decision_outcome is None
                and not value.outcome_ref
            ):
                return False
        elif not (
            decision_outcome_is_authoritative(value.decision_outcome)
            and decision_outcome_fingerprint(value.decision_outcome)
            == value.outcome_ref
            and value.decision_progress is None
            and not value.progress_ref
        ):
            return False

        optional_records = (
            (
                value.local_receipt,
                value.local_receipt_ref,
                LocalCommitReceipt,
                local_commit_receipt_fingerprint,
                local_commit_receipt_is_authoritative,
            ),
            (
                value.evidence_certificate,
                value.evidence_certificate_ref,
                EvidenceCommitCertificate,
                evidence_commit_certificate_fingerprint,
                None,
            ),
            (
                value.distributed_state,
                value.distributed_state_ref,
                DistributedCommitState,
                distributed_commit_state_fingerprint,
                distributed_commit_state_is_authoritative,
            ),
            (
                value.distributed_certificate,
                value.distributed_certificate_ref,
                DistributedCommitCertificate,
                distributed_commit_certificate_fingerprint,
                None,
            ),
            (
                value.outcome_certificate,
                value.outcome_certificate_ref,
                OutcomeCertificate,
                outcome_certificate_fingerprint,
                None,
            ),
            (
                value.finality_verification,
                value.finality_verification_ref,
                CommitFinalityVerification,
                commit_finality_verification_fingerprint,
                commit_finality_verification_is_authoritative,
            ),
        )
        for runtime, ref, expected_type, fingerprint, authoritative in optional_records:
            if runtime is None:
                if ref:
                    return False
                continue
            if not (type(runtime) is expected_type and ref):
                return False
            if authoritative is not None and not authoritative(runtime):
                return False
            if fingerprint(runtime) != ref:
                return False
        if value.distributed_certificate is not None and not (
            value.distributed_state is not None
            and distributed_commit_value_root(value.distributed_certificate.proposal)
            == value.distributed_certificate.commit_value_root
            == value.distributed_certificate.proposal.commit_value_root
            and _distributed_certificate_registered_final(
                value.distributed_certificate,
                value.distributed_state,
            )
        ):
            return False

        authorizations = (
            (value.deliver_authorization, value.deliver_authorization_ref),
            (value.publish_authorization, value.publish_authorization_ref),
            (value.execute_authorization, value.execute_authorization_ref),
        )
        for authorization, ref in authorizations:
            if authorization is None:
                if ref:
                    return False
                continue
            if not (
                ref
                and commit_output_authorization_is_authoritative(authorization)
                and commit_output_authorization_fingerprint(authorization) == ref
            ):
                return False
        if value.terminal:
            if any(item is None for item, _ in authorizations):
                return False
        elif any(item is not None or ref for item, ref in authorizations):
            return False
        trace_ids = tuple(event.lineage["event_id"] for event in value.trace_events)
        if trace_ids != value.trace_event_ids:
            return False
        if commit_payload_fingerprint(
            {"event_ids": trace_ids},
            schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
            profile=value.profile,
        ) != value.trace_root:
            return False
        for event in value.trace_events:
            event.validate()
        replay_commit_trace(
            value.trace_events,
            require_complete=value.terminal,
        )
        return True
    except Exception:
        return False

def _distributed_certificate_registered_final(
    certificate: DistributedCommitCertificate,
    state: DistributedCommitState,
) -> bool:
    """Verify the immutable final-registration fact without current-head bias."""

    try:
        certificate_ref = distributed_commit_certificate_fingerprint(certificate)
        return bool(
            distributed_commit_state_is_authoritative(state)
            and certificate.status.value == "final"
            and not state.frozen
            and any(
                item.certificate_ref == certificate_ref
                and item.proposal_digest == certificate.proposal_digest
                and item.commit_value_root == certificate.commit_value_root
                for item in state.final_registrations
            )
        )
    except (AttributeError, GovernanceError, ValueError):
        return False



__all__ = ["hybrid_commit_evaluation_is_authoritative"]
