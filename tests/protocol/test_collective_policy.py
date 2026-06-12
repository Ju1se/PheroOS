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

    assert "swarm_trace_lineage_incomplete" in codes


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
