"""Sealed and late-finality branch of the Commit Decision v2 reducer."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._commit_finality_v2 import (
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
)
from pheroos.governance._commit_decision_v2.common import _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    commit_decision_dependency_set_root_v2,
    commit_decision_frozen_dependency_root_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionMutationKindV2,
    CommitDecisionOutcomeKindV2,
    CommitDecisionPhaseV2,
)
from pheroos.governance._commit_decision_v2.gate_status import (
    CommitDecisionGateStatusV2,
)
from pheroos.governance._commit_decision_v2.reducer_support import (
    _gate_status_outcome,
    _progress,
    _successor,
    _terminal_outcome,
    _validate_finality_projection,
    _validate_seal_inclusion,
)
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.seal_inclusion import (
    CommitDecisionSealInclusionV2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2


def _evaluate_sealed_v2(
    request: CommitDecisionRequestV2,
    *,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    source_context_root: str,
    verified_finality: CommitFinalityProjectionV2 | None,
    verified_seal_inclusion: CommitDecisionSealInclusionV2 | None,
    current_gate_status: CommitDecisionGateStatusV2 | None,
) -> CommitDecisionSnapshotV2:
    seal = parent.seal
    assert seal is not None
    frozen = commit_decision_frozen_dependency_root_v2(dependencies)
    if current_gate_status is None or (
        current_gate_status.current_step != request.current_step
    ):
        raise ValueError("sealed commit evaluation requires same-step current gates")
    _validate_verified_finality_inputs(
        request,
        parent=parent,
        verified_finality=verified_finality,
        verified_seal_inclusion=verified_seal_inclusion,
    )
    priority = _same_step_terminal_priority(
        continuity_reason=_continuity_failure(request, parent, frozen),
        gate_status=current_gate_status,
        finality=verified_finality,
    )
    if priority is not None:
        kind, reasons = priority
        return _terminal(
            request,
            parent=parent,
            dependencies=dependencies,
            frozen=frozen,
            source_context_root=source_context_root,
            kind=kind,
            reasons=reasons,
            finality_root=(
                "" if verified_finality is None else verified_finality.projection_root
            ),
        )
    if parent.assurance is CommitAssurance.EVIDENCE_BOUND:
        return _evidence_bound_terminal(
            request,
            parent=parent,
            dependencies=dependencies,
            frozen=frozen,
            source_context_root=source_context_root,
            inclusion=verified_seal_inclusion,
        )
    if request.current_step >= parent.finality_deadline_step:
        deadline_reason = (
            "finality:verified_owner_handle_missing_at_deadline"
            if verified_finality is None
            else "finality:pending_at_deadline"
        )
        return _terminal(
            request,
            parent=parent,
            dependencies=dependencies,
            frozen=frozen,
            source_context_root=source_context_root,
            kind=CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE,
            reasons=(deadline_reason,),
            mutation=CommitDecisionMutationKindV2.DEADLINE_TERMINATED,
        )
    finality_kind = _external_finality_kind(verified_finality)
    if finality_kind is not None and verified_finality is not None:
        return _terminal(
            request,
            parent=parent,
            dependencies=dependencies,
            frozen=frozen,
            source_context_root=source_context_root,
            kind=finality_kind,
            reasons=(f"finality:{verified_finality.status.value}",),
            finality_root=verified_finality.projection_root,
        )
    return _pending_heartbeat(
        request,
        parent=parent,
        dependencies=dependencies,
        source_context_root=source_context_root,
        finality_handle_present=verified_finality is not None,
    )


def _validate_verified_finality_inputs(
    request: CommitDecisionRequestV2,
    *,
    parent: CommitDecisionSnapshotV2,
    verified_finality: CommitFinalityProjectionV2 | None,
    verified_seal_inclusion: CommitDecisionSealInclusionV2 | None,
) -> None:
    """Bind optional finality and seal inputs to the exact sealed parent."""

    portable_finality = request.finality_projection
    if (portable_finality is None) != (verified_finality is None) or (
        portable_finality is not None
        and verified_finality is not None
        and portable_finality.to_dict() != verified_finality.to_dict()
    ):
        raise ValueError("commit finality requires its exact verified owner projection")
    if (
        parent.assurance
        in {
            CommitAssurance.ADVISORY,
            CommitAssurance.EVIDENCE_BOUND,
        }
        and verified_finality is not None
    ):
        raise ValueError("commit assurance rejects external finality")
    if verified_seal_inclusion is not None:
        _validate_seal_inclusion(verified_seal_inclusion, parent)
    if verified_finality is None:
        return
    if verified_seal_inclusion is None:
        raise ValueError("commit finality requires verified seal inclusion")
    assert parent.seal is not None
    _validate_finality_projection(
        verified_finality,
        parent.seal,
        assurance=parent.assurance,
        seal_transition_id=verified_seal_inclusion.transition_id,
        step=request.current_step,
    )


def _same_step_terminal_priority(
    *,
    continuity_reason: str,
    gate_status: CommitDecisionGateStatusV2,
    finality: CommitFinalityProjectionV2 | None,
) -> tuple[CommitDecisionOutcomeKindV2, tuple[str, ...]] | None:
    """Normalize same-step facts before applying the declared priority."""

    gate_reasons = tuple(gate_status.reason_codes)
    invalid = tuple(
        reason
        for reason in ((continuity_reason,) + gate_reasons)
        if reason.startswith("invalid:")
    )
    if invalid:
        return CommitDecisionOutcomeKindV2.INVALID, invalid
    safety = tuple(reason for reason in gate_reasons if reason.startswith("safety:"))
    if finality is not None and finality.status is CommitFinalityStatusV2.CONFLICT:
        safety += ("finality:conflict",)
    if safety:
        return CommitDecisionOutcomeKindV2.SAFETY_VIOLATION, safety
    gate_kind = _gate_status_outcome(gate_status)
    if gate_kind is not None:
        return gate_kind, gate_reasons
    return None


def _continuity_failure(
    request: CommitDecisionRequestV2,
    parent: CommitDecisionSnapshotV2,
    frozen: str,
) -> str:
    assert parent.seal is not None
    if frozen != parent.seal.frozen_dependency_root:
        return "invalid:frozen_dependency_changed"
    if parent.assurance is not CommitAssurance.EVIDENCE_BOUND and (
        request.current_step != parent.current_step + 1
    ):
        return "invalid:heartbeat_step_gap"
    return ""


def _external_finality_kind(
    finality: CommitFinalityProjectionV2 | None,
) -> CommitDecisionOutcomeKindV2 | None:
    if finality is None or finality.status is CommitFinalityStatusV2.PENDING:
        return None
    if finality.status is CommitFinalityStatusV2.VERIFIED:
        return CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
    if finality.status is CommitFinalityStatusV2.UNAVAILABLE:
        return CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE
    return None


def _evidence_bound_terminal(
    request: CommitDecisionRequestV2,
    *,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    frozen: str,
    source_context_root: str,
    inclusion: CommitDecisionSealInclusionV2 | None,
) -> CommitDecisionSnapshotV2:
    seal = parent.seal
    assert seal is not None
    same_step = request.current_step == seal.sealed_at_step
    if not same_step:
        return _terminal(
            request,
            parent=parent,
            dependencies=dependencies,
            frozen=frozen,
            source_context_root=source_context_root,
            kind=CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE,
            reasons=("evidence_finality_not_same_step",),
        )
    if inclusion is None:
        raise ValueError("evidence finality requires verified seal inclusion")
    _validate_seal_inclusion(inclusion, parent, require_current_seal=True)
    finality_root = _root(
        "evidence-bound-finality",
        {
            "seal_root": seal.seal_root,
            "seal_transition_id": parent.transition_id,
            "seal_snapshot_root": parent.snapshot_root,
            "seal_receipt_root": inclusion.receipt_root,
            "seal_head_root": inclusion.head_root,
            "seal_inclusion_root": inclusion.inclusion_root,
            "step": request.current_step,
        },
    )
    return _terminal(
        request,
        parent=parent,
        dependencies=dependencies,
        frozen=frozen,
        source_context_root=source_context_root,
        kind=CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT,
        reasons=("evidence_finality_verified",),
        finality_root=finality_root,
    )


def _terminal(
    request: CommitDecisionRequestV2,
    *,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    frozen: str,
    source_context_root: str,
    kind: CommitDecisionOutcomeKindV2,
    reasons: Sequence[str],
    finality_root: str = "",
    mutation: CommitDecisionMutationKindV2 = CommitDecisionMutationKindV2.FINALIZED,
) -> CommitDecisionSnapshotV2:
    outcome = _terminal_outcome(
        kind,
        request.current_step,
        parent=parent,
        frozen_dependency_root=frozen,
        reason_codes=reasons,
        finality_root=finality_root,
    )
    return _successor(
        request,
        parent=parent,
        mutation=mutation,
        dependencies=dependencies,
        assessment=parent.assessment,
        window=parent.window,
        seal=parent.seal,
        progress=None,
        outcome=outcome,
        source_context_root=source_context_root,
    )


def _pending_heartbeat(
    request: CommitDecisionRequestV2,
    *,
    parent: CommitDecisionSnapshotV2,
    dependencies: Sequence[CommitDecisionDependencyV2],
    source_context_root: str,
    finality_handle_present: bool,
) -> CommitDecisionSnapshotV2:
    assert parent.seal is not None
    progress = _progress(
        parent=parent,
        phase=CommitDecisionPhaseV2.PROVISIONAL,
        current_step=request.current_step,
        evidence_deadline=parent.evidence_deadline_step,
        finality_deadline=parent.finality_deadline_step,
        assessment=parent.assessment,
        window=parent.window,
        seal=parent.seal,
        dependency_root=commit_decision_dependency_set_root_v2(dependencies),
        next_inputs=("finality",),
        unmet=(
            (
                "finality:pending"
                if finality_handle_present
                else "finality:verified_owner_handle_missing"
            ),
        ),
        heartbeat_sequence=(
            0 if parent.progress is None else parent.progress.heartbeat_sequence
        )
        + 1,
    )
    return _successor(
        request,
        parent=parent,
        mutation=CommitDecisionMutationKindV2.HEARTBEAT,
        dependencies=dependencies,
        assessment=parent.assessment,
        window=parent.window,
        seal=parent.seal,
        progress=progress,
        outcome=None,
        source_context_root=source_context_root,
    )


__all__: tuple[str, ...] = ()
