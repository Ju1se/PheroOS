from __future__ import annotations

from typing import Any


LEGACY_MATURITY_POLICY_SOURCE = "legacy_maturity_policy"
LEGACY_MATURITY_ORDER = ["observer", "worker", "specialist", "verifier", "blocker"]
LEGACY_MATURITY_ACTIONS = {
    "observer": ["read_trace", "emit_unverified_signal"],
    "worker": ["emit_unverified_signal", "perform_low_risk_task"],
    "specialist": ["emit_unverified_signal", "participate_quorum"],
    "verifier": ["participate_quorum", "verify_limited_evidence"],
    "blocker": ["participate_quorum", "propose_blocking_signal"],
}
LEGACY_MATURITY_DEMOTION_RULES = [
    {"metric": "constraint_violation_rate", "operator": ">", "value": 0.05, "maturity": "worker"},
    {"metric": "rejected_signal_rate", "operator": ">", "value": 0.15, "maturity": "worker"},
]
LEGACY_MATURITY_PROMOTION_RULES = [
    {
        "maturity": "blocker",
        "min_total_runs": 20,
        "min_reliability": 0.85,
        "min_verified_signal_count": 10,
        "min_accepted_quorum_participation": 5,
        "requires_can_emit_blocking": True,
        "allowed_trust_levels": ["core_system", "trusted_first_party"],
    },
    {
        "maturity": "verifier",
        "min_total_runs": 10,
        "min_reliability": 0.78,
        "min_verified_signal_count": 5,
    },
    {
        "maturity": "specialist",
        "min_total_runs": 3,
        "min_reliability": 0.68,
        "min_accepted_quorum_participation": 1,
    },
]
LEGACY_MATURITY_TRUST_DEFAULTS = {
    "core_system": "worker",
    "trusted_first_party": "worker",
}
LEGACY_MATURITY_DEFAULT = "observer"
LEGACY_MATURITY_SIGNAL_TEMPLATE = "Agent maturity is {maturity}."


def legacy_maturity_policy_source() -> str:
    return LEGACY_MATURITY_POLICY_SOURCE


def legacy_maturity_policy() -> dict[str, Any]:
    return {
        "maturity_order": list(LEGACY_MATURITY_ORDER),
        "actions": {key: list(value) for key, value in LEGACY_MATURITY_ACTIONS.items()},
        "demotion_rules": [dict(rule) for rule in LEGACY_MATURITY_DEMOTION_RULES],
        "promotion_rules": [dict(rule) for rule in LEGACY_MATURITY_PROMOTION_RULES],
        "trust_defaults": dict(LEGACY_MATURITY_TRUST_DEFAULTS),
        "default_maturity": LEGACY_MATURITY_DEFAULT,
        "signal_template": LEGACY_MATURITY_SIGNAL_TEMPLATE,
    }


def legacy_maturity_signal_template() -> str:
    return LEGACY_MATURITY_SIGNAL_TEMPLATE


def render_maturity_signal_template(template: str, agent: dict[str, Any]) -> str:
    replacements = {
        "{agent}": str(agent.get("agent") or ""),
        "{maturity}": str(agent.get("maturity") or ""),
        "{trust_level}": str(agent.get("trust_level") or ""),
    }
    text = str(template or "")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.strip()
