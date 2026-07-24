"""Durable, provider-neutral ABI for scope-bound Trace storage.

This module adds a versioned store boundary around ``ScopedTraceEvent`` v1.  It
does not alter that envelope's wire format and does not prescribe a database,
queue, event bus, or logging implementation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from pheroos.trace._scoped_store_v2_codec import (
    _canonical_event,
    _closed,
    _computed_root,
    _digest,
    _integer,
    _root,
    _text,
)
from pheroos.trace.scoped import ScopedTraceEvent

SCOPED_TRACE_STORE_VERSION_V2 = "pheroos-scoped-trace-store-v2"
SCOPED_TRACE_RECORD_VERSION_V2 = "pheroos-scoped-trace-record-v2"
SCOPED_TRACE_APPEND_RECEIPT_VERSION_V2 = "pheroos-scoped-trace-append-receipt-v2"
SCOPED_TRACE_CURSOR_VERSION_V2 = "pheroos-scoped-trace-cursor-v2"
SCOPED_TRACE_CHECKPOINT_VERSION_V2 = "pheroos-scoped-trace-checkpoint-v2"
SCOPED_TRACE_RETIREMENT_VERSION_V2 = "pheroos-scoped-trace-retirement-v2"

_FAILURE_STAGES = frozenset(
    {"append_before_publish", "retire_before_publish", "checkpoint_before_return"}
)


@dataclass(frozen=True)
class ScopedTraceRecordV2:
    scope_ref: str
    stream: str
    sequence: int
    event: ScopedTraceEvent
    record_root: str = ""
    version: str = SCOPED_TRACE_RECORD_VERSION_V2

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != SCOPED_TRACE_RECORD_VERSION_V2
        ):
            raise ValueError("scoped trace record version is unsupported")
        scope_ref = _root(self.scope_ref, "record scope_ref")
        stream = _text(self.stream, "record stream")
        sequence = _integer(self.sequence, "record sequence")
        event = _canonical_event(self.event)
        if event.scope_ref != scope_ref or event.stream != stream:
            raise ValueError("scoped trace record binding does not match its envelope")
        core = {
            "event": event.to_dict(),
            "scope_ref": scope_ref,
            "sequence": sequence,
            "stream": stream,
            "version": self.version,
        }
        computed = _digest(core)
        object.__setattr__(self, "event", event)
        object.__setattr__(
            self,
            "record_root",
            _computed_root(self.record_root, computed, "scoped trace record root"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "stream": self.stream,
            "sequence": self.sequence,
            "event": self.event.to_dict(),
            "record_root": self.record_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopedTraceRecordV2:
        raw = _closed(
            payload,
            frozenset(
                {"version", "scope_ref", "stream", "sequence", "event", "record_root"}
            ),
            "scoped trace record",
        )
        event = raw["event"]
        if type(event) is not dict:
            raise ValueError("scoped trace record event must be an object")
        return cls(
            version=raw["version"],
            scope_ref=raw["scope_ref"],
            stream=raw["stream"],
            sequence=raw["sequence"],
            event=ScopedTraceEvent.from_dict(deepcopy(event)),
            record_root=raw["record_root"],
        )


@dataclass(frozen=True)
class ScopedTraceAppendReceiptV2:
    disposition: str
    record: ScopedTraceRecordV2
    receipt_root: str = ""
    version: str = SCOPED_TRACE_APPEND_RECEIPT_VERSION_V2

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != SCOPED_TRACE_APPEND_RECEIPT_VERSION_V2
        ):
            raise ValueError("scoped trace receipt version is unsupported")
        if type(self.disposition) is not str or self.disposition not in {
            "appended",
            "replayed",
        }:
            raise ValueError("scoped trace receipt disposition is unsupported")
        if not isinstance(self.record, ScopedTraceRecordV2):
            raise TypeError("scoped trace receipt requires a v2 record")
        record = ScopedTraceRecordV2.from_dict(self.record.to_dict())
        computed = _digest(
            {
                "disposition": self.disposition,
                "record_root": record.record_root,
                "version": self.version,
            }
        )
        object.__setattr__(self, "record", record)
        object.__setattr__(
            self,
            "receipt_root",
            _computed_root(self.receipt_root, computed, "scoped trace receipt root"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "disposition": self.disposition,
            "record": self.record.to_dict(),
            "receipt_root": self.receipt_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopedTraceAppendReceiptV2:
        raw = _closed(
            payload,
            frozenset({"version", "disposition", "record", "receipt_root"}),
            "scoped trace receipt",
        )
        if type(raw["record"]) is not dict:
            raise ValueError("scoped trace receipt record must be an object")
        return cls(
            version=raw["version"],
            disposition=raw["disposition"],
            record=ScopedTraceRecordV2.from_dict(raw["record"]),
            receipt_root=raw["receipt_root"],
        )


@dataclass(frozen=True)
class ScopedTraceCursorV2:
    scope_ref: str
    stream: str
    next_sequence: int
    prefix_root: str
    cursor_root: str = ""
    version: str = SCOPED_TRACE_CURSOR_VERSION_V2

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != SCOPED_TRACE_CURSOR_VERSION_V2
        ):
            raise ValueError("scoped trace cursor version is unsupported")
        _root(self.scope_ref, "cursor scope_ref")
        _text(self.stream, "cursor stream")
        _integer(self.next_sequence, "cursor next_sequence")
        _root(self.prefix_root, "cursor prefix_root")
        computed = _digest(
            {
                "next_sequence": self.next_sequence,
                "prefix_root": self.prefix_root,
                "scope_ref": self.scope_ref,
                "stream": self.stream,
                "version": self.version,
            }
        )
        object.__setattr__(
            self,
            "cursor_root",
            _computed_root(self.cursor_root, computed, "scoped trace cursor root"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "stream": self.stream,
            "next_sequence": self.next_sequence,
            "prefix_root": self.prefix_root,
            "cursor_root": self.cursor_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopedTraceCursorV2:
        raw = _closed(
            payload,
            frozenset(
                {
                    "version",
                    "scope_ref",
                    "stream",
                    "next_sequence",
                    "prefix_root",
                    "cursor_root",
                }
            ),
            "scoped trace cursor",
        )
        return cls(
            version=raw["version"],
            scope_ref=raw["scope_ref"],
            stream=raw["stream"],
            next_sequence=raw["next_sequence"],
            prefix_root=raw["prefix_root"],
            cursor_root=raw["cursor_root"],
        )


@dataclass(frozen=True)
class ScopedTraceRetirementV2:
    scope_ref: str
    history_root: str
    retirement_root: str = ""
    version: str = SCOPED_TRACE_RETIREMENT_VERSION_V2

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != SCOPED_TRACE_RETIREMENT_VERSION_V2
        ):
            raise ValueError("scoped trace retirement version is unsupported")
        _root(self.scope_ref, "retirement scope_ref")
        _root(self.history_root, "retirement history_root")
        computed = _digest(
            {
                "history_root": self.history_root,
                "scope_ref": self.scope_ref,
                "version": self.version,
            }
        )
        object.__setattr__(
            self,
            "retirement_root",
            _computed_root(
                self.retirement_root, computed, "scoped trace retirement root"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "history_root": self.history_root,
            "retirement_root": self.retirement_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopedTraceRetirementV2:
        raw = _closed(
            payload,
            frozenset({"version", "scope_ref", "history_root", "retirement_root"}),
            "scoped trace retirement",
        )
        return cls(
            version=raw["version"],
            scope_ref=raw["scope_ref"],
            history_root=raw["history_root"],
            retirement_root=raw["retirement_root"],
        )


@dataclass(frozen=True)
class ScopedTraceCheckpointV2:
    records: tuple[ScopedTraceRecordV2, ...]
    retirements: tuple[ScopedTraceRetirementV2, ...]
    checkpoint_root: str = ""
    version: str = SCOPED_TRACE_CHECKPOINT_VERSION_V2

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != SCOPED_TRACE_CHECKPOINT_VERSION_V2
        ):
            raise ValueError("scoped trace checkpoint version is unsupported")
        if type(self.records) is not tuple or type(self.retirements) is not tuple:
            raise ValueError("scoped trace checkpoint collections must be tuples")
        records = tuple(
            ScopedTraceRecordV2.from_dict(item.to_dict()) for item in self.records
        )
        retirements = tuple(
            ScopedTraceRetirementV2.from_dict(item.to_dict())
            for item in self.retirements
        )
        record_keys = tuple(
            (item.scope_ref, item.stream, item.sequence) for item in records
        )
        retirement_keys = tuple(item.scope_ref for item in retirements)
        if record_keys != tuple(sorted(record_keys)):
            raise ValueError("scoped trace checkpoint records are not canonical order")
        if retirement_keys != tuple(sorted(retirement_keys)):
            raise ValueError(
                "scoped trace checkpoint retirements are not canonical order"
            )
        computed = _digest(
            {
                "records": [item.to_dict() for item in records],
                "retirements": [item.to_dict() for item in retirements],
                "version": self.version,
            }
        )
        object.__setattr__(self, "records", records)
        object.__setattr__(self, "retirements", retirements)
        object.__setattr__(
            self,
            "checkpoint_root",
            _computed_root(
                self.checkpoint_root, computed, "scoped trace checkpoint root"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "records": [item.to_dict() for item in self.records],
            "retirements": [item.to_dict() for item in self.retirements],
            "checkpoint_root": self.checkpoint_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopedTraceCheckpointV2:
        raw = _closed(
            payload,
            frozenset({"version", "records", "retirements", "checkpoint_root"}),
            "scoped trace checkpoint",
        )
        if type(raw["records"]) is not list or type(raw["retirements"]) is not list:
            raise ValueError("scoped trace checkpoint collections must be arrays")
        if any(
            type(item) is not dict for item in (*raw["records"], *raw["retirements"])
        ):
            raise ValueError("scoped trace checkpoint entries must be objects")
        return cls(
            version=raw["version"],
            records=tuple(
                ScopedTraceRecordV2.from_dict(item) for item in raw["records"]
            ),
            retirements=tuple(
                ScopedTraceRetirementV2.from_dict(item) for item in raw["retirements"]
            ),
            checkpoint_root=raw["checkpoint_root"],
        )


@runtime_checkable
class ScopedTraceStoreV2(Protocol):
    store_version: str

    def append_scoped_v2(
        self, event: ScopedTraceEvent
    ) -> ScopedTraceAppendReceiptV2: ...
    def snapshot_scoped_v2(
        self, scope_ref: str, stream: str, cursor: ScopedTraceCursorV2 | None = None
    ) -> tuple[ScopedTraceRecordV2, ...]: ...
    def cursor_scoped_v2(self, scope_ref: str, stream: str) -> ScopedTraceCursorV2: ...
    def retire_scope_v2(self, scope_ref: str) -> ScopedTraceRetirementV2: ...
    def checkpoint_v2(self) -> ScopedTraceCheckpointV2: ...
    def restart_v2(self, checkpoint: ScopedTraceCheckpointV2) -> ScopedTraceStoreV2: ...


class InMemoryScopedTraceStoreV2:
    """Thread-safe stdlib reference store with deterministic restart images."""

    store_version = SCOPED_TRACE_STORE_VERSION_V2

    def __init__(
        self,
        checkpoint: ScopedTraceCheckpointV2 | None = None,
        *,
        failure_stage: str | None = None,
    ) -> None:
        if failure_stage is not None and failure_stage not in _FAILURE_STAGES:
            raise ValueError("scoped trace failure stage is unsupported")
        self._lock = RLock()
        self._failure_stage = failure_stage
        self._records: dict[tuple[str, str], list[ScopedTraceRecordV2]] = {}
        self._identities: dict[tuple[str, str, str, str], ScopedTraceRecordV2] = {}
        self._retirements: dict[str, ScopedTraceRetirementV2] = {}
        if checkpoint is not None:
            self._restore(checkpoint)

    def _fail(self, stage: str) -> None:
        if self._failure_stage == stage:
            raise RuntimeError(f"injected scoped trace failure: {stage}")

    def append_scoped_v2(self, event: ScopedTraceEvent) -> ScopedTraceAppendReceiptV2:
        envelope = _canonical_event(event)
        key = (envelope.scope_ref, envelope.stream)
        with self._lock:
            if envelope.scope_ref in self._retirements:
                raise ValueError("scoped trace scope is retired")
            possible = (
                self._identities.get((*key, "trace", envelope.trace_id)),
                self._identities.get((*key, "transition", envelope.transition_id)),
            )
            matches = tuple(item for item in possible if item is not None)
            if matches:
                distinct = {item.record_root for item in matches}
                if (
                    len(distinct) != 1
                    or matches[0].event.envelope_root != envelope.envelope_root
                ):
                    raise ValueError(
                        "scoped trace identity replay changed its envelope"
                    )
                return ScopedTraceAppendReceiptV2("replayed", deepcopy(matches[0]))
            sequence = len(self._records.get(key, ()))
            record = ScopedTraceRecordV2(
                envelope.scope_ref, envelope.stream, sequence, envelope
            )
            self._fail("append_before_publish")
            self._records.setdefault(key, []).append(record)
            self._identities[(*key, "trace", envelope.trace_id)] = record
            self._identities[(*key, "transition", envelope.transition_id)] = record
            return ScopedTraceAppendReceiptV2("appended", deepcopy(record))

    def snapshot_scoped_v2(
        self, scope_ref: str, stream: str, cursor: ScopedTraceCursorV2 | None = None
    ) -> tuple[ScopedTraceRecordV2, ...]:
        scope_ref = _root(scope_ref, "snapshot scope_ref")
        stream = _text(stream, "snapshot stream")
        with self._lock:
            records = self._records.get((scope_ref, stream), ())
            start = 0
            if cursor is not None:
                cursor = ScopedTraceCursorV2.from_dict(cursor.to_dict())
                if cursor.scope_ref != scope_ref or cursor.stream != stream:
                    raise ValueError("scoped trace cursor binding mismatch")
                if cursor.next_sequence > len(
                    records
                ) or cursor.prefix_root != _prefix_root(
                    records[: cursor.next_sequence]
                ):
                    raise ValueError("scoped trace cursor is stale or forged")
                start = cursor.next_sequence
            return tuple(deepcopy(records[start:]))

    def cursor_scoped_v2(self, scope_ref: str, stream: str) -> ScopedTraceCursorV2:
        scope_ref = _root(scope_ref, "cursor scope_ref")
        stream = _text(stream, "cursor stream")
        with self._lock:
            records = self._records.get((scope_ref, stream), ())
            return ScopedTraceCursorV2(
                scope_ref, stream, len(records), _prefix_root(records)
            )

    def retire_scope_v2(self, scope_ref: str) -> ScopedTraceRetirementV2:
        scope_ref = _root(scope_ref, "retirement scope_ref")
        with self._lock:
            existing = self._retirements.get(scope_ref)
            if existing is not None:
                return deepcopy(existing)
            retirement = ScopedTraceRetirementV2(
                scope_ref, self._scope_history_root(scope_ref)
            )
            self._fail("retire_before_publish")
            self._retirements[scope_ref] = retirement
            return deepcopy(retirement)

    def checkpoint_v2(self) -> ScopedTraceCheckpointV2:
        with self._lock:
            records = tuple(
                record for key in sorted(self._records) for record in self._records[key]
            )
            retirements = tuple(
                self._retirements[key] for key in sorted(self._retirements)
            )
            checkpoint = ScopedTraceCheckpointV2(records, retirements)
            self._fail("checkpoint_before_return")
            return deepcopy(checkpoint)

    def restart_v2(self, checkpoint: ScopedTraceCheckpointV2) -> ScopedTraceStoreV2:
        return InMemoryScopedTraceStoreV2(
            ScopedTraceCheckpointV2.from_dict(checkpoint.to_dict())
        )

    def _scope_history_root(self, scope_ref: str) -> str:
        records = [
            item.to_dict()
            for key in sorted(self._records)
            if key[0] == scope_ref
            for item in self._records[key]
        ]
        return _digest(
            {
                "records": records,
                "scope_ref": scope_ref,
                "version": SCOPED_TRACE_STORE_VERSION_V2,
            }
        )

    def _restore(self, checkpoint: ScopedTraceCheckpointV2) -> None:
        checkpoint = ScopedTraceCheckpointV2.from_dict(checkpoint.to_dict())
        for record in checkpoint.records:
            key = (record.scope_ref, record.stream)
            records = self._records.setdefault(key, [])
            if record.sequence != len(records):
                raise ValueError("scoped trace checkpoint sequence is not contiguous")
            for kind, identity in (
                ("trace", record.event.trace_id),
                ("transition", record.event.transition_id),
            ):
                identity_key = (*key, kind, identity)
                if identity_key in self._identities:
                    raise ValueError(
                        "scoped trace checkpoint contains duplicate identity"
                    )
                self._identities[identity_key] = record
            records.append(record)
        for retirement in checkpoint.retirements:
            if retirement.scope_ref in self._retirements:
                raise ValueError(
                    "scoped trace checkpoint contains duplicate retirement"
                )
            if retirement.history_root != self._scope_history_root(
                retirement.scope_ref
            ):
                raise ValueError("scoped trace retirement history root mismatch")
            self._retirements[retirement.scope_ref] = retirement


def _prefix_root(records: Sequence[ScopedTraceRecordV2]) -> str:
    return _digest(
        {
            "record_roots": [item.record_root for item in records],
            "version": SCOPED_TRACE_CURSOR_VERSION_V2,
        }
    )


for _public in (
    ScopedTraceRecordV2,
    ScopedTraceAppendReceiptV2,
    ScopedTraceCursorV2,
    ScopedTraceRetirementV2,
    ScopedTraceCheckpointV2,
    ScopedTraceStoreV2,
    InMemoryScopedTraceStoreV2,
):
    _public.__module__ = "pheroos.trace"


__all__ = [
    "SCOPED_TRACE_APPEND_RECEIPT_VERSION_V2",
    "SCOPED_TRACE_CHECKPOINT_VERSION_V2",
    "SCOPED_TRACE_CURSOR_VERSION_V2",
    "SCOPED_TRACE_RECORD_VERSION_V2",
    "SCOPED_TRACE_RETIREMENT_VERSION_V2",
    "SCOPED_TRACE_STORE_VERSION_V2",
    "InMemoryScopedTraceStoreV2",
    "ScopedTraceAppendReceiptV2",
    "ScopedTraceCheckpointV2",
    "ScopedTraceCursorV2",
    "ScopedTraceRecordV2",
    "ScopedTraceRetirementV2",
    "ScopedTraceStoreV2",
]
