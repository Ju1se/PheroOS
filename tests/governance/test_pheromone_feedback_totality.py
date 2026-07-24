from __future__ import annotations

from dataclasses import replace

import pytest

from pheroos.governance.errors import GovernanceError
from pheroos.governance.pheromone import PheromonePolicy, PheromoneTrail
from pheroos.governance.pheromone_feedback import (
    PheromoneFeedback,
    pheromone_kind_for_feedback,
    reinforce_pheromone_trails_with_records,
    stale_matching_trails,
    validate_pheromone_feedback,
)


TARGET = "decision:feedback"
CANDIDATE = "candidate:alpha"


def _policy(**overrides: object) -> PheromonePolicy:
    values: dict[str, object] = {
        "enabled": True,
        "max_strength": 10.0,
        "per_source_cap": 10.0,
        "per_round_deposit_cap": 10.0,
        "require_provenance": True,
        "require_trace": True,
    }
    values.update(overrides)
    return PheromonePolicy(**values)


def _feedback(**overrides: object) -> PheromoneFeedback:
    values: dict[str, object] = {
        "source_id": "source:a",
        "subject_type": "route",
        "subject_id": "route:a",
        "candidate_id": CANDIDATE,
        "target": TARGET,
        "outcome": "success",
        "strength_delta": 1.0,
        "evidence_id": "evidence:feedback",
        "provenance": "runtime:test",
        "trace_event_id": "trace:feedback",
        "step": 2,
    }
    values.update(overrides)
    return PheromoneFeedback(**values)


def _trail(**overrides: object) -> PheromoneTrail:
    values: dict[str, object] = {
        "candidate_id": CANDIDATE,
        "strength": 2.0,
        "subject_type": "route",
        "subject_id": "route:a",
        "target": TARGET,
        "kind": "positive",
        "source_id": "source:a",
        "evidence_id": "evidence:deposit",
        "provenance": "runtime:test",
        "trace_event_id": "trace:deposit",
        "updated_at_step": 1,
    }
    values.update(overrides)
    return PheromoneTrail(**values)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source_id": 1}, "source_id must be a string"),
        ({"outcome": "indeterminate"}, "unsupported pheromone feedback outcome"),
        ({"subject_type": "swarm"}, "unsupported pheromone feedback subject type"),
        ({"trace_event_id": ""}, "missing trace event id"),
    ],
)
def test_feedback_validation_rejects_remaining_invalid_shapes(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        validate_pheromone_feedback(
            replace(_feedback(), **changes),
            _policy(),
        )


def test_candidate_feedback_accepts_matching_subject_without_candidate_set() -> None:
    validate_pheromone_feedback(
        _feedback(subject_type="candidate", subject_id=CANDIDATE),
        _policy(),
    )


def test_disabled_feedback_returns_existing_memory_without_mutation() -> None:
    existing = _trail()

    result = reinforce_pheromone_trails_with_records(
        [existing],
        [_feedback()],
        _policy(feedback_enabled=False),
    )

    assert result.trails == (existing,)
    assert result.records == ()
    assert result.processed_feedback_ids == frozenset()
    assert result.budget_state is not None
    assert result.budget_state.round_used == 0.0


def test_feedback_cannot_precede_matching_trail_update() -> None:
    with pytest.raises(GovernanceError, match="must not precede matching trail update"):
        reinforce_pheromone_trails_with_records(
            [_trail(updated_at_step=3)],
            [_feedback(step=2)],
            _policy(feedback_enabled=True),
        )


def test_subminimum_new_feedback_is_rejected_without_consuming_budget() -> None:
    result = reinforce_pheromone_trails_with_records(
        [],
        [_feedback(strength_delta=0.5)],
        _policy(feedback_enabled=True, min_strength=1.0),
    )

    assert result.trails == ()
    assert len(result.records) == 1
    assert result.records[0].action == "reinforce_rejected"
    assert result.records[0].applied_strength == 0.0
    assert result.budget_state is not None
    assert result.budget_state.round_used == 0.0


@pytest.mark.parametrize(
    ("outcome", "kind"),
    [
        ("failure", "negative"),
        ("hazard", "alarm"),
        ("novel", "novelty"),
    ],
)
def test_feedback_outcomes_map_to_remaining_pheromone_kinds(
    outcome: str,
    kind: str,
) -> None:
    assert pheromone_kind_for_feedback(_feedback(outcome=outcome)) == kind


def test_stale_feedback_wrapper_updates_matching_memory() -> None:
    changed = stale_matching_trails(
        [_trail()],
        _feedback(outcome="stale", strength_delta=0.0),
        _policy(),
    )

    assert len(changed) == 1
    assert changed[0].kind == "stale"
    assert changed[0].trace_event_id == "trace:feedback"


def test_stale_feedback_cannot_precede_matching_trail_update() -> None:
    with pytest.raises(GovernanceError, match="must not precede matching trail update"):
        stale_matching_trails(
            [_trail(updated_at_step=3)],
            _feedback(outcome="stale", strength_delta=0.0, step=2),
            _policy(),
        )


def test_reinforcement_rejects_duplicate_feedback_trace_ids() -> None:
    first = _feedback(trace_event_id="trace:duplicate")

    with pytest.raises(GovernanceError, match="duplicate.*trace_event_id"):
        reinforce_pheromone_trails_with_records(
            [],
            [first, replace(first, outcome="failure")],
            _policy(feedback_enabled=True),
        )


def test_reinforcement_rejects_equivalent_feedback_records() -> None:
    first = _feedback(trace_event_id="trace:first")

    with pytest.raises(GovernanceError, match="duplicate equivalent"):
        reinforce_pheromone_trails_with_records(
            [],
            [first, replace(first, trace_event_id="trace:second")],
            _policy(feedback_enabled=True),
        )
