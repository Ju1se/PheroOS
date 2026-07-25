"""Private Commit TCK reference probes 08 13 handlers."""

from __future__ import annotations

from typing import Any

from pheroos.conformance._commit_reference import (
    assess_reference_scenario,
    build_reference_stable_commit,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_tck.models import (
    result as _result,
    text_value as _text,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.attention import evaluate_hybrid_attention_step

from pheroos.governance.candidate import Candidate, CandidateSet

from pheroos.governance.certificate import (
    local_commit_receipt_fingerprint,
)

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionProgress,
    commit_window_state_fingerprint,
    decision_outcome_fingerprint,
    reduce_commit_liveness,
)

from pheroos.governance.errors import GovernanceError

from pheroos.governance.hybrid_commit import (
    bind_hybrid_commit_channels,
    hybrid_attention_projection,
    hybrid_commit_truth_projection,
)

from pheroos.governance.support_lease import (
    evaluate_support_leases,
)

from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
)

from pheroos.protocol.manifest import capability_manifest_from_dict

from pheroos.protocol.validation import validate_capability_manifest

from pheroos.conformance._commit_tck_reference.authority import (
    _candidate_topology,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _initialize_window,
    _liveness_input,
    _local_commit_outcome,
    _verified_scout,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _reference_scenario,
    _require_vector_manifest,
    _risk_trace_sequence,
)

from pheroos.conformance._commit_tck_reference.state import (
    advance_commit_window_state,
)


def _probe_case_08(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, shared_cluster=True)
    evaluation = evaluate_support_leases(
        scenario.leases,
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.support_replay_state,
        commit_policy=collective_commit_policy(scenario.policy),
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    return _result(
        metrics={
            "equivocation_finding_count": len(evaluation.equivocation_findings),
            "active_support_cluster_count": evaluation.active_support_cluster_count,
            "excluded_lease_count": len(evaluation.excluded_lease_fingerprints),
        },
        roots={"lease_root": evaluation.lease_root},
        outcome={"equivocation_detected": bool(evaluation.equivocation_findings)},
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="support_equivocation",
    )


def _probe_case_09(vector: _CommitTckRequest) -> dict[str, Any]:
    manifest = capability_manifest_from_dict(_require_vector_manifest(vector))
    diagnostics = validate_capability_manifest(manifest)
    codes = sorted(item.code for item in diagnostics if item.level == "error")
    policy = manifest.protocol.collective_commit_policy
    assert policy is not None
    low = policy.risk_bands["LOW"]
    high = policy.risk_bands["HIGH"]
    monotonic = "commit_risk_monotonicity_invalid" not in codes
    return _result(
        metrics={
            "low_minimum_positive": low.minimum_positive_evidence,
            "high_minimum_positive": high.minimum_positive_evidence,
        },
        roots={
            "manifest_root": commit_manifest_fingerprint(
                manifest,
                profile=vector.profile,
            ),
        },
        outcome={
            "valid": not codes,
            "risk_transition_monotonic": monotonic,
            "diagnostic_codes": codes,
        },
        failure_code=(codes[0] if codes else None),
    )


def _probe_case_10(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, variant="original-heads")
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix="original-heads",
    )
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=collective_commit_policy(scenario.policy),
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    changed = _reference_scenario(vector, variant="changed-heads")
    changed_assessment = assess_reference_scenario(
        changed,
        step=5,
        suffix="changed-heads",
    )
    rejected = False
    try:
        advance_commit_window_state(
            window,
            assessment=changed_assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=changed.threshold,
            current_step=6,
        )
    except (GovernanceError, ValueError):
        rejected = True
    return _result(
        metrics={
            "original_window_count": window.window_count,
            "changed_risk_root": int(
                scenario.context.risk_assessment_fingerprint
                != changed.context.risk_assessment_fingerprint
            ),
            "changed_membership_root": int(
                scenario.context.membership_root != changed.context.membership_root
            ),
        },
        roots={
            "window_state_ref": commit_window_state_fingerprint(window),
            "original_risk_root": scenario.context.risk_assessment_fingerprint,
            "changed_risk_root": changed.context.risk_assessment_fingerprint,
            "original_membership_root": scenario.context.membership_root,
            "changed_membership_root": changed.context.membership_root,
        },
        outcome={"stale_window_reuse_rejected": rejected},
        trace_sequence=_risk_trace_sequence(scenario),
        failure_code="authority_head_changed" if rejected else None,
    )


def _probe_case_11(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    policy = scenario.manifest.protocol.collective_decision_policy
    if policy is None:
        raise ValueError("case 11 requires a declared Hybrid attention policy")
    assessment = assess_reference_scenario(scenario, step=5, suffix="hybrid-truth")
    attention_candidate = _text(
        vector.inputs.get("attention_candidate"),
        "case 11 attention_candidate",
    )
    candidates = CandidateSet(
        tuple(
            Candidate(item.id, item.target, item.safe_fallback)
            for item in scenario.manifest.protocol.candidates
        )
    )
    scouts = [
        _verified_scout(
            scenario,
            source_id=f"scout:{attention_candidate}:{index}",
            candidate_id=attention_candidate,
        )
        for index in range(1, 3)
    ]
    attention, directive = evaluate_hybrid_attention_step(
        protocol_id=scenario.protocol_id,
        candidate_set=candidates,
        policy=policy,
        target=scenario.target,
        current_step=5,
        scout_reports=scouts,
        topology=_candidate_topology(scenario),
        fallback_candidate_id=scenario.fallback_id,
    )
    bound = bind_hybrid_commit_channels(
        attention=attention,
        exploration_directive=directive,
        commit_assessment=assessment,
    )
    truth = hybrid_commit_truth_projection(bound)
    attention_projection = hybrid_attention_projection(bound)
    return _result(
        metrics={
            "leader_margin": bound.leader_margin,
            "attention_top_candidate": directive.candidate_order[0],
        },
        roots={
            "commit_truth_root": bound.commit_truth_root,
            "commit_evidence_root": bound.commit_evidence_root,
            "commit_challenge_root": bound.commit_challenge_root,
            "commit_lease_root": bound.commit_lease_root,
            "attention_root": bound.attention_fingerprint,
        },
        outcome={
            "commit_leader": bound.leader_candidate_id,
            "attention_commit_authority": bound.attention_commit_authority,
            "truth_projection": truth,
            "attention_projection": attention_projection,
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_12(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(scenario, step=5, suffix="single-step")
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=collective_commit_policy(scenario.policy),
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    decision = reduce_commit_liveness(
        window,
        commit_policy=collective_commit_policy(scenario.policy),
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=5,
            suffix="single-step",
            finality_status=CommitFinalityStatus.PENDING,
            next_required_inputs=("stability_window",),
        ),
    )
    if type(decision) is not DecisionProgress:
        raise ValueError("single-step readiness unexpectedly became terminal")
    return _result(
        metrics={
            "window_count": window.window_count,
            "required_stability_steps": window.minimum_stability_steps,
        },
        roots={
            "window_root": window.window_root,
            "progress_window_ref": decision.window_state_ref,
        },
        progress={
            "phase": decision.phase.value,
            "terminal": decision.terminal,
            "window_count": decision.window_count,
            "leader_candidate_id": decision.leader_candidate_id,
        },
        outcome=None,
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_13(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-13")
    outcome = _local_commit_outcome(stable, suffix="case-13")
    return _result(
        metrics={
            "window_count": stable.window.window_count,
            "required_stability_steps": stable.window.minimum_stability_steps,
        },
        roots={
            "window_root": stable.window.window_root,
            "receipt_ref": local_commit_receipt_fingerprint(stable.receipt),
            "outcome_ref": decision_outcome_fingerprint(outcome),
        },
        progress=None,
        outcome={
            "kind": outcome.kind.value,
            "candidate_id": outcome.candidate_id,
            "authoritative_commit": outcome.authoritative_commit,
            "epistemically_committed": outcome.epistemically_committed,
        },
        trace_sequence=_risk_trace_sequence(scenario),
        certificate={
            "kind": "local_receipt",
            "ref": local_commit_receipt_fingerprint(stable.receipt),
        },
    )
