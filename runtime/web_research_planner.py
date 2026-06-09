from __future__ import annotations

from typing import Any

from runtime.research_selection import research_skill_selected
from runtime.swarm.source_policy_modes import source_mode_is_wrds_only
from runtime.tool_names import WEB_SEARCH_TOOL_NAME
from runtime.workflows.source_tool_helpers import SEARCH_TOOL_NAMES


def ensure_required_web_research_step(
    plan: list[dict[str, Any]],
    *,
    task: str,
    english_search_query: str | None = None,
    selected_skills: list[dict[str, Any]],
    preferred_web_search_tool: str = WEB_SEARCH_TOOL_NAME,
    source_mode: Any = None,
) -> list[dict[str, Any]]:
    if source_mode_is_wrds_only(source_mode):
        return plan
    if not research_skill_selected(selected_skills) or plan_has_any_tool_call(plan, SEARCH_TOOL_NAMES):
        return plan

    query = normalize_search_query(english_search_query or task)
    research_step = {
        "id": "web-search",
        "title": "联网检索相关资料",
        "action": "Search public web sources for the requested analysis.",
        "tool_calls": [{"name": preferred_web_search_tool, "args": {"query": query, "max_results": 5}}],
    }
    return [research_step, *plan]


def plan_has_any_tool_call(plan: list[dict[str, Any]], tool_names: set[str]) -> bool:
    for step in plan:
        tool_calls = step.get("tool_calls") or []
        if any(call.get("name") in tool_names for call in tool_calls if isinstance(call, dict)):
            return True
    return False


def normalize_search_query(query: str) -> str:
    return query.strip()
