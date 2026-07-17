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


SWARM_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    _contract("explore", frozenset({"scout_count"})),
    _contract(
        "scout_report",
        frozenset(
            {
                "scout_id",
                "candidate_id",
                "evidence_id",
                "provenance",
                "support",
                "source_trace_event_id",
                "verification_trace_event_id",
            }
        ),
    ),
    *(
        _contract(
            event_type,
            frozenset(
                {
                    "source_id",
                    "candidate_id",
                    "strength",
                    "provenance",
                    "source_trace_event_id",
                    "verification_trace_event_id",
                }
            ),
        )
        for event_type in ("recruit", "inhibit")
    ),
    _contract(
        "candidate_score",
        frozenset(
            {
                "scores",
                "score_breakdown",
                "scout_diversity",
                "pheromone_source_diversity",
            }
        ),
    ),
    _contract(
        "consensus_check",
        frozenset({"quorum_threshold", "min_independent_scouts"}),
    ),
    *(
        _contract(
            event_type,
            frozenset(
                {
                    "target",
                    "candidate_id",
                    "decision_reason",
                    "upstream_score_lineage",
                }
            ),
        )
        for event_type in ("commit", "fallback")
    ),
    _contract(
        "output",
        frozenset(
            {
                "committed_candidate",
                "evidence_provenance",
                "stop_resolution",
                "publication_permission",
                "authorized",
            }
        ),
    ),
)


__all__: tuple[str, ...] = ()
