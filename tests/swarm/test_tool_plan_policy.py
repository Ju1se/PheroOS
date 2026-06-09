from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runtime.swarm.tool_plan_policy import (
    effective_source_mode_decision_for_orchestration,
    effective_source_mode_for_orchestration,
    filter_plan_by_source_and_tool_policy,
    partition_skills_by_source_policy,
    source_mode_is_wrds_only,
    web_tools_disabled_for_state,
    wrds_source_required_for_state,
)
from runtime.swarm.action_policy import source_policy_blocked_tool_targets_from_policy
from runtime.swarm.legacy_tool_policy import legacy_web_research_tool_actions
from runtime.swarm.policing import tool_policy_violations
from runtime.swarm.signal_extractor import initial_signals_from_state


@dataclass(frozen=True)
class SkillStub:
    name: str


def test_tool_plan_policy_filters_web_tools_for_wrds_alias_modes() -> None:
    plan = [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [
                {"name": "provider_web_search", "args": {"query": "SNDK"}},
                {"name": "wrds_company_financials", "args": {"query": "SNDK"}},
            ],
        }
    ]

    updated = filter_plan_by_source_and_tool_policy(plan, source_mode="WRDS-FIRST")

    assert source_mode_is_wrds_only("WRDS-FIRST") is True
    assert updated == [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [{"name": "wrds_company_financials", "args": {"query": "SNDK"}}],
        }
    ]


def test_tool_plan_policy_applies_capability_block_and_allow_rules_without_source_mode() -> None:
    plan = [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [
                {"name": "approved_source_fetch", "args": {"url": "https://example.com"}},
                {"name": "wrds_company_financials", "args": {"query": "SNDK"}},
                {"name": "read_file", "args": {"path": "README.md"}},
            ],
        }
    ]

    updated = filter_plan_by_source_and_tool_policy(
        plan,
        source_mode=None,
        tool_policy={
            "blocked_tool_targets": ["tool:approved_source_fetch"],
            "allowed_tool_targets": ["tool:wrds_company_financials"],
        },
    )

    assert updated == [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [{"name": "wrds_company_financials", "args": {"query": "SNDK"}}],
        }
    ]


def test_source_policy_filter_uses_declared_blocked_tool_targets() -> None:
    plan = [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [
                {"name": "custom_news_api", "args": {"query": "SNDK"}},
                {"name": "web_search", "args": {"query": "SNDK"}},
                {"name": "wrds_company_financials", "args": {"query": "SNDK"}},
            ],
        }
    ]

    updated = filter_plan_by_source_and_tool_policy(
        plan,
        source_mode="WRDS_ONLY",
        tool_policy={"source_policy_blocked_tool_targets": ["tool:custom_news_api"]},
    )

    assert updated == [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [
                {"name": "web_search", "args": {"query": "SNDK"}},
                {"name": "wrds_company_financials", "args": {"query": "SNDK"}},
            ],
        }
    ]


def test_source_policy_uses_declared_targets_before_legacy_web_tool_compatibility() -> None:
    declared = source_policy_blocked_tool_targets_from_policy(
        {"source_policy_blocked_tool_targets": ["tool:custom_news_api"]}
    )
    fallback = source_policy_blocked_tool_targets_from_policy({})

    assert declared == {"tool:custom_news_api"}
    assert "tool:web_search" not in declared
    assert fallback == legacy_web_research_tool_actions()


def test_source_policy_accepts_legacy_blocked_tool_target_field_alias() -> None:
    assert source_policy_blocked_tool_targets_from_policy(
        {"web_research_tool_targets": ["custom_news_api"]}
    ) == {"custom_news_api"}


def test_source_policy_blocks_public_web_skill_in_wrds_only_mode() -> None:
    web = SkillStub("web-research")
    value = SkillStub("value-investing-research")
    active, blocked = partition_skills_by_source_policy([web, value], source_mode="WRDS_FIRST")

    assert active == [value]
    assert blocked == [web]


def test_source_policy_blocks_public_web_capability_metadata_in_wrds_only_mode() -> None:
    public_web = {"name": "quality-lens", "capability_types": ["public_web_research"]}
    value = {"name": "value-investing-research", "capability_types": ["investment.research"]}

    active, blocked = partition_skills_by_source_policy([public_web, value], source_mode="WRDS_FIRST")

    assert active == [value]
    assert blocked == [public_web]


def test_source_policy_leaves_skills_active_without_wrds_mode() -> None:
    web = {"name": "web-research"}
    active, blocked = partition_skills_by_source_policy([web], source_mode=None)

    assert active == [web]
    assert blocked == []


def test_effective_source_mode_does_not_use_task_type_without_declared_policy() -> None:
    assert effective_source_mode_for_orchestration(
        {"task": "Analyze AAPL", "metadata": {}},
        orchestration={"task_type": "investment"},
    ) is None
    assert effective_source_mode_decision_for_orchestration(
        {"task": "Analyze AAPL", "metadata": {}},
        orchestration={"task_type": "investment"},
    ) == {"source_mode": None, "source": "default"}


def test_effective_source_mode_uses_capability_tool_policy_before_task_fallback() -> None:
    state = {
        "task": "Analyze AAPL",
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "tool_policy": {"source_mode": "WRDS_ONLY"},
                }
            }
        },
    }

    decision = effective_source_mode_decision_for_orchestration(state, orchestration={"task_type": "general"})

    assert decision == {"source_mode": "WRDS_ONLY", "source": "capability_tool_policy"}
    assert effective_source_mode_for_orchestration(state, orchestration={"task_type": "general"}) == "WRDS_ONLY"


def test_effective_source_mode_uses_data_gate_before_plan_filtering() -> None:
    state = {
        "task": "Analyze AAPL",
        "metadata": {},
        "data_gate": {"source_mode": "WRDS_ONLY"},
    }
    plan = [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [
                {"name": "web_search", "args": {"query": "AAPL"}},
                {"name": "wrds_company_financials", "args": {"query": "AAPL"}},
            ],
        }
    ]

    decision = effective_source_mode_decision_for_orchestration(state, orchestration={"task_type": "general"})
    updated = filter_plan_by_source_and_tool_policy(plan, source_mode=decision["source_mode"])

    assert decision == {"source_mode": "WRDS_ONLY", "source": "data_gate"}
    assert updated == [
        {
            "id": "mixed",
            "title": "Mixed",
            "tool_calls": [{"name": "wrds_company_financials", "args": {"query": "AAPL"}}],
        }
    ]


def test_web_tools_disabled_for_state_uses_declared_source_policy() -> None:
    assert web_tools_disabled_for_state({"metadata": {"source_mode": "WRDS-FIRST"}}) is True
    assert web_tools_disabled_for_state(
        {"metadata": {"os_plan": {"swarm_plan": {"tool_policy": {"source_mode": "WRDS_ONLY"}}}}}
    ) is True
    assert web_tools_disabled_for_state({"metadata": {"investment_web_search_disabled": True}}) is False
    assert web_tools_disabled_for_state({"data_gate": {"source_mode": "WRDS_FIRST"}, "metadata": {}}) is True
    assert web_tools_disabled_for_state({"task": "Analyze AAPL valuation", "metadata": {}}) is False
    assert web_tools_disabled_for_state({"task": "FastAPI release notes", "metadata": {}}) is False


def test_wrds_source_requirement_uses_source_policy_helper() -> None:
    assert wrds_source_required_for_state({"metadata": {"source_mode": "WRDS-FIRST"}}) is True
    assert wrds_source_required_for_state({"data_gate": {"source_mode": "WRDS_FIRST"}, "metadata": {}}) is True
    assert wrds_source_required_for_state({"metadata": {"os_plan": {"wrds_only_mode": True}}}) is True
    assert wrds_source_required_for_state({"metadata": {"os_plan": {"wrds_only_mode": False}}}) is False


def test_source_policy_no_longer_uses_investment_web_search_flag() -> None:
    assert "investment_web_search_disabled" not in Path("runtime/swarm/tool_plan_policy.py").read_text(encoding="utf-8")
    assert "investment_web_search_disabled" not in Path("runtime/swarm/action_policy.py").read_text(encoding="utf-8")


def test_initial_signals_use_shared_source_policy_aliases() -> None:
    signals = initial_signals_from_state({"run_id": "run-1", "metadata": {"source_mode": "WRDS-FIRST"}})

    assert any(signal.target == "tool:web_search" and signal.blocking for signal in signals)
    assert any("active WRDS-only source policy" in signal.content for signal in signals)
    assert not any("investment analysis" in signal.content.lower() for signal in signals)


def test_initial_signals_use_declared_source_policy_blocked_tool_targets() -> None:
    signals = initial_signals_from_state(
        {
            "run_id": "run-1",
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {
                            "source_mode": "WRDS_ONLY",
                            "source_policy_blocked_tool_targets": ["tool:custom_news_api"],
                            "source_policy_block_message": "{action} blocked by declared {source_mode} source policy.",
                            "source_policy_constraint_message": "Declared {source_mode} source policy is active.",
                        }
                    }
                }
            },
        }
    )

    blocking_targets = {signal.target for signal in signals if signal.blocking}
    content_by_target = {signal.target: signal.content for signal in signals}

    assert "tool:custom_news_api" in blocking_targets
    assert content_by_target["constraint:data_source_policy"] == "Declared WRDS_ONLY source policy is active."
    assert content_by_target["tool:custom_news_api"] == (
        "tool:custom_news_api blocked by declared WRDS_ONLY source policy."
    )
    assert "tool:web_search" not in blocking_targets


def test_policing_uses_shared_source_policy_aliases() -> None:
    violations = tool_policy_violations(
        {
            "metadata": {"source_mode": "WRDS_FIRST"},
            "execution_log": [{"tool_calls": [{"name": "web_search"}]}],
        }
    )

    assert violations == [
        {
            "agent": "tool_registry",
            "target": "tool:web_search",
            "type": "tool_policy_violation",
            "reason": "tool attempted while blocked by active source policy",
            "penalty": "route_block",
        }
    ]


def test_policing_uses_declared_source_policy_blocked_tool_targets() -> None:
    violations = tool_policy_violations(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {
                            "source_mode": "WRDS_ONLY",
                            "source_policy_blocked_tool_targets": ["tool:custom_news_api"],
                        }
                    }
                }
            },
            "execution_log": [{"tool_calls": [{"name": "custom_news_api"}, {"name": "web_search"}]}],
        }
    )

    assert [item["target"] for item in violations] == ["tool:custom_news_api"]
    assert violations[0]["reason"] == "tool attempted while blocked by active source policy"


def test_policing_uses_capability_tool_policy_for_non_web_tools() -> None:
    violations = tool_policy_violations(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {
                            "allowed_tool_targets": ["tool:read_file"],
                            "blocked_tool_targets": ["tool:dangerous_export"],
                        }
                    }
                }
            },
            "execution_log": [
                {
                    "tool_calls": [
                        {"name": "dangerous_export"},
                        {"name": "write_file"},
                        {"name": "read_file"},
                    ]
                }
            ],
        }
    )

    assert [item["target"] for item in violations] == ["tool:dangerous_export", "tool:write_file"]
    assert violations[0]["tool_policy_decision"]["reason"] == "capability_tool_policy_block"
    assert violations[1]["tool_policy_decision"]["reason"] == "not_declared_in_capability_tool_policy"
