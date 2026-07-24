"""Public Store adversarial lanes for Commit Gate v2 Conformance."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import cast

from pheroos.conformance.checks._commit_gate_v2_context_support import (
    CommitGateV2ConformanceContext,
    capability_v2,
    commit_gate_context_v2,
    issue_permission_v2,
    prepare_permission_v2,
    prepare_stop_v2,
    resolve_stop_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceDomainRetirementRequestV2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
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
from pheroos.governance.commit_gate_v2 import (
    commit_permission_state_is_current_v2,
    issue_commit_permission_v2,
    open_commit_permission_authority_session_v2,
    open_commit_stop_authority_session_v2,
    rehydrate_commit_permission_state_v2,
    resolve_commit_stop_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


class PublicCommitGateFaultStoreV2:
    """Delegate only through the public Store protocol and alter returned views."""

    def __init__(self, store: GovernanceStateStoreV2, domain_root: str) -> None:
        self._store = store
        self._domain_root = domain_root
        self.finality_transition_ids: set[str] = set()
        self.view_mutator: Callable[[GovernanceCommitViewV2], None] | None = None

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self._store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Mapping[str, object]:
        return cast(
            Mapping[str, object], self._store.load_state_v2(scope_ref, stream_ref)
        )

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
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
        self, batch: GovernanceCommitBatchV2
    ) -> GovernanceCommitAttemptV2:
        return self._store.atomic_commit_v2(batch)


def run_commit_gate_v2_finality_integrity_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> tuple[str, ...]:
    problems: list[str] = []
    context = commit_gate_context_v2(adapter, "public-finality-integrity")
    request, source = prepare_permission_v2(context, "public-finality-integrity")
    if (
        issue_permission_v2(context, request, source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        return ("tamper_fixture_commit",)
    wrapper = PublicCommitGateFaultStoreV2(context.store, context.domain.domain_root)
    reader = cast(GovernanceStateStoreV2, wrapper)
    state = rehydrate_commit_permission_state_v2(
        request.to_dict(), domain=context.domain, state_reader=reader
    )

    wrapper.finality_transition_ids.add(request.transition_id)
    if commit_permission_state_is_current_v2(state):
        problems.append("finality_not_fail_closed")
    if _rehydrate_succeeds(context, reader, request.to_dict()):
        problems.append("finality_rehydrate_accepted")
    wrapper.finality_transition_ids.clear()

    for failure, accepted_failure, mutator in (
        (
            "inclusion_tamper_not_fail_closed",
            "inclusion_tamper_rehydrate_accepted",
            _remove_inclusion,
        ),
        (
            "position_tamper_not_fail_closed",
            "position_tamper_rehydrate_accepted",
            _forge_position,
        ),
    ):
        wrapper.view_mutator = mutator
        if commit_permission_state_is_current_v2(state):
            problems.append(failure)
        if _rehydrate_succeeds(context, reader, request.to_dict()):
            problems.append(accepted_failure)
    return tuple(problems)


def run_commit_gate_v2_race_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> tuple[str, ...]:
    problems: list[str] = []
    identical = commit_gate_context_v2(adapter, "public-race-identical")
    request, source = prepare_permission_v2(identical, "public-race-identical")
    with ThreadPoolExecutor(max_workers=32) as pool:
        identical_results = tuple(
            pool.map(
                lambda _: issue_permission_v2(identical, request, source),
                range(32),
            )
        )
    committed = tuple(
        item
        for item in identical_results
        if item.disposition is GovernanceCommitDispositionV2.COMMITTED
        and item.committed_transition is not None
    )
    receipts = {
        item.committed_transition.receipt.receipt_root
        for item in committed
        if item.committed_transition is not None
    }
    if len(committed) != 32 or len(receipts) != 1:
        problems.append("race_32_identical_exact_retry")

    conflicting = commit_gate_context_v2(adapter, "public-race-conflicting")
    requests = tuple(
        prepare_stop_v2(
            conflicting,
            f"public-race-conflicting:{index}",
            blocked=bool(index % 2),
        )
        for index in range(32)
    )
    with ThreadPoolExecutor(max_workers=32) as pool:
        conflict_results = tuple(
            pool.map(
                lambda pair: resolve_stop_v2(conflicting, pair[0], pair[1]),
                requests,
            )
        )
    dispositions = tuple(item.disposition for item in conflict_results)
    if (
        dispositions.count(GovernanceCommitDispositionV2.COMMITTED) != 1
        or dispositions.count(GovernanceCommitDispositionV2.RETRY_REQUIRED) != 31
    ):
        problems.append("race_32_conflicting_one_winner")
    return tuple(problems)


def run_commit_gate_v2_seal_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> tuple[str, ...]:
    context = commit_gate_context_v2(adapter, "public-seal")
    stop, stop_source = prepare_stop_v2(context, "public-seal:accepted")
    stop_session = open_commit_stop_authority_session_v2(
        capability_v2(context.store, context.domain, context.grant), stop
    )
    accepted = resolve_commit_stop_v2(
        stop, source=stop_source, authority_session=stop_session
    )
    permission, permission_source = prepare_permission_v2(
        context, "public-seal:pending"
    )
    permission_session = open_commit_permission_authority_session_v2(
        capability_v2(context.store, context.domain, context.grant), permission
    )
    if (
        accepted.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or accepted.committed_transition is None
    ):
        return ("sealed_fixture_commit",)

    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=stop.run_ref,
        request_ref="request:commit-gate-v2:public-seal",
        transition_id="transition:commit-gate-v2:public-seal",
        stream_refs=_all_committed_streams(context, stop.stream_ref),
        reason_ref="reason:conformance-complete",
        observed_epoch=stop.observed_epoch + 1,
    )
    retirement_session = open_governance_authority_session_v2(
        capability_v2(
            context.store,
            context.domain,
            context.grant,
            retirement.observed_epoch,
        ),
        retirement,
    )
    retired = retire_governance_domain_v2(
        retirement, authority_session=retirement_session
    )
    exact_retry = resolve_commit_stop_v2(
        stop, source=None, authority_session=stop_session
    )
    denied = issue_commit_permission_v2(
        permission,
        source=permission_source,
        authority_session=permission_session,
    )
    problems = []
    if retired.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("domain_seal")
    if (
        exact_retry.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or exact_retry.committed_transition is None
        or exact_retry.committed_transition.receipt.receipt_root
        != accepted.committed_transition.receipt.receipt_root
    ):
        problems.append("sealed_historical_exact_retry")
    if (
        denied.disposition is not GovernanceCommitDispositionV2.DENIED
        or denied.failure is None
        or denied.failure.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED
    ):
        problems.append("sealed_new_write_not_denied")
    return tuple(problems)


def _rehydrate_succeeds(
    context: CommitGateV2ConformanceContext,
    reader: GovernanceStateStoreV2,
    payload: object,
) -> bool:
    try:
        rehydrate_commit_permission_state_v2(
            payload, domain=context.domain, state_reader=reader
        )
    except Exception:
        return False
    return True


def _remove_inclusion(view: GovernanceCommitViewV2) -> None:
    if view.committed_transition is not None:
        object.__setattr__(view.committed_transition, "inclusion_proof", None)


def _forge_position(view: GovernanceCommitViewV2) -> None:
    if view.position_observation is not None:
        object.__setattr__(
            view.position_observation,
            "observed_head_root",
            "sha256:" + "0" * 64,
        )


def _all_committed_streams(
    context: CommitGateV2ConformanceContext,
    stop_stream_ref: str,
) -> tuple[str, ...]:
    streams = {
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        context.replay_state.snapshot.stream_ref,
        context.risk_state.snapshot.stream_ref,
        context.membership_state.snapshot.verification_stream_ref,
        context.membership_state.snapshot.stream_ref,
        context.support_state.snapshot.stream_ref,
        stop_stream_ref,
    }
    return tuple(sorted(streams, key=lambda item: item.encode("utf-8")))


__all__: tuple[str, ...] = ()
