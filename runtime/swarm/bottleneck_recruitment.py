from __future__ import annotations

from typing import Any

from runtime.agent_registry import AgentRegistry
from runtime.swarm.agent_outputs import runtime_agent_outputs
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_bottleneck_report(state: dict[str, Any]) -> dict[str, Any]:
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    agent_outputs = runtime_agent_outputs(state)
    evidence_gaps = data_gate.get("evidence_gaps") if isinstance(data_gate.get("evidence_gaps"), list) else []
    decision_blockers = data_gate.get("decision_blockers") if isinstance(data_gate.get("decision_blockers"), list) else []
    missing_data = agent_missing_data_count(agent_outputs)
    metric_count = len(registry.get("metrics") or []) if isinstance(registry.get("metrics"), list) else 0
    pending_evidence = len(evidence_gaps) + len(decision_blockers) + missing_data
    verification_capacity = metric_count + len(data_gate.get("coverage_flags") or [])
    bottlenecks: list[dict[str, Any]] = []
    if pending_evidence:
        strength = min(1.0, 0.35 + (pending_evidence / max(pending_evidence + verification_capacity, 1)))
        agents = agent_specs_from_state(state)
        recruit, recruitment_source = recruit_agents_for_bottleneck(
            state,
            target="handoff:evidence_verification",
            agents=agents,
        )
        bottlenecks.append(
            {
                "target": "handoff:evidence_verification",
                "strength": round(strength, 3),
                "pending_evidence": pending_evidence,
                "verified_evidence": verification_capacity,
                "recruit": recruit,
                "recruitment_source": recruitment_source,
                "throttle": throttled_agents_for_bottleneck(state, agents=agents),
                "reason": "Evidence production or data gaps exceed verified metric capacity.",
            }
        )
    return {
        "status": "bottleneck_detected" if bottlenecks else "clear",
        "pending_evidence": pending_evidence,
        "verified_evidence": verification_capacity,
        "bottlenecks": bottlenecks,
    }


def bottleneck_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    for item in report.get("bottlenecks") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.BOTTLENECK,
                target=str(item.get("target") or "handoff"),
                content=str(item.get("reason") or "Swarm handoff bottleneck detected."),
                strength=float(item.get("strength") or 0.5),
                confidence=0.8,
                verification_state=VerificationState.VERIFIED,
                source_module="bottleneck_recruitment",
                evidence_ref="data_gate/metric_registry/agent_missing_data",
                metadata={
                    "pending_evidence": item.get("pending_evidence"),
                    "verified_evidence": item.get("verified_evidence"),
                    "recruit": item.get("recruit", []),
                    "recruitment_source": item.get("recruitment_source"),
                    "throttle": item.get("throttle", []),
                },
            )
        )
    return signals


def agent_missing_data_count(outputs: dict[str, Any]) -> int:
    total = 0
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        missing = output.get("missing_data")
        if isinstance(missing, list):
            total += len(missing)
        elif missing:
            total += 1
    return total


def recruit_agents_for_bottleneck(
    state: dict[str, Any],
    *,
    target: str,
    agents: list[dict[str, Any]] | None = None,
) -> tuple[list[str], str]:
    agents = agents if agents is not None else agent_specs_from_state(state)
    if not agents:
        return [], "missing_agent_registry"
    policy = agent_selection_policy_from_state(state)
    selected = []
    for agent in agents:
        score = bottleneck_agent_score(agent, policy=policy, target=target)
        if score <= 0:
            continue
        selected.append((score, str(agent.get("key") or agent.get("agent") or "")))
    selected = [(score, agent) for score, agent in selected if agent]
    if not selected:
        if policy_has_selection_terms(policy):
            return [], "agent_selection_policy_no_match"
        fallback = [
            str(agent.get("key") or agent.get("agent") or "")
            for agent in agents
            if str(agent.get("key") or agent.get("agent") or "").strip()
        ][:3]
        return fallback, "agent_registry_fallback" if fallback else "missing_agent_registry"
    selected.sort(key=lambda item: (-item[0], item[1]))
    source = "agent_selection_policy" if policy_has_selection_terms(policy) else "agent_registry_scored"
    return [agent for _score, agent in selected[:4]], source


def throttled_agents_for_bottleneck(state: dict[str, Any], *, agents: list[dict[str, Any]]) -> list[str]:
    policy = agent_selection_policy_from_state(state)
    forbidden = policy_exact_terms(policy.get("forbidden_roles"))
    if not forbidden:
        return []
    throttled = []
    for agent in agents:
        agent_id = str(agent.get("key") or agent.get("agent") or "").strip()
        if agent_id and agent_terms(agent) & forbidden:
            throttled.append(agent_id)
    return throttled


def policy_has_selection_terms(policy: dict[str, Any]) -> bool:
    return bool(
        policy_exact_terms(policy.get("required_roles"))
        or policy_exact_terms(policy.get("optional_roles"))
        or policy_exact_terms(policy.get("forbidden_roles"))
        or (policy.get("target_affinity_weights") if isinstance(policy.get("target_affinity_weights"), dict) else {})
    )


def bottleneck_agent_score(agent: dict[str, Any], *, policy: dict[str, Any], target: str) -> float:
    terms = agent_terms(agent)
    forbidden = policy_exact_terms(policy.get("forbidden_roles"))
    if forbidden and terms & forbidden:
        return 0.0
    required = policy_exact_terms(policy.get("required_roles"))
    if required and not terms & required:
        return 0.0
    optional = policy_exact_terms(policy.get("optional_roles"))
    score = 0.0
    if required and terms & required:
        score += 0.65
    if optional and terms & optional:
        score += 0.45
    evidence_terms = {"evidence", "audit", "auditor", "verifier", "verification", "quality", "data", "risk"}
    if terms & evidence_terms:
        score += 0.3
    target_weights = policy.get("target_affinity_weights") if isinstance(policy.get("target_affinity_weights"), dict) else {}
    target_weight = target_weights.get(canonical_target(target)) or target_weights.get(target)
    if target_weight:
        score += float(target_weight)
    return score


def agent_specs_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    registry = metadata.get("agent_registry") if isinstance(metadata.get("agent_registry"), dict) else {}
    agents = registry.get("agents") if isinstance(registry.get("agents"), list) else []
    if agents:
        return [agent for agent in agents if isinstance(agent, dict)]
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    allocations = swarm_plan.get("agent_allocation") if isinstance(swarm_plan.get("agent_allocation"), list) else []
    agents = [
        {
            "key": item.get("agent"),
            "name": item.get("name"),
            "agent_type": item.get("agent_type"),
            "committee_role": item.get("committee_role"),
            "tags": item.get("tags") or [],
            "focus": item.get("focus") or item.get("activation_reason"),
        }
        for item in allocations
        if isinstance(item, dict)
    ]
    if agents:
        return agents
    enabled_ids = enabled_capability_ids_from_metadata(metadata)
    if not enabled_ids:
        return []
    return [
        agent
        for agent in AgentRegistry().catalog(enabled_capability_ids=enabled_ids).get("agents", [])
        if isinstance(agent, dict)
    ]


def enabled_capability_ids_from_metadata(metadata: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for item in metadata.get("enabled_capabilities") if isinstance(metadata.get("enabled_capabilities"), list) else []:
        if isinstance(item, dict):
            text = str(item.get("id") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            ids.add(text)
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    for item in os_plan.get("auto_enabled") if isinstance(os_plan.get("auto_enabled"), list) else []:
        text = str(item or "").strip()
        if text:
            ids.add(text)
    return ids


def agent_selection_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("agent_selection_policy") if isinstance(swarm_plan.get("agent_selection_policy"), dict) else {}
    return policy


def agent_terms(agent: dict[str, Any]) -> set[str]:
    values = [
        agent.get("key"),
        agent.get("agent"),
        agent.get("name"),
        agent.get("agent_type"),
        agent.get("committee_role"),
        agent.get("description"),
    ]
    values.extend(agent.get("tags") if isinstance(agent.get("tags"), list) else [])
    values.extend(agent.get("focus") if isinstance(agent.get("focus"), list) else [agent.get("focus")])
    values.extend(agent.get("required_capabilities") if isinstance(agent.get("required_capabilities"), list) else [])
    return policy_terms(values)


def policy_terms(value: Any) -> set[str]:
    values = value if isinstance(value, list) else [value]
    output = set()
    for item in values:
        text = str(item or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
        output.update(part for part in text.replace("-", "_").replace("/", "_").split("_") if part)
    return output


def policy_exact_terms(value: Any) -> set[str]:
    values = value if isinstance(value, list) else [value]
    output = set()
    for item in values:
        text = str(item or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
    return output
