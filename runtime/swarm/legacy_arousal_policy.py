from __future__ import annotations

from typing import Any


LEGACY_AROUSAL_SIGNAL_TEMPLATE_SOURCE = "legacy_arousal_policy"
LEGACY_AROUSAL_SIGNAL_TEMPLATE = "Arousal level is {arousal_level}; raise verification intensity."


def legacy_arousal_signal_template_source() -> str:
    return LEGACY_AROUSAL_SIGNAL_TEMPLATE_SOURCE


def legacy_arousal_signal_template() -> str:
    return LEGACY_AROUSAL_SIGNAL_TEMPLATE


def render_arousal_signal_template(template: str, report: dict[str, Any]) -> str:
    recommendations = report.get("recommendations") if isinstance(report.get("recommendations"), dict) else {}
    triggers = report.get("triggers") if isinstance(report.get("triggers"), list) else []
    replacements = {
        "{arousal_level}": str(report.get("arousal_level") or 0),
        "{status}": str(report.get("status") or "normal"),
        "{trigger_count}": str(len(triggers)),
        "{triggers}": ", ".join(str(trigger) for trigger in triggers) or "none",
        "{verifier_strictness}": str(recommendations.get("verifier_strictness") or "normal"),
    }
    text = str(template or "")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.strip()
