from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import copy, deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest

from pheroos.governance import replay_state_from_hybrid_step
from pheroos.governance._authority_session_v2.operations import (
    bind_governance_issuer_capability_v2,
)
from pheroos.governance._authority_store_v2_contracts.batch import (
    GovernanceCommitBatchV2,
    GovernanceTraceBatchV2,
)
from pheroos.governance._authority_store_v2_contracts.domain import (
    PreparedGovernanceTransitionV2,
)
from pheroos.governance._authority_store_v2_contracts.receipt import (
    GovernanceCommitInclusionProofV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitReceiptV2,
    GovernanceCommittedTransitionV2,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance._hybrid_replay_v2.source import VerifiedHybridSourceStepV2
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.hybrid_replay_v2 import (
    HybridReplayAdvanceRequestV2,
    VerifiedHybridReplayStateV2,
    advance_hybrid_replay_state_v2,
    hybrid_replay_state_is_current_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
)
from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent
from tests.governance.test_hybrid_replay_v2_operations import (
    _Context,
    _advance,
    _assert_failure,
    _context,
    _request,
    _source_for,
)
from tests.governance.test_hybrid_replay_v2_projection import (
    _step,
    _with_snapshot_mutation,
)


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_plain(item) for item in cast(list[object] | tuple[object, ...], value)]
    return value


class _CanonicalViewStore:
    """Delegating Store that can substitute a separately canonical commit view."""

    def __init__(self, store: GovernanceStateStoreV2) -> None:
        self.store = store
        self.view_builder: (
            Callable[[GovernanceCommitViewV2], GovernanceCommitViewV2] | None
        ) = None

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Mapping[str, Any]:
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_builder is None:
            return view
        return self.view_builder(view)

    def atomic_commit_v2(
        self, batch: GovernanceCommitBatchV2
    ) -> GovernanceCommitAttemptV2:
        return self.store.atomic_commit_v2(batch)


def _canonical_context(scope_ref: str) -> tuple[_Context, _CanonicalViewStore]:
    base = _context(scope_ref=scope_ref)
    store = _CanonicalViewStore(base.store)
    capability = bind_governance_issuer_capability_v2(
        cast(GovernanceStateStoreV2, store),
        base.domain,
        base.grant,
        "run:hybrid-replay",
        3,
    )
    return (
        _Context(base.domain, cast(Any, store), base.grant, capability),
        store,
    )


def _rebuild_view(
    view: GovernanceCommitViewV2,
    *,
    state_records: Mapping[str, Any] | None = None,
    read_set: GovernanceAuthorityReadSetV2 | None = None,
    trace_events: tuple[TraceEvent, ...] | None = None,
) -> GovernanceCommitViewV2:
    committed = view.committed_transition
    assert committed is not None
    base_batch = committed.batch
    base_transition = base_batch.transition
    assert base_transition is not None
    selected_read_set = read_set or base_batch.read_set
    target = next(
        item
        for item in selected_read_set.entries
        if item.stream_ref == base_batch.stream_ref
    )
    transition = PreparedGovernanceTransitionV2(
        domain_root=base_batch.domain_root,
        scope_ref=base_batch.scope_ref,
        stream_ref=base_batch.stream_ref,
        transition_id=base_batch.transition_id,
        expected_revision=target.expected_revision,
        expected_root=target.expected_root,
        read_set_root=selected_read_set.root(),
        state_records=(
            base_transition.state_records if state_records is None else state_records
        ),
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=base_batch.domain_root,
        scope_ref=base_batch.scope_ref,
        stream_ref=base_batch.stream_ref,
        transition_id=base_batch.transition_id,
        events=trace_events or base_batch.trace_batch.events,
    )
    batch = GovernanceCommitBatchV2(
        domain=base_batch.domain,
        scope_ref=base_batch.scope_ref,
        stream_ref=base_batch.stream_ref,
        transition_id=base_batch.transition_id,
        kind="transition",
        read_set=selected_read_set,
        trace_batch=trace_batch,
        transition=transition,
    )
    revision = transition.expected_revision + 1
    head = GovernanceHeadV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        revision=revision,
        parent_root=transition.expected_root,
        state_root=transition.state_root,
        transition_id=batch.transition_id,
        batch_root=batch.batch_root,
    )
    receipt = GovernanceCommitReceiptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=revision,
        parent_root=transition.expected_root,
        head_root=head.head_root,
        state_root=transition.state_root,
        read_set_root=selected_read_set.root(),
        trace_root=trace_batch.trace_root,
        batch_root=batch.batch_root,
    )
    inclusion = GovernanceCommitInclusionProofV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=revision,
        batch_root=batch.batch_root,
        receipt_root=receipt.receipt_root,
        head_root=receipt.head_root,
    )
    rebuilt = GovernanceCommittedTransitionV2(
        batch=batch,
        receipt=receipt,
        inclusion_proof=inclusion,
    )
    position = GovernanceCommitPositionObservationV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        receipt_root=receipt.receipt_root,
        observed_revision=revision,
        observed_head_root=receipt.head_root,
        position=GovernanceCommitPositionV2.CURRENT,
    )
    return GovernanceCommitViewV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=rebuilt,
        position_observation=position,
        observed_revision=position.observed_revision,
        observed_head_root=position.observed_head_root,
    )


def _committed_fixture(
    scope_ref: str,
) -> tuple[
    _Context,
    _CanonicalViewStore,
    HybridReplayAdvanceRequestV2,
    GovernanceCommitAttemptV2,
]:
    context, store = _canonical_context(scope_ref)
    step = _step()
    request = _request(
        context,
        step,
        advance_ref=f"advance:{scope_ref}",
        current_step=1,
    )
    committed = _advance(context, request, step)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    return context, store, request, committed


def test_verified_state_exposes_all_reverified_properties_and_object_guards() -> None:
    context, _, request, _ = _committed_fixture("scope:hybrid-replay-state-properties")
    state = rehydrate_hybrid_replay_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )

    assert repr(state) == "<VerifiedHybridReplayStateV2 redacted>"
    assert copy(state) is state
    assert deepcopy(state) is state
    assert state.request_root == request.request_root
    assert state.stream_ref == request.stream_ref
    assert state.transition_id == request.transition_id
    assert state.observed_head_root.startswith("sha256:")
    with pytest.raises(AttributeError, match="immutable"):
        state.extra = "forbidden"  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="not portable"):
        state.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        state.__getstate__()
    with pytest.raises(TypeError, match="final"):

        class _ForbiddenState(VerifiedHybridReplayStateV2):
            pass


def test_public_operations_reject_wrong_request_domain_reader_and_broken_handle() -> (
    None
):
    context, _, request, _ = _committed_fixture("scope:hybrid-replay-public-validation")
    with pytest.raises(TypeError, match="exact HybridReplayAdvanceRequestV2"):
        open_hybrid_replay_authority_session_v2(
            context.capability,
            object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="exact AuthorityDomainV2"):
        rehydrate_hybrid_replay_state_v2(
            request,
            domain=object(),  # type: ignore[arg-type]
            state_reader=context.store,
        )
    with pytest.raises(TypeError, match="StateReader v2"):
        rehydrate_hybrid_replay_state_v2(
            request,
            domain=context.domain,
            state_reader=object(),  # type: ignore[arg-type]
        )

    broken = object.__new__(VerifiedHybridReplayStateV2)
    assert not hybrid_replay_state_is_current_v2(broken)

    state = rehydrate_hybrid_replay_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )
    object.__setattr__(state, "_request", object())
    assert not hybrid_replay_state_is_current_v2(state)
    state = rehydrate_hybrid_replay_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )
    object.__setattr__(state, "_receipt_root", 1)
    assert not hybrid_replay_state_is_current_v2(state)


def test_advance_rejects_malformed_source_and_dynamically_nonconforming_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(scope_ref="scope:hybrid-replay-malformed-source")
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:malformed-source",
        current_step=1,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    malformed = object.__new__(VerifiedHybridSourceStepV2)
    attempt = advance_hybrid_replay_state_v2(
        request,
        source=malformed,
        authority_session=session,
    )
    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    )

    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    monkeypatch.delattr(InMemoryGovernanceStateStoreV2, "atomic_commit_v2")
    attempt = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )
    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
    )


def _second_request(
    context: _Context,
    first_step: Any,
    first: HybridReplayAdvanceRequestV2,
    *,
    suffix: str,
) -> tuple[Any, HybridReplayAdvanceRequestV2]:
    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_id=f"trace:adjustment:{suffix}",
    )
    second = _request(
        context,
        second_step,
        advance_ref=f"advance:{suffix}",
        current_step=2,
        parent=first.snapshot,
    )
    return second_step, second


def _remove_parent_replay_receipt(snapshot: dict[str, Any]) -> None:
    snapshot["replay_receipts"] = [
        receipt
        for receipt in snapshot["replay_receipts"]
        if receipt["event_id"] != "trace:adjustment:one"
    ]


def test_advance_rejects_missing_or_substituted_parent_before_source_use() -> None:
    context = _context(scope_ref="scope:hybrid-replay-parent-missing")
    first_step = _step()
    first = _request(
        context,
        first_step,
        advance_ref="advance:uncommitted-parent",
        current_step=1,
    )
    _, second = _second_request(context, first_step, first, suffix="missing-parent")
    session = open_hybrid_replay_authority_session_v2(context.capability, second)
    missing = advance_hybrid_replay_state_v2(
        second,
        source=_source_for(second),
        authority_session=session,
    )
    _assert_failure(
        missing,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
    )

    context = _context(scope_ref="scope:hybrid-replay-parent-root")
    first_step = _step()
    first = _request(
        context,
        first_step,
        advance_ref="advance:committed-parent",
        current_step=1,
    )
    assert _advance(context, first, first_step).committed_transition is not None
    _, second = _second_request(context, first_step, first, suffix="parent-root")
    substituted = _with_snapshot_mutation(
        second,
        lambda snapshot: snapshot.__setitem__(
            "parent_snapshot_root", "sha256:" + "e" * 64
        ),
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, substituted)
    mismatch = advance_hybrid_replay_state_v2(
        substituted,
        source=_source_for(second),
        authority_session=session,
    )
    _assert_failure(
        mismatch,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    (
        (
            lambda snapshot: snapshot["candidate_projection"]["candidates"][
                0
            ].__setitem__("safe_fallback", True),
            "/snapshot",
        ),
        (
            lambda snapshot: snapshot.__setitem__("current_step", 1),
            "/snapshot/revision",
        ),
        (
            _remove_parent_replay_receipt,
            "/snapshot/replay_receipts",
        ),
    ),
)
def test_advance_rejects_each_continuity_substitution(
    mutation: Callable[[dict[str, Any]], None],
    expected_path: str,
) -> None:
    context = _context(
        scope_ref=f"scope:hybrid-replay-continuity:{expected_path.rsplit('/', 1)[-1]}"
    )
    first_step = _step()
    first = _request(
        context,
        first_step,
        advance_ref="advance:continuity-parent",
        current_step=1,
    )
    assert _advance(context, first, first_step).committed_transition is not None
    _, second = _second_request(context, first_step, first, suffix="continuity-child")
    substituted = _with_snapshot_mutation(second, mutation)
    session = open_hybrid_replay_authority_session_v2(context.capability, substituted)
    attempt = advance_hybrid_replay_state_v2(
        substituted,
        source=_source_for(second),
        authority_session=session,
    )
    assert attempt.failure is not None
    assert attempt.failure.path == expected_path


def _invalid_view(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
    return GovernanceCommitViewV2(
        domain_root=view.domain_root,
        scope_ref=view.scope_ref,
        stream_ref=view.stream_ref,
        transition_id=view.transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.INVALID,
        failure=GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            path="/transition_id",
            stage=GovernanceFailureStageV2.LOAD,
        ),
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )


def test_parent_invalid_view_and_canonical_malformed_state_fail_closed() -> None:
    context, store, first, _ = _committed_fixture(
        "scope:hybrid-replay-parent-invalid-view"
    )
    first_step = _step()
    _, second = _second_request(context, first_step, first, suffix="invalid-parent")
    store.view_builder = lambda view: (
        _invalid_view(view) if view.transition_id == first.transition_id else view
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, second)
    attempt = advance_hybrid_replay_state_v2(
        second,
        source=_source_for(second),
        authority_session=session,
    )
    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
    )

    context, store, first, _ = _committed_fixture(
        "scope:hybrid-replay-parent-malformed-state"
    )
    first_step = _step()
    _, second = _second_request(context, first_step, first, suffix="malformed-parent")

    def malformed(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        if view.transition_id != first.transition_id:
            return view
        assert view.committed_transition is not None
        transition = view.committed_transition.batch.transition
        assert transition is not None
        state = cast(dict[str, Any], _plain(transition.state_records))
        state.pop("schema")
        return _rebuild_view(view, state_records=state)

    store.view_builder = malformed
    session = open_hybrid_replay_authority_session_v2(context.capability, second)
    attempt = advance_hybrid_replay_state_v2(
        second,
        source=_source_for(second),
        authority_session=session,
    )
    _assert_failure(
        attempt,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda state: state.pop("schema"),
        lambda state: state.__setitem__("schema", "unsupported"),
        lambda state: state.__setitem__("snapshot_root", "sha256:" + "a" * 64),
        lambda state: state.__setitem__("session_binding", {}),
        lambda state: state["session_binding"].__setitem__("run_ref", "run:other"),
        lambda state: state["session_binding"].__setitem__("grant_ref", ""),
    ),
)
def test_rehydrate_rejects_canonical_semantic_state_substitution(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    context, store, request, _ = _committed_fixture(
        f"scope:hybrid-replay-state-substitution:{id(mutate)}"
    )

    def rebuild(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        assert view.committed_transition is not None
        transition = view.committed_transition.batch.transition
        assert transition is not None
        state = cast(dict[str, Any], _plain(transition.state_records))
        mutate(state)
        return _rebuild_view(view, state_records=state)

    store.view_builder = rebuild
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        rehydrate_hybrid_replay_state_v2(
            request,
            domain=context.domain,
            state_reader=context.store,
        )


def test_rehydrate_rejects_receipt_trace_and_read_set_semantic_substitution() -> None:
    context, store, request, _ = _committed_fixture(
        "scope:hybrid-replay-receipt-substitution"
    )

    def receipt_revision(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        assert view.committed_transition is not None
        entries = list(view.committed_transition.batch.read_set.entries)
        target_index = next(
            index
            for index, item in enumerate(entries)
            if item.stream_ref == request.stream_ref
        )
        entries[target_index] = replace(entries[target_index], expected_revision=1)
        return _rebuild_view(
            view,
            read_set=GovernanceAuthorityReadSetV2(entries=tuple(entries)),
        )

    store.view_builder = receipt_revision
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        rehydrate_hybrid_replay_state_v2(
            request,
            domain=context.domain,
            state_reader=context.store,
        )

    context, store, request, _ = _committed_fixture(
        "scope:hybrid-replay-trace-substitution"
    )

    def trace(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        assert view.committed_transition is not None
        event = view.committed_transition.batch.trace_batch.events[0]
        changed = TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason="semantically substituted reason",
            lineage=dict(event.lineage),
        )
        return _rebuild_view(view, trace_events=(changed,))

    store.view_builder = trace
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        rehydrate_hybrid_replay_state_v2(
            request,
            domain=context.domain,
            state_reader=context.store,
        )

    context, store, request, _ = _committed_fixture(
        "scope:hybrid-replay-read-set-substitution"
    )

    def read_set(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        assert view.committed_transition is not None
        entries = (
            *view.committed_transition.batch.read_set.entries,
            GovernanceReadPreconditionV2(
                stream_ref="authority:unexpected",
                expected_revision=0,
                expected_root="sha256:" + "b" * 64,
            ),
        )
        return _rebuild_view(
            view,
            read_set=GovernanceAuthorityReadSetV2(
                entries=tuple(
                    sorted(entries, key=lambda item: item.stream_ref.encode())
                )
            ),
        )

    store.view_builder = read_set
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        rehydrate_hybrid_replay_state_v2(
            request,
            domain=context.domain,
            state_reader=context.store,
        )


def test_retry_matcher_and_expected_request_reject_semantic_substitution() -> None:
    context, store, request, _ = _committed_fixture("scope:hybrid-replay-retry-matcher")

    def malformed(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        assert view.committed_transition is not None
        transition = view.committed_transition.batch.transition
        assert transition is not None
        state = cast(dict[str, Any], _plain(transition.state_records))
        state.pop("schema")
        return _rebuild_view(view, state_records=state)

    store.view_builder = malformed
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    attempt = advance_hybrid_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID

    context, _, request, _ = _committed_fixture(
        "scope:hybrid-replay-request-substitution"
    )
    substituted = _with_snapshot_mutation(
        request,
        lambda snapshot: snapshot.__setitem__("source_step_root", "sha256:" + "c" * 64),
    )
    with pytest.raises(Exception, match="authority_binding_mismatch"):
        rehydrate_hybrid_replay_state_v2(
            substituted,
            domain=context.domain,
            state_reader=context.store,
        )
