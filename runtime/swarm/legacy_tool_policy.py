from __future__ import annotations


LEGACY_WEB_RESEARCH_TOOL_ACTIONS = {
    "tool:web_search",
    "tool:provider_web_search",
    "tool:fetch_url",
    "tool:approved_source_fetch",
}
LEGACY_DEFAULT_TOOL_POLICY_VIOLATION_TARGET = "tool:web_search"

LEGACY_SOURCE_POLICY_TOOL_TARGET_KEYS = (
    "source_policy_blocking_tool_targets",
    "source_mode_blocked_tool_targets",
    "web_research_tool_targets",
)
LEGACY_OS_PLAN_WRDS_ONLY_MODE_KEY = "wrds_only_mode"
LEGACY_SOURCE_POLICY_BLOCK_MESSAGE_TEMPLATE = (
    "{action} is blocked because the current {source_mode} source policy disallows that tool target."
)
LEGACY_SOURCE_POLICY_INITIAL_BLOCK_MESSAGE_TEMPLATE = "{action} is blocked by the active WRDS-only source policy."
LEGACY_SOURCE_POLICY_CONSTRAINT_MESSAGE = (
    "The active source policy uses the WRDS/metric-registry path; web research is disabled unless explicitly allowed."
)
LEGACY_SOURCE_POLICY_SKILL_BLOCK_REASON = "WRDS_ONLY source policy disables public web research."
LEGACY_SOURCE_POLICY_TOOL_DISABLED_DETAIL_TEMPLATE = (
    "{action} is disabled because the current source policy is {source_mode}."
)
LEGACY_WRDS_SOURCE_READY_DETAIL = "WRDS data source is active."
LEGACY_WRDS_SOURCE_BLOCKED_DETAIL = "WRDS-only mode requires an active WRDS data source."


def legacy_web_research_tool_actions() -> set[str]:
    return set(LEGACY_WEB_RESEARCH_TOOL_ACTIONS)


def legacy_default_tool_policy_violation_target() -> str:
    return LEGACY_DEFAULT_TOOL_POLICY_VIOLATION_TARGET


def legacy_source_policy_blocked_tool_target_values(policy: dict[str, object]) -> list[str]:
    for key in LEGACY_SOURCE_POLICY_TOOL_TARGET_KEYS:
        values = string_list(policy.get(key))
        if values:
            return values
    return []


def legacy_os_plan_wrds_only_mode(os_plan: dict[str, object]) -> bool:
    return bool(os_plan.get(LEGACY_OS_PLAN_WRDS_ONLY_MODE_KEY))


def legacy_source_policy_block_message(*, action: str, source_mode: str = "WRDS_ONLY") -> str:
    return render_source_policy_message_template(
        LEGACY_SOURCE_POLICY_BLOCK_MESSAGE_TEMPLATE,
        action=action,
        source_mode=source_mode,
    )


def legacy_source_policy_initial_block_message(*, action: str, source_mode: str = "WRDS_ONLY") -> str:
    return render_source_policy_message_template(
        LEGACY_SOURCE_POLICY_INITIAL_BLOCK_MESSAGE_TEMPLATE,
        action=action,
        source_mode=source_mode,
    )


def legacy_source_policy_constraint_message() -> str:
    return LEGACY_SOURCE_POLICY_CONSTRAINT_MESSAGE


def legacy_source_policy_skill_block_reason() -> str:
    return LEGACY_SOURCE_POLICY_SKILL_BLOCK_REASON


def legacy_source_policy_tool_disabled_detail(*, action: str, source_mode: str = "WRDS_ONLY") -> str:
    return render_source_policy_message_template(
        LEGACY_SOURCE_POLICY_TOOL_DISABLED_DETAIL_TEMPLATE,
        action=action,
        source_mode=source_mode,
    )


def legacy_wrds_source_readiness_detail(*, ready: bool) -> str:
    return LEGACY_WRDS_SOURCE_READY_DETAIL if ready else LEGACY_WRDS_SOURCE_BLOCKED_DETAIL


def render_source_policy_message_template(template: str, *, action: str = "", source_mode: str = "WRDS_ONLY") -> str:
    return (
        str(template or "")
        .replace("{action}", action)
        .replace("{source_mode}", source_mode)
        .strip()
    )


def string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
