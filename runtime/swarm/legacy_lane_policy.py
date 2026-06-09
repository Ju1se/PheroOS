from __future__ import annotations

from typing import Any


LEGACY_LANE_POLICY_SOURCE = "legacy_lane_policy"
LEGACY_LANES = ["inspection", "execution", "verification", "synthesis", "control"]
LEGACY_AGENT_PREFERRED_LANES = {
    "writer": "synthesis",
    "final_judge": "control",
}
LEGACY_TERM_LANE_PREFERENCES = [
    {"lane": "control", "terms": ["control", "chair"]},
    {"lane": "verification", "terms": ["verification", "verifier", "evidence", "audit", "auditor", "risk"]},
]
LEGACY_LANE_FALLBACK_ORDER = ["synthesis", "inspection", "control", "verification"]
LEGACY_DEFAULT_LANE = "inspection"
LEGACY_LANE_ASSIGNMENT_SIGNAL_TEMPLATE = "Assigned {agent} to {lane} lane."


def legacy_lane_policy_source() -> str:
    return LEGACY_LANE_POLICY_SOURCE


def legacy_lane_policy() -> dict[str, Any]:
    return {
        "lanes": list(LEGACY_LANES),
        "preferred_lanes": dict(LEGACY_AGENT_PREFERRED_LANES),
        "term_lane_preferences": [
            {"lane": item["lane"], "terms": list(item["terms"])}
            for item in LEGACY_TERM_LANE_PREFERENCES
        ],
        "fallback_order": list(LEGACY_LANE_FALLBACK_ORDER),
        "default_lane": LEGACY_DEFAULT_LANE,
        "assignment_signal_template": LEGACY_LANE_ASSIGNMENT_SIGNAL_TEMPLATE,
    }


def legacy_lane_assignment_signal_template() -> str:
    return LEGACY_LANE_ASSIGNMENT_SIGNAL_TEMPLATE


def render_lane_assignment_signal_template(template: str, assignment: dict[str, Any]) -> str:
    replacements = {
        "{agent}": str(assignment.get("agent") or ""),
        "{lane}": str(assignment.get("lane") or ""),
        "{status}": str(assignment.get("status") or ""),
        "{trust_level}": str(assignment.get("trust_level") or ""),
    }
    text = str(template or "")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.strip()
