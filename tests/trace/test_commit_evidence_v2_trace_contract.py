from __future__ import annotations

from copy import deepcopy
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from pheroos.conformance.checks._commit_evidence_v2_context_support import (
    advance_v2,
    attestations_v2,
    commit_replay_v2,
    context_v2_for_evidence,
    request_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.trace import InMemoryTraceStore, TraceEvent
from pheroos.trace.schema import trace_schema


@pytest.fixture(scope="module")
def evidence_event() -> TraceEvent:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    context = context_v2_for_evidence(adapter, "trace-schema")
    attestations = attestations_v2("trace-schema")
    _, replay_state = commit_replay_v2(
        context,
        attestations,
        advance_ref="advance:trace-schema:replay",
    )
    request, source = request_v2(
        context,
        replay_state,
        attestations,
        advance_ref="advance:trace-schema:evidence",
    )
    attempt = advance_v2(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    event = attempt.committed_transition.batch.trace_batch.events[0]
    assert event.event_type == "commit_evidence_qualified_v2"
    return event


def _payload(event: TraceEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


def _mutated(event: TraceEvent, mutation: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    if mutation == "profile_assurance":
        lineage["profile"] = "pheroos-certified-commit-v1"
    elif mutation == "history_count":
        lineage["history_count"] = cast(int, lineage["history_count"]) + 7
    elif mutation == "transition_id":
        lineage["transition_id"] = "transition:commit-evidence-v2:invalid"
    elif mutation == "boolean_revision":
        lineage["revision"] = True
    elif mutation == "unknown":
        lineage["portable_authority"] = True
    else:  # pragma: no cover - closed test mutation declaration
        raise AssertionError(mutation)
    return TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )


def test_real_evidence_event_matches_runtime_and_closed_schema(
    evidence_event: TraceEvent,
) -> None:
    assert InMemoryTraceStore().append(evidence_event).sequence == 0
    Draft202012Validator(trace_schema()).validate(_payload(evidence_event))


@pytest.mark.parametrize(
    "mutation",
    (
        "profile_assurance",
        "history_count",
        "transition_id",
        "boolean_revision",
        "unknown",
    ),
)
def test_evidence_runtime_and_schema_reject_closed_lineage_mutations(
    evidence_event: TraceEvent,
    mutation: str,
) -> None:
    mutated = _mutated(evidence_event, mutation)
    with pytest.raises((TypeError, ValueError)):
        InMemoryTraceStore().append(mutated)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(_payload(mutated))
