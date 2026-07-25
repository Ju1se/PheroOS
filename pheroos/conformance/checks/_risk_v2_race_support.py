"""Public 32-way idempotency and fork-race checks for Risk v2."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    rehydrate_risk_state_v2,
    risk_state_is_current_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


_WORKERS = 32


def run_risk_v2_race_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
) -> list[str]:
    """Prove one-result idempotency and one-winner linear fork publication."""

    problems: list[str] = []
    _same_request_race(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _fork_race(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    return problems


def _same_request_race(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context = context_factory(adapter, "race-same-request")
    request, source = request_factory(context, advance_ref="advance:race:same-request")
    barrier = Barrier(_WORKERS)

    def submit() -> Any:
        barrier.wait()
        return advance_factory(context, request, source)

    with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        futures = tuple(executor.submit(submit) for _ in range(_WORKERS))
        results = tuple(future.result() for future in futures)
    receipts = {
        item.committed_transition.receipt.receipt_root
        for item in results
        if item.committed_transition is not None
    }
    if (
        any(
            item.disposition is not GovernanceCommitDispositionV2.COMMITTED
            for item in results
        )
        or len(receipts) != 1
        or context.store.load_head_v2(request.scope_ref, request.stream_ref).revision
        != 1
    ):
        problems.append("race_32_same_request")


def _fork_race(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context = context_factory(adapter, "race-forks")
    parent, parent_source = request_factory(context, advance_ref="advance:race:parent")
    parent_attempt = advance_factory(context, parent, parent_source)
    if parent_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("race_fork_parent_setup")
        return
    verified_parent = rehydrate_risk_state_v2(
        parent.to_dict(), domain=context.domain, state_reader=context.store
    )
    forks = tuple(
        request_factory(
            context,
            advance_ref=f"advance:race:fork:{index:02d}",
            risk_band=RiskBand.MODERATE,
            parent=parent.snapshot,
            current_step=3,
        )
        for index in range(_WORKERS)
    )
    barrier = Barrier(_WORKERS)

    def submit(item: tuple[Any, Any]) -> Any:
        barrier.wait()
        return advance_factory(context, item[0], item[1])

    with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        futures = tuple(executor.submit(submit, item) for item in forks)
        results = tuple(future.result() for future in futures)
    committed = tuple(
        item
        for item in results
        if item.disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    stale = tuple(
        item
        for item in results
        if item.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
        and item.failure is not None
        and item.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    )
    if len(committed) != 1 or len(stale) != _WORKERS - 1:
        problems.append("race_32_forks_one_winner")
    if context.store.load_head_v2(
        parent.scope_ref, parent.stream_ref
    ).revision != 2 or risk_state_is_current_v2(verified_parent):
        problems.append("race_32_forks_currentness")


__all__: list[str] = []
