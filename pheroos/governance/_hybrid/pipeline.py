from __future__ import annotations

"""Sole diagnostic-total Hybrid Commit evaluation pipeline."""

from collections.abc import Mapping, Sequence

from pheroos.governance._certificate.local import (
    LocalCommitReceipt,
    local_commit_receipt_fingerprint,
)
from pheroos.governance._certificate.outcome import (
    OutcomeCertificate,
    outcome_certificate_fingerprint,
)
from pheroos.governance._certificate.portable import (
    EvidenceCommitCertificate,
    evidence_commit_certificate_fingerprint,
)
from pheroos.governance._hybrid.attention import (
    _bind_attention_channel,
    _with_exact_attention_channel_diagnostic,
)
from pheroos.governance._hybrid.binding import hybrid_commit_step_fingerprint
from pheroos.governance._hybrid.commit import (
    _advance_window_if_required,
    hybrid_commit_evaluation_is_authoritative,
)
from pheroos.governance._hybrid.evaluation_records import (
    HYBRID_COMMIT_EVALUATION_VERSION,
    _HYBRID_COMMIT_EVALUATION_ISSUANCE,
    _ZERO_ROOT,
    HybridCommitAttentionStatus,
    HybridCommitDiagnostic,
    HybridCommitEvaluation,
    HybridCommitEvaluationStatus,
    _diagnostic,
    _diagnostic_from_exception,
    _hybrid_commit_evaluation_payload,
    hybrid_commit_evaluation_fingerprint,
)
from pheroos.governance._hybrid.finality import (
    _resolve_declared_finality,
    _resolve_outcome_certificate,
)
from pheroos.governance._hybrid.output import _certificate_for_outcome
from pheroos.governance._hybrid.preflight import (
    _establish_authority_envelope,
    _validated_prior_trace,
)
from pheroos.governance._hybrid.request import (
    HybridCommitEvaluationRequest,
    _issued_request_ref,
    _safe_declared_assurance,
    _safe_diagnostic_profile,
    _safe_diagnostic_step,
    _safe_diagnostic_text,
    _safe_fingerprint,
)
from pheroos.governance._hybrid.trace import _build_evaluation_trace
from pheroos.governance.attention import (
    attention_breakdown_fingerprint,
    exploration_directive_fingerprint,
)
from pheroos.governance.commit import (
    CommitAssessment,
    CommitEvaluationContext,
    commit_assessment_fingerprint,
    commit_evaluation_context_fingerprint,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    CommitFinalityVerification,
    CommitReplayState,
    CommitWindowState,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionProgress,
    commit_finality_verification_fingerprint,
    commit_replay_state_fingerprint,
    commit_window_state_fingerprint,
    decision_outcome_fingerprint,
    decision_progress_fingerprint,
    issue_commit_liveness_input,
    reduce_commit_liveness,
)
from pheroos.governance.distributed_commit import (
    DistributedCommitCertificate,
    DistributedCommitState,
    distributed_commit_certificate_fingerprint,
    distributed_commit_state_fingerprint,
)
from pheroos.governance.output import (
    CommitOutputAuthorization,
    authorize_terminal_execution,
    authorize_terminal_publication,
    commit_output_authorization_fingerprint,
    deliver_terminal_outcome,
)
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE
from pheroos.trace import TraceEvent


def evaluate_hybrid_commit_step(
    *,
    request: object,
    _trace_builder=_build_evaluation_trace,
):
    """Evaluate one logical step as a diagnostic total function.

    A canonical request with a usable governance authority envelope always
    reaches the official liveness reducer.  Malformed runtime facts are
    converted into the reducer's issued ``invalid`` outcome.  If even the
    authority envelope cannot be established, the function still returns a
    deterministic non-authoritative invalid diagnostic envelope.
    """

    if type(request) is not HybridCommitEvaluationRequest:
        return _non_authoritative_invalid(
            request,
            _diagnostic(
                "invalid_evaluation_request",
                "request",
                "Hybrid Commit evaluation requires the canonical request record",
                fatal=True,
            ),
        )

    try:
        authority = _establish_authority_envelope(request)
    except Exception as exc:
        return _non_authoritative_invalid(
            request,
            _diagnostic_from_exception(
                "authority_envelope_unavailable",
                "authority",
                exc,
                fatal=True,
            ),
        )

    assessment = authority["assessment"]
    context = authority["context"]
    window_state = authority["window_state"]
    replay_state = authority["replay_state"]
    policy = authority["commit_policy"]
    diagnostics: list[HybridCommitDiagnostic] = []
    binding_step: object | None = None
    prior_trace: tuple[TraceEvent, ...] = ()

    binding_step, attention_diagnostic = _bind_attention_channel(
        request,
        assessment=assessment,
    )
    if attention_diagnostic is not None:
        diagnostics.append(attention_diagnostic)

    try:
        window_state = _advance_window_if_required(
            request,
            assessment=assessment,
            window_state=window_state,
            commit_policy=policy,
        )
    except Exception as exc:
        diagnostics.append(
            _diagnostic_from_exception(
                "invalid_window_transition",
                "window",
                exc,
                fatal=True,
            )
        )

    try:
        prior_trace = _validated_prior_trace(request, assessment=assessment)
    except Exception as exc:
        diagnostics.append(
            _diagnostic_from_exception(
                "invalid_prior_commit_trace",
                "trace",
                exc,
                fatal=True,
            )
        )

    local_receipt: LocalCommitReceipt | None = None
    evidence_certificate: EvidenceCommitCertificate | None = None
    distributed_state: DistributedCommitState | None = None
    distributed_certificate: DistributedCommitCertificate | None = None
    finality_verification: CommitFinalityVerification | None = None
    finality_status = CommitFinalityStatus.NOT_REQUIRED
    finality_reasons: tuple[str, ...] = ()
    next_required: set[str] = set()

    if not _has_fatal(diagnostics):
        try:
            (
                local_receipt,
                evidence_certificate,
                distributed_state,
                distributed_certificate,
                finality_verification,
                finality_status,
                finality_reasons,
                finality_required,
            ) = _resolve_declared_finality(
                request,
                context=context,
                assessment=assessment,
                window_state=window_state,
                replay_state=replay_state,
                commit_policy=policy,
            )
            next_required.update(finality_required)
        except Exception as exc:
            diagnostics.append(
                _diagnostic_from_exception(
                    "invalid_finality_record",
                    "finality",
                    exc,
                    fatal=True,
                    references=_exception_references(request),
                )
            )
            finality_status = CommitFinalityStatus.PENDING

    fatal_codes = tuple(item.code for item in diagnostics if item.fatal)
    try:
        liveness_input = issue_commit_liveness_input(
            window_state,
            assessment=assessment,
            replay_state=replay_state,
            risk_chain_state=request.risk_chain_state,
            risk_assessment=request.risk_assessment,
            threshold_snapshot=request.threshold_snapshot,
            membership_snapshot=request.membership_snapshot,
            membership_epoch_state=request.membership_epoch_state,
            support_replay_state=request.support_replay_state,
            commit_policy=policy,
            previous_progress=(
                request.previous_progress
                if type(request.previous_progress) is DecisionProgress
                else None
            ),
            current_step=request.current_step,
            finality_status=finality_status,
            finality_verification=finality_verification,
            invalid_reason_codes=fatal_codes,
            finality_reason_codes=finality_reasons,
            next_required_inputs=tuple(next_required),
            input_id=request.request_id,
            issuer_id=request.issuer_id,
            authority=request.authority,
            provenance=request.provenance,
            trace_event_id=f"{request.trace_event_id}:liveness",
        )
        decision = reduce_commit_liveness(
            window_state,
            commit_policy=policy,
            liveness_input=liveness_input,
        )
    except Exception as exc:
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic_from_exception(
                "liveness_authority_unavailable",
                "liveness",
                exc,
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )

    progress = decision if type(decision) is DecisionProgress else None
    outcome = decision if type(decision) is DecisionOutcome else None
    outcome_certificate: OutcomeCertificate | None = None
    deliver: CommitOutputAuthorization | None = None
    publish: CommitOutputAuthorization | None = None
    execute: CommitOutputAuthorization | None = None

    if outcome is not None:
        if (
            outcome.kind is not DecisionOutcomeKind.EVIDENCE_COMMIT
            and (prior_trace or not _has_fatal(diagnostics))
        ):
            try:
                outcome_certificate = _resolve_outcome_certificate(
                    request,
                    outcome=outcome,
                    window_state=window_state,
                    context=context,
                    assessment=assessment,
                    commit_policy=policy,
                )
            except Exception as exc:
                diagnostics.append(
                    _diagnostic_from_exception(
                        "outcome_certificate_unavailable",
                        "outcome_certificate",
                        exc,
                        fatal=False,
                    )
                )
        deliver = deliver_terminal_outcome(
            outcome,
            output_payload_fingerprint=request.output_payload_fingerprint,
        )
        action_certificate = _certificate_for_outcome(
            outcome,
            local_receipt=local_receipt,
            evidence_certificate=evidence_certificate,
            distributed_certificate=distributed_certificate,
            outcome_certificate=outcome_certificate,
        )
        publish = authorize_terminal_publication(
            outcome,
            commit_policy=policy,
            threshold_snapshot=request.threshold_snapshot,
            certificate=action_certificate,  # type: ignore[arg-type]
            output_payload_fingerprint=request.output_payload_fingerprint,
            stop_resolution=request.publish_stop_resolution,  # type: ignore[arg-type]
            permission=request.publish_permission,  # type: ignore[arg-type]
            current_step=request.current_step,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            distributed_state=distributed_state,
            portable_certificate=evidence_certificate,
            trusted_witness_attestations=request.trusted_witness_attestations,
        )
        execute = authorize_terminal_execution(
            outcome,
            commit_policy=policy,
            threshold_snapshot=request.threshold_snapshot,
            certificate=action_certificate,  # type: ignore[arg-type]
            output_payload_fingerprint=request.output_payload_fingerprint,
            stop_resolution=request.execute_stop_resolution,  # type: ignore[arg-type]
            permission=request.execute_permission,  # type: ignore[arg-type]
            current_step=request.current_step,
            trusted_issuer_attestations=request.trusted_issuer_attestations,
            distributed_state=distributed_state,
            portable_certificate=evidence_certificate,
            trusted_witness_attestations=request.trusted_witness_attestations,
        )
        if not deliver.authorized:
            diagnostics.append(
                _diagnostic(
                    "terminal_delivery_denied",
                    "output",
                    "authoritative terminal outcome was not deliverable",
                    fatal=True,
                )
            )

    trace_events: tuple[TraceEvent, ...]
    try:
        trace_events = _trace_builder(
            request,
            prior_trace=prior_trace,
            assessment=assessment,
            window_state=window_state,
            progress=progress,
            outcome=outcome,
            local_receipt=local_receipt,
            evidence_certificate=evidence_certificate,
            distributed_state=distributed_state,
            distributed_certificate=distributed_certificate,
            outcome_certificate=outcome_certificate,
            deliver=deliver,
            publish=publish,
            execute=execute,
            invalid_path=_has_fatal(diagnostics),
        )
    except Exception as exc:
        diagnostics.append(
            _diagnostic_from_exception(
                "commit_trace_generation_failed",
                "trace",
                exc,
                fatal=True,
            )
        )
        trace_events = ()

    if outcome is not None and (deliver is None or not deliver.authorized):
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "terminal_delivery_totality_failed",
                "output",
                "terminal result could not satisfy mandatory delivery",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )
    if _has_fatal(diagnostics) and (
        outcome is None or outcome.kind is not DecisionOutcomeKind.INVALID
    ):
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "fail_closed_outcome_unavailable",
                "evaluation",
                "fatal diagnostics did not reduce to an issued invalid outcome",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )

    if not trace_events:
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "authoritative_trace_unavailable",
                "trace",
                "Hybrid Commit evaluation could not verify an authoritative trace",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )

    issued = _issue_evaluation(
        request,
        binding_step=binding_step,
        assessment=assessment,
        context=context,
        window_state=window_state,
        replay_state=replay_state,
        progress=progress,
        outcome=outcome,
        local_receipt=local_receipt,
        evidence_certificate=evidence_certificate,
        distributed_state=distributed_state,
        distributed_certificate=distributed_certificate,
        outcome_certificate=outcome_certificate,
        finality_verification=finality_verification,
        deliver=deliver,
        publish=publish,
        execute=execute,
        trace_events=trace_events,
        diagnostics=tuple(diagnostics),
    )
    if not hybrid_commit_evaluation_is_authoritative(issued):
        return _non_authoritative_invalid(
            request,
            *diagnostics,
            _diagnostic(
                "issued_evaluation_self_verification_failed",
                "evaluation",
                "issued Hybrid Commit evaluation failed authority self-verification",
                fatal=True,
            ),
            authority=authority,
            window_state=window_state,
        )
    return issued

def _issue_evaluation(
    request: HybridCommitEvaluationRequest,
    *,
    binding_step: object | None,
    assessment: CommitAssessment,
    context: CommitEvaluationContext,
    window_state: CommitWindowState,
    replay_state: CommitReplayState,
    progress: DecisionProgress | None,
    outcome: DecisionOutcome | None,
    local_receipt: LocalCommitReceipt | None,
    evidence_certificate: EvidenceCommitCertificate | None,
    distributed_state: DistributedCommitState | None,
    distributed_certificate: DistributedCommitCertificate | None,
    outcome_certificate: OutcomeCertificate | None,
    finality_verification: CommitFinalityVerification | None,
    deliver: CommitOutputAuthorization | None,
    publish: CommitOutputAuthorization | None,
    execute: CommitOutputAuthorization | None,
    trace_events: tuple[TraceEvent, ...],
    diagnostics: tuple[HybridCommitDiagnostic, ...],
) -> HybridCommitEvaluation:
    trace_ids = tuple(event.lineage["event_id"] for event in trace_events)
    trace_root = commit_payload_fingerprint(
        {"event_ids": trace_ids},
        schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
        profile=assessment.profile,
    )
    if progress is not None:
        status = HybridCommitEvaluationStatus.PROGRESS
        terminal = False
    elif outcome is not None and outcome.kind is DecisionOutcomeKind.INVALID:
        status = HybridCommitEvaluationStatus.INVALID
        terminal = True
    else:
        status = HybridCommitEvaluationStatus.OUTCOME
        terminal = True
    provisional = HybridCommitEvaluation(
        evaluation_version=HYBRID_COMMIT_EVALUATION_VERSION,
        request_ref=_issued_request_ref(request, diagnostics, profile=assessment.profile),
        status=status,
        authoritative=True,
        terminal=terminal,
        assurance_downgraded=False,
        profile=assessment.profile,
        assurance=assessment.assurance,
        protocol_id=assessment.protocol_id,
        run_id=assessment.run_id,
        target=assessment.target,
        epoch=assessment.epoch,
        current_step=request.current_step,
        attention_status=(
            HybridCommitAttentionStatus.VERIFIED
            if binding_step is not None
            else HybridCommitAttentionStatus.UNAVAILABLE
        ),
        binding_step_ref=(
            hybrid_commit_step_fingerprint(binding_step) if binding_step is not None else ""
        ),
        attention_ref=(
            attention_breakdown_fingerprint(request.attention)
            if binding_step is not None
            else ""
        ),
        exploration_directive_ref=(
            exploration_directive_fingerprint(request.exploration_directive)
            if binding_step is not None
            else ""
        ),
        assessment_ref=commit_assessment_fingerprint(assessment),
        context_ref=commit_evaluation_context_fingerprint(context),
        window_state_ref=commit_window_state_fingerprint(window_state),
        window_root=window_state.window_root,
        replay_state_ref=commit_replay_state_fingerprint(replay_state),
        replay_root=replay_state.receipt_root,
        progress_ref=(decision_progress_fingerprint(progress) if progress else ""),
        outcome_ref=(decision_outcome_fingerprint(outcome) if outcome else ""),
        local_receipt_ref=(
            local_commit_receipt_fingerprint(local_receipt) if local_receipt else ""
        ),
        evidence_certificate_ref=(
            evidence_commit_certificate_fingerprint(evidence_certificate)
            if evidence_certificate
            else ""
        ),
        distributed_state_ref=(
            distributed_commit_state_fingerprint(distributed_state)
            if distributed_state
            else ""
        ),
        distributed_certificate_ref=(
            distributed_commit_certificate_fingerprint(distributed_certificate)
            if distributed_certificate
            else ""
        ),
        outcome_certificate_ref=(
            outcome_certificate_fingerprint(outcome_certificate)
            if outcome_certificate
            else ""
        ),
        finality_verification_ref=(
            commit_finality_verification_fingerprint(finality_verification)
            if finality_verification
            else ""
        ),
        deliver_authorization_ref=(
            commit_output_authorization_fingerprint(deliver) if deliver else ""
        ),
        publish_authorization_ref=(
            commit_output_authorization_fingerprint(publish) if publish else ""
        ),
        execute_authorization_ref=(
            commit_output_authorization_fingerprint(execute) if execute else ""
        ),
        trace_event_ids=trace_ids,
        trace_root=trace_root,
        diagnostics=diagnostics,
        evaluation_root=_ZERO_ROOT,
        binding_step=binding_step,
        attention=(
            request.attention
            if binding_step is not None
            else None
        ),
        exploration_directive=(
            request.exploration_directive
            if binding_step is not None
            else None
        ),
        commit_assessment=assessment,
        commit_window_state=window_state,
        commit_replay_state=replay_state,
        decision_progress=progress,
        decision_outcome=outcome,
        local_receipt=local_receipt,
        evidence_certificate=evidence_certificate,
        distributed_state=distributed_state,
        distributed_certificate=distributed_certificate,
        outcome_certificate=outcome_certificate,
        finality_verification=finality_verification,
        deliver_authorization=deliver,
        publish_authorization=publish,
        execute_authorization=execute,
        trace_events=trace_events,
    )
    root = commit_payload_fingerprint(
        _hybrid_commit_evaluation_payload(provisional, include_root=False),
        schema=HYBRID_COMMIT_EVALUATION_VERSION,
        profile=assessment.profile,
    )
    result = _replace_evaluation_root(provisional, root)
    object.__setattr__(
        result,
        "_issuance",
        (
            _HYBRID_COMMIT_EVALUATION_ISSUANCE,
            hybrid_commit_evaluation_fingerprint(result),
        ),
    )
    return result

def _replace_evaluation_root(
    evaluation: HybridCommitEvaluation,
    root: str,
) -> HybridCommitEvaluation:
    return HybridCommitEvaluation(
        **{
            name: (root if name == "evaluation_root" else getattr(evaluation, name))
            for name, definition in evaluation.__dataclass_fields__.items()
            if definition.init
        }
    )

def _non_authoritative_invalid(
    request: object,
    *diagnostics: HybridCommitDiagnostic,
    authority: Mapping[str, object] | None = None,
    window_state: object | None = None,
) -> HybridCommitEvaluation:
    assessment = authority.get("assessment") if authority else None
    context = authority.get("context") if authority else None
    replay_state = authority.get("replay_state") if authority else None
    request_assessment = (
        request.commit_assessment
        if type(request) is HybridCommitEvaluationRequest
        else None
    )
    request_policy = (
        request.commit_policy
        if type(request) is HybridCommitEvaluationRequest
        else None
    )
    assurance = _safe_declared_assurance(request_policy, request_assessment)
    candidate_profile = _safe_diagnostic_profile(
        assessment if assessment is not None else request_assessment,
        assurance=assurance,
    )
    profile = (
        candidate_profile
        if candidate_profile in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]
        else sorted(COMMIT_PROFILES_BY_ASSURANCE[assurance.value])[0]
    )
    identity_source = assessment if assessment is not None else request_assessment
    protocol_id = _safe_diagnostic_text(
        getattr(identity_source, "protocol_id", None),
        "protocol:invalid-hybrid-commit-evaluation",
    )
    run_id = _safe_diagnostic_text(
        getattr(identity_source, "run_id", None),
        "run:invalid-hybrid-commit-evaluation",
    )
    target = _safe_diagnostic_text(
        getattr(identity_source, "target", None),
        "target:invalid-hybrid-commit-evaluation",
    )
    epoch = _safe_diagnostic_step(getattr(identity_source, "epoch", None))
    current_step = _safe_diagnostic_step(
        request.current_step
        if type(request) is HybridCommitEvaluationRequest
        else None
    )
    diagnostic_values = tuple(diagnostics) or (
        _diagnostic(
            "invalid_evaluation",
            "evaluation",
            "Hybrid Commit evaluation authority was unavailable",
            fatal=True,
        ),
    )
    diagnostic_values = _with_exact_attention_channel_diagnostic(
        diagnostic_values,
        request=request,
    )
    request_ref = commit_payload_fingerprint(
        {
            "diagnostic_codes": tuple(item.code for item in diagnostic_values),
            "request_id": _safe_diagnostic_text(
                request.request_id
                if type(request) is HybridCommitEvaluationRequest
                else None,
                "invalid-request",
            ),
        },
        schema="pheroos-hybrid-commit-invalid-request-v1",
        profile=profile,
    )
    window = window_state if type(window_state) is CommitWindowState else None
    replay = replay_state if type(replay_state) is CommitReplayState else None
    provisional = HybridCommitEvaluation(
        evaluation_version=HYBRID_COMMIT_EVALUATION_VERSION,
        request_ref=request_ref,
        status=HybridCommitEvaluationStatus.INVALID,
        authoritative=False,
        terminal=True,
        assurance_downgraded=False,
        profile=profile,
        assurance=assurance,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        current_step=current_step,
        attention_status=HybridCommitAttentionStatus.UNAVAILABLE,
        binding_step_ref="",
        attention_ref="",
        exploration_directive_ref="",
        assessment_ref=(
            commit_assessment_fingerprint(assessment)
            if type(assessment) is CommitAssessment
            else ""
        ),
        context_ref=(
            commit_evaluation_context_fingerprint(context)
            if type(context) is CommitEvaluationContext
            else ""
        ),
        window_state_ref=(
            commit_window_state_fingerprint(window) if window else ""
        ),
        window_root=(window.window_root if window else ""),
        replay_state_ref=(
            commit_replay_state_fingerprint(replay) if replay else ""
        ),
        replay_root=(replay.receipt_root if replay else ""),
        progress_ref="",
        outcome_ref="",
        local_receipt_ref="",
        evidence_certificate_ref="",
        distributed_state_ref="",
        distributed_certificate_ref="",
        outcome_certificate_ref="",
        finality_verification_ref="",
        deliver_authorization_ref="",
        publish_authorization_ref="",
        execute_authorization_ref="",
        trace_event_ids=(),
        trace_root=commit_payload_fingerprint(
            {"event_ids": ()},
            schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
            profile=profile,
        ),
        diagnostics=diagnostic_values,
        evaluation_root=_ZERO_ROOT,
        commit_assessment=assessment,
        commit_window_state=window,
        commit_replay_state=replay,
    )
    root = commit_payload_fingerprint(
        _hybrid_commit_evaluation_payload(provisional, include_root=False),
        schema=HYBRID_COMMIT_EVALUATION_VERSION,
        profile=profile,
    )
    return _replace_evaluation_root(provisional, root)

def _has_fatal(diagnostics: Sequence[HybridCommitDiagnostic]) -> bool:
    return any(item.fatal for item in diagnostics)

def _exception_references(
    request: HybridCommitEvaluationRequest,
) -> tuple[str, ...]:
    values = (
        _safe_fingerprint(request.local_receipt, local_commit_receipt_fingerprint),
        _safe_fingerprint(
            request.evidence_certificate,
            evidence_commit_certificate_fingerprint,
        ),
        _safe_fingerprint(
            request.distributed_certificate,
            distributed_commit_certificate_fingerprint,
        ),
    )
    return tuple(item for item in values if item)



__all__ = ["evaluate_hybrid_commit_step"]
