from __future__ import annotations

from typing import Any

from runtime.swarm.agent_profile import AgentProfileStore, update_profile_from_result
from runtime.swarm.data_gate_permissions import blocked_conclusion_permissions
from runtime.swarm.legacy_response_thresholds import (
    legacy_mandatory_committee_from_terms,
    legacy_role_demand_from_terms,
    legacy_role_demand_from_thresholds,
)
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.trust_badge import trust_badge_map


def build_agent_allocation_trace(member_specs: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """Explain why committee members were activated.

    This is a deterministic first pass of response-threshold allocation. It does
    not yet mutate the committee composition; it exposes activation reasons so
    the dashboard can explain the swarm's role selection.
    """

    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    tenant_id = tenant_id_from_state(state)
    raw_stop_signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    stop_signals = [signal for signal in raw_stop_signals if isinstance(signal, dict) and is_active_blocker(signal)]
    encounter_report = state.get("encounter_rate_report") if isinstance(state.get("encounter_rate_report"), dict) else {}
    bottleneck_report = state.get("bottleneck_report") if isinstance(state.get("bottleneck_report"), dict) else {}
    trust_badges = trust_badge_map(state.get("trust_badges") if isinstance(state.get("trust_badges"), list) else [])
    bottleneck_targets = {
        str(agent)
        for item in bottleneck_report.get("bottlenecks") or []
        if isinstance(item, dict)
        for agent in item.get("recruit", [])
    }
    evidence_gap_strength = 0.8 if data_gate.get("evidence_gaps") else 0.35
    risk_strength = 0.85 if stop_signals or data_gate.get("decision_blockers") else 0.45
    conclusion_demand = 0.35 if blocked_conclusion_permissions(data_gate) else 0.8
    contact_rate_bonus = contact_rate_bonus_for(encounter_report)

    demand_context = {
        "evidence_gap_strength": evidence_gap_strength,
        "risk_strength": risk_strength,
        "conclusion_demand": conclusion_demand,
    }
    trace = []
    for index, spec in enumerate(member_specs):
        key = str(spec.get("key") or spec.get("agent") or f"agent_{index}")
        task_type, demand, reason = role_demand_for_spec(spec, demand_context)
        profile = AgentProfileStore().get(key, tenant_id=tenant_id)
        trust_badge = trust_badges.get(key, {})
        manifest_threshold = manifest_threshold_for(spec, task_type)
        threshold = profile.threshold_for(
            task_type,
            manifest_threshold if manifest_threshold is not None else default_threshold_for(key, default_enabled=bool(spec.get("default_enabled", True))),
        )
        bottleneck_bonus = 0.22 if key in bottleneck_targets else 0.0
        trust_penalty = float(trust_badge.get("trust_penalty") or 0.0)
        utility = (
            demand
            - threshold
            + (0.2 * profile.capability_for(task_type))
            + (0.1 * profile.reliability)
            + contact_rate_bonus
            + bottleneck_bonus
            - trust_penalty
        )
        trace.append(
            {
                "agent": key,
                "name": spec.get("name") or key,
                "task_type": task_type,
                "demand_strength": round(float(demand), 3),
                "threshold": round(float(threshold), 3),
                "contact_rate_bonus": round(float(contact_rate_bonus), 3),
                "bottleneck_bonus": round(float(bottleneck_bonus), 3),
                "trust_penalty": round(float(trust_penalty), 3),
                "trust_level": trust_badge.get("trust_level"),
                "allowed_lanes": trust_badge.get("allowed_lanes", []),
                "utility": round(float(utility), 3),
                "reliability": round(float(profile.reliability), 3),
                "activated": utility >= 0,
                "reason": reason,
            }
        )
    return trace


def select_committee_members_by_threshold(
    member_specs: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    explicit_selection: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trace = build_agent_allocation_trace(member_specs, state)
    if explicit_selection or not dynamic_committee_enabled(state):
        return member_specs, trace

    active_keys = {item["agent"] for item in trace if item.get("activated")}
    active_keys.update(
        str(spec.get("key") or spec.get("agent") or "")
        for spec in member_specs
        if mandatory_committee_spec(spec)
    )
    selected = [spec for spec in member_specs if spec.get("key") in active_keys]
    if len(selected) < 4:
        selected = member_specs[:4]
    return selected, trace


def update_agent_profiles_from_outputs(
    outputs: dict[str, Any],
    allocation_trace: list[dict[str, Any]],
    *,
    store: AgentProfileStore | None = None,
    tenant_id: str = "default",
) -> None:
    store = store or AgentProfileStore()
    profiles = {agent_id: store.get(agent_id, tenant_id=tenant_id) for agent_id in outputs}
    task_by_agent = {str(item.get("agent")): str(item.get("task_type") or "agent_review") for item in allocation_trace}
    for agent_id, output in outputs.items():
        if not isinstance(output, dict):
            continue
        status = str(output.get("status") or "").lower()
        failure_reason = output.get("failure_reason") or output.get("error")
        success = status not in {"failed", "error", "unstructured_failed"} and not failure_reason
        profiles[agent_id] = update_profile_from_result(
            profiles[agent_id],
            task_type=task_by_agent.get(agent_id, "agent_review"),
            success=success,
            hard_veto=bool(output.get("hard_veto")),
            failure_reason=str(failure_reason) if failure_reason else None,
        )
    if profiles:
        store.update_many(profiles, tenant_id=tenant_id)


def dynamic_committee_enabled(state: dict[str, Any]) -> bool:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    if metadata.get("swarm_dynamic_committee") is False:
        return False
    return bool(metadata.get("os_plan")) or metadata.get("swarm_dynamic_committee") is True


def tenant_id_from_state(state: dict[str, Any]) -> str:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return str(metadata.get("tenant_id") or os_plan.get("tenant_id") or "default")


def default_threshold_for(agent_id: str, *, default_enabled: bool) -> float:
    return 0.35 if default_enabled else 0.65


def role_demand_for_spec(spec: dict[str, Any], context: dict[str, float]) -> tuple[str, float, str]:
    terms = manifest_terms(spec)
    thresholds = manifest_initial_thresholds(spec)
    declared_demand = manifest_role_demand_from_profiles(spec, thresholds=thresholds, context=context)
    if declared_demand is not None:
        return declared_demand
    legacy_threshold_demand = legacy_role_demand_from_thresholds(thresholds, context)
    if legacy_threshold_demand is not None:
        return legacy_threshold_demand
    legacy_term_demand = legacy_role_demand_from_terms(terms, context)
    if legacy_term_demand is not None:
        return legacy_term_demand
    if thresholds:
        task_type = sorted(thresholds)[0]
        return (task_type, 0.5, f"manifest-declared threshold for {task_type}")
    return ("agent_review", 0.5, "default agent participation")


def mandatory_committee_spec(spec: dict[str, Any]) -> bool:
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    terms = manifest_terms(spec)
    return bool(
        swarm.get("can_block")
        or swarm.get("must_follow_committed_candidate")
        or legacy_mandatory_committee_from_terms(terms)
    )


def manifest_initial_thresholds(spec: dict[str, Any]) -> dict[str, Any]:
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    return swarm.get("initial_thresholds") if isinstance(swarm.get("initial_thresholds"), dict) else {}


def manifest_role_demand_from_profiles(
    spec: dict[str, Any],
    *,
    thresholds: dict[str, Any],
    context: dict[str, float],
) -> tuple[str, float, str] | None:
    profiles = manifest_demand_profiles(spec)
    for task_type in thresholds:
        profile = profiles.get(task_type)
        if not isinstance(profile, dict):
            continue
        demand = manifest_profile_demand(profile, context)
        if demand is None:
            continue
        reason = str(profile.get("reason") or f"manifest-declared demand profile for {task_type}")
        return (str(task_type), demand, reason)
    return None


def manifest_demand_profiles(spec: dict[str, Any]) -> dict[str, Any]:
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    for key in ("response_demand_profiles", "demand_profiles", "initial_demand_profiles"):
        profiles = swarm.get(key)
        if isinstance(profiles, dict):
            return profiles
    return {}


def manifest_profile_demand(profile: dict[str, Any], context: dict[str, float]) -> float | None:
    if "demand" in profile:
        try:
            return float(profile.get("demand"))
        except (TypeError, ValueError):
            return None
    context_key = str(profile.get("context") or profile.get("demand_context") or "").strip()
    if context_key in context:
        return float(context[context_key])
    return None


def manifest_terms(spec: dict[str, Any]) -> set[str]:
    values = [
        spec.get("key"),
        spec.get("agent"),
        spec.get("name"),
        spec.get("agent_type"),
        spec.get("committee_role"),
        spec.get("description"),
        spec.get("focus"),
    ]
    for key in ("tags", "focus_items", "required_capabilities", "required_tools"):
        values.extend(spec.get(key) if isinstance(spec.get(key), list) else [])
    values.extend(manifest_initial_thresholds(spec).keys())
    output: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
        output.update(part for part in text.replace("-", "_").replace("/", "_").split("_") if part)
    return output


def manifest_threshold_for(spec: dict[str, Any], task_type: str) -> float | None:
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    thresholds = swarm.get("initial_thresholds") if isinstance(swarm.get("initial_thresholds"), dict) else {}
    if task_type in thresholds:
        try:
            return float(thresholds[task_type])
        except (TypeError, ValueError):
            return None
    return None


def contact_rate_bonus_for(report: dict[str, Any]) -> float:
    status = str(report.get("status") or "")
    rate = float(report.get("rate") or 0.0)
    if status == "healthy":
        return min(0.08, rate * 0.08)
    if status == "poor":
        return -0.12
    if status == "degraded":
        return -0.04
    return 0.0
