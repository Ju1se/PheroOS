"""Same-step seal transition for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.protocol.commit_models import CommitAssurance, CollectiveCommitPolicy

from pheroos.governance._commit_decision_v2.assessment_records import (
    CommitAssessmentV2,
    CommitCandidateMetricsV2,
)
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    commit_decision_frozen_dependency_root_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionDependencyRoleV2,
    CommitDecisionMutationKindV2,
    CommitDecisionPhaseV2,
)
from pheroos.governance._commit_decision_v2.liveness_records import (
    CommitDecisionWindowSealV2,
)
from pheroos.governance._commit_decision_v2.reducer_support import (
    _deadline_outcome,
    _progress,
    _reset_window,
    _successor,
)
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2


def _seal_commit_decision_v2(
    request: CommitDecisionRequestV2,
    *,
    policy: CollectiveCommitPolicy,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    dependency_root: str,
    source_context_root: str,
    assessment: CommitAssessmentV2 | None,
) -> CommitDecisionSnapshotV2:
    """Seal only after re-evaluating every gate at the seal step."""

    if assessment is None or assessment.current_step != request.current_step:
        raise ValueError("commit decision seal requires a same-step assessment")
    if assessment.dependency_set_root != dependency_root:
        raise ValueError("commit decision seal assessment dependencies are mismatched")
    frozen = commit_decision_frozen_dependency_root_v2(dependencies)
    if request.current_step >= parent.evidence_deadline_step:
        outcome = _deadline_outcome(
            request.current_step,
            policy=policy,
            parent=parent,
            assessment=assessment,
            window=parent.window,
            dependency_root=frozen,
            sealed=False,
        )
        assert outcome is not None
        return _successor(
            request,
            parent=parent,
            mutation=CommitDecisionMutationKindV2.DEADLINE_TERMINATED,
            dependencies=dependencies,
            assessment=assessment,
            window=parent.window,
            seal=None,
            progress=None,
            outcome=outcome,
            source_context_root=source_context_root,
        )
    output = request.output_proposal
    leader = _same_stable_leader(parent, assessment)
    ready = (
        leader is not None
        and request.current_step == parent.current_step
        and not parent.window.reset_budget_exhausted
        and parent.window.streak_count >= parent.window.required_stability_steps
        and _seal_dependencies_continuous(parent, dependencies)
    )
    if not ready or output is None:
        window = _reset_window(
            parent.window,
            required=parent.window.required_stability_steps,
            reason="seal_precondition_changed",
        )
        progress = _progress(
            parent=parent,
            phase=CommitDecisionPhaseV2.DELIBERATE,
            current_step=request.current_step,
            evidence_deadline=parent.evidence_deadline_step,
            finality_deadline=parent.finality_deadline_step,
            window=window,
            dependency_root=dependency_root,
            next_inputs=("candidate_evidence",),
            unmet=("seal_precondition_changed",),
        )
        return _successor(
            request,
            parent=parent,
            mutation=CommitDecisionMutationKindV2.WINDOW_RESET,
            dependencies=dependencies,
            assessment=assessment,
            window=window,
            seal=None,
            progress=progress,
            outcome=None,
            source_context_root=source_context_root,
        )
    assert leader is not None and output is not None
    if (
        output.candidate_ref != leader.candidate_ref
        or output.claim_root != leader.claim_root
    ):
        raise ValueError("commit decision output does not match the stable leader")
    seal = CommitDecisionWindowSealV2(
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        window_root=parent.window.window_root,
        frozen_dependency_root=frozen,
        sealed_at_step=request.current_step,
        candidate_ref=output.candidate_ref,
        claim_root=output.claim_root,
        output_contract_root=output.output_contract_root,
        output_payload_root=output.payload_root,
        output_payload=output.payload,
    )
    next_input = (
        "same_step_finalization"
        if parent.assurance is CommitAssurance.EVIDENCE_BOUND
        else "finality"
    )
    progress = _progress(
        parent=parent,
        phase=CommitDecisionPhaseV2.PROVISIONAL,
        current_step=request.current_step,
        evidence_deadline=parent.evidence_deadline_step,
        finality_deadline=parent.finality_deadline_step,
        assessment=assessment,
        window=parent.window,
        seal=seal,
        dependency_root=dependency_root,
        next_inputs=(next_input,),
        unmet=(next_input,),
    )
    return _successor(
        request,
        parent=parent,
        mutation=CommitDecisionMutationKindV2.SEALED,
        dependencies=dependencies,
        assessment=assessment,
        window=parent.window,
        seal=seal,
        progress=progress,
        outcome=None,
        source_context_root=source_context_root,
    )


def _same_stable_leader(
    parent: CommitDecisionSnapshotV2,
    assessment: CommitAssessmentV2,
) -> CommitCandidateMetricsV2 | None:
    if (
        parent.assessment is None
        or not assessment.leader_ready_for_stability
        or not assessment.stop_clear
        or not assessment.permission_allowed
        or assessment.replay_conflict_refs
        or assessment.equivocation_refs
        or assessment.leader_candidate_ref != parent.window.leader_candidate_ref
    ):
        return None
    previous = next(
        (
            item
            for item in parent.assessment.candidate_metrics
            if item.candidate_ref == parent.window.leader_candidate_ref
        ),
        None,
    )
    current = next(
        (
            item
            for item in assessment.candidate_metrics
            if item.candidate_ref == assessment.leader_candidate_ref
        ),
        None,
    )
    if previous is None or current is None or previous.claim_root != current.claim_root:
        return None
    return current


def _seal_dependencies_continuous(
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> bool:
    old = {item.role: item.dependency_root for item in parent.dependencies}
    new = {item.role: item.dependency_root for item in dependencies}
    return all(
        old.get(role) == new.get(role)
        for role in {
            CommitDecisionDependencyRoleV2.RISK,
            CommitDecisionDependencyRoleV2.MEMBERSHIP,
            CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION,
        }
    )


__all__: tuple[str, ...] = ()
