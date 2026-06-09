from __future__ import annotations

import json

from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import ConnectionControlPlane
from runtime.os_kernel import OSKernel
from runtime.runtime_context import RuntimeMaterializer, model_config_from_capabilities
from runtime.secret_store import LocalEncryptedSecretStore


def make_control(tmp_path) -> ConnectionControlPlane:
    return ConnectionControlPlane(
        path=tmp_path / "connections.json",
        secret_store=LocalEncryptedSecretStore(
            path=tmp_path / "secrets.json",
            key_path=tmp_path / "secret.key",
        ),
    )


def write_manifest(root, folder: str, payload: dict) -> None:
    capability_dir = root / folder
    capability_dir.mkdir(parents=True)
    (capability_dir / "capability.json").write_text(json.dumps(payload), encoding="utf-8")


def make_capability_runtime(tmp_path, control: ConnectionControlPlane) -> RuntimeMaterializer:
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
            "tools": ["wrds_status"],
            "data_sources": [
                {
                    "provider_id": "wrds",
                    "source_kind": "professional_database",
                    "dataset_kind": "financial_fundamentals",
                    "normalized_result_schema": "open-multi-agent.data_source_result.v0.1",
                    "license": {"kind": "restricted"},
                    "adapter_metadata": {"legacy_alias": "wrds_result"},
                }
            ],
        },
    )
    write_manifest(
        capabilities_dir,
        "value",
        {
            "id": "value-investing-research",
            "name": "Value Investing",
            "version": "0.1.0",
            "description": "Value investing research.",
            "capability_types": ["skill:value-investing-research"],
            "permissions": ["skill:read", "data:read"],
            "risk_level": "low",
        },
    )
    registry = CapabilityRegistry(capabilities_dir)
    state_store = CapabilityStateStore(tmp_path / "capability-state.json")
    kernel = OSKernel(registry=registry, state_store=state_store, control_plane=control)
    return RuntimeMaterializer(
        control_plane=control,
        workspace_root=tmp_path,
        capability_registry=registry,
        capability_state_store=state_store,
        agent_registry=AgentRegistry(capabilities_dir=capabilities_dir, agents_dir=tmp_path / "missing-agents"),
        os_kernel=kernel,
    )


def test_runtime_context_hot_loads_active_connections(tmp_path) -> None:
    control = make_control(tmp_path)
    materializer = RuntimeMaterializer(control_plane=control, workspace_root=tmp_path)

    empty_context = materializer.build_context(tenant_id="tenant-a")
    assert empty_context.capability_index["connections"] == []
    assert "wrds_status" not in empty_context.tool_registry.names()

    control.confirm(
        raw="wrds\nusername: student\npassword: very-secret",
        tenant_id="tenant-a",
        validate=False,
        discover=False,
    )
    hot_context = materializer.build_context(tenant_id="tenant-a")

    assert any(connection["provider"] == "wrds" for connection in hot_context.capability_index["connections"])
    assert "wrds_status" in hot_context.tool_registry.names()


def test_model_config_degrades_to_single_provider_when_only_minimax_exists(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    config = model_config_from_capabilities(control.capability_index(tenant_id="tenant-a"))

    assert config.orchestrator == "minimax-m2.7"
    assert config.final_judge == "minimax-m2.7"


def test_model_config_auto_routes_openai_only_provider(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="sk-proj-openaiabcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    config = model_config_from_capabilities(control.capability_index(tenant_id="tenant-a"))

    assert config.orchestrator.startswith("gpt")
    assert config.writer.startswith("gpt")
    assert config.default_fallback_models.startswith(config.orchestrator)


def test_model_config_auto_routes_anthropic_and_openai_with_fallback(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="sk-ant-api03-anthropicabcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    control.confirm(
        raw="sk-proj-openaiabcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    capability_index = control.capability_index(tenant_id="tenant-a")
    config = model_config_from_capabilities(capability_index)
    materializer = RuntimeMaterializer(control_plane=control, workspace_root=tmp_path)
    policy = materializer.build_context(tenant_id="tenant-a").model_routing_policy

    assert config.orchestrator.startswith("claude")
    assert config.executor.startswith("gpt")
    assert "gpt" in config.default_fallback_models
    assert "claude" in config.default_fallback_models
    assert policy["selected_models"]["judgment"].startswith("claude")
    assert "fallback_chains" in policy


def test_model_config_scopes_kimi_connection_to_one_agent(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    control.confirm(
        raw=(
            "kimi cn\n"
            "api_key: sk-kimiexampleabcdefghijklmnopqrstuvwxyz123456\n"
            "agent_scope: critic\n"
            "preferred_model: kimi-k2.6"
        ),
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    config = model_config_from_capabilities(control.capability_index(tenant_id="tenant-a"))

    assert config.orchestrator == "minimax-m2.7"
    assert config.writer == "minimax-m2.7"
    assert config.critic == "kimi-k2.6"


def test_model_config_scopes_provider_to_arbitrary_manifest_model_attr(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    control.confirm(
        raw=(
            "kimi cn\n"
            "api_key: sk-kimiexampleabcdefghijklmnopqrstuvwxyz123456\n"
            "agent_scope: custom_reviewer_model\n"
            "preferred_model: kimi-k2.6"
        ),
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    config = model_config_from_capabilities(control.capability_index(tenant_id="tenant-a"))

    assert config.model_for("custom_reviewer_model") == "kimi-k2.6"
    assert config.agent_model_overrides == {"custom_reviewer_model": "kimi-k2.6"}
    assert config.model_for("unknown_manifest_model") == config.committee_member_fallback


def test_model_config_scoped_provider_uses_legacy_agent_scope_alias(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    control.confirm(
        raw=(
            "kimi cn\n"
            "api_key: sk-kimiexampleabcdefghijklmnopqrstuvwxyz123456\n"
            "agent_scope: red_team_skeptic\n"
            "preferred_model: kimi-k2.6"
        ),
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    config = model_config_from_capabilities(control.capability_index(tenant_id="tenant-a"))

    assert config.red_team_agent == "kimi-k2.6"
    assert config.model_for("red_team_agent") == "kimi-k2.6"


def test_model_config_routes_moonshot_only_provider(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="kimi cn\napi_key: sk-kimiexampleabcdefghijklmnopqrstuvwxyz123456",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    config = model_config_from_capabilities(control.capability_index(tenant_id="tenant-a"))

    assert config.orchestrator == "kimi-k2.6"
    assert config.final_judge == "kimi-k2.6"


def test_runtime_context_uses_os_capabilities_to_gate_wrds_tools(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="wrds\nusername: student\npassword: very-secret",
        tenant_id="tenant-a",
        validate=False,
        discover=False,
    )
    materializer = make_capability_runtime(tmp_path, control)

    context = materializer.build_context(tenant_id="tenant-a", task="分析 AAPL")

    assert "wrds-financial-data" in {item["id"] for item in context.enabled_capabilities}
    assert "wrds_status" in context.tool_registry.names()
    assert "wrds_company_financials" not in context.tool_registry.names()
    assert "web_search" not in context.tool_registry.names()
    assert "wrds_query" not in context.tool_registry.names()
    assert any(
        grant.get("capability_id") == "wrds-financial-data" and "network:wrds" in grant.get("permission_grants", [])
        for grant in context.permission_grants
    )
    assert context.data_source_registry["sources"][0]["capability_id"] == "wrds-financial-data"
    assert context.data_source_registry["schema_version"] == "open-multi-agent.data_source_registry.v0.1"
    descriptor = context.data_source_registry["provider_descriptors"][0]
    assert descriptor["provider_id"] == "wrds"
    assert descriptor["source_kind"] == "professional_database"
    assert descriptor["dataset_kind"] == "financial_fundamentals"
    assert descriptor["normalized_result_schema"] == "open-multi-agent.data_source_result.v0.1"
    assert descriptor["adapter_metadata"]["legacy_alias"] == "wrds_result"
    assert context.agent_registry == {"agents": [], "diagnostics": []}


def test_runtime_context_respects_disabled_wrds_capability(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="wrds\nusername: student\npassword: very-secret",
        tenant_id="tenant-a",
        validate=False,
        discover=False,
    )
    materializer = make_capability_runtime(tmp_path, control)
    assert materializer.capability_state_store is not None
    materializer.capability_state_store.disable(capability_id="wrds-financial-data", tenant_id="tenant-a")

    context = materializer.build_context(tenant_id="tenant-a", task="分析 AAPL")

    assert "wrds_status" not in context.tool_registry.names()
    assert context.os_plan is not None
    assert context.os_plan["needs_confirmation"][0]["reason"] == "disabled_by_user"


def test_runtime_context_hot_loads_public_financial_data_capability(tmp_path) -> None:
    control = make_control(tmp_path)
    materializer = make_capability_runtime(tmp_path, control)
    assert materializer.capability_registry is not None
    write_manifest(
        materializer.capability_registry.capabilities_dir,
        "public",
        {
            "id": "public-financial-data",
            "name": "Public Financial Data",
            "version": "0.1.0",
            "description": "SEC, FRED, Stooq, and Kenneth French data.",
            "capability_types": ["public_financial_data", "macro_data", "market_prices", "filings"],
            "permissions": ["network:approved-provider", "data:read", "tool:deterministic-read"],
            "risk_level": "low",
            "tools": ["sec_company_search", "fred_series", "market_price_history", "kenneth_french_factors"],
            "data_packages": ["sec_company_facts", "fred_macro_series", "stooq_market_prices", "kenneth_french_factors"],
        },
    )

    context = materializer.build_context(
        tenant_id="tenant-a",
        task="用 SEC EDGAR, FRED, Stooq 和 Kenneth French 数据分析 AAPL",
    )

    assert "public-financial-data" in {item["id"] for item in context.enabled_capabilities}
    assert {"sec_company_search", "fred_series", "market_price_history", "kenneth_french_factors"} <= set(context.tool_registry.names())
    public_source = next(item for item in context.data_source_registry["sources"] if item["capability_id"] == "public-financial-data")
    assert "fred_macro_series" in public_source["data_packages"]
    public_descriptor = next(
        item for item in context.data_source_registry["provider_descriptors"]
        if item["capability_id"] == "public-financial-data"
    )
    assert public_descriptor["source_kind"] == "capability_declared_source"
    assert public_descriptor["dataset_kind"] == "declared_data_packages"
    assert context.tool_registry.run("fred_series", {"series_id": "FEDFUNDS"}).data["missing_connections"] == ["fred"]


def test_runtime_context_exposes_safe_validation_issues(tmp_path) -> None:
    control = make_control(tmp_path)
    materializer = make_capability_runtime(tmp_path, control)

    context = materializer.build_context(tenant_id="tenant-a", task="分析 AAPL")
    public = context.to_public_dict()

    assert any(issue["code"] == "missing_model_provider" for issue in context.validation_issues or [])
    assert any(issue["code"] == "missing_connection" for issue in context.validation_issues or [])
    serialized = json.dumps(public, ensure_ascii=False)
    assert "very-secret" not in serialized
    assert "password" not in serialized.lower()


def test_runtime_context_materializes_compliance_workflow_plugins(tmp_path) -> None:
    control = make_control(tmp_path)
    registry = CapabilityRegistry()
    state_store = CapabilityStateStore(tmp_path / "capability-state.json")
    agent_registry = AgentRegistry()
    kernel = OSKernel(
        registry=registry,
        state_store=state_store,
        control_plane=control,
        agent_registry=agent_registry,
    )
    materializer = RuntimeMaterializer(
        control_plane=control,
        workspace_root=tmp_path,
        capability_registry=registry,
        capability_state_store=state_store,
        agent_registry=agent_registry,
        os_kernel=kernel,
    )

    context = materializer.build_context(
        tenant_id="tenant-a",
        task="Audit this policy for PII, RBAC, approval, and retention requirements",
    )

    assert {"ai-model-provider", "compliance-workflow"} <= {item["id"] for item in context.enabled_capabilities}
    assert context.tool_registry.names() == ["read_file"]
    assert "write_file" not in context.tool_registry.names()
    agent_keys = {agent["key"] for agent in context.agent_registry["agents"]}
    assert {"policy_interpreter_agent", "dlp_privacy_auditor_agent", "human_in_loop_agent"} <= agent_keys
    workflow = context.capability_runtime["capabilities"]["compliance-workflow"]["entrypoints"]["workflow"]
    assert workflow["graph_mode"] == "compliance_workflow"
    assert "dlp_gate" in workflow["required_gates"]


def test_runtime_context_materializes_evidence_research_plugins_without_granting_arbitrary_network(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    registry = CapabilityRegistry()
    state_store = CapabilityStateStore(tmp_path / "capability-state.json")
    agent_registry = AgentRegistry()
    kernel = OSKernel(
        registry=registry,
        state_store=state_store,
        control_plane=control,
        agent_registry=agent_registry,
    )
    materializer = RuntimeMaterializer(
        control_plane=control,
        workspace_root=tmp_path,
        capability_registry=registry,
        capability_state_store=state_store,
        agent_registry=agent_registry,
        os_kernel=kernel,
    )

    context = materializer.build_context(
        tenant_id="tenant-a",
        task="Verify the citations, source quality, and contradictions in this research memo",
    )

    assert "evidence-research" in {item["id"] for item in context.enabled_capabilities}
    assert context.capability_index["model_providers"]
    agent_keys = {agent["key"] for agent in context.agent_registry["agents"]}
    assert {"claim_decomposition_agent", "citation_auditor_agent", "contradiction_mapper_agent"} <= agent_keys
    assert context.os_plan is not None
    assert context.os_plan["swarm_plan"]["selection_mode"] == "pheromone_response_threshold"
    assert {"research:claim_decomposition", "gate:research_evidence_gate"} <= {
        signal["canonical_target"] for signal in context.os_plan["swarm_plan"]["target_signals"]
    }
    assert "provider_web_search" in context.tool_registry.names()
    assert "approved_source_fetch" in context.tool_registry.names()
    assert context.tool_registry.run("web_search", {"query": "citation audit"}).ok is False
    web_manifest = {tool["name"]: tool for tool in context.tool_registry.manifest()}
    assert web_manifest["provider_web_search"]["granted"] is True
    assert web_manifest["provider_web_search"]["connection_granted"] is True
    assert web_manifest["approved_source_fetch"]["granted"] is True
    assert web_manifest["approved_source_fetch"]["connection_granted"] is True
    assert web_manifest["web_search"]["granted"] is False
    workflow = context.capability_runtime["capabilities"]["evidence-research"]["entrypoints"]["workflow"]
    assert workflow["graph_mode"] == "evidence_research"


def test_evidence_research_runtime_plan_keeps_source_retrieval_with_provider_search(tmp_path) -> None:
    from runtime.workflows.domain_execution import apply_domain_workflow_plan

    control = make_control(tmp_path)
    control.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    registry = CapabilityRegistry()
    state_store = CapabilityStateStore(tmp_path / "capability-state.json")
    agent_registry = AgentRegistry()
    kernel = OSKernel(
        registry=registry,
        state_store=state_store,
        control_plane=control,
        agent_registry=agent_registry,
    )
    context = RuntimeMaterializer(
        control_plane=control,
        workspace_root=tmp_path,
        capability_registry=registry,
        capability_state_store=state_store,
        agent_registry=agent_registry,
        os_kernel=kernel,
    ).build_context(
        tenant_id="tenant-a",
        task="研究 multi-agent 集群中的蚁群和蜂群决策机制是否可行",
    )
    state = {"task": "研究 multi-agent 集群中的蚁群和蜂群决策机制是否可行", "metadata": context.to_public_dict()}
    result = {
        "metadata": state["metadata"],
        "english_search_query": "ant colony bee colony decision making multi-agent systems",
        "plan": [],
        "tool_manifest": context.tool_registry.manifest(),
    }

    updated = apply_domain_workflow_plan(state, result)

    retrieval_steps = [step for step in updated["plan"] if step["id"] == "source-retrieval"]
    assert retrieval_steps
    assert retrieval_steps[0]["tool_calls"][0]["name"] == "provider_web_search"
