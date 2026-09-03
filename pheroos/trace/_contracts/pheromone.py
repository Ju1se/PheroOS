from __future__ import annotations

from pheroos.trace._contracts.base import TraceEventContract
from pheroos.trace._validation_core import build_declared_event_validator


def _contract(
    event_type: str,
    required: frozenset[str],
    *,
    schema_condition: bool = True,
) -> TraceEventContract:
    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=build_declared_event_validator(
            required,
            schema_condition=schema_condition,
        ),
        authority_relevant=True,
        schema_condition=schema_condition,
    )


PHEROMONE_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    # Collective replay events remain valid as private attention-profile
    # lineage.  They are deliberately absent from the manifest conformance
    # registry; keeping their trace contracts lets the implemented Hybrid
    # profile replay and audit its internal evidence without making swarm
    # semantics mandatory for baseline implementations.
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
    _contract(
        "pheromone_deposit",
        frozenset(
            {
                "source_id",
                "provenance",
                "subject_type",
                "subject_id",
                "candidate_id",
                "kind",
                "source_kind",
                "source_strength",
                "old_strength",
                "requested_strength",
                "applied_strength",
                "new_strength",
                "round_budget_remaining",
                "source_budget_remaining",
                "step",
                "deposited_at_step",
                "updated_at_step",
                "source_trace_event_id",
                "trace_event_id",
            }
        ),
    ),
    _contract(
        "pheromone_evaporate",
        frozenset(
            {
                "subject_type",
                "subject_id",
                "kind",
                "source_kind",
                "source_id",
                "provenance",
                "source_strength",
                "old_strength",
                "requested_strength",
                "applied_strength",
                "new_strength",
                "strength_delta",
                "elapsed_steps",
                "step",
                "source_updated_at_step",
                "deposited_at_step",
                "profile",
                "candidate_id",
                "source_trace_event_id",
                "trace_event_id",
            }
        ),
    ),
    _contract(
        "pheromone_diffuse",
        frozenset(
            {
                "source_subject",
                "target_subject",
                "hop",
                "attenuation",
                "policy_attenuation",
                "edge_attenuation",
                "root_trace_event_id",
                "source_strength",
                "requested_strength",
                "applied_strength",
                "new_strength",
                "round_budget_remaining",
                "source_budget_remaining",
                "source_id",
                "candidate_id",
                "source_kind",
                "kind",
                "provenance",
                "source_trace_event_id",
                "trace_event_id",
            }
        ),
    ),
    _contract(
        "pheromone_reinforce",
        frozenset(
            {
                "feedback_source",
                "source_id",
                "provenance",
                "outcome",
                "reward",
                "delta",
                "source_strength",
                "requested_strength",
                "applied_strength",
                "old_strength",
                "new_strength",
                "candidate_id",
                "subject_type",
                "subject_id",
                "source_kind",
                "kind",
                "budget_result",
                "step",
                "source_trace_event_id",
                "feedback_trace_event_id",
                "trace_event_id",
            }
        ),
    ),
    _contract(
        "pheromone_score",
        frozenset(
            {
                "scores",
                "score_breakdown",
                "kind_breakdown",
                "subject_breakdown",
                "active_trails",
                "current_step",
            }
        ),
    ),
    _contract(
        "pheromone_clip",
        frozenset(
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
                "requested_strength",
                "applied_strength",
                "round_budget_remaining",
                "source_budget_remaining",
            }
        ),
    ),
    _contract(
        "pheromone_expire",
        frozenset(
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
                "old_strength",
                "source_strength",
                "requested_strength",
                "applied_strength",
                "new_strength",
                "strength_delta",
                "step",
                "source_updated_at_step",
                "deposited_at_step",
                "ttl_steps",
                "elapsed_steps",
            }
        ),
    ),
    # Observation has three versioned variants selected by its runtime
    # validator, so its common required set remains empty as in Trace ABI v1.
    _contract("pheromone_observe", frozenset()),
    _contract(
        "pheromone_normalize",
        frozenset(
            {
                "candidates",
                "pre_scores",
                "post_scores",
                "response_model",
                "competition_mode",
            }
        ),
    ),
    # This legacy informational built-in was already accepted by v1 without a
    # schema condition.  Declaring it closes the built-in set without changing
    # its wire or runtime behavior.
    _contract("pheromone_inhibit", frozenset(), schema_condition=False),
)


__all__: tuple[str, ...] = ()
