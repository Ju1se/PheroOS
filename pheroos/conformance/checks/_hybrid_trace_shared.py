from __future__ import annotations

from math import isclose
from typing import Any

from pheroos.trace import TraceEvent


_FIXED_EVENT_STAGES = {
    "explore": 0,
    "scout_report": 0,
    "recruit": 0,
    "inhibit": 0,
    "policy_adjustment": 1,
    "layer_proposal": 2,
    "pheromone_deposit": 3,
    "pheromone_diffuse": 5,
    "pheromone_reinforce": 6,
    "pheromone_score": 7,
    "pheromone_normalize": 7,
    "pheromone_observe": 7,
    "coordination_assess": 8,
    "coordination_resolve": 8,
    "candidate_score": 9,
    "consensus_check": 10,
    "commit": 11,
    "fallback": 11,
    "output": 12,
}


def event_stage_order_problems(events: tuple[TraceEvent, ...]) -> list[str]:
    problems: list[str] = []
    previous = -1
    for index, event in enumerate(events):
        stage = event_stage(event)
        if stage is None:
            continue
        if stage < previous:
            problems.append(f"authority_event_order:{index}:{event.event_type}")
        previous = max(previous, stage)
    return problems


def event_stage(event: TraceEvent) -> int | None:
    if event.event_type == "pheromone_clip":
        return _clip_stage(event)
    if event.event_type in {"pheromone_evaporate", "pheromone_expire"}:
        return _decay_stage(event)
    return _FIXED_EVENT_STAGES.get(event.event_type)


def _clip_stage(event: TraceEvent) -> int:
    return {
        "diffusion": 5,
        "feedback": 6,
    }.get(str(event.lineage.get("lifecycle")), 3)


def _decay_stage(event: TraceEvent) -> int:
    return 6 if event.lineage.get("phase") == "post_reinforcement" else 4


def near(left: Any, right: Any) -> bool:
    try:
        return isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9)
    except (TypeError, ValueError):
        return False
