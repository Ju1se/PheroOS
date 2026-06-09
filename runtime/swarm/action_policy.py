from __future__ import annotations

from typing import Any

from runtime.swarm.stop_policy import canonical_action
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.legacy_tool_policy import (
    legacy_source_policy_block_message,
    legacy_source_policy_constraint_message,
    legacy_source_policy_initial_block_message,
    legacy_source_policy_blocked_tool_target_values,
    legacy_web_research_tool_actions,
    render_source_policy_message_template,
)
from runtime.swarm.source_policy_modes import canonical_wrds_only_source_mode, source_mode_is_wrds_only


def source_policy_blocking_signal(state: dict[str, Any], action: Any) -> dict[str, Any] | None:
    normalized_action = canonical_action(action)
    blocked_targets = source_policy_blocked_tool_targets(state)
    if normalized_action not in blocked_targets:
        return None
    wrds_only_source_mode = canonical_wrds_only_source_mode()
    return {
        "id": "source_policy:web_research_disabled",
        "type": "stop_signal",
        "target": "constraint:data_source_policy",
        "blocking": True,
        "verification_state": "blocking",
        "content": source_policy_block_message(state, normalized_action),
        "source_module": "source_policy",
        "metadata": {
            "blocked_action": normalized_action,
            "source_policy": wrds_only_source_mode,
            "source_policy_blocked_tool_targets": sorted(blocked_targets),
        },
    }


def source_policy_blocks_tool(state: dict[str, Any], action: Any) -> bool:
    normalized_action = canonical_action(action)
    return bool(normalized_action and normalized_action in source_policy_blocked_tool_targets(state))


def source_policy_constraint_message(state: dict[str, Any]) -> str:
    policy = _tool_policy_from_state(state)
    template = str(policy.get("source_policy_constraint_message") or "").strip()
    if template:
        return render_source_policy_message_template(template, source_mode=canonical_wrds_only_source_mode())
    return legacy_source_policy_constraint_message()


def source_policy_block_message(state: dict[str, Any], action: Any, *, initial_signal: bool = False) -> str:
    normalized_action = canonical_action(action)
    policy = _tool_policy_from_state(state)
    template = str(policy.get("source_policy_block_message") or "").strip()
    wrds_only_source_mode = canonical_wrds_only_source_mode()
    if template:
        return render_source_policy_message_template(
            template,
            action=normalized_action,
            source_mode=wrds_only_source_mode,
        )
    if initial_signal:
        return legacy_source_policy_initial_block_message(action=normalized_action, source_mode=wrds_only_source_mode)
    return legacy_source_policy_block_message(action=normalized_action, source_mode=wrds_only_source_mode)


def source_policy_blocked_tool_targets(state: dict[str, Any]) -> set[str]:
    if not web_research_disabled_by_source_policy(state):
        return set()
    policy = _tool_policy_from_state(state)
    return source_policy_blocked_tool_targets_from_policy(policy)


def source_policy_blocked_tool_targets_from_policy(policy: dict[str, Any]) -> set[str]:
    declared = declared_source_policy_blocked_tool_targets_from_policy(policy)
    if declared:
        return declared
    return legacy_web_research_tool_actions()


def declared_source_policy_blocked_tool_targets_from_policy(policy: dict[str, Any]) -> set[str]:
    declared = {
        canonical_target(item)
        for item in _string_list(policy.get("source_policy_blocked_tool_targets"))
    }
    if declared:
        return declared
    legacy_declared = {
        canonical_target(item)
        for item in legacy_source_policy_blocked_tool_target_values(policy)
    }
    if legacy_declared:
        return legacy_declared
    return set()


def web_research_disabled_by_source_policy(state: dict[str, Any]) -> bool:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    source_mode = metadata.get("source_mode") or data_gate.get("source_mode")
    if source_mode_is_wrds_only(source_mode):
        return True
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    tool_policy = swarm_plan.get("tool_policy") if isinstance(swarm_plan.get("tool_policy"), dict) else {}
    policy_source_mode = tool_policy.get("source_mode") or tool_policy.get("source_policy")
    return source_mode_is_wrds_only(policy_source_mode)


def related_actions_for_action(action: Any) -> set[str]:
    normalized_action = canonical_action(action)
    legacy_web_actions = legacy_web_research_tool_actions()
    if normalized_action in legacy_web_actions:
        return legacy_web_actions
    return {normalized_action} if normalized_action else set()


def _tool_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("tool_policy") if isinstance(swarm_plan.get("tool_policy"), dict) else {}
    return policy


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
