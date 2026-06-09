from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from runtime.agent_metrics import metric_started_at, record_agent_metric
from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry
from runtime.state import AgentState
from runtime.swarm.protocol import capability_protocol_bundle
from runtime.swarm.recovery_engine import build_recovery_trace, protocol_targets, select_recovery_agents
from runtime.tool_names import (
    APPROVED_SOURCE_FETCH_TOOL_NAME,
    FETCH_URL_TOOL_NAME,
    PROVIDER_WEB_SEARCH_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
)
from runtime.workflows.domain_execution import (
    attach_domain_workflow_stop_signals,
    available_tool_names,
    domain_workflow_from_state,
    merge_metadata,
    workflow_agents_by_type,
)
from runtime.workflows.legacy_guardrails import legacy_source_candidate_only_caveat
from runtime.workflows.source_tool_helpers import (
    FETCH_TOOL_NAMES,
    SEARCH_TOOL_NAMES,
)


def augment_orchestration_result(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    execution_plan = build_execution_plan(
        task=str(state.get("task") or result.get("translated_task") or ""),
        available_tools=available_tool_names(result),
        preferred_query=str(result.get("english_search_query") or state.get("task") or ""),
    )
    trace = build_workflow_trace(state, workflow=workflow, execution_plan=execution_plan)
    updated = {**result, "plan": execution_plan, "domain_workflow": trace}
    return merge_metadata(updated, domain_workflow=trace)


def build_execution_plan(*, task: str, available_tools: set[str], preferred_query: str) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "id": "claim-decomposition",
            "title": "Claim decomposition",
            "action": "Decompose the task or draft into atomic claims before retrieval.",
            "tool_calls": [],
        }
    ]
    search_tool = (
        PROVIDER_WEB_SEARCH_TOOL_NAME
        if PROVIDER_WEB_SEARCH_TOOL_NAME in available_tools
        else WEB_SEARCH_TOOL_NAME
    )
    if search_tool in available_tools:
        steps.append(
            {
                "id": "source-retrieval",
                "title": "Source retrieval",
                "action": "Retrieve candidate sources for the atomic claims. Tool execution remains permission-gated.",
                "tool_calls": [{"name": search_tool, "args": {"query": preferred_query or task, "max_results": 5}}],
            }
        )
    steps.extend(
        [
            {
                "id": "source-quality-and-citation-audit",
                "title": "Source quality and citation audit",
                "action": "Score source authority and verify that each citation supports the exact attached claim.",
                "tool_calls": [],
            },
            {
                "id": "contradiction-map",
                "title": "Contradiction map",
                "action": "Find conflicting evidence, stale facts, unsupported claims, and unresolved gaps.",
                "tool_calls": [],
            },
        ]
    )
    return steps


async def research_agent_node(runtime: Any, state: AgentState) -> AgentState:
    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    try:
        content, model_used, fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.research_agent,
            fallback_model=runtime.model_config.research_agent_fallback,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Evidence Research Agent. Do not synthesize beyond evidence. Decompose claims, "
                        "identify source candidates, rate source quality, map contradictions, and mark unsupported "
                        "claims. Return strict JSON with keys: status, sources, key_facts, evidence_gaps, "
                        "reliability, source_grounding."
                    ),
                },
                {"role": "user", "content": graph_runtime.research_context(state)},
            ],
        )
        result = {
            "research_brief": graph_runtime.parse_research_brief(
                content,
                grounding=graph_runtime.describe_source_grounding(state),
            )
        }
        result = attach_evidence_node_outputs(state, result)
        record_agent_metric(
            agent="evidence_research_agent",
            model=model_used,
            started_at=started_at,
            status="completed_with_fallback" if fallback_reason else "completed",
            failure_reason=fallback_reason,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        record_agent_metric(
            agent="evidence_research_agent",
            model=runtime.model_config.research_agent,
            started_at=started_at,
            status="completed_with_model_failure",
            failure_reason=exc,
        )
        return {
            "research_brief": graph_runtime.failed_research_brief(
                exc,
                grounding=graph_runtime.describe_source_grounding(state),
            )
        }


def build_workflow_trace(
    state: dict[str, Any],
    *,
    workflow: dict[str, Any],
    execution_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "workflow_id": workflow.get("workflow_id") or "evidence-research",
        "graph_mode": "evidence_research",
        "domain_nodes": workflow.get("ordered_nodes") or [],
        "graph_nodes": workflow.get("graph_nodes") or [],
        "agents": workflow_agents_by_type(state, "evidence_research_member"),
        "required_gates": workflow.get("required_gates") or [],
        "execution_plan": execution_plan,
        "node_outputs": build_evidence_node_outputs(state, research_brief={}),
        "guardrails": [
            "writer cannot use unverified citations as facts",
            "declared citation audit gates can block unsupported citation use",
            "contradictions must be surfaced as contested evidence",
            "external sources remain unverified until evidence stewardship accepts them",
        ],
        "writer_policy": workflow.get("writer_policy"),
    }


def augment_execution_result(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    workflow = dict(domain_workflow_from_state(state))
    node_outputs = dict(workflow.get("node_outputs") if isinstance(workflow.get("node_outputs"), dict) else {})
    execution_state = {**state, "execution_log": result.get("execution_log", state.get("execution_log", []))}
    research = result.get("research_brief") if isinstance(result.get("research_brief"), dict) else {}
    node_outputs.update(build_evidence_node_outputs(execution_state, research_brief=research))
    workflow["node_outputs"] = node_outputs
    workflow["claim_evidence_graph"] = node_outputs.get("literature_evidence_steward", {})
    workflow["contested_claims"] = node_outputs.get("contradiction_mapper", {}).get("contested_claims", [])
    workflow["gate_status"] = evidence_gate_status(node_outputs)
    updated = {**result, "domain_workflow": workflow}
    return attach_domain_workflow_stop_signals(state, merge_metadata(updated, domain_workflow=workflow))


def attach_evidence_node_outputs(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    workflow = dict(domain_workflow_from_state({**state, **result}))
    research = result.get("research_brief") if isinstance(result.get("research_brief"), dict) else {}
    node_outputs = dict(workflow.get("node_outputs") if isinstance(workflow.get("node_outputs"), dict) else {})
    node_outputs.update(build_evidence_node_outputs(state, research_brief=research))
    workflow["node_outputs"] = node_outputs
    workflow["claim_evidence_graph"] = node_outputs.get("literature_evidence_steward", {})
    workflow["contested_claims"] = node_outputs.get("contradiction_mapper", {}).get("contested_claims", [])
    workflow["gate_status"] = evidence_gate_status(node_outputs)
    updated = {**result, "domain_workflow": workflow}
    return attach_domain_workflow_stop_signals(state, merge_metadata(updated, domain_workflow=workflow))


def build_evidence_node_outputs(state: dict[str, Any], *, research_brief: dict[str, Any]) -> dict[str, Any]:
    claims = claim_decomposition_node(state, research_brief=research_brief)
    retrieval = source_retrieval_node(state, execution_log=state.get("execution_log", []))
    recovery = evidence_recovery_node(state=state, retrieval=retrieval, execution_log=state.get("execution_log", []))
    quality = source_quality_rater_node(research_brief=research_brief, retrieval=retrieval)
    steward = literature_evidence_steward_node(claims=claims, research_brief=research_brief, quality=quality)
    citation = citation_auditor_node(steward=steward, quality=quality)
    contradiction = contradiction_mapper_node(steward=steward, research_brief=research_brief)
    return {
        "claim_decomposition": claims,
        "source_retrieval": retrieval,
        "evidence_recovery": recovery,
        "source_quality_rater": quality,
        "literature_evidence_steward": steward,
        "citation_auditor": citation,
        "contradiction_mapper": contradiction,
    }


def claim_decomposition_node(state: dict[str, Any], *, research_brief: dict[str, Any]) -> dict[str, Any]:
    facts = research_brief.get("key_facts") if isinstance(research_brief.get("key_facts"), list) else []
    if facts:
        claims = [{"claim_id": f"claim-{index + 1:03d}", "claim": str(fact), "claim_type": "fact"} for index, fact in enumerate(facts[:10])]
    else:
        claims = [{"claim_id": "claim-001", "claim": str(state.get("task") or ""), "claim_type": "research_question"}]
    return {"status": "completed", "claims": claims}


def source_retrieval_node(state: dict[str, Any], *, execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    candidates_by_url: dict[str, dict[str, Any]] = {}
    fetches_by_url: dict[str, dict[str, Any]] = {}
    fetch_attempts: list[dict[str, Any]] = []
    for entry in execution_log if isinstance(execution_log, list) else []:
        if not isinstance(entry, dict):
            continue
        for call in entry.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("name") or "")
            result = call.get("result") if isinstance(call, dict) else {}
            data = result.get("data") if isinstance(result, dict) else {}
            if tool_name in SEARCH_TOOL_NAMES:
                candidates = data.get("results") if isinstance(data, dict) else []
                for candidate in candidates if isinstance(candidates, list) else []:
                    url = str(candidate.get("url") or "").strip()
                    normalized = normalize_source_url(url)
                    if not normalized:
                        continue
                    candidates_by_url.setdefault(
                        normalized,
                        {
                            "title": candidate.get("title") or candidate.get("name") or "source",
                            "url": url,
                            "snippet": candidate.get("snippet") or "",
                            "source_type": "provider_search_candidate" if tool_name == PROVIDER_WEB_SEARCH_TOOL_NAME else "search_candidate",
                            "retrieval_tool": tool_name,
                            "verified_text_available": False,
                        },
                    )
            elif tool_name in FETCH_TOOL_NAMES:
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                url = str(args.get("url") or (data.get("url") if isinstance(data, dict) else "") or "").strip()
                normalized = normalize_source_url(url)
                attempt = {
                    "tool": tool_name,
                    "url": url,
                    "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
                    "error": result.get("error") if isinstance(result, dict) else None,
                }
                fetch_attempts.append(attempt)
                if not normalized or not attempt["ok"] or not isinstance(data, dict):
                    continue
                try:
                    word_count = int(data.get("word_count") or 0)
                except (TypeError, ValueError):
                    word_count = 0
                fetches_by_url[normalized] = {
                    "title": data.get("title") or candidates_by_url.get(normalized, {}).get("title") or "source",
                    "url": url,
                    "source_type": "full_text_retrieved",
                    "retrieval_tool": candidates_by_url.get(normalized, {}).get("retrieval_tool"),
                    "fetch_tool": tool_name,
                    "verified_text_available": word_count > 0,
                    "word_count": word_count,
                    "text_quality": data.get("text_quality"),
                }
    for normalized, fetched in fetches_by_url.items():
        base = candidates_by_url.get(normalized, {})
        candidates_by_url[normalized] = {**base, **fetched}
    sources = list(candidates_by_url.values())
    full_text_count = sum(1 for source in sources if source.get("verified_text_available"))
    return {
        "status": "full_text_retrieved" if full_text_count else "candidate_sources_retrieved" if sources else "pending_or_not_run",
        "sources": sources[:10],
        "candidate_count": len(sources),
        "full_text_count": full_text_count,
        "fetch_attempts": fetch_attempts,
        "needs_recovery": bool(sources and not full_text_count),
        "conclusion_allowed": False,
    }


def evidence_recovery_node(
    *,
    retrieval: dict[str, Any],
    execution_log: list[dict[str, Any]],
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_count = int(retrieval.get("candidate_count") or 0)
    full_text_count = int(retrieval.get("full_text_count") or 0)
    attempts = retrieval.get("fetch_attempts") if isinstance(retrieval.get("fetch_attempts"), list) else []
    approved_attempts = [
        item
        for item in attempts
        if isinstance(item, dict) and item.get("tool") == APPROVED_SOURCE_FETCH_TOOL_NAME
    ]
    arbitrary_fetch_failures = [
        item
        for item in attempts
        if isinstance(item, dict)
        and item.get("tool") == FETCH_URL_TOOL_NAME
        and item.get("ok") is False
        and "network:arbitrary" in str(item.get("error") or "")
    ]
    recovery_trace = build_recovery_trace(
        state or {},
        target="research:source_retrieval",
        context={
            "candidate_count": candidate_count,
            "full_text_count": full_text_count,
            "fetch_attempts": attempts,
            "needs_recovery": bool(retrieval.get("needs_recovery")),
        },
    )
    recruited_agents = recruited_agents_for_recovery(
        state or {},
        target="research:source_retrieval",
        recovery_trace=recovery_trace,
    )
    if full_text_count:
        status = "resolved_after_recruitment" if approved_attempts else "resolved"
        blocking = False
        action = "full_text_available"
    elif candidate_count and approved_attempts:
        status = "blocked_after_recovery"
        blocking = True
        action = "approved_fetch_failed"
    elif candidate_count:
        status = "recruitment_required"
        blocking = False
        action = "retry_with_approved_source_fetch"
    else:
        status = "no_source_candidates"
        blocking = True
        action = "rerun_source_retrieval"
    return {
        "status": status,
        "blocking": blocking,
        "recruited_agents": recruited_agents if candidate_count else recruited_agents[:1],
        "recruitment_source": recruitment_source(
            recovery_trace,
            recruited_agents,
            state=state or {},
            target="research:source_retrieval",
        ),
        "recovery_protocol_id": (
            (recovery_trace.get("selected_protocol") or {}).get("id")
            if isinstance(recovery_trace.get("selected_protocol"), dict)
            else None
        ),
        "recovery_trace": recovery_trace,
        "recovery_actions": [action],
        "candidate_count": candidate_count,
        "full_text_count": full_text_count,
        "approved_source_fetch_attempts": len(approved_attempts),
        "permission_gaps": ["network:arbitrary"] if arbitrary_fetch_failures and not approved_attempts else [],
        "principle": "PheroOS recruits recovery agents and approved-source fetch before emitting an evidence stop-signal.",
    }


def source_quality_rater_node(*, research_brief: dict[str, Any], retrieval: dict[str, Any]) -> dict[str, Any]:
    sources = retrieval.get("sources") if isinstance(retrieval.get("sources"), list) else []
    rated = []
    for source in sources:
        url = str(source.get("url") or "")
        source_type = "official" if ".gov" in url or ".edu" in url else source.get("source_type", "retrieved")
        has_full_text = bool(source.get("verified_text_available"))
        if source_type == "official" and has_full_text:
            score = 0.9
        elif has_full_text:
            score = 0.72
        elif source_type == "official":
            score = 0.62
        else:
            score = 0.45
        rated.append({**source, "source_type": source_type, "quality_score": score})
    if not rated:
        source_grounding = research_brief.get("source_grounding") or research_brief.get("status")
        rated = [{"source_id": "research_brief", "source_type": source_grounding or "unknown", "quality_score": 0.4}]
    return {"status": "rated", "sources": rated}


def literature_evidence_steward_node(
    *,
    claims: dict[str, Any],
    research_brief: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    sources = quality.get("sources") if isinstance(quality.get("sources"), list) else []
    primary_source = sources[0] if sources else {"source_id": "missing", "quality_score": 0}
    verified_sources = [source for source in sources if isinstance(source, dict) and source.get("verified_text_available")]
    gaps = research_brief.get("evidence_gaps") if isinstance(research_brief.get("evidence_gaps"), list) else []
    links = []
    for claim in claims.get("claims", []):
        if gaps:
            support_status = "unsupported"
            caveat = "Evidence gaps remain; do not present as confirmed fact."
        elif verified_sources:
            support_status = "verified_source_available"
            caveat = "Verified source text is available; still cite exact passages carefully."
        else:
            support_status = "source_candidate_only"
            caveat = legacy_source_candidate_only_caveat()
        links.append(
            {
                **claim,
                "support_status": support_status,
                "sources": [primary_source],
                "required_caveat": caveat,
            }
        )
    return {"status": "linked", "links": links, "evidence_gaps": gaps}


def citation_auditor_node(*, steward: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    links = steward.get("links") if isinstance(steward.get("links"), list) else []
    unsupported = [link for link in links if link.get("support_status") == "unsupported"]
    low_quality = [
        source
        for source in quality.get("sources", [])
        if isinstance(source, dict) and float(source.get("quality_score") or 0) < 0.5
    ]
    source_candidates = [
        source for source in quality.get("sources", []) if isinstance(source, dict) and source.get("url")
    ]
    no_verified_source_text = bool(source_candidates) and not any(source.get("verified_text_available") for source in source_candidates)
    blocking = bool(unsupported) or no_verified_source_text
    return {
        "status": "blocked" if blocking else "warn" if low_quality else "passed",
        "blocking": blocking,
        "unsupported_claims": [item.get("claim_id") for item in unsupported],
        "verification_gaps": ["no full-text source available after recovery"] if no_verified_source_text else [],
        "low_quality_sources": low_quality,
    }


def contradiction_mapper_node(*, steward: dict[str, Any], research_brief: dict[str, Any]) -> dict[str, Any]:
    gaps = research_brief.get("evidence_gaps") if isinstance(research_brief.get("evidence_gaps"), list) else []
    links = steward.get("links") if isinstance(steward.get("links"), list) else []
    contested = [link for link in links if link.get("support_status") in {"unsupported", "contradicted"}]
    return {
        "status": "contested" if contested or gaps else "no_conflict_detected",
        "contested_claims": contested,
        "unresolved_gaps": gaps,
    }


def evidence_gate_status(node_outputs: dict[str, Any]) -> dict[str, Any]:
    citation = node_outputs.get("citation_auditor") if isinstance(node_outputs.get("citation_auditor"), dict) else {}
    contradiction = node_outputs.get("contradiction_mapper") if isinstance(node_outputs.get("contradiction_mapper"), dict) else {}
    recovery = node_outputs.get("evidence_recovery") if isinstance(node_outputs.get("evidence_recovery"), dict) else {}
    blocked = bool(citation.get("blocking"))
    caveats = list(contradiction.get("unresolved_gaps", []) or [])
    caveats.extend(citation.get("verification_gaps", []) or [])
    return {
        "status": "blocked" if blocked else "warn" if contradiction.get("status") == "contested" else "passed",
        "blocked": blocked,
        "blocked_conclusions": ["confirmed factual claim"] if blocked else [],
        "required_caveats": caveats,
        "recovery_status": recovery.get("status"),
    }


def normalize_source_url(value: Any) -> str:
    parsed = urlparse(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))


def recruited_agents_for_recovery(
    state: dict[str, Any],
    *,
    target: str,
    recovery_trace: dict[str, Any] | None = None,
) -> list[str]:
    if isinstance(recovery_trace, dict):
        selected = recovery_trace.get("selected_agents") if isinstance(recovery_trace.get("selected_agents"), list) else []
        agents = [
            str(item.get("agent") or "").strip()
            for item in selected
            if isinstance(item, dict) and str(item.get("agent") or "").strip()
        ]
        if agents:
            return agents[:4]
        if recovery_trace.get("status") != "no_recovery_protocol":
            return []
    agents = allocated_recovery_agents(state, target=target)
    if agents:
        return agents
    return capability_catalog_recovery_agents(state, target=target)


def allocated_recovery_agents(state: dict[str, Any], *, target: str) -> list[str]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    allocations = swarm_plan.get("agent_allocation") if isinstance(swarm_plan.get("agent_allocation"), list) else []
    matched: list[tuple[float, str]] = []
    for allocation in allocations:
        if not isinstance(allocation, dict) or not allocation.get("activated"):
            continue
        agent = str(allocation.get("agent") or "").strip()
        if not agent:
            continue
        target_matches = allocation.get("matched_targets") if isinstance(allocation.get("matched_targets"), list) else []
        has_target_match = any(
            isinstance(item, dict)
            and str(item.get("canonical_target") or item.get("target") or "").strip() == target
            for item in target_matches
        )
        role_text = " ".join(
            str(allocation.get(key) or "")
            for key in ("agent", "name", "committee_role", "agent_type", "activation_reason")
        ).lower()
        if has_target_match or any(marker in role_text for marker in ("source", "evidence", "citation", "retrieval", "quality")):
            try:
                utility = float(allocation.get("utility") or 0)
            except (TypeError, ValueError):
                utility = 0.0
            matched.append((utility, agent))
    output = [agent for _utility, agent in sorted(matched, reverse=True)]
    if output:
        return output[:4]
    return []


def capability_catalog_recovery_agents(state: dict[str, Any], *, target: str) -> list[str]:
    manifest = capability_manifest_for_recovery(state)
    if manifest is None:
        return []
    bundle = capability_protocol_bundle([manifest.to_public_dict()])
    protocol = first_matching_recovery_protocol(bundle.get("recovery_protocols"), target=target)
    if not protocol:
        return []
    catalog = AgentRegistry(capabilities_dir=CapabilityRegistry().capabilities_dir).catalog(
        enabled_capability_ids={manifest.id}
    )
    agents = catalog.get("agents") if isinstance(catalog.get("agents"), list) else []
    if not agents:
        return []
    recovery_state = {
        **state,
        "metadata": {
            **(state.get("metadata") if isinstance(state.get("metadata"), dict) else {}),
            "agent_registry": {"agents": agents},
        },
    }
    selected = select_recovery_agents(recovery_state, protocol=protocol, target=target)
    return [
        str(item.get("agent") or "").strip()
        for item in selected
        if isinstance(item, dict) and str(item.get("agent") or "").strip()
    ][:4]


def capability_manifest_for_recovery(state: dict[str, Any]) -> Any | None:
    workflow = domain_workflow_from_state(state)
    capability_id = str(
        workflow.get("capability_id")
        or workflow.get("workflow_id")
        or "evidence-research"
    ).strip()
    registry = CapabilityRegistry()
    return registry.get(capability_id) or registry.get("evidence-research")


def first_matching_recovery_protocol(protocols: Any, *, target: str) -> dict[str, Any]:
    for protocol in protocols if isinstance(protocols, list) else []:
        if not isinstance(protocol, dict):
            continue
        targets = protocol_targets(protocol)
        if not targets or target in targets:
            return protocol
    return {}


def recruitment_source(
    recovery_trace: dict[str, Any],
    recruited_agents: list[str],
    *,
    state: dict[str, Any],
    target: str,
) -> str:
    selected = recovery_trace.get("selected_agents") if isinstance(recovery_trace.get("selected_agents"), list) else []
    if selected:
        return "recovery_engine"
    if recovery_trace.get("status") == "no_recovery_protocol":
        if recruited_agents and recruited_agents == allocated_recovery_agents(state, target=target):
            return "swarm_allocation_fallback"
        if recruited_agents and recruited_agents == capability_catalog_recovery_agents(state, target=target):
            return "capability_agent_catalog_fallback"
        return "recovery_protocol_missing"
    return "recovery_engine_no_matching_agent"
