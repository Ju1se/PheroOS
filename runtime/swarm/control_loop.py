from __future__ import annotations

from typing import Any

from runtime.swarm.agent_decisions import (
    has_agent_decision_value,
    runtime_agent_decision,
    state_with_agent_decision,
)
from runtime.swarm.agent_allocator import allocate_agents_for_pressure
from runtime.swarm.event_log import swarm_event
from runtime.swarm.execution_context import SwarmExecutionContext
from runtime.swarm.execution_loop import public_execution_loop_report, run_swarm_execution_loop
from runtime.swarm.outcome_feedback import build_outcome_feedback
from runtime.swarm.quorum import build_quorum_trace
from runtime.swarm.recovery_engine import apply_recovery_resolution, build_recovery_trace
from runtime.swarm.recruitment import protocol_matches_target, recruit_agents_for_recovery
from runtime.swarm.signal_extractor import update_state_with_signals
from runtime.swarm.target_pressure import compute_target_pressure_map
from runtime.swarm.target_registry import canonical_target


GENERIC_CONTROL_LOOP_SCHEMA_VERSION = "pheroos.generic_control_loop.v1"


def run_generic_swarm_control_loop(state: dict[str, Any], *, tool_registry: Any | None = None) -> dict[str, Any]:
    context = SwarmExecutionContext.from_state(state)
    pressure = compute_target_pressure_map(state, context=context)
    allocation = allocate_agents_for_pressure(context, pressure)
    loop_state = state_with_allocations(state, allocation["selected"] + allocation["suppressed"])
    loop = run_swarm_execution_loop(loop_state, max_rounds=context.max_rounds)
    loop_report = public_execution_loop_report(loop)
    current_state = apply_loop_signals(loop_state, loop.get("signals") or [])

    recovery_traces = []
    recruitment_reports = []
    events = []
    events.extend(pressure.get("events") or [])
    events.extend(allocation.get("events") or [])
    events.extend(loop.get("events") or [])

    for target in recovery_targets(context, pressure):
        recruitment_reports.append(recruit_agents_for_recovery(context, target=target))
        events.append(
            swarm_event(
                event_type="recovery.started",
                run_id=context.run_id,
                tenant_id=context.tenant_id,
                actor="pheroos.control_loop",
                target=target,
                summary=f"Started declared recovery for {target}.",
                payload={"target_pressure": pressure.get("by_target", {}).get(target, {})},
            )
        )
        recovery_trace = build_recovery_trace(
            current_state,
            target=target,
            context=recovery_context(current_state, pressure=pressure, target=target),
            tool_registry=tool_registry,
        )
        recovery_traces.append(recovery_trace)
        events.extend(recovery_detail_events(context, recovery_trace=recovery_trace, target=target))
        events.append(
            swarm_event(
                event_type="recovery.succeeded" if recovery_trace.get("status") == "recovery_succeeded" else "recovery.failed",
                run_id=context.run_id,
                tenant_id=context.tenant_id,
                actor="pheroos.control_loop",
                target=target,
                summary=f"Declared recovery {recovery_trace.get('status')} for {target}.",
                payload=recovery_trace,
            )
        )
        if recovery_trace.get("status") == "recovery_succeeded":
            current_state = {**current_state, **apply_recovery_resolution(current_state, recovery_trace)}

    current_state = state_with_recovery_trace(current_state, recovery_traces)
    quorum = build_quorum_trace(current_state)
    status = control_loop_status(quorum=quorum, recovery_traces=recovery_traces)
    events.extend(candidate_events(context, quorum=quorum, status=status))
    report: dict[str, Any] = {
        "schema_version": GENERIC_CONTROL_LOOP_SCHEMA_VERSION,
        "run_id": context.run_id,
        "tenant_id": context.tenant_id,
        "status": status,
        "intent": context.intent,
        "protocol_source": context.protocol_source,
        "max_rounds": context.max_rounds,
        "target_pressure": pressure,
        "agent_allocation": allocation,
        "activated_agents": [item["agent"] for item in allocation["selected"]],
        "execution_loop": loop_report,
        "recruitment_reports": recruitment_reports,
        "recovery_traces": recovery_traces,
        "quorum_trace": quorum,
        "events": events,
        "state_updates": {
            "pheromone_field_snapshot": current_state.get("pheromone_field_snapshot", {}),
            "stop_signals": current_state.get("stop_signals", []),
            "signal_resolution_report": current_state.get("signal_resolution_report", {}),
        },
    }
    feedback = build_outcome_feedback(current_state, report, context=context)
    report["outcome_feedback"] = feedback
    report["events"] = [*events, *(feedback.get("events") or [])]
    return report


def state_with_allocations(state: dict[str, Any], allocations: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    return {
        **state,
        "metadata": {
            **metadata,
            "os_plan": {
                **os_plan,
                "swarm_plan": {
                    **swarm_plan,
                    "agent_allocation": allocations,
                    "activated_agents": [item["agent"] for item in allocations if item.get("activated")],
                },
            },
        },
    }


def apply_loop_signals(state: dict[str, Any], signals: list[Any]) -> dict[str, Any]:
    if not signals:
        return state
    seed_state = state
    if not isinstance(state.get("pheromone_field_snapshot"), dict) and isinstance(state.get("stop_signals"), list):
        seed_state = {
            **state,
            "pheromone_field_snapshot": {
                "signals": [signal for signal in state.get("stop_signals") or [] if isinstance(signal, dict)],
            },
        }
    updates = update_state_with_signals(seed_state, signals)
    return {**state, **updates}


def state_with_recovery_trace(state: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
    if not traces:
        return state
    failed = next((trace for trace in traces if trace.get("status") == "recovery_failed" and trace.get("fallback_candidate")), None)
    agent_decision = runtime_agent_decision(state)
    if failed and not has_agent_decision_value(agent_decision):
        agent_decision = {**agent_decision, "final_decision": failed.get("fallback_candidate")}
    updated_state = {
        **state,
        "recovery_traces": traces,
        "recovery_trace": traces[-1],
    }
    return state_with_agent_decision(updated_state, agent_decision) if agent_decision else updated_state


def recovery_targets(context: SwarmExecutionContext, pressure: dict[str, Any]) -> list[str]:
    by_target = pressure.get("by_target") if isinstance(pressure.get("by_target"), dict) else {}
    output = []
    for target, item in by_target.items():
        if safe_float(item.get("pressure"), 0.0) < context.target_pressure_threshold:
            continue
        if any(protocol_matches_target(protocol, target) for protocol in context.recovery_protocols):
            output.append(canonical_target(target))
    return sorted(set(output))


def recovery_detail_events(
    context: SwarmExecutionContext,
    *,
    recovery_trace: dict[str, Any],
    target: str,
) -> list[dict[str, Any]]:
    trace_items = recovery_trace.get("trace") if isinstance(recovery_trace.get("trace"), list) else []
    events = []
    for item in trace_items:
        if not isinstance(item, dict):
            continue
        event_type = str(item.get("event_type") or item.get("type") or "").strip()
        if not event_type.startswith("recovery.") or event_type in {"recovery.succeeded", "recovery.failed"}:
            continue
        events.append(
            swarm_event(
                event_type=event_type,
                run_id=context.run_id,
                tenant_id=context.tenant_id,
                actor=str(item.get("actor") or "recovery_engine"),
                target=item.get("target") or recovery_trace.get("target") or target,
                summary=str(item.get("summary") or event_type),
                payload={**item, "recovery_trace": recovery_trace},
            )
        )
    return events


def recovery_context(state: dict[str, Any], *, pressure: dict[str, Any], target: str) -> dict[str, Any]:
    data = state.get("recovery_context") if isinstance(state.get("recovery_context"), dict) else {}
    target_pressure = pressure.get("by_target", {}).get(target, {}) if isinstance(pressure.get("by_target"), dict) else {}
    return {
        **data,
        "target": target,
        "canonical_target": target,
        "needs_recovery": True,
        "target_pressure": target_pressure.get("pressure"),
    }


def control_loop_status(*, quorum: dict[str, Any], recovery_traces: list[dict[str, Any]]) -> str:
    if any(trace.get("status") == "recovery_failed" for trace in recovery_traces):
        return "blocked"
    if quorum.get("status") == "committed" and quorum.get("committed_candidate"):
        return "committed"
    return "completed"


def candidate_events(context: SwarmExecutionContext, *, quorum: dict[str, Any], status: str) -> list[dict[str, Any]]:
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    events = []
    if committed and status == "committed":
        events.append(
            swarm_event(
                event_type="candidate.committed",
                run_id=context.run_id,
                tenant_id=context.tenant_id,
                actor="pheroos.control_loop",
                target=committed.get("id") or committed.get("label") or "candidate",
                summary="Generic quorum committed a declared candidate.",
                payload={"candidate": committed, "candidate_source": quorum.get("candidate_source")},
            )
        )
    for candidate in quorum.get("candidates") or []:
        if isinstance(candidate, dict) and candidate.get("blocked"):
            events.append(
                swarm_event(
                    event_type="candidate.blocked",
                    run_id=context.run_id,
                    tenant_id=context.tenant_id,
                    actor="pheroos.control_loop",
                    target=candidate.get("id") or candidate.get("label") or "candidate",
                    summary="Generic quorum blocked a candidate.",
                    payload={"candidate": candidate},
                )
            )
    return events


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
