from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from pheroos.governance import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.runtime_policy import (
    resolve_collective_fallback_id,
    validate_collective_runtime_policy,
)
from pheroos.protocol import CollectiveDecisionPolicy, PheromoneKindProfile


LAYER_IDS = ("reactive", "learned", "evolutionary", "metacognitive")


def complete_hybrid_policy() -> CollectiveDecisionPolicy:
    return CollectiveDecisionPolicy(
        mode="hybrid",
        pheromone_enabled=True,
        pheromone_kind_profiles={
            "positive": PheromoneKindProfile(
                scored_subject_types=["candidate"],
            )
        },
        pheromone_diffusion_enabled=True,
        pheromone_diffusion_max_hops=1,
        pheromone_diffusion_attenuation=0.5,
        pheromone_feedback_enabled=True,
        layer_coordination_enabled=True,
        layer_weight_bounds={layer_id: (0.0, 1.0) for layer_id in LAYER_IDS},
        layer_default_weights={layer_id: 1.0 for layer_id in LAYER_IDS},
        layer_confidence_thresholds={layer_id: 0.5 for layer_id in LAYER_IDS},
        policy_adjustment_bounds={"pheromone_positive_weight": (0.0, 2.0)},
        fallback_candidate="candidate:fallback",
    )


def test_runtime_policy_requires_the_canonical_protocol_declaration() -> None:
    with pytest.raises(
        GovernanceError,
        match="must use the canonical protocol declaration",
    ):
        validate_collective_runtime_policy(
            cast(CollectiveDecisionPolicy, object()),
        )


def test_runtime_policy_requires_a_string_fallback_declaration() -> None:
    with pytest.raises(
        GovernanceError,
        match="fallback_candidate must be a string",
    ):
        validate_collective_runtime_policy(
            CollectiveDecisionPolicy(
                fallback_candidate=cast(str, 7),
            )
        )


def test_runtime_policy_rejects_hybrid_features_outside_hybrid_mode() -> None:
    with pytest.raises(
        GovernanceError,
        match="Hybrid features require mode='hybrid'",
    ):
        validate_collective_runtime_policy(
            CollectiveDecisionPolicy(
                mode="ant_colony",
                pheromone_feedback_enabled=True,
            )
        )


def test_runtime_policy_rejects_an_incomplete_hybrid_declaration() -> None:
    with pytest.raises(
        GovernanceError,
        match="requires the complete Hybrid path",
    ):
        validate_collective_runtime_policy(
            CollectiveDecisionPolicy(mode="hybrid"),
        )


@pytest.mark.parametrize(
    "policy",
    [
        replace(
            complete_hybrid_policy(),
            pheromone_max_strength=0.0,
        ),
        replace(
            complete_hybrid_policy(),
            pheromone_per_source_cap=0.0,
        ),
        replace(
            complete_hybrid_policy(),
            pheromone_per_round_deposit_cap=0.0,
        ),
    ],
    ids=("max-strength", "source-cap", "round-cap"),
)
def test_runtime_policy_requires_positive_hybrid_strength_budgets(
    policy: CollectiveDecisionPolicy,
) -> None:
    with pytest.raises(
        GovernanceError,
        match="requires positive pheromone strength and budgets",
    ):
        validate_collective_runtime_policy(policy)


@pytest.mark.parametrize(
    ("field_name", "policy"),
    [
        (
            "layer_weight_bounds",
            replace(
                complete_hybrid_policy(),
                layer_weight_bounds={
                    layer_id: (0.0, 1.0)
                    for layer_id in LAYER_IDS
                    if layer_id != "metacognitive"
                },
            ),
        ),
        (
            "layer_default_weights",
            replace(
                complete_hybrid_policy(),
                layer_default_weights={
                    layer_id: 1.0
                    for layer_id in LAYER_IDS
                    if layer_id != "metacognitive"
                },
            ),
        ),
        (
            "layer_confidence_thresholds",
            replace(
                complete_hybrid_policy(),
                layer_confidence_thresholds={
                    layer_id: 0.5
                    for layer_id in LAYER_IDS
                    if layer_id != "metacognitive"
                },
            ),
        ),
    ],
)
def test_runtime_policy_requires_complete_layer_maps(
    field_name: str,
    policy: CollectiveDecisionPolicy,
) -> None:
    with pytest.raises(
        GovernanceError,
        match=rf"{field_name} must cover every supported layer",
    ):
        validate_collective_runtime_policy(policy)


def test_fallback_resolution_requires_a_canonical_candidate_set() -> None:
    with pytest.raises(
        GovernanceError,
        match="requires a candidate set",
    ):
        resolve_collective_fallback_id(
            candidate_set=cast(CandidateSet, object()),
            policy=CollectiveDecisionPolicy(
                fallback_candidate="candidate:fallback",
            ),
            target="decision:collective",
            fallback_candidate_id=None,
        )
