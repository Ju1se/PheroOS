from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.swarm.target_registry import canonical_target, target_kind


@dataclass(frozen=True)
class SwarmExecutionContext:
    run_id: str
    tenant_id: str
    task: str
    intent: str
    metadata: dict[str, Any]
    os_plan: dict[str, Any]
    swarm_plan: dict[str, Any]
    targets: list[dict[str, Any]] = field(default_factory=list)
    allocations: list[dict[str, Any]] = field(default_factory=list)
    agents: list[dict[str, Any]] = field(default_factory=list)
    recovery_protocols: list[dict[str, Any]] = field(default_factory=list)
    capability_protocols: list[dict[str, Any]] = field(default_factory=list)
    candidate_policy: dict[str, Any] = field(default_factory=dict)
    quorum_policy: dict[str, Any] = field(default_factory=dict)
    stop_signal_policy: dict[str, Any] = field(default_factory=dict)
    tool_policy: dict[str, Any] = field(default_factory=dict)
    output_policy: dict[str, Any] = field(default_factory=dict)
    evidence_policy: dict[str, Any] = field(default_factory=dict)
    agent_selection_policy: dict[str, Any] = field(default_factory=dict)
    swarm_loop_policy: dict[str, Any] = field(default_factory=dict)
    protocol_source: str | None = None
    max_rounds: int = 2
    target_pressure_threshold: float = 0.7

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "SwarmExecutionContext":
        metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
        swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
        loop_policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
        quorum_policy = swarm_plan.get("quorum_policy") if isinstance(swarm_plan.get("quorum_policy"), dict) else {}
        return cls(
            run_id=str(state.get("run_id") or "unknown"),
            tenant_id=str(metadata.get("tenant_id") or os_plan.get("tenant_id") or "default"),
            task=str(state.get("task") or os_plan.get("task") or ""),
            intent=str(os_plan.get("intent") or os_plan.get("task_type") or swarm_plan.get("intent") or ""),
            metadata=metadata,
            os_plan=os_plan,
            swarm_plan=swarm_plan,
            targets=targets_from_swarm_plan(swarm_plan),
            allocations=[item for item in swarm_plan.get("agent_allocation") or [] if isinstance(item, dict)],
            agents=agents_from_metadata(metadata),
            recovery_protocols=[item for item in swarm_plan.get("recovery_protocols") or [] if isinstance(item, dict)],
            capability_protocols=[item for item in swarm_plan.get("capability_protocols") or [] if isinstance(item, dict)],
            candidate_policy=swarm_plan.get("candidate_policy") if isinstance(swarm_plan.get("candidate_policy"), dict) else {},
            quorum_policy=quorum_policy,
            stop_signal_policy=swarm_plan.get("stop_signal_policy") if isinstance(swarm_plan.get("stop_signal_policy"), dict) else {},
            tool_policy=swarm_plan.get("tool_policy") if isinstance(swarm_plan.get("tool_policy"), dict) else {},
            output_policy=swarm_plan.get("output_policy") if isinstance(swarm_plan.get("output_policy"), dict) else {},
            evidence_policy=swarm_plan.get("evidence_policy") if isinstance(swarm_plan.get("evidence_policy"), dict) else {},
            agent_selection_policy=swarm_plan.get("agent_selection_policy") if isinstance(swarm_plan.get("agent_selection_policy"), dict) else {},
            swarm_loop_policy=loop_policy,
            protocol_source=swarm_plan.get("protocol_source"),
            max_rounds=safe_int(loop_policy.get("max_rounds") or swarm_plan.get("max_rounds") or quorum_policy.get("max_swarm_rounds"), 2),
            target_pressure_threshold=safe_float(loop_policy.get("target_pressure_threshold"), 0.7),
        )


def targets_from_swarm_plan(swarm_plan: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in swarm_plan.get("target_signals") or []:
        if not isinstance(item, dict):
            continue
        canonical = canonical_target(item.get("canonical_target") or item.get("target"))
        if canonical == "run" or canonical in seen:
            continue
        seen.add(canonical)
        output.append(
            {
                **item,
                "target": item.get("target") or canonical,
                "canonical_target": canonical,
                "target_kind": target_kind(canonical),
                "demand_strength": safe_float(item.get("demand_strength") or item.get("default_pressure"), 0.6),
            }
        )
    return output


def agents_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    registry = metadata.get("agent_registry") if isinstance(metadata.get("agent_registry"), dict) else {}
    agents = registry.get("agents") if isinstance(registry.get("agents"), list) else []
    return [item for item in agents if isinstance(item, dict)]


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
