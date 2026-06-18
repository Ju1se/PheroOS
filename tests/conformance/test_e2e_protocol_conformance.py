import json
from pathlib import Path

from pheroos.conformance import run_conformance, validate_manifest


def test_e2e_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/e2e-protocol/capability.json")
    conformance = run_conformance("examples/e2e-protocol")

    assert validation.ok is True
    assert conformance.ok is True
    assert "extension_contract" in {check.name for check in conformance.checks}


def test_secret_like_manifest_fields_fail_validation(tmp_path: Path) -> None:
    payload = json.loads(Path("examples/e2e-protocol/capability.json").read_text())
    payload["protocol"]["extensions"] = {"x-runtime": {"password": "not-allowed"}}
    path = tmp_path / "capability.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    validation = validate_manifest(path)

    assert validation.ok is False
    assert "secret-like manifest fields" in validation.checks[0].detail
