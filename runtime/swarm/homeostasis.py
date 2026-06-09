from __future__ import annotations

import json
from typing import Any

from runtime.swarm.agent_outputs import runtime_agent_outputs
from runtime.swarm.legacy_homeostasis_policy import (
    legacy_homeostasis_policy_source,
    legacy_homeostasis_recommendation,
    legacy_homeostasis_recommendation_rules,
    legacy_homeostasis_signal_template,
    render_homeostasis_signal_template,
)
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


SWARM_LOOP_HOMEOSTASIS_POLICY_SOURCE = "capability_swarm_loop_policy"


def build_homeostasis_report(state: dict[str, Any]) -> dict[str, Any]:
    variables = {
        "token_heat": token_heat(state),
        "latency_pressure": latency_pressure(state),
        "evidence_coverage": evidence_coverage(state),
        "risk_pressure": risk_pressure(state),
        "verification_backlog": verification_backlog(state),
        "tool_failure_rate": tool_failure_rate(state),
        "crowding": crowding(state),
    }
    recommendations = recommendations_for(variables, state=state)
    recommendation_sources = recommendation_sources_for(variables, state=state)
    status = "unstable" if max(variables["risk_pressure"], variables["verification_backlog"], variables["tool_failure_rate"]) >= 0.75 else "strained" if any(value >= 0.6 for value in variables.values()) else "stable"
    return {
        "status": status,
        "variables": {k: round(v, 3) for k, v in variables.items()},
        "recommendations": recommendations,
        "recommendation_sources": recommendation_sources,
    }


def homeostasis_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    if report.get("status") == "stable":
        return []
    pressure = max(report.get("variables", {}).values() or [0])
    content, content_source = homeostasis_signal_content(report, state=state)
    return [
        PheromoneSignal(
            run_id=str(state.get("run_id") or "unknown"),
            tenant_id=str((state.get("metadata") or {}).get("tenant_id") or "default"),
            type=SignalType.HOMEOSTASIS,
            target="system:swarm_stability",
            content=content,
            strength=float(pressure),
            confidence=0.75,
            verification_state=VerificationState.VERIFIED,
            source_module="homeostasis",
            evidence_ref="run_state_metrics",
            metadata={**report, "signal_template_source": content_source},
        )
    ]


def token_heat(state: dict[str, Any]) -> float:
    text = json.dumps(
        {
            "research": state.get("research_brief"),
            "agent_outputs": runtime_agent_outputs(state),
            "final": state.get("final"),
        },
        ensure_ascii=False,
        default=str,
    )
    return min(1.0, len(text) / 60000)


def latency_pressure(state: dict[str, Any]) -> float:
    metrics = state.get("agent_metrics") if isinstance(state.get("agent_metrics"), list) else []
    durations = [float(item.get("duration_seconds") or 0) for item in metrics if isinstance(item, dict)]
    if not durations:
        return 0.0
    return min(1.0, sum(durations) / max(len(durations), 1) / 30.0)


def evidence_coverage(state: dict[str, Any]) -> float:
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    metrics = registry.get("metrics") if isinstance(registry.get("metrics"), list) else []
    gaps = data_gate.get("evidence_gaps") if isinstance(data_gate.get("evidence_gaps"), list) else []
    return min(1.0, len(metrics) / max(len(metrics) + len(gaps), 1))


def risk_pressure(state: dict[str, Any]) -> float:
    stop_count = len(
        [signal for signal in state.get("stop_signals") or [] if isinstance(signal, dict) and is_active_blocker(signal)]
    ) if isinstance(state.get("stop_signals"), list) else 0
    review = state.get("review") if isinstance(state.get("review"), dict) else {}
    risk = min(0.6, stop_count * 0.2)
    if str(review.get("status") or "").upper() in {"REJECT_CONDITIONAL", "REJECT_FATAL"}:
        risk += 0.35
    return min(1.0, risk)


def verification_backlog(state: dict[str, Any]) -> float:
    bottleneck = state.get("bottleneck_report") if isinstance(state.get("bottleneck_report"), dict) else {}
    pending = float(bottleneck.get("pending_evidence") or 0)
    verified = float(bottleneck.get("verified_evidence") or 0)
    return min(1.0, pending / max(pending + verified, 1))


def tool_failure_rate(state: dict[str, Any]) -> float:
    attempts = 0
    failures = 0
    for entry in state.get("execution_log") if isinstance(state.get("execution_log"), list) else []:
        calls = entry.get("tool_calls") if isinstance(entry, dict) and isinstance(entry.get("tool_calls"), list) else []
        for call in calls:
            attempts += 1
            result = call.get("result") if isinstance(call, dict) else None
            if isinstance(result, dict) and result.get("ok") is False:
                failures += 1
    return failures / attempts if attempts else 0.0


def crowding(state: dict[str, Any]) -> float:
    allocations = state.get("agent_allocation_trace") if isinstance(state.get("agent_allocation_trace"), list) else []
    active = len([item for item in allocations if isinstance(item, dict) and item.get("activated")])
    return min(1.0, active / 8.0)


def recommendations_for(variables: dict[str, float], *, state: dict[str, Any] | None = None) -> list[str]:
    keys = triggered_recommendation_keys(variables)
    return [homeostasis_recommendation(key, state=state or {})[0] for key in keys]


def recommendation_sources_for(variables: dict[str, float], *, state: dict[str, Any]) -> dict[str, str]:
    return {
        key: homeostasis_recommendation(key, state=state)[1]
        for key in triggered_recommendation_keys(variables)
    }


def triggered_recommendation_keys(variables: dict[str, float]) -> list[str]:
    keys = [key for key, threshold in legacy_homeostasis_recommendation_rules() if variables.get(key, 0.0) >= threshold]
    return keys or ["default"]


def homeostasis_recommendation(key: str, *, state: dict[str, Any]) -> tuple[str, str]:
    policy = swarm_loop_policy_from_state(state)
    recommendations = (
        policy.get("homeostasis_recommendations")
        if isinstance(policy.get("homeostasis_recommendations"), dict)
        else {}
    )
    declared = str(recommendations.get(key) or "").strip()
    if declared:
        return declared, SWARM_LOOP_HOMEOSTASIS_POLICY_SOURCE
    return legacy_homeostasis_recommendation(key), legacy_homeostasis_policy_source()


def homeostasis_signal_content(report: dict[str, Any], *, state: dict[str, Any]) -> tuple[str, str]:
    policy = swarm_loop_policy_from_state(state)
    declared = str(policy.get("homeostasis_signal_template") or "").strip()
    if declared:
        return (
            render_homeostasis_signal_template(declared, report),
            SWARM_LOOP_HOMEOSTASIS_POLICY_SOURCE,
        )
    return (
        render_homeostasis_signal_template(legacy_homeostasis_signal_template(), report),
        legacy_homeostasis_policy_source(),
    )


def swarm_loop_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    return policy
