"""Finality, seal, malicious-reader, and race Support v2 lanes."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

from pheroos.conformance.checks._support_v2_context_support import (
    advance_support_v2,
    capability_v2,
    commit_upstreams_v2,
    context_v2,
    initialize_v2,
    issue_v2,
    support_state_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import RUN_REF
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceDomainRetirementRequestV2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.support_v2 import (
    SupportAdvanceRequestV2,
    VerifiedSupportSourceV2,
    advance_support_state_v2,
    open_support_authority_session_v2,
    rehydrate_support_state_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


def run_support_v2_finality_race_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> list[str]:
    problems: list[str] = []
    for lane, operation in (
        ("seal_finality_tamper", _seal_finality_and_tamper),
        ("race_32", _race_32),
    ):
        try:
            operation(adapter, problems)
        except Exception as exc:
            problems.append(f"{lane}_exception:{type(exc).__name__}:{exc}")
    return problems


def _seal_finality_and_tamper(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    finality_context = context_v2(adapter, "finality-tamper")
    request, source = initialize_v2(finality_context, "finality-tamper")
    if not _committed(advance_support_v2(finality_context, request, source)):
        problems.append("finality_tamper_initialize")
        return
    _assert_finality_and_tamper_fail_closed(
        finality_context.store,
        finality_context.domain,
        request,
        problems,
    )
    _assert_sealed_domain_behavior(adapter, problems)


def _assert_finality_and_tamper_fail_closed(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: SupportAdvanceRequestV2,
    problems: list[str],
) -> None:
    finality_reader = _ReaderOverrideV2(
        store,
        domain.domain_root,
        request.transition_id,
        mode="finality",
    )
    try:
        rehydrate_support_state_v2(
            request.to_dict(),
            domain=domain,
            state_reader=cast(GovernanceStateStoreV2, finality_reader),
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE:
            problems.append("finality_wrong_diagnostic")
    else:
        problems.append("finality_not_fail_closed")

    tamper_reader = _ReaderOverrideV2(
        store,
        domain.domain_root,
        request.transition_id,
        mode="tamper",
    )
    try:
        rehydrate_support_state_v2(
            request.to_dict(),
            domain=domain,
            state_reader=cast(GovernanceStateStoreV2, tamper_reader),
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not (
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        ):
            problems.append("tamper_wrong_diagnostic")
    else:
        problems.append("tamper_not_fail_closed")


def _assert_sealed_domain_behavior(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    sealed = context_v2(adapter, "sealed")
    upstreams = commit_upstreams_v2(sealed, label="sealed")
    initialized, initialized_source = initialize_v2(sealed, "sealed")
    initialized_session = open_support_authority_session_v2(
        capability_v2(sealed, initialized.observed_epoch),
        initialized,
    )
    initialized_attempt = advance_support_state_v2(
        initialized,
        source=initialized_source,
        authority_session=initialized_session,
    )
    if not _committed(initialized_attempt):
        problems.append("sealed_initialize")
        return
    pending, pending_source = issue_v2(
        sealed,
        support_state_v2(sealed, initialized),
        upstreams.membership_state,
        "sealed:pending",
        current_step=5,
    )
    pending_session = open_support_authority_session_v2(
        capability_v2(sealed, pending.observed_epoch),
        pending,
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=sealed.domain.domain_root,
        scope_ref=sealed.domain.scope_ref,
        run_ref=RUN_REF,
        request_ref="request:support-v2:retire",
        transition_id="transition:support-v2:retire",
        stream_refs=tuple(
            sorted(
                (
                    governance_issuer_grant_stream_ref_v2(
                        sealed.domain.scope_ref,
                        sealed.grant.grant_ref,
                    ),
                    upstreams.verification_request.stream_ref,
                    upstreams.membership_request.stream_ref,
                    initialized.stream_ref,
                )
            )
        ),
        reason_ref="reason:conformance-complete",
        observed_epoch=100,
    )
    retirement_session = open_governance_authority_session_v2(
        capability_v2(sealed, retirement.observed_epoch),
        retirement,
    )
    retired = retire_governance_domain_v2(
        retirement,
        authority_session=retirement_session,
    )
    if not _committed(retired):
        problems.append("domain_seal_not_committed")
        return
    if not _committed(
        advance_support_state_v2(
            initialized,
            source=None,
            authority_session=initialized_session,
        )
    ):
        problems.append("sealed_exact_retry")
    denied = advance_support_state_v2(
        pending,
        source=pending_source,
        authority_session=pending_session,
    )
    if not _failure(
        denied,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
    ):
        problems.append("sealed_new_mutation_not_denied")


def _race_32(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    identical = context_v2(adapter, "race-identical")
    request, source = initialize_v2(identical, "race-identical")
    session = open_support_authority_session_v2(
        capability_v2(identical, request.observed_epoch),
        request,
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = tuple(
            executor.map(
                lambda _: advance_support_state_v2(
                    request,
                    source=source,
                    authority_session=session,
                ),
                range(32),
            )
        )
    receipts = {
        outcome.committed_transition.receipt.receipt_root
        for outcome in outcomes
        if outcome.committed_transition is not None
    }
    if not all(_committed(outcome) for outcome in outcomes) or len(receipts) != 1:
        problems.append("race_32_same_request")
    if (
        identical.store.load_head_v2(
            identical.domain.scope_ref,
            request.stream_ref,
        ).revision
        != 1
    ):
        problems.append("race_32_same_request_revision")

    conflicting = context_v2(adapter, "race-conflicting")
    candidates = tuple(
        initialize_v2(conflicting, f"race-conflicting:{index:02d}")
        for index in range(32)
    )
    sessions = tuple(
        open_support_authority_session_v2(
            capability_v2(conflicting, candidate.observed_epoch),
            candidate,
        )
        for candidate, _ in candidates
    )
    work = tuple(zip(candidates, sessions, strict=True))

    def commit(
        item: tuple[
            tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2],
            GovernanceAuthoritySessionV2,
        ],
    ) -> GovernanceCommitAttemptV2:
        ((candidate, candidate_source), candidate_session) = item
        return advance_support_state_v2(
            candidate,
            source=candidate_source,
            authority_session=candidate_session,
        )

    with ThreadPoolExecutor(max_workers=32) as executor:
        conflicts = tuple(executor.map(commit, work))
    committed = sum(_committed(outcome) for outcome in conflicts)
    if committed != 1 or any(
        outcome.disposition
        not in (
            GovernanceCommitDispositionV2.COMMITTED,
            GovernanceCommitDispositionV2.RETRY_REQUIRED,
        )
        for outcome in conflicts
    ):
        problems.append("race_32_forks_one_winner")
    if (
        conflicting.store.load_head_v2(
            conflicting.domain.scope_ref,
            candidates[0][0].stream_ref,
        ).revision
        != 1
    ):
        problems.append("race_32_forks_revision")


class _ReaderOverrideV2:
    def __init__(
        self,
        store: GovernanceStateStoreV2,
        domain_root: str,
        transition_id: str,
        *,
        mode: str,
    ) -> None:
        self._store = store
        self._domain_root = domain_root
        self._transition_id = transition_id
        self._mode = mode

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self._store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self._store.load_state_v2(scope_ref, stream_ref)

    def atomic_commit_v2(self, batch: Any) -> GovernanceCommitAttemptV2:
        return self._store.atomic_commit_v2(batch)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        if transition_id == self._transition_id and self._mode == "finality":
            return GovernanceCommitViewV2(
                domain_root=self._domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=(AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE),
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
        if transition_id == self._transition_id and self._mode == "tamper":
            if view.committed_transition is not None:
                object.__setattr__(view.committed_transition, "inclusion_proof", None)
        return view


def _committed(attempt: GovernanceCommitAttemptV2) -> bool:
    return bool(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.committed_transition is not None
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
