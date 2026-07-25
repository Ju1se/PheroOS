"""Private Commit TCK reference probes 14 handlers."""

from __future__ import annotations

from typing import Any

from pheroos.conformance._commit_reference import (
    assess_reference_scenario,
    issue_reference_action_gates,
    issue_reference_lease,
    reference_fingerprint,
    rotate_reference_context,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_tck.models import (
    result as _result,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.commit import (
    CandidateCommitInput,
    commit_assessment_fingerprint,
)

from pheroos.governance.commit_state import (
    commit_window_state_fingerprint,
    restart_commit_window_epoch,
)

from pheroos.protocol.commit_models import CommitAction

from pheroos.conformance._commit_tck_reference.liveness import (
    _initialize_window,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _binding,
    _observation,
    _reference_scenario,
    _risk_trace_sequence,
)

from pheroos.conformance._commit_tck_reference.state import (
    advance_commit_window_state,
)

from pheroos.conformance._commit_tck_reference.timeline import (
    _epoch_threshold,
)


def _probe_case_14(vector: _CommitTckRequest) -> dict[str, Any]:
    # Gate failure.
    gate = _reference_scenario(vector, variant="gate-reset")
    gate_window = _initialize_window(gate)
    ready = assess_reference_scenario(gate, step=5, suffix="gate-ready")
    gate_window = advance_commit_window_state(
        gate_window,
        assessment=ready,
        commit_policy=gate.policy,
        threshold_snapshot=gate.threshold,
        current_step=5,
    )
    stop, permission = issue_reference_action_gates(
        gate.namespace,
        context=gate.context,
        action=CommitAction.COMMIT,
        blocked=True,
        current_step=6,
        expires_at_step=20,
        suffix="gate-blocked",
    )
    blocked = assess_reference_scenario(
        gate,
        step=6,
        suffix="gate-blocked",
        stop_resolution=stop,
        permission=permission,
    )
    gate_reset = advance_commit_window_state(
        gate_window,
        assessment=blocked,
        commit_policy=gate.policy,
        threshold_snapshot=gate.threshold,
        current_step=6,
    )

    # Leader change after an append-only evidence/support head rotation.
    leader = _reference_scenario(
        vector,
        variant="leader-reset",
        minimum_membership_size=4,
    )
    leader_window = _initialize_window(leader)
    alpha_leads = assess_reference_scenario(
        leader,
        step=5,
        suffix="alpha-leads",
    )
    leader_window = advance_commit_window_state(
        leader_window,
        assessment=alpha_leads,
        commit_policy=leader.policy,
        threshold_snapshot=leader.threshold,
        current_step=5,
    )
    beta_extra = tuple(
        _observation(
            leader,
            index=1_400 + index,
            principal_index=3,
            candidate_id=leader.other_id,
        )
        for index in range(1, 3)
    )
    beta_original = next(
        item for item in leader.candidate_inputs if item.candidate_id == leader.other_id
    )
    beta_positives = (*beta_original.positive_observations, *beta_extra)
    beta_binding = _binding(
        leader,
        candidate_id=leader.other_id,
        positives=beta_positives,
        variant="beta-expanded",
    )
    beta_expanded = CandidateCommitInput(
        candidate_id=leader.other_id,
        claim_fingerprint=leader.claims[leader.other_id],
        evidence_binding=beta_binding,
        positive_observations=beta_positives,
        counter_observations=(),
        dispositions=(),
        challenges=(leader.challenges[leader.other_id],),
    )
    leader_inputs = tuple(
        beta_expanded if item.candidate_id == leader.other_id else item
        for item in leader.candidate_inputs
    )
    beta_lease, beta_support_replay = issue_reference_lease(
        leader.namespace,
        index=1_403,
        principal=leader.principals[3],
        observation=beta_extra[0],
        candidate_id=leader.other_id,
        claim_fingerprint=leader.claims[leader.other_id],
        profile=leader.profile,
        assurance=leader.assurance,
        manifest_root=leader.manifest_root,
        commit_policy_root=leader.commit_policy_root,
        protocol_id=leader.protocol_id,
        run_id=leader.run_id,
        target=leader.target,
        epoch=leader.epoch,
        policy=leader.policy,
        membership_snapshot=leader.membership_snapshot,
        membership_state=leader.membership_state,
        replay_state=leader.support_replay_state,
        prior_leases=leader.leases,
        current_step=6,
    )
    leader_leases = (*leader.leases, beta_lease)
    (
        leader_context,
        leader_replay,
        beta_support_replay,
        leader_stop,
        leader_permission,
    ) = rotate_reference_context(
        leader,
        candidate_inputs=leader_inputs,
        leases=leader_leases,
        current_step=6,
        suffix="beta-leads",
        support_replay_state=beta_support_replay,
    )
    beta_leads = assess_reference_scenario(
        leader,
        step=6,
        suffix="beta-leads",
        candidate_inputs=leader_inputs,
        leases=leader_leases,
        context=leader_context,
        replay_state=leader_replay,
        support_replay_state=beta_support_replay,
        stop_resolution=leader_stop,
        permission=leader_permission,
    )
    leader_reset = advance_commit_window_state(
        leader_window,
        assessment=beta_leads,
        commit_policy=leader.policy,
        threshold_snapshot=leader.threshold,
        current_step=6,
    )

    # Step gap.
    gap = _reference_scenario(vector, variant="gap-reset")
    gap_window = _initialize_window(gap)
    gap_first = assess_reference_scenario(gap, step=5, suffix="gap-first")
    gap_window = advance_commit_window_state(
        gap_window,
        assessment=gap_first,
        commit_policy=gap.policy,
        threshold_snapshot=gap.threshold,
        current_step=5,
    )
    gap_next = assess_reference_scenario(gap, step=7, suffix="gap-next")
    gap_reset = advance_commit_window_state(
        gap_window,
        assessment=gap_next,
        commit_policy=gap.policy,
        threshold_snapshot=gap.threshold,
        current_step=7,
    )

    # Epoch transition.
    epoch = _reference_scenario(vector, variant="epoch-reset")
    epoch_window = _initialize_window(epoch)
    epoch_first = assess_reference_scenario(epoch, step=5, suffix="epoch-first")
    epoch_window = advance_commit_window_state(
        epoch_window,
        assessment=epoch_first,
        commit_policy=collective_commit_policy(epoch.policy),
        threshold_snapshot=epoch.threshold,
        current_step=5,
    )
    new_threshold = _epoch_threshold(epoch, epoch=epoch.epoch + 1, step=6)
    epoch_reset = restart_commit_window_epoch(
        epoch_window,
        new_epoch=epoch.epoch + 1,
        current_step=6,
        commit_policy=collective_commit_policy(epoch.policy),
        threshold_snapshot=new_threshold,
        membership_root=reference_fingerprint(
            f"membership:{epoch.namespace}:{epoch.epoch + 1}"
        ),
    )
    reasons = {
        "gate_failure": gate_reset.reset_reason,
        "leader_change": leader_reset.reset_reason,
        "step_gap": gap_reset.reset_reason,
        "epoch_change": epoch_reset.reset_reason,
    }
    reset_counts = {
        "gate_failure": gate_reset.window_count,
        "leader_change": leader_reset.window_count,
        "step_gap": gap_reset.window_count,
        "epoch_change": epoch_reset.window_count,
    }
    prior_assessments_not_retained = bool(
        gate_reset.ordered_assessment_refs == ()
        and leader_reset.ordered_assessment_refs
        == (commit_assessment_fingerprint(beta_leads),)
        and gap_reset.ordered_assessment_refs
        == (commit_assessment_fingerprint(gap_next),)
        and epoch_reset.ordered_assessment_refs == ()
    )
    return _result(
        metrics={
            "gate_window_count": gate_reset.window_count,
            "leader_window_count": leader_reset.window_count,
            "gap_window_count": gap_reset.window_count,
            "epoch_window_count": epoch_reset.window_count,
        },
        roots={
            "gate_window_ref": commit_window_state_fingerprint(gate_reset),
            "leader_window_ref": commit_window_state_fingerprint(leader_reset),
            "gap_window_ref": commit_window_state_fingerprint(gap_reset),
            "epoch_window_ref": commit_window_state_fingerprint(epoch_reset),
        },
        outcome={
            "reset_reasons": reasons,
            "all_reset": bool(
                reasons
                == {
                    "gate_failure": "gate_failure",
                    "leader_change": "leader_change",
                    "step_gap": "step_gap",
                    "epoch_change": "epoch_change",
                }
                and reset_counts
                == {
                    "gate_failure": 0,
                    "leader_change": 1,
                    "step_gap": 1,
                    "epoch_change": 0,
                }
                and prior_assessments_not_retained
            ),
            "prior_assessments_not_retained": (prior_assessments_not_retained),
            "deadlines_not_extended": epoch_reset.absolute_deadline_step
            == epoch_window.absolute_deadline_step,
        },
        trace_sequence=_risk_trace_sequence(gate),
    )
