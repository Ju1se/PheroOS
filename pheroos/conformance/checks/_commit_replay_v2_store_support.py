"""Public delegating Store boundary shared by Commit Replay v2 checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any, cast

from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_state_v2 import CommitReplayAdvanceRequestV2
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


_RUN_REF = "run:commit-replay-v2"


class PublicCommitReplayFaultStoreV2:
    """Delegate through public StateStore v2 while altering only returned views."""

    def __init__(self, store: GovernanceStateStoreV2, domain_root: str) -> None:
        self._store = store
        self._domain_root = domain_root
        self.finality_transition_ids: set[str] = set()
        self.view_mutator: Callable[[GovernanceCommitViewV2], None] | None = None
        self.lose_next_committed_response = False
        self.reset_observations()

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def reset_observations(self) -> None:
        self.head_reads = 0
        self.state_reads = 0
        self.commit_view_reads = 0
        self.atomic_commits = 0

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        self.head_reads += 1
        return self._store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        self.state_reads += 1
        return self._store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        self.commit_view_reads += 1
        if transition_id in self.finality_transition_ids:
            return GovernanceCommitViewV2(
                domain_root=self._domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                    path="/transition_id",
                    stage=GovernanceFailureStageV2.FINALITY,
                ),
                committed_transition=None,
                position_observation=None,
                observed_revision=None,
                observed_head_root=None,
            )
        view = self._store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_mutator is not None:
            self.view_mutator(view)
        return view

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        self.atomic_commits += 1
        result = self._store.atomic_commit_v2(batch)
        if (
            self.lose_next_committed_response
            and result.disposition is GovernanceCommitDispositionV2.COMMITTED
        ):
            self.lose_next_committed_response = False
            return GovernanceCommitAttemptV2(
                domain_root=batch.domain_root,
                scope_ref=batch.scope_ref,
                stream_ref=batch.stream_ref,
                transition_id=batch.transition_id,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                    path="/transition_id",
                    stage=GovernanceFailureStageV2.FINALITY,
                ),
                committed_transition=None,
                position_observation=None,
            )
        return result


def fault_commit_replay_context_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    label: str,
) -> tuple[Any, PublicCommitReplayFaultStoreV2]:
    """Rebind an activated public context to the delegating Store proxy."""

    base = context_factory(adapter, label)
    store = PublicCommitReplayFaultStoreV2(base.store, base.domain.domain_root)
    capability = bind_governance_issuer_capability_v2(
        cast(GovernanceStateStoreV2, store),
        base.domain,
        base.grant,
        _RUN_REF,
        3,
    )
    context = replace(
        base,
        store=cast(GovernanceStateStoreV2, store),
        capability=capability,
    )
    store.reset_observations()
    return context, store


def commit_replay_head_revision_v2(
    context: Any,
    request: CommitReplayAdvanceRequestV2,
) -> int:
    return cast(
        int,
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision,
    )


def is_commit_replay_failure_v2(
    attempt: GovernanceCommitAttemptV2,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
) -> bool:
    return (
        attempt.disposition is disposition
        and attempt.failure is not None
        and attempt.failure.code is code
        and attempt.committed_transition is None
    )


__all__: list[str] = []
