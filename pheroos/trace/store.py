from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable, Protocol, runtime_checkable

from pheroos.trace.commit_contracts import COMMIT_EVENT_TYPES
from pheroos.trace.event import TraceEvent


@dataclass(frozen=True)
class TraceRecord:
    sequence: int
    event: TraceEvent


@runtime_checkable
class TraceStore(Protocol):
    """Provider-neutral append-only storage boundary for canonical Trace records.

    Implementations may persist records however they choose, but the public
    boundary exposes only append and an immutable chronological snapshot.  It
    deliberately does not prescribe databases, transactions, queues, or
    provider lifecycle.
    """

    def append(self, event: TraceEvent) -> TraceRecord:
        """Validate and append one canonical event, returning its record."""

        ...

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        """Return an immutable chronological snapshot of appended records."""

        ...


class InMemoryTraceStore:
    __slots__ = ("__records", "__commit_event_ids")

    def __init__(self) -> None:
        self.__records: list[TraceRecord] = []
        self.__commit_event_ids: dict[str, int] = {}

    def append(self, event: TraceEvent) -> TraceRecord:
        # Validation happens before mutation.  The stored event and the record
        # returned to the caller are independent deep snapshots, so neither the
        # input event nor a returned lineage container can rewrite history.
        snapshot = deepcopy(event)
        snapshot.validate()
        if snapshot.event_type in COMMIT_EVENT_TYPES:
            event_id = snapshot.lineage["event_id"]
            existing_sequence = self.__commit_event_ids.get(event_id)
            if existing_sequence is not None:
                existing = self.__records[existing_sequence]
                if existing.event != snapshot:
                    raise ValueError("commit trace event id replay changed its payload")
                return deepcopy(existing)
        record = TraceRecord(sequence=len(self.__records), event=snapshot)
        self.__records.append(record)
        if snapshot.event_type in COMMIT_EVENT_TYPES:
            self.__commit_event_ids[snapshot.lineage["event_id"]] = record.sequence
        return deepcopy(record)

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        return tuple(deepcopy(self.__records))

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(deepcopy(record.event) for record in self.__records)

    def require_events(self, required_events: Iterable[str]) -> list[str]:
        return missing_required_events(self.events, required_events)


def missing_required_events(
    events: Iterable[TraceEvent],
    required_events: Iterable[str],
) -> list[str]:
    observed = {event.event_type for event in events}
    return sorted(
        {event_type for event_type in required_events if event_type not in observed}
    )


TraceRecord.__module__ = "pheroos.trace"
TraceStore.__module__ = "pheroos.trace"
InMemoryTraceStore.__module__ = "pheroos.trace"
missing_required_events.__module__ = "pheroos.trace"


__all__: tuple[str, ...] = ()
