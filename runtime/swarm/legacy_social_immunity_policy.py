from __future__ import annotations

from typing import Any


LEGACY_SOCIAL_IMMUNITY_POLICY_SOURCE = "legacy_social_immunity_policy"
LEGACY_SOCIAL_IMMUNITY_RECOMMENDATIONS = {
    "quarantine_required": "quarantine contaminated artifacts and require verifier-only handling",
    "heightened": "raise verifier strictness and keep writer confidence conservative",
    "clear": "normal verification intensity",
}
LEGACY_SOCIAL_IMMUNITY_AROUSAL_SIGNAL_TEMPLATE = (
    "High-risk or contaminated context detected; increase verification intensity."
)


def legacy_social_immunity_policy_source() -> str:
    return LEGACY_SOCIAL_IMMUNITY_POLICY_SOURCE


def legacy_social_immunity_recommendation(status: str) -> str:
    return LEGACY_SOCIAL_IMMUNITY_RECOMMENDATIONS.get(status, LEGACY_SOCIAL_IMMUNITY_RECOMMENDATIONS["clear"])


def legacy_social_immunity_arousal_signal_template() -> str:
    return LEGACY_SOCIAL_IMMUNITY_AROUSAL_SIGNAL_TEMPLATE


def render_social_immunity_arousal_signal_template(template: str, report: dict[str, Any]) -> str:
    replacements = {
        "{status}": str(report.get("status") or "clear"),
        "{arousal_level}": str(report.get("arousal_level") or 0),
        "{quarantine_count}": str(report.get("quarantine_count") or 0),
        "{recommendation}": str(report.get("recommendation") or ""),
    }
    text = str(template or "")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.strip()
