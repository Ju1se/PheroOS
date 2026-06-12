from pheroos.conformance import run_conformance, validate_manifest


def test_e2e_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/e2e-protocol/capability.json")
    conformance = run_conformance("examples/e2e-protocol")

    assert validation.ok is True
    assert conformance.ok is True
