from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from runtime.connection_control import DEFAULT_TENANT_ID
from runtime.audit_log import read_run_audit_record
from runtime.redaction import redact_sensitive
from runtime.swarm.trace_store import SwarmTraceStore


router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}/trace")
def get_run_trace(run_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    """Return a dashboard-safe, first-class research trace for one run."""

    store = SwarmTraceStore()
    audit_record = read_run_audit_record(run_id, tenant_id=tenant_id)
    timeline = store.timeline(run_id=run_id, tenant_id=tenant_id)
    pheromone_snapshot = store.reconstruct_pheromone_snapshot(run_id=run_id, tenant_id=tenant_id)
    evidence_graph = store.evidence_graph(run_id=run_id, tenant_id=tenant_id)
    agent_allocation = store.agent_allocation(run_id=run_id, tenant_id=tenant_id)
    tool_events = store.tool_events(run_id=run_id, tenant_id=tenant_id)
    permission_events = store.permission_events(run_id=run_id, tenant_id=tenant_id)
    why_committed = store.why_committed(run_id=run_id, tenant_id=tenant_id)

    found = bool(
        audit_record
        or timeline
        or pheromone_snapshot.get("signal_count")
        or evidence_graph.get("nodes")
        or evidence_graph.get("edges")
        or agent_allocation.get("data")
        or tool_events.get("data")
        or permission_events.get("data")
        or why_committed.get("status") == "found"
    )
    if not found:
        raise HTTPException(status_code=404, detail="run trace not found")

    payload = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "audit_record": audit_record or {},
        "summary": build_trace_summary(audit_record or {}, why_committed, pheromone_snapshot),
        "trace": {
            "timeline": timeline,
            "pheromone_snapshot": pheromone_snapshot,
            "why_committed": why_committed,
            "evidence_graph": evidence_graph,
            "agent_allocation": agent_allocation,
            "tool_events": tool_events,
            "permission_events": permission_events,
        },
        "redaction_status": "redacted",
    }
    safe = redact_sensitive(payload, max_string_length=2_000)
    return safe if isinstance(safe, dict) else {"run_id": run_id, "redaction_status": "redacted"}


def build_trace_summary(
    audit_record: dict[str, Any],
    why_committed: dict[str, Any],
    pheromone_snapshot: dict[str, Any],
) -> dict[str, Any]:
    os_plan = audit_record.get("os_plan") if isinstance(audit_record.get("os_plan"), dict) else {}
    swarm = audit_record.get("swarm_governance") if isinstance(audit_record.get("swarm_governance"), dict) else {}
    quorum = why_committed.get("quorum_trace") if isinstance(why_committed.get("quorum_trace"), dict) else {}
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    return {
        "status": audit_record.get("status") or "trace_only",
        "task": audit_record.get("task"),
        "route": audit_record.get("route"),
        "runtime_ready": os_plan.get("runtime_ready"),
        "enabled_capabilities": audit_record.get("enabled_capabilities", []),
        "selected_skills": audit_record.get("selected_skills", []),
        "agent_metrics": audit_record.get("agent_metrics", []),
        "data_gate": audit_record.get("data_gate", {}),
        "review": audit_record.get("review", {}),
        "final_preview": audit_record.get("final_preview"),
        "committed_candidate": committed.get("label") or swarm.get("committed_candidate"),
        "quorum_status": quorum.get("status") or swarm.get("quorum_status"),
        "blocking_targets": pheromone_snapshot.get("blocking_targets") or swarm.get("blocking_targets", []),
        "signal_count": pheromone_snapshot.get("signal_count") or swarm.get("signal_count"),
    }
