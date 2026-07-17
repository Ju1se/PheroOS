from __future__ import annotations

"""Authoritative Hybrid Commit trace construction and lineage helpers."""

from collections.abc import Sequence
from typing import Any

from pheroos.governance._certificate.local import (
    LOCAL_COMMIT_RECEIPT_VERSION,
    LocalCommitReceipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_payload,
)
from pheroos.governance._certificate.outcome import (
    OUTCOME_CERTIFICATE_VERSION,
    OutcomeCertificate,
    outcome_certificate_fingerprint,
    outcome_certificate_payload,
)
from pheroos.governance._certificate.portable import (
    EVIDENCE_COMMIT_CERTIFICATE_VERSION,
    EvidenceCommitCertificate,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_payload,
)
from pheroos.governance._hybrid.output import _certificate_for_outcome
from pheroos.governance._hybrid.request import HybridCommitEvaluationRequest
from pheroos.governance.commit import (
    CommitAssessment,
    candidate_commit_metrics_fingerprint,
    candidate_commit_metrics_payload,
    commit_assessment_fingerprint,
)
from pheroos.governance.commit_state import (
    CommitWindowState,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionProgress,
    commit_window_state_fingerprint,
    commit_window_state_payload,
    decision_outcome_fingerprint,
    decision_outcome_payload,
    decision_progress_fingerprint,
    decision_progress_payload,
)
from pheroos.governance.distributed_commit import (
    DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
    DISTRIBUTED_STATE_VERSION,
    WITNESS_VERIFICATION_VERSION,
    DistributedCommitCertificate,
    DistributedCommitState,
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_payload,
    distributed_commit_state_fingerprint,
    distributed_commit_state_payload,
    witness_verification_fingerprint,
    witness_verification_is_authoritative,
    witness_verification_payload,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.output import (
    CommitOutputAuthorization,
    commit_output_authorization_payload,
)
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
    action_permission_is_authoritative,
    action_permission_payload,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
    stop_resolution_verification_is_authoritative,
    stop_resolution_verification_payload,
)
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.trace import TraceEvent, make_commit_trace_event
from pheroos.trace.commit_contracts import replay_commit_trace


def _build_evaluation_trace(
    request: HybridCommitEvaluationRequest,
    *,
    prior_trace: tuple[TraceEvent, ...],
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    progress: DecisionProgress | None,
    outcome: DecisionOutcome | None,
    local_receipt: LocalCommitReceipt | None,
    evidence_certificate: EvidenceCommitCertificate | None,
    distributed_state: DistributedCommitState | None,
    distributed_certificate: DistributedCommitCertificate | None,
    outcome_certificate: OutcomeCertificate | None,
    deliver: CommitOutputAuthorization | None,
    publish: CommitOutputAuthorization | None,
    execute: CommitOutputAuthorization | None,
    invalid_path: bool,
) -> tuple[TraceEvent, ...]:
    events = list(prior_trace)
    if invalid_path and not prior_trace:
        # No observation/evidence events are invented when the caller cannot
        # provide a valid upstream chain.  An issued invalid outcome and its
        # mandatory delivery remain traceable without claiming those facts.
        if outcome is None or deliver is None:
            raise GovernanceError("invalid trace path lacks outcome or delivery")
        outcome_event = _decision_outcome_trace_event(
            request,
            outcome,
            previous=(),
        )
        output_event = _output_trace_event(
            request,
            outcome=outcome,
            deliver=deliver,
            publish=publish,
            execute=execute,
            certificate=None,
            distributed_state=None,
            previous=(outcome_event,),
        )
        result = (outcome_event, output_event)
        replay_commit_trace(result, require_complete=True)
        return result

    metric_events: list[TraceEvent] = []
    predecessor_ids = tuple(
        event.lineage["event_id"]
        for event in events
    )
    for metrics in assessment.candidate_metrics:
        metrics_ref = candidate_commit_metrics_fingerprint(
            metrics,
            profile=assessment.profile,
        )
        existing = _find_trace_record(events, "commit_metrics", metrics_ref)
        if existing is not None:
            metric_events.append(existing)
            continue
        event = make_commit_trace_event(
            event_type="commit_metrics",
            protocol_id=assessment.protocol_id,
            target=assessment.target,
            reason="recorded authoritative Optimal Commit candidate metrics",
            profile=assessment.profile,
            assurance=assessment.assurance.value,
            manifest_root=assessment.manifest_root,
            commit_policy_root=assessment.commit_policy_root,
            run_id=assessment.run_id,
            epoch=assessment.epoch,
            step=max(assessment.evaluated_at_step, _last_trace_step(events)),
            record_schema="pheroos-candidate-commit-metrics-v1",
            record_payload=candidate_commit_metrics_payload(metrics),
            previous_event_ids=predecessor_ids,
            details={
                "assessment_ref": commit_assessment_fingerprint(assessment),
                "candidate_id": metrics.candidate_id,
                "net_evidence": metrics.net_evidence,
                "support_clusters": metrics.active_support_clusters,
                "source_diversity": metrics.source_diversity,
                "margin": metrics.margin,
                "ready_for_stability": metrics.ready_for_stability,
            },
        )
        events.append(event)
        metric_events.append(event)

    window_ref = commit_window_state_fingerprint(window_state)
    window_event = _find_trace_record(
        events,
        ("commit_window_advanced", "commit_window_reset"),
        window_ref,
    )
    if window_event is None:
        reset_count = (
            request.commit_policy.commit_window.maximum_leader_resets
            - window_state.remaining_reset_budget
        )
        is_reset = bool(
            window_state.previous_state_fingerprint
            and window_state.reset_reason
            not in {"", "none", "initialized"}
        )
        if is_reset:
            window_event = make_commit_trace_event(
                event_type="commit_window_reset",
                protocol_id=assessment.protocol_id,
                target=assessment.target,
                reason="reset authoritative commit stability window",
                profile=assessment.profile,
                assurance=assessment.assurance.value,
                manifest_root=assessment.manifest_root,
                commit_policy_root=assessment.commit_policy_root,
                run_id=assessment.run_id,
                epoch=assessment.epoch,
                step=request.current_step,
                record_schema="pheroos-commit-window-state-v1",
                record_payload=commit_window_state_payload(window_state),
                previous_event_ids=tuple(
                    event.lineage["event_id"] for event in events
                ),
                details={
                    "assessment_ref": commit_assessment_fingerprint(assessment),
                    "prior_window_ref": window_state.previous_state_fingerprint,
                    "reset_count": max(1, reset_count),
                    "remaining_reset_budget": window_state.remaining_reset_budget,
                    "reason_codes": [window_state.reset_reason],
                },
            )
        else:
            window_event = make_commit_trace_event(
                event_type="commit_window_advanced",
                protocol_id=assessment.protocol_id,
                target=assessment.target,
                reason="advanced authoritative commit stability window",
                profile=assessment.profile,
                assurance=assessment.assurance.value,
                manifest_root=assessment.manifest_root,
                commit_policy_root=assessment.commit_policy_root,
                run_id=assessment.run_id,
                epoch=assessment.epoch,
                step=request.current_step,
                record_schema="pheroos-commit-window-state-v1",
                record_payload=commit_window_state_payload(window_state),
                previous_event_ids=tuple(
                    event.lineage["event_id"] for event in metric_events
                ),
                details={
                    "assessment_ref": commit_assessment_fingerprint(assessment),
                    "leader_candidate_id": window_state.leader_candidate_id,
                    "stability_count": window_state.window_count,
                    "required_stability_steps": window_state.minimum_stability_steps,
                    "window_root": window_state.window_root,
                    "reset_count": max(0, reset_count),
                },
            )
        events.append(window_event)

    certificate_events: list[TraceEvent] = []
    for certificate, kind, final in (
        (
            local_receipt,
            "local_receipt",
            assessment.assurance is CommitAssurance.EVIDENCE_BOUND,
        ),
        (
            evidence_certificate,
            "evidence_commit",
            assessment.assurance is CommitAssurance.CERTIFIED,
        ),
    ):
        if certificate is None:
            continue
        cert_event = _certificate_trace_event(
            request,
            certificate=certificate,
            certificate_kind=kind,
            final=final,
            previous=(window_event,),
        )
        existing = _find_trace_record(
            events,
            "commit_certificate_issued",
            cert_event.lineage["record_ref"],
        )
        if existing is None:
            events.append(cert_event)
            certificate_events.append(cert_event)
        else:
            certificate_events.append(existing)

    distributed_lineage = _append_distributed_witness_trace(
        request,
        events=events,
        window_event=window_event,
        portable_certificate_event=next(
            (
                item
                for item in certificate_events
                if item.lineage["certificate_kind"] == "evidence_commit"
            ),
            None,
        ),
        distributed_state=distributed_state,
        distributed_certificate=distributed_certificate,
    )
    if distributed_certificate is not None:
        cert_event = _certificate_trace_event(
            request,
            certificate=distributed_certificate,
            certificate_kind="distributed_commit",
            final=True,
            previous=tuple((window_event, *distributed_lineage)),
        )
        existing = _find_trace_record(
            events,
            "commit_certificate_issued",
            cert_event.lineage["record_ref"],
        )
        if existing is None:
            events.append(cert_event)
            certificate_events.append(cert_event)
        else:
            certificate_events.append(existing)
    distributed_conflicts = _append_distributed_conflict_trace(
        events=events,
        distributed_state=distributed_state,
    )
    distributed_lineage = tuple((*distributed_lineage, *distributed_conflicts))

    if outcome_certificate is not None:
        cert_event = _certificate_trace_event(
            request,
            certificate=outcome_certificate,
            certificate_kind="outcome",
            final=True,
            previous=(window_event,),
        )
        existing = _find_trace_record(
            events,
            "commit_certificate_issued",
            cert_event.lineage["record_ref"],
        )
        if existing is None:
            events.append(cert_event)
            certificate_events.append(cert_event)
        else:
            certificate_events.append(existing)

    if progress is not None:
        progress_ref = decision_progress_fingerprint(progress)
        existing = _find_trace_record(events, "quorum_pending", progress_ref)
        if existing is None:
            details: dict[str, object] = {
                "assessment_ref": progress.assessment_ref,
                "phase": progress.phase.value,
                "unmet_gates": list(progress.unmet_gates),
                "absolute_deadline_step": progress.absolute_deadline_step,
            }
            if progress.seal_ref:
                details["sealed_window_ref"] = progress.seal_ref
            if progress.previous_progress_ref:
                details["previous_progress_ref"] = progress.previous_progress_ref
            progress_event = make_commit_trace_event(
                event_type="quorum_pending",
                protocol_id=progress.protocol_id,
                target=progress.target,
                reason="Optimal Commit remains non-terminal pending declared gates",
                profile=progress.profile,
                assurance=progress.assurance.value,
                manifest_root=progress.manifest_root,
                commit_policy_root=progress.commit_policy_root,
                run_id=progress.run_id,
                epoch=progress.epoch,
                step=progress.current_step,
                record_schema="pheroos-decision-progress-v1",
                record_payload=decision_progress_payload(progress),
                previous_event_ids=tuple(
                    item.lineage["event_id"]
                    for item in (
                        window_event,
                        *certificate_events,
                        *distributed_lineage,
                    )
                ),
                details=details,
            )
            events.append(progress_event)
        result = tuple(events)
        replay_commit_trace(result, require_complete=False)
        return result

    if outcome is None or deliver is None:
        raise GovernanceError("terminal evaluation trace lacks outcome or delivery")
    outcome_event = _decision_outcome_trace_event(
        request,
        outcome,
        previous=tuple(
            (*certificate_events, *distributed_lineage, window_event)
        ),
    )
    events.append(outcome_event)
    action_authority_events = _append_current_action_authority_trace(
        request,
        events=events,
        outcome_event=outcome_event,
    )
    action_certificate = _certificate_for_outcome(
        outcome,
        local_receipt=local_receipt,
        evidence_certificate=evidence_certificate,
        distributed_certificate=distributed_certificate,
        outcome_certificate=outcome_certificate,
    )
    output_event = _output_trace_event(
        request,
        outcome=outcome,
        deliver=deliver,
        publish=publish,
        execute=execute,
        certificate=action_certificate,
        distributed_state=distributed_state,
        previous=tuple((outcome_event, *action_authority_events)),
    )
    events.append(output_event)
    result = tuple(events)
    replay = replay_commit_trace(result, require_complete=True)
    if replay.outcome_ref != decision_outcome_fingerprint(outcome):
        raise GovernanceError("trace replay outcome does not match governance result")
    if outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT and (
        outcome.certificate_ref not in replay.certificate_refs
    ):
        raise GovernanceError("trace replay omits the exact commit certificate")
    return result

def _certificate_trace_event(
    request: HybridCommitEvaluationRequest,
    *,
    certificate: object,
    certificate_kind: str,
    final: bool,
    previous: tuple[TraceEvent, ...],
) -> TraceEvent:
    if type(certificate) is LocalCommitReceipt:
        payload = local_commit_receipt_payload(certificate)
        schema = LOCAL_COMMIT_RECEIPT_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.claim_fingerprint
        output = certificate.output_payload_fingerprint
        scope = certificate
    elif type(certificate) is EvidenceCommitCertificate:
        payload = evidence_commit_certificate_payload(certificate)
        schema = EVIDENCE_COMMIT_CERTIFICATE_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.claim_fingerprint
        output = certificate.output_payload_fingerprint
        scope = certificate
    elif type(certificate) is DistributedCommitCertificate:
        payload = distributed_commit_certificate_payload(certificate)
        schema = DISTRIBUTED_COMMIT_CERTIFICATE_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.proposal.claim_fingerprint
        output = certificate.proposal.output_payload_fingerprint
        scope = certificate
        commit_value_root = certificate.commit_value_root
    elif type(certificate) is OutcomeCertificate:
        payload = outcome_certificate_payload(certificate)
        schema = OUTCOME_CERTIFICATE_VERSION
        candidate_id = certificate.candidate_id
        claim = certificate.claim_fingerprint
        output = certificate.output_payload_fingerprint
        scope = certificate
    else:
        raise GovernanceError("commit certificate trace record is not canonical")
    details = {
        "certificate_kind": certificate_kind,
        "candidate_id": candidate_id,
        "claim_fingerprint": claim,
        "output_fingerprint": output,
        "final": final,
    }
    if type(certificate) is DistributedCommitCertificate:
        details["commit_value_root"] = commit_value_root
    return make_commit_trace_event(
        event_type="commit_certificate_issued",
        protocol_id=scope.protocol_id,
        target=scope.target,
        reason=f"recorded {certificate_kind} certificate",
        profile=scope.profile,
        assurance=scope.assurance.value,
        manifest_root=scope.manifest_root,
        commit_policy_root=scope.commit_policy_root,
        run_id=scope.run_id,
        epoch=scope.epoch,
        step=max(scope.issued_at_step, _last_trace_step(previous)),
        record_schema=schema,
        record_payload=payload,
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
    )

def _append_distributed_witness_trace(
    request: HybridCommitEvaluationRequest,
    *,
    events: list[TraceEvent],
    window_event: TraceEvent,
    portable_certificate_event: TraceEvent | None,
    distributed_state: DistributedCommitState | None,
    distributed_certificate: DistributedCommitCertificate | None,
) -> tuple[TraceEvent, ...]:
    if distributed_state is None:
        return ()
    if portable_certificate_event is None:
        raise GovernanceError(
            "distributed trace requires the exact portable certificate event"
        )

    by_ref: dict[str, object] = {}
    for verification in (
        *distributed_state.witness_verifications,
        *(
            distributed_certificate.witnesses
            if distributed_certificate is not None
            else ()
        ),
    ):
        if not witness_verification_is_authoritative(verification):
            raise GovernanceError(
                "distributed trace witness verification is not authoritative"
            )
        by_ref[witness_verification_fingerprint(verification)] = verification
    verifications = tuple(by_ref[key] for key in sorted(by_ref))
    if not verifications:
        state_ref = distributed_commit_state_fingerprint(distributed_state)
        existing = _find_trace_record(events, "commit_provisional", state_ref)
        if existing is None:
            existing = make_commit_trace_event(
                event_type="commit_provisional",
                protocol_id=distributed_state.protocol_id,
                target=distributed_state.target,
                reason="distributed commit awaits its first verified witness",
                profile=distributed_state.profile,
                assurance=distributed_state.assurance.value,
                manifest_root=distributed_state.manifest_root,
                commit_policy_root=distributed_state.commit_policy_root,
                run_id=distributed_state.run_id,
                epoch=distributed_state.epoch,
                step=max(distributed_state.current_step, _last_trace_step(events)),
                record_schema=DISTRIBUTED_STATE_VERSION,
                record_payload=distributed_commit_state_payload(distributed_state),
                previous_event_ids=(
                    portable_certificate_event.lineage["event_id"],
                ),
                details={
                    "portable_certificate_ref": portable_certificate_event.lineage[
                        "certificate_ref"
                    ],
                    "candidate_id": portable_certificate_event.lineage[
                        "candidate_id"
                    ],
                    "witness_count": 0,
                    "witness_quorum": distributed_state.witness_quorum,
                    "final": False,
                },
            )
            events.append(existing)
        return (existing,)

    witness_events: list[TraceEvent] = []
    for verification in verifications:
        witness = verification.witness
        verification_ref = witness_verification_fingerprint(verification)
        existing = _find_trace_record(events, "quorum_witness", verification_ref)
        if existing is None:
            existing = make_commit_trace_event(
                event_type="quorum_witness",
                protocol_id=witness.protocol_id,
                target=witness.target,
                reason="verified distributed commit quorum witness",
                profile=witness.profile,
                assurance=witness.assurance.value,
                manifest_root=distributed_state.manifest_root,
                commit_policy_root=distributed_state.commit_policy_root,
                run_id=witness.run_id,
                epoch=witness.epoch,
                step=max(verification.verified_at_step, _last_trace_step(events)),
                record_schema=WITNESS_VERIFICATION_VERSION,
                record_payload=witness_verification_payload(verification),
                previous_event_ids=(
                    portable_certificate_event.lineage["event_id"],
                ),
                details={
                    "proposal_digest": witness.proposal_digest,
                    "commit_value_root": witness.commit_value_root,
                    "principal_cluster_id": witness.principal_cluster_id,
                    "failure_domain": witness.failure_domain,
                    "verified": True,
                    "expires_at_step": verification.expires_at_step,
                },
            )
            events.append(existing)
        witness_events.append(existing)

    included = tuple(
        item
        for item in verifications
        if item.witness.principal_cluster_id
        not in distributed_state.excluded_cluster_ids
    )
    commit_value_roots = {item.witness.commit_value_root for item in included}
    if len(commit_value_roots) != 1:
        if not distributed_state.frozen:
            raise GovernanceError(
                "non-frozen distributed trace has conflicting commit values"
            )
        return tuple(witness_events)
    grouped: dict[tuple[str, str, str], list[Any]] = {}
    for item in included:
        key = (
            item.witness.commit_value_root,
            item.witness.proposal_digest,
            item.witness.candidate_id,
        )
        grouped.setdefault(key, []).append(item)
    if not grouped:
        raise GovernanceError("distributed trace lacks an eligible witness group")
    if distributed_certificate is not None:
        selected_key = (
            distributed_certificate.commit_value_root,
            distributed_certificate.proposal_digest,
            distributed_certificate.candidate_id,
        )
        if selected_key not in grouped:
            raise GovernanceError(
                "distributed certificate lacks its exact witness proposal group"
            )
    else:
        selected_key = min(
            grouped,
            key=lambda key: (
                -len(
                    {
                        item.witness.principal_cluster_id
                        for item in grouped[key]
                    }
                ),
                key,
            ),
        )
    selected_group = tuple(grouped[selected_key])
    commit_value_root, proposal_digest, candidate_id = selected_key
    witness_count = len(
        {item.witness.principal_cluster_id for item in selected_group}
    )
    if witness_count >= distributed_state.witness_quorum:
        return tuple(witness_events)

    state_ref = distributed_commit_state_fingerprint(distributed_state)
    existing = _find_trace_record(events, "commit_provisional", state_ref)
    if existing is None:
        existing = make_commit_trace_event(
            event_type="commit_provisional",
            protocol_id=distributed_state.protocol_id,
            target=distributed_state.target,
            reason="distributed commit remains below declared witness quorum",
            profile=distributed_state.profile,
            assurance=distributed_state.assurance.value,
            manifest_root=distributed_state.manifest_root,
            commit_policy_root=distributed_state.commit_policy_root,
            run_id=distributed_state.run_id,
            epoch=distributed_state.epoch,
            step=max(distributed_state.current_step, _last_trace_step(events)),
            record_schema=DISTRIBUTED_STATE_VERSION,
            record_payload=distributed_commit_state_payload(distributed_state),
            previous_event_ids=tuple(
                item.lineage["event_id"] for item in witness_events
            ),
            details={
                "portable_certificate_ref": portable_certificate_event.lineage[
                    "certificate_ref"
                ],
                "proposal_digest": proposal_digest,
                "commit_value_root": commit_value_root,
                "candidate_id": candidate_id,
                "witness_count": witness_count,
                "witness_quorum": distributed_state.witness_quorum,
                "final": False,
            },
        )
        events.append(existing)
    return tuple((*witness_events, existing))

def _append_distributed_conflict_trace(
    *,
    events: list[TraceEvent],
    distributed_state: DistributedCommitState | None,
) -> tuple[TraceEvent, ...]:
    if distributed_state is None or not distributed_state.frozen:
        return ()
    state_ref = distributed_commit_state_fingerprint(distributed_state)
    result: list[TraceEvent] = []
    for finding in distributed_state.conflict_findings:
        certificate_events: list[TraceEvent] = []
        for certificate_ref in finding.certificate_refs:
            event = _find_trace_record(
                events,
                "commit_certificate_issued",
                certificate_ref,
            )
            if event is None:
                raise GovernanceError(
                    "frozen distributed state lacks exact conflicting certificate lineage"
                )
            certificate_events.append(event)
        payload = {
            "finding_id": finding.finding_id,
            "target": finding.target,
            "epoch": finding.epoch,
            "certificate_refs": finding.certificate_refs,
            "commit_value_roots": finding.commit_value_roots,
            "proposal_digests": finding.proposal_digests,
            "candidate_ids": finding.candidate_ids,
            "detected_at_step": finding.detected_at_step,
        }
        event = make_commit_trace_event(
            event_type="certificate_conflict",
            protocol_id=distributed_state.protocol_id,
            target=distributed_state.target,
            reason="detected conflicting final distributed certificates",
            profile=distributed_state.profile,
            assurance=distributed_state.assurance.value,
            manifest_root=distributed_state.manifest_root,
            commit_policy_root=distributed_state.commit_policy_root,
            run_id=distributed_state.run_id,
            epoch=distributed_state.epoch,
            step=max(finding.detected_at_step, _last_trace_step(events)),
            record_schema="pheroos-certificate-conflict-finding-v1",
            record_payload=payload,
            previous_event_ids=tuple(
                item.lineage["event_id"] for item in certificate_events
            ),
            details={
                "finding_id": finding.finding_id,
                "left_certificate_ref": finding.certificate_refs[0],
                "right_certificate_ref": finding.certificate_refs[1],
                "commit_value_roots": finding.commit_value_roots,
                "distributed_state_ref": state_ref,
                "frozen": True,
            },
        )
        existing = _find_trace_record(
            events,
            "certificate_conflict",
            event.lineage["record_ref"],
        )
        if existing is None:
            events.append(event)
            result.append(event)
        else:
            result.append(existing)
    if not result:
        raise GovernanceError(
            "frozen distributed state requires certificate conflict lineage"
        )
    return tuple(result)

def _decision_outcome_trace_event(
    request: HybridCommitEvaluationRequest,
    outcome: DecisionOutcome,
    *,
    previous: tuple[TraceEvent, ...],
) -> TraceEvent:
    details: dict[str, object] = {
        "kind": outcome.kind.value,
        "authoritative_commit": outcome.authoritative_commit,
        "epistemically_committed": outcome.epistemically_committed,
        "candidate_id": outcome.candidate_id,
        "reason_codes": sorted(set(outcome.reason_codes)),
    }
    if outcome.assessment_ref:
        details["assessment_ref"] = outcome.assessment_ref
    if outcome.certificate_ref:
        details["certificate_ref"] = outcome.certificate_ref
    if outcome.seal_ref:
        details["sealed_window_ref"] = outcome.seal_ref
    return make_commit_trace_event(
        event_type="decision_outcome",
        protocol_id=outcome.protocol_id,
        target=outcome.target,
        reason=f"issued terminal {outcome.kind.value} outcome",
        profile=outcome.profile,
        assurance=outcome.assurance.value,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        run_id=outcome.run_id,
        epoch=outcome.epoch,
        step=outcome.current_step,
        record_schema="pheroos-decision-outcome-v1",
        record_payload=decision_outcome_payload(outcome),
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
    )

def _append_current_action_authority_trace(
    request: HybridCommitEvaluationRequest,
    *,
    events: list[TraceEvent],
    outcome_event: TraceEvent,
) -> tuple[TraceEvent, ...]:
    """Record the exact canonical publish/execute facts consumed by authorization.

    Cross-action, blocked, denied, and expired facts remain useful negative
    evidence and are therefore traced too.  Malformed or non-authoritative
    caller objects are never promoted into verified trace facts; the output
    authorizer records their fail-closed denial instead.
    """

    dependencies: list[TraceEvent] = []
    seen_ids: set[str] = set()
    facts = (
        request.publish_stop_resolution,
        request.publish_permission,
        request.execute_stop_resolution,
        request.execute_permission,
    )
    for fact in facts:
        if not _action_fact_matches_trace_identity(
            fact,
            request=request,
            outcome_event=outcome_event,
        ):
            continue
        if type(fact) is StopResolutionVerification:
            if not stop_resolution_verification_is_authoritative(fact):
                continue
            record_ref = stop_resolution_verification_fingerprint(fact)
            event_type = "stop_resolution_verified"
            record_schema = "pheroos-stop-resolution-verification-v1"
            record_payload = stop_resolution_verification_payload(fact)
            details = {
                "action": fact.action.value,
                "blocked": fact.blocked,
                "expires_at_step": fact.expires_at_step,
            }
            reason = f"recorded current {fact.action.value} stop resolution"
        elif type(fact) is ActionPermission:
            if not action_permission_is_authoritative(fact):
                continue
            record_ref = action_permission_fingerprint(fact)
            event_type = "action_permission_issued"
            record_schema = "pheroos-action-permission-v1"
            record_payload = action_permission_payload(fact)
            details = {
                "action": fact.action.value,
                "allowed": fact.allowed,
                "expires_at_step": fact.expires_at_step,
            }
            reason = f"recorded current {fact.action.value} action permission"
        else:
            continue

        existing = _find_trace_record(events, event_type, record_ref)
        if existing is None:
            existing = make_commit_trace_event(
                event_type=event_type,
                protocol_id=fact.protocol_id,
                target=fact.target,
                reason=reason,
                profile=fact.profile,
                assurance=fact.assurance.value,
                manifest_root=fact.manifest_root,
                commit_policy_root=fact.commit_policy_root,
                run_id=fact.run_id,
                epoch=fact.epoch,
                step=max(fact.issued_at_step, _last_trace_step(events)),
                record_schema=record_schema,
                record_payload=record_payload,
                previous_event_ids=(outcome_event.lineage["event_id"],),
                details=details,
            )
            events.append(existing)
        event_id = existing.lineage["event_id"]
        if event_id not in seen_ids:
            dependencies.append(existing)
            seen_ids.add(event_id)
    return tuple(dependencies)

def _action_fact_matches_trace_identity(
    fact: object,
    *,
    request: HybridCommitEvaluationRequest,
    outcome_event: TraceEvent,
) -> bool:
    if type(fact) not in {StopResolutionVerification, ActionPermission}:
        return False
    lineage = outcome_event.lineage
    try:
        return bool(
            fact.profile == lineage["profile"]
            and fact.assurance.value == lineage["assurance"]
            and fact.manifest_root == lineage["manifest_root"]
            and fact.commit_policy_root == lineage["commit_policy_root"]
            and fact.protocol_id == outcome_event.protocol_id
            and fact.run_id == lineage["run_id"]
            and fact.target == outcome_event.target
            and fact.epoch == lineage["epoch"]
            and fact.issued_at_step <= request.current_step
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False

def _output_trace_event(
    request: HybridCommitEvaluationRequest,
    *,
    outcome: DecisionOutcome,
    deliver: CommitOutputAuthorization,
    publish: CommitOutputAuthorization | None,
    execute: CommitOutputAuthorization | None,
    certificate: object | None,
    distributed_state: DistributedCommitState | None,
    previous: tuple[TraceEvent, ...],
) -> TraceEvent:
    payload = {
        "outcome_ref": decision_outcome_fingerprint(outcome),
        "authorizations": {
            "deliver": commit_output_authorization_payload(deliver),
            "publish": (
                commit_output_authorization_payload(publish) if publish else None
            ),
            "execute": (
                commit_output_authorization_payload(execute) if execute else None
            ),
        },
    }
    reasons = set(deliver.reason_codes)
    if publish is not None:
        reasons.update(publish.reason_codes)
    if execute is not None:
        reasons.update(execute.reason_codes)
    details: dict[str, object] = {
        "outcome_ref": decision_outcome_fingerprint(outcome),
        "deliver": deliver.authorized,
        "publish": bool(publish and publish.authorized),
        "execute": bool(execute and execute.authorized),
        "reason_codes": sorted(reasons),
    }
    if certificate is not None:
        details["certificate_ref"] = _certificate_fingerprint(certificate)
    if distributed_state is not None:
        details["distributed_state_ref"] = distributed_commit_state_fingerprint(
            distributed_state
        )
    return make_commit_trace_event(
        event_type="output_decided",
        protocol_id=outcome.protocol_id,
        target=outcome.target,
        reason="evaluated mandatory delivery and independent action gates",
        profile=outcome.profile,
        assurance=outcome.assurance.value,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        run_id=outcome.run_id,
        epoch=outcome.epoch,
        step=outcome.current_step,
        record_schema="pheroos-commit-output-decision-v1",
        record_payload=payload,
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
    )

def _certificate_fingerprint(certificate: object) -> str:
    if type(certificate) is LocalCommitReceipt:
        return local_commit_receipt_fingerprint(certificate)
    if type(certificate) is EvidenceCommitCertificate:
        return evidence_commit_certificate_fingerprint(certificate)
    if type(certificate) is DistributedCommitCertificate:
        return distributed_commit_certificate_fingerprint(certificate)
    if type(certificate) is OutcomeCertificate:
        return outcome_certificate_fingerprint(certificate)
    raise GovernanceError("output certificate is not canonical")

def _find_trace_record(
    events: Sequence[TraceEvent],
    event_types: str | tuple[str, ...],
    record_ref: str,
) -> TraceEvent | None:
    allowed = {event_types} if isinstance(event_types, str) else set(event_types)
    return next(
        (
            event
            for event in events
            if event.event_type in allowed
            and event.lineage["record_ref"] == record_ref
        ),
        None,
    )

def _last_trace_step(events: Sequence[TraceEvent]) -> int:
    return max((event.lineage["step"] for event in events), default=0)



__all__: list[str] = []
