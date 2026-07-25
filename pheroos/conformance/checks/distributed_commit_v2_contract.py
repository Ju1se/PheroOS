"""Public-only dual-StateStore Conformance for durable Distributed Commit v2."""

from __future__ import annotations

from copy import deepcopy

from pheroos.conformance.checks._distributed_v2_context_support import capability_v2
from pheroos.conformance.checks._distributed_v2_vertical_support import (
    DistributedV2ConflictVertical,
    DistributedV2Vertical,
    advance_conflict_decision_v2,
    build_verified_distributed_vertical_v2,
    freeze_external_witness_conflict_v2,
    verified_finality_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.commit_finality_v2 import VerifiedCommitFinalityInputV2
from pheroos.governance.commit_decision_v2 import CommitDecisionOutcomeKindV2
from pheroos.governance.distributed_commit_v2 import (
    DistributedAdvanceRequestV2,
    DistributedLaneStatusV2,
    DistributedLaneV2,
    DistributedMutationKindV2,
    DistributedWitnessConflictObservationV2,
    DistributedWitnessStateV2,
    VerifiedDistributedCertificateStateV2,
    VerifiedDistributedEpochStateV2,
    VerifiedDistributedProposalStateV2,
    VerifiedDistributedWitnessStateV2,
    advance_distributed_commit_v2,
    distributed_lane_stream_ref_v2,
    distributed_state_is_current_v2,
    open_distributed_authority_session_v2,
    rehydrate_distributed_state_v2,
)


GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-distributed-commit-conformance-v2"
)
_CHECK_NAME = "distributed_commit_v2_contract"


def run_governance_distributed_commit_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run the complete verified four-lane Store/restart matrix."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        if adapter.conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
            return CheckResult(_CHECK_NAME, False, "adapter_version")
        implementation_id = adapter.implementation_id
        if (
            type(implementation_id) is not str
            or not implementation_id
            or implementation_id != implementation_id.strip()
        ):
            return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME,
            False,
            f"adapter_exception:{type(exc).__name__}:{exc}",
        )
    problems: list[str] = []
    try:
        vertical = build_verified_distributed_vertical_v2(
            adapter,
            f"matrix:{implementation_id}",
        )
        _evaluate_verified_vertical_v2(vertical, problems)
        _evaluate_restart_v2(adapter, vertical, problems)
        _evaluate_portable_tamper_v2(vertical, problems)
        conflict = freeze_external_witness_conflict_v2(
            vertical, f"matrix:{implementation_id}"
        )
        _evaluate_conflict_vertical_v2(adapter, conflict, problems)
    except Exception as exc:  # total boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _evaluate_verified_vertical_v2(
    vertical: DistributedV2Vertical,
    problems: list[str],
) -> None:
    states = (
        (DistributedLaneV2.EPOCH, vertical.epoch, DistributedLaneStatusV2.ACTIVE),
        (
            DistributedLaneV2.PROPOSAL,
            vertical.proposal,
            DistributedLaneStatusV2.ACTIVE,
        ),
        (
            DistributedLaneV2.WITNESS,
            vertical.witness,
            DistributedLaneStatusV2.ACTIVE,
        ),
        (
            DistributedLaneV2.CERTIFICATE,
            vertical.certificate,
            DistributedLaneStatusV2.VERIFIED,
        ),
    )
    for lane, state, status in states:
        snapshot = state.snapshot
        expected_stream = distributed_lane_stream_ref_v2(
            snapshot.scope_ref,
            snapshot.protocol_ref,
            snapshot.run_ref,
            snapshot.target_ref,
            lane,
        )
        if (
            snapshot.lane is not lane
            or snapshot.stream_ref != expected_stream
            or snapshot.status is not status
            or snapshot.revision != 1
            or not distributed_state_is_current_v2(state)
        ):
            problems.append(f"lane_currentness:{lane.value}")
    if len({state.snapshot.stream_ref for _, state, _ in states}) != 4:
        problems.append("four_fixed_streams")
    expected_events = {
        "distributed_epoch_advanced_v2",
        "distributed_proposal_advanced_v2",
        "distributed_witness_advanced_v2",
        "distributed_certificate_advanced_v2",
    }
    observed_events: set[str] = set()
    for request in _requests(vertical):
        view = vertical.context.store.load_commit_view_v2(
            request.scope_ref,
            request.stream_ref,
            request.transition_id,
        )
        committed = view.committed_transition
        if committed is None:
            problems.append("committed_view_missing")
            continue
        observed_events.update(
            event.event_type for event in committed.batch.trace_batch.events
        )
    if observed_events != expected_events:
        problems.append("four_lane_trace")
    if type(verified_finality_v2(vertical)) is not VerifiedCommitFinalityInputV2:
        problems.append("verified_finality_handle")


def _evaluate_restart_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    vertical: DistributedV2Vertical,
    problems: list[str],
) -> None:
    restarted = adapter.restart_store_v2(vertical.context.store)
    if restarted is vertical.context.store:
        problems.append("restart_store_identity")
    expected_types = (
        VerifiedDistributedEpochStateV2,
        VerifiedDistributedProposalStateV2,
        VerifiedDistributedWitnessStateV2,
        VerifiedDistributedCertificateStateV2,
    )
    for request, expected_type in zip(_requests(vertical), expected_types, strict=True):
        state = rehydrate_distributed_state_v2(
            request.to_dict(),
            domain=vertical.context.domain,
            state_reader=restarted,
        )
        if type(state) is not expected_type or not distributed_state_is_current_v2(
            state
        ):
            problems.append(f"restart_rehydrate:{request.snapshot.lane.value}")


def _evaluate_portable_tamper_v2(
    vertical: DistributedV2Vertical,
    problems: list[str],
) -> None:
    payload = deepcopy(vertical.certificate_request.to_dict())
    payload["request_root"] = "sha256:" + "0" * 64
    try:
        rehydrate_distributed_state_v2(
            payload,
            domain=vertical.context.domain,
            state_reader=vertical.context.store,
        )
    except Exception:
        return
    problems.append("portable_request_tamper_accepted")


def _evaluate_conflict_vertical_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    conflict: DistributedV2ConflictVertical,
    problems: list[str],
) -> None:
    baseline = conflict.baseline
    snapshot = conflict.witness.snapshot
    state = snapshot.state
    if (
        snapshot.status is not DistributedLaneStatusV2.FROZEN
        or snapshot.mutation_kind is not DistributedMutationKindV2.EQUIVOCATION_FROZEN
        or snapshot.revision != 2
        or type(state) is not DistributedWitnessStateV2
        or len(state.witnesses) != 2
        or len(state.equivocations) != 1
        or state.equivocations[0].conflict_observation is None
        or state.equivocations[0].conflict_observation.observation_root
        != conflict.observation.observation_root
    ):
        problems.append("external_conflict_freeze")
    if (
        baseline.context.store.load_head_v2(
            baseline.proposal.snapshot.scope_ref, baseline.proposal.stream_ref
        ).revision
        != 1
        or baseline.context.store.load_head_v2(
            baseline.certificate.snapshot.scope_ref, baseline.certificate.stream_ref
        ).revision
        != 1
    ):
        problems.append("external_conflict_advanced_authority")
    view = baseline.context.store.load_commit_view_v2(
        conflict.witness_request.scope_ref,
        conflict.witness_request.stream_ref,
        conflict.witness_request.transition_id,
    )
    if view.committed_transition is None or tuple(
        item.event_type for item in view.committed_transition.batch.trace_batch.events
    ) != ("distributed_witness_conflict_v2",):
        problems.append("external_conflict_trace")
    retry = advance_distributed_commit_v2(
        conflict.witness_request,
        source=conflict.witness_source,
        authority_session=open_distributed_authority_session_v2(
            capability_v2(baseline.context, conflict.witness_request.observed_epoch),
            conflict.witness_request,
        ),
    )
    if (
        retry.committed_transition is None
        or view.committed_transition is None
        or retry.committed_transition.receipt.receipt_root
        != view.committed_transition.receipt.receipt_root
    ):
        problems.append("external_conflict_exact_retry")
    restarted = adapter.restart_store_v2(baseline.context.store)
    restored = rehydrate_distributed_state_v2(
        conflict.witness_request.to_dict(),
        domain=baseline.context.domain,
        state_reader=restarted,
    )
    restored_state = restored.snapshot.state
    if (
        type(restored) is not VerifiedDistributedWitnessStateV2
        or type(restored_state) is not DistributedWitnessStateV2
        or restored_state.equivocations[0].conflict_observation is None
    ):
        problems.append("external_conflict_restart")
    portable = DistributedWitnessConflictObservationV2.from_dict(
        conflict.observation.to_dict()
    )
    if portable.to_dict() != conflict.observation.to_dict():
        problems.append("external_conflict_portable_roundtrip")
    terminal = advance_conflict_decision_v2(
        conflict, f"matrix:{baseline.context.adapter.implementation_id}"
    ).snapshot
    if (
        terminal.outcome is None
        or terminal.outcome.kind is not CommitDecisionOutcomeKindV2.SAFETY_VIOLATION
    ):
        problems.append("external_conflict_decision_safety")


def _requests(
    vertical: DistributedV2Vertical,
) -> tuple[
    DistributedAdvanceRequestV2,
    DistributedAdvanceRequestV2,
    DistributedAdvanceRequestV2,
    DistributedAdvanceRequestV2,
]:
    return (
        vertical.epoch_request,
        vertical.proposal_request,
        vertical.witness_request,
        vertical.certificate_request,
    )


run_governance_distributed_commit_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2",
    "run_governance_distributed_commit_conformance_v2",
]
