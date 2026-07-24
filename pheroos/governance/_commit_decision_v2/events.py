"""Canonical Trace events for one committed Decision v2 replacement."""

from __future__ import annotations

from collections.abc import Mapping

from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._commit_decision_v2.enums import CommitDecisionMutationKindV2
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2


def _commit_decision_events_v2(
    request: CommitDecisionRequestV2,
    snapshot: CommitDecisionSnapshotV2,
    session_binding: Mapping[str, object],
    *,
    parent_head_root: str,
    read_set_root: str,
) -> tuple[TraceEvent, ...]:
    base = _base_lineage(
        request,
        snapshot,
        session_binding,
        parent_head_root=parent_head_root,
        read_set_root=read_set_root,
    )
    events: list[TraceEvent] = []
    mutation = snapshot.mutation_kind
    if mutation is CommitDecisionMutationKindV2.INITIALIZED:
        events.append(_event("commit_decision_initialized_v2", request, base))
    if snapshot.assessment is not None and mutation in {
        CommitDecisionMutationKindV2.ASSESSED,
        CommitDecisionMutationKindV2.WINDOW_RESET,
    }:
        events.append(_event("commit_assessment_evaluated_v2", request, base))
    if mutation is CommitDecisionMutationKindV2.ASSESSED:
        events.append(_event("commit_window_advanced_v2", request, base))
    if mutation is CommitDecisionMutationKindV2.WINDOW_RESET:
        events.append(_event("commit_window_reset_v2", request, base))
    if mutation is CommitDecisionMutationKindV2.EPOCH_RESTARTED:
        events.append(_event("commit_epoch_restarted_v2", request, base))
    if mutation is CommitDecisionMutationKindV2.SEALED:
        events.append(_event("commit_window_sealed_v2", request, base))
    if snapshot.progress is not None:
        events.append(_event("commit_decision_progressed_v2", request, base))
    if snapshot.outcome is not None:
        events.append(_event("commit_decision_outcome_committed_v2", request, base))
    if not events:
        raise ValueError("commit decision mutation has no applicable Trace event")
    return tuple(events)


def _base_lineage(
    request: CommitDecisionRequestV2,
    snapshot: CommitDecisionSnapshotV2,
    session_binding: Mapping[str, object],
    *,
    parent_head_root: str,
    read_set_root: str,
) -> dict[str, object]:
    binding = _portable_projection(session_binding)
    if type(binding) is not dict:
        raise TypeError("commit decision session binding is invalid")
    lineage: dict[str, object] = {
        "domain_root": snapshot.domain_root,
        "scope_ref": snapshot.scope_ref,
        "stream_ref": snapshot.stream_ref,
        "transition_id": snapshot.transition_id,
        "request_root": request.request_root,
        "request_ref": request.mutation_ref,
        "observed_epoch": request.observed_epoch,
        "mutation_ref": snapshot.mutation_ref,
        "command": request.command.value,
        "mutation_kind": snapshot.mutation_kind.value,
        "revision": snapshot.revision,
        "parent_revision": snapshot.parent_revision,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "state_root": snapshot.state_root,
        "history_root": snapshot.history_root,
        "history_count": snapshot.history_count,
        "protocol_ref": snapshot.protocol_ref,
        "run_ref": snapshot.run_ref,
        "target_ref": snapshot.target_ref,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance.value,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "epoch": snapshot.epoch,
        "current_step": snapshot.current_step,
        "evidence_deadline_step": snapshot.evidence_deadline_step,
        "finality_deadline_step": snapshot.finality_deadline_step,
        "dependency_set_root": snapshot.dependency_set_root,
        "source_context_root": snapshot.source_context_root,
        "assessment_root": ""
        if snapshot.assessment is None
        else snapshot.assessment.assessment_root,
        "window_root": snapshot.window.window_root,
        "seal_root": "" if snapshot.seal is None else snapshot.seal.seal_root,
        "progress_root": ""
        if snapshot.progress is None
        else snapshot.progress.progress_root,
        "outcome_root": ""
        if snapshot.outcome is None
        else snapshot.outcome.outcome_root,
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": binding["operation"],
        "session_binding": binding,
        "read_set_root": read_set_root,
        "dependencies": [item.to_dict() for item in snapshot.dependencies],
    }
    return lineage


def _event(
    event_type: str,
    request: CommitDecisionRequestV2,
    lineage: Mapping[str, object],
) -> TraceEvent:
    return TraceEvent(
        event_type=event_type,
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="atomically advance durable Commit Decision v2 authority",
        lineage=dict(lineage),
    )


__all__: tuple[str, ...] = ()
