from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from runtime.legacy_agent_registry import (
    legacy_committee_agent_catalog_from_metadata,
    selected_agent_ids_from_metadata,
)
from runtime.legacy_value_investing_support import legacy_default_committee_capability_ids
from runtime.state import AgentState
from runtime.swarm.agent_outputs import runtime_agent_outputs
from runtime.swarm.response_threshold import select_committee_members_by_threshold


_DEFAULT_COMMITTEE_SPEC_CACHE: dict[frozenset[str], list[dict[str, Any]]] = {}


def _graph_runtime() -> Any:
    from runtime import graph as graph_runtime

    return graph_runtime


def metric_registry_for_model(value: Any) -> dict[str, Any]:
    return _graph_runtime().metric_registry_for_model(value)


def summarize_wrds_result_for_model(value: Any) -> dict[str, Any]:
    return _graph_runtime().summarize_wrds_result_for_model(value)


def latest_periods(periods: list[str], *, limit: int) -> list[str]:
    return _graph_runtime().latest_periods(periods, limit=limit)


def period_sort_key(period: str) -> tuple[int, int, int]:
    return _graph_runtime().period_sort_key(period)


def model_safe_execution_log(execution_log: Any, *, text_limit: int = 4_000) -> list[dict[str, Any]]:
    return _graph_runtime().model_safe_execution_log(execution_log, text_limit=text_limit)


def describe_source_grounding(state: AgentState) -> str:
    return _graph_runtime().describe_source_grounding(state)


def parse_optional_json(content: str) -> dict[str, Any] | None:
    return _graph_runtime().parse_optional_json(content)


def ensure_string_list(value: Any) -> list[str]:
    return _graph_runtime().ensure_string_list(value)


def parse_positive_int(value: Any, default: int) -> int:
    return _graph_runtime().parse_positive_int(value, default)


def parse_bool_value(value: Any, default: bool) -> bool:
    return _graph_runtime().parse_bool_value(value, default)


def agent_outputs_for_state(state: AgentState | dict[str, Any]) -> dict[str, Any]:
    return runtime_agent_outputs(state) if isinstance(state, dict) else {}


def deterministic_wrds_research_brief(state: AgentState) -> dict[str, Any]:
    registry = metric_registry_for_model(state.get("metric_registry", {}))
    contract = state.get("data_contract", {}) if isinstance(state.get("data_contract"), dict) else {}
    gate = state.get("data_gate", {}) if isinstance(state.get("data_gate"), dict) else {}
    company = summarize_wrds_result_for_model(state.get("wrds_result", {})).get("company", {})
    periods = latest_periods([str(metric.get("period") or "") for metric in registry.get("derived_metrics", [])], limit=8)
    return {
        "status": "completed_wrds_only",
        "sources": [
            {
                "title": "WRDS/Compustat standardized company financials",
                "url": None,
                "date": contract.get("as_of_date"),
                "key_facts": [
                    f"Matched company: {company.get('name') or 'unknown'} ({company.get('ticker') or 'unknown'})",
                    f"Data gate status: {gate.get('status') or 'unknown'}",
                    f"Metric registry contains {registry.get('metric_count', 0)} derived metrics; {registry.get('metrics_in_context', 0)} shown to agents.",
                ],
                "reliability": gate.get("confidence") or "medium",
            }
        ],
        "key_facts": [
            f"WRDS-only mode is active; allowed source is WRDS/Compustat only.",
            f"Latest visible metric periods: {', '.join(periods) if periods else 'unknown'}.",
            f"Company identity: {company.get('name') or 'unknown'}, ticker {company.get('ticker') or 'unknown'}, gvkey {company.get('gvkey') or 'unknown'}.",
        ],
        "evidence_gaps": list(gate.get("limitations") or [])
        + [
            "No SEC/company-release reconciliation in this run.",
            "Non-GAAP EPS and management guidance are unavailable unless separately sourced.",
        ],
        "reliability": gate.get("confidence") or "medium",
        "source_grounding": "wrds_compustat_internal_consistency_only",
    }


def deterministic_wrds_quant_analysis(state: AgentState) -> dict[str, Any]:
    registry = metric_registry_for_model(state.get("metric_registry", {}))
    gate = state.get("data_gate", {}) if isinstance(state.get("data_gate"), dict) else {}
    metrics = registry.get("derived_metrics") if isinstance(registry.get("derived_metrics"), list) else []
    latest_by_name: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("metric") or "")
        current = latest_by_name.get(name)
        if current is None or period_sort_key(str(metric.get("period") or "")) > period_sort_key(str(current.get("period") or "")):
            latest_by_name[name] = metric
    focus_names = [
        "revenue",
        "gross_margin",
        "gross_margin_before_depreciation",
        "gross_margin_after_depreciation_candidate",
        "operating_margin",
        "net_income",
        "diluted_eps",
        "operating_cash_flow",
        "capex",
        "free_cash_flow",
        "cash",
        "debt",
        "shares_outstanding",
        "market_price",
    ]
    selected = [latest_by_name[name] for name in focus_names if name in latest_by_name]
    ttm_metrics = registry.get("ttm_metrics") if isinstance(registry.get("ttm_metrics"), list) else []
    return {
        "status": "completed_wrds_only",
        "assumptions": [
            "Use deterministic WRDS/Compustat metric registry only.",
            "Treat all metrics as preliminary because WRDS-only mode has no SEC/company-release reconciliation.",
        ],
        "formulas": sorted({str(metric.get("formula")) for metric in selected if metric.get("formula")}),
        "calculations": [
            "The runtime calculated derived metrics before model agents ran; Quant Agent did not perform LLM mental math.",
            "Gross margin basis is split when depreciation materially affects Compustat gross profit.",
            "TTM valuation multiples, when available, are registry-derived from the latest four quarters and latest quarter price/share/debt/cash fields.",
        ],
        "metrics": selected,
        "ttm_metrics": ttm_metrics,
        "metric_series": registry.get("metric_series", {}),
        "annual_metric_series": registry.get("annual_metric_series", {}),
        "quarterly_metric_series": registry.get("quarterly_metric_series", {}),
        "ttm_metric_series": registry.get("ttm_metric_series", {}),
        "sensitivity": [],
        "missing_data": [
            "SEC/company release reconciliation",
            "Non-GAAP EPS reconciliation",
            "Management guidance",
            "Segment-specific disclosures",
        ],
        "data_quality": gate.get("confidence") or "medium",
    }


def committee_member_specs_for_state(state: AgentState) -> list[dict[str, Any]]:
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    enabled_capability_ids = enabled_committee_capability_ids_from_state(state)
    catalog = (
        metadata.get("agent_catalog")
        if isinstance(metadata.get("agent_catalog"), list)
        else legacy_committee_agent_catalog_from_metadata(metadata)
    )
    specs = normalize_committee_agent_catalog(catalog) if isinstance(catalog, list) else []
    if not specs:
        specs = default_committee_member_specs_from_manifests(enabled_capability_ids=enabled_capability_ids)

    selected = normalize_selected_committee_members(selected_agent_ids_from_metadata(metadata))
    explicit_selection = bool(selected)
    if explicit_selection:
        specs = [spec for spec in specs if spec.get("key") in selected]
    if not specs:
        specs = default_committee_member_specs_from_manifests(enabled_capability_ids=enabled_capability_ids)
    specs.sort(key=lambda spec: (committee_member_order(spec), str(spec.get("key") or "")))
    specs, _trace = select_committee_members_by_threshold(
        specs,
        state,
        explicit_selection=explicit_selection,
    )
    specs.sort(key=lambda spec: (committee_member_order(spec), str(spec.get("key") or "")))
    return specs


def default_committee_member_specs_from_manifests(
    *,
    enabled_capability_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    cache_key = frozenset(enabled_capability_ids or legacy_default_committee_capability_ids())
    if cache_key in _DEFAULT_COMMITTEE_SPEC_CACHE:
        return [dict(spec) for spec in _DEFAULT_COMMITTEE_SPEC_CACHE[cache_key]]
    try:
        from runtime.agent_registry import AgentRegistry

        repo_root = Path(__file__).resolve().parents[2]
        specs = AgentRegistry(
            capabilities_dir=repo_root / "capabilities",
            agents_dir=repo_root / "agents",
        ).committee_specs(enabled_capability_ids=set(cache_key))
    except Exception:  # noqa: BLE001
        specs = []
    _DEFAULT_COMMITTEE_SPEC_CACHE[cache_key] = [dict(spec) for spec in specs]
    return [dict(spec) for spec in _DEFAULT_COMMITTEE_SPEC_CACHE[cache_key]]


def enabled_committee_capability_ids_from_state(state: AgentState | dict[str, Any]) -> set[str] | None:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    ids: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            ids.add(value.strip())
            return
        if isinstance(value, dict):
            capability_id = str(value.get("id") or value.get("capability_id") or "").strip()
            if capability_id:
                ids.add(capability_id)
            return
        if isinstance(value, list):
            for item in value:
                collect(item)

    collect(metadata.get("enabled_capabilities"))
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    collect(os_plan.get("enabled_capabilities"))
    collect(os_plan.get("auto_enabled"))
    return ids or None


def normalize_committee_agent_catalog(catalog: list[Any]) -> list[dict[str, Any]]:
    from runtime.agent_registry import committee_capable

    specs: list[dict[str, Any]] = []
    for item in catalog:
        if not isinstance(item, dict):
            continue
        if not committee_capable(item):
            continue
        key = str(item.get("key") or "").strip()
        focus = str(item.get("focus") or "").strip()
        if not key or not focus:
            continue
        specs.append(
            {
                "key": key,
                "name": str(item.get("name") or key),
                "model_attr": str(item.get("model_attr") or key),
                "focus": focus,
                "order": parse_positive_int(item.get("order"), 1000),
                "capability_id": item.get("capability_id"),
                "swarm": item.get("swarm") if isinstance(item.get("swarm"), dict) else {},
            }
        )
    return specs


def normalize_selected_committee_members(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def committee_member_order(spec: dict[str, Any]) -> int:
    return parse_positive_int(spec.get("order"), 1000)


def committee_member_context(
    state: AgentState,
    *,
    spec: dict[str, Any],
    prior_outputs: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "task": state["task"],
            "translated_task": state.get("translated_task"),
            "member": spec["key"],
            "focus": spec["focus"],
            "swarm_signal_policy": {
                "allowed_signal_types": (
                    (spec.get("swarm") or {}).get("signal_emit_permissions")
                    if isinstance(spec.get("swarm"), dict)
                    else []
                ),
                "can_propose_stop_signal": bool(
                    isinstance(spec.get("swarm"), dict) and (spec.get("swarm") or {}).get("can_block")
                ),
                "rules": [
                    "Committee agents may propose signals only through emitted_signals.",
                    "Agent-emitted signals are treated as unverified or contested proposals.",
                    "Only deterministic system gates can promote a signal to verified/blocking enforcement.",
                ],
            },
            "active_committee_members": [
                {
                    "key": item.get("key"),
                    "name": item.get("name"),
                    "focus": item.get("focus"),
                }
                for item in (
                    state.get("active_committee_member_specs")
                    if isinstance(state.get("active_committee_member_specs"), list)
                    else committee_member_specs_for_state(state)
                )
            ],
            "agent_outputs_so_far": summarize_agent_outputs_for_model(prior_outputs or {}),
            "committee_outputs_so_far": summarize_agent_outputs_for_model(prior_outputs or {}),
            "selected_skills": state.get("selected_skills", []),
            "skill_context": state.get("skill_context", ""),
            "research_brief": state.get("research_brief", {}),
            "quant_analysis": state.get("quant_analysis", {}),
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "execution_log": model_safe_execution_log(state.get("execution_log", []), text_limit=1_500),
            "source_grounding": describe_source_grounding(state),
        },
        ensure_ascii=False,
    )


def committee_discussion_context(state: AgentState, *, transcript: list[dict[str, Any]], round_number: int) -> str:
    agent_outputs = agent_outputs_for_state(state)
    summarized_outputs = summarize_agent_outputs_for_model(agent_outputs)
    return json.dumps(
        {
            "task": state["task"],
            "round": round_number,
            "max_rounds": 3,
            "agent_outputs": summarized_outputs,
            "committee_outputs": summarized_outputs,
            "active_committee_members": [
                {"key": item.get("key"), "name": item.get("name"), "focus": item.get("focus")}
                for item in committee_member_specs_for_state(state)
            ],
            "previous_transcript": transcript,
            "discussion_pressure": committee_discussion_pressure(state),
            "data_gate": state.get("data_gate", {}),
        },
        ensure_ascii=False,
    )


def investment_committee_context(state: AgentState) -> str:
    agent_outputs = agent_outputs_for_state(state)
    summarized_outputs = summarize_agent_outputs_for_model(agent_outputs)
    return json.dumps(
        {
            "task": state["task"],
            "translated_task": state.get("translated_task"),
            "research_brief": state.get("research_brief", {}),
            "quant_analysis": state.get("quant_analysis", {}),
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "agent_outputs": summarized_outputs,
            "committee_outputs": summarized_outputs,
            "active_committee_members": [
                {"key": item.get("key"), "name": item.get("name"), "focus": item.get("focus")}
                for item in committee_member_specs_for_state(state)
            ],
            "discussion_transcript": state.get("discussion_transcript", []),
            "source_grounding": describe_source_grounding(state),
        },
        ensure_ascii=False,
    )


def parse_committee_output(content: str, *, member: str) -> dict[str, Any]:
    payload = parse_optional_json(content)
    if payload is None:
        salvaged = salvage_committee_output(content)
        if salvaged:
            return normalize_committee_payload(salvaged, member=member, status_default="salvaged")
        return {
            "status": "unstructured",
            "member": member,
            "sub_plan": [],
            "thesis": content.strip(),
            "score": None,
            "confidence": "unknown",
            "evidence_used": [],
            "missing_data": [],
            "risks": [],
            "hard_veto": False,
            "evidence_requests": [],
            "role_assessment": {},
            "emitted_signals": [],
        }
    return normalize_committee_payload(payload, member=member)


def normalize_committee_payload(
    payload: dict[str, Any],
    *,
    member: str,
    status_default: str = "completed",
) -> dict[str, Any]:
    return {
        "status": str(payload.get("status") or status_default),
        "member": member,
        "sub_plan": ensure_string_list(payload.get("sub_plan")),
        "thesis": str(payload.get("thesis") or ""),
        "score": normalize_score(payload.get("score")),
        "confidence": payload.get("confidence", "unknown"),
        "evidence_used": ensure_string_list(payload.get("evidence_used")),
        "missing_data": ensure_string_list(payload.get("missing_data")),
        "risks": ensure_string_list(payload.get("risks")),
        "hard_veto": parse_bool_value(payload.get("hard_veto"), False),
        "evidence_requests": ensure_string_list(payload.get("evidence_requests")),
        "role_assessment": payload.get("role_assessment") if isinstance(payload.get("role_assessment"), dict) else {},
        "emitted_signals": normalize_emitted_signal_payloads(payload.get("emitted_signals")),
    }


def normalize_emitted_signal_payloads(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        return []
    output: list[dict[str, Any]] = []
    allowed_keys = {
        "type",
        "signal_type",
        "target",
        "content",
        "reason",
        "strength",
        "confidence",
        "priority",
        "evidence_ref",
        "verification_state",
        "blocking",
        "hard_veto",
    }
    for item in values:
        if not isinstance(item, dict):
            continue
        sanitized = {str(key): item[key] for key in item if str(key) in allowed_keys}
        if sanitized:
            output.append(sanitized)
    return output


def salvage_committee_output(content: str) -> dict[str, Any]:
    parsed = parse_embedded_json_object(content)
    if parsed is not None:
        return parsed
    payload: dict[str, Any] = {}
    structured = False
    text = str(content or "")
    for key in ("status", "confidence"):
        value = regex_json_string_value(text, key)
        if value is not None:
            payload[key] = value
            structured = True
    score_match = re.search(r'"score"\s*:\s*"?(-?\d+(?:\.\d+)?)%?"?', text, flags=re.IGNORECASE)
    if score_match:
        payload["score"] = score_match.group(1)
        structured = True
    hard_veto_match = re.search(r'"hard_veto"\s*:\s*("?(?:true|false|yes|no|0|1)"?)', text, flags=re.IGNORECASE)
    if hard_veto_match:
        payload["hard_veto"] = hard_veto_match.group(1).strip('"')
        structured = True
    thesis = regex_json_string_value(text, "thesis")
    if thesis is not None:
        payload["thesis"] = thesis
        structured = True
    elif structured and text.strip():
        payload["thesis"] = text.strip()
    return payload if structured else {}


def parse_embedded_json_object(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if not text:
        return None
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict):
        return decoded
    if isinstance(decoded, str):
        nested = parse_optional_json(decoded)
        if nested is not None:
            return nested
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            decoded, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return None


def regex_json_string_value(text: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
    if not match:
        return None
    value = match.group(1)
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace('\\"', '"')


def failed_committee_output(member: str, exc: Exception) -> dict[str, Any]:
    return {
        "status": "failed",
        "member": member,
        "sub_plan": [],
        "thesis": "",
        "score": None,
        "confidence": "none",
        "evidence_used": [],
        "missing_data": [],
        "risks": [str(exc)],
        "hard_veto": False,
        "evidence_requests": [],
        "role_assessment": {},
        "failure_reason": str(exc),
    }


def opening_transcript_entry(member: str, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": 0,
        "speaker": member,
        "target": "committee",
        "claim": output.get("thesis") or "",
        "challenge": "",
        "response": "",
        "score": output.get("score"),
        "confidence": output.get("confidence"),
        "hard_veto": bool(output.get("hard_veto")),
        "role_assessment": output.get("role_assessment") if isinstance(output.get("role_assessment"), dict) else {},
    }


def parse_discussion_round(content: str, *, round_number: int) -> dict[str, Any]:
    payload = parse_optional_json(content)
    if payload is None:
        payload = parse_embedded_json_object(content)
    if payload is None:
        clean_content = strip_reasoning_blocks(content)
        return {
            "continue_discussion": False,
            "turns": [
                {
                    "round": round_number,
                    "speaker": "committee_discussion",
                    "target": "committee",
                    "claim": "",
                    "challenge": clean_content,
                    "response": "",
                    "score_delta": None,
                    "confidence_delta": None,
                }
            ],
        }

    turns = []
    for item in payload.get("turns") or []:
        if not isinstance(item, dict):
            continue
        turns.append(
            {
                "round": round_number,
                "speaker": str(item.get("speaker") or "committee_discussion"),
                "target": str(item.get("target") or "committee"),
                "claim": str(item.get("claim") or ""),
                "challenge": str(item.get("challenge") or ""),
                "response": str(item.get("response") or ""),
                "score_delta": normalize_score(item.get("score_delta")),
                "confidence_delta": item.get("confidence_delta"),
            }
        )
    if not turns:
        turns = fallback_discussion_turns({}, round_number=round_number)
    return {
        "continue_discussion": parse_bool_value(payload.get("continue_discussion"), False),
        "turns": turns,
    }


def fallback_discussion_turns(state: AgentState | dict[str, Any], *, round_number: int) -> list[dict[str, Any]]:
    outputs = agent_outputs_for_state(state)
    hard_vetoes = [name for name, output in outputs.items() if isinstance(output, dict) and output.get("hard_veto")]
    challenge = "No structured challenge was produced; committee should preserve evidence limitations."
    if hard_vetoes:
        challenge = f"Hard vetoes require explicit treatment: {', '.join(hard_vetoes)}."
    return [
        {
            "round": round_number,
            "speaker": "committee_discussion",
            "target": "committee",
            "claim": "",
            "challenge": challenge,
            "response": "Recorded as a discussion limitation.",
            "score_delta": None,
            "confidence_delta": None,
        }
    ]


def strip_reasoning_blocks(content: Any) -> str:
    text = str(content or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def should_continue_committee_discussion(
    state: AgentState,
    *,
    transcript: list[dict[str, Any]],
    model_requested_continue: bool,
    rounds_completed: int,
) -> bool:
    if rounds_completed >= 3:
        return False
    if model_requested_continue:
        return True
    pressure = committee_discussion_pressure(state)
    if rounds_completed < 1:
        return True
    return bool(pressure["hard_vetoes"] or pressure["high_score_dispersion"] or pressure["major_missing_data"])


def committee_discussion_pressure(state: AgentState) -> dict[str, Any]:
    outputs = agent_outputs_for_state(state)
    scores = [
        float(output.get("score"))
        for output in outputs.values()
        if isinstance(output, dict) and isinstance(output.get("score"), (int, float))
    ]
    missing_count = sum(
        len(output.get("missing_data") or []) + len(output.get("evidence_requests") or [])
        for output in outputs.values()
        if isinstance(output, dict)
    )
    hard_vetoes = [
        name for name, output in outputs.items() if isinstance(output, dict) and bool(output.get("hard_veto"))
    ]
    return {
        "hard_vetoes": hard_vetoes,
        "score_range": max(scores) - min(scores) if len(scores) >= 2 else 0,
        "high_score_dispersion": (max(scores) - min(scores)) >= 30 if len(scores) >= 2 else False,
        "missing_count": missing_count,
        "major_missing_data": missing_count >= 6,
    }


def parse_agent_decision(content: str, *, state: AgentState) -> dict[str, Any]:
    payload = parse_optional_json(content)
    if payload is None:
        return fallback_agent_decision(state, summary=content.strip())
    return {
        "status": str(payload.get("status") or "completed"),
        "decision": str(payload.get("decision") or ""),
        "final_decision": str(payload.get("final_decision") or payload.get("decision") or ""),
        "conviction": str(payload.get("conviction") or payload.get("confidence") or "unknown"),
        "position_size": str(payload.get("position_size") or ""),
        "time_horizon": str(payload.get("time_horizon") or ""),
        "core_thesis": str(payload.get("core_thesis") or ""),
        "key_evidence": ensure_string_list(payload.get("key_evidence")),
        "main_risk": str(payload.get("main_risk") or ""),
        "invalidation_point": str(payload.get("invalidation_point") or ""),
        "consensus": ensure_string_list(payload.get("consensus")),
        "dissent": ensure_string_list(payload.get("dissent")),
        "hard_vetoes": ensure_string_list(payload.get("hard_vetoes")),
        "scorecard": normalize_scorecard(payload.get("scorecard"), state=state),
        "confidence": payload.get("confidence", "unknown"),
        "open_questions": ensure_string_list(payload.get("open_questions")),
        "evidence_limitations": ensure_string_list(payload.get("evidence_limitations")),
    }


def parse_committee_decision(content: str, *, state: AgentState) -> dict[str, Any]:
    return parse_agent_decision(content, state=state)


def fallback_agent_decision(state: AgentState, *, summary: str = "") -> dict[str, Any]:
    outputs = agent_outputs_for_state(state)
    hard_vetoes = [name for name, output in outputs.items() if isinstance(output, dict) and output.get("hard_veto")]
    limitations = []
    for output in outputs.values():
        if isinstance(output, dict):
            limitations.extend(ensure_string_list(output.get("missing_data")))
            limitations.extend(ensure_string_list(output.get("evidence_requests")))
    return {
        "status": "fallback",
        "decision": summary or "Committee completed with limited structured synthesis.",
        "final_decision": "Watch",
        "conviction": "unknown",
        "position_size": "",
        "time_horizon": "",
        "core_thesis": "",
        "key_evidence": [],
        "main_risk": "",
        "invalidation_point": "",
        "consensus": [],
        "dissent": [],
        "hard_vetoes": hard_vetoes,
        "scorecard": normalize_scorecard(None, state=state),
        "confidence": "unknown",
        "open_questions": [],
        "evidence_limitations": limitations,
    }


def fallback_committee_decision(state: AgentState, *, summary: str = "") -> dict[str, Any]:
    return fallback_agent_decision(state, summary=summary)


def apply_protocol_decision_boundary(state: AgentState, decision: dict[str, Any]) -> dict[str, Any]:
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    committed_label = str(committed.get("label") or "").strip()
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    publication_blocked = gate.get("report_publication_allowed") is False or bool(gate.get("decision_blockers"))
    if committed_label.lower() != "insufficient data" and not publication_blocked:
        return decision
    proposed = str(decision.get("final_decision") or decision.get("decision") or "").strip()
    output = dict(decision)
    output["committee_proposed_decision"] = proposed
    output["protocol_decision"] = "Insufficient Data"
    output["publication_status"] = "blocked_by_data_gate" if publication_blocked else "blocked_by_quorum"
    output["decision_authority"] = "quorum_marshal"
    output["final_decision"] = "Insufficient Data"
    output["decision"] = "Insufficient Data"
    output["conviction"] = "N/A"
    output["position_size"] = "0%"
    limitations = ensure_string_list(output.get("evidence_limitations"))
    if publication_blocked and not any("Data Gate" in item or "数据" in item for item in limitations):
        limitations.insert(0, "Data Gate / PheroOS blocked formal valuation and report publication; committee output remains a proposal, not a publishable investment conclusion.")
    output["evidence_limitations"] = limitations
    return output


def normalize_scorecard(value: Any, *, state: AgentState) -> list[dict[str, Any]]:
    fallback = scorecard_fallback_by_agent(state)
    if isinstance(value, list):
        scorecard = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            agent = str(item.get("agent") or item.get("member") or "").strip()
            fallback_item = fallback.get(agent, {}) if agent else {}
            normalized = {
                "agent": agent or str(fallback_item.get("agent") or ""),
                "score": normalize_score(item.get("score")) if normalize_score(item.get("score")) is not None else fallback_item.get("score"),
                "confidence": best_confidence(item.get("confidence"), fallback_item.get("confidence")),
                "hard_veto": parse_bool_value(item.get("hard_veto"), bool(fallback_item.get("hard_veto", False))),
            }
            if normalized["agent"]:
                seen.add(normalized["agent"])
            scorecard.append(normalized)
        for agent, fallback_item in fallback.items():
            if agent not in seen:
                scorecard.append(fallback_item)
        if scorecard:
            return scorecard
    return list(fallback.values())


def scorecard_fallback_by_agent(state: AgentState) -> dict[str, dict[str, Any]]:
    fallback: dict[str, dict[str, Any]] = {}
    outputs = agent_outputs_for_state(state)
    for name, output in outputs.items():
        if not isinstance(output, dict):
            continue
        embedded = parse_embedded_json_object(str(output.get("thesis") or "")) or {}
        score = output.get("score")
        if score is None:
            score = embedded.get("score")
        confidence = output.get("confidence")
        if not confidence or confidence == "unknown":
            confidence = embedded.get("confidence") or confidence
        hard_veto = output.get("hard_veto")
        if hard_veto is None:
            hard_veto = embedded.get("hard_veto")
        fallback[name] = {
            "agent": name,
            "score": normalize_score(score),
            "confidence": confidence or "unknown",
            "hard_veto": parse_bool_value(hard_veto, False),
        }
    for turn in state.get("discussion_transcript", []) or []:
        if not isinstance(turn, dict):
            continue
        speaker = str(turn.get("speaker") or "").strip()
        if not speaker:
            continue
        current = fallback.setdefault(
            speaker,
            {"agent": speaker, "score": None, "confidence": "unknown", "hard_veto": False},
        )
        turn_payload = parse_embedded_json_object(str(turn.get("claim") or "")) or {}
        turn_score = normalize_score(turn.get("score"))
        if turn_score is None:
            turn_score = normalize_score(turn_payload.get("score"))
        if current.get("score") is None and turn_score is not None:
            current["score"] = turn_score
        turn_confidence = turn.get("confidence") or turn_payload.get("confidence")
        if current.get("confidence") in (None, "", "unknown") and turn_confidence:
            current["confidence"] = turn_confidence
        current["hard_veto"] = bool(current.get("hard_veto")) or parse_bool_value(
            turn.get("hard_veto", turn_payload.get("hard_veto")),
            False,
        )
    return fallback


def best_confidence(primary: Any, fallback: Any) -> Any:
    primary_text = str(primary or "").strip()
    if primary_text and primary_text.lower() != "unknown":
        return primary
    fallback_text = str(fallback or "").strip()
    if fallback_text:
        return fallback
    return "unknown"


def agent_decision_to_domain_analysis(decision: dict[str, Any]) -> dict[str, Any]:
    risks = [*ensure_string_list(decision.get("hard_vetoes")), *ensure_string_list(decision.get("evidence_limitations"))]
    return {
        "status": decision.get("status") or "completed",
        "domain": "investment_committee",
        "judgment": str(decision.get("decision") or decision.get("final_decision") or ""),
        "framework_points": [
            *ensure_string_list(decision.get("consensus")),
            *ensure_string_list(decision.get("key_evidence")),
        ],
        "risks": risks,
        "missing_evidence": ensure_string_list(decision.get("open_questions")),
        "confidence": str(decision.get("confidence") or "unknown"),
    }


def committee_decision_to_domain_analysis(decision: dict[str, Any]) -> dict[str, Any]:
    return agent_decision_to_domain_analysis(decision)


def summarize_agent_outputs_for_model(outputs: Any) -> dict[str, Any]:
    if not isinstance(outputs, dict):
        return {}
    summary = {}
    for name, output in outputs.items():
        if not isinstance(output, dict):
            continue
        summary[name] = {
            "status": output.get("status"),
            "thesis": output.get("thesis"),
            "score": output.get("score"),
            "confidence": output.get("confidence"),
            "hard_veto": output.get("hard_veto"),
            "evidence_used": output.get("evidence_used"),
            "missing_data": output.get("missing_data"),
            "risks": output.get("risks"),
            "evidence_requests": output.get("evidence_requests"),
            "role_assessment": output.get("role_assessment"),
        }
    return summary


def summarize_committee_outputs_for_model(outputs: Any) -> dict[str, Any]:
    return summarize_agent_outputs_for_model(outputs)


def normalize_score(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        try:
            number = float(stripped)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None
