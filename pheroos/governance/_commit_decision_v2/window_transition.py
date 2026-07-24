"""Private window-transition implementation for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pheroos.governance._commit_decision_v2.assessment_records import (
    CommitAssessmentV2,
)
from pheroos.governance._commit_decision_v2.common import _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionMutationKindV2,
)
from pheroos.governance._commit_decision_v2.liveness_records import (
    CommitDecisionWindowV2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2


def _advance_window_impl_v2(
    parent: CommitDecisionSnapshotV2,
    assessment: CommitAssessmentV2,
    *,
    required_stability_steps: int,
    dependencies: Sequence[CommitDecisionDependencyV2],
    continuity: Callable[
        [
            CommitDecisionSnapshotV2,
            CommitAssessmentV2,
            Sequence[CommitDecisionDependencyV2],
        ],
        bool,
    ],
) -> tuple[CommitDecisionWindowV2, CommitDecisionMutationKindV2]:
    """Compute a window successor through the reducer-owned continuity rule."""

    required = max(parent.window.required_stability_steps, required_stability_steps)
    same = continuity(parent, assessment, dependencies)
    reset = parent.window.streak_count > 0 and not same
    exhausted = parent.window.reset_budget_exhausted
    remaining = parent.window.remaining_reset_budget
    if reset:
        if remaining == 0:
            exhausted = True
        else:
            remaining -= 1
    may_start = assessment.leader_ready_for_stability and not exhausted
    if same and may_start:
        streak = parent.window.streak_count + 1
        started = parent.window.streak_started_at_step
        leader = assessment.leader_candidate_ref
    elif may_start:
        streak = 1
        started = assessment.current_step
        leader = assessment.leader_candidate_ref
    else:
        streak, started, leader = 0, None, ""
    if exhausted:
        reason = "budget_exhausted:readiness_reset"
    elif same:
        reason = "advanced"
    elif reset:
        reason = "readiness_reset"
    else:
        reason = "assessed"
    rolling_streak = _root(
        "window-streak",
        {
            "parent": parent.window.rolling_streak_root,
            "assessment": assessment.assessment_root,
            "count": streak,
            "reason": reason,
        },
    )
    history = _root(
        "window-history",
        {
            "parent": parent.window.rolling_history_root,
            "assessment": assessment.assessment_root,
            "reason": reason,
        },
    )
    return (
        CommitDecisionWindowV2(
            required_stability_steps=required,
            streak_count=streak,
            streak_started_at_step=started,
            leader_candidate_ref=leader,
            last_ready=assessment.leader_ready_for_stability,
            last_assessment_root=assessment.assessment_root,
            rolling_streak_root=rolling_streak,
            rolling_history_root=history,
            reset_reason=reason,
            remaining_reset_budget=remaining,
            reset_budget_exhausted=exhausted,
            remaining_epoch_restart_budget=parent.window.remaining_epoch_restart_budget,
        ),
        CommitDecisionMutationKindV2.WINDOW_RESET
        if reset
        else CommitDecisionMutationKindV2.ASSESSED,
    )
