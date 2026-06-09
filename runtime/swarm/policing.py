from __future__ import annotations

from typing import Any

from runtime.output_contract import committed_candidate_conflict_violations, output_policy_from_state, raw_data_policy_violation
from runtime.swarm.action_policy import source_policy_blocks_tool
from runtime.swarm.candidate_registry import (
    fallbackish_candidate_text,
    legacy_fallbackish_candidate_allowed,
    normalized_candidate_label,
)
from runtime.swarm.legacy_output_phrases import legacy_fallback_candidate_conflict_present
from runtime.swarm.data_gate_permissions import publication_conclusion_permission_target
from runtime.swarm.legacy_data_gate_permissions import legacy_publication_action_conclusion_target
from runtime.swarm.target_registry import (
    canonical_target,
    target_kind,
)
from runtime.swarm.tool_policy_resolver import resolve_tool_policy
from runtime.swarm.stop_policy import stop_policy_rules, stop_signal_policy_from_state
from runtime.swarm.legacy_tool_policy import legacy_default_tool_policy_violation_target
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState
from runtime.writer_guardrails import declared_writer_actions, stop_policy_action_markers
from runtime.workflows.legacy_guardrails import (
    legacy_domain_workflow_policing_violations,
)


def build_policing_trace(state: dict[str, Any], diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "agent")
        status = str(item.get("status") or "")
        if status == "rejected":
            violations.append(
                {
                    "agent": agent,
                    "target": item.get("target") or "signal",
                    "type": item.get("type") or "signal",
                    "reason": item.get("reason") or "signal rejected by manifest or governance policy",
                    "penalty": "reliability_down",
                }
            )
        elif item.get("proposed_blocking"):
            warnings.append(
                {
                    "agent": agent,
                    "target": item.get("target") or "signal",
                    "type": item.get("type") or "stop_signal",
                    "reason": "blocking request accepted only as a contested proposal",
                }
            )
    violations.extend(writer_candidate_violations(state))
    violations.extend(tool_policy_violations(state))
    violations.extend(raw_data_leak_violations(state))
    violations.extend(domain_workflow_violations(state))
    return {
        "status": "violations_detected" if violations else "watch" if warnings else "clear",
        "violations": violations,
        "warnings": warnings,
    }


def policing_signals(state: dict[str, Any], trace: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    for item in trace.get("violations") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.POLICING,
                target=f"agent:{item.get('agent')}",
                content=str(item.get("reason") or "Agent violated signal governance policy."),
                strength=0.78,
                confidence=0.9,
                verification_state=VerificationState.VERIFIED,
                source_module="worker_policing",
                evidence_ref="agent_signal_diagnostics",
                metadata={"penalty": item.get("penalty"), "signal_type": item.get("type"), "target": item.get("target")},
            )
        )
        stop_signal = stop_signal_for_violation(run_id, tenant_id, item, state=state)
        if stop_signal is not None:
            signals.append(stop_signal)
    return signals


def stop_signal_for_violation(
    run_id: str,
    tenant_id: str,
    item: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
) -> PheromoneSignal | None:
    blocking_target = blocking_target_for_violation(item, state=state)
    if blocking_target is None:
        return None
    violation_type = str(item.get("type") or "")
    target = str(item.get("target") or "")
    return PheromoneSignal(
        run_id=run_id,
        tenant_id=tenant_id,
        type=SignalType.STOP_SIGNAL,
        target=blocking_target,
        content=str(item.get("reason") or "Protocol Police blocked unsafe runtime behavior."),
        strength=1.0,
        confidence=0.9,
        decay_rate=0.0,
        priority="hard",
        verification_state=VerificationState.BLOCKING,
        source_module="worker_policing",
        evidence_ref="policing_trace",
        blocking=True,
        metadata={"penalty": item.get("penalty"), "signal_type": violation_type, "violation_target": target},
    )


def blocking_target_for_violation(item: dict[str, Any], *, state: dict[str, Any] | None = None) -> str | None:
    violation_type = str(item.get("type") or "")
    target = str(item.get("target") or "")
    if violation_type == "tool_policy_violation":
        if target.startswith("tool:"):
            return target
        if target:
            return f"tool:{target}"
        return legacy_default_tool_policy_violation_target()
    if violation_type in {"writer_violation", "raw_data_leak"}:
        return explicit_output_target_for_violation(item) or publication_target_for_violation(state)
    if violation_type in {
        "domain_workflow_violation",
        "code_workflow_violation",
        "compliance_workflow_violation",
        "evidence_workflow_violation",
    }:
        return canonical_target(target)
    return None


def publication_target_for_violation(state: dict[str, Any] | None) -> str:
    gate = state.get("data_gate") if isinstance(state, dict) and isinstance(state.get("data_gate"), dict) else {}
    return publication_conclusion_permission_target(gate)


def explicit_output_target_for_violation(item: dict[str, Any]) -> str:
    for key in ("blocked_target", "policy_target", "output_target", "canonical_target", "target", "action"):
        target = output_target_from_value(item.get(key))
        if target:
            return target
    for key in ("policy_actions", "blocked_actions"):
        actions = item.get(key)
        if not isinstance(actions, list):
            continue
        for action in actions:
            target = output_target_from_value(action)
            if target:
                return target
    return ""


def output_target_from_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    canonical = canonical_target(text)
    kind = target_kind(canonical)
    if kind == "decision":
        return canonical
    if kind == "writer":
        return writer_action_output_target(canonical)
    return ""


def writer_action_output_target(action: str) -> str:
    tail = str(action or "").split(":", 1)[-1].replace("-", "_")
    compatibility_target = legacy_publication_action_conclusion_target(tail)
    if compatibility_target:
        return compatibility_target
    return canonical_target(f"decision:{tail}")


def writer_candidate_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    label = str(committed.get("label") or "")
    final = str(state.get("final") or state.get("draft_final") or "")
    policy = output_policy_from_state(state)
    policy_conflicts = policy.get("committed_candidate_conflicts") if isinstance(policy.get("committed_candidate_conflicts"), list) else []
    conflicts = committed_candidate_conflict_violations(final, state, policy=policy)
    if conflicts:
        return [
            {
                "agent": "writer",
                "target": "quorum:committed_candidate",
                "type": "writer_violation",
                "reason": f"writer output conflicts with committed candidate: {item.get('message')}",
                "penalty": "revision_required",
                "policy_code": item.get("code"),
            }
            for item in conflicts
        ]
    if policy_conflicts:
        return []
    if fallback_committed_candidate(committed, quorum) and legacy_fallback_candidate_conflict_present(final):
        return [
            {
                "agent": "writer",
                "target": "quorum:committed_candidate",
                "type": "writer_violation",
                "reason": f"writer output conflicts with fallback committed candidate: {label or committed.get('id') or 'fallback'}",
                "penalty": "revision_required",
            }
        ]
    return []


def fallback_committed_candidate(committed: dict[str, Any], quorum: dict[str, Any]) -> bool:
    if bool(committed.get("safe_fallback")):
        return True
    fallback = quorum.get("fallback_candidate") if isinstance(quorum.get("fallback_candidate"), dict) else {}
    if fallback and candidate_reference_keys(committed).intersection(candidate_reference_keys(fallback)):
        return True
    if not legacy_fallbackish_candidate_allowed(quorum):
        return False
    return fallbackish_candidate_text(f"{committed.get('id')} {committed.get('label')}")


def candidate_reference_keys(value: dict[str, Any]) -> set[str]:
    keys = set()
    for field in ("id", "candidate", "label", "target", "canonical_target"):
        normalized = normalized_candidate_label(value.get(field))
        if normalized:
            keys.add(normalized)
    return keys


def tool_policy_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for call in execution_log_tool_calls(state):
        name = str(call.get("name") or "")
        if not name:
            continue
        if source_policy_blocks_tool(state, f"tool:{name}"):
            violations.append(
                {
                    "agent": "tool_registry",
                    "target": f"tool:{name}",
                    "type": "tool_policy_violation",
                    "reason": "tool attempted while blocked by active source policy",
                    "penalty": "route_block",
                }
            )
            continue
        decision = resolve_tool_policy(tool_name=name, state=state)
        if decision.get("status") not in {"blocked", "denied"}:
            continue
        violations.append(
            {
                "agent": "tool_registry",
                "target": decision.get("canonical_tool") or f"tool:{name}",
                "type": "tool_policy_violation",
                "reason": f"tool policy decision: {decision.get('reason')}",
                "penalty": "route_block",
                "tool_policy_decision": decision,
            }
        )
    return violations


def execution_log_tool_calls(state: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for entry in state.get("execution_log") if isinstance(state.get("execution_log"), list) else []:
        for call in entry.get("tool_calls") if isinstance(entry, dict) and isinstance(entry.get("tool_calls"), list) else []:
            if isinstance(call, dict):
                calls.append(call)
    return calls


def raw_data_leak_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    final = str(state.get("final") or state.get("draft_final") or "")
    if not final:
        return []
    violation = raw_data_policy_violation(final, state)
    if violation is None:
        return []
    return [
        {
            "agent": "writer",
            "target": "artifact:final",
            "type": "raw_data_leak",
            "reason": f"writer appears to expose raw data markers: {', '.join(violation.get('matched_markers') or [])}",
            "penalty": "revision_required",
            "policy_code": violation.get("code"),
            "policy_source": violation.get("policy_source"),
            "matched_markers": violation.get("matched_markers") or [],
        }
    ]


def domain_workflow_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    declared = declared_domain_workflow_violations(state)
    if declared or capability_writer_stop_policy_declared(state):
        return declared
    workflow = domain_workflow(state)
    graph_mode = str(workflow.get("graph_mode") or "")
    return legacy_domain_workflow_violations(state, graph_mode=graph_mode)


def legacy_domain_workflow_violations(state: dict[str, Any], *, graph_mode: str) -> list[dict[str, Any]]:
    return legacy_domain_workflow_policing_violations(state, graph_mode=graph_mode)


def declared_domain_workflow_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    policy = stop_signal_policy_from_state(state)
    if not capability_writer_stop_policy_declared(state):
        return []
    workflow = domain_workflow(state)
    gate_status = workflow.get("gate_status") if isinstance(workflow.get("gate_status"), dict) else {}
    if not bool(gate_status.get("blocked")):
        return []
    final = str(state.get("final") or state.get("draft_final") or "")
    actions = set(declared_writer_actions(final, policy))
    if not actions and not stop_policy_action_markers(policy):
        return []
    violations: list[dict[str, Any]] = []
    for target in declared_gate_trigger_targets(policy, actions):
        violations.append(
            {
                "agent": "writer",
                "target": target,
                "type": "domain_workflow_violation",
                "reason": f"writer output conflicts with declared workflow gate action: {', '.join(sorted(actions))}",
                "penalty": "revision_required",
                "policy_actions": sorted(actions),
            }
        )
    return violations


def capability_writer_stop_policy_declared(state: dict[str, Any]) -> bool:
    policy = stop_signal_policy_from_state(state)
    return any(
        str(action or "").strip().lower().startswith("writer:")
        for rule in stop_policy_rules(policy)
        for action in rule.get("blocked_actions") or []
    )


def declared_gate_trigger_targets(policy: dict[str, Any], actions: set[str]) -> list[str]:
    targets: list[str] = []
    for rule in stop_policy_rules(policy):
        blocked_actions = {str(action) for action in rule.get("blocked_actions") or []}
        if not blocked_actions.intersection(actions):
            continue
        for target in rule.get("trigger_targets") or []:
            value = str(target or "").strip()
            if value and value not in targets:
                targets.append(value)
    return targets


def domain_workflow(state: dict[str, Any]) -> dict[str, Any]:
    workflow = state.get("domain_workflow") if isinstance(state.get("domain_workflow"), dict) else {}
    if workflow:
        return workflow
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    workflow = metadata.get("domain_workflow") if isinstance(metadata.get("domain_workflow"), dict) else {}
    return workflow
