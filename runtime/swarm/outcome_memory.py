from __future__ import annotations

from typing import Any

from runtime.swarm.agent_outputs import runtime_agent_outputs
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_outcome_memory_steward_report(state: dict[str, Any]) -> dict[str, Any]:
    outputs = runtime_agent_outputs(state)
    allocation = state.get("agent_allocation_trace") if isinstance(state.get("agent_allocation_trace"), list) else []
    diagnostics = state.get("agent_signal_diagnostics") if isinstance(state.get("agent_signal_diagnostics"), list) else []
    verification = state.get("agent_signal_verification_trace") if isinstance(state.get("agent_signal_verification_trace"), list) else []
    policing = state.get("policing_trace") if isinstance(state.get("policing_trace"), dict) else {}

    updates: list[dict[str, Any]] = []
    task_by_agent = {str(item.get("agent")): str(item.get("task_type") or "agent_review") for item in allocation if isinstance(item, dict)}
    rejected_by_agent: dict[str, int] = {}
    for item in diagnostics:
        if isinstance(item, dict) and str(item.get("status")) == "rejected":
            agent = str(item.get("agent") or "unknown")
            rejected_by_agent[agent] = rejected_by_agent.get(agent, 0) + 1
    promoted_count = len([item for item in verification if isinstance(item, dict) and str(item.get("status")) == "promoted"])

    for agent, output in sorted(outputs.items()):
        if not isinstance(output, dict):
            continue
        status = str(output.get("status") or "").lower()
        success = status not in {"failed", "error", "unstructured_failed"}
        updates.append(
            {
                "agent": str(agent),
                "task_type": task_by_agent.get(str(agent), "agent_review"),
                "success": success,
                "rejected_signal_count": rejected_by_agent.get(str(agent), 0),
                "hard_veto": bool(output.get("hard_veto")),
                "learning_scope": "agent_process_only",
            }
        )

    violations = policing.get("violations") if isinstance(policing.get("violations"), list) else []
    status = "penalize_protocol_violations" if violations or rejected_by_agent else "update_profiles"
    return {
        "schema_version": "pheroos.outcome_memory_steward.v1",
        "status": status,
        "profile_updates": updates,
        "promoted_signal_count": promoted_count,
        "rejected_signal_count": sum(rejected_by_agent.values()),
        "protocol_violation_count": len(violations),
        "memory_boundary": "does_not_store_domain_conclusions",
        "excluded_fields": [
            "agent_outputs.*.thesis",
            "agent_outputs.*.decision",
            "agent_outputs.*.final_decision",
            "legacy_agent_outputs.*.thesis",
            "legacy_agent_outputs.*.decision",
            "legacy_agent_outputs.*.final_decision",
            "agent_decision",
            "final_answer",
            "domain_conclusion",
        ],
    }


def outcome_memory_steward_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    if not report.get("profile_updates"):
        return []
    return [
        PheromoneSignal(
            run_id=str(state.get("run_id") or "unknown"),
            tenant_id=str((state.get("metadata") or {}).get("tenant_id") or "default"),
            type=SignalType.CAPABILITY,
            target="agent_profiles:process_reliability",
            content="Outcome Memory Steward updated process-only agent profile evidence.",
            strength=0.55,
            confidence=0.72,
            verification_state=VerificationState.VERIFIED,
            source_module="outcome_memory_steward",
            metadata={
                "profile_update_count": len(report.get("profile_updates") or []),
                "rejected_signal_count": report.get("rejected_signal_count"),
                "memory_boundary": report.get("memory_boundary"),
            },
        )
    ]
