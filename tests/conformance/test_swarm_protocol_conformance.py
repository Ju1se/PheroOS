from pheroos.conformance import run_conformance, validate_manifest


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
