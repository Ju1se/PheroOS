from __future__ import annotations

import json

import pytest

from runtime.agent_registry import AgentRegistry


def write_agent(root, capability: str, filename: str, payload: dict) -> None:
    agents_dir = root / capability / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def agent_payload(key: str = "demo_agent") -> dict:
    return {
        "key": key,
        "name": "Demo Agent",
        "agent_type": "investment_committee_member",
        "focus": ["Assess one narrow issue."],
        "model_attr": key,
        "default_enabled": True,
        "order": 10,
        "committee_role": "specialist",
        "required_capabilities": ["investment.research"],
        "required_tools": ["metric_registry.compute"],
        "risk_level": "low",
        "swarm": {"initial_thresholds": {"committee_review": 0.4}, "can_block": False},
        "ui": {"accent": "emerald"},
    }


def test_agent_registry_loads_agents_from_capability_manifests(tmp_path) -> None:
    write_agent(tmp_path, "value-investing-research", "demo.json", agent_payload("demo_agent"))

    catalog = AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").catalog()

    assert catalog["diagnostics"] == []
    assert catalog["agents"][0]["key"] == "demo_agent"
    assert catalog["agents"][0]["capability_id"] == "value-investing-research"
    assert catalog["agents"][0]["focus_items"] == ["Assess one narrow issue."]
    assert catalog["agents"][0]["committee_role"] == "specialist"
    assert catalog["agents"][0]["required_tools"] == ["metric_registry.compute"]
    assert catalog["agents"][0]["accent"] == "emerald"
    assert catalog["agents"][0]["swarm"]["initial_thresholds"]["committee_review"] == 0.4


def test_agent_registry_filters_by_enabled_capability_ids(tmp_path) -> None:
    write_agent(tmp_path, "enabled-capability", "one.json", agent_payload("enabled_agent"))
    write_agent(tmp_path, "disabled-capability", "two.json", agent_payload("disabled_agent"))

    catalog = AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").catalog(
        enabled_capability_ids={"enabled-capability"}
    )

    assert [agent["key"] for agent in catalog["agents"]] == ["enabled_agent"]


def test_agent_registry_committee_specs_can_use_user_selection(tmp_path) -> None:
    write_agent(tmp_path, "value-investing-research", "one.json", agent_payload("one_agent"))
    write_agent(tmp_path, "value-investing-research", "two.json", agent_payload("two_agent"))

    specs = AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").committee_specs(
        selected_keys=["two_agent"],
        enabled_capability_ids={"value-investing-research"},
    )

    assert [spec["key"] for spec in specs] == ["two_agent"]
    assert specs[0]["required_tools"] == ["metric_registry.compute"]
    assert specs[0]["swarm"]["can_block"] is False


def test_agent_registry_committee_specs_use_manifest_committee_role(tmp_path) -> None:
    write_agent(
        tmp_path,
        "toy-review",
        "reviewer.json",
        {
            **agent_payload("toy_reviewer"),
            "agent_type": "toy_review_member",
            "committee_role": "evidence_reviewer",
            "required_capabilities": ["toy.review"],
        },
    )
    write_agent(
        tmp_path,
        "toy-review",
        "worker.json",
        {
            **agent_payload("toy_worker"),
            "agent_type": "toy_review_member",
            "committee_role": "",
            "required_capabilities": ["toy.review"],
        },
    )

    specs = AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").committee_specs(
        enabled_capability_ids={"toy-review"}
    )

    assert [spec["key"] for spec in specs] == ["toy_reviewer"]
    assert specs[0]["committee_role"] == "evidence_reviewer"


def test_agent_registry_legacy_committee_agent_type_remains_compatibility_path(tmp_path) -> None:
    write_agent(
        tmp_path,
        "legacy-capability",
        "legacy.json",
        {
            **agent_payload("legacy_agent"),
            "agent_type": "investment_committee_member",
            "committee_role": "",
        },
    )

    specs = AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").committee_specs(
        enabled_capability_ids={"legacy-capability"}
    )

    assert [spec["key"] for spec in specs] == ["legacy_agent"]
    assert specs[0]["committee_role"] is None


def test_built_in_investment_agents_expose_swarm_metadata() -> None:
    catalog = AgentRegistry().catalog(enabled_capability_ids={"value-investing-research"})
    data_agent = next(agent for agent in catalog["agents"] if agent["key"] == "data_auditor_agent")

    assert data_agent["swarm"]["can_block"] is True
    assert "stop_signal" in data_agent["swarm"]["signal_emit_permissions"]


def test_built_in_roadmap_agents_are_discoverable() -> None:
    catalog = AgentRegistry().catalog(
        enabled_capability_ids={"code-development", "compliance-workflow", "evidence-research"}
    )
    agents = {agent["key"]: agent for agent in catalog["agents"]}

    assert catalog["diagnostics"] == []
    assert "repo_scout_agent" in agents
    assert "dlp_privacy_auditor_agent" in agents
    assert "citation_auditor_agent" in agents
    assert agents["repo_scout_agent"]["agent_type"] == "code_development_member"
    assert agents["dlp_privacy_auditor_agent"]["swarm"]["can_block"] is True
    assert "stop_signal" in agents["citation_auditor_agent"]["swarm"]["signal_emit_permissions"]


def test_agent_registry_rejects_duplicate_keys(tmp_path) -> None:
    write_agent(tmp_path, "one", "agent.json", agent_payload("duplicate_agent"))
    write_agent(tmp_path, "two", "agent.json", agent_payload("duplicate_agent"))

    with pytest.raises(ValueError, match="duplicate agent key"):
        AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").load()


def test_agent_registry_rejects_malformed_risk_level(tmp_path) -> None:
    payload = {**agent_payload("bad_agent"), "risk_level": "catastrophic"}
    write_agent(tmp_path, "one", "agent.json", payload)

    catalog = AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").catalog()

    assert catalog["agents"] == []
    assert "risk_level" in catalog["diagnostics"][0]["error"]


def test_agent_registry_validates_selected_keys(tmp_path) -> None:
    write_agent(tmp_path, "one", "agent.json", agent_payload("known_agent"))

    result = AgentRegistry(capabilities_dir=tmp_path, agents_dir=tmp_path / "missing").validate_selected_keys(
        ["known_agent", "missing_agent"]
    )

    assert result["valid"] is False
    assert result["unknown"] == ["missing_agent"]
