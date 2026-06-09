from __future__ import annotations

from typing import Any


LEGACY_HOMEOSTASIS_POLICY_SOURCE = "legacy_homeostasis_policy"
LEGACY_HOMEOSTASIS_RECOMMENDATIONS = {
    "risk_pressure": "increase verifier and Red Team strictness",
    "verification_backlog": "recruit evidence receivers before producing more narrative",
    "tool_failure_rate": "deprioritize failing tool route",
    "token_heat": "compress agent outputs before final synthesis",
    "crowding": "split work into lanes or suppress low-demand agents",
    "default": "maintain current swarm balance",
}
LEGACY_HOMEOSTASIS_SIGNAL_TEMPLATE = "Swarm homeostasis is {status}; apply stability recommendations."
LEGACY_HOMEOSTASIS_RECOMMENDATION_RULES = (
    ("risk_pressure", 0.6),
    ("verification_backlog", 0.6),
    ("tool_failure_rate", 0.4),
    ("token_heat", 0.7),
    ("crowding", 0.7),
)


def legacy_homeostasis_policy_source() -> str:
    return LEGACY_HOMEOSTASIS_POLICY_SOURCE


def legacy_homeostasis_recommendation(key: str) -> str:
    return LEGACY_HOMEOSTASIS_RECOMMENDATIONS.get(key, LEGACY_HOMEOSTASIS_RECOMMENDATIONS["default"])


def legacy_homeostasis_signal_template() -> str:
    return LEGACY_HOMEOSTASIS_SIGNAL_TEMPLATE


def legacy_homeostasis_recommendation_rules() -> tuple[tuple[str, float], ...]:
    return tuple((str(key), float(threshold)) for key, threshold in LEGACY_HOMEOSTASIS_RECOMMENDATION_RULES)


def render_homeostasis_signal_template(template: str, report: dict[str, Any]) -> str:
    recommendations = report.get("recommendations") if isinstance(report.get("recommendations"), list) else []
    replacements = {
        "{status}": str(report.get("status") or "stable"),
        "{recommendation_count}": str(len(recommendations)),
        "{recommendations}": "; ".join(str(item) for item in recommendations),
    }
    text = str(template or "")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.strip()
