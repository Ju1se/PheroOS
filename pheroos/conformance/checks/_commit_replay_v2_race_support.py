"""Public concurrent reconciliation and currentness checks."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

from pheroos.conformance.checks._commit_replay_v2_store_support import (
    commit_replay_head_revision_v2,
    fault_commit_replay_context_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.commit_state_v2 import (
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    VerifiedCommitReplaySourceV2,
    commit_replay_state_is_current_v2,
    rehydrate_commit_replay_state_v2,
    require_current_commit_replay_state_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


_WORKERS = 32

_ContextFactory = Callable[..., Any]
_ReceiptFactory = Callable[..., CommitReplayReceiptV2]
_RequestFactory = Callable[
    ...,
    tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2],
]
_AdvanceFactory = Callable[
    [Any, CommitReplayAdvanceRequestV2, object], GovernanceCommitAttemptV2
]


def run_public_commit_replay_race_matrix_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
) -> tuple[str, ...]:
    problems: list[str] = []
    _evaluate_same_request_race(
        adapter,
        context_factory,
        receipt_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _evaluate_two_fork_race(
        adapter,
        context_factory,
        receipt_factory,
        request_factory,
        advance_factory,
        problems,
    )
    return tuple(problems)


def _evaluate_same_request_race(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
    problems: list[str],
) -> None:
    context, _ = fault_commit_replay_context_v2(
        adapter, context_factory, "public-race-same"
    )
    request, source = request_factory(
        context,
        advance_ref="advance:public-race-same",
        receipt=receipt_factory(401, suffix=":same"),
        current_step=1,
    )
    barrier = Barrier(_WORKERS)

    def same_worker(_index: int) -> GovernanceCommitAttemptV2:
        barrier.wait()
        return advance_factory(context, request, source)

    with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        results = tuple(executor.map(same_worker, range(_WORKERS)))
    roots = {
        result.committed_transition.receipt.receipt_root
        for result in results
        if result.committed_transition is not None
    }
    if (
        any(
            result.disposition is not GovernanceCommitDispositionV2.COMMITTED
            for result in results
        )
        or len(roots) != 1
        or commit_replay_head_revision_v2(context, request) != 1
    ):
        problems.append("concurrent_same_request")


def _evaluate_two_fork_race(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
    problems: list[str],
) -> None:
    context, _ = fault_commit_replay_context_v2(
        adapter, context_factory, "public-race-fork"
    )
    parent, parent_source = request_factory(
        context,
        advance_ref="advance:public-race-parent",
        receipt=None,
        current_step=1,
    )
    if (
        advance_factory(context, parent, parent_source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("concurrent_fork_parent")
        return
    verified_parent = rehydrate_commit_replay_state_v2(
        parent.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    fork_a, source_a = request_factory(
        context,
        advance_ref="advance:public-race-fork:a",
        receipt=receipt_factory(402, suffix=":fork:a"),
        current_step=2,
        parent=parent.snapshot,
    )
    fork_b, source_b = request_factory(
        context,
        advance_ref="advance:public-race-fork:b",
        receipt=receipt_factory(403, suffix=":fork:b"),
        current_step=2,
        parent=parent.snapshot,
    )
    results = _run_two_fork_workers(
        context, fork_a, source_a, fork_b, source_b, advance_factory
    )
    family_a = results[0::2]
    family_b = results[1::2]
    dispositions = (
        {item.disposition for item in family_a},
        {item.disposition for item in family_b},
    )
    expected_families = {
        frozenset({GovernanceCommitDispositionV2.COMMITTED}),
        frozenset({GovernanceCommitDispositionV2.RETRY_REQUIRED}),
    }
    if {frozenset(item) for item in dispositions} != expected_families:
        problems.append("concurrent_two_fork_disposition")
    loser = (
        family_a
        if dispositions[0] == {GovernanceCommitDispositionV2.RETRY_REQUIRED}
        else family_b
    )
    if any(
        item.failure is None
        or item.failure.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
        for item in loser
    ):
        problems.append("concurrent_two_fork_diagnostic")
    if commit_replay_head_revision_v2(context, fork_a) != 2:
        problems.append("concurrent_two_fork_revision")
    _check_superseded_parent(verified_parent, problems)
    winning_request = (
        fork_a
        if dispositions[0] == {GovernanceCommitDispositionV2.COMMITTED}
        else fork_b
    )
    current = rehydrate_commit_replay_state_v2(
        winning_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    if (
        current.position is not GovernanceCommitPositionV2.CURRENT
        or not commit_replay_state_is_current_v2(current)
        or require_current_commit_replay_state_v2(current).snapshot_root
        != winning_request.snapshot.snapshot_root
    ):
        problems.append("winning_fork_currentness")


def _run_two_fork_workers(
    context: Any,
    fork_a: CommitReplayAdvanceRequestV2,
    source_a: VerifiedCommitReplaySourceV2,
    fork_b: CommitReplayAdvanceRequestV2,
    source_b: VerifiedCommitReplaySourceV2,
    advance_factory: _AdvanceFactory,
) -> tuple[GovernanceCommitAttemptV2, ...]:
    barrier = Barrier(_WORKERS)
    work = tuple(
        (fork_a, source_a) if index % 2 == 0 else (fork_b, source_b)
        for index in range(_WORKERS)
    )

    def worker(
        item: tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2],
    ) -> GovernanceCommitAttemptV2:
        barrier.wait()
        request, source = item
        return advance_factory(context, request, source)

    with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
        return tuple(executor.map(worker, work))


def _check_superseded_parent(verified_parent: Any, problems: list[str]) -> None:
    if (
        commit_replay_state_is_current_v2(verified_parent)
        or verified_parent.position is not GovernanceCommitPositionV2.SUPERSEDED
    ):
        problems.append("superseded_parent_currentness")
    try:
        require_current_commit_replay_state_v2(verified_parent)
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE:
            problems.append("superseded_parent_diagnostic")
    else:
        problems.append("superseded_parent_requirement")


__all__: list[str] = []
