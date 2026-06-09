from __future__ import annotations


LEGACY_INVESTMENT_ORCHESTRATION_GUIDANCE = (
    "For investment tasks, decide research questions and high-level data packages only; do not list WRDS field names. A dedicated WRDS Planner will translate packages into fields.",
    "When the task is a public company name, stock ticker, or company investment analysis, set task_type to investment/company_research, set required_agents.wrds=true if WRDS tools are available, include required_data_packages such as company_identity, annual_financials_10y, quarterly_financials_16q, valuation_snapshot, cash_flow_and_capex, balance_sheet_and_debt, profitability_and_margin, inventory_and_working_capital, and include wrds_company_financials.",
    "Do not route ordinary company research to the WRDS-only agent; WRDS should be a data prefetch step that Research, Quant, and Committee can consume.",
)

LEGACY_MODEL_ROLE_ORCHESTRATION_GUIDANCE = (
    "Use GLM-style reasoning roles for judgment-heavy work and MiniMax-style roles for execution/writing/cross-check work.",
)
LEGACY_SOURCE_MODE_TOOL_GUIDANCE_TEMPLATE = (
    "Source mode is {source_mode}: do not include blocked public-web or source-fetch tools"
    "{blocked_tools_clause}; use capability-approved source tools only."
)


def legacy_investment_orchestration_guidance() -> list[str]:
    return list(LEGACY_INVESTMENT_ORCHESTRATION_GUIDANCE)


def legacy_model_role_orchestration_guidance() -> list[str]:
    return list(LEGACY_MODEL_ROLE_ORCHESTRATION_GUIDANCE)


def legacy_source_mode_tool_guidance(*, source_mode: str, blocked_tools: str) -> str:
    return render_source_mode_tool_guidance(
        LEGACY_SOURCE_MODE_TOOL_GUIDANCE_TEMPLATE,
        source_mode=source_mode,
        blocked_tools=blocked_tools,
    )


def render_source_mode_tool_guidance(template: str, *, source_mode: str, blocked_tools: str) -> str:
    blocked_tools_clause = f" ({blocked_tools})" if blocked_tools else ""
    return (
        str(template or "")
        .replace("{source_mode}", source_mode)
        .replace("{blocked_tools}", blocked_tools)
        .replace("{blocked_tools_clause}", blocked_tools_clause)
        .strip()
    )
