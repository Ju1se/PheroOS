from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, cast

import pytest

from pheroos.conformance.checks import scoped_trace_store_v2_contract as checker
from pheroos.trace import (
    InMemoryScopedTraceStoreV2,
    ScopedTraceAppendReceiptV2,
    ScopedTraceCheckpointV2,
    ScopedTraceCursorV2,
    ScopedTraceRecordV2,
    ScopedTraceRetirementV2,
)
from tests.conformance.test_scoped_trace_store_v2_contract import _StoreProxy


class _Adapter:
    implementation_id: object = "tests-scoped-trace-totality"
    conformance_version = checker.SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2

    def __init__(self, stores: list[object] | None = None) -> None:
        self.stores = stores or []

    def create_store_v2(self) -> object:
        if self.stores:
            return self.stores.pop(0)
        return InMemoryScopedTraceStoreV2()

    def restart_store_v2(self, store: object, checkpoint: object) -> object:
        return cast(Any, store).restart_v2(checkpoint)

    def create_failure_injected_store_v2(self, stage: str) -> object:
        return InMemoryScopedTraceStoreV2(failure_stage=stage)


def _skip_exercises(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "_exercise_core",
        "_exercise_checkpoint_order",
        "_exercise_races",
        "_exercise_failures",
    ):
        monkeypatch.setattr(checker, name, lambda *_args: None)


@pytest.mark.parametrize("value", (None, "", " padded "))
def test_adapter_identity_and_protocol_failures_are_exact(value: object) -> None:
    if value is None:
        result = checker.run_scoped_trace_store_conformance_v2(object())
        assert result.detail == "adapter_protocol"
        return
    adapter = _Adapter()
    adapter.implementation_id = value
    result = checker.run_scoped_trace_store_conformance_v2(cast(Any, adapter))
    assert result.detail == "adapter_implementation_id"


def test_adapter_version_store_protocol_and_store_version_fail_exactly() -> None:
    wrong_version = _Adapter()
    wrong_version.conformance_version = "unsupported"
    assert (
        checker.run_scoped_trace_store_conformance_v2(cast(Any, wrong_version)).detail
        == "adapter_version"
    )

    wrong_store = _Adapter([object()])
    assert (
        checker.run_scoped_trace_store_conformance_v2(cast(Any, wrong_store)).detail
        == "store_protocol"
    )

    store = _StoreProxy()
    store.store_version = "unsupported"
    wrong_store_version = _Adapter([store])
    assert (
        checker.run_scoped_trace_store_conformance_v2(
            cast(Any, wrong_store_version)
        ).detail
        == "store_version"
    )


def test_fresh_store_and_adapter_exception_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _skip_exercises(monkeypatch)
    protocol = checker.run_scoped_trace_store_conformance_v2(
        cast(Any, _Adapter([InMemoryScopedTraceStoreV2(), object()]))
    )
    assert protocol.detail == "fresh_store_protocol"

    populated = InMemoryScopedTraceStoreV2()
    populated.append_scoped_v2(checker._event(1))
    isolated = checker.run_scoped_trace_store_conformance_v2(
        cast(Any, _Adapter([InMemoryScopedTraceStoreV2(), populated]))
    )
    assert isolated.detail == "fresh_store_isolation"

    class _ExplodingAdapter(_Adapter):
        def create_store_v2(self) -> object:
            raise RuntimeError("create exploded")

    exploded = checker.run_scoped_trace_store_conformance_v2(
        cast(Any, _ExplodingAdapter())
    )
    assert exploded.detail == "adapter_exception:RuntimeError:create exploded"


def test_reference_check_entrypoint_passes() -> None:
    assert checker.check().ok


class _AliasingSnapshotStore(_StoreProxy):
    def __init__(self, *, initially_populated: bool = False) -> None:
        super().__init__()
        self.cached: tuple[ScopedTraceRecordV2, ...] | None = None
        if initially_populated:
            self.inner.append_scoped_v2(checker._event(99))

    def snapshot_scoped_v2(
        self,
        scope_ref: str,
        stream: str,
        cursor: ScopedTraceCursorV2 | None = None,
    ) -> tuple[ScopedTraceRecordV2, ...]:
        observed = self.inner.snapshot_scoped_v2(scope_ref, stream, cursor)
        if observed and self.cached is None:
            self.cached = observed
        return self.cached if self.cached is not None else observed


def test_append_snapshot_isolation_alarms_are_observable() -> None:
    initially_populated: list[str] = []
    checker._exercise_append_and_snapshots(
        cast(Any, _AliasingSnapshotStore(initially_populated=True)),
        initially_populated,
    )
    assert "fresh_store_not_empty" in initially_populated

    aliasing: list[str] = []
    checker._exercise_append_and_snapshots(
        cast(Any, _AliasingSnapshotStore()),
        aliasing,
    )
    assert "snapshot_history_mutated" in aliasing

    class _CorruptSnapshotStore(_StoreProxy):
        def snapshot_scoped_v2(
            self,
            scope_ref: str,
            stream: str,
            cursor: ScopedTraceCursorV2 | None = None,
        ) -> tuple[ScopedTraceRecordV2, ...]:
            observed = self.inner.snapshot_scoped_v2(scope_ref, stream, cursor)
            if observed:
                changed = deepcopy(observed[0])
                changed.event.event.lineage["nested"]["items"].append(7)
                return (changed,)
            return observed

    corrupt: list[str] = []
    checker._exercise_append_and_snapshots(cast(Any, _CorruptSnapshotStore()), corrupt)
    assert "input_output_snapshot_isolation" in corrupt


class _RestartAdapter(_Adapter):
    def __init__(self, result: object) -> None:
        super().__init__()
        self.result = result

    def restart_store_v2(self, _store: object, _checkpoint: object) -> object:
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_restart_contract_failures_are_distinguished() -> None:
    store = InMemoryScopedTraceStoreV2()
    problems: list[str] = []
    assert (
        checker._exercise_restart(
            store,
            cast(Any, _RestartAdapter(RuntimeError("restart"))),
            problems,
        )
        is None
    )
    assert problems == ["restart_exception:RuntimeError"]

    problems = []
    assert (
        checker._exercise_restart(
            store,
            cast(Any, _RestartAdapter(object())),
            problems,
        )
        is None
    )
    assert problems == ["restart_store_protocol"]

    mismatched = InMemoryScopedTraceStoreV2()
    mismatched.append_scoped_v2(checker._event(1))
    problems = []
    checker._exercise_restart(
        store,
        cast(Any, _RestartAdapter(mismatched)),
        problems,
    )
    assert "restart_checkpoint" in problems
    assert "restart_cursor" in problems


class _RetirementBreakingStore(_StoreProxy):
    def __init__(self) -> None:
        super().__init__()
        self.inner.append_scoped_v2(checker._event(1))
        self.inner.append_scoped_v2(checker._event(2))
        self.retirements = 0

    def retire_scope_v2(self, scope_ref: str) -> ScopedTraceRetirementV2:
        result = self.inner.retire_scope_v2(scope_ref)
        self.retirements += 1
        if self.retirements > 1:
            changed = deepcopy(result)
            object.__setattr__(changed, "history_root", "sha256:" + "0" * 64)
            return changed
        return result

    def snapshot_scoped_v2(
        self,
        scope_ref: str,
        stream: str,
        cursor: ScopedTraceCursorV2 | None = None,
    ) -> tuple[ScopedTraceRecordV2, ...]:
        if self.retirements:
            return ()
        return self.inner.snapshot_scoped_v2(scope_ref, stream, cursor)

    def append_scoped_v2(self, event: object) -> ScopedTraceAppendReceiptV2:
        try:
            return self.inner.append_scoped_v2(event)
        except ValueError:
            fresh = InMemoryScopedTraceStoreV2()
            return fresh.append_scoped_v2(event)


def test_retirement_failures_cannot_hide_from_the_checker() -> None:
    store = _RetirementBreakingStore()
    problems: list[str] = []
    checker._exercise_retirement(store, cast(Any, _RestartAdapter(store)), problems)
    assert {
        "retirement_idempotence",
        "retired_history_unreadable",
        "retired_scope_append_accepted",
        "retirement_lost_on_restart",
    } <= set(problems)


class _BadReplayRaceStore(_StoreProxy):
    def __init__(self) -> None:
        super().__init__()
        self.lock = Lock()
        self.ordinal = 0

    def append_scoped_v2(self, event: object) -> ScopedTraceAppendReceiptV2:
        receipt = self.inner.append_scoped_v2(event)
        with self.lock:
            self.ordinal += 1
            changed = deepcopy(receipt)
            object.__setattr__(changed, "disposition", "replayed")
            object.__setattr__(
                changed.record,
                "record_root",
                f"sha256:{self.ordinal:064x}",
            )
            return changed

    def snapshot_scoped_v2(
        self,
        scope_ref: str,
        stream: str,
        cursor: ScopedTraceCursorV2 | None = None,
    ) -> tuple[ScopedTraceRecordV2, ...]:
        return ()


class _DroppingDistinctStore(_StoreProxy):
    def snapshot_scoped_v2(
        self,
        scope_ref: str,
        stream: str,
        cursor: ScopedTraceCursorV2 | None = None,
    ) -> tuple[ScopedTraceRecordV2, ...]:
        return self.inner.snapshot_scoped_v2(scope_ref, stream, cursor)[1:]


def test_race_failures_cover_publication_identity_sequence_and_loss() -> None:
    problems: list[str] = []
    checker._exercise_races(
        cast(Any, _Adapter([_BadReplayRaceStore(), _DroppingDistinctStore()])),
        problems,
    )
    assert {
        "race_replay_publication_count",
        "race_replay_record_identity",
        "race_replay_history",
        "race_distinct_sequence",
        "race_distinct_loss_or_duplicate",
    } <= set(problems)

    protocol: list[str] = []
    checker._exercise_races(cast(Any, _Adapter([object()])), protocol)
    assert protocol == ["race_store_protocol"]

    distinct_protocol: list[str] = []
    checker._exercise_races(
        cast(Any, _Adapter([InMemoryScopedTraceStoreV2(), object()])),
        distinct_protocol,
    )
    assert distinct_protocol == ["distinct_race_store_protocol"]


class _UnorderedCheckpointStore(_StoreProxy):
    def checkpoint_v2(self) -> ScopedTraceCheckpointV2:
        checkpoint = self.inner.checkpoint_v2()
        changed = deepcopy(checkpoint)
        object.__setattr__(changed, "records", tuple(reversed(changed.records)))
        object.__setattr__(
            changed,
            "retirements",
            tuple(reversed(changed.retirements)),
        )
        return changed


class _AcceptingCheckpointAdapter(_Adapter):
    def restart_store_v2(self, _store: object, _checkpoint: object) -> object:
        return InMemoryScopedTraceStoreV2()


def test_checkpoint_order_and_tamper_acceptance_alarms() -> None:
    protocol: list[str] = []
    checker._exercise_checkpoint_order(cast(Any, _Adapter([object()])), protocol)
    assert protocol == ["checkpoint_order_store_protocol"]

    problems: list[str] = []
    checker._exercise_checkpoint_order(
        cast(Any, _AcceptingCheckpointAdapter([_UnorderedCheckpointStore()])),
        problems,
    )
    assert "checkpoint_record_order" in problems
    assert "checkpoint_retirement_order" in problems
    assert "checkpoint_portable_canonical_order" in problems
    assert {
        "checkpoint_records_tamper_accepted",
        "checkpoint_retirements_tamper_accepted",
        "checkpoint_root_tamper_accepted",
    } <= set(problems)


class _PublishedFailureStore(_StoreProxy):
    def __init__(self, stage: str) -> None:
        super().__init__()
        self.stage = stage

    def append_scoped_v2(self, event: object) -> ScopedTraceAppendReceiptV2:
        receipt = self.inner.append_scoped_v2(event)
        if self.stage == "append_before_publish":
            raise RuntimeError("published append")
        return receipt

    def retire_scope_v2(self, scope_ref: str) -> ScopedTraceRetirementV2:
        retirement = self.inner.retire_scope_v2(scope_ref)
        if self.stage == "retire_before_publish":
            raise RuntimeError("published retirement")
        return retirement


class _FailureAdapter(_Adapter):
    def create_failure_injected_store_v2(self, stage: str) -> object:
        if stage == "checkpoint_before_return":
            return InMemoryScopedTraceStoreV2()
        return _PublishedFailureStore(stage)


def test_failure_injection_protocol_and_publication_alarms() -> None:
    class _ProtocolFailureAdapter(_Adapter):
        def create_failure_injected_store_v2(self, _stage: str) -> object:
            return object()

    protocol: list[str] = []
    checker._exercise_failures(cast(Any, _ProtocolFailureAdapter()), protocol)
    assert all(item.startswith("failure_store_protocol:") for item in protocol)

    problems: list[str] = []
    checker._exercise_failures(cast(Any, _FailureAdapter()), problems)
    assert "failure_published_record:append_before_publish" in problems
    assert "failure_not_injected:checkpoint_before_return" in problems
    assert "retirement_failure_published_tombstone" in problems


def test_valid_receipt_rejects_non_receipts() -> None:
    assert not checker._valid_receipt(object(), "appended", 0, checker._event(1))
