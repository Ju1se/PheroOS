from __future__ import annotations

from copy import deepcopy

from pheroos.conformance import (
    TRACE_STORE_CONFORMANCE_VERSION,
    TraceStoreConformanceAdapter,
    run_trace_store_conformance,
)
from pheroos.conformance.checks import trace_store_contract
from pheroos.trace import TraceEvent, TraceRecord, TraceStore


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
