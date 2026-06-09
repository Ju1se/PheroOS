from __future__ import annotations

import json

import pytest

from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.capability_manifest_security import compute_capability_checksum


def write_manifest(root, folder: str, payload: dict) -> None:
    capability_dir = root / folder
    capability_dir.mkdir(parents=True)
    (capability_dir / "capability.json").write_text(json.dumps(payload), encoding="utf-8")


def manifest_payload(capability_id: str = "demo") -> dict:
    return {
        "id": capability_id,
        "name": "Demo Capability",
        "version": "0.1.0",
        "description": "A low-risk test capability.",
        "capability_types": ["demo_type"],
        "permissions": ["data:read"],
        "risk_level": "low",
    }


def test_capability_registry_loads_valid_manifest(tmp_path) -> None:
    payload = {
        **manifest_payload("demo-capability"),
        "required_connections": ["model_provider"],
        "agents_path": "agents",
        "entrypoints": {"workflow": "demo/workflow.py:build"},
        "swarm": {"required_protocols": ["data_gate"], "allowed_signal_types": ["risk"]},
        "ui": {"accent": "green"},
    }
    write_manifest(tmp_path, "demo", payload)

    catalog = CapabilityRegistry(tmp_path).catalog()

    assert catalog["diagnostics"] == []
    assert catalog["capabilities"][0]["id"] == "demo-capability"
    assert catalog["capabilities"][0]["capability_types"] == ["demo_type"]
    assert catalog["capabilities"][0]["required_connections"] == ["model_provider"]
    assert catalog["capabilities"][0]["agents_path"] == "agents"
    assert catalog["capabilities"][0]["entrypoints"]["workflow"] == "demo/workflow.py:build"
    assert catalog["capabilities"][0]["swarm"]["required_protocols"] == ["data_gate"]
    assert catalog["capabilities"][0]["ui"]["accent"] == "green"
    assert catalog["capabilities"][0]["trust_level"] == "first_party_reviewed"
    assert catalog["capabilities"][0]["sandbox"]["secrets"] == "no_direct_access"
    assert catalog["capabilities"][0]["sandbox"]["model_calls"] == "gateway_only"
    assert catalog["capabilities"][0]["security_diagnostics"]["status"] == "ok"


def test_capability_registry_skips_invalid_manifest_with_diagnostic(tmp_path) -> None:
    write_manifest(tmp_path, "valid", manifest_payload("valid-capability"))
    invalid_dir = tmp_path / "invalid"
    invalid_dir.mkdir()
    (invalid_dir / "capability.json").write_text('{"id": "broken"}', encoding="utf-8")

    catalog = CapabilityRegistry(tmp_path).catalog()

    assert [item["id"] for item in catalog["capabilities"]] == ["valid-capability"]
    assert catalog["diagnostics"][0]["status"] == "invalid"
    assert "missing required fields" in catalog["diagnostics"][0]["error"]


def test_capability_registry_rejects_duplicate_ids(tmp_path) -> None:
    write_manifest(tmp_path, "one", manifest_payload("duplicate"))
    write_manifest(tmp_path, "two", manifest_payload("duplicate"))

    with pytest.raises(ValueError, match="duplicate capability id"):
        CapabilityRegistry(tmp_path).load()


def test_capability_registry_reports_unknown_permissions(tmp_path) -> None:
    write_manifest(
        tmp_path,
        "demo",
        {
            **manifest_payload("demo-capability"),
            "permissions": ["data:read", "moon:launch"],
        },
    )

    catalog = CapabilityRegistry(tmp_path).catalog()

    diagnostics = catalog["capabilities"][0]["permission_diagnostics"]
    assert diagnostics["status"] == "warning"
    assert diagnostics["unknown_permissions"] == ["moon:launch"]


def test_capability_registry_reports_security_policy_violations(tmp_path) -> None:
    write_manifest(
        tmp_path,
        "unsafe",
        {
            **manifest_payload("unsafe-capability"),
            "trust_level": "third_party_untrusted",
            "sandbox": {
                "network": "arbitrary",
                "filesystem": "workspace_write",
                "secrets": "direct_access",
                "model_calls": "direct_provider",
                "tools": "direct",
            },
            "allowed_imports": ["requests", "subprocess"],
            "swarm": {"allowed_signal_types": ["stop_signal"]},
        },
    )

    catalog = CapabilityRegistry(tmp_path).catalog()
    security = catalog["capabilities"][0]["security_diagnostics"]
    codes = {item["code"] for item in security["findings"]}

    assert security["status"] == "blocked"
    assert "secret_access_policy_violation" in codes
    assert "model_gateway_bypass" in codes
    assert "tool_registry_bypass" in codes
    assert "untrusted_arbitrary_network" in codes
    assert "untrusted_filesystem_write" in codes
    assert "untrusted_blocking_signal" in codes
    assert "untrusted_unsigned_capability" in codes
    assert "dangerous_allowed_import" in codes


def test_capability_checksum_detects_manifest_change(tmp_path) -> None:
    write_manifest(tmp_path, "demo", manifest_payload("demo-capability"))
    capability_dir = tmp_path / "demo"
    first = compute_capability_checksum(capability_dir)

    (capability_dir / "agents").mkdir()
    (capability_dir / "agents" / "demo.json").write_text('{"key":"demo"}', encoding="utf-8")
    second = compute_capability_checksum(capability_dir)

    assert first is not None
    assert second is not None
    assert first != second


def test_capability_registry_can_list_by_type_and_required_connections(tmp_path) -> None:
    write_manifest(
        tmp_path,
        "demo",
        {
            **manifest_payload("demo-capability"),
            "capability_types": ["investment.research", "valuation"],
            "required_connections": ["wrds", "model_provider"],
        },
    )
    registry = CapabilityRegistry(tmp_path)

    assert [item.id for item in registry.list_by_type("valuation")] == ["demo-capability"]
    assert registry.missing_required_connections(
        capability_id="demo-capability",
        active_connection_keys={"model_provider"},
    ) == ["wrds"]


def test_built_in_roadmap_capabilities_load_with_entrypoints() -> None:
    catalog = CapabilityRegistry().catalog()
    by_id = {item["id"]: item for item in catalog["capabilities"]}

    assert catalog["diagnostics"] == []
    assert {"code-development", "compliance-workflow", "evidence-research"} <= set(by_id)
    assert by_id["code-development"]["entrypoints"]["workflow"] == "workflow.py:build_workflow_descriptor"
    assert by_id["compliance-workflow"]["entrypoints"]["data_contract"] == (
        "policy_contract.py:build_policy_contract_descriptor"
    )
    assert by_id["evidence-research"]["entrypoints"]["evidence_adapter"] == (
        "evidence_adapter.py:build_evidence_adapter_descriptor"
    )
    assert by_id["code-development"]["permission_diagnostics"]["status"] == "ok"
    assert by_id["compliance-workflow"]["security_diagnostics"]["status"] == "ok"
    assert by_id["evidence-research"]["security_diagnostics"]["status"] == "ok"


def test_capability_state_store_enable_disable_and_reenable(tmp_path) -> None:
    store = CapabilityStateStore(tmp_path / "state.json")

    store.enable(capability_id="demo", tenant_id="tenant-a", permission_grants=["data:read"])
    assert store.enabled_ids(tenant_id="tenant-a") == ["demo"]
    assert store.disabled_ids(tenant_id="tenant-a") == []

    assert store.disable(capability_id="demo", tenant_id="tenant-a") is True
    assert store.enabled_ids(tenant_id="tenant-a") == []
    assert store.disabled_ids(tenant_id="tenant-a") == ["demo"]

    store.enable(capability_id="demo", tenant_id="tenant-a", reason="manual-confirmed")
    assert store.enabled_ids(tenant_id="tenant-a") == ["demo"]
    assert store.disabled_ids(tenant_id="tenant-a") == []
