from __future__ import annotations

from typing import Any

from runtime.research_selection import selected_skills_request_direct_wrds_data


LEGACY_WRDS_FINANCIAL_DATA_CAPABILITY_ID = "wrds-financial-data"


def legacy_wrds_financial_data_capability_id() -> str:
    return LEGACY_WRDS_FINANCIAL_DATA_CAPABILITY_ID


def legacy_should_run_wrds_agent(state: dict[str, Any]) -> bool:
    orchestration = state.get("orchestration") if isinstance(state.get("orchestration"), dict) else {}
    if orchestration.get("task_type") == "wrds":
        return True
    if selected_skills_request_direct_wrds_data(list(state.get("selected_skills", []) or [])):
        return True
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    return bool(metadata.get("wrds_sql") or metadata.get("wrds_action"))


def legacy_should_bypass_graph_to_wrds(
    *,
    task: str,
    metadata: dict[str, Any],
    skills: list[Any],
) -> bool:
    if metadata.get("wrds_sql") or metadata.get("wrds_action"):
        return True
    if task.strip().lower().startswith(("select ", "with ")):
        return True
    return selected_skills_request_direct_wrds_data(list(skills))


def legacy_direct_wrds_orchestration() -> dict[str, Any]:
    return {
        "task_type": "wrds",
        "depth": "shallow",
        "committee": False,
        "required_agents": {
            "memory": False,
            "wrds": True,
            "research": False,
            "quant": False,
            "domain": False,
            "critic": False,
            "writer": False,
            "final_judge": False,
        },
        "rationale": "Explicit WRDS data retrieval request; bypassing the general multi-agent workflow.",
        "routing_source": "legacy_wrds_routing_fallback",
    }


def legacy_direct_wrds_plan_step() -> dict[str, Any]:
    return {
        "id": "wrds",
        "title": "WRDS data retrieval",
        "action": "Run a single read-only WRDS data retrieval action.",
        "tool_calls": [],
    }
