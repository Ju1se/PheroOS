from __future__ import annotations

from copy import copy, deepcopy
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pheroos.governance import (
    PolicyAdjustmentProposal,
    RunScopedPolicyOverlay,
    apply_policy_adjustment_overlay,
    validate_policy_adjustment_proposal,
    validate_policy_adjustment_proposals,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.policy_adjustment import (
    adjustment_value_allowed,
    numeric,
    run_scoped_policy_overlay_is_authoritative,
    validate_absolute_adjustment_value,
    validate_policy_adjustment_bounds,
)
from pheroos.protocol.models import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
)


def _policy(**overrides: Any) -> CollectiveDecisionPolicy:
    values: dict[str, Any] = {
        "mode": "hybrid",
        "pheromone_max_strength": 2.0,
        "pheromone_evaporation_rate": 0.2,
        "pheromone_response_model": "linear",
        "pheromone_exploration_floor": 0.1,
        "pheromone_cautionary_override_threshold": 1.0,
        "layer_emergency_override_threshold": 0.8,
        "pheromone_kind_profiles": {
            "positive": PheromoneKindProfile(
                weight=1.0,
                evaporation_rate=0.2,
                response_model="linear",
            )
        },
        "layer_weight_bounds": {
            "learned": (0.0, 2.0),
            "evolutionary": (0.0, 2.0),
            "metacognitive": (0.0, 2.0),
        },
        "layer_default_weights": {
            "learned": 1.0,
            "evolutionary": 1.0,
            "metacognitive": 1.0,
        },
        "policy_adjustment_bounds": {
            "pheromone_evaporation_rate": (0.0, 1.0),
            "pheromone_response_model": {
                "allowed_values": (
                    "linear",
                    "saturating",
                    "threshold",
                    "competitive",
                )
            },
            "pheromone_exploration_floor": (0.0, 1.0),
            "pheromone_cautionary_override_threshold": (0.0, 2.0),
            "layer_emergency_override_threshold": (0.0, 1.0),
            "pheromone_positive_weight": (0.0, 2.0),
            "pheromone_negative_weight": (0.0, 2.0),
            "pheromone_cautionary_weight": (0.0, 2.0),
            "pheromone_alarm_weight": (0.0, 2.0),
            "pheromone_novelty_weight": (0.0, 2.0),
            "layer_learned_weight": (0.0, 2.0),
            "layer_evolutionary_weight": (0.0, 2.0),
            "layer_metacognitive_weight": (0.0, 2.0),
        },
    }
    values.update(overrides)
    return CollectiveDecisionPolicy(**values)


def _proposal(
    adjustments: dict[str, Any] | None = None,
    *,
    layer_id: str = "evolutionary",
    source_id: str = "source:evolutionary",
    provenance: str = "runtime:evolutionary",
    trace_event_id: str = "trace:policy-adjustment",
) -> PolicyAdjustmentProposal:
    return PolicyAdjustmentProposal(
        layer_id=layer_id,
        source_id=source_id,
        adjustments=adjustments
        if adjustments is not None
        else {"pheromone_evaporation_rate": 0.3},
        provenance=provenance,
        trace_event_id=trace_event_id,
    )


def test_overlay_values_are_immutable_canonical_and_fail_closed() -> None:
    policy = _policy()
    proposal = _proposal()
    assert deepcopy(proposal) is proposal

    overlay = validate_policy_adjustment_proposal(proposal, policy)
    assert run_scoped_policy_overlay_is_authoritative(overlay)
    assert repr(overlay) == repr(dict(overlay))
    assert overlay != object()
    assert copy(overlay) is overlay
    assert deepcopy(overlay) is overlay
    with pytest.raises(AttributeError, match="immutable"):
        del overlay.source_ids

    nested = RunScopedPolicyOverlay(
        {
            "nested": {
                "sequence": [1, 2],
                "unordered": {"second", "first"},
            }
        }
    )
    assert not run_scoped_policy_overlay_is_authoritative(nested)
    assert not run_scoped_policy_overlay_is_authoritative(object())

    corrupted = RunScopedPolicyOverlay({"value": 1})
    object.__setattr__(corrupted, "_values", object())
    assert not run_scoped_policy_overlay_is_authoritative(corrupted)


def test_adjustment_batches_reject_duplicate_identity_and_keys_atomically() -> None:
    policy = _policy()
    first = _proposal(
        {"pheromone_evaporation_rate": 0.3},
        source_id="source:first",
        trace_event_id="trace:duplicate",
    )
    duplicate_trace = _proposal(
        {"pheromone_exploration_floor": 0.2},
        source_id="source:second",
        trace_event_id="trace:duplicate",
    )
    with pytest.raises(GovernanceError, match="duplicate.*trace_event_id"):
        validate_policy_adjustment_proposals(
            [first, duplicate_trace],
            policy,
        )

    duplicate_key = _proposal(
        {"pheromone_evaporation_rate": 0.4},
        layer_id="learned",
        source_id="source:second",
        trace_event_id="trace:second",
    )
    with pytest.raises(GovernanceError, match="more than once"):
        validate_policy_adjustment_proposals(
            [first, duplicate_key],
            policy,
        )


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (
            SimpleNamespace(policy_adjustment_bounds=None),
            "does not expose adjustment bounds",
        ),
        (
            SimpleNamespace(
                policy_adjustment_bounds={"pheromone_evaporation_rate": (1.0, 0.0)}
            ),
            "bounds are invalid",
        ),
        (
            SimpleNamespace(
                policy_adjustment_bounds={
                    "pheromone_evaporation_rate": {
                        "min": "invalid",
                        "max": 1.0,
                    }
                }
            ),
            "bounds are invalid",
        ),
        (
            SimpleNamespace(
                policy_adjustment_bounds={
                    "pheromone_response_model": {"allowed_values": ()}
                }
            ),
            "allowed values are invalid",
        ),
        (
            SimpleNamespace(
                policy_adjustment_bounds={
                    "pheromone_evaporation_rate": {"minimum": 0.0, "maximum": 1.0}
                }
            ),
            "bounds are invalid",
        ),
        (
            SimpleNamespace(
                policy_adjustment_bounds={"layer_learned_weight": (0.0, 1.0)},
                layer_weight_bounds={},
            ),
            "requires declared layer weight bounds",
        ),
    ],
)
def test_policy_adjustment_bound_shapes_fail_closed(
    policy: object,
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        validate_policy_adjustment_bounds(policy)


def test_mapping_bounds_and_enum_bounds_validate_deterministically() -> None:
    policy = SimpleNamespace(
        policy_adjustment_bounds={
            "pheromone_evaporation_rate": {"min": 0.1, "max": 0.5},
            "pheromone_response_model": {"allowed_values": ("linear", "saturating")},
        }
    )
    validate_policy_adjustment_bounds(policy)


@pytest.mark.parametrize(
    ("proposal", "message"),
    [
        (
            _proposal(source_id=cast(Any, 1)),
            "source_id must be a string",
        ),
        (
            _proposal(layer_id="unsupported"),
            "unsupported layer id",
        ),
        (
            _proposal(source_id=""),
            "source_id is required",
        ),
        (
            _proposal(provenance=""),
            "missing provenance",
        ),
        (
            _proposal(trace_event_id=""),
            "missing trace event id",
        ),
        (
            _proposal({}),
            "at least one adjustment",
        ),
    ],
)
def test_policy_adjustment_proposal_identity_is_total(
    proposal: PolicyAdjustmentProposal,
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        validate_policy_adjustment_proposal(proposal, _policy())


def test_proposal_cannot_escape_the_declared_field_set() -> None:
    policy = _policy(
        policy_adjustment_bounds={"pheromone_evaporation_rate": (0.0, 1.0)}
    )
    with pytest.raises(GovernanceError, match="outside declared bounds"):
        validate_policy_adjustment_proposal(
            _proposal({"pheromone_response_model": "linear"}),
            policy,
        )


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        (
            "pheromone_response_model",
            "unsupported",
            "response model adjustment is unsupported",
        ),
        (
            "pheromone_evaporation_rate",
            "not-numeric",
            "must be a finite number",
        ),
        (
            "pheromone_evaporation_rate",
            1.1,
            "evaporation adjustment is outside absolute bounds",
        ),
        (
            "pheromone_exploration_floor",
            -0.1,
            "exploration adjustment is outside absolute bounds",
        ),
        (
            "pheromone_positive_weight",
            10.1,
            "weight adjustment is outside absolute bounds",
        ),
        (
            "pheromone_cautionary_override_threshold",
            10.1,
            "threshold adjustment is outside absolute bounds",
        ),
        (
            "layer_emergency_override_threshold",
            1.1,
            "emergency threshold adjustment is outside absolute bounds",
        ),
    ],
)
def test_absolute_adjustment_values_reject_every_unsafe_dimension(
    key: str,
    value: Any,
    message: str,
) -> None:
    with pytest.raises(GovernanceError, match=message):
        validate_absolute_adjustment_value(key, value)


def test_overlay_application_rechecks_the_active_policy_envelope() -> None:
    broad = _policy(policy_adjustment_bounds={"pheromone_evaporation_rate": (0.0, 1.0)})
    overlay = validate_policy_adjustment_proposal(
        _proposal({"pheromone_evaporation_rate": 0.8}),
        broad,
    )
    narrow = _policy(
        policy_adjustment_bounds={"pheromone_evaporation_rate": (0.0, 0.5)}
    )
    with pytest.raises(GovernanceError, match="value is outside declared bounds"):
        apply_policy_adjustment_overlay(narrow, overlay)

    response_policy = _policy(
        policy_adjustment_bounds={
            "pheromone_response_model": {"allowed_values": ("linear", "saturating")}
        }
    )
    response_overlay = validate_policy_adjustment_proposal(
        _proposal({"pheromone_response_model": "saturating"}),
        response_policy,
    )
    without_response_declaration = _policy(policy_adjustment_bounds={})
    with pytest.raises(GovernanceError, match="outside declared bounds"):
        apply_policy_adjustment_overlay(
            without_response_declaration,
            response_overlay,
        )


def test_adjustment_bound_predicates_are_exact_and_total() -> None:
    assert not adjustment_value_allowed(
        "linear",
        {"allowed_values": ()},
    )
    assert adjustment_value_allowed(0.5, {"min": 0.0, "max": 1.0})
    assert not adjustment_value_allowed(
        "0.5",
        {"min": 0.0, "max": 1.0},
    )
    assert not adjustment_value_allowed(0.5, {"other": (0.0, 1.0)})
    assert not adjustment_value_allowed(0.5, object())

    assert numeric(1)
    assert not numeric(True)
    assert not numeric(float("inf"))
