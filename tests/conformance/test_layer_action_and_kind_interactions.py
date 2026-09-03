from dataclasses import replace

from pheroos.conformance.checks import layer_coordination_policy
from pheroos.governance.layer_coordination import SUPPORTED_LAYER_ACTIONS
from pheroos.protocol import load_capability_manifest


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
