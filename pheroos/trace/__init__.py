from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


VALID_EVENT_TYPES = frozenset(
    {
        "plan",
        "grant",
        "expose",
        "invoke",
        "evidence",
        "signal",
        "block",
        "commit",
        "recovery",
        "output",
    }
)


@dataclass(frozen=True)
class TraceEvent:
    event_type: str
    protocol_id: str
    target: str
    reason: str
    lineage: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in VALID_EVENT_TYPES:
            raise ValueError(f"unsupported trace event type: {self.event_type}")
        if not self.protocol_id:
            raise ValueError("trace event protocol_id is required")
        if not self.target:
            raise ValueError("trace event target is required")


@dataclass(frozen=True)
class TraceRecord:
    sequence: int
    event: TraceEvent


@dataclass
class InMemoryTraceStore:
    _records: list[TraceRecord] = field(default_factory=list)

    def append(self, event: TraceEvent) -> TraceRecord:
        event.validate()
        record = TraceRecord(sequence=len(self._records), event=event)
        self._records.append(record)
        return record

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        return tuple(self._records)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(record.event for record in self._records)

    def require_events(self, required_events: Iterable[str]) -> list[str]:
        return missing_required_events(self.events, required_events)


def missing_required_events(events: Iterable[TraceEvent], required_events: Iterable[str]) -> list[str]:
    observed = {event.event_type for event in events}
    return sorted({event_type for event_type in required_events if event_type not in observed})


__all__ = [
    "InMemoryTraceStore",
    "TraceEvent",
    "TraceRecord",
    "VALID_EVENT_TYPES",
    "missing_required_events",
]
