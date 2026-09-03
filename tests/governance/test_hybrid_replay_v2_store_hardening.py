from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest

import pheroos.governance._hybrid_replay_v2.projection as projection_module
from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_session_v2.operations import (
    bind_governance_issuer_capability_v2,
)
from pheroos.governance._authority_v2 import (
    FAILURE_STAGE_AFTER_ATOMIC_PUBLICATION_V2,
)
from pheroos.governance._authority_store_v2_contracts.batch import (
    GovernanceTraceBatchV2,
)
from pheroos.governance._hybrid_replay_v2.contracts import (
    HybridReplayAdvanceRequestV2,
)
from pheroos.governance._hybrid_replay_v2.evaluator import (
    evaluate_hybrid_collective_step_v2,
)
from pheroos.governance._hybrid_replay_v2.operations import (
    advance_hybrid_replay_state_v2,
    hybrid_replay_state_is_current_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
    require_current_hybrid_replay_state_v2,
)
from pheroos.governance._hybrid_replay_v2.projection import (
    build_hybrid_replay_advance_request_v2,
)
from pheroos.governance._hybrid_replay_v2.source import VerifiedHybridSourceStepV2
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent
from tests.governance.test_hybrid_replay_v2_operations import (
    _Context,
    _assert_failure,
    _context,
    _request,
    _source_for,
)
from tests.governance.test_hybrid_replay_v2_projection import _fixture, _step
from tests.swarm.test_hybrid_pheromone_vertical_slice import verified_scout


class _ObservingStore:
    """Delegating Store used to count and fault exact ABI operations."""

    def __init__(self, store: GovernanceStateStoreV2, domain_root: str) -> None:
        self.store = store
        self.domain_root = domain_root
        self.finality_transition_ids: set[str] = set()
        self.head_mutator: Callable[[GovernanceHeadV2], object] | None = None
        self.view_mutator: Callable[[GovernanceCommitViewV2], None] | None = None
        self.reset_counts()

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def reset_counts(self) -> None:
        self.head_reads = 0
        self.state_reads = 0
        self.commit_view_reads = 0
        self.atomic_commits = 0

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        self.head_reads += 1
        head = self.store.load_head_v2(scope_ref, stream_ref)
        if (
            stream_ref == GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
            and self.head_mutator is not None
        ):
            return cast(Any, self.head_mutator(head))
        return head

    def load_state_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        self.state_reads += 1
        return self.store.load_state_v2(scope_ref, stream_ref)

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
                domain_root=self.domain_root,
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
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_mutator is not None:
            self.view_mutator(view)
        return view

    def atomic_commit_v2(self, batch: Any) -> GovernanceCommitAttemptV2:
        self.atomic_commits += 1
        return self.store.atomic_commit_v2(batch)


def _observed_context(**kwargs: Any) -> tuple[_Context, _ObservingStore]:
    base = _context(**kwargs)
    store = _ObservingStore(base.store, base.domain.domain_root)
    capability = bind_governance_issuer_capability_v2(
        cast(GovernanceStateStoreV2, store),
        base.domain,
        base.grant,
        "run:hybrid-replay",
        3,
    )
    context = _Context(
        base.domain,
        cast(Any, store),
        base.grant,
        capability,
    )
    store.reset_counts()
    return context, store


def _advance_with_open_session(
    context: _Context,
    request: HybridReplayAdvanceRequestV2,
) -> GovernanceCommitAttemptV2:
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    return advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )


def _request_from_source(
    context: _Context,
    source: VerifiedHybridSourceStepV2,
    *,
    advance_ref: str,
) -> HybridReplayAdvanceRequestV2:
    return build_hybrid_replay_advance_request_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        observed_epoch=3,
        advance_ref=advance_ref,
        source=source,
    )


def _evaluate_bounded_source(
    context: _Context,
    current_step: int,
    *,
    verified_state: object = None,
) -> VerifiedHybridSourceStepV2:
    protocol, _, _, neighborhood = _fixture()
    target = protocol.quorum_policy.target
    return evaluate_hybrid_collective_step_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        observed_epoch=3,
        manifest=protocol,
        current_step=current_step,
        scout_reports=[
            verified_scout(
                f"scout:bounded:{current_step}:a", "candidate:alpha", target
            ),
            verified_scout(
                f"scout:bounded:{current_step}:b", "candidate:alpha", target
            ),
        ],
        topology=neighborhood,
        verified_replay_state=cast(Any, verified_state),
    )


def _advance_source(
    context: _Context,
    request: HybridReplayAdvanceRequestV2,
    source: VerifiedHybridSourceStepV2,
) -> GovernanceCommitAttemptV2:
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    return advance_hybrid_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def test_source_manifest_authority_profile_must_match_session_domain() -> None:
    context, store = _observed_context(
        scope_ref="scope:hybrid-replay-authority-profile"
    )
    manifest, _, _, neighborhood = _fixture()
    manifest = replace(
        manifest,
        authority_policy=replace(
            manifest.authority_policy,
            profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
        ),
    )
    target = manifest.quorum_policy.target
    source = evaluate_hybrid_collective_step_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        observed_epoch=3,
        manifest=manifest,
        current_step=1,
        scout_reports=[
            verified_scout("scout:profile:a", "candidate:alpha", target),
            verified_scout("scout:profile:b", "candidate:alpha", target),
        ],
        topology=neighborhood,
    )
    request = _request_from_source(
        context,
        source,
        advance_ref="advance:authority-profile",
    )

    attempt = _advance_source(context, request, source)

    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
    )
    assert attempt.failure is not None
    assert attempt.failure.path == "/manifest/authority_policy"
    assert store.atomic_commits == 0
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 0
    )


def test_long_distance_stale_parent_uses_bounded_store_calls_and_cas_retry() -> None:
    context, store = _observed_context(scope_ref="scope:hybrid-replay-bounded-history")
    first_source = _evaluate_bounded_source(context, 1)
    first = _request_from_source(
        context,
        first_source,
        advance_ref="advance:bounded:1",
    )
    assert _advance_source(context, first, first_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    first_state = rehydrate_hybrid_replay_state_v2(
        first.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )

    history_length = 16
    stale_source = _evaluate_bounded_source(
        context,
        history_length + 1,
        verified_state=first_state,
    )
    stale = _request_from_source(
        context,
        stale_source,
        advance_ref="advance:bounded:stale",
    )
    current_state = first_state
    for current_step in range(2, history_length + 1):
        source = _evaluate_bounded_source(
            context,
            current_step,
            verified_state=current_state,
        )
        request = _request_from_source(
            context,
            source,
            advance_ref=f"advance:bounded:{current_step}",
        )
        assert _advance_source(context, request, source).disposition is (
            GovernanceCommitDispositionV2.COMMITTED
        )
        current_state = rehydrate_hybrid_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    session = open_hybrid_replay_authority_session_v2(context.capability, stale)
    store.reset_counts()

    attempt = advance_hybrid_replay_state_v2(
        stale,
        source=stale_source,
        authority_session=session,
    )

    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert store.commit_view_reads == 2
    assert store.head_reads == 1
    assert store.state_reads == 1
    assert store.atomic_commits == 1
    assert context.store.load_head_v2(stale.scope_ref, stale.stream_ref).revision == (
        history_length
    )


def test_reconciliation_finality_precedes_source_verification_and_all_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, store = _observed_context(
        scope_ref="scope:hybrid-replay-reconciliation-finality"
    )
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:reconciliation-finality",
        current_step=1,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    store.finality_transition_ids.add(request.transition_id)
    store.reset_counts()
    source_verifications = 0

    def fail_if_verified(*_args: object, **_kwargs: object) -> None:
        nonlocal source_verifications
        source_verifications += 1
        raise AssertionError("source verification must follow finality")

    monkeypatch.setattr(
        projection_module,
        "verify_hybrid_replay_request_source_v2",
        fail_if_verified,
    )
    attempt = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )

    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    )
    assert source_verifications == 0
    assert store.commit_view_reads == 1
    assert store.head_reads == 0
    assert store.state_reads == 0
    assert store.atomic_commits == 0


def test_historical_parent_finality_precedes_source_verification_and_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, store = _observed_context(scope_ref="scope:hybrid-replay-parent-finality")
    first_step = _step()
    first = _request(
        context,
        first_step,
        advance_ref="advance:parent-finality:1",
        current_step=1,
    )
    assert _advance_with_open_session(context, first).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.2,
        adjustment_id="trace:adjustment:parent-finality:2",
    )
    second = _request(
        context,
        second_step,
        advance_ref="advance:parent-finality:2",
        current_step=2,
        parent=first.snapshot,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, second)
    store.finality_transition_ids.add(first.transition_id)
    store.reset_counts()
    source_verifications = 0

    def fail_if_verified(*_args: object, **_kwargs: object) -> None:
        nonlocal source_verifications
        source_verifications += 1
        raise AssertionError("source verification must follow parent finality")

    monkeypatch.setattr(
        projection_module,
        "verify_hybrid_replay_request_source_v2",
        fail_if_verified,
    )
    attempt = advance_hybrid_replay_state_v2(
        second,
        source=_source_for(second),
        authority_session=session,
    )

    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    )
    assert source_verifications == 0
    assert store.commit_view_reads == 2
    assert store.head_reads == 1
    assert store.state_reads == 1
    assert store.atomic_commits == 0

    store.reset_counts()
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_hybrid_replay_state_v2(
            first.to_dict(),
            domain=context.domain,
            state_reader=store,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )
    assert store.commit_view_reads == 1


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            "non_exact",
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
        ),
        (
            "cross_bound",
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        ),
    ),
)
def test_lifecycle_head_is_exact_and_authority_bound_before_source_or_write(
    mutation: str,
    expected_code: AuthorityDiagnosticCodeV2,
) -> None:
    context, store = _observed_context(
        scope_ref=f"scope:hybrid-replay-lifecycle-head:{mutation}"
    )
    step = _step()
    request = _request(
        context,
        step,
        advance_ref=f"advance:lifecycle-head:{mutation}",
        current_step=1,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    if mutation == "non_exact":
        store.head_mutator = lambda _head: object()
    else:
        store.head_mutator = lambda _head: GovernanceHeadV2.genesis(
            context.domain,
            "authority:lifecycle-substitution",
        )
    store.reset_counts()

    attempt = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )

    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.INVALID,
        expected_code,
    )
    assert store.head_reads == 1
    assert store.state_reads == 1
    assert store.atomic_commits == 0


def test_postpublication_finality_exact_retry_reconciles_without_recommit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    armed = False

    def lose_response(stage: str, _batch: object) -> None:
        if armed and stage == FAILURE_STAGE_AFTER_ATOMIC_PUBLICATION_V2:
            raise OSError("response lost after publication")

    context, store = _observed_context(
        scope_ref="scope:hybrid-replay-postpublication",
        failure_injector=lose_response,
    )
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:postpublication",
        current_step=1,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    store.reset_counts()
    armed = True
    first = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )
    _assert_failure(
        first,
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
    )
    assert store.atomic_commits == 1
    assert store.load_head_v2(request.scope_ref, request.stream_ref).revision == 1
    armed = False

    def fail_if_verified(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("exact recovery retry must reconcile first")

    monkeypatch.setattr(
        projection_module,
        "verify_hybrid_replay_request_source_v2",
        fail_if_verified,
    )
    recovered = advance_hybrid_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert recovered.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert recovered.committed_transition is not None
    assert recovered.position_observation is not None
    assert store.atomic_commits == 1
    assert store.load_head_v2(request.scope_ref, request.stream_ref).revision == 1

    conflict_step = _step(
        adjustment_value=1.3,
        adjustment_id="trace:adjustment:postpublication:conflict",
    )
    conflict = _request(
        context,
        conflict_step,
        advance_ref=request.advance_ref,
        current_step=1,
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
    _assert_failure(
        rejected,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
    )
    assert store.atomic_commits == 1


def _replace_read_set(
    view: GovernanceCommitViewV2,
    entries: list[GovernanceReadPreconditionV2],
) -> None:
    assert view.committed_transition is not None
    read_set = GovernanceAuthorityReadSetV2(
        entries=tuple(sorted(entries, key=lambda item: item.stream_ref.encode()))
    )
    object.__setattr__(view.committed_transition.batch, "read_set", read_set)


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
    else:
        selected_index = next(
            index
            for index, item in enumerate(entries)
            if (stream_kind == "replay" and item.stream_ref == request.stream_ref)
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
        else:  # pragma: no cover - closed test vector
            raise AssertionError("unknown read-set mutation")
    _replace_read_set(view, entries)


@pytest.mark.parametrize(
    ("stream_kind", "variant"),
    (
        *(
            (kind, mutation)
            for kind in ("replay", "grant", "lifecycle")
            for mutation in ("missing", "revision", "root")
        ),
        ("additional", "extra"),
    ),
)
def test_historical_read_set_mutations_fail_closed(
    stream_kind: str,
    variant: str,
) -> None:
    context = _context(
        scope_ref=f"scope:hybrid-replay-read-set-{stream_kind}-{variant}"
    )
    step = _step()
    request = _request(
        context,
        step,
        advance_ref=f"advance:read-set:{stream_kind}:{variant}",
        current_step=1,
    )
    assert _advance_with_open_session(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    reader = _ObservingStore(context.store, context.domain.domain_root)
    reader.view_mutator = lambda view: _mutate_read_set(
        view,
        request,
        stream_kind,
        variant,
    )

    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_hybrid_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=reader,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )


def test_historical_trace_binds_exact_read_set_root() -> None:
    context = _context(scope_ref="scope:hybrid-replay-trace-read-set-root")
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:trace-read-set-root",
        current_step=1,
    )
    assert _advance_with_open_session(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    reader = _ObservingStore(context.store, context.domain.domain_root)

    def mutate_trace(view: GovernanceCommitViewV2) -> None:
        assert view.committed_transition is not None
        batch = view.committed_transition.batch
        trace_batch = batch.trace_batch
        event = trace_batch.events[0]
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
                domain_root=trace_batch.domain_root,
                scope_ref=trace_batch.scope_ref,
                stream_ref=trace_batch.stream_ref,
                transition_id=trace_batch.transition_id,
                events=(substituted,),
            ),
        )

    reader.view_mutator = mutate_trace
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_hybrid_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=reader,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("grant_expected_revision", True),
        ("grant_expected_root", "not-a-root"),
        ("lifecycle_expected_revision", False),
        ("lifecycle_expected_root", "sha256:BAD"),
    ),
)
def test_stored_session_read_preconditions_require_exact_protocol_types(
    field: str,
    value: object,
) -> None:
    context = _context(scope_ref=f"scope:hybrid-replay-binding-{field}")
    step = _step()
    request = _request(
        context,
        step,
        advance_ref=f"advance:binding:{field}",
        current_step=1,
    )
    assert _advance_with_open_session(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    reader = _ObservingStore(context.store, context.domain.domain_root)

    def mutate_binding(view: GovernanceCommitViewV2) -> None:
        assert view.committed_transition is not None
        transition = view.committed_transition.batch.transition
        assert transition is not None
        records = cast(dict[str, Any], _plain_mapping(transition.state_records))
        binding = cast(dict[str, Any], records["session_binding"])
        binding[field] = value
        object.__setattr__(transition, "state_records", records)

    reader.view_mutator = mutate_binding
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_hybrid_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=reader,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "inclusion_delete",
        "inclusion_replace",
        "batch_delete",
        "position_forge",
    ),
)
def test_untrusted_commit_view_artifacts_fail_closed_without_writes(
    mutation: str,
) -> None:
    context, store = _observed_context(
        scope_ref=f"scope:hybrid-replay-untrusted-view:{mutation}"
    )
    source = _evaluate_bounded_source(context, 1)
    request = _request_from_source(
        context,
        source,
        advance_ref=f"advance:untrusted-view:{mutation}",
    )
    assert _advance_source(context, request, source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    verified = rehydrate_hybrid_replay_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )

    def mutate(view: GovernanceCommitViewV2) -> None:
        assert view.committed_transition is not None
        committed = view.committed_transition
        if mutation == "inclusion_delete":
            object.__setattr__(committed, "inclusion_proof", None)
        elif mutation == "inclusion_replace":
            replacement = replace(
                committed.inclusion_proof,
                transition_id="transition:foreign-inclusion",
                inclusion_root="",
            )
            object.__setattr__(committed, "inclusion_proof", replacement)
        elif mutation == "batch_delete":
            object.__setattr__(committed, "batch", None)
        else:
            assert view.position_observation is not None
            forged = replace(
                view.position_observation,
                observed_revision=view.position_observation.observed_revision + 1,
                observed_head_root="sha256:" + "d" * 64,
                position=GovernanceCommitPositionV2.SUPERSEDED,
                observation_root="",
            )
            object.__setattr__(view, "position_observation", forged)

    store.view_mutator = mutate
    store.reset_counts()
    session = open_hybrid_replay_authority_session_v2(
        context.capability,
        request,
    )
    retried = advance_hybrid_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    _assert_failure(
        retried,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
    )
    assert store.atomic_commits == 0
    assert not hybrid_replay_state_is_current_v2(verified)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as current_caught:
        require_current_hybrid_replay_state_v2(verified)
    assert current_caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rehydrate_caught:
        rehydrate_hybrid_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert rehydrate_caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 1
    )


def _plain_mapping(value: object) -> object:
    if isinstance(value, dict):
        return {key: _plain_mapping(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _plain_mapping(item) for key, item in cast(Any, value).items()}
    if isinstance(value, (list, tuple)):
        return [_plain_mapping(item) for item in value]
    return value
