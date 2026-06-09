from __future__ import annotations

from typing import Any


LEGACY_SWARM_CONTROLLER_POLICY_SOURCE = "legacy_swarm_controller_policy"
LEGACY_SWARM_CONTROLLER_POLICY = {
    "default_action_target": "committee",
    "default_action_reason": "swarm controller action",
    "default_bottleneck_reason": "bottleneck detected",
    "default_lane_violation_reason": "lane violation",
    "runtime_budget_default_recommendation": "maintain current activation",
    "runtime_budget_target": "committee",
    "low_return_reason": "low verified return rate",
    "verification_policy_reason": "derived from arousal and Data Gate pressure",
    "arousal_verification_target": "critic_and_final_judge",
    "arousal_verification_reason": "arousal controller requested stricter checks",
    "quorum_policy_signal_template": "Swarm controller updated quorum policy from arousal and independence requirements.",
    "homeostasis_action_rules": [
        {
            "action": "prioritize_evidence_receivers",
            "target": "committee",
            "terms": ["recruit evidence"],
        },
        {
            "action": "compress_before_synthesis",
            "target": "writer",
            "terms": ["compress"],
        },
        {
            "action": "reduce_crowding",
            "target": "committee",
            "terms": ["suppress", "split work"],
        },
    ],
}


def legacy_swarm_controller_policy_source() -> str:
    return LEGACY_SWARM_CONTROLLER_POLICY_SOURCE


def legacy_swarm_controller_policy() -> dict[str, Any]:
    return {
        **{key: value for key, value in LEGACY_SWARM_CONTROLLER_POLICY.items() if key != "homeostasis_action_rules"},
        "homeostasis_action_rules": [
            {"action": rule["action"], "target": rule["target"], "terms": list(rule["terms"])}
            for rule in LEGACY_SWARM_CONTROLLER_POLICY["homeostasis_action_rules"]
        ],
    }


def legacy_swarm_controller_value(key: str) -> Any:
    return legacy_swarm_controller_policy().get(key)


def controller_homeostasis_action(
    recommendation: str,
    policy: dict[str, Any],
    *,
    policy_source: str,
) -> dict[str, Any] | None:
    text = recommendation.lower()
    rules = policy.get("homeostasis_action_rules") if isinstance(policy.get("homeostasis_action_rules"), list) else []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        terms = [str(term).strip().lower() for term in rule.get("terms") or [] if str(term).strip()]
        action = str(rule.get("action") or "").strip()
        if action and terms and any(term in text for term in terms):
            return {
                "action": action,
                "target": str(rule.get("target") or policy.get("default_action_target") or ""),
                "reason": recommendation,
                "action_policy_source": policy_source,
            }
    return None


def render_swarm_controller_template(template: str, values: dict[str, Any]) -> str:
    replacements = {
        "{threshold_delta}": str(values.get("threshold_delta") or 0.0),
        "{min_independence_score}": str(values.get("min_independence_score") or 0.0),
        "{force_fallback_when_low_independence}": str(values.get("force_fallback_when_low_independence") or False),
    }
    text = str(template or "")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.strip()
