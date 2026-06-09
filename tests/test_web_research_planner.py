from __future__ import annotations

from runtime.web_research_planner import ensure_required_web_research_step


def test_web_research_planner_inserts_search_step_for_research_skill() -> None:
    plan = [{"id": "analysis", "title": "Analyze", "tool_calls": []}]

    updated = ensure_required_web_research_step(
        plan,
        task="调研 LangGraph 最新文档",
        english_search_query="LangGraph release notes",
        selected_skills=[{"name": "web-research"}],
        preferred_web_search_tool="provider_web_search",
    )

    assert updated[0]["id"] == "web-search"
    assert updated[0]["tool_calls"] == [
        {"name": "provider_web_search", "args": {"query": "LangGraph release notes", "max_results": 5}}
    ]
    assert updated[1] == plan[0]


def test_web_research_planner_uses_capability_metadata_not_only_legacy_skill_names() -> None:
    plan = [{"id": "analysis", "title": "Analyze", "tool_calls": []}]

    updated = ensure_required_web_research_step(
        plan,
        task="Review the claim against public sources",
        english_search_query="claim public source review",
        selected_skills=[{"name": "quality-lens", "capability_types": ["evidence.research"]}],
    )

    assert updated[0]["id"] == "web-search"
    assert updated[0]["tool_calls"] == [
        {"name": "web_search", "args": {"query": "claim public source review", "max_results": 5}}
    ]


def test_web_research_planner_preserves_original_language_without_translated_query() -> None:
    updated = ensure_required_web_research_step(
        [{"id": "analysis", "title": "Analyze", "tool_calls": []}],
        task="调研杭州旅游",
        selected_skills=[{"name": "web-research"}],
    )

    assert updated[0]["tool_calls"][0]["args"]["query"] == "调研杭州旅游"


def test_web_research_planner_does_not_insert_when_source_policy_blocks_web() -> None:
    plan = [{"id": "analysis", "title": "Analyze", "tool_calls": []}]

    updated = ensure_required_web_research_step(
        plan,
        task="SNDK investment analysis",
        selected_skills=[{"name": "value-investing-research"}],
        source_mode="WRDS_ONLY",
    )

    assert updated == plan
