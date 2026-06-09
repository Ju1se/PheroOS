from __future__ import annotations


LEGACY_TASK_TYPE_ALIASES = {
    "wrds": "wrds",
    "wrds_data": "wrds",
    "wrds_query": "wrds",
    "professional_data": "wrds",
    "investment": "investment",
    "investment_company_research": "investment",
    "investment_company_analysis": "investment",
    "investment_equity_research": "investment",
    "investment_stock_research": "investment",
    "stock_research": "investment",
    "equity_research": "investment",
    "company_research": "investment",
    "company_analysis": "investment",
    "investment_research": "investment",
    "security_analysis": "investment",
    "portfolio": "portfolio_review",
    "portfolio_review": "portfolio_review",
    "portfolio_analysis": "portfolio_review",
    "holdings_review": "portfolio_review",
    "document": "document_writing",
    "document_writing": "document_writing",
    "writing": "document_writing",
    "drafting": "document_writing",
    "memo_writing": "document_writing",
    "data": "data_analysis",
    "data_analysis": "data_analysis",
    "dataset_analysis": "data_analysis",
    "tabular_analysis": "data_analysis",
    "spreadsheet_analysis": "data_analysis",
}

LEGACY_CODE_TASK_HINTS = ("code", "api", "代码", "接口", "bug")
LEGACY_PORTFOLIO_TASK_HINTS = ("portfolio", "组合", "持仓", "仓位", "配置", "rebalance", "allocation")
LEGACY_INVESTMENT_TASK_HINTS = ("投资", "估值", "valuation")

LEGACY_DIRECT_ANSWER_COMPLEX_MARKERS = (
    "analysis",
    "analyze",
    "research",
    "report",
    "investment",
    "valuation",
    "financial",
    "stock",
    "latest",
    "source",
    "code",
    "api",
    "file",
    "分析",
    "研究",
    "报告",
    "投资",
    "估值",
    "财务",
    "股票",
    "最新",
    "来源",
    "代码",
    "接口",
    "文件",
)

LEGACY_QUANT_HINTS = (
    "valuation",
    "financial",
    "fundamental",
    "earnings",
    "cash flow",
    "margin",
    "roic",
    "fcf",
    "pe",
    "ev/ebitda",
    "估值",
    "财务",
    "盈利",
    "现金流",
    "毛利率",
    "净利率",
    "回测",
)

LEGACY_DOMAIN_HINTS = (
    "investment",
    "value investing",
    "business",
    "strategy",
    "academic",
    "paper",
    "code",
    "api",
    "投资",
    "价值投资",
    "商业",
    "战略",
    "论文",
    "报告",
    "代码",
    "接口",
    "分析",
)


def legacy_normalize_task_type(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_").replace("/", "_")
    return LEGACY_TASK_TYPE_ALIASES.get(normalized, value.strip() or "general")


def legacy_should_force_direct_answer(
    *,
    task: str,
    task_type: str,
    depth: str,
    has_selected_skills: bool,
    required_agents: dict[str, bool],
) -> bool:
    if has_selected_skills:
        return False
    if any(required_agents.get(name) for name in ("memory", "research", "quant", "critic", "final_judge")):
        return False
    lowered = task.lower()
    if any(marker in lowered for marker in LEGACY_DIRECT_ANSWER_COMPLEX_MARKERS):
        return False
    return task_type.lower() in {"general", "knowledge_qa", "definition", "translation"} or depth.lower() in {
        "direct",
        "shallow",
        "simple",
    }


def legacy_infer_task_type(
    task: str,
    *,
    skill_names: set[str],
    direct_wrds_selected: bool,
    investment_research_selected: bool,
    research_selected: bool,
    known_research_marker_found: bool,
    company_like_task: bool,
) -> str:
    lowered = task.lower()
    if direct_wrds_selected or "wrds" in lowered:
        return "wrds"
    if "data-analysis" in skill_names:
        return "data_analysis"
    if "document-writing" in skill_names:
        return "document_writing"
    if "fastapi-api" in skill_names or any(word in lowered for word in LEGACY_CODE_TASK_HINTS):
        return "coding"
    if any(word in lowered for word in LEGACY_PORTFOLIO_TASK_HINTS):
        return "portfolio_review"
    if (
        investment_research_selected
        or any(word in lowered for word in LEGACY_INVESTMENT_TASK_HINTS)
        or known_research_marker_found
        or company_like_task
    ):
        return "investment"
    if research_selected:
        return "research"
    return "general"


def legacy_needs_quant_analysis(task: str) -> bool:
    lowered = task.lower()
    return any(hint in lowered for hint in LEGACY_QUANT_HINTS)


def legacy_needs_domain_analysis(task: str) -> bool:
    lowered = task.lower()
    return any(hint in lowered for hint in LEGACY_DOMAIN_HINTS)
