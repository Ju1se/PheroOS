from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pheroos.trace._lineage_primitives import (
    finite_number,
    require_boolean,
    require_count_mapping,
    require_nonempty_text_sequence,
    require_nonnegative_number,
    require_positive_integer,
    require_score_mapping,
    require_text_fields,
)
from pheroos.trace._lineage_types import TraceEventView


LineageRule = Callable[[TraceEventView, frozenset[str]], None]


def apply_swarm_lineage_rule(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> bool:
    """Apply the one declared swarm rule in immutable ABI order."""

    for event_types, rule in _SWARM_LINEAGE_RULES:
        if event.event_type in event_types:
            rule(event, required_fields)
            return True
    return False


def _validate_explore(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    require_positive_integer(event.event_type, event.lineage, "scout_count")


def _validate_scout_report(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    require_text_fields(
        event.event_type,
        event.lineage,
        {
            "scout_id",
            "candidate_id",
            "evidence_id",
            "provenance",
            "source_trace_event_id",
            "verification_trace_event_id",
        },
    )
    require_nonnegative_number(event.event_type, event.lineage, "support")


def _validate_recruitment_signal(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    require_text_fields(
        event.event_type,
        event.lineage,
        {
            "source_id",
            "candidate_id",
            "provenance",
            "source_trace_event_id",
            "verification_trace_event_id",
        },
    )
    require_nonnegative_number(event.event_type, event.lineage, "strength")


def _validate_candidate_score(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    event_type = "candidate_score"
    require_score_mapping(event_type, lineage, "scores")
    breakdown = lineage["score_breakdown"]
    if not isinstance(breakdown, dict) or not breakdown:
        raise ValueError(
            "candidate_score trace lineage score_breakdown must be a non-empty object"
        )
    if set(breakdown) != set(lineage["scores"]):
        raise ValueError(
            "candidate_score trace scores and breakdown must cover the same candidates"
        )
    for candidate_id, categories in breakdown.items():
        _validate_candidate_breakdown(lineage, candidate_id, categories)
    require_count_mapping(event_type, lineage, "scout_diversity")
    require_count_mapping(event_type, lineage, "pheromone_source_diversity")


def _validate_candidate_breakdown(
    lineage: dict[str, Any],
    candidate_id: Any,
    categories: Any,
) -> None:
    event_type = "candidate_score"
    if (
        not isinstance(candidate_id, str)
        or not candidate_id
        or not isinstance(categories, dict)
        or not categories
    ):
        raise ValueError(
            "candidate_score trace breakdown must map candidate ids to category objects"
        )
    values = [
        finite_number(
            event_type,
            f"score_breakdown.{candidate_id}.{name}",
            value,
        )
        for name, value in categories.items()
    ]
    if sum(values) != lineage["scores"][candidate_id]:
        raise ValueError(
            "candidate_score trace breakdown does not reconstruct score for "
            f"{candidate_id}"
        )


def _validate_consensus_check(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    threshold = finite_number(
        event.event_type,
        "quorum_threshold",
        lineage["quorum_threshold"],
    )
    if threshold <= 0:
        raise ValueError(
            "consensus_check trace lineage quorum_threshold must be positive"
        )
    require_positive_integer(
        event.event_type,
        lineage,
        "min_independent_scouts",
    )


def _validate_commit_or_fallback(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    del required_fields
    lineage = event.lineage
    require_text_fields(
        event.event_type,
        lineage,
        {"target", "candidate_id", "decision_reason"},
    )
    if lineage["target"] != event.target:
        raise ValueError(
            f"{event.event_type} trace lineage target must match the event target"
        )
    require_nonempty_text_sequence(
        event.event_type,
        lineage,
        "upstream_score_lineage",
    )


def _validate_output(
    event: TraceEventView,
    required_fields: frozenset[str],
) -> None:
    lineage = event.lineage
    for field_name in required_fields:
        require_boolean(event.event_type, lineage, field_name)
    expected = all(
        lineage[field_name]
        for field_name in (
            "committed_candidate",
            "evidence_provenance",
            "stop_resolution",
            "publication_permission",
        )
    )
    if lineage["authorized"] is not expected:
        raise ValueError(
            "output trace authorization must equal the four declared output gates"
        )


_SWARM_LINEAGE_RULES: tuple[tuple[frozenset[str], LineageRule], ...] = (
    (frozenset({"explore"}), _validate_explore),
    (frozenset({"scout_report"}), _validate_scout_report),
    (frozenset({"recruit", "inhibit"}), _validate_recruitment_signal),
    (frozenset({"candidate_score"}), _validate_candidate_score),
    (frozenset({"consensus_check"}), _validate_consensus_check),
    (frozenset({"commit", "fallback"}), _validate_commit_or_fallback),
    (frozenset({"output"}), _validate_output),
)


__all__: tuple[str, ...] = ()
