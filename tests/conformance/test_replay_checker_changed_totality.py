from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from pheroos.conformance.checks import (
    _commit_replay_v2_finality_support as commit_finality,
)
from pheroos.conformance.checks import (
    _commit_replay_v2_integrity_support as commit_integrity,
)
from pheroos.conformance.checks import (
    _commit_replay_v2_race_support as commit_race,
)
from pheroos.conformance.checks import (
    _commit_replay_v2_resource_support as commit_resource,
)
from pheroos.conformance.checks import (
    _hybrid_replay_v2_public_support as hybrid_public,
)
from pheroos.conformance.checks import (
    _hybrid_replay_v2_resource_support as hybrid_resource,
)
from pheroos.conformance.checks import _risk_v2_core_support as risk_core
from pheroos.conformance.checks import _risk_v2_finality_support as risk_finality
from pheroos.conformance.checks import _risk_v2_integrity_support as risk_integrity
from pheroos.conformance.checks import _risk_v2_race_support as risk_race
from pheroos.conformance.checks import _risk_v2_resource_support as risk_resource
from pheroos.conformance.checks import _support_v2_core_support as support_core
from pheroos.conformance.checks import (
    _support_v2_finality_race_support as support_finality,
)
from pheroos.conformance.checks import (
    _support_v2_integrity_support as support_integrity,
)
from pheroos.conformance.checks import commit_replay_v2_contract as commit_contract
from pheroos.conformance.checks import hybrid_replay_v2_contract as hybrid_contract
from pheroos.conformance.checks import risk_v2_contract as risk_contract
from pheroos.conformance.checks import support_v2_contract as support_contract
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


def _adapter() -> ReferenceGovernanceStateStoreConformanceAdapterV2:
    return ReferenceGovernanceStateStoreConformanceAdapterV2()


def _commit_args() -> tuple[Any, Any, Any, Any, Any]:
    return (
        _adapter(),
        commit_contract._context,
        commit_contract._receipt,
        commit_contract._request,
        commit_contract._advance,
    )


def _commit_baseline() -> tuple[Any, Any, Any]:
    context = commit_contract._context(_adapter(), "changed-totality")
    request, source = commit_contract._request(
        context,
        advance_ref="advance:changed-totality",
        receipt=commit_contract._receipt(901, suffix=":changed-totality"),
        current_step=1,
    )
    return context, request, source


def _commit_empty_baseline(label: str) -> Any:
    context = commit_contract._context(_adapter(), label)
    request, _source = commit_contract._request(
        context,
        advance_ref=f"advance:{label}",
        receipt=None,
        current_step=1,
    )
    return request


def _hybrid_args() -> tuple[Any, Any, Any, Any, Any]:
    return (
        _adapter(),
        hybrid_contract._context,
        hybrid_contract._source,
        hybrid_contract._request,
        hybrid_contract._advance,
    )


def _hybrid_baseline(label: str) -> dict[str, object]:
    context = hybrid_contract._context(_adapter(), label)
    source = hybrid_contract._source(context, current_step=1, event_suffix=label)
    request = hybrid_contract._request(
        context,
        source,
        f"advance:{label}",
        observed_epoch=3,
    )
    return request.snapshot.to_dict()


def _risk_args() -> tuple[Any, Any, Any, Any]:
    return (
        _adapter(),
        risk_contract.context_v2,
        risk_contract.request_v2,
        risk_contract.advance_v2,
    )


def test_commit_finality_checker_alarms_on_wrong_failure_and_write_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        commit_finality, "is_commit_replay_failure_v2", lambda *_: False
    )
    monkeypatch.setattr(commit_finality, "commit_replay_head_revision_v2", lambda *_: 9)
    problems: list[str] = []

    commit_finality._evaluate_finality(*_commit_args(), problems)

    assert problems == [
        "reconciliation_finality_unavailable",
        "reconciliation_finality_zero_write",
        "parent_finality_unavailable",
        "parent_finality_zero_write",
        "rehydrate_finality_zero_write",
    ]


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (
            GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/state",
            ),
            ["rehydrate_finality_code"],
        ),
        (None, ["rehydrate_finality_unavailable"]),
    ],
)
def test_commit_finality_checker_alarms_on_rehydrate_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    exception: GovernanceAuthorityBindingErrorV2 | None,
    expected: list[str],
) -> None:
    if exception is None:
        monkeypatch.setattr(
            commit_finality,
            "rehydrate_commit_replay_state_v2",
            lambda *_args, **_kwargs: object(),
        )
    else:

        def raise_wrong(*_args: object, **_kwargs: object) -> object:
            raise exception

        monkeypatch.setattr(
            commit_finality,
            "rehydrate_commit_replay_state_v2",
            raise_wrong,
        )
    problems: list[str] = []

    commit_finality._evaluate_finality(*_commit_args(), problems)

    assert problems == expected


def test_commit_lost_response_checker_alarms_on_publication_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(commit_finality, "commit_replay_head_revision_v2", lambda *_: 9)
    problems: list[str] = []

    commit_finality._evaluate_lost_response(
        _adapter(),
        commit_contract._context,
        commit_contract._receipt,
        commit_contract._request,
        problems,
    )

    assert problems == [
        "post_publication_not_once",
        "canonical_exact_retry",
        "canonical_retry_conflict",
    ]


def test_commit_portability_checker_alarms_on_accepted_raw_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, request, source = _commit_baseline()
    receipt = request.snapshot.receipts[0]
    session = commit_finality.open_commit_replay_authority_session_v2(
        context.capability,
        request,
    )
    monkeypatch.setattr(
        commit_integrity,
        "is_commit_replay_failure_v2",
        lambda *_: False,
    )
    problems: list[str] = []

    commit_integrity._check_portable_source_rejections(
        request,
        source,
        session,
        receipt,
        problems,
    )

    assert problems == [f"portable_source_{index}" for index in range(7)]


def test_commit_authority_checker_alarms_on_cross_context_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context, request, source = _commit_baseline()
    monkeypatch.setattr(
        commit_integrity,
        "advance_commit_replay_state_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED
        ),
    )
    problems: list[str] = []

    commit_integrity._check_cross_authority_rejections(
        request,
        source,
        object(),
        source,
        object(),
        source,
        object(),
        problems,
    )

    assert problems == [
        "same_context_source",
        "cross_context_source",
        "same_context_session",
        "cross_context_session",
    ]


def test_commit_race_checker_alarms_on_revision_and_currentness_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(commit_race, "commit_replay_head_revision_v2", lambda *_: 9)
    monkeypatch.setattr(
        commit_race,
        "require_current_commit_replay_state_v2",
        lambda _state: SimpleNamespace(snapshot_root="sha256:" + "0" * 64),
    )
    problems: list[str] = []

    commit_race._evaluate_two_fork_race(*_commit_args(), problems)

    assert problems == [
        "concurrent_two_fork_revision",
        "superseded_parent_requirement",
        "winning_fork_currentness",
    ]


def test_commit_superseded_checker_alarms_on_wrong_typed_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        commit_race, "commit_replay_state_is_current_v2", lambda _: True
    )

    def wrong_diagnostic(_state: object) -> object:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/state",
        )

    monkeypatch.setattr(
        commit_race,
        "require_current_commit_replay_state_v2",
        wrong_diagnostic,
    )
    problems: list[str] = []

    commit_race._check_superseded_parent(object(), problems)

    assert problems == [
        "superseded_parent_currentness",
        "superseded_parent_diagnostic",
    ]


def test_commit_resource_checker_alarms_on_count_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = commit_contract._context(_adapter(), "resource-count-drift")
    baseline, _source = commit_contract._request(
        context,
        advance_ref="advance:resource-count-drift",
        receipt=None,
        current_step=1,
    )
    monkeypatch.setattr(commit_resource, "_MAX_RECEIPTS", 1)
    monkeypatch.setattr(
        commit_resource,
        "_prepare",
        lambda *_args, **_kwargs: (baseline, object()),
    )
    monkeypatch.setattr(commit_resource, "_snapshot_error", lambda _payload: None)
    problems: list[str] = []

    commit_resource._check_count_bound(baseline, problems)

    assert problems == ["resource_count_exact", "resource_count_over"]


def test_commit_resource_checker_alarms_on_text_boundary_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context, baseline, _source = _commit_baseline()
    monkeypatch.setattr(commit_resource, "_MAX_TEXT_BYTES", 4_095)
    problems: list[str] = []

    commit_resource._check_text_bound(baseline, problems)

    assert problems == ["resource_text_exact", "resource_text_over"]


def test_commit_resource_checker_alarms_on_wrong_overflow_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _context, baseline, _source = _commit_baseline()
    real_receipt = commit_resource.CommitReplayReceiptV2
    calls = 0

    def receipt_factory(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("unexpected diagnostic")
        return real_receipt(*args, **kwargs)

    monkeypatch.setattr(commit_resource, "CommitReplayReceiptV2", receipt_factory)
    problems: list[str] = []

    commit_resource._check_text_bound(baseline, problems)

    assert problems == ["resource_text_over"]


def test_commit_resource_checker_alarms_on_unsatisfiable_snapshot_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _commit_empty_baseline("resource-vector")
    monkeypatch.setattr(commit_resource, "_allocate_text", lambda *_: False)
    problems: list[str] = []

    commit_resource._check_snapshot_and_preflight_bounds(baseline, problems)

    assert problems == ["resource_snapshot_vector"]


def test_commit_resource_checker_alarms_on_exact_snapshot_constructor_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _commit_empty_baseline("resource-exact-constructor")
    real_prepare = commit_resource._prepare
    calls = 0

    def fail_second_prepare(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("injected exact snapshot failure")
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(commit_resource, "_prepare", fail_second_prepare)
    problems: list[str] = []

    commit_resource._check_snapshot_and_preflight_bounds(baseline, problems)

    assert problems == ["resource_snapshot_exact"]


def test_commit_resource_checker_alarms_on_exact_snapshot_size_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _commit_empty_baseline("resource-exact-size")
    real_prepare = commit_resource._prepare
    calls = 0

    def drift_second_prepare(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            return baseline, object()
        return real_prepare(*args, **kwargs)

    monkeypatch.setattr(commit_resource, "_prepare", drift_second_prepare)
    problems: list[str] = []

    commit_resource._check_snapshot_and_preflight_bounds(baseline, problems)

    assert problems == ["resource_snapshot_exact"]


def test_commit_resource_checker_alarms_on_overflow_vector_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _commit_empty_baseline("resource-over-vector")
    real_allocate = commit_resource._allocate_text
    calls = 0

    def fail_second_allocation(*args: object, **kwargs: object) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            return False
        return real_allocate(*args, **kwargs)

    monkeypatch.setattr(commit_resource, "_allocate_text", fail_second_allocation)
    problems: list[str] = []

    commit_resource._check_snapshot_and_preflight_bounds(baseline, problems)

    assert problems == ["resource_snapshot_over_vector"]


def test_commit_resource_checker_alarms_on_missed_snapshot_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _commit_empty_baseline("resource-overflow")
    monkeypatch.setattr(commit_resource, "_prepare_error", lambda *_: None)
    problems: list[str] = []

    commit_resource._check_snapshot_and_preflight_bounds(baseline, problems)

    assert problems == ["resource_snapshot_over"]


def test_commit_resource_checker_alarms_on_preflight_vector_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _commit_empty_baseline("resource-preflight-vector")
    real_allocate = commit_resource._allocate_text
    calls = 0

    def fail_third_allocation(*args: object, **kwargs: object) -> bool:
        nonlocal calls
        calls += 1
        if calls == 3:
            return False
        return real_allocate(*args, **kwargs)

    monkeypatch.setattr(commit_resource, "_allocate_text", fail_third_allocation)
    problems: list[str] = []

    commit_resource._check_snapshot_and_preflight_bounds(baseline, problems)

    assert problems == ["resource_preflight_vector"]


def test_commit_resource_checker_alarms_on_missed_preflight_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _commit_empty_baseline("resource-preflight-overflow")
    monkeypatch.setattr(commit_resource, "_snapshot_replace_error", lambda *_: None)
    problems: list[str] = []

    commit_resource._check_snapshot_and_preflight_bounds(baseline, problems)

    assert problems == ["resource_preflight_over"]


def test_commit_vertical_checker_alarms_on_rehydration_and_currentness_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_rehydrate = commit_contract.rehydrate_commit_replay_state_v2
    calls = 0

    def drift_first_rehydrate(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(position=GovernanceCommitPositionV2.SUPERSEDED)
        return real_rehydrate(*args, **kwargs)

    monkeypatch.setattr(
        commit_contract,
        "rehydrate_commit_replay_state_v2",
        drift_first_rehydrate,
    )
    monkeypatch.setattr(
        commit_contract,
        "commit_replay_state_is_current_v2",
        lambda _state: True,
    )
    problems: list[str] = []

    commit_contract._vertical_restart_and_fork(_adapter(), problems)

    assert problems == ["rehydration", "superseded_parent"]


def test_commit_source_checker_alarms_on_observed_store_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_context = commit_contract._context

    class RevisionDriftStore:
        def __init__(self, store: object) -> None:
            self._store = store

        def __getattr__(self, name: str) -> Any:
            return getattr(self._store, name)

        def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
            return SimpleNamespace(revision=9)

    def drift_context(adapter: object, suffix: str) -> Any:
        context = real_context(adapter, suffix)
        return replace(context, store=RevisionDriftStore(context.store))

    monkeypatch.setattr(commit_contract, "_context", drift_context)
    problems: list[str] = []

    commit_contract._source_and_determinism(_adapter(), problems)

    assert problems == [
        "raw_source_mutation:snapshot",
        "raw_source_mutation:dict",
        "raw_source_mutation:digest",
        "raw_source_mutation:same_shape",
        "transition_conflict_mutation",
    ]


def test_commit_source_checker_alarms_on_accepted_raw_and_conflicting_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_context = commit_contract._context
    real_advance = commit_contract.advance_commit_replay_state_v2
    real_context_advance = commit_contract._advance
    captured: list[Any] = []

    def capture_context(adapter: object, suffix: str) -> Any:
        context = real_context(adapter, suffix)
        captured.append(context)
        return context

    raw_calls = 0

    def accept_raw(
        request: Any,
        *,
        source: object,
        authority_session: object,
    ) -> Any:
        nonlocal raw_calls
        raw_calls += 1
        if raw_calls <= 4:
            _rebuilt, verified = commit_contract._request(
                captured[0],
                advance_ref="advance:deterministic",
                receipt=commit_contract._receipt(9),
                current_step=1,
            )
            source = verified
        return real_advance(
            request,
            source=source,
            authority_session=authority_session,
        )

    context_advance_calls = 0

    def accept_conflict(context: Any, request: Any, source: object) -> Any:
        nonlocal context_advance_calls
        context_advance_calls += 1
        if context_advance_calls == 1:
            return SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.COMMITTED,
                failure=None,
            )
        return real_context_advance(context, request, source)

    monkeypatch.setattr(commit_contract, "_context", capture_context)
    monkeypatch.setattr(commit_contract, "advance_commit_replay_state_v2", accept_raw)
    monkeypatch.setattr(commit_contract, "_advance", accept_conflict)
    problems: list[str] = []

    commit_contract._source_and_determinism(_adapter(), problems)

    assert problems == [
        "raw_source:snapshot",
        "raw_source_mutation:snapshot",
        "raw_source:dict",
        "raw_source_mutation:dict",
        "raw_source:digest",
        "raw_source_mutation:digest",
        "raw_source:same_shape",
        "raw_source_mutation:same_shape",
        "transition_conflict",
    ]


def test_hybrid_vertical_checker_alarms_on_incomplete_receipt_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_request = hybrid_contract._request
    real_advance = hybrid_contract._advance

    class ReceiptProjection:
        def __init__(self, snapshot: object) -> None:
            self._snapshot = snapshot
            self.replay_receipts: tuple[object, ...] = ()

        def __getattr__(self, name: str) -> Any:
            return getattr(self._snapshot, name)

    class RequestProjection:
        def __init__(self, request: object) -> None:
            self._request = request
            self.snapshot = ReceiptProjection(request.snapshot)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._request, name)

    calls = 0

    def project_first_request(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        request = real_request(*args, **kwargs)
        calls += 1
        return RequestProjection(request) if calls == 1 else request

    def unwrap_advance(context: Any, request: Any, source: object) -> Any:
        return real_advance(context, getattr(request, "_request", request), source)

    monkeypatch.setattr(hybrid_contract, "_request", project_first_request)
    monkeypatch.setattr(hybrid_contract, "_advance", unwrap_advance)
    problems: list[str] = []

    hybrid_contract._evaluate_vertical_restart_and_fork(_adapter(), problems)

    assert problems == ["complete_hybrid_receipts"]


def test_hybrid_vertical_checker_alarms_on_rehydration_and_currentness_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_rehydrate = hybrid_contract.rehydrate_hybrid_replay_state_v2
    real_current = hybrid_contract.hybrid_replay_state_is_current_v2
    rehydrate_calls = 0
    current_calls = 0

    def drift_first_rehydrate(*args: object, **kwargs: object) -> Any:
        nonlocal rehydrate_calls
        rehydrate_calls += 1
        if rehydrate_calls == 1:
            return object()
        return real_rehydrate(*args, **kwargs)

    def drift_parent_current(state: object) -> bool:
        nonlocal current_calls
        current_calls += 1
        return True if current_calls == 1 else real_current(state)

    monkeypatch.setattr(
        hybrid_contract,
        "rehydrate_hybrid_replay_state_v2",
        drift_first_rehydrate,
    )
    monkeypatch.setattr(
        hybrid_contract,
        "hybrid_replay_state_is_current_v2",
        drift_parent_current,
    )
    problems: list[str] = []

    hybrid_contract._evaluate_vertical_restart_and_fork(_adapter(), problems)

    assert problems == ["current_rehydration", "successor_supersedes_parent"]


def test_hybrid_source_checker_alarms_on_store_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_context = hybrid_contract._context

    class RevisionDriftStore:
        def __init__(self, store: object) -> None:
            self._store = store

        def __getattr__(self, name: str) -> Any:
            return getattr(self._store, name)

        def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
            return SimpleNamespace(revision=9)

    def drift_context(adapter: object, suffix: str) -> Any:
        context = real_context(adapter, suffix)
        return replace(context, store=RevisionDriftStore(context.store))

    monkeypatch.setattr(hybrid_contract, "_context", drift_context)
    problems: list[str] = []

    hybrid_contract._evaluate_source_context_substitution(_adapter(), problems)

    assert problems == ["source_rejection_before_mutation"]


def test_hybrid_public_finality_checker_alarms_on_unexpected_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hybrid_public, "_is_failure", lambda *_: False)
    problems: list[str] = []

    hybrid_public._evaluate_public_finality_and_reconciliation(
        *_hybrid_args(),
        problems,
    )

    assert problems == [
        "reconciliation_finality_unavailable",
        "historical_parent_finality_unavailable",
        "post_publication_lost_response",
        "canonical_reconciliation_conflict",
    ]


def test_hybrid_public_finality_checker_alarms_on_write_observation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_reset = hybrid_public._PublicHybridFaultStoreV2.reset_observations

    def drift_reset(store: Any) -> None:
        real_reset(store)
        store.atomic_commits = 9

    monkeypatch.setattr(
        hybrid_public._PublicHybridFaultStoreV2,
        "reset_observations",
        drift_reset,
    )
    problems: list[str] = []

    hybrid_public._evaluate_public_finality_and_reconciliation(
        *_hybrid_args(),
        problems,
    )

    assert problems == [
        "reconciliation_finality_zero_write",
        "historical_parent_finality_zero_write",
        "post_publication_was_not_published_once",
        "complete_canonical_exact_reconciliation",
        "canonical_reconciliation_conflict",
    ]


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (
            GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/state",
            ),
            ["rehydrate_finality_code"],
        ),
        (None, ["rehydrate_finality_unavailable"]),
    ],
)
def test_hybrid_public_finality_checker_alarms_on_rehydrate_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    exception: GovernanceAuthorityBindingErrorV2 | None,
    expected: list[str],
) -> None:
    real_rehydrate = hybrid_public.rehydrate_hybrid_replay_state_v2
    calls = 0

    def drift_second_rehydrate(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            if exception is not None:
                raise exception
            return object()
        return real_rehydrate(*args, **kwargs)

    monkeypatch.setattr(
        hybrid_public,
        "rehydrate_hybrid_replay_state_v2",
        drift_second_rehydrate,
    )
    problems: list[str] = []

    hybrid_public._evaluate_public_finality_and_reconciliation(
        *_hybrid_args(),
        problems,
    )

    assert problems == expected


def test_hybrid_lost_response_checker_alarms_on_missing_commit_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_fault_context = hybrid_public._fault_context
    real_advance = hybrid_public.advance_hybrid_replay_state_v2
    real_load = hybrid_public._PublicHybridFaultStoreV2.load_commit_view_v2
    captured: list[Any] = []
    advance_calls = 0

    def capture_context(*args: object, **kwargs: object) -> Any:
        context, store = real_fault_context(*args, **kwargs)
        captured.append(store)
        return context, store

    def arm_missing_view(*args: object, **kwargs: object) -> Any:
        nonlocal advance_calls
        result = real_advance(*args, **kwargs)
        advance_calls += 1
        if advance_calls == 2:
            captured[0].raise_next_commit_view = True
        return result

    def missing_view_once(store: Any, *args: object, **kwargs: object) -> Any:
        if getattr(store, "raise_next_commit_view", False):
            store.raise_next_commit_view = False
            raise KeyError("injected missing public commit view")
        return real_load(store, *args, **kwargs)

    monkeypatch.setattr(hybrid_public, "_fault_context", capture_context)
    monkeypatch.setattr(
        hybrid_public, "advance_hybrid_replay_state_v2", arm_missing_view
    )
    monkeypatch.setattr(
        hybrid_public._PublicHybridFaultStoreV2,
        "load_commit_view_v2",
        missing_view_once,
    )
    problems: list[str] = []

    hybrid_public._evaluate_lost_response_reconciliation(
        _adapter(),
        hybrid_contract._context,
        hybrid_contract._source,
        hybrid_contract._request,
        problems,
    )

    assert problems == ["complete_canonical_exact_reconciliation"]


def test_hybrid_integrity_checker_alarms_on_reconciliation_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected reconciliation exception")

    monkeypatch.setattr(
        hybrid_public,
        "open_hybrid_replay_authority_session_v2",
        explode,
    )
    problems: list[str] = []

    hybrid_public._evaluate_public_historical_integrity(
        *_hybrid_args(),
        problems,
    )

    assert problems == [
        f"public-canonical-view-{mutation}_reconciliation_exception"
        for mutation in (
            "inclusion_delete",
            "batch_delete",
            "position_delete",
            "position_forge_superseded",
        )
    ]


def test_hybrid_integrity_checker_alarms_on_non_fail_closed_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hybrid_public, "_is_failure", lambda *_: False)
    problems: list[str] = []

    hybrid_public._evaluate_public_historical_integrity(
        *_hybrid_args(),
        problems,
    )

    assert problems == [
        f"public-canonical-view-{mutation}_reconciliation"
        for mutation in (
            "inclusion_delete",
            "batch_delete",
            "position_delete",
            "position_forge_superseded",
        )
    ]


def test_hybrid_invalid_rehydrate_checker_alarms_on_wrong_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def wrong_diagnostic(*_args: object, **_kwargs: object) -> object:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/state",
        )

    monkeypatch.setattr(
        hybrid_public,
        "rehydrate_hybrid_replay_state_v2",
        wrong_diagnostic,
    )
    problems: list[str] = []

    hybrid_public._expect_invalid_rehydration(
        SimpleNamespace(domain=object(), store=object()),
        SimpleNamespace(to_dict=lambda: {}),
        "wrong_rehydrate_diagnostic",
        problems,
    )

    assert problems == ["wrong_rehydrate_diagnostic"]


def test_hybrid_resource_checker_alarms_on_negative_snapshot_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _hybrid_baseline("hybrid-resource-negative")
    monkeypatch.setattr(hybrid_resource, "_FINAL_SNAPSHOT_TRAILS_V2", 1)
    monkeypatch.setattr(hybrid_resource, "_MAX_SNAPSHOT_BYTES_V2", 0)
    monkeypatch.setattr(
        hybrid_resource.HybridReplaySnapshotV2,
        "from_dict",
        staticmethod(lambda _payload: SimpleNamespace(canonical_bytes=lambda: b"x")),
    )
    problems: list[str] = []

    hybrid_resource._check_final_snapshot_bound(baseline, problems)

    assert problems == ["resource_snapshot_vector"]


def test_hybrid_resource_checker_alarms_on_unsatisfiable_quote_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _hybrid_baseline("hybrid-resource-quotes")
    monkeypatch.setattr(hybrid_resource, "_FINAL_SNAPSHOT_TRAILS_V2", 1)
    monkeypatch.setattr(hybrid_resource, "_MAX_SNAPSHOT_BYTES_V2", 10_000)
    monkeypatch.setattr(
        hybrid_resource.HybridReplaySnapshotV2,
        "from_dict",
        staticmethod(lambda _payload: SimpleNamespace(canonical_bytes=lambda: b"x")),
    )
    problems: list[str] = []

    hybrid_resource._check_final_snapshot_bound(baseline, problems)

    assert problems == ["resource_snapshot_vector"]


def test_hybrid_resource_checker_alarms_on_exact_snapshot_constructor_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _hybrid_baseline("hybrid-resource-constructor")
    monkeypatch.setattr(hybrid_resource, "_FINAL_SNAPSHOT_TRAILS_V2", 1)
    monkeypatch.setattr(hybrid_resource, "_MAX_SNAPSHOT_BYTES_V2", 1)
    calls = 0

    def fail_second(_payload: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("injected exact snapshot constructor failure")
        return SimpleNamespace(canonical_bytes=lambda: b"x")

    monkeypatch.setattr(
        hybrid_resource.HybridReplaySnapshotV2,
        "from_dict",
        staticmethod(fail_second),
    )
    problems: list[str] = []

    hybrid_resource._check_final_snapshot_bound(baseline, problems)

    assert problems == ["resource_snapshot_exact"]


def test_hybrid_resource_checker_alarms_on_exact_snapshot_size_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _hybrid_baseline("hybrid-resource-size")
    monkeypatch.setattr(hybrid_resource, "_FINAL_SNAPSHOT_TRAILS_V2", 1)
    monkeypatch.setattr(hybrid_resource, "_MAX_SNAPSHOT_BYTES_V2", 1)
    calls = 0

    def drift_second(_payload: object) -> Any:
        nonlocal calls
        calls += 1
        payload = b"x" if calls == 1 else b""
        return SimpleNamespace(canonical_bytes=lambda: payload)

    monkeypatch.setattr(
        hybrid_resource.HybridReplaySnapshotV2,
        "from_dict",
        staticmethod(drift_second),
    )
    problems: list[str] = []

    hybrid_resource._check_final_snapshot_bound(baseline, problems)

    assert problems == ["resource_snapshot_exact"]


def test_risk_vertical_checker_alarms_on_rehydration_and_currentness_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_rehydrate = risk_core.rehydrate_risk_state_v2
    calls = 0

    def drift_first_rehydrate(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return object()
        return real_rehydrate(*args, **kwargs)

    monkeypatch.setattr(risk_core, "rehydrate_risk_state_v2", drift_first_rehydrate)
    monkeypatch.setattr(risk_core, "risk_state_is_current_v2", lambda _state: True)
    problems: list[str] = []

    risk_core._vertical_restart_linearity(_adapter(), problems)

    assert problems == ["current_rehydration", "successor_supersedes_parent"]


def test_risk_fixed_lineage_checker_alarms_on_stream_identity_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_request = risk_core.request_v2

    def drift_proposal_stream(*args: object, **kwargs: object) -> Any:
        if str(kwargs.get("advance_ref", "")).startswith(
            "advance:fixed-lineage:proposal:"
        ):
            return SimpleNamespace(stream_ref="risk:drifted-stream"), object()
        return real_request(*args, **kwargs)

    monkeypatch.setattr(risk_core, "request_v2", drift_proposal_stream)
    problems: list[str] = []

    risk_core._fixed_lineage_epoch_jump(_adapter(), problems)

    assert problems == ["fixed_lineage_130_portable_epochs"]


def test_risk_fixed_lineage_checker_alarms_on_currentness_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(risk_core, "risk_state_is_current_v2", lambda _state: True)
    problems: list[str] = []

    risk_core._fixed_lineage_epoch_jump(_adapter(), problems)

    assert problems == ["fixed_lineage_epoch_130_currentness"]


def test_risk_sealed_domain_checker_alarms_on_non_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(risk_core, "is_failure_v2", lambda *_: False)
    problems: list[str] = []

    risk_core._sealed_domain_matrix(_adapter(), problems)

    assert problems == ["sealed_domain_historical_or_zero_write"]


def test_risk_source_checker_alarms_on_accepted_raw_and_cross_context_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = risk_contract.context_v2(_adapter(), "risk-raw-source-drift")
    request, source = risk_contract.request_v2(
        context,
        advance_ref="advance:risk-raw-source-drift",
    )
    session = risk_core.open_risk_authority_session_v2(context.capability, request)
    monkeypatch.setattr(
        risk_core,
        "advance_risk_state_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED,
        ),
    )
    problems: list[str] = []

    risk_core._raw_source_and_session_binding(
        context,
        request,
        source,
        session,
        problems,
    )

    assert problems == [
        "raw_source:snapshot",
        "raw_source:dict",
        "raw_source:digest",
        "raw_source:same_shape",
        "source_or_session_binding",
    ]


def test_risk_scope_checker_alarms_on_accepted_cross_domain_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = risk_contract.context_v2(_adapter(), "risk-scope-drift")
    request, _source = risk_contract.request_v2(
        context,
        advance_ref="advance:risk-scope-drift",
    )
    session = risk_core.open_risk_authority_session_v2(context.capability, request)
    monkeypatch.setattr(
        risk_core,
        "advance_risk_state_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED,
        ),
    )
    problems: list[str] = []

    risk_core._domain_run_and_issuer_binding(
        _adapter(),
        context,
        request,
        session,
        problems,
    )

    assert problems == ["scope_domain_run_binding"]


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (
            GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
                "/issuer",
            ),
            ["issuer_diagnostic"],
        ),
        (None, ["issuer_binding"]),
    ],
)
def test_risk_issuer_checker_alarms_on_session_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    exception: GovernanceAuthorityBindingErrorV2 | None,
    expected: list[str],
) -> None:
    context = risk_contract.context_v2(_adapter(), "risk-issuer-drift")
    request, _source = risk_contract.request_v2(
        context,
        advance_ref="advance:risk-issuer-drift",
    )
    session = risk_core.open_risk_authority_session_v2(context.capability, request)

    def drift_session(*_args: object, **_kwargs: object) -> object:
        if exception is not None:
            raise exception
        return object()

    monkeypatch.setattr(risk_core, "open_risk_authority_session_v2", drift_session)
    problems: list[str] = []

    risk_core._domain_run_and_issuer_binding(
        _adapter(),
        context,
        request,
        session,
        problems,
    )

    assert problems == expected


def test_risk_selector_checker_alarms_on_unsupported_profile_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = risk_contract.context_v2(_adapter(), "risk-selector-drift")
    monkeypatch.setattr(risk_core, "is_failure_v2", lambda *_: False)
    problems: list[str] = []

    risk_core._selector_and_operation_binding(_adapter(), context, problems)

    assert problems == ["authority_selector"]


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (
            GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/operation",
            ),
            ["operation_diagnostic"],
        ),
        (None, ["operation_denied"]),
    ],
)
def test_risk_operation_checker_alarms_on_session_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    exception: GovernanceAuthorityBindingErrorV2 | None,
    expected: list[str],
) -> None:
    context = risk_contract.context_v2(_adapter(), "risk-operation-drift")

    def drift_session(*_args: object, **_kwargs: object) -> object:
        if exception is not None:
            raise exception
        return object()

    monkeypatch.setattr(risk_core, "open_risk_authority_session_v2", drift_session)
    problems: list[str] = []

    risk_core._selector_and_operation_binding(_adapter(), context, problems)

    assert problems == expected


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (
            GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/state",
            ),
            ["rehydrate_finality_diagnostic"],
        ),
        (None, ["rehydrate_finality_unavailable"]),
    ],
)
def test_risk_finality_checker_alarms_on_rehydrate_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    exception: GovernanceAuthorityBindingErrorV2 | None,
    expected: list[str],
) -> None:
    def drift_rehydrate(*_args: object, **_kwargs: object) -> object:
        if exception is not None:
            raise exception
        return object()

    monkeypatch.setattr(risk_finality, "rehydrate_risk_state_v2", drift_rehydrate)
    problems: list[str] = []

    risk_finality._reconciliation_and_rehydrate_finality(*_risk_args(), problems)

    assert problems == expected


def test_risk_integrity_checker_alarms_on_write_observation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(risk_integrity, "risk_head_revision_v2", lambda *_: 9)
    problems: list[str] = []

    risk_integrity._detached_view_mutation(
        *_risk_args(),
        "inclusion",
        problems,
    )

    assert problems == ["inclusion_zero_write"]


def test_risk_integrity_checker_alarms_on_detached_store_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_rehydrate = risk_integrity.rehydrate_risk_state_v2
    calls = 0

    def drift_recovered_state(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        result = real_rehydrate(*args, **kwargs)
        if calls == 2:
            return SimpleNamespace(
                snapshot=SimpleNamespace(snapshot_root="sha256:" + "0" * 64)
            )
        return result

    monkeypatch.setattr(
        risk_integrity,
        "rehydrate_risk_state_v2",
        drift_recovered_state,
    )
    problems: list[str] = []

    risk_integrity._detached_view_mutation(
        *_risk_args(),
        "inclusion",
        problems,
    )

    assert problems == ["inclusion_detached_store_preservation"]


@pytest.mark.parametrize(
    ("exception", "expected_tail"),
    [
        (
            GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/state",
            ),
            "forged_current_position_diagnostic",
        ),
        (None, "forged_current_position_not_typed"),
    ],
)
def test_risk_forged_position_checker_alarms_on_currentness_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    exception: GovernanceAuthorityBindingErrorV2 | None,
    expected_tail: str,
) -> None:
    monkeypatch.setattr(
        risk_integrity,
        "risk_state_is_current_v2",
        lambda _state: True,
    )

    def drift_current_requirement(_state: object) -> object:
        if exception is not None:
            raise exception
        return object()

    monkeypatch.setattr(
        risk_integrity,
        "require_current_risk_state_v2",
        drift_current_requirement,
    )
    problems: list[str] = []

    risk_integrity._forged_current_position(*_risk_args(), problems)

    assert problems == ["forged_current_position_accepted", expected_tail]


def test_risk_cross_domain_checker_alarms_on_wrong_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def wrong_diagnostic(*_args: object, **_kwargs: object) -> object:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/state",
        )

    monkeypatch.setattr(risk_integrity, "rehydrate_risk_state_v2", wrong_diagnostic)
    problems: list[str] = []

    risk_integrity._cross_domain_rehydration(*_risk_args(), problems)

    assert problems == ["cross_domain_diagnostic"]


def test_risk_race_checker_alarms_on_parent_currentness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(risk_race, "risk_state_is_current_v2", lambda _state: True)
    problems: list[str] = []

    risk_race._fork_race(*_risk_args(), problems)

    assert problems == ["race_32_forks_currentness"]


def test_risk_resource_checker_alarms_on_write_observation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(risk_resource, "risk_head_revision_v2", lambda *_: 9)
    adapter, context_factory, request_factory, advance_factory = _risk_args()

    problems = risk_resource.run_risk_v2_resource_matrix(
        adapter,
        context_factory=context_factory,
        request_factory=request_factory,
        advance_factory=advance_factory,
    )

    assert problems == ["resource_rejection_zero_write"]


def test_risk_resource_checker_alarms_on_exact_text_projection_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = risk_contract.context_v2(_adapter(), "risk-resource-text-drift")
    base, _source = risk_contract.request_v2(
        context,
        advance_ref="advance:risk-resource-text-drift",
    )
    real_replace = risk_resource.replace
    calls = 0

    def drift_exact(*args: object, **kwargs: object) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(assessment_ref="")
        return real_replace(*args, **kwargs)

    monkeypatch.setattr(risk_resource, "replace", drift_exact)
    problems: list[str] = []

    risk_resource._individual_text_bound(base, problems)

    assert problems == ["resource_text_exact"]


def test_support_core_checker_alarms_on_projection_and_evaluation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        support_core,
        "require_current_support_state_v2",
        lambda _state: object(),
    )
    monkeypatch.setattr(support_core, "evaluate_support_v2", lambda **_kwargs: object())
    monkeypatch.setattr(
        support_core,
        "support_lease_status_v2",
        lambda *_args, **_kwargs: support_core.SupportLeaseStatusV2.EXPIRED,
    )
    problems: list[str] = []

    support_core._vertical_restart_and_evaluation(_adapter(), problems)

    assert problems == [
        "initialize_current_projection",
        "public_evaluation",
        "derived_lease_status",
        "restart_rehydrate",
    ]


def test_support_core_checker_alarms_on_revoke_projection_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_revoke = support_core.revoke_v2
    real_advance = support_core.advance_support_v2
    real_check_wire = support_core._check_canonical_wire

    class SnapshotProjection:
        def __init__(self, snapshot: object) -> None:
            self._snapshot = snapshot
            self.leases = (object(),)
            self.history_count = 99

        def __getattr__(self, name: str) -> Any:
            return getattr(self._snapshot, name)

    class RequestProjection:
        def __init__(self, request: object) -> None:
            self._request = request
            self.snapshot = SnapshotProjection(request.snapshot)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._request, name)

    def project_revoke(*args: object, **kwargs: object) -> Any:
        request, source = real_revoke(*args, **kwargs)
        return RequestProjection(request), source

    def unwrap_advance(
        context: Any, request: Any, source: object, **kwargs: object
    ) -> Any:
        return real_advance(
            context,
            getattr(request, "_request", request),
            source,
            **kwargs,
        )

    monkeypatch.setattr(support_core, "revoke_v2", project_revoke)
    monkeypatch.setattr(support_core, "advance_support_v2", unwrap_advance)
    monkeypatch.setattr(support_core, "_check_canonical_wire", lambda *_: None)
    problems: list[str] = []

    support_core._vertical_restart_and_evaluation(_adapter(), problems)

    monkeypatch.setattr(support_core, "_check_canonical_wire", real_check_wire)
    assert problems == ["revoke_projection_or_history", "restart_rehydrate"]


def test_support_upstream_checker_alarms_on_current_projection_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = support_core.context_v2(_adapter(), "support-upstream-drift")
    upstreams = support_core.commit_upstreams_v2(
        context,
        label="support-upstream-drift",
    )
    monkeypatch.setattr(
        support_core,
        "require_current_principal_verification_set_v2",
        lambda _state: object(),
    )
    monkeypatch.setattr(
        support_core,
        "require_current_membership_state_v2",
        lambda _state: object(),
    )
    problems: list[str] = []

    support_core._check_upstream_authority(context, upstreams, problems)

    assert problems == [
        "verification_current_projection",
        "membership_current_projection",
    ]


def test_support_wire_checker_alarms_on_round_trip_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = support_core.context_v2(_adapter(), "support-wire-drift")
    upstreams = support_core.commit_upstreams_v2(
        context,
        label="support-wire-drift",
    )
    request, _source = support_core.initialize_v2(context, "support-wire-drift")

    class DriftVerificationRequest:
        @staticmethod
        def from_dict(_payload: object) -> object:
            return object()

    monkeypatch.setattr(
        support_core,
        "PrincipalVerificationSetAdvanceRequestV2",
        DriftVerificationRequest,
    )
    problems: list[str] = []

    support_core._check_canonical_wire(upstreams, request, problems)

    assert problems == ["canonical_wire_round_trip"]


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (
            GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/state",
            ),
            ["finality_wrong_diagnostic", "tamper_wrong_diagnostic"],
        ),
        (
            None,
            ["finality_not_fail_closed", "tamper_not_fail_closed"],
        ),
    ],
)
def test_support_finality_checker_alarms_on_rehydrate_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
    exception: GovernanceAuthorityBindingErrorV2 | None,
    expected: list[str],
) -> None:
    context = support_finality.context_v2(_adapter(), "support-finality-drift")
    request, source = support_finality.initialize_v2(
        context,
        "support-finality-drift",
    )
    assert support_finality._committed(
        support_finality.advance_support_v2(context, request, source)
    )

    def drift_rehydrate(*_args: object, **_kwargs: object) -> object:
        if exception is not None:
            raise exception
        return object()

    monkeypatch.setattr(
        support_finality,
        "rehydrate_support_state_v2",
        drift_rehydrate,
    )
    problems: list[str] = []

    support_finality._assert_finality_and_tamper_fail_closed(
        context.store,
        context.domain,
        request,
        problems,
    )

    assert problems == expected


def test_support_sealed_checker_alarms_on_exact_retry_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_committed = support_finality._committed
    calls = 0

    def reject_third(attempt: object) -> bool:
        nonlocal calls
        calls += 1
        return False if calls == 3 else real_committed(attempt)

    monkeypatch.setattr(support_finality, "_committed", reject_third)
    problems: list[str] = []

    support_finality._assert_sealed_domain_behavior(_adapter(), problems)

    assert problems == ["sealed_exact_retry"]


def test_support_sealed_checker_alarms_on_new_mutation_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(support_finality, "_failure", lambda *_: False)
    problems: list[str] = []

    support_finality._assert_sealed_domain_behavior(_adapter(), problems)

    assert problems == ["sealed_new_mutation_not_denied"]


def test_support_staleness_checker_alarms_on_non_retry_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(support_integrity, "_failure", lambda *_: False)
    problems: list[str] = []

    support_integrity._stale_parent_and_membership(_adapter(), problems)

    assert problems == [
        "stale_parent_not_retry_required",
        "stale_membership_not_retry_required",
    ]


def test_support_rotation_checker_alarms_on_missing_issued_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_issue = support_integrity.issue_v2
    real_advance = support_integrity.advance_support_v2

    class RequestProjection:
        def __init__(self, request: object) -> None:
            self._request = request
            self.issued_lease = None

        def __getattr__(self, name: str) -> Any:
            return getattr(self._request, name)

    def project_issue(*args: object, **kwargs: object) -> Any:
        request, source = real_issue(*args, **kwargs)
        return RequestProjection(request), source

    def unwrap_advance(
        context: Any, request: Any, source: object, **kwargs: object
    ) -> Any:
        return real_advance(
            context,
            getattr(request, "_request", request),
            source,
            **kwargs,
        )

    monkeypatch.setattr(support_integrity, "issue_v2", project_issue)
    monkeypatch.setattr(support_integrity, "advance_support_v2", unwrap_advance)
    problems: list[str] = []

    support_integrity._issuer_rotation(_adapter(), problems)

    assert problems == ["issuer_rotation_missing_lease"]


def test_support_rotation_checker_alarms_on_lineage_projection_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_switch = support_integrity.switch_v2
    real_advance = support_integrity.advance_support_v2

    class RequestProjection:
        def __init__(self, request: object) -> None:
            self._request = request
            self.stream_ref = "support:drifted-stream"

        def __getattr__(self, name: str) -> Any:
            return getattr(self._request, name)

    def project_switch(*args: object, **kwargs: object) -> Any:
        request, source = real_switch(*args, **kwargs)
        return RequestProjection(request), source

    def unwrap_advance(
        context: Any, request: Any, source: object, **kwargs: object
    ) -> Any:
        return real_advance(
            context,
            getattr(request, "_request", request),
            source,
            **kwargs,
        )

    monkeypatch.setattr(support_integrity, "switch_v2", project_switch)
    monkeypatch.setattr(support_integrity, "advance_support_v2", unwrap_advance)
    problems: list[str] = []

    support_integrity._issuer_rotation(_adapter(), problems)

    assert problems == ["issuer_rotation_fixed_lineage"]


def test_support_rotation_checker_alarms_on_rehydrate_projection_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        support_integrity,
        "require_current_support_state_v2",
        lambda _state: object(),
    )
    problems: list[str] = []

    support_integrity._issuer_rotation(_adapter(), problems)

    assert problems == ["issuer_rotation_rehydrate"]


def test_support_canonical_checker_alarms_on_noncanonical_wire_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AcceptingSupportRequest:
        @staticmethod
        def from_dict(_payload: object) -> object:
            return object()

    monkeypatch.setattr(
        support_integrity,
        "SupportAdvanceRequestV2",
        AcceptingSupportRequest,
    )
    problems: list[str] = []

    support_integrity._canonical_wire_and_resource(_adapter(), problems)

    assert problems == ["noncanonical_wire_accepted"] * 4


def test_support_resource_checker_alarms_on_oversized_record_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class AcceptingVerificationRecord:
        @staticmethod
        def from_dict(_payload: object) -> object:
            return object()

    monkeypatch.setattr(
        support_integrity,
        "PrincipalVerificationRecordV2",
        AcceptingVerificationRecord,
    )
    problems: list[str] = []

    support_integrity._canonical_wire_and_resource(_adapter(), problems)

    assert problems == ["resource_limit_accepted"]


def test_support_runner_rejects_noncanonical_implementation_identifier() -> None:
    class PaddedImplementationId(ReferenceGovernanceStateStoreConformanceAdapterV2):
        implementation_id = " padded-support-v2 "

    result = support_contract.run_governance_support_conformance_v2(
        PaddedImplementationId()
    )

    assert result.ok is False
    assert result.detail == "adapter_implementation_id"


def test_support_runner_contains_unexpected_submatrix_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(_adapter: object) -> list[str]:
        raise RuntimeError("injected support submatrix failure")

    monkeypatch.setattr(support_contract, "run_support_v2_core_matrix", explode)

    result = support_contract.run_governance_support_conformance_v2(_adapter())

    assert result.ok is False
    assert result.detail == (
        "adapter_exception:RuntimeError:injected support submatrix failure"
    )
