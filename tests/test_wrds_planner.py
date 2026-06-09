from __future__ import annotations

from runtime.wrds_planner import build_wrds_data_plan, normalize_data_packages, normalize_research_questions


def test_wrds_planner_expands_investment_packages_without_field_prompting() -> None:
    plan = build_wrds_data_plan(
        task="MU",
        orchestration={
            "task_type": "investment",
            "required_data_packages": ["company_identity", "annual_financials_10y", "quarterly_financials_16q"],
        },
    )

    assert plan["planner"] == "deterministic_wrds_planner"
    assert plan["industry_profile"] == "semiconductor_memory"
    assert plan["required_actual_periods"] == {"annual_years": 10, "quarterly_quarters": 16}
    assert "sale" in plan["fields_by_table"]["comp.funda"]
    assert "saleq" in plan["fields_by_table"]["comp.fundq"]
    assert "xint" in plan["fields_by_table"]["comp.funda"]
    assert "gdwl" in plan["fields_by_table"]["comp.funda"]
    assert "ajex" in plan["fields_by_table"]["comp.funda"]
    assert "fields_by_table" in plan


def test_default_investment_packages_add_semiconductor_cycle_for_mu() -> None:
    packages = normalize_data_packages(None, task="MU", task_type="investment")

    assert "company_identity" in packages
    assert "annual_financials_10y" in packages
    assert "quarterly_financials_16q" in packages
    assert "crsp_market_data" in packages
    assert "capital_iq_profile" in packages
    assert "optionmetrics_security" not in packages
    assert "ibes_estimates" not in packages
    assert "compustat_segments" not in packages
    assert "debt_interest_coverage" in packages
    assert "capital_returns" in packages
    assert "goodwill_intangibles" in packages
    assert "split_adjustment" in packages
    assert "semiconductor_cycle" in packages
    assert "peer_comparison" in packages


def test_omitted_wrds_task_type_preserves_legacy_investment_defaults() -> None:
    packages = normalize_data_packages(None, task="MU")

    assert "company_identity" in packages
    assert "semiconductor_cycle" in packages
    assert "peer_comparison" in packages


def test_unavailable_wrds_packages_are_filtered_from_account_default_plan() -> None:
    packages = normalize_data_packages(
        ["company_identity", "ibes_estimates", "compustat_segments", "crsp_market_data"],
        task="AVGO",
        task_type="investment",
    )

    assert "company_identity" in packages
    assert "crsp_market_data" in packages
    assert "capital_iq_profile" in packages
    assert "optionmetrics_security" not in packages
    assert "ibes_estimates" not in packages
    assert "compustat_segments" not in packages


def test_optionmetrics_is_conditional_on_market_risk_tasks() -> None:
    packages = normalize_data_packages(None, task="AAPL volatility and options market risk", task_type="investment")

    assert "optionmetrics_security" in packages
    assert "ibes_estimates" not in packages
    assert "compustat_segments" not in packages


def test_research_questions_are_domain_aware_defaults() -> None:
    questions = normalize_research_questions(None, task="MU", industry_profile="semiconductor_memory")

    assert any("HBM" in question for question in questions)
    assert any("cycle" in question.lower() for question in questions)
