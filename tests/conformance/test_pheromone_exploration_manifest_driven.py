from __future__ import annotations

from dataclasses import replace

import pytest

from pheroos.conformance.checks import pheromone_response_model
from pheroos.protocol import load_capability_manifest


@pytest.mark.parametrize(
    "updates",
    [
        pytest.param({"novelty_decay_rate": 0.0}, id="no-novelty-decay"),
        pytest.param({"novelty_decay_rate": 0.25}, id="fractional-novelty-decay"),
        pytest.param({"novelty_decay_rate": 1.0}, id="complete-novelty-decay"),
        pytest.param({"stale_route_reopen_threshold": 0.0}, id="zero-reopen-threshold"),
        pytest.param({"stale_route_reopen_threshold": 20.0}, id="threshold-above-max"),
        pytest.param(
            {
                "pheromone_min_strength": 0.5,
                "stale_route_reopen_threshold": 0.2,
            },
            id="threshold-below-min",
        ),
        pytest.param(
            {
                "exploration_enabled": False,
                "novelty_decay_rate": 0.3,
                "stale_route_reopen_threshold": 0.4,
            },
            id="declared-values-while-disabled",
        ),
    ],
)
def test_response_check_exercises_manifest_exploration_boundaries(updates) -> None:
    manifest = hybrid_manifest(**updates)

    result = pheromone_response_model.check(manifest)

    assert result.ok is True, result.detail


def test_response_check_passes_declared_exploration_values_to_governance(monkeypatch) -> None:
    manifest = hybrid_manifest(
        novelty_decay_rate=0.375,
        stale_route_reopen_threshold=0.625,
    )
    observed: list[tuple[bool, float, float]] = []
    observe = pheromone_response_model.observe_pheromone_exploration

    def tracking_observe(*, policy, **kwargs):
        observed.append(
            (
                policy.exploration_enabled,
                policy.novelty_decay_rate,
                policy.stale_route_reopen_threshold,
            )
        )
        return observe(policy=policy, **kwargs)

    monkeypatch.setattr(
        pheromone_response_model,
        "observe_pheromone_exploration",
        tracking_observe,
    )

    result = pheromone_response_model.check(manifest)

    assert result.ok is True, result.detail
    assert (True, 0.375, 0.625) in observed
    assert (False, 0.375, 0.625) in observed


def test_response_check_detects_missing_exploration_observations(monkeypatch) -> None:
    manifest = hybrid_manifest(
        novelty_decay_rate=0.5,
        stale_route_reopen_threshold=0.2,
    )
    monkeypatch.setattr(
        pheromone_response_model,
        "observe_pheromone_exploration",
        lambda **kwargs: (),
    )

    result = pheromone_response_model.check(manifest)

    assert result.ok is False
    assert "novelty_decay_rate" in result.detail
    assert "stale_route_reopen_threshold" in result.detail


def test_response_check_does_not_enable_undeclared_exploration(monkeypatch) -> None:
    manifest = hybrid_manifest(
        exploration_enabled=False,
        novelty_decay_rate=0.5,
        stale_route_reopen_threshold=0.2,
    )
    observed_enabled_values: list[bool] = []
    observe = pheromone_response_model.observe_pheromone_exploration

    def tracking_observe(*, policy, **kwargs):
        observed_enabled_values.append(policy.exploration_enabled)
        return observe(policy=policy, **kwargs)

    monkeypatch.setattr(
        pheromone_response_model,
        "observe_pheromone_exploration",
        tracking_observe,
    )

    result = pheromone_response_model.check(manifest)

    assert result.ok is True, result.detail
    assert observed_enabled_values
    assert set(observed_enabled_values) == {False}


@pytest.mark.parametrize(
    "updates",
    [
        {"novelty_decay_rate": "invalid"},
        {"stale_route_reopen_threshold": "invalid"},
    ],
)
def test_response_check_is_total_for_malformed_direct_exploration_policy(updates) -> None:
    manifest = hybrid_manifest(**updates)

    result = pheromone_response_model.check(manifest)

    assert result.ok is False
    assert result.detail.startswith("exercise:")


def hybrid_manifest(**updates):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    return replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )
