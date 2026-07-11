from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from pheroos.conformance.checks import (
    pheromone_behavior,
    pheromone_subject_scoring,
    score_breakdown_contract,
)
from pheroos.conformance.report import CheckResult
from pheroos.conformance.profile import profile_for_manifest
from pheroos.conformance.runner import MANIFEST_CHECKS, safe_check
from pheroos.protocol import load_capability_manifest
from pheroos.protocol.models import CapabilityManifest, PheromoneKindProfile
from pheroos.protocol.validation import validate_capability_manifest


CHECKS = (
    score_breakdown_contract.check,
    pheromone_behavior.check,
    pheromone_subject_scoring.check,
)


@pytest.mark.parametrize(
    ("maximum", "diversity"),
    [
        pytest.param(0.5, None, id="low-strength-cap"),
        pytest.param(None, 3, id="multiple-sources"),
        pytest.param(0.5, 3, id="low-cap-multiple-sources"),
    ],
)
@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.__module__.rsplit(".", 1)[-1])
def test_hybrid_fixture_uses_manifest_strength_and_diversity(
    check: Callable[[CapabilityManifest], CheckResult],
    maximum: float | None,
    diversity: int | None,
) -> None:
    manifest = hybrid_manifest(maximum=maximum, diversity=diversity)

    result = check(manifest)

    assert result.ok is True, result.detail


@pytest.mark.parametrize("check", CHECKS, ids=lambda check: check.__module__.rsplit(".", 1)[-1])
def test_hybrid_fixture_check_is_total_and_fails_closed(
    check: Callable[[CapabilityManifest], CheckResult],
) -> None:
    manifest = hybrid_manifest(diversity="invalid")

    result = check(manifest)

    assert result.ok is False
    assert result.detail.startswith("fixture_error:")


@pytest.mark.parametrize(
    "variant",
    [
        pytest.param("source-cap-0.001", id="source-cap-0.001"),
        pytest.param("source-cap-0.1", id="source-cap-0.1"),
        pytest.param("round-cap-0.001", id="round-cap-0.001"),
        pytest.param("round-cap-0.1", id="round-cap-0.1"),
        pytest.param("round-cap-1", id="round-cap-1"),
        pytest.param("saturation-0", id="saturation-0"),
        pytest.param("saturation-0.001", id="saturation-0.001"),
        pytest.param("exploration-disabled", id="exploration-disabled"),
        pytest.param("quorum-1", id="quorum-1"),
        pytest.param("zero-layer-weights", id="zero-layer-weights"),
        pytest.param("zero-positive-kind-weight", id="zero-positive-kind-weight"),
        pytest.param("zero-positive-kind-ttl", id="zero-positive-kind-ttl"),
        pytest.param("diffusion-hops-3", id="diffusion-hops-3"),
        pytest.param("positive-kind-competitive", id="positive-kind-competitive"),
        pytest.param("extension-only-kind-profile", id="extension-only-kind-profile"),
        pytest.param("extension-scoring-kind-profile", id="extension-scoring-kind-profile"),
        pytest.param("stale-only-kind-profile", id="stale-only-kind-profile"),
        pytest.param("all-adjustment-bounds", id="all-adjustment-bounds"),
    ],
)
def test_full_hybrid_profile_accepts_validation_clean_legal_policy_matrix(
    variant: str,
) -> None:
    manifest = legal_policy_variant(variant)

    assert validate_capability_manifest(manifest) == []
    failures = [
        result
        for check_name in profile_for_manifest(manifest).required_checks
        if check_name != "manifest_schema"
        for result in [safe_check(check_name, MANIFEST_CHECKS[check_name], manifest)]
        if not result.ok
    ]

    assert failures == []


def hybrid_manifest(
    *,
    maximum: float | None = None,
    diversity: int | str | None = None,
) -> CapabilityManifest:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    updates: dict[str, object] = {}
    if maximum is not None:
        updates["pheromone_max_strength"] = maximum
    if diversity is not None:
        updates["pheromone_min_source_diversity"] = diversity
    return replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )


def legal_policy_variant(variant: str) -> CapabilityManifest:
    manifest = hybrid_manifest()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    updates: dict[str, object]
    if variant == "source-cap-0.001":
        updates = {"pheromone_per_source_cap": 0.001}
    elif variant == "source-cap-0.1":
        updates = {"pheromone_per_source_cap": 0.1}
    elif variant.startswith("round-cap-"):
        updates = {
            "pheromone_per_source_cap": 100.0,
            "pheromone_per_round_deposit_cap": float(
                variant.removeprefix("round-cap-")
            ),
        }
    elif variant == "saturation-0":
        updates = {"pheromone_saturation_threshold": 0.0}
    elif variant == "saturation-0.001":
        updates = {"pheromone_saturation_threshold": 0.001}
    elif variant == "exploration-disabled":
        updates = {"exploration_enabled": False}
    elif variant == "quorum-1":
        updates = {"quorum_threshold": 1}
    elif variant == "zero-layer-weights":
        updates = {
            "layer_default_weights": {
                layer_id: 0.0 for layer_id in policy.layer_default_weights
            }
        }
    elif variant == "zero-positive-kind-weight":
        updates = {
            "pheromone_kind_profiles": {
                **policy.pheromone_kind_profiles,
                "positive": replace(
                    policy.pheromone_kind_profiles["positive"],
                    weight=0.0,
                ),
            }
        }
    elif variant == "zero-positive-kind-ttl":
        updates = {
            "pheromone_kind_profiles": {
                **policy.pheromone_kind_profiles,
                "positive": replace(
                    policy.pheromone_kind_profiles["positive"],
                    ttl_steps=0,
                ),
            }
        }
    elif variant == "diffusion-hops-3":
        updates = {"pheromone_diffusion_max_hops": 3}
    elif variant == "positive-kind-competitive":
        updates = {
            "pheromone_kind_profiles": {
                **policy.pheromone_kind_profiles,
                "positive": replace(
                    policy.pheromone_kind_profiles["positive"],
                    response_model="competitive",
                ),
            }
        }
    elif variant == "extension-only-kind-profile":
        updates = {
            "pheromone_kind_profiles": {
                "x-a.kind": PheromoneKindProfile(weight=1.0),
            }
        }
    elif variant == "extension-scoring-kind-profile":
        updates = {
            "pheromone_kind_profiles": {
                "x-a.kind": PheromoneKindProfile(
                    weight=1.0,
                    scored_subject_types=["candidate"],
                ),
            }
        }
    elif variant == "stale-only-kind-profile":
        updates = {
            "pheromone_kind_profiles": {
                "stale": PheromoneKindProfile(weight=0.0),
            }
        }
    elif variant == "all-adjustment-bounds":
        updates = {
            "policy_adjustment_bounds": {
                "pheromone_evaporation_rate": (0.0, 1.0),
                "pheromone_positive_weight": (0.0, 10.0),
                "pheromone_negative_weight": (0.0, 10.0),
                "pheromone_cautionary_weight": (0.0, 10.0),
                "pheromone_alarm_weight": (0.0, 10.0),
                "pheromone_novelty_weight": (0.0, 10.0),
                "pheromone_response_model": {
                    "allowed_values": [
                        "linear",
                        "saturating",
                        "threshold",
                        "competitive",
                    ]
                },
                "pheromone_exploration_floor": (0.0, 1.0),
                "pheromone_cautionary_override_threshold": (
                    0.0,
                    policy.pheromone_max_strength,
                ),
                "layer_emergency_override_threshold": (0.0, 1.0),
                "layer_learned_weight": policy.layer_weight_bounds["learned"],
                "layer_evolutionary_weight": policy.layer_weight_bounds[
                    "evolutionary"
                ],
                "layer_metacognitive_weight": policy.layer_weight_bounds[
                    "metacognitive"
                ],
            }
        }
    else:  # pragma: no cover - parametrization owns the closed fixture set
        raise AssertionError(f"unknown legal policy variant: {variant}")
    return replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )
