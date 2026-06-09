from __future__ import annotations

from typing import Any

from runtime.swarm.legacy_target_aliases import (
    LEGACY_CODE_TEST_GATE_TARGET,
    LEGACY_COMPLIANCE_APPROVAL_TARGET,
    LEGACY_RESEARCH_EVIDENCE_GATE_TARGET,
)


LEGACY_DOMAIN_WORKFLOW_WRITER_FALLBACK_SOURCE = "legacy_graph_mode_writer_fallback"
LEGACY_DOMAIN_WORKFLOW_POLICING_FALLBACK_SOURCE = "legacy_graph_mode_policing_fallback"
LEGACY_SOURCE_CANDIDATE_ONLY_CAVEAT = (
    "Only source candidates are available; recruit evidence recovery before confirmed synthesis."
)


def legacy_domain_workflow_writer_fallback_source() -> str:
    return LEGACY_DOMAIN_WORKFLOW_WRITER_FALLBACK_SOURCE


def legacy_domain_workflow_policing_fallback_source() -> str:
    return LEGACY_DOMAIN_WORKFLOW_POLICING_FALLBACK_SOURCE


def legacy_domain_workflow_writer_policy(text: str, state: dict[str, Any], *, graph_mode: str) -> str:
    handler = LEGACY_DOMAIN_WORKFLOW_WRITER_POLICIES.get(graph_mode)
    if handler is None:
        return text
    return handler(text, state)


def legacy_domain_workflow_policing_violations(state: dict[str, Any], *, graph_mode: str) -> list[dict[str, Any]]:
    handler = LEGACY_DOMAIN_WORKFLOW_VIOLATION_HANDLERS.get(graph_mode)
    if handler is None:
        return []
    return [
        {
            **violation,
            "source": legacy_domain_workflow_policing_fallback_source(),
            "graph_mode": graph_mode,
        }
        for violation in handler(state)
        if isinstance(violation, dict)
    ]


def legacy_source_candidate_only_caveat() -> str:
    return LEGACY_SOURCE_CANDIDATE_ONLY_CAVEAT


def apply_code_development_writer_policy(text: str, state: dict[str, Any]) -> str:
    if not tests_failed(state):
        return text
    if not contains_any(text, ("完成", "已修复", "通过测试", "tests passed", "successfully fixed", "accepted patch")):
        return text
    return "\n".join(
        [
            "# Code Workflow Guardrail Report",
            "",
            "当前版本不能声称修复完成或测试通过。code-development workflow 的 Test Gate / execution_log 显示测试或工具步骤失败。",
            "",
            "## Required Action",
            "Writer 必须报告失败测试、保留未解决风险，并要求重新进入 patch/test/regression judge 流程。",
            "",
            "## Blocked Draft Preview",
            str(text or "")[:1200],
        ]
    )


def apply_compliance_writer_policy(text: str, state: dict[str, Any]) -> str:
    if not contains_any(text, ("可以发送", "已发送", "可以导出", "已导出", "send the email", "email sent", "export the data", "data exported")):
        return text
    if approval_recorded(state):
        return text
    return "\n".join(
        [
            "# Compliance Workflow Guardrail Report",
            "",
            "当前版本不能批准、发送或导出外部动作。compliance-workflow 要求外发、导出、数据库写入等动作先经过 human approval。",
            "",
            "## Required Action",
            "生成审批请求，列出审批人、动作范围、敏感字段和证据包；审批前只能给出合规观察和风险提示。",
            "",
            "## Blocked Draft Preview",
            str(text or "")[:1200],
        ]
    )


def apply_evidence_research_writer_policy(text: str, state: dict[str, Any]) -> str:
    research = state.get("research_brief") if isinstance(state.get("research_brief"), dict) else {}
    gaps = research.get("evidence_gaps") if isinstance(research.get("evidence_gaps"), list) else []
    if not gaps:
        return text
    if not contains_any(text, ("已证实", "确定证明", "无争议", "confirmed", "proves that", "definitively")):
        return text
    return "\n".join(
        [
            "# Evidence Research Guardrail Report",
            "",
            "当前版本把存在 evidence gaps 的研究写成了强确认结论。evidence-research workflow 要求先通过 citation audit / contradiction map。",
            "",
            "## Evidence Gaps",
            *[f"- {gap}" for gap in gaps[:8]],
            "",
            "## Required Action",
            "将结论降级为待验证判断，或补齐 claim-evidence graph 后重新运行 citation audit。",
            "",
            "## Blocked Draft Preview",
            str(text or "")[:1200],
        ]
    )


def code_workflow_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    if not tests_failed(state):
        return []
    final = str(state.get("final") or state.get("draft_final") or "")
    if not contains_any(final, ("完成", "已修复", "通过测试", "tests passed", "successfully fixed", "accepted patch")):
        return []
    return [
        {
            "agent": "writer",
            "target": LEGACY_CODE_TEST_GATE_TARGET,
            "type": "code_workflow_violation",
            "reason": "writer claimed code success while the code-development Test Gate failed",
            "penalty": "revision_required",
        }
    ]


def compliance_workflow_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    final = str(state.get("final") or state.get("draft_final") or "")
    if not contains_any(final, ("可以发送", "已发送", "可以导出", "已导出", "send the email", "email sent", "export the data", "data exported")):
        return []
    if approval_recorded(state):
        return []
    return [
        {
            "agent": "writer",
            "target": LEGACY_COMPLIANCE_APPROVAL_TARGET,
            "type": "compliance_workflow_violation",
            "reason": "writer approved an external compliance action without human approval",
            "penalty": "approval_required",
        }
    ]


def evidence_workflow_violations(state: dict[str, Any]) -> list[dict[str, Any]]:
    research = state.get("research_brief") if isinstance(state.get("research_brief"), dict) else {}
    gaps = research.get("evidence_gaps") if isinstance(research.get("evidence_gaps"), list) else []
    final = str(state.get("final") or state.get("draft_final") or "")
    if not gaps or not contains_any(final, ("已证实", "确定证明", "无争议", "confirmed", "proves that", "definitively")):
        return []
    return [
        {
            "agent": "writer",
            "target": LEGACY_RESEARCH_EVIDENCE_GATE_TARGET,
            "type": "evidence_workflow_violation",
            "reason": "writer produced a strong evidence-research conclusion while evidence gaps remain",
            "penalty": "revision_required",
        }
    ]


LEGACY_DOMAIN_WORKFLOW_WRITER_POLICIES = {
    "code_development": apply_code_development_writer_policy,
    "compliance_workflow": apply_compliance_writer_policy,
    "evidence_research": apply_evidence_research_writer_policy,
}

LEGACY_DOMAIN_WORKFLOW_VIOLATION_HANDLERS = {
    "code_development": code_workflow_violations,
    "compliance_workflow": compliance_workflow_violations,
    "evidence_research": evidence_workflow_violations,
}


def tests_failed(state: dict[str, Any]) -> bool:
    for step in state.get("execution_log") or []:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "")
        if step_id != "test-runner":
            continue
        if str(step.get("status") or "").lower() == "failed":
            return True
        for call in step.get("tool_calls") or []:
            result = call.get("result") if isinstance(call, dict) else {}
            if isinstance(result, dict) and result.get("ok") is False:
                return True
    return False


def approval_recorded(state: dict[str, Any]) -> bool:
    workflow = domain_workflow(state)
    approval = workflow.get("approval") if isinstance(workflow.get("approval"), dict) else {}
    if str(approval.get("status") or "").lower() in {"approved", "confirmed"}:
        return True
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    return bool(metadata.get("human_approval_confirmed"))


def domain_workflow(state: dict[str, Any]) -> dict[str, Any]:
    workflow = state.get("domain_workflow") if isinstance(state.get("domain_workflow"), dict) else {}
    if workflow:
        return workflow
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    workflow = metadata.get("domain_workflow") if isinstance(metadata.get("domain_workflow"), dict) else {}
    return workflow


def contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(needle.lower() in lowered for needle in needles)
