from __future__ import annotations


LEGACY_RESEARCH_SKILL_NAMES = {"web-research", "value-investing-research"}
LEGACY_PUBLIC_WEB_RESEARCH_SKILL_NAMES = {"web-research"}
LEGACY_COMPANY_FINANCIAL_DATA_SKILL_NAMES = {"value-investing-research", "wrds-data"}
LEGACY_INVESTMENT_RESEARCH_SKILL_NAMES = {"value-investing-research"}
LEGACY_DIRECT_WRDS_DATA_SKILL_NAMES = {"wrds-data"}
LEGACY_RESEARCH_CAPABILITY_TYPE_MARKERS = {"public_web_research", "evidence.research", "investment.research"}
LEGACY_PUBLIC_WEB_RESEARCH_CAPABILITY_TYPE_MARKERS = {"public_web_research", "skill:web-research"}
LEGACY_COMPANY_FINANCIAL_DATA_CAPABILITY_TYPE_MARKERS = {
    "financial_fundamentals",
    "investment.research",
    "professional_financial_database",
    "skill:value-investing-research",
}
LEGACY_INVESTMENT_RESEARCH_CAPABILITY_TYPE_MARKERS = {
    "investment.research",
    "portfolio.review",
    "skill:value-investing-research",
}
LEGACY_DIRECT_WRDS_DATA_CAPABILITY_TYPE_MARKERS = {
    "professional_financial_database",
    "financial_data_source",
    "skill:wrds-data",
}
LEGACY_RESEARCH_METADATA_FLAGS = {"requires_web_research", "public_web_research", "web_research"}
LEGACY_PUBLIC_WEB_RESEARCH_METADATA_FLAGS = {"requires_web_research", "public_web_research", "web_research"}
LEGACY_COMPANY_FINANCIAL_DATA_METADATA_FLAGS = {
    "company_financial_data",
    "professional_financial_data",
    "requires_wrds_company_financials",
    "wrds_company_financials",
}
LEGACY_INVESTMENT_RESEARCH_METADATA_FLAGS = {"investment_research", "value_investing_research", "portfolio_review"}
LEGACY_DIRECT_WRDS_DATA_METADATA_FLAGS = {"wrds_data", "direct_wrds_data", "professional_financial_database"}


def legacy_research_skill_names() -> set[str]:
    return set(LEGACY_RESEARCH_SKILL_NAMES)


def legacy_public_web_research_skill_names() -> set[str]:
    return set(LEGACY_PUBLIC_WEB_RESEARCH_SKILL_NAMES)


def legacy_company_financial_data_skill_names() -> set[str]:
    return set(LEGACY_COMPANY_FINANCIAL_DATA_SKILL_NAMES)


def legacy_investment_research_skill_names() -> set[str]:
    return set(LEGACY_INVESTMENT_RESEARCH_SKILL_NAMES)


def legacy_direct_wrds_data_skill_names() -> set[str]:
    return set(LEGACY_DIRECT_WRDS_DATA_SKILL_NAMES)


def legacy_research_capability_type_markers() -> set[str]:
    return set(LEGACY_RESEARCH_CAPABILITY_TYPE_MARKERS)


def legacy_public_web_research_capability_type_markers() -> set[str]:
    return set(LEGACY_PUBLIC_WEB_RESEARCH_CAPABILITY_TYPE_MARKERS)


def legacy_company_financial_data_capability_type_markers() -> set[str]:
    return set(LEGACY_COMPANY_FINANCIAL_DATA_CAPABILITY_TYPE_MARKERS)


def legacy_investment_research_capability_type_markers() -> set[str]:
    return set(LEGACY_INVESTMENT_RESEARCH_CAPABILITY_TYPE_MARKERS)


def legacy_direct_wrds_data_capability_type_markers() -> set[str]:
    return set(LEGACY_DIRECT_WRDS_DATA_CAPABILITY_TYPE_MARKERS)


def legacy_research_metadata_flags() -> set[str]:
    return set(LEGACY_RESEARCH_METADATA_FLAGS)


def legacy_public_web_research_metadata_flags() -> set[str]:
    return set(LEGACY_PUBLIC_WEB_RESEARCH_METADATA_FLAGS)


def legacy_company_financial_data_metadata_flags() -> set[str]:
    return set(LEGACY_COMPANY_FINANCIAL_DATA_METADATA_FLAGS)


def legacy_investment_research_metadata_flags() -> set[str]:
    return set(LEGACY_INVESTMENT_RESEARCH_METADATA_FLAGS)


def legacy_direct_wrds_data_metadata_flags() -> set[str]:
    return set(LEGACY_DIRECT_WRDS_DATA_METADATA_FLAGS)
