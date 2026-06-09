from __future__ import annotations

from typing import Any

from runtime.swarm.legacy_swarm_controller_policy import (
    controller_homeostasis_action,
    legacy_swarm_controller_policy,
    legacy_swarm_controller_policy_source,
    render_swarm_controller_template,
)
from runtime.swarm.response_threshold import mandatory_committee_spec
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


DECLARED_SWARM_CONTROLLER_POLICY_SOURCE = "capability_swarm_loop_policy"


def build_swarm_controller_report(state: dict[str, Any], member_specs: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn swarm protocol reports into runtime control decisions.

    The lower-level swarm modules intentionally produce descriptive reports:
    encounter rate, bottlenecks, arousal, lane assignments, and homeostasis.
    This controller is the OS-level actuator. It converts those reports into
    concrete scheduling, verification, quorum, and writer policies while
    keeping domain analysis outside this layer.
    """

    overrides: dict[str, dict[str, Any]] = {}
    actions: list[dict[str, Any]] = []
    controller_policy, controller_policy_source = effective_swarm_controller_policy(state)

    bottleneck = state.get("bottleneck_report") if isinstance(state.get("bottleneck_report"), dict) else {}
    for item in bottleneck.get("bottlenecks") or []:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or controller_policy.get("default_bottleneck_reason") or "")
        for agent in item.get("recruit") or []:
            _merge_agent_override(
                overrides,
                str(agent),
                {"recruit": True, "priority_delta": 0.2, "activation_bias": 0.15, "reasons": [reason]},
            )
            actions.append({"action": "recruit", "agent": str(agent), "reason": reason})
        for agent in item.get("throttle") or []:
            _merge_agent_override(
                overrides,
                str(agent),
                {"throttle": True, "priority_delta": -0.15, "activation_bias": -0.2, "reasons": [reason]},
            )
            actions.append({"action": "throttle", "agent": str(agent), "reason": reason})

    encounter = state.get("encounter_rate_report") if isinstance(state.get("encounter_rate_report"), dict) else {}
    encounter_status = str(encounter.get("status") or "")
    runtime_budget = {
        "mode": "normal",
        "recommendation": encounter.get("recommendation") or controller_policy.get("runtime_budget_default_recommendation"),
    }
    if encounter_status in {"poor", "degraded"}:
        runtime_budget["mode"] = "conservative" if encounter_status == "degraded" else "reduced_expansion"
        actions.append(
            {
                "action": "adjust_runtime_budget",
                "target": str(controller_policy.get("runtime_budget_target") or ""),
                "reason": str(encounter.get("recommendation") or controller_policy.get("low_return_reason") or ""),
                "action_policy_source": controller_policy_source,
            }
        )

    arousal = state.get("arousal_report") if isinstance(state.get("arousal_report"), dict) else {}
    recommendations = arousal.get("recommendations") if isinstance(arousal.get("recommendations"), dict) else {}
    blocked_conclusion_targets = [
        str(item)
        for item in arousal.get("blocked_conclusion_targets") or recommendations.get("blocked_conclusion_targets") or []
        if str(item).strip()
    ]
    allowed_conclusion_targets = [
        str(item)
        for item in recommendations.get("allowed_conclusion_targets")
        or recommendations.get("allow_conclusion_targets")
        or []
        if str(item).strip()
    ]
    verification_policy = {
        "strictness": recommendations.get("verifier_strictness") or "normal",
        "reason": str(controller_policy.get("verification_policy_reason") or ""),
        "policy_source": controller_policy_source,
    }
    writer_policy = {
        "temperature_cap": recommendations.get("writer_temperature_cap", 0.2),
        "allow_formal_conclusion": bool(recommendations.get("allow_formal_conclusion", True)),
        "allowed_conclusion_targets": list(dict.fromkeys(allowed_conclusion_targets)),
        "allow_conclusion_targets": list(dict.fromkeys(allowed_conclusion_targets)),
        "blocked_conclusion_targets": list(dict.fromkeys(blocked_conclusion_targets)),
    }
    quorum_policy = {
        "threshold_delta": recommendations.get("quorum_threshold_delta", 0.0),
        "min_independence_score": 0.5,
        "force_fallback_when_low_independence": True,
    }
    if str(arousal.get("status") or "") in {"watch", "elevated"}:
        actions.append(
            {
                "action": "raise_verification_policy",
                "target": str(controller_policy.get("arousal_verification_target") or ""),
                "reason": ", ".join(arousal.get("triggers") or [])
                or str(controller_policy.get("arousal_verification_reason") or ""),
                "action_policy_source": controller_policy_source,
            }
        )

    homeostasis = state.get("homeostasis_report") if isinstance(state.get("homeostasis_report"), dict) else {}
    for recommendation in homeostasis.get("recommendations") or []:
        text = str(recommendation)
        action = controller_homeostasis_action(text, controller_policy, policy_source=controller_policy_source)
        if action:
            actions.append(action)

    lane = state.get("lane_assignment_report") if isinstance(state.get("lane_assignment_report"), dict) else {}
    lane_policy = {
        "status": lane.get("status") or "unknown",
        "assignments": lane.get("assignments") or [],
        "violations": lane.get("violations") or [],
    }
    for violation in lane_policy["violations"]:
        if not isinstance(violation, dict):
            continue
        agent = str(violation.get("agent") or "")
        if agent:
            _merge_agent_override(
                overrides,
                agent,
                {
                    "throttle": True,
                    "priority_delta": -1.0,
                    "activation_bias": -1.0,
                    "reasons": [str(violation.get("reason") or controller_policy.get("default_lane_violation_reason") or "")],
                },
            )
            actions.append({"action": "block_lane_violation", "agent": agent, "reason": violation.get("reason")})

    member_keys = [str(spec.get("key") or spec.get("agent") or "") for spec in member_specs]
    return {
        "status": "controlling" if actions else "idle",
        "member_count": len([key for key in member_keys if key]),
        "actions": actions,
        "agent_overrides": overrides,
        "verification_policy": verification_policy,
        "quorum_policy": quorum_policy,
        "writer_policy": writer_policy,
        "lane_policy": lane_policy,
        "runtime_budget": runtime_budget,
        "controller_action_policy_source": controller_policy_source,
    }


def apply_controller_to_member_specs(
    member_specs: list[dict[str, Any]],
    report: dict[str, Any],
    *,
    explicit_selection: bool = False,
    min_members: int = 4,
) -> list[dict[str, Any]]:
    """Apply safe controller scheduling decisions to committee members."""

    if explicit_selection:
        return [dict(spec) for spec in member_specs]

    overrides = report.get("agent_overrides") if isinstance(report.get("agent_overrides"), dict) else {}
    next_specs = [dict(spec) for spec in member_specs]
    filtered: list[dict[str, Any]] = []
    remaining_count = len(next_specs)
    for spec in next_specs:
        key = str(spec.get("key") or "")
        override = overrides.get(key) if isinstance(overrides.get(key), dict) else {}
        if override.get("throttle") and not mandatory_committee_spec(spec) and remaining_count - 1 >= min_members:
            remaining_count -= 1
            continue
        if override:
            spec["swarm_controller_override"] = _dashboard_safe_override(override)
        filtered.append(spec)

    if not filtered:
        filtered = next_specs
    filtered.sort(key=lambda spec: (int(spec.get("order") or 1000), str(spec.get("key") or "")))
    return filtered


def swarm_controller_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    if report.get("status") == "idle":
        return []
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    for action in report.get("actions") or []:
        if not isinstance(action, dict):
            continue
        default_target = controller_default_value(state, "default_action_target")
        default_reason = controller_default_value(state, "default_action_reason")
        target = action.get("agent") or action.get("target") or default_target
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.DEMAND,
                target=f"agent:{target}" if action.get("agent") else str(target),
                content=str(action.get("reason") or action.get("action") or default_reason),
                strength=0.75,
                confidence=0.8,
                verification_state=VerificationState.VERIFIED,
                source_module="swarm_controller",
                metadata=action,
            )
        )
    quorum_policy = report.get("quorum_policy") if isinstance(report.get("quorum_policy"), dict) else {}
    if quorum_policy:
        template = str(controller_default_value(state, "quorum_policy_signal_template") or "")
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.QUORUM,
                target="quorum:policy",
                content=render_swarm_controller_template(template, quorum_policy),
                strength=0.65,
                confidence=0.82,
                verification_state=VerificationState.VERIFIED,
                source_module="swarm_controller",
                metadata=quorum_policy,
            )
        )
    return signals


def _merge_agent_override(
    overrides: dict[str, dict[str, Any]],
    agent: str,
    patch: dict[str, Any],
) -> None:
    current = overrides.setdefault(
        agent,
        {"priority_delta": 0.0, "activation_bias": 0.0, "recruit": False, "throttle": False, "reasons": []},
    )
    current["priority_delta"] = round(float(current.get("priority_delta") or 0) + float(patch.get("priority_delta") or 0), 3)
    current["activation_bias"] = round(float(current.get("activation_bias") or 0) + float(patch.get("activation_bias") or 0), 3)
    current["recruit"] = bool(current.get("recruit") or patch.get("recruit"))
    current["throttle"] = bool(current.get("throttle") or patch.get("throttle"))
    current["reasons"] = list(dict.fromkeys([*current.get("reasons", []), *patch.get("reasons", [])]))


def _dashboard_safe_override(override: dict[str, Any]) -> dict[str, Any]:
    return {
        "priority_delta": override.get("priority_delta"),
        "activation_bias": override.get("activation_bias"),
        "recruit": bool(override.get("recruit")),
        "throttle": bool(override.get("throttle")),
        "reasons": list(override.get("reasons") or []),
    }


def effective_swarm_controller_policy(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    declared = controller_action_policy_from_state(state)
    if declared:
        policy = legacy_swarm_controller_policy()
        policy.update(declared)
        return policy, DECLARED_SWARM_CONTROLLER_POLICY_SOURCE
    return legacy_swarm_controller_policy(), legacy_swarm_controller_policy_source()


def controller_default_value(state: dict[str, Any], key: str) -> Any:
    policy, _source = effective_swarm_controller_policy(state)
    return policy.get(key)


def controller_action_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    loop_policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    policy = loop_policy.get("controller_action_policy") if isinstance(loop_policy.get("controller_action_policy"), dict) else {}
    return policy
