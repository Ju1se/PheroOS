from __future__ import annotations

from typing import Any

from runtime.swarm.agent_allocator import policy_terms
from runtime.swarm.execution_context import SwarmExecutionContext
from runtime.swarm.target_registry import canonical_target


RECRUITMENT_SCHEMA_VERSION = "pheroos.recruitment.v1"


def recruit_agents_for_recovery(
    context: SwarmExecutionContext,
    *,
    target: str,
) -> dict[str, Any]:
    canonical = canonical_target(target)
    protocols = [protocol for protocol in context.recovery_protocols if protocol_matches_target(protocol, canonical)]
    selected = []
    protocol_lineage = []
    for protocol in protocols:
        protocol_ref = recovery_protocol_reference(context, protocol=protocol, target=canonical)
        protocol_lineage.append(protocol_ref)
        allowed_roles = exact_terms(protocol.get("allowed_agent_roles"))
        allowed_tags = exact_terms(protocol.get("allowed_capability_tags"))
        required_tools = exact_terms(protocol.get("required_tools"))
        for agent in context.agents:
            score, reasons = recruitment_score(agent, allowed_roles=allowed_roles, allowed_tags=allowed_tags, required_tools=required_tools)
            if score <= 0:
                continue
            selected.append(
                {
                    "agent": str(agent.get("key") or agent.get("agent")),
                    "protocol_id": protocol_ref.get("protocol_id"),
                    "capability_id": protocol_ref.get("capability_id"),
                    "source": protocol_ref.get("source"),
                    "protocol_source": protocol_ref.get("protocol_source"),
                    "target": canonical,
                    "score": round(score, 3),
                    "reasons": reasons,
                }
            )
    selected = [item for item in selected if item.get("agent")]
    selected.sort(key=lambda item: (-float(item["score"]), str(item["agent"])))
    return {
        "schema_version": RECRUITMENT_SCHEMA_VERSION,
        "target": canonical,
        "recruitment_source": "recovery_protocol_roles_tags",
        "protocol_source": context.protocol_source,
        "protocol_lineage": dedupe_protocol_rows(protocol_lineage),
        "selected_agents": dedupe_agent_rows(selected)[:4],
    }


def recovery_protocol_reference(
    context: SwarmExecutionContext,
    *,
    protocol: dict[str, Any],
    target: str,
) -> dict[str, Any]:
    protocol_id = str(protocol.get("id") or protocol.get("recovery_id") or "").strip()
    capability_id = str(protocol.get("capability_id") or "").strip()
    for capability_protocol in context.capability_protocols:
        if not isinstance(capability_protocol, dict):
            continue
        for candidate in capability_protocol.get("recovery_protocols") or []:
            if not isinstance(candidate, dict):
                continue
            candidate_id = str(candidate.get("id") or candidate.get("recovery_id") or "").strip()
            if protocol_id and candidate_id and protocol_id != candidate_id:
                continue
            if not protocol_id and not protocol_matches_target(candidate, target):
                continue
            declared_capability_id = str(
                capability_protocol.get("capability_id") or capability_protocol.get("id") or ""
            ).strip()
            return {
                "protocol_id": protocol_id or candidate_id,
                "capability_id": capability_id or declared_capability_id or None,
                "source": "capability_protocol",
                "protocol_source": context.protocol_source,
            }
    return {
        "protocol_id": protocol_id,
        "capability_id": capability_id or None,
        "source": "capability_protocol" if capability_id else "swarm_plan_recovery_protocol",
        "protocol_source": context.protocol_source,
    }


def protocol_matches_target(protocol: dict[str, Any], target: str) -> bool:
    targets = protocol.get("targets") if isinstance(protocol.get("targets"), list) else []
    if not targets:
        return True
    return any(
        canonical_target(item.get("canonical_target") or item.get("target") if isinstance(item, dict) else item) == target
        for item in targets
    )


def recruitment_score(
    agent: dict[str, Any],
    *,
    allowed_roles: set[str],
    allowed_tags: set[str],
    required_tools: set[str],
) -> tuple[float, list[str]]:
    terms = policy_terms(agent)
    score = 0.0
    reasons: list[str] = []
    if allowed_roles and terms & allowed_roles:
        score += 0.55
        reasons.append("allowed_role")
    if allowed_tags and terms & allowed_tags:
        score += 0.45
        reasons.append("allowed_capability_tag")
    if required_tools and terms & required_tools:
        score += 0.2
        reasons.append("required_tool_match")
    if not allowed_roles and not allowed_tags and not required_tools:
        score += 0.1
        reasons.append("default_recovery_candidate")
    return score, reasons


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


def dedupe_agent_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for row in rows:
        key = (row.get("agent"), row.get("protocol_id"), row.get("capability_id"))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def dedupe_protocol_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for row in rows:
        key = (row.get("protocol_id"), row.get("capability_id"))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output
