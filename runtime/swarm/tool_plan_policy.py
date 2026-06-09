from __future__ import annotations

from typing import Any

from runtime.research_selection import skill_requests_public_web_research
from runtime.swarm.action_policy import (
    source_policy_blocked_tool_targets_from_policy,
)
from runtime.swarm.legacy_tool_policy import (
    legacy_os_plan_wrds_only_mode,
)
from runtime.swarm.source_policy_modes import canonical_wrds_only_source_mode, source_mode_is_wrds_only
from runtime.swarm.tool_policy_resolver import (
    allowed_tool_targets,
    blocked_tool_targets,
    canonical_tool_action,
    tool_aliases,
    tool_policy_from_state,
)

def effective_source_mode_for_orchestration(state: dict[str, Any], *, orchestration: dict[str, Any]) -> str | None:
    return effective_source_mode_decision_for_orchestration(state, orchestration=orchestration).get("source_mode")


def effective_source_mode_decision_for_orchestration(
    state: dict[str, Any],
    *,
    orchestration: dict[str, Any],
) -> dict[str, Any]:
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    if source_mode_is_wrds_only(metadata.get("source_mode")):
        return {"source_mode": canonical_wrds_only_source_mode(), "source": "metadata"}
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    if source_mode_is_wrds_only(data_gate.get("source_mode")):
        return {"source_mode": canonical_wrds_only_source_mode(), "source": "data_gate"}
    policy_source_mode = declared_source_mode_from_tool_policy(tool_policy_from_state(state))
    if source_mode_is_wrds_only(policy_source_mode):
        return {"source_mode": canonical_wrds_only_source_mode(), "source": "capability_tool_policy"}
    return {"source_mode": metadata.get("source_mode"), "source": "metadata" if metadata.get("source_mode") else "default"}


def declared_source_mode_from_tool_policy(policy: dict[str, Any]) -> str | None:
    source_mode = str(policy.get("source_mode") or policy.get("source_policy") or "").strip()
    if not source_mode:
        return None
    return canonical_wrds_only_source_mode() if source_mode_is_wrds_only(source_mode) else source_mode


def web_tools_disabled_for_state(state: dict[str, Any]) -> bool:
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    if source_mode_is_wrds_only(metadata.get("source_mode")):
        return True
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    if source_mode_is_wrds_only(data_gate.get("source_mode")):
        return True
    if source_mode_is_wrds_only(declared_source_mode_from_tool_policy(tool_policy_from_state(state))):
        return True
    return False


def wrds_source_required_for_state(state: dict[str, Any]) -> bool:
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return web_tools_disabled_for_state(state) or legacy_os_plan_wrds_only_mode(os_plan)


def partition_skills_by_source_policy(skills: list[Any], *, source_mode: Any) -> tuple[list[Any], list[Any]]:
    if not source_mode_is_wrds_only(source_mode):
        return skills, []
    active: list[Any] = []
    blocked: list[Any] = []
    for skill in skills:
        if skill_requests_public_web_research(skill):
            blocked.append(skill)
        else:
            active.append(skill)
    return active, blocked


def filter_plan_by_source_and_tool_policy(
    plan: list[dict[str, Any]],
    *,
    source_mode: Any,
    tool_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    policy = tool_policy if isinstance(tool_policy, dict) else {}
    wrds_only = source_mode_is_wrds_only(source_mode)
    blocked_targets = blocked_tool_targets(policy)
    allowed_targets = allowed_tool_targets(policy)
    aliases = tool_aliases(policy)
    source_policy_blocked_targets = source_policy_blocked_tool_targets_from_policy(policy) if wrds_only else set()
    if not wrds_only and not blocked_targets and not allowed_targets:
        return plan

    filtered_plan: list[dict[str, Any]] = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        tool_calls = step.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue
        filtered_calls = [
            call
            for call in tool_calls
            if isinstance(call, dict)
            and tool_call_allowed_by_source_and_capability_policy(
                str(call.get("name") or ""),
                source_mode_wrds_only=wrds_only,
                source_policy_blocked_targets=source_policy_blocked_targets,
                blocked_targets=blocked_targets,
                allowed_targets=allowed_targets,
                aliases=aliases,
            )
        ]
        if wrds_only and not any(str(call.get("name") or "").startswith("wrds_") for call in filtered_calls):
            continue
        if filtered_calls:
            filtered_plan.append({**step, "tool_calls": filtered_calls})
    return filtered_plan


def tool_call_allowed_by_source_and_capability_policy(
    tool_name: str,
    *,
    source_mode_wrds_only: bool,
    source_policy_blocked_targets: set[str],
    blocked_targets: set[str],
    allowed_targets: set[str],
    aliases: dict[str, str],
) -> bool:
    canonical_tool = canonical_tool_action(tool_name, aliases=aliases)
    if source_mode_wrds_only and canonical_tool in source_policy_blocked_targets:
        return False
    if canonical_tool in blocked_targets:
        return False
    if allowed_targets and canonical_tool not in allowed_targets:
        return False
    return True
