from __future__ import annotations

from typing import Any

from runtime.swarm.event_log import swarm_event
from runtime.swarm.execution_context import SwarmExecutionContext
from runtime.swarm.legacy_outcome_feedback import legacy_outcome_feedback_excluded_fields


OUTCOME_FEEDBACK_SCHEMA_VERSION = "pheroos.outcome_feedback.v1"


def build_outcome_feedback(
    state: dict[str, Any],
    control_report: dict[str, Any],
    *,
    context: SwarmExecutionContext | None = None,
) -> dict[str, Any]:
    context = context or SwarmExecutionContext.from_state(state)
    loop = control_report.get("execution_loop") if isinstance(control_report.get("execution_loop"), dict) else {}
    quorum = control_report.get("quorum_trace") if isinstance(control_report.get("quorum_trace"), dict) else {}
    recovery = control_report.get("recovery_traces") if isinstance(control_report.get("recovery_traces"), list) else []
    process_metrics = {
        "status": control_report.get("status"),
        "round_count": loop.get("round_count", 0),
        "accepted_signal_count": loop.get("accepted_signal_count", 0),
        "activated_agent_count": len(control_report.get("activated_agents") or []),
        "recovery_attempt_count": len(recovery),
        "recovery_failure_count": sum(1 for item in recovery if isinstance(item, dict) and item.get("status") == "recovery_failed"),
        "recovery_success_count": sum(1 for item in recovery if isinstance(item, dict) and item.get("status") == "recovery_succeeded"),
        "quorum_status": quorum.get("status"),
        "candidate_source": quorum.get("candidate_source"),
    }
    event = swarm_event(
        event_type="outcome_feedback.updated",
        run_id=context.run_id,
        tenant_id=context.tenant_id,
        actor="pheroos.outcome_feedback",
        summary="Updated process-only swarm outcome feedback.",
        payload={"process_metrics": process_metrics, "domain_conclusion_stored": False},
    )
    return {
        "schema_version": OUTCOME_FEEDBACK_SCHEMA_VERSION,
        "run_id": context.run_id,
        "tenant_id": context.tenant_id,
        "process_metrics": process_metrics,
        "domain_conclusion_stored": False,
        "stored_fields": sorted(process_metrics),
        "excluded_fields": [
            "final_answer",
            "final",
            "domain_conclusion",
            "domain_decision",
            "agent_decision",
            "committed_candidate",
            "committed_candidate_label",
            *legacy_outcome_feedback_excluded_fields(),
        ],
        "events": [event],
    }
