from __future__ import annotations

from typing import Any


LEGACY_DATA_GATE_TOOL_NAMES = {"wrds_company_search", "wrds_company_financials", "wrds_query"}


def legacy_data_gate_tool_names() -> set[str]:
    return set(LEGACY_DATA_GATE_TOOL_NAMES)


def legacy_graph_data_gate_required(
    state: dict[str, Any],
    *,
    has_financial_data: bool,
) -> bool:
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    if not has_financial_data and not metadata.get("require_data_gate"):
        return False
    orchestration = state.get("orchestration") or {}
    task_type = str(orchestration.get("task_type") or state.get("route") or "").lower()
    required = orchestration.get("required_agents") if isinstance(orchestration.get("required_agents"), dict) else {}
    return bool(orchestration.get("committee")) or task_type == "investment" or bool(required.get("wrds"))
