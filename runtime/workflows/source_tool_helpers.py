from __future__ import annotations

from typing import Any

from runtime.research_selection import (
    selected_skills_request_investment_research,
    skill_requests_public_web_research,
)
from runtime.tool_names import (
    APPROVED_SOURCE_FETCH_TOOL_NAME,
    FETCH_URL_TOOL_NAME,
    PROVIDER_WEB_SEARCH_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
)
from runtime.wrds_company_planner import known_research_company_markers
from runtime.workflows.legacy_source_grounding import legacy_source_grounding_keywords
from tools.web_tools import score_search_result


SEARCH_TOOL_NAMES = {WEB_SEARCH_TOOL_NAME, PROVIDER_WEB_SEARCH_TOOL_NAME}
FETCH_TOOL_NAMES = {FETCH_URL_TOOL_NAME, APPROVED_SOURCE_FETCH_TOOL_NAME}
WRDS_COMPANY_TOOL_NAMES = {"wrds_company_search", "wrds_company_financials"}

def should_auto_fetch_search_results(
    task: str,
    args: dict[str, Any],
    *,
    selected_skills: list[dict[str, Any]] | None = None,
    english_search_query: str | None = None,
) -> bool:
    if args.get("fetch_top_results") is False:
        return False
    if args.get("fetch_top_results") is True:
        return True
    if web_research_selected(selected_skills):
        return True
    if looks_like_known_entity_research(task, args=args, english_search_query=english_search_query):
        return True
    text = task.lower()
    return any(keyword in text for keyword in legacy_source_grounding_keywords())


def web_research_selected(selected_skills: list[dict[str, Any]] | None) -> bool:
    return any(skill_requests_public_web_research(skill) for skill in selected_skills or [])


def value_research_selected(selected_skills: list[dict[str, Any]] | None) -> bool:
    return selected_skills_request_investment_research(selected_skills or [])


def looks_like_known_entity_research(
    task: str,
    *,
    args: dict[str, Any] | None = None,
    english_search_query: str | None = None,
) -> bool:
    query = str((args or {}).get("query") or "")
    combined = " ".join([task, query, english_search_query or ""]).lower()
    return any(marker in combined for marker in known_research_company_markers())


def select_search_result_urls(search_data: dict[str, Any], *, limit: int = 5) -> list[str]:
    results = search_data.get("results", [])
    if not isinstance(results, list):
        return []

    query = str(search_data.get("searched_query") or search_data.get("query") or "")
    scored = []
    for index, item in enumerate(results):
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        url = item["url"]
        title = str(item.get("title") or "").lower()
        snippet = str(item.get("snippet") or "").lower()
        haystack = f"{title} {url} {snippet}".lower()
        score = score_search_result(item, query)
        if "docs." in haystack or "/docs" in haystack or "documentation" in haystack:
            score += 5
        if "github.com" in haystack:
            score += 3
        if "official" in title or "官方网站" in title or "官网" in title:
            score += 2
        if "investor" in haystack or "annual report" in haystack or "financial reports" in haystack:
            score += 6
        scored.append((score, -index, url))

    scored.sort(reverse=True)
    return [url for _, _, url in scored[:limit]]


def preferred_source_fetch_tool(tool_names: list[str] | set[str]) -> str:
    names = set(tool_names or [])
    if APPROVED_SOURCE_FETCH_TOOL_NAME in names:
        return APPROVED_SOURCE_FETCH_TOOL_NAME
    return FETCH_URL_TOOL_NAME


def step_tool_results_succeeded(results: list[dict[str, Any]]) -> bool:
    if not results:
        return True
    non_fetch_results = [item for item in results if item.get("name") not in FETCH_TOOL_NAMES]
    if non_fetch_results and not all(item["result"].get("ok") for item in non_fetch_results):
        if any(item.get("name") in SEARCH_TOOL_NAMES and item["result"].get("ok") for item in results):
            return True
        return False
    if any(item.get("name") in SEARCH_TOOL_NAMES and item["result"].get("ok") for item in results):
        return True
    return all(item["result"].get("ok") for item in results)


def summarize_execution_metric_status(execution_log: list[dict[str, Any]]) -> tuple[str, str | None]:
    failed_tools = []
    failed_steps = any(step.get("status") == "failed" for step in execution_log)
    for step in execution_log:
        has_successful_search = any(
            isinstance(call, dict)
            and call.get("name") in SEARCH_TOOL_NAMES
            and (call.get("result") or {}).get("ok")
            for call in step.get("tool_calls", []) or []
        )
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            result = call.get("result") or {}
            if result.get("ok") is False:
                if call.get("name") in SEARCH_TOOL_NAMES and has_successful_search:
                    continue
                if call.get("name") in FETCH_TOOL_NAMES and has_successful_search:
                    continue
                failed_tools.append(f"{call.get('name')}: {result.get('error') or 'tool returned ok=false'}")

    if not failed_tools:
        return "completed", None

    status = "completed_with_step_failures" if failed_steps else "completed_with_partial_tool_failures"
    return status, "; ".join(failed_tools[:3])


def should_upgrade_search_to_provider(state: dict[str, Any], tool_names: list[str]) -> bool:
    if PROVIDER_WEB_SEARCH_TOOL_NAME not in set(tool_names):
        return False
    if web_research_selected(state.get("selected_skills")) or value_research_selected(state.get("selected_skills")):
        return True
    return False


def requires_source_grounding(state: dict[str, Any]) -> bool:
    if web_research_selected(state.get("selected_skills")) or value_research_selected(state.get("selected_skills")):
        return True
    if any_search_tool_called(state.get("execution_log", [])):
        return looks_like_known_entity_research(
            str(state.get("task") or ""),
            args={"query": state.get("english_search_query") or ""},
            english_search_query=state.get("english_search_query"),
        )
    return False


def any_tool_called(execution_log: Any, tool_name: str) -> bool:
    if not isinstance(execution_log, list):
        return False
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        for call in step.get("tool_calls", []) or []:
            if isinstance(call, dict) and call.get("name") == tool_name:
                return True
    return False


def any_search_tool_called(execution_log: Any) -> bool:
    return any(any_tool_called(execution_log, tool_name) for tool_name in SEARCH_TOOL_NAMES)


def has_fetched_source_text(execution_log: Any, *, min_word_count: int = 80) -> bool:
    if not isinstance(execution_log, list):
        return False
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict) or call.get("name") not in FETCH_TOOL_NAMES:
                continue
            result = call.get("result") or {}
            data = result.get("data") or {}
            try:
                word_count = int(data.get("word_count") or 0)
            except (TypeError, ValueError):
                word_count = 0
            if result.get("ok") and word_count >= min_word_count:
                return True
    return False


def has_provider_web_search_results(execution_log: Any) -> bool:
    if not isinstance(execution_log, list):
        return False
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict) or call.get("name") != PROVIDER_WEB_SEARCH_TOOL_NAME:
                continue
            result = call.get("result") or {}
            data = result.get("data") or {}
            if result.get("ok") and isinstance(data.get("results"), list) and data["results"]:
                return True
    return False


def has_wrds_professional_data(execution_log: Any) -> bool:
    if not isinstance(execution_log, list):
        return False
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict) or call.get("name") != "wrds_company_financials":
                continue
            result = call.get("result") or {}
            data = result.get("data") or {}
            if result.get("ok") and data.get("status") == "matched_with_financials" and data.get("row_count"):
                return True
    return False


def describe_source_grounding(state: dict[str, Any]) -> str:
    execution_log = state.get("execution_log", [])
    if has_fetched_source_text(execution_log):
        return "fetched_source_text"
    if has_wrds_professional_data(execution_log):
        return "wrds_professional_data"
    if any_tool_called(execution_log, PROVIDER_WEB_SEARCH_TOOL_NAME):
        return "provider_native_web_search"
    if any_tool_called(execution_log, WEB_SEARCH_TOOL_NAME):
        return "search_snippets_only"
    return "no_external_sources"
