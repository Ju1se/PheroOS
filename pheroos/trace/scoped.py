from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from pheroos.trace.commit_contracts import COMMIT_EVENT_TYPES
from pheroos.trace.event import TraceEvent


SCOPED_TRACE_EVENT_VERSION = "pheroos-scoped-trace-event-v1"
SCOPED_TRACE_EVENT_SCHEMA_ID = (
    "https://pheroos.dev/schemas/scoped-trace-event-v1.schema.json"
)
_SCOPE_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ScopedTraceEvent:
    """Outer scope binding for a canonical v1 TraceEvent.

    The envelope keeps tenant/run identity out of the event body and therefore
    leaves existing TraceEvent and Commit Wire v1 roots byte-stable.
    """

    scope_ref: str
    stream: str
    transition_id: str
    trace_id: str
    event: TraceEvent
    event_root: str = ""
    envelope_root: str = ""
    version: str = SCOPED_TRACE_EVENT_VERSION

    def __post_init__(self) -> None:
        if self.version != SCOPED_TRACE_EVENT_VERSION:
            raise ValueError("scoped trace event version is unsupported")
        if not isinstance(self.scope_ref, str) or not _SCOPE_PATTERN.fullmatch(
            self.scope_ref
        ):
            raise ValueError("scoped trace event scope_ref must be canonical sha256")
        for name, value in (
            ("stream", self.stream),
            ("transition_id", self.transition_id),
            ("trace_id", self.trace_id),
        ):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"scoped trace event {name} must be canonical nonblank text")
        if not isinstance(self.event, TraceEvent):
            raise TypeError("scoped trace event requires a canonical TraceEvent")
        event = deepcopy(self.event)
        event.validate()
        lineage_id = (
            event.lineage.get("event_id")
            if event.event_type in COMMIT_EVENT_TYPES
            else event.lineage.get("trace_event_id")
        )
        if lineage_id is not None and lineage_id != self.trace_id:
            raise ValueError("scoped trace id does not match canonical event lineage")
        object.__setattr__(self, "event", event)
        computed = _event_root(event)
        if self.event_root and self.event_root != computed:
            raise ValueError("scoped trace event root does not match its event")
        object.__setattr__(self, "event_root", computed)
        computed_envelope = _envelope_root(
            scope_ref=self.scope_ref,
            stream=self.stream,
            transition_id=self.transition_id,
            trace_id=self.trace_id,
            event_root=computed,
        )
        if self.envelope_root and self.envelope_root != computed_envelope:
            raise ValueError("scoped trace envelope root does not match its binding")
        object.__setattr__(self, "envelope_root", computed_envelope)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "stream": self.stream,
            "transition_id": self.transition_id,
            "trace_id": self.trace_id,
            "event": {
                "event_type": self.event.event_type,
                "protocol_id": self.event.protocol_id,
                "target": self.event.target,
                "reason": self.event.reason,
                "lineage": deepcopy(self.event.lineage),
            },
            "event_root": self.event_root,
            "envelope_root": self.envelope_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopedTraceEvent:
        fields = {
            "version",
            "scope_ref",
            "stream",
            "transition_id",
            "trace_id",
            "event",
            "event_root",
            "envelope_root",
        }
        if not isinstance(payload, Mapping) or set(payload) != fields:
            raise ValueError("scoped trace event fields are invalid")
        event = payload["event"]
        event_fields = {"event_type", "protocol_id", "target", "reason", "lineage"}
        if not isinstance(event, Mapping) or set(event) != event_fields:
            raise ValueError("scoped trace event body fields are invalid")
        lineage = event["lineage"]
        if not isinstance(lineage, Mapping):
            raise ValueError("scoped trace event lineage must be an object")
        return cls(
            version=payload["version"],
            scope_ref=payload["scope_ref"],
            stream=payload["stream"],
            transition_id=payload["transition_id"],
            trace_id=payload["trace_id"],
            event=TraceEvent(
                event_type=event["event_type"],
                protocol_id=event["protocol_id"],
                target=event["target"],
                reason=event["reason"],
                lineage=deepcopy(dict(lineage)),
            ),
            event_root=payload["event_root"],
            envelope_root=payload["envelope_root"],
        )


def scoped_trace_event_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCOPED_TRACE_EVENT_SCHEMA_ID,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "version",
            "scope_ref",
            "stream",
            "transition_id",
            "trace_id",
            "event",
            "event_root",
            "envelope_root",
        ],
        "properties": {
            "version": {"const": SCOPED_TRACE_EVENT_VERSION},
            "scope_ref": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "stream": {"type": "string", "minLength": 1},
            "transition_id": {"type": "string", "minLength": 1},
            "trace_id": {"type": "string", "minLength": 1},
            "event": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "event_type",
                    "protocol_id",
                    "target",
                    "reason",
                    "lineage",
                ],
                "properties": {
                    "event_type": {"type": "string", "minLength": 1},
                    "protocol_id": {"type": "string", "minLength": 1},
                    "target": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                    "lineage": {"type": "object"},
                },
            },
            "event_root": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "envelope_root": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
        },
    }


def _event_root(event: TraceEvent) -> str:
    canonical = json.dumps(
        {
            "event": {
                "event_type": event.event_type,
                "lineage": event.lineage,
                "protocol_id": event.protocol_id,
                "reason": event.reason,
                "target": event.target,
            },
            "version": SCOPED_TRACE_EVENT_VERSION,
        },
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _envelope_root(
    *,
    scope_ref: str,
    stream: str,
    transition_id: str,
    trace_id: str,
    event_root: str,
) -> str:
    canonical = json.dumps(
        {
            "event_root": event_root,
            "scope_ref": scope_ref,
            "stream": stream,
            "trace_id": trace_id,
            "transition_id": transition_id,
            "version": SCOPED_TRACE_EVENT_VERSION,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "SCOPED_TRACE_EVENT_SCHEMA_ID",
    "SCOPED_TRACE_EVENT_VERSION",
    "ScopedTraceEvent",
    "scoped_trace_event_schema",
]
