from dataclasses import replace

from pheroos.conformance import run_conformance, validate_manifest
from pheroos.conformance.checks import pheromone_behavior, pheromone_policy, swarm_trace_contract
from pheroos.protocol import CollectiveDecisionPolicy, TracePolicy, load_capability_manifest


def test_swarm_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/swarm-protocol/capability.json")
    conformance = run_conformance("examples/swarm-protocol")

    assert validation.ok is True
    assert conformance.ok is True
    assert conformance.profile == "pheroos-swarm-v1"
    assert {check.name for check in conformance.checks} >= {
        "collective_policy",
        "safe_fallback_collective",
        "pheromone_behavior",
        "pheromone_policy",
        "kernel_contract",
        "swarm_trace_contract",
    }


def test_swarm_trace_contract_skips_quorum_collective_mode() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=CollectiveDecisionPolicy(
            mode="quorum",
            fallback_candidate="candidate:safe_fallback",
        ),
        trace_policy=TracePolicy(required_events=["block", "commit", "recovery", "output"]),
    )

    result = swarm_trace_contract.check(replace(manifest, protocol=protocol))

    assert result.ok is True


def test_pheromone_policy_conformance_reports_stigmergic_memory_invariants() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=replace(
            manifest.protocol.collective_decision_policy,
            pheromone_decay_model="adaptive",
            pheromone_min_strength=4,
            pheromone_max_strength=1,
            pheromone_positive_weight=-1,
            pheromone_novelty_weight=-1,
            pheromone_cautionary_override_threshold=-1,
            pheromone_per_source_cap=-1,
            pheromone_per_round_deposit_cap=-1,
            pheromone_min_source_diversity=0,
            pheromone_require_provenance=False,
            pheromone_require_trace=False,
        ),
    )

    result = pheromone_policy.check(replace(manifest, protocol=protocol))

    assert result.ok is False
    assert "decay_model" in result.detail
    assert "strength_bounds" in result.detail
    assert "weights" in result.detail
    assert "cautionary_threshold" in result.detail
    assert "caps" in result.detail
    assert "min_source_diversity" in result.detail


def test_pheromone_behavior_conformance_proves_runtime_boundaries() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")

    result = pheromone_behavior.check(manifest)

    assert result.ok is True
    assert result.detail == ""


def test_pheromone_policy_conformance_does_not_overconstrain_trace_policy_flags() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=replace(
            manifest.protocol.collective_decision_policy,
            pheromone_require_provenance=False,
            pheromone_require_trace=False,
        ),
    )

    result = pheromone_policy.check(replace(manifest, protocol=protocol))

    assert result.ok is True
