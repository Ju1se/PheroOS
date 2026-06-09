from __future__ import annotations

from typing import Any

from runtime.swarm.legacy_tool_health_policy import (
    legacy_tool_health_failure_hints,
    legacy_tool_health_recommendation,
    legacy_tool_health_recommendation_source,
    legacy_tool_health_signal_fallback_content,
)
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


SWARM_LOOP_TOOL_HEALTH_RECOMMENDATION_SOURCE = "capability_swarm_loop_policy"


def build_tool_health_sentinel_report(state: dict[str, Any]) -> dict[str, Any]:
    attempts = 0
    failures = 0
    slow = 0
    by_tool: dict[str, dict[str, Any]] = {}

    for entry in state.get("execution_log") if isinstance(state.get("execution_log"), list) else []:
        calls = entry.get("tool_calls") if isinstance(entry, dict) and isinstance(entry.get("tool_calls"), list) else []
        for call in calls:
            if not isinstance(call, dict):
                continue
            tool = str(call.get("name") or "unknown_tool")
            attempts += 1
            item = by_tool.setdefault(tool, {"tool": tool, "attempts": 0, "failures": 0, "empty_results": 0, "slow_calls": 0})
            item["attempts"] += 1
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            failed = bool(result.get("ok") is False or call.get("error"))
            text = str(result.get("error") or result.get("detail") or call.get("error") or "").lower()
            if any(hint in text for hint in legacy_tool_health_failure_hints()):
                failed = True
            if is_empty_result(result):
                item["empty_results"] += 1
            duration = as_float(call.get("duration_seconds") or result.get("duration_seconds"))
            if duration >= 30:
                slow += 1
                item["slow_calls"] += 1
            if failed:
                failures += 1
                item["failures"] += 1

    wrds = state.get("wrds_result") if isinstance(state.get("wrds_result"), dict) else {}
    if wrds and wrds.get("ok") is False:
        attempts += 1
        failures += 1
        item = by_tool.setdefault("wrds", {"tool": "wrds", "attempts": 0, "failures": 0, "empty_results": 0, "slow_calls": 0})
        item["attempts"] += 1
        item["failures"] += 1

    metrics = state.get("agent_metrics") if isinstance(state.get("agent_metrics"), list) else []
    model_failures = [
        item
        for item in metrics
        if isinstance(item, dict)
        and str(item.get("status") or "").lower() in {"failed", "completed_with_model_failure"}
    ]
    if model_failures:
        attempts += len(model_failures)
        failures += len(model_failures)
        item = by_tool.setdefault("model_gateway", {"tool": "model_gateway", "attempts": 0, "failures": 0, "empty_results": 0, "slow_calls": 0})
        item["attempts"] += len(model_failures)
        item["failures"] += len(model_failures)

    failure_rate = failures / attempts if attempts else 0.0
    if attempts == 0:
        status = "no_tool_activity"
    elif failure_rate >= 0.5:
        status = "failing"
    elif failure_rate >= 0.2 or slow:
        status = "degraded"
    else:
        status = "healthy"
    recommendation_text, recommendation_source = recommendation(status, state=state)
    return {
        "schema_version": "pheroos.tool_health_sentinel.v1",
        "status": status,
        "attempts": attempts,
        "failures": failures,
        "failure_rate": round(failure_rate, 3),
        "slow_call_count": slow,
        "model_failure_count": len(model_failures),
        "tools": list(by_tool.values()),
        "recommendation": recommendation_text,
        "recommendation_source": recommendation_source,
    }


def tool_health_sentinel_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    if report.get("status") in {"healthy", "no_tool_activity"}:
        return []
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    blocking = report.get("status") == "failing"
    return [
        PheromoneSignal(
            run_id=run_id,
            tenant_id=tenant_id,
            type=SignalType.TOOL_HEALTH,
            target="system:tool_routes",
            content=str(report.get("recommendation") or legacy_tool_health_signal_fallback_content()),
            strength=0.9 if blocking else 0.65,
            confidence=0.82,
            priority="hard" if blocking else "normal",
            blocking=blocking,
            verification_state=VerificationState.BLOCKING if blocking else VerificationState.VERIFIED,
            source_module="tool_health_sentinel",
            evidence_ref="execution_log/agent_metrics",
            metadata={"failure_rate": report.get("failure_rate"), "failures": report.get("failures")},
        )
    ]


def is_empty_result(result: dict[str, Any]) -> bool:
    if not result or result.get("ok") is False:
        return False
    data = result.get("data")
    if data in (None, "", [], {}):
        return True
    return False


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def recommendation(status: str, *, state: dict[str, Any] | None = None) -> tuple[str, str]:
    policy = swarm_loop_policy_from_state(state or {})
    recommendations = policy.get("tool_health_recommendations") if isinstance(policy.get("tool_health_recommendations"), dict) else {}
    declared = str(recommendations.get(status) or "").strip()
    if declared:
        return declared, SWARM_LOOP_TOOL_HEALTH_RECOMMENDATION_SOURCE
    return legacy_tool_health_recommendation(status), legacy_tool_health_recommendation_source()


def swarm_loop_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    return policy
