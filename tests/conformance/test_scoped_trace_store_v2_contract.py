from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import inspect
import json
from pathlib import Path
from threading import RLock

import pytest

from pheroos.conformance.checks.scoped_trace_store_v2_contract import (
    SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2,
    ReferenceScopedTraceStoreConformanceAdapterV2,
    ScopedTraceStoreConformanceAdapterV2,
    run_scoped_trace_store_conformance_v2,
)
from pheroos.trace import (
    SCOPED_TRACE_CURSOR_VERSION_V2,
    SCOPED_TRACE_STORE_VERSION_V2,
    InMemoryScopedTraceStoreV2,
    ScopedTraceAppendReceiptV2,
    ScopedTraceCheckpointV2,
    ScopedTraceCursorV2,
    ScopedTraceEvent,
    ScopedTraceRecordV2,
    ScopedTraceRetirementV2,
    ScopedTraceStoreV2,
)


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return "sha256:" + sha256(encoded).hexdigest()


def _prefix(records: list[ScopedTraceRecordV2]) -> str:
    return _digest(
        {
            "record_roots": [item.record_root for item in records],
            "version": SCOPED_TRACE_CURSOR_VERSION_V2,
        }
    )


class _IndependentStdlibStoreV2:
    """Independent test implementation; it does not wrap the reference store."""

    store_version = SCOPED_TRACE_STORE_VERSION_V2

    def __init__(
        self,
        checkpoint: ScopedTraceCheckpointV2 | None = None,
        failure: str | None = None,
    ) -> None:
        self.lock = RLock()
        self.records: dict[tuple[str, str], list[ScopedTraceRecordV2]] = {}
        self.index: dict[tuple[str, str, str, str], ScopedTraceRecordV2] = {}
        self.retired: dict[str, ScopedTraceRetirementV2] = {}
        self.failure = failure
        if checkpoint:
            checkpoint = ScopedTraceCheckpointV2.from_dict(checkpoint.to_dict())
            for record in checkpoint.records:
                items = self.records.setdefault((record.scope_ref, record.stream), [])
                if record.sequence != len(items):
                    raise ValueError("gap")
                self._index(record)
                items.append(record)
            for retirement in checkpoint.retirements:
                if retirement.history_root != self._history(retirement.scope_ref):
                    raise ValueError("retirement root")
                self.retired[retirement.scope_ref] = retirement

    def _index(self, record: ScopedTraceRecordV2) -> None:
        base = (record.scope_ref, record.stream)
        keys = (
            (*base, "trace", record.event.trace_id),
            (*base, "transition", record.event.transition_id),
        )
        if any(key in self.index for key in keys):
            raise ValueError("duplicate identity")
        for key in keys:
            self.index[key] = record

    def append_scoped_v2(
        self,
        event: ScopedTraceEvent,
    ) -> ScopedTraceAppendReceiptV2:
        envelope = ScopedTraceEvent.from_dict(event.to_dict())
        base = (envelope.scope_ref, envelope.stream)
        with self.lock:
            if envelope.scope_ref in self.retired:
                raise ValueError("retired")
            found = tuple(
                item
                for item in (
                    self.index.get((*base, "trace", envelope.trace_id)),
                    self.index.get((*base, "transition", envelope.transition_id)),
                )
                if item is not None
            )
            if found:
                if (
                    len({item.record_root for item in found}) != 1
                    or found[0].event != envelope
                ):
                    raise ValueError("identity conflict")
                return ScopedTraceAppendReceiptV2("replayed", deepcopy(found[0]))
            record = ScopedTraceRecordV2(
                envelope.scope_ref,
                envelope.stream,
                len(self.records.get(base, ())),
                envelope,
            )
            if self.failure == "append_before_publish":
                raise RuntimeError("failure")
            self.records.setdefault(base, []).append(record)
            self._index(record)
            return ScopedTraceAppendReceiptV2("appended", deepcopy(record))

    def snapshot_scoped_v2(
        self,
        scope_ref: str,
        stream: str,
        cursor: ScopedTraceCursorV2 | None = None,
    ) -> tuple[ScopedTraceRecordV2, ...]:
        with self.lock:
            records = self.records.get((scope_ref, stream), [])
            start = 0
            if cursor:
                cursor = ScopedTraceCursorV2.from_dict(cursor.to_dict())
                if (
                    cursor.scope_ref != scope_ref
                    or cursor.stream != stream
                    or cursor.next_sequence > len(records)
                    or cursor.prefix_root != _prefix(records[: cursor.next_sequence])
                ):
                    raise ValueError("cursor")
                start = cursor.next_sequence
            return tuple(deepcopy(records[start:]))

    def cursor_scoped_v2(self, scope_ref: str, stream: str) -> ScopedTraceCursorV2:
        with self.lock:
            records = self.records.get((scope_ref, stream), [])
            return ScopedTraceCursorV2(
                scope_ref, stream, len(records), _prefix(records)
            )

    def retire_scope_v2(self, scope_ref: str) -> ScopedTraceRetirementV2:
        with self.lock:
            if scope_ref in self.retired:
                return deepcopy(self.retired[scope_ref])
            retirement = ScopedTraceRetirementV2(scope_ref, self._history(scope_ref))
            if self.failure == "retire_before_publish":
                raise RuntimeError("failure")
            self.retired[scope_ref] = retirement
            return deepcopy(retirement)

    def _history(self, scope_ref: str) -> str:
        records = [
            record.to_dict()
            for key in sorted(self.records)
            if key[0] == scope_ref
            for record in self.records[key]
        ]
        return _digest(
            {
                "records": records,
                "scope_ref": scope_ref,
                "version": SCOPED_TRACE_STORE_VERSION_V2,
            }
        )

    def checkpoint_v2(self) -> ScopedTraceCheckpointV2:
        with self.lock:
            checkpoint = ScopedTraceCheckpointV2(
                tuple(
                    record
                    for key in sorted(self.records)
                    for record in self.records[key]
                ),
                tuple(self.retired[key] for key in sorted(self.retired)),
            )
            if self.failure == "checkpoint_before_return":
                raise RuntimeError("failure")
            return deepcopy(checkpoint)

    def restart_v2(self, checkpoint: ScopedTraceCheckpointV2) -> ScopedTraceStoreV2:
        return _IndependentStdlibStoreV2(checkpoint)


class _IndependentAdapterV2:
    implementation_id = "tests-independent-stdlib-scoped-trace-store-v2"
    conformance_version = SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2

    def create_store_v2(self) -> ScopedTraceStoreV2:
        return _IndependentStdlibStoreV2()

    def restart_store_v2(
        self,
        store: ScopedTraceStoreV2,
        checkpoint: ScopedTraceCheckpointV2,
    ) -> ScopedTraceStoreV2:
        return _IndependentStdlibStoreV2(checkpoint)

    def create_failure_injected_store_v2(self, stage: str) -> ScopedTraceStoreV2:
        return _IndependentStdlibStoreV2(failure=stage)


class _StoreProxy:
    store_version = SCOPED_TRACE_STORE_VERSION_V2

    def __init__(self) -> None:
        self.inner = InMemoryScopedTraceStoreV2()

    def append_scoped_v2(self, event):
        return self.inner.append_scoped_v2(event)

    def snapshot_scoped_v2(self, scope_ref, stream, cursor=None):
        return self.inner.snapshot_scoped_v2(scope_ref, stream, cursor)

    def cursor_scoped_v2(self, scope_ref, stream):
        return self.inner.cursor_scoped_v2(scope_ref, stream)

    def retire_scope_v2(self, scope_ref):
        return self.inner.retire_scope_v2(scope_ref)

    def checkpoint_v2(self):
        return self.inner.checkpoint_v2()

    def restart_v2(self, checkpoint):
        return type(self)()


class _EchoStore(_StoreProxy):
    def append_scoped_v2(self, event):
        return event


class _ConstantStore(_StoreProxy):
    def __init__(self) -> None:
        super().__init__()
        self.constant = None

    def append_scoped_v2(self, event):
        if self.constant is None:
            self.constant = self.inner.append_scoped_v2(event)
        return deepcopy(self.constant)


class _OutOfOrderStore(_StoreProxy):
    def snapshot_scoped_v2(self, scope_ref, stream, cursor=None):
        return tuple(reversed(self.inner.snapshot_scoped_v2(scope_ref, stream, cursor)))


class _CrossScopeStore(_StoreProxy):
    def snapshot_scoped_v2(self, scope_ref, stream, cursor=None):
        if cursor is None and scope_ref.endswith("b" * 64):
            return self.inner.snapshot_scoped_v2("sha256:" + "a" * 64, stream)
        return self.inner.snapshot_scoped_v2(scope_ref, stream, cursor)


class _ConflictAcceptingStore(_StoreProxy):
    def append_scoped_v2(self, event):
        try:
            return self.inner.append_scoped_v2(event)
        except ValueError:
            changed = deepcopy(event)
            object.__setattr__(changed, "trace_id", changed.trace_id + ":accepted")
            object.__setattr__(
                changed, "transition_id", changed.transition_id + ":accepted"
            )
            object.__setattr__(changed, "envelope_root", "")
            changed = ScopedTraceEvent.from_dict(changed.to_dict())
            return self.inner.append_scoped_v2(changed)


class _MalformedAcceptingStore(_StoreProxy):
    def append_scoped_v2(self, event):
        try:
            return self.inner.append_scoped_v2(event)
        except ValueError:
            repaired = deepcopy(event)
            object.__setattr__(repaired, "scope_ref", "sha256:" + "a" * 64)
            object.__setattr__(repaired, "envelope_root", "")
            repaired = ScopedTraceEvent.from_dict(repaired.to_dict())
            return self.inner.append_scoped_v2(repaired)


class _BadAdapter:
    implementation_id = "tests-bad-scoped-trace-store-v2"
    conformance_version = SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2
    store_kind = _StoreProxy

    def create_store_v2(self):
        return self.store_kind()

    def restart_store_v2(self, store, checkpoint):
        return self.store_kind()

    def create_failure_injected_store_v2(self, stage):
        return InMemoryScopedTraceStoreV2(failure_stage=stage)


def test_reference_and_independent_stdlib_adapters_pass_the_same_matrix() -> None:
    for adapter in (
        ReferenceScopedTraceStoreConformanceAdapterV2(),
        _IndependentAdapterV2(),
    ):
        assert isinstance(adapter, ScopedTraceStoreConformanceAdapterV2)
        result = run_scoped_trace_store_conformance_v2(adapter)
        assert result.ok, result.detail


@pytest.mark.parametrize(
    "store_kind",
    [
        _EchoStore,
        _ConstantStore,
        _OutOfOrderStore,
        _CrossScopeStore,
        _ConflictAcceptingStore,
        _MalformedAcceptingStore,
    ],
)
def test_tck_rejects_echo_constant_out_of_order_cross_scope_conflict_and_malformed(
    store_kind,
) -> None:
    adapter = _BadAdapter()
    adapter.store_kind = store_kind
    result = run_scoped_trace_store_conformance_v2(adapter)
    assert not result.ok


def test_adapter_requests_never_contain_expected_answers() -> None:
    methods = (
        ScopedTraceStoreConformanceAdapterV2.create_store_v2,
        ScopedTraceStoreConformanceAdapterV2.restart_store_v2,
        ScopedTraceStoreConformanceAdapterV2.create_failure_injected_store_v2,
    )
    for method in methods:
        assert "expected" not in inspect.signature(method).parameters


def test_public_tck_and_trace_abi_modules_remain_locally_auditable() -> None:
    assert len(Path("pheroos/trace/scoped_store_v2.py").read_text().splitlines()) < 600
    assert (
        len(
            Path("pheroos/conformance/checks/scoped_trace_store_v2_contract.py")
            .read_text()
            .splitlines()
        )
        < 600
    )
