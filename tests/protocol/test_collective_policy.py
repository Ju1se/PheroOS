from dataclasses import dataclass, replace

import pytest

from pheroos.protocol import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    TracePolicy,
    collective_fallback_id,
    has_hybrid_pheromone_features,
    is_swarm_policy,
    load_capability_manifest,
    validate_capability_manifest,
)


@dataclass
class _MutableExtensionRecord:
    mode: str
    values: list[str]


def test_swarm_manifest_validates_without_errors() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")

    assert validate_capability_manifest(manifest) == []
    assert manifest.protocol.collective_decision_policy is not None
    assert (
        manifest.protocol.collective_decision_policy.pheromone_decay_model
        == "exponential"
    )
    assert manifest.protocol.collective_decision_policy.pheromone_novelty_weight == 0.5
    assert manifest.protocol.collective_decision_policy.pheromone_per_source_cap == 3
    assert (
        manifest.protocol.collective_decision_policy.pheromone_per_round_deposit_cap
        == 5
    )
    assert (
        manifest.protocol.collective_decision_policy.pheromone_min_source_diversity == 1
    )
    assert (
        manifest.protocol.collective_decision_policy.pheromone_require_provenance
        is True
    )
    assert manifest.protocol.collective_decision_policy.pheromone_require_trace is True


def test_collective_policy_preserves_extension_metadata() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    policy = replace(
        manifest.protocol.collective_decision_policy,
        extensions={"x-collective": {"memory": "external-runtime-owned"}},
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)
    updated = replace(manifest, protocol=protocol)

    assert validate_capability_manifest(updated) == []
    assert updated.protocol.collective_decision_policy.extensions["x-collective"] == {
        "memory": "external-runtime-owned"
    }


def test_collective_policy_rejects_unsupported_mode_thresholds_and_evaporation() -> (
    None
):
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    bad_policy = CollectiveDecisionPolicy(
        mode="unsupported",
        min_independent_scouts=0,
        quorum_threshold=0,
        pheromone_enabled=True,
        pheromone_evaporation_rate=1.5,
        fallback_candidate="candidate:safe_fallback",
    )
    protocol = replace(manifest.protocol, collective_decision_policy=bad_policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_mode_unsupported" in codes
    assert "collective_min_scouts_invalid" in codes
    assert "collective_quorum_threshold_invalid" in codes
    assert "collective_pheromone_evaporation_invalid" in codes


def test_collective_policy_rejects_invalid_pheromone_memory_fields() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    bad_policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_decay_model="adaptive",
        pheromone_min_strength=5,
        pheromone_max_strength=1,
        pheromone_positive_weight=-1,
        pheromone_negative_weight=-1,
        pheromone_cautionary_weight=-1,
        pheromone_novelty_weight=-1,
        pheromone_cautionary_override_threshold=-1,
        pheromone_per_source_cap=-1,
        pheromone_per_round_deposit_cap=-1,
        pheromone_min_source_diversity=0,
    )
    protocol = replace(manifest.protocol, collective_decision_policy=bad_policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_pheromone_decay_model_invalid" in codes
    assert "collective_pheromone_strength_bounds_invalid" in codes
    assert "collective_pheromone_weight_invalid" in codes
    assert "collective_pheromone_cautionary_threshold_invalid" in codes
    assert "collective_pheromone_cap_invalid" in codes
    assert "collective_pheromone_source_diversity_invalid" in codes


def test_protocol_accepts_explicit_pheromone_provenance_trace_policy_without_overconstraint() -> (
    None
):
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    explicit_policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_enabled=True,
        pheromone_require_provenance=False,
        pheromone_require_trace=False,
    )
    protocol = replace(manifest.protocol, collective_decision_policy=explicit_policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_pheromone_provenance_required" not in codes
    assert "collective_pheromone_trace_required" not in codes


def test_collective_policy_requires_declared_safe_fallback() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    bad_policy = replace(
        manifest.protocol.collective_decision_policy,
        fallback_candidate="candidate:alpha",
    )
    protocol = replace(manifest.protocol, collective_decision_policy=bad_policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_fallback_not_safe" in codes


def test_collective_policy_checks_required_swarm_trace_events() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        trace_policy=TracePolicy(
            required_events=["block", "commit", "recovery", "output"]
        ),
    )

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }
    messages = {
        item.message
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "swarm_trace_lineage_incomplete" in codes
    assert any("pheromone_score" in message for message in messages)
    assert any("pheromone_clip" in message for message in messages)
    assert any("pheromone_expire" in message for message in messages)


def test_quorum_collective_policy_does_not_require_swarm_trace_events() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    quorum_policy = CollectiveDecisionPolicy(
        mode="quorum",
        min_independent_scouts=1,
        quorum_threshold=1,
        fallback_candidate="candidate:safe_fallback",
    )
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=quorum_policy,
        trace_policy=TracePolicy(
            required_events=["block", "commit", "recovery", "output"]
        ),
    )

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert is_swarm_policy(quorum_policy) is False
    assert "swarm_trace_lineage_incomplete" not in codes


def test_collective_policy_can_default_to_quorum_fallback_candidate() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    defaulting_policy = replace(
        manifest.protocol.collective_decision_policy, fallback_candidate=""
    )
    protocol = replace(manifest.protocol, collective_decision_policy=defaulting_policy)

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))

    assert (
        collective_fallback_id(protocol)
        == manifest.protocol.quorum_policy.fallback_candidate
    )
    assert diagnostics == []


def test_hybrid_pheromone_manifest_loads_full_abi_fields() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = manifest.protocol.collective_decision_policy

    assert validate_capability_manifest(manifest) == []
    assert policy is not None
    assert has_hybrid_pheromone_features(policy) is True
    assert policy.pheromone_scored_subject_types == (
        "candidate",
        "route",
        "tool",
        "agent",
    )
    assert policy.pheromone_kind_profiles["alarm"].weight == 2
    assert policy.pheromone_kind_profiles["stale"].weight == 0
    assert policy.pheromone_response_model == "saturating"
    assert policy.pheromone_diffusion_enabled is True
    assert policy.pheromone_feedback_enabled is True
    assert policy.layer_coordination_enabled is True
    assert policy.layer_weight_bounds["learned"] == (0.0, 1.5)
    assert policy.policy_adjustment_bounds["pheromone_response_model"][
        "allowed_values"
    ] == (
        "linear",
        "saturating",
        "threshold",
        "competitive",
    )


def test_hybrid_policy_rejects_invalid_profiles_response_layers_and_adjustment_bounds() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    bad_policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_scored_subject_types=["unsupported"],
        pheromone_kind_profiles={
            "stale": PheromoneKindProfile(weight=1, scored_subject_types=["candidate"]),
            "positive": PheromoneKindProfile(
                weight=-1, evaporation_rate=2, ttl_steps=-1, response_model="adaptive"
            ),
        },
        pheromone_response_model="adaptive",
        pheromone_competition_mode="global",
        pheromone_activation_threshold=-1,
        pheromone_diffusion_attenuation=2,
        pheromone_diffusion_max_hops=-1,
        novelty_decay_rate=2,
        layer_min_provenance=0,
        layer_default_weights={"unknown": -1},
        layer_weight_bounds={"learned": (2, 1)},
        policy_adjustment_bounds={
            "pheromone_require_trace": [0, 1],
            "pheromone_evaporation_rate": [1, 0],
        },
    )
    protocol = replace(manifest.protocol, collective_decision_policy=bad_policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_pheromone_subject_type_invalid" in codes
    assert "collective_pheromone_kind_profile_invalid" in codes
    assert "collective_pheromone_stale_scores_invalid" in codes
    assert "collective_pheromone_response_model_invalid" in codes
    assert "collective_pheromone_competition_mode_invalid" in codes
    assert "collective_pheromone_threshold_invalid" in codes
    assert "collective_pheromone_diffusion_attenuation_invalid" in codes
    assert "collective_pheromone_diffusion_hops_invalid" in codes
    assert "collective_pheromone_novelty_decay_invalid" in codes
    assert "collective_layer_provenance_invalid" in codes
    assert "collective_layer_id_invalid" in codes
    assert "collective_layer_weight_invalid" in codes
    assert "collective_layer_bounds_invalid" in codes
    assert "collective_policy_adjustment_unsafe" in codes
    assert "collective_policy_adjustment_bounds_invalid" in codes


def test_direct_manifest_validation_rejects_empty_scored_subject_types() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_scored_subject_types=[],
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_pheromone_subject_types_empty" in codes


def test_hybrid_features_require_hybrid_mode_and_trace_lineage() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(manifest.protocol.collective_decision_policy, mode="ant_colony")
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=policy,
        trace_policy=TracePolicy(
            required_events=["block", "commit", "recovery", "output"]
        ),
    )

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))
    codes = {item.code for item in diagnostics}
    messages = {item.message for item in diagnostics}

    assert "collective_hybrid_mode_required" in codes
    assert "swarm_trace_lineage_incomplete" in codes
    assert any("pheromone_diffuse" in message for message in messages)
    assert any("coordination_resolve" in message for message in messages)


def test_hybrid_mode_cannot_downgrade_to_an_empty_swarm_profile() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = CollectiveDecisionPolicy(
        mode="hybrid",
        fallback_candidate="candidate:safe_fallback",
    )
    diagnostics = validate_capability_manifest(
        replace(
            manifest,
            protocol=replace(manifest.protocol, collective_decision_policy=policy),
        )
    )

    assert "collective_hybrid_declaration_incomplete" in {
        item.code for item in diagnostics
    }


def test_hybrid_mode_always_activates_hybrid_trace_profile() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    policy = replace(manifest.protocol.collective_decision_policy, mode="hybrid")
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))

    assert has_hybrid_pheromone_features(policy) is True
    assert "swarm_trace_lineage_incomplete" in {item.code for item in diagnostics}
    assert any("pheromone_diffuse" in item.message for item in diagnostics)


def test_hybrid_only_declarations_are_rejected_in_basic_swarm_mode() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_kind_profiles={"positive": PheromoneKindProfile()},
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert policy.mode == "bee_swarm"
    assert "collective_hybrid_mode_required" in codes


def test_enabled_hybrid_features_require_lineage_and_complete_diffusion_semantics() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_require_provenance=False,
        pheromone_require_trace=False,
        pheromone_diffusion_max_hops=0,
        pheromone_diffusion_attenuation=0,
    )
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=policy,
        evidence_policy=replace(
            manifest.protocol.evidence_policy, require_provenance=False
        ),
    )

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_hybrid_provenance_required" in codes
    assert "collective_hybrid_trace_required" in codes
    assert "collective_pheromone_diffusion_declaration_invalid" in codes


def test_layer_coordination_requires_all_declared_layer_bounds_and_safe_conflict_fallback() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        layer_weight_bounds={"learned": (0, 1)},
        layer_default_weights={"learned": 1},
        layer_confidence_thresholds={"learned": 0.5},
        layer_fallback_on_unresolved_conflict=False,
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))
    codes = {item.code for item in diagnostics}

    assert "collective_layer_coverage_incomplete" in codes
    assert "collective_layer_fallback_required" in codes


def test_policy_adjustment_allowlist_rejects_unknown_reactive_and_out_of_declared_layer_bounds() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        policy_adjustment_bounds={
            "manifest": [0, 1],
            "layer_reactive_weight": [0, 1],
            "layer_learned_weight": [0, 2],
            "pheromone_response_model": {"allowed_values": ["adaptive"]},
        },
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))
    codes = {item.code for item in diagnostics}

    assert "collective_policy_adjustment_unknown" in codes
    assert "collective_policy_adjustment_bounds_invalid" in codes


def test_protocol_policy_validation_rejects_direct_non_finite_numbers_and_unknown_kind_keys() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_max_strength=float("inf"),
        layer_default_weights={"learned": float("nan")},
        pheromone_kind_profiles={"custom": PheromoneKindProfile(weight=float("nan"))},
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_pheromone_strength_bounds_invalid" in codes
    assert "collective_layer_weight_invalid" in codes
    assert "collective_pheromone_kind_invalid" in codes
    assert "collective_pheromone_kind_profile_invalid" in codes


@pytest.mark.parametrize(
    ("updates", "expected_code"),
    [
        (
            {"pheromone_scored_subject_types": ["candidate", "evidence"]},
            "collective_pheromone_subject_type_invalid",
        ),
        (
            {
                "pheromone_kind_profiles": {
                    "positive": PheromoneKindProfile(
                        scored_subject_types=["evidence"],
                    )
                }
            },
            "collective_pheromone_kind_profile_invalid",
        ),
    ],
)
def test_protocol_rejects_evidence_pheromone_scoring_declarations(
    updates: dict[str, object],
    expected_code: str,
) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(manifest.protocol.collective_decision_policy, **updates)
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert expected_code in codes


@pytest.mark.parametrize(
    "field_name",
    [
        "pheromone_max_strength",
        "pheromone_per_source_cap",
        "pheromone_per_round_deposit_cap",
    ],
)
def test_hybrid_policy_requires_positive_memory_bounds(field_name: str) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(manifest.protocol.collective_decision_policy, **{field_name: 0.0})
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_hybrid_budget_inactive" in codes


def test_hybrid_minimum_strength_must_fit_effective_deposit_caps() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_min_strength=4.0,
        pheromone_per_source_cap=3.0,
        pheromone_per_round_deposit_cap=5.0,
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_hybrid_min_strength_unreachable" in codes


def test_threshold_activation_must_be_reachable_by_declared_kind_profiles() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_activation_threshold=1000.0,
    )
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_pheromone_activation_unreachable" in codes


@pytest.mark.parametrize(
    "field_name", ["exploration_floor", "pheromone_exploration_floor"]
)
def test_exploration_floors_are_absolutely_bounded(field_name: str) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(manifest.protocol.collective_decision_policy, **{field_name: 1.01})
    protocol = replace(manifest.protocol, collective_decision_policy=policy)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert "collective_pheromone_threshold_invalid" in codes


def test_protocol_policy_and_kind_profile_take_defensive_snapshots() -> None:
    kind_subjects = ["candidate"]
    profile_values = ["profile:original"]
    profile_tags = {"runtime"}
    profile_extensions = {
        "x-profile": {
            "owner": "runtime",
            "record": _MutableExtensionRecord("profile", profile_values),
            "tags": profile_tags,
        }
    }
    profile = PheromoneKindProfile(
        scored_subject_types=kind_subjects,
        extensions=profile_extensions,
    )
    scored_subjects = ["candidate"]
    profiles = {"positive": profile}
    layer_bounds = {"learned": (0.0, 1.0)}
    adjustment_bounds = {"layer_learned_weight": [0.0, 1.0]}
    policy_values = ["policy:original"]
    extensions = {
        "x-policy": {
            "owner": "runtime",
            "record": _MutableExtensionRecord("policy", policy_values),
        }
    }
    policy = CollectiveDecisionPolicy(
        pheromone_scored_subject_types=scored_subjects,
        pheromone_kind_profiles=profiles,
        layer_weight_bounds=layer_bounds,
        policy_adjustment_bounds=adjustment_bounds,
        extensions=extensions,
    )

    kind_subjects.append("route")
    profile_extensions["x-profile"]["owner"] = "mutated"
    profile_values.append("profile:mutated")
    profile_tags.add("mutated")
    scored_subjects.append("route")
    profiles.clear()
    layer_bounds["learned"] = (0.0, 9.0)
    adjustment_bounds["layer_learned_weight"][1] = 9.0
    extensions["x-policy"]["owner"] = "mutated"
    policy_values.append("policy:mutated")

    assert profile.scored_subject_types == ("candidate",)
    assert profile.extensions["x-profile"]["owner"] == "runtime"
    assert profile.extensions["x-profile"]["record"]["values"] == ("profile:original",)
    assert profile.extensions["x-profile"]["tags"] == frozenset({"runtime"})
    assert policy.pheromone_scored_subject_types == ("candidate",)
    assert list(policy.pheromone_kind_profiles) == ["positive"]
    assert type(policy.pheromone_kind_profiles["positive"]) is PheromoneKindProfile
    assert policy.layer_weight_bounds["learned"] == (0.0, 1.0)
    assert policy.policy_adjustment_bounds["layer_learned_weight"] == (0.0, 1.0)
    assert policy.extensions["x-policy"]["owner"] == "runtime"
    assert policy.extensions["x-policy"]["record"]["values"] == ("policy:original",)


def test_governance_kind_profile_compatibility_export_uses_protocol_canonical_type() -> (
    None
):
    from pheroos.governance import PheromoneKindProfile as GovernanceKindProfile

    assert GovernanceKindProfile is PheromoneKindProfile
