from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.graph import END

import runtime.graph as graph_module
from runtime.agent_metrics import current_agent_metrics, reset_agent_metrics, start_agent_metrics
from runtime.graph import (
    AgentRuntime,
    apply_protocol_decision_boundary,
    apply_review_grounding_policy,
    build_direct_wrds_orchestration,
    collect_wrds_results,
    committee_member_order,
    committee_member_specs_for_state,
    deterministic_plan,
    enforce_source_mode_on_plan,
    ensure_required_wrds_company_step,
    ensure_required_web_research_step,
    extract_tool_calls_from_text,
    has_fetched_source_text,
    normalize_orchestration,
    normalize_run_result,
    normalize_scorecard,
    normalize_wrds_company_tool_args,
    next_after_writer,
    parse_committee_output,
    parse_discussion_round,
    parse_json_object,
    parse_plan,
    preserve_runtime_metadata,
    select_search_result_urls,
    should_auto_fetch_search_results,
    should_bypass_graph_to_wrds,
    should_run_data_gate,
    should_run_workflow_host,
    should_run_wrds_agent,
    should_upgrade_search_to_provider,
    step_tool_results_succeeded,
    summarize_execution_metric_status,
    summarize_run_outcome,
    tool_manifest_for_state,
    wrds_argument_normalizer_from_state,
)
from runtime.capability_runtime import CapabilityEntrypointError, load_capability_descriptor
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import ConnectionControlPlane
from runtime.llm import ModelConfig
from runtime.os_kernel import OSKernel
from runtime.runtime_context import RuntimeMaterializer
from runtime.secret_store import LocalEncryptedSecretStore
from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.skill_loader import SkillLoader
from runtime.tool_registry import ToolRegistry
from runtime.workflows.orchestration_guidance import source_mode_orchestration_guidance
from tools.safe_tools import ToolResult


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(model)
        if model == "orchestrator":
            return (
                '{"translated_task":"Build a FastAPI endpoint","english_search_query":"Build a FastAPI endpoint",'
                '"task_type":"coding","depth":"standard",'
                '"required_agents":{"memory":false,"research":false,"quant":false,"domain":true,"critic":true,"writer":true,"final_judge":true},'
                '"rationale":"FastAPI coding task",'
                '"steps":[{"id":"1","title":"Inspect","action":"Inspect existing files",'
                '"tool_calls":[{"name":"list_files","args":{"path":".","pattern":"*.md"}}]}]}'
            )
        if model == "research_agent":
            return (
                '{"status":"completed","sources":[{"title":"Source A","url":"https://example.com",'
                '"key_facts":["fact"],"reliability":"medium"}],"key_facts":["fact"],'
                '"evidence_gaps":["gap"],"reliability":"medium","source_grounding":"fetched_source_text"}'
            )
        if model == "quant_agent":
            return (
                '{"status":"insufficient_data","assumptions":["none"],"formulas":["FCF yield = FCF / market cap"],'
                '"calculations":["No FCF input available"],"metrics":[],"sensitivity":[],'
                '"missing_data":["FCF"],"data_quality":"partial"}'
            )
        if model == "domain_expert":
            return (
                '{"status":"completed","domain":"coding","judgment":"Implementation looks scoped.",'
                '"framework_points":["separate routes and schemas"],"risks":["missing tests"],'
                '"missing_evidence":["existing app structure"],"confidence":"medium"}'
            )
        if model == "critic":
            return '{"status":"pass","issues":[],"overclaims":[],"data_errors":[],"citation_gaps":[],"minimal_fixes":[],"summary":"Looks good for MVP."}'
        if model == "writer":
            return "MVP 运行完成。"
        if model == "final_judge":
            return "MVP 运行完成。"
        return "MVP 运行完成。"


class EmptyPlanLLM:
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        return (
            '{"translated_task":"Say hello","english_search_query":"Say hello",'
            '"task_type":"general","depth":"direct",'
            '"required_agents":{"memory":false,"research":false,"quant":false,"domain":false,'
            '"critic":false,"writer":true,"final_judge":false},'
            '"rationale":"No tool required","steps":[]}'
        )


def investment_os_plan() -> dict:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    return {
        "intent": "investment_analysis",
        "swarm_plan": build_goal_routed_swarm_plan(
            task="Analyze AAPL as an investment",
            intent="investment_analysis",
            required_capability_types=["investment.research"],
            agents=[],
            capabilities=[manifest.to_public_dict()],
        ),
    }


@pytest.mark.anyio
async def test_runtime_model_gateway_keyword_is_chat_boundary(tmp_path: Path) -> None:
    gateway = FakeLLM()
    runtime = AgentRuntime(
        model_gateway=gateway,
        skill_loader=SkillLoader(skills_dir=tmp_path / "skills"),
    )

    content, model_used, fallback_reason = await runtime._chat_with_fallback(
        primary_model="writer",
        fallback_model=None,
        messages=[{"role": "user", "content": "draft"}],
    )

    assert content == "MVP 运行完成。"
    assert model_used == "writer"
    assert fallback_reason is None
    assert runtime.model_gateway is gateway
    assert runtime.llm is gateway
    assert gateway.calls == ["writer"]


@pytest.mark.anyio
async def test_runtime_preflight_blocks_before_model_or_tool_execution(tmp_path: Path) -> None:
    llm = FakeLLM()
    control = ConnectionControlPlane(
        path=tmp_path / "connections.json",
        secret_store=LocalEncryptedSecretStore(path=tmp_path / "secrets.json", key_path=tmp_path / "secret.key"),
    )
    registry = CapabilityRegistry(tmp_path / "capabilities")
    state_store = CapabilityStateStore(tmp_path / "capability-state.json")
    kernel = OSKernel(registry=registry, state_store=state_store, control_plane=control)
    materializer = RuntimeMaterializer(
        control_plane=control,
        workspace_root=tmp_path,
        capability_registry=registry,
        capability_state_store=state_store,
        os_kernel=kernel,
    )
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(skills_dir=tmp_path / "skills"),
        runtime_context_factory=materializer.build_context,
    )

    result = await runtime.run(task="解释 ROIC", metadata={"tenant_id": "tenant-a"})

    assert llm.calls == []
    assert result["route"] == "preflight_blocked"
    assert result["run_status"] == "blocked"
    assert result["review"]["status"] == "REJECT_FATAL"
    assert "Patroller Gate Report" in result["final"]
    assert any(issue["code"] == "missing_model_provider" for issue in result["metadata"]["runtime_validation_issues"])


def test_preserve_runtime_metadata_restores_os_plan_and_tenant() -> None:
    initial = {
        "tenant_id": "tenant-a",
        "os_plan": {"tenant_id": "tenant-a", "intent": "evidence_research"},
        "capability_runtime": {"capabilities": {"evidence-research": {}}},
    }
    result = preserve_runtime_metadata({"metadata": {"domain_workflow": {"graph_mode": "evidence_research"}}}, initial)

    assert result["tenant_id"] == "tenant-a"
    assert result["metadata"]["tenant_id"] == "tenant-a"
    assert result["metadata"]["os_plan"]["intent"] == "evidence_research"
    assert result["metadata"]["domain_workflow"]["graph_mode"] == "evidence_research"


def fake_wrds_company_financials(**_kwargs) -> ToolResult:
    return ToolResult(
        True,
        {
            "status": "matched_with_financials",
            "company": {
                "gvkey": "001000",
                "tic": "GIGD",
                "conm": "GigaDevice",
                "sic": "3674",
                "naics": "334413",
                "fyr": 12,
            },
            "candidates": [
                {
                    "gvkey": "001000",
                    "tic": "GIGD",
                    "conm": "GigaDevice",
                    "match_score": 100,
                }
            ],
            "rows": [
                {
                    "gvkey": "001000",
                    "tic": "GIGD",
                    "conm": "GigaDevice",
                    "fyear": 2025,
                    "datadate": "2025-12-31",
                    "sale": 1000,
                    "cogs": 600,
                    "dp": 50,
                    "oiadp": 180,
                    "ni": 150,
                    "epsfi": 1.5,
                    "oancf": 200,
                    "capx": 80,
                    "at": 2000,
                    "lt": 800,
                    "dltt": 300,
                    "dlc": 20,
                    "che": 250,
                    "seq": 1200,
                    "csho": 100,
                    "prcc_f": 20,
                    "invt": 120,
                    "indfmt": "INDL",
                    "datafmt": "STD",
                    "consol": "C",
                    "popsrc": "D",
                    "curcd": "USD",
                    "calculated": {"free_cash_flow": 120},
                }
            ],
            "row_count": 1,
            "quarterly_rows": [],
            "quarterly_row_count": 0,
            "data_packages": ["company_identity", "annual_financials_10y"],
        },
    )


def fake_wrds_registry(tmp_path: Path) -> ToolRegistry:
    registry = ToolRegistry(workspace_root=tmp_path, wrds_enabled=True)
    registry._tools["wrds_company_financials"] = fake_wrds_company_financials
    return registry


class OrchestratorFailingLLM(FakeLLM):
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if model == "orchestrator":
            self.calls.append(model)
            return (
                '{"translated_task":"Build a FastAPI endpoint","english_search_query":"Build a FastAPI endpoint",'
                '"task_type":"coding","required_agents":{},"steps":[]}'
            )
        return await super().chat(model=model, messages=messages, temperature=temperature)


class SimpleQuestionLLM(FakeLLM):
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(model)
        if model == "orchestrator":
            return (
                '{"translated_task":"Explain ROIC","english_search_query":"Explain ROIC",'
                '"task_type":"general","depth":"direct",'
                '"required_agents":{"memory":false,"research":false,"quant":false,"domain":true,"critic":false,"writer":false,"final_judge":false},'
                '"rationale":"Simple concept explanation; no tools or specialist agents needed.",'
                '"steps":[{"id":"direct","title":"Direct answer","action":"Answer from general knowledge","tool_calls":[]}]}'
            )
        if model == "writer":
            return "ROIC 是投入资本回报率。"
        return await super().chat(model=model, messages=messages, temperature=temperature)


class RecoverableFailureLLM(FakeLLM):
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(model)
        if model == "research_primary":
            raise RuntimeError("LiteLLM returned HTTP 400: contentFilter 1301")
        if model == "quant_primary":
            raise RuntimeError("LiteLLM request timed out after 300s (ReadTimeout)")
        if model == "research_fallback":
            return (
                '{"status":"completed","sources":[{"title":"Fallback source","url":"https://example.com",'
                '"key_facts":["fallback fact"],"reliability":"medium"}],"key_facts":["fallback fact"],'
                '"evidence_gaps":[],"reliability":"medium","source_grounding":"search_snippets_only"}'
            )
        if model == "quant_fallback":
            return (
                '{"status":"insufficient_data","assumptions":["fallback"],"formulas":["ROIC = NOPAT / IC"],'
                '"calculations":["inputs missing"],"metrics":[],"sensitivity":[],'
                '"missing_data":["NOPAT"],"data_quality":"partial"}'
            )
        return await super().chat(model=model, messages=messages, temperature=temperature)


class CommitteeLLM(FakeLLM):
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(model)
        if model == "orchestrator":
            return (
                '{"translated_task":"Analyze GigaDevice","english_search_query":"GigaDevice annual report financial results",'
                '"task_type":"investment","depth":"deep","committee":true,'
                '"required_agents":{"memory":false,"research":true,"quant":true,"domain":false,"critic":true,"writer":true,"final_judge":true},'
                '"rationale":"Investment research requires committee review.",'
                '"steps":[{"id":"direct","title":"Use existing evidence","action":"No external tool in this unit test","tool_calls":[]}]}'
            )
        if model == "research_agent":
            return (
                '{"status":"completed","sources":[{"title":"Annual report","url":"https://example.com/ar",'
                '"key_facts":["revenue grew"],"reliability":"medium"}],"key_facts":["revenue grew"],'
                '"evidence_gaps":["latest filing text"],"reliability":"medium","source_grounding":"search_snippets_only"}'
            )
        if model == "quant_agent":
            return (
                '{"status":"insufficient_data","assumptions":["public snippets only"],"formulas":["ROIC = NOPAT / IC"],'
                '"calculations":["No full statements available"],"metrics":[],"sensitivity":[],'
                '"missing_data":["NOPAT"],"data_quality":"partial"}'
            )
        if model in {
            "cio_agent",
            "data_auditor_agent",
            "fundamental_analyst_agent",
            "quant_research_agent",
            "industry_strategy_agent",
            "market_execution_agent",
            "risk_manager_agent",
            "red_team_agent",
        }:
            hard_veto = "true" if model == "risk_manager_agent" else "false"
            score = 35 if model == "risk_manager_agent" else 60
            return (
                '{"status":"completed","sub_plan":["review evidence"],"thesis":"'
                + model
                + ' view","score":'
                + str(score)
                + ',"confidence":0.6,"evidence_used":["revenue grew"],'
                '"missing_data":["full filing"],"risks":["limited evidence"],"hard_veto":'
                + hard_veto
                + ',"evidence_requests":["annual report"],"role_assessment":{"summary":"role-specific view"}}'
            )
        if model == "committee_challenge":
            return (
                '{"round":1,"continue_discussion":false,"turns":[{"speaker":"risk_manager_agent",'
                '"target":"quant_research_agent","claim":"risk constrains valuation","challenge":"valuation lacks filings",'
                '"response":"lower confidence until filings are fetched","score_delta":-5,"confidence_delta":-0.1}]}'
            )
        if model == "investment_committee":
            return (
                '{"status":"completed","decision":"Watchlist only until filings are fetched.",'
                '"final_decision":"Watch","conviction":"Low","position_size":"0%","time_horizon":"1 year",'
                '"core_thesis":"Evidence is not yet strong enough for capital allocation.",'
                '"key_evidence":["revenue grew"],"main_risk":"limited source grounding",'
                '"invalidation_point":"audited filings contradict growth thesis",'
                '"consensus":["business requires more evidence"],"dissent":["valuation is inconclusive"],'
                '"hard_vetoes":["risk_manager_agent"],"scorecard":[{"agent":"risk_manager_agent","score":35,"confidence":0.6,"hard_veto":true}],'
                '"confidence":0.55,"open_questions":["latest margins"],"evidence_limitations":["search snippets only"]}'
            )
        if model == "critic":
            return '{"status":"needs_sources","issues":["source gap"],"overclaims":[],"data_errors":[],"citation_gaps":["search snippets only"],"minimal_fixes":[],"summary":"Limit claims."}'
        if model == "writer":
            return "WRDS-only 模式：WRDS-only preliminary view。委员会结论：暂列观察名单。"
        if model == "final_judge":
            return "WRDS-only 模式：WRDS-only preliminary view。委员会结论：暂列观察名单，等待财报正文。"
        return await super().chat(model=model, messages=messages, temperature=temperature)


class CommitteeFallbackLLM(CommitteeLLM):
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        if model == "glm-fundamental":
            self.calls.append(model)
            raise RuntimeError("LiteLLM returned HTTP 429: rate limit")
        if model == "minimax-fallback":
            self.calls.append(model)
            return (
                '{"status":"completed","sub_plan":["fallback review"],"thesis":"fallback fundamental view",'
                '"score":52,"confidence":0.45,"evidence_used":["wrds metrics"],'
                '"missing_data":["filing"],"risks":["fallback used"],"hard_veto":false,'
                '"evidence_requests":["company filing"],"role_assessment":{"summary":"fallback view"}}'
            )
        if model == "glm-investment":
            self.calls.append(model)
            raise RuntimeError("LiteLLM returned HTTP 429: rate limit")
        if model == "minimax-investment-fallback":
            self.calls.append(model)
            return (
                '{"status":"completed","decision":"Fallback chair says watchlist only.",'
                '"final_decision":"Watch","conviction":"Low","position_size":"0%","time_horizon":"1 year",'
                '"core_thesis":"Fallback synthesis preserves limitations.",'
                '"key_evidence":["wrds metrics"],"main_risk":"rate limited primary chair",'
                '"invalidation_point":"verified filings change evidence",'
                '"consensus":["fallback used"],"dissent":[],"hard_vetoes":[],'
                '"scorecard":[{"agent":"fundamental_analyst_agent","score":52,"confidence":0.45,"hard_veto":false}],'
                '"confidence":0.4,"open_questions":["filing"],"evidence_limitations":["fallback synthesis"]}'
            )
        return await super().chat(model=model, messages=messages, temperature=temperature)


class MiniMaxFallbackLLM(FakeLLM):
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(model)
        if model == "minimax-critic":
            raise RuntimeError("MiniMax returned HTTP 400: context window exceeds limit (2013)")
        if model == "glm-critic-fallback":
            return (
                '{"status":"pass","issues":[],"overclaims":[],"data_errors":[],"citation_gaps":[],'
                '"minimal_fixes":[],"summary":"Fallback critic completed after MiniMax context failure."}'
            )
        return await super().chat(model=model, messages=messages, temperature=temperature)


def write_skill(root: Path) -> None:
    skill_dir = root / "fastapi-api"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: fastapi-api
description: Use this skill for FastAPI APIs and tests.
---

# FastAPI API Skill
""",
        encoding="utf-8",
    )


@pytest.mark.anyio
async def test_agent_runtime_runs_graph(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    write_skill(tmp_path)
    llm = FakeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(
            orchestrator="orchestrator",
            research_agent="research_agent",
            quant_agent="quant_agent",
            domain_expert="domain_expert",
            critic="critic",
            writer="writer",
            final_judge="final_judge",
        ),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime.run(task="Build a FastAPI endpoint")

    assert result["route"] == "coding"
    assert result["selected_skills"][0]["name"] == "fastapi-api"
    assert result["plan"][0]["title"] == "Inspect"
    assert result["execution_log"][0]["tool_calls"][0]["name"] == "list_files"
    assert result["execution_log"][0]["tool_calls"][0]["result"]["ok"] is True
    assert result["research_brief"]["status"] == "skipped"
    assert result["quant_analysis"]["status"] == "skipped"
    assert result["domain_analysis"]["domain"] == "coding"
    assert result["review"]["status"] == "pass"
    assert result["final"] == "MVP 运行完成。"
    assert [metric["agent"] for metric in result["agent_metrics"]] == [
        "orchestrator",
        "executor",
        "domain_expert",
        "critic",
        "writer",
        "final_judge",
    ]
    assert result["agent_metrics"][0]["model"] == "orchestrator"
    assert all("duration_ms" in metric for metric in result["agent_metrics"])
    assert {metric["status"] for metric in result["agent_metrics"]} == {"completed"}
    assert next(metric for metric in result["agent_metrics"] if metric["agent"] == "executor")["model"] == "minimax-m2.7"
    assert llm.calls == ["orchestrator", "domain_expert", "critic", "writer", "final_judge"]


@pytest.mark.anyio
async def test_simple_question_uses_direct_route_without_specialists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = SimpleQuestionLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(orchestrator="orchestrator", writer="writer"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime.run(task="解释什么是 ROIC。")

    assert result["route"] == "general"
    assert result["execution_log"] == []
    assert result["research_brief"]["status"] == "skipped"
    assert result["quant_analysis"]["status"] == "skipped"
    assert result["domain_analysis"]["status"] == "skipped"
    assert result["review"]["status"] == "skipped"
    assert [metric["agent"] for metric in result["agent_metrics"]] == ["orchestrator", "writer"]
    assert llm.calls == ["orchestrator", "writer"]


@pytest.mark.anyio
async def test_explicit_wrds_request_bypasses_general_graph(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    monkeypatch.setenv("WRDS_USERNAME", "user")
    monkeypatch.setenv("WRDS_PASSWORD", "secret")
    llm = FakeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(orchestrator="orchestrator"),
        tool_registry=ToolRegistry(workspace_root=tmp_path, wrds_enabled=True),
    )

    result = await runtime.run(task="WRDS status", metadata={"wrds_action": "status"})

    assert result["route"] == "wrds"
    assert result["orchestration"]["task_type"] == "wrds"
    assert result["wrds_result"]["ok"] is True
    assert result["agent_outputs"] == {}
    assert result["agent_decision"]["status"] == "skipped"
    assert "agent decision" in result["agent_decision"]["reason"]
    assert [metric["agent"] for metric in result["agent_metrics"]] == ["wrds_agent"]
    assert llm.calls == []


def test_wrds_routing_uses_capability_runtime_entrypoints() -> None:
    class LegacyDirectWrdsSkill:
        name = "wrds-data"

    direct_wrds_capability = SimpleNamespace(
        name="quality-data",
        capability_types=["professional_financial_database"],
    )
    investment_capability = SimpleNamespace(
        name="quality-investment",
        capability_types=["investment.research"],
    )

    assert should_run_wrds_agent({"orchestration": {"task_type": "wrds"}}) is True
    assert (
        should_run_wrds_agent(
            {
                "orchestration": {"task_type": "general"},
                "selected_skills": [
                    {
                        "name": "quality-data",
                        "capability_types": ["professional_financial_database"],
                    }
                ],
            }
        )
        is True
    )
    assert (
        should_run_wrds_agent(
            {
                "orchestration": {"task_type": "general"},
                "selected_skills": [
                    {
                        "name": "quality-investment",
                        "capability_types": ["investment.research"],
                    }
                ],
            }
        )
        is False
    )
    assert (
        should_bypass_graph_to_wrds(task="status", metadata={}, skills=[LegacyDirectWrdsSkill()])
        is True
    )
    assert should_bypass_graph_to_wrds(task="status", metadata={}, skills=[direct_wrds_capability]) is True
    assert (
        should_bypass_graph_to_wrds(task="status", metadata={}, skills=[investment_capability])
        is False
    )
    assert build_direct_wrds_orchestration()["routing_source"] == "capability_runtime_routing"


def test_wrds_routing_legacy_fallback_is_separate_compatibility_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class LegacyDirectWrdsSkill:
        name = "wrds-data"

    monkeypatch.setattr(graph_module, "wrds_runtime_routing_entrypoint", lambda name: None)

    assert should_run_wrds_agent({"orchestration": {"task_type": "wrds"}}) is True
    assert should_bypass_graph_to_wrds(task="select * from comp.company", metadata={}, skills=[]) is True
    assert should_bypass_graph_to_wrds(task="status", metadata={}, skills=[LegacyDirectWrdsSkill()]) is True
    assert build_direct_wrds_orchestration()["routing_source"] == "legacy_wrds_routing_fallback"


def test_generic_workflow_host_runs_only_for_deferred_descriptor_workflows() -> None:
    workflow = {
        "graph_mode": "toy_review",
        "node_entrypoints": {"toy_scout": "workflow.py:toy_scout_node"},
    }
    metadata = {
        "capability_runtime": {
            "capabilities": {
                "toy-review": {
                    "entrypoints": {
                        "workflow": workflow,
                    }
                }
            }
        }
    }

    assert should_run_workflow_host(
        {
            "metadata": metadata,
            "domain_workflow": {
                "graph_mode": "toy_review",
                "status": "deferred",
                "deferred_to_graph_node": "workflow_host",
            },
        }
    )
    assert should_run_workflow_host(
        {
            "metadata": metadata,
            "defer_generic_workflow_host": True,
        }
    )
    assert not should_run_workflow_host(
        {
            "metadata": metadata,
            "domain_workflow": {
                "graph_mode": "toy_review",
                "status": "executed",
                "graph_host_node": "workflow_host",
            },
        }
    )
    compliance_manifest = CapabilityRegistry().get("compliance-workflow")
    assert compliance_manifest is not None
    compliance_workflow = load_capability_descriptor(compliance_manifest)["entrypoints"]["workflow"]
    compliance_metadata = {
        "capability_runtime": {
            "capabilities": {
                "compliance-workflow": {
                    "entrypoints": {
                        "workflow": compliance_workflow,
                    }
                }
            }
        }
    }
    assert should_run_workflow_host(
        {
            "metadata": compliance_metadata,
            "domain_workflow": {
                "graph_mode": "compliance_workflow",
                "status": "deferred",
                "deferred_to_graph_node": "workflow_host",
            },
        }
    )
    assert not should_run_workflow_host(
        {
            "metadata": compliance_metadata,
            "domain_workflow": {
                "graph_mode": "compliance_workflow",
                "status": "planned",
                "source": "capability_workflow_orchestration_entrypoint",
            },
            "defer_generic_workflow_host": True,
        }
    )
    assert not should_run_workflow_host(
        {
            "metadata": {
                "capability_runtime": {
                    "capabilities": {
                        "value-investing-research": {
                            "entrypoints": {
                                "workflow": {
                                    "graph_mode": "investment_committee",
                                    "node_entrypoints": {"research": "workflow.py:research_node"},
                                },
                            }
                        }
                    }
                }
            },
            "defer_generic_workflow_host": True,
        }
    )


def test_normalized_run_result_redacts_raw_wrds_rows() -> None:
    result = normalize_run_result(
        {
            "execution_log": [
                {
                    "step_id": "wrds",
                    "tool_calls": [
                        {
                            "name": "wrds_company_financials",
                            "args": {"query": "AAPL"},
                            "result": {
                                "ok": True,
                                "data": {
                                    "company": {"tic": "AAPL"},
                                    "rows": [{"sale": 1}],
                                    "quarterly_rows": [{"saleq": 1}],
                                    "row_count": 1,
                                    "quarterly_row_count": 1,
                                },
                            },
                        }
                    ],
                }
            ],
            "wrds_result": {
                "ok": True,
                "data": {
                    "company_financials": {
                        "company": {"tic": "AAPL"},
                        "rows": [{"sale": 1}],
                        "quarterly_rows": [{"saleq": 1}],
                        "row_count": 1,
                    }
                },
            },
        }
    )

    financials = result["wrds_result"]["data"]["company_financials"]
    assert financials["rows"]["redacted"] is True
    assert financials["rows"]["count"] == 1
    assert financials["row_count"] == 1
    call_data = result["execution_log"][0]["tool_calls"][0]["result"]["data"]
    assert call_data["quarterly_rows"]["redacted"] is True


def test_normalized_run_result_exposes_generic_agent_state_with_legacy_mirror() -> None:
    result = normalize_run_result(
        {
            "agent_outputs": {
                "generic_reviewer": {"status": "completed", "thesis": "Generic view."}
            },
            "committee_outputs": {
                "legacy_reviewer": {"status": "completed", "thesis": "Legacy view."}
            },
            "agent_decision": {"decision": "Approve generic result."},
            "committee_decision": {"decision": "Reject legacy result."},
        }
    )

    assert result["agent_outputs"]["generic_reviewer"]["thesis"] == "Generic view."
    assert result["agent_decision"]["decision"] == "Approve generic result."
    assert result["committee_outputs"]["legacy_reviewer"]["thesis"] == "Legacy view."
    assert result["committee_decision"]["decision"] == "Reject legacy result."


def test_model_contexts_use_generic_agent_state_and_explicit_legacy_lineage() -> None:
    state = {
        "task": "Review toy artifact",
        "plan": [],
        "execution_log": [],
        "agent_outputs": {
            "toy_reviewer": {"status": "completed", "thesis": "Generic toy review."}
        },
        "committee_outputs": {
            "legacy_reviewer": {"status": "completed", "thesis": "Legacy review."}
        },
        "agent_decision": {"decision": "Approve toy artifact."},
        "committee_decision": {"decision": "Reject legacy artifact."},
    }

    for context_json in (
        graph_module.critic_context(state),
        graph_module.writer_context(state),
        graph_module.final_judge_context(state),
    ):
        payload = json.loads(context_json)

        assert "committee_outputs" not in payload
        assert "committee_decision" not in payload
        assert payload["agent_outputs"]["toy_reviewer"]["thesis"] == "Generic toy review."
        assert payload["legacy_agent_outputs"]["legacy_reviewer"]["thesis"] == "Legacy review."
        assert payload["agent_decision"]["decision"] == "Approve toy artifact."
        assert payload["legacy_agent_decision"]["decision"] == "Reject legacy artifact."


def test_value_investing_support_prefers_generic_agent_outputs_over_legacy_state() -> None:
    state = {
        "task": "Review value committee output",
        "agent_outputs": {
            "generic_agent": {
                "status": "completed",
                "thesis": "Generic committee view.",
                "score": 88,
                "confidence": "medium",
                "hard_veto": True,
                "missing_data": ["generic missing"],
                "evidence_requests": ["generic request"],
            }
        },
        "committee_outputs": {
            "legacy_agent": {
                "status": "completed",
                "thesis": "Legacy committee view should not win.",
                "score": 10,
                "confidence": "low",
                "hard_veto": False,
                "missing_data": ["legacy missing"],
            }
        },
        "discussion_transcript": [],
    }

    discussion_payload = json.loads(
        graph_module.committee_discussion_context(state, transcript=[], round_number=1)
    )
    investment_payload = json.loads(graph_module.investment_committee_context(state))

    for payload in (discussion_payload, investment_payload):
        assert payload["agent_outputs"]["generic_agent"]["thesis"] == "Generic committee view."
        assert "legacy_agent" not in payload["agent_outputs"]
        assert payload["committee_outputs"] == payload["agent_outputs"]

    pressure = graph_module.committee_discussion_pressure(state)
    assert pressure["hard_vetoes"] == ["generic_agent"]
    assert pressure["missing_count"] == 2

    fallback = graph_module.fallback_agent_decision(state, summary="fallback")
    assert fallback["hard_vetoes"] == ["generic_agent"]
    assert fallback["evidence_limitations"] == ["generic missing", "generic request"]
    assert graph_module.fallback_committee_decision(state, summary="fallback") == fallback

    scorecard = {item["agent"]: item for item in normalize_scorecard(None, state=state)}
    assert scorecard["generic_agent"]["score"] == 88
    assert scorecard["generic_agent"]["hard_veto"] is True
    assert "legacy_agent" not in scorecard


def test_wrds_result_collector_uses_runtime_descriptor() -> None:
    manifest = CapabilityRegistry().get("wrds-financial-data")
    assert manifest is not None
    runtime_nodes = load_capability_descriptor(manifest)["entrypoints"]["runtime_nodes"]
    execution_log = [
        {
            "step_id": "wrds-company-financials",
            "tool_calls": [
                {
                    "name": "wrds_company_financials",
                    "result": {
                        "ok": True,
                        "data": {
                            "status": "matched_with_financials",
                            "company": {"tic": "AAPL"},
                            "rows": [{"sale": 1}],
                            "quarterly_rows": [],
                            "row_count": 1,
                            "table": "comp.funda",
                        },
                    },
                }
            ],
        }
    ]
    state = {
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    "wrds-financial-data": {"entrypoints": {"runtime_nodes": runtime_nodes}},
                }
            }
        }
    }

    result = collect_wrds_results(execution_log, state=state)

    assert result["data"]["company_financials"]["company"]["tic"] == "AAPL"
    assert result["result_collector_trace"][0]["source"] == "capability_result_collector"
    provider_result = result["data_source_results"][0]
    assert provider_result["provider_id"] == "wrds"
    assert provider_result["dataset_kind"] == "financial_fundamentals"
    assert provider_result["normalized_payload"]["company"]["tic"] == "AAPL"
    assert provider_result["normalized_payload"]["row_count"] == 1
    assert "rows" not in provider_result["normalized_payload"]
    assert "rows" not in provider_result
    assert result["provider_results"] == result["data_source_results"]


def test_wrds_argument_normalizer_uses_runtime_descriptor() -> None:
    manifest = CapabilityRegistry().get("wrds-financial-data")
    assert manifest is not None
    runtime_nodes = load_capability_descriptor(manifest)["entrypoints"]["runtime_nodes"]
    state = {
        "task": "ORCL",
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    "wrds-financial-data": {"entrypoints": {"runtime_nodes": runtime_nodes}},
                }
            }
        },
    }

    normalizer = wrds_argument_normalizer_from_state(state, "wrds_company_search")
    assert normalizer is not None
    args = normalizer(args={}, state=state, step={"title": "Resolve ORCL"}, tool_name="wrds_company_search")

    assert args == {"query": "ORCL", "max_results": 8}


@pytest.mark.anyio
async def test_agent_runtime_audits_orchestrator_fallback_metrics(tmp_path: Path, monkeypatch) -> None:
    audit_path = tmp_path / "agent_runs.jsonl"
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "true")
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(audit_path))
    write_skill(tmp_path)
    runtime = AgentRuntime(
        llm=OrchestratorFailingLLM(),
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(orchestrator="orchestrator"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime.run(task="Build a FastAPI endpoint")

    record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert record["status"] == "degraded"
    assert result["route"] == "coding"
    assert result["agent_metrics"][0]["agent"] == "orchestrator"
    assert result["agent_metrics"][0]["status"] == "completed_with_fallback"
    assert "orchestrator response must include" in result["agent_metrics"][0]["failure_reason"]
    assert record["agent_metrics"][0]["status"] == "completed_with_fallback"


@pytest.mark.anyio
async def test_specialist_agents_return_structured_views(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(
            research_agent="research_agent",
            quant_agent="quant_agent",
            domain_expert="domain_expert",
        ),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    state = {
        "task": "药明康德",
        "translated_task": "WuXi AppTec",
        "english_search_query": "WuXi AppTec",
        "selected_skills": [{"name": "value-investing-research"}],
        "plan": [],
        "execution_log": [],
        "orchestration": {"required_agents": {"research": True, "quant": True, "domain": True}},
    }
    research = await runtime._research_agent(state)
    quant = await runtime._quant_agent({**state, **research})
    domain = await runtime._domain_expert({**state, **research, **quant})

    assert research["research_brief"]["key_facts"] == ["fact"]
    assert quant["quant_analysis"]["missing_data"] == ["FCF"]
    assert domain["domain_analysis"]["judgment"] == "Implementation looks scoped."


@pytest.mark.anyio
async def test_graph_node_prefers_capability_workflow_node_entrypoint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = FakeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(research_agent="research_agent"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    workflow = {
        "id": "toy-review.workflow",
        "capability_id": "toy-review",
        "graph_mode": "toy_review",
        "graph_nodes": ["research_agent"],
        "node_entrypoints": {"research_agent": "workflow.py:toy_scout_node"},
    }
    state = {
        "task": "Run toy review",
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    "toy-review": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
        "selected_skills": [{"name": "toy-review"}],
        "recovery_context": {"candidate_count": 2, "full_text_count": 1},
    }

    result = await runtime._research_agent(state)

    assert result["claim_type"] == "toy_claim"
    assert result["evidence_available"] is True
    assert llm.calls == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("capability_id", "graph_mode"),
    [
        ("evidence-research", "evidence_research"),
        ("compliance-workflow", "compliance_workflow"),
    ],
)
async def test_builtin_research_workflow_nodes_use_descriptor_entrypoints(
    tmp_path: Path,
    monkeypatch,
    capability_id: str,
    graph_mode: str,
) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = FakeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(research_agent="research_agent"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    manifest = CapabilityRegistry().get(capability_id)
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    assert workflow["graph_mode"] == graph_mode
    assert workflow["node_entrypoints"]["research_agent"] == "workflow.py:research_agent_node"
    state = {
        "task": "Verify this memo",
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    capability_id: {"entrypoints": {"workflow": workflow}},
                }
            }
        },
        "selected_skills": [{"name": capability_id}],
        "execution_log": [],
    }

    result = await runtime._research_agent(state)

    assert result["research_brief"]["key_facts"] == ["fact"]
    assert result["workflow_node_trace"][0]["source"] == "capability_workflow_node_entrypoint"
    assert result["workflow_node_trace"][0]["capability_id"] == capability_id


@pytest.mark.anyio
async def test_legacy_research_graph_mode_fallback_is_traced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = FakeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(research_agent="research_agent"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    workflow = {
        "id": "legacy-compliance.workflow",
        "graph_mode": "compliance_workflow",
        "graph_nodes": ["research_agent"],
    }
    state = {
        "task": "Audit policy controls",
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    "legacy-compliance": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
        "selected_skills": [{"name": "legacy-compliance"}],
        "execution_log": [],
    }

    result = await runtime._research_agent(state)

    assert result["research_brief"]["key_facts"] == ["fact"]
    assert result["workflow_node_trace"][0]["source"] == "legacy_graph_mode_node_fallback"
    assert result["workflow_node_trace"][0]["graph_mode"] == "compliance_workflow"


@pytest.mark.anyio
async def test_protocol_research_graph_node_requires_declared_entrypoint_before_legacy_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(research_agent="research_agent"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    workflow = {
        "id": "thin-compliance.workflow",
        "capability_id": "thin-compliance",
        "graph_mode": "compliance_workflow",
        "graph_nodes": ["research_agent"],
    }
    state = {
        "task": "Audit policy controls",
        "metadata": {
            "os_plan": {
                "intent_source": "capability_protocol_intent",
                "selected_capability_id": "thin-compliance",
                "swarm_plan": {
                    "protocol_source": "capability_manifest",
                    "capability_protocols": [
                        {"capability_id": "thin-compliance", "generated_legacy_protocol": False}
                    ],
                },
            },
            "capability_runtime": {
                "capabilities": {
                    "thin-compliance": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
        "selected_skills": [{"name": "thin-compliance"}],
        "execution_log": [],
    }

    with pytest.raises(CapabilityEntrypointError, match="thin-compliance.research_agent"):
        await runtime._research_agent(state)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "node",
    [
        "data_gate",
        "quant_agent",
        "domain_expert",
        "committee_opening",
        "committee_discussion",
        "investment_committee",
    ],
)
async def test_protocol_specialist_graph_nodes_require_declared_entrypoints_before_static_fallback(
    tmp_path: Path,
    monkeypatch,
    node: str,
) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(
            research_agent="research_agent",
            quant_agent="quant_agent",
            domain_expert="domain_expert",
        ),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    workflow = {
        "id": "thin-specialist.workflow",
        "capability_id": "thin-specialist",
        "graph_mode": "custom_protocol",
        "graph_nodes": [node],
    }
    state = {
        "task": "Run protocol specialist node",
        "metadata": {
            "os_plan": {
                "intent_source": "capability_protocol_intent",
                "selected_capability_id": "thin-specialist",
                "swarm_plan": {
                    "protocol_source": "capability_manifest",
                    "capability_protocols": [
                        {"capability_id": "thin-specialist", "generated_legacy_protocol": False}
                    ],
                },
            },
            "capability_runtime": {
                "capabilities": {
                    "thin-specialist": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
        "selected_skills": [{"name": "thin-specialist"}],
        "plan": [],
        "execution_log": [],
    }

    with pytest.raises(CapabilityEntrypointError, match=rf"thin-specialist\.{node}"):
        await getattr(runtime, f"_{node}")(state)


@pytest.mark.anyio
async def test_research_graph_node_manifest_backfill_precedes_legacy_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = FakeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(research_agent="research_agent"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    workflow = {
        "workflow_id": "compliance-workflow",
        "graph_mode": "compliance_workflow",
        "graph_nodes": ["research_agent"],
    }
    state = {
        "task": "Audit policy controls",
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    "compliance-workflow": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
        "selected_skills": [{"name": "compliance-workflow"}],
        "execution_log": [],
    }

    result = await runtime._research_agent(state)

    assert result["research_brief"]["key_facts"] == ["fact"]
    assert result["workflow_node_trace"][0]["source"] == "capability_workflow_node_entrypoint"
    assert result["workflow_node_trace"][0]["capability_id"] == "compliance-workflow"


@pytest.mark.anyio
async def test_research_and_quant_fallback_on_recoverable_llm_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = RecoverableFailureLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(
            research_agent="research_primary",
            research_agent_fallback="research_fallback",
            quant_agent="quant_primary",
            quant_agent_fallback="quant_fallback",
        ),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    state = {
        "task": "分析沪电股份",
        "translated_task": "分析沪电股份",
        "english_search_query": "沪电股份",
        "selected_skills": [{"name": "value-investing-research"}],
        "plan": [],
        "execution_log": [],
        "orchestration": {"required_agents": {"research": True, "quant": True}},
    }

    research = await runtime._research_agent(state)
    quant = await runtime._quant_agent({**state, **research})

    assert research["research_brief"]["key_facts"] == ["fallback fact"]
    assert quant["quant_analysis"]["missing_data"] == ["NOPAT"]
    assert llm.calls[:4] == ["research_primary", "research_fallback", "quant_primary", "quant_fallback"]


@pytest.mark.anyio
async def test_investment_task_runs_committee_branch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = CommitteeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(
            orchestrator="orchestrator",
            research_agent="research_agent",
            quant_agent="quant_agent",
            cio_agent="cio_agent",
            data_auditor_agent="data_auditor_agent",
            fundamental_analyst_agent="fundamental_analyst_agent",
            quant_research_agent="quant_research_agent",
            industry_strategy_agent="industry_strategy_agent",
            market_execution_agent="market_execution_agent",
            risk_manager_agent="risk_manager_agent",
            red_team_agent="red_team_agent",
            committee_challenge="committee_challenge",
            investment_committee="investment_committee",
            critic="critic",
            writer="writer",
            final_judge="final_judge",
        ),
        tool_registry=fake_wrds_registry(tmp_path),
    )

    result = await runtime.run(task="深度分析兆易创新", metadata={"os_plan": investment_os_plan()})

    assert result["orchestration"]["committee"] is True
    assert result["metadata"]["source_mode"] == "WRDS_ONLY"
    assert all(
        call.get("name") not in {"web_search", "provider_web_search", "fetch_url", "approved_source_fetch"}
        for step in result["plan"]
        for call in (step.get("tool_calls") or [])
        if isinstance(call, dict)
    )
    assert result["committee_outputs"]["data_auditor_agent"]["thesis"] == "data_auditor_agent view"
    assert result["committee_outputs"]["risk_manager_agent"]["hard_veto"] is True
    assert result["agent_outputs"]["data_auditor_agent"]["thesis"] == "data_auditor_agent view"
    assert result["agent_outputs"]["risk_manager_agent"]["hard_veto"] is True
    assert result["discussion_transcript"][0]["round"] == 0
    assert any(turn["round"] == 1 for turn in result["discussion_transcript"])
    assert result["committee_decision"]["hard_vetoes"] == ["risk_manager_agent"]
    assert result["committee_decision"]["final_decision"] == "Watch"
    assert result["committee_decision"]["position_size"] == "0%"
    assert result["agent_decision"]["hard_vetoes"] == ["risk_manager_agent"]
    assert result["agent_decision"]["final_decision"] == "Watch"
    assert result["domain_analysis"]["domain"] == "investment_committee"
    assert result["review"]["status"] == "needs_sources"
    assert "WRDS-only 模式" in result["final"]
    assert result["final"].endswith("委员会结论：暂列观察名单，等待财报正文。")
    metric_agents = [metric["agent"] for metric in result["agent_metrics"]]
    assert metric_agents[:5] == ["orchestrator", "executor", "data_gate", "research_agent", "quant_agent"]
    assert {
        "data_auditor_agent",
        "quant_research_agent",
        "risk_manager_agent",
        "committee_discussion",
        "investment_committee",
        "critic",
        "writer",
        "final_judge",
    }.issubset(metric_agents)


@pytest.mark.anyio
async def test_glm_committee_members_and_chair_fallback_to_minimax(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = CommitteeFallbackLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(
            orchestrator="orchestrator",
            research_agent="research_agent",
            quant_agent="quant_agent",
            cio_agent="cio_agent",
            data_auditor_agent="data_auditor_agent",
            fundamental_analyst_agent="glm-fundamental",
            quant_research_agent="quant_research_agent",
            industry_strategy_agent="industry_strategy_agent",
            market_execution_agent="market_execution_agent",
            risk_manager_agent="risk_manager_agent",
            red_team_agent="red_team_agent",
            committee_member_fallback="minimax-fallback",
            committee_challenge="committee_challenge",
            investment_committee="glm-investment",
            investment_committee_fallback="minimax-investment-fallback",
            critic="critic",
            writer="writer",
            final_judge="final_judge",
        ),
        tool_registry=fake_wrds_registry(tmp_path),
    )

    result = await runtime.run(task="深度分析兆易创新")

    assert "glm-fundamental" in llm.calls
    assert "minimax-fallback" in llm.calls
    assert "glm-investment" in llm.calls
    assert "minimax-investment-fallback" in llm.calls
    assert result["committee_outputs"]["fundamental_analyst_agent"]["thesis"] == "fallback fundamental view"
    assert result["agent_outputs"]["fundamental_analyst_agent"]["thesis"] == "fallback fundamental view"
    assert result["committee_decision"]["decision"] == "Fallback chair says watchlist only."
    assert result["agent_decision"]["decision"] == "Fallback chair says watchlist only."
    metrics = {metric["agent"]: metric for metric in result["agent_metrics"]}
    assert metrics["fundamental_analyst_agent"]["status"] == "completed_with_fallback"
    assert metrics["fundamental_analyst_agent"]["model"] == "minimax-fallback (fallback from glm-fundamental)"
    assert "429" in metrics["fundamental_analyst_agent"]["failure_reason"]
    assert metrics["investment_committee"]["status"] == "completed_with_fallback"
    assert metrics["investment_committee"]["model"] == "minimax-investment-fallback (fallback from glm-investment)"


@pytest.mark.anyio
async def test_minimax_roles_fallback_to_glm_on_context_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = MiniMaxFallbackLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(
            orchestrator="orchestrator",
            domain_expert="domain_expert",
            critic="minimax-critic",
            writer="writer",
            final_judge="final_judge",
            minimax_fallback_models="glm-critic-fallback",
        ),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime.run(task="Build a FastAPI endpoint")

    assert "minimax-critic" in llm.calls
    assert "glm-critic-fallback" in llm.calls
    assert result["review"]["status"] == "pass"
    critic_metric = next(metric for metric in result["agent_metrics"] if metric["agent"] == "critic")
    assert critic_metric["status"] == "completed_with_fallback"
    assert critic_metric["model"] == "glm-critic-fallback (fallback from minimax-critic)"
    assert "context window exceeds limit" in critic_metric["failure_reason"]


def test_parse_json_object_accepts_fenced_json() -> None:
    payload = parse_json_object('```json\n{"steps": []}\n```')

    assert payload == {"steps": []}


def test_parse_json_object_strips_reasoning_blocks() -> None:
    payload = parse_json_object('<think>{"draft": "ignore"}</think>\n{"steps": [{"id": "1"}]}')

    assert payload == {"steps": [{"id": "1"}]}


def test_parse_discussion_round_recovers_json_after_reasoning() -> None:
    parsed = parse_discussion_round(
        '<think>private chain</think>\n{"round":1,"turns":[{"speaker":"red_team_agent","target":"cio_agent","challenge":"show evidence","response":"need data"}],"continue_discussion":false}',
        round_number=1,
    )

    assert parsed["continue_discussion"] is False
    assert parsed["turns"][0]["speaker"] == "red_team_agent"
    assert parsed["turns"][0]["challenge"] == "show evidence"


def test_extract_tool_calls_from_malformed_executor_json() -> None:
    content = (
        '{"tool_calls": [{"index": 0, "name": "read_file", '
        '"args": {"path": "apple_domain_expert_analysis.md"}, '
        '"index": 1, "name": "read_file", '
        '"args": {"path": "apple_critic_review.md"}]}]}'
    )

    assert extract_tool_calls_from_text(content) == [
        {"name": "read_file", "args": {"path": "apple_domain_expert_analysis.md"}},
        {"name": "read_file", "args": {"path": "apple_critic_review.md"}},
    ]


def test_committee_output_recovers_malformed_json_score() -> None:
    content = (
        '{"status":"completed","thesis":"Attack the \\"operating leverage\\" thesis with '
        'unescaped "inner quotes" that break JSON","score":40,"confidence":"medium","hard_veto":false}'
    )

    parsed = parse_committee_output(content, member="red_team_agent")

    assert parsed["status"] in {"completed", "salvaged"}
    assert parsed["score"] == 40
    assert parsed["confidence"] == "medium"
    assert parsed["hard_veto"] is False


def test_scorecard_fills_missing_scores_from_outputs_and_transcript() -> None:
    state = {
        "committee_outputs": {
            "red_team_agent": {
                "status": "unstructured",
                "thesis": '{"score":40,"confidence":"medium","hard_veto":false}',
                "score": None,
                "confidence": "unknown",
                "hard_veto": False,
            },
            "risk_manager_agent": {
                "status": "completed",
                "score": 42,
                "confidence": "low",
                "hard_veto": False,
            },
        },
        "discussion_transcript": [
            {"round": 0, "speaker": "red_team_agent", "claim": '{"score":40,"confidence":"medium"}'}
        ],
    }

    scorecard = normalize_scorecard(
        [{"agent": "red_team_agent", "score": None, "confidence": "unknown", "hard_veto": False}],
        state=state,
    )

    by_agent = {item["agent"]: item for item in scorecard}
    assert by_agent["red_team_agent"]["score"] == 40
    assert by_agent["red_team_agent"]["confidence"] == "medium"
    assert by_agent["risk_manager_agent"]["score"] == 42


def test_stock_research_task_type_routes_to_investment_committee() -> None:
    orchestration = normalize_orchestration(
        {"task_type": "stock_research", "required_agents": {"research": True}},
        task="沪电股份",
        selected_skills=[],
    )

    assert orchestration["task_type"] == "investment"
    assert orchestration["committee"] is True
    assert orchestration["required_agents"]["quant"] is True


def test_selected_investment_capability_metadata_routes_to_committee_without_legacy_skill_name() -> None:
    selected = [SimpleNamespace(name="quality-investment", capability_types=["investment.research"])]

    orchestration = normalize_orchestration(
        {"required_agents": {}},
        task="prepare a neutral capability memo",
        selected_skills=selected,
    )

    assert orchestration["task_type"] == "investment"
    assert orchestration["committee"] is True
    assert orchestration["required_agents"]["wrds"] is True
    assert orchestration["required_agents"]["quant"] is True


def test_selected_direct_wrds_capability_metadata_infers_wrds_without_legacy_skill_name() -> None:
    selected = [SimpleNamespace(name="quality-data", capability_types=["professional_financial_database"])]

    orchestration = normalize_orchestration(
        {"required_agents": {}},
        task="check the data connection status",
        selected_skills=selected,
    )

    assert orchestration["task_type"] == "wrds"
    assert orchestration["required_agents"]["wrds"] is True
    assert orchestration["committee"] is False


def test_committee_member_specs_follow_user_selected_agent_catalog() -> None:
    state = {
        "task": "分析 AAPL",
        "metadata": {
            "committee_member_ids": ["risk_manager_agent"],
            "committee_agent_catalog": [
                {
                    "key": "data_auditor_agent",
                    "name": "Data Auditor",
                    "agent_type": "investment_committee_member",
                    "focus": "Audit data.",
                    "model_attr": "data_auditor_agent",
                    "order": 10,
                },
                {
                    "key": "risk_manager_agent",
                    "name": "Risk Manager",
                    "agent_type": "investment_committee_member",
                    "focus": "Find downside risk.",
                    "model_attr": "risk_manager_agent",
                    "order": 20,
                },
            ],
        },
    }

    specs = committee_member_specs_for_state(state)

    assert [spec["key"] for spec in specs] == ["risk_manager_agent"]
    assert specs[0]["focus"] == "Find downside risk."


def test_committee_member_specs_prefer_generic_agent_catalog_over_legacy() -> None:
    state = {
        "task": "Analyze a protocol-backed committee task",
        "metadata": {
            "agent_catalog": [
                {
                    "key": "generic_reviewer_agent",
                    "name": "Generic Reviewer",
                    "agent_type": "toy_review_member",
                    "committee_role": "toy_reviewer",
                    "focus": "Review capability-declared evidence.",
                    "model_attr": "generic_reviewer_agent",
                    "order": 5,
                }
            ],
            "committee_agent_catalog": [
                {
                    "key": "legacy_reviewer_agent",
                    "name": "Legacy Reviewer",
                    "agent_type": "toy_review_member",
                    "committee_role": "toy_reviewer",
                    "focus": "Legacy catalog should not win.",
                    "model_attr": "legacy_reviewer_agent",
                    "order": 1,
                }
            ],
        },
    }

    specs = committee_member_specs_for_state(state)

    assert [spec["key"] for spec in specs] == ["generic_reviewer_agent"]
    assert specs[0]["focus"] == "Review capability-declared evidence."


def test_committee_member_specs_use_shared_manifest_committee_semantics() -> None:
    state = {
        "task": "Analyze a protocol-backed committee task",
        "metadata": {
            "committee_agent_catalog": [
                {
                    "key": "toy_reviewer_agent",
                    "name": "Toy Reviewer",
                    "agent_type": "toy_review_member",
                    "committee_role": "toy_reviewer",
                    "focus": "Review toy evidence.",
                    "model_attr": "toy_reviewer_agent",
                    "order": 5,
                },
                {
                    "key": "plain_worker_agent",
                    "name": "Plain Worker",
                    "agent_type": "toy_worker",
                    "focus": "Do non-committee work.",
                    "model_attr": "plain_worker_agent",
                    "order": 10,
                },
            ],
        },
    }

    specs = committee_member_specs_for_state(state)

    assert [spec["key"] for spec in specs] == ["toy_reviewer_agent"]


def test_committee_member_specs_fallback_uses_enabled_capability_ids() -> None:
    state = {
        "task": "Review a toy capability packet",
        "metadata": {"enabled_capabilities": [{"id": "toy-review"}]},
    }

    specs = committee_member_specs_for_state(state)

    assert [spec["key"] for spec in specs] == [
        "toy_scout_agent",
        "toy_evidence_agent",
        "toy_reviewer_agent",
    ]
    assert {spec.get("capability_id") for spec in specs} == {"toy-review"}


def test_committee_member_order_uses_declared_order_not_agent_name_special_case() -> None:
    source = Path("capabilities/value-investing-research/support.py").read_text(encoding="utf-8")

    assert '"data_auditor_agent"' not in source
    assert "investment_committee_member" not in source
    assert committee_member_order({"key": "data_auditor_agent", "order": 25}) == 25
    assert committee_member_order({"key": "custom_auditor", "order": 5}) == 5


def test_committee_member_model_lookup_uses_manifest_model_resolver() -> None:
    source = Path("capabilities/value-investing-research/runtime_nodes.py").read_text(encoding="utf-8")

    assert "model_config.model_for(model_attr" in source
    assert "getattr(runtime.model_config, model_attr" not in source


def test_investment_company_research_task_type_routes_to_committee() -> None:
    orchestration = normalize_orchestration(
        {
            "task_type": "investment/company_research",
            "depth": "comprehensive",
            "required_agents": {"wrds": True, "research": True, "quant": True},
        },
        task="英伟达",
        selected_skills=[],
    )

    assert orchestration["task_type"] == "investment"
    assert orchestration["committee"] is True
    assert orchestration["required_agents"] == {
        "memory": False,
        "wrds": True,
        "research": True,
        "quant": True,
        "domain": False,
        "critic": True,
        "writer": True,
        "final_judge": True,
    }


def test_committee_output_accepts_unstructured_text() -> None:
    output = parse_committee_output("Need more filings before deciding.", member="data_auditor_agent")

    assert output["status"] == "unstructured"
    assert output["member"] == "data_auditor_agent"
    assert output["thesis"] == "Need more filings before deciding."
    assert output["emitted_signals"] == []


def test_committee_output_preserves_sanitized_emitted_signals() -> None:
    output = parse_committee_output(
        json.dumps(
            {
                "status": "completed",
                "thesis": "Valuation needs more support.",
                "emitted_signals": [
                    {
                        "type": "risk",
                        "target": "valuation",
                        "content": "No TTM multiple in metric registry.",
                        "api_key": "must-not-pass-through",
                    }
                ],
            }
        ),
        member="quant_research_agent",
    )

    assert output["emitted_signals"] == [
        {"type": "risk", "target": "valuation", "content": "No TTM multiple in metric registry."}
    ]


def test_parse_plan_accepts_tool_calls_inside_action() -> None:
    plan = parse_plan(
        '{"steps":[{"id":"1","title":"List","action":{"tool_calls":[{"name":"list_files","args":{"path":"."}}]}}]}'
    )

    assert plan[0]["tool_calls"] == [{"name": "list_files", "args": {"path": "."}}]


def test_parse_plan_accepts_tool_aliases_and_skips_empty_calls() -> None:
    plan = parse_plan(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "1",
                        "title": "Search",
                        "action": "Search public sources",
                        "tools": ["web_search", {"name": ""}, {}],
                    }
                ]
            }
        )
    )

    assert plan[0]["tool_calls"] == [{"name": "web_search", "args": {}}]


def test_parse_plan_accepts_openai_function_tool_call_shape() -> None:
    plan = parse_plan(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "1",
                        "title": "Search",
                        "action": "Search public sources",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "web_search",
                                    "arguments": '{"query":"GigaDevice annual report financial results","max_results":5}',
                                }
                            }
                        ],
                    }
                ]
            }
        )
    )

    assert plan[0]["tool_calls"] == [
        {"name": "web_search", "args": {"query": "GigaDevice annual report financial results", "max_results": 5}}
    ]


def test_web_research_step_is_inserted_when_orchestrator_misses_it() -> None:
    plan = [{"id": "1", "title": "Analyze", "action": "Analyze available context", "tool_calls": []}]

    updated = ensure_required_web_research_step(
        plan,
        task="调研 LangGraph 最新文档",
        english_search_query="LangGraph release notes",
        selected_skills=[{"name": "web-research"}],
    )

    assert updated[0]["tool_calls"] == [
        {"name": "web_search", "args": {"query": "LangGraph release notes", "max_results": 5}}
    ]
    assert updated[1] == plan[0]


def test_web_research_step_preserves_original_language_by_default() -> None:
    plan = [{"id": "1", "title": "Analyze", "action": "Analyze available context", "tool_calls": []}]

    updated = ensure_required_web_research_step(
        plan,
        task="调研杭州旅游",
        selected_skills=[{"name": "web-research"}],
    )

    assert updated[0]["tool_calls"] == [{"name": "web_search", "args": {"query": "调研杭州旅游", "max_results": 5}}]


def test_value_investing_step_does_not_insert_web_research() -> None:
    plan = [{"id": "1", "title": "Analyze", "action": "Analyze available context", "tool_calls": []}]

    updated = ensure_required_web_research_step(
        plan,
        task="分析药明康德",
        english_search_query="药明康德",
        selected_skills=[{"name": "value-investing-research"}],
        preferred_web_search_tool="provider_web_search",
        source_mode="WRDS_ONLY",
    )

    assert updated == plan


def test_wrds_only_source_mode_does_not_insert_web_research() -> None:
    plan = [{"id": "1", "title": "Analyze", "action": "Analyze available context", "tool_calls": []}]

    updated = ensure_required_web_research_step(
        plan,
        task="SNDK",
        english_search_query="SNDK investment analysis",
        selected_skills=[{"name": "value-investing-research"}],
        preferred_web_search_tool="provider_web_search",
        source_mode="WRDS_ONLY",
    )

    assert updated == plan


def test_source_mode_orchestration_guidance_uses_declared_tool_policy_text() -> None:
    guidance = source_mode_orchestration_guidance(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {
                            "source_mode": "WRDS_ONLY",
                            "source_policy_blocked_tool_targets": ["tool:custom_news_api"],
                            "source_mode_guidance": "Use {source_mode}; blocked tools: {blocked_tools}.",
                        }
                    }
                }
            }
        }
    )

    assert guidance == {
        "instruction": "Use WRDS_ONLY; blocked tools: custom_news_api.",
        "trace": {
            "source": "capability_tool_policy_source_mode",
            "source_mode": "WRDS_ONLY",
            "blocked_tool_targets": ["tool:custom_news_api"],
            "blocked_tool_target_source": "capability_tool_policy_source_mode",
        },
    }


def test_source_mode_orchestration_guidance_uses_legacy_template_without_declared_text() -> None:
    guidance = source_mode_orchestration_guidance(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {"source_mode": "WRDS_ONLY"},
                    }
                }
            }
        }
    )

    assert guidance is not None
    assert guidance["trace"]["source"] == "legacy_source_mode_tool_guidance"
    assert guidance["trace"]["blocked_tool_target_source"] == "legacy_source_policy_tool_targets"
    assert "web_search" in guidance["instruction"]
    assert "tool:web_search" in guidance["trace"]["blocked_tool_targets"]


@pytest.mark.anyio
async def test_orchestrator_records_capability_tool_policy_source_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path / "skills"),
        model_config=ModelConfig(orchestrator="orchestrator"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime._orchestrator(
        {
            "task": "Build a FastAPI endpoint",
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {"source_mode": "WRDS_ONLY"},
                    }
                }
            },
        }
    )

    assert result["metadata"]["source_mode"] == "WRDS_ONLY"
    assert result["metadata"]["source_mode_source"] == "capability_tool_policy"
    assert result["source_mode_decision"] == {
        "source_mode": "WRDS_ONLY",
        "source": "capability_tool_policy",
    }
    assert result["metadata"]["source_mode_decision"] == result["source_mode_decision"]


@pytest.mark.anyio
async def test_orchestrator_marks_legacy_deterministic_plan_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    runtime = AgentRuntime(
        llm=EmptyPlanLLM(),
        skill_loader=SkillLoader(tmp_path / "skills"),
        model_config=ModelConfig(orchestrator="orchestrator"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime._orchestrator({"task": "Say hello", "metadata": {}})

    assert result["plan"][0]["id"] == "direct"
    assert result["plan_fallback_trace"][0]["source"] == "legacy_deterministic_plan_fallback"
    assert result["plan_fallback_trace"][0]["step_count"] == len(result["plan"])


@pytest.mark.anyio
async def test_orchestrator_uses_web_research_plan_adapter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    skill_dir = tmp_path / "skills" / "web-research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: web-research\ndescription: Research public web sources.\n---\nUse public sources.\n",
        encoding="utf-8",
    )
    manifest = CapabilityRegistry().get("web-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path / "skills"),
        model_config=ModelConfig(orchestrator="orchestrator"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime._orchestrator(
        {
            "task": "Research LangGraph latest documentation",
            "metadata": {
                "capability_runtime": {
                    "capabilities": {
                        "web-research": {"entrypoints": {"workflow": workflow}},
                    }
                }
            },
        }
    )

    assert result["plan"][0]["id"] == "web-search"
    assert result["plan_adapter_trace"][0]["adapter"] == "public_web_search"
    assert result["plan_adapter_trace"][0]["status"] == "executed"
    assert result["plan_adapter_outputs"]["public_web_search"]["source"] == "capability_plan_entrypoint"


def test_wrds_only_source_mode_strips_web_tools_from_plan() -> None:
    plan = [
        {
            "id": "wrds",
            "title": "WRDS",
            "action": "Fetch WRDS",
            "tool_calls": [{"name": "wrds_company_financials", "args": {"query": "SNDK"}}],
        },
        {
            "id": "web",
            "title": "Web",
            "action": "Search web",
            "tool_calls": [
                {"name": "provider_web_search", "args": {"query": "SNDK"}},
                {"name": "fetch_url", "args": {"url": "https://example.com"}},
            ],
        },
    ]

    updated = enforce_source_mode_on_plan(plan, source_mode="WRDS_ONLY")

    assert len(updated) == 1
    assert updated[0]["tool_calls"][0]["name"] == "wrds_company_financials"


def test_capability_tool_policy_strips_blocked_tools_from_plan_without_wrds_mode() -> None:
    plan = [
        {
            "id": "web",
            "title": "Web",
            "action": "Search web",
            "tool_calls": [{"name": "provider_web_search", "args": {"query": "SNDK"}}],
        },
        {
            "id": "wrds",
            "title": "WRDS",
            "action": "Fetch WRDS",
            "tool_calls": [{"name": "wrds_company_financials", "args": {"query": "SNDK"}}],
        },
    ]

    updated = enforce_source_mode_on_plan(
        plan,
        source_mode=None,
        tool_policy={"blocked_tool_targets": ["tool:provider_web_search"]},
    )

    assert [step["id"] for step in updated] == ["wrds"]
    assert updated[0]["tool_calls"][0]["name"] == "wrds_company_financials"


def test_capability_tool_policy_allowlist_strips_undeclared_tools_from_plan() -> None:
    plan = [
        {
            "id": "mixed",
            "title": "Mixed",
            "action": "Fetch data",
            "tool_calls": [
                {"name": "wrds_company_financials", "args": {"query": "SNDK"}},
                {"name": "approved_source_fetch", "args": {"url": "https://example.com"}},
            ],
        }
    ]

    updated = enforce_source_mode_on_plan(
        plan,
        source_mode=None,
        tool_policy={"allowed_tool_targets": ["tool:wrds_company_financials"]},
    )

    assert len(updated) == 1
    assert updated[0]["tool_calls"] == [{"name": "wrds_company_financials", "args": {"query": "SNDK"}}]


def test_tool_manifest_filters_declared_source_policy_blocked_targets() -> None:
    manifest = [
        {"name": "custom_news_api"},
        {"name": "web_search"},
        {"name": "wrds_company_financials"},
    ]
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "tool_policy": {
                        "source_mode": "WRDS_ONLY",
                        "source_policy_blocked_tool_targets": ["tool:custom_news_api"],
                    }
                }
            }
        }
    }

    filtered = tool_manifest_for_state(manifest, state)

    assert [tool["name"] for tool in filtered] == ["web_search", "wrds_company_financials"]


def test_wrds_company_step_is_inserted_for_company_research_when_available() -> None:
    plan = [{"id": "1", "title": "Analyze", "action": "Analyze available context", "tool_calls": []}]

    updated = ensure_required_wrds_company_step(
        plan,
        task="沪电股份",
        orchestration={"task_type": "investment", "required_agents": {"wrds": True}},
        selected_skills=[{"name": "value-investing-research"}],
        available_tools=[{"name": "wrds_company_financials"}],
    )

    assert updated[0]["tool_calls"] == [
        {
            "name": "wrds_company_financials",
            "args": {
                "query": "沪电股份",
                "max_years": 10,
                "max_quarters": 16,
                "max_candidates": 5,
                "data_packages": [
                    "company_identity",
                    "annual_financials_10y",
                    "quarterly_financials_16q",
                    "valuation_snapshot",
                    "cash_flow_and_capex",
                    "balance_sheet_and_debt",
                    "profitability_and_margin",
                    "inventory_and_working_capital",
                    "debt_interest_coverage",
                    "capital_returns",
                    "goodwill_intangibles",
                    "split_adjustment",
                    "crsp_market_data",
                    "capital_iq_profile",
                ],
            },
        }
    ]
    assert updated[0]["data_plan"]["planner"] == "deterministic_wrds_planner"
    assert updated[1] == plan[0]


def test_existing_wrds_company_step_is_augmented_with_required_packages() -> None:
    plan = [
        {
            "id": "1",
            "title": "Fetch financials",
            "action": "Fetch partial WRDS data",
            "tool_calls": [
                {
                    "name": "wrds_company_financials",
                    "args": {
                        "query": "apple",
                        "max_years": 5,
                        "max_quarters": 4,
                        "data_packages": ["company_identity", "annual_financials_10y"],
                    },
                }
            ],
        }
    ]

    updated = ensure_required_wrds_company_step(
        plan,
        task="apple",
        orchestration={"task_type": "investment", "required_agents": {"wrds": True}},
        selected_skills=[],
        available_tools=[{"name": "wrds_company_financials"}],
    )

    args = updated[0]["tool_calls"][0]["args"]
    assert updated[0]["id"] == "1"
    assert args["max_years"] == 10
    assert args["max_quarters"] == 16
    assert "crsp_market_data" in args["data_packages"]
    assert "capital_iq_profile" in args["data_packages"]
    assert "optionmetrics_security" not in args["data_packages"]
    assert "ibes_estimates" not in args["data_packages"]
    assert "compustat_segments" not in args["data_packages"]
    assert updated[0]["data_plan"]["planner"] == "deterministic_wrds_planner"


def test_wrds_company_search_shorthand_gets_query_from_task() -> None:
    args = normalize_wrds_company_tool_args(
        {},
        state={"task": "ORCL"},
        step={"title": "Resolve ORCL company identity"},
        tool_name="wrds_company_search",
    )

    assert args == {"query": "ORCL", "max_results": 8}


def test_wrds_company_tool_preserves_explicit_query() -> None:
    args = normalize_wrds_company_tool_args(
        {"query": "AAPL", "max_results": 3},
        state={"task": "ORCL"},
        step={"title": "Resolve company identity"},
        tool_name="wrds_company_search",
    )

    assert args == {"query": "AAPL", "max_results": 3}


@pytest.mark.anyio
async def test_executor_normalizes_wrds_company_search_before_tool_registry(tmp_path: Path) -> None:
    class RecordingToolRegistry:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def arun(self, name: str, args: dict | None = None) -> ToolResult:
            self.calls.append((name, args or {}))
            return ToolResult(True, {"status": "matched", "args": args or {}})

    registry = RecordingToolRegistry()
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(skills_dir=tmp_path / "skills"),
        tool_registry=registry,
    )

    results = await runtime._execute_tool_calls(
        [{"name": "wrds_company_search", "args": {}}],
        state={"task": "ORCL"},
        step={"title": "Resolve ORCL company identity"},
    )

    assert registry.calls == [("wrds_company_search", {"query": "ORCL", "max_results": 8})]
    assert results[0]["args"] == {"query": "ORCL", "max_results": 8}
    assert results[0]["result"]["ok"] is True


@pytest.mark.anyio
async def test_executor_blocks_tool_not_declared_by_capability_tool_policy(tmp_path: Path) -> None:
    class RecordingToolRegistry:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def manifest(self) -> list[dict]:
            return [
                {"name": "read_file", "required_permissions": ["data:read"], "granted": True, "connection_granted": True},
                {
                    "name": "approved_source_fetch",
                    "required_permissions": ["network:approved-provider"],
                    "granted": True,
                    "connection_granted": True,
                },
            ]

        async def arun(self, name: str, args: dict | None = None) -> ToolResult:
            self.calls.append((name, args or {}))
            return ToolResult(True, {"status": "executed"})

    registry = RecordingToolRegistry()
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(skills_dir=tmp_path / "skills"),
        tool_registry=registry,
    )
    state = {
        "task": "Run toy workflow",
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "tool_policy": {"allowed_tool_targets": ["tool:approved_source_fetch"]}
                }
            }
        },
    }

    results = await runtime._execute_tool_calls(
        [{"name": "read_file", "args": {"path": "README.md"}}],
        state=state,
        step={"title": "Read file"},
    )

    assert registry.calls == []
    assert results[0]["result"]["ok"] is False
    assert results[0]["event_type"] == "tool.denied"
    decision = results[0]["result"]["data"]["tool_policy_decision"]
    assert decision["status"] == "denied"
    assert decision["reason"] == "not_declared_in_capability_tool_policy"


@pytest.mark.anyio
async def test_auto_fetch_after_search_uses_capability_tool_policy(tmp_path: Path) -> None:
    class RecordingToolRegistry:
        def __init__(self) -> None:
            self.async_calls: list[tuple[str, dict]] = []
            self.sync_calls: list[tuple[str, dict]] = []

        def manifest(self) -> list[dict]:
            return [
                {"name": "web_search", "required_permissions": ["network:arbitrary"], "granted": True, "connection_granted": True},
                {
                    "name": "approved_source_fetch",
                    "required_permissions": ["network:approved-provider"],
                    "granted": True,
                    "connection_granted": True,
                },
            ]

        def names(self) -> set[str]:
            return {"web_search", "approved_source_fetch"}

        async def arun(self, name: str, args: dict | None = None) -> ToolResult:
            self.async_calls.append((name, args or {}))
            return ToolResult(
                True,
                {
                    "query": (args or {}).get("query"),
                    "results": [{"title": "Official docs", "url": "https://example.com/docs"}],
                },
            )

        def run(self, name: str, args: dict | None = None) -> ToolResult:
            self.sync_calls.append((name, args or {}))
            return ToolResult(True, {"fetched": True})

    registry = RecordingToolRegistry()
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(skills_dir=tmp_path / "skills"),
        tool_registry=registry,
    )
    state = {
        "task": "Summarize official docs",
        "english_search_query": "official docs",
        "selected_skills": [],
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "tool_policy": {"allowed_tool_targets": ["tool:web_search"]}
                }
            }
        },
    }

    results = await runtime._execute_tool_calls(
        [{"name": "web_search", "args": {"query": "official docs", "fetch_top_results": True}}],
        state=state,
        step={"title": "Search docs"},
    )

    assert registry.async_calls == [("web_search", {"query": "official docs", "fetch_top_results": True})]
    assert registry.sync_calls == []
    assert results[0]["result"]["ok"] is True
    assert results[1]["name"] == "approved_source_fetch"
    assert results[1]["result"]["ok"] is False
    decision = results[1]["result"]["data"]["tool_policy_decision"]
    assert decision["status"] == "denied"
    assert decision["reason"] == "not_declared_in_capability_tool_policy"


def test_investment_data_gate_runs_even_without_wrds_result() -> None:
    assert should_run_data_gate(
        {
            "task": "apple",
            "orchestration": {
                "task_type": "investment",
                "committee": True,
                "required_agents": {"wrds": True},
            },
            "plan": [],
        }
    )


def test_data_gate_graph_routing_uses_data_contract_required_policy() -> None:
    assert should_run_data_gate(
        {
            "task": "custom gate review",
            "orchestration": {"task_type": "general", "committee": False, "required_agents": {"custom_gate": True}},
            "metadata": {
                "data_contract_descriptor": {
                    "id": "custom.data_contract",
                    "gate_policy": {"required_when": {"required_agents": ["custom_gate"]}},
                }
            },
            "plan": [],
        }
    )


def test_data_gate_graph_routing_descriptor_required_policy_suppresses_legacy_fallback() -> None:
    assert (
        should_run_data_gate(
            {
                "task": "custom investment review",
                "orchestration": {
                    "task_type": "investment",
                    "committee": True,
                    "required_agents": {"wrds": True},
                },
                "metadata": {
                    "data_contract_descriptor": {
                        "id": "custom.data_contract",
                        "gate_policy": {"required_when": {"required_agents": ["custom_gate"]}},
                    }
                },
                "plan": [
                    {
                        "id": "wrds",
                        "tool_calls": [
                            {"name": "wrds_company_financials", "args": {"query": "ABC"}},
                        ],
                    }
                ],
            }
        )
        is False
    )


def test_publication_block_sets_blocked_run_outcome() -> None:
    status, reasons = summarize_run_outcome(
        {
            "data_gate": {
                "status": "PASS_WRDS_ONLY",
                "blocking": False,
                "report_publication_allowed": False,
            },
            "review": {"status": "pass"},
            "agent_metrics": [],
        }
    )

    assert status == "blocked"
    assert reasons == ["Data Gate blocked publication."]


def test_declared_publication_permission_block_sets_blocked_run_outcome() -> None:
    status, reasons = summarize_run_outcome(
        {
            "data_gate": {
                "status": "PASS_WITH_LIMITS",
                "blocking": False,
                "conclusion_permissions": {
                    "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                },
            },
            "review": {"status": "pass"},
            "agent_metrics": [],
        }
    )

    assert status == "blocked"
    assert reasons == ["Data Gate blocked publication."]


def test_publication_block_stops_before_final_judge() -> None:
    assert (
        next_after_writer(
            {
                "data_gate": {
                    "status": "PASS_WRDS_ONLY",
                    "blocking": False,
                    "report_publication_allowed": False,
                },
                "review": {"status": "pass"},
                "orchestration": {"required_agents": {"final_judge": True}},
            }
        )
        == END
    )


def test_declared_publication_permission_block_stops_before_final_judge() -> None:
    assert (
        next_after_writer(
            {
                "data_gate": {
                    "status": "PASS_WITH_LIMITS",
                    "blocking": False,
                    "conclusion_permissions": {
                        "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                    },
                },
                "review": {"status": "pass"},
                "orchestration": {"required_agents": {"final_judge": True}},
            }
        )
        == END
    )


@pytest.mark.anyio
async def test_writer_metric_uses_generic_data_gate_publication_block_reason(tmp_path: Path) -> None:
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    token = start_agent_metrics()
    try:
        result = await runtime._writer(
            {
                "data_gate": {
                    "status": "PASS_WITH_LIMITS",
                    "blocking": False,
                    "conclusion_permissions": {
                        "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                    },
                },
                "review": {"status": "pass"},
            }
        )
        metrics = current_agent_metrics()
    finally:
        reset_agent_metrics(token)

    assert "Data Readiness Defect Report" in result["final"]
    assert metrics[0]["status"] == "data_gate_publication_blocked"
    assert metrics[0]["failure_reason"] == "data_gate_publication_blocked"


@pytest.mark.anyio
async def test_writer_metric_uses_generic_swarm_publication_block_reason(tmp_path: Path) -> None:
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    token = start_agent_metrics()
    try:
        result = await runtime._writer(
            {
                "data_gate": {
                    "status": "PASS",
                    "blocking": False,
                    "conclusion_permissions": {
                        "decision:toy_publish": {"allowed": True, "label": "toy publish"},
                    },
                },
                "stop_signals": [
                    {
                        "target": "decision:toy_publish",
                        "blocking": True,
                        "verification_state": "blocking",
                    }
                ],
                "review": {"status": "pass"},
            }
        )
        metrics = current_agent_metrics()
    finally:
        reset_agent_metrics(token)

    assert "Data Readiness Defect Report" in result["final"]
    assert metrics[0]["status"] == "swarm_stop_signal_blocked"
    assert metrics[0]["failure_reason"] == "swarm_publication_blocked"


def test_declared_publication_stop_signal_stops_before_final_judge() -> None:
    assert (
        next_after_writer(
            {
                "stop_signals": [
                    {
                        "target": "decision:toy_publish",
                        "blocking": True,
                        "verification_state": "blocking",
                    }
                ],
                "review": {"status": "pass"},
                "orchestration": {"required_agents": {"final_judge": True}},
            }
        )
        == END
    )


def test_protocol_boundary_overrides_publishable_committee_decision_when_quorum_commits_insufficient_data() -> None:
    decision = {"decision": "WATCH", "final_decision": "WATCH", "evidence_limitations": []}
    updated = apply_protocol_decision_boundary(
        {
            "data_gate": {"report_publication_allowed": False, "decision_blockers": [{"code": "missing"}]},
            "quorum_trace": {"committed_candidate": {"label": "Insufficient Data"}},
        },
        decision,
    )

    assert updated["committee_proposed_decision"] == "WATCH"
    assert updated["final_decision"] == "Insufficient Data"
    assert updated["protocol_decision"] == "Insufficient Data"
    assert updated["decision_authority"] == "quorum_marshal"


@pytest.mark.anyio
async def test_executor_runs_provider_web_search_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")

    async def provider_web_search(**kwargs):
        return {
            "query": kwargs["query"],
            "engine": "provider_native_web_search",
            "results": [{"title": "Source", "url": "https://example.com", "snippet": "fact"}],
        }

    registry = ToolRegistry(
        workspace_root=tmp_path,
        provider_web_search=provider_web_search,
        provider_web_search_enabled=True,
        permission_grants=["network:arbitrary"],
    )
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        tool_registry=registry,
    )

    result = await runtime._executor(
        {
            "task": "Summarize FastAPI release notes",
            "search_query": "FastAPI release notes",
            "english_search_query": "FastAPI release notes",
            "selected_skills": [],
            "plan": [
                {
                    "id": "search",
                    "title": "Search",
                    "action": "Search with provider native tool",
                    "tool_calls": [{"name": "provider_web_search", "args": {"query": "FastAPI release notes", "max_results": 3}}],
                }
            ],
        }
    )

    calls = result["execution_log"][0]["tool_calls"]
    assert calls[0]["name"] == "provider_web_search"
    assert calls[0]["result"]["ok"] is True
    assert calls[0]["result"]["data"]["engine"] == "provider_native_web_search"


@pytest.mark.anyio
async def test_provider_web_search_falls_back_to_local_search(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")

    async def provider_web_search(**_kwargs):
        raise RuntimeError("native search down")

    registry = ToolRegistry(
        workspace_root=tmp_path,
        provider_web_search=provider_web_search,
        provider_web_search_enabled=True,
        permission_grants=["network:arbitrary"],
    )
    registry._tools["web_search"] = lambda **kwargs: ToolResult(
        True,
        {"query": kwargs["query"], "results": [{"title": "Fallback", "url": "https://example.com"}]},
    )
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        tool_registry=registry,
    )

    result = await runtime._executor(
        {
            "task": "Summarize FastAPI release notes",
            "search_query": "FastAPI release notes",
            "english_search_query": "FastAPI release notes",
            "selected_skills": [],
            "plan": [
                {
                    "id": "search",
                    "title": "Search",
                    "action": "Search with provider native tool",
                    "tool_calls": [{"name": "provider_web_search", "args": {"query": "FastAPI release notes", "max_results": 3}}],
                }
            ],
        }
    )

    calls = result["execution_log"][0]["tool_calls"]
    assert [call["name"] for call in calls[:2]] == ["provider_web_search", "web_search"]
    assert calls[0]["result"]["ok"] is False
    assert calls[1]["result"]["ok"] is True
    assert result["execution_log"][0]["status"] == "completed"


@pytest.mark.anyio
async def test_wrds_only_source_mode_blocks_web_search_without_investment_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")

    async def provider_web_search(**_kwargs):
        raise AssertionError("provider search should not be called in WRDS_ONLY source mode")

    registry = ToolRegistry(
        workspace_root=tmp_path,
        provider_web_search=provider_web_search,
        provider_web_search_enabled=True,
        permission_grants=["network:arbitrary"],
    )
    registry._tools["web_search"] = lambda **_kwargs: (_ for _ in ()).throw(AssertionError("local search should not run"))
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        tool_registry=registry,
    )

    result = await runtime._executor(
        {
            "task": "apple",
            "orchestration": {"task_type": "investment", "committee": True},
            "metadata": {"source_mode": "WRDS_ONLY"},
            "search_query": "Apple valuation",
            "english_search_query": "Apple valuation",
            "selected_skills": [],
            "plan": [
                {
                    "id": "search",
                    "title": "Search",
                    "action": "Search public sources",
                    "tool_calls": [{"name": "web_search", "args": {"query": "Apple valuation", "max_results": 3}}],
                }
            ],
        }
    )

    calls = result["execution_log"][0]["tool_calls"]
    assert calls[0]["name"] in {"web_search", "provider_web_search"}
    assert calls[0]["result"]["ok"] is False
    assert "WRDS_ONLY" in calls[0]["result"]["error"]
    assert "source policy" in calls[0]["result"]["error"]
    assert "investment analysis" not in calls[0]["result"]["error"]


@pytest.mark.anyio
async def test_executor_blocks_web_tools_in_wrds_only_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")

    async def provider_web_search(**_kwargs):
        raise AssertionError("provider search should not be called in WRDS_ONLY mode")

    registry = ToolRegistry(
        workspace_root=tmp_path,
        provider_web_search=provider_web_search,
        provider_web_search_enabled=True,
        permission_grants=["network:arbitrary"],
    )
    runtime = AgentRuntime(
        llm=FakeLLM(),
        skill_loader=SkillLoader(tmp_path),
        tool_registry=registry,
    )

    result = await runtime._executor(
        {
            "task": "SNDK",
            "metadata": {"source_mode": "WRDS_ONLY"},
            "search_query": "SNDK",
            "english_search_query": "SNDK",
            "selected_skills": [],
            "plan": [
                {
                    "id": "search",
                    "title": "Search",
                    "action": "Search with provider native tool",
                    "tool_calls": [{"name": "provider_web_search", "args": {"query": "SNDK", "max_results": 3}}],
                }
            ],
        }
    )

    call = result["execution_log"][0]["tool_calls"][0]
    assert call["name"] == "provider_web_search"
    assert call["result"]["ok"] is False
    assert "WRDS_ONLY" in call["result"]["error"]
    assert "source policy" in call["result"]["error"]
    assert "investment analysis" not in call["result"]["error"]


@pytest.mark.anyio
async def test_executor_does_not_dynamically_propose_tools_for_investment_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    llm = FakeLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )

    result = await runtime._executor(
        {
            "task": "apple",
            "orchestration": {"task_type": "investment"},
            "metadata": {"os_plan": investment_os_plan()},
            "selected_skills": [],
            "plan": [
                {
                    "id": "analysis",
                    "title": "Analyze",
                    "action": "Analyze after explicit data retrieval.",
                    "tool_calls": None,
                }
            ],
        }
    )

    assert result["execution_log"][0]["tool_calls"] == []
    assert "minimax-m2.7" not in llm.calls


def test_web_research_helpers_select_official_sources() -> None:
    assert should_auto_fetch_search_results("Summarize LiteLLM configuration with sources", {}) is True
    assert should_auto_fetch_search_results("Search only", {"fetch_top_results": False}) is False
    assert should_auto_fetch_search_results("药明康德", {"query": "WuXi AppTec"}) is True
    assert should_auto_fetch_search_results("五粮液", {"query": "Wuliangye Yibin Co Ltd"}) is True
    assert should_auto_fetch_search_results(
        "bare entity",
        {"query": "WuXi AppTec"},
        selected_skills=[{"name": "web-research"}],
    ) is True
    assert should_auto_fetch_search_results(
        "bare entity",
        {"query": "quality source"},
        selected_skills=[{"name": "quality-lens", "capability_types": ["public_web_research"]}],
    ) is True

    urls = select_search_result_urls(
        {
            "results": [
                {"title": "Random blog", "url": "https://example.com/blog"},
                {"title": "Official docs", "url": "https://docs.example.com/guide"},
                {"title": "GitHub repo", "url": "https://github.com/example/project"},
            ]
        }
    )

    assert urls[:2] == ["https://docs.example.com/guide", "https://github.com/example/project"]


def test_deterministic_plan_uses_capability_metadata_for_research_selection() -> None:
    web_plan = deterministic_plan(
        task="Review public sources",
        english_search_query="public source review",
        selected_skills=[{"name": "quality-lens", "capability_types": ["public_web_research"]}],
    )
    investment_plan = deterministic_plan(
        task="Review investment data",
        english_search_query="investment data review",
        selected_skills=[{"name": "quality-investment", "capability_types": ["investment.research"]}],
    )

    assert web_plan[0]["id"] == "web-search"
    assert investment_plan[0]["id"] == "direct"


def test_provider_search_upgrade_uses_capability_metadata_not_legacy_names() -> None:
    tools = ["web_search", "provider_web_search"]

    assert should_upgrade_search_to_provider(
        {"selected_skills": [{"name": "quality-lens", "capability_types": ["public_web_research"]}]},
        tools,
    ) is True
    assert should_upgrade_search_to_provider(
        {"selected_skills": [{"name": "quality-investment", "capability_types": ["investment.research"]}]},
        tools,
    ) is True
    assert should_upgrade_search_to_provider({"selected_skills": [{"name": "quality-lens"}]}, tools) is False
    assert (
        should_upgrade_search_to_provider(
            {"orchestration": {"task_type": "investment", "committee": True}, "selected_skills": []},
            tools,
        )
        is False
    )


def test_review_grounding_policy_requires_fetched_source_text() -> None:
    review = apply_review_grounding_policy(
        {"status": "pass", "issues": [], "summary": "Looks good."},
        {
            "task": "药明康德",
            "english_search_query": "WuXi AppTec",
            "selected_skills": [{"name": "web-research"}],
            "execution_log": [
                {
                    "tool_calls": [
                        {
                            "name": "web_search",
                            "result": {"ok": True, "data": {"results": [{"url": "https://example.com"}]}},
                        }
                    ]
                }
            ],
        },
    )

    assert review["status"] == "needs_sources"
    assert "No fetched source text" in review["issues"][-1]


def test_review_grounding_policy_accepts_fetched_source_text() -> None:
    execution_log = [
        {
            "tool_calls": [
                {
                    "name": "fetch_url",
                    "result": {
                        "ok": True,
                        "data": {"word_count": 250, "url": "https://www.wuxiapptec.com"},
                    },
                }
            ]
        }
    ]

    assert has_fetched_source_text(execution_log) is True
    review = apply_review_grounding_policy(
        {"status": "pass", "issues": [], "summary": "Looks good."},
        {
            "task": "药明康德",
            "english_search_query": "WuXi AppTec",
            "selected_skills": [{"name": "web-research"}],
            "execution_log": execution_log,
        },
    )

    assert review["status"] == "pass"


def test_review_grounding_policy_accepts_approved_source_fetch_text() -> None:
    execution_log = [
        {
            "tool_calls": [
                {
                    "name": "approved_source_fetch",
                    "result": {
                        "ok": True,
                        "data": {"word_count": 250, "url": "https://example.org/paper"},
                    },
                }
            ]
        }
    ]

    assert has_fetched_source_text(execution_log) is True


def test_web_research_fetch_failures_are_partial_not_step_failure() -> None:
    assert (
        step_tool_results_succeeded(
            [
                {"name": "web_search", "result": {"ok": True}},
                {"name": "approved_source_fetch", "result": {"ok": False, "error": "403"}},
            ]
        )
        is True
    )
    status, failure_reason = summarize_execution_metric_status(
        [
            {
                "status": "completed",
                "tool_calls": [
                    {"name": "web_search", "result": {"ok": True}},
                    {"name": "approved_source_fetch", "result": {"ok": False, "error": "403"}},
                ],
            }
        ]
    )

    assert status == "completed"
    assert failure_reason is None


def test_web_research_helpers_prefer_company_sources_over_dictionary_results() -> None:
    urls = select_search_result_urls(
        {
            "query": "药明康德 公司 财报 新闻 业务 风险",
            "searched_query": "药明康德",
            "results": [
                {
                    "title": "药（汉语文字）_百度百科",
                    "url": "https://baike.baidu.com/item/%E8%8D%AF/2361462",
                    "snippet": "药，汉语常用字。",
                },
                {
                    "title": "药明康德 | 官方网站",
                    "url": "https://www.wuxiapptec.cn/",
                    "snippet": "药明康德提供一体化药物研发和生产服务。",
                },
            ],
        }
    )

    assert urls[0] == "https://www.wuxiapptec.cn/"
