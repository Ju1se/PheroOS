from __future__ import annotations

from typing import Any


GLOBAL_LANE_SAFETY_POLICY_SOURCE = "global_lane_safety_policy"
GLOBAL_RESTRICTED_LANES = {
    "writer": {"execution", "control"},
    "third_party_untrusted": {"execution", "control", "synthesis"},
}
GLOBAL_TRUST_DEFAULT_LANES = {
    "third_party_untrusted": "inspection",
}


def global_default_lane_for_trust(badge: dict[str, Any]) -> str | None:
    trust_level = str(badge.get("trust_level") or "")
    return GLOBAL_TRUST_DEFAULT_LANES.get(trust_level)


def global_lane_violation(agent: str, lane: str, badge: dict[str, Any]) -> str | None:
    if agent == "writer" and lane in GLOBAL_RESTRICTED_LANES["writer"]:
        return "writer cannot enter execution or control lane"
    trust_level = str(badge.get("trust_level") or "")
    if lane in GLOBAL_RESTRICTED_LANES.get(trust_level, set()):
        return f"{trust_level} agents default to inspection lane"
    return None
