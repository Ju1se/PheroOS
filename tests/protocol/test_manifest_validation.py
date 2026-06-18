import json
from dataclasses import replace
from pathlib import Path

import pytest

from pheroos.protocol import DriverSpec, load_capability_manifest, validate_capability_manifest
from pheroos.protocol.manifest import capability_manifest_from_dict


def test_toy_manifest_validates_without_errors() -> None:
    manifest = load_capability_manifest("examples/toy-protocol/capability.json")

    diagnostics = validate_capability_manifest(manifest)

    assert diagnostics == []


def test_manifest_loader_preserves_namespaced_extension_metadata() -> None:
    payload = json.loads(Path("examples/e2e-protocol/capability.json").read_text())
    payload["extensions"] = {"x-runtime": {"owner": "external"}}
    payload["x-acme.runtime"] = {"adapter": "outside-core"}
    payload["drivers"][0]["extensions"] = {"x-driver": {"adapter": "external"}}
    payload["drivers"][0]["x-acme.driver"] = {"kind": "test-double"}
    payload["protocol"]["extensions"] = {"x-protocol": {"mode": "integration"}}
    payload["protocol"]["targets"][0]["x-target"] = {"scope": "declared"}
    payload["protocol"]["candidates"][0]["extensions"] = {"x-candidate": {"rank": 1}}
    payload["protocol"]["signals"][0]["extensions"] = {"x-signal": {"source": "agent"}}

    manifest = capability_manifest_from_dict(payload)

    assert manifest.extensions["x-runtime"] == {"owner": "external"}
    assert manifest.extensions["x-acme.runtime"] == {"adapter": "outside-core"}
    assert manifest.protocol.extensions["x-protocol"] == {"mode": "integration"}
    assert manifest.protocol.targets[0].extensions["x-target"] == {"scope": "declared"}
    assert manifest.protocol.candidates[0].extensions["x-candidate"] == {"rank": 1}
    assert manifest.protocol.signals[0].extensions["x-signal"] == {"source": "agent"}
    assert isinstance(manifest.drivers[0], DriverSpec)
    assert manifest.drivers[0].extensions["x-driver"] == {"adapter": "external"}
    assert manifest.drivers[0].extensions["x-acme.driver"] == {"kind": "test-double"}
    assert validate_capability_manifest(manifest) == []


def test_manifest_loader_preserves_collective_policy_extensions() -> None:
    payload = json.loads(Path("examples/swarm-protocol/capability.json").read_text())
    payload["protocol"]["collective_decision_policy"]["extensions"] = {
        "x-collective": {"memory": "external-runtime-owned"}
    }
    payload["protocol"]["collective_decision_policy"]["x-acme.policy"] = {"mode": "observed"}

    manifest = capability_manifest_from_dict(payload)

    assert manifest.protocol.collective_decision_policy is not None
    assert manifest.protocol.collective_decision_policy.extensions["x-collective"] == {
        "memory": "external-runtime-owned"
    }
    assert manifest.protocol.collective_decision_policy.extensions["x-acme.policy"] == {"mode": "observed"}


def test_e2e_manifest_loads_provider_neutral_driver_specs() -> None:
    manifest = load_capability_manifest("examples/e2e-protocol/capability.json")
    driver = manifest.drivers[0]

    assert isinstance(driver, DriverSpec)
    assert driver.id == "driver:toy-evidence"
    assert driver.kind == "tool"
    assert driver.permissions == ["driver:invoke"]
    assert driver.config_ref == ""
    assert driver.extensions == {}


def test_manifest_loader_rejects_secret_like_fields_before_dropping_unknowns() -> None:
    payload = json.loads(Path("examples/toy-protocol/capability.json").read_text())
    payload["api_key"] = "not-allowed"

    with pytest.raises(ValueError, match="secret-like manifest fields"):
        capability_manifest_from_dict(payload)


def test_protocol_validation_reports_secret_like_extension_fields() -> None:
    manifest = load_capability_manifest("examples/toy-protocol/capability.json")
    bad_manifest = replace(manifest, extensions={"x-runtime": {"token": "not-allowed"}})

    diagnostics = validate_capability_manifest(bad_manifest)

    assert {item.code for item in diagnostics} == {"secret_like_manifest_field"}
    assert diagnostics[0].path == "extensions.x-runtime.token"
