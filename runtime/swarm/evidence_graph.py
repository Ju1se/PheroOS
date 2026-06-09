from __future__ import annotations

from typing import Any

from runtime.swarm.agent_decisions import runtime_agent_decision, runtime_agent_decision_source
from runtime.swarm.authority import can_create_blocker, can_create_fact, signal_authority_level
from runtime.swarm.data_gate_permissions import (
    blocked_conclusion_permissions,
    data_gate_conclusion_permission,
    effective_conclusion_permissions,
    permission_label,
    publication_conclusion_permission_target,
)
from runtime.swarm.evidence_contract import build_writer_evidence_contract
from runtime.swarm.target_registry import canonical_target, candidate_target, target_kind


def build_evidence_graph(state: dict[str, Any]) -> dict[str, Any]:
    """Build a dashboard/model-safe graph of facts, proposals, blockers, and output permissions."""

    signals = collect_signals(state)
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    decision = runtime_agent_decision(state)
    decision_source = runtime_agent_decision_source(state)
    review = state.get("review") if isinstance(state.get("review"), dict) else {}

    signal_nodes = [signal_to_node(signal) for signal in signals]
    fact_nodes = [node for node in signal_nodes if node["governance_status"] in {"fact", "blocker"}]
    proposal_nodes = [node for node in signal_nodes if node["governance_status"] == "proposal"]
    blocker_nodes = [node for node in signal_nodes if node["governance_status"] == "blocker"]
    metric_nodes = metric_evidence_nodes(registry)
    permission_nodes = output_permission_nodes(data_gate)
    candidate_nodes = candidate_decision_nodes(quorum, blocker_nodes)
    claim_nodes = decision_claim_nodes(
        decision,
        data_gate,
        quorum,
        state,
        decision_source=decision_source,
    )
    review_nodes = review_issue_nodes(review)
    edges = evidence_edges(
        signal_nodes=signal_nodes,
        metric_nodes=metric_nodes,
        permission_nodes=permission_nodes,
        candidate_nodes=candidate_nodes,
        claim_nodes=claim_nodes,
        review_nodes=review_nodes,
    )
    summary = graph_summary(
        fact_nodes=fact_nodes,
        proposal_nodes=proposal_nodes,
        blocker_nodes=blocker_nodes,
        candidate_nodes=candidate_nodes,
        permission_nodes=permission_nodes,
        review_nodes=review_nodes,
    )
    graph = {
        "schema_version": "pheroos.evidence_graph.v1",
        "run_id": state.get("run_id"),
        "facts": fact_nodes,
        "proposals": proposal_nodes,
        "blockers": blocker_nodes,
        "metrics": metric_nodes,
        "output_permissions": permission_nodes,
        "candidate_decisions": candidate_nodes,
        "decision_claims": claim_nodes,
        "review_findings": review_nodes,
        "edges": edges,
        "summary": summary,
        "writer_contract": writer_contract(permission_nodes, blocker_nodes, proposal_nodes),
    }
    graph["writer_contract"] = {
        **graph["writer_contract"],
        **build_writer_evidence_contract({**state, "evidence_graph": graph}, graph),
    }
    return graph


def collect_signals(state: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    snapshot = state.get("pheromone_field_snapshot") if isinstance(state.get("pheromone_field_snapshot"), dict) else {}
    for signal in snapshot.get("signals") or []:
        add_signal(output, seen, signal)
    for signal in state.get("constraint_signals") or []:
        add_signal(output, seen, signal)
    for signal in state.get("stop_signals") or []:
        add_signal(output, seen, signal)
    return output


def add_signal(output: list[dict[str, Any]], seen: set[str], signal: Any) -> None:
    if not isinstance(signal, dict):
        return
    signal_id = str(signal.get("id") or f"{signal.get('type')}:{signal.get('target')}:{len(output)}")
    if signal_id in seen:
        return
    seen.add(signal_id)
    output.append(signal)


def signal_to_node(signal: dict[str, Any]) -> dict[str, Any]:
    source_module = str(signal.get("source_module") or "")
    verification = str(signal.get("verification_state") or "")
    blocking = bool(signal.get("blocking"))
    raw_target = str(signal.get("target") or "")
    canonical = canonical_target(raw_target)
    governance_status = "proposal"
    if blocking and can_create_blocker(signal):
        governance_status = "blocker"
    elif verification in {"verified", "blocking"} and can_create_fact(signal):
        governance_status = "fact"
    elif verification == "rejected":
        governance_status = "rejected"
    return {
        "id": str(signal.get("id") or ""),
        "kind": "signal",
        "signal_type": str(signal.get("type") or ""),
        "target": raw_target,
        "canonical_target": canonical,
        "target_kind": target_kind(canonical),
        "content": str(signal.get("content") or ""),
        "source_module": source_module or None,
        "source_agent": signal.get("source_agent"),
        "verification_state": verification or "unverified",
        "authority_level": signal_authority_level(signal),
        "strength": signal.get("strength"),
        "confidence": signal.get("confidence"),
        "blocking": blocking,
        "governance_status": governance_status,
        "metadata": safe_metadata(signal.get("metadata")),
    }


def safe_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    blocked = {"api_key", "password", "secret", "token", "authorization"}
    return {str(key): ("[redacted]" if str(key).lower() in blocked else item) for key, item in value.items()}


def metric_evidence_nodes(registry: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = registry.get("metrics") if isinstance(registry.get("metrics"), list) else []
    nodes: list[dict[str, Any]] = []
    for index, metric in enumerate(metrics[:24]):
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("name") or metric.get("metric") or "").strip()
        if not name:
            continue
        period = str(metric.get("period") or metric.get("fiscal_period") or metric.get("date") or "")
        node_id = f"metric:{name}:{period or index}"
        nodes.append(
            {
                "id": node_id,
                "kind": "metric",
                "canonical_target": canonical_target(f"metric:{name}"),
                "name": name,
                "period": period or None,
                "value": metric.get("value"),
                "unit": metric.get("unit"),
                "formula": metric.get("formula"),
                "source": metric.get("source") or metric.get("source_table") or "metric_registry",
                "verification_state": "verified",
                "authority_level": 4,
            }
        )
    return nodes


def output_permission_nodes(data_gate: dict[str, Any]) -> list[dict[str, Any]]:
    if not data_gate or str(data_gate.get("status") or "").lower() in {"", "skipped"}:
        return []
    nodes: list[dict[str, Any]] = []
    for permission in effective_conclusion_permissions(data_gate):
        nodes.append(permission_node(permission["target"], permission["allowed"], data_gate, permission["label"]))
    return nodes


def permission_node(target: str, allowed: Any, data_gate: dict[str, Any], label: str) -> dict[str, Any]:
    allowed_bool = bool(allowed) if allowed is not None else False
    return {
        "id": f"permission:{target}",
        "kind": "output_permission",
        "target": target,
        "canonical_target": canonical_target(target),
        "label": label,
        "allowed": allowed_bool,
        "status": "allowed" if allowed_bool else "blocked",
        "source_module": "data_gate",
        "verification_state": "verified",
        "authority_level": 5,
        "reason": data_gate.get("next_action") or data_gate.get("status") or "data_gate",
    }


def candidate_decision_nodes(quorum: dict[str, Any], blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = quorum.get("candidates") if isinstance(quorum.get("candidates"), list) else []
    blocker_targets = sorted({node["canonical_target"] for node in blockers})
    nodes: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("id") or "candidate")
        candidate_id = str(item.get("id") or candidate_target(label))
        nodes.append(
            {
                "id": candidate_id,
                "kind": "candidate",
                "label": label,
                "canonical_target": candidate_target(candidate_id),
                "support_score": item.get("support_score"),
                "oppose_score": item.get("oppose_score"),
                "risk_score": item.get("risk_score"),
                "evidence_score": item.get("evidence_score"),
                "stop_score": item.get("stop_score"),
                "committed": bool(item.get("committed")),
                "blocked": bool(item.get("blocked")),
                "reason": item.get("reason"),
                "blocked_by": blocker_targets if item.get("blocked") else [],
            }
        )
    return nodes


def decision_claim_nodes(
    decision: dict[str, Any],
    data_gate: dict[str, Any],
    quorum: dict[str, Any],
    state: dict[str, Any],
    *,
    decision_source: str,
) -> list[dict[str, Any]]:
    if not decision:
        return []
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    blocked_outputs = {item["canonical_target"] for item in blocked_conclusion_permissions(data_gate)}
    source_module = decision_claim_source_module(decision, state, decision_source=decision_source)
    claims = []
    for key in ("decision", "final_decision", "core_thesis", "main_risk", "invalidation_point"):
        value = decision.get(key)
        if value:
            target = decision_claim_target(key, committed, blocked_outputs)
            output_allowed = decision_claim_output_allowed(target, data_gate, blocked_outputs, state)
            claims.append(
                {
                    "id": f"claim:{key}",
                    "kind": "claim",
                    "claim_type": key,
                    "canonical_target": target,
                    "content": str(value),
                    "source_module": source_module,
                    "decision_source": decision_source,
                    "verification_state": "contested" if output_allowed else "unverified",
                    "output_allowed": output_allowed,
                    "committed_candidate": committed.get("label"),
                }
            )
    for index, item in enumerate(decision.get("key_evidence") or []):
        publication_target = publication_conclusion_permission_target(data_gate)
        output_allowed = decision_claim_output_allowed(publication_target, data_gate, blocked_outputs, state)
        claims.append(
            {
                "id": f"claim:key_evidence:{index}",
                "kind": "claim",
                "claim_type": "key_evidence",
                "canonical_target": canonical_target(publication_target),
                "content": str(item),
                "source_module": source_module,
                "decision_source": decision_source,
                "verification_state": "unverified",
                "output_allowed": output_allowed,
                "committed_candidate": committed.get("label"),
            }
        )
    return claims


def decision_claim_output_allowed(
    target: str,
    data_gate: dict[str, Any],
    blocked_outputs: set[str],
    state: dict[str, Any],
) -> bool:
    canonical = canonical_target(target)
    target_permission = data_gate_conclusion_permission(data_gate, canonical)
    if target_permission is not None:
        return bool(target_permission)

    publication_permission = data_gate_conclusion_permission(data_gate, publication_conclusion_permission_target(data_gate))
    if publication_permission is not None:
        return bool(publication_permission) and canonical not in blocked_outputs

    if protocol_backed_data_gate(state, data_gate):
        return False

    return canonical not in blocked_outputs


def protocol_backed_data_gate(state: dict[str, Any], data_gate: dict[str, Any]) -> bool:
    if not data_gate or str(data_gate.get("status") or "").lower() in {"", "skipped"}:
        return False
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    if str(swarm_plan.get("protocol_source") or "").strip() != "capability_manifest":
        return False
    protocols = swarm_plan.get("capability_protocols") if isinstance(swarm_plan.get("capability_protocols"), list) else []
    if not protocols:
        return True
    return any(isinstance(item, dict) and not item.get("generated_legacy_protocol") for item in protocols)


def decision_claim_target(claim_type: str, committed: dict[str, Any], blocked_outputs: set[str]) -> str:
    if claim_type in {"decision", "final_decision"}:
        for key in ("target", "canonical_target"):
            if committed.get(key):
                return canonical_target(committed.get(key))
        if blocked_outputs:
            return sorted(blocked_outputs)[0]
    return f"claim:{claim_type}"


def decision_claim_source_module(
    decision: dict[str, Any],
    state: dict[str, Any],
    *,
    decision_source: str,
) -> str:
    explicit_source = first_non_empty_string(
        decision.get("source_module"),
        decision.get("source"),
        nested_string(decision, ("metadata", "source_module")),
        nested_string(decision, ("metadata", "workflow_source")),
    )
    if explicit_source:
        return explicit_source

    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    workflow = state.get("domain_workflow") if isinstance(state.get("domain_workflow"), dict) else {}
    if not workflow:
        workflow = metadata.get("domain_workflow") if isinstance(metadata.get("domain_workflow"), dict) else {}
    workflow_source = workflow_source_module(workflow)
    if workflow_source:
        return workflow_source

    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    selected_capability = first_non_empty_string(os_plan.get("selected_capability_id"), os_plan.get("capability_id"))
    if selected_capability:
        return f"capability:{selected_capability}"

    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    plan_source = swarm_plan_source_module(swarm_plan)
    if plan_source:
        return plan_source

    routing = state.get("workflow_routing") if isinstance(state.get("workflow_routing"), dict) else {}
    graph_mode = first_non_empty_string(routing.get("graph_mode"))
    if graph_mode:
        return f"workflow:{graph_mode}"

    if decision_source == "agent_decision":
        return "agent_decision"

    return "legacy:investment_committee"


def workflow_source_module(workflow: dict[str, Any]) -> str:
    capability_id = first_non_empty_string(workflow.get("capability_id"))
    if capability_id:
        return f"capability:{capability_id}"
    workflow_id = first_non_empty_string(workflow.get("workflow_id"), workflow.get("id"))
    if workflow_id:
        return f"workflow:{workflow_id}"
    graph_mode = first_non_empty_string(workflow.get("graph_mode"))
    if graph_mode:
        return f"workflow:{graph_mode}"
    return ""


def swarm_plan_source_module(swarm_plan: dict[str, Any]) -> str:
    for item in swarm_plan.get("workflow_entrypoints") or []:
        if not isinstance(item, dict):
            continue
        capability_id = first_non_empty_string(item.get("capability_id"))
        if capability_id:
            return f"capability:{capability_id}"
        workflow = first_non_empty_string(item.get("workflow"))
        if workflow:
            return f"workflow:{workflow}"
    for item in swarm_plan.get("capability_protocols") or []:
        if not isinstance(item, dict):
            continue
        capability_id = first_non_empty_string(item.get("capability_id"))
        if capability_id:
            return f"capability:{capability_id}"
    return ""


def nested_string(mapping: dict[str, Any], path: tuple[str, ...]) -> str:
    value: Any = mapping
    for key in path:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return first_non_empty_string(value)


def first_non_empty_string(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def review_issue_nodes(review: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for key in ("issues", "overclaims", "data_errors", "citation_gaps"):
        values = review.get(key) if isinstance(review.get(key), list) else []
        for index, item in enumerate(values):
            nodes.append(
                {
                    "id": f"review:{key}:{index}",
                    "kind": "review_finding",
                    "finding_type": key,
                    "content": str(item),
                    "source_module": "critic",
                    "verification_state": "contested",
                    "authority_level": 3,
                }
            )
    return nodes


def evidence_edges(
    *,
    signal_nodes: list[dict[str, Any]],
    metric_nodes: list[dict[str, Any]],
    permission_nodes: list[dict[str, Any]],
    candidate_nodes: list[dict[str, Any]],
    claim_nodes: list[dict[str, Any]],
    review_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    blockers = [node for node in signal_nodes if node["governance_status"] == "blocker"]
    for permission in permission_nodes:
        for blocker in blockers:
            if permission_blocked_by_signal(permission, blocker):
                edges.append({"source": blocker["id"], "target": permission["id"], "relation": "blocks"})
    for candidate in candidate_nodes:
        for blocker in blockers:
            if candidate.get("blocked"):
                edges.append({"source": blocker["id"], "target": candidate["id"], "relation": "blocks_candidate"})
    for claim in claim_nodes:
        for metric in metric_nodes[:16]:
            if metric_supports_claim(metric, claim):
                edges.append({"source": metric["id"], "target": claim["id"], "relation": "available_evidence"})
        for finding in review_nodes:
            edges.append({"source": finding["id"], "target": claim["id"], "relation": "challenges"})
    return edges


def permission_blocked_by_signal(permission: dict[str, Any], blocker: dict[str, Any]) -> bool:
    if blocker["canonical_target"] == permission["canonical_target"]:
        return True
    return permission.get("allowed") is False and target_kind(blocker.get("canonical_target")) == "gate"


def metric_supports_claim(metric: dict[str, Any], claim: dict[str, Any]) -> bool:
    content = normalize_evidence_text(claim.get("content"))
    if not content:
        return False
    name = str(metric.get("name") or "").strip()
    if not name:
        return False
    aliases = metric_aliases(name)
    value = metric.get("value")
    if value is not None and normalize_evidence_text(value) in content:
        return True
    return any(alias in content for alias in aliases)


def metric_aliases(name: str) -> list[str]:
    normalized = normalize_evidence_text(name.replace("_", " "))
    aliases = {normalized}
    compact = name.strip().lower()
    common = {
        "free_cash_flow": ["free cash flow", "fcf"],
        "fcf": ["free cash flow", "fcf"],
        "revenue": ["revenue", "sales"],
        "sale": ["revenue", "sales"],
        "gross_margin": ["gross margin"],
        "operating_margin": ["operating margin"],
        "net_margin": ["net margin"],
        "roic": ["roic", "return on invested capital"],
        "roe": ["roe", "return on equity"],
        "debt": ["debt", "leverage"],
        "capex": ["capex", "capital expenditure", "capital expenditures"],
    }
    aliases.update(common.get(compact, []))
    return [alias for alias in aliases if alias]


def normalize_evidence_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def graph_summary(
    *,
    fact_nodes: list[dict[str, Any]],
    proposal_nodes: list[dict[str, Any]],
    blocker_nodes: list[dict[str, Any]],
    candidate_nodes: list[dict[str, Any]],
    permission_nodes: list[dict[str, Any]],
    review_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    committed = next((item for item in candidate_nodes if item.get("committed")), None)
    return {
        "fact_count": len(fact_nodes),
        "proposal_count": len(proposal_nodes),
        "blocker_count": len(blocker_nodes),
        "candidate_count": len(candidate_nodes),
        "review_finding_count": len(review_nodes),
        "committed_candidate": committed.get("label") if committed else None,
        "blocked_outputs": [item["canonical_target"] for item in permission_nodes if not item.get("allowed")],
        "allowed_outputs": [item["canonical_target"] for item in permission_nodes if item.get("allowed")],
    }


def writer_contract(
    permission_nodes: list[dict[str, Any]],
    blocker_nodes: list[dict[str, Any]],
    proposal_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    blocked_outputs = [item["canonical_target"] for item in permission_nodes if not item.get("allowed")]
    allowed_outputs = [item["canonical_target"] for item in permission_nodes if item.get("allowed")]
    return {
        "rule": "Writer may express only Data Gate / Evidence Graph allowed conclusions and must not promote proposals into facts.",
        "allowed_outputs": allowed_outputs,
        "blocked_outputs": blocked_outputs,
        "blocking_reasons": [node["content"] for node in blocker_nodes[:8]],
        "proposal_count": len(proposal_nodes),
        "unverified_signal_policy": "unverified or contested agent signals may be described as agent proposals, not as verified facts",
    }
