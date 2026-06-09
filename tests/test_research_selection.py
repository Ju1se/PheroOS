from __future__ import annotations

from runtime.research_selection import (
    skill_requests_company_financial_data,
    skill_requests_direct_wrds_data,
    skill_requests_investment_research,
    skill_requests_public_web_research,
)


def test_research_selection_uses_capability_metadata_before_legacy_skill_names() -> None:
    assert skill_requests_public_web_research({"name": "quality-lens", "capability_types": ["public_web_research"]})
    assert skill_requests_company_financial_data(
        {"name": "renamed-financial-data", "capability_types": ["professional_financial_database"]}
    )
    assert skill_requests_investment_research(
        {"name": "renamed-portfolio-research", "capability_types": ["investment.research"]}
    )
    assert skill_requests_direct_wrds_data({"name": "renamed-wrds", "wrds_data": True})


def test_research_selection_keeps_legacy_skill_names_as_compatibility() -> None:
    assert skill_requests_public_web_research({"name": "web-research"})
    assert skill_requests_company_financial_data({"name": "wrds-data"})
    assert skill_requests_investment_research({"name": "value-investing-research"})
    assert skill_requests_direct_wrds_data({"name": "wrds-data"})
