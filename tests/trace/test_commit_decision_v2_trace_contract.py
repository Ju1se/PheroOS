from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from tests.governance.test_commit_decision_v2_operations import (
    PROFILE,
    RUN_REF,
    TARGET,
    _capability,
    _decision_context,
)

from pheroos.governance._commit_decision_v2.operations import (
    advance_commit_decision_v2,
    open_commit_decision_authority_session_v2,
)
from pheroos.governance._commit_decision_v2.source import (
    prepare_commit_decision_initialize_v2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.trace import InMemoryTraceStore, TraceEvent
from pheroos.trace._contracts.commit_decision_authority import (
    COMMIT_DECISION_EVENT_TYPES,
)
from pheroos.trace.schema import trace_schema


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _payload(event: TraceEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


@pytest.fixture(scope="module")
def initialized_event() -> TraceEvent:
    context = _decision_context("scope:decision-v2:trace-contract")
    request, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:trace:initialize",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    attempt = advance_commit_decision_v2(
        request,
        source=source,
        authority_session=open_commit_decision_authority_session_v2(
            _capability(context, request.observed_epoch), request
        ),
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    events = attempt.committed_transition.batch.trace_batch.events
    return next(
        event
        for event in events
        if event.event_type == "commit_decision_initialized_v2"
    )


_EVENT_SHAPES = {
    "commit_decision_initialized_v2": ("initialize", "initialized"),
    "commit_assessment_evaluated_v2": ("evaluate", "assessed"),
    "commit_window_advanced_v2": ("evaluate", "assessed"),
    "commit_window_reset_v2": ("evaluate", "window_reset"),
    "commit_epoch_restarted_v2": ("epoch_restart", "epoch_restarted"),
    "commit_window_sealed_v2": ("seal", "sealed"),
    "commit_decision_progressed_v2": ("evaluate", "heartbeat"),
    "commit_decision_outcome_committed_v2": ("evaluate", "finalized"),
}


def _event_variant(event: TraceEvent, event_type: str) -> TraceEvent:
    lineage = deepcopy(event.lineage)
    command, mutation = _EVENT_SHAPES[event_type]
    lineage["command"] = command
    lineage["mutation_kind"] = mutation
    lineage["assessment_root"] = (
        _root(f"trace:{event_type}:assessment")
        if event_type
        in {
            "commit_assessment_evaluated_v2",
            "commit_window_advanced_v2",
            "commit_window_reset_v2",
        }
        else ""
    )
    lineage["seal_root"] = (
        _root(f"trace:{event_type}:seal")
        if event_type == "commit_window_sealed_v2"
        else ""
    )
    terminal = event_type == "commit_decision_outcome_committed_v2"
    lineage["progress_root"] = "" if terminal else _root(f"trace:{event_type}:progress")
    lineage["outcome_root"] = _root(f"trace:{event_type}:outcome") if terminal else ""
    return TraceEvent(
        event_type=event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )


@pytest.mark.parametrize("event_type", sorted(COMMIT_DECISION_EVENT_TYPES))
def test_all_eight_decision_trace_types_have_closed_valid_shapes(
    initialized_event: TraceEvent,
    event_type: str,
) -> None:
    event = _event_variant(initialized_event, event_type)
    record = InMemoryTraceStore().append(event)
    assert record.event.event_type == event_type


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_field",
        "unknown_field",
        "bool_revision",
        "stream_identity",
        "transition_identity",
        "dependency_root",
        "dependency_set_root",
        "read_set_root",
        "duplicate_dependency",
        "session_target",
        "command_mutation",
        "nul_text",
        "assessment_omitted",
    ),
)
def test_decision_trace_rejects_detached_lineage_substitution(
    initialized_event: TraceEvent,
    mutation: str,
) -> None:
    event = _event_variant(initialized_event, "commit_assessment_evaluated_v2")
    lineage = deepcopy(event.lineage)
    _mutate_decision_lineage(lineage, mutation)
    forged = TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=lineage,
    )
    with pytest.raises((TypeError, ValueError)):
        InMemoryTraceStore().append(forged)


def _mutate_decision_lineage(lineage: dict[str, object], mutation: str) -> None:
    dependencies = cast(list[dict[str, object]], lineage["dependencies"])
    simple_replacements: dict[str, tuple[str, object]] = {
        "unknown_field": ("portable_authority", True),
        "bool_revision": ("revision", True),
        "stream_identity": (
            "stream_ref",
            "authority:commit-decision-v2:" + "0" * 64,
        ),
        "transition_identity": (
            "transition_id",
            "transition:commit-decision-v2:" + "0" * 64,
        ),
        "dependency_set_root": (
            "dependency_set_root",
            _root("trace:forged:dependency-set"),
        ),
        "read_set_root": ("read_set_root", _root("trace:forged:read-set")),
        "command_mutation": ("command", "seal"),
        "nul_text": ("mutation_ref", "mutation:bad\x00ref"),
    }
    if mutation in simple_replacements:
        key, value = simple_replacements[mutation]
        lineage[key] = value
    elif mutation == "missing_field":
        del lineage["source_context_root"]
    elif mutation == "dependency_root":
        dependencies[0]["dependency_root"] = _root("trace:forged:dependency")
    elif mutation == "duplicate_dependency":
        lineage["dependencies"] = [*dependencies, deepcopy(dependencies[0])]
    elif mutation == "session_target":
        binding = cast(dict[str, object], lineage["session_binding"])
        binding["target_refs"] = ["target:forged"]
    else:
        lineage["assessment_root"] = ""


def test_real_initialized_event_is_accepted_by_independent_trace_validation(
    initialized_event: TraceEvent,
) -> None:
    record = InMemoryTraceStore().append(initialized_event)
    assert record.sequence == 0


@pytest.mark.parametrize("event_type", sorted(COMMIT_DECISION_EVENT_TYPES))
def test_all_decision_trace_shapes_are_accepted_by_closed_json_schema(
    initialized_event: TraceEvent,
    event_type: str,
) -> None:
    Draft202012Validator(trace_schema()).validate(
        _payload(_event_variant(initialized_event, event_type))
    )


def test_real_initialized_event_is_accepted_by_closed_json_schema(
    initialized_event: TraceEvent,
) -> None:
    Draft202012Validator(trace_schema()).validate(_payload(initialized_event))


@pytest.mark.parametrize(
    "mutation",
    ("unknown", "bool_revision", "nul_text", "command_event_mismatch"),
)
def test_closed_json_schema_rejects_decision_shape_drift(
    initialized_event: TraceEvent,
    mutation: str,
) -> None:
    payload = _payload(initialized_event)
    lineage = cast(dict[str, object], payload["lineage"])
    if mutation == "unknown":
        lineage["portable_authority"] = True
    elif mutation == "bool_revision":
        lineage["revision"] = True
    elif mutation == "nul_text":
        lineage["mutation_ref"] = "mutation:bad\x00ref"
    else:
        payload["event_type"] = "commit_window_sealed_v2"
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)
