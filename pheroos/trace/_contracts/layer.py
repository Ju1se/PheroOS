from __future__ import annotations

from pheroos.trace._contracts.base import TraceEventContract
from pheroos.trace._validation_core import build_declared_event_validator


def _contract(event_type: str, required: frozenset[str]) -> TraceEventContract:
    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=build_declared_event_validator(
            required,
            schema_condition=True,
        ),
        authority_relevant=True,
        schema_condition=True,
    )


LAYER_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    _contract(
        "layer_proposal",
        frozenset(
            {
                "layer_id",
                "source_id",
                "action",
                "effect",
                "candidate_id",
                "confidence",
                "support",
                "risk",
                "proposed_strength",
                "proposed_pheromone_kind",
                "subject_type",
                "subject_id",
                "evidence_id",
                "provenance",
                "source_trace_event_id",
            }
        ),
    ),
    _contract(
        "coordination_assess",
        frozenset(
            {
                "confidences",
                "weights",
                "snapshots",
                "coverage",
                "action_effects",
                "trace_coverage_confirmations",
                "proposal_lineage",
            }
        ),
    ),
    _contract(
        "coordination_resolve",
        frozenset(
            {
                "conflicts",
                "resolution",
                "selected_candidate",
                "fallback_used",
                "reason",
                "proposal_lineage",
            }
        ),
    ),
    _contract(
        "policy_adjustment",
        frozenset(
            {
                "proposed_values",
                "declared_bounds",
                "result",
                "source_id",
                "layer_id",
                "provenance",
                "source_trace_event_id",
            }
        ),
    ),
)


__all__: tuple[str, ...] = ()
