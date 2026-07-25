from __future__ import annotations

from collections.abc import Callable
from math import isclose
from typing import Any

from pheroos.trace._lineage_primitives import (
    finite_number,
    require_boolean,
    require_nonempty_text_sequence,
    require_nonnegative_integer,
    require_nonnegative_number,
    require_positive_integer,
    require_score_mapping,
    require_subject,
    require_text_fields,
)
from pheroos.trace._lineage_types import TraceEventView
from pheroos.trace._pheromone_clip_rules import validate_pheromone_clip_lineage
from pheroos.trace._pheromone_receipts import (
    require_matching_replay_fingerprints,
    validate_processed_replay_receipts,
)
from pheroos.trace._lineage_primitives import validate_budget_result


LineageRule = Callable[[TraceEventView, frozenset[str]], None]


def apply_pheromone_lineage_rule(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> bool:
    """Apply the one declared pheromone rule in immutable ABI order."""

    for event_types, rule in _PHEROMONE_LINEAGE_RULES:
        if event.event_type in event_types:
            rule(event, required_fields)
            return True
    return False


def _validate_deposit(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_text_fields(
        event_type,
        lineage,
        {
            "source_id",
            "provenance",
            "subject_type",
            "subject_id",
            "candidate_id",
            "kind",
            "source_kind",
            "source_trace_event_id",
            "trace_event_id",
        },
    )
    source_strength = require_nonnegative_number(event_type, lineage, "source_strength")
    old_strength = require_nonnegative_number(event_type, lineage, "old_strength")
    requested_strength = require_nonnegative_number(
        event_type, lineage, "requested_strength"
    )
    applied_strength = require_nonnegative_number(
        event_type, lineage, "applied_strength"
    )
    new_strength = require_nonnegative_number(event_type, lineage, "new_strength")
    _validate_budget_fields(event_type, lineage)
    if not isclose(source_strength, old_strength, abs_tol=1e-9) or not isclose(
        old_strength, 0.0, abs_tol=1e-9
    ):
        raise ValueError("pheromone_deposit trace must start from zero source strength")
    if applied_strength > requested_strength + 1e-9:
        raise ValueError("pheromone_deposit trace applied strength exceeds its request")
    if not isclose(
        new_strength,
        source_strength + applied_strength,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "pheromone_deposit trace applied strength must reconstruct new strength"
        )
    _validate_deposit_identity_and_steps(event_type, lineage)


def _validate_deposit_identity_and_steps(
    event_type: str,
    lineage: dict[str, Any],
) -> None:
    if lineage["source_kind"] != lineage["kind"]:
        raise ValueError("pheromone_deposit trace must preserve pheromone kind")
    if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
        raise ValueError(
            "pheromone_deposit trace result id must match its deposit source id"
        )
    require_nonnegative_integer(event_type, lineage, "step")
    require_nonnegative_integer(event_type, lineage, "deposited_at_step")
    require_nonnegative_integer(event_type, lineage, "updated_at_step")
    if lineage["updated_at_step"] != lineage["step"]:
        raise ValueError(
            "pheromone_deposit trace updated step must equal lifecycle step"
        )
    if lineage["deposited_at_step"] > lineage["updated_at_step"]:
        raise ValueError(
            "pheromone_deposit trace deposit step must not follow update step"
        )


def _validate_evaporate(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_text_fields(
        event_type,
        lineage,
        {
            "subject_type",
            "subject_id",
            "kind",
            "source_kind",
            "source_id",
            "provenance",
            "profile",
            "candidate_id",
            "source_trace_event_id",
            "trace_event_id",
        },
    )
    transition = _read_decay_transition(event_type, lineage)
    (
        source_strength,
        old_strength,
        requested_strength,
        applied_strength,
        new_strength,
    ) = transition
    if new_strength > old_strength:
        raise ValueError(
            "pheromone_evaporate trace new strength must not exceed old strength"
        )
    delta = finite_number(event_type, "strength_delta", lineage["strength_delta"])
    if not (
        isclose(source_strength, old_strength, abs_tol=1e-9)
        and isclose(requested_strength, source_strength, abs_tol=1e-9)
        and isclose(applied_strength, new_strength, abs_tol=1e-9)
        and isclose(delta, new_strength - source_strength, abs_tol=1e-9)
    ):
        raise ValueError(
            "pheromone_evaporate trace strengths do not reconstruct transition"
        )
    _validate_evaporation_identity_and_steps(event_type, lineage)


def _validate_evaporation_identity_and_steps(
    event_type: str,
    lineage: dict[str, Any],
) -> None:
    if lineage["source_kind"] != lineage["kind"]:
        raise ValueError("pheromone_evaporate trace must preserve pheromone kind")
    if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
        raise ValueError(
            "pheromone_evaporate trace must update its source trail in place"
        )
    require_positive_integer(event_type, lineage, "elapsed_steps")
    require_nonnegative_integer(event_type, lineage, "step")
    require_nonnegative_integer(event_type, lineage, "source_updated_at_step")
    require_nonnegative_integer(event_type, lineage, "deposited_at_step")
    if lineage["step"] - lineage["source_updated_at_step"] != lineage["elapsed_steps"]:
        raise ValueError(
            "pheromone_evaporate trace elapsed steps do not reconstruct transition"
        )
    if lineage["deposited_at_step"] > lineage["source_updated_at_step"]:
        raise ValueError("pheromone_evaporate trace source update precedes deposit")


def _read_decay_transition(
    event_type: str,
    lineage: dict[str, Any],
) -> tuple[float, float, float, float, float]:
    return (
        require_nonnegative_number(event_type, lineage, "source_strength"),
        require_nonnegative_number(event_type, lineage, "old_strength"),
        require_nonnegative_number(event_type, lineage, "requested_strength"),
        require_nonnegative_number(event_type, lineage, "applied_strength"),
        require_nonnegative_number(event_type, lineage, "new_strength"),
    )


def _validate_diffuse(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_subject(event_type, lineage, "source_subject")
    require_subject(event_type, lineage, "target_subject")
    require_text_fields(
        event_type,
        lineage,
        {
            "root_trace_event_id",
            "source_id",
            "candidate_id",
            "source_kind",
            "kind",
            "provenance",
            "source_trace_event_id",
            "trace_event_id",
        },
    )
    require_positive_integer(event_type, lineage, "hop")
    attenuation = finite_number(event_type, "attenuation", lineage["attenuation"])
    if not 0 <= attenuation <= 1:
        raise ValueError(
            "pheromone_diffuse trace lineage attenuation must be between 0 and 1"
        )
    policy_attenuation = finite_number(
        event_type,
        "policy_attenuation",
        lineage["policy_attenuation"],
    )
    edge_attenuation = finite_number(
        event_type,
        "edge_attenuation",
        lineage["edge_attenuation"],
    )
    _validate_diffusion_attenuation(
        attenuation,
        policy_attenuation,
        edge_attenuation,
    )
    _validate_diffusion_transition(event_type, lineage, attenuation)


def _validate_diffusion_attenuation(
    attenuation: float,
    policy_attenuation: float,
    edge_attenuation: float,
) -> None:
    if not 0 <= policy_attenuation <= 1 or not 0 <= edge_attenuation <= 1:
        raise ValueError(
            "pheromone_diffuse trace policy and edge attenuation must be between 0 and 1"
        )
    if not isclose(
        attenuation,
        policy_attenuation * edge_attenuation,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "pheromone_diffuse trace attenuation factors do not reconstruct"
        )


def _validate_diffusion_transition(
    event_type: str,
    lineage: dict[str, Any],
    attenuation: float,
) -> None:
    source_strength = require_nonnegative_number(event_type, lineage, "source_strength")
    requested_strength = require_nonnegative_number(
        event_type, lineage, "requested_strength"
    )
    applied_strength = require_nonnegative_number(
        event_type, lineage, "applied_strength"
    )
    new_strength = require_nonnegative_number(event_type, lineage, "new_strength")
    _validate_budget_fields(event_type, lineage)
    if not isclose(requested_strength, source_strength * attenuation, abs_tol=1e-9):
        raise ValueError(
            "pheromone_diffuse trace request must equal attenuated source strength"
        )
    if applied_strength > requested_strength + 1e-9:
        raise ValueError("pheromone_diffuse trace applied strength exceeds its request")
    if not isclose(new_strength, applied_strength, abs_tol=1e-9):
        raise ValueError(
            "pheromone_diffuse trace applied strength must equal new strength"
        )
    if lineage["source_kind"] != lineage["kind"]:
        raise ValueError("pheromone_diffuse trace must preserve pheromone kind")
    if lineage["source_trace_event_id"] == lineage["trace_event_id"]:
        raise ValueError("pheromone_diffuse trace must issue a derived trail id")


def _validate_budget_fields(event_type: str, lineage: dict[str, Any]) -> None:
    for field_name in ("round_budget_remaining", "source_budget_remaining"):
        require_nonnegative_number(event_type, lineage, field_name)


def _validate_reinforce(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_text_fields(
        event_type,
        lineage,
        {
            "feedback_source",
            "source_id",
            "provenance",
            "outcome",
            "candidate_id",
            "subject_type",
            "subject_id",
            "source_kind",
            "kind",
            "source_trace_event_id",
            "feedback_trace_event_id",
            "trace_event_id",
        },
    )
    finite_number(event_type, "reward", lineage["reward"])
    delta = finite_number(event_type, "delta", lineage["delta"])
    source_strength = require_nonnegative_number(event_type, lineage, "source_strength")
    requested_strength = require_nonnegative_number(
        event_type, lineage, "requested_strength"
    )
    applied_strength = require_nonnegative_number(
        event_type, lineage, "applied_strength"
    )
    old_strength = require_nonnegative_number(event_type, lineage, "old_strength")
    new_strength = require_nonnegative_number(event_type, lineage, "new_strength")
    validate_budget_result(event_type, lineage["budget_result"])
    _validate_reinforcement_transition(
        lineage,
        delta=delta,
        source_strength=source_strength,
        requested_strength=requested_strength,
        applied_strength=applied_strength,
        old_strength=old_strength,
        new_strength=new_strength,
    )
    require_nonnegative_integer(event_type, lineage, "step")


def _validate_reinforcement_transition(
    lineage: dict[str, Any],
    *,
    delta: float,
    source_strength: float,
    requested_strength: float,
    applied_strength: float,
    old_strength: float,
    new_strength: float,
) -> None:
    if not isclose(source_strength, old_strength, abs_tol=1e-9) or not isclose(
        new_strength - source_strength,
        delta,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "pheromone_reinforce trace delta must reconstruct new strength"
        )
    if not isclose(applied_strength, abs(delta), abs_tol=1e-9):
        raise ValueError(
            "pheromone_reinforce trace applied strength must equal delta magnitude"
        )
    if applied_strength > requested_strength + 1e-9:
        raise ValueError(
            "pheromone_reinforce trace applied strength exceeds its request"
        )
    if lineage["feedback_source"] != lineage["source_id"]:
        raise ValueError(
            "pheromone_reinforce trace feedback source identity is inconsistent"
        )
    if delta < 0 and (lineage["outcome"] != "stale" or lineage["kind"] != "stale"):
        raise ValueError(
            "negative pheromone reinforcement must be an explicit stale transition"
        )


def _validate_score(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = "pheromone_score"
    require_nonnegative_integer(event_type, lineage, "current_step")
    current_step = lineage["current_step"]
    require_score_mapping(event_type, lineage, "scores")
    candidates = set(lineage["scores"])
    for dimension in ("score_breakdown", "kind_breakdown", "subject_breakdown"):
        _validate_score_dimension(lineage, candidates, dimension)
    trails = lineage["active_trails"]
    if not isinstance(trails, (list, tuple)):
        raise ValueError("pheromone_score trace lineage active_trails must be an array")
    _validate_active_trails(trails, current_step)
    if "processed_replay_receipts" in lineage:
        validate_processed_replay_receipts(
            event_type,
            lineage["processed_replay_receipts"],
        )


def _validate_score_dimension(
    lineage: dict[str, Any],
    candidates: set[str],
    dimension: str,
) -> None:
    event_type = "pheromone_score"
    breakdown = lineage[dimension]
    if not isinstance(breakdown, dict) or set(breakdown) != candidates:
        raise ValueError(
            f"{event_type} trace lineage {dimension} must cover exactly the scored candidates"
        )
    for candidate_id, categories in breakdown.items():
        if not isinstance(categories, dict):
            raise ValueError(
                f"{event_type} trace lineage {dimension}.{candidate_id} must be an object"
            )
        values = [
            finite_number(
                event_type,
                f"{dimension}.{candidate_id}.{name}",
                value,
            )
            for name, value in categories.items()
        ]
        if not isclose(
            sum(values),
            lineage["scores"][candidate_id],
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"{event_type} trace lineage {dimension} does not reconstruct score for {candidate_id}"
            )


def _validate_active_trails(
    trails: list[Any] | tuple[Any, ...], current_step: int
) -> None:
    trace_ids: set[str] = set()
    for index, trail in enumerate(trails):
        _validate_active_trail(trail, index, current_step, trace_ids)


def _validate_active_trail(
    trail: Any,
    index: int,
    current_step: int,
    trace_ids: set[str],
) -> None:
    event_type = "pheromone_score"
    required = {
        "trace_event_id",
        "source_id",
        "candidate_id",
        "subject_type",
        "subject_id",
        "kind",
        "source_kind",
        "strength",
        "provenance",
        "deposited_at_step",
        "updated_at_step",
        "ttl_steps",
    }
    if not isinstance(trail, dict) or not required.issubset(trail):
        raise ValueError(
            f"pheromone_score trace lineage active_trails[{index}] is incomplete"
        )
    require_text_fields(
        event_type,
        trail,
        required - {"strength", "deposited_at_step", "updated_at_step", "ttl_steps"},
    )
    require_nonnegative_number(event_type, trail, "strength")
    require_nonnegative_integer(event_type, trail, "deposited_at_step")
    require_nonnegative_integer(event_type, trail, "updated_at_step")
    deposited_at_step = trail["deposited_at_step"]
    updated_at_step = trail["updated_at_step"]
    _validate_active_trail_steps(
        trail,
        current_step,
        deposited_at_step,
        updated_at_step,
    )
    trace_id = trail["trace_event_id"]
    if trace_id in trace_ids:
        raise ValueError("pheromone_score trace active trail ids must be unique")
    trace_ids.add(trace_id)


def _validate_active_trail_steps(
    trail: dict[str, Any],
    current_step: int,
    deposited_at_step: int,
    updated_at_step: int,
) -> None:
    if deposited_at_step > updated_at_step:
        raise ValueError("pheromone_score trace active trail update precedes deposit")
    if updated_at_step > current_step:
        raise ValueError(
            "pheromone_score trace active trail update exceeds current step"
        )
    ttl_steps = trail["ttl_steps"]
    if ttl_steps is not None:
        _validate_active_trail_ttl(
            trail,
            current_step,
            deposited_at_step,
            ttl_steps,
        )


def _validate_active_trail_ttl(
    trail: dict[str, Any],
    current_step: int,
    deposited_at_step: int,
    ttl_steps: Any,
) -> None:
    if isinstance(ttl_steps, bool) or not isinstance(ttl_steps, int) or ttl_steps < 0:
        raise ValueError(
            "pheromone_score trace active trail ttl_steps must be null or a non-negative integer"
        )
    if current_step - deposited_at_step >= ttl_steps and trail["kind"] != "stale":
        raise ValueError(
            "pheromone_score trace cannot retain an expired non-stale active trail"
        )


def _validate_clip(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    validate_pheromone_clip_lineage(event)


def _validate_expire(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_text_fields(
        event_type,
        lineage,
        {
            "action",
            "target",
            "candidate_id",
            "subject_type",
            "subject_id",
            "kind",
            "source_kind",
            "source_id",
            "provenance",
            "source_trace_event_id",
            "trace_event_id",
        },
    )
    if lineage["action"] != "expire" or lineage["kind"] != "stale":
        raise ValueError(
            "pheromone_expire trace lineage must record an expire transition to stale"
        )
    if lineage["target"] != event.target:
        raise ValueError(
            "pheromone_expire trace lineage target must match the event target"
        )
    transition = _read_decay_transition(event_type, lineage)
    (
        source_strength,
        old_strength,
        requested_strength,
        applied_strength,
        new_strength,
    ) = transition
    delta = finite_number(event_type, "strength_delta", lineage["strength_delta"])
    if new_strength > old_strength:
        raise ValueError(
            "pheromone_expire trace new strength must not exceed old strength"
        )
    if not (
        isclose(source_strength, old_strength, abs_tol=1e-9)
        and isclose(requested_strength, source_strength, abs_tol=1e-9)
        and isclose(applied_strength, new_strength, abs_tol=1e-9)
        and isclose(delta, new_strength - source_strength, abs_tol=1e-9)
    ):
        raise ValueError(
            "pheromone_expire trace strengths do not reconstruct transition"
        )
    _validate_expire_identity_and_steps(event_type, lineage)


def _validate_expire_identity_and_steps(
    event_type: str,
    lineage: dict[str, Any],
) -> None:
    if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
        raise ValueError("pheromone_expire trace must update its source trail in place")
    for field_name in (
        "step",
        "source_updated_at_step",
        "deposited_at_step",
        "ttl_steps",
        "elapsed_steps",
    ):
        require_nonnegative_integer(event_type, lineage, field_name)
    if lineage["step"] - lineage["source_updated_at_step"] != lineage["elapsed_steps"]:
        raise ValueError(
            "pheromone_expire trace elapsed steps do not reconstruct transition"
        )
    if lineage["step"] - lineage["deposited_at_step"] < lineage["ttl_steps"]:
        raise ValueError("pheromone_expire trace transition precedes its declared TTL")


def _validate_observe(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    if {"lifecycle", "result"} & set(lineage):
        _validate_replay_observation(event)
        return
    if {
        "candidate_id",
        "subject_type",
        "subject_id",
        "novelty_pressure",
        "reopen_eligible",
    } & set(lineage):
        _validate_candidate_observation(event)
        return
    if {"exploration_floor", "candidate_ids"} & set(lineage):
        _validate_exploration_floor_observation(event)
        return
    raise ValueError(
        "pheromone_observe trace lineage does not match a supported observation variant"
    )


def _validate_replay_observation(event: TraceEventView) -> None:
    lineage = event.lineage
    event_type = event.event_type
    required = {
        "lifecycle",
        "source_trace_event_id",
        "result",
        "replay_payload",
        "replay_payload_fingerprint",
        "processed_payload_fingerprint",
    }
    missing = sorted(required - set(lineage))
    if missing:
        raise ValueError(
            "pheromone_observe replay lineage missing required fields: "
            f"{', '.join(missing)}"
        )
    require_text_fields(
        event_type,
        lineage,
        {"lifecycle", "source_trace_event_id", "result"},
    )
    if lineage["result"] != "replay_ignored":
        raise ValueError(
            "pheromone_observe replay lineage result must be replay_ignored"
        )
    if lineage["lifecycle"] not in {"deposit", "diffusion", "feedback"}:
        raise ValueError(
            "pheromone_observe replay lineage has an unsupported lifecycle"
        )
    if set(lineage) != required:
        raise ValueError(
            "pheromone_observe replay lineage must contain exactly the replay receipt fields"
        )
    require_matching_replay_fingerprints(event_type, lineage)


def _validate_candidate_observation(event: TraceEventView) -> None:
    lineage = event.lineage
    event_type = event.event_type
    required = {
        "candidate_id",
        "subject_type",
        "subject_id",
        "novelty_pressure",
        "reopen_eligible",
        "source_trace_event_id",
    }
    missing = sorted(required - set(lineage))
    if missing:
        raise ValueError(
            "pheromone_observe trace lineage missing required fields: "
            f"{', '.join(missing)}"
        )
    require_text_fields(
        event_type,
        lineage,
        {"candidate_id", "subject_type", "subject_id", "source_trace_event_id"},
    )
    require_nonnegative_number(event_type, lineage, "novelty_pressure")
    require_boolean(event_type, lineage, "reopen_eligible")
    if set(lineage) != required:
        raise ValueError(
            "pheromone_observe exploration lineage must contain exactly the state fields"
        )


def _validate_exploration_floor_observation(event: TraceEventView) -> None:
    lineage = event.lineage
    event_type = event.event_type
    required = {"exploration_floor", "candidate_ids"}
    missing = sorted(required - set(lineage))
    if missing:
        raise ValueError(
            "pheromone_observe exploration lineage missing required fields: "
            f"{', '.join(missing)}"
        )
    require_nonnegative_number(event_type, lineage, "exploration_floor")
    require_nonempty_text_sequence(event_type, lineage, "candidate_ids")
    if set(lineage) != required:
        raise ValueError(
            "pheromone_observe exploration floor lineage must contain exactly the floor fields"
        )


def _validate_normalize(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = event.event_type
    require_nonempty_text_sequence(event_type, lineage, "candidates")
    require_score_mapping(event_type, lineage, "pre_scores")
    require_score_mapping(event_type, lineage, "post_scores")
    require_text_fields(
        event_type,
        lineage,
        {"response_model", "competition_mode"},
    )
    candidates = set(lineage["candidates"])
    if (
        set(lineage["pre_scores"]) != candidates
        or set(lineage["post_scores"]) != candidates
    ):
        raise ValueError(
            "pheromone_normalize trace scores must cover exactly the declared candidates"
        )
    response_model = lineage["response_model"]
    per_kind_competitive = bool(
        response_model.startswith("competitive:")
        and all(
            kind and kind.strip() == kind
            for kind in response_model.removeprefix("competitive:").split(",")
        )
    )
    if (
        response_model
        not in {
            "linear",
            "saturating",
            "threshold",
            "competitive",
        }
        and not per_kind_competitive
    ):
        raise ValueError("pheromone_normalize trace response_model is unsupported")
    if lineage["competition_mode"] not in {"none", "normalize"}:
        raise ValueError("pheromone_normalize trace competition_mode is unsupported")


_PHEROMONE_LINEAGE_RULES: tuple[tuple[frozenset[str], LineageRule], ...] = (
    (frozenset({"pheromone_deposit"}), _validate_deposit),
    (frozenset({"pheromone_evaporate"}), _validate_evaporate),
    (frozenset({"pheromone_diffuse"}), _validate_diffuse),
    (frozenset({"pheromone_reinforce"}), _validate_reinforce),
    (frozenset({"pheromone_score"}), _validate_score),
    (frozenset({"pheromone_clip"}), _validate_clip),
    (frozenset({"pheromone_expire"}), _validate_expire),
    (frozenset({"pheromone_observe"}), _validate_observe),
    (frozenset({"pheromone_normalize"}), _validate_normalize),
)


__all__: tuple[str, ...] = ()
