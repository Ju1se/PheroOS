from __future__ import annotations

from typing import Any

from runtime.data_gate import apply_wrds_only_report_policy
from runtime.output_contract import apply_output_policy, evidence_policy_from_state, output_policy_from_state
from runtime.swarm.legacy_output_phrases import (
    legacy_formal_recommendation_present,
    legacy_formal_valuation_writer_action,
)
from runtime.swarm.stop_signal import apply_swarm_report_policy
from runtime.swarm.stop_policy import (
    action_blocked_by_stop_policy,
    active_blocking_signals,
    canonical_action,
    stop_policy_rules,
    stop_signal_policy_from_state,
)
from runtime.swarm.evidence_contract import validate_writer_evidence_contract
from runtime.workflows.legacy_guardrails import (
    legacy_domain_workflow_writer_fallback_source,
    legacy_domain_workflow_writer_policy,
)


def writer_system_prompt(state: dict[str, Any] | None = None) -> str:
    prompt = (
        "You are the Writer / Synthesis Agent. Produce the final answer in concise Chinese. "
        "For direct/simple tasks, answer normally from general knowledge. For governed, research, "
        "coding, compliance, data-heavy, or workflow tasks, only organize and express evidence, "
        "claims, tool results, agent outputs, domain workflow outputs, and critic findings already "
        "present in runtime context. "
        "Do not add unverified facts. If the critic flags source gaps, make the limitations "
        "prominent before any conclusion. If critic status is REJECT_CONDITIONAL or REJECT_FATAL, "
        "return a defect memo rather than a normal report. "
        "If evidence_graph contains contamination or quarantine blockers, do not use the contaminated "
        "artifact as evidence."
    )
    policy = policy_prompt_summary(state or {}, actor="writer")
    return f"{prompt} {policy}" if policy else prompt


def apply_writer_guardrails(text: str, state: dict[str, Any]) -> str:
    guarded = apply_wrds_only_report_policy(str(text or "").strip(), state)
    guarded = apply_stop_action_policy(guarded, state)
    if is_guardrail_report(guarded):
        return guarded
    guarded = apply_swarm_report_policy(guarded, state)
    if is_guardrail_report(guarded):
        return guarded
    guarded = apply_output_policy(guarded, state, actor="writer")
    if is_guardrail_report(guarded):
        return guarded
    guarded = apply_evidence_steward_policy(guarded, state)
    if is_guardrail_report(guarded):
        return guarded
    guarded = apply_evidence_graph_contract_policy(guarded, state)
    if is_guardrail_report(guarded):
        return guarded
    guarded = apply_domain_workflow_policy(guarded, state)
    if is_guardrail_report(guarded):
        return guarded
    return guarded


def apply_stop_action_policy(text: str, state: dict[str, Any], *, actor: str = "writer") -> str:
    for action in inferred_actions(text, state=state, actor=actor):
        signal = action_blocked_by_stop_policy(state, action)
        if signal:
            return "\n".join(
                [
                    "# Stop-Signal Action Policy Guardrail Report",
                    "",
                    f"当前版本触发 `{action}`，但 capability-declared stop-signal policy 已阻断该动作。",
                    "",
                    "## Blocking Signal",
                    f"- `{signal.get('target')}`: {signal.get('content') or 'active stop-signal'}",
                    "",
                    "## Required Action",
                    "先解决对应 stop-signal 或 recovery protocol，再重新生成输出。Writer 只能表达未被 policy 阻断的内容。",
                    "",
                    "## Blocked Draft Preview",
                    str(text or "")[:1200],
                ]
            )
    return text


def inferred_writer_actions(text: str, state: dict[str, Any] | None = None) -> list[str]:
    return inferred_actions(text, state=state, actor="writer")


def inferred_actions(text: str, state: dict[str, Any] | None = None, *, actor: str) -> list[str]:
    actor = str(actor or "writer").strip().lower()
    policy = stop_signal_policy_from_state(state or {})
    actions = declared_actions_for_actor(text, policy, actor=actor)
    if stop_policy_action_markers(policy):
        return actions
    if actor == "writer" and not actions and legacy_formal_recommendation_present(text):
        actions.append(legacy_formal_valuation_writer_action())
    if actor == "writer":
        if contains_any(str(text or ""), ("已证实", "确定证明", "无争议", "confirmed", "proves that", "definitively")):
            append_unique(actions, "writer:confirmed_claim")
        if contains_any(str(text or ""), ("可以发送", "已发送", "可以导出", "已导出", "send the email", "email sent", "export the data", "data exported")):
            append_unique(actions, "writer:approval_claim")
        if contains_any(str(text or ""), ("完成", "已修复", "通过测试", "tests passed", "successfully fixed", "accepted patch")):
            append_unique(actions, "writer:claim_tests_passed")
    return actions


def declared_writer_actions(text: str, policy: dict[str, Any]) -> list[str]:
    return declared_actions_for_actor(text, policy, actor="writer")


def declared_actions_for_actor(text: str, policy: dict[str, Any], *, actor: str) -> list[str]:
    haystack = normalize_action_text(text)
    if not haystack:
        return []
    actor_prefix = f"{str(actor or '').strip().lower()}:"
    actions: list[str] = []
    for marker in stop_policy_action_markers(policy):
        action = canonical_action(marker.get("action"))
        if not action.startswith(actor_prefix):
            continue
        if marker_matches(haystack, marker):
            append_unique(actions, action)
    return actions


def stop_policy_action_markers(policy: dict[str, Any]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for source in (policy, *[rule for rule in policy.get("rules") or [] if isinstance(rule, dict)]):
        for item in source.get("action_markers") or source.get("action_cues") or []:
            if isinstance(item, dict):
                markers.append(dict(item))
    return markers


def marker_matches(haystack: str, marker: dict[str, Any]) -> bool:
    phrases = string_list(marker.get("phrases") or marker.get("keywords") or marker.get("markers"))
    return any(normalize_action_text(phrase) in haystack for phrase in phrases if normalize_action_text(phrase))


def normalize_action_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def policy_prompt_summary(state: dict[str, Any], *, actor: str) -> str:
    output_policy = output_policy_from_state(state)
    evidence_policy = evidence_policy_from_state(state)
    stop_policy = stop_signal_policy_from_state(state)
    blockers = active_blocking_signals(state)
    parts: list[str] = []
    allowed_modes = string_list(output_policy.get("allowed_output_modes"))
    if allowed_modes:
        parts.append(f"Allowed output modes: {', '.join(allowed_modes)}.")
    required_caveats = string_list(output_policy.get("required_caveats"))
    if required_caveats:
        parts.append(f"Required caveats: {', '.join(required_caveats)}.")
    blocked_phrases = string_list(output_policy.get("blocked_phrases"))
    if blocked_phrases:
        parts.append(f"Blocked phrases: {', '.join(blocked_phrases)}.")
    if output_policy.get("defect_memo_on_block"):
        parts.append("If an active stop-signal blocks publication, output a defect memo.")
    defect_markers = string_list(output_policy.get("defect_memo_markers"))
    if defect_markers:
        parts.append(f"Accepted defect memo markers: {', '.join(defect_markers)}.")
    if evidence_policy:
        if evidence_policy.get("citation_required"):
            parts.append("Citations are required for final claims.")
        parts.append("Raw data is not allowed in final output.")
        unsupported = str(evidence_policy.get("unsupported_claim_action") or "").strip()
        if unsupported:
            parts.append(f"Unsupported claim action: {unsupported}.")
    blocked_actions = policy_blocked_actions_for_actor(stop_policy, actor)
    if blocked_actions:
        parts.append(f"Capability stop policy can block these {actor} actions: {', '.join(blocked_actions)}.")
    if blockers:
        targets = sorted({str(signal.get("target") or "") for signal in blockers if str(signal.get("target") or "").strip()})
        if targets:
            parts.append(f"Active blocking targets: {', '.join(targets)}.")
    if not parts:
        return ""
    return "Capability policy summary: " + " ".join(parts)


def policy_blocked_actions_for_actor(policy: dict[str, Any], actor: str) -> list[str]:
    prefix = f"{actor}:"
    actions: list[str] = []
    for value in string_list(policy.get("blocked_actions")):
        if value.startswith(prefix) and value not in actions:
            actions.append(value)
    for rule in policy.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        for value in string_list(rule.get("blocked_actions") or rule.get("actions")):
            if value.startswith(prefix) and value not in actions:
                actions.append(value)
    return actions


def apply_evidence_steward_policy(text: str, state: dict[str, Any]) -> str:
    steward = state.get("evidence_steward_report") if isinstance(state.get("evidence_steward_report"), dict) else {}
    blocked_claim = claim_present(text, steward.get("blocked_claims"))
    unsupported_claim = claim_present(text, steward.get("unsupported_claims"))
    if not blocked_claim and not unsupported_claim:
        return text
    claim = blocked_claim or unsupported_claim or {}
    status = "blocked_by_data_gate" if blocked_claim else "unsupported"
    return "\n".join(
        [
            "# Evidence Steward Guardrail Report",
            "",
            f"当前版本包含 Evidence Steward 标记为 `{status}` 的 claim，因此不能作为最终报告发布。",
            "",
            "## Rejected Claim",
            f"- {claim.get('content') or 'unsupported claim'}",
            "",
            "## Required Action",
            "删除该 claim，或先通过 deterministic metric registry / verified evidence graph 补齐证据链后重新运行。",
            "",
            "## Blocked Draft Preview",
            str(text or "")[:1200],
        ]
    )


def apply_evidence_graph_contract_policy(text: str, state: dict[str, Any]) -> str:
    if not isinstance(state.get("evidence_graph"), dict) and not isinstance(state.get("evidence_steward_report"), dict):
        return text
    violations = validate_writer_evidence_contract(text, state)
    actionable = [item for item in violations if item.get("code") not in {"forbidden_phrase", "committed_candidate_mismatch"}]
    if not actionable:
        return text
    return "\n".join(
        [
            "# Evidence Graph Contract Guardrail Report",
            "",
            "当前版本违反 Evidence Graph writer contract，因此不能作为最终报告发布。",
            "",
            "## Contract Violations",
            *[f"- `{item.get('code')}`: {item.get('message')}" for item in actionable[:8]],
            "",
            "## Required Action",
            "Writer 只能使用 verified_claims / caveated_claims / required_caveats / allowed_metrics。请删除新增或未证实的强结论，或先补齐 Evidence Graph 边。",
            "",
            "## Blocked Draft Preview",
            str(text or "")[:1200],
        ]
    )


def apply_domain_workflow_policy(text: str, state: dict[str, Any]) -> str:
    declared = apply_declared_domain_gate_policy(text, state)
    if is_guardrail_report(declared) or capability_writer_stop_policy_declared(state):
        return declared
    workflow = domain_workflow(state)
    graph_mode = str(workflow.get("graph_mode") or "")
    return apply_legacy_domain_workflow_policy(text, state, graph_mode=graph_mode)


def apply_legacy_domain_workflow_policy(text: str, state: dict[str, Any], *, graph_mode: str) -> str:
    guarded = legacy_domain_workflow_writer_policy(text, state, graph_mode=graph_mode)
    if not is_guardrail_report(guarded):
        return guarded
    return attach_legacy_writer_fallback_source(guarded, graph_mode=graph_mode)


def attach_legacy_writer_fallback_source(report: str, *, graph_mode: str) -> str:
    return "\n".join(
        [
            str(report),
            "",
            "## Policy Source",
            f"- `{legacy_domain_workflow_writer_fallback_source()}`: `{graph_mode}`",
        ]
    )


def apply_declared_domain_gate_policy(text: str, state: dict[str, Any]) -> str:
    policy = stop_signal_policy_from_state(state)
    if not policy_blocked_actions_for_actor(policy, "writer"):
        return text
    workflow = domain_workflow(state)
    gate_status = workflow.get("gate_status") if isinstance(workflow.get("gate_status"), dict) else {}
    if not bool(gate_status.get("blocked")):
        return text
    actions = set(inferred_writer_actions(text, state=state))
    if not actions:
        return text
    trigger_targets = declared_gate_trigger_targets(policy, actions)
    if not trigger_targets:
        return text
    existing = list(state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else [])
    additions = [
        {
            "type": "stop_signal",
            "target": target,
            "blocking": True,
            "verification_state": "blocking",
            "source_module": "domain_workflow",
            "source_agent": "domain_workflow",
            "content": f"{workflow.get('workflow_id') or workflow.get('graph_mode') or 'domain workflow'} gate blocked writer action.",
            "metadata": {"gate_status": gate_status.get("status"), "blocking_gates": gate_status.get("blocking_gates", [])},
        }
        for target in trigger_targets
    ]
    return apply_stop_action_policy(text, {**state, "stop_signals": [*existing, *additions]})


def capability_writer_stop_policy_declared(state: dict[str, Any]) -> bool:
    return bool(policy_blocked_actions_for_actor(stop_signal_policy_from_state(state), "writer"))


def declared_gate_trigger_targets(policy: dict[str, Any], actions: set[str]) -> list[str]:
    targets: list[str] = []
    for rule in stop_policy_rules(policy):
        blocked_actions = {str(action) for action in rule.get("blocked_actions") or []}
        if not blocked_actions.intersection(actions):
            continue
        for target in rule.get("trigger_targets") or []:
            value = str(target or "").strip()
            if value and value not in targets:
                targets.append(value)
    return targets


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


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def claim_present(text: str, claims: Any) -> dict[str, Any] | None:
    haystack = str(text or "").lower()
    if not isinstance(claims, list):
        return None
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        content = str(claim.get("content") or "").strip()
        if len(content) < 16:
            continue
        if content.lower() in haystack:
            return claim
    return None


def is_guardrail_report(text: str) -> bool:
    return str(text or "").lstrip().startswith("# ") and "Guardrail Report" in str(text or "")[:120]
