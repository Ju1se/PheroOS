from __future__ import annotations

from collections import defaultdict
from typing import Any

from runtime.swarm.event_log import swarm_event
from runtime.swarm.execution_context import SwarmExecutionContext
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.target_registry import canonical_target


TARGET_PRESSURE_SCHEMA_VERSION = "pheroos.target_pressure.v1"


def compute_target_pressure_map(
    state: dict[str, Any],
    *,
    context: SwarmExecutionContext | None = None,
) -> dict[str, Any]:
    context = context or SwarmExecutionContext.from_state(state)
    by_target: dict[str, dict[str, Any]] = {}
    for target in context.targets:
        canonical = canonical_target(target.get("canonical_target") or target.get("target"))
        pressure = safe_float(target.get("demand_strength"), 0.55)
        by_target[canonical] = {
            "target": canonical,
            "pressure": pressure,
            "base_pressure": pressure,
            "reasons": [{"source": "target_declaration", "weight": round(pressure, 3)}],
        }

    add_stop_signal_pressure(by_target, state)
    add_evidence_gap_pressure(by_target, state, context)
    add_recovery_failure_pressure(by_target, state)

    targets = []
    for canonical, item in sorted(by_target.items()):
        pressure = min(1.0, max(0.0, safe_float(item.get("pressure"), 0.0)))
        targets.append({**item, "target": canonical, "pressure": round(pressure, 3)})
    events = [
        swarm_event(
            event_type="target.pressure.updated",
            run_id=context.run_id,
            tenant_id=context.tenant_id,
            actor="pheroos.target_pressure",
            target=item["target"],
            summary=f"Target pressure for {item['target']} is {item['pressure']}.",
            payload={"pressure": item["pressure"], "reasons": item.get("reasons", [])},
        )
        for item in targets
    ]
    return {
        "schema_version": TARGET_PRESSURE_SCHEMA_VERSION,
        "threshold": context.target_pressure_threshold,
        "targets": targets,
        "by_target": {item["target"]: item for item in targets},
        "events": events,
    }


def add_stop_signal_pressure(by_target: dict[str, dict[str, Any]], state: dict[str, Any]) -> None:
    for signal in active_stop_signals(state):
        target = canonical_target(signal.get("target"))
        entry = pressure_entry(by_target, target)
        entry["pressure"] = max(safe_float(entry.get("pressure"), 0.0), 0.95)
        entry["reasons"].append({"source": "active_stop_signal", "signal_id": signal.get("id"), "weight": 0.95})


def add_evidence_gap_pressure(
    by_target: dict[str, dict[str, Any]],
    state: dict[str, Any],
    context: SwarmExecutionContext,
) -> None:
    gaps = evidence_gaps_from_state(state)
    if not gaps:
        return
    gate_targets = [target["canonical_target"] for target in context.targets if str(target.get("canonical_target")).startswith("gate:")]
    fallback_targets = gate_targets or [target["canonical_target"] for target in context.targets] or ["run"]
    grouped: dict[str, int] = defaultdict(int)
    for gap in gaps:
        target = canonical_target(gap.get("canonical_target") or gap.get("target") or gap.get("evidence_target") or fallback_targets[0])
        if target == "run":
            target = fallback_targets[0]
        grouped[target] += 1
    for target, count in grouped.items():
        entry = pressure_entry(by_target, target)
        weight = min(0.92, 0.72 + (0.04 * count))
        entry["pressure"] = max(safe_float(entry.get("pressure"), 0.0), weight)
        entry["reasons"].append({"source": "evidence_gap", "gap_count": count, "weight": round(weight, 3)})


def add_recovery_failure_pressure(by_target: dict[str, dict[str, Any]], state: dict[str, Any]) -> None:
    traces = []
    direct = state.get("recovery_trace")
    if isinstance(direct, dict):
        traces.append(direct)
    traces.extend(item for item in state.get("recovery_traces") or [] if isinstance(item, dict))
    for trace in traces:
        if str(trace.get("status") or "") != "recovery_failed":
            continue
        target = canonical_target(trace.get("target"))
        entry = pressure_entry(by_target, target)
        entry["pressure"] = max(safe_float(entry.get("pressure"), 0.0), 0.98)
        entry["reasons"].append({"source": "recovery_failed", "weight": 0.98})


def pressure_entry(by_target: dict[str, dict[str, Any]], target: str) -> dict[str, Any]:
    canonical = canonical_target(target)
    if canonical not in by_target:
        by_target[canonical] = {
            "target": canonical,
            "pressure": 0.0,
            "base_pressure": 0.0,
            "reasons": [],
        }
    return by_target[canonical]


def active_stop_signals(state: dict[str, Any]) -> list[dict[str, Any]]:
    signals = []
    signals.extend(state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else [])
    snapshot = state.get("pheromone_field_snapshot") if isinstance(state.get("pheromone_field_snapshot"), dict) else {}
    signals.extend(snapshot.get("stop_signals") if isinstance(snapshot.get("stop_signals"), list) else [])
    signals.extend(
        signal
        for signal in snapshot.get("signals") or []
        if isinstance(signal, dict) and signal.get("type") == "stop_signal"
    )
    return [signal for signal in signals if isinstance(signal, dict) and is_active_blocker(signal)]


def evidence_gaps_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    gaps.extend(item for item in data_gate.get("evidence_gaps") or [] if isinstance(item, dict))
    evidence_graph = state.get("evidence_graph") if isinstance(state.get("evidence_graph"), dict) else {}
    gaps.extend(item for item in evidence_graph.get("blockers") or [] if isinstance(item, dict))
    return gaps


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
