from __future__ import annotations

from math import isclose
from numbers import Real
from typing import Any, cast

from pheroos.trace._lineage_primitives import (
    finite_number,
    require_nonnegative_integer,
    require_nonnegative_number,
    require_positive_integer,
    require_subject,
    require_text_fields,
)
from pheroos.trace._lineage_types import TraceEventView
from pheroos.trace._pheromone_clip_payload import (
    require_exact_payload_fields as _require_exact_payload_fields,
    require_payload_object as _require_payload_object,
    require_payload_text_fields as _require_payload_text_fields,
    trail_payload_effective as _trail_payload_effective,
    validate_trail_payload as _validate_trail_payload,
)
from pheroos.trace._pheromone_receipts import (
    pheromone_clip_payload_fingerprint,
)


def validate_pheromone_clip_lineage(event: TraceEventView) -> None:
    event_type = "pheromone_clip"
    lineage = event.lineage
    require_text_fields(
        event_type,
        lineage,
        {
            "lifecycle",
            "result",
            "source_id",
            "provenance",
            "candidate_id",
            "subject_type",
            "subject_id",
            "kind",
            "source_trace_event_id",
            "trace_event_id",
        },
    )
    _validate_clip_outcome(lineage)
    requested = require_nonnegative_number(event_type, lineage, "requested_strength")
    applied = require_nonnegative_number(event_type, lineage, "applied_strength")
    for field_name in ("round_budget_remaining", "source_budget_remaining"):
        require_nonnegative_number(event_type, lineage, field_name)
    _validate_applied_strength(lineage, requested, applied)
    causal_payload = _validate_causal_binding(lineage)
    source_strength, new_strength = _validate_common_transition(lineage)
    _validate_clip_lifecycle(
        event,
        causal_payload,
        requested=requested,
        applied=applied,
        source_strength=source_strength,
        new_strength=new_strength,
    )


def _validate_clip_outcome(lineage: dict[str, Any]) -> None:
    if lineage["lifecycle"] not in {"deposit", "diffusion", "feedback"}:
        raise ValueError("pheromone_clip trace lifecycle is unsupported")
    if lineage["result"] not in {"applied", "rejected"}:
        raise ValueError("pheromone_clip trace result is unsupported")


def _validate_applied_strength(
    lineage: dict[str, Any],
    requested: float,
    applied: float,
) -> None:
    if applied > requested:
        raise ValueError(
            "pheromone_clip trace applied strength must not exceed requested strength"
        )
    if lineage["result"] == "rejected" and applied != 0:
        raise ValueError("rejected pheromone_clip trace must apply zero strength")
    if lineage["result"] == "applied" and applied <= 0:
        raise ValueError("applied pheromone_clip trace must apply positive strength")


def _validate_causal_binding(lineage: dict[str, Any]) -> dict[str, Any] | None:
    causal_payload = lineage.get("causal_payload")
    causal_fingerprint = lineage.get("causal_fingerprint")
    if lineage["result"] == "rejected" and (
        causal_payload is None or causal_fingerprint is None
    ):
        raise ValueError(
            "rejected pheromone_clip trace requires causal_payload and causal_fingerprint"
        )
    if (causal_payload is None) != (causal_fingerprint is None):
        raise ValueError(
            "pheromone_clip causal payload and fingerprint must be declared together"
        )
    if causal_payload is None:
        return None
    if not isinstance(causal_payload, dict):
        raise ValueError("pheromone_clip causal_payload must be an object")
    if not isinstance(causal_fingerprint, str) or not causal_fingerprint:
        raise ValueError("pheromone_clip causal_fingerprint must be a non-empty string")
    expected_fingerprint = pheromone_clip_payload_fingerprint(causal_payload)
    if causal_fingerprint != expected_fingerprint:
        raise ValueError("pheromone_clip causal payload fingerprint does not match")
    if causal_payload.get("lifecycle") != lineage["lifecycle"]:
        raise ValueError("pheromone_clip causal payload lifecycle does not match")
    return causal_payload


def _validate_common_transition(
    lineage: dict[str, Any],
) -> tuple[float, float]:
    event_type = "pheromone_clip"
    lifecycle = lineage["lifecycle"]
    common_transition = {"source_kind", "source_strength", "new_strength", "step"}
    missing = sorted(common_transition - set(lineage))
    if missing:
        raise ValueError(
            f"pheromone_clip {lifecycle} lineage missing required fields: {', '.join(missing)}"
        )
    require_text_fields(event_type, lineage, {"source_kind"})
    source_strength = require_nonnegative_number(event_type, lineage, "source_strength")
    new_strength = require_nonnegative_number(event_type, lineage, "new_strength")
    require_nonnegative_integer(event_type, lineage, "step")
    return source_strength, new_strength


def _validate_clip_lifecycle(
    event: TraceEventView,
    causal_payload: dict[str, Any] | None,
    *,
    requested: float,
    applied: float,
    source_strength: float,
    new_strength: float,
) -> None:
    lifecycle = event.lineage["lifecycle"]
    if lifecycle == "deposit":
        _validate_deposit_clip_transition(
            event,
            causal_payload,
            applied,
            source_strength,
            new_strength,
        )
        return
    if lifecycle == "diffusion":
        _validate_diffusion_clip_transition(
            event,
            cast(dict[str, Any], causal_payload),
            requested,
            applied,
            source_strength,
            new_strength,
        )
        return
    _validate_feedback_clip_transition(
        event,
        cast(dict[str, Any], causal_payload),
        requested,
        applied,
        source_strength,
        new_strength,
    )


def _validate_deposit_clip_transition(
    event: TraceEventView,
    causal_payload: dict[str, Any] | None,
    applied: float,
    source_strength: float,
    new_strength: float,
) -> None:
    lineage = event.lineage
    if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
        raise ValueError("deposit pheromone_clip trace identity is inconsistent")
    if source_strength != 0 or not isclose(new_strength, applied, abs_tol=1e-9):
        raise ValueError("deposit pheromone_clip trace does not reconstruct transition")
    if lineage["source_kind"] != lineage["kind"]:
        raise ValueError("deposit pheromone_clip trace must preserve kind")
    if causal_payload is not None:
        _validate_deposit_clip_payload(event, causal_payload)


def _validate_diffusion_clip_transition(
    event: TraceEventView,
    causal_payload: dict[str, Any],
    requested: float,
    applied: float,
    source_strength: float,
    new_strength: float,
) -> None:
    event_type = "pheromone_clip"
    lineage = event.lineage
    required = {
        "source_subject",
        "target_subject",
        "hop",
        "attenuation",
        "policy_attenuation",
        "edge_attenuation",
        "root_trace_event_id",
    }
    missing = sorted(required - set(lineage))
    if missing:
        raise ValueError(
            "pheromone_clip diffusion lineage missing required fields: "
            f"{', '.join(missing)}"
        )
    require_subject(event_type, lineage, "source_subject")
    require_subject(event_type, lineage, "target_subject")
    require_text_fields(event_type, lineage, {"root_trace_event_id"})
    require_positive_integer(event_type, lineage, "hop")
    attenuation = finite_number(event_type, "attenuation", lineage["attenuation"])
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
    if not all(
        0 <= value <= 1 for value in (attenuation, policy_attenuation, edge_attenuation)
    ):
        raise ValueError(
            "pheromone_clip diffusion attenuation must be between zero and one"
        )
    if not isclose(
        attenuation,
        policy_attenuation * edge_attenuation,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "pheromone_clip diffusion attenuation factors do not reconstruct"
        )
    if not isclose(requested, source_strength * attenuation, abs_tol=1e-9):
        raise ValueError("pheromone_clip diffusion request is not causally derived")
    if applied != 0 or new_strength != 0 or lineage["result"] != "rejected":
        raise ValueError("pheromone_clip diffusion must record a rejected transition")
    _validate_diffusion_clip_payload(event, causal_payload)


def _validate_feedback_clip_transition(
    event: TraceEventView,
    causal_payload: dict[str, Any],
    requested: float,
    applied: float,
    source_strength: float,
    new_strength: float,
) -> None:
    event_type = "pheromone_clip"
    lineage = event.lineage
    required = {"outcome", "reward", "feedback_trace_event_id"}
    missing = sorted(required - set(lineage))
    if missing:
        raise ValueError(
            "pheromone_clip feedback lineage missing required fields: "
            f"{', '.join(missing)}"
        )
    require_text_fields(event_type, lineage, {"outcome", "feedback_trace_event_id"})
    finite_number(event_type, "reward", lineage["reward"])
    if "strength_delta" not in lineage:
        raise ValueError(
            "pheromone_clip feedback lineage missing required field: strength_delta"
        )
    strength_delta = require_nonnegative_number(
        event_type,
        lineage,
        "strength_delta",
    )
    expected_requested = abs(
        strength_delta if strength_delta != 0.0 else float(lineage["reward"])
    )
    if not isclose(requested, expected_requested, abs_tol=1e-9):
        raise ValueError("pheromone_clip feedback request is not causally derived")
    if applied != 0 or not isclose(new_strength, source_strength, abs_tol=1e-9):
        raise ValueError(
            "pheromone_clip feedback must record an unchanged rejected transition"
        )
    _validate_feedback_clip_payload(event, causal_payload)


def _validate_deposit_clip_payload(
    event: TraceEventView,
    payload: dict[str, Any],
) -> None:
    _require_exact_payload_fields(
        payload,
        {"lifecycle", "input", "effective"},
        "deposit causal payload",
    )
    item = _require_payload_object(payload, "input", "deposit causal payload")
    effective = _require_payload_object(payload, "effective", "deposit causal payload")
    _validate_trail_payload(item, "deposit causal payload.input")
    _require_exact_payload_fields(
        effective,
        {"target", "candidate_id", "subject_type", "subject_id", "source_id"},
        "deposit causal payload.effective",
    )
    _require_payload_text_fields(
        effective,
        {"target", "candidate_id", "subject_type", "subject_id", "source_id"},
        "deposit causal payload.effective",
        allow_empty=False,
    )
    raw_effective = _trail_payload_effective(item)
    if effective != raw_effective:
        raise ValueError(
            "deposit causal payload effective binding does not match input trail"
        )
    lineage = event.lineage
    expected = {
        "candidate_id": effective["candidate_id"],
        "subject_type": effective["subject_type"],
        "subject_id": effective["subject_id"],
        "source_id": effective["source_id"],
        "kind": item["kind"],
        "provenance": item["provenance"],
        "trace_event_id": item["trace_event_id"],
        "source_trace_event_id": item["trace_event_id"],
    }
    if event.target != effective["target"] or any(
        lineage.get(field_name) != value for field_name, value in expected.items()
    ):
        raise ValueError(
            "deposit pheromone_clip causal payload does not bind trace lineage"
        )
    if not isclose(
        float(lineage["requested_strength"]),
        float(item["strength"]),
        abs_tol=1e-9,
    ):
        raise ValueError("deposit pheromone_clip request does not match causal input")
    if lineage["step"] != item["updated_at_step"]:
        raise ValueError("deposit pheromone_clip step does not match causal input")


def _validate_feedback_clip_payload(
    event: TraceEventView,
    payload: dict[str, Any],
) -> None:
    _require_exact_payload_fields(
        payload,
        {"lifecycle", "input", "source_state"},
        "feedback causal payload",
    )
    item = _require_payload_object(payload, "input", "feedback causal payload")
    source = _require_payload_object(payload, "source_state", "feedback causal payload")
    _validate_feedback_input(item)
    _validate_feedback_source_state(source, item)
    _validate_feedback_lineage_binding(event, item, source)


def _validate_feedback_input(item: dict[str, Any]) -> None:
    _require_exact_payload_fields(
        item,
        {
            "source_id",
            "subject_type",
            "subject_id",
            "candidate_id",
            "target",
            "outcome",
            "reward",
            "strength_delta",
            "evidence_id",
            "provenance",
            "trace_event_id",
            "step",
        },
        "feedback causal payload.input",
    )
    _require_payload_text_fields(
        item,
        {
            "source_id",
            "subject_type",
            "subject_id",
            "candidate_id",
            "target",
            "outcome",
            "provenance",
            "trace_event_id",
        },
        "feedback causal payload.input",
        allow_empty=False,
    )
    _require_payload_text_fields(
        item,
        {"evidence_id"},
        "feedback causal payload.input",
        allow_empty=True,
    )
    finite_number("pheromone_clip", "causal_payload.input.reward", item["reward"])
    strength_delta = finite_number(
        "pheromone_clip",
        "causal_payload.input.strength_delta",
        item["strength_delta"],
    )
    if strength_delta < 0:
        raise ValueError("feedback causal payload strength_delta must be non-negative")
    require_nonnegative_integer("pheromone_clip", item, "step")


def _validate_feedback_source_state(
    source: dict[str, Any],
    item: dict[str, Any],
) -> None:
    _require_exact_payload_fields(
        source,
        {"trace_event_id", "strength", "kind", "provenance"},
        "feedback causal payload.source_state",
    )
    _require_payload_text_fields(
        source,
        {"trace_event_id", "kind", "provenance"},
        "feedback causal payload.source_state",
        allow_empty=False,
    )
    require_nonnegative_number("pheromone_clip", source, "strength")
    if float(source["strength"]) == 0.0:
        _validate_new_memory_source_state(source, item)


def _validate_new_memory_source_state(
    source: dict[str, Any],
    item: dict[str, Any],
) -> None:
    expected_kind = {
        "success": "positive",
        "failure": "negative",
        "blocked": "cautionary",
        "congested": "cautionary",
        "hazard": "alarm",
        "novel": "novelty",
        "stale": "stale",
    }.get(item["outcome"])
    if (
        source["trace_event_id"] != item["trace_event_id"]
        or source["kind"] != expected_kind
        or source["provenance"] != item["provenance"]
    ):
        raise ValueError(
            "feedback causal payload new-memory source state does not match input"
        )


def _validate_feedback_lineage_binding(
    event: TraceEventView,
    item: dict[str, Any],
    source: dict[str, Any],
) -> None:
    lineage = event.lineage
    expected = {
        "source_id": item["source_id"],
        "candidate_id": item["candidate_id"],
        "subject_type": item["subject_type"],
        "subject_id": item["subject_id"],
        "outcome": item["outcome"],
        "reward": item["reward"],
        "strength_delta": item["strength_delta"],
        "feedback_trace_event_id": item["trace_event_id"],
        "trace_event_id": item["trace_event_id"],
        "source_trace_event_id": source["trace_event_id"],
        "source_strength": source["strength"],
        "source_kind": source["kind"],
        "provenance": source["provenance"],
        "step": item["step"],
    }
    if event.target != item["target"]:
        raise ValueError("feedback pheromone_clip target does not match causal input")
    for field_name, value in expected.items():
        _require_lineage_match(
            lineage,
            field_name,
            value,
            prefix="feedback",
        )


def _validate_diffusion_clip_payload(
    event: TraceEventView,
    payload: dict[str, Any],
) -> None:
    _require_exact_payload_fields(
        payload,
        {"lifecycle", "input", "effective"},
        "diffusion causal payload",
    )
    item = _require_payload_object(payload, "input", "diffusion causal payload")
    effective = _require_payload_object(
        payload, "effective", "diffusion causal payload"
    )
    source_trail, target_subject, edge = _validate_diffusion_input(item)
    _validate_diffusion_effective(effective)
    source_effective = _trail_payload_effective(source_trail)
    expected_effective = _expected_diffusion_effective(
        source_trail,
        target_subject,
        source_effective,
    )
    if effective != expected_effective:
        raise ValueError(
            "diffusion causal payload effective binding does not match input"
        )
    _validate_diffusion_topology(
        item, source_trail, target_subject, edge, source_effective
    )
    _validate_diffusion_lineage_binding(
        event,
        item,
        source_trail,
        target_subject,
        edge,
        effective,
    )


def _validate_diffusion_input(
    item: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require_exact_payload_fields(
        item,
        {
            "source_trail",
            "target_subject",
            "edge",
            "policy_attenuation",
            "hop",
            "parent_trace_event_id",
            "derived_trace_event_id",
        },
        "diffusion causal payload.input",
    )
    source_trail = _require_payload_object(
        item,
        "source_trail",
        "diffusion causal payload.input",
    )
    target_subject = _require_payload_object(
        item,
        "target_subject",
        "diffusion causal payload.input",
    )
    edge = _require_payload_object(
        item,
        "edge",
        "diffusion causal payload.input",
    )
    _validate_trail_payload(
        source_trail,
        "diffusion causal payload.input.source_trail",
    )
    _validate_target_subject(target_subject)
    _validate_diffusion_edge(edge)
    for mapping, field_name in (
        (item, "policy_attenuation"),
        (edge, "attenuation"),
    ):
        value = finite_number("pheromone_clip", field_name, mapping[field_name])
        if not 0 <= value <= 1:
            raise ValueError(
                "diffusion causal payload attenuation must be between zero and one"
            )
    require_positive_integer("pheromone_clip", item, "hop")
    _require_payload_text_fields(
        item,
        {"parent_trace_event_id", "derived_trace_event_id"},
        "diffusion causal payload.input",
        allow_empty=False,
    )
    return source_trail, target_subject, edge


def _validate_target_subject(target_subject: dict[str, Any]) -> None:
    _require_exact_payload_fields(
        target_subject,
        {"subject_type", "subject_id", "candidate_id", "target"},
        "diffusion causal payload.input.target_subject",
    )
    _require_payload_text_fields(
        target_subject,
        {"subject_type", "subject_id", "candidate_id", "target"},
        "diffusion causal payload.input.target_subject",
        allow_empty=False,
    )


def _validate_diffusion_edge(edge: dict[str, Any]) -> None:
    _require_exact_payload_fields(
        edge,
        {
            "source_subject_type",
            "source_subject_id",
            "target_subject_type",
            "target_subject_id",
            "attenuation",
        },
        "diffusion causal payload.input.edge",
    )
    _require_payload_text_fields(
        edge,
        {
            "source_subject_type",
            "source_subject_id",
            "target_subject_type",
            "target_subject_id",
        },
        "diffusion causal payload.input.edge",
        allow_empty=False,
    )


def _validate_diffusion_effective(effective: dict[str, Any]) -> None:
    _require_exact_payload_fields(
        effective,
        {
            "target",
            "candidate_id",
            "subject_type",
            "subject_id",
            "source_id",
            "source_kind",
            "source_strength",
            "root_trace_event_id",
        },
        "diffusion causal payload.effective",
    )
    _require_payload_text_fields(
        effective,
        {
            "target",
            "candidate_id",
            "subject_type",
            "subject_id",
            "source_id",
            "source_kind",
            "root_trace_event_id",
        },
        "diffusion causal payload.effective",
        allow_empty=False,
    )
    require_nonnegative_number("pheromone_clip", effective, "source_strength")


def _expected_diffusion_effective(
    source_trail: dict[str, Any],
    target_subject: dict[str, Any],
    source_effective: dict[str, str],
) -> dict[str, Any]:
    return {
        "target": target_subject["target"] or source_effective["target"],
        "candidate_id": (
            target_subject["candidate_id"] or source_effective["candidate_id"]
        ),
        "subject_type": target_subject["subject_type"],
        "subject_id": target_subject["subject_id"],
        "source_id": source_effective["source_id"],
        "source_kind": source_trail["kind"],
        "source_strength": source_trail["strength"],
        "root_trace_event_id": (
            source_trail["diffusion_root_trace_event_id"]
            or source_trail["trace_event_id"]
        ),
    }


def _validate_diffusion_topology(
    item: dict[str, Any],
    source_trail: dict[str, Any],
    target_subject: dict[str, Any],
    edge: dict[str, Any],
    source_effective: dict[str, str],
) -> None:
    if (
        edge["source_subject_type"] != source_effective["subject_type"]
        or edge["source_subject_id"] != source_effective["subject_id"]
        or edge["target_subject_type"] != target_subject["subject_type"]
        or edge["target_subject_id"] != target_subject["subject_id"]
        or item["parent_trace_event_id"] != source_trail["trace_event_id"]
    ):
        raise ValueError("diffusion causal payload topology does not match input trail")


def _validate_diffusion_lineage_binding(
    event: TraceEventView,
    item: dict[str, Any],
    source_trail: dict[str, Any],
    target_subject: dict[str, Any],
    edge: dict[str, Any],
    effective: dict[str, Any],
) -> None:
    expected_subjects = {
        "source_subject": {
            "type": edge["source_subject_type"],
            "id": edge["source_subject_id"],
        },
        "target_subject": {
            "type": target_subject["subject_type"],
            "id": target_subject["subject_id"],
        },
    }
    expected = {
        "candidate_id": effective["candidate_id"],
        "subject_type": effective["subject_type"],
        "subject_id": effective["subject_id"],
        "source_id": effective["source_id"],
        "source_kind": effective["source_kind"],
        "kind": effective["source_kind"],
        "provenance": source_trail["provenance"],
        "source_trace_event_id": item["parent_trace_event_id"],
        "trace_event_id": item["derived_trace_event_id"],
        "root_trace_event_id": effective["root_trace_event_id"],
        "hop": item["hop"],
        "policy_attenuation": item["policy_attenuation"],
        "edge_attenuation": edge["attenuation"],
        "source_strength": effective["source_strength"],
        "step": source_trail["updated_at_step"],
    }
    if event.target != effective["target"]:
        raise ValueError(
            "diffusion pheromone_clip target does not match causal payload"
        )
    for field_name, value in {**expected_subjects, **expected}.items():
        _require_lineage_match(
            event.lineage,
            field_name,
            value,
            prefix="diffusion",
        )


def _require_lineage_match(
    lineage: dict[str, Any],
    field_name: str,
    value: Any,
    *,
    prefix: str,
) -> None:
    observed = lineage.get(field_name)
    if isinstance(value, Real) and not isinstance(value, bool):
        if not isclose(float(cast(Any, observed)), float(value), abs_tol=1e-9):
            raise ValueError(
                f"{prefix} pheromone_clip causal payload mismatch: {field_name}"
            )
    elif observed != value:
        raise ValueError(
            f"{prefix} pheromone_clip causal payload mismatch: {field_name}"
        )


__all__: tuple[str, ...] = ()
