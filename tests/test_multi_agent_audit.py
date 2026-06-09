from __future__ import annotations

from runtime.graph import (
    next_after_domain,
    next_after_executor,
    next_after_research,
    next_after_orchestrator,
    next_after_patroller,
    next_after_quant,
    next_after_writer,
    normalize_orchestration,
    should_run_executor_node,
)


def test_audit_redline_simple_question_routes_directly_to_writer() -> None:
    state = {
        "task": "解释什么是 ROIC。",
        "orchestration": {
            "required_agents": {
                "memory": False,
                "research": False,
                "quant": False,
                "domain": False,
                "critic": False,
                "writer": True,
                "final_judge": False,
            }
        },
        "plan": [{"id": "direct", "title": "Direct answer", "action": "Answer directly", "tool_calls": []}],
        "selected_skills": [],
    }

    assert should_run_executor_node(state) is False
    assert next_after_orchestrator(state) == "patroller_gate"
    assert next_after_patroller(state) == "writer"


def test_audit_redline_complex_investment_task_uses_ordered_specialists() -> None:
    state = {
        "task": "分析药明康德是否符合价值投资逻辑。",
        "orchestration": {
            "required_agents": {
                "memory": False,
                "research": True,
                "quant": True,
                "domain": True,
                "critic": True,
                "writer": True,
                "final_judge": True,
            }
        },
        "selected_skills": [{"name": "web-research"}, {"name": "value-investing-research"}],
        "plan": [
            {
                "id": "web-search",
                "title": "Search",
                "action": "Search public sources",
                "tool_calls": [{"name": "web_search", "args": {"query": "WuXi AppTec valuation"}}],
            }
        ],
        "execution_log": [{"tool_calls": [{"name": "web_search", "result": {"ok": True}}]}],
    }

    assert next_after_orchestrator(state) == "patroller_gate"
    assert next_after_patroller(state) == "executor"
    assert next_after_executor(state) == "research_agent"
    assert next_after_research(state) == "quant_agent"
    assert next_after_quant(state) == "committee_opening"
    assert next_after_writer(state) == "final_judge"


def test_audit_required_agent_flags_respect_false_strings() -> None:
    orchestration = normalize_orchestration(
        {
            "task_type": "general",
            "required_agents": {
                "research": "false",
                "quant": "false",
                "domain": "false",
                "critic": "false",
                "writer": "true",
                "final_judge": "false",
            },
        },
        task="解释什么是 ROIC。",
        selected_skills=[],
    )

    assert orchestration["required_agents"] == {
        "memory": False,
        "wrds": False,
        "research": False,
        "quant": False,
        "domain": False,
        "critic": False,
        "writer": True,
        "final_judge": False,
    }
    assert orchestration["committee"] is False


def test_audit_investment_orchestration_enables_committee() -> None:
    orchestration = normalize_orchestration(
        {
            "task_type": "investment",
            "depth": "deep",
            "required_agents": {},
        },
        task="深度分析兆易创新",
        selected_skills=[],
    )

    assert orchestration["committee"] is True
    assert orchestration["required_agents"]["wrds"] is True
    assert orchestration["required_agents"]["research"] is True
    assert orchestration["required_agents"]["quant"] is True


def test_protocol_os_plan_suppresses_company_name_investment_heuristic() -> None:
    orchestration = normalize_orchestration(
        {
            "task_type": "general",
            "depth": "shallow",
            "required_agents": {
                "research": False,
                "quant": False,
                "critic": False,
                "writer": True,
                "final_judge": False,
            },
        },
        task="AAPL",
        selected_skills=[],
        os_plan={
            "intent": "evidence_research",
            "intent_source": "capability_protocol_intent",
            "committee_plan": {"required": False},
            "swarm_plan": {"protocol_source": "capability_manifest", "tool_policy": {}},
        },
    )

    assert orchestration["task_type"] == "general"
    assert orchestration["committee"] is False
    assert orchestration["required_agents"]["wrds"] is False
    assert orchestration["required_agents"]["quant"] is False


def test_protocol_source_policy_preserves_company_investment_defaults() -> None:
    orchestration = normalize_orchestration(
        {
            "task_type": "general",
            "depth": "deep",
            "required_agents": {},
        },
        task="AAPL",
        selected_skills=[],
        os_plan={
            "intent": "investment_analysis",
            "intent_source": "capability_protocol_intent",
            "committee_plan": {"required": False},
            "swarm_plan": {
                "protocol_source": "capability_manifest",
                "tool_policy": {"source_mode": "WRDS_ONLY"},
            },
        },
    )

    assert orchestration["task_type"] == "investment"
    assert orchestration["committee"] is True
    assert orchestration["required_agents"]["wrds"] is True
    assert orchestration["required_agents"]["domain"] is False
    assert orchestration["required_agents"]["critic"] is True
    assert orchestration["required_agents"]["final_judge"] is True


def test_company_name_overrides_general_orchestrator_misclassification() -> None:
    orchestration = normalize_orchestration(
        {
            "task_type": "general",
            "depth": "shallow",
            "required_agents": {
                "research": False,
                "quant": False,
                "critic": False,
                "writer": True,
                "final_judge": False,
            },
        },
        task="AAPL",
        selected_skills=[],
    )

    assert orchestration["task_type"] == "investment"
    assert orchestration["committee"] is True
    assert orchestration["required_agents"]["wrds"] is True
    assert orchestration["required_agents"]["research"] is True
    assert orchestration["required_agents"]["quant"] is True
