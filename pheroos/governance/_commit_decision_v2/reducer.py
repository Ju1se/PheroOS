"""Pure complete-replacement reducer for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CollectiveCommitPolicy

from pheroos.governance._commit_finality_v2 import CommitFinalityProjectionV2
from pheroos.governance._commit_decision_v2.assessment_records import CommitAssessmentV2
from pheroos.governance._commit_decision_v2.common import _saturating_future_step
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    commit_decision_dependency_set_root_v2,
    commit_decision_frozen_dependency_root_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionCommandV2,
    CommitDecisionDependencyRoleV2,
    CommitDecisionMutationKindV2,
    CommitDecisionOutcomeKindV2,
    CommitDecisionPhaseV2,
)
from pheroos.governance._commit_decision_v2.gate_status import (
    CommitDecisionGateStatusV2,
)
from pheroos.governance._commit_decision_v2.liveness_records import (
    CommitDecisionWindowV2,
)
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.seal_inclusion import (
    CommitDecisionSealInclusionV2,
)
from pheroos.governance._commit_decision_v2.reducer_support import (
    _deadline_outcome,
    _empty_window,
    _fallback_outcome,
    _genesis_snapshot,
    _progress,
    _reset_window,
    _successor,
    _terminal_outcome,
    _validate_parent_dependency,
    _validate_request_context,
)
from pheroos.governance._commit_decision_v2.sealed_reducer import (
    _evaluate_sealed_v2,
)
from pheroos.governance._commit_decision_v2.seal_reducer import (
    _seal_commit_decision_v2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_decision_v2.window_transition import (
    _advance_window_impl_v2,
)


def reduce_commit_decision_v2(
    request: CommitDecisionRequestV2,
    *,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    dependencies: Sequence[CommitDecisionDependencyV2],
    source_context_root: str,
    parent: CommitDecisionSnapshotV2 | None,
    assessment: CommitAssessmentV2 | None,
    required_stability_steps: int,
    verified_finality: CommitFinalityProjectionV2 | None = None,
    verified_seal_inclusion: CommitDecisionSealInclusionV2 | None = None,
    current_gate_status: CommitDecisionGateStatusV2 | None = None,
) -> CommitDecisionSnapshotV2:
    """Derive one full successor; the result is data until Store commits it."""

    if type(request) is not CommitDecisionRequestV2:
        raise TypeError("commit decision reducer requires an exact request v2")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("commit decision reducer requires an exact manifest v2")
    policy = manifest.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("commit decision manifest has no exact commit policy")
    if parent is not None and parent.outcome is not None:
        raise ValueError("commit decision terminal state is sticky")
    _validate_request_context(request, manifest, profile, parent)
    dependency_root = commit_decision_dependency_set_root_v2(dependencies)
    _validate_parent_dependency(parent, dependencies)
    if request.command is CommitDecisionCommandV2.INITIALIZE:
        return _initialize(
            request,
            manifest=manifest,
            profile=profile,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=source_context_root,
            required_stability_steps=required_stability_steps,
        )
    if parent is None:
        raise ValueError("commit decision successor requires a committed parent")
    if request.command is CommitDecisionCommandV2.EPOCH_RESTART:
        return _restart_epoch(
            request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=source_context_root,
            required_stability_steps=required_stability_steps,
        )
    if request.command is CommitDecisionCommandV2.EXPLICIT_UNSEAL:
        return _explicit_unseal(
            request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=source_context_root,
        )
    if request.command is CommitDecisionCommandV2.SEAL:
        return _seal_commit_decision_v2(
            request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=source_context_root,
            assessment=assessment,
        )
    return _evaluate(
        request,
        policy=policy,
        parent=parent,
        dependencies=dependencies,
        dependency_root=dependency_root,
        source_context_root=source_context_root,
        assessment=assessment,
        required_stability_steps=required_stability_steps,
        verified_finality=verified_finality,
        verified_seal_inclusion=verified_seal_inclusion,
        current_gate_status=current_gate_status,
    )


def _initialize(
    request: CommitDecisionRequestV2,
    *,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    dependencies: Sequence[CommitDecisionDependencyV2],
    dependency_root: str,
    source_context_root: str,
    required_stability_steps: int,
) -> CommitDecisionSnapshotV2:
    policy = manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    if {item.role for item in dependencies} != {CommitDecisionDependencyRoleV2.PARENT}:
        raise ValueError(
            "commit decision initialization binds only its parent dependency"
        )
    window = _empty_window(
        required_stability_steps,
        reset_budget=policy.commit_window.maximum_leader_resets,
        restart_budget=policy.commit_window.maximum_epoch_restarts,
        reason="initialized",
    )
    evidence_deadline = _saturating_future_step(
        request.current_step,
        policy.commit_window.deliberation_deadline_steps,
        "commit decision evidence deadline",
    )
    finality_deadline = _saturating_future_step(
        request.current_step,
        policy.commit_window.run_deadline_steps,
        "commit decision finality deadline",
    )
    if evidence_deadline > finality_deadline:
        raise ValueError("commit decision deadlines are not ordered")
    progress = _progress(
        parent=None,
        phase=CommitDecisionPhaseV2.SEARCH,
        current_step=request.current_step,
        evidence_deadline=evidence_deadline,
        finality_deadline=finality_deadline,
        window=window,
        dependency_root=dependency_root,
        next_inputs=(
            "commit_replay",
            "risk",
            "membership",
            "principal_verification",
            "support",
            "evidence",
            "commit_stop",
            "commit_permission",
        ),
        unmet=("evidence_dependencies",),
    )
    return _genesis_snapshot(
        request,
        manifest=manifest,
        profile=profile,
        epoch=request.observed_epoch,
        initialized_at=request.current_step,
        evidence_deadline=evidence_deadline,
        finality_deadline=finality_deadline,
        dependencies=dependencies,
        window=window,
        progress=progress,
        source_context_root=source_context_root,
    )


def _evaluate(
    request: CommitDecisionRequestV2,
    *,
    policy: CollectiveCommitPolicy,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    dependency_root: str,
    source_context_root: str,
    assessment: CommitAssessmentV2 | None,
    required_stability_steps: int,
    verified_finality: CommitFinalityProjectionV2 | None,
    verified_seal_inclusion: CommitDecisionSealInclusionV2 | None,
    current_gate_status: CommitDecisionGateStatusV2 | None,
) -> CommitDecisionSnapshotV2:
    if parent.seal is not None:
        return _evaluate_sealed_v2(
            request,
            parent=parent,
            dependencies=dependencies,
            source_context_root=source_context_root,
            verified_finality=verified_finality,
            verified_seal_inclusion=verified_seal_inclusion,
            current_gate_status=current_gate_status,
        )
    if assessment is None:
        return _missing_inputs_successor(
            request,
            policy=policy,
            parent=parent,
            dependencies=dependencies,
            dependency_root=dependency_root,
            source_context_root=source_context_root,
        )
    if assessment.current_step != request.current_step:
        raise ValueError("commit decision evaluation requires a same-step assessment")
    if assessment.dependency_set_root != dependency_root:
        raise ValueError("commit decision assessment dependencies are mismatched")
    window, mutation = _advance_window(
        parent,
        assessment,
        required_stability_steps=required_stability_steps,
        dependencies=dependencies,
    )
    outcome = _deadline_outcome(
        request.current_step,
        policy=policy,
        parent=parent,
        assessment=assessment,
        window=window,
        dependency_root=commit_decision_frozen_dependency_root_v2(dependencies),
        sealed=False,
    )
    progress = None
    if outcome is None:
        phase = (
            CommitDecisionPhaseV2.QUORUM_PENDING
            if assessment.leader_ready_for_stability
            else CommitDecisionPhaseV2.DELIBERATE
        )
        next_inputs = (
            ("seal",)
            if window.streak_count >= window.required_stability_steps
            else ("candidate_evidence",)
        )
        progress = _progress(
            parent=parent,
            phase=phase,
            current_step=request.current_step,
            evidence_deadline=parent.evidence_deadline_step,
            finality_deadline=parent.finality_deadline_step,
            assessment=assessment,
            window=window,
            dependency_root=dependency_root,
            next_inputs=next_inputs,
            unmet=assessment.reason_codes,
        )
    return _successor(
        request,
        parent=parent,
        mutation=CommitDecisionMutationKindV2.DEADLINE_TERMINATED
        if outcome
        else mutation,
        dependencies=dependencies,
        assessment=assessment,
        window=window,
        seal=None,
        progress=progress,
        outcome=outcome,
        source_context_root=source_context_root,
    )


def _missing_inputs_successor(
    request: CommitDecisionRequestV2,
    *,
    policy: CollectiveCommitPolicy,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    dependency_root: str,
    source_context_root: str,
) -> CommitDecisionSnapshotV2:
    missing = tuple(
        item.role.value
        for item in dependencies
        if item.role is not CommitDecisionDependencyRoleV2.PARENT and item.revision == 0
    )
    if not missing:
        raise ValueError("commit decision missing-input path has no missing dependency")
    outcome = None
    progress = None
    if request.current_step >= parent.evidence_deadline_step:
        outcome = _fallback_outcome(
            request.current_step,
            policy=policy,
            parent=parent,
            reason="evidence_dependencies_unavailable_at_deadline",
            dependencies=dependencies,
        )
    else:
        progress = _progress(
            parent=parent,
            phase=CommitDecisionPhaseV2.SEARCH,
            current_step=request.current_step,
            evidence_deadline=parent.evidence_deadline_step,
            finality_deadline=parent.finality_deadline_step,
            window=parent.window,
            dependency_root=dependency_root,
            next_inputs=missing,
            unmet=tuple(f"missing:{role}" for role in missing),
        )
    return _successor(
        request,
        parent=parent,
        mutation=(
            CommitDecisionMutationKindV2.DEADLINE_TERMINATED
            if outcome is not None
            else CommitDecisionMutationKindV2.HEARTBEAT
        ),
        dependencies=dependencies,
        assessment=None,
        window=parent.window,
        seal=None,
        progress=progress,
        outcome=outcome,
        source_context_root=source_context_root,
    )


def _restart_epoch(
    request: CommitDecisionRequestV2,
    *,
    policy: CollectiveCommitPolicy,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    dependency_root: str,
    source_context_root: str,
    required_stability_steps: int,
) -> CommitDecisionSnapshotV2:
    if parent.seal is not None or request.restart_epoch is None:
        raise ValueError("commit decision epoch restart is not available")
    if (
        request.observed_epoch != parent.epoch
        or request.restart_epoch != parent.epoch + 1
    ):
        raise ValueError("commit decision epoch restart is not contiguous")
    if parent.window.remaining_epoch_restart_budget == 0:
        outcome = None
        progress = None
        if request.current_step >= parent.evidence_deadline_step:
            outcome = _fallback_outcome(
                request.current_step,
                policy=policy,
                parent=parent,
                reason="epoch_restart_budget_exhausted",
                dependencies=dependencies,
            )
        else:
            progress = _progress(
                parent=parent,
                phase=CommitDecisionPhaseV2.DELIBERATE,
                current_step=request.current_step,
                evidence_deadline=parent.evidence_deadline_step,
                finality_deadline=parent.finality_deadline_step,
                window=parent.window,
                dependency_root=dependency_root,
                next_inputs=("candidate_evidence",),
                unmet=("epoch_restart_budget_exhausted",),
            )
        return _successor(
            request,
            parent=parent,
            mutation=(
                CommitDecisionMutationKindV2.DEADLINE_TERMINATED
                if outcome is not None
                else CommitDecisionMutationKindV2.WINDOW_RESET
            ),
            dependencies=dependencies,
            assessment=None,
            window=parent.window,
            seal=None,
            progress=progress,
            outcome=outcome,
            source_context_root=source_context_root,
        )
    window = _empty_window(
        required_stability_steps,
        reset_budget=parent.window.remaining_reset_budget,
        restart_budget=parent.window.remaining_epoch_restart_budget - 1,
        reason="epoch_restarted",
        reset_budget_exhausted=parent.window.reset_budget_exhausted,
    )
    progress = _progress(
        parent=parent,
        phase=CommitDecisionPhaseV2.SEARCH,
        current_step=request.current_step,
        evidence_deadline=parent.evidence_deadline_step,
        finality_deadline=parent.finality_deadline_step,
        window=window,
        dependency_root=dependency_root,
        next_inputs=("candidate_evidence",),
        unmet=("epoch_restarted",),
    )
    return _successor(
        request,
        parent=parent,
        mutation=CommitDecisionMutationKindV2.EPOCH_RESTARTED,
        dependencies=dependencies,
        assessment=None,
        window=window,
        seal=None,
        progress=progress,
        outcome=None,
        source_context_root=source_context_root,
        epoch=request.restart_epoch,
    )


def _explicit_unseal(
    request: CommitDecisionRequestV2,
    *,
    policy: CollectiveCommitPolicy,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    dependency_root: str,
    source_context_root: str,
) -> CommitDecisionSnapshotV2:
    if parent.seal is None:
        raise ValueError("commit decision explicit unseal requires a seal")
    if request.current_step >= parent.finality_deadline_step:
        outcome = _terminal_outcome(
            CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE,
            request.current_step,
            parent=parent,
            frozen_dependency_root=commit_decision_frozen_dependency_root_v2(
                dependencies
            ),
            reason_codes=("finality:deadline_reached",),
        )
        return _successor(
            request,
            parent=parent,
            mutation=CommitDecisionMutationKindV2.DEADLINE_TERMINATED,
            dependencies=dependencies,
            assessment=parent.assessment,
            window=parent.window,
            seal=parent.seal,
            progress=None,
            outcome=outcome,
            source_context_root=source_context_root,
        )
    window = _reset_window(
        parent.window,
        required=parent.window.required_stability_steps,
        reason="explicit_unseal",
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
        unmet=("explicit_unseal",),
    )
    return _successor(
        request,
        parent=parent,
        mutation=CommitDecisionMutationKindV2.WINDOW_RESET,
        dependencies=dependencies,
        assessment=None,
        window=window,
        seal=None,
        progress=progress,
        outcome=None,
        source_context_root=source_context_root,
    )


def _advance_window(
    parent: CommitDecisionSnapshotV2,
    assessment: CommitAssessmentV2,
    *,
    required_stability_steps: int,
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> tuple[CommitDecisionWindowV2, CommitDecisionMutationKindV2]:
    return _advance_window_impl_v2(
        parent,
        assessment,
        required_stability_steps=required_stability_steps,
        dependencies=dependencies,
        continuity=_window_semantics_continuous,
    )


def _window_semantics_continuous(
    parent: CommitDecisionSnapshotV2,
    assessment: CommitAssessmentV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> bool:
    """Preserve a ready streak across benign append-only dependency advances."""

    if (
        not parent.window.last_ready
        or not assessment.leader_ready_for_stability
        or assessment.current_step != parent.current_step + 1
        or assessment.leader_candidate_ref != parent.window.leader_candidate_ref
        or parent.assessment is None
        or not parent.assessment.stop_clear
        or not parent.assessment.permission_allowed
        or not assessment.stop_clear
        or not assessment.permission_allowed
        or assessment.replay_conflict_refs
        or assessment.equivocation_refs
    ):
        return False
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
        return False
    immutable_roles = {
        CommitDecisionDependencyRoleV2.RISK,
        CommitDecisionDependencyRoleV2.MEMBERSHIP,
        CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION,
    }
    old = {item.role: item.dependency_root for item in parent.dependencies}
    new = {item.role: item.dependency_root for item in dependencies}
    return all(
        role in old and role in new and old[role] == new[role]
        for role in immutable_roles
    )


__all__ = ("reduce_commit_decision_v2",)
