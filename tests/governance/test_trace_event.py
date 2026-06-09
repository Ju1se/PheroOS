from pheroos.governance import TraceEvent


def test_trace_event_carries_protocol_lineage() -> None:
    event = TraceEvent(
        event_type="commit",
        protocol_id="toy.review",
        target="decision:review",
        reason="declared candidate",
        lineage={"candidate": "candidate:accept"},
    )

    assert event.lineage["candidate"] == "candidate:accept"
