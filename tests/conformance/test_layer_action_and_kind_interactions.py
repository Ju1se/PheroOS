from dataclasses import replace

from pheroos.conformance.checks import layer_coordination_policy, pheromone_kind_profile
from pheroos.governance.layer_coordination import SUPPORTED_LAYER_ACTIONS
from pheroos.protocol import load_capability_manifest


def test_layer_conformance_exercises_every_builtin_action(monkeypatch) -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
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


def test_layer_action_proof_derives_manifest_thresholds_and_provenance() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
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


def test_kind_conformance_exercises_priority_and_suppression_interactions(
    monkeypatch,
) -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    profiles = {
        kind: replace(
            profile,
            priority=index,
            can_suppress_positive=(kind == "cautionary"),
        )
        for index, (kind, profile) in enumerate(
            reversed(sorted(policy.pheromone_kind_profiles.items()))
        )
    }
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(
                policy,
                pheromone_kind_profiles=profiles,
            ),
        ),
    )
    priority_batches: list[set[str]] = []
    score_batches: list[set[str]] = []
    deposit = pheromone_kind_profile.deposit_pheromone_trails
    score = pheromone_kind_profile.score_pheromone_trails_result

    def tracking_deposit(trails, *args, **kwargs):
        priority_batches.append({trail.kind for trail in trails})
        return deposit(trails, *args, **kwargs)

    def tracking_score(*, trails, **kwargs):
        score_batches.append({trail.kind for trail in trails})
        return score(trails=trails, **kwargs)

    monkeypatch.setattr(
        pheromone_kind_profile,
        "deposit_pheromone_trails",
        tracking_deposit,
    )
    monkeypatch.setattr(
        pheromone_kind_profile,
        "score_pheromone_trails_result",
        tracking_score,
    )

    result = pheromone_kind_profile.check(manifest)

    declared_kinds = set(profiles)
    assert result.ok is True, result.detail
    assert any(batch == declared_kinds for batch in priority_batches)
    assert {"positive", "cautionary"} in score_batches
    assert {"positive", "alarm"} in score_batches
