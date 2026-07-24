from __future__ import annotations

from typing import Any

from pheroos.governance.pheromone import pheromone_diffusion_trace_event_id
from pheroos.protocol.models import is_supported_pheromone_subject_type
from pheroos.trace import TraceEvent

from ._hybrid_trace_lifecycle_state import (
    OUTCOME_KINDS,
    LifecycleContext,
    expected_budget_application,
    source_state,
)
from ._hybrid_trace_shared import near


def process_clip(context: LifecycleContext, index: int, event: TraceEvent) -> None:
    item = event.lineage
    trace_id = str(item.get("trace_event_id", ""))
    if trace_id in context.observed_clip_ids:
        context.problems.append(f"authority_pheromone_clip_duplicate:{trace_id}")
    context.observed_clip_ids.add(trace_id)
    context.problems.extend(_clip_base_problems(context, index, item))
    source_id = str(item.get("source_id", ""))
    requested = float(item.get("requested_strength", 0.0))
    applied = float(item.get("applied_strength", 0.0))
    lifecycle = str(item.get("lifecycle", ""))
    if lifecycle == "deposit":
        remaining = _deposit_clip(
            context, index, item, trace_id, source_id, requested, applied
        )
    elif lifecycle == "diffusion":
        remaining = _diffusion_clip(
            context, index, event, trace_id, source_id, requested, applied
        )
    else:
        remaining = _feedback_clip(
            context, index, event, trace_id, source_id, requested, applied
        )
    _clip_remaining_budget_problems(context, index, item, remaining)


def _clip_base_problems(
    context: LifecycleContext,
    index: int,
    item: Any,
) -> list[str]:
    applied = float(item.get("applied_strength", 0.0))
    checks = (
        (applied > context.maximum, f"authority_pheromone_clip_strength_bound:{index}"),
        (
            item.get("candidate_id") not in context.declared_candidate_ids,
            f"authority_pheromone_clip_candidate:{index}",
        ),
        (
            not is_supported_pheromone_subject_type(str(item.get("subject_type", ""))),
            f"authority_pheromone_clip_subject_type:{index}",
        ),
        (
            item.get("subject_type") == "candidate"
            and item.get("subject_id") != item.get("candidate_id"),
            f"authority_pheromone_clip_subject_id:{index}",
        ),
        (
            context.score_current_step is not None
            and int(item.get("step", 0)) > context.score_current_step,
            f"authority_pheromone_clip_future_step:{index}",
        ),
    )
    return [message for failed, message in checks if failed]


def _deposit_clip(
    context: LifecycleContext,
    index: int,
    item: Any,
    trace_id: str,
    source_id: str,
    requested: float,
    applied: float,
) -> tuple[float, float, float]:
    remaining = expected_budget_application(
        context,
        source_id=source_id,
        requested=requested,
        enforce_minimum=True,
    )
    if not near(applied, remaining[0]):
        context.problems.append(f"authority_pheromone_clip_deposit_applied:{index}")
    deposit = context.deposit_events_by_trace.get(trace_id)
    if applied > 0.0 and deposit is None:
        context.problems.append(f"authority_pheromone_clip_deposit_missing:{index}")
    elif applied > 0.0:
        assert deposit is not None
        context.problems.extend(
            _deposit_transition_problems(index, item, deposit.lineage)
        )
    elif deposit is not None:
        context.problems.append(
            f"authority_pheromone_clip_rejected_deposit_applied:{index}"
        )
    return remaining


def _deposit_transition_problems(index: int, clip: Any, deposit: Any) -> list[str]:
    fields = (
        "source_id",
        "provenance",
        "candidate_id",
        "subject_type",
        "subject_id",
        "kind",
        "source_kind",
        "source_trace_event_id",
        "trace_event_id",
        "requested_strength",
        "applied_strength",
        "new_strength",
        "step",
    )
    return [
        f"authority_pheromone_clip_deposit_transition:{index}:{field}"
        for field in fields
        if not _transition_field_matches(clip.get(field), deposit.get(field))
    ]


def _transition_field_matches(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        return near(left, right)
    return bool(left == right)


def _diffusion_clip(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
    trace_id: str,
    source_id: str,
    requested: float,
    applied: float,
) -> tuple[float, float, float]:
    item = event.lineage
    source = source_state(context, index, event)
    source_trace_id = str(item.get("source_trace_event_id", ""))
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
            f"authority_pheromone_clip_diffusion_hop:{index}",
        ),
        (
            not near(
                item.get("policy_attenuation"),
                context.effective_policy.pheromone_diffusion_attenuation,
            ),
            f"authority_pheromone_clip_diffusion_policy_attenuation:{index}",
        ),
        (
            _diffusion_parent_invalid(context, source_trace_id, root_trace_id, hop),
            f"authority_pheromone_clip_diffusion_parent_lineage:{index}",
        ),
        (
            target_subject.get("type") != item.get("subject_type")
            or target_subject.get("id") != item.get("subject_id"),
            f"authority_pheromone_clip_diffusion_target_subject:{index}",
        ),
        (
            trace_id != canonical or trace_id in context.states,
            f"authority_pheromone_clip_diffusion_trace_lineage:{index}",
        ),
    )
    context.problems.extend(message for failed, message in checks if failed)
    remaining = expected_budget_application(
        context,
        source_id=source_id,
        requested=requested,
        enforce_minimum=True,
    )
    tail_checks = (
        (
            not near(remaining[0], 0.0) or not near(applied, 0.0),
            f"authority_pheromone_clip_diffusion_rejection:{index}",
        ),
        (
            trace_id in context.diffuse_events_by_trace,
            f"authority_pheromone_clip_diffusion_applied:{index}",
        ),
        (
            item.get("source_kind") != source.get("kind"),
            f"authority_pheromone_clip_diffusion_source_kind:{index}",
        ),
        (
            item.get("kind") != item.get("source_kind"),
            f"authority_pheromone_clip_diffusion_kind:{index}",
        ),
        (
            item.get("provenance") != source.get("provenance"),
            f"authority_pheromone_clip_diffusion_provenance:{index}",
        ),
        (
            context.score_current_step is not None
            and int(item.get("step", 0)) > context.score_current_step,
            f"authority_pheromone_clip_diffusion_future_step:{index}",
        ),
    )
    context.problems.extend(message for failed, message in tail_checks if failed)
    return remaining


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


def _feedback_clip(
    context: LifecycleContext,
    index: int,
    event: TraceEvent,
    trace_id: str,
    source_id: str,
    requested: float,
    applied: float,
) -> tuple[float, float, float]:
    item = event.lineage
    source_trace_id = str(item.get("source_trace_event_id", ""))
    feedback_trace_id = str(item.get("feedback_trace_event_id", ""))
    source_was_known = source_trace_id in context.states
    source = source_state(context, index, event)
    expected_kind = OUTCOME_KINDS.get(str(item.get("outcome", "")))
    checks = (
        (
            expected_kind is None or item.get("kind") != expected_kind,
            f"authority_pheromone_clip_feedback_outcome_kind:{index}",
        ),
        (
            item.get("source_kind") != item.get("kind"),
            f"authority_pheromone_clip_feedback_source_kind:{index}",
        ),
        (
            item.get("candidate_id") not in context.declared_candidate_ids,
            f"authority_pheromone_clip_feedback_candidate:{index}",
        ),
        (
            not is_supported_pheromone_subject_type(str(item.get("subject_type", ""))),
            f"authority_pheromone_clip_feedback_subject_type:{index}",
        ),
        (
            item.get("subject_type") == "candidate"
            and item.get("subject_id") != item.get("candidate_id"),
            f"authority_pheromone_clip_feedback_subject_id:{index}",
        ),
        (
            context.score_current_step is not None
            and int(item.get("step", 0)) > context.score_current_step,
            f"authority_pheromone_clip_feedback_future_step:{index}",
        ),
        (
            trace_id != feedback_trace_id,
            f"authority_pheromone_clip_feedback_lineage:{index}",
        ),
        (
            float(item.get("source_strength", 0.0)) <= 0.0
            and not (source_trace_id == feedback_trace_id == trace_id),
            f"authority_pheromone_clip_feedback_new_trail_lineage:{index}",
        ),
    )
    context.problems.extend(message for failed, message in checks if failed)
    headroom = min(
        requested, max(0.0, context.maximum - float(source.get("strength", 0.0)))
    )
    remaining = expected_budget_application(
        context,
        source_id=source_id,
        requested=headroom,
        enforce_minimum=float(source.get("strength", 0.0)) <= 0.0,
    )
    if not near(remaining[0], 0.0) or not near(applied, 0.0):
        context.problems.append(f"authority_pheromone_clip_feedback_rejection:{index}")
    if not source_was_known:
        context.states.pop(source_trace_id, None)
    return remaining


def _clip_remaining_budget_problems(
    context: LifecycleContext,
    index: int,
    item: Any,
    remaining: tuple[float, float, float],
) -> None:
    if not near(item.get("round_budget_remaining"), remaining[1]):
        context.problems.append(f"authority_pheromone_clip_round_budget:{index}")
    if not near(item.get("source_budget_remaining"), remaining[2]):
        context.problems.append(f"authority_pheromone_clip_source_budget:{index}")
