"""Commit-window progression and issued evaluation authority verification."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

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
    HybridCommitStep,
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
    AttentionBreakdown,
    ExplorationDirective,
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
    CommitReplayState,
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


_RecordT = TypeVar("_RecordT")


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
        assessment = value.commit_assessment
        if type(assessment) is not CommitAssessment:
            return False
        if not commit_assessment_is_authoritative(assessment):
            return False
        if commit_assessment_fingerprint(assessment) != value.assessment_ref:
            return False
        window_state = value.commit_window_state
        if type(window_state) is not CommitWindowState:
            return False
        if not commit_window_state_is_authoritative(window_state):
            return False
        if commit_window_state_fingerprint(window_state) != value.window_state_ref:
            return False
        if window_state.window_root != value.window_root:
            return False
        replay_state = value.commit_replay_state
        if type(replay_state) is not CommitReplayState:
            return False
        if not commit_replay_state_is_authoritative(replay_state):
            return False
        if commit_replay_state_fingerprint(replay_state) != value.replay_state_ref:
            return False
        if replay_state.receipt_root != value.replay_root:
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
            binding_step = value.binding_step
            attention = value.attention
            directive = value.exploration_directive
            if not value.binding_step_ref or type(binding_step) is not HybridCommitStep:
                return False
            if not hybrid_commit_step_is_authoritative(binding_step):
                return False
            if hybrid_commit_step_fingerprint(binding_step) != value.binding_step_ref:
                return False
            if not value.attention_ref or type(attention) is not AttentionBreakdown:
                return False
            if not attention_breakdown_is_authoritative(attention):
                return False
            if attention_breakdown_fingerprint(attention) != value.attention_ref:
                return False
            if (
                not value.exploration_directive_ref
                or type(directive) is not ExplorationDirective
            ):
                return False
            if not exploration_directive_is_authoritative(directive):
                return False
            if (
                exploration_directive_fingerprint(directive)
                != value.exploration_directive_ref
            ):
                return False
            if directive.source_attention_fingerprint != value.attention_ref:
                return False
            if directive.protocol_id != attention.protocol_id:
                return False
            if directive.target != attention.target:
                return False
            if directive.current_step != attention.current_step:
                return False
            if any(
                item.code == _ATTENTION_CHANNEL_DIAGNOSTIC_CODE
                for item in value.diagnostics
            ):
                return False
        else:
            return False
        if value.status is HybridCommitEvaluationStatus.PROGRESS:
            progress = value.decision_progress
            if not (
                progress is not None
                and decision_progress_is_authoritative(progress)
                and decision_progress_fingerprint(progress) == value.progress_ref
                and value.decision_outcome is None
                and not value.outcome_ref
            ):
                return False
        else:
            outcome = value.decision_outcome
            if not (
                outcome is not None
                and decision_outcome_is_authoritative(outcome)
                and decision_outcome_fingerprint(outcome) == value.outcome_ref
                and value.decision_progress is None
                and not value.progress_ref
            ):
                return False
        optional_records_valid = (
            _optional_record_matches(
                value.local_receipt,
                value.local_receipt_ref,
                expected_type=LocalCommitReceipt,
                fingerprint=local_commit_receipt_fingerprint,
                authoritative=local_commit_receipt_is_authoritative,
            )
            and _optional_record_matches(
                value.evidence_certificate,
                value.evidence_certificate_ref,
                expected_type=EvidenceCommitCertificate,
                fingerprint=evidence_commit_certificate_fingerprint,
            )
            and _optional_record_matches(
                value.distributed_state,
                value.distributed_state_ref,
                expected_type=DistributedCommitState,
                fingerprint=distributed_commit_state_fingerprint,
                authoritative=distributed_commit_state_is_authoritative,
            )
            and _optional_record_matches(
                value.distributed_certificate,
                value.distributed_certificate_ref,
                expected_type=DistributedCommitCertificate,
                fingerprint=distributed_commit_certificate_fingerprint,
            )
            and _optional_record_matches(
                value.outcome_certificate,
                value.outcome_certificate_ref,
                expected_type=OutcomeCertificate,
                fingerprint=outcome_certificate_fingerprint,
            )
            and _optional_record_matches(
                value.finality_verification,
                value.finality_verification_ref,
                expected_type=CommitFinalityVerification,
                fingerprint=commit_finality_verification_fingerprint,
                authoritative=commit_finality_verification_is_authoritative,
            )
        )
        if not optional_records_valid:
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
        if (
            commit_payload_fingerprint(
                {"event_ids": trace_ids},
                schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
                profile=value.profile,
            )
            != value.trace_root
        ):
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


def _optional_record_matches(
    runtime: object | None,
    ref: str,
    *,
    expected_type: type[_RecordT],
    fingerprint: Callable[[_RecordT], str],
    authoritative: Callable[[_RecordT], bool] | None = None,
) -> bool:
    if runtime is None:
        return not ref
    if type(runtime) is not expected_type or not ref:
        return False
    canonical = runtime
    if authoritative is not None and not authoritative(canonical):
        return False
    return fingerprint(canonical) == ref


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
