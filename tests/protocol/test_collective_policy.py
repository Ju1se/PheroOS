from dataclasses import replace

from pheroos.protocol import (
    CollectiveDecisionPolicy,
    TracePolicy,
    collective_fallback_id,
    is_swarm_policy,
    load_capability_manifest,
    validate_capability_manifest,
)


def test_swarm_manifest_validates_without_errors() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")

    assert validate_capability_manifest(manifest) == []
    assert manifest.protocol.collective_decision_policy is not None
    assert manifest.protocol.collective_decision_policy.pheromone_decay_model == "exponential"
    assert manifest.protocol.collective_decision_policy.pheromone_novelty_weight == 0.5
    assert manifest.protocol.collective_decision_policy.pheromone_per_source_cap == 3
    assert manifest.protocol.collective_decision_policy.pheromone_per_round_deposit_cap == 5
    assert manifest.protocol.collective_decision_policy.pheromone_min_source_diversity == 1
    assert manifest.protocol.collective_decision_policy.pheromone_require_provenance is True
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


def test_collective_policy_rejects_unsupported_mode_thresholds_and_evaporation() -> None:
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

    codes = {item.code for item in validate_capability_manifest(replace(manifest, protocol=protocol))}

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

    codes = {item.code for item in validate_capability_manifest(replace(manifest, protocol=protocol))}

    assert "collective_pheromone_decay_model_invalid" in codes
    assert "collective_pheromone_strength_bounds_invalid" in codes
    assert "collective_pheromone_weight_invalid" in codes
    assert "collective_pheromone_cautionary_threshold_invalid" in codes
    assert "collective_pheromone_cap_invalid" in codes
    assert "collective_pheromone_source_diversity_invalid" in codes


def test_protocol_accepts_explicit_pheromone_provenance_trace_policy_without_overconstraint() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    explicit_policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_enabled=True,
        pheromone_require_provenance=False,
        pheromone_require_trace=False,
    )
    protocol = replace(manifest.protocol, collective_decision_policy=explicit_policy)

    codes = {item.code for item in validate_capability_manifest(replace(manifest, protocol=protocol))}

    assert "collective_pheromone_provenance_required" not in codes
    assert "collective_pheromone_trace_required" not in codes


def test_collective_policy_requires_declared_safe_fallback() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    bad_policy = replace(
        manifest.protocol.collective_decision_policy,
        fallback_candidate="candidate:alpha",
    )
    protocol = replace(manifest.protocol, collective_decision_policy=bad_policy)

    codes = {item.code for item in validate_capability_manifest(replace(manifest, protocol=protocol))}

    assert "collective_fallback_not_safe" in codes


def test_collective_policy_checks_required_swarm_trace_events() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        trace_policy=TracePolicy(required_events=["block", "commit", "recovery", "output"]),
    )

    codes = {item.code for item in validate_capability_manifest(replace(manifest, protocol=protocol))}
    messages = {item.message for item in validate_capability_manifest(replace(manifest, protocol=protocol))}

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
        trace_policy=TracePolicy(required_events=["block", "commit", "recovery", "output"]),
    )

    codes = {item.code for item in validate_capability_manifest(replace(manifest, protocol=protocol))}

    assert is_swarm_policy(quorum_policy) is False
    assert "swarm_trace_lineage_incomplete" not in codes


def test_collective_policy_can_default_to_quorum_fallback_candidate() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    defaulting_policy = replace(manifest.protocol.collective_decision_policy, fallback_candidate="")
    protocol = replace(manifest.protocol, collective_decision_policy=defaulting_policy)

    diagnostics = validate_capability_manifest(replace(manifest, protocol=protocol))

    assert collective_fallback_id(protocol) == manifest.protocol.quorum_policy.fallback_candidate
    assert diagnostics == []
