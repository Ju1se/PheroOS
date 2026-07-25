"""Core public-only lanes for durable Risk v2 Conformance."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json

from pheroos.conformance.checks._risk_v2_context_support import (
    BASE_EPOCH,
    RUN_REF,
    RiskV2ConformanceContext,
    advance_v2,
    context_v2,
    head_revision_v2,
    is_failure_v2,
    rebind_context_v2,
    request_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceDomainRetirementRequestV2,
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    RiskStateAdvanceRequestV2,
    VerifiedRiskSourceV2,
    VerifiedRiskStateV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    rehydrate_risk_state_v2,
    require_current_risk_state_v2,
    risk_state_is_current_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


@dataclass(frozen=True, slots=True)
class _SameShapeSource:
    context_root: str


def run_risk_v2_core_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> list[str]:
    """Run restart, fixed-lineage, binding, and determinism lanes."""

    problems: list[str] = []
    _vertical_restart_linearity(adapter, problems)
    _fixed_lineage_epoch_jump(adapter, problems)
    _sealed_domain_matrix(adapter, problems)
    _source_session_and_selector_matrix(adapter, problems)
    _deterministic_transcript(adapter, problems)
    return problems


def _vertical_restart_linearity(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "vertical")
    genesis, genesis_source = request_v2(context, advance_ref="advance:genesis")
    committed = advance_v2(context, genesis, genesis_source)
    if (
        committed.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or committed.committed_transition is None
    ):
        problems.append("genesis_commit")
        return

    batch = committed.committed_transition.batch
    expected_streams = {
        genesis.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    if {entry.stream_ref for entry in batch.read_set.entries} != expected_streams:
        problems.append("complete_authority_read_set")
    events = batch.trace_batch.events
    if tuple(event.event_type for event in events) != (
        "risk_state_advanced",
        "risk_assessed_v2",
    ) or any(
        event.lineage.get("read_set_root") != batch.read_set.root()
        or event.lineage.get("snapshot_root") != genesis.snapshot.snapshot_root
        for event in events
    ):
        problems.append("atomic_trace_lineage")

    verified = rehydrate_risk_state_v2(
        json.loads(genesis.canonical_bytes()),
        domain=context.domain,
        state_reader=context.store,
    )
    if (
        type(verified) is not VerifiedRiskStateV2
        or verified.position is not GovernanceCommitPositionV2.CURRENT
        or not risk_state_is_current_v2(verified)
        or require_current_risk_state_v2(verified) != genesis.snapshot
    ):
        problems.append("current_rehydration")

    restarted_store = adapter.restart_store_v2(context.store)
    restarted = rebind_context_v2(context, restarted_store)
    restarted_parent = rehydrate_risk_state_v2(
        genesis.to_dict(),
        domain=restarted.domain,
        state_reader=restarted.store,
    )
    child_a, source_a = request_v2(
        restarted,
        advance_ref="advance:child:a",
        risk_band=RiskBand.MODERATE,
        parent=restarted_parent.snapshot,
        current_step=3,
    )
    child_b, source_b = request_v2(
        restarted,
        advance_ref="advance:child:b",
        risk_band=RiskBand.HIGH,
        parent=restarted_parent.snapshot,
        current_step=3,
    )
    session_a = open_risk_authority_session_v2(restarted.capability, child_a)
    accepted_a = advance_risk_state_v2(
        child_a,
        source=source_a,
        authority_session=session_a,
    )
    stale_b = advance_v2(restarted, child_b, source_b)
    if (
        accepted_a.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or accepted_a.committed_transition is None
    ):
        problems.append("restart_child_commit")
    if not is_failure_v2(
        stale_b,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    ):
        problems.append("stale_fork_retry")
    if risk_state_is_current_v2(restarted_parent):
        problems.append("successor_supersedes_parent")

    revoked = revoke_governance_issuer_grant_v2(
        restarted.store,
        restarted.domain,
        restarted.grant.grant_ref,
        "transition:risk-v2:revoke-after-commit",
        BASE_EPOCH + 1,
    )
    exact_retry = advance_risk_state_v2(
        child_a,
        source=None,
        authority_session=session_a,
    )
    if revoked.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("grant_revocation")
    if (
        exact_retry.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or exact_retry.committed_transition is None
        or accepted_a.committed_transition is None
        or exact_retry.committed_transition.receipt.receipt_root
        != accepted_a.committed_transition.receipt.receipt_root
    ):
        problems.append("exact_retry_after_revocation")


def _fixed_lineage_epoch_jump(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    """Prove an epoch beyond the Store stream cap stays in one lineage."""

    context = context_v2(adapter, "fixed-lineage-epoch-130")
    first, first_source = request_v2(
        context,
        advance_ref="advance:fixed-lineage:first",
        epoch=BASE_EPOCH,
    )
    first_attempt = advance_v2(context, first, first_source)
    if first_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("fixed_lineage_epoch_130_genesis")
        return

    proposed_streams = {
        request_v2(
            context,
            advance_ref=f"advance:fixed-lineage:proposal:{epoch}",
            epoch=epoch,
        )[0].stream_ref
        for epoch in range(BASE_EPOCH + 1, BASE_EPOCH + 131)
    }
    if proposed_streams != {first.stream_ref}:
        problems.append("fixed_lineage_130_portable_epochs")
        return

    restarted_store = adapter.restart_store_v2(context.store)
    jumped_epoch = BASE_EPOCH + 130
    restarted = rebind_context_v2(
        context,
        restarted_store,
        epoch=jumped_epoch,
    )
    parent = rehydrate_risk_state_v2(
        first.to_dict(),
        domain=restarted.domain,
        state_reader=restarted.store,
    )
    second, second_source = request_v2(
        restarted,
        advance_ref="advance:fixed-lineage:epoch-130",
        parent=parent.snapshot,
        epoch=jumped_epoch,
        current_step=3,
    )
    second_attempt = advance_v2(restarted, second, second_source)
    if (
        first.stream_ref != second.stream_ref
        or second.snapshot.parent_epoch != BASE_EPOCH
        or second.snapshot.epoch != jumped_epoch
        or second.snapshot.revision != 2
        or not second.snapshot.assessment.window_reset_required
        or second_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("fixed_lineage_epoch_130")
        return

    current = rehydrate_risk_state_v2(
        json.loads(second.canonical_bytes()),
        domain=restarted.domain,
        state_reader=restarted.store,
    )
    if (
        risk_state_is_current_v2(parent)
        or not risk_state_is_current_v2(current)
        or require_current_risk_state_v2(current).snapshot_root
        != second.snapshot.snapshot_root
    ):
        problems.append("fixed_lineage_epoch_130_currentness")


def _sealed_domain_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(
        adapter,
        "sealed-domain",
        operations=(
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
    )
    request, source = request_v2(
        context,
        advance_ref="advance:sealed-domain:genesis",
    )
    initial_session = open_risk_authority_session_v2(context.capability, request)
    committed = advance_risk_state_v2(
        request,
        source=source,
        authority_session=initial_session,
    )
    if (
        committed.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or committed.committed_transition is None
    ):
        problems.append("sealed_domain_setup")
        return

    child, child_source = request_v2(
        context,
        advance_ref="advance:sealed-domain:child",
        parent=request.snapshot,
        current_step=3,
    )
    child_session = open_risk_authority_session_v2(context.capability, child)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        context.domain.scope_ref,
        context.grant.grant_ref,
    )
    retirement_request = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=RUN_REF,
        request_ref="request:risk-v2:sealed-domain",
        transition_id="transition:risk-v2:sealed-domain",
        stream_refs=tuple(
            sorted((grant_stream, request.stream_ref), key=lambda item: item.encode())
        ),
        reason_ref="reason:risk-v2-conformance-complete",
        observed_epoch=BASE_EPOCH + 1,
    )
    retirement_session = open_governance_authority_session_v2(
        context.capability,
        retirement_request,
    )
    sealed = retire_governance_domain_v2(
        retirement_request,
        authority_session=retirement_session,
    )
    if sealed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("sealed_domain_retirement")
        return

    historical = rehydrate_risk_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    revision_before = head_revision_v2(context, request)
    denied = advance_risk_state_v2(
        child,
        source=child_source,
        authority_session=child_session,
    )
    exact_retry = advance_risk_state_v2(
        request,
        source=None,
        authority_session=initial_session,
    )
    if (
        historical.request_root != request.request_root
        or not is_failure_v2(
            denied,
            GovernanceCommitDispositionV2.DENIED,
            AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
        )
        or head_revision_v2(context, request) != revision_before
    ):
        problems.append("sealed_domain_historical_or_zero_write")
    if (
        exact_retry.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or exact_retry.committed_transition is None
        or exact_retry.committed_transition.receipt.receipt_root
        != committed.committed_transition.receipt.receipt_root
    ):
        problems.append("sealed_domain_exact_retry")


def _source_session_and_selector_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "source-session")
    request, source = request_v2(context, advance_ref="advance:source-session")
    session = open_risk_authority_session_v2(context.capability, request)
    _raw_source_and_session_binding(context, request, source, session, problems)
    _domain_run_and_issuer_binding(adapter, context, request, session, problems)
    _selector_and_operation_binding(adapter, context, problems)


def _raw_source_and_session_binding(
    context: RiskV2ConformanceContext,
    request: RiskStateAdvanceRequestV2,
    source: VerifiedRiskSourceV2,
    session: object,
    problems: list[str],
) -> None:
    for label, candidate in (
        ("snapshot", request.snapshot),
        ("dict", request.to_dict()),
        ("digest", request.request_root),
        ("same_shape", _SameShapeSource(source.context_root)),
    ):
        attempt = advance_risk_state_v2(
            request,
            source=candidate,
            authority_session=session,
        )
        if attempt.disposition is not GovernanceCommitDispositionV2.INVALID:
            problems.append(f"raw_source:{label}")
    if head_revision_v2(context, request) != 0:
        problems.append("raw_source_zero_write")

    other_request, other_source = request_v2(
        context,
        advance_ref="advance:other-source",
        risk_band=RiskBand.MODERATE,
    )
    cross_source = advance_risk_state_v2(
        request,
        source=other_source,
        authority_session=session,
    )
    wrong_session = open_risk_authority_session_v2(context.capability, other_request)
    cross_session = advance_risk_state_v2(
        request,
        source=source,
        authority_session=wrong_session,
    )
    missing_session = advance_risk_state_v2(
        request,
        source=source,
        authority_session=None,
    )
    if any(
        item.disposition is not GovernanceCommitDispositionV2.INVALID
        for item in (cross_source, cross_session)
    ) or not is_failure_v2(
        missing_session,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
    ):
        problems.append("source_or_session_binding")
    if head_revision_v2(context, request) != 0:
        problems.append("source_session_zero_write")


def _domain_run_and_issuer_binding(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context: RiskV2ConformanceContext,
    request: RiskStateAdvanceRequestV2,
    session: object,
    problems: list[str],
) -> None:
    foreign = context_v2(adapter, "foreign-source")
    _, foreign_source = request_v2(
        foreign,
        advance_ref="advance:source-session",
    )
    cross_domain = advance_risk_state_v2(
        request,
        source=foreign_source,
        authority_session=session,
    )
    _, other_run_source = request_v2(
        context,
        advance_ref="advance:source-session",
        run_ref="run:risk-v2:foreign",
    )
    cross_run = advance_risk_state_v2(
        request,
        source=other_run_source,
        authority_session=session,
    )
    if any(
        item.disposition is not GovernanceCommitDispositionV2.INVALID
        for item in (cross_domain, cross_run)
    ):
        problems.append("scope_domain_run_binding")

    spoofed, _ = request_v2(
        context,
        advance_ref="advance:spoofed-issuer",
        issuer_ref="issuer:spoofed",
    )
    try:
        open_risk_authority_session_v2(context.capability, spoofed)
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH:
            problems.append("issuer_diagnostic")
    else:
        problems.append("issuer_binding")


def _selector_and_operation_binding(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context: RiskV2ConformanceContext,
    problems: list[str],
) -> None:
    mismatched_manifest = replace(
        context.manifest,
        authority_policy=replace(
            context.manifest.authority_policy,
            profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
        ),
    )
    selector_request, selector_source = request_v2(
        context,
        advance_ref="advance:authority-selector",
        manifest=mismatched_manifest,
    )
    selector = advance_v2(context, selector_request, selector_source)
    if not is_failure_v2(
        selector,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
    ):
        problems.append("authority_selector")

    denied = context_v2(
        adapter,
        "operation-denied",
        operations=(GovernanceIssuerOperationV2.ADVANCE_REPLAY,),
    )
    denied_request, _ = request_v2(denied, advance_ref="advance:operation-denied")
    try:
        open_risk_authority_session_v2(denied.capability, denied_request)
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED:
            problems.append("operation_diagnostic")
    else:
        problems.append("operation_denied")


def _deterministic_transcript(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    first = context_v2(adapter, "deterministic")
    second = context_v2(adapter, "deterministic")
    first_request, first_source = request_v2(
        first,
        advance_ref="advance:deterministic",
    )
    second_request, second_source = request_v2(
        second,
        advance_ref="advance:deterministic",
    )
    first_attempt = advance_v2(first, first_request, first_source)
    second_attempt = advance_v2(second, second_request, second_source)
    if (
        first_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or second_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or first_attempt.committed_transition is None
        or second_attempt.committed_transition is None
        or first_request.to_dict() != second_request.to_dict()
        or first_attempt.committed_transition.batch.trace_batch.events
        != second_attempt.committed_transition.batch.trace_batch.events
    ):
        problems.append("deterministic_transcript")


__all__: list[str] = []
