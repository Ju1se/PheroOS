from __future__ import annotations

import re
from typing import Any

from runtime.swarm.candidate_registry import (
    fallbackish_candidate_text,
    legacy_fallbackish_candidate_allowed,
    normalized_candidate_label,
)
from runtime.swarm.data_gate_permissions import (
    blocked_conclusion_permissions,
    writer_action_for_conclusion_target,
)
from runtime.swarm.legacy_data_gate_permissions import legacy_formal_valuation_conclusion_target
from runtime.swarm.legacy_output_phrases import (
    legacy_formal_valuation_phrases,
    legacy_formal_recommendation_present,
    legacy_insufficient_data_phrases,
)
from runtime.swarm.target_registry import canonical_target


STRONG_UNSUPPORTED_PATTERNS = (
    re.compile(r"\b(will\s+double|guaranteed|proves?|certainly|must\s+rise|must\s+fall)\b", re.I),
    re.compile(r"(一定|必然|确定性|证明了|翻倍|保证|无风险)"),
)
CITATION_MARKER_RE = re.compile(r"(https?://|\[[0-9]+\]|\bsource\s*:|\bcitation\s*:|来源|引用)", re.I)


def build_writer_evidence_contract(state: dict[str, Any], evidence_graph: dict[str, Any] | None = None) -> dict[str, Any]:
    graph = evidence_graph if isinstance(evidence_graph, dict) else state.get("evidence_graph")
    graph = graph if isinstance(graph, dict) else {}
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    steward = state.get("evidence_steward_report") if isinstance(state.get("evidence_steward_report"), dict) else {}
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    enforcement = state.get("enforcement_bus_report") if isinstance(state.get("enforcement_bus_report"), dict) else {}
    output_policy = policy_from_state(state, "output_policy")
    evidence_policy = policy_from_state(state, "evidence_policy")
    claims = graph.get("decision_claims") if isinstance(graph.get("decision_claims"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    metrics = graph.get("metrics") if isinstance(graph.get("metrics"), list) else []
    evidence_by_claim = evidence_sources_by_claim(edges)
    verified_claim_ids = set(evidence_by_claim)
    verified_claims = [
        claim_to_contract_item(claim, "verified", evidence_sources=evidence_by_claim.get(str(claim.get("id") or ""), []))
        for claim in claims
        if isinstance(claim, dict) and claim.get("id") in verified_claim_ids and claim.get("output_allowed") is not False
    ]
    caveated_claims = [
        claim_to_contract_item(claim, "caveated")
        for claim in claims
        if isinstance(claim, dict)
        and claim.get("id") not in verified_claim_ids
        and claim.get("output_allowed") is not False
    ]
    blocked_claims = [
        claim_to_contract_item(claim, "blocked")
        for claim in claims
        if isinstance(claim, dict) and claim.get("output_allowed") is False
    ]
    for claim in steward.get("blocked_claims") or []:
        if isinstance(claim, dict):
            blocked_claims.append(claim_to_contract_item(claim, "blocked"))
    unsupported_claims = [
        claim_to_contract_item(claim, "unsupported")
        for claim in steward.get("unsupported_claims") or []
        if isinstance(claim, dict)
    ]
    unsupported_action = str(evidence_policy.get("unsupported_claim_action") or "caveat_or_block").strip().lower()
    declared_writer_can_create_facts = bool(output_policy.get("writer_can_create_facts", False))
    writer_can_create_facts = False
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    required_caveats = unique_strings(
        [
            *list_values(data_gate.get("required_caveats")),
            *list_values(enforcement.get("required_caveats")),
            *list_values(output_policy.get("required_caveats")),
        ]
    )
    forbidden_phrases = writer_forbidden_phrases(
        state=state,
        graph=graph,
        data_gate=data_gate,
        committed=committed,
        output_policy=output_policy,
    )
    return {
        "schema_version": "pheroos.writer_evidence_contract.v1",
        "committed_candidate": committed.get("label"),
        "verified_claims": verified_claims,
        "caveated_claims": caveated_claims,
        "blocked_claims": dedupe_claim_items(blocked_claims),
        "unsupported_claims": dedupe_claim_items(unsupported_claims),
        "required_caveats": required_caveats,
        "forbidden_phrases": forbidden_phrases,
        "allowed_metrics": allowed_metric_items(metrics),
        "policy": {
            "final_claims_must_use_verified_or_caveated_claims": bool(
                output_policy.get("final_claim_evidence_required", True)
            ),
            "blocked_claims_must_not_appear": True,
            "unsupported_strong_claims_must_not_appear": (not writer_can_create_facts)
            and unsupported_action in {"block", "caveat_or_block"},
            "required_caveats_must_appear": bool(required_caveats),
            "required_evidence_for_final_claims": list_values(
                evidence_policy.get("required_evidence_for_final_claims")
            ),
            "allow_caveated_claim_without_evidence": bool(
                evidence_policy.get("allow_caveated_claim_without_evidence", True)
            ),
            "citation_required": bool(evidence_policy.get("citation_required", False)),
            "raw_data_allowed_in_final": False,
            "declared_raw_data_allowed_in_final": bool(evidence_policy.get("raw_data_allowed_in_final", False)),
            "unsupported_claim_action": unsupported_action or "caveat_or_block",
            "writer_can_create_facts": writer_can_create_facts,
            "declared_writer_can_create_facts": declared_writer_can_create_facts,
        },
    }


def validate_writer_evidence_contract(text: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    contract = build_writer_evidence_contract(state)
    policy = contract.get("policy") if isinstance(contract.get("policy"), dict) else {}
    haystack = normalize_text(text)
    violations: list[dict[str, Any]] = []
    for caveat in contract.get("required_caveats") or []:
        if normalize_text(caveat) and normalize_text(caveat) not in haystack:
            violations.append({"code": "missing_required_caveat", "message": str(caveat)})
    for claim in (contract.get("blocked_claims") or []) + (contract.get("unsupported_claims") or []):
        content = str(claim.get("content") or "").strip()
        if len(content) >= 12 and normalize_text(content) in haystack:
            if unsupported_claim_is_caveated(claim, text, policy):
                continue
            violations.append({"code": f"{claim.get('status')}_claim_in_final", "message": content})
    for claim in contract.get("caveated_claims") or []:
        content = str(claim.get("content") or "").strip()
        if len(content) < 12 or normalize_text(content) not in haystack:
            continue
        if not policy.get("allow_caveated_claim_without_evidence", True):
            violations.append({"code": "missing_required_evidence", "message": content})
        elif not has_caveat_near_text(text, content):
            violations.append({"code": "caveated_claim_without_caveat", "message": content})
        if policy.get("citation_required") and not has_citation_near_text(text, content):
            violations.append({"code": "missing_citation", "message": content})
    for claim in contract.get("verified_claims") or []:
        content = str(claim.get("content") or "").strip()
        if (
            len(content) >= 12
            and normalize_text(content) in haystack
            and policy.get("citation_required")
            and not has_citation_near_text(text, content)
        ):
            violations.append({"code": "missing_citation", "message": content})
    for phrase in contract.get("forbidden_phrases") or []:
        if phrase_present(text, str(phrase)):
            violations.append({"code": "forbidden_phrase", "message": str(phrase)})
    if policy.get("unsupported_strong_claims_must_not_appear", True):
        for pattern in STRONG_UNSUPPORTED_PATTERNS:
            match = pattern.search(str(text or ""))
            if match and not strong_claim_is_supported(match.group(0), text, contract):
                violations.append({"code": "unsupported_strong_claim", "message": match.group(0)})
                break
    output_policy = policy_from_state(state, "output_policy")
    committed = committed_candidate_from_state(state)
    if (
        not committed_candidate_conflict_rules(output_policy)
        and fallback_committed_candidate(committed, state)
        and legacy_formal_recommendation_present(text)
    ):
        violations.append({"code": "committed_candidate_mismatch", "message": committed_candidate_label(committed)})
    return dedupe_violations(violations)


def writer_forbidden_phrases(
    *,
    state: dict[str, Any],
    graph: dict[str, Any],
    data_gate: dict[str, Any],
    committed: dict[str, Any],
    output_policy: dict[str, Any],
) -> list[str]:
    phrases: list[Any] = []
    stop_policy = policy_from_state(state, "stop_signal_policy")
    markers_declared = bool(stop_policy_action_markers(stop_policy))
    conflict_rules = committed_candidate_conflict_rules(output_policy)
    blocked_outputs = blocked_output_targets(graph, data_gate)
    declared_marker_phrases = []
    for target in sorted(blocked_outputs):
        declared_marker_phrases.extend(
            action_marker_phrases(stop_policy, writer_action_for_conclusion_target(target))
        )
    phrases.extend(declared_marker_phrases)

    if legacy_formal_valuation_conclusion_target() in blocked_outputs and not markers_declared and not conflict_rules:
        phrases.extend(legacy_formal_valuation_phrases())

    conflict_phrases = committed_candidate_conflict_phrases(committed, output_policy)
    if conflict_phrases:
        phrases.extend(conflict_phrases)
    elif not conflict_rules and fallback_committed_candidate(committed, state):
        phrases.extend(legacy_insufficient_data_phrases())
    return unique_strings(phrases)


def blocked_output_targets(graph: dict[str, Any], data_gate: dict[str, Any]) -> set[str]:
    writer_contract = graph.get("writer_contract") if isinstance(graph.get("writer_contract"), dict) else {}
    targets = [canonical_target(target) for target in list_values(writer_contract.get("blocked_outputs"))]
    targets.extend(
        canonical_target(permission.get("canonical_target") or permission.get("target") or "")
        for permission in blocked_conclusion_permissions(data_gate)
    )
    return {target for target in targets if target}


def committed_candidate_conflict_phrases(committed: dict[str, Any], output_policy: dict[str, Any]) -> list[str]:
    phrases: list[Any] = []
    for rule in committed_candidate_conflict_rules(output_policy):
        if committed_candidate_matches_rule(committed, rule):
            phrases.extend(list_values(rule.get("blocked_phrases")))
    return unique_strings(phrases)


def committed_candidate_conflict_rules(output_policy: dict[str, Any]) -> list[dict[str, Any]]:
    rules = output_policy.get("committed_candidate_conflicts") if isinstance(output_policy, dict) else []
    return [dict(rule) for rule in rules or [] if isinstance(rule, dict)]


def committed_candidate_matches_rule(committed: dict[str, Any], rule: dict[str, Any]) -> bool:
    committed_keys = candidate_match_keys(committed)
    rule_keys = candidate_match_keys(rule)
    return bool(committed_keys and rule_keys and committed_keys.intersection(rule_keys))


def candidate_match_keys(value: dict[str, Any]) -> set[str]:
    keys = {
        normalized_candidate_label(value.get("candidate")),
        normalized_candidate_label(value.get("id")),
        normalized_candidate_label(value.get("label")),
        normalized_candidate_label(value.get("target")),
        normalized_candidate_label(value.get("canonical_target")),
    }
    return {key for key in keys if key}


def committed_candidate_from_state(state: dict[str, Any]) -> dict[str, Any]:
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    return quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}


def fallback_committed_candidate(committed: dict[str, Any], state: dict[str, Any]) -> bool:
    if bool(committed.get("safe_fallback")):
        return True
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    fallback = quorum.get("fallback_candidate") if isinstance(quorum.get("fallback_candidate"), dict) else {}
    if fallback and candidate_match_keys(committed).intersection(candidate_match_keys(fallback)):
        return True
    if not legacy_fallbackish_candidate_allowed(quorum):
        return False
    return fallbackish_candidate_text(f"{committed.get('id')} {committed.get('label')}")


def committed_candidate_label(committed: dict[str, Any]) -> str:
    return str(committed.get("label") or committed.get("id") or "fallback committed candidate")


def action_marker_phrases(stop_policy: dict[str, Any], action: str) -> list[str]:
    action_key = normalize_action(action)
    phrases: list[Any] = []
    for marker in stop_policy_action_markers(stop_policy):
        if normalize_action(marker.get("action")) != action_key:
            continue
        phrases.extend(list_values(marker.get("phrases") or marker.get("keywords") or marker.get("markers")))
    return unique_strings(phrases)


def stop_policy_action_markers(stop_policy: dict[str, Any]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    sources = [stop_policy]
    sources.extend(rule for rule in stop_policy.get("rules") or [] if isinstance(rule, dict))
    for source in sources:
        for marker in source.get("action_markers") or source.get("action_cues") or []:
            if isinstance(marker, dict):
                markers.append(dict(marker))
    return markers


def normalize_action(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ":" not in text:
        return "_".join(text.lower().replace("-", "_").split())
    prefix, tail = text.split(":", 1)
    return f"{prefix.strip().lower().replace('-', '_')}:{'_'.join(tail.strip().lower().replace('-', '_').split())}"


def policy_from_state(state: dict[str, Any], key: str) -> dict[str, Any]:
    direct = state.get(key) if isinstance(state.get(key), dict) else {}
    if direct:
        return direct
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    direct = metadata.get(key) if isinstance(metadata.get(key), dict) else {}
    if direct:
        return direct
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    return swarm_plan.get(key) if isinstance(swarm_plan.get(key), dict) else {}


def list_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def evidence_sources_by_claim(edges: list[Any]) -> dict[str, list[str]]:
    by_claim: dict[str, list[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("relation")) not in {"available_evidence", "supports", "verifies"}:
            continue
        target = str(edge.get("target") or "")
        source = str(edge.get("source") or "")
        if not target or not source:
            continue
        by_claim.setdefault(target, [])
        if source not in by_claim[target]:
            by_claim[target].append(source)
    return by_claim


def claim_to_contract_item(claim: dict[str, Any], status: str, *, evidence_sources: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": claim.get("id") or claim.get("claim_id"),
        "status": status,
        "claim_type": claim.get("claim_type"),
        "content": str(claim.get("content") or ""),
        "source_module": claim.get("source_module"),
        "agent": claim.get("agent"),
        "evidence_sources": evidence_sources or [],
    }


def allowed_metric_items(metrics: list[Any]) -> list[dict[str, Any]]:
    output = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("name") or "").strip()
        if not name:
            continue
        output.append(
            {
                "name": name,
                "period": metric.get("period"),
                "value": metric.get("value"),
                "unit": metric.get("unit"),
                "source": metric.get("source"),
            }
        )
    return output


def has_caveat_near_text(text: str, claim: str) -> bool:
    lower = str(text or "").lower()
    claim_lower = str(claim or "").lower()
    index = lower.find(claim_lower)
    if index < 0:
        return False
    window = lower[max(0, index - 160): index + len(claim_lower) + 160]
    caveat_terms = ("preliminary", "caveat", "may", "suggests", "unverified", "初步", "可能", "假设", "限制", "未验证")
    return any(term in window for term in caveat_terms)


def has_citation_near_text(text: str, claim: str) -> bool:
    lower = str(text or "").lower()
    claim_lower = str(claim or "").lower()
    index = lower.find(claim_lower)
    if index < 0:
        return False
    window = str(text or "")[max(0, index - 180): index + len(claim_lower) + 180]
    return bool(CITATION_MARKER_RE.search(window))


def unsupported_claim_is_caveated(claim: dict[str, Any], text: str, policy: dict[str, Any]) -> bool:
    if str(claim.get("status") or "") != "unsupported":
        return False
    action = str(policy.get("unsupported_claim_action") or "caveat_or_block").lower()
    if action not in {"caveat", "caveat_or_block"}:
        return False
    content = str(claim.get("content") or "")
    return has_caveat_near_text(text, content)


def strong_claim_is_supported(match_text: str, text: str, contract: dict[str, Any]) -> bool:
    normalized_match = normalize_text(match_text)
    if not normalized_match:
        return False
    for claim in contract.get("verified_claims") or []:
        content = str(claim.get("content") or "")
        if normalized_match in normalize_text(content) and claim.get("evidence_sources"):
            return True
    policy = contract.get("policy") if isinstance(contract.get("policy"), dict) else {}
    if not policy.get("allow_caveated_claim_without_evidence", True):
        return False
    for claim in contract.get("caveated_claims") or []:
        content = str(claim.get("content") or "")
        if normalized_match in normalize_text(content) and has_caveat_near_text(text, content):
            return True
    return False


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def phrase_present(text: str, phrase: str) -> bool:
    needle = str(phrase or "").strip()
    if not needle:
        return False
    haystack = str(text or "")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]*", needle):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(needle).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9])"
        return re.search(pattern, haystack, re.I) is not None
    return needle.lower() in haystack.lower()


def unique_strings(values: list[Any]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def dedupe_claim_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        key = (item.get("id"), normalize_text(item.get("content")), item.get("status"))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def dedupe_violations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        key = (item.get("code"), item.get("message"))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output
