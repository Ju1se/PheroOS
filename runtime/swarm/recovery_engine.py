from __future__ import annotations

import re
from typing import Any

from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.resolution import apply_stop_signal_resolution
from runtime.swarm.target_registry import canonical_target


def build_recovery_trace(
    state: dict[str, Any],
    *,
    target: str | None = None,
    context: dict[str, Any] | None = None,
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    target = canonical_target(target or inferred_recovery_target(state, context))
    protocols = matching_recovery_protocols(state, target=target)
    target_pressure = recovery_target_pressure(state, target=target, context=context)
    trace: list[dict[str, Any]] = [
        {
            "event_type": "recovery.target_pressure_computed",
            "target": target,
            "target_pressure": target_pressure,
        }
    ]

    if not protocols:
        return {
            "schema_version": "pheroos.recovery_trace.v1",
            "status": "no_recovery_protocol",
            "target": target,
            "target_pressure": target_pressure,
            "selected_protocol": None,
            "selected_agents": [],
            "fallback_candidate": None,
            "trace": [
                *trace,
                {
                    "event_type": "recovery.no_protocol",
                    "target": target,
                    "reason": "no capability-declared recovery protocol matched target",
                },
            ],
        }

    protocol = protocols[0]
    selected_protocol = selected_recovery_protocol_summary(state, protocol=protocol, target=target)
    selected_agents = select_recovery_agents(state, protocol=protocol, target=target)
    tool_results = execute_recovery_tools(protocol, tool_registry=tool_registry, context=context)
    recovery_context = recovery_context_with_tool_results(context, tool_results)
    success = recovery_success(protocol, state=state, context=recovery_context)
    status = "recovery_succeeded" if success else "recovery_failed"
    fallback = None if success else protocol.get("recovery_failure_candidate")
    tool_trace = recovery_tool_trace(protocol=protocol, tool_registry=tool_registry, tool_results=tool_results)
    return {
        "schema_version": "pheroos.recovery_trace.v1",
        "status": status,
        "target": target,
        "target_pressure": target_pressure,
        "selected_protocol": selected_protocol,
        "selected_agents": selected_agents,
        "tool_results": tool_results,
        "fallback_candidate": fallback,
        "trace": [
            *trace,
            {
                "event_type": "recovery.protocol_selected",
                "protocol_id": selected_protocol.get("id"),
                "capability_id": selected_protocol.get("capability_id"),
                "source": selected_protocol.get("source"),
                "protocol_source": selected_protocol.get("protocol_source"),
                "target": target,
            },
            {
                "event_type": "recovery.agents_selected",
                "protocol_id": selected_protocol.get("id"),
                "capability_id": selected_protocol.get("capability_id"),
                "source": selected_protocol.get("source"),
                "protocol_source": selected_protocol.get("protocol_source"),
                "agents": [agent["agent"] for agent in selected_agents],
                "selected_agents": selected_agents,
                "selection_basis": "protocol_roles_tags_target_affinity_trust_maturity",
            },
            *tool_trace,
            {
                "event_type": "recovery.succeeded" if success else "recovery.failed",
                "protocol_id": selected_protocol.get("id"),
                "capability_id": selected_protocol.get("capability_id"),
                "source": selected_protocol.get("source"),
                "protocol_source": selected_protocol.get("protocol_source"),
                "fallback_candidate": fallback,
            },
        ],
    }


def selected_recovery_protocol_summary(
    state: dict[str, Any],
    *,
    protocol: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    lineage = recovery_protocol_lineage(state, protocol=protocol, target=target)
    capability_id = lineage.get("capability_id") or protocol.get("capability_id")
    return {
        "id": recovery_protocol_id(protocol) or lineage.get("protocol_id"),
        "capability_id": capability_id,
        "source": lineage.get("source") or ("capability_protocol" if capability_id else "swarm_plan_recovery_protocol"),
        "protocol_source": lineage.get("protocol_source"),
        "max_rounds": protocol.get("max_rounds"),
        "required_tools": list(protocol.get("required_tools") or []),
        "allowed_agent_roles": list(protocol.get("allowed_agent_roles") or []),
        "allowed_capability_tags": list(protocol.get("allowed_capability_tags") or []),
        "trust_requirements": dict(protocol.get("trust_requirements") or {}),
        "maturity_requirements": dict(protocol.get("maturity_requirements") or {}),
    }


def recovery_protocol_lineage(
    state: dict[str, Any],
    *,
    protocol: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    protocol_id = recovery_protocol_id(protocol)
    protocol_source = swarm_plan.get("protocol_source")
    capability_id = str(protocol.get("capability_id") or "").strip()
    for capability_protocol in swarm_plan.get("capability_protocols") or []:
        if not isinstance(capability_protocol, dict):
            continue
        for candidate in capability_protocol.get("recovery_protocols") or []:
            if not isinstance(candidate, dict):
                continue
            if not recovery_protocol_ref_matches(candidate, protocol, target):
                continue
            declared_capability_id = str(
                capability_protocol.get("capability_id") or capability_protocol.get("id") or ""
            ).strip()
            return {
                "source": "capability_protocol",
                "protocol_source": protocol_source,
                "capability_id": capability_id or declared_capability_id or None,
                "protocol_id": protocol_id or recovery_protocol_id(candidate),
            }
    return {
        "source": "capability_protocol" if capability_id else "swarm_plan_recovery_protocol",
        "protocol_source": protocol_source,
        "capability_id": capability_id or None,
        "protocol_id": protocol_id,
    }


def recovery_protocol_ref_matches(left: dict[str, Any], right: dict[str, Any], target: str) -> bool:
    left_id = recovery_protocol_id(left)
    right_id = recovery_protocol_id(right)
    if left_id and right_id:
        return left_id == right_id
    left_targets = protocol_targets(left)
    right_targets = protocol_targets(right)
    canonical = canonical_target(target)
    return bool(left_targets and right_targets and canonical in left_targets and canonical in right_targets)


def recovery_protocol_id(protocol: dict[str, Any]) -> str:
    return str(protocol.get("id") or protocol.get("recovery_id") or "").strip()


def execute_recovery_tools(
    protocol: dict[str, Any],
    *,
    tool_registry: Any | None,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    if tool_registry is None:
        return []
    results: list[dict[str, Any]] = []
    for tool_name in [str(item).strip() for item in protocol.get("required_tools") or [] if str(item).strip()]:
        args = recovery_tool_args(protocol=protocol, context=context, tool_name=tool_name)
        result = tool_registry.run(tool_name, args)
        results.append(
            {
                "name": tool_name,
                "args": args,
                "ok": bool(getattr(result, "ok", False)),
                "data": getattr(result, "data", {}) if isinstance(getattr(result, "data", {}), dict) else {},
                "error": getattr(result, "error", None),
            }
        )
    return results


def recovery_tool_args(*, protocol: dict[str, Any], context: dict[str, Any], tool_name: str) -> dict[str, Any]:
    for source in (context, protocol):
        for key in ("tool_args_by_name", "tool_args"):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, dict) and isinstance(value.get(tool_name), dict):
                return dict(value[tool_name])
    return {}


def recovery_context_with_tool_results(context: dict[str, Any], tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not tool_results:
        return dict(context)
    success_count = sum(1 for item in tool_results if item.get("ok"))
    return {
        **context,
        "tool_results": tool_results,
        "tool_success_count": success_count,
        "tool_failure_count": len(tool_results) - success_count,
    }


def recovery_tool_trace(
    *,
    protocol: dict[str, Any],
    tool_registry: Any | None,
    tool_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    required_tools = [str(item).strip() for item in protocol.get("required_tools") or [] if str(item).strip()]
    if not required_tools:
        return []
    if tool_registry is None:
        return [
            {
                "event_type": "recovery.tools_not_executed",
                "reason": "tool_registry_unavailable",
                "required_tools": required_tools,
            }
        ]
    return [
        {
            "event_type": "recovery.tools_executed",
            "required_tools": required_tools,
            "succeeded": [item["name"] for item in tool_results if item.get("ok")],
            "failed": [item["name"] for item in tool_results if not item.get("ok")],
        }
    ]


def apply_recovery_resolution(
    state: dict[str, Any],
    recovery_trace: dict[str, Any],
    *,
    authority: str | None = None,
) -> dict[str, Any]:
    if recovery_trace.get("status") != "recovery_succeeded":
        return {"signal_resolution_report": {"status": "not_applicable", "resolved": [], "open_blockers": []}}
    protocol = recovery_trace.get("selected_protocol") if isinstance(recovery_trace.get("selected_protocol"), dict) else {}
    resolution_authority = authority or str(protocol.get("id") or "").strip()
    if not resolution_authority:
        return {"signal_resolution_report": {"status": "missing_recovery_authority", "resolved": [], "open_blockers": []}}
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    return apply_stop_signal_resolution(
        {
            **state,
            "metadata": {
                **metadata,
                "resolution_authority": resolution_authority,
            },
        }
    )


def matching_recovery_protocols(state: dict[str, Any], *, target: str) -> list[dict[str, Any]]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    protocols = swarm_plan.get("recovery_protocols") if isinstance(swarm_plan.get("recovery_protocols"), list) else []
    matched = []
    for protocol in protocols:
        if not isinstance(protocol, dict):
            continue
        targets = protocol_targets(protocol)
        if not targets or canonical_target(target) in targets:
            matched.append(protocol)
    return sorted(matched, key=lambda item: -protocol_target_demand(item, target))


def protocol_targets(protocol: dict[str, Any]) -> set[str]:
    targets = set()
    for item in protocol.get("targets") or []:
        if isinstance(item, dict):
            targets.add(canonical_target(item.get("canonical_target") or item.get("target")))
        else:
            targets.add(canonical_target(item))
    for item in protocol.get("trigger_targets") or []:
        targets.add(canonical_target(item))
    return {target for target in targets if target != "run"}


def protocol_target_demand(protocol: dict[str, Any], target: str) -> float:
    for item in protocol.get("targets") or []:
        if not isinstance(item, dict):
            continue
        if canonical_target(item.get("canonical_target") or item.get("target")) == canonical_target(target):
            return safe_float(item.get("demand_strength") or item.get("default_pressure"), 0.5)
    return 0.5


def select_recovery_agents(state: dict[str, Any], *, protocol: dict[str, Any], target: str) -> list[dict[str, Any]]:
    agents = agent_specs_from_state(state)
    allocations = allocations_by_agent(state)
    selected = []
    for agent in agents:
        score, reasons = recovery_agent_score(
            state,
            agent,
            allocations.get(str(agent.get("key") or agent.get("agent") or "")),
            protocol,
            target,
        )
        if score <= 0:
            continue
        selected.append(
            {
                "agent": str(agent.get("key") or agent.get("agent")),
                "name": agent.get("name") or agent.get("key") or agent.get("agent"),
                "score": round(score, 3),
                "reasons": reasons,
            }
        )
    selected.sort(key=lambda item: (-float(item["score"]), item["agent"]))
    return selected[:4]


def recovery_agent_score(
    state: dict[str, Any],
    agent: dict[str, Any],
    allocation: dict[str, Any] | None,
    protocol: dict[str, Any],
    target: str,
) -> tuple[float, list[str]]:
    role_terms = agent_terms(agent)
    allowed_roles = normalized_policy_terms(protocol.get("allowed_agent_roles"))
    allowed_tags = normalized_policy_terms(protocol.get("allowed_capability_tags"))
    required_tools = normalized_policy_terms(protocol.get("required_tools"))
    trust_ok, trust_delta, trust_reason = trust_requirement_score(state, agent, protocol)
    if not trust_ok:
        return 0.0, [trust_reason or "trust requirement not met"]
    maturity_ok, maturity_delta, maturity_reason = maturity_requirement_score(state, agent, protocol)
    if not maturity_ok:
        return 0.0, [maturity_reason or "maturity requirement not met"]
    score = 0.0
    reasons: list[str] = []
    if allowed_roles and role_terms & allowed_roles:
        score += 0.5
        reasons.append("allowed_role")
    if allowed_tags and role_terms & allowed_tags:
        score += 0.45
        reasons.append("allowed_capability_tag")
    if required_tools and normalized_policy_terms(agent.get("required_tools")) & required_tools:
        score += 0.2
        reasons.append("required_tool_match")
    if allocation:
        matched_targets = {
            canonical_target(item.get("canonical_target") or item.get("target"))
            for item in allocation.get("matched_targets") or []
            if isinstance(item, dict)
        }
        if canonical_target(target) in matched_targets:
            score += 0.35
            reasons.append("target_affinity")
        if allocation.get("activated"):
            score += 0.15
            reasons.append("activated")
        score += min(0.15, max(0.0, safe_float(allocation.get("utility"), 0.0)) * 0.1)
    if not allowed_roles and not allowed_tags and canonical_target(target).split(":")[-1].replace("_", " ") in " ".join(role_terms):
        score += 0.25
        reasons.append("target_text_affinity")
    if trust_delta:
        score += trust_delta
        reasons.append(trust_reason)
    if maturity_delta:
        score += maturity_delta
        reasons.append(maturity_reason)
    return score, reasons


def trust_requirement_score(
    state: dict[str, Any],
    agent: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[bool, float, str]:
    requirements = protocol.get("trust_requirements") if isinstance(protocol.get("trust_requirements"), dict) else {}
    if not requirements:
        return True, 0.0, ""
    trust_level = normalized_trust_level(agent_trust_level(state, agent))
    allowed = normalized_trust_levels(requirements.get("allowed_trust_levels") or requirements.get("allowed_levels"))
    blocked = normalized_trust_levels(requirements.get("blocked_trust_levels") or requirements.get("blocked_levels"))
    if blocked and trust_level in blocked:
        return False, 0.0, "blocked_trust_level"
    if allowed and trust_level not in allowed:
        return False, 0.0, "missing_allowed_trust_level"
    minimum = normalized_trust_level(requirements.get("min_trust_level") or requirements.get("minimum_trust_level"))
    if minimum and trust_rank(trust_level) < trust_rank(minimum):
        return False, 0.0, "below_min_trust_level"
    return True, 0.12, "trust_requirement"


def maturity_requirement_score(
    state: dict[str, Any],
    agent: dict[str, Any],
    protocol: dict[str, Any],
) -> tuple[bool, float, str]:
    requirements = protocol.get("maturity_requirements") if isinstance(protocol.get("maturity_requirements"), dict) else {}
    if not requirements:
        return True, 0.0, ""
    maturity = normalized_maturity(agent_maturity(state, agent))
    minimum = normalized_maturity(requirements.get("min_maturity") or requirements.get("minimum_maturity"))
    if minimum and maturity_rank(maturity) < maturity_rank(minimum):
        return False, 0.0, "below_min_maturity"
    required_actions = normalized_policy_terms(requirements.get("required_actions"))
    allowed_actions = normalized_policy_terms(agent_allowed_actions(state, agent))
    if required_actions and not required_actions.issubset(allowed_actions):
        return False, 0.0, "missing_maturity_action"
    return True, 0.1, "maturity_requirement"


def agent_trust_level(state: dict[str, Any], agent: dict[str, Any]) -> str:
    explicit = str(agent.get("trust_level") or agent.get("provider_trust_level") or "").strip()
    if explicit:
        return explicit
    identity = agent.get("identity") if isinstance(agent.get("identity"), dict) else {}
    if identity.get("trust_level"):
        return str(identity.get("trust_level"))
    badge = trust_badge_for_agent(state, agent_key(agent))
    if badge.get("trust_level"):
        return str(badge.get("trust_level"))
    return "trusted_first_party"


def agent_maturity(state: dict[str, Any], agent: dict[str, Any]) -> str:
    explicit = str(agent.get("maturity") or "").strip()
    if explicit:
        return explicit
    item = maturity_report_for_agent(state, agent_key(agent))
    if item.get("maturity"):
        return str(item.get("maturity"))
    return "worker"


def agent_allowed_actions(state: dict[str, Any], agent: dict[str, Any]) -> list[str]:
    actions = agent.get("allowed_actions") if isinstance(agent.get("allowed_actions"), list) else []
    item = maturity_report_for_agent(state, agent_key(agent))
    report_actions = item.get("allowed_actions") if isinstance(item.get("allowed_actions"), list) else []
    return [*actions, *report_actions]


def trust_badge_for_agent(state: dict[str, Any], agent: str) -> dict[str, Any]:
    for item in report_items_from_state(state, "trust_badges"):
        if str(item.get("agent") or item.get("agent_id") or "") == agent:
            return item
    return {}


def maturity_report_for_agent(state: dict[str, Any], agent: str) -> dict[str, Any]:
    report = state.get("maturity_report") if isinstance(state.get("maturity_report"), dict) else {}
    if not report:
        metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
        report = metadata.get("maturity_report") if isinstance(metadata.get("maturity_report"), dict) else {}
    for item in report.get("agents") or []:
        if isinstance(item, dict) and str(item.get("agent") or item.get("agent_id") or "") == agent:
            return item
    return {}


def report_items_from_state(state: dict[str, Any], key: str) -> list[dict[str, Any]]:
    direct = state.get(key) if isinstance(state.get(key), list) else []
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    nested = metadata.get(key) if isinstance(metadata.get(key), list) else []
    return [item for item in [*direct, *nested] if isinstance(item, dict)]


def agent_key(agent: dict[str, Any]) -> str:
    return str(agent.get("key") or agent.get("agent") or "").strip()


def normalized_trust_levels(value: Any) -> set[str]:
    return {normalized_trust_level(item) for item in normalized_policy_terms(value) if normalized_trust_level(item)}


def normalized_trust_level(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "first_party": "trusted_first_party",
        "first_party_reviewed": "trusted_first_party",
        "trusted": "trusted_first_party",
        "internal": "trusted_first_party",
        "third_party": "third_party_untrusted",
        "untrusted": "third_party_untrusted",
    }
    return aliases.get(text, text)


def trust_rank(value: str) -> int:
    order = {
        "external_content": 0,
        "third_party_untrusted": 1,
        "user_installed": 2,
        "trusted_first_party": 3,
        "core_system": 4,
    }
    return order.get(normalized_trust_level(value), 2)


def normalized_maturity(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text.replace("-", "_")


def maturity_rank(value: str) -> int:
    order = {"observer": 0, "worker": 1, "specialist": 2, "verifier": 3, "blocker": 4}
    return order.get(normalized_maturity(value), 1)


def agent_specs_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    registry = metadata.get("agent_registry") if isinstance(metadata.get("agent_registry"), dict) else {}
    agents = registry.get("agents") if isinstance(registry.get("agents"), list) else []
    if agents:
        return [agent for agent in agents if isinstance(agent, dict)]
    allocations = allocations_from_state(state)
    output = []
    for allocation in allocations:
        if not isinstance(allocation, dict):
            continue
        key = str(allocation.get("agent") or "").strip()
        if not key:
            continue
        output.append(
            {
                "key": key,
                "name": allocation.get("name") or key,
                "agent_type": allocation.get("agent_type"),
                "committee_role": allocation.get("committee_role"),
                "focus": allocation.get("focus") or allocation.get("activation_reason"),
                "tags": allocation.get("tags") or [],
            }
        )
    return output


def allocations_by_agent(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("agent") or ""): item
        for item in allocations_from_state(state)
        if isinstance(item, dict) and str(item.get("agent") or "").strip()
    }


def allocations_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    allocations = swarm_plan.get("agent_allocation") if isinstance(swarm_plan.get("agent_allocation"), list) else []
    return [item for item in allocations if isinstance(item, dict)]


def recovery_target_pressure(state: dict[str, Any], *, target: str, context: dict[str, Any]) -> float:
    pressure = 0.0
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    for signal in swarm_plan.get("target_signals") or []:
        if isinstance(signal, dict) and canonical_target(signal.get("canonical_target") or signal.get("target")) == target:
            pressure = max(pressure, safe_float(signal.get("demand_strength"), 0.0))
    if context.get("needs_recovery"):
        pressure = max(pressure, 0.86)
    if context.get("candidate_count") and not context.get("full_text_count"):
        pressure = max(pressure, 0.82)
    for signal in state.get("stop_signals") or []:
        if isinstance(signal, dict) and is_active_blocker(signal) and canonical_target(signal.get("target")) == target:
            pressure = max(pressure, 0.95)
    return round(pressure or 0.5, 3)


def recovery_success(protocol: dict[str, Any], *, state: dict[str, Any], context: dict[str, Any]) -> bool:
    condition = str(protocol.get("recovery_success_condition") or "").strip()
    if not condition:
        return bool(context.get("full_text_count") or context.get("recovery_succeeded") or state.get("recovery_succeeded"))
    return condition_satisfied(condition, state={**state, "context": context, "recovery": context})


def condition_satisfied(condition: str, *, state: dict[str, Any]) -> bool:
    match = re.fullmatch(r"([a-zA-Z0-9_.]+)\s*(==|!=|>=|<=|>|<)\s*(.+)", condition)
    if not match:
        return bool(value_at_path(state, condition))
    path, operator, raw_expected = match.groups()
    actual = value_at_path(state, path)
    expected = parse_condition_value(raw_expected)
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    actual_number = safe_float(actual, 0.0)
    expected_number = safe_float(expected, 0.0)
    if operator == ">":
        return actual_number > expected_number
    if operator == "<":
        return actual_number < expected_number
    if operator == ">=":
        return actual_number >= expected_number
    if operator == "<=":
        return actual_number <= expected_number
    return False


def value_at_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def parse_condition_value(value: str) -> Any:
    text = value.strip().strip("\"'")
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def inferred_recovery_target(state: dict[str, Any], context: dict[str, Any]) -> str:
    for key in ("target", "canonical_target", "recovery_target"):
        if context.get(key):
            return str(context[key])
    for signal in state.get("stop_signals") or []:
        if isinstance(signal, dict) and is_active_blocker(signal):
            return str(signal.get("target") or "run")
    return "gate:research_evidence_gate"


def agent_terms(agent: dict[str, Any]) -> set[str]:
    values: list[Any] = [
        agent.get("key"),
        agent.get("agent"),
        agent.get("name"),
        agent.get("agent_type"),
        agent.get("committee_role"),
        agent.get("description"),
    ]
    values.extend(agent.get("focus") if isinstance(agent.get("focus"), list) else [agent.get("focus")])
    values.extend(agent.get("tags") if isinstance(agent.get("tags"), list) else [])
    values.extend(agent.get("required_capabilities") if isinstance(agent.get("required_capabilities"), list) else [])
    return normalized_terms(values)


def normalized_terms(value: Any) -> set[str]:
    values = value if isinstance(value, list) else [value]
    output = set()
    for item in values:
        text = str(item or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
        output.update(part for part in re.split(r"[\s,_:/.-]+", text) if part)
    return output


def normalized_policy_terms(value: Any) -> set[str]:
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


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
