from __future__ import annotations

from typing import Any

from runtime.agent_metrics import metric_started_at, record_agent_metric
from runtime.state import AgentState
from runtime.workflows.domain_execution import (
    attach_domain_workflow_stop_signals,
    available_tool_names,
    domain_workflow_from_state,
    merge_metadata,
    workflow_agents_by_type,
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
    )
    trace = build_workflow_trace(state, workflow=workflow, execution_plan=execution_plan)
    updated = {**result, "plan": execution_plan, "domain_workflow": trace}
    return merge_metadata(updated, domain_workflow=trace)


def build_execution_plan(*, task: str, available_tools: set[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "id": "policy-interpretation",
            "title": "Policy interpretation",
            "action": "Interpret relevant policy text into obligations, exceptions, and prohibited actions.",
            "tool_calls": [],
        },
        {
            "id": "dlp-rbac-approval-gates",
            "title": "DLP, RBAC, and approval gates",
            "action": "Check PII, sensitive spans, access-control constraints, and human-approval requirements.",
            "tool_calls": [],
        },
        {
            "id": "case-evidence-map",
            "title": "Compliance evidence map",
            "action": "Map each finding to policy, clause, case evidence, or unresolved gap.",
            "tool_calls": [],
        },
    ]
    if "read_file" in available_tools and ("policy_path" in task or "document_path" in task):
        steps.insert(
            0,
            {
                "id": "read-policy-document",
                "title": "Read policy document",
                "action": "Read a user-provided policy document path before interpretation.",
                "tool_calls": [],
            },
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
                        "You are the Compliance Workflow Research Agent. Do not give legal advice and do not approve "
                        "external actions. Extract obligations, sensitive-data risks, RBAC constraints, approval needs, "
                        "retention issues, evidence gaps, and escalation triggers. Return strict JSON with keys: "
                        "status, sources, key_facts, evidence_gaps, reliability, source_grounding."
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
        result = attach_compliance_node_outputs(state, result)
        record_agent_metric(
            agent="compliance_research_agent",
            model=model_used,
            started_at=started_at,
            status="completed_with_fallback" if fallback_reason else "completed",
            failure_reason=fallback_reason,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        record_agent_metric(
            agent="compliance_research_agent",
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
        "workflow_id": workflow.get("workflow_id") or "compliance-workflow",
        "graph_mode": "compliance_workflow",
        "domain_nodes": workflow.get("ordered_nodes") or [],
        "graph_nodes": workflow.get("graph_nodes") or [],
        "agents": workflow_agents_by_type(state, "compliance_workflow_member"),
        "required_gates": workflow.get("required_gates") or [],
        "execution_plan": execution_plan,
        "node_outputs": build_compliance_node_outputs(state, research_brief={}),
        "guardrails": [
            "external actions require human approval",
            "PII and sensitive spans must be redacted before output",
            "RBAC gaps block access or export recommendations",
            "legal-advice claims must be downgraded to compliance workflow observations",
        ],
        "writer_policy": workflow.get("writer_policy"),
    }


def attach_compliance_node_outputs(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    workflow = dict(domain_workflow_from_state({**state, **result}))
    research = result.get("research_brief") if isinstance(result.get("research_brief"), dict) else {}
    node_outputs = dict(workflow.get("node_outputs") if isinstance(workflow.get("node_outputs"), dict) else {})
    node_outputs.update(build_compliance_node_outputs(state, research_brief=research))
    workflow["node_outputs"] = node_outputs
    workflow["approval"] = node_outputs.get("approval_coordinator", {})
    workflow["compliance_evidence_map"] = node_outputs.get("case_evidence_steward", {})
    workflow["gate_status"] = compliance_gate_status(node_outputs)
    updated = {**result, "domain_workflow": workflow}
    return attach_domain_workflow_stop_signals(state, merge_metadata(updated, domain_workflow=workflow))


def build_compliance_node_outputs(state: dict[str, Any], *, research_brief: dict[str, Any]) -> dict[str, Any]:
    policy = policy_interpreter_node(state, research_brief=research_brief)
    obligations = clause_obligation_extractor_node(research_brief=research_brief)
    dlp = dlp_privacy_auditor_node(state, research_brief=research_brief)
    rbac = rbac_access_control_node(state, research_brief=research_brief)
    approval = approval_coordinator_node(state, dlp=dlp, rbac=rbac)
    evidence = case_evidence_steward_node(research_brief=research_brief, policy=policy, obligations=obligations)
    risk = risk_escalation_node(dlp=dlp, rbac=rbac, approval=approval)
    return {
        "policy_interpreter": policy,
        "clause_obligation_extractor": obligations,
        "dlp_privacy_auditor": dlp,
        "rbac_access_control": rbac,
        "approval_coordinator": approval,
        "case_evidence_steward": evidence,
        "risk_escalation": risk,
    }


def policy_interpreter_node(state: dict[str, Any], *, research_brief: dict[str, Any]) -> dict[str, Any]:
    task = str(state.get("task") or "")
    scope = "mixed" if any(word in task.lower() for word in ["contract", "policy", "regulation", "法规", "合同"]) else "internal_policy"
    return {
        "status": "completed",
        "policy_scope": scope,
        "allowed_actions": ["summarize", "classify", "draft_internal_memo"],
        "restricted_actions": ["external_send", "database_write", "credential_export"],
        "uncertainties": research_brief.get("evidence_gaps", []),
    }


def clause_obligation_extractor_node(*, research_brief: dict[str, Any]) -> dict[str, Any]:
    facts = research_brief.get("key_facts") if isinstance(research_brief.get("key_facts"), list) else []
    return {
        "status": "completed" if facts else "pending_evidence",
        "obligations": facts[:6],
        "missing_clauses": research_brief.get("evidence_gaps", []),
    }


def dlp_privacy_auditor_node(state: dict[str, Any], *, research_brief: dict[str, Any]) -> dict[str, Any]:
    text = " ".join([str(state.get("task") or ""), " ".join(map(str, research_brief.get("key_facts", []) or []))])
    lower = text.lower()
    classes = []
    if any(token in lower for token in ["ssn", "身份证", "phone", "email", "@"]):
        classes.append("pii")
    if any(token in lower for token in ["customer", "客户", "employee", "员工"]):
        classes.append("customer_or_employee_data")
    return {
        "status": "blocked" if classes else "passed",
        "blocking": bool(classes),
        "sensitive_data_classes": classes,
        "redaction_required": bool(classes),
    }


def rbac_access_control_node(state: dict[str, Any], *, research_brief: dict[str, Any]) -> dict[str, Any]:
    task = str(state.get("task") or "").lower()
    restricted = any(word in task for word in ["hr", "payroll", "salary", "employee", "客户名单", "薪酬"])
    return {
        "status": "blocked" if restricted else "passed",
        "blocking": restricted,
        "decision": "deny_or_mask" if restricted else "allow_read_only",
        "reason": "Sensitive HR/customer data requires explicit role grant." if restricted else "No restricted data class detected.",
    }


def approval_coordinator_node(state: dict[str, Any], *, dlp: dict[str, Any], rbac: dict[str, Any]) -> dict[str, Any]:
    task = str(state.get("task") or "").lower()
    external_action = any(word in task for word in ["send", "email", "export", "external", "发送", "外发", "导出"])
    required = external_action or bool(dlp.get("blocking")) or bool(rbac.get("blocking"))
    return {
        "status": "pending_approval" if required else "not_required",
        "approval_required": required,
        "requested_action": "external_or_sensitive_action" if required else "read_only_analysis",
    }


def case_evidence_steward_node(
    *,
    research_brief: dict[str, Any],
    policy: dict[str, Any],
    obligations: dict[str, Any],
) -> dict[str, Any]:
    facts = research_brief.get("key_facts") if isinstance(research_brief.get("key_facts"), list) else []
    return {
        "status": "mapped" if facts else "evidence_gap",
        "links": [
            {"claim": fact, "policy_scope": policy.get("policy_scope"), "support": "research_brief"}
            for fact in facts[:8]
        ],
        "unmapped_obligations": obligations.get("missing_clauses", []),
    }


def risk_escalation_node(*, dlp: dict[str, Any], rbac: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
    blockers = [name for name, gate in {"dlp": dlp, "rbac": rbac, "approval": approval}.items() if gate.get("blocking") or gate.get("approval_required")]
    return {
        "status": "escalate" if blockers else "normal",
        "severity": "high" if blockers else "low",
        "blocking_gates": blockers,
    }


def compliance_gate_status(node_outputs: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        name
        for name, output in node_outputs.items()
        if isinstance(output, dict) and (output.get("blocking") or output.get("status") in {"blocked", "pending_approval"})
    ]
    return {"status": "blocked" if blockers else "passed", "blocked": bool(blockers), "blocking_gates": blockers}
