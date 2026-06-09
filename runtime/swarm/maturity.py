from __future__ import annotations

from typing import Any

from runtime.swarm.agent_profile import AgentProfileStore
from runtime.swarm.global_maturity_safety_policy import (
    GLOBAL_MATURITY_SAFETY_POLICY_SOURCE,
    global_can_reach_blocker,
    global_maturity_override_for_trust,
)
from runtime.swarm.legacy_maturity_policy import (
    legacy_maturity_policy,
    legacy_maturity_policy_source,
    legacy_maturity_signal_template,
    render_maturity_signal_template,
)
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


DECLARED_MATURITY_POLICY_SOURCE = "capability_swarm_loop_policy"


def build_maturity_report(
    member_specs: list[dict[str, Any]],
    trust_badges: list[dict[str, Any]],
    *,
    store: AgentProfileStore | None = None,
    tenant_id: str = "default",
    maturity_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = store or AgentProfileStore()
    policy, policy_source = effective_maturity_policy(maturity_policy)
    badge_by_agent = {str(item.get("agent")): item for item in trust_badges if isinstance(item, dict)}
    agents = []
    for spec in member_specs:
        key = str(spec.get("key") or spec.get("agent") or "agent")
        badge = badge_by_agent.get(key, {})
        profile = store.get(key, tenant_id=tenant_id)
        maturity, maturity_source = maturity_for(profile.to_dict(), badge, policy=policy, policy_source=policy_source)
        agents.append(
            {
                "agent": key,
                "maturity": maturity,
                "maturity_source": maturity_source,
                "trust_level": badge.get("trust_level") or "trusted_first_party",
                "reliability": profile.reliability,
                "total_runs": profile.total_runs,
                "successful_runs": profile.successful_runs,
                "allowed_actions": actions_for(maturity, policy),
                "can_reach_blocker": global_can_reach_blocker(badge),
            }
        )
    return {
        "status": "evaluated",
        "agents": agents,
        "maturity_policy_source": policy_source,
        "maturity_order": maturity_order(policy),
    }


def maturity_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals = []
    template, template_source = maturity_signal_template_from_state(state)
    order = report.get("maturity_order") if isinstance(report.get("maturity_order"), list) else None
    for item in report.get("agents") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.MATURITY,
                target=f"agent:{item.get('agent')}",
                content=render_maturity_signal_template(template, item),
                strength=maturity_strength(str(item.get("maturity")), order),
                confidence=0.7,
                verification_state=VerificationState.VERIFIED,
                source_module="maturity_lifecycle",
                metadata={
                    "allowed_actions": item.get("allowed_actions", []),
                    "trust_level": item.get("trust_level"),
                    "maturity_source": item.get("maturity_source"),
                    "signal_template_source": template_source,
                },
            )
        )
    return signals


def maturity_for(
    profile: dict[str, Any],
    badge: dict[str, Any],
    *,
    policy: dict[str, Any],
    policy_source: str,
) -> tuple[str, str]:
    override = global_maturity_override_for_trust(badge)
    if override:
        return override, GLOBAL_MATURITY_SAFETY_POLICY_SOURCE
    for rule in policy.get("demotion_rules") if isinstance(policy.get("demotion_rules"), list) else []:
        maturity = demotion_maturity(profile, rule)
        if maturity:
            return maturity, policy_source
    for rule in policy.get("promotion_rules") if isinstance(policy.get("promotion_rules"), list) else []:
        if promotion_rule_matches(profile, badge, rule):
            return str(rule.get("maturity") or default_maturity(badge, policy)), policy_source
    return default_maturity(badge, policy), policy_source


def actions_for(maturity: str, policy: dict[str, Any]) -> list[str]:
    actions = policy.get("actions") if isinstance(policy.get("actions"), dict) else {}
    values = actions.get(maturity)
    if isinstance(values, list):
        return [str(item) for item in values if str(item).strip()]
    fallback = actions.get(default_maturity({}, policy))
    return [str(item) for item in fallback if str(item).strip()] if isinstance(fallback, list) else []


def maturity_strength(maturity: str, order: list[Any] | None = None) -> float:
    normalized_order = [str(item) for item in order or legacy_maturity_policy()["maturity_order"]]
    return (normalized_order.index(maturity) + 1) / len(normalized_order) if maturity in normalized_order else 0.2


def effective_maturity_policy(policy: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    if isinstance(policy, dict) and policy:
        return policy, DECLARED_MATURITY_POLICY_SOURCE
    return legacy_maturity_policy(), legacy_maturity_policy_source()


def maturity_order(policy: dict[str, Any]) -> list[str]:
    order = [str(item).strip() for item in policy.get("maturity_order") or [] if str(item).strip()]
    return order or legacy_maturity_policy()["maturity_order"]


def demotion_maturity(profile: dict[str, Any], rule: Any) -> str:
    if not isinstance(rule, dict):
        return ""
    metric = str(rule.get("metric") or "")
    operator = str(rule.get("operator") or ">")
    threshold = as_float(rule.get("value"))
    value = as_float(profile.get(metric))
    if operator == ">" and value > threshold:
        return str(rule.get("maturity") or "")
    if operator == ">=" and value >= threshold:
        return str(rule.get("maturity") or "")
    return ""


def promotion_rule_matches(profile: dict[str, Any], badge: dict[str, Any], rule: Any) -> bool:
    if not isinstance(rule, dict):
        return False
    trust_levels = [str(item) for item in rule.get("allowed_trust_levels") or [] if str(item).strip()]
    trust_level = str(badge.get("trust_level") or "")
    if trust_levels and trust_level not in trust_levels:
        return False
    if rule.get("requires_can_emit_blocking") and not badge.get("can_emit_blocking"):
        return False
    metric_checks = {
        "total_runs": int(profile.get("total_runs") or 0),
        "reliability": as_float(profile.get("reliability")),
        "verified_signal_count": int(profile.get("verified_signal_count") or 0),
        "accepted_quorum_participation": int(profile.get("accepted_quorum_participation") or 0),
    }
    for metric, value in metric_checks.items():
        threshold_key = f"min_{metric}"
        if threshold_key in rule and value < as_float(rule.get(threshold_key)):
            return False
    return True


def default_maturity(badge: dict[str, Any], policy: dict[str, Any]) -> str:
    trust_defaults = policy.get("trust_defaults") if isinstance(policy.get("trust_defaults"), dict) else {}
    trust_level = str(badge.get("trust_level") or "")
    if trust_level and str(trust_defaults.get(trust_level) or "").strip():
        return str(trust_defaults[trust_level]).strip()
    return str(policy.get("default_maturity") or "").strip() or str(legacy_maturity_policy()["default_maturity"])


def maturity_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    loop_policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    policy = loop_policy.get("maturity_policy") if isinstance(loop_policy.get("maturity_policy"), dict) else {}
    return policy


def maturity_signal_template_from_state(state: dict[str, Any]) -> tuple[str, str]:
    policy = maturity_policy_from_state(state)
    declared = str(policy.get("signal_template") or "").strip()
    if declared:
        return declared, DECLARED_MATURITY_POLICY_SOURCE
    return legacy_maturity_signal_template(), legacy_maturity_policy_source()


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
