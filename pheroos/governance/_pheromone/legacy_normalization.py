"""Fail-closed legacy pheromone trail normalization."""

from __future__ import annotations

from dataclasses import replace

from pheroos.governance._pheromone.records import PheromoneTrail
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.errors import GovernanceError


def normalize_legacy_pheromone_trail_impl(
    trail: PheromoneTrail,
    *,
    target: str,
    source_id: str,
    provenance: str,
    trace_event_id: str,
    source_role: str = "",
    evidence_id: str = "",
) -> PheromoneTrail:
    """Bind a legacy trail without inventing authority or lineage."""

    if not isinstance(trail, PheromoneTrail):
        raise GovernanceError("legacy pheromone trail must be a PheromoneTrail")
    _validate_required_bindings(
        trail,
        {
            "target": target,
            "source_id": source_id,
            "provenance": provenance,
            "trace_event_id": trace_event_id,
        },
    )
    _validate_optional_bindings(
        trail,
        {"source_role": source_role, "evidence_id": evidence_id},
    )
    subject_type, subject_id = _resolve_legacy_subject(trail)
    if subject_type == "candidate" and trail.candidate_id != subject_id:
        raise GovernanceError(
            "legacy candidate pheromone subject must match candidate_id"
        )
    return replace(
        trail,
        subject_type=subject_type,
        subject_id=subject_id,
        target=target,
        source_id=source_id,
        source_role=source_role or trail.source_role,
        evidence_id=evidence_id or trail.evidence_id,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )


def _validate_required_bindings(
    trail: PheromoneTrail,
    supplied: dict[str, str],
) -> None:
    for field_name, value in supplied.items():
        if not is_nonblank_string(value):
            raise GovernanceError(
                f"legacy pheromone normalization requires non-blank {field_name}"
            )
        current = getattr(trail, field_name)
        if current and current != value:
            raise GovernanceError(
                f"legacy pheromone {field_name} conflicts with declared binding"
            )


def _validate_optional_bindings(
    trail: PheromoneTrail,
    supplied: dict[str, str],
) -> None:
    for field_name, value in supplied.items():
        if value and not is_nonblank_string(value):
            raise GovernanceError(
                f"legacy pheromone {field_name} must be non-blank when supplied"
            )
        current = getattr(trail, field_name)
        if current and value and current != value:
            raise GovernanceError(
                f"legacy pheromone {field_name} conflicts with declared binding"
            )


def _resolve_legacy_subject(trail: PheromoneTrail) -> tuple[str, str]:
    declared_subject_id = trail.subject_id
    declared_subject_type = trail.subject_type
    legacy_subjects = [
        ("candidate", trail.candidate_id),
        ("route", trail.route_id),
        ("tool", trail.tool_id),
    ]
    bound_subjects = [
        (kind, identifier) for kind, identifier in legacy_subjects if identifier
    ]
    if declared_subject_id:
        if not is_nonblank_string(declared_subject_id):
            raise GovernanceError("legacy pheromone subject_id must be non-blank")
        if any(
            kind == declared_subject_type and identifier != declared_subject_id
            for kind, identifier in bound_subjects
        ):
            raise GovernanceError("legacy pheromone subject binding is inconsistent")
        subject_type = declared_subject_type
        subject_id = declared_subject_id
    else:
        direct_subjects = [
            (kind, identifier)
            for kind, identifier in bound_subjects
            if kind != "candidate" or not trail.route_id and not trail.tool_id
        ]
        route_tool_subjects = [
            item for item in bound_subjects if item[0] in {"route", "tool"}
        ]
        if len(route_tool_subjects) > 1:
            raise GovernanceError(
                "legacy pheromone trail has ambiguous route/tool subject bindings"
            )
        if route_tool_subjects:
            subject_type, subject_id = route_tool_subjects[0]
        elif direct_subjects:
            subject_type, subject_id = direct_subjects[0]
        else:
            raise GovernanceError("legacy pheromone trail does not identify a subject")

    return subject_type, subject_id


__all__: list[str] = []
