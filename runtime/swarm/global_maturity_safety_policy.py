from __future__ import annotations

from typing import Any


GLOBAL_MATURITY_SAFETY_POLICY_SOURCE = "global_maturity_safety_policy"
GLOBAL_TRUST_MATURITY_OVERRIDES = {
    "third_party_untrusted": "observer",
    "external_content": "observer",
    "user_installed": "worker",
}
GLOBAL_BLOCKER_TRUST_LEVELS = {"core_system", "trusted_first_party"}


def global_maturity_override_for_trust(badge: dict[str, Any]) -> str | None:
    trust_level = str(badge.get("trust_level") or "")
    return GLOBAL_TRUST_MATURITY_OVERRIDES.get(trust_level)


def global_can_reach_blocker(badge: dict[str, Any]) -> bool:
    trust_level = str(badge.get("trust_level") or "")
    return trust_level in GLOBAL_BLOCKER_TRUST_LEVELS and bool(badge.get("can_emit_blocking"))
