from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.data_sources import public_safe_data_source_results
from runtime.redaction import redact_sensitive
from runtime.swarm.agent_decisions import runtime_agent_decision_artifacts
from runtime.swarm.agent_outputs import runtime_agent_output_artifacts
from runtime.swarm.legacy_data_gate_permissions import legacy_publication_allowed_field
from runtime.swarm.legacy_quorum_targets import legacy_quorum_flags_from_report
from runtime.workflows.wrds_payload_safety import audit_safe_wrds_result_summary


DEFAULT_AUDIT_LOG_PATH = "logs/agent_runs.jsonl"


def append_run_audit(run: dict[str, Any]) -> None:
    if not audit_log_enabled():
        return
    path = audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = build_audit_record(run)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def audit_log_path() -> Path:
    return Path(os.getenv("AGENT_AUDIT_LOG_PATH", DEFAULT_AUDIT_LOG_PATH))


def audit_log_enabled() -> bool:
    value = os.getenv("AGENT_AUDIT_LOG_ENABLED", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def build_audit_record(run: dict[str, Any]) -> dict[str, Any]:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run.get("run_id"),
        "tenant_id": audit_tenant_id(run),
        "status": run.get("run_status") or ("failed" if run.get("error") else "completed"),
        "degraded_reasons": run.get("degraded_reasons", []),
        "error": truncate_string(run.get("error"), 500),
        "task": run.get("task"),
        "translated_task": run.get("translated_task"),
        "search_query": run.get("search_query") or run.get("english_search_query"),
        "english_search_query": run.get("english_search_query"),
        "route": run.get("route"),
        "os_plan": summarize_os_plan(run.get("metadata", {}).get("os_plan") if isinstance(run.get("metadata"), dict) else None),
        "enabled_capabilities": summarize_enabled_capabilities(
            run.get("metadata", {}).get("enabled_capabilities") if isinstance(run.get("metadata"), dict) else None
        ),
        "permission_grants": summarize_permission_grants(
            run.get("metadata", {}).get("permission_grants") if isinstance(run.get("metadata"), dict) else None
        ),
        "orchestration": summarize_orchestration(run.get("orchestration", {})),
        "selected_skills": [skill.get("name") for skill in run.get("selected_skills", []) if isinstance(skill, dict)],
        "agent_metrics": summarize_agent_metrics(run.get("agent_metrics", [])),
        "plan": summarize_plan(run.get("plan", [])),
        "tool_calls": summarize_tool_calls(run.get("execution_log", [])),
        "wrds_result": audit_safe_wrds_result_summary(run.get("wrds_result", {})),
        "data_source_results": summarize_data_source_results(run.get("data_source_results") or run.get("provider_results")),
        "data_contract": summarize_data_contract(run.get("data_contract", {})),
        "data_gate": summarize_data_gate(run.get("data_gate", {})),
        "research_brief": summarize_research_brief(run.get("research_brief", {})),
        "quant_analysis": summarize_quant_analysis(run.get("quant_analysis", {})),
        "domain_analysis": summarize_domain_analysis(run.get("domain_analysis", {})),
        **summarize_agent_output_artifacts(run),
        "discussion_transcript": summarize_discussion_transcript(run.get("discussion_transcript", [])),
        **summarize_agent_decision_artifacts(run),
        "swarm_governance": summarize_swarm_governance(run),
        "review": run.get("review", {}),
        "final_preview": str(run.get("final") or "")[:800],
    }
    safe = redact_sensitive(record, max_string_length=1_500)
    return safe if isinstance(safe, dict) else {}


def read_run_audit_record(
    run_id: str,
    *,
    path: str | Path | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the latest redacted audit summary for a run id."""

    records = read_run_audit_records(run_id=run_id, path=path, limit=1, tenant_id=tenant_id)
    return records[0] if records else None


def read_run_audit_records(
    *,
    run_id: str | None = None,
    path: str | Path | None = None,
    limit: int = 100,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    audit_path = Path(path) if path is not None else audit_log_path()
    if not audit_path.exists():
        return []
    records: list[dict[str, Any]] = []
    with audit_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            if run_id and item.get("run_id") != run_id:
                continue
            if tenant_id is not None and str(item.get("tenant_id") or "default") != str(tenant_id):
                continue
            safe = redact_sensitive(item, max_string_length=1_500)
            if isinstance(safe, dict):
                records.append(safe)
    if limit <= 0:
        return []
    return list(reversed(records[-limit:]))


def audit_tenant_id(run: dict[str, Any]) -> str:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return str(metadata.get("tenant_id") or os_plan.get("tenant_id") or "default")


def summarize_swarm_governance(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get("swarm_metrics") if isinstance(run.get("swarm_metrics"), dict) else {}
    quorum = run.get("quorum_trace") if isinstance(run.get("quorum_trace"), dict) else {}
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    legacy_quorum_flags = legacy_quorum_flags_from_report(quorum)
    return {
        "signal_count": metrics.get("signal_count"),
        "stop_signal_count": metrics.get("stop_signal_count"),
        "blocking_signal_count": metrics.get("blocking_signal_count"),
        "blocking_targets": list_field(metrics.get("blocking_targets")),
        "committed_candidate": committed.get("label"),
        "quorum_status": quorum.get("status"),
        "blocked_conclusion_targets": list_field(quorum.get("blocked_conclusion_targets")),
        **legacy_quorum_flags,
    }


def summarize_os_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    return {
        "intent": plan.get("intent"),
        "required_capabilities": list_field(plan.get("required_capabilities")),
        "available_capabilities": list_field(plan.get("available_capabilities")),
        "missing_capabilities": list_field(plan.get("missing_capabilities")),
        "auto_enabled": list_field(plan.get("auto_enabled")),
        "needs_confirmation_count": len(plan.get("needs_confirmation") if isinstance(plan.get("needs_confirmation"), list) else []),
        "connection_requirements": plan.get("connection_requirements") if isinstance(plan.get("connection_requirements"), list) else [],
        "runtime_ready": plan.get("runtime_ready"),
    }


def summarize_enabled_capabilities(capabilities: Any) -> list[dict[str, Any]]:
    if not isinstance(capabilities, list):
        return []
    return [
        {
            "id": item.get("id"),
            "risk_level": item.get("risk_level"),
            "capability_types": list_field(item.get("capability_types")),
        }
        for item in capabilities
        if isinstance(item, dict)
    ]


def summarize_permission_grants(grants: Any) -> list[dict[str, Any]]:
    if not isinstance(grants, list):
        return []
    return [
        {
            "capability_id": item.get("capability_id"),
            "auto_enable": item.get("auto_enable"),
            "permission_grants": list_field(item.get("permission_grants")),
            "blocked_permissions": list_field(item.get("blocked_permissions")),
            "risk_level": item.get("risk_level"),
        }
        for item in grants
        if isinstance(item, dict)
    ]


def summarize_orchestration(orchestration: Any) -> dict[str, Any]:
    if not isinstance(orchestration, dict):
        return {}
    return {
        "task_type": orchestration.get("task_type"),
        "depth": orchestration.get("depth"),
        "committee": orchestration.get("committee"),
        "required_agents": orchestration.get("required_agents"),
        "rationale": truncate_string(orchestration.get("rationale"), 500),
    }


def summarize_data_source_results(results: Any) -> list[dict[str, Any]]:
    summaries = []
    for item in public_safe_data_source_results(results):
        payload = item.get("normalized_payload") if isinstance(item.get("normalized_payload"), dict) else {}
        summaries.append(
            {
                "provider_id": item.get("provider_id"),
                "source_kind": item.get("source_kind"),
                "dataset_kind": item.get("dataset_kind"),
                "ok": item.get("ok"),
                "status": payload.get("status"),
                "row_count": payload.get("row_count"),
                "quarterly_row_count": payload.get("quarterly_row_count"),
                "tool_name": payload.get("tool_name"),
            }
        )
    return summaries


def summarize_plan(plan: Any) -> list[dict[str, Any]]:
    if not isinstance(plan, list):
        return []
    summary = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        tool_calls = step.get("tool_calls") or []
        summary.append(
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "action": step.get("action"),
                "tools": [call.get("name") for call in tool_calls if isinstance(call, dict)],
            }
        )
    return summary


def summarize_data_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    return {
        "status": contract.get("status"),
        "mode": contract.get("mode"),
        "as_of_date": contract.get("as_of_date"),
        "forbidden_sources_after_as_of": contract.get("forbidden_sources_after_as_of"),
        "ticker": contract.get("ticker"),
        "company_name": contract.get("company_name"),
        "gvkey": contract.get("gvkey"),
        "cik": contract.get("cik"),
    }


def summarize_data_gate(gate: Any) -> dict[str, Any]:
    if not isinstance(gate, dict):
        return {}
    errors = gate.get("critical_errors") if isinstance(gate.get("critical_errors"), list) else []
    warnings = gate.get("warnings") if isinstance(gate.get("warnings"), list) else []
    publication_allowed_field = legacy_publication_allowed_field()
    return {
        "status": gate.get("status"),
        "blocking": gate.get("blocking"),
        "quality_score": gate.get("quality_score"),
        "data_completeness_score": gate.get("data_completeness_score"),
        "decision_readiness_score": gate.get("decision_readiness_score"),
        publication_allowed_field: gate.get(publication_allowed_field),
        "critical_error_count": len(errors),
        "warning_count": len(warnings),
        "decision_blocker_count": len(gate.get("decision_blockers") if isinstance(gate.get("decision_blockers"), list) else []),
        "critical_errors": [
            {
                "code": item.get("code"),
                "message": truncate_string(item.get("message"), 240),
                "period": item.get("period"),
                "metric": item.get("metric"),
            }
            for item in errors
            if isinstance(item, dict)
        ][:10],
    }


def summarize_agent_metrics(metrics: Any) -> list[dict[str, Any]]:
    if not isinstance(metrics, list):
        return []
    summary = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        summary.append(
            {
                "agent": metric.get("agent"),
                "model": metric.get("model"),
                "model_used": bool(metric.get("model_used", True)),
                "duration_ms": metric.get("duration_ms"),
                "status": metric.get("status"),
                "failure_reason": truncate_string(metric.get("failure_reason"), 500),
            }
        )
    return summary


def summarize_research_brief(research_brief: Any) -> dict[str, Any]:
    if not isinstance(research_brief, dict):
        return {}
    return {
        "status": research_brief.get("status"),
        "key_facts": list_field(research_brief.get("key_facts")),
        "evidence_gaps": list_field(research_brief.get("evidence_gaps")),
        "reliability": research_brief.get("reliability"),
        "source_grounding": research_brief.get("source_grounding"),
        "source_count": len(research_brief.get("sources", [])) if isinstance(research_brief.get("sources"), list) else 0,
    }


def summarize_quant_analysis(quant_analysis: Any) -> dict[str, Any]:
    if not isinstance(quant_analysis, dict):
        return {}
    return {
        "status": quant_analysis.get("status"),
        "metrics": quant_analysis.get("metrics") if isinstance(quant_analysis.get("metrics"), list) else [],
        "missing_data": list_field(quant_analysis.get("missing_data")),
        "data_quality": quant_analysis.get("data_quality"),
    }


def summarize_domain_analysis(domain_analysis: Any) -> dict[str, Any]:
    if not isinstance(domain_analysis, dict):
        return {}
    return {
        "status": domain_analysis.get("status"),
        "domain": domain_analysis.get("domain"),
        "judgment": truncate_string(domain_analysis.get("judgment"), 800),
        "risks": list_field(domain_analysis.get("risks")),
        "missing_evidence": list_field(domain_analysis.get("missing_evidence")),
        "confidence": domain_analysis.get("confidence"),
    }


def summarize_agent_output_artifacts(run: dict[str, Any]) -> dict[str, Any]:
    summaries = {
        str(artifact.get("artifact_id") or "agent_outputs"): summarize_agent_outputs(
            artifact.get("value")
        )
        for artifact in runtime_agent_output_artifacts(run)
        if isinstance(artifact, dict)
    }
    if "agent_outputs" in summaries:
        source = "agent_outputs"
    elif "legacy_agent_outputs" in summaries:
        source = "legacy_agent_outputs"
    else:
        source = "none"
    return {
        "agent_outputs": summaries.get(
            "agent_outputs", summaries.get("legacy_agent_outputs", {})
        ),
        "legacy_agent_outputs": summaries.get("legacy_agent_outputs", {}),
        "agent_output_source": source,
    }


def summarize_agent_outputs(outputs: Any) -> dict[str, Any]:
    if not isinstance(outputs, dict):
        return {}
    summary = {}
    for name, output in outputs.items():
        if not isinstance(output, dict):
            continue
        summary[name] = {
            "status": output.get("status"),
            "score": output.get("score"),
            "confidence": output.get("confidence"),
            "hard_veto": bool(output.get("hard_veto")),
            "thesis": truncate_string(output.get("thesis"), 500),
            "missing_data": list_field(output.get("missing_data")),
            "risks": list_field(output.get("risks")),
            "role_assessment": output.get("role_assessment") if isinstance(output.get("role_assessment"), dict) else {},
        }
    return summary


def summarize_agent_decision_artifacts(run: dict[str, Any]) -> dict[str, Any]:
    summaries = {
        str(artifact.get("artifact_id") or "agent_decision"): summarize_agent_decision(
            artifact.get("value")
        )
        for artifact in runtime_agent_decision_artifacts(run)
        if isinstance(artifact, dict)
    }
    if "agent_decision" in summaries:
        source = "agent_decision"
    elif "legacy_agent_decision" in summaries:
        source = "legacy_agent_decision"
    else:
        source = "none"
    return {
        "agent_decision": summaries.get(
            "agent_decision", summaries.get("legacy_agent_decision", {})
        ),
        "legacy_agent_decision": summaries.get("legacy_agent_decision", {}),
        "agent_decision_source": source,
    }


def summarize_discussion_transcript(transcript: Any) -> list[dict[str, Any]]:
    if not isinstance(transcript, list):
        return []
    summary = []
    for turn in transcript[:24]:
        if not isinstance(turn, dict):
            continue
        summary.append(
            {
                "round": turn.get("round"),
                "speaker": turn.get("speaker"),
                "target": turn.get("target"),
                "claim": truncate_string(turn.get("claim"), 300),
                "challenge": truncate_string(turn.get("challenge"), 300),
                "response": truncate_string(turn.get("response"), 300),
                "score": turn.get("score"),
                "confidence": turn.get("confidence"),
            }
        )
    return summary


def summarize_agent_decision(decision: Any) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    return {
        "status": decision.get("status"),
        "decision": truncate_string(decision.get("decision"), 800),
        "final_decision": decision.get("final_decision"),
        "conviction": decision.get("conviction"),
        "position_size": decision.get("position_size"),
        "time_horizon": decision.get("time_horizon"),
        "core_thesis": truncate_string(decision.get("core_thesis"), 800),
        "main_risk": truncate_string(decision.get("main_risk"), 500),
        "invalidation_point": truncate_string(decision.get("invalidation_point"), 500),
        "consensus": list_field(decision.get("consensus")),
        "dissent": list_field(decision.get("dissent")),
        "hard_vetoes": list_field(decision.get("hard_vetoes")),
        "confidence": decision.get("confidence"),
        "open_questions": list_field(decision.get("open_questions")),
        "evidence_limitations": list_field(decision.get("evidence_limitations")),
    }


def summarize_tool_calls(execution_log: Any) -> list[dict[str, Any]]:
    if not isinstance(execution_log, list):
        return []
    calls = []
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            result = call.get("result") or {}
            data = result.get("data") or {}
            calls.append(
                {
                    "step_id": step.get("step_id"),
                    "step_title": step.get("title"),
                    "name": call.get("name"),
                    "args": safe_tool_args(call.get("args") or {}),
                    "ok": result.get("ok"),
                    "error": truncate_string(result.get("error"), 300),
                    "status_code": data.get("status_code"),
                    "url": data.get("url"),
                    "title": data.get("title"),
                    "text_quality": data.get("text_quality"),
                    "word_count": data.get("word_count"),
                    "result_count": len(data.get("results", [])) if isinstance(data.get("results"), list) else None,
                }
            )
    return calls


def safe_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    safe = redact_sensitive(args, max_string_length=500)
    return safe if isinstance(safe, dict) else {}


def list_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def truncate_string(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."
