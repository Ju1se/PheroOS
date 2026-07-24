"""Shared terminal and continuity helpers for the Decision v2 reducer."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CommitAssurance, CollectiveCommitPolicy

from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
)
from pheroos.governance._commit_decision_v2.assessment_records import CommitAssessmentV2
from pheroos.governance._commit_decision_v2.common import _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    commit_decision_frozen_dependency_root_v2,
    dependency_by_role_v2,
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
    CommitDecisionOutcomeV2,
    CommitDecisionProgressV2,
    CommitDecisionWindowSealV2,
    CommitDecisionWindowV2,
)
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.seal_inclusion import (
    CommitDecisionSealInclusionV2,
)
from pheroos.governance._commit_decision_v2.snapshot import (
    COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2,
    COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_DECISION_GENESIS_TRANSITION_ID_V2,
    CommitDecisionSnapshotV2,
)


def _deadline_outcome(
    step: int,
    *,
    policy: CollectiveCommitPolicy,
    parent: CommitDecisionSnapshotV2,
    assessment: CommitAssessmentV2,
    window: CommitDecisionWindowV2,
    dependency_root: str,
    sealed: bool,
) -> CommitDecisionOutcomeV2 | None:
    if step < parent.evidence_deadline_step:
        return None
    global_reasons = tuple(assessment.reason_codes)
    candidate_reasons = tuple(
        reason for item in assessment.candidate_metrics for reason in item.reason_codes
    )
    reasons = global_reasons + candidate_reasons
    if (
        any(reason.startswith("invalid:") for reason in global_reasons)
        or assessment.replay_conflict_refs
    ):
        kind = CommitDecisionOutcomeKindV2.INVALID
    elif (
        any(reason.startswith("safety:") for reason in reasons)
        or assessment.equivocation_refs
    ):
        kind = CommitDecisionOutcomeKindV2.SAFETY_VIOLATION
    elif not assessment.stop_clear or not assessment.permission_allowed:
        kind = CommitDecisionOutcomeKindV2.BLOCKED
    elif sealed:
        kind = CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE
    else:
        kind = CommitDecisionOutcomeKindV2(policy.terminal_outcome.deadline_outcome)
    return CommitDecisionOutcomeV2(
        kind=kind,
        candidate_ref=(
            policy.terminal_outcome.safe_fallback_candidate
            if kind is CommitDecisionOutcomeKindV2.SAFE_FALLBACK
            else ""
        ),
        claim_root="",
        output_contract_root="",
        output_payload_root="",
        finality_root="",
        epistemically_committed=False,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
        reason_codes=tuple(reasons) or ("deadline_reached",),
        current_step=step,
        evidence_deadline_step=parent.evidence_deadline_step,
        finality_deadline_step=parent.finality_deadline_step,
        window_root=window.window_root,
        seal_root="",
        frozen_dependency_root=dependency_root,
    )


def _fallback_outcome(
    step: int,
    *,
    policy: CollectiveCommitPolicy,
    parent: CommitDecisionSnapshotV2,
    reason: str,
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> CommitDecisionOutcomeV2:
    kind = CommitDecisionOutcomeKindV2(policy.terminal_outcome.deadline_outcome)
    return CommitDecisionOutcomeV2(
        kind=kind,
        candidate_ref=(
            policy.terminal_outcome.safe_fallback_candidate
            if kind is CommitDecisionOutcomeKindV2.SAFE_FALLBACK
            else ""
        ),
        claim_root="",
        output_contract_root="",
        output_payload_root="",
        finality_root="",
        epistemically_committed=False,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
        reason_codes=(reason,),
        current_step=step,
        evidence_deadline_step=parent.evidence_deadline_step,
        finality_deadline_step=parent.finality_deadline_step,
        window_root=parent.window.window_root,
        seal_root="",
        frozen_dependency_root=commit_decision_frozen_dependency_root_v2(dependencies),
    )


def _terminal_outcome(
    kind: CommitDecisionOutcomeKindV2,
    step: int,
    *,
    parent: CommitDecisionSnapshotV2,
    frozen_dependency_root: str,
    reason_codes: Sequence[str],
    finality_root: str = "",
) -> CommitDecisionOutcomeV2:
    seal = parent.seal
    commit = kind is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
    return CommitDecisionOutcomeV2(
        kind=kind,
        candidate_ref=seal.candidate_ref if commit and seal else "",
        claim_root=seal.claim_root if commit and seal else "",
        output_contract_root=seal.output_contract_root if commit and seal else "",
        output_payload_root=seal.output_payload_root if commit and seal else "",
        finality_root=finality_root,
        epistemically_committed=commit,
        delivery_eligible=True,
        publication_eligible=False,
        execution_eligible=False,
        reason_codes=reason_codes,
        current_step=step,
        evidence_deadline_step=parent.evidence_deadline_step,
        finality_deadline_step=parent.finality_deadline_step,
        window_root=parent.window.window_root,
        seal_root="" if seal is None else seal.seal_root,
        frozen_dependency_root=frozen_dependency_root,
    )


def _gate_status_outcome(
    status: CommitDecisionGateStatusV2,
) -> CommitDecisionOutcomeKindV2 | None:
    reasons = tuple(status.reason_codes)
    if any(reason.startswith("invalid:") for reason in reasons):
        return CommitDecisionOutcomeKindV2.INVALID
    if any(reason.startswith("safety:") for reason in reasons):
        return CommitDecisionOutcomeKindV2.SAFETY_VIOLATION
    if not status.stop_clear or not status.permission_allowed:
        return CommitDecisionOutcomeKindV2.BLOCKED
    if not status.all_clear:
        return CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE
    return None


def _empty_window(
    required: int,
    *,
    reset_budget: int,
    restart_budget: int,
    reason: str,
    reset_budget_exhausted: bool = False,
) -> CommitDecisionWindowV2:
    return CommitDecisionWindowV2(
        required_stability_steps=required,
        streak_count=0,
        streak_started_at_step=None,
        leader_candidate_ref="",
        last_ready=False,
        last_assessment_root="",
        rolling_streak_root=_root("empty-streak", {"required": required}),
        rolling_history_root=_root("empty-window-history", {"required": required}),
        reset_reason=reason,
        remaining_reset_budget=reset_budget,
        reset_budget_exhausted=reset_budget_exhausted,
        remaining_epoch_restart_budget=restart_budget,
    )


def _reset_window(
    window: CommitDecisionWindowV2,
    *,
    required: int,
    reason: str,
) -> CommitDecisionWindowV2:
    exhausted = window.reset_budget_exhausted or window.remaining_reset_budget == 0
    effective_reason = f"budget_exhausted:{reason}" if exhausted else reason
    remaining = 0 if exhausted else window.remaining_reset_budget - 1
    return CommitDecisionWindowV2(
        required_stability_steps=max(required, window.required_stability_steps),
        streak_count=0,
        streak_started_at_step=None,
        leader_candidate_ref="",
        last_ready=False,
        last_assessment_root="",
        rolling_streak_root=_root(
            "reset-streak",
            {"parent": window.rolling_streak_root, "reason": effective_reason},
        ),
        rolling_history_root=_root(
            "reset-window-history",
            {"parent": window.rolling_history_root, "reason": effective_reason},
        ),
        reset_reason=effective_reason,
        remaining_reset_budget=remaining,
        reset_budget_exhausted=exhausted,
        remaining_epoch_restart_budget=window.remaining_epoch_restart_budget,
    )


def _genesis_snapshot(
    request: CommitDecisionRequestV2,
    *,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    epoch: int,
    initialized_at: int,
    evidence_deadline: int,
    finality_deadline: int,
    dependencies: Sequence[CommitDecisionDependencyV2],
    window: CommitDecisionWindowV2,
    progress: CommitDecisionProgressV2,
    source_context_root: str,
) -> CommitDecisionSnapshotV2:
    policy = manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return CommitDecisionSnapshotV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        protocol_ref=request.protocol_ref,
        run_ref=request.run_ref,
        target_ref=request.target_ref,
        profile=profile,
        assurance=CommitAssurance(policy.assurance),
        manifest_root=manifest.manifest_root,
        commit_policy_root=_commit_policy_root(manifest, profile),
        epoch=epoch,
        stream_ref=request.stream_ref,
        mutation_ref=request.mutation_ref,
        transition_id=request.transition_id,
        mutation_kind=CommitDecisionMutationKindV2.INITIALIZED,
        mutation_issuer_ref=request.mutation_issuer_ref,
        revision=1,
        parent_revision=0,
        parent_transition_id=COMMIT_DECISION_GENESIS_TRANSITION_ID_V2,
        parent_snapshot_root=COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2,
        initialized_at_step=initialized_at,
        current_step=request.current_step,
        evidence_deadline_step=evidence_deadline,
        finality_deadline_step=finality_deadline,
        parent_history_root=COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2,
        parent_history_count=0,
        history_root="",
        history_count=1,
        dependencies=dependencies,
        dependency_set_root="",
        assessment=None,
        window=window,
        seal=None,
        progress=progress,
        outcome=None,
        source_context_root=source_context_root,
    )


def _validate_request_context(
    request: CommitDecisionRequestV2,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    parent: CommitDecisionSnapshotV2 | None,
) -> None:
    from pheroos.governance._commit_gate_v2.source_common import (
        _validated_gate_context_v2,
    )

    context = _validated_gate_context_v2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        manifest=manifest,
        profile=profile,
        run_ref=request.run_ref,
        target_ref=request.target_ref,
        observed_epoch=request.observed_epoch,
        request_ref=request.mutation_ref,
        current_step=request.current_step,
        mutation_issuer_ref=request.mutation_issuer_ref,
    )
    if context.protocol_ref != request.protocol_ref:
        raise ValueError("commit decision protocol identity is mismatched")
    if parent is None:
        if request.command is not CommitDecisionCommandV2.INITIALIZE:
            raise ValueError("commit decision genesis command must initialize")
        return
    observed = (
        request.domain_root,
        request.scope_ref,
        request.protocol_ref,
        request.run_ref,
        request.target_ref,
        context.manifest_root,
        context.commit_policy_root,
        profile,
    )
    expected = (
        parent.domain_root,
        parent.scope_ref,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
        parent.manifest_root,
        parent.commit_policy_root,
        parent.profile,
    )
    if observed != expected or request.current_step < parent.current_step:
        raise ValueError("commit decision successor context is mismatched")
    if request.observed_epoch != parent.epoch:
        raise ValueError("commit decision epoch changed without restart")


def _validate_parent_dependency(
    parent: CommitDecisionSnapshotV2 | None,
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> None:
    dependency = dependency_by_role_v2(
        dependencies, CommitDecisionDependencyRoleV2.PARENT
    )
    if parent is None:
        expected = (
            0,
            COMMIT_DECISION_GENESIS_TRANSITION_ID_V2,
            COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2,
        )
    else:
        expected = (parent.revision, parent.transition_id, parent.snapshot_root)
    observed = (
        dependency.revision,
        dependency.transition_id,
        dependency.snapshot_root,
    )
    if observed != expected:
        raise ValueError("commit decision parent dependency is mismatched")


def _validate_finality_projection(
    projection: CommitFinalityProjectionV2,
    seal: CommitDecisionWindowSealV2,
    *,
    assurance: CommitAssurance,
    seal_transition_id: str,
    step: int,
) -> None:
    expected_owner = {
        CommitAssurance.CERTIFIED: CommitFinalityOwnerV2.CERTIFICATE,
        CommitAssurance.DISTRIBUTED: CommitFinalityOwnerV2.DISTRIBUTED,
    }.get(assurance)
    if (
        expected_owner is None
        or projection.owner is not expected_owner
        or projection.seal_transition_id != seal_transition_id
        or projection.seal_root != seal.seal_root
        or projection.frozen_dependency_root != seal.frozen_dependency_root
        or projection.verified_at_step != step
    ):
        raise ValueError("commit finality projection is cross-bound")


def _validate_seal_inclusion(
    inclusion: CommitDecisionSealInclusionV2,
    sealed_parent: CommitDecisionSnapshotV2,
    *,
    require_current_seal: bool = False,
) -> None:
    seal = sealed_parent.seal
    if seal is None or (
        inclusion.stream_ref != sealed_parent.stream_ref
        or inclusion.revision > sealed_parent.revision
        or inclusion.seal_root != seal.seal_root
        or inclusion.frozen_dependency_root != seal.frozen_dependency_root
        or (
            require_current_seal
            and (
                inclusion.revision != sealed_parent.revision
                or inclusion.transition_id != sealed_parent.transition_id
                or inclusion.snapshot_root != sealed_parent.snapshot_root
            )
        )
    ):
        raise ValueError("commit decision seal inclusion is cross-bound")


def _progress(
    *,
    parent: CommitDecisionSnapshotV2 | None,
    phase: CommitDecisionPhaseV2,
    current_step: int,
    evidence_deadline: int,
    finality_deadline: int,
    window: CommitDecisionWindowV2,
    dependency_root: str,
    next_inputs: Sequence[str],
    unmet: Sequence[str],
    assessment: CommitAssessmentV2 | None = None,
    seal: CommitDecisionWindowSealV2 | None = None,
    heartbeat_sequence: int = 0,
) -> CommitDecisionProgressV2:
    if type(phase) is not CommitDecisionPhaseV2:
        raise TypeError("commit decision progress phase is invalid")
    previous = (
        ""
        if parent is None or parent.progress is None
        else parent.progress.progress_root
    )
    return CommitDecisionProgressV2(
        phase=phase,
        current_step=current_step,
        evidence_deadline_step=evidence_deadline,
        finality_deadline_step=finality_deadline,
        assessment_root="" if assessment is None else assessment.assessment_root,
        window_root=window.window_root,
        seal_root="" if seal is None else seal.seal_root,
        dependency_set_root=dependency_root,
        heartbeat_sequence=heartbeat_sequence,
        previous_progress_root=previous,
        remaining_reset_budget=window.remaining_reset_budget,
        remaining_epoch_restart_budget=window.remaining_epoch_restart_budget,
        leader_candidate_ref=window.leader_candidate_ref,
        streak_count=window.streak_count,
        next_required_inputs=next_inputs,
        unmet_gates=unmet,
    )


def _successor(
    request: CommitDecisionRequestV2,
    *,
    parent: CommitDecisionSnapshotV2,
    mutation: CommitDecisionMutationKindV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    assessment: CommitAssessmentV2 | None,
    window: CommitDecisionWindowV2,
    seal: CommitDecisionWindowSealV2 | None,
    progress: CommitDecisionProgressV2 | None,
    outcome: CommitDecisionOutcomeV2 | None,
    source_context_root: str,
    epoch: int | None = None,
) -> CommitDecisionSnapshotV2:
    return CommitDecisionSnapshotV2(
        domain_root=parent.domain_root,
        scope_ref=parent.scope_ref,
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
        profile=parent.profile,
        assurance=parent.assurance,
        manifest_root=parent.manifest_root,
        commit_policy_root=parent.commit_policy_root,
        epoch=parent.epoch if epoch is None else epoch,
        stream_ref=request.stream_ref,
        mutation_ref=request.mutation_ref,
        transition_id=request.transition_id,
        mutation_kind=mutation,
        mutation_issuer_ref=request.mutation_issuer_ref,
        revision=parent.revision + 1,
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        initialized_at_step=parent.initialized_at_step,
        current_step=request.current_step,
        evidence_deadline_step=parent.evidence_deadline_step,
        finality_deadline_step=parent.finality_deadline_step,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        history_root="",
        history_count=parent.history_count + 1,
        dependencies=dependencies,
        dependency_set_root="",
        assessment=assessment,
        window=window,
        seal=seal,
        progress=progress,
        outcome=outcome,
        source_context_root=source_context_root,
    )


def _commit_policy_root(manifest: ScopedProtocolManifestV2, profile: str) -> str:
    from pheroos.protocol.commit_wire import commit_policy_fingerprint

    policy = manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return commit_policy_fingerprint(policy, profile=profile)


__all__: tuple[str, ...] = ()
