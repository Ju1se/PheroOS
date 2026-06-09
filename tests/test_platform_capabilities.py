from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.routes.dependencies import (
    get_agent_registry,
    get_capability_registry,
    get_capability_state_store,
    get_connection_control_plane,
    get_os_kernel,
)
from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import ConnectionControlPlane
from runtime.os_kernel import OSKernel
from runtime.secret_store import LocalEncryptedSecretStore


def write_manifest(root, folder: str, payload: dict) -> None:
    capability_dir = root / folder
    capability_dir.mkdir(parents=True)
    (capability_dir / "capability.json").write_text(json.dumps(payload), encoding="utf-8")


def make_objects(tmp_path):
    capabilities_dir = tmp_path / "capabilities"
    write_manifest(
        capabilities_dir,
        "wrds",
        {
            "id": "wrds-financial-data",
            "name": "WRDS",
            "version": "0.1.0",
            "description": "WRDS financial data.",
            "capability_types": ["financial_fundamentals"],
            "permissions": ["network:wrds", "secret:wrds", "data:read", "tool:deterministic-read"],
            "risk_level": "low",
            "connections": ["wrds"],
        },
    )
    write_manifest(
        capabilities_dir,
        "fastapi",
        {
            "id": "fastapi-api",
            "name": "FastAPI",
            "version": "0.1.0",
            "description": "Code writing.",
            "capability_types": ["code_development", "skill:fastapi-api"],
            "permissions": ["skill:read", "filesystem:write"],
            "risk_level": "medium",
            "requires_confirmation": True,
        },
    )
    agents_dir = capabilities_dir / "wrds-financial-data" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "demo_agent.json").write_text(
        json.dumps(
            {
                "key": "demo_agent",
                "name": "Demo Agent",
                "agent_type": "investment_committee_member",
                "focus": "Demo committee focus.",
            }
        ),
        encoding="utf-8",
    )
    registry = CapabilityRegistry(capabilities_dir)
    agent_registry = AgentRegistry(capabilities_dir=capabilities_dir, agents_dir=tmp_path / "missing-agents")
    state_store = CapabilityStateStore(tmp_path / "capability-state.json")
    control = ConnectionControlPlane(
        path=tmp_path / "connections.json",
        secret_store=LocalEncryptedSecretStore(
            path=tmp_path / "secrets.json",
            key_path=tmp_path / "secret.key",
        ),
    )
    kernel = OSKernel(registry=registry, state_store=state_store, control_plane=control, agent_registry=agent_registry)
    return registry, agent_registry, state_store, control, kernel


def test_platform_capability_catalog_plan_enable_and_disable_api(tmp_path) -> None:
    registry, agent_registry, state_store, control, kernel = make_objects(tmp_path)
    app.dependency_overrides[get_agent_registry] = lambda: agent_registry
    app.dependency_overrides[get_capability_registry] = lambda: registry
    app.dependency_overrides[get_capability_state_store] = lambda: state_store
    app.dependency_overrides[get_connection_control_plane] = lambda: control
    app.dependency_overrides[get_os_kernel] = lambda: kernel
    client = TestClient(app)
    try:
        catalog = client.get("/platform/capability-catalog")
        plan = client.post(
            "/platform/os/plan",
            json={"task": "分析 AAPL", "tenant_id": "tenant-a", "committee_member_ids": ["demo_agent"]},
        )
        active = client.get("/platform/capabilities/active", params={"tenant_id": "tenant-a"})
        agents = client.get("/platform/agents", params={"tenant_id": "tenant-a"})
        needs_confirmation = client.post(
            "/platform/capabilities/enable",
            json={"capability_id": "fastapi-api", "tenant_id": "tenant-a"},
        )
        confirmed = client.post(
            "/platform/capabilities/enable",
            json={"capability_id": "fastapi-api", "tenant_id": "tenant-a", "confirmed": True},
        )
        disabled = client.post("/platform/capabilities/fastapi-api/disable", params={"tenant_id": "tenant-a"})
    finally:
        app.dependency_overrides.clear()

    assert catalog.status_code == 200
    assert {item["id"] for item in catalog.json()["capabilities"]} == {"fastapi-api", "wrds-financial-data"}
    assert plan.status_code == 200
    assert plan.json()["auto_enabled"] == ["wrds-financial-data"]
    assert plan.json()["committee_plan"]["members"][0]["key"] == "demo_agent"
    assert active.status_code == 200
    assert active.json()["capabilities"][0]["id"] == "wrds-financial-data"
    assert agents.status_code == 200
    assert agents.json()["agents"][0]["key"] == "demo_agent"
    assert needs_confirmation.json()["status"] == "needs_confirmation"
    assert confirmed.json()["status"] == "enabled"
    assert disabled.json()["capability_id"] == "fastapi-api"
