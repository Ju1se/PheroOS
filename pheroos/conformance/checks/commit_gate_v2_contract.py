"""Public-only Conformance matrix for durable Commit Gate v2 authority."""

from __future__ import annotations

from dataclasses import replace
import json

from pheroos.conformance.checks._commit_gate_v2_adversarial_support import (
    run_commit_gate_v2_finality_integrity_matrix,
    run_commit_gate_v2_race_matrix,
    run_commit_gate_v2_seal_matrix,
)
from pheroos.conformance.checks._commit_gate_v2_context_support import (
    GATE_STEP_V2,
    advance_verification_only_v2,
    commit_gate_context_v2,
    issue_permission_v2,
    prepare_permission_v2,
    prepare_stop_v2,
    resolve_stop_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.commit_gate_v2 import (
    CommitPermissionRequestV2,
    CommitStopRequestV2,
    VerifiedCommitPermissionStateV2,
    VerifiedCommitStopStateV2,
    commit_permission_allows_v2,
    commit_permission_state_is_current_v2,
    commit_permission_stream_ref_v2,
    commit_stop_blocks_v2,
    commit_stop_state_is_current_v2,
    commit_stop_stream_ref_v2,
    rehydrate_commit_permission_state_v2,
    rehydrate_commit_stop_state_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-commit-gate-conformance-v2"
)
_CHECK_NAME = "commit_gate_v2_contract"


def run_governance_commit_gate_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run the active Store-backed Stop/Permission matrix without private APIs."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        if adapter.conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
            return CheckResult(_CHECK_NAME, False, "adapter_version")
        if type(adapter.implementation_id) is not str or not adapter.implementation_id:
            return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME, False, f"adapter_exception:{type(exc).__name__}"
        )

    problems: list[str] = []
    try:
        _vertical_restart_exact_retry(adapter, problems)
        _principal_verification_toctou(adapter, problems)
        _conflict_and_source_authority(adapter, problems)
        problems.extend(run_commit_gate_v2_finality_integrity_matrix(adapter))
        problems.extend(run_commit_gate_v2_race_matrix(adapter))
        problems.extend(run_commit_gate_v2_seal_matrix(adapter))
    except Exception as exc:  # total boundary for independent Store adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _vertical_restart_exact_retry(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = commit_gate_context_v2(adapter, "vertical")
    stop, stop_source = prepare_stop_v2(context, "vertical", blocked=True)
    permission, permission_source = prepare_permission_v2(context, "vertical")
    stop_attempt = resolve_stop_v2(context, stop, stop_source)
    permission_attempt = issue_permission_v2(context, permission, permission_source)
    for label, request, attempt, event_type in (
        ("stop", stop, stop_attempt, "commit_stop_resolved_v2"),
        (
            "permission",
            permission,
            permission_attempt,
            "commit_permission_issued_v2",
        ),
    ):
        _validate_atomic_attempt(label, request, attempt, event_type, problems)

    stop_state = rehydrate_commit_stop_state_v2(
        json.loads(stop.canonical_bytes()),
        domain=context.domain,
        state_reader=context.store,
    )
    permission_state = rehydrate_commit_permission_state_v2(
        permission.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    if (
        type(stop_state) is not VerifiedCommitStopStateV2
        or stop_state.position is not GovernanceCommitPositionV2.CURRENT
        or not commit_stop_state_is_current_v2(stop_state)
        or not commit_stop_blocks_v2(stop_state, current_step=GATE_STEP_V2)
    ):
        problems.append("stop_restartable_currentness")
    if (
        type(permission_state) is not VerifiedCommitPermissionStateV2
        or permission_state.position is not GovernanceCommitPositionV2.CURRENT
        or not commit_permission_state_is_current_v2(permission_state)
        or not commit_permission_allows_v2(
            permission_state,
            current_step=GATE_STEP_V2,
            candidate_ref=permission.snapshot.candidate_refs[0],
        )
        or commit_permission_allows_v2(
            permission_state,
            current_step=permission.snapshot.expires_at_step,
            candidate_ref=permission.snapshot.candidate_refs[0],
        )
    ):
        problems.append("permission_restartable_currentness")
    if stop.stream_ref != commit_stop_stream_ref_v2(
        context.domain.scope_ref,
        context.manifest.id,
        stop.run_ref,
        stop.target_ref,
    ) or permission.stream_ref != commit_permission_stream_ref_v2(
        context.domain.scope_ref,
        context.manifest.id,
        permission.run_ref,
        permission.target_ref,
    ):
        problems.append("fixed_stream_identity")

    restarted_store = adapter.restart_store_v2(context.store)
    restarted = replace(context, store=restarted_store)
    retry = issue_permission_v2(restarted, permission, None)
    if (
        retry.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or retry.committed_transition is None
        or permission_attempt.committed_transition is None
        or retry.committed_transition.receipt.receipt_root
        != permission_attempt.committed_transition.receipt.receipt_root
    ):
        problems.append("lost_response_exact_retry_after_restart")
    try:
        rehydrated = rehydrate_commit_permission_state_v2(
            permission.to_dict(),
            domain=context.domain,
            state_reader=restarted_store,
        )
        if not commit_permission_state_is_current_v2(rehydrated):
            problems.append("restart_rehydrate")
    except Exception:
        problems.append("restart_rehydrate")


def _validate_atomic_attempt(
    label: str,
    request: CommitStopRequestV2 | CommitPermissionRequestV2,
    attempt: GovernanceCommitAttemptV2,
    event_type: str,
    problems: list[str],
) -> None:
    if (
        attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or attempt.committed_transition is None
    ):
        problems.append(f"{label}_genesis_commit")
        return
    batch = attempt.committed_transition.batch
    if len(batch.read_set.entries) != 8:
        problems.append(f"{label}_eight_entry_read_set")
    events = batch.trace_batch.events
    if (
        len(events) != 1
        or events[0].event_type != event_type
        or events[0].lineage.get("request_root") != request.request_root
        or events[0].lineage.get("read_set_root") != batch.read_set.root()
    ):
        problems.append(f"{label}_atomic_trace")


def _principal_verification_toctou(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = commit_gate_context_v2(adapter, "verification-toctou")
    request, source = prepare_permission_v2(context, "verification-toctou")
    advanced = advance_verification_only_v2(context, "verification-toctou")
    stale = issue_permission_v2(context, request, source)
    if advanced.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("verification_toctou_setup")
    if (
        stale.disposition is not GovernanceCommitDispositionV2.RETRY_REQUIRED
        or stale.failure is None
        or stale.failure.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
        or context.store.load_head_v2(request.scope_ref, request.stream_ref).revision
        != 0
    ):
        problems.append("verification_toctou_not_closed")


def _conflict_and_source_authority(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = commit_gate_context_v2(adapter, "conflict")
    winner, winner_source = prepare_stop_v2(context, "winner")
    loser, loser_source = prepare_stop_v2(context, "loser", blocked=True)
    accepted = resolve_stop_v2(context, winner, winner_source)
    stale = resolve_stop_v2(context, loser, loser_source)
    if accepted.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("conflicting_winner")
    if (
        stale.disposition is not GovernanceCommitDispositionV2.RETRY_REQUIRED
        or stale.failure is None
        or stale.failure.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    ):
        problems.append("conflicting_genesis_retry")

    forged_context = commit_gate_context_v2(adapter, "forged-source")
    request, source = prepare_stop_v2(forged_context, "forged-source")
    del source
    forged = _SameShapeSource(request.snapshot.evaluation_context_root)
    rejected = resolve_stop_v2(forged_context, request, forged)
    if (
        rejected.disposition is not GovernanceCommitDispositionV2.INVALID
        or forged_context.store.load_head_v2(
            request.scope_ref, request.stream_ref
        ).revision
        != 0
    ):
        problems.append("portable_source_forgery")


class _SameShapeSource:
    def __init__(self, context_root: str) -> None:
        self.context_root = context_root


run_governance_commit_gate_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2",
    "run_governance_commit_gate_conformance_v2",
]
