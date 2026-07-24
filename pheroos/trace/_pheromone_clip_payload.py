from __future__ import annotations

from typing import Any

from pheroos.trace._lineage_primitives import (
    require_nonnegative_integer,
    require_nonnegative_number,
)


_TRAIL_PAYLOAD_FIELDS = frozenset(
    {
        "candidate_id",
        "strength",
        "subject_type",
        "subject_id",
        "target",
        "route_id",
        "tool_id",
        "kind",
        "source_id",
        "source_role",
        "evidence_id",
        "provenance",
        "trace_event_id",
        "deposited_at_step",
        "updated_at_step",
        "ttl_steps",
        "lineage_event_ids",
        "diffusion_root_trace_event_id",
        "diffusion_parent_trace_event_id",
        "diffusion_hop",
    }
)


def validate_trail_payload(item: dict[str, Any], path: str) -> None:
    require_exact_payload_fields(item, set(_TRAIL_PAYLOAD_FIELDS), path)
    require_payload_text_fields(
        item,
        {
            "candidate_id",
            "subject_type",
            "subject_id",
            "target",
            "route_id",
            "tool_id",
            "kind",
            "source_id",
            "source_role",
            "evidence_id",
            "provenance",
            "trace_event_id",
            "diffusion_root_trace_event_id",
            "diffusion_parent_trace_event_id",
        },
        path,
        allow_empty=True,
    )
    for field_name in ("subject_type", "kind", "provenance", "trace_event_id"):
        if not item[field_name]:
            raise ValueError(f"{path}.{field_name} must be non-empty")
    require_nonnegative_number("pheromone_clip", item, "strength")
    for field_name in ("deposited_at_step", "updated_at_step", "diffusion_hop"):
        require_nonnegative_integer("pheromone_clip", item, field_name)
    ttl_steps = item["ttl_steps"]
    if ttl_steps is not None and (
        isinstance(ttl_steps, bool) or not isinstance(ttl_steps, int) or ttl_steps < 0
    ):
        raise ValueError(f"{path}.ttl_steps must be null or a non-negative integer")
    lineage_ids = item["lineage_event_ids"]
    if not isinstance(lineage_ids, list) or any(
        not isinstance(trace_id, str) or not trace_id for trace_id in lineage_ids
    ):
        raise ValueError(
            f"{path}.lineage_event_ids must be an array of non-empty strings"
        )
    if item["trace_event_id"] not in lineage_ids:
        raise ValueError(f"{path}.lineage_event_ids must contain trace_event_id")


def trail_payload_effective(item: dict[str, Any]) -> dict[str, str]:
    if item["subject_id"]:
        subject_type = item["subject_type"]
        subject_id = item["subject_id"]
    elif item["candidate_id"]:
        subject_type = "candidate"
        subject_id = item["candidate_id"]
    elif item["route_id"]:
        subject_type = "route"
        subject_id = item["route_id"]
    elif item["tool_id"]:
        subject_type = "tool"
        subject_id = item["tool_id"]
    else:
        subject_type = item["subject_type"]
        subject_id = ""
    candidate_id = item["candidate_id"]
    if not candidate_id and subject_type == "candidate":
        candidate_id = subject_id
    return {
        "target": item["target"],
        "candidate_id": candidate_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "source_id": item["source_id"] or item["provenance"],
    }


def require_payload_object(
    payload: dict[str, Any],
    field_name: str,
    path: str,
) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{path}.{field_name} must be an object")
    return value


def require_exact_payload_fields(
    payload: dict[str, Any],
    expected: set[str],
    path: str,
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{path} fields do not match the canonical contract")


def require_payload_text_fields(
    payload: dict[str, Any],
    fields: set[str],
    path: str,
    *,
    allow_empty: bool,
) -> None:
    for field_name in fields:
        value = payload.get(field_name)
        if not isinstance(value, str) or (not allow_empty and not value):
            qualifier = "a string" if allow_empty else "a non-empty string"
            raise ValueError(f"{path}.{field_name} must be {qualifier}")


__all__: tuple[str, ...] = ()
