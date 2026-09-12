from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from pheroos.conformance import (
    TRACE_STORE_CONFORMANCE_VERSION,
    TraceStoreConformanceAdapter,
    run_trace_store_conformance,
)
from pheroos.conformance.checks import trace_store_contract
from pheroos.trace import InMemoryTraceStore, TraceEvent, TraceRecord, TraceStore


class _ExternalTraceStore:
    def __init__(self) -> None:
        self._records: list[TraceRecord] = []

    def append(self, event: TraceEvent) -> TraceRecord:
        snapshot = deepcopy(event)
        snapshot.validate()
        record = TraceRecord(len(self._records), snapshot)
        self._records.append(record)
        return deepcopy(record)

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        return tuple(deepcopy(self._records))


class _ExternalTraceStoreAdapter:
    implementation_id = "example-external-trace-store-v1"
    conformance_version = TRACE_STORE_CONFORMANCE_VERSION

    def create_store(self) -> TraceStore:
        return _ExternalTraceStore()


def test_reference_trace_store_contract_is_active_and_complete() -> None:
    result = trace_store_contract.check()

    assert result.ok is True, result.detail
    assert result.name == "trace_store_contract"
    assert result.detail == ""


def test_independent_external_trace_store_runs_the_same_matrix() -> None:
    adapter = _ExternalTraceStoreAdapter()

    assert isinstance(adapter, TraceStoreConformanceAdapter)
    result = run_trace_store_conformance(adapter)

    assert result.ok is True, result.detail


def test_trace_store_conformance_rejects_an_incomplete_adapter() -> None:
    class Incomplete:
        implementation_id = "incomplete-v1"

    result = run_trace_store_conformance(Incomplete())  # type: ignore[arg-type]

    assert result.ok is False
    assert result.detail == "adapter_protocol"


def test_trace_store_conformance_rejects_an_unknown_matrix_version() -> None:
    class UnknownVersion(_ExternalTraceStoreAdapter):
        conformance_version = "pheroos-trace-store-conformance-v999"

    result = run_trace_store_conformance(UnknownVersion())

    assert result.ok is False
    assert result.detail == "adapter_version"


def test_trace_store_conformance_detects_mutable_history() -> None:
    class LeakyStore:
        def __init__(self) -> None:
            self._records: list[TraceRecord] = []

        def append(self, event: TraceEvent) -> TraceRecord:
            event.validate()
            record = TraceRecord(len(self._records), event)
            self._records.append(record)
            return record

        @property
        def records(self) -> tuple[TraceRecord, ...]:
            return tuple(self._records)

    class LeakyAdapter:
        implementation_id = "leaky-trace-store-v1"
        conformance_version = TRACE_STORE_CONFORMANCE_VERSION

        def create_store(self) -> TraceStore:
            return LeakyStore()

    result = run_trace_store_conformance(LeakyAdapter())

    assert result.ok is False
    assert "input_snapshot_isolation" in result.detail
    assert "output_snapshot_isolation" in result.detail


class _BrokenTraceStore:
    def __init__(self) -> None:
        self._records: list[TraceRecord] = []

    def append(self, event):
        stored = TraceRecord(sequence=8, event=event)
        self._records.append(stored)
        return TraceRecord(sequence=9, event=event)

    @property
    def records(self):
        return tuple(self._records)


class _TraceAdapter:
    implementation_id = "test-trace-store"
    conformance_version = trace_store_contract.TRACE_STORE_CONFORMANCE_VERSION

    def __init__(self, stores) -> None:
        self._stores = iter(stores)

    def create_store(self):
        return next(self._stores)


@pytest.mark.parametrize("implementation_id", [1, "", " spaced "])
def test_trace_store_adapter_identity_is_canonical(implementation_id: object) -> None:
    adapter = SimpleNamespace(
        implementation_id=implementation_id,
        conformance_version=trace_store_contract.TRACE_STORE_CONFORMANCE_VERSION,
        create_store=InMemoryTraceStore,
    )
    result = trace_store_contract.run_trace_store_conformance(adapter)
    assert result.ok is False
    assert result.detail == "adapter_implementation_id"


def test_trace_store_conformance_reports_external_backend_contract_failures() -> None:
    protocol_failure = trace_store_contract.run_trace_store_conformance(object())
    assert protocol_failure.detail == "adapter_protocol"

    bad_version = SimpleNamespace(
        implementation_id="test-trace-store",
        conformance_version="unsupported",
        create_store=InMemoryTraceStore,
    )
    assert trace_store_contract.run_trace_store_conformance(bad_version).detail == (
        "adapter_version"
    )

    non_store = _TraceAdapter([object()])
    assert trace_store_contract.run_trace_store_conformance(non_store).detail == (
        "store_protocol"
    )

    bad_fresh = _TraceAdapter([InMemoryTraceStore(), object()])
    fresh_result = trace_store_contract.run_trace_store_conformance(bad_fresh)
    assert fresh_result.ok is False
    assert fresh_result.detail == "fresh_store_protocol"

    prepopulated = InMemoryTraceStore()
    prepopulated.append(
        trace_store_contract.TraceEvent(
            event_type="x-test.preexisting",
            protocol_id="protocol:test",
            target="decision:test",
            reason="preexisting record",
        )
    )
    isolated = _TraceAdapter([InMemoryTraceStore(), prepopulated])
    isolation_result = trace_store_contract.run_trace_store_conformance(isolated)
    assert isolation_result.ok is False
    assert isolation_result.detail == "fresh_store_isolation"

    broken = _TraceAdapter([_BrokenTraceStore(), _BrokenTraceStore()])
    broken_result = trace_store_contract.run_trace_store_conformance(broken)
    assert broken_result.ok is False
    assert set(broken_result.detail.split(", ")) >= {
        "first_record_binding",
        "first_record_snapshot",
        "input_snapshot_isolation",
        "output_snapshot_isolation",
        "invalid_event_accepted",
        "invalid_event_mutated_store",
        "chronological_sequence",
        "record_order",
    }

    exhausted = _TraceAdapter([])
    exception_result = trace_store_contract.run_trace_store_conformance(exhausted)
    assert exception_result.ok is False
    assert exception_result.detail.startswith("adapter_exception:StopIteration")
