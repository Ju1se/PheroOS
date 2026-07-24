"""Public-ABI adversarial support for the Hybrid Replay v2 matrix.

This module deliberately composes only public Protocol, Governance, Store, and
Trace contracts.  Its delegating Store is a consumer-side proxy: it neither
uses adapter mutation hooks nor inspects an implementation-private image.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from pheroos.conformance.checks._hybrid_replay_v2_resource_support import (
    run_public_hybrid_replay_resource_matrix_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance import (
    HybridReplayAdvanceRequestV2,
    VerifiedHybridSourceStepV2,
    advance_hybrid_replay_state_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    TraceEvent,
)
from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)


_RUN_REF = "run:hybrid-replay-v2"

_ContextFactory = Callable[..., Any]
_SourceFactory = Callable[..., VerifiedHybridSourceStepV2]
_RequestFactory = Callable[..., HybridReplayAdvanceRequestV2]
_AdvanceFactory = Callable[
    [Any, HybridReplayAdvanceRequestV2, VerifiedHybridSourceStepV2],
    GovernanceCommitAttemptV2,
]


class _PublicHybridFaultStoreV2:
    """Observe and inject faults through the public StateStore v2 surface."""

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
                    code=(AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE),
                    path="/transition_id",
                    stage=GovernanceFailureStageV2.FINALITY,
                ),
                committed_transition=None,
                position_observation=None,
            )
        return result


def run_public_hybrid_replay_adversarial_matrix_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: _ContextFactory,
    source_factory: _SourceFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
) -> tuple[str, ...]:
    """Run public finality, historical-integrity, and resource subchecks."""

    problems: list[str] = []
    _evaluate_public_finality_and_reconciliation(
        adapter,
        context_factory,
        source_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _evaluate_public_historical_integrity(
        adapter,
        context_factory,
        source_factory,
        request_factory,
        advance_factory,
        problems,
    )
    resource_context, resource_store = _fault_context(
        adapter,
        context_factory,
        "public-resources",
    )
    problems.extend(
        run_public_hybrid_replay_resource_matrix_v2(
            context=resource_context,
            store=resource_store,
            source_factory=source_factory,
            request_factory=request_factory,
        )
    )
    return tuple(problems)


def _fault_context(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    label: str,
) -> tuple[Any, _PublicHybridFaultStoreV2]:
    base = context_factory(adapter, label)
    store = _PublicHybridFaultStoreV2(base.store, base.domain.domain_root)
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


def _evaluate_public_finality_and_reconciliation(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    source_factory: _SourceFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
    problems: list[str],
) -> None:
    context, store = _fault_context(adapter, context_factory, "public-finality")
    source = source_factory(context, current_step=1, event_suffix="finality")
    request = request_factory(
        context,
        source,
        "advance:public-finality",
        observed_epoch=3,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    store.finality_transition_ids.add(request.transition_id)
    store.reset_observations()
    unavailable = advance_hybrid_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    if not _is_failure(
        unavailable,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("reconciliation_finality_unavailable")
    if (
        store.atomic_commits != 0
        or store.state_reads != 0
        or store.load_head_v2(request.scope_ref, request.stream_ref).revision != 0
    ):
        problems.append("reconciliation_finality_zero_write")

    parent_context, parent_store = _fault_context(
        adapter, context_factory, "public-parent-finality"
    )
    first_source = source_factory(
        parent_context,
        current_step=1,
        event_suffix="parent-finality-1",
    )
    first = request_factory(
        parent_context,
        first_source,
        "advance:public-parent-finality:1",
        observed_epoch=3,
    )
    first_attempt = advance_factory(parent_context, first, first_source)
    if first_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("parent_finality_setup")
        return
    verified_parent = rehydrate_hybrid_replay_state_v2(
        first.to_dict(),
        domain=parent_context.domain,
        state_reader=parent_context.store,
    )
    child_source = source_factory(
        parent_context,
        current_step=2,
        verified_state=verified_parent,
        event_suffix="parent-finality-2",
    )
    child = request_factory(
        parent_context,
        child_source,
        "advance:public-parent-finality:2",
        observed_epoch=3,
    )
    child_session = open_hybrid_replay_authority_session_v2(
        parent_context.capability,
        child,
    )
    parent_store.finality_transition_ids.add(first.transition_id)
    parent_store.reset_observations()
    child_attempt = advance_hybrid_replay_state_v2(
        child,
        source=child_source,
        authority_session=child_session,
    )
    if not _is_failure(
        child_attempt,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("historical_parent_finality_unavailable")
    if (
        parent_store.atomic_commits != 0
        or parent_store.load_head_v2(child.scope_ref, child.stream_ref).revision != 1
    ):
        problems.append("historical_parent_finality_zero_write")
    try:
        rehydrate_hybrid_replay_state_v2(
            first.to_dict(),
            domain=parent_context.domain,
            state_reader=parent_context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE:
            problems.append("rehydrate_finality_code")
    else:
        problems.append("rehydrate_finality_unavailable")

    _evaluate_lost_response_reconciliation(
        adapter,
        context_factory,
        source_factory,
        request_factory,
        problems,
    )


def _evaluate_lost_response_reconciliation(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    source_factory: _SourceFactory,
    request_factory: _RequestFactory,
    problems: list[str],
) -> None:
    context, store = _fault_context(adapter, context_factory, "public-lost-response")
    source = source_factory(context, current_step=1, event_suffix="lost-response")
    request = request_factory(
        context,
        source,
        "advance:public-lost-response",
        observed_epoch=3,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    store.lose_next_committed_response = True
    first = advance_hybrid_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    if not _is_failure(
        first,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    ):
        problems.append("post_publication_lost_response")
    if (
        store.atomic_commits != 1
        or store.load_head_v2(request.scope_ref, request.stream_ref).revision != 1
    ):
        problems.append("post_publication_was_not_published_once")

    recovered = advance_hybrid_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    try:
        stored = store.load_commit_view_v2(
            request.scope_ref,
            request.stream_ref,
            request.transition_id,
        )
    except KeyError:
        stored = None
    if (
        recovered.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or recovered.committed_transition is None
        or stored is None
        or stored.committed_transition is None
        or recovered.committed_transition.to_dict()
        != stored.committed_transition.to_dict()
        or store.atomic_commits != 1
        or store.load_head_v2(request.scope_ref, request.stream_ref).revision != 1
    ):
        problems.append("complete_canonical_exact_reconciliation")

    conflict_source = source_factory(
        context,
        current_step=1,
        event_suffix="lost-response-conflict",
    )
    conflict = request_factory(
        context,
        conflict_source,
        request.advance_ref,
        observed_epoch=3,
    )
    conflict_session = open_hybrid_replay_authority_session_v2(
        context.capability,
        conflict,
    )
    rejected = advance_hybrid_replay_state_v2(
        conflict,
        source=None,
        authority_session=conflict_session,
    )
    if (
        not _is_failure(
            rejected,
            GovernanceCommitDispositionV2.INVALID,
            AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
        )
        or store.atomic_commits != 1
    ):
        problems.append("canonical_reconciliation_conflict")


def _evaluate_public_historical_integrity(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    source_factory: _SourceFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
    problems: list[str],
) -> None:
    variants = (
        *(
            (kind, mutation)
            for kind in ("state", "grant", "lifecycle")
            for mutation in ("missing", "revision", "root")
        ),
        ("additional", "extra"),
    )
    for stream_kind, variant in variants:
        label = f"public-read-set-{stream_kind}-{variant}"
        context, store = _fault_context(adapter, context_factory, label)
        source = source_factory(context, current_step=1, event_suffix=label)
        request = request_factory(
            context,
            source,
            f"advance:{label}",
            observed_epoch=3,
        )
        if (
            advance_factory(context, request, source).disposition
            is not GovernanceCommitDispositionV2.COMMITTED
        ):
            problems.append(f"{label}_setup")
            continue
        store.view_mutator = _read_set_mutator(
            request,
            stream_kind,
            variant,
        )
        _expect_invalid_rehydration(context, request, label, problems)

    for mutation in (
        "inclusion_delete",
        "batch_delete",
        "position_delete",
        "position_forge_superseded",
    ):
        label = f"public-canonical-view-{mutation}"
        context, store = _fault_context(adapter, context_factory, label)
        source = source_factory(context, current_step=1, event_suffix=label)
        request = request_factory(
            context,
            source,
            f"advance:{label}",
            observed_epoch=3,
        )
        if (
            advance_factory(context, request, source).disposition
            is not GovernanceCommitDispositionV2.COMMITTED
        ):
            problems.append(f"{label}_setup")
            continue
        store.view_mutator = _canonical_view_mutator(mutation)
        _expect_invalid_rehydration(context, request, label, problems)
        try:
            session = open_hybrid_replay_authority_session_v2(
                context.capability,
                request,
            )
            retry = advance_hybrid_replay_state_v2(
                request,
                source=None,
                authority_session=session,
            )
        except Exception:
            problems.append(f"{label}_reconciliation_exception")
            continue
        if (
            not _is_failure(
                retry,
                GovernanceCommitDispositionV2.INVALID,
                AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            )
            or store.atomic_commits != 1
            or store.load_head_v2(request.scope_ref, request.stream_ref).revision != 1
        ):
            problems.append(f"{label}_reconciliation")

    context, store = _fault_context(
        adapter, context_factory, "public-trace-read-set-root"
    )
    source = source_factory(context, current_step=1, event_suffix="trace-read-set")
    request = request_factory(
        context,
        source,
        "advance:public-trace-read-set-root",
        observed_epoch=3,
    )
    if (
        advance_factory(context, request, source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("trace_read_set_root_setup")
        return
    store.view_mutator = _mutate_trace_read_set_root
    _expect_invalid_rehydration(
        context,
        request,
        "trace_read_set_root_tamper",
        problems,
    )


def _replace_read_set(
    view: GovernanceCommitViewV2,
    entries: Sequence[GovernanceReadPreconditionV2],
) -> None:
    assert view.committed_transition is not None
    read_set = GovernanceAuthorityReadSetV2(
        entries=tuple(sorted(entries, key=lambda item: item.stream_ref.encode()))
    )
    object.__setattr__(view.committed_transition.batch, "read_set", read_set)


def _read_set_mutator(
    request: HybridReplayAdvanceRequestV2,
    stream_kind: str,
    variant: str,
) -> Callable[[GovernanceCommitViewV2], None]:
    def mutate(view: GovernanceCommitViewV2) -> None:
        _mutate_read_set(view, request, stream_kind, variant)

    return mutate


def _mutate_read_set(
    view: GovernanceCommitViewV2,
    request: HybridReplayAdvanceRequestV2,
    stream_kind: str,
    variant: str,
) -> None:
    assert view.committed_transition is not None
    entries = list(view.committed_transition.batch.read_set.entries)
    if variant == "extra":
        entries.append(
            GovernanceReadPreconditionV2(
                stream_ref="authority:unexpected",
                expected_revision=0,
                expected_root="sha256:" + "a" * 64,
            )
        )
        _replace_read_set(view, entries)
        return
    selected_index = next(
        index
        for index, item in enumerate(entries)
        if (stream_kind == "state" and item.stream_ref == request.stream_ref)
        or (
            stream_kind == "lifecycle"
            and item.stream_ref == GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
        )
        or (
            stream_kind == "grant"
            and item.stream_ref
            not in {
                request.stream_ref,
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
            }
        )
    )
    selected = entries[selected_index]
    if variant == "missing":
        del entries[selected_index]
    elif variant == "revision":
        entries[selected_index] = replace(
            selected,
            expected_revision=selected.expected_revision + 1,
        )
    elif variant == "root":
        entries[selected_index] = replace(
            selected,
            expected_root="sha256:" + "b" * 64,
        )
    else:
        raise ValueError("unknown public read-set mutation")
    _replace_read_set(view, entries)


def _mutate_trace_read_set_root(view: GovernanceCommitViewV2) -> None:
    assert view.committed_transition is not None
    batch = view.committed_transition.batch
    event = batch.trace_batch.events[0]
    lineage = dict(event.lineage)
    lineage["read_set_root"] = "sha256:" + "c" * 64
    substituted = TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )
    object.__setattr__(
        batch,
        "trace_batch",
        GovernanceTraceBatchV2(
            domain_root=batch.trace_batch.domain_root,
            scope_ref=batch.trace_batch.scope_ref,
            stream_ref=batch.trace_batch.stream_ref,
            transition_id=batch.trace_batch.transition_id,
            events=(substituted,),
        ),
    )


def _canonical_view_mutator(
    mutation: str,
) -> Callable[[GovernanceCommitViewV2], None]:
    def mutate(view: GovernanceCommitViewV2) -> None:
        assert view.committed_transition is not None
        if mutation == "inclusion_delete":
            object.__setattr__(view.committed_transition, "inclusion_proof", None)
        elif mutation == "batch_delete":
            object.__setattr__(view.committed_transition, "batch", None)
        elif mutation == "position_delete":
            object.__setattr__(view, "position_observation", None)
        elif mutation == "position_forge_superseded":
            assert view.position_observation is not None
            object.__setattr__(
                view.position_observation,
                "position",
                GovernanceCommitPositionV2.SUPERSEDED,
            )
        else:
            raise ValueError("unknown public canonical-view mutation")

    return mutate


def _expect_invalid_rehydration(
    context: Any,
    request: HybridReplayAdvanceRequestV2,
    label: str,
    problems: list[str],
) -> None:
    try:
        rehydrate_hybrid_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not (
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        ):
            problems.append(label)
    except Exception:
        problems.append(label)
    else:
        problems.append(label)


def _is_failure(
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
