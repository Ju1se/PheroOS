"""Private Commit TCK reference probes 31 34 handlers."""

from __future__ import annotations

from dataclasses import replace

from typing import Any

from pheroos.conformance._commit_reference import (
    build_reference_distributed_commit,
    build_reference_portable_commit,
    build_reference_stable_commit,
    reference_fingerprint,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_tck.models import (
    result as _result,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.certificate import (
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
)

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionOutcomeKind,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
)

from pheroos.governance.distributed_commit import (
    distributed_commit_state_fingerprint,
    evaluate_distributed_finality,
)

from pheroos.governance.hybrid_commit import (
    HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
    HybridCommitEvaluationRequest,
    evaluate_hybrid_commit_step,
    hybrid_commit_evaluation_is_authoritative,
)

from pheroos.governance.output import (
    authorize_terminal_publication,
    commit_output_authorization_fingerprint,
    deliver_terminal_outcome,
)

from pheroos.conformance._commit_tck_reference.authority import (
    _authority_trace_events,
    _hybrid_attention_for_scenario,
)

from pheroos.conformance._commit_tck_reference.distributed import (
    _output_gates,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _local_commit_outcome,
)

from pheroos.conformance._commit_tck_reference.mutation import (
    _coded_terminal_outcome,
    _terminal_variant_vector,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _reference_scenario,
    _risk_trace_sequence,
)

from pheroos.conformance._commit_tck_reference.timeline import (
    _deadline_outcome,
    _heartbeat_to_deadline,
)


def _probe_case_31(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-31")
    portable = build_reference_portable_commit(stable, variant="case-31")
    bundle = build_reference_distributed_commit(
        portable,
        witness_count=0,
        variant="case-31",
    )
    progress, outcome = _heartbeat_to_deadline(
        stable,
        suffix="case-31",
        final_status=CommitFinalityStatus.UNAVAILABLE,
        final_reason_codes=("witness_quorum_unavailable",),
    )
    decision = evaluate_distributed_finality(
        bundle.state,
        stable.receipt,
        certificate=None,
        current_step=outcome.current_step,
        outcome=outcome,
    )
    return _result(
        metrics={
            "pending_step": progress.current_step,
            "deadline_step": outcome.current_step,
            "witness_count": len(bundle.state.witness_verifications),
        },
        roots={
            "outcome_ref": decision_outcome_fingerprint(outcome),
            "distributed_state_ref": distributed_commit_state_fingerprint(bundle.state),
        },
        progress={"phase": progress.phase.value, "terminal": progress.terminal},
        outcome={
            "kind": outcome.kind.value,
            "distributed_finality_kind": decision.kind.value,
            "terminal": decision.terminal,
            "authoritative_commit": decision.authoritative_commit,
            "epistemically_committed": outcome.epistemically_committed,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="finality_unavailable",
    )


def _probe_case_32(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-32")
    outcome = _local_commit_outcome(stable, suffix="case-32")
    receipt_ref = local_commit_receipt_fingerprint(stable.receipt)
    stop, permission = _output_gates(
        scenario,
        outcome,
        certificate_ref=receipt_ref,
        suffix="case-32",
        issued_at_step=outcome.current_step,
        stop_expires_at_step=outcome.current_step + 3,
        permission_expires_at_step=outcome.current_step + 1,
    )
    current_step = outcome.current_step + 1
    publication = authorize_terminal_publication(
        outcome,
        commit_policy=collective_commit_policy(scenario.policy),
        threshold_snapshot=scenario.threshold,
        certificate=stable.receipt,
        output_payload_fingerprint=stable.output_fingerprint,
        stop_resolution=stop,
        permission=permission,
        current_step=current_step,
    )
    return _result(
        metrics={
            "commit_step": outcome.current_step,
            "publication_step": current_step,
            "permission_expires_at_step": permission.expires_at_step,
        },
        roots={
            "outcome_ref": decision_outcome_fingerprint(outcome),
            "receipt_ref": receipt_ref,
        },
        outcome={
            "historical_outcome_authoritative": decision_outcome_is_authoritative(
                outcome
            ),
            "historical_receipt_authoritative": local_commit_receipt_is_authoritative(
                stable.receipt
            ),
            "publication_authorized": publication.authorized,
            "publication_reason_codes": list(publication.reason_codes),
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "local_receipt", "historically_valid": True},
        failure_code="publication_permission_expired",
    )


def _probe_case_33(vector: _CommitTckRequest) -> dict[str, Any]:
    outcomes: dict[str, DecisionOutcome] = {}

    evidence_vector = _terminal_variant_vector(vector, "evidence_commit")
    evidence = _reference_scenario(evidence_vector)
    evidence_stable = build_reference_stable_commit(
        evidence,
        variant="case-33:evidence",
    )
    outcomes["evidence_commit"] = _local_commit_outcome(
        evidence_stable,
        suffix="case-33:evidence",
    )

    for kind in ("safe_fallback", "advisory"):
        selected = _terminal_variant_vector(vector, kind)
        scenario = _reference_scenario(selected)
        _, outcomes[kind] = _deadline_outcome(
            scenario,
            suffix=f"case-33:{kind}",
        )

    for kind, codes in (
        ("blocked", {"blocked": ("hard_commit_stop",)}),
        ("invalid", {"invalid": ("invalid_protocol_instance",)}),
        ("safety_violation", {"safety": ("authority_conflict",)}),
    ):
        selected = _terminal_variant_vector(vector, kind)
        scenario = _reference_scenario(selected)
        outcomes[kind] = _coded_terminal_outcome(
            scenario,
            suffix=f"case-33:{kind}",
            **codes,
        )

    unavailable_vector = _terminal_variant_vector(
        vector,
        "finality_unavailable",
    )
    unavailable = _reference_scenario(unavailable_vector)
    unavailable_stable = build_reference_stable_commit(
        unavailable,
        variant="case-33:finality-unavailable",
    )
    _, outcomes["finality_unavailable"] = _heartbeat_to_deadline(
        unavailable_stable,
        suffix="case-33:finality-unavailable",
        final_status=CommitFinalityStatus.UNAVAILABLE,
        final_reason_codes=("portable_certificate_unavailable",),
    )

    expected_kinds = tuple(item.value for item in DecisionOutcomeKind)
    if set(outcomes) != set(expected_kinds):
        raise ValueError("case 33 did not construct every terminal outcome kind")
    deliveries = {
        kind: deliver_terminal_outcome(
            outcome,
            output_payload_fingerprint=reference_fingerprint(
                f"delivery:{vector.id}:{kind}"
            ),
        )
        for kind, outcome in outcomes.items()
    }
    denied = tuple(
        sorted(kind for kind, result in deliveries.items() if not result.authorized)
    )
    return _result(
        metrics={
            "terminal_outcome_count": len(outcomes),
            "authorized_delivery_count": sum(
                int(item.authorized) for item in deliveries.values()
            ),
        },
        roots={
            "outcome_refs": {
                kind: decision_outcome_fingerprint(outcome)
                for kind, outcome in sorted(outcomes.items())
            },
            "delivery_roots": {
                kind: commit_output_authorization_fingerprint(delivery)
                for kind, delivery in sorted(deliveries.items())
            },
        },
        outcome={
            "all_terminal": all(item.terminal for item in outcomes.values()),
            "all_authoritative": all(
                decision_outcome_is_authoritative(item) for item in outcomes.values()
            ),
            "all_delivered": not denied,
            "denied_kinds": list(denied),
            "kinds": list(sorted(outcomes)),
        },
        trace_sequence=["decision_outcome", "output_decided"],
        failure_code=("terminal_delivery_denied" if denied else None),
    )


def _probe_case_34(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-34")
    step = stable.window.last_evaluated_step
    attention, directive = _hybrid_attention_for_scenario(
        scenario,
        current_step=step,
        candidate_id=scenario.other_id,
    )
    request = HybridCommitEvaluationRequest(
        request_version=HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
        request_id=f"hybrid-evaluation:{scenario.namespace}:case-34",
        attention=attention,
        exploration_directive=directive,
        commit_assessment=stable.assessments[-1],
        context=scenario.context,
        window_state=stable.window,
        replay_state=scenario.replay_state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=step,
        output_payload_fingerprint=stable.output_fingerprint,
        issuer_id="governance:tck:hybrid-total",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:hybrid-total",
        trace_event_id=f"trace:{scenario.namespace}:hybrid-total",
        local_receipt=stable.receipt,
        prior_trace_events=_authority_trace_events(scenario),
    )
    evaluation = evaluate_hybrid_commit_step(request=request)
    mutation_field = vector.inputs.get("evaluation_mutation_field", "")
    if not isinstance(mutation_field, str):
        raise ValueError("case 34 evaluation_mutation_field must be a string")
    checked_evaluation = evaluation
    if mutation_field:
        if mutation_field != "evaluation_root":
            raise ValueError("case 34 evaluation mutation field is unsupported")
        checked_evaluation = replace(
            evaluation,
            evaluation_root=reference_fingerprint(
                f"tampered:{scenario.namespace}:evaluation-root"
            ),
        )
    verified_authoritative = hybrid_commit_evaluation_is_authoritative(
        checked_evaluation
    )
    progress = evaluation.decision_progress
    outcome = evaluation.decision_outcome
    return _result(
        metrics={
            "diagnostic_count": len(evaluation.diagnostics),
            "trace_event_count": len(evaluation.trace_events),
        },
        roots={
            "evaluation_root": evaluation.evaluation_root,
            "progress_ref": evaluation.progress_ref,
            "outcome_ref": evaluation.outcome_ref,
            "local_receipt_ref": evaluation.local_receipt_ref,
            "evidence_certificate_ref": evaluation.evidence_certificate_ref,
            "distributed_certificate_ref": evaluation.distributed_certificate_ref,
            "trace_root": evaluation.trace_root,
        },
        progress=(
            {
                "phase": progress.phase.value,
                "next_required_inputs": list(progress.next_required_inputs),
                "terminal": progress.terminal,
            }
            if progress is not None
            else None
        ),
        outcome=(
            {
                "kind": outcome.kind.value,
                "authoritative_commit": outcome.authoritative_commit,
                "epistemically_committed": outcome.epistemically_committed,
            }
            if outcome is not None
            else None
        ),
        trace_sequence=[item.event_type for item in evaluation.trace_events],
        certificate={
            "declared_assurance": evaluation.assurance.value,
            "assurance_downgraded": evaluation.assurance_downgraded,
            "local_receipt_present": bool(evaluation.local_receipt_ref),
            "required_certificate_present": bool(
                evaluation.evidence_certificate_ref
                or evaluation.distributed_certificate_ref
            ),
            "self_reported_authoritative": checked_evaluation.authoritative,
            "verified_authoritative": verified_authoritative,
            "embedded_mutation_field": mutation_field,
            "terminal": evaluation.terminal,
        },
        failure_code=(
            "embedded_authority_mutation"
            if mutation_field and not verified_authoritative
            else "assurance_input_missing"
            if progress is not None
            and not evaluation.evidence_certificate_ref
            and not evaluation.assurance_downgraded
            else None
        ),
    )
