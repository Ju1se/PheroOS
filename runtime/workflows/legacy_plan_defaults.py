from __future__ import annotations

from typing import Any

from runtime.research_selection import research_skill_selected, selected_skills_request_investment_research
from runtime.swarm.source_policy_modes import source_mode_is_wrds_only
from runtime.tool_names import WEB_SEARCH_TOOL_NAME


LEGACY_CODE_PLAN_SKILL_NAMES = {"fastapi-api"}
LEGACY_CODE_PLAN_HINTS = ("代码", "项目", "api", "fastapi")


def legacy_deterministic_plan(
    *,
    task: str,
    english_search_query: str,
    selected_skills: list[dict[str, Any]],
    preferred_web_search_tool: str = WEB_SEARCH_TOOL_NAME,
    source_mode: Any = None,
) -> list[dict[str, Any]]:
    skill_names = {str(skill.get("name") or "") for skill in selected_skills}
    if source_mode_is_wrds_only(source_mode):
        return [
            {
                "id": "direct",
                "title": "Source-policy controlled analysis",
                "action": "Use capability-approved source tools only.",
                "tool_calls": [],
            }
        ]
    if (
        research_skill_selected(selected_skills)
        and not selected_skills_request_investment_research(selected_skills)
        and not source_mode_is_wrds_only(source_mode)
    ):
        return [
            {
                "id": "web-search",
                "title": "Research public sources",
                "action": "Search public web sources for evidence.",
                "tool_calls": [{"name": preferred_web_search_tool, "args": {"query": english_search_query, "max_results": 5}}],
            }
        ]
    if skill_names.intersection(LEGACY_CODE_PLAN_SKILL_NAMES) or any(word in task.lower() for word in LEGACY_CODE_PLAN_HINTS):
        return [
            {
                "id": "inspect",
                "title": "Inspect workspace",
                "action": "List relevant workspace files.",
                "tool_calls": [{"name": "list_files", "args": {"path": ".", "pattern": "*", "max_results": 120}}],
            }
        ]
    return [{"id": "direct", "title": "No tool required", "action": "Answer from provided context.", "tool_calls": []}]
