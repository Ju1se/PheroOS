from __future__ import annotations

import re
from typing import Any

from runtime.legacy_wrds_company_planner import (
    legacy_cjk_company_suffixes,
    legacy_company_query_intent_markers,
    legacy_known_research_company_markers,
    legacy_non_company_query_markers,
    legacy_ticker_excluded_codes,
)
from runtime.research_selection import selected_skills_request_company_financial_data
from runtime.wrds_planner import build_wrds_data_plan, normalize_data_packages
from tools.web_tools import has_cjk
from tools.wrds_tools import COMPANY_ALIASES, clean_company_query, company_search_terms


def known_research_company_markers() -> tuple[str, ...]:
    return legacy_known_research_company_markers()


def ensure_required_wrds_company_step(
    plan: list[dict[str, Any]],
    *,
    task: str,
    orchestration: dict[str, Any],
    selected_skills: list[dict[str, Any]],
    available_tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    available_tool_names = {str(tool.get("name") or "") for tool in available_tools if isinstance(tool, dict)}
    if "wrds_company_financials" not in available_tool_names:
        return plan
    if not wrds_company_data_required(task=task, orchestration=orchestration, selected_skills=selected_skills):
        return plan

    company_query = extract_company_query(task)
    wrds_plan = build_wrds_data_plan(task=task, orchestration=orchestration)
    if plan_has_tool_call(plan, "wrds_company_financials"):
        return augment_wrds_company_financials_steps(plan, task=task, wrds_plan=wrds_plan)
    if plan_has_any_tool_call(plan, {"wrds_query"}):
        return plan
    wrds_step = {
        "id": "wrds-company-financials",
        "title": "WRDS company financial data",
        "action": "Resolve the company in WRDS and retrieve the planned professional data packages.",
        "tool_calls": [
            {
                "name": "wrds_company_financials",
                "args": {
                    "query": company_query,
                    "max_years": wrds_plan["required_actual_periods"]["annual_years"],
                    "max_quarters": wrds_plan["required_actual_periods"]["quarterly_quarters"],
                    "max_candidates": 5,
                    "data_packages": wrds_plan["data_packages"],
                },
            }
        ],
        "data_plan": wrds_plan,
    }
    return [wrds_step, *plan]


def augment_wrds_company_financials_steps(
    plan: list[dict[str, Any]],
    *,
    task: str,
    wrds_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    required_periods = wrds_plan.get("required_actual_periods") if isinstance(wrds_plan.get("required_actual_periods"), dict) else {}
    required_years = parse_positive_int(required_periods.get("annual_years"), 10)
    required_quarters = parse_positive_int(required_periods.get("quarterly_quarters"), 16)
    required_packages = wrds_plan.get("data_packages") if isinstance(wrds_plan.get("data_packages"), list) else []
    updated_plan: list[dict[str, Any]] = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        tool_calls = step.get("tool_calls")
        if not isinstance(tool_calls, list):
            updated_plan.append(step)
            continue
        updated_calls = []
        changed = False
        for call in tool_calls:
            if not isinstance(call, dict) or call.get("name") != "wrds_company_financials":
                updated_calls.append(call)
                continue
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            packages = normalize_data_packages(
                [*listify(args.get("data_packages") or args.get("packages")), *listify(required_packages)],
                task=task,
                task_type="investment",
            )
            updated_calls.append(
                {
                    **call,
                    "args": {
                        **args,
                        "query": str(args.get("query") or extract_company_query(task)),
                        "max_years": max(parse_positive_int(args.get("max_years"), required_years), required_years),
                        "max_quarters": max(parse_positive_int(args.get("max_quarters"), required_quarters), required_quarters),
                        "max_candidates": max(parse_positive_int(args.get("max_candidates"), 5), 5),
                        "data_packages": packages,
                    },
                }
            )
            changed = True
        updated_step = {**step, "tool_calls": updated_calls}
        if changed:
            updated_step["data_plan"] = wrds_plan
        updated_plan.append(updated_step)
    return updated_plan


def wrds_company_data_required(
    *,
    task: str,
    orchestration: dict[str, Any],
    selected_skills: list[dict[str, Any]],
) -> bool:
    required = orchestration.get("required_agents") if isinstance(orchestration, dict) else {}
    if isinstance(required, dict) and required.get("wrds"):
        return True
    if selected_skills_request_company_financial_data(selected_skills):
        return True
    lowered = task.lower()
    if any(marker in lowered for marker in known_research_company_markers()):
        return True
    if any(term in lowered for term in legacy_company_query_intent_markers()):
        return bool(company_search_terms(task))
    return looks_like_ticker_or_company_name(task)


def extract_company_query(task: str) -> str:
    for alias in sorted(company_search_terms(task), key=len, reverse=True):
        if alias and (alias in task or alias.lower() in task.lower()):
            return alias
    cleaned = clean_company_query(task)
    return cleaned or task.strip()


def looks_like_ticker_or_company_name(task: str) -> bool:
    text = task.strip()
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in ("解释", "什么是", "define", "definition", "meaning", "概念")):
        return False
    return looks_like_wrds_company_query(text)


def looks_like_wrds_company_query(task: str) -> bool:
    text = task.strip()
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in legacy_non_company_query_markers()):
        return False

    cleaned = clean_company_query(text).strip()
    if not cleaned:
        return False
    cleaned_lower = cleaned.lower()
    known_aliases = {alias.lower() for alias in COMPANY_ALIASES}
    known_aliases.update(str(value).lower() for values in COMPANY_ALIASES.values() for value in values)
    if cleaned_lower in known_aliases:
        return True
    if re.fullmatch(r"[A-Z]{1,6}(?:\.[A-Z])?", cleaned) and cleaned not in legacy_ticker_excluded_codes():
        return True
    if has_cjk(cleaned) and any(suffix in cleaned for suffix in legacy_cjk_company_suffixes()):
        return True
    if (
        not has_cjk(cleaned)
        and len(cleaned) <= 40
        and len(cleaned.split()) <= 4
        and bool(company_search_terms(cleaned))
    ):
        return True
    return False


def normalize_wrds_company_tool_args(
    args: dict[str, Any],
    *,
    state: dict[str, Any],
    step: dict[str, Any] | None = None,
    tool_name: str,
) -> dict[str, Any]:
    normalized = dict(args or {})
    if not str(normalized.get("query") or "").strip():
        normalized["query"] = infer_wrds_company_query(state=state, step=step)
    if tool_name == "wrds_company_search":
        normalized["max_results"] = parse_positive_int(normalized.get("max_results"), 8)
    return normalized


def infer_wrds_company_query(*, state: dict[str, Any], step: dict[str, Any] | None = None) -> str:
    task_query = extract_company_query(str(state.get("task") or ""))
    if task_query:
        return task_query
    if step:
        for key in ("title", "action"):
            value = str(step.get(key) or "").strip()
            if value:
                step_query = extract_company_query(value)
                if step_query:
                    return step_query
    return str(state.get("task") or "").strip()


def plan_has_tool_call(plan: list[dict[str, Any]], tool_name: str) -> bool:
    return plan_has_any_tool_call(plan, {tool_name})


def plan_has_any_tool_call(plan: list[dict[str, Any]], tool_names: set[str]) -> bool:
    for step in plan:
        tool_calls = step.get("tool_calls") or []
        if any(call.get("name") in tool_names for call in tool_calls if isinstance(call, dict)):
            return True
    return False


def listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def parse_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
