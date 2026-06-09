from __future__ import annotations


LEGACY_KNOWN_RESEARCH_COMPANY_MARKERS = (
    "药明康德",
    "wuxi apptec",
    "五粮液",
    "wuliangye",
    "贵州茅台",
    "kweichow moutai",
    "moutai",
    "兆易创新",
    "gigadevice",
    "沪电股份",
    "wus printed circuit",
)
LEGACY_NON_COMPANY_QUERY_MARKERS = (
    "release note",
    "documentation",
    "docs",
    "api",
    "fastapi",
    "langgraph",
    "github",
    "python",
    "openai",
    "旅游",
    "景点",
    "文档",
    "教程",
    "路线",
)
LEGACY_TICKER_EXCLUDED_CODES = {"API", "DOC", "DOCS"}
LEGACY_CJK_COMPANY_SUFFIXES = ("股份", "公司", "集团", "银行", "科技", "控股", "有限")
LEGACY_COMPANY_QUERY_INTENT_MARKERS = ("公司", "股票", "财报", "估值", "投资", "ticker", "stock", "valuation")


def legacy_known_research_company_markers() -> tuple[str, ...]:
    return tuple(LEGACY_KNOWN_RESEARCH_COMPANY_MARKERS)


def legacy_non_company_query_markers() -> tuple[str, ...]:
    return tuple(LEGACY_NON_COMPANY_QUERY_MARKERS)


def legacy_ticker_excluded_codes() -> set[str]:
    return set(LEGACY_TICKER_EXCLUDED_CODES)


def legacy_cjk_company_suffixes() -> tuple[str, ...]:
    return tuple(LEGACY_CJK_COMPANY_SUFFIXES)


def legacy_company_query_intent_markers() -> tuple[str, ...]:
    return tuple(LEGACY_COMPANY_QUERY_INTENT_MARKERS)
