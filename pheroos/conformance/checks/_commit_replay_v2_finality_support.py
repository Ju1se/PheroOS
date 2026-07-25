"""Public finality and canonical reconciliation checks for Commit Replay v2."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pheroos.conformance.checks._commit_replay_v2_store_support import (
    commit_replay_head_revision_v2,
    fault_commit_replay_context_v2,
    is_commit_replay_failure_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.commit_state_v2 import (
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    VerifiedCommitReplaySourceV2,
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


_ContextFactory = Callable[..., Any]
_ReceiptFactory = Callable[..., CommitReplayReceiptV2]
_RequestFactory = Callable[
    ...,
    tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2],
]
_AdvanceFactory = Callable[
    [Any, CommitReplayAdvanceRequestV2, object], GovernanceCommitAttemptV2
]


def run_public_commit_replay_finality_matrix_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
) -> tuple[str, ...]:
    problems: list[str] = []
    _evaluate_finality(
        adapter,
        context_factory,
        receipt_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _evaluate_lost_response(
        adapter,
        context_factory,
        receipt_factory,
        request_factory,
        problems,
    )
    return tuple(problems)


def _evaluate_finality(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
    problems: list[str],
) -> None:
    context, store = fault_commit_replay_context_v2(
        adapter, context_factory, "public-finality"
    )
    request, source = request_factory(
        context,
        advance_ref="advance:public-reconcile-finality",
        receipt=receipt_factory(101, suffix=":finality"),
        current_step=1,
    )
    session = open_commit_replay_authority_session_v2(context.capability, request)
    store.finality_transition_ids.add(request.transition_id)
    store.reset_observations()
    unavailable = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    if not is_commit_replay_failure_v2(
        unavailable,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("reconciliation_finality_unavailable")
    if (
        store.atomic_commits != 0
        or commit_replay_head_revision_v2(context, request) != 0
    ):
        problems.append("reconciliation_finality_zero_write")

    parent_context, parent_store = fault_commit_replay_context_v2(
        adapter, context_factory, "public-parent-finality"
    )
    parent, parent_source = request_factory(
        parent_context,
        advance_ref="advance:public-parent-finality:1",
        receipt=None,
        current_step=1,
    )
    if (
        advance_factory(parent_context, parent, parent_source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("parent_finality_setup")
        return
    child, child_source = request_factory(
        parent_context,
        advance_ref="advance:public-parent-finality:2",
        receipt=receipt_factory(102, suffix=":parent-finality"),
        current_step=2,
        parent=parent.snapshot,
    )
    child_session = open_commit_replay_authority_session_v2(
        parent_context.capability, child
    )
    parent_store.finality_transition_ids.add(parent.transition_id)
    parent_store.reset_observations()
    child_attempt = advance_commit_replay_state_v2(
        child,
        source=child_source,
        authority_session=child_session,
    )
    if not is_commit_replay_failure_v2(
        child_attempt,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("parent_finality_unavailable")
    if (
        parent_store.atomic_commits != 0
        or commit_replay_head_revision_v2(parent_context, child) != 1
    ):
        problems.append("parent_finality_zero_write")
    try:
        rehydrate_commit_replay_state_v2(
            parent.to_dict(),
            domain=parent_context.domain,
            state_reader=parent_context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE:
            problems.append("rehydrate_finality_code")
    else:
        problems.append("rehydrate_finality_unavailable")
    if (
        parent_store.atomic_commits != 0
        or commit_replay_head_revision_v2(parent_context, child) != 1
    ):
        problems.append("rehydrate_finality_zero_write")


def _evaluate_lost_response(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    problems: list[str],
) -> None:
    context, store = fault_commit_replay_context_v2(
        adapter, context_factory, "public-lost-response"
    )
    request, source = request_factory(
        context,
        advance_ref="advance:public-lost-response",
        receipt=receipt_factory(103, suffix=":lost"),
        current_step=1,
    )
    session = open_commit_replay_authority_session_v2(context.capability, request)
    store.lose_next_committed_response = True
    first = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    if not is_commit_replay_failure_v2(
        first,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("post_publication_lost_response")
    if (
        store.atomic_commits != 1
        or commit_replay_head_revision_v2(context, request) != 1
    ):
        problems.append("post_publication_not_once")

    recovered = advance_commit_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    stored = context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    if (
        recovered.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or recovered.committed_transition is None
        or stored.committed_transition is None
        or recovered.committed_transition.to_dict()
        != stored.committed_transition.to_dict()
        or store.atomic_commits != 1
        or commit_replay_head_revision_v2(context, request) != 1
    ):
        problems.append("canonical_exact_retry")

    conflict, _ = request_factory(
        context,
        advance_ref=request.advance_ref,
        receipt=receipt_factory(104, suffix=":conflict"),
        current_step=1,
    )
    conflict_session = open_commit_replay_authority_session_v2(
        context.capability, conflict
    )
    rejected = advance_commit_replay_state_v2(
        conflict,
        source=None,
        authority_session=conflict_session,
    )
    if (
        not is_commit_replay_failure_v2(
            rejected,
            GovernanceCommitDispositionV2.INVALID,
            AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
        )
        or store.atomic_commits != 1
        or commit_replay_head_revision_v2(context, request) != 1
    ):
        problems.append("canonical_retry_conflict")


__all__: list[str] = []
