"""Finality, reconciliation, and lost-response checks for public Risk v2."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pheroos.conformance.checks._risk_v2_store_support import (
    fault_risk_context_v2,
    is_risk_failure_v2,
    risk_head_revision_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
)
from pheroos.governance.risk_v2 import RiskBand, rehydrate_risk_state_v2
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


def run_risk_v2_finality_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
) -> list[str]:
    """Exercise exact recovery and every public finality boundary."""

    problems: list[str] = []
    _lost_response_and_conflict(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _reconciliation_and_rehydrate_finality(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _historical_parent_finality(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    return problems


def _lost_response_and_conflict(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context, store = fault_risk_context_v2(adapter, context_factory, "lost-response")
    request, source = request_factory(context, advance_ref="advance:lost-response")
    store.lose_next_committed_response = True
    unavailable = advance_factory(context, request, source)
    if not is_risk_failure_v2(
        unavailable,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("lost_response_finality")
    if store.atomic_commits != 1 or risk_head_revision_v2(context, request) != 1:
        problems.append("lost_response_atomic_publication")

    recovered = advance_factory(context, request, None)
    repeated = advance_factory(context, request, None)
    if (
        recovered.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or repeated.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or recovered.committed_transition is None
        or repeated.committed_transition is None
        or recovered.committed_transition.receipt.receipt_root
        != repeated.committed_transition.receipt.receipt_root
        or store.atomic_commits != 1
    ):
        problems.append("lost_response_exact_retry")

    conflicting, conflicting_source = request_factory(
        context,
        advance_ref="advance:lost-response",
        risk_band=RiskBand.HIGH,
    )
    conflict = advance_factory(context, conflicting, conflicting_source)
    if not is_risk_failure_v2(
        conflict,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
    ):
        problems.append("canonical_transition_conflict")
    if store.atomic_commits != 1 or risk_head_revision_v2(context, request) != 1:
        problems.append("conflict_zero_write")


def _reconciliation_and_rehydrate_finality(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context, store = fault_risk_context_v2(
        adapter, context_factory, "reconciliation-finality"
    )
    request, source = request_factory(
        context, advance_ref="advance:reconciliation-finality"
    )
    committed = advance_factory(context, request, source)
    if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("reconciliation_setup")
        return
    store.finality_transition_ids.add(request.transition_id)
    store.reset_observations()

    retry = advance_factory(context, request, None)
    if not is_risk_failure_v2(
        retry,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("reconciliation_finality_unavailable")
    if store.atomic_commits != 0 or risk_head_revision_v2(context, request) != 1:
        problems.append("reconciliation_finality_zero_write")

    try:
        rehydrate_risk_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE:
            problems.append("rehydrate_finality_diagnostic")
    else:
        problems.append("rehydrate_finality_unavailable")
    if store.atomic_commits != 0 or risk_head_revision_v2(context, request) != 1:
        problems.append("rehydrate_finality_zero_write")


def _historical_parent_finality(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context, store = fault_risk_context_v2(adapter, context_factory, "parent-finality")
    parent, parent_source = request_factory(
        context, advance_ref="advance:parent-finality"
    )
    committed = advance_factory(context, parent, parent_source)
    if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("parent_finality_setup")
        return
    child, child_source = request_factory(
        context,
        advance_ref="advance:parent-finality:child",
        risk_band=RiskBand.MODERATE,
        parent=parent.snapshot,
        current_step=3,
    )
    store.finality_transition_ids.add(parent.transition_id)
    store.reset_observations()
    blocked = advance_factory(context, child, child_source)
    if not is_risk_failure_v2(
        blocked,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("historical_parent_finality_unavailable")
    if store.atomic_commits != 0 or risk_head_revision_v2(context, parent) != 1:
        problems.append("historical_parent_finality_zero_write")


__all__: list[str] = []
