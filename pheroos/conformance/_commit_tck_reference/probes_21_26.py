"""Private Commit TCK reference probes 21 26 handlers."""

from __future__ import annotations

from copy import deepcopy

from dataclasses import replace

from typing import Any

from pheroos.conformance._commit_reference import (
    assess_reference_scenario,
    build_reference_portable_commit,
    build_reference_stable_commit,
    issue_reference_action_gates,
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
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_payload,
    local_commit_receipt_fingerprint,
    outcome_certificate_payload,
    issue_outcome_certificate,
    verify_evidence_commit_certificate,
)

from pheroos.governance.commit import (
    CommitAssessmentStatus,
    commit_assessment_fingerprint,
)

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionOutcomeKind,
    ReplayNamespace,
    ReplayReceipt,
    decision_outcome_fingerprint,
    record_commit_replay_receipts,
    reduce_commit_liveness,
)

from pheroos.governance.errors import GovernanceError

from pheroos.governance.stop_signal import (
    stop_resolution_verification_fingerprint,
)

from pheroos.protocol.commit_models import CommitAction

from pheroos.protocol.commit_wire import (
    commit_payload_fingerprint,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _initialize_window,
    _liveness_input,
)

from pheroos.conformance._commit_tck_reference.mutation import (
    _mutate_path,
    _scalar_leaf_paths,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _reference_scenario,
    _risk_trace_event,
    _risk_trace_sequence,
)

from pheroos.conformance._commit_tck_reference.state import (
    advance_commit_window_state,
)

from pheroos.conformance._commit_tck_reference.timeline import (
    _deadline_outcome,
)


def _probe_case_21(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, blocked=True)
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(scenario, step=5, suffix="hard-stop")
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=collective_commit_policy(scenario.policy),
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    terminal = reduce_commit_liveness(
        window,
        commit_policy=collective_commit_policy(scenario.policy),
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=5,
            suffix="hard-stop",
            finality_status=CommitFinalityStatus.PENDING,
        ),
    )
    if type(terminal) is not DecisionOutcome:
        raise ValueError("hard commit stop did not become terminal")
    return _result(
        metrics={"window_count": window.window_count},
        roots={
            "stop_resolution_root": assessment.stop_resolution_fingerprint,
            "outcome_ref": decision_outcome_fingerprint(terminal),
        },
        outcome={
            "kind": terminal.kind.value,
            "candidate_id": terminal.candidate_id,
            "fallback_bypassed_stop": terminal.kind
            is DecisionOutcomeKind.SAFE_FALLBACK,
            "authoritative_commit": terminal.authoritative_commit,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="commit_hard_stop",
    )


def _probe_case_22(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    publish_stop, publish_permission = issue_reference_action_gates(
        scenario.namespace,
        context=scenario.context,
        action=CommitAction.PUBLISH,
        blocked=False,
        current_step=5,
        expires_at_step=20,
        suffix="publish-only",
    )
    commit_rejected_publish_stop = False
    try:
        mismatched = assess_reference_scenario(
            scenario,
            step=5,
            suffix="publish-stop-as-commit",
            stop_resolution=publish_stop,
            permission=publish_permission,
        )
        commit_rejected_publish_stop = (
            mismatched.status is not CommitAssessmentStatus.READY
        )
    except (GovernanceError, ValueError):
        commit_rejected_publish_stop = True
    execute_stop, _ = issue_reference_action_gates(
        scenario.namespace,
        context=scenario.context,
        action=CommitAction.EXECUTE,
        blocked=False,
        current_step=5,
        expires_at_step=20,
        suffix="execute-only",
    )
    return _result(
        metrics={
            "distinct_action_count": len(
                {
                    scenario.stop_resolution.action.value,
                    publish_stop.action.value,
                    execute_stop.action.value,
                }
            )
        },
        roots={
            "commit_stop_ref": stop_resolution_verification_fingerprint(
                scenario.stop_resolution
            ),
            "publish_stop_ref": stop_resolution_verification_fingerprint(publish_stop),
            "execute_stop_ref": stop_resolution_verification_fingerprint(execute_stop),
        },
        outcome={
            "commit_rejected_publish_gate": commit_rejected_publish_stop,
            "actions": [
                scenario.stop_resolution.action.value,
                publish_stop.action.value,
                execute_stop.action.value,
            ],
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="action_scope_mismatch" if commit_rejected_publish_stop else None,
    )


def _probe_case_23(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    other_stop, other_permission = issue_reference_action_gates(
        scenario.namespace,
        context=scenario.context,
        action=CommitAction.COMMIT,
        blocked=True,
        current_step=5,
        expires_at_step=20,
        suffix="other-target",
        target="decision:other",
    )
    rejected_other_target = False
    try:
        mismatched = assess_reference_scenario(
            scenario,
            step=5,
            suffix="other-target",
            stop_resolution=other_stop,
            permission=other_permission,
        )
        rejected_other_target = mismatched.status is not CommitAssessmentStatus.READY
    except (GovernanceError, ValueError):
        rejected_other_target = True
    unaffected = assess_reference_scenario(
        scenario,
        step=5,
        suffix="target-a",
    )
    return _result(
        metrics={"target_count": 2},
        roots={"target_a_assessment_ref": commit_assessment_fingerprint(unaffected)},
        outcome={
            "target_a": scenario.target,
            "target_b": other_stop.target,
            "target_b_stop_rejected_for_a": rejected_other_target,
            "target_a_ready": unaffected.status is CommitAssessmentStatus.READY,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_24(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    window, outcome = _deadline_outcome(scenario, suffix="case-24")
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="case-24:assessment",
    )
    output_ref = commit_payload_fingerprint(
        {"terminal": outcome.kind.value, "candidate_id": outcome.candidate_id},
        schema="pheroos-tck-terminal-output-v1",
        profile=scenario.profile,
    )
    certificate = issue_outcome_certificate(
        outcome,
        window,
        commit_policy=collective_commit_policy(scenario.policy),
        output_payload_fingerprint=output_ref,
        certificate_id=f"outcome-certificate:{scenario.namespace}:fallback",
        context=scenario.context,
        assessment=assessment,
        issuer_id="governance:tck:outcome-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=outcome.current_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:outcome-certificate",
        trace_event_id=f"trace:{scenario.namespace}:outcome-certificate",
    )
    payload = outcome_certificate_payload(certificate)
    accepted_as_commit = verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations={},
    )
    return _result(
        metrics={
            "outcome_certificate_leaf_count": len(tuple(_scalar_leaf_paths(payload)))
        },
        roots={
            "outcome_certificate_root": certificate.certificate_root,
            "output_payload_fingerprint": output_ref,
        },
        outcome={
            "terminal_kind": outcome.kind.value,
            "accepted_as_commit_certificate": accepted_as_commit,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={
            "kind": "outcome",
            "schema_discriminator": certificate.schema_discriminator,
        },
        failure_code="certificate_kind_mismatch",
    )


def _probe_case_25(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-25")
    portable = build_reference_portable_commit(stable, variant="case-25")
    payload = deepcopy(evidence_commit_certificate_payload(portable.certificate))
    certificate_mutation = vector.inputs.get("certificate_mutation_path")
    if not isinstance(certificate_mutation, list):
        raise ValueError("case 25 certificate_mutation_path must be an array")
    if certificate_mutation:
        _mutate_path(payload, certificate_mutation)
    certificate_valid = verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
    )

    event = _risk_trace_event(scenario)
    trace_mutation = vector.inputs.get("trace_mutation_path")
    if not isinstance(trace_mutation, list):
        raise ValueError("case 25 trace_mutation_path must be an array")
    trace_valid = True
    if trace_mutation:
        lineage = deepcopy(event.lineage)
        _mutate_path(lineage, trace_mutation)
        forged = replace(event, lineage=lineage)
        try:
            forged.validate()
        except (ValueError, TypeError):
            trace_valid = False
    else:
        event.validate()
    certificate_ref = evidence_commit_certificate_fingerprint(portable.certificate)
    return _result(
        metrics={
            "certificate_scalar_leaf_count": len(
                tuple(
                    _scalar_leaf_paths(
                        evidence_commit_certificate_payload(portable.certificate)
                    )
                )
            ),
            "trace_scalar_leaf_count": len(tuple(_scalar_leaf_paths(event.lineage))),
        },
        roots={
            "certificate_ref": certificate_ref,
            "certificate_body_root": portable.certificate.certificate_body_root,
            "certificate_root": portable.certificate.certificate_root,
            "trace_event_id": event.lineage["event_id"],
        },
        outcome={
            "certificate_valid": certificate_valid,
            "trace_valid": trace_valid,
            "certificate_mutated": bool(certificate_mutation),
            "trace_mutated": bool(trace_mutation),
        },
        trace_sequence=([event.event_type] if trace_valid else []),
        certificate={
            "kind": "evidence_commit",
            "verified": certificate_valid,
            "ref": certificate_ref,
        },
        failure_code=(
            "certificate_leaf_mutation"
            if certificate_mutation and not certificate_valid
            else "trace_leaf_mutation"
            if trace_mutation and not trace_valid
            else None
        ),
    )


def _probe_case_26(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-26")
    portable = build_reference_portable_commit(stable, variant="case-26")
    nonce = f"nonce:cross-scope:{scenario.namespace}"
    first = ReplayReceipt(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"observation:{scenario.namespace}:scope-a",
        nonce=nonce,
        payload_fingerprint=reference_fingerprint(f"scope-a:{scenario.namespace}"),
        target=scenario.target,
        candidate_id=scenario.leader_id,
        epoch=scenario.epoch,
        principal_id=scenario.principals[0].principal_id,
    )
    second = ReplayReceipt(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"observation:{scenario.namespace}:scope-b",
        nonce=nonce,
        payload_fingerprint=reference_fingerprint(f"scope-b:{scenario.namespace}"),
        target="decision:other",
        candidate_id=scenario.other_id,
        epoch=scenario.epoch + 1,
        principal_id=scenario.principals[0].principal_id,
    )
    replay = record_commit_replay_receipts(
        scenario.replay_state,
        current_step=6,
        receipts=(first,),
    )
    replay_rejected = False
    try:
        record_commit_replay_receipts(replay, current_step=7, receipts=(second,))
    except (GovernanceError, ValueError):
        replay_rejected = True
    certificate_claim_rejected = not verify_evidence_commit_certificate(
        portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        expected_claim_fingerprint=reference_fingerprint("wrong-claim"),
    )
    certificate_output_rejected = not verify_evidence_commit_certificate(
        portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        expected_output_payload_fingerprint=reference_fingerprint("wrong-output"),
    )
    return _result(
        metrics={"replay_scope_count": 3},
        roots={
            "receipt_ref": local_commit_receipt_fingerprint(stable.receipt),
            "certificate_ref": evidence_commit_certificate_fingerprint(
                portable.certificate
            ),
        },
        outcome={
            "nonce_cross_scope_rejected": replay_rejected,
            "certificate_cross_candidate_rejected": certificate_claim_rejected,
            "certificate_cross_output_rejected": certificate_output_rejected,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={"kind": "evidence_commit", "verified": True},
        failure_code="cross_scope_replay_rejected",
    )
