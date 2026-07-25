from __future__ import annotations

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from pheroos.trace import TraceEvent
from pheroos.trace.schema import trace_schema
from tests.governance.test_commit_replay_v2_operations import (
    _advance,
    _context,
    _request,
)


def _event() -> TraceEvent:
    context = _context()
    request, source = _request(context, advance="advance:trace", additions=())
    attempt, _ = _advance(context, request, source)
    assert attempt.committed_transition is not None
    return attempt.committed_transition.batch.trace_batch.events[0]


def _payload(event: TraceEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


def test_commit_replay_trace_is_closed_and_schema_valid() -> None:
    event = _event()
    event.validate()
    Draft202012Validator(trace_schema()).validate(_payload(event))
    assert event.event_type == "commit_replay_advanced"
    assert event.lineage["parent_transition_id"] == "genesis"

    lineage = dict(event.lineage)
    lineage["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        ).validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("stream_ref", "authority:commit-replay-v2:" + "0" * 64, "stream_ref"),
        ("transition_id", "transition:commit-replay-v2:" + "0" * 64, "transition_id"),
        ("parent_transition_id", "not-genesis", "genesis parent"),
        ("profile", "pheroos-certified-commit-v1", "profile and assurance"),
        ("read_set_root", "sha256:" + "0" * 64, None),
    ],
)
def test_commit_replay_trace_binding_mutations_fail(
    field: str, value: str, message: str | None
) -> None:
    event = _event()
    lineage = deepcopy(event.lineage)
    lineage[field] = value
    if field == "read_set_root":
        # A root-shaped replacement is structurally valid at the Trace ABI;
        # committed-view rehydration independently binds it to the batch root.
        mutated = TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        )
        mutated.validate()
        Draft202012Validator(trace_schema()).validate(_payload(mutated))
        return
    with pytest.raises(ValueError, match=message):
        TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        ).validate()
