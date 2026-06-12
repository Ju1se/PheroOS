from pheroos.governance import TraceEvent
from pheroos.trace import TraceEvent as CanonicalTraceEvent


def test_trace_event_carries_protocol_lineage() -> None:
    event = TraceEvent(
        event_type="commit",
        protocol_id="toy.review",
        target="decision:review",
        reason="declared candidate",
        lineage={"candidate": "candidate:accept"},
    )

    assert event.lineage["candidate"] == "candidate:accept"


def test_governance_trace_event_is_compatibility_alias() -> None:
    assert TraceEvent is CanonicalTraceEvent
