import pytest

from pheroos.trace import InMemoryTraceStore, TraceEvent


def test_trace_store_appends_records_and_validates_required_events() -> None:
    store = InMemoryTraceStore()
    for event_type in [
        "plan",
        "explore",
        "grant",
        "expose",
        "invoke",
        "evidence",
        "scout_report",
        "signal",
        "recruit",
        "inhibit",
        "pheromone_deposit",
        "pheromone_evaporate",
        "candidate_score",
        "consensus_check",
        "block",
        "commit",
        "fallback",
        "recovery",
        "output",
    ]:
        store.append(
            TraceEvent(
                event_type=event_type,
                protocol_id="e2e.review",
                target="decision:e2e",
                reason="test",
            )
        )

    assert [record.sequence for record in store.records] == list(range(19))
    assert store.require_events(["plan", "invoke", "output"]) == []


def test_trace_store_rejects_unknown_event_type() -> None:
    store = InMemoryTraceStore()

    with pytest.raises(ValueError):
        store.append(
            TraceEvent(
                event_type="unknown",
                protocol_id="e2e.review",
                target="decision:e2e",
                reason="test",
            )
        )
