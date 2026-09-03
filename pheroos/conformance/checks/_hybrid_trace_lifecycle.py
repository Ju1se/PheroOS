from __future__ import annotations

from typing import Any

from pheroos.governance import (
    PolicyAdjustmentProposal,
    apply_policy_adjustment_overlay,
    validate_policy_adjustment_proposals,
)
from pheroos.governance.pheromone import pheromone_policy_from_collective
from pheroos.protocol.models import CapabilityManifest
from pheroos.trace import TraceEvent

from ._hybrid_trace_lifecycle_clips import process_clip
from ._hybrid_trace_lifecycle_state import (
    LIFECYCLE_EVENT_TYPES,
    LifecycleContext,
    create_lifecycle_context,
    lifecycle_state_near as lifecycle_state_near,
)
from ._hybrid_trace_lifecycle_transitions import process_transition


def pheromone_lifecycle_policy_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
) -> list[str]:
    """Causally replay lifecycle transitions into the scored active memory."""

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return ["authority_pheromone_policy_missing"]
    try:
        context = _build_context(manifest, events, policy)
    except Exception as exc:
        return [f"authority_pheromone_lifecycle_policy:{type(exc).__name__}"]
    for index, event in enumerate(events):
        if event.event_type not in LIFECYCLE_EVENT_TYPES:
            continue
        if event.event_type == "pheromone_clip":
            process_clip(context, index, event)
        else:
            process_transition(context, index, event)
    _finalize_active_memory(context, events)
    return context.problems


def _build_context(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    policy: Any,
) -> LifecycleContext:
    accepted = [
        PolicyAdjustmentProposal(
            layer_id=str(event.lineage.get("layer_id", "")),
            source_id=str(event.lineage.get("source_id", "")),
            adjustments=dict(event.lineage.get("proposed_values", {})),
            provenance=str(event.lineage.get("provenance", "")),
            trace_event_id=str(event.lineage.get("source_trace_event_id", "")),
        )
        for event in events
        if event.event_type == "policy_adjustment"
        and event.lineage.get("result") == "accepted"
    ]
    batch = validate_policy_adjustment_proposals(accepted, policy)
    effective_policy = apply_policy_adjustment_overlay(policy, batch.overlay)
    runtime_policy = pheromone_policy_from_collective(effective_policy)
    return create_lifecycle_context(
        manifest,
        events,
        effective_policy,
        runtime_policy,
    )


def _finalize_active_memory(
    context: LifecycleContext,
    events: tuple[TraceEvent, ...],
) -> None:
    if len(context.score_events) != 1:
        return
    score_event = context.score_events[0]
    current_step = int(score_event.lineage.get("current_step", 0))
    context.problems.extend(_lifecycle_step_problems(events, current_step))
    active = {
        str(item.get("trace_event_id", "")): dict(item)
        for item in score_event.lineage.get("active_trails", ())
    }
    context.problems.extend(_active_state_problems(context, active))
    context.problems.extend(_diffusion_ttl_problems(context, active))
    context.problems.extend(_expiration_ttl_problems(context, active))


def _lifecycle_step_problems(
    events: tuple[TraceEvent, ...],
    current_step: int,
) -> list[str]:
    relevant = {
        "pheromone_deposit",
        "pheromone_evaporate",
        "pheromone_expire",
        "pheromone_reinforce",
    }
    problems: list[str] = []
    for index, event in enumerate(events):
        if event.event_type not in relevant:
            continue
        step = int(event.lineage.get("step", 0))
        if step > current_step:
            problems.append(f"authority_pheromone_lifecycle_future_step:{index}")
        if (
            event.event_type in {"pheromone_evaporate", "pheromone_expire"}
            and step != current_step
        ):
            problems.append(f"authority_pheromone_lifecycle_current_step:{index}")
    return problems


def _active_state_problems(
    context: LifecycleContext,
    active: dict[str, dict[str, Any]],
) -> list[str]:
    return [
        f"authority_pheromone_active_transition:{trace_id}"
        for trace_id, expected in context.states.items()
        if trace_id not in active
        or not lifecycle_state_near(active[trace_id], expected)
    ]


def _diffusion_ttl_problems(
    context: LifecycleContext,
    active: dict[str, dict[str, Any]],
) -> list[str]:
    problems: list[str] = []
    for trace_id, source_trace_id in context.diffusion_parents.items():
        observed = active.get(trace_id)
        source = active.get(source_trace_id)
        if (
            observed is not None
            and source is not None
            and observed.get("ttl_steps") != source.get("ttl_steps")
        ):
            problems.append(f"authority_pheromone_diffuse_ttl:{trace_id}")
    return problems


def _expiration_ttl_problems(
    context: LifecycleContext,
    active: dict[str, dict[str, Any]],
) -> list[str]:
    problems: list[str] = []
    for trace_id, (
        source_kind,
        recorded_ttl,
    ) in context.expiration_effective_ttls.items():
        observed = active.get(trace_id)
        if observed is None:
            continue
        expected_ttl = _effective_expiration_ttl(context, source_kind, observed)
        if expected_ttl != recorded_ttl:
            problems.append(f"authority_pheromone_expire_ttl:{trace_id}")
    return problems


def _effective_expiration_ttl(
    context: LifecycleContext,
    source_kind: str,
    observed: dict[str, Any],
) -> Any:
    raw_ttl = observed.get("ttl_steps")
    if raw_ttl is not None:
        return raw_ttl
    profile = context.runtime_policy.kind_profiles.get(source_kind)
    return profile.ttl_steps if profile is not None else None
