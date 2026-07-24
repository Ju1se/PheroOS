from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pheroos.protocol.models import CapabilityManifest
from pheroos.trace import TraceEvent

from ._hybrid_trace_shared import near


LIFECYCLE_EVENT_TYPES = frozenset(
    {
        "pheromone_deposit",
        "pheromone_evaporate",
        "pheromone_expire",
        "pheromone_diffuse",
        "pheromone_reinforce",
        "pheromone_clip",
    }
)

OUTCOME_KINDS = {
    "success": "positive",
    "failure": "negative",
    "blocked": "cautionary",
    "congested": "cautionary",
    "hazard": "alarm",
    "novel": "novelty",
    "stale": "stale",
}


@dataclass
class LifecycleContext:
    effective_policy: Any
    runtime_policy: Any
    maximum: float
    minimum: float
    round_cap: float
    source_cap: float
    score_events: list[TraceEvent]
    score_current_step: int | None
    declared_candidate_ids: set[str]
    deposit_events_by_trace: dict[str, TraceEvent]
    diffuse_events_by_trace: dict[str, TraceEvent]
    problems: list[str] = field(default_factory=list)
    round_used: float = 0.0
    source_used: dict[str, float] = field(default_factory=dict)
    states: dict[str, dict[str, Any]] = field(default_factory=dict)
    diffusion_lineage: dict[str, tuple[str, int]] = field(default_factory=dict)
    diffusion_parents: dict[str, str] = field(default_factory=dict)
    expiration_effective_ttls: dict[str, tuple[str, int]] = field(default_factory=dict)
    observed_clip_ids: set[str] = field(default_factory=set)


def create_lifecycle_context(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    effective_policy: Any,
    runtime_policy: Any,
) -> LifecycleContext:
    score_events = [event for event in events if event.event_type == "pheromone_score"]
    current_step = (
        int(score_events[0].lineage.get("current_step", 0))
        if len(score_events) == 1
        else None
    )
    target = manifest.protocol.quorum_policy.target
    return LifecycleContext(
        effective_policy=effective_policy,
        runtime_policy=runtime_policy,
        maximum=float(runtime_policy.max_strength),
        minimum=float(runtime_policy.min_strength),
        round_cap=float(runtime_policy.per_round_deposit_cap),
        source_cap=float(runtime_policy.per_source_cap),
        score_events=score_events,
        score_current_step=current_step,
        declared_candidate_ids={
            candidate.id
            for candidate in manifest.protocol.candidates
            if candidate.target == target
        },
        deposit_events_by_trace=_events_by_trace(events, "pheromone_deposit"),
        diffuse_events_by_trace=_events_by_trace(events, "pheromone_diffuse"),
    )


def _events_by_trace(
    events: tuple[TraceEvent, ...],
    event_type: str,
) -> dict[str, TraceEvent]:
    return {
        str(event.lineage.get("trace_event_id", "")): event
        for event in events
        if event.event_type == event_type
    }


def trail_state(
    *,
    trace_event_id: str,
    source_id: str,
    candidate_id: str,
    subject_type: str,
    subject_id: str,
    kind: str,
    strength: float,
    source_kind: str | None = None,
    provenance: str | None = None,
    deposited_at_step: int | None = None,
    updated_at_step: int | None = None,
    ttl_steps: int | None = None,
    ttl_bound: bool = False,
) -> dict[str, Any]:
    return {
        "trace_event_id": trace_event_id,
        "source_id": source_id,
        "candidate_id": candidate_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "kind": kind,
        "strength": strength,
        "source_kind": source_kind,
        "provenance": provenance,
        "deposited_at_step": deposited_at_step,
        "updated_at_step": updated_at_step,
        "ttl_steps": ttl_steps,
        "ttl_bound": ttl_bound,
    }


def source_state(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
) -> dict[str, Any]:
    item = event.lineage
    trace_id = str(item.get("source_trace_event_id", ""))
    subject_type, subject_id = _source_subject(event)
    claimed = trail_state(
        trace_event_id=trace_id,
        source_id=str(item.get("source_id", "")),
        candidate_id=str(item.get("candidate_id", "")),
        subject_type=subject_type,
        subject_id=subject_id,
        kind=str(item.get("source_kind", "")),
        strength=float(item.get("source_strength", 0.0)),
        source_kind=None,
        provenance=(
            str(item.get("provenance", ""))
            if event.event_type != "pheromone_reinforce"
            else None
        ),
        deposited_at_step=_source_deposited_step(event),
        updated_at_step=_source_updated_step(event),
        ttl_steps=int(item["ttl_steps"]) if item.get("ttl_steps") is not None else None,
        ttl_bound="ttl_steps" in item and event.event_type != "pheromone_expire",
    )
    known = context.states.get(trace_id)
    if known is None:
        context.states[trace_id] = claimed
        return claimed
    if not lifecycle_state_near(known, claimed):
        context.problems.append(f"authority_pheromone_source_transition:{index}")
    return known


def _source_subject(event: TraceEvent) -> tuple[str, str]:
    item = event.lineage
    diffusion = event.event_type == "pheromone_diffuse" or (
        event.event_type == "pheromone_clip" and item.get("lifecycle") == "diffusion"
    )
    subject = item.get("source_subject", {}) if diffusion else item
    return str(subject.get("type" if diffusion else "subject_type", "")), str(
        subject.get("id" if diffusion else "subject_id", "")
    )


def _source_deposited_step(event: TraceEvent) -> int | None:
    if event.event_type not in {"pheromone_evaporate", "pheromone_expire"}:
        return None
    return int(event.lineage["deposited_at_step"])


def _source_updated_step(event: TraceEvent) -> int | None:
    if event.event_type not in {"pheromone_evaporate", "pheromone_expire"}:
        return None
    return int(event.lineage["source_updated_at_step"])


def consume_budget(
    context: LifecycleContext,
    *,
    index: int,
    source_id: str,
    requested: float,
    applied: float,
    round_remaining: Any,
    source_remaining: Any,
    enforce_minimum: bool,
) -> None:
    expected, _, _ = expected_budget_application(
        context,
        source_id=source_id,
        requested=requested,
        enforce_minimum=enforce_minimum,
    )
    if not near(applied, expected):
        context.problems.append(f"authority_pheromone_budget_applied:{index}")
        expected = applied
    used_by_source = context.source_used.get(source_id, 0.0)
    context.round_used += expected
    context.source_used[source_id] = used_by_source + expected
    _record_remaining_budget_problems(
        context,
        index,
        source_id,
        round_remaining,
        source_remaining,
    )


def _record_remaining_budget_problems(
    context: LifecycleContext,
    index: int,
    source_id: str,
    round_remaining: Any,
    source_remaining: Any,
) -> None:
    expected_round = max(0.0, context.round_cap - context.round_used)
    expected_source = max(
        0.0,
        context.source_cap - context.source_used[source_id],
    )
    if not near(round_remaining, expected_round):
        context.problems.append(f"authority_pheromone_round_budget_lineage:{index}")
    if not near(source_remaining, expected_source):
        context.problems.append(f"authority_pheromone_source_budget_lineage:{index}")


def expected_budget_application(
    context: LifecycleContext,
    *,
    source_id: str,
    requested: float,
    enforce_minimum: bool,
) -> tuple[float, float, float]:
    available_round = max(0.0, context.round_cap - context.round_used)
    available_source = max(
        0.0,
        context.source_cap - context.source_used.get(source_id, 0.0),
    )
    applied = min(requested, context.maximum, available_round, available_source)
    if enforce_minimum and applied < context.minimum:
        applied = 0.0
    return (
        applied,
        max(0.0, available_round - applied),
        max(0.0, available_source - applied),
    )


def lifecycle_state_near(
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    identity_fields = (
        "trace_event_id",
        "source_id",
        "candidate_id",
        "subject_type",
        "subject_id",
        "kind",
    )
    if any(observed.get(name) != expected.get(name) for name in identity_fields):
        return False
    if not near(observed.get("strength"), expected.get("strength")):
        return False
    return _optional_state_fields_match(observed, expected)


def _optional_state_fields_match(
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    for name in ("deposited_at_step", "updated_at_step"):
        value = expected.get(name)
        if value is not None and observed.get(name) != value:
            return False
    provenance = expected.get("provenance")
    if provenance is not None and observed.get("provenance") != provenance:
        return False
    source_kind = expected.get("source_kind")
    if source_kind is not None and observed.get("source_kind") != source_kind:
        return False
    if expected.get("ttl_bound") and observed.get("ttl_steps") != expected.get(
        "ttl_steps"
    ):
        return False
    return True
