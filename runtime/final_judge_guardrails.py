from __future__ import annotations

from typing import Any

from runtime.output_contract import apply_output_policy
from runtime.writer_guardrails import apply_stop_action_policy, apply_writer_guardrails, policy_prompt_summary


def final_judge_system_prompt(state: dict[str, Any] | None = None) -> str:
    prompt = (
        "You are the GLM Final Judge. Perform a final fact and logic check on the draft. "
        "Do not add new facts. Preserve limitations from Research, Quant, Committee, Domain, and Critic. "
        "If the draft overclaims, revise it minimally. Never turn unresolved data defects, active blockers, "
        "or missing evidence into stronger conclusions. If evidence_graph contains contamination or quarantine "
        "blockers, remove any claim that depends on the contaminated artifact. Return the final user-facing "
        "answer in Chinese."
    )
    policy = policy_prompt_summary(state or {}, actor="final_judge")
    return f"{prompt} {policy}" if policy else prompt


def apply_final_judge_guardrails(text: str, state: dict[str, Any]) -> str:
    guarded = apply_output_policy(text, state, actor="final_judge")
    if str(guarded or "").lstrip().startswith("# ") and "Guardrail Report" in str(guarded or "")[:120]:
        return guarded
    guarded = apply_stop_action_policy(guarded, state, actor="final_judge")
    if str(guarded or "").lstrip().startswith("# ") and "Guardrail Report" in str(guarded or "")[:120]:
        return guarded
    return apply_writer_guardrails(text, state)
