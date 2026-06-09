from __future__ import annotations

import json
from typing import Any

from runtime.swarm.event_log import swarm_event
from runtime.swarm.contracts import signal_contract
from runtime.swarm.lifecycle import blocking_status_for_signal, lifecycle_state_for_signal
from runtime.swarm.target_pressure import compute_target_pressure_map
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.tool_policy_resolver import tool_policy_event_type


def governance_events_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive normalized governance events from a completed run payload."""

    run_id = str(run.get("run_id") or "")
    if not run_id:
        return []
    tenant_id = run_tenant_id(run)
    events: list[dict[str, Any]] = []
    events.extend(core_lifecycle_events(run, run_id=run_id, tenant_id=tenant_id))
    events.extend(capability_protocol_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_signal_lifecycle_events(run):
        events.extend(signal_lifecycle_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_target_pressure_events(run):
        events.extend(target_pressure_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_event_type(run, "candidate.created"):
        events.extend(candidate_created_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_event_type(run, "candidate.committed"):
        events.extend(candidate_commit_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_candidate_block_events(run):
        events.extend(candidate_block_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_agent_allocation_events(run):
        events.extend(agent_allocation_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_tool_events(run):
        events.extend(tool_call_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_permission_events(run):
        events.extend(permission_decision_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_recovery_timeline_events(run):
        events.extend(recovery_trace_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_artifact_quarantine_events(run):
        events.extend(artifact_quarantine_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_claim_timeline_events(run):
        events.extend(claim_lifecycle_events(run, run_id=run_id, tenant_id=tenant_id))
    events.extend(output_lifecycle_events(run, run_id=run_id, tenant_id=tenant_id))
    if not has_outcome_feedback_events(run):
        events.extend(outcome_feedback_events(run, run_id=run_id, tenant_id=tenant_id))
    return dedupe_events(events)


def explicit_runtime_events_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Return first-class runtime event records already emitted by the run."""

    explicit_events: list[dict[str, Any]] = []
    explicit_events.extend(event_items(run.get("swarm_protocol_trace")))
    control_loop = run.get("swarm_control_loop") if isinstance(run.get("swarm_control_loop"), dict) else {}
    explicit_events.extend(event_items(control_loop.get("events")))
    return dedupe_event_items(
        explicit_events,
        excluded_markers={event_marker(event) for event in event_items(run.get("pheromone_trace"))},
    )


def core_lifecycle_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    input_envelope = metadata.get("input_envelope") if isinstance(metadata.get("input_envelope"), dict) else {}
    task = run.get("task") or input_envelope.get("user_input_redacted") or input_envelope.get("user_input")
    if task and not has_event_type(run, "input.received"):
        events.append(
            swarm_event(
                event_type="input.received",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="ai_os.input_envelope",
                target="run",
                summary="Input was received by AI-as-OS.",
                payload={
                    "task_preview": str(task)[:1200],
                    "input_envelope": input_envelope,
                    "requested_output_format": input_envelope.get("requested_output_format"),
                    "risk_mode": input_envelope.get("risk_mode"),
                },
            )
        )
    os_plan = os_plan_from_run(run)
    if os_plan and not has_event_type(run, "os.plan.created"):
        events.append(
            swarm_event(
                event_type="os.plan.created",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="os_kernel",
                target="run",
                summary="OS plan was created.",
                payload={
                    "intent": os_plan.get("intent") or os_plan.get("task_type"),
                    "runtime_ready": os_plan.get("runtime_ready"),
                    "required_capabilities": os_plan.get("required_capabilities"),
                    "swarm_plan": os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {},
                    "os_routing_trace": os_plan.get("os_routing_trace") if isinstance(os_plan.get("os_routing_trace"), list) else [],
                },
            )
        )
    if runtime_materialized(run) and not has_event_type(run, "runtime.materialized"):
        events.append(
            swarm_event(
                event_type="runtime.materialized",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="runtime.materializer",
                target="run",
                summary="Runtime context was materialized.",
                payload={
                    "enabled_capabilities": metadata.get("enabled_capabilities"),
                    "permission_grants": metadata.get("permission_grants"),
                    "validation_issues": metadata.get("runtime_validation_issues"),
                    "capability_runtime": metadata.get("capability_runtime"),
                },
            )
        )
    return events


def capability_protocol_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    swarm_plan = swarm_plan_from_run(run)
    protocols = swarm_plan.get("capability_protocols") if isinstance(swarm_plan.get("capability_protocols"), list) else []
    events = []
    for protocol in protocols:
        if not isinstance(protocol, dict):
            continue
        capability_id = str(protocol.get("capability_id") or protocol.get("id") or "").strip()
        if not capability_id:
            continue
        events.append(
            swarm_event(
                event_type="capability.protocol.loaded",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="runtime.materializer",
                target=f"capability:{capability_id}",
                summary=f"Loaded protocol for {capability_id}.",
                payload={
                    "capability_id": capability_id,
                    "protocol": protocol,
                    "protocol_source": swarm_plan.get("protocol_source"),
                    "intent": swarm_plan.get("intent"),
                },
            )
        )
    return events


def signal_lifecycle_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    snapshot = run.get("pheromone_field_snapshot") if isinstance(run.get("pheromone_field_snapshot"), dict) else {}
    signals = snapshot.get("signals") if isinstance(snapshot.get("signals"), list) else []
    events: list[dict[str, Any]] = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        lifecycle = lifecycle_state_for_signal(signal).value
        blocking_status = blocking_status_for_signal(signal).value
        actor = signal.get("source_module") or signal.get("source_agent") or "pheromone_field"
        target = signal.get("target") or "run"
        payload = {
            "signal": signal,
            "signal_id": signal.get("id"),
            "signal_type": signal.get("type"),
            "lifecycle_state": lifecycle,
            "blocking_status": blocking_status,
            "contract": signal_contract(signal),
        }
        events.append(
            swarm_event(
                event_type="signal.created",
                run_id=run_id,
                tenant_id=tenant_id,
                actor=str(actor),
                target=target,
                lifecycle_state=lifecycle,
                summary=f"Signal {signal.get('id') or signal.get('type') or 'unknown'} was recorded.",
                payload=payload,
            )
        )
        lifecycle_event = signal_lifecycle_event_type(lifecycle, blocking_status)
        if lifecycle_event:
            events.append(
                swarm_event(
                    event_type=lifecycle_event,
                    run_id=run_id,
                    tenant_id=tenant_id,
                    actor=str(actor),
                    target=target,
                    lifecycle_state=lifecycle,
                    summary=f"Signal {signal.get('id') or signal.get('type') or 'unknown'} reached {lifecycle}.",
                    payload=payload,
                )
            )
    return events


def signal_lifecycle_event_type(lifecycle: str, blocking_status: str) -> str | None:
    if blocking_status == "blocking":
        return "signal.promoted_to_blocking"
    if lifecycle == "verified":
        return "signal.verified"
    if lifecycle in {"rejected", "rejected_by_gate"}:
        return "signal.rejected"
    if lifecycle in {"resolved", "accepted_patch"}:
        return "signal.resolved"
    return None


def target_pressure_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    pressure = target_pressure_report_from_run(run)
    events = []
    for item in target_pressure_items(pressure):
        target = canonical_target(item.get("canonical_target") or item.get("target"))
        pressure_value = min(1.0, max(0.0, safe_float(item.get("pressure"), 0.0)))
        events.append(
            swarm_event(
                event_type="target.pressure.updated",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="pheroos.target_pressure",
                target=target,
                summary=f"Target pressure for {target} is {round(pressure_value, 3)}.",
                payload={
                    "target_pressure": item,
                    "pressure": round(pressure_value, 3),
                    "reasons": item.get("reasons") if isinstance(item.get("reasons"), list) else [],
                    "threshold": pressure.get("threshold"),
                    "schema_version": pressure.get("schema_version"),
                    "source": pressure.get("source") or "target_pressure_report",
                },
            )
        )
    return events


def target_pressure_report_from_run(run: dict[str, Any]) -> dict[str, Any]:
    control_loop = run.get("swarm_control_loop") if isinstance(run.get("swarm_control_loop"), dict) else {}
    control_pressure = control_loop.get("target_pressure") if isinstance(control_loop.get("target_pressure"), dict) else {}
    if target_pressure_items(control_pressure):
        return {**control_pressure, "source": "generic_swarm_control_loop"}
    direct_pressure = run.get("target_pressure") if isinstance(run.get("target_pressure"), dict) else {}
    if target_pressure_items(direct_pressure):
        return {**direct_pressure, "source": "run_target_pressure"}
    computed = compute_target_pressure_map(run)
    return {**computed, "source": "derived_from_run_state"}


def target_pressure_items(pressure: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(pressure, dict):
        return []
    raw_targets = pressure.get("targets") if isinstance(pressure.get("targets"), list) else []
    if not raw_targets:
        by_target = pressure.get("by_target") if isinstance(pressure.get("by_target"), dict) else {}
        raw_targets = list(by_target.values())
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_targets:
        if not isinstance(item, dict):
            continue
        target = canonical_target(item.get("canonical_target") or item.get("target"))
        if not target or target in seen:
            continue
        seen.add(target)
        output.append({**item, "target": item.get("target") or target, "canonical_target": target})
    return sorted(output, key=lambda item: str(item.get("canonical_target") or item.get("target") or ""))


def candidate_created_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    for candidate in candidate_declarations_from_run(run):
        candidate_id = candidate.get("id") or candidate.get("candidate") or candidate.get("target") or candidate.get("label")
        if not candidate_id:
            continue
        events.append(
            swarm_event(
                event_type="candidate.created",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="candidate_registry",
                target=candidate_id,
                summary="Declared candidate was registered.",
                payload={"candidate": candidate, "candidate_id": candidate_id},
            )
        )
    return events


def candidate_commit_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    quorum = quorum_trace_from_run(run)
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    if not committed:
        return []
    return [
        swarm_event(
            event_type="candidate.committed",
            run_id=run_id,
            tenant_id=tenant_id,
            actor="quorum_marshal",
            target=committed.get("id") or committed.get("label") or "candidate",
            summary="Quorum committed a candidate.",
            payload={
                "candidate": committed,
                "candidate_source": quorum.get("candidate_source"),
                "quorum_status": quorum.get("status"),
                "quorum_trace": quorum,
            },
        )
    ]


def candidate_block_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    quorum = quorum_trace_from_run(run)
    events = []
    for candidate in quorum.get("candidates") or []:
        if not isinstance(candidate, dict) or not candidate.get("blocked"):
            continue
        events.append(
            swarm_event(
                event_type="candidate.blocked",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="quorum_marshal",
                target=candidate.get("id") or candidate.get("candidate") or candidate.get("label") or "candidate",
                summary="Quorum blocked a candidate.",
                payload={
                    "candidate": candidate,
                    "candidate_source": quorum.get("candidate_source"),
                    "quorum_status": quorum.get("status"),
                },
            )
        )
    return events


def outcome_feedback_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    feedback = outcome_feedback_from_run(run)
    if not feedback:
        return []
    return [
        swarm_event(
            event_type="outcome_feedback.updated",
            run_id=run_id,
            tenant_id=tenant_id,
            actor="pheroos.outcome_feedback",
            summary="Updated process-only swarm outcome feedback.",
            payload={
                "process_metrics": feedback.get("process_metrics") if isinstance(feedback.get("process_metrics"), dict) else {},
                "domain_conclusion_stored": bool(feedback.get("domain_conclusion_stored")),
                "stored_fields": feedback.get("stored_fields") if isinstance(feedback.get("stored_fields"), list) else [],
                "excluded_fields": feedback.get("excluded_fields") if isinstance(feedback.get("excluded_fields"), list) else [],
                "schema_version": feedback.get("schema_version"),
            },
        )
    ]


def agent_allocation_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    for allocation in agent_allocations_from_run(run):
        agent = str(allocation.get("agent") or allocation.get("agent_id") or allocation.get("key") or "").strip()
        if not agent:
            continue
        activated = allocation.get("activated")
        event_type = "agent.allocated" if activated is not False else "agent.suppressed"
        events.append(
            swarm_event(
                event_type=event_type,
                run_id=run_id,
                tenant_id=tenant_id,
                actor="pheroos.agent_allocator",
                target=f"agent:{agent}",
                summary=allocation.get("activation_reason")
                or allocation.get("reason")
                or ("Agent allocated." if event_type == "agent.allocated" else "Agent suppressed."),
                payload={"agent": agent, "allocation": allocation},
            )
        )
    return events


def tool_call_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    execution_log = run.get("execution_log") if isinstance(run.get("execution_log"), list) else []
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        step_id = step.get("step_id") or step.get("id")
        step_title = step.get("title")
        calls = step.get("tool_calls") if isinstance(step.get("tool_calls"), list) else []
        for call in calls:
            if not isinstance(call, dict):
                continue
            tool = str(call.get("name") or "unknown")
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            decision = result.get("tool_policy_decision") if isinstance(result.get("tool_policy_decision"), dict) else {}
            event_type = str(call.get("event_type") or "").strip()
            if not event_type and decision:
                event_type = tool_policy_event_type(decision)
            if not event_type:
                event_type = "tool.call.completed" if result.get("ok") is not False else "tool.call.failed"
            events.append(
                swarm_event(
                    event_type=event_type,
                    run_id=run_id,
                    tenant_id=tenant_id,
                    actor="tool_registry",
                    target=f"tool:{tool}",
                    summary=f"{tool} {event_type}.",
                    payload={
                        "step_id": step_id,
                        "step_title": step_title,
                        "tool": tool,
                        "args": call.get("args"),
                        "result": result,
                        "tool_policy_decision": decision,
                    },
                )
            )
    return events


def permission_decision_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    events = []
    for decision in permission_decisions(metadata.get("permission_grants")):
        capability_id = str(decision.get("capability_id") or "")
        for permission in decision.get("permission_grants") or []:
            events.append(
                swarm_event(
                    event_type="permission.granted",
                    run_id=run_id,
                    tenant_id=tenant_id,
                    actor="permission_policy",
                    target=str(permission),
                    summary=f"Granted {permission}.",
                    payload={"capability_id": capability_id, "permission": permission, "status": "granted"},
                )
            )
        for permission in decision.get("blocked_permissions") or []:
            events.append(
                swarm_event(
                    event_type="permission.pending_confirmation",
                    run_id=run_id,
                    tenant_id=tenant_id,
                    actor="permission_policy",
                    target=str(permission),
                    summary=f"{permission} requires confirmation.",
                    payload={
                        "capability_id": capability_id,
                        "permission": permission,
                        "status": "pending_confirmation",
                    },
                )
            )
    return events


def recovery_trace_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    for trace in recovery_traces_from_run(run):
        target = trace.get("target") or trace.get("canonical_target") or "run"
        trace_events = trace.get("trace") if isinstance(trace.get("trace"), list) else []
        for item in trace_events:
            if not isinstance(item, dict):
                continue
            event_type = str(item.get("event_type") or item.get("type") or "").strip()
            if not event_type.startswith("recovery."):
                continue
            events.append(
                swarm_event(
                    event_type=event_type,
                    run_id=run_id,
                    tenant_id=tenant_id,
                    actor=item.get("actor") or "recovery_engine",
                    target=item.get("target") or target,
                    summary=item.get("summary") or event_type,
                    payload={**item, "recovery_trace": trace},
                )
            )
    return events


def artifact_quarantine_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    for artifact in quarantined_artifacts_from_run(run):
        artifact_id = artifact.get("artifact_id") or artifact.get("id") or artifact.get("target") or "artifact"
        target = artifact.get("target") or f"artifact:{artifact_id}"
        events.append(
            swarm_event(
                event_type="artifact.quarantined",
                run_id=run_id,
                tenant_id=tenant_id,
                actor=str(artifact.get("source_module") or artifact.get("source") or "social_immunity"),
                target=target,
                lifecycle_state="blocking",
                summary=str(artifact.get("reason") or "Artifact quarantined by governance policy."),
                payload={"artifact": artifact},
            )
        )
    return events


def claim_lifecycle_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    for claim in receiver_claims_from_run(run):
        target = claim_target(claim)
        events.append(
            swarm_event(
                event_type="claim.created",
                run_id=run_id,
                tenant_id=tenant_id,
                actor=str(claim.get("agent") or "receiver_normalizer"),
                target=target,
                summary="Receiver normalized a claim.",
                payload={"claim": claim, "claim_id": claim.get("id") or claim.get("claim_id")},
            )
        )
    steward = evidence_steward_report_from_run(run)
    for claim in steward_claims(steward, "linked_claims"):
        events.append(
            swarm_event(
                event_type="claim.verified",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="evidence_steward",
                target=claim_target(claim),
                lifecycle_state="verified",
                summary="Evidence Steward linked a claim to evidence.",
                payload={
                    "claim": claim,
                    "claim_id": claim.get("claim_id") or claim.get("id"),
                    "support_status": claim.get("support_status") or "linked",
                },
            )
        )
    for claim in [*steward_claims(steward, "unsupported_claims"), *steward_claims(steward, "blocked_claims")]:
        status = str(claim.get("support_status") or ("blocked" if claim.get("blocked_target") else "unsupported"))
        events.append(
            swarm_event(
                event_type="claim.blocked",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="evidence_steward",
                target=canonical_target(claim.get("blocked_target") or claim_target(claim)),
                lifecycle_state="blocking" if status.startswith("blocked") else "verified",
                summary=f"Evidence Steward marked claim {status}.",
                payload={
                    "claim": claim,
                    "claim_id": claim.get("claim_id") or claim.get("id"),
                    "support_status": status,
                    "writer_constraints": steward.get("writer_constraints") if isinstance(steward.get("writer_constraints"), dict) else {},
                },
            )
        )
    return events


def output_lifecycle_events(run: dict[str, Any], *, run_id: str, tenant_id: str) -> list[dict[str, Any]]:
    events = []
    draft = str(run.get("draft_final") or "")
    final = str(run.get("final") or "")
    if draft and is_guardrail_report_text(draft) and not has_event_type(run, "writer.blocked"):
        events.append(
            swarm_event(
                event_type="writer.blocked",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="writer",
                target="artifact:draft_final",
                lifecycle_state="blocking",
                summary="Writer output was blocked by a governance guardrail report.",
                payload={"draft_preview": draft[:1200], "guardrail_report": guardrail_report_title(draft)},
            )
        )
    if final and is_guardrail_report_text(final) and final_judge_participated(run) and not has_event_type(run, "final_judge.rejected"):
        events.append(
            swarm_event(
                event_type="final_judge.rejected",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="final_judge",
                target="artifact:final",
                lifecycle_state="rejected",
                summary="Final Judge rejected output through a governance guardrail report.",
                payload={"final_preview": final[:1200], "guardrail_report": guardrail_report_title(final)},
            )
        )
    if final and output_publishable(run, final) and not has_event_type(run, "output.published"):
        events.append(
            swarm_event(
                event_type="output.published",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="final_judge" if final_judge_participated(run) else "writer",
                target="artifact:final",
                summary="Final output was published.",
                payload={"final_preview": final[:1200], "run_status": run.get("run_status") or run.get("status")},
            )
        )
    return events


def run_tenant_id(run: dict[str, Any]) -> str:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return str(metadata.get("tenant_id") or os_plan.get("tenant_id") or "default")


def swarm_plan_from_run(run: dict[str, Any]) -> dict[str, Any]:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    os_plan = run.get("os_plan") if isinstance(run.get("os_plan"), dict) else {}
    if not os_plan:
        os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan")
    return swarm_plan if isinstance(swarm_plan, dict) else {}


def os_plan_from_run(run: dict[str, Any]) -> dict[str, Any]:
    direct = run.get("os_plan") if isinstance(run.get("os_plan"), dict) else {}
    if direct:
        return direct
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    nested = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return nested


def runtime_materialized(run: dict[str, Any]) -> bool:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    return bool(
        metadata.get("_runtime_materialized")
        or metadata.get("capability_runtime")
        or metadata.get("capability_index")
        or metadata.get("enabled_capabilities")
    )


def quorum_trace_from_run(run: dict[str, Any]) -> dict[str, Any]:
    direct = run.get("quorum_trace") if isinstance(run.get("quorum_trace"), dict) else {}
    if direct:
        return direct
    control_loop = run.get("swarm_control_loop") if isinstance(run.get("swarm_control_loop"), dict) else {}
    quorum = control_loop.get("quorum_trace") if isinstance(control_loop.get("quorum_trace"), dict) else {}
    return quorum


def outcome_feedback_from_run(run: dict[str, Any]) -> dict[str, Any]:
    direct = run.get("outcome_feedback") if isinstance(run.get("outcome_feedback"), dict) else {}
    if direct:
        return direct
    control_loop = run.get("swarm_control_loop") if isinstance(run.get("swarm_control_loop"), dict) else {}
    feedback = control_loop.get("outcome_feedback") if isinstance(control_loop.get("outcome_feedback"), dict) else {}
    return feedback


def social_immunity_report_from_run(run: dict[str, Any]) -> dict[str, Any]:
    direct = run.get("social_immunity_report") if isinstance(run.get("social_immunity_report"), dict) else {}
    if direct:
        return direct
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    nested = metadata.get("social_immunity_report") if isinstance(metadata.get("social_immunity_report"), dict) else {}
    return nested


def input_preflight_report_from_run(run: dict[str, Any]) -> dict[str, Any]:
    direct = run.get("input_preflight") if isinstance(run.get("input_preflight"), dict) else {}
    if direct:
        return direct
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    nested = metadata.get("input_preflight") if isinstance(metadata.get("input_preflight"), dict) else {}
    return nested


def receiver_normalizer_report_from_run(run: dict[str, Any]) -> dict[str, Any]:
    direct = run.get("receiver_normalizer_report") if isinstance(run.get("receiver_normalizer_report"), dict) else {}
    if direct:
        return direct
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    nested = metadata.get("receiver_normalizer_report") if isinstance(metadata.get("receiver_normalizer_report"), dict) else {}
    return nested


def evidence_steward_report_from_run(run: dict[str, Any]) -> dict[str, Any]:
    direct = run.get("evidence_steward_report") if isinstance(run.get("evidence_steward_report"), dict) else {}
    if direct:
        return direct
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    nested = metadata.get("evidence_steward_report") if isinstance(metadata.get("evidence_steward_report"), dict) else {}
    return nested


def quarantined_artifacts_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    preflight = input_preflight_report_from_run(run)
    for item in preflight.get("quarantine_artifacts") or []:
        if isinstance(item, dict):
            artifacts.append({**item, "source_module": "input_preflight"})
    report = social_immunity_report_from_run(run)
    for item in report.get("contaminants") or []:
        if isinstance(item, dict):
            artifacts.append({**item, "source_module": "social_immunity"})
    return dedupe_dicts(artifacts)


def receiver_claims_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    report = receiver_normalizer_report_from_run(run)
    return [dict(item) for item in report.get("claims") or [] if isinstance(item, dict)]


def steward_claims(report: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [dict(item) for item in report.get(key) or [] if isinstance(item, dict)]


def claim_target(claim: dict[str, Any]) -> str:
    claim_id = str(claim.get("claim_id") or claim.get("id") or "").strip()
    if claim_id:
        return f"claim:{claim_id}" if not claim_id.startswith("claim:") else claim_id
    return "claim"


def candidate_declarations_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    swarm_plan = swarm_plan_from_run(run)
    output: list[dict[str, Any]] = []
    candidate_policy = swarm_plan.get("candidate_policy") if isinstance(swarm_plan.get("candidate_policy"), dict) else {}
    for item in candidate_policy.get("candidates") or []:
        if isinstance(item, dict):
            output.append({**item, "source": "candidate_policy"})
    quorum_policy = swarm_plan.get("quorum_policy") if isinstance(swarm_plan.get("quorum_policy"), dict) else {}
    for item in quorum_policy.get("candidates") or []:
        if isinstance(item, dict):
            output.append({**item, "source": "quorum_policy"})
    quorum = quorum_trace_from_run(run)
    for item in quorum.get("candidates") or []:
        if isinstance(item, dict):
            output.append({**item, "source": "quorum_trace"})
    for protocol in swarm_plan.get("capability_protocols") or []:
        if not isinstance(protocol, dict):
            continue
        capability_id = protocol.get("capability_id") or protocol.get("id")
        for item in protocol.get("candidates") or []:
            if isinstance(item, dict):
                output.append({**item, "source": "capability_protocol", "capability_id": capability_id})
    return dedupe_candidates(output)


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.get("id") or candidate.get("candidate") or candidate.get("target") or candidate.get("label") or "")
        if not key:
            continue
        normalized = key.strip().lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(candidate)
    return output


def final_judge_participated(run: dict[str, Any]) -> bool:
    metrics = run.get("agent_metrics") if isinstance(run.get("agent_metrics"), list) else []
    if any(isinstance(item, dict) and str(item.get("agent") or "") == "final_judge" for item in metrics):
        return True
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    metrics = metadata.get("agent_metrics") if isinstance(metadata.get("agent_metrics"), list) else []
    return any(isinstance(item, dict) and str(item.get("agent") or "") == "final_judge" for item in metrics)


def output_publishable(run: dict[str, Any], final: str) -> bool:
    if is_guardrail_report_text(final):
        return False
    status = str(run.get("run_status") or run.get("status") or "").strip().lower()
    if status in {"blocked", "failed", "error", "runtime_error"}:
        return False
    if run.get("preflight_blocked") is True:
        return False
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    if metadata.get("preflight_blocked") is True:
        return False
    return bool(final.strip())


def is_guardrail_report_text(text: str) -> bool:
    preview = str(text or "").lstrip()[:160]
    return preview.startswith("# ") and "Guardrail Report" in preview


def guardrail_report_title(text: str) -> str:
    for line in str(text or "").splitlines():
        line = line.strip()
        if line:
            return line[:160]
    return "Guardrail Report"


def agent_allocations_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    allocations = run.get("agent_allocation_trace") if isinstance(run.get("agent_allocation_trace"), list) else []
    if allocations:
        return [item for item in allocations if isinstance(item, dict)]
    swarm_plan = swarm_plan_from_run(run)
    plan_allocations = swarm_plan.get("agent_allocation") if isinstance(swarm_plan.get("agent_allocation"), list) else []
    return [item for item in plan_allocations if isinstance(item, dict)]


def permission_decisions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def has_recovery_timeline_events(run: dict[str, Any]) -> bool:
    return has_event_prefix(run, "recovery.")


def has_signal_lifecycle_events(run: dict[str, Any]) -> bool:
    return has_event_prefix(run, "signal.")


def has_target_pressure_events(run: dict[str, Any]) -> bool:
    return has_event_type(run, "target.pressure.updated")


def has_candidate_block_events(run: dict[str, Any]) -> bool:
    return has_event_type(run, "candidate.blocked")


def has_agent_allocation_events(run: dict[str, Any]) -> bool:
    return has_event_type(run, "agent.allocated") or has_event_type(run, "agent.suppressed")


def has_tool_events(run: dict[str, Any]) -> bool:
    return has_event_prefix(run, "tool.")


def has_permission_events(run: dict[str, Any]) -> bool:
    return has_event_prefix(run, "permission.")


def has_outcome_feedback_events(run: dict[str, Any]) -> bool:
    return has_event_type(run, "outcome_feedback.updated")


def has_artifact_quarantine_events(run: dict[str, Any]) -> bool:
    return has_event_type(run, "artifact.quarantined")


def has_claim_timeline_events(run: dict[str, Any]) -> bool:
    return has_event_prefix(run, "claim.")


def has_event_type(run: dict[str, Any], event_type: str) -> bool:
    return any(event_type_for(item) == str(event_type) for item in existing_event_items_from_run(run))


def has_event_prefix(run: dict[str, Any], prefix: str) -> bool:
    return any(event_type_for(item).startswith(prefix) for item in existing_event_items_from_run(run))


def existing_event_items_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [*event_items(run.get("pheromone_trace")), *explicit_runtime_events_from_run(run)]


def event_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict) and event_type_for(item)]


def event_type_for(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or event.get("type") or event.get("event") or "").strip()


def recovery_traces_from_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    direct = run.get("recovery_trace")
    if isinstance(direct, dict):
        traces.append(direct)
    elif isinstance(direct, list):
        traces.extend(item for item in direct if isinstance(item, dict))
    traces.extend(item for item in run.get("recovery_traces") or [] if isinstance(item, dict))
    domain_workflow = run.get("domain_workflow") if isinstance(run.get("domain_workflow"), dict) else {}
    node_outputs = domain_workflow.get("node_outputs") if isinstance(domain_workflow.get("node_outputs"), dict) else {}
    for node_output in node_outputs.values():
        if not isinstance(node_output, dict):
            continue
        nested = node_output.get("recovery_trace")
        if isinstance(nested, dict):
            traces.append(nested)
    return dedupe_dicts(traces)


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return dedupe_event_items(events)


def dedupe_event_items(
    events: list[dict[str, Any]],
    *,
    excluded_markers: set[tuple[str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    output = []
    seen = set()
    if excluded_markers:
        seen.update(excluded_markers)
    for event in events:
        marker = event_marker(event)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(event)
    return output


def event_marker(event: dict[str, Any]) -> tuple[str, str, str]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if not payload:
        known = {
            "schema_version",
            "event_id",
            "run_id",
            "tenant_id",
            "timestamp",
            "event_type",
            "type",
            "event",
            "actor",
            "source_module",
            "source_agent",
            "target",
            "canonical_target",
            "lifecycle_state",
            "summary",
            "redaction_status",
        }
        payload = {key: value for key, value in event.items() if key not in known}
    return (
        event_type_for(event),
        canonical_target(event.get("canonical_target") or event.get("target")),
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
    )


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for item in items:
        marker = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output
