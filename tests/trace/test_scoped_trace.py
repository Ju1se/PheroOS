from __future__ import annotations

from dataclasses import replace
import json

import pytest

from pheroos.kernel import runtime_scope_ref
from pheroos.trace import (
    SCOPED_TRACE_EVENT_SCHEMA_ID,
    SCOPED_TRACE_EVENT_VERSION,
    ScopedTraceEvent,
    TraceEvent,
    scoped_trace_event_schema,
)


def scoped_event() -> ScopedTraceEvent:
    return ScopedTraceEvent(
        scope_ref=runtime_scope_ref("tenant-a", "run-1"),
        stream="governance:commit",
        transition_id="transition:1",
        trace_id="trace:1",
        event=TraceEvent(
            event_type="plan",
            protocol_id="protocol:one",
            target="decision:one",
            reason="scope binding",
            lineage={"details": {"values": [1]}},
        ),
    )


def test_scoped_trace_round_trip_binds_opaque_scope_without_changing_inner_event() -> (
    None
):
    envelope = scoped_event()
    portable = json.loads(json.dumps(envelope.to_dict()))

    restored = ScopedTraceEvent.from_dict(portable)

    assert restored == envelope
    assert restored.version == SCOPED_TRACE_EVENT_VERSION
    assert restored.scope_ref.startswith("sha256:")
    assert "tenant-a" not in json.dumps(portable)
    assert restored.event == envelope.event


def test_scoped_trace_defensively_snapshots_event_and_portable_views() -> None:
    event = TraceEvent(
        event_type="plan",
        protocol_id="protocol:one",
        target="decision:one",
        reason="snapshot",
        lineage={"nested": {"values": [1]}},
    )
    envelope = ScopedTraceEvent(
        scope_ref=runtime_scope_ref("tenant-a", "run-1"),
        stream="commit",
        transition_id="transition:1",
        trace_id="trace:1",
        event=event,
    )
    event.lineage["nested"]["values"].append(2)
    portable = envelope.to_dict()
    portable["event"]["lineage"]["nested"]["values"].append(3)

    assert envelope.event.lineage["nested"]["values"] == [1]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"scope_ref": "tenant-a"}, "scope_ref"),
        ({"version": "pheroos-scoped-trace-event-v999"}, "version"),
        ({"event_root": "sha256:" + "0" * 64}, "root"),
        (
            {"scope_ref": runtime_scope_ref("tenant-b", "run-1")},
            "envelope root",
        ),
    ],
)
def test_scoped_trace_rejects_unknown_version_scope_leak_and_root_tamper(
    change: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(scoped_event(), **change)


def test_scoped_trace_rejects_trace_identity_mismatch() -> None:
    event = TraceEvent(
        event_type="plan",
        protocol_id="protocol:one",
        target="decision:one",
        reason="identity",
        lineage={"trace_event_id": "trace:canonical"},
    )

    with pytest.raises(ValueError, match="trace id"):
        ScopedTraceEvent(
            scope_ref=runtime_scope_ref("tenant-a", "run-1"),
            stream="commit",
            transition_id="transition:1",
            trace_id="trace:forged",
            event=event,
        )


def test_scoped_trace_schema_is_closed_and_versioned() -> None:
    schema = scoped_trace_event_schema()

    assert schema["$id"] == SCOPED_TRACE_EVENT_SCHEMA_ID
    assert schema["additionalProperties"] is False
    assert schema["properties"]["version"]["const"] == SCOPED_TRACE_EVENT_VERSION
