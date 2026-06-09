from __future__ import annotations

import json

from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import ConnectionControlPlane
from runtime.os_kernel import OSKernel, infer_intent, required_capability_types
from runtime.secret_store import LocalEncryptedSecretStore


def write_manifest(root, folder: str, payload: dict) -> None:
    capability_dir = root / folder
    capability_dir.mkdir(parents=True)
    (capability_dir / "capability.json").write_text(json.dumps(payload), encoding="utf-8")


def write_agent(root, capability: str, filename: str, payload: dict) -> None:
    agents_dir = root / capability / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def make_control(tmp_path) -> ConnectionControlPlane:
    return ConnectionControlPlane(
        path=tmp_path / "connections.json",
        secret_store=LocalEncryptedSecretStore(
            path=tmp_path / "secrets.json",
            key_path=tmp_path / "secret.key",
        ),
    )


def make_kernel(tmp_path) -> OSKernel:
    write_manifest(
        tmp_path / "capabilities",
        "model",
        {
            "id": "ai-model-provider",
            "name": "AI Model Provider",
            "version": "0.1.0",
            "description": "Chat model provider.",
            "capability_types": ["chat_model"],
            "permissions": ["model:chat", "secret:model-provider", "network:approved-provider"],
            "risk_level": "low",
            "connections": ["model_provider"],
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "wrds",
        {
            "id": "wrds-financial-data",
            "name": "WRDS",
            "version": "0.1.0",
            "description": "WRDS financial data.",
            "capability_types": ["financial_fundamentals", "professional_financial_database"],
            "permissions": ["network:wrds", "secret:wrds", "data:read", "tool:deterministic-read"],
            "risk_level": "low",
            "connections": ["wrds"],
            "tools": ["wrds_status", "wrds_company_financials"],
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "value",
        {
            "id": "value-investing-research",
            "name": "Value Investing",
            "version": "0.1.0",
            "description": "Value investing research.",
            "capability_types": ["skill:value-investing-research", "portfolio.review"],
            "permissions": ["skill:read", "data:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["investment_analysis", "financial_data_retrieval", "portfolio_review"],
                "required_capability_types": ["financial_fundamentals", "professional_financial_database"],
                "required_capability_types_by_intent": {
                    "investment_analysis": ["financial_fundamentals", "professional_financial_database"],
                    "financial_data_retrieval": ["financial_fundamentals", "professional_financial_database"],
                    "portfolio_review": [],
                },
                "targets": [
                    {
                        "target": "decision:formal_valuation",
                        "keywords": ["valuation", "investment", "价值投资"],
                        "compatible_intents": ["investment_analysis", "financial_data_retrieval"],
                    },
                    {
                        "target": "gate:data_gate",
                        "keywords": ["wrds", "financial", "data"],
                        "compatible_intents": ["investment_analysis", "financial_data_retrieval"],
                    },
                    {
                        "target": "decision:portfolio_review",
                        "keywords": ["portfolio", "allocation", "position", "rebalance"],
                        "compatible_intents": ["portfolio_review"],
                    },
                    {
                        "target": "constraint:portfolio_risk",
                        "keywords": ["risk", "concentration", "position sizing"],
                        "compatible_intents": ["portfolio_review"],
                    },
                ],
            },
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "public",
        {
            "id": "public-financial-data",
            "name": "Public Financial Data",
            "version": "0.1.0",
            "description": "SEC, FRED, Stooq, and factor data.",
            "capability_types": ["public_financial_data", "macro_data", "market_prices", "filings"],
            "permissions": ["network:approved-provider", "data:read", "tool:deterministic-read"],
            "risk_level": "low",
            "tools": ["sec_company_search", "fred_series", "market_price_history", "kenneth_french_factors"],
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "value-investing-research",
        "risk_manager_agent.json",
        {
            "key": "risk_manager_agent",
            "name": "Risk Manager Agent",
            "agent_type": "investment_committee_member",
            "focus": "Find downside risk.",
            "order": 10,
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "value-investing-research",
        "red_team_agent.json",
        {
            "key": "red_team_agent",
            "name": "Red Team Agent",
            "agent_type": "investment_committee_member",
            "focus": "Challenge the thesis.",
            "order": 20,
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "document-writing",
        {
            "id": "document-writing",
            "name": "Document Writing",
            "version": "0.1.0",
            "description": "Document writing.",
            "capability_types": ["document_writing", "skill:document-writing"],
            "permissions": ["skill:read", "model:chat"],
            "risk_level": "low",
            "protocol": {
                "intents": ["document_writing"],
                "targets": [
                    {
                        "target": "artifact:document_draft",
                        "default_pressure": 0.82,
                        "keywords": ["draft", "document", "memo", "proposal", "撰写"],
                    },
                    {
                        "target": "gate:document_quality",
                        "default_pressure": 0.74,
                        "keywords": ["quality", "structure", "tone", "润色"],
                    },
                ],
                "candidates": [
                    {"candidate": "candidate:document:ready", "target": "artifact:document_draft"},
                    {"candidate": "candidate:document:revise", "target": "gate:document_quality", "safe_fallback": True},
                ],
                "quorum_policy": {
                    "candidates": ["candidate:document:ready", "candidate:document:revise"],
                    "candidate_fallback": "candidate:document:revise",
                },
            },
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "data-analysis",
        {
            "id": "data-analysis",
            "name": "Data Analysis",
            "version": "0.1.0",
            "description": "Data analysis.",
            "capability_types": ["data_analysis", "skill:data-analysis"],
            "permissions": ["skill:read", "data:read", "tool:deterministic-read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["data_analysis"],
                "targets": [
                    {
                        "target": "metric:data_quality",
                        "default_pressure": 0.8,
                        "keywords": ["csv", "xlsx", "spreadsheet", "dataset", "data quality"],
                    },
                    {
                        "target": "artifact:data_summary",
                        "default_pressure": 0.82,
                        "keywords": ["summary statistics", "statistics", "dataset"],
                    },
                    {
                        "target": "gate:analysis_reproducibility",
                        "default_pressure": 0.72,
                        "keywords": ["reproducible", "deterministic", "quality"],
                    },
                ],
                "candidates": [
                    {"candidate": "candidate:data:complete", "target": "artifact:data_summary"},
                    {"candidate": "candidate:data:needs_more_data", "target": "metric:data_quality", "safe_fallback": True},
                ],
                "quorum_policy": {
                    "candidates": ["candidate:data:complete", "candidate:data:needs_more_data"],
                    "candidate_fallback": "candidate:data:needs_more_data",
                },
                "tool_policy": {"allowed_tool_targets": ["tool:list_files", "tool:read_file"]},
            },
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "code-development",
        {
            "id": "code-development",
            "name": "Controlled Code Development",
            "version": "0.1.0",
            "description": "Controlled code editing with test and interface gates.",
            "capability_types": ["code_development", "skill:code-development"],
            "permissions": ["skill:read", "data:read", "tool:deterministic-read", "filesystem:write", "shell:execute"],
            "risk_level": "medium",
            "requires_confirmation": True,
            "connections": ["model_provider"],
            "swarm": {
                "intents": ["code_development"],
                "targets": [
                    {"target": "gate:code_test_gate", "demand_strength": 0.9, "keywords": ["test", "pytest", "regression"]},
                    {"target": "decision:code_patch_acceptance", "demand_strength": 0.88, "keywords": ["patch", "accept", "regression"]},
                ],
            },
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "compliance-workflow",
        {
            "id": "compliance-workflow",
            "name": "Compliance Workflow",
            "version": "0.1.0",
            "description": "Read-only compliance and approval planning.",
            "capability_types": ["compliance.workflow", "skill:compliance-workflow"],
            "permissions": ["skill:read", "data:read", "tool:deterministic-read", "model:chat"],
            "risk_level": "low",
            "connections": ["model_provider"],
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "evidence-research",
        {
            "id": "evidence-research",
            "name": "Evidence Research",
            "version": "0.1.0",
            "description": "Claim decomposition, source quality, and citation audit.",
            "capability_types": ["evidence.research", "skill:evidence-research"],
            "permissions": ["skill:read", "data:read", "tool:deterministic-read", "network:approved-provider", "model:chat"],
            "risk_level": "low",
            "connections": ["model_provider"],
            "swarm": {
                "intents": ["evidence_research"],
                "targets": [
                    {"target": "research:claim_decomposition", "demand_strength": 0.88, "keywords": ["claim", "atomic", "scope"]},
                    {
                        "target": "research:source_retrieval",
                        "demand_strength": 0.86,
                        "keywords": ["source", "retrieval", "coverage"],
                    },
                    {
                        "target": "metric:research_source_quality",
                        "demand_strength": 0.84,
                        "keywords": ["source_quality", "provenance", "authority"],
                    },
                    {
                        "target": "gate:research_evidence_gate",
                        "demand_strength": 0.9,
                        "keywords": ["evidence", "claim_evidence_graph", "support_strength"],
                    },
                    {
                        "target": "issue:research_contradiction",
                        "demand_strength": 0.72,
                        "keywords": ["contradiction", "counterevidence", "uncertainty"],
                    },
                    {"target": "gate:research_citation_audit", "demand_strength": 0.76, "keywords": ["citation", "quote", "unsupported"]},
                ],
            },
        },
    )
    write_manifest(
        tmp_path / "capabilities",
        "fastapi",
        {
            "id": "fastapi-api",
            "name": "FastAPI",
            "version": "0.1.0",
            "description": "Code editing capability.",
            "capability_types": ["code_development", "skill:fastapi-api"],
            "permissions": ["skill:read", "filesystem:write"],
            "risk_level": "medium",
            "requires_confirmation": True,
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "code-development",
        "repo_scout_agent.json",
        {
            "key": "repo_scout_agent",
            "name": "Repo Scout Agent",
            "agent_type": "code_development_member",
            "focus": ["Inspect repository context."],
            "order": 10,
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "compliance-workflow",
        "dlp_privacy_auditor_agent.json",
        {
            "key": "dlp_privacy_auditor_agent",
            "name": "DLP Privacy Auditor Agent",
            "agent_type": "compliance_workflow_member",
            "focus": ["Find PII and privacy risk."],
            "order": 10,
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "evidence-research",
        "citation_auditor_agent.json",
        {
            "key": "citation_auditor_agent",
            "name": "Citation Auditor Agent",
            "agent_type": "evidence_research_member",
            "focus": ["Verify citation support."],
            "order": 10,
        },
    )
    return OSKernel(
        registry=CapabilityRegistry(tmp_path / "capabilities"),
        state_store=CapabilityStateStore(tmp_path / "capability-state.json"),
        control_plane=make_control(tmp_path),
        agent_registry=AgentRegistry(capabilities_dir=tmp_path / "capabilities", agents_dir=tmp_path / "missing-agents"),
    )


def test_legacy_os_intent_compatibility_delegates_static_fallbacks() -> None:
    assert infer_intent("Summarize this CSV dataset with summary statistics") == "data_analysis"
    assert required_capability_types(task="Summarize this CSV dataset", intent="data_analysis") == [
        "chat_model",
        "data_analysis",
        "skill:data-analysis",
    ]
    assert required_capability_types(
        task="Summarize this CSV dataset",
        intent="data_analysis",
        suppress_legacy_static_fallback=True,
    ) == ["chat_model"]


def test_investment_task_auto_enables_safe_capabilities_but_requires_connections(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="分析 AAPL 是否符合价值投资逻辑", tenant_id="tenant-a")

    assert plan["intent"] == "investment_analysis"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert set(plan["auto_enabled"]) == {"ai-model-provider", "value-investing-research", "wrds-financial-data"}
    assert "professional_financial_database" in plan["required_capabilities"]
    assert {item["connection"] for item in plan["connection_requirements"]} == {"model_provider", "wrds"}
    assert plan["runtime_ready"] is False


def test_investment_task_is_runtime_ready_when_required_connections_exist(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    kernel.control_plane.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=False,
    )
    kernel.control_plane.confirm(
        raw="wrds\nusername: student\npassword: very-secret",
        tenant_id="tenant-a",
        validate=False,
        discover=False,
    )

    plan = kernel.plan(task="分析 AAPL 是否符合价值投资逻辑", tenant_id="tenant-a")

    assert plan["connection_requirements"] == []
    assert plan["missing_capabilities"] == []
    assert plan["runtime_ready"] is True


def test_investment_task_committee_plan_uses_selected_agent_ids(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(
        task="分析 AAPL 是否符合价值投资逻辑",
        tenant_id="tenant-a",
        selected_agent_ids=["red_team_agent"],
    )

    assert plan["committee_plan"]["selection_mode"] == "user_selected"
    assert [member["key"] for member in plan["committee_plan"]["members"]] == ["red_team_agent"]


def test_protocol_capability_can_declare_non_investment_committee_plan(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    write_manifest(
        tmp_path / "capabilities",
        "toy-committee-review",
        {
            "id": "toy-committee-review",
            "name": "Toy Committee Review",
            "version": "0.1.0",
            "description": "Toy protocol with a committee-style reviewer.",
            "capability_types": ["toy.committee"],
            "permissions": ["skill:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["toy_committee_review"],
                "intent_keywords": {"toy_committee_review": ["toy committee review"]},
                "required_capability_types": ["toy.committee"],
                "targets": [
                    {
                        "target": "gate:toy_committee_gate",
                        "keywords": ["toy committee review"],
                    }
                ],
            },
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "toy-committee-review",
        "toy_reviewer_agent.json",
        {
            "key": "toy_reviewer_agent",
            "name": "Toy Reviewer Agent",
            "agent_type": "toy_review_member",
            "committee_role": "toy_reviewer",
            "focus": ["toy committee review", "toy committee gate"],
            "order": 10,
        },
    )

    plan = kernel.plan(task="Run a toy committee review", tenant_id="tenant-a")

    assert plan["intent"] == "toy_committee_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["committee_plan"]["required"] is True
    assert plan["committee_plan"]["selection_mode"] == "pheromone_response_threshold"
    assert [member["key"] for member in plan["committee_plan"]["members"]] == ["toy_reviewer_agent"]


def test_code_task_does_not_auto_enable_high_risk_capability(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="帮我实现一个 FastAPI endpoint", tenant_id="tenant-a")

    assert "code-development" not in plan["auto_enabled"]
    assert [item["capability"]["id"] for item in plan["needs_confirmation"]] == ["code-development"]
    assert plan["needs_confirmation"][0]["permission_decision"]["needs_confirmation"] is True
    assert plan["agent_plan"]["agents"] == []
    assert plan["runtime_ready"] is False


def test_compliance_task_auto_enables_read_only_workflow(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="Audit this policy for PII, RBAC, approval, and retention requirements", tenant_id="tenant-a")

    assert plan["intent"] == "compliance_workflow"
    assert {"ai-model-provider", "compliance-workflow"} <= set(plan["auto_enabled"])
    assert plan["needs_confirmation"] == []
    assert "compliance.workflow" in plan["required_capabilities"]
    assert [agent["key"] for agent in plan["agent_plan"]["agents"]] == ["dlp_privacy_auditor_agent"]
    assert {item["connection"] for item in plan["connection_requirements"]} == {"model_provider"}
    assert plan["runtime_ready"] is False


def test_evidence_research_task_auto_enables_claim_evidence_workflow(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="Verify the citations, source quality, and contradictions in this research memo", tenant_id="tenant-a")

    assert plan["intent"] == "evidence_research"
    assert {"ai-model-provider", "evidence-research"} <= set(plan["auto_enabled"])
    assert plan["needs_confirmation"] == []
    assert "evidence.research" in plan["required_capabilities"]
    assert [agent["key"] for agent in plan["agent_plan"]["agents"]] == ["citation_auditor_agent"]
    assert plan["runtime_ready"] is False


def test_swarm_collective_decision_research_is_not_misrouted_to_investment(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(
        task="研究蚁群以及蜂群的群体决策机制可以对multi-agent系统的借鉴",
        tenant_id="tenant-a",
    )

    assert plan["intent"] == "evidence_research"
    assert {"ai-model-provider", "evidence-research"} <= set(plan["auto_enabled"])
    assert "financial_fundamentals" not in plan["required_capabilities"]
    assert "skill:value-investing-research" not in plan["required_capabilities"]
    assert "wrds-financial-data" not in plan["auto_enabled"]
    assert {item["connection"] for item in plan["connection_requirements"]} == {"model_provider"}
    assert plan["committee_plan"]["required"] is False


def test_generic_analysis_word_alone_does_not_force_investment_intent(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(
        task="分析蚁群算法和蜂群决策对多智能体系统治理的启发",
        tenant_id="tenant-a",
    )

    assert plan["intent"] == "evidence_research"
    assert "financial_fundamentals" not in plan["required_capabilities"]
    assert "wrds-financial-data" not in plan["auto_enabled"]


def test_pheroos_goal_router_recruits_evidence_agents_by_target(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    write_agent(
        tmp_path / "capabilities",
        "evidence-research",
        "claim_decomposition_agent.json",
        {
            "key": "claim_decomposition_agent",
            "name": "Claim Decomposition Agent",
            "agent_type": "evidence_research_member",
            "committee_role": "claim_decomposer",
            "focus": ["atomic_claims", "verification_units", "scope_boundaries"],
            "tags": ["research", "claims", "evidence"],
            "order": 5,
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "evidence-research",
        "source_quality_rater_agent.json",
        {
            "key": "source_quality_rater_agent",
            "name": "Source Quality Rater Agent",
            "agent_type": "evidence_research_member",
            "committee_role": "source_quality_rater",
            "focus": ["source_quality", "provenance", "authority"],
            "tags": ["research", "quality", "provenance"],
            "order": 15,
        },
    )

    plan = kernel.plan(
        task="研究蚁群以及蜂群的群体决策机制可以对multi-agent系统的借鉴",
        tenant_id="tenant-a",
    )

    assert plan["swarm_plan"]["schema_version"] == "pheroos.goal_router.v1"
    targets = {signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]}
    assert {
        "research:claim_decomposition",
        "metric:research_source_quality",
        "gate:research_evidence_gate",
    } <= targets
    activated = set(plan["swarm_plan"]["activated_agents"])
    assert {"claim_decomposition_agent", "source_quality_rater_agent", "citation_auditor_agent"} <= activated
    assert plan["agent_plan"]["selection_mode"] == "pheromone_response_threshold"
    assert {"claim_decomposition_agent", "source_quality_rater_agent"} <= {
        agent["key"] for agent in plan["agent_plan"]["agents"]
    }


def test_pheroos_goal_router_prefers_capability_declared_protocol_targets(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    (tmp_path / "capabilities" / "evidence-research" / "capability.json").write_text(
        json.dumps(
            {
            "id": "evidence-research",
            "name": "Evidence Research",
            "version": "0.1.0",
            "description": "Claim decomposition, source quality, and citation audit.",
            "capability_types": ["evidence.research", "skill:evidence-research"],
            "permissions": ["skill:read", "data:read", "tool:deterministic-read", "network:approved-provider", "model:chat"],
            "risk_level": "low",
            "connections": ["model_provider"],
            "agents_path": "agents",
            "swarm": {
                "targets": [
                    {
                        "target": "research:source_retrieval",
                        "demand_strength": 0.91,
                        "keywords": ["retrieval", "source"],
                        "summary": "Capability-declared retrieval target.",
                    }
                ],
                "recovery_protocols": [
                    {
                        "id": "declared_recovery",
                        "targets": [{"target": "research:source_retrieval", "demand_strength": 0.95}],
                        "max_rounds": 4,
                    }
                ],
                "candidate_policy": {
                    "candidate_type": "research_synthesis",
                    "candidates": [{"id": "candidate:synthesis:insufficient_evidence", "label": "Insufficient evidence"}],
                },
                "quorum_policy": {"candidate_type": "research_synthesis", "max_swarm_rounds": 4},
                "stop_signal_policy": {"authority_level_required": 3, "blocked_actions": ["writer:unsourced_claim"]},
            },
            }
        ),
        encoding="utf-8",
    )

    plan = kernel.plan(task="Verify source quality for this claim", tenant_id="tenant-a")

    swarm = plan["swarm_plan"]
    assert swarm["protocol_source"] == "capability_manifest"
    assert swarm["target_signals"] == [
        {
            "schema_version": "pheroos.goal_router.v1",
            "type": "goal",
            "target": "research:source_retrieval",
            "canonical_target": "research:source_retrieval",
            "target_kind": "research",
            "demand_strength": 0.91,
            "source_module": "os_kernel.goal_router",
            "lifecycle_state": "active",
            "content": "Capability-declared retrieval target.",
        }
    ]
    assert swarm["candidate_policy"]["candidate_type"] == "research_synthesis"
    assert swarm["recovery_protocols"][0]["id"] == "declared_recovery"
    assert swarm["max_rounds"] == 4


def test_os_kernel_uses_capability_declared_intent_and_targets_for_new_capability(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    write_manifest(
        tmp_path / "capabilities",
        "toy-review",
        {
            "id": "toy-review",
            "name": "Toy Review",
            "version": "0.1.0",
            "description": "Toy protocol proof capability.",
            "capability_types": ["toy.review", "skill:toy-review"],
            "permissions": ["skill:read", "data:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["toy_review"],
                "targets": [
                    {"target": "decision:toy_accept", "default_pressure": 0.87, "keywords": ["toy", "accept"]},
                    {"target": "gate:toy_evidence_gate", "default_pressure": 0.91, "keywords": ["toy", "evidence"]},
                ],
                "candidates": [
                    {"candidate": "candidate:toy:accept", "target": "decision:toy_accept"},
                    {"candidate": "candidate:toy:reject", "target": "decision:toy_accept"},
                    {
                        "candidate": "candidate:toy:insufficient_evidence",
                        "target": "decision:toy_accept",
                        "safe_fallback": True,
                    },
                ],
                "quorum_policy": {
                    "candidates": [
                        "candidate:toy:accept",
                        "candidate:toy:reject",
                        "candidate:toy:insufficient_evidence",
                    ],
                    "max_swarm_rounds": 3,
                },
            },
        },
    )
    write_agent(
        tmp_path / "capabilities",
        "toy-review",
        "toy_evidence_agent.json",
        {
            "key": "toy_evidence_agent",
            "name": "Toy Evidence Agent",
            "agent_type": "toy_review_member",
            "committee_role": "toy_evidence",
            "focus": ["toy", "evidence", "accept"],
            "tags": ["toy", "evidence"],
            "order": 10,
        },
    )

    plan = kernel.plan(task="toy_review this artifact", tenant_id="tenant-a")

    assert plan["intent"] == "toy_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert "toy.review" in plan["required_capabilities"]
    assert plan["os_routing_trace"][0]["event_type"] == "os.intent.legacy_inferred"
    assert plan["os_routing_trace"][0]["used"] is False
    assert plan["os_routing_trace"][1]["source"] == "capability_protocol_intent"
    assert plan["os_routing_trace"][2]["source"] == "capability_protocol"
    assert "toy-review" in plan["auto_enabled"]
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert {signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]} == {
        "decision:toy_accept",
        "gate:toy_evidence_gate",
    }
    assert "toy_evidence_agent" in plan["swarm_plan"]["activated_agents"]


def test_os_kernel_routes_protocol_intent_from_declared_target_keywords(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    write_manifest(
        tmp_path / "capabilities",
        "quality-lens",
        {
            "id": "quality-lens",
            "name": "Quality Lens",
            "version": "0.1.0",
            "description": "Review artifacts for quality.",
            "capability_types": ["artifact.review", "skill:quality-lens"],
            "permissions": ["skill:read", "data:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["artifact_review"],
                "targets": [
                    {
                        "target": "gate:artifact_quality",
                        "default_pressure": 0.88,
                        "keywords": ["qa", "artifact-check"],
                    }
                ],
                "candidates": [
                    {"candidate": "candidate:artifact:pass", "target": "gate:artifact_quality"},
                    {"candidate": "candidate:artifact:revise", "target": "gate:artifact_quality", "safe_fallback": True},
                ],
                "quorum_policy": {
                    "candidates": ["candidate:artifact:pass", "candidate:artifact:revise"],
                    "candidate_fallback": "candidate:artifact:revise",
                },
            },
        },
    )

    plan = kernel.plan(task="please qa this artifact", tenant_id="tenant-a")

    assert plan["intent"] == "artifact_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert "artifact.review" in plan["required_capabilities"]
    assert "quality-lens" in plan["auto_enabled"]
    assert plan["swarm_plan"]["target_signals"][0]["canonical_target"] == "gate:artifact_quality"


def test_os_kernel_routes_protocol_intent_from_declared_intent_keywords(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    write_manifest(
        tmp_path / "capabilities",
        "keyword-review",
        {
            "id": "keyword-review",
            "name": "Keyword Review",
            "version": "0.1.0",
            "description": "Review artifacts from intent keywords.",
            "capability_types": ["keyword.review", "skill:keyword-review"],
            "permissions": ["skill:read", "data:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["keyword_review"],
                "intent_keywords": {
                    "keyword_review": ["aurora-gate"],
                },
                "required_capability_types": ["keyword.review", "skill:keyword-review"],
                "targets": [
                    {
                        "target": "gate:keyword_review",
                        "default_pressure": 0.84,
                        "keywords": ["completion-only"],
                    }
                ],
                "candidates": [
                    {"candidate": "candidate:keyword:pass", "target": "gate:keyword_review"},
                    {"candidate": "candidate:keyword:revise", "target": "gate:keyword_review", "safe_fallback": True},
                ],
                "quorum_policy": {
                    "candidates": ["candidate:keyword:pass", "candidate:keyword:revise"],
                    "candidate_fallback": "candidate:keyword:revise",
                },
            },
        },
    )

    plan = kernel.plan(task="aurora-gate this artifact", tenant_id="tenant-a")

    assert plan["intent"] == "keyword_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["capability_id"] == "keyword-review"
    assert plan["protocol_intent_matches"][0]["matched_markers"] == ["aurora-gate"]
    assert plan["protocol_intent_matches"][0]["identity_match_count"] == 0
    assert plan["protocol_intent_matches"][0]["keyword_match_count"] == 1
    assert "keyword.review" in plan["required_capabilities"]
    assert "keyword-review" in plan["auto_enabled"]
    assert plan["os_routing_trace"][0]["used"] is False
    assert plan["os_routing_trace"][1]["legacy_fallback"] is False
    assert plan["os_routing_trace"][2]["source"] == "capability_protocol"
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert plan["swarm_plan"]["target_signals"][0]["canonical_target"] == "gate:keyword_review"


def test_explicit_protocol_without_requirement_types_does_not_use_static_capability_defaults(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    write_manifest(
        tmp_path / "capabilities",
        "thin-code",
        {
            "id": "thin-code-router",
            "name": "Thin Code Router",
            "version": "0.1.0",
            "description": "Malformed protocol router with no resolvable capability type.",
            "capability_types": [],
            "permissions": ["skill:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["code_development"],
                "targets": [],
            },
        },
    )

    plan = kernel.plan(task="thin-code-router code_development endpoint patch", tenant_id="tenant-a")

    assert plan["intent"] == "code_development"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["capability_id"] == "thin-code-router"
    assert plan["required_capabilities"] == ["chat_model"]
    assert "code-development" not in plan["auto_enabled"]
    assert plan["needs_capability"] is True
    assert plan["runtime_ready"] is False
    requirement_event = next(
        item for item in plan["os_routing_trace"] if item["event_type"] == "os.required_capabilities.selected"
    )
    assert requirement_event["source"] == "capability_protocol_missing_requirements"
    assert requirement_event["legacy_fallback"] is False
    assert requirement_event["needs_capability"] is True
    assert any(
        item["event_type"] == "os.required_capabilities.needs_capability"
        and item["selected_capability_id"] == "thin-code-router"
        for item in plan["os_routing_trace"]
    )
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert plan["swarm_plan"]["needs_capability"] is True
    assert plan["swarm_plan"]["routing_trace"][0]["event_type"] == "goal_router.protocol_targets_missing"


def test_explicit_protocol_without_targets_is_not_runtime_ready_even_when_connections_exist(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    kernel.control_plane.confirm(
        raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=False,
    )
    write_manifest(
        tmp_path / "capabilities",
        "targetless-review",
        {
            "id": "targetless-review",
            "name": "Targetless Review",
            "version": "0.1.0",
            "description": "Protocol with requirements but no declared targets.",
            "capability_types": ["targetless.review", "skill:targetless-review"],
            "permissions": ["skill:read", "data:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["targetless_review"],
                "targets": [],
            },
        },
    )

    plan = kernel.plan(task="targetless_review this artifact", tenant_id="tenant-a")

    assert plan["intent"] == "targetless_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert "targetless.review" in plan["required_capabilities"]
    assert "targetless-review" in plan["auto_enabled"]
    assert plan["connection_requirements"] == []
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert plan["swarm_plan"]["needs_capability"] is True
    assert plan["swarm_plan"]["routing_trace"][0]["event_type"] == "goal_router.protocol_targets_missing"
    assert plan["needs_capability"] is True
    assert plan["runtime_ready"] is False


def test_declared_evidence_protocol_routes_without_goal_router_fallback(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="Verify the citations, source quality, and contradictions in this research memo", tenant_id="tenant-a")

    assert plan["intent"] == "evidence_research"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["capability_id"] == "evidence-research"
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    evidence_protocol = next(
        item for item in plan["swarm_plan"]["capability_protocols"] if item["capability_id"] == "evidence-research"
    )
    assert evidence_protocol["generated_legacy_protocol"] is False
    assert evidence_protocol["source"] == "capability_swarm_protocol"
    assert {"research:claim_decomposition", "gate:research_evidence_gate"} <= {
        signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]
    }


def test_protocol_intent_matching_respects_target_compatible_intents(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    write_manifest(
        tmp_path / "capabilities",
        "dual-review",
        {
            "id": "dual-review",
            "name": "Dual Review",
            "version": "0.1.0",
            "description": "Protocol with two review intents and intent-specific target keywords.",
            "capability_types": ["dual.review", "skill:dual-review"],
            "permissions": ["skill:read", "data:read"],
            "risk_level": "low",
            "protocol": {
                "intents": ["alpha_review", "beta_review"],
                "intent_keywords": {
                    "alpha_review": ["alpha-direct"],
                },
                "required_capability_types_by_intent": {
                    "alpha_review": [],
                    "beta_review": [],
                },
                "targets": [
                    {
                        "target": "gate:alpha_review",
                        "keywords": ["alpha-gate"],
                        "compatible_intents": ["alpha_review"],
                    },
                    {
                        "target": "gate:beta_review",
                        "keywords": ["beta-gate"],
                        "compatible_intents": ["beta_review"],
                    },
                ],
            },
        },
    )

    plan = kernel.plan(task="beta-gate this artifact", tenant_id="tenant-a")

    assert plan["intent"] == "beta_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["matched_markers"] == ["beta-gate"]
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert [signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]] == ["gate:beta_review"]

    direct = kernel.plan(task="alpha-direct this artifact", tenant_id="tenant-a")

    assert direct["intent"] == "alpha_review"
    assert direct["protocol_intent_matches"][0]["matched_markers"] == ["alpha-direct"]


def test_single_unaligned_protocol_keyword_does_not_override_specific_legacy_intent(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="Patch this source code endpoint", tenant_id="tenant-a")

    assert plan["intent"] == "code_development"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["capability_id"] == "code-development"
    assert all(match["capability_id"] != "evidence-research" for match in plan["protocol_intent_matches"])
    assert [item["capability"]["id"] for item in plan["needs_confirmation"]] == ["code-development"]


def test_general_agent_plan_respects_user_selection(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(
        task="Verify the citations and source quality in this research memo",
        tenant_id="tenant-a",
        selected_agent_ids=["citation_auditor_agent", "missing_agent"],
    )

    assert plan["agent_plan"]["selection_mode"] == "user_selected"
    assert [agent["key"] for agent in plan["agent_plan"]["agents"]] == ["citation_auditor_agent"]
    assert plan["agent_plan"]["warnings"] == ["unknown agent ignored: missing_agent"]


def test_public_financial_sources_are_auto_enabled_when_requested(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="用 SEC EDGAR、FRED、Stooq 和 Kenneth French 数据分析 AAPL", tenant_id="tenant-a")

    assert "public_financial_data" in plan["required_capabilities"]
    assert "public-financial-data" in plan["auto_enabled"]
    assert plan["needs_confirmation"] == []


def test_disabled_capability_is_not_auto_reenabled(tmp_path) -> None:
    kernel = make_kernel(tmp_path)
    kernel.state_store.disable(capability_id="wrds-financial-data", tenant_id="tenant-a")

    plan = kernel.plan(task="分析 AAPL", tenant_id="tenant-a")

    assert "wrds-financial-data" not in plan["auto_enabled"]
    assert plan["needs_confirmation"][0]["capability"]["id"] == "wrds-financial-data"
    assert plan["needs_confirmation"][0]["reason"] == "disabled_by_user"


def test_portfolio_review_uses_specific_taxonomy_and_committee(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="Review my portfolio allocation and position sizing", tenant_id="tenant-a")

    assert plan["intent"] == "portfolio_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["capability_id"] == "value-investing-research"
    assert {"ai-model-provider", "value-investing-research"} <= set(plan["auto_enabled"])
    assert "portfolio.review" in plan["required_capabilities"]
    assert "financial_fundamentals" not in plan["required_capabilities"]
    assert "professional_financial_database" not in plan["required_capabilities"]
    assert plan["os_routing_trace"][2]["source"] == "capability_protocol"
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert {signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]} == {
        "decision:portfolio_review",
        "constraint:portfolio_risk",
    }
    assert plan["committee_plan"]["required"] is True


def test_document_writing_uses_document_capability(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="帮我撰写一份项目 proposal", tenant_id="tenant-a")

    assert plan["intent"] == "document_writing"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["capability_id"] == "document-writing"
    assert {"ai-model-provider", "document-writing"} <= set(plan["auto_enabled"])
    assert plan["required_capabilities"] == ["chat_model", "document_writing", "skill:document-writing"]
    assert plan["os_routing_trace"][0]["used"] is False
    assert plan["os_routing_trace"][0]["reason"]["matched_hint_group"] == "document_writing"
    assert plan["os_routing_trace"][2]["source"] == "capability_protocol"
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert {signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]} == {
        "artifact:document_draft",
        "gate:document_quality",
    }
    assert plan["committee_plan"]["required"] is False


def test_data_analysis_uses_data_analysis_capability(tmp_path) -> None:
    kernel = make_kernel(tmp_path)

    plan = kernel.plan(task="Analyze this CSV dataset and compute summary statistics", tenant_id="tenant-a")

    assert plan["intent"] == "data_analysis"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["protocol_intent_matches"][0]["capability_id"] == "data-analysis"
    assert {"ai-model-provider", "data-analysis"} <= set(plan["auto_enabled"])
    assert "data_analysis" in plan["required_capabilities"]
    assert plan["os_routing_trace"][2]["source"] == "capability_protocol"
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert {signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]} == {
        "metric:data_quality",
        "artifact:data_summary",
        "gate:analysis_reproducibility",
    }
    assert plan["committee_plan"]["required"] is False
