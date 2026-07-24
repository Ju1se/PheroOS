from __future__ import annotations

from typing import Any

from pheroos.governance.pheromone import pheromone_diffusion_trace_event_id
from pheroos.trace import TraceEvent

from ._hybrid_trace_lifecycle_state import (
    OUTCOME_KINDS,
    LifecycleContext,
    consume_budget,
    source_state,
    trail_state,
)
from ._hybrid_trace_shared import near


def process_transition(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
) -> None:
    item = event.lineage
    for field_name in ("source_strength", "new_strength"):
        if float(item.get(field_name, 0.0)) > context.maximum:
            context.problems.append(
                f"authority_{event.event_type}_{field_name}_bound:{index}"
            )
    if event.event_type == "pheromone_deposit":
        _deposit_transition(context, index, event)
        return
    source = source_state(context, index, event)
    source_trace_id = str(item.get("source_trace_event_id", ""))
    result_trace_id = str(item.get("trace_event_id", ""))
    _dispatch_existing_transition(
        context,
        index,
        event,
        source,
        source_trace_id,
        result_trace_id,
    )


def _dispatch_existing_transition(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
    source: dict[str, Any],
    source_trace_id: str,
    result_trace_id: str,
) -> None:
    handlers = {
        "pheromone_evaporate": _evaporation_transition,
        "pheromone_expire": _expiration_transition,
        "pheromone_diffuse": _diffusion_transition,
        "pheromone_reinforce": _reinforcement_transition,
    }
    handlers[event.event_type](
        context,
        index,
        event,
        source,
        source_trace_id,
        result_trace_id,
    )


def _deposit_transition(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
) -> None:
    item = event.lineage
    trace_id = str(item.get("trace_event_id", ""))
    if trace_id in context.states:
        context.problems.append(f"authority_pheromone_duplicate_transition:{trace_id}")
    consume_budget(
        context,
        index=index,
        source_id=str(item.get("source_id", "")),
        requested=float(item.get("requested_strength", 0.0)),
        applied=float(item.get("applied_strength", 0.0)),
        round_remaining=item.get("round_budget_remaining"),
        source_remaining=item.get("source_budget_remaining"),
        enforce_minimum=True,
    )
    context.states[trace_id] = trail_state(
        trace_event_id=trace_id,
        source_id=str(item.get("source_id", "")),
        candidate_id=str(item.get("candidate_id", "")),
        subject_type=str(item.get("subject_type", "")),
        subject_id=str(item.get("subject_id", "")),
        kind=str(item.get("kind", "")),
        strength=float(item.get("new_strength", 0.0)),
        source_kind=str(item.get("source_kind", "")),
        provenance=str(item.get("provenance", "")),
        deposited_at_step=int(item.get("deposited_at_step", 0)),
        updated_at_step=int(item.get("updated_at_step", 0)),
        ttl_steps=int(item["ttl_steps"]) if item.get("ttl_steps") is not None else None,
        ttl_bound=True,
    )


def _evaporation_transition(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
    source: dict[str, Any],
    source_trace_id: str,
    result_trace_id: str,
) -> None:
    item = event.lineage
    expected, profile = _expected_evaporation(context, source, item)
    if not near(item.get("new_strength"), expected):
        context.problems.append(f"authority_pheromone_evaporation_replay:{index}")
    if item.get("profile") != profile:
        context.problems.append(f"authority_pheromone_evaporation_profile:{index}")
    context.states[source_trace_id] = _continued_state(
        source,
        item,
        result_trace_id,
        ttl_steps=source.get("ttl_steps"),
        ttl_bound=bool(source.get("ttl_bound", False)),
    )


def _expected_evaporation(
    context: LifecycleContext,
    source: dict[str, Any],
    item: Any,
) -> tuple[float, str]:
    profile = context.runtime_policy.kind_profiles.get(source["kind"])
    rate = (
        profile.evaporation_rate
        if profile is not None and profile.evaporation_rate is not None
        else context.runtime_policy.evaporation_rate
    )
    retention = max(0.0, min(1.0, 1.0 - float(rate)))
    elapsed = int(item.get("elapsed_steps", 0))
    expected = _decayed_strength(
        context.runtime_policy.decay_model,
        source["strength"],
        retention,
        float(rate),
        elapsed,
    )
    if source["kind"] == "novelty" and context.runtime_policy.exploration_enabled:
        expected *= (1.0 - context.runtime_policy.novelty_decay_rate) ** elapsed
    expected = min(context.maximum, max(context.minimum, expected))
    label = (
        f"kind:{source['kind']}"
        if source["kind"] in context.runtime_policy.kind_profiles
        else f"global:{context.runtime_policy.decay_model}"
    )
    return expected, label


def _decayed_strength(
    model: str,
    strength: float,
    retention: float,
    rate: float,
    elapsed: int,
) -> float:
    if model == "exponential":
        return strength * (retention**elapsed)
    if model == "step":
        return strength * retention
    return strength * max(0.0, 1.0 - rate * elapsed)


def _expiration_transition(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
    source: dict[str, Any],
    source_trace_id: str,
    result_trace_id: str,
) -> None:
    item = event.lineage
    if not near(item.get("new_strength"), context.minimum):
        context.problems.append(f"authority_pheromone_expiry_floor:{index}")
    context.expiration_effective_ttls[result_trace_id] = (
        str(item.get("source_kind", "")),
        int(item.get("ttl_steps", 0)),
    )
    context.states[source_trace_id] = _continued_state(
        source,
        item,
        result_trace_id,
        ttl_steps=source.get("ttl_steps"),
        ttl_bound=bool(source.get("ttl_bound", False)),
    )


def _continued_state(
    source: dict[str, Any],
    item: Any,
    result_trace_id: str,
    *,
    ttl_steps: Any,
    ttl_bound: bool,
) -> dict[str, Any]:
    return trail_state(
        **{
            **source,
            "trace_event_id": result_trace_id,
            "kind": str(item.get("kind", "")),
            "strength": float(item.get("new_strength", 0.0)),
            "source_kind": str(item.get("source_kind", "")),
            "provenance": str(item.get("provenance", "")),
            "deposited_at_step": int(item.get("deposited_at_step", 0)),
            "updated_at_step": int(item.get("step", 0)),
            "ttl_steps": ttl_steps,
            "ttl_bound": ttl_bound,
        }
    )


def _diffusion_transition(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
    source: dict[str, Any],
    source_trace_id: str,
    result_trace_id: str,
) -> None:
    item = event.lineage
    hop = int(item.get("hop", 0))
    root_trace_id = str(item.get("root_trace_event_id", ""))
    target_subject = item.get("target_subject", {})
    canonical = pheromone_diffusion_trace_event_id(
        root_trace_id,
        hop,
        str(target_subject.get("type", "")),
        str(target_subject.get("id", "")),
    )
    checks = (
        (
            hop > int(context.effective_policy.pheromone_diffusion_max_hops),
            f"authority_pheromone_diffuse_hop_bound:{index}",
        ),
        (
            float(item.get("attenuation", 0.0))
            > float(context.effective_policy.pheromone_diffusion_attenuation) + 1e-9,
            f"authority_pheromone_diffuse_attenuation_bound:{index}",
        ),
        (
            not near(
                item.get("policy_attenuation"),
                context.effective_policy.pheromone_diffusion_attenuation,
            ),
            f"authority_pheromone_diffuse_policy_attenuation:{index}",
        ),
        (
            _diffusion_parent_invalid(context, source_trace_id, root_trace_id, hop),
            f"authority_pheromone_diffuse_parent_lineage:{index}",
        ),
        (
            result_trace_id != canonical or result_trace_id in context.states,
            f"authority_pheromone_diffuse_trace_lineage:{index}",
        ),
    )
    context.problems.extend(message for failed, message in checks if failed)
    consume_budget(
        context,
        index=index,
        source_id=str(item.get("source_id", "")),
        requested=float(item.get("requested_strength", 0.0)),
        applied=float(item.get("applied_strength", 0.0)),
        round_remaining=item.get("round_budget_remaining"),
        source_remaining=item.get("source_budget_remaining"),
        enforce_minimum=True,
    )
    context.states[result_trace_id] = trail_state(
        trace_event_id=result_trace_id,
        source_id=str(item.get("source_id", "")),
        candidate_id=str(item.get("candidate_id", "")),
        subject_type=str(target_subject.get("type", "")),
        subject_id=str(target_subject.get("id", "")),
        kind=str(item.get("kind", "")),
        strength=float(item.get("new_strength", 0.0)),
        source_kind=str(item.get("source_kind", "")),
        provenance=str(item.get("provenance", "")),
        deposited_at_step=source.get("deposited_at_step"),
        updated_at_step=source.get("updated_at_step"),
        ttl_steps=source.get("ttl_steps"),
        ttl_bound=bool(source.get("ttl_bound", False)),
    )
    context.diffusion_lineage[result_trace_id] = (root_trace_id, hop)
    context.diffusion_parents[result_trace_id] = source_trace_id


def _diffusion_parent_invalid(
    context: LifecycleContext,
    source_trace_id: str,
    root_trace_id: str,
    hop: int,
) -> bool:
    parent = context.diffusion_lineage.get(source_trace_id)
    if parent is None:
        return hop != 1 or root_trace_id != source_trace_id
    return root_trace_id != parent[0] or hop != parent[1] + 1


def _reinforcement_transition(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
    source: dict[str, Any],
    source_trace_id: str,
    result_trace_id: str,
) -> None:
    item = event.lineage
    feedback_trace_id = str(item.get("feedback_trace_event_id", ""))
    expected_kind = OUTCOME_KINDS.get(str(item.get("outcome", "")))
    checks = (
        (
            expected_kind is None or item.get("kind") != expected_kind,
            f"authority_pheromone_reinforce_outcome_kind:{index}",
        ),
        (
            result_trace_id != feedback_trace_id,
            f"authority_pheromone_reinforce_feedback_lineage:{index}",
        ),
        (
            source["strength"] <= 0.0 and source_trace_id != feedback_trace_id,
            f"authority_pheromone_reinforce_new_trail_lineage:{index}",
        ),
        (
            result_trace_id == source_trace_id and source["strength"] > 0.0,
            f"authority_pheromone_reinforce_self_transition:{index}",
        ),
        (
            result_trace_id != source_trace_id and result_trace_id in context.states,
            f"authority_pheromone_duplicate_transition:{result_trace_id}",
        ),
    )
    context.problems.extend(message for failed, message in checks if failed)
    _reinforcement_budget(context, index, item, source)
    if result_trace_id != source_trace_id:
        context.states.pop(source_trace_id, None)
    context.states[result_trace_id] = _reinforced_state(
        context,
        item,
        source,
        result_trace_id,
    )


def _reinforcement_budget(
    context: LifecycleContext,
    index: int,
    item: Any,
    source: dict[str, Any],
) -> None:
    if float(item.get("delta", 0.0)) >= 0.0:
        headroom = min(
            float(item.get("requested_strength", 0.0)),
            max(0.0, context.maximum - source["strength"]),
        )
        consume_budget(
            context,
            index=index,
            source_id=str(item.get("source_id", "")),
            requested=headroom,
            applied=float(item.get("applied_strength", 0.0)),
            round_remaining=item.get("budget_result", {}).get("round_remaining"),
            source_remaining=item.get("budget_result", {}).get("source_remaining"),
            enforce_minimum=source["strength"] <= 0.0,
        )
        return
    _negative_reinforcement_budget(context, index, item)


def _negative_reinforcement_budget(
    context: LifecycleContext,
    index: int,
    item: Any,
) -> None:
    if not near(item.get("new_strength"), context.minimum):
        context.problems.append(f"authority_pheromone_reinforce_stale_floor:{index}")
    budget = item.get("budget_result", {})
    if not near(
        budget.get("round_remaining"), max(0.0, context.round_cap - context.round_used)
    ):
        context.problems.append(f"authority_pheromone_round_budget_lineage:{index}")
    source_id = str(item.get("source_id", ""))
    remaining = max(0.0, context.source_cap - context.source_used.get(source_id, 0.0))
    if not near(budget.get("source_remaining"), remaining):
        context.problems.append(f"authority_pheromone_source_budget_lineage:{index}")


def _reinforced_state(
    context: LifecycleContext,
    item: Any,
    source: dict[str, Any],
    result_trace_id: str,
) -> dict[str, Any]:
    existing = source["strength"] > 0.0
    kind = str(item.get("kind", ""))
    return trail_state(
        trace_event_id=result_trace_id,
        source_id=str(item.get("source_id", "")),
        candidate_id=str(item.get("candidate_id", "")),
        subject_type=str(item.get("subject_type", "")),
        subject_id=str(item.get("subject_id", "")),
        kind=kind,
        strength=float(item.get("new_strength", 0.0)),
        source_kind=str(item.get("source_kind", "")),
        provenance=str(item.get("provenance", "")),
        deposited_at_step=(
            source.get("deposited_at_step") if existing else int(item.get("step", 0))
        ),
        updated_at_step=int(item.get("step", 0)),
        ttl_steps=(source.get("ttl_steps") if existing else _kind_ttl(context, kind)),
        ttl_bound=True,
    )


def _kind_ttl(context: LifecycleContext, kind: str) -> int | None:
    if kind not in context.runtime_policy.kind_profiles:
        return None
    value = context.runtime_policy.kind_profiles[kind].ttl_steps
    return int(value) if value is not None else None
