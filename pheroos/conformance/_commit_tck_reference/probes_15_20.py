"""Private Commit TCK reference probes 15 20 handlers."""

from __future__ import annotations

from dataclasses import replace

from typing import Any

from pheroos.conformance._commit_reference import (
    assess_reference_scenario,
    build_reference_stable_commit,
    rotate_reference_context,
)

from pheroos.conformance._commit_tck.models import (
    result as _result,
    text_value as _text,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.commit import (
    CandidateCommitInput,
    commit_assessment_fingerprint,
    candidate_commit_metrics_payload,
)

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcomeKind,
    decision_outcome_fingerprint,
)

from pheroos.governance.risk import (
    commit_threshold_snapshot_fingerprint,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _initialize_window,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _binding,
    _observation,
    _reference_scenario,
    _require_vector_manifest,
    _risk_trace_sequence,
)

from pheroos.conformance._commit_tck_reference.state import (
    advance_commit_window_state,
)

from pheroos.conformance._commit_tck_reference.timeline import (
    _deadline_outcome,
    _heartbeat_to_deadline,
)


def _probe_case_15(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, variant="evidence-continuity")
    leader = next(
        item
        for item in scenario.candidate_inputs
        if item.candidate_id == scenario.leader_id
    )
    extra = _observation(
        scenario,
        index=1_501,
        principal_index=0,
        candidate_id=scenario.leader_id,
    )
    expanded_positives = (*leader.positive_observations, extra)
    expanded_binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=expanded_positives,
        variant="expanded-positive",
    )
    expanded_leader = CandidateCommitInput(
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        evidence_binding=expanded_binding,
        positive_observations=expanded_positives,
        counter_observations=(),
        dispositions=(),
        challenges=(scenario.challenges[scenario.leader_id],),
    )
    expanded_inputs = tuple(
        expanded_leader if item.candidate_id == scenario.leader_id else item
        for item in scenario.candidate_inputs
    )
    window = _initialize_window(scenario)
    first = assess_reference_scenario(
        scenario,
        step=5,
        suffix="two-positive",
    )
    window = advance_commit_window_state(
        window,
        assessment=first,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    context, replay, support_replay, stop, permission = rotate_reference_context(
        scenario,
        candidate_inputs=expanded_inputs,
        leases=scenario.leases,
        current_step=6,
        suffix="expanded-positive",
    )
    second = assess_reference_scenario(
        scenario,
        step=6,
        suffix="three-positive",
        candidate_inputs=expanded_inputs,
        context=context,
        replay_state=replay,
        support_replay_state=support_replay,
        stop_resolution=stop,
        permission=permission,
    )
    continued = advance_commit_window_state(
        window,
        assessment=second,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=6,
    )
    return _result(
        metrics={
            "first_window_count": window.window_count,
            "second_window_count": continued.window_count,
        },
        roots={
            "first_evidence_root": first.collective_evidence_root,
            "second_evidence_root": second.collective_evidence_root,
            "window_root": continued.window_root,
        },
        outcome={
            "evidence_root_changed": first.collective_evidence_root
            != second.collective_evidence_root,
            "leader_continuous": first.leader_candidate_id
            == second.leader_candidate_id,
            "window_continued": continued.window_count == window.window_count + 1,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_16(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, tie=True)
    assessment = assess_reference_scenario(scenario, step=5, suffix="tie")
    leaders = [
        item.candidate_id
        for item in assessment.candidate_metrics
        if item.net_evidence
        == max(metric.net_evidence for metric in assessment.candidate_metrics)
    ]
    return _result(
        metrics={
            "leader_margin": assessment.leader_margin,
            "top_candidate_count": len(leaders),
        },
        roots={"assessment_ref": commit_assessment_fingerprint(assessment)},
        outcome={
            "status": assessment.status.value,
            "unique_leader": assessment.unique_leader,
            "leader_candidate_id": assessment.leader_candidate_id,
            "lexical_tie_break_used": bool(assessment.leader_candidate_id),
        },
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="non_unique_argmax",
    )


def _probe_case_17(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    order = vector.inputs.get("candidate_order")
    if not isinstance(order, list) or sorted(order) != [0, 1]:
        raise ValueError("case 17 candidate_order must be a two-item permutation")
    candidates = tuple(scenario.candidate_inputs[index] for index in order)
    leases = scenario.leases if order == [0, 1] else tuple(reversed(scenario.leases))
    normalized_candidates = tuple(
        replace(
            item,
            positive_observations=tuple(reversed(item.positive_observations)),
            challenges=tuple(reversed(item.challenges)),
        )
        for item in candidates
    )
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="permutation",
        candidate_inputs=normalized_candidates,
        leases=leases,
    )
    metrics = [
        candidate_commit_metrics_payload(item) for item in assessment.candidate_metrics
    ]
    return _result(
        metrics={
            "candidate_metrics": metrics,
            "leader_margin": assessment.leader_margin,
        },
        roots={
            "assessment_ref": commit_assessment_fingerprint(assessment),
            "evidence_root": assessment.collective_evidence_root,
            "challenge_root": assessment.collective_challenge_root,
            "lease_root": assessment.collective_lease_root,
        },
        outcome={
            "status": assessment.status.value,
            "leader_candidate_id": assessment.leader_candidate_id,
            "unique_leader": assessment.unique_leader,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_18(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-18")
    progress, terminal = _heartbeat_to_deadline(
        stable,
        suffix="case-18",
        final_status=CommitFinalityStatus.PENDING,
    )
    return _result(
        metrics={
            "pending_step": progress.current_step,
            "deadline_step": terminal.current_step,
        },
        roots={
            "window_root": stable.window.window_root,
            "terminal_outcome_ref": decision_outcome_fingerprint(terminal),
        },
        progress={
            "phase": progress.phase.value,
            "terminal": progress.terminal,
            "sealed_window": progress.sealed_window,
        },
        outcome={
            "kind": terminal.kind.value,
            "terminal": terminal.terminal,
            "deadline_reached": terminal.current_step
            >= min(
                terminal.absolute_deadline_step,
                terminal.absolute_run_deadline_step,
            ),
            "authoritative_commit": terminal.authoritative_commit,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_19(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    window, terminal = _deadline_outcome(scenario, suffix="case-19")
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="case-19:assessment",
    )
    leader = next(
        item
        for item in assessment.candidate_metrics
        if item.candidate_id == assessment.leader_candidate_id
    )
    return _result(
        metrics={
            "positive_evidence": leader.positive_evidence,
            "minimum_positive_evidence": scenario.threshold.minimum_positive_evidence,
            "window_count": window.window_count,
        },
        roots={
            "threshold_root": commit_threshold_snapshot_fingerprint(scenario.threshold),
            "outcome_threshold_root": terminal.threshold_root,
        },
        outcome={
            "kind": terminal.kind.value,
            "authoritative_commit": terminal.authoritative_commit,
            "threshold_lowered": terminal.threshold_root
            != commit_threshold_snapshot_fingerprint(scenario.threshold),
            "failed_gate_became_commit": terminal.kind
            is DecisionOutcomeKind.EVIDENCE_COMMIT,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_20(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest = _require_vector_manifest(vector)
    deadline_kind = _text(
        manifest["protocol"]["collective_commit_policy"]["terminal_outcome"][
            "deadline_outcome"
        ],
        "case 20 deadline outcome",
    )
    scenario = _reference_scenario(
        vector,
        variant=f"deadline-{deadline_kind}",
    )
    _, terminal = _deadline_outcome(scenario, suffix=f"case-20:{deadline_kind}")
    return _result(
        metrics={"deadline_step": terminal.current_step},
        roots={"outcome_ref": decision_outcome_fingerprint(terminal)},
        outcome={
            "declared_deadline_outcome": deadline_kind,
            "kind": terminal.kind.value,
            "candidate_id": terminal.candidate_id,
            "authoritative_commit": terminal.authoritative_commit,
            "epistemically_committed": terminal.epistemically_committed,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )
