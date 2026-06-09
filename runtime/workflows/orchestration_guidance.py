from __future__ import annotations

from typing import Any

from runtime.research_selection import (
    selected_skills_request_company_financial_data,
    selected_skills_request_investment_research,
)
from runtime.swarm.action_policy import (
    declared_source_policy_blocked_tool_targets_from_policy,
    source_policy_blocked_tool_targets_from_policy,
)
from runtime.swarm.source_policy_modes import canonical_wrds_only_source_mode, source_mode_is_wrds_only
from runtime.swarm.tool_policy_resolver import tool_policy_from_state
from runtime.workflows.legacy_orchestration_guidance import (
    legacy_investment_orchestration_guidance,
    legacy_model_role_orchestration_guidance,
    legacy_source_mode_tool_guidance,
    render_source_mode_tool_guidance,
)
from runtime.workflows.routing import workflow_descriptors_from_state


BASE_ORCHESTRATOR_PROMPT = (
    "You are the Orchestrator Agent for a daily-use multi-agent runtime. "
    "Do not solve the task. Preserve the user's original language, choose which specialist "
    "agents are needed, and create a concise tool plan. Return strict JSON only "
    "with keys: translated_task, english_search_query, task_type, depth, "
    "research_questions, required_data_packages, required_agents, rationale, steps. "
    "required_agents must contain booleans "
    "for memory, wrds, research, quant, domain, critic, writer, final_judge. steps is "
    "an array; each step has id, title, action, and optional tool_calls. "
    "For backward compatibility, translated_task should normally equal the original task, "
    "and english_search_query is just the web search query field; it may be Chinese or any "
    "other useful language. Use only available tools. "
    "Capability-specific workflow, source, and data instructions are supplied as orchestration guidance."
)


def build_orchestrator_system_prompt(guidance: list[str]) -> str:
    if not guidance:
        return BASE_ORCHESTRATOR_PROMPT
    guidance_text = " ".join(item for item in guidance if item)
    return f"{BASE_ORCHESTRATOR_PROMPT} Orchestration guidance: {guidance_text}"


def orchestration_guidance_for_state(
    state: dict[str, Any],
    *,
    selected_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    working_state = {**state, "selected_skills": selected_skills}
    instructions: list[str] = []
    trace: list[dict[str, Any]] = []
    workflows = workflow_descriptors_from_state(working_state)

    workflow_guidance = descriptor_orchestration_guidance(working_state)
    if workflow_guidance:
        instructions.extend(workflow_guidance)
        trace.append(
            {
                "source": "capability_workflow_orchestration_guidance",
                "instruction_count": len(workflow_guidance),
            }
        )
    elif not workflows and legacy_investment_guidance_applies(selected_skills):
        legacy_guidance = legacy_investment_orchestration_guidance()
        instructions.extend(legacy_guidance)
        trace.append(
            {
                "source": "legacy_investment_orchestration_guidance",
                "instruction_count": len(legacy_guidance),
            }
        )

    source_guidance = source_mode_orchestration_guidance(working_state)
    if source_guidance:
        instructions.append(source_guidance["instruction"])
        trace.append(source_guidance["trace"])

    if not workflows:
        model_role_guidance = legacy_model_role_orchestration_guidance()
        instructions.extend(model_role_guidance)
        trace.append(
            {
                "source": "legacy_model_role_orchestration_guidance",
                "instruction_count": len(model_role_guidance),
            }
        )

    return {"instructions": unique_guidance(instructions), "trace": trace}


def descriptor_orchestration_guidance(state: dict[str, Any]) -> list[str]:
    guidance: list[str] = []
    for workflow in workflow_descriptors_from_state(state):
        raw_items = workflow.get("orchestration_guidance")
        if isinstance(raw_items, str):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            continue
        guidance.extend(str(item).strip() for item in raw_items if str(item).strip())
    return unique_guidance(guidance)


def legacy_investment_guidance_applies(selected_skills: list[dict[str, Any]]) -> bool:
    return (
        selected_skills_request_investment_research(selected_skills)
        or selected_skills_request_company_financial_data(selected_skills)
    )


def source_mode_orchestration_guidance(state: dict[str, Any]) -> dict[str, Any] | None:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    policy = tool_policy_from_state(state)
    declared_source_mode = str(policy.get("source_mode") or policy.get("source_policy") or "").strip()
    source_mode = declared_source_mode or str(metadata.get("source_mode") or "").strip()
    if not source_mode_is_wrds_only(source_mode):
        return None
    declared_blocked_targets = declared_source_policy_blocked_tool_targets_from_policy(policy)
    blocked_targets = declared_blocked_targets or source_policy_blocked_tool_targets_from_policy(policy)
    blocked_tools = ", ".join(sorted(target.split(":", 1)[1] for target in blocked_targets if target.startswith("tool:")))
    declared_guidance = str(policy.get("source_mode_guidance") or policy.get("source_policy_guidance") or "").strip()
    source = "capability_tool_policy_source_mode" if declared_guidance else "legacy_source_mode_tool_guidance"
    wrds_only_source_mode = canonical_wrds_only_source_mode()
    instruction = (
        render_source_mode_tool_guidance(declared_guidance, source_mode=wrds_only_source_mode, blocked_tools=blocked_tools)
        if declared_guidance
        else legacy_source_mode_tool_guidance(source_mode=wrds_only_source_mode, blocked_tools=blocked_tools)
    )
    return {
        "instruction": instruction,
        "trace": {
            "source": source,
            "source_mode": wrds_only_source_mode,
            "blocked_tool_targets": sorted(blocked_targets),
            "blocked_tool_target_source": (
                "capability_tool_policy_source_mode" if declared_blocked_targets else "legacy_source_policy_tool_targets"
            ),
        },
    }


def unique_guidance(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
