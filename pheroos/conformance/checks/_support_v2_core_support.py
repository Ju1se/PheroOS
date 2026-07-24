"""Public vertical and persistence lanes for Support v2 Conformance."""

from __future__ import annotations

from pheroos.conformance.checks._support_v2_context_support import (
    SupportV2ConformanceContext,
    SupportV2Upstreams,
    advance_support_v2,
    commit_upstreams_v2,
    context_v2,
    initialize_v2,
    issue_v2,
    rebind_store_v2,
    revoke_v2,
    support_state_v2,
    switch_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import root_v2
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.governance.support_v2 import (
    MembershipCommitRequestV2,
    PrincipalVerificationSetAdvanceRequestV2,
    SupportAdvanceRequestV2,
    SupportEvaluationV2,
    SupportLeaseStatusV2,
    evaluate_support_v2,
    rehydrate_membership_state_v2,
    rehydrate_principal_verification_set_state_v2,
    require_current_membership_state_v2,
    require_current_principal_verification_set_v2,
    require_current_support_state_v2,
    support_lease_status_v2,
)


def run_support_v2_core_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> list[str]:
    problems: list[str] = []
    try:
        _vertical_restart_and_evaluation(adapter, problems)
    except Exception as exc:
        problems.append(f"vertical_exception:{type(exc).__name__}:{exc}")
    return problems


def _vertical_restart_and_evaluation(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "vertical")
    upstreams = commit_upstreams_v2(context, label="vertical")
    _check_upstream_authority(context, upstreams, problems)

    initialized, initialize_source = initialize_v2(context, "vertical")
    initialized_attempt = advance_support_v2(
        context,
        initialized,
        initialize_source,
    )
    if not _committed(initialized_attempt):
        problems.append("initialize_not_committed")
        return
    initialized_state = support_state_v2(context, initialized)
    if require_current_support_state_v2(initialized_state) != initialized.snapshot:
        problems.append("initialize_current_projection")
    _check_trace_types(
        context,
        initialized,
        ("support_state_advanced",),
        "initialize_trace",
        problems,
    )

    claim_root = root_v2("claim:vertical")
    issued, issue_source = issue_v2(
        context,
        initialized_state,
        upstreams.membership_state,
        "vertical:issue",
        current_step=5,
        claim_root=claim_root,
    )
    issued_attempt = advance_support_v2(context, issued, issue_source)
    if not _committed(issued_attempt) or issued.issued_lease is None:
        problems.append("issue_not_committed")
        return
    issued_state = support_state_v2(context, issued)
    _check_trace_types(
        context,
        issued,
        ("support_state_advanced", "support_lease_issued_v2"),
        "issue_trace",
        problems,
    )
    evaluation = evaluate_support_v2(
        support_state=issued_state,
        membership_state=upstreams.membership_state,
        manifest=context.manifest,
        candidate_ref=issued.issued_lease.candidate_ref,
        claim_root=claim_root,
        epoch=upstreams.membership_request.snapshot.epoch,
        current_step=5,
    )
    if (
        type(evaluation) is not SupportEvaluationV2
        or tuple(evaluation.included_lease_roots) != (issued.issued_lease.lease_root,)
        or SupportEvaluationV2.from_dict(evaluation.to_dict()) != evaluation
    ):
        problems.append("public_evaluation")
    if (
        support_lease_status_v2(
            issued_state,
            issued.issued_lease.lease_root,
            current_step=5,
        )
        is not SupportLeaseStatusV2.ACTIVE
    ):
        problems.append("derived_lease_status")

    switched, switch_source = switch_v2(
        context,
        issued_state,
        upstreams.membership_state,
        issued.issued_lease.lease_root,
        "vertical:switch",
        current_step=6,
        claim_root=claim_root,
    )
    switched_attempt = advance_support_v2(context, switched, switch_source)
    if not _committed(switched_attempt) or switched.issued_lease is None:
        problems.append("switch_not_committed")
        return
    switched_state = support_state_v2(context, switched)
    _check_trace_types(
        context,
        switched,
        (
            "support_state_advanced",
            "support_lease_revoked_v2",
            "support_lease_issued_v2",
        ),
        "switch_trace",
        problems,
    )

    revoked, revoke_source = revoke_v2(
        context,
        switched_state,
        switched.issued_lease.lease_root,
        "vertical:revoke",
        current_step=7,
    )
    revoked_attempt = advance_support_v2(context, revoked, revoke_source)
    if not _committed(revoked_attempt):
        problems.append("revoke_not_committed")
        return
    _check_trace_types(
        context,
        revoked,
        ("support_state_advanced", "support_lease_revoked_v2"),
        "revoke_trace",
        problems,
    )
    if revoked.snapshot.leases or revoked.snapshot.history_count != 4:
        problems.append("revoke_projection_or_history")

    restarted = adapter.restart_store_v2(context.store)
    recovered_context = rebind_store_v2(context, restarted)
    recovered_verification = rehydrate_principal_verification_set_state_v2(
        upstreams.verification_request.to_dict(),
        domain=context.domain,
        state_reader=restarted,
    )
    recovered_membership = rehydrate_membership_state_v2(
        upstreams.membership_request.to_dict(),
        domain=context.domain,
        state_reader=restarted,
    )
    recovered_support = support_state_v2(recovered_context, revoked)
    if (
        require_current_principal_verification_set_v2(recovered_verification)
        != upstreams.verification_request.snapshot
        or require_current_membership_state_v2(recovered_membership)
        != upstreams.membership_request.snapshot
        or require_current_support_state_v2(recovered_support) != revoked.snapshot
    ):
        problems.append("restart_rehydrate")
    _check_canonical_wire(upstreams, revoked, problems)


def _check_upstream_authority(
    context: SupportV2ConformanceContext,
    upstreams: SupportV2Upstreams,
    problems: list[str],
) -> None:
    verification = upstreams.verification_request
    membership = upstreams.membership_request
    if (
        require_current_principal_verification_set_v2(upstreams.verification_state)
        != verification.snapshot
    ):
        problems.append("verification_current_projection")
    if (
        require_current_membership_state_v2(upstreams.membership_state)
        != membership.snapshot
    ):
        problems.append("membership_current_projection")
    for request, expected, label in (
        (verification, ("principal_verification_set_advanced",), "verification_trace"),
        (membership, ("membership_epoch_committed",), "membership_trace"),
    ):
        _check_trace_types(context, request, expected, label, problems)


def _check_trace_types(
    context: SupportV2ConformanceContext,
    request: (
        PrincipalVerificationSetAdvanceRequestV2
        | MembershipCommitRequestV2
        | SupportAdvanceRequestV2
    ),
    expected: tuple[str, ...],
    label: str,
    problems: list[str],
) -> None:
    view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    if view.committed_transition is None:
        problems.append(f"{label}_missing_commit")
        return
    observed = tuple(
        event.event_type for event in view.committed_transition.batch.trace_batch.events
    )
    if observed != expected:
        problems.append(f"{label}_types")


def _check_canonical_wire(
    upstreams: SupportV2Upstreams,
    support: SupportAdvanceRequestV2,
    problems: list[str],
) -> None:
    if (
        PrincipalVerificationSetAdvanceRequestV2.from_dict(
            upstreams.verification_request.to_dict()
        )
        != upstreams.verification_request
        or MembershipCommitRequestV2.from_dict(upstreams.membership_request.to_dict())
        != upstreams.membership_request
        or SupportAdvanceRequestV2.from_dict(support.to_dict()) != support
    ):
        problems.append("canonical_wire_round_trip")


def _committed(attempt: GovernanceCommitAttemptV2) -> bool:
    return bool(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.committed_transition is not None
    )


__all__: tuple[str, ...] = ()
