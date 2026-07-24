"""Thin public-only orchestration for Commit Replay v2 adversarial checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pheroos.conformance.checks._commit_replay_v2_finality_support import (
    run_public_commit_replay_finality_matrix_v2,
)
from pheroos.conformance.checks._commit_replay_v2_integrity_support import (
    run_public_commit_replay_integrity_matrix_v2,
)
from pheroos.conformance.checks._commit_replay_v2_race_support import (
    run_public_commit_replay_race_matrix_v2,
)
from pheroos.conformance.checks._commit_replay_v2_resource_support import (
    run_public_commit_replay_resource_matrix_v2,
)
from pheroos.conformance.checks._commit_replay_v2_store_support import (
    fault_commit_replay_context_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.commit_state_v2 import (
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    VerifiedCommitReplaySourceV2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitAttemptV2


_ContextFactory = Callable[..., Any]
_ReceiptFactory = Callable[..., CommitReplayReceiptV2]
_RequestFactory = Callable[
    ...,
    tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2],
]
_AdvanceFactory = Callable[
    [Any, CommitReplayAdvanceRequestV2, object], GovernanceCommitAttemptV2
]


def run_public_commit_replay_adversarial_matrix_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
) -> tuple[str, ...]:
    """Compose public finality, integrity, race, and resource submatrices."""

    problems = [
        *run_public_commit_replay_finality_matrix_v2(
            adapter,
            context_factory=context_factory,
            receipt_factory=receipt_factory,
            request_factory=request_factory,
            advance_factory=advance_factory,
        ),
        *run_public_commit_replay_integrity_matrix_v2(
            adapter,
            context_factory=context_factory,
            receipt_factory=receipt_factory,
            request_factory=request_factory,
            advance_factory=advance_factory,
        ),
        *run_public_commit_replay_race_matrix_v2(
            adapter,
            context_factory=context_factory,
            receipt_factory=receipt_factory,
            request_factory=request_factory,
            advance_factory=advance_factory,
        ),
    ]
    resource_context, resource_store = fault_commit_replay_context_v2(
        adapter,
        context_factory,
        "public-resources",
    )
    problems.extend(
        run_public_commit_replay_resource_matrix_v2(
            context=resource_context,
            store=resource_store,
            request_factory=request_factory,
        )
    )
    return tuple(problems)


__all__: list[str] = []
