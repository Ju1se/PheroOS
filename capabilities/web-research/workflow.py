from __future__ import annotations

from typing import Any


def build_workflow_descriptor() -> dict[str, Any]:
    return {
        "id": "web-research.plan",
        "graph_mode": "",
        "ordered_nodes": [],
        "required_protocols": ["tool_policy", "evidence_policy"],
        "plan_entrypoints": {
            "public_web_search": "workflow.py:plan_public_web_search",
        },
    }


def plan_public_web_search(
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
    adapter: str,
) -> dict[str, Any]:
    from runtime.web_research_planner import SEARCH_TOOL_NAMES, ensure_required_web_research_step

    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    plan = [step for step in result.get("plan") or [] if isinstance(step, dict)]
    preferred_tool = str(result.get("preferred_web_search_tool") or "web_search")
    updated = ensure_required_web_research_step(
        plan,
        task=str(state.get("task") or result.get("task") or ""),
        english_search_query=str(result.get("english_search_query") or result.get("search_query") or ""),
        selected_skills=result.get("selected_skills") if isinstance(result.get("selected_skills"), list) else [],
        preferred_web_search_tool=preferred_tool,
        source_mode=metadata.get("source_mode"),
    )
    return {
        "status": "applied" if updated != plan else "no_change",
        "plan": updated,
        "handled_tools": sorted({preferred_tool, *SEARCH_TOOL_NAMES}),
        "source": "capability_plan_entrypoint",
        "workflow_id": workflow.get("id"),
        "adapter": adapter,
    }
