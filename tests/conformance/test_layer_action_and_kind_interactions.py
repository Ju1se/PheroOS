from dataclasses import replace
from pathlib import Path

from pheroos.conformance.checks import (
    layer_coordination_policy,
    policy_adjustment_bounds,
)
from pheroos.governance.layer_coordination import (
    SUPPORTED_LAYER_ACTIONS,
    LayerCoordinationState,
    layer_coordination_policy_from_collective,
)
from pheroos.protocol import load_capability_manifest


ROOT = Path(__file__).resolve().parents[2]


def test_layer_conformance_exercises_every_builtin_action(monkeypatch) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    observed: set[str] = set()
    evaluate = layer_coordination_policy.evaluate_layer_coordination

    def tracking_evaluate(**kwargs):
        observed.update(proposal.action for proposal in kwargs["proposals"])
        return evaluate(**kwargs)

    monkeypatch.setattr(
        layer_coordination_policy,
        "evaluate_layer_coordination",
        tracking_evaluate,
    )

    result = layer_coordination_policy.check(manifest)

    assert result.ok is True, result.detail
    assert set(layer_coordination_policy.BUILTIN_ACTION_EFFECTS) == set(
        SUPPORTED_LAYER_ACTIONS
    )
    assert set(SUPPORTED_LAYER_ACTIONS) <= observed


def _manifest_with_policy(manifest, **updates):
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    return replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )


def test_policy_adjustment_checker_exercises_every_owned_effective_field() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = hybrid.protocol.collective_decision_policy
    assert policy is not None
    bounds = {
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
        "layer_evolutionary_weight": policy.layer_weight_bounds["evolutionary"],
        "layer_metacognitive_weight": policy.layer_weight_bounds["metacognitive"],
    }
    all_bounds = _manifest_with_policy(
        hybrid,
        policy_adjustment_bounds=bounds,
    )
    result = policy_adjustment_bounds.check(all_bounds)
    assert result.ok is True, result.detail

    assert policy_adjustment_bounds.accepted_value_for([1.0, 2.0]) == 1.0
    assert policy_adjustment_bounds.accepted_value_for((1.0, 2.0)) == 1.0
    assert (
        policy_adjustment_bounds.accepted_value_for(
            {"allowed_values": ["linear", "threshold"]}
        )
        == "linear"
    )
    assert policy_adjustment_bounds.accepted_value_for({"min": 0.25}) == 0.25
    assert policy_adjustment_bounds.accepted_value_for(object()) == 0
    assert policy_adjustment_bounds.rejected_value_for([1.0, 2.0]) == 3.0
    assert (
        policy_adjustment_bounds.rejected_value_for({"allowed_values": ["linear"]})
        == "unsupported"
    )
    assert policy_adjustment_bounds.rejected_value_for({"max": 2.0}) == 3.0
    assert type(policy_adjustment_bounds.rejected_value_for(object())) is object

    effective = all_bounds.protocol.collective_decision_policy
    assert effective is not None
    expected_values = {
        "pheromone_evaporation_rate": effective.pheromone_evaporation_rate,
        "pheromone_response_model": effective.pheromone_response_model,
        "pheromone_exploration_floor": effective.pheromone_exploration_floor,
        "pheromone_cautionary_override_threshold": (
            effective.pheromone_cautionary_override_threshold
        ),
        "layer_emergency_override_threshold": (
            effective.layer_emergency_override_threshold
        ),
        "pheromone_positive_weight": effective.pheromone_positive_weight,
        "pheromone_negative_weight": effective.pheromone_negative_weight,
        "pheromone_cautionary_weight": effective.pheromone_cautionary_weight,
        "pheromone_alarm_weight": effective.pheromone_kind_profiles["alarm"].weight,
        "pheromone_novelty_weight": effective.pheromone_novelty_weight,
        "layer_learned_weight": effective.layer_default_weights["learned"],
        "layer_evolutionary_weight": effective.layer_default_weights["evolutionary"],
        "layer_metacognitive_weight": effective.layer_default_weights["metacognitive"],
    }
    normalized_effective = replace(
        effective,
        pheromone_kind_profiles={
            kind: replace(
                profile,
                evaporation_rate=effective.pheromone_evaporation_rate,
                response_model=effective.pheromone_response_model,
                weight=(
                    effective.pheromone_cautionary_weight
                    if kind == "cautionary"
                    else profile.weight
                ),
            )
            for kind, profile in effective.pheromone_kind_profiles.items()
        },
    )
    assert all(
        policy_adjustment_bounds.effective_adjustment_applied(
            normalized_effective,
            key,
            value,
        )
        for key, value in expected_values.items()
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            effective,
            "unsupported",
            0,
        )
        is False
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            effective,
            "pheromone_evaporation_rate",
            -1.0,
        )
        is False
    )
    without_positive = replace(
        effective,
        pheromone_kind_profiles={
            kind: profile
            for kind, profile in effective.pheromone_kind_profiles.items()
            if kind != "positive"
        },
    )
    assert (
        policy_adjustment_bounds.effective_adjustment_applied(
            without_positive,
            "pheromone_positive_weight",
            effective.pheromone_positive_weight,
        )
        is False
    )

    undeclared = policy_adjustment_bounds.check(
        _manifest_with_policy(hybrid, policy_adjustment_bounds={})
    )
    assert undeclared.ok is True
    unsafe = policy_adjustment_bounds.check(
        _manifest_with_policy(
            hybrid,
            policy_adjustment_bounds={"fallback_candidate": (0.0, 1.0)},
        )
    )
    assert unsafe.ok is False
    assert "unsafe:fallback_candidate" in unsafe.detail
    assert "bounded_rejected:fallback_candidate" in unsafe.detail

    malformed = policy_adjustment_bounds._bounded_adjustment_problems(
        effective,
        "unsupported",
        object(),
    )
    assert "bounded_rejected:unsupported" in malformed


def test_layer_coordination_helpers_report_malformed_state_and_policy() -> None:
    hybrid = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = hybrid.protocol.collective_decision_policy
    assert collective is not None
    policy = layer_coordination_policy_from_collective(collective)
    candidates = layer_coordination_policy.candidate_set(hybrid)
    target = layer_coordination_policy.active_target(hybrid)
    primary = layer_coordination_policy.exercise_candidate_id(hybrid)
    assert primary is not None
    fallback_id = hybrid.protocol.quorum_policy.fallback_candidate

    proposal = layer_coordination_policy.action_proposal(
        "support",
        layer_id="learned",
        candidate_id=primary,
        target=target,
        policy=policy,
    )
    bad_positive = LayerCoordinationState(
        allocated_weights={"learned": 1.0},
        score_breakdown={primary: {"layer_learned": -1.0}},
    )
    assert layer_coordination_policy._action_state_problems(
        action="support",
        layer_id="learned",
        effect="wrong-effect",
        expected_effect="candidate_preference",
        expected_sign="positive",
        primary=primary,
        item=proposal,
        state=bad_positive,
    ) == [
        "action_effect:support",
        "action_lineage:support",
        "action_score:support",
    ]

    bad_negative = LayerCoordinationState(
        allocated_weights={"learned": 1.0},
        score_breakdown={primary: {"layer_learned": 1.0}},
        trace_lineage=[proposal.trace_event_id],
        action_effects={proposal.trace_event_id: "candidate_risk_pressure"},
    )
    assert layer_coordination_policy._action_state_problems(
        action="risk",
        layer_id="learned",
        effect="candidate_risk_pressure",
        expected_effect="candidate_risk_pressure",
        expected_sign="negative",
        primary=primary,
        item=proposal,
        state=bad_negative,
    ) == ["action_score:risk"]

    bad_zero = LayerCoordinationState(
        allocated_weights={"learned": 1.0},
        score_breakdown={primary: {"layer_learned": 1.0}},
        trace_lineage=[proposal.trace_event_id],
        action_effects={proposal.trace_event_id: "scouting_required"},
    )
    assert layer_coordination_policy._action_state_problems(
        action="request_scouting",
        layer_id="learned",
        effect="scouting_required",
        expected_effect="scouting_required",
        expected_sign="zero",
        primary=primary,
        item=proposal,
        state=bad_zero,
    ) == ["action_score:request_scouting"]

    interaction_expectations = {
        "request_scouting": "action_conflict:request_scouting",
        "fallback_pressure": "action_conflict:fallback_pressure",
        "alarm": "action_conflict:alarm",
        "cautionary": "action_conflict:cautionary",
        "confirm_trace_coverage": ("action_confirmation:confirm_trace_coverage"),
    }
    for action, marker in interaction_expectations.items():
        item = layer_coordination_policy.action_proposal(
            action,
            layer_id=(
                "metacognitive" if action == "confirm_trace_coverage" else "reactive"
            ),
            candidate_id=primary,
            target=target,
            policy=policy,
        )
        problems = layer_coordination_policy._action_interaction_problems(
            action=action,
            primary=primary,
            item=item,
            state=LayerCoordinationState(),
            candidates=candidates,
            target=target,
            policy=policy,
        )
        assert marker in problems

    proposed = layer_coordination_policy.action_proposal(
        "propose_pheromone",
        layer_id="evolutionary",
        candidate_id=primary,
        target=target,
        policy=policy,
        collective_policy=None,
    )
    assert proposed.proposed_pheromone_kind == "positive"
    assert proposed.proposed_strength == 1.0
    assert (
        layer_coordination_policy._action_interaction_problems(
            action="propose_pheromone",
            primary=primary,
            item=proposed,
            state=LayerCoordinationState(),
            candidates=candidates,
            target=target,
            policy=policy,
        )
        == []
    )

    no_secondary = layer_coordination_policy.coordination_interaction_problems(
        policy=policy,
        candidates=candidates,
        target=target,
        primary=primary,
        secondary=None,
        fallback_id=fallback_id,
    )
    assert no_secondary == []

    invalid_declared = replace(
        collective,
        layer_min_provenance=0,
        layer_conflict_threshold=-1.0,
        layer_emergency_override_threshold=-1.0,
        layer_default_weights={"unknown": -1.0},
        layer_weight_bounds={"unknown": (-1.0, -2.0)},
    )
    assert set(
        layer_coordination_policy.declared_policy_problems(invalid_declared)
    ) == {
        "bounds",
        "layer_id",
        "min_layer_provenance",
        "thresholds",
        "weights",
    }

    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert layer_coordination_policy.check(toy).ok is True
    assert layer_coordination_policy.layer_coordination_problems(toy) == [
        "collective_policy"
    ]
    without_candidates = replace(
        hybrid,
        protocol=replace(hybrid.protocol, candidates=()),
    )
    assert layer_coordination_policy.layer_coordination_problems(
        without_candidates
    ) == ["active_target_candidates"]
    malformed = layer_coordination_policy.check(
        _manifest_with_policy(hybrid, layer_min_provenance="invalid")
    )
    assert malformed.ok is False
    assert malformed.detail.startswith("exercise:TypeError")


def test_layer_action_proof_derives_manifest_thresholds_and_provenance() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    policy = replace(
        policy,
        layer_confidence_thresholds={
            layer_id: 1.0
            for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
        },
        layer_emergency_override_threshold=1.0,
        layer_min_provenance=4,
    )
    manifest = replace(
        manifest,
        protocol=replace(manifest.protocol, collective_decision_policy=policy),
    )

    result = layer_coordination_policy.check(manifest)

    assert result.ok is True, result.detail
