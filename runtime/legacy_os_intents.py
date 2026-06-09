from __future__ import annotations

import re

from runtime.legacy_skill_matching import needs_value_investing_research, needs_web_research, needs_wrds_data


EXPLICIT_INVESTMENT_HINTS = (
    "投资",
    "估值",
    "股票",
    "股价",
    "买入",
    "卖出",
    "持有",
    "价值投资",
    "基本面",
    "财务",
    "财报",
    "现金流",
    "护城河",
    "仓位",
    "组合",
    "市盈率",
    "市净率",
    "pe",
    "pb",
    "ev/ebitda",
    "fundamental",
    "valuation",
    "investment",
    "stock",
    "equity",
    "financial",
    "cash flow",
    "portfolio",
    "buy",
    "sell",
    "hold",
)
GENERIC_ENTITY_ANALYSIS_HINTS = (
    "分析",
    "研究",
    "调研",
    "怎么看",
    "怎么样",
    "如何评价",
    "报告",
    "input",
)
NON_FINANCIAL_RESEARCH_HINTS = (
    "蚁群",
    "蜂群",
    "昆虫",
    "群体智能",
    "群体决策",
    "蚁群算法",
    "蜂群算法",
    "信息素",
    "多智能体",
    "智能体",
    "机制",
    "算法",
    "理论",
    "论文",
    "生物",
    "仿生",
    "设计",
    "前端",
    "界面",
    "开发者",
    "架构",
    "系统",
    "协议",
    "治理",
    "agent",
    "multi-agent",
    "multi agent",
    "swarm",
    "ant colony",
    "bee colony",
    "honeybee",
    "collective decision",
    "pheromone",
    "stigmergy",
    "architecture",
    "design",
    "frontend",
    "developer",
    "documentation",
    "docs",
    "html",
    "css",
    "ui",
    "ux",
    "protocol",
    "governance",
    "algorithm",
    "theory",
)
COMMON_PUBLIC_COMPANY_NAMES = (
    "apple",
    "aapl",
    "tencent",
    "oracle",
    "orcl",
    "amazon",
    "amzn",
    "microsoft",
    "msft",
    "google",
    "alphabet",
    "goog",
    "googl",
    "meta",
    "nvidia",
    "nvda",
    "micron",
    "mu",
    "broadcom",
    "avgo",
    "corning",
    "glw",
    "sandisk",
    "sndk",
    "tesla",
    "tsla",
    "netflix",
    "nflx",
    "药明康德",
    "五粮液",
    "贵州茅台",
    "兆易创新",
    "沪电股份",
)
NON_TICKER_ACRONYMS = (
    "AI",
    "API",
    "CPU",
    "CSV",
    "CSS",
    "EDGAR",
    "FRED",
    "GDP",
    "GPU",
    "HTML",
    "HTTP",
    "HTTPS",
    "JSON",
    "LLM",
    "MCP",
    "OS",
    "PDF",
    "SEC",
    "SQL",
    "TTM",
    "UI",
    "UX",
    "WRDS",
)
CODE_HINTS = (
    "fastapi",
    "api",
    "代码",
    "实现",
    "测试",
    "debug",
    "endpoint",
    "repo",
    "repository",
    "patch",
    "pull request",
    "重构",
    "修复",
)
COMPLIANCE_HINTS = (
    "compliance",
    "policy",
    "privacy",
    "pii",
    "rbac",
    "approval",
    "audit",
    "retention",
    "dlp",
    "least privilege",
    "合规",
    "政策",
    "隐私",
    "审批",
    "审计",
    "留存",
    "权限",
    "访问控制",
    "敏感信息",
    "数据泄露",
)
EVIDENCE_RESEARCH_HINTS = (
    "evidence",
    "citation",
    "cite",
    "claim",
    "source quality",
    "contradiction",
    "fact check",
    "verify",
    "verification",
    "provenance",
    "证据",
    "引用",
    "出处",
    "来源质量",
    "事实核查",
    "核验",
    "验证",
    "矛盾",
    "证伪",
    "群体智能",
    "群体决策",
    "蚁群",
    "蜂群",
    "multi-agent",
    "multi agent",
    "swarm",
    "collective decision",
    "pheromone",
    "stigmergy",
)
PORTFOLIO_HINTS = (
    "portfolio",
    "组合",
    "持仓",
    "仓位",
    "配置",
    "再平衡",
    "rebalance",
    "allocation",
    "position sizing",
)
DOCUMENT_HINTS = (
    "文档",
    "报告",
    "memo",
    "proposal",
    "撰写",
    "改写",
    "润色",
    "总结",
    "draft",
    "rewrite",
    "summarize",
    "document",
)
DATA_ANALYSIS_HINTS = (
    "csv",
    "xlsx",
    "spreadsheet",
    "表格",
    "数据分析",
    "统计",
    "dataset",
    "data analysis",
    "analyze data",
    "summary statistics",
)
PUBLIC_FINANCIAL_DATA_HINTS = (
    "sec",
    "edgar",
    "fred",
    "stooq",
    "yfinance",
    "yahoo finance",
    "kenneth french",
    "fama french",
    "french factors",
    "宏观",
    "利率",
    "filing",
    "filings",
    "factor",
    "factors",
)
LEGACY_REQUIRED_CAPABILITY_TYPES_BY_INTENT = {
    "investment_analysis": ("financial_fundamentals", "skill:value-investing-research"),
    "financial_data_retrieval": ("financial_fundamentals", "skill:value-investing-research"),
    "portfolio_review": ("portfolio.review", "skill:value-investing-research"),
    "document_writing": ("document_writing", "skill:document-writing"),
    "data_analysis": ("data_analysis", "skill:data-analysis"),
    "web_research": ("public_web_research", "skill:web-research"),
    "code_development": ("code_development", "skill:code-development"),
    "compliance_workflow": ("compliance.workflow", "skill:compliance-workflow"),
    "evidence_research": ("evidence.research", "skill:evidence-research"),
}


def infer_legacy_intent(task: str) -> str:
    lowered = str(task or "").lower()
    if any(hint in lowered for hint in COMPLIANCE_HINTS):
        return "compliance_workflow"
    if any(hint in lowered for hint in EVIDENCE_RESEARCH_HINTS):
        return "evidence_research"
    if any(hint in lowered for hint in PORTFOLIO_HINTS):
        return "portfolio_review"
    if is_legacy_investment_intent(task):
        return "investment_analysis"
    if needs_wrds_data(task):
        return "financial_data_retrieval"
    if any(hint in lowered for hint in DATA_ANALYSIS_HINTS):
        return "data_analysis"
    if any(hint in lowered for hint in DOCUMENT_HINTS):
        return "document_writing"
    if any(hint in lowered for hint in CODE_HINTS):
        return "code_development"
    if needs_web_research(task):
        return "web_research"
    return "general_chat"


def legacy_intent_reason(task: str, intent: str) -> dict[str, object]:
    lowered = str(task or "").lower()
    hint_groups = {
        "compliance_workflow": ("compliance", COMPLIANCE_HINTS),
        "evidence_research": ("evidence_research", EVIDENCE_RESEARCH_HINTS),
        "portfolio_review": ("portfolio", PORTFOLIO_HINTS),
        "data_analysis": ("data_analysis", DATA_ANALYSIS_HINTS),
        "document_writing": ("document_writing", DOCUMENT_HINTS),
        "code_development": ("code_development", CODE_HINTS),
        "web_research": ("web_research", ()),
    }
    if intent in hint_groups:
        group, hints = hint_groups[intent]
        matched = matched_hints(lowered, hints)
        if matched:
            return {"matched_hint_group": group, "matched_hints": matched[:8]}
    if intent == "investment_analysis":
        matched = matched_hints(lowered, EXPLICIT_INVESTMENT_HINTS)
        if matched:
            return {"matched_hint_group": "explicit_investment", "matched_hints": matched[:8]}
        if looks_like_public_company_reference(task):
            return {"matched_hint_group": "public_company_reference", "matched_hints": []}
        if needs_value_investing_research(task):
            return {"matched_hint_group": "legacy_value_investing_skill", "matched_hints": []}
    if intent == "financial_data_retrieval" and needs_wrds_data(task):
        return {"matched_hint_group": "wrds_data", "matched_hints": []}
    if intent == "web_research" and needs_web_research(task):
        return {"matched_hint_group": "web_research", "matched_hints": []}
    return {"matched_hint_group": "default", "matched_hints": []}


def legacy_required_capability_types(
    *,
    task: str,
    intent: str,
    protocol_required_capability_types: list[str] | None = None,
    suppress_legacy_static_fallback: bool = False,
) -> list[str]:
    protocol_required = [str(item).strip() for item in protocol_required_capability_types or [] if str(item).strip()]
    required = ["chat_model"]
    if protocol_required:
        required.extend(protocol_required)
        if needs_public_financial_data(task):
            required.append("public_financial_data")
        if needs_wrds_data(task):
            required.append("professional_financial_database")
        return unique(required)
    if suppress_legacy_static_fallback:
        return unique(required)
    required.extend(LEGACY_REQUIRED_CAPABILITY_TYPES_BY_INTENT.get(str(intent or ""), ()))
    if needs_public_financial_data(task):
        required.append("public_financial_data")
    if needs_wrds_data(task):
        required.append("professional_financial_database")
    return unique(required)


def legacy_unknown_committee_member_warning(key: str) -> str:
    return f"unknown committee member ignored: {key}"


def matched_hints(lowered_text: str, hints: tuple[str, ...]) -> list[str]:
    return [hint for hint in hints if contains_hint(lowered_text, hint)]


def is_legacy_investment_intent(task: str) -> bool:
    """Return True only when a task has explicit financial/company-investing context."""
    raw = str(task or "").strip()
    lowered = raw.lower()
    has_explicit_finance = contains_any_hint(lowered, EXPLICIT_INVESTMENT_HINTS)
    has_non_financial_context = contains_any_hint(lowered, NON_FINANCIAL_RESEARCH_HINTS)

    if has_explicit_finance:
        return True
    if has_non_financial_context:
        return False
    if needs_value_investing_research(raw):
        return True
    if looks_like_public_company_reference(raw):
        return is_short_entity_query(raw) or any(hint in lowered for hint in GENERIC_ENTITY_ANALYSIS_HINTS)
    return False


def looks_like_public_company_reference(task: str) -> bool:
    lowered = str(task or "").lower()
    if contains_any_hint(lowered, COMMON_PUBLIC_COMPANY_NAMES):
        return True
    for token in re.findall(r"\b[A-Z][A-Z0-9.]{0,5}\b", str(task or "")):
        if token in NON_TICKER_ACRONYMS:
            continue
        if 1 <= len(token.replace(".", "")) <= 5:
            return True
    return False


def contains_any_hint(lowered_text: str, hints: tuple[str, ...]) -> bool:
    return any(contains_hint(lowered_text, hint) for hint in hints)


def contains_hint(lowered_text: str, hint: str) -> bool:
    needle = hint.lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9 .:/&+-]*", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lowered_text) is not None
    return needle in lowered_text


def is_short_entity_query(task: str) -> bool:
    normalized = re.sub(r"[“”\"'()（）\[\]{}，,。.!?？:：；;]+", " ", str(task or "")).strip()
    if not normalized:
        return False
    tokens = [token for token in re.split(r"\s+", normalized) if token]
    return len(tokens) <= 3 and len(normalized) <= 32


def needs_public_financial_data(task: str) -> bool:
    lowered = str(task or "").lower()
    return any(hint in lowered for hint in PUBLIC_FINANCIAL_DATA_HINTS)


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
