from __future__ import annotations

from typing import Any

from runtime.swarm.legacy_encounter_rate_policy import (
    legacy_encounter_rate_recommendation_source,
    legacy_encounter_rate_recommendation,
)
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


SWARM_LOOP_ENCOUNTER_RATE_RECOMMENDATION_SOURCE = "capability_swarm_loop_policy"


def build_encounter_rate_report(state: dict[str, Any]) -> dict[str, Any]:
    """Estimate recent verified-return rate from local runtime events.

    This is the ant encounter-rate primitive: the runtime does not need global
    certainty to adjust effort. It looks at recent local returns from agents,
    tools, verifiers, and Data Gate.
    """

    agent_metrics = state.get("agent_metrics") if isinstance(state.get("agent_metrics"), list) else []
    verification_trace = (
        state.get("agent_signal_verification_trace")
        if isinstance(state.get("agent_signal_verification_trace"), list)
        else []
    )
    tool_attempts, tool_successes = tool_return_counts(state.get("execution_log"))
    agent_attempts = len(agent_metrics)
    agent_successes = sum(1 for item in agent_metrics if metric_success(item))
    verifier_attempts = len(verification_trace)
    verifier_successes = sum(1 for item in verification_trace if str(item.get("status")) == "promoted")
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    data_gate_attempts = 1 if data_gate and data_gate.get("status") not in {None, "skipped"} else 0
    data_gate_successes = 1 if str(data_gate.get("status") or "").lower() in {"pass", "warn", "pass_wrds_only"} else 0

    attempts = agent_attempts + verifier_attempts + tool_attempts + data_gate_attempts
    successes = agent_successes + verifier_successes + tool_successes + data_gate_successes
    rate = round(successes / attempts, 3) if attempts else 0.0
    status = "insufficient_history"
    if attempts:
        status = "healthy" if rate >= 0.67 else "degraded" if rate >= 0.34 else "poor"
    recommendation, recommendation_source = recommendation_for_rate(status, state=state)
    return {
        "status": status,
        "rate": rate,
        "success_events": successes,
        "attempts": attempts,
        "agent_successes": agent_successes,
        "agent_attempts": agent_attempts,
        "tool_successes": tool_successes,
        "tool_attempts": tool_attempts,
        "verifier_successes": verifier_successes,
        "verifier_attempts": verifier_attempts,
        "recommendation": recommendation,
        "recommendation_source": recommendation_source,
    }


def encounter_rate_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    if not report.get("attempts"):
        return []
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    return [
        PheromoneSignal(
            run_id=str(state.get("run_id") or "unknown"),
            tenant_id=tenant_id,
            type=SignalType.ENCOUNTER_RATE,
            target=f"task:{task_target(state)}",
            content=f"Recent verified return rate is {report['rate']:.0%}; scheduler status is {report['status']}.",
            strength=float(report.get("rate") or 0.0),
            confidence=0.75 if report.get("attempts") else 0.2,
            verification_state=VerificationState.VERIFIED,
            source_module="encounter_rate",
            evidence_ref="agent_metrics/tool_returns/verifier_trace",
            metadata={key: report.get(key) for key in ("success_events", "attempts", "recommendation")},
        )
    ]


def tool_return_counts(execution_log: Any) -> tuple[int, int]:
    attempts = 0
    successes = 0
    for entry in execution_log if isinstance(execution_log, list) else []:
        calls = entry.get("tool_calls") if isinstance(entry, dict) and isinstance(entry.get("tool_calls"), list) else []
        for call in calls:
            attempts += 1
            result = call.get("result") if isinstance(call, dict) else None
            if not isinstance(result, dict) or result.get("ok") is not False:
                successes += 1
    return attempts, successes


def metric_success(metric: Any) -> bool:
    if not isinstance(metric, dict):
        return False
    status = str(metric.get("status") or "").lower()
    return status.startswith("completed") or status in {"done", "success"}


def task_target(state: dict[str, Any]) -> str:
    orchestration = state.get("orchestration") if isinstance(state.get("orchestration"), dict) else {}
    task_type = str(orchestration.get("task_type") or state.get("route") or "run").strip().lower()
    return task_type or "run"


def recommendation_for_rate(status: str, *, state: dict[str, Any] | None = None) -> tuple[str, str]:
    policy = swarm_loop_policy_from_state(state or {})
    recommendations = (
        policy.get("encounter_rate_recommendations")
        if isinstance(policy.get("encounter_rate_recommendations"), dict)
        else {}
    )
    declared = str(recommendations.get(status) or "").strip()
    if declared:
        return declared, SWARM_LOOP_ENCOUNTER_RATE_RECOMMENDATION_SOURCE
    return legacy_encounter_rate_recommendation(status), legacy_encounter_rate_recommendation_source()


def swarm_loop_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    return policy
