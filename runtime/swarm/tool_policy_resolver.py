from __future__ import annotations

from typing import Any

from runtime.swarm.stop_signal_policy import blocking_signal_for_action
from runtime.swarm.stop_policy import canonical_action
from runtime.swarm.target_registry import canonical_target


def resolve_tool_policy(
    *,
    tool_name: str,
    state: dict[str, Any],
    tool_manifest: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    action = canonical_action(f"tool:{tool_name}")
    policy = tool_policy_from_state(state)
    aliases = tool_aliases(policy)
    canonical_tool = canonical_tool_action(tool_name, aliases=aliases)
    tool_spec = tool_spec_by_name(tool_manifest or [], tool_name)

    stop_signal = blocking_signal_for_action(state, action)
    if stop_signal is not None:
        return decision(
            tool_name=tool_name,
            status="blocked",
            reason="stop_signal",
            canonical_tool=canonical_tool,
            detail={"blocked_by_signal": stop_signal.get("id"), "target": stop_signal.get("target")},
        )

    if canonical_tool in blocked_tool_targets(policy):
        return decision(
            tool_name=tool_name,
            status="blocked",
            reason="capability_tool_policy_block",
            canonical_tool=canonical_tool,
        )

    missing_permissions = [
        permission
        for permission in tool_spec.get("required_permissions") or []
        if tool_spec.get("granted") is False
    ]
    if missing_permissions or tool_spec.get("granted") is False:
        return decision(
            tool_name=tool_name,
            status="denied",
            reason="global_permission_policy",
            canonical_tool=canonical_tool,
            detail={"missing_permissions": missing_permissions},
        )

    if tool_spec.get("connection_granted") is False:
        return decision(
            tool_name=tool_name,
            status="denied",
            reason="missing_connection",
            canonical_tool=canonical_tool,
            detail={"required_connections": list(tool_spec.get("required_connections") or [])},
        )

    allowed_targets = allowed_tool_targets(policy)
    if allowed_targets and canonical_tool not in allowed_targets:
        return decision(
            tool_name=tool_name,
            status="denied",
            reason="not_declared_in_capability_tool_policy",
            canonical_tool=canonical_tool,
        )

    quarantine = quarantine_report(state)
    if quarantine.get("quarantine_count"):
        return decision(
            tool_name=tool_name,
            status="allowed_with_quarantine",
            reason="tool_output_quarantine_required",
            canonical_tool=canonical_tool,
            detail={"quarantine_count": quarantine.get("quarantine_count")},
        )

    return decision(
        tool_name=tool_name,
        status="allowed",
        reason="allowed_by_global_and_capability_policy",
        canonical_tool=canonical_tool,
    )


def decision(
    *,
    tool_name: str,
    status: str,
    reason: str,
    canonical_tool: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "canonical_tool": canonical_tool,
        "status": status,
        "reason": reason,
        **(detail or {}),
    }


def tool_policy_event_type(decision: dict[str, Any]) -> str:
    status = str(decision.get("status") or "").strip()
    if status == "allowed":
        return "tool.allowed"
    if status == "allowed_with_quarantine":
        return "tool.allowed_with_quarantine"
    if status == "blocked":
        return "tool.blocked"
    if status == "denied":
        return "tool.denied"
    return "tool.policy.unknown"


def tool_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("tool_policy") if isinstance(swarm_plan.get("tool_policy"), dict) else {}
    return policy


def allowed_tool_targets(policy: dict[str, Any]) -> set[str]:
    return {canonical_target(item) for item in string_list(policy.get("allowed_tool_targets"))}


def blocked_tool_targets(policy: dict[str, Any]) -> set[str]:
    return {canonical_target(item) for item in string_list(policy.get("blocked_tool_targets"))}


def tool_aliases(policy: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    raw_aliases = policy.get("tool_aliases") if isinstance(policy.get("tool_aliases"), dict) else {}
    for alias, target in raw_aliases.items():
        alias_text = str(alias).strip()
        target_text = str(target).strip()
        if alias_text and target_text:
            aliases[alias_text] = canonical_target(target_text)
            aliases[alias_text.lower()] = canonical_target(target_text)
    return aliases


def canonical_tool_action(tool_name: str, *, aliases: dict[str, str]) -> str:
    action = canonical_action(f"tool:{tool_name}")
    if action in aliases:
        return aliases[action]
    if tool_name in aliases:
        return aliases[tool_name]
    if tool_name.lower() in aliases:
        return aliases[tool_name.lower()]
    return action


def tool_spec_by_name(manifest: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    for spec in manifest:
        if isinstance(spec, dict) and str(spec.get("name") or "") == tool_name:
            return spec
    return {}


def quarantine_report(state: dict[str, Any]) -> dict[str, Any]:
    report = state.get("social_immunity_report") if isinstance(state.get("social_immunity_report"), dict) else {}
    if report:
        return report
    return {}


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
