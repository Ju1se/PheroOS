from __future__ import annotations

from collections import Counter
from typing import Any

from runtime.redaction import redact_sensitive
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.target_registry import canonical_target


def build_governance_snapshot(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize governance state from normalized timeline records."""

    event_type_counts = Counter(str(record.get("type") or record.get("event_type") or "") for record in records)
    committed_candidates: list[dict[str, Any]] = []
    registered_candidates: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []
    allocated_agents: list[dict[str, Any]] = []
    suppressed_agents: list[dict[str, Any]] = []
    capability_protocols: list[dict[str, Any]] = []
    tool_decisions: list[dict[str, Any]] = []
    permission_decisions: list[dict[str, Any]] = []
    recovery_events: list[dict[str, Any]] = []
    target_pressure_updates: list[dict[str, Any]] = []
    quarantined_artifacts: list[dict[str, Any]] = []
    created_claims: list[dict[str, Any]] = []
    verified_claims: list[dict[str, Any]] = []
    blocked_claims: list[dict[str, Any]] = []
    writer_blocks: list[dict[str, Any]] = []
    final_judge_rejections: list[dict[str, Any]] = []
    published_outputs: list[dict[str, Any]] = []
    outcome_feedback_updates: list[dict[str, Any]] = []
    input_events: list[dict[str, Any]] = []
    os_plan_events: list[dict[str, Any]] = []
    runtime_materializations: list[dict[str, Any]] = []
    blocking_targets: set[str] = set()

    for record in records:
        event_type = str(record.get("type") or record.get("event_type") or "")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if is_active_blocker(payload) or record.get("lifecycle_state") == "blocking":
            blocking_targets.add(canonical_target(record.get("canonical_target") or record.get("target")))
        if event_type == "input.received":
            input_events.append(
                {
                    "task_preview": payload.get("task_preview"),
                    "requested_output_format": payload.get("requested_output_format"),
                    "risk_mode": payload.get("risk_mode"),
                }
            )
        elif event_type == "os.plan.created":
            os_plan_events.append(
                {
                    "intent": payload.get("intent"),
                    "runtime_ready": payload.get("runtime_ready"),
                    "required_capabilities": payload.get("required_capabilities"),
                }
            )
        elif event_type == "runtime.materialized":
            runtime_materializations.append(
                {
                    "enabled_capabilities": payload.get("enabled_capabilities"),
                    "permission_grants": payload.get("permission_grants"),
                    "validation_issues": payload.get("validation_issues"),
                }
            )
        elif event_type == "candidate.created":
            candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
            if candidate:
                registered_candidates.append(candidate)
        elif event_type == "candidate.committed":
            candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
            if candidate:
                committed_candidates.append(candidate)
        elif event_type == "candidate.blocked":
            candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
            if candidate:
                blocked_candidates.append(candidate)
        elif event_type == "agent.allocated":
            agent = event_agent(payload)
            if agent:
                allocated_agents.append({"agent": agent, "allocation": payload.get("allocation", {})})
        elif event_type == "agent.suppressed":
            agent = event_agent(payload)
            if agent:
                suppressed_agents.append({"agent": agent, "allocation": payload.get("allocation", {})})
        elif event_type == "capability.protocol.loaded":
            protocol = payload.get("protocol") if isinstance(payload.get("protocol"), dict) else {}
            capability_protocols.append(
                {
                    "capability_id": payload.get("capability_id") or protocol.get("capability_id"),
                    "protocol_source": payload.get("protocol_source"),
                    "intent": payload.get("intent"),
                    "protocol": protocol,
                }
            )
        elif event_type.startswith("tool."):
            tool_decisions.append({"event_type": event_type, "tool": payload.get("tool"), "decision": payload.get("tool_policy_decision", {})})
        elif event_type.startswith("permission."):
            permission_decisions.append(
                {
                    "event_type": event_type,
                    "permission": payload.get("permission"),
                    "capability_id": payload.get("capability_id"),
                    "status": payload.get("status"),
                }
            )
        elif event_type.startswith("recovery."):
            recovery_events.append({"event_type": event_type, "target": record.get("canonical_target") or record.get("target"), "payload": payload})
        elif event_type == "target.pressure.updated":
            target_pressure_updates.append(
                {
                    "target": record.get("canonical_target") or record.get("target"),
                    "pressure": payload.get("pressure"),
                    "reasons": payload.get("reasons", []),
                    "threshold": payload.get("threshold"),
                    "source": payload.get("source"),
                }
            )
        elif event_type == "artifact.quarantined":
            artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
            if artifact:
                quarantined_artifacts.append(artifact)
        elif event_type == "claim.created":
            claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else {}
            if claim:
                created_claims.append(claim)
        elif event_type == "claim.verified":
            claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else {}
            if claim:
                verified_claims.append(claim)
        elif event_type == "claim.blocked":
            claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else {}
            if claim:
                blocked_claims.append(claim)
        elif event_type == "writer.blocked":
            writer_blocks.append(
                {
                    "target": record.get("canonical_target") or record.get("target"),
                    "guardrail_report": payload.get("guardrail_report"),
                    "draft_preview": payload.get("draft_preview"),
                }
            )
        elif event_type == "final_judge.rejected":
            final_judge_rejections.append(
                {
                    "target": record.get("canonical_target") or record.get("target"),
                    "guardrail_report": payload.get("guardrail_report"),
                    "final_preview": payload.get("final_preview"),
                }
            )
        elif event_type == "output.published":
            published_outputs.append(
                {
                    "target": record.get("canonical_target") or record.get("target"),
                    "final_preview": payload.get("final_preview"),
                    "run_status": payload.get("run_status"),
                }
            )
        elif event_type == "outcome_feedback.updated":
            outcome_feedback_updates.append(
                {
                    "process_metrics": payload.get("process_metrics", {}),
                    "domain_conclusion_stored": payload.get("domain_conclusion_stored"),
                    "stored_fields": payload.get("stored_fields", []),
                    "excluded_fields": payload.get("excluded_fields", []),
                }
            )

    snapshot = {
        "event_count": len(records),
        "event_type_counts": dict(sorted((key, value) for key, value in event_type_counts.items() if key)),
        "blocking_targets": sorted(blocking_targets),
        "input_events": dedupe_dicts(input_events),
        "os_plan_events": dedupe_dicts(os_plan_events),
        "runtime_materializations": dedupe_dicts(runtime_materializations),
        "registered_candidates": dedupe_dicts(registered_candidates),
        "committed_candidates": dedupe_dicts(committed_candidates),
        "blocked_candidates": dedupe_dicts(blocked_candidates),
        "allocated_agents": dedupe_dicts(allocated_agents),
        "suppressed_agents": dedupe_dicts(suppressed_agents),
        "capability_protocols": dedupe_dicts(capability_protocols),
        "tool_decisions": dedupe_dicts(tool_decisions),
        "permission_decisions": dedupe_dicts(permission_decisions),
        "recovery_events": dedupe_dicts(recovery_events),
        "target_pressure_updates": dedupe_dicts(target_pressure_updates),
        "quarantined_artifacts": dedupe_dicts(quarantined_artifacts),
        "created_claims": dedupe_dicts(created_claims),
        "verified_claims": dedupe_dicts(verified_claims),
        "blocked_claims": dedupe_dicts(blocked_claims),
        "writer_blocks": dedupe_dicts(writer_blocks),
        "final_judge_rejections": dedupe_dicts(final_judge_rejections),
        "published_outputs": dedupe_dicts(published_outputs),
        "outcome_feedback_updates": dedupe_dicts(outcome_feedback_updates),
    }
    safe = redact_sensitive(snapshot)
    return safe if isinstance(safe, dict) else snapshot


def event_agent(payload: dict[str, Any]) -> Any:
    if payload.get("agent"):
        return payload.get("agent")
    allocation = payload.get("allocation") if isinstance(payload.get("allocation"), dict) else {}
    return allocation.get("agent") or allocation.get("agent_id") or allocation.get("key")


def dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for item in items:
        marker = repr(sorted(item.items()))
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output
