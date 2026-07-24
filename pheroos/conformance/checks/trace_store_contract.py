from __future__ import annotations

from typing import Protocol, runtime_checkable

from pheroos.conformance.report import CheckResult
from pheroos.trace import InMemoryTraceStore, TraceEvent, TraceStore


TRACE_STORE_CONFORMANCE_VERSION = "pheroos-trace-store-conformance-v1"


@runtime_checkable
class TraceStoreConformanceAdapter(Protocol):
    """Test fixture contract for an external append-only TraceStore backend."""

    implementation_id: str
    conformance_version: str

    def create_store(self) -> TraceStore: ...


class ReferenceTraceStoreConformanceAdapter:
    """Conformance fixture for the provider-free in-memory Trace store."""

    __slots__ = ()

    implementation_id = "pheroos-in-memory-trace-store-v1"
    conformance_version = TRACE_STORE_CONFORMANCE_VERSION

    def create_store(self) -> TraceStore:
        return InMemoryTraceStore()


def run_trace_store_conformance(
    adapter: TraceStoreConformanceAdapter,
) -> CheckResult:
    """Run append, validation, ordering, isolation, and freshness checks."""

    if not isinstance(adapter, TraceStoreConformanceAdapter):
        return CheckResult("trace_store_contract", False, "adapter_protocol")
    if (
        not isinstance(adapter.implementation_id, str)
        or not adapter.implementation_id
        or adapter.implementation_id != adapter.implementation_id.strip()
    ):
        return CheckResult(
            "trace_store_contract",
            False,
            "adapter_implementation_id",
        )
    if adapter.conformance_version != TRACE_STORE_CONFORMANCE_VERSION:
        return CheckResult("trace_store_contract", False, "adapter_version")
    problems: list[str] = []
    try:
        store = adapter.create_store()
        if not isinstance(store, TraceStore):
            return CheckResult("trace_store_contract", False, "store_protocol")
        _evaluate_trace_store(store, problems)
        fresh = adapter.create_store()
        if not isinstance(fresh, TraceStore):
            problems.append("fresh_store_protocol")
        elif fresh.records:
            problems.append("fresh_store_isolation")
    except Exception as exc:  # total-function boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(
        "trace_store_contract",
        not problems,
        ", ".join(problems),
    )


def check() -> CheckResult:
    return run_trace_store_conformance(ReferenceTraceStoreConformanceAdapter())


def _evaluate_trace_store(store: TraceStore, problems: list[str]) -> None:
    first = _exercise_first_append(store, problems)
    _exercise_snapshot_isolation(store, first, problems)
    _exercise_invalid_append(store, problems)
    _exercise_chronological_append(store, problems)


def _exercise_first_append(
    store: TraceStore,
    problems: list[str],
) -> TraceEvent:
    if store.records:
        problems.append("fresh_store_not_empty")

    first = TraceEvent(
        event_type="ext.pheroos.trace_store_conformance",
        protocol_id="protocol:trace-store-conformance",
        target="decision:trace-store-conformance",
        reason="verify append-only provider contract",
        lineage={"ordinal": 1},
    )
    first_record = store.append(first)
    if first_record.sequence != 0 or first_record.event != first:
        problems.append("first_record_binding")
    if store.records != (first_record,):
        problems.append("first_record_snapshot")
    return first


def _exercise_snapshot_isolation(
    store: TraceStore,
    first: TraceEvent,
    problems: list[str],
) -> None:
    first.lineage["ordinal"] = 999
    observed = store.records
    if not observed or observed[0].event.lineage != {"ordinal": 1}:
        problems.append("input_snapshot_isolation")
    if observed:
        observed[0].event.lineage["ordinal"] = 888
        if store.records[0].event.lineage != {"ordinal": 1}:
            problems.append("output_snapshot_isolation")


def _exercise_invalid_append(
    store: TraceStore,
    problems: list[str],
) -> None:
    before_invalid = store.records
    try:
        store.append(
            TraceEvent(
                event_type="not-namespaced",
                protocol_id="protocol:trace-store-conformance",
                target="decision:trace-store-conformance",
                reason="must fail before append",
            )
        )
    except ValueError:
        pass
    else:
        problems.append("invalid_event_accepted")
    if store.records != before_invalid:
        problems.append("invalid_event_mutated_store")


def _exercise_chronological_append(
    store: TraceStore,
    problems: list[str],
) -> None:
    second = TraceEvent(
        event_type="x-pheroos.trace_store_conformance_completed",
        protocol_id="protocol:trace-store-conformance",
        target="decision:trace-store-conformance",
        reason="verify chronological sequence",
        lineage={"ordinal": 2},
    )
    second_record = store.append(second)
    if second_record.sequence != 1 or second_record.event != second:
        problems.append("chronological_sequence")
    if tuple(record.sequence for record in store.records) != (0, 1):
        problems.append("record_order")


TraceStoreConformanceAdapter.__module__ = "pheroos.conformance"
ReferenceTraceStoreConformanceAdapter.__module__ = "pheroos.conformance"
run_trace_store_conformance.__module__ = "pheroos.conformance"


__all__ = [
    "ReferenceTraceStoreConformanceAdapter",
    "TRACE_STORE_CONFORMANCE_VERSION",
    "TraceStoreConformanceAdapter",
    "check",
    "run_trace_store_conformance",
]
