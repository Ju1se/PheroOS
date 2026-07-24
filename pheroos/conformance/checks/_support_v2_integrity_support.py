"""Replay, staleness, rotation, and canonical-input Support v2 lanes."""

from __future__ import annotations

from pheroos.conformance.checks._support_v2_context_support import (
    activate_rotated_grant_v2,
    advance_support_v2,
    capability_v2,
    commit_upstreams_v2,
    context_v2,
    initialize_v2,
    issue_v2,
    rebind_store_v2,
    support_state_v2,
    switch_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import root_v2
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.governance.support_v2 import (
    MAX_VERIFICATION_EVIDENCE_ROOTS_V2,
    PrincipalVerificationRecordV2,
    SupportAdvanceRequestV2,
    advance_support_state_v2,
    open_support_authority_session_v2,
    rehydrate_support_state_v2,
    require_current_support_state_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


def run_support_v2_integrity_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> list[str]:
    problems: list[str] = []
    for lane, operation in (
        ("lost_response", _lost_response_exact_retry),
        ("stale_parent", _stale_parent_and_membership),
        ("issuer_rotation", _issuer_rotation),
        ("canonical_resource", _canonical_wire_and_resource),
    ):
        try:
            operation(adapter, problems)
        except Exception as exc:
            problems.append(f"{lane}_exception:{type(exc).__name__}:{exc}")
    return problems


def _lost_response_exact_retry(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "lost-response")
    upstreams = commit_upstreams_v2(context, label="lost-response")
    initialized, initialize_source = initialize_v2(context, "lost-response")
    if not _committed(advance_support_v2(context, initialized, initialize_source)):
        problems.append("lost_response_initialize")
        return
    initialized_state = support_state_v2(context, initialized)
    request, source = issue_v2(
        context,
        initialized_state,
        upstreams.membership_state,
        "lost-response",
        current_step=5,
    )
    session = open_support_authority_session_v2(
        capability_v2(context, request.observed_epoch),
        request,
    )
    accepted = advance_support_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    if not _committed(accepted):
        problems.append("lost_response_initial_commit")
        return
    assert accepted.committed_transition is not None
    expected_receipt = accepted.committed_transition.receipt.receipt_root

    restarted = adapter.restart_store_v2(context.store)
    recovered = rebind_store_v2(context, restarted)
    restarted_session = open_support_authority_session_v2(
        capability_v2(recovered, request.observed_epoch),
        request,
    )
    exact_retry = advance_support_state_v2(
        request,
        source=None,
        authority_session=restarted_session,
    )
    if not _same_receipt(exact_retry, expected_receipt):
        problems.append("lost_response_exact_retry")

    revoked = revoke_governance_issuer_grant_v2(
        recovered.store,
        recovered.domain,
        recovered.grant.grant_ref,
        "transition:support-v2:grant-revoked-after-commit",
        100,
    )
    if not _committed(revoked):
        problems.append("lost_response_grant_revoke")
    post_revoke_retry = advance_support_state_v2(
        request,
        source=None,
        authority_session=restarted_session,
    )
    if not _same_receipt(post_revoke_retry, expected_receipt):
        problems.append("lost_response_retry_after_revoke")


def _stale_parent_and_membership(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "stale-parent")
    upstreams = commit_upstreams_v2(context, label="stale-parent")
    initialized, initialize_source = initialize_v2(context, "stale-parent")
    if not _committed(advance_support_v2(context, initialized, initialize_source)):
        problems.append("stale_parent_initialize")
        return
    initialized_state = support_state_v2(context, initialized)
    winner, winner_source = issue_v2(
        context,
        initialized_state,
        upstreams.membership_state,
        "stale-parent:winner",
        current_step=5,
    )
    loser, loser_source = issue_v2(
        context,
        initialized_state,
        upstreams.membership_state,
        "stale-parent:loser",
        current_step=5,
    )
    if not _committed(advance_support_v2(context, winner, winner_source)):
        problems.append("stale_parent_winner")
        return
    rejected = advance_support_v2(context, loser, loser_source)
    if not _failure(
        rejected,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    ):
        problems.append("stale_parent_not_retry_required")

    membership_context = context_v2(adapter, "stale-membership")
    first = commit_upstreams_v2(membership_context, label="membership:first")
    initial, initial_source = initialize_v2(membership_context, "stale-membership")
    if not _committed(advance_support_v2(membership_context, initial, initial_source)):
        problems.append("stale_membership_initialize")
        return
    pending, pending_source = issue_v2(
        membership_context,
        support_state_v2(membership_context, initial),
        first.membership_state,
        "stale-membership:pending",
        current_step=5,
    )
    pending_session = open_support_authority_session_v2(
        capability_v2(membership_context, pending.observed_epoch),
        pending,
    )
    commit_upstreams_v2(
        membership_context,
        label="membership:successor",
        epoch=2,
        verification_parent=first.verification_request.snapshot,
        membership_parent=first.membership_request.snapshot,
    )
    membership_rejected = advance_support_state_v2(
        pending,
        source=pending_source,
        authority_session=pending_session,
    )
    if not _failure(
        membership_rejected,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    ):
        problems.append("stale_membership_not_retry_required")


def _issuer_rotation(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "issuer-rotation")
    upstreams = commit_upstreams_v2(context, label="issuer-rotation")
    initialized, initialize_source = initialize_v2(context, "issuer-rotation")
    if not _committed(advance_support_v2(context, initialized, initialize_source)):
        problems.append("issuer_rotation_initialize")
        return
    claim = root_v2("claim:issuer-rotation")
    issued, issue_source = issue_v2(
        context,
        support_state_v2(context, initialized),
        upstreams.membership_state,
        "issuer-rotation:a",
        current_step=5,
        claim_root=claim,
    )
    if not _committed(advance_support_v2(context, issued, issue_source)):
        problems.append("issuer_rotation_issue")
        return
    if issued.issued_lease is None:
        problems.append("issuer_rotation_missing_lease")
        return
    rotated = activate_rotated_grant_v2(context)
    switched, switch_source = switch_v2(
        context,
        support_state_v2(context, issued),
        upstreams.membership_state,
        issued.issued_lease.lease_root,
        "issuer-rotation:b",
        current_step=6,
        claim_root=claim,
        grant=rotated,
    )
    if not _committed(
        advance_support_v2(context, switched, switch_source, grant=rotated)
    ):
        problems.append("issuer_rotation_switch")
        return
    if (
        switched.stream_ref != initialized.stream_ref
        or switched.issued_lease is None
        or switched.issued_lease.issuance_issuer_ref != rotated.issuer_ref
        or switched.revocation is None
        or switched.revocation.lease_issuance_issuer_ref != context.grant.issuer_ref
        or switched.revocation.revocation_issuer_ref != rotated.issuer_ref
    ):
        problems.append("issuer_rotation_fixed_lineage")
    recovered = rehydrate_support_state_v2(
        switched.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    if require_current_support_state_v2(recovered) != switched.snapshot:
        problems.append("issuer_rotation_rehydrate")


def _canonical_wire_and_resource(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "canonical-resource")
    request, source = initialize_v2(context, "canonical-resource")
    if not _committed(advance_support_v2(context, request, source)):
        problems.append("canonical_resource_initialize")
        return
    payloads: list[object] = []
    missing_root = request.to_dict()
    missing_root["request_root"] = ""
    payloads.append(missing_root)
    tuple_array = request.to_dict()
    tuple_array["evicted_lease_roots"] = ()
    payloads.append(tuple_array)
    bool_epoch = request.to_dict()
    bool_epoch["observed_epoch"] = True
    bool_snapshot = bool_epoch["snapshot"]
    assert type(bool_snapshot) is dict
    bool_snapshot["observed_epoch"] = True
    payloads.append(bool_epoch)
    repaired_snapshot = request.to_dict()
    repaired_body = repaired_snapshot["snapshot"]
    assert type(repaired_body) is dict
    repaired_body["snapshot_root"] = ""
    payloads.append(repaired_snapshot)
    for payload in payloads:
        try:
            SupportAdvanceRequestV2.from_dict(payload)
        except (TypeError, ValueError):
            pass
        else:
            problems.append("noncanonical_wire_accepted")

    record = commit_upstreams_v2(
        context_v2(adapter, "resource-record"),
        label="resource-record",
    ).verification_request.snapshot.records[0]
    oversized = record.to_dict()
    oversized["evidence_roots"] = [root_v2("resource-root")] * (
        MAX_VERIFICATION_EVIDENCE_ROOTS_V2 + 1
    )
    try:
        PrincipalVerificationRecordV2.from_dict(oversized)
    except (TypeError, ValueError):
        pass
    else:
        problems.append("resource_limit_accepted")


def _committed(attempt: GovernanceCommitAttemptV2) -> bool:
    return bool(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.committed_transition is not None
    )


def _same_receipt(attempt: GovernanceCommitAttemptV2, expected: str) -> bool:
    return bool(
        _committed(attempt)
        and attempt.committed_transition is not None
        and attempt.committed_transition.receipt.receipt_root == expected
    )


def _failure(
    attempt: GovernanceCommitAttemptV2,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
) -> bool:
    return bool(
        attempt.disposition is disposition
        and attempt.failure is not None
        and attempt.failure.code is code
        and attempt.committed_transition is None
    )


__all__: tuple[str, ...] = ()
