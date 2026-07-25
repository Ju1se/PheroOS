from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, Literal, cast

import pytest

import pheroos.conformance.checks.commit_decision_v2_contract as contract
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.commit_decision_v2_contract import (
    run_governance_commit_decision_conformance_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitInclusionProofV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitPositionV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitViewV2,
    GovernanceCommittedTransitionV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionOutcomeKindV2,
    CommitDecisionSnapshotV2,
)
from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
)
from pheroos.trace import TraceEvent


_Scenario = Literal[
    "missing_initialize_rejected",
    "retry_and_restart_rehydrate",
    "restart_retry_and_currentness",
    "missing_progress_rejected",
    "cas_progress_and_deadline",
    "missing_terminal_mistyped",
    "ready_initialize_rejected",
    "ready_evaluate_rejected",
    "ready_window_invalid",
    "ready_seal_rejected",
    "ready_finalize_rejected",
    "ready_terminal_mistyped",
    "terminal_retry_and_rehydrate",
    "terminal_restart_not_current",
    "trace_event_sequence_invalid",
    "trace_read_set_lineage_invalid",
]
_SnapshotTransform = Callable[[CommitDecisionSnapshotV2], CommitDecisionSnapshotV2]
_ViewFault = Literal["superseded", "unavailable"]

_MISSING_INITIALIZE = "mutation:commit-decision:missing:initialize"
_MISSING_CHILD_A = "mutation:commit-decision:missing:child-a"
_MISSING_CHILD_B = "mutation:commit-decision:missing:child-b"
_MISSING_DEADLINE = "mutation:commit-decision:missing:deadline"
_READY_INITIALIZE = "mutation:commit-decision:ready:initialize"
_READY_EVALUATE_7 = "mutation:commit-decision:ready:evaluate:7"
_READY_EVALUATE_8 = "mutation:commit-decision:ready:evaluate:8"
_READY_SEAL = "mutation:commit-decision:ready:seal"
_READY_FINALIZE = "mutation:commit-decision:ready:finalize"


class _AdversarialAdapter(ReferenceGovernanceStateStoreConformanceAdapterV2):
    implementation_id = "adversarial-commit-decision-v2-store"

    def __init__(self, scenario: _Scenario) -> None:
        self._scenario = scenario

    def create_store_v2(
        self,
        domains: Sequence[AuthorityDomainV2],
    ) -> GovernanceStateStoreV2:
        store = super().create_store_v2(domains)
        return cast(
            GovernanceStateStoreV2,
            _AdversarialStore(
                store,
                self._scenario,
                scope_ref=domains[0].scope_ref,
                restarted=False,
            ),
        )

    def restart_store_v2(
        self,
        store: GovernanceStateStoreV2,
    ) -> GovernanceStateStoreV2:
        selected = cast(_AdversarialStore, store)
        restarted = super().restart_store_v2(selected.delegate)
        return cast(
            GovernanceStateStoreV2,
            _AdversarialStore(
                restarted,
                self._scenario,
                scope_ref=selected.scope_ref,
                restarted=True,
            ),
        )


class _AdversarialStore:
    def __init__(
        self,
        delegate: GovernanceStateStoreV2,
        scenario: _Scenario,
        *,
        scope_ref: str,
        restarted: bool,
    ) -> None:
        self.delegate = delegate
        self.scope_ref = scope_ref
        self._scenario = scenario
        self._restarted = restarted
        self._committed_view_counts: dict[str, int] = {}
        self._invalid_head_stream: str | None = None
        self._forged_views: dict[str, GovernanceCommitViewV2] = {}

    @property
    def state_store_version(self) -> str:
        return self.delegate.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if stream_ref == self._invalid_head_stream:
            self._invalid_head_stream = None
            return cast(GovernanceHeadV2, object())
        return self.delegate.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self.delegate.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        cached = self._forged_views.get(transition_id)
        cached_match = _cached_view_v2(cached, expected_receipt_root)
        if cached_match is not None:
            return cached_match
        view = self.delegate.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        mutation = _mutation_from_view(view)
        if mutation is None:
            return view
        count = self._committed_view_counts.get(mutation, 0) + 1
        self._committed_view_counts[mutation] = count
        fault = _VIEW_FAULTS.get((self._scenario, self._restarted, mutation, count))
        faulted = _faulted_view_v2(view, fault)
        if faulted is not None:
            return faulted
        snapshot_fault = _SNAPSHOT_FORGERIES.get(self._scenario)
        if (
            snapshot_fault is not None
            and (
                mutation,
                count,
            )
            == snapshot_fault[:2]
        ):
            altered = _with_snapshot(view, snapshot_fault[2])
            self._forged_views[transition_id] = altered
            return altered
        return view

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        attempt = self.delegate.atomic_commit_v2(batch)
        mutation = _mutation_from_batch(batch)
        scenario = self._scenario
        if scenario == "cas_progress_and_deadline" and mutation == _MISSING_CHILD_A:
            self._invalid_head_stream = batch.stream_ref
        if mutation in _REJECTED_MUTATIONS.get(scenario, frozenset()):
            return _failure_attempt(batch)
        trace_fault = _TRACE_FAULTS.get(scenario)
        if mutation == _MISSING_INITIALIZE and trace_fault is not None:
            return _with_adversarial_trace(
                attempt,
                wrong_event_type=trace_fault,
            )
        return attempt


def _mutation_from_batch(batch: GovernanceCommitBatchV2) -> str | None:
    transition = batch.transition
    if transition is None:
        return None
    request = transition.state_records.get("request")
    if not isinstance(request, Mapping):
        return None
    mutation = request.get("mutation_ref")
    return mutation if type(mutation) is str else None


def _mutation_from_view(view: GovernanceCommitViewV2) -> str | None:
    committed = view.committed_transition
    if committed is None:
        return None
    return _mutation_from_batch(committed.batch)


def _cached_view_v2(
    cached: GovernanceCommitViewV2 | None,
    expected_receipt_root: str | None,
) -> GovernanceCommitViewV2 | None:
    if (
        cached is None
        or cached.committed_transition is None
        or expected_receipt_root != cached.committed_transition.receipt.receipt_root
    ):
        return None
    return replace(
        cached,
        expected_receipt_root=expected_receipt_root,
        view_root="",
    )


def _faulted_view_v2(
    view: GovernanceCommitViewV2,
    fault: _ViewFault | None,
) -> GovernanceCommitViewV2 | None:
    if fault == "unavailable":
        return _unavailable_view(view)
    if fault == "superseded":
        return _with_position(view, GovernanceCommitPositionV2.SUPERSEDED)
    return None


def _failure_attempt(batch: GovernanceCommitBatchV2) -> GovernanceCommitAttemptV2:
    failure = GovernanceFailureV2(
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/adversarial_store",
        stage=GovernanceFailureStageV2.COMMIT,
    )
    return GovernanceCommitAttemptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        disposition=GovernanceCommitDispositionV2.INVALID,
        failure=failure,
        committed_transition=None,
        position_observation=None,
    )


def _unavailable_view(
    view: GovernanceCommitViewV2,
) -> GovernanceCommitViewV2:
    return GovernanceCommitViewV2(
        domain_root=view.domain_root,
        scope_ref=view.scope_ref,
        stream_ref=view.stream_ref,
        transition_id=view.transition_id,
        expected_receipt_root=view.expected_receipt_root,
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            path="/transition_id",
            stage=GovernanceFailureStageV2.LOAD,
        ),
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )


def _with_position(
    view: GovernanceCommitViewV2,
    position: GovernanceCommitPositionV2,
) -> GovernanceCommitViewV2:
    observation = view.position_observation
    assert observation is not None
    replaced = replace(
        observation,
        position=position,
        seal_root=None,
        observation_root="",
    )
    return replace(
        view,
        position_observation=replaced,
        view_root="",
    )


def _snapshot_from_view(
    view: GovernanceCommitViewV2,
) -> CommitDecisionSnapshotV2:
    committed = view.committed_transition
    assert committed is not None
    transition = committed.batch.transition
    assert transition is not None
    records = cast(dict[str, object], transition.to_dict()["state_records"])
    return CommitDecisionSnapshotV2.from_dict(records["snapshot"])


def _without_missing_gates(
    snapshot: CommitDecisionSnapshotV2,
) -> CommitDecisionSnapshotV2:
    progress = snapshot.progress
    assert progress is not None
    altered_progress = replace(
        progress,
        unmet_gates=(),
        progress_root="",
    )
    return replace(
        snapshot,
        progress=altered_progress,
        state_root="",
        history_root="",
        snapshot_root="",
    )


def _blocked_outcome(snapshot: CommitDecisionSnapshotV2) -> CommitDecisionSnapshotV2:
    outcome = snapshot.outcome
    assert outcome is not None
    altered_outcome = replace(
        outcome,
        kind=CommitDecisionOutcomeKindV2.BLOCKED,
        epistemically_committed=False,
        outcome_root="",
    )
    return replace(
        snapshot,
        outcome=altered_outcome,
        state_root="",
        history_root="",
        snapshot_root="",
    )


def _without_ready_window(
    snapshot: CommitDecisionSnapshotV2,
) -> CommitDecisionSnapshotV2:
    window = replace(
        snapshot.window,
        streak_count=0,
        streak_started_at_step=None,
        leader_candidate_ref="",
        last_ready=False,
        window_root="",
    )
    progress = snapshot.progress
    assert progress is not None
    altered_progress = replace(
        progress,
        window_root=window.window_root,
        leader_candidate_ref="",
        streak_count=0,
        progress_root="",
    )
    return replace(
        snapshot,
        window=window,
        progress=altered_progress,
        state_root="",
        history_root="",
        snapshot_root="",
    )


_VIEW_FAULTS: dict[tuple[_Scenario, bool, str, int], _ViewFault] = {
    ("retry_and_restart_rehydrate", False, _MISSING_INITIALIZE, 1): "unavailable",
    ("retry_and_restart_rehydrate", True, _MISSING_INITIALIZE, 2): "unavailable",
    ("restart_retry_and_currentness", True, _MISSING_INITIALIZE, 1): "unavailable",
    ("restart_retry_and_currentness", True, _MISSING_INITIALIZE, 3): "superseded",
    ("terminal_retry_and_rehydrate", True, _READY_FINALIZE, 1): "unavailable",
    ("terminal_retry_and_rehydrate", True, _READY_FINALIZE, 2): "unavailable",
    ("terminal_restart_not_current", True, _READY_FINALIZE, 3): "superseded",
}
_SNAPSHOT_FORGERIES: dict[
    _Scenario,
    tuple[str, int, _SnapshotTransform],
] = {
    "cas_progress_and_deadline": (
        _MISSING_CHILD_A,
        2,
        _without_missing_gates,
    ),
    "missing_terminal_mistyped": (
        _MISSING_DEADLINE,
        1,
        _blocked_outcome,
    ),
    "ready_window_invalid": (
        _READY_EVALUATE_8,
        1,
        _without_ready_window,
    ),
    "ready_terminal_mistyped": (
        _READY_FINALIZE,
        1,
        _blocked_outcome,
    ),
}
_REJECTED_MUTATIONS: dict[_Scenario, frozenset[str]] = {
    "missing_initialize_rejected": frozenset({_MISSING_INITIALIZE}),
    "missing_progress_rejected": frozenset({_MISSING_CHILD_A}),
    "cas_progress_and_deadline": frozenset({_MISSING_CHILD_B, _MISSING_DEADLINE}),
    "ready_initialize_rejected": frozenset({_READY_INITIALIZE}),
    "ready_evaluate_rejected": frozenset({_READY_EVALUATE_7}),
    "ready_seal_rejected": frozenset({_READY_SEAL}),
    "ready_finalize_rejected": frozenset({_READY_FINALIZE}),
}
_TRACE_FAULTS: dict[_Scenario, bool] = {
    "trace_event_sequence_invalid": True,
    "trace_read_set_lineage_invalid": False,
}


def _with_snapshot(
    view: GovernanceCommitViewV2,
    transform: _SnapshotTransform,
) -> GovernanceCommitViewV2:
    snapshot = transform(_snapshot_from_view(view))
    committed = view.committed_transition
    assert committed is not None
    transition = committed.batch.transition
    assert transition is not None
    records = dict(transition.state_records)
    records["snapshot"] = snapshot.to_dict()
    records["snapshot_root"] = snapshot.snapshot_root
    altered_transition = replace(
        transition,
        state_records=records,
        state_root="",
        transition_root="",
    )
    events = tuple(
        _event_for_snapshot(event, snapshot)
        for event in committed.batch.trace_batch.events
    )
    rebuilt, position = _rebuild_committed(
        committed,
        view.position_observation,
        transition=altered_transition,
        events=events,
    )
    return replace(
        view,
        expected_receipt_root=rebuilt.receipt.receipt_root,
        committed_transition=rebuilt,
        position_observation=position,
        observed_head_root=position.observed_head_root,
        view_root="",
    )


def _event_for_snapshot(
    event: TraceEvent,
    snapshot: CommitDecisionSnapshotV2,
) -> TraceEvent:
    lineage = dict(event.lineage)
    lineage.update(
        {
            "domain_root": snapshot.domain_root,
            "scope_ref": snapshot.scope_ref,
            "stream_ref": snapshot.stream_ref,
            "transition_id": snapshot.transition_id,
            "mutation_ref": snapshot.mutation_ref,
            "mutation_kind": snapshot.mutation_kind.value,
            "revision": snapshot.revision,
            "parent_revision": snapshot.parent_revision,
            "parent_transition_id": snapshot.parent_transition_id,
            "parent_snapshot_root": snapshot.parent_snapshot_root,
            "snapshot_root": snapshot.snapshot_root,
            "state_root": snapshot.state_root,
            "history_root": snapshot.history_root,
            "history_count": snapshot.history_count,
            "epoch": snapshot.epoch,
            "current_step": snapshot.current_step,
            "dependency_set_root": snapshot.dependency_set_root,
            "source_context_root": snapshot.source_context_root,
            "assessment_root": (
                ""
                if snapshot.assessment is None
                else snapshot.assessment.assessment_root
            ),
            "window_root": snapshot.window.window_root,
            "seal_root": "" if snapshot.seal is None else snapshot.seal.seal_root,
            "progress_root": (
                "" if snapshot.progress is None else snapshot.progress.progress_root
            ),
            "outcome_root": (
                "" if snapshot.outcome is None else snapshot.outcome.outcome_root
            ),
            "dependencies": [item.to_dict() for item in snapshot.dependencies],
        }
    )
    return TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )


def _with_adversarial_trace(
    attempt: GovernanceCommitAttemptV2,
    *,
    wrong_event_type: bool,
) -> GovernanceCommitAttemptV2:
    committed = attempt.committed_transition
    assert committed is not None
    original = committed.batch.trace_batch.events
    first = original[0]
    lineage = dict(first.lineage)
    event_type = first.event_type
    read_set = committed.batch.read_set
    transition = cast(
        PreparedGovernanceTransitionV2,
        committed.batch.transition,
    )
    if wrong_event_type:
        event_type = "x-adversarial-unexpected"
    else:
        entries = list(read_set.entries)
        selected = next(
            index
            for index, entry in enumerate(entries)
            if entry.stream_ref != committed.batch.stream_ref
        )
        entries[selected] = replace(
            entries[selected],
            expected_root="sha256:" + ("0" * 64),
        )
        read_set = GovernanceAuthorityReadSetV2(entries=tuple(entries))
        transition = replace(
            transition,
            read_set_root=read_set.root(),
            transition_root="",
        )
    changed = TraceEvent(
        event_type=event_type,
        protocol_id=first.protocol_id,
        target=first.target,
        reason=first.reason,
        lineage=lineage,
    )
    rebuilt, position = _rebuild_committed(
        committed,
        attempt.position_observation,
        transition=transition,
        events=(changed, *original[1:]),
        read_set=read_set,
    )
    return replace(
        attempt,
        committed_transition=rebuilt,
        position_observation=position,
        attempt_root="",
    )


def _rebuild_committed(
    committed: GovernanceCommittedTransitionV2,
    original_position: GovernanceCommitPositionObservationV2 | None,
    *,
    transition: PreparedGovernanceTransitionV2,
    events: tuple[TraceEvent, ...],
    read_set: GovernanceAuthorityReadSetV2 | None = None,
) -> tuple[
    GovernanceCommittedTransitionV2,
    GovernanceCommitPositionObservationV2,
]:
    batch = committed.batch
    selected_read_set = batch.read_set if read_set is None else read_set
    trace_batch = GovernanceTraceBatchV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        events=events,
    )
    rebuilt_batch = replace(
        batch,
        read_set=selected_read_set,
        read_set_root="",
        trace_batch=trace_batch,
        transition=transition,
        transition_root=None,
        trace_root="",
        batch_root="",
    )
    receipt = committed.receipt
    head = GovernanceHeadV2(
        domain_root=receipt.domain_root,
        scope_ref=receipt.scope_ref,
        stream_ref=receipt.stream_ref,
        revision=receipt.revision,
        parent_root=receipt.parent_root,
        state_root=transition.state_root,
        transition_id=receipt.transition_id,
        batch_root=rebuilt_batch.batch_root,
    )
    rebuilt_receipt = GovernanceCommitReceiptV2(
        domain_root=receipt.domain_root,
        scope_ref=receipt.scope_ref,
        stream_ref=receipt.stream_ref,
        transition_id=receipt.transition_id,
        revision=receipt.revision,
        parent_root=receipt.parent_root,
        head_root=head.head_root,
        state_root=transition.state_root,
        read_set_root=selected_read_set.root(),
        trace_root=trace_batch.trace_root,
        batch_root=rebuilt_batch.batch_root,
    )
    inclusion = GovernanceCommitInclusionProofV2(
        domain_root=receipt.domain_root,
        scope_ref=receipt.scope_ref,
        stream_ref=receipt.stream_ref,
        transition_id=receipt.transition_id,
        revision=receipt.revision,
        batch_root=rebuilt_batch.batch_root,
        receipt_root=rebuilt_receipt.receipt_root,
        head_root=head.head_root,
    )
    rebuilt = GovernanceCommittedTransitionV2(
        batch=rebuilt_batch,
        receipt=rebuilt_receipt,
        inclusion_proof=inclusion,
    )
    assert original_position is not None
    position = replace(
        original_position,
        receipt_root=rebuilt_receipt.receipt_root,
        observed_head_root=head.head_root,
        observation_root="",
    )
    return rebuilt, position


@pytest.mark.parametrize(
    ("scenario", "expected"),
    (
        ("missing_initialize_rejected", ("missing_initialize_commit",)),
        (
            "retry_and_restart_rehydrate",
            (
                "same_process_exact_retry",
                "restart_rehydrate",
            ),
        ),
        (
            "restart_retry_and_currentness",
            (
                "restart_lost_response_exact_retry",
                "restart_current_state",
            ),
        ),
        ("missing_progress_rejected", ("missing_progress_commit",)),
        (
            "cas_progress_and_deadline",
            (
                "decision_parent_cas_race",
                "bounded_missing_progress",
                "missing_deadline_commit",
            ),
        ),
        ("missing_terminal_mistyped", ("missing_deadline_typed_terminal",)),
        ("ready_initialize_rejected", ("ready_initialize_commit",)),
        ("ready_evaluate_rejected", ("ready_evaluate_commit:7",)),
        ("ready_window_invalid", ("ready_window",)),
        ("ready_seal_rejected", ("same_step_seal_commit",)),
        ("ready_finalize_rejected", ("evidence_finality_commit",)),
        ("ready_terminal_mistyped", ("ready_typed_terminal",)),
        (
            "terminal_retry_and_rehydrate",
            (
                "terminal_restart_exact_retry",
                "terminal_restart_rehydrate",
            ),
        ),
        (
            "terminal_restart_not_current",
            ("terminal_restart_currentness",),
        ),
        (
            "trace_event_sequence_invalid",
            ("missing_initialize_trace",),
        ),
        (
            "trace_read_set_lineage_invalid",
            ("missing_initialize_trace:read_set_root",),
        ),
    ),
)
def test_commit_decision_matrix_reports_adversarial_store_contract_violations(
    scenario: _Scenario,
    expected: tuple[str, ...],
) -> None:
    result = run_governance_commit_decision_conformance_v2(
        _AdversarialAdapter(scenario)
    )

    assert result.name == "commit_decision_v2_contract"
    assert result.ok is False
    for diagnostic in expected:
        assert diagnostic in result.detail, result.detail


def test_expect_events_totalizes_an_absent_committed_transition() -> None:
    """Cover the pure guard unreachable after the runner's committed gate."""

    domain = _AdversarialAdapter("missing_initialize_rejected").create_domain_v2(
        "scope:expect-events-totality"
    )
    attempt = GovernanceCommitAttemptV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref="stream:expect-events-totality",
        transition_id="transition:expect-events-totality",
        disposition=GovernanceCommitDispositionV2.INVALID,
        failure=GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            path="/committed_transition",
            stage=GovernanceFailureStageV2.TRACE,
        ),
        committed_transition=None,
        position_observation=None,
    )
    problems: list[str] = []

    contract._expect_events(attempt, ("never",), problems, "missing_trace")

    assert problems == ["missing_trace"]
