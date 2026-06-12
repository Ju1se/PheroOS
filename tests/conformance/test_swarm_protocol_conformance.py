from dataclasses import replace

from pheroos.conformance import run_conformance, validate_manifest
from pheroos.conformance.checks import swarm_trace_contract
from pheroos.protocol import CollectiveDecisionPolicy, TracePolicy, load_capability_manifest


def test_swarm_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/swarm-protocol/capability.json")
    conformance = run_conformance("examples/swarm-protocol")

    assert validation.ok is True
    assert conformance.ok is True
    assert {check.name for check in conformance.checks} >= {
        "collective_policy",
        "safe_fallback_collective",
        "pheromone_policy",
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
