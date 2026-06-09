from __future__ import annotations

from runtime.wrds_company_planner import (
    ensure_required_wrds_company_step,
    normalize_wrds_company_tool_args,
    wrds_company_data_required,
)


def test_wrds_company_planner_inserts_required_company_financials_step() -> None:
    plan = [{"id": "analysis", "title": "Analyze", "tool_calls": []}]

    updated = ensure_required_wrds_company_step(
        plan,
        task="ORCL",
        orchestration={"task_type": "investment", "required_agents": {"wrds": True}},
        selected_skills=[{"name": "value-investing-research"}],
        available_tools=[{"name": "wrds_company_financials"}],
    )

    assert updated[0]["id"] == "wrds-company-financials"
    assert updated[0]["tool_calls"][0]["name"] == "wrds_company_financials"
    assert updated[0]["tool_calls"][0]["args"]["query"] == "ORCL"
    assert updated[0]["data_plan"]["planner"] == "deterministic_wrds_planner"
    assert updated[1] == plan[0]


def test_wrds_company_planner_augments_existing_financials_step() -> None:
    plan = [
        {
            "id": "wrds",
            "title": "Fetch",
            "tool_calls": [
                {
                    "name": "wrds_company_financials",
                    "args": {"query": "AAPL", "max_years": 3, "max_quarters": 2, "data_packages": ["company_identity"]},
                }
            ],
        }
    ]

    updated = ensure_required_wrds_company_step(
        plan,
        task="AAPL",
        orchestration={"task_type": "investment", "required_agents": {"wrds": True}},
        selected_skills=[],
        available_tools=[{"name": "wrds_company_financials"}],
    )

    args = updated[0]["tool_calls"][0]["args"]
    assert args["max_years"] == 10
    assert args["max_quarters"] == 16
    assert "valuation_snapshot" in args["data_packages"]
    assert updated[0]["data_plan"]["planner"] == "deterministic_wrds_planner"


def test_wrds_company_requirement_uses_capability_metadata_not_only_legacy_skill_name() -> None:
    task = "define API documentation"
    orchestration = {"task_type": "general", "required_agents": {}}

    assert wrds_company_data_required(
        task=task,
        orchestration=orchestration,
        selected_skills=[{"name": "quality-investment", "capability_types": ["investment.research"]}],
    ) is True
    assert wrds_company_data_required(
        task=task,
        orchestration=orchestration,
        selected_skills=[{"name": "quality-lens"}],
    ) is False


def test_wrds_company_requirement_does_not_follow_task_type_without_data_signal() -> None:
    assert wrds_company_data_required(
        task="define API documentation",
        orchestration={"task_type": "investment", "required_agents": {}},
        selected_skills=[],
    ) is False


def test_wrds_company_tool_args_normalize_shorthand_query() -> None:
    args = normalize_wrds_company_tool_args(
        {},
        state={"task": "SNDK"},
        step={"title": "Resolve company"},
        tool_name="wrds_company_search",
    )

    assert args == {"query": "SNDK", "max_results": 8}
