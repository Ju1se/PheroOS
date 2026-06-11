from pheroos.conformance import run_conformance, validate_manifest


def test_toy_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/toy-protocol/capability.json")
    conformance = run_conformance("examples/toy-protocol")

    assert validation.ok is True
    assert conformance.ok is True
    assert {check.name for check in conformance.checks} >= {
        "manifest_schema",
        "candidate_declaration",
        "quorum_policy",
        "recovery_policy",
        "output_contract",
        "trace_contract",
        "driver_contract",
        "domain_neutrality_public_core",
        "kernel_import_boundary",
    }
