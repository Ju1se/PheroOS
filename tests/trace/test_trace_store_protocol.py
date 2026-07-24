from __future__ import annotations

import inspect
import pickle
import typing

import pheroos.trace as trace
from pheroos.trace import store


class _ProviderTraceStore:
    """Small independent structural provider used only to prove the ABI."""

    def __init__(self) -> None:
        self._records: tuple[trace.TraceRecord, ...] = ()

    def append(self, event: trace.TraceEvent) -> trace.TraceRecord:
        event.validate()
        record = trace.TraceRecord(sequence=len(self._records), event=event)
        self._records = (*self._records, record)
        return record

    @property
    def records(self) -> tuple[trace.TraceRecord, ...]:
        return self._records


class _AppendWithoutRecords:
    def append(self, event: trace.TraceEvent) -> trace.TraceRecord:
        return trace.TraceRecord(sequence=0, event=event)


def test_trace_store_is_minimal_provider_neutral_public_abi() -> None:
    assert trace.TraceStore is store.TraceStore
    assert trace.TraceStore.__module__ == "pheroos.trace"
    assert "TraceStore" in trace.__all__
    assert pickle.loads(pickle.dumps(trace.TraceStore)) is trace.TraceStore

    public_members = {
        name for name in trace.TraceStore.__dict__ if not name.startswith("_")
    }
    assert public_members == {"append", "records"}
    assert inspect.signature(trace.TraceStore.append) == inspect.signature(
        trace.InMemoryTraceStore.append
    )
    assert typing.get_type_hints(trace.TraceStore.append) == {
        "event": trace.TraceEvent,
        "return": trace.TraceRecord,
    }
    assert (
        typing.get_type_hints(trace.TraceStore.records.fget)["return"]
        == (tuple[trace.TraceRecord, ...])
    )


def test_in_memory_and_independent_stores_structurally_conform() -> None:
    in_memory = trace.InMemoryTraceStore()
    provider = _ProviderTraceStore()

    assert isinstance(in_memory, trace.TraceStore)
    assert isinstance(provider, trace.TraceStore)
    assert not isinstance(_AppendWithoutRecords(), trace.TraceStore)

    event = trace.TraceEvent(
        event_type="ext.provider_neutral",
        protocol_id="protocol:trace-store",
        target="decision:trace-store",
        reason="prove provider-neutral structural conformance",
    )
    record = provider.append(event)

    assert record.sequence == 0
    assert provider.records == (record,)
