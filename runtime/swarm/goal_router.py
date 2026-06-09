from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.swarm.goal_targets import GOAL_ROUTER_VERSION, GoalTarget
from runtime.swarm.legacy_goal_targets import legacy_default_targets_for_intent
from runtime.swarm.protocol import capability_protocol_bundle
from runtime.swarm.target_registry import canonical_target


@dataclass(frozen=True)
class GoalRoutingResult:
    targets: list[GoalTarget]
    trace: list[dict[str, Any]]
    needs_capability: bool = False


def build_goal_routed_swarm_plan(
    *,
    task: str,
    intent: str,
    required_capability_types: list[str],
    agents: list[dict[str, Any]],
    capabilities: list[dict[str, Any]] | None = None,
    selected_agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    protocol_bundle = capability_protocol_bundle(capabilities)
    explicit_protocol_present = any(
        isinstance(protocol, dict) and not protocol.get("generated_legacy_protocol")
        for protocol in protocol_bundle.get("protocols", [])
    )
    routing = route_goal_targets(
        task=task,
        intent=intent,
        required_capability_types=required_capability_types,
        protocol_targets=protocol_bundle.get("targets", []),
        explicit_protocol_present=explicit_protocol_present,
    )
    targets = routing.targets
    selected = [str(item).strip() for item in selected_agent_ids or [] if str(item).strip()]
    allocation = allocate_agents_to_targets(
        agents=agents,
        intent=intent,
        targets=targets,
        explicit_selected_agent_ids=selected,
        agent_selection_policy=protocol_bundle.get("agent_selection_policy", {}),
    )
    activated = [item["agent"] for item in allocation if item.get("activated")]
    return {
        "schema_version": GOAL_ROUTER_VERSION,
        "intent": intent,
        "target_signals": [target.to_signal() for target in targets],
        "target_count": len(targets),
        "agent_allocation": allocation,
        "activated_agents": activated,
        "activated_agent_count": len(activated),
        "capability_protocols": protocol_bundle.get("protocols", []),
        "protocol_source": protocol_bundle.get("protocol_source"),
        "recovery_protocols": protocol_bundle.get("recovery_protocols", []),
        "candidate_policy": protocol_bundle.get("candidate_policy", {}),
        "quorum_policy": protocol_bundle.get("quorum_policy", {}),
        "stop_signal_policy": protocol_bundle.get("stop_signal_policy", {}),
        "evidence_policy": protocol_bundle.get("evidence_policy", {}),
        "tool_policy": protocol_bundle.get("tool_policy", {}),
        "output_policy": protocol_bundle.get("output_policy", {}),
        "agent_selection_policy": protocol_bundle.get("agent_selection_policy", {}),
        "swarm_loop_policy": protocol_bundle.get("swarm_loop_policy", {}),
        "target_aliases": protocol_bundle.get("target_aliases", {}),
        "generated_legacy_protocol_count": protocol_bundle.get("generated_legacy_protocol_count", 0),
        "validation_diagnostics": protocol_bundle.get("validation_diagnostics", []),
        "workflow_entrypoints": protocol_bundle.get("workflow_entrypoints", []),
        "max_rounds": int((protocol_bundle.get("quorum_policy") or {}).get("max_swarm_rounds") or 2),
        "routing_trace": routing.trace,
        "legacy_goal_router_fallback": any(item.get("event_type") == "legacy_goal_router_fallback" for item in routing.trace),
        "needs_capability": routing.needs_capability,
        "selection_mode": "user_selected" if selected else "pheromone_response_threshold",
        "routing_logic": [
            "capability manifest targets -> canonical targets",
            "legacy fallback intent defaults only run when no capability target declarations exist",
            "targets -> demand strengths",
            "agent manifest focus/tags/role/swarm metadata -> response utility",
            "activated agents become the runtime swarm for this task",
        ],
    }


def infer_goal_targets(
    *,
    task: str,
    intent: str,
    required_capability_types: list[str],
    protocol_targets: list[dict[str, Any]] | None = None,
) -> list[GoalTarget]:
    return route_goal_targets(
        task=task,
        intent=intent,
        required_capability_types=required_capability_types,
        protocol_targets=protocol_targets,
    ).targets


def route_goal_targets(
    *,
    task: str,
    intent: str,
    required_capability_types: list[str],
    protocol_targets: list[dict[str, Any]] | None = None,
    explicit_protocol_present: bool = False,
) -> GoalRoutingResult:
    raw_protocol_targets = protocol_targets or []
    targets = goal_targets_from_protocol(raw_protocol_targets, intent=intent)
    trace: list[dict[str, Any]] = []
    needs_capability = False
    if targets:
        trace.append(
            {
                "event_type": "goal_router.protocol_targets_loaded",
                "source": "capability_protocol",
                "intent": intent,
                "target_count": len(targets),
            }
        )
    if not targets and explicit_protocol_present:
        needs_capability = True
        trace.append(
            {
                "event_type": "goal_router.protocol_targets_missing",
                "intent": intent,
                "reason": "explicit capability protocol was present but declared no goal targets",
                "required_capability_types": list(required_capability_types),
            }
        )
    elif not targets:
        defaults = list(legacy_default_targets_for_intent(intent))
        if defaults:
            targets = defaults
            trace.append(
                {
                    "event_type": "legacy_goal_router_fallback",
                    "fallback_type": "legacy_default_targets_by_intent",
                    "intent": intent,
                    "reason": "no capability-declared protocol targets were available",
                    "target_count": len(targets),
                }
            )
        else:
            needs_capability = True
            trace.append(
                {
                    "event_type": "goal_router.needs_capability",
                    "intent": intent,
                    "reason": "no capability-declared protocol targets and no legacy default targets",
                    "required_capability_types": list(required_capability_types),
                }
            )
    targets = dedupe_targets(targets)
    if targets:
        needs_capability = False
    return GoalRoutingResult(targets=targets, trace=trace, needs_capability=needs_capability)


def goal_targets_from_protocol(protocol_targets: list[dict[str, Any]], *, intent: str | None = None) -> list[GoalTarget]:
    output = []
    for item in protocol_targets:
        if not isinstance(item, dict):
            continue
        if not target_supports_intent(item, intent):
            continue
        canonical = canonical_target(item.get("canonical_target") or item.get("target"))
        if canonical == "run":
            continue
        keywords = item.get("keywords") if isinstance(item.get("keywords"), list) else []
        output.append(
            GoalTarget(
                canonical,
                safe_float(item.get("demand_strength"), 0.7),
                tuple(str(keyword).lower().replace("-", "_") for keyword in keywords if str(keyword).strip()),
                str(item.get("summary") or item.get("content") or f"Capability protocol requires {canonical}."),
            )
        )
    return output


def target_supports_intent(target: dict[str, Any], intent: str | None) -> bool:
    compatible = target.get("compatible_intents") if isinstance(target.get("compatible_intents"), list) else []
    compatible_intents = {str(item).strip() for item in compatible if str(item).strip()}
    if not compatible_intents:
        return True
    return str(intent or "").strip() in compatible_intents


def allocate_agents_to_targets(
    *,
    agents: list[dict[str, Any]],
    intent: str,
    targets: list[GoalTarget],
    explicit_selected_agent_ids: list[str],
    agent_selection_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    selected = set(explicit_selected_agent_ids)
    selection_policy = agent_selection_policy if isinstance(agent_selection_policy, dict) else {}
    policy_terms = agent_selection_policy_terms(selection_policy)
    rows = []
    for agent in agents:
        key = str(agent.get("key") or "")
        if not key:
            continue
        type_bonus, type_reason = preferred_agent_bonus(
            agent,
            policy_terms=policy_terms,
        )
        target_matches = score_agent_targets(agent, targets)
        strongest = max((item["score"] for item in target_matches), default=0.0)
        swarm = agent.get("swarm") if isinstance(agent.get("swarm"), dict) else {}
        can_block_bonus = 0.06 if swarm.get("can_block") and any(target.target.startswith(("gate:", "decision:")) for target in targets) else 0.0
        default_bonus = 0.08 if agent.get("default_enabled", True) else -0.08
        explicit_bonus = 1.0 if key in selected else 0.0
        utility = type_bonus + strongest + can_block_bonus + default_bonus + explicit_bonus
        threshold = 0.46 if policy_terms else 0.52
        activated = key in selected or utility >= threshold
        rows.append(
            {
                "agent": key,
                "name": agent.get("name") or key,
                "agent_type": agent.get("agent_type"),
                "capability_id": agent.get("capability_id"),
                "committee_role": agent.get("committee_role"),
                "matched_targets": [item for item in target_matches if item["score"] > 0],
                "utility": round(float(utility), 3),
                "threshold": round(float(threshold), 3),
                "activated": bool(activated),
                "activation_reason": activation_reason(
                    selected=key in selected,
                    type_bonus=type_bonus,
                    type_reason=type_reason,
                    strongest=strongest,
                    can_block_bonus=can_block_bonus,
                    default_bonus=default_bonus,
                    activated=activated,
                ),
            }
        )
    rows.sort(key=lambda item: (not item.get("activated"), -float(item.get("utility") or 0), str(item.get("agent"))))
    if not selected and targets and policy_terms and not any(item.get("activated") for item in rows):
        for row in rows[:1]:
            row["activated"] = True
            row["activation_reason"] = "fallback: highest pheromone utility for this target set"
    return rows


def preferred_agent_bonus(
    agent: dict[str, Any],
    *,
    policy_terms: set[str],
) -> tuple[float, str]:
    if policy_terms:
        if agent_selection_terms(agent) & policy_terms:
            return 0.42, "agent role matches protocol selection policy"
        return -0.12, ""
    return 0.24, "agent eligible for target scoring"


def agent_selection_policy_terms(policy: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in ("required_roles", "optional_roles", "allowed_agent_roles", "allowed_capability_tags"):
        value = policy.get(key)
        if isinstance(value, list):
            values.extend(value)
    return normalized_selection_terms(values)


def agent_selection_terms(agent: dict[str, Any]) -> set[str]:
    values: list[Any] = [
        agent.get("key"),
        agent.get("agent"),
        agent.get("agent_type"),
        agent.get("committee_role"),
    ]
    for key in ("tags", "required_capabilities", "required_tools"):
        value = agent.get(key)
        if isinstance(value, list):
            values.extend(value)
    return normalized_selection_terms(values)


def normalized_selection_terms(values: list[Any]) -> set[str]:
    output: set[str] = set()
    for item in values:
        text = str(item or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
    return output


def score_agent_targets(agent: dict[str, Any], targets: list[GoalTarget]) -> list[dict[str, Any]]:
    text = agent_search_text(agent)
    output = []
    for target in targets:
        matches = [keyword for keyword in target.keywords if keyword and keyword.lower() in text]
        role = str(agent.get("committee_role") or "").lower()
        key = str(agent.get("key") or "").lower()
        canonical = canonical_target(target.target)
        target_tail = canonical.rsplit(":", 1)[-1].replace("-", "_")
        if target_tail in role or target_tail in key:
            matches.append(target_tail)
        score = min(0.78, (0.16 * len(set(matches))) + (0.08 * target.demand_strength))
        output.append(
            {
                "target": target.target,
                "canonical_target": canonical,
                "demand_strength": round(target.demand_strength, 3),
                "score": round(float(score), 3),
                "matched_keywords": sorted(set(matches))[:8],
            }
        )
    return output


def agent_search_text(agent: dict[str, Any]) -> str:
    values: list[str] = [
        str(agent.get("key") or ""),
        str(agent.get("name") or ""),
        str(agent.get("description") or ""),
        str(agent.get("committee_role") or ""),
        str(agent.get("agent_type") or ""),
    ]
    for key in ("focus_items", "tags", "required_capabilities", "required_tools"):
        value = agent.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
    focus = agent.get("focus")
    if isinstance(focus, str):
        values.append(focus)
    return " ".join(values).lower().replace("-", "_")


def activation_reason(
    *,
    selected: bool,
    type_bonus: float,
    type_reason: str,
    strongest: float,
    can_block_bonus: float,
    default_bonus: float,
    activated: bool,
) -> str:
    if selected:
        return "user-selected agent bypassed response threshold"
    if not activated:
        return "below response threshold for current goal targets"
    reasons = []
    if type_bonus > 0 and type_reason:
        reasons.append(type_reason)
    if strongest > 0:
        reasons.append("manifest focus matches pheromone targets")
    if can_block_bonus > 0:
        reasons.append("can block gate/decision targets")
    if default_bonus > 0:
        reasons.append("default enabled")
    return "; ".join(reasons) or "activated by pheromone utility"


def dedupe_targets(targets: list[GoalTarget]) -> list[GoalTarget]:
    output: list[GoalTarget] = []
    seen: set[str] = set()
    for target in targets:
        canonical = canonical_target(target.target)
        if canonical in seen:
            continue
        seen.add(canonical)
        output.append(target)
    return output


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
