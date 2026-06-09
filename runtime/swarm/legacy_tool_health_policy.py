from __future__ import annotations


LEGACY_TOOL_HEALTH_RECOMMENDATION_SOURCE = "legacy_tool_health_policy"
LEGACY_TOOL_HEALTH_SIGNAL_FALLBACK_CONTENT = "Tool route health degraded."
LEGACY_TOOL_HEALTH_RECOMMENDATIONS = {
    "failing": "block or reroute failing tool/model path before publication",
    "degraded": "lower confidence and prefer deterministic fallback routes",
    "healthy": "maintain current tool route",
    "no_tool_activity": "maintain current tool route",
}
LEGACY_TOOL_HEALTH_FAILURE_HINTS = (
    "timeout",
    "401",
    "403",
    "429",
    "500",
    "502",
    "503",
    "529",
    "rate limit",
    "schema",
    "empty",
)


def legacy_tool_health_recommendation_source() -> str:
    return LEGACY_TOOL_HEALTH_RECOMMENDATION_SOURCE


def legacy_tool_health_recommendation(status: str) -> str:
    return LEGACY_TOOL_HEALTH_RECOMMENDATIONS.get(status, LEGACY_TOOL_HEALTH_RECOMMENDATIONS["healthy"])


def legacy_tool_health_signal_fallback_content() -> str:
    return LEGACY_TOOL_HEALTH_SIGNAL_FALLBACK_CONTENT


def legacy_tool_health_failure_hints() -> tuple[str, ...]:
    return tuple(LEGACY_TOOL_HEALTH_FAILURE_HINTS)
