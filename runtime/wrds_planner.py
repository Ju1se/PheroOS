from __future__ import annotations

from typing import Any

from runtime.legacy_wrds_planner_defaults import (
    ACCOUNT_AVAILABLE_PACKAGES,
    ACCOUNT_UNAVAILABLE_PACKAGES,
    BASE_INVESTMENT_PACKAGES,
    MARKET_RISK_PACKAGES,
    PACKAGE_CATALOG,
    SEMICONDUCTOR_PACKAGES,
    build_default_data_packages,
    build_default_research_questions,
    infer_industry_profile,
    legacy_wrds_investment_defaults_enabled,
    legacy_wrds_task_type,
    requires_optionmetrics_market_risk,
)


def normalize_data_packages(value: Any, *, task: str, task_type: str | None = None) -> list[str]:
    normalized_task_type = legacy_wrds_task_type(task_type)
    if isinstance(value, str):
        raw = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw = [str(item).strip() for item in value]
    else:
        raw = []
    packages = [item for item in raw if item in PACKAGE_CATALOG and item not in ACCOUNT_UNAVAILABLE_PACKAGES]
    if not packages and legacy_wrds_investment_defaults_enabled(normalized_task_type):
        packages = build_default_data_packages(task, task_type=normalized_task_type)
    elif packages and legacy_wrds_investment_defaults_enabled(normalized_task_type):
        packages = dedupe_packages([*packages, *build_default_data_packages(task, task_type=normalized_task_type)])
    if "company_identity" not in packages and legacy_wrds_investment_defaults_enabled(normalized_task_type):
        packages.insert(0, "company_identity")
    return dedupe_packages(packages)


def normalize_research_questions(value: Any, *, task: str, industry_profile: str) -> list[str]:
    if isinstance(value, str):
        questions = [value.strip()]
    elif isinstance(value, list):
        questions = [str(item).strip() for item in value]
    else:
        questions = []
    questions = [item for item in questions if item]
    return questions or build_default_research_questions(task, industry_profile=industry_profile)


def build_wrds_data_plan(
    *,
    task: str,
    orchestration: dict[str, Any] | None = None,
    data_packages: list[str] | None = None,
) -> dict[str, Any]:
    orchestration = orchestration or {}
    task_type = legacy_wrds_task_type(orchestration.get("task_type"))
    packages = normalize_data_packages(
        data_packages if data_packages is not None else orchestration.get("required_data_packages"),
        task=task,
        task_type=task_type,
    )
    annual_years = 10 if "annual_financials_10y" in packages else 5
    quarterly_quarters = 16 if "quarterly_financials_16q" in packages else 0
    fields_by_table: dict[str, list[str]] = {}
    for package in packages:
        spec = PACKAGE_CATALOG.get(package, {})
        for table in spec.get("tables", []):
            fields_by_table.setdefault(table, [])
            fields_by_table[table] = dedupe_fields([*fields_by_table[table], *spec.get("fields", [])])
    unavailable_requested = [package for package in packages if package in ACCOUNT_UNAVAILABLE_PACKAGES]
    return {
        "status": "planned",
        "planner": "deterministic_wrds_planner",
        "account_permission_profile": "current_account_queryable_packages_only",
        "account_available_packages": sorted(ACCOUNT_AVAILABLE_PACKAGES),
        "account_unavailable_packages": sorted(ACCOUNT_UNAVAILABLE_PACKAGES),
        "unavailable_requested_packages": unavailable_requested,
        "industry_profile": infer_industry_profile(task),
        "data_packages": packages,
        "required_actual_periods": {
            "annual_years": annual_years,
            "quarterly_quarters": quarterly_quarters,
        },
        "fields_by_table": fields_by_table,
        "package_descriptions": {name: PACKAGE_CATALOG[name]["description"] for name in packages if name in PACKAGE_CATALOG},
        "peer_candidates": PACKAGE_CATALOG["peer_comparison"].get("default_peers", []) if "peer_comparison" in packages else [],
    }


def dedupe_packages(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def dedupe_fields(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
