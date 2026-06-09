from __future__ import annotations

from typing import Any


def build_workflow_descriptor() -> dict[str, Any]:
    """Describe the capability-owned investment committee path.

    The LangGraph implementation still lives in `runtime.graph`; this descriptor
    is the first entrypoint bridge so the OS Kernel can reason about the
    workflow without hardcoding capability internals.
    """

    return {
        "id": "value-investing-research.workflow",
        "graph_mode": "investment_committee",
        "ordered_nodes": [
            "orchestrator",
            "executor_wrds",
            "data_gate",
            "deterministic_research",
            "deterministic_quant",
            "committee_opening",
            "committee_discussion",
            "investment_committee",
            "critic",
            "writer",
            "final_judge",
        ],
        "node_policy": {
            "memory_agent": {"required": False, "reason": "Investment workflow uses data contract context before optional memory."},
            "executor": {"required": True, "reason": "WRDS/metric-registry data path must execute before Data Gate."},
            "data_gate": {"required": True, "reason": "Investment conclusions require Data Gate approval or caveats."},
            "research_agent": {"required": True, "reason": "Research summary must be derived from the metric/data contract path."},
            "quant_agent": {"required": True, "reason": "Quant view must be deterministic/metric-registry constrained."},
            "domain_expert": {"required": False, "reason": "Investment domain judgment is handled by committee members."},
            "committee_opening": {"required": True, "reason": "Committee debate is mandatory for investment research."},
            "critic": {"required": True, "reason": "Critic gate checks overclaims and evidence gaps before writing."},
            "writer": {"required": True, "reason": "Writer produces only Data Gate / Evidence Graph constrained output."},
            "final_judge": {"required": True, "reason": "Final judge enforces caveats and publication limits."}
        },
        "orchestration_guidance": [
            "For investment tasks, decide research questions and high-level data packages only; do not list WRDS field names. A dedicated WRDS Planner will translate packages into fields.",
            "When the task is a public company name, stock ticker, or company investment analysis, set task_type to investment/company_research, set required_agents.wrds=true if WRDS tools are available, include required_data_packages such as company_identity, annual_financials_10y, quarterly_financials_16q, valuation_snapshot, cash_flow_and_capex, balance_sheet_and_debt, profitability_and_margin, inventory_and_working_capital, and include wrds_company_financials.",
            "Do not route ordinary company research to the WRDS-only agent; WRDS should be a data prefetch step that Research, Quant, and Committee can consume."
        ],
        "node_entrypoints": {
            "data_gate": "capabilities/value-investing-research/runtime_nodes.py:data_gate_node",
            "research_agent": "capabilities/value-investing-research/runtime_nodes.py:research_agent_node",
            "quant_agent": "capabilities/value-investing-research/runtime_nodes.py:quant_agent_node",
            "committee_opening": "capabilities/value-investing-research/runtime_nodes.py:committee_opening_node",
            "committee_discussion": "capabilities/value-investing-research/runtime_nodes.py:committee_discussion_node",
            "investment_committee": "capabilities/value-investing-research/runtime_nodes.py:investment_committee_node"
        },
        "plan_entrypoints": {
            "wrds_company_financials": "workflow.py:plan_wrds_company_financials",
        },
        "metric_registry_entrypoint": "workflow.py:build_metric_registry_adapter",
        "required_protocols": ["data_gate", "quorum", "stop_signal"],
        "writer_contract": "evidence_graph.writer_contract",
    }


def plan_wrds_company_financials(
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
    adapter: str,
) -> dict[str, Any]:
    from runtime.wrds_company_planner import ensure_required_wrds_company_step

    plan = [step for step in result.get("plan") or [] if isinstance(step, dict)]
    updated = ensure_required_wrds_company_step(
        plan,
        task=str(state.get("task") or result.get("task") or ""),
        orchestration=result.get("orchestration") if isinstance(result.get("orchestration"), dict) else {},
        selected_skills=result.get("selected_skills") if isinstance(result.get("selected_skills"), list) else [],
        available_tools=result.get("tool_manifest") if isinstance(result.get("tool_manifest"), list) else [],
    )
    return {
        "status": "applied" if updated != plan else "no_change",
        "plan": updated,
        "handled_tools": [adapter],
        "source": "capability_plan_entrypoint",
        "workflow_id": workflow.get("id"),
    }


def build_metric_registry_adapter(
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    from runtime.data_gate import build_metric_registry

    data_contract = result.get("data_contract") if isinstance(result.get("data_contract"), dict) else {}
    registry = build_metric_registry(state.get("wrds_result", {}), data_contract=data_contract)
    return {
        "status": registry.get("status", "created"),
        "metric_registry": registry,
        "source": "capability_metric_registry_entrypoint",
        "workflow_id": workflow.get("id"),
    }
