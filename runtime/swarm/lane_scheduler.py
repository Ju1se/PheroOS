from __future__ import annotations

from typing import Any

from runtime.swarm.global_lane_safety_policy import (
    GLOBAL_LANE_SAFETY_POLICY_SOURCE,
    global_default_lane_for_trust,
    global_lane_violation,
)
from runtime.swarm.legacy_lane_policy import (
    legacy_lane_assignment_signal_template,
    legacy_lane_policy_source,
    legacy_lane_policy,
    render_lane_assignment_signal_template,
)
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState
from runtime.swarm.trust_badge import trust_badge_map


DECLARED_LANE_POLICY_SOURCE = "capability_swarm_loop_policy"


def build_lane_assignment_report(
    member_specs: list[dict[str, Any]],
    trust_badges: list[dict[str, Any]],
    *,
    lane_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    badges = trust_badge_map(trust_badges)
    policy, policy_source = effective_lane_policy(lane_policy)
    assignments: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for spec in member_specs:
        key = str(spec.get("key") or spec.get("agent") or "agent")
        badge = badges.get(key, {})
        lane, lane_source = preferred_lane(spec, badge, policy=policy, policy_source=policy_source)
        default_lane = global_default_lane_for_trust(badge)
        if default_lane:
            lane = default_lane
            lane_source = GLOBAL_LANE_SAFETY_POLICY_SOURCE
        violation = global_lane_violation(key, lane, badge)
        item = {
            "agent": key,
            "lane": lane,
            "allowed_lanes": badge.get("allowed_lanes") or [lane],
            "trust_level": badge.get("trust_level") or "trusted_first_party",
            "status": "blocked" if violation else "assigned",
            "reason": violation or f"assigned to {lane} lane",
            "lane_source": GLOBAL_LANE_SAFETY_POLICY_SOURCE if violation else lane_source,
        }
        assignments.append(item)
        if violation:
            violations.append(item)
    return {
        "status": "violations_detected" if violations else "assigned",
        "lanes": lane_list(policy),
        "lane_policy_source": policy_source,
        "assignments": assignments,
        "violations": violations,
    }


def lane_assignment_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals = []
    template, template_source = lane_assignment_signal_template_from_state(state)
    for item in report.get("assignments") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.LANE_ASSIGNMENT,
                target=f"agent:{item.get('agent')}",
                content=render_lane_assignment_signal_template(template, item),
                strength=1.0,
                confidence=0.9,
                priority="hard",
                verification_state=VerificationState.VERIFIED,
                source_module="lane_scheduler",
                metadata={
                    "lane": item.get("lane"),
                    "trust_level": item.get("trust_level"),
                    "status": item.get("status"),
                    "lane_source": item.get("lane_source"),
                    "signal_template_source": template_source,
                },
            )
        )
    return signals


def preferred_lane(
    spec: dict[str, Any],
    badge: dict[str, Any],
    *,
    policy: dict[str, Any],
    policy_source: str,
) -> tuple[str, str]:
    key = str(spec.get("key") or spec.get("agent") or "").strip()
    allowed = [str(item).strip() for item in badge.get("allowed_lanes") or [] if str(item).strip()]
    explicit_lane = explicit_preferred_lane(spec, policy)
    if explicit_lane:
        return explicit_lane, policy_source
    terms = manifest_terms(spec)
    for item in policy.get("term_lane_preferences") if isinstance(policy.get("term_lane_preferences"), list) else []:
        if not isinstance(item, dict):
            continue
        lane = str(item.get("lane") or "").strip()
        preference_terms = {str(term).strip().lower() for term in item.get("terms") or [] if str(term).strip()}
        if lane and preference_terms and terms & preference_terms and lane_allowed(lane, allowed):
            return lane, policy_source
    for lane in [str(item).strip() for item in policy.get("fallback_order") or [] if str(item).strip()]:
        if lane_allowed(lane, allowed):
            return lane, policy_source
    default_lane = str(policy.get("default_lane") or "inspection").strip() or "inspection"
    return default_lane, policy_source


def effective_lane_policy(policy: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    if isinstance(policy, dict) and policy:
        return policy, DECLARED_LANE_POLICY_SOURCE
    return legacy_lane_policy(), legacy_lane_policy_source()


def explicit_preferred_lane(spec: dict[str, Any], policy: dict[str, Any]) -> str:
    preferred = policy.get("preferred_lanes") if isinstance(policy.get("preferred_lanes"), dict) else {}
    for value in (
        spec.get("key"),
        spec.get("agent"),
        spec.get("name"),
        spec.get("agent_type"),
        spec.get("committee_role"),
    ):
        text = str(value or "").strip()
        if text and str(preferred.get(text) or "").strip():
            return str(preferred[text]).strip()
    return ""


def lane_allowed(lane: str, allowed: list[str]) -> bool:
    return not allowed or lane in allowed


def lane_list(policy: dict[str, Any]) -> list[str]:
    lanes = [str(item).strip() for item in policy.get("lanes") or [] if str(item).strip()]
    return lanes or legacy_lane_policy()["lanes"]


def lane_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    loop_policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    policy = loop_policy.get("lane_policy") if isinstance(loop_policy.get("lane_policy"), dict) else {}
    return policy


def lane_assignment_signal_template_from_state(state: dict[str, Any]) -> tuple[str, str]:
    policy = lane_policy_from_state(state)
    declared = str(policy.get("assignment_signal_template") or "").strip()
    if declared:
        return declared, DECLARED_LANE_POLICY_SOURCE
    return legacy_lane_assignment_signal_template(), legacy_lane_policy_source()


def manifest_terms(spec: dict[str, Any]) -> set[str]:
    values = [
        spec.get("key"),
        spec.get("agent"),
        spec.get("name"),
        spec.get("agent_type"),
        spec.get("committee_role"),
        spec.get("description"),
        spec.get("focus"),
    ]
    for key in ("tags", "focus_items", "required_capabilities", "required_tools"):
        values.extend(spec.get(key) if isinstance(spec.get(key), list) else [])
    output: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
        output.update(part for part in text.replace("-", "_").replace("/", "_").split("_") if part)
    return output
