from __future__ import annotations

from typing import Any

from runtime.swarm.agent_decisions import runtime_agent_decision, runtime_agent_decision_source
from runtime.swarm.agent_outputs import runtime_agent_outputs
from runtime.swarm.candidate_registry import (
    CandidateTemplate,
    candidate_match_keys,
    candidate_registry_from_state,
    normalized_candidate_label,
    selected_candidate_label,
)
from runtime.swarm.data_gate_permissions import is_publication_target
from runtime.swarm.legacy_quorum_targets import legacy_quorum_block_flags
from runtime.swarm.pheromone_field import field_from_state
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.target_registry import canonical_target


def build_quorum_trace(state: dict[str, Any]) -> dict[str, Any]:
    decision = runtime_agent_decision(state)
    decision_source = runtime_agent_decision_source(state)
    stop_signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    active_blockers = [signal for signal in stop_signals if isinstance(signal, dict) and is_active_blocker(signal)]
    active_blocker_targets = {canonical_target(signal.get("target")) for signal in active_blockers}
    blocked_conclusion_targets = sorted(target for target in active_blocker_targets if target.startswith("decision:"))
    decision_conclusion_blocked = any(not is_publication_target(target) for target in blocked_conclusion_targets)
    legacy_block_flags = legacy_quorum_block_flags(active_blocker_targets)

    registry = candidate_registry_from_state(state)
    candidate_templates = registry.candidates
    quorum_policy = quorum_policy_from_state(state)
    evidence_coverage = evidence_coverage_score(state, conclusion_blocked=decision_conclusion_blocked)
    source_independence = source_independence_score(state)
    unresolved_risk = unresolved_risk_score(state, active_blocker_count=len(active_blockers))
    weights = quorum_weight_inputs(quorum_policy)
    raw_selected = decision.get("final_decision") or decision.get("decision")
    selected = selected_candidate_label(raw_selected, registry)
    fallback_label = registry.fallback_candidate_label
    if fallback_label and fallback_forced_by_blockers(
        selected,
        candidate_templates,
        active_blocker_targets=active_blocker_targets,
        force_fallback_when_blocked=registry.force_fallback_when_blocked,
    ):
        selected = fallback_label

    candidates = []
    for candidate in candidate_templates:
        is_fallback = normalized_candidate_label(candidate.label) == normalized_candidate_label(fallback_label)
        stop_blocked = candidate_blocked_by_stop_signal(
            candidate,
            active_blocker_targets=active_blocker_targets,
            is_fallback=is_fallback,
        )
        stop_score = 1.0 if stop_blocked else 0.0
        selected_candidate = normalized_candidate_label(candidate.label) == normalized_candidate_label(selected)
        support_report = candidate_support_signal_report(candidate, state)
        evidence_report = candidate_evidence_graph_report(candidate, state)
        candidate_evidence_coverage = evidence_report["evidence_score"] if evidence_report["verified_edge_count"] else evidence_coverage
        candidate_source_independence = (
            evidence_report["source_independence_score"] if evidence_report["verified_edge_count"] else source_independence
        )
        support_score = candidate_support_score(
            selected=selected_candidate,
            stop_blocked=stop_blocked,
            evidence_coverage=candidate_evidence_coverage,
            source_independence=candidate_source_independence,
            source_quality=evidence_report["source_quality_score"],
            unresolved_risk=unresolved_risk,
            signal_support=support_report["support_delta"],
            agent_reliability=support_report["agent_reliability"],
            weights=weights,
        )
        evidence_score = candidate_evidence_coverage
        risk_score = candidate_risk_score(
            unresolved_risk=unresolved_risk,
            stop_score=stop_score,
            signal_oppose=support_report["oppose_score"],
            weights=weights,
        )
        candidates.append(
            {
                "id": candidate.id,
                "label": candidate.label,
                "support_score": support_score,
                "oppose_score": round(clamp01(0.25 + support_report["oppose_score"] * 0.5 + stop_score * 0.35), 3),
                "risk_score": risk_score,
                "evidence_score": evidence_score,
                "source_independence_score": candidate_source_independence,
                "source_quality_score": evidence_report["source_quality_score"],
                "evidence_graph_score": evidence_report["evidence_score"],
                "evidence_graph_edge_count": evidence_report["verified_edge_count"],
                "unresolved_risk_score": unresolved_risk,
                "support_signal_score": support_report["support_delta"],
                "support_signal_count": support_report["signal_count"],
                "agent_reliability_score": support_report["agent_reliability"],
                "stop_score": stop_score,
                "committed": normalized_candidate_label(candidate.label) == normalized_candidate_label(selected),
                "blocked": bool(stop_score),
                "reason": "blocked by stop-signal" if stop_score else "candidate remains available",
                "source": candidate.source,
            }
        )

    selected_blocked_without_fallback = bool(
        selected
        and not fallback_label
        and any(item["committed"] and item["blocked"] for item in candidates)
    )
    if selected_blocked_without_fallback:
        selected = ""
        candidates = [
            {
                **item,
                "committed": False,
                "reason": "blocked by stop-signal; no declared fallback candidate",
            }
            if item["committed"] and item["blocked"]
            else item
            for item in candidates
        ]
    committed_candidate = next((item for item in candidates if item["committed"]), None)
    sorted_scores = sorted((item["support_score"] for item in candidates), reverse=True)
    if len(sorted_scores) > 1:
        margin = round(sorted_scores[0] - sorted_scores[1], 3)
    elif sorted_scores:
        margin = sorted_scores[0]
    else:
        margin = 0.0
    return {
        "status": "committed" if committed_candidate else "blocked" if selected_blocked_without_fallback else "pending",
        "committed_candidate": committed_candidate,
        "candidates": candidates,
        "quorum_margin": margin,
        "blocking_stop_signal_count": len(active_blockers),
        "blocked_conclusion_targets": blocked_conclusion_targets,
        **legacy_block_flags,
        "candidate_source": registry.source,
        "decision_source": decision_source,
        "generated_legacy_candidate_fallback": registry.generated_legacy_candidate_fallback,
        "candidate_registry_trace": registry.trace,
        "scoring_inputs": {
            "evidence_coverage": evidence_coverage,
            "source_independence": source_independence,
            "unresolved_risk": unresolved_risk,
            "evidence_graph_source": "state.evidence_graph",
            "support_signal_source": "pheromone_field",
            "weights": weights,
        },
        "fallback_candidate": {
            "id": registry.fallback_candidate_id,
            "label": registry.fallback_candidate_label,
        }
        if registry.fallback_candidate_id and registry.fallback_candidate_label
        else None,
    }


def fallback_forced_by_blockers(
    selected: str,
    candidates: list[CandidateTemplate],
    *,
    active_blocker_targets: set[str],
    force_fallback_when_blocked: bool,
) -> bool:
    selected_candidate = next(
        (candidate for candidate in candidates if normalized_candidate_label(candidate.label) == normalized_candidate_label(selected)),
        None,
    )
    if selected_candidate is not None and candidate_has_active_blocker(selected_candidate, active_blocker_targets):
        return True
    return force_fallback_when_blocked and any(
        candidate_has_active_blocker(candidate, active_blocker_targets)
        for candidate in candidates
        if not candidate.safe_fallback
    )


def candidate_blocked_by_stop_signal(
    candidate: CandidateTemplate,
    *,
    active_blocker_targets: set[str],
    is_fallback: bool,
) -> bool:
    if is_fallback:
        return False
    return candidate_has_active_blocker(candidate, active_blocker_targets)


def candidate_has_active_blocker(candidate: CandidateTemplate, active_blocker_targets: set[str]) -> bool:
    return bool(set(candidate.blocked_by_targets) & active_blocker_targets)


def quorum_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    return swarm_plan.get("quorum_policy") if isinstance(swarm_plan.get("quorum_policy"), dict) else {}


def quorum_weight_inputs(policy: dict[str, Any]) -> dict[str, float]:
    return {
        "evidence_coverage_weight": safe_float(policy.get("evidence_coverage_weight"), 0.0),
        "source_independence_weight": safe_float(policy.get("source_independence_weight"), 0.0),
        "source_quality_weight": safe_float(policy.get("source_quality_weight"), 0.0),
        "unresolved_risk_penalty": safe_float(policy.get("unresolved_risk_penalty") or policy.get("risk_weight"), 0.0),
        "stop_signal_penalty": safe_float(policy.get("stop_signal_penalty") or policy.get("stop_signal_weight"), 0.0),
    }


def candidate_support_score(
    *,
    selected: bool,
    stop_blocked: bool,
    evidence_coverage: float,
    source_independence: float,
    source_quality: float,
    unresolved_risk: float,
    signal_support: float,
    agent_reliability: float,
    weights: dict[str, float],
) -> float:
    base = 0.72 if selected else 0.35
    if stop_blocked:
        base = min(base, 0.2)
    weighted = (
        base
        + signal_support * (0.28 + max(0.0, agent_reliability - 0.65) * 0.2)
        + weights["evidence_coverage_weight"] * (evidence_coverage - 0.5) * 0.35
        + weights["source_independence_weight"] * (source_independence - 0.5) * 0.25
        + weights["source_quality_weight"] * (source_quality - 0.5) * 0.3
        - weights["unresolved_risk_penalty"] * unresolved_risk * 0.25
        - weights["stop_signal_penalty"] * (1.0 if stop_blocked else 0.0)
    )
    return round(clamp01(weighted), 3)


def candidate_risk_score(
    *,
    unresolved_risk: float,
    stop_score: float,
    signal_oppose: float,
    weights: dict[str, float],
) -> float:
    weighted = 0.25 + unresolved_risk * 0.5 + signal_oppose * 0.35 + stop_score * (0.35 + weights["stop_signal_penalty"])
    return round(clamp01(weighted), 3)


def candidate_support_signal_report(candidate: CandidateTemplate, state: dict[str, Any]) -> dict[str, Any]:
    positive = 0.0
    negative = 0.0
    reliability_weighted = 0.0
    reliability_total = 0.0
    count = 0
    for signal in candidate_support_signals(candidate, state):
        strength = normalized_score(signal.get("strength", 0.5))
        confidence = normalized_score(signal.get("confidence", 0.5))
        reliability = agent_reliability_score(signal, state)
        weight = strength * confidence * reliability
        if weight <= 0:
            continue
        count += 1
        reliability_weighted += reliability * weight
        reliability_total += weight
        if signal_poses_candidate_support(signal):
            positive += weight
        else:
            negative += weight
    total = positive + negative
    agent_reliability = round(reliability_weighted / reliability_total, 3) if reliability_total else 0.65
    support_delta = round((positive - negative) / total, 3) if total else 0.0
    oppose_score = round(negative / total, 3) if total else 0.0
    return {
        "support_delta": support_delta,
        "oppose_score": oppose_score,
        "agent_reliability": agent_reliability,
        "signal_count": count,
    }


def candidate_support_signals(candidate: CandidateTemplate, state: dict[str, Any]) -> list[dict[str, Any]]:
    matches = candidate_match_keys(candidate)
    signals = [signal.to_dict() for signal in field_from_state(state).signals()]
    output = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        if str(signal.get("verification_state") or "") == "rejected":
            continue
        signal_type = str(signal.get("type") or "")
        if signal_type not in {"quorum", "evidence", "progress", "risk", "negative"}:
            continue
        if signal_mentions_candidate(signal, matches):
            output.append(signal)
    return output


def signal_mentions_candidate(signal: dict[str, Any], matches: set[str]) -> bool:
    metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    values = [
        signal.get("target"),
        metadata.get("candidate"),
        metadata.get("candidate_id"),
        metadata.get("candidate_label"),
        metadata.get("supports_candidate"),
        metadata.get("opposes_candidate"),
    ]
    return any(normalized_candidate_label(value) in matches for value in values if str(value or "").strip())


def signal_poses_candidate_support(signal: dict[str, Any]) -> bool:
    metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    stance = normalized_candidate_label(metadata.get("stance") or metadata.get("support") or metadata.get("vote"))
    if stance in {"oppose", "opposes", "against", "reject", "negative", "veto"}:
        return False
    return str(signal.get("type") or "") not in {"risk", "negative"}


def agent_reliability_score(signal: dict[str, Any], state: dict[str, Any]) -> float:
    metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    agent = str(signal.get("source_agent") or metadata.get("agent") or "").strip()
    if not agent:
        return 0.65
    for source in profile_sources(state):
        score = reliability_from_source(source, agent)
        if score is not None:
            return score
    return 0.65


def profile_sources(state: dict[str, Any]) -> list[Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    return [
        state.get("agent_profiles"),
        metadata.get("agent_profiles"),
        state.get("maturity_report"),
        metadata.get("maturity_report"),
    ]


def reliability_from_source(source: Any, agent: str) -> float | None:
    if isinstance(source, dict):
        if isinstance(source.get(agent), dict) and "reliability" in source[agent]:
            return normalized_score(source[agent].get("reliability"))
        if source.get("agent_id") == agent and "reliability" in source:
            return normalized_score(source.get("reliability"))
        agents = source.get("agents") if isinstance(source.get("agents"), list) else []
        for item in agents:
            if isinstance(item, dict) and str(item.get("agent") or item.get("agent_id") or "") == agent and "reliability" in item:
                return normalized_score(item.get("reliability"))
    return None


SUPPORTING_EVIDENCE_RELATIONS = {
    "available_evidence",
    "corroborates",
    "evidence_for",
    "supports",
    "supports_candidate",
    "supports_claim",
    "verifies",
}
CHALLENGING_EVIDENCE_RELATIONS = {
    "blocks",
    "blocks_candidate",
    "challenges",
    "contradicts",
    "opposes",
    "opposes_candidate",
}


def candidate_evidence_graph_report(candidate: CandidateTemplate, state: dict[str, Any]) -> dict[str, Any]:
    graph = state.get("evidence_graph") if isinstance(state.get("evidence_graph"), dict) else {}
    nodes_by_id = evidence_graph_nodes_by_id(graph)
    matches = candidate_match_keys(candidate)
    support_count = 0
    challenge_count = 0
    quality_values: list[float] = []
    source_refs: list[str] = []
    required_targets = set(candidate.required_evidence_targets)
    required_hits: set[str] = set()

    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        relation = normalized_edge_relation(edge.get("relation") or edge.get("type"))
        if relation not in SUPPORTING_EVIDENCE_RELATIONS and relation not in CHALLENGING_EVIDENCE_RELATIONS:
            continue
        if not edge_mentions_candidate(edge, matches, nodes_by_id):
            continue
        evidence_node = evidence_node_for_candidate_edge(edge, matches, nodes_by_id)
        if not evidence_reference_verified(edge, evidence_node):
            continue
        quality = evidence_reference_quality(edge, evidence_node)
        if relation in SUPPORTING_EVIDENCE_RELATIONS:
            support_count += 1
            quality_values.append(quality)
            source_refs.append(evidence_source_reference(edge, evidence_node))
            required_hits.update(required_evidence_hits(evidence_node, required_targets))
        else:
            challenge_count += 1

    source_refs = [item for item in source_refs if item]
    avg_quality = round(sum(quality_values) / len(quality_values), 3) if quality_values else 0.65
    if required_targets:
        coverage_basis = len(required_hits) / max(len(required_targets), 1)
        if not required_hits and support_count:
            coverage_basis = min(1.0, support_count / max(len(required_targets), 1)) * 0.5
    else:
        coverage_basis = 1.0 if support_count else 0.0
    evidence_score = round(clamp01(coverage_basis * avg_quality - challenge_count * 0.15), 3)
    source_independence = round(clamp01(len(set(source_refs)) / max(len(source_refs), 1)), 3) if source_refs else 0.65
    return {
        "evidence_score": evidence_score,
        "verified_edge_count": support_count,
        "challenge_edge_count": challenge_count,
        "source_quality_score": avg_quality,
        "source_independence_score": source_independence,
        "source_count": len(set(source_refs)),
        "required_evidence_hits": sorted(required_hits),
    }


def evidence_graph_nodes_by_id(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for value in graph.values():
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("id") or "").strip()
            if node_id:
                nodes[node_id] = item
    return nodes


def normalized_edge_relation(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", "_").split())


def edge_mentions_candidate(edge: dict[str, Any], matches: set[str], nodes_by_id: dict[str, dict[str, Any]]) -> bool:
    metadata = edge.get("metadata") if isinstance(edge.get("metadata"), dict) else {}
    values = [
        edge.get("source"),
        edge.get("target"),
        edge.get("candidate"),
        metadata.get("candidate"),
        metadata.get("candidate_id"),
        metadata.get("candidate_label"),
        metadata.get("supports_candidate"),
    ]
    if any(normalized_candidate_label(value) in matches for value in values if str(value or "").strip()):
        return True
    return any(node_mentions_candidate(nodes_by_id.get(endpoint), matches) for endpoint in edge_endpoint_ids(edge))


def evidence_node_for_candidate_edge(
    edge: dict[str, Any],
    matches: set[str],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    endpoints = edge_endpoint_ids(edge)
    non_candidate_nodes = [
        nodes_by_id.get(endpoint)
        for endpoint in endpoints
        if normalized_candidate_label(endpoint) not in matches and not node_mentions_candidate(nodes_by_id.get(endpoint), matches)
    ]
    for node in non_candidate_nodes:
        if isinstance(node, dict):
            return node
    return {}


def edge_endpoint_ids(edge: dict[str, Any]) -> list[str]:
    output = []
    for key in ("source", "target", "from", "to"):
        value = str(edge.get(key) or "").strip()
        if value:
            output.append(value)
    return output


def node_mentions_candidate(node: dict[str, Any] | None, matches: set[str]) -> bool:
    if not isinstance(node, dict):
        return False
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    values = [
        node.get("id"),
        node.get("label"),
        node.get("canonical_target"),
        node.get("target"),
        metadata.get("candidate"),
        metadata.get("candidate_id"),
        metadata.get("candidate_label"),
    ]
    return any(normalized_candidate_label(value) in matches for value in values if str(value or "").strip())


def evidence_reference_verified(edge: dict[str, Any], node: dict[str, Any]) -> bool:
    verification = str(node.get("verification_state") or edge.get("verification_state") or "").strip().lower()
    governance_status = str(node.get("governance_status") or "").strip().lower()
    if verification in {"verified", "blocking", "fact"} or governance_status in {"fact", "blocker"}:
        return True
    if node.get("kind") in {"metric", "output_permission"} and verification != "rejected":
        return True
    return bool(edge.get("verified"))


def evidence_reference_quality(edge: dict[str, Any], node: dict[str, Any]) -> float:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    edge_metadata = edge.get("metadata") if isinstance(edge.get("metadata"), dict) else {}
    for source in (edge, edge_metadata, node, metadata):
        for key in ("source_quality_score", "source_quality", "quality_score", "reliability", "confidence"):
            if key in source:
                return normalized_score(source.get(key))
    return 0.65


def evidence_source_reference(edge: dict[str, Any], node: dict[str, Any]) -> str:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    edge_metadata = edge.get("metadata") if isinstance(edge.get("metadata"), dict) else {}
    for source in (node, metadata, edge, edge_metadata):
        for key in ("source", "source_id", "source_uri", "url", "source_module", "id"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return ""


def required_evidence_hits(node: dict[str, Any], required_targets: set[str]) -> set[str]:
    if not required_targets or not isinstance(node, dict):
        return set()
    values = {
        canonical_target(node.get("canonical_target")),
        canonical_target(node.get("target")),
        canonical_target(node.get("id")),
    }
    return {target for target in required_targets if target in values}


def evidence_coverage_score(state: dict[str, Any], *, conclusion_blocked: bool) -> float:
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    for key in ("evidence_coverage", "decision_readiness_score", "data_completeness_score", "quality_score"):
        if key in data_gate:
            return normalized_score(data_gate.get(key))
    evidence_graph = state.get("evidence_graph") if isinstance(state.get("evidence_graph"), dict) else {}
    summary = evidence_graph.get("summary") if isinstance(evidence_graph.get("summary"), dict) else {}
    if "evidence_coverage" in summary:
        return normalized_score(summary.get("evidence_coverage"))
    return 0.45 if conclusion_blocked else 0.65


def source_independence_score(state: dict[str, Any]) -> float:
    for key in ("independence_report", "source_independence_report"):
        report = state.get(key) if isinstance(state.get(key), dict) else {}
        for score_key in ("source_diversity", "independence_score", "source_independence"):
            if score_key in report:
                return normalized_score(report.get(score_key))
    outputs = runtime_agent_outputs(state)
    source_refs = []
    for output in outputs.values():
        if not isinstance(output, dict):
            continue
        refs = output.get("evidence_used") if isinstance(output.get("evidence_used"), list) else []
        source_refs.extend(str(ref) for ref in refs if str(ref).strip())
    if source_refs:
        return round(clamp01(len(set(source_refs)) / max(len(source_refs), 1)), 3)
    return 0.65


def unresolved_risk_score(state: dict[str, Any], *, active_blocker_count: int) -> float:
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    gap_count = len(data_gate.get("evidence_gaps") or []) if isinstance(data_gate.get("evidence_gaps"), list) else 0
    blocker_count = len(data_gate.get("decision_blockers") or []) if isinstance(data_gate.get("decision_blockers"), list) else 0
    agent_outputs = runtime_agent_outputs(state)
    hard_veto_count = sum(1 for item in agent_outputs.values() if isinstance(item, dict) and item.get("hard_veto"))
    return round(clamp01((gap_count * 0.15) + (blocker_count * 0.2) + (active_blocker_count * 0.2) + (hard_veto_count * 0.2)), 3)


def normalized_score(value: Any) -> float:
    score = safe_float(value, 0.0)
    if score > 1.0:
        score = score / 100.0
    return round(clamp01(score), 3)


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
