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
        "pheromone_score",
        "pheromone_clip",
        "pheromone_expire",
        "pheromone_inhibit",
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

    assert [record.sequence for record in store.records] == list(range(23))
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


def test_trace_event_lineage_carries_pheromone_metadata() -> None:
    store = InMemoryTraceStore()
    deposit = store.append(
        TraceEvent(
            event_type="pheromone_deposit",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="traceable pheromone mark",
            lineage={
                "candidate_id": "candidate:alpha",
                "kind": "cautionary",
                "evidence_id": "evidence:a",
                "trace_event_id": "trace:pheromone",
            },
        )
    )
    score = store.append(
        TraceEvent(
            event_type="pheromone_score",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="candidate pheromone score contribution",
            lineage={
                "subject_type": "candidate",
                "subject_id": "candidate:alpha",
                "kind": "positive",
                "old_strength": 4,
                "new_strength": 3,
                "source_id": "agent:a",
                "evidence_id": "evidence:a",
                "step": 1,
            },
        )
    )
    expire = store.append(
        TraceEvent(
            event_type="pheromone_expire",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="expired pheromone represented as stale",
            lineage={
                "subject_type": "route",
                "subject_id": "route:alpha",
                "kind": "stale",
                "old_strength": 1,
                "new_strength": 0,
                "source_id": "agent:a",
                "evidence_id": "evidence:a",
                "step": 2,
            },
        )
    )

    assert deposit.event.lineage["kind"] == "cautionary"
    assert score.event.lineage["subject_type"] == "candidate"
    assert score.event.lineage["old_strength"] == 4
    assert score.event.lineage["new_strength"] == 3
    assert expire.event.lineage["kind"] == "stale"
    assert store.require_events(["pheromone_deposit", "pheromone_score", "pheromone_expire"]) == []


def test_trace_lineage_can_carry_uniform_pheromone_subjects() -> None:
    store = InMemoryTraceStore()
    record = store.append(
        TraceEvent(
            event_type="pheromone_deposit",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="uniform pheromone subjects deposited",
            lineage={
                "subjects": [
                    {"subject_type": "route", "subject_id": "route:research"},
                    {"subject_type": "tool", "subject_id": "tool:parser"},
                    {"subject_type": "evidence", "subject_id": "evidence:a"},
                    {"subject_type": "agent", "subject_id": "agent:a"},
                ]
            },
        )
    )

    assert [item["subject_type"] for item in record.event.lineage["subjects"]] == [
        "route",
        "tool",
        "evidence",
        "agent",
    ]
