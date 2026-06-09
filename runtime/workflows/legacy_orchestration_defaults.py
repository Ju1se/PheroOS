from __future__ import annotations

from typing import Any

from runtime.research_selection import (
    research_skill_selected,
    selected_skills_request_company_financial_data,
    selected_skills_request_investment_research,
    skill_name,
)
from runtime.workflows.legacy_graph_routing import (
    legacy_needs_domain_analysis,
    legacy_should_force_direct_answer,
)
from runtime.wrds_company_planner import looks_like_ticker_or_company_name
from runtime.wrds_planner import infer_industry_profile, normalize_data_packages, normalize_research_questions


LEGACY_GRAPH_ORCHESTRATION_AGENT_KEYS = (
    "memory",
    "wrds",
    "research",
    "quant",
    "domain",
    "critic",
    "writer",
    "final_judge",
)


def legacy_normalize_orchestration_defaults(
    payload: dict[str, Any],
    *,
    task: str,
    selected_skills: list[Any],
    task_type: str,
    suppress_investment_defaults: bool,
) -> dict[str, Any]:
    required = payload.get("required_agents")
    if not isinstance(required, dict):
        required = {}
    skill_names = {skill_name(skill) for skill in selected_skills}
    auto_company_investment = (
        not suppress_investment_defaults
        and task_type.lower() in {"general", "research"}
        and looks_like_ticker_or_company_name(task)
    )
    if auto_company_investment:
        task_type = "investment"
    depth = str(payload.get("depth") or "standard")
    research_default = research_skill_selected(selected_skills)
    quant_default = selected_skills_request_investment_research(selected_skills)
    heuristic_investment_default = task_type == "investment" and not suppress_investment_defaults
    wrds_default = selected_skills_request_company_financial_data(selected_skills) or task_type == "wrds" or heuristic_investment_default
    committee_default = selected_skills_request_investment_research(selected_skills) or heuristic_investment_default
    domain_default = bool(skill_names) or legacy_needs_domain_analysis(task)
    critic_default = research_default or quant_default or domain_default
    final_judge_default = critic_default
    committee = legacy_parse_agent_flag(payload, "committee", committee_default)
    required_agents = {
        "memory": legacy_parse_agent_flag(required, "memory", False),
        "wrds": legacy_parse_agent_flag(required, "wrds", wrds_default),
        "research": legacy_parse_agent_flag(required, "research", research_default or committee),
        "quant": legacy_parse_agent_flag(required, "quant", quant_default or committee),
        "domain": legacy_parse_agent_flag(required, "domain", domain_default and not committee),
        "critic": legacy_parse_agent_flag(required, "critic", critic_default or committee),
        "writer": legacy_parse_agent_flag(required, "writer", True),
        "final_judge": legacy_parse_agent_flag(required, "final_judge", final_judge_default or committee),
    }
    if committee:
        required_agents.update(
            {
                "wrds": wrds_default or bool(required.get("wrds")),
                "research": True,
                "quant": True,
                "domain": False,
                "critic": True,
                "writer": True,
                "final_judge": True,
            }
        )
    if auto_company_investment:
        committee = True
        required_agents.update(
            {
                "memory": False,
                "wrds": True,
                "research": True,
                "quant": True,
                "domain": False,
                "critic": True,
                "writer": True,
                "final_judge": True,
            }
        )
    if legacy_should_force_direct_answer(
        task=task,
        task_type=task_type,
        depth=depth,
        has_selected_skills=bool(skill_names),
        required_agents=required_agents,
    ):
        committee = False
        required_agents.update(
            {
                "memory": False,
                "wrds": False,
                "research": False,
                "quant": False,
                "domain": False,
                "critic": False,
                "writer": True,
                "final_judge": False,
            }
        )
    industry_profile = infer_industry_profile(task)
    required_data_packages = normalize_data_packages(
        payload.get("required_data_packages") or payload.get("data_packages"),
        task=task,
        task_type=task_type,
    )
    research_questions = (
        normalize_research_questions(
            payload.get("research_questions"),
            task=task,
            industry_profile=industry_profile,
        )
        if task_type == "investment"
        else []
    )
    return {
        "task_type": task_type,
        "depth": depth,
        "committee": committee,
        "industry_profile": industry_profile,
        "research_questions": research_questions,
        "required_data_packages": required_data_packages,
        "required_agents": required_agents,
        "rationale": str(payload.get("rationale") or ""),
    }


def legacy_parse_agent_flag(required: dict[str, Any], key: str, default: bool) -> bool:
    return legacy_parse_bool_value(required.get(key, default), default)


def legacy_parse_bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "required"}:
            return True
        if normalized in {"0", "false", "no", "off", "skip", "skipped"}:
            return False
    return bool(value)
