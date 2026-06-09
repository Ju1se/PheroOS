from __future__ import annotations

import re
from typing import Any

from runtime.swarm.event_log import swarm_event
from runtime.swarm.execution_context import SwarmExecutionContext
from runtime.swarm.recovery_engine import maturity_requirement_score, trust_requirement_score
from runtime.swarm.target_registry import canonical_target


AGENT_ALLOCATOR_SCHEMA_VERSION = "pheroos.agent_allocator.v1"


def allocate_agents_for_pressure(
    context: SwarmExecutionContext,
    pressure_map: dict[str, Any],
) -> dict[str, Any]:
    policy = context.agent_selection_policy
    threshold = safe_float(policy.get("activation_threshold"), 0.46)
    candidate_rows = allocation_candidates(context)
    selected: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for row in candidate_rows:
        score, reasons, matched_targets = allocation_score(row, context=context, pressure_map=pressure_map)
        output = {
            **row,
            "matched_targets": matched_targets,
            "utility": round(score, 3),
            "threshold": threshold,
            "activated": score >= threshold,
            "activation_reason": "; ".join(reasons) if reasons else "below response threshold for current goal targets",
            "allocation_source": "target_pressure",
        }
        if output["activated"]:
            selected.append(output)
        else:
            suppressed.append(output)
    selected.sort(key=lambda item: (-safe_float(item.get("utility"), 0.0), str(item.get("agent") or "")))
    suppressed.sort(key=lambda item: (-safe_float(item.get("utility"), 0.0), str(item.get("agent") or "")))
    events = [
        swarm_event(
            event_type="agent.allocated",
            run_id=context.run_id,
            tenant_id=context.tenant_id,
            actor="pheroos.agent_allocator",
            target=f"agent:{item['agent']}",
            summary=f"Allocated {item['agent']} by target pressure.",
            payload={"agent": item["agent"], "utility": item["utility"], "matched_targets": item.get("matched_targets", [])},
        )
        for item in selected
    ]
    events.extend(
        swarm_event(
            event_type="agent.suppressed",
            run_id=context.run_id,
            tenant_id=context.tenant_id,
            actor="pheroos.agent_allocator",
            target=f"agent:{item['agent']}",
            summary=f"Suppressed {item['agent']} below target pressure threshold.",
            payload={"agent": item["agent"], "utility": item["utility"], "threshold": item["threshold"]},
        )
        for item in suppressed
    )
    return {
        "schema_version": AGENT_ALLOCATOR_SCHEMA_VERSION,
        "activation_threshold": threshold,
        "selected": selected,
        "suppressed": suppressed,
        "events": events,
    }


def allocation_candidates(context: SwarmExecutionContext) -> list[dict[str, Any]]:
    if context.allocations:
        return [normalize_allocation(item) for item in context.allocations if str(item.get("agent") or "").strip()]
    output = []
    for agent in context.agents:
        key = str(agent.get("key") or agent.get("agent") or "").strip()
        if not key:
            continue
        output.append(
            normalize_allocation(
                {
                    "agent": key,
                    "name": agent.get("name") or key,
                    "agent_type": agent.get("agent_type"),
                    "committee_role": agent.get("committee_role"),
                    "tags": agent.get("tags") or [],
                    "focus": agent.get("focus") or agent.get("focus_items") or [],
                }
            )
        )
    return output


def normalize_allocation(value: dict[str, Any]) -> dict[str, Any]:
    agent = str(value.get("agent") or value.get("key") or "").strip()
    return {
        **value,
        "agent": agent,
        "name": value.get("name") or agent,
        "matched_targets": value.get("matched_targets") if isinstance(value.get("matched_targets"), list) else [],
    }


def allocation_score(
    row: dict[str, Any],
    *,
    context: SwarmExecutionContext,
    pressure_map: dict[str, Any],
) -> tuple[float, list[str], list[dict[str, Any]]]:
    policy = context.agent_selection_policy
    terms = policy_terms(row)
    forbidden = exact_terms(policy.get("forbidden_roles"))
    if forbidden and terms & forbidden:
        return 0.0, ["forbidden role suppressed"], []
    required = exact_terms(policy.get("required_roles"))
    optional = exact_terms(policy.get("optional_roles"))
    requirement_protocol = {
        "trust_requirements": policy.get("trust_requirements") if isinstance(policy.get("trust_requirements"), dict) else {},
        "maturity_requirements": policy.get("maturity_requirements")
        if isinstance(policy.get("maturity_requirements"), dict)
        else {},
    }
    requirement_state = {"metadata": context.metadata}
    trust_ok, trust_delta, trust_reason = trust_requirement_score(requirement_state, row, requirement_protocol)
    if not trust_ok:
        return 0.0, [trust_reason], []
    maturity_ok, maturity_delta, maturity_reason = maturity_requirement_score(requirement_state, row, requirement_protocol)
    if not maturity_ok:
        return 0.0, [maturity_reason], []
    score = safe_float(row.get("utility"), 0.0) * 0.35
    reasons: list[str] = []
    if required:
        if terms & required:
            score += 0.45
            reasons.append("required role")
        else:
            score -= 0.35
            reasons.append("missing required role")
    if optional and terms & optional:
        score += 0.2
        reasons.append("optional role")
    matched = matched_target_pressure(row, context=context, pressure_map=pressure_map)
    if matched:
        max_pressure = max(safe_float(item.get("pressure"), 0.0) for item in matched)
        score += max_pressure * 0.55
        reasons.append("target pressure")
    if row.get("activated"):
        score += 0.1
        reasons.append("previously activated")
    if trust_delta:
        score += trust_delta
        reasons.append(trust_reason)
    if maturity_delta:
        score += maturity_delta
        reasons.append(maturity_reason)
    if not required and not optional and not matched:
        score += 0.1
    return score, reasons, matched


def matched_target_pressure(
    row: dict[str, Any],
    *,
    context: SwarmExecutionContext,
    pressure_map: dict[str, Any],
) -> list[dict[str, Any]]:
    by_target = pressure_map.get("by_target") if isinstance(pressure_map.get("by_target"), dict) else {}
    raw_matches = row.get("matched_targets") if isinstance(row.get("matched_targets"), list) else []
    canonical_matches = {
        canonical_target(item.get("canonical_target") or item.get("target"))
        for item in raw_matches
        if isinstance(item, dict)
    }
    if not canonical_matches:
        row_text = " ".join(policy_terms(row))
        for target in context.targets:
            canonical = canonical_target(target.get("canonical_target") or target.get("target"))
            tail = canonical.rsplit(":", 1)[-1].replace("_", " ")
            if tail and tail in row_text:
                canonical_matches.add(canonical)
    if not canonical_matches and len(context.targets) == 1:
        canonical_matches.add(context.targets[0]["canonical_target"])
    output = []
    for target in sorted(canonical_matches):
        pressure = by_target.get(target)
        if isinstance(pressure, dict):
            output.append(
                {
                    "target": target,
                    "canonical_target": target,
                    "pressure": pressure.get("pressure"),
                    "reasons": pressure.get("reasons", []),
                }
            )
    return output


def policy_terms(value: dict[str, Any]) -> set[str]:
    raw: list[Any] = [
        value.get("agent"),
        value.get("key"),
        value.get("name"),
        value.get("agent_type"),
        value.get("committee_role"),
        value.get("description"),
    ]
    for key in ("tags", "focus", "focus_items", "required_capabilities", "required_tools"):
        item = value.get(key)
        raw.extend(item if isinstance(item, list) else [item])
    output = set()
    for item in raw:
        text = str(item or "").strip().lower()
        if not text:
            continue
        output.add(text)
        output.add(text.replace("-", "_"))
        output.add(text.replace("_", "-"))
        output.update(part for part in re.split(r"[\s,_:/.-]+", text) if part)
    return output


def exact_terms(value: Any) -> set[str]:
    raw = value if isinstance(value, list) else [value]
    output = set()
    for item in raw:
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
