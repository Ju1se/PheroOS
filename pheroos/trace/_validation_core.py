from __future__ import annotations

from pheroos.trace._coordination_lineage_rules import (
    apply_coordination_lineage_rule,
)
from pheroos.trace._collective_lineage_rules import apply_collective_lineage_rule
from pheroos.trace._lineage_types import (
    DECLARED_COORDINATION_LAYER_IDS as DECLARED_COORDINATION_LAYER_IDS,
    EXTENSION_EVENT_PREFIXES as EXTENSION_EVENT_PREFIXES,
    LAYER_SNAPSHOT_FIELDS as LAYER_SNAPSHOT_FIELDS,
    PHEROMONE_CLIP_PAYLOAD_VERSION as PHEROMONE_CLIP_PAYLOAD_VERSION,
    TraceEventValidator as TraceEventValidator,
    TraceEventView as TraceEventView,
)
from pheroos.trace._pheromone_lineage_rules import apply_pheromone_lineage_rule
from pheroos.trace._pheromone_receipts import (
    canonical_pheromone_clip_payload as canonical_pheromone_clip_payload,
    pheromone_clip_payload_fingerprint as pheromone_clip_payload_fingerprint,
)
from pheroos.trace.commit_contracts import (
    COMMIT_EVENT_TYPES,
    validate_commit_trace_event,
)


def build_declared_event_validator(
    required_fields: frozenset[str],
    *,
    schema_condition: bool,
) -> TraceEventValidator:
    """Bind one immutable declaration to the complete low-level validator."""

    declared_fields = frozenset(required_fields)

    def validate_declared_event(event: TraceEventView) -> None:
        _validate_declared_event_lineage(
            event,
            required_fields=declared_fields,
            schema_condition=schema_condition,
        )

    return validate_declared_event


def _validate_declared_event_lineage(
    event: TraceEventView,
    *,
    required_fields: frozenset[str],
    schema_condition: bool,
) -> None:
    """Validate built-in lineage through fixed, provider-free rule families."""

    if not isinstance(event.lineage, dict):
        raise ValueError("trace event lineage must be an object")
    if event.event_type in COMMIT_EVENT_TYPES:
        validate_commit_trace_event(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=event.lineage,
        )
        return
    if not schema_condition:
        return
    missing = sorted(field for field in required_fields if field not in event.lineage)
    if missing:
        raise ValueError(
            f"{event.event_type} trace lineage missing required fields: "
            f"{', '.join(missing)}"
        )
    if apply_pheromone_lineage_rule(event, required_fields):
        return
    if apply_collective_lineage_rule(event, required_fields):
        return
    apply_coordination_lineage_rule(event, required_fields)


__all__: tuple[str, ...] = ()
