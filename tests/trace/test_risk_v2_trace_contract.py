from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from pheroos.trace import EVENT_LINEAGE_CONTRACTS, VALID_EVENT_TYPES, TraceEvent
from pheroos.trace.schema import trace_schema
from tests.governance.test_risk_v2_owner import _advance, _context, _request

EVENT_TYPES = ("risk_state_advanced", "risk_assessed_v2")


def _events() -> tuple[TraceEvent, TraceEvent]:
    context = _context(scope_ref="scope:risk-v2:trace")
    request, source = _request(context, advance_ref="advance:trace")
    attempt, _ = _advance(context, request, source)
    assert attempt.committed_transition is not None
    events = attempt.committed_transition.batch.trace_batch.events
    assert len(events) == 2
    return events  # type: ignore[return-value]


def _payload(event: TraceEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


def test_risk_v2_trace_runtime_and_schema_accept_exact_atomic_events() -> None:
    events = _events()
    assert tuple(event.event_type for event in events) == EVENT_TYPES
    for event in events:
        event.validate()
        Draft202012Validator(trace_schema()).validate(_payload(event))
        assert event.event_type in VALID_EVENT_TYPES
        assert EVENT_LINEAGE_CONTRACTS[event.event_type] == frozenset(event.lineage)


@pytest.mark.parametrize("event_index", (0, 1))
def test_risk_v2_trace_runtime_and_schema_reject_unknown_lineage(
    event_index: int,
) -> None:
    event = _events()[event_index]
    payload = _payload(event)
    payload["lineage"]["caller_extension"] = "must-not-enter-authority-lineage"

    with pytest.raises(ValueError, match="unknown fields"):
        TraceEvent(**payload).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value.__setitem__("protocol_id", "protocol:legacy"),
            "protocol_id",
        ),
        (
            lambda value: value["lineage"].__setitem__("stream_ref", "bad"),
            "stream_ref",
        ),
        (
            lambda value: value["lineage"].__setitem__(
                "transition_id", "transition:bad"
            ),
            "transition_id",
        ),
        (
            lambda value: value["lineage"].__setitem__(
                "profile", "pheroos-certified-commit-v1"
            ),
            "profile and assurance",
        ),
        (
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "target_refs", []
            ),
            "target/action bounds",
        ),
    ],
)
def test_risk_state_trace_rejects_context_and_identity_substitution(
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    payload = _payload(_events()[0])
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        TraceEvent(**payload).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("previous_assessment_root", "sha256:" + "0" * 64, "initial assessment"),
        ("window_reset_required", True, "initial assessment"),
        ("source_trace_roots", [], "count"),
        (
            "source_trace_roots",
            ["sha256:" + "f" * 64, "sha256:" + "0" * 64],
            "canonical",
        ),
        ("rationale_codes", ["z", "a"], "canonical"),
        ("expires_at_step", 2, "not fresh"),
    ],
)
def test_risk_assessed_trace_rejects_noncanonical_semantics(
    field: str,
    value: object,
    message: str,
) -> None:
    event = _events()[1]
    lineage = deepcopy(event.lineage)
    lineage[field] = value

    with pytest.raises(ValueError, match=message):
        TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        ).validate()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assessment_ref", "a" * 4097),
        ("issuer_ref", "i" * 4097),
        ("assessment_method", "m" * 4097),
        ("provenance_ref", "p" * 4097),
        ("rationale_codes", ["r" * 4097]),
    ],
)
def test_risk_assessed_trace_runtime_and_schema_reject_oversized_text(
    field: str,
    value: object,
) -> None:
    event = _events()[1]
    payload = _payload(event)
    payload["lineage"][field] = value

    with pytest.raises(ValueError, match="byte bound"):
        TraceEvent(**payload).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


def test_risk_trace_runtime_enforces_utf8_bytes_beyond_schema_approximation() -> None:
    event = _events()[1]
    payload = _payload(event)
    payload["lineage"]["assessment_method"] = "界" * 1366

    with pytest.raises(ValueError, match="byte bound"):
        TraceEvent(**payload).validate()
