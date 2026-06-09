from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from runtime.agent_metrics import (
    current_agent_metrics,
    metric_started_at,
    record_agent_metric,
    reset_agent_metrics,
    start_agent_metrics,
)
from runtime.audit_log import append_run_audit
from runtime.capability_registry import CapabilityRegistry
from runtime.capability_runtime import CapabilityEntrypointError, load_capability_descriptor, load_function, safe_entrypoint_path
from runtime.data_gate import (
    DATA_CONTRACT_DATA_GATE_REQUIRED_SOURCE,
    data_gate_failed,
    data_gate_required_decision,
    data_gate_publication_blocked,
)
from runtime.data_sources import public_safe_data_source_results
from runtime.input_envelope import build_input_envelope, preflight_input_envelope
from runtime.legacy_agent_registry import (
    legacy_committee_agent_catalog_metadata,
    selected_agent_ids_from_metadata,
)
from runtime.legacy_runtime_validation import legacy_wrds_validation_issue_codes
from runtime.legacy_value_investing_support import legacy_value_investing_capability_id
from runtime.llm import ModelConfig, ProviderWebSearchConfig
from runtime.ports import ChatModelClient
from runtime.skill_loader import Skill, SkillLoader
from runtime.state import AgentState
from runtime.tool_registry import ToolRegistry
from runtime.runtime_context import RuntimeContext, model_config_from_capabilities
from runtime.research_selection import (
    research_skill_selected,
    selected_skills_request_direct_wrds_data,
    selected_skills_request_investment_research,
    skill_name,
)
from runtime.swarm_pipeline import attach_swarm_execution_loop
from runtime.swarm.agent_decisions import legacy_committee_decision, runtime_agent_decision
from runtime.swarm.agent_outputs import legacy_committee_outputs, runtime_agent_outputs
from runtime.swarm.quorum import build_quorum_trace
from runtime.swarm.quorum_marshal import build_quorum_marshal_report, quorum_marshal_signals
from runtime.swarm.patroller_gate import (
    build_patroller_report,
    patroller_blocked,
    patroller_signals,
    render_patroller_defect_memo,
)
from runtime.swarm.capability_sandbox import (
    build_capability_sandbox_auditor_report,
    capability_sandbox_auditor_signals,
)
from runtime.swarm.evidence_graph import build_evidence_graph
from runtime.swarm.evidence_steward import build_evidence_steward_report, evidence_steward_signals
from runtime.swarm.governance_agents import build_governance_actor_trace
from runtime.swarm.enforcement_bus import apply_enforcement_bus
from runtime.swarm.governance_results import build_governance_results
from runtime.swarm.bottleneck_recruitment import build_bottleneck_report, bottleneck_signals
from runtime.swarm.encounter_rate import build_encounter_rate_report, encounter_rate_signals
from runtime.swarm.arousal import build_arousal_report, arousal_signals
from runtime.swarm.homeostasis import build_homeostasis_report, homeostasis_signals
from runtime.swarm.independent_scout import apply_independent_scout_adjustment, independent_scout_signals
from runtime.swarm.lane_scheduler import build_lane_assignment_report, lane_assignment_signals
from runtime.swarm.maturity import build_maturity_report, maturity_signals
from runtime.swarm.outcome_memory import build_outcome_memory_steward_report, outcome_memory_steward_signals
from runtime.swarm.controllers import (
    apply_controller_to_member_specs,
    build_swarm_controller_report,
    swarm_controller_signals,
)
from runtime.swarm.policing import build_policing_trace, policing_signals
from runtime.swarm.pheromone_store import append_swarm_trace
from runtime.swarm.response_threshold import (
    build_agent_allocation_trace,
    select_committee_members_by_threshold,
    update_agent_profiles_from_outputs,
)
from runtime.swarm.signal_extractor import (
    agent_emitted_signals_from_outputs,
    initial_signals_from_state,
    update_state_with_signals,
)
from runtime.swarm.signal_verifier import verify_agent_signal_proposals
from runtime.swarm.receiver_normalizer import build_receiver_normalizer_report, receiver_normalizer_signals
from runtime.swarm.social_immunity import build_social_immunity_report, sanitize_artifact_text, social_immunity_signals
from runtime.swarm.tool_health import build_tool_health_sentinel_report, tool_health_sentinel_signals
from runtime.swarm.action_policy import source_policy_blocked_tool_targets, source_policy_blocks_tool
from runtime.swarm.legacy_tool_policy import (
    legacy_source_policy_skill_block_reason,
    legacy_source_policy_tool_disabled_detail,
)
from runtime.swarm.tool_policy_resolver import (
    resolve_tool_policy,
    tool_policy_event_type,
    tool_policy_from_state,
)
from runtime.swarm.tool_plan_policy import (
    effective_source_mode_decision_for_orchestration,
    filter_plan_by_source_and_tool_policy,
    partition_skills_by_source_policy,
    web_tools_disabled_for_state,
)
from runtime.swarm.source_policy_modes import canonical_wrds_only_source_mode, source_mode_is_wrds_only
from runtime.swarm.resolution import apply_stop_signal_resolution
from runtime.swarm.stop_signal import report_publication_blocked, swarm_context_for_model, tool_blocked_by_signal
from runtime.swarm.trust_badge import build_trust_badges
from runtime.wrds_company_planner import (
    ensure_required_wrds_company_step,
    extract_company_query,
    known_research_company_markers,
    looks_like_ticker_or_company_name,
    normalize_wrds_company_tool_args as default_normalize_wrds_company_tool_args,
)
from runtime.web_research_planner import ensure_required_web_research_step
from runtime.workflows.routing import (
    active_node_order,
    workflow_descriptor_from_state,
    workflow_node_order_from_state,
    workflow_node_required,
    workflow_routing_summary,
)
from runtime.workflows.domain_execution import (
    apply_domain_workflow_execution_results,
    apply_domain_workflow_plan_async,
    apply_domain_workflow_plan_adapters,
    plan_adapter_handled_tool,
    workflow_with_manifest_defaults,
)
from runtime.workflows.legacy_dispatch import legacy_builtin_graph_mode
from runtime.workflows.orchestration_guidance import (
    build_orchestrator_system_prompt,
    orchestration_guidance_for_state,
)
from runtime.workflows.legacy_plan_defaults import legacy_deterministic_plan
from runtime.workflows.legacy_data_gate_routing import (
    legacy_data_gate_tool_names,
    legacy_graph_data_gate_required,
)
from runtime.workflows.legacy_wrds_routing import (
    legacy_direct_wrds_plan_step,
    legacy_direct_wrds_orchestration,
    legacy_wrds_financial_data_capability_id,
    legacy_should_bypass_graph_to_wrds,
    legacy_should_run_wrds_agent,
)
from runtime.workflows.legacy_orchestration_defaults import legacy_normalize_orchestration_defaults
from runtime.workflows.legacy_graph_routing import (
    legacy_infer_task_type,
    legacy_needs_domain_analysis,
    legacy_needs_quant_analysis,
    legacy_normalize_task_type,
)
from runtime.workflows.legacy_node_dispatch import legacy_research_node_fallback
from runtime.workflows.legacy_result_defaults import (
    legacy_memory_context_metadata_keys,
    legacy_runtime_preflight_blocked_summary,
    legacy_skipped_analysis_reason,
)
from runtime.workflows.wrds_payload_safety import (
    public_safe_execution_log,
    public_safe_wrds_result,
    summarize_wrds_result_for_model,
)
from runtime.tool_names import (
    APPROVED_SOURCE_FETCH_TOOL_NAME,
    PROVIDER_WEB_SEARCH_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
)
from runtime.workflows import source_tool_helpers
from runtime.workflows.source_tool_helpers import (
    FETCH_TOOL_NAMES,
    SEARCH_TOOL_NAMES,
    WRDS_COMPANY_TOOL_NAMES,
)
from tools.safe_tools import ToolResult
from tools.web_tools import build_search_queries, has_cjk

_CAPABILITY_NODE_CACHE: dict[tuple[str, str, str], Any] = {}


class AgentRuntime:
    def __init__(
        self,
        *,
        model_gateway: ChatModelClient | None = None,
        llm: ChatModelClient | None = None,
        skill_loader: SkillLoader,
        model_config: ModelConfig | None = None,
        tool_registry: ToolRegistry | None = None,
        runtime_context_factory: Any | None = None,
    ) -> None:
        selected_model_gateway = model_gateway or llm
        if selected_model_gateway is None:
            raise ValueError("model_gateway is required")
        self.model_gateway = selected_model_gateway
        self.llm = selected_model_gateway
        self.skill_loader = skill_loader
        self.model_config = model_config or ModelConfig.from_env()
        self.runtime_context_factory = runtime_context_factory
        self.provider_web_search_config = ProviderWebSearchConfig.from_env()
        self.tool_registry = tool_registry or ToolRegistry(
            workspace_root=Path.cwd(),
            provider_web_search=self._provider_web_search if self.provider_web_search_config.enabled else None,
            provider_web_search_enabled=self.provider_web_search_config.enabled,
        )
        self.graph = self._build_graph()

    async def run(
        self,
        *,
        task: str,
        skill_names: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not task.strip():
            raise ValueError("task must not be empty")

        metadata = metadata or {}
        existing_envelope = metadata.get("input_envelope") if isinstance(metadata.get("input_envelope"), dict) else {}
        existing_preflight = metadata.get("input_preflight") if isinstance(metadata.get("input_preflight"), dict) else {}
        if existing_envelope and existing_preflight:
            preflight_report = existing_preflight
            normalized_task = str(preflight_report.get("normalized_task") or task)
            metadata = {
                **metadata,
                "original_task_redacted": str(
                    metadata.get("original_task_redacted")
                    or existing_envelope.get("user_input")
                    or normalized_task
                ),
            }
        else:
            tenant_id_for_envelope = str(metadata.get("tenant_id") or "default")
            envelope = build_input_envelope(
                task=task,
                tenant_id=tenant_id_for_envelope,
                selected_agent_ids=selected_agent_ids_from_metadata(metadata),
                metadata=metadata,
            )
            preflight_report = preflight_input_envelope(envelope)
            normalized_task = str(preflight_report.get("normalized_task") or task)
            metadata = {
                **metadata,
                "input_envelope": envelope.to_public_dict(),
                "input_preflight": preflight_report,
                "original_task_redacted": envelope.user_input_redacted,
            }
        if self.runtime_context_factory is not None and not metadata.get("_runtime_materialized"):
            tenant_id = str(metadata.get("tenant_id") or "default")
            try:
                context: RuntimeContext = self.runtime_context_factory(
                    tenant_id=tenant_id,
                    task=normalized_task,
                    metadata=metadata,
                )
            except TypeError:
                context = self.runtime_context_factory(tenant_id=tenant_id)
            fatal_issues = fatal_runtime_validation_issues(context.validation_issues or [])
            if fatal_issues:
                return runtime_preflight_blocked_result(
                    task=task,
                    skill_names=skill_names,
                    metadata=metadata,
                    tenant_id=tenant_id,
                    context=context,
                    fatal_issues=fatal_issues,
                )
            delegate = AgentRuntime(
                model_gateway=context.model_gateway,
                skill_loader=self.skill_loader,
                model_config=model_config_from_capabilities(context.capability_index),
                tool_registry=context.tool_registry,
            )
            agent_catalog = (context.agent_registry or {}).get("agents", [])
            enriched_metadata = {
                **metadata,
                "_runtime_materialized": True,
                "tenant_id": tenant_id,
                "capability_index": context.capability_index,
                "model_routing_policy": context.model_routing_policy,
                "os_plan": context.os_plan,
                "enabled_capabilities": context.enabled_capabilities,
                "permission_grants": context.permission_grants,
                "data_source_registry": context.data_source_registry,
                "skill_registry": context.skill_registry,
                "agent_registry": context.agent_registry,
                "capability_runtime": context.capability_runtime,
                "agent_catalog": agent_catalog,
                **legacy_committee_agent_catalog_metadata(agent_catalog),
                "runtime_validation_issues": context.validation_issues or [],
            }
            return await delegate.run(task=normalized_task, skill_names=skill_names, metadata=enriched_metadata)

        run_id = uuid.uuid4().hex
        initial_state: AgentState = {
            "run_id": run_id,
            "task": normalized_task,
            "metadata": {
                **metadata,
                "requested_skill_names": skill_names or [],
            },
        }
        metrics_token = start_agent_metrics()
        try:
            direct_wrds_skills = self.skill_loader.match(normalized_task, explicit_names=skill_names)
            if should_bypass_graph_to_wrds(task=normalized_task, metadata=metadata or {}, skills=direct_wrds_skills):
                wrds_state: AgentState = {
                    **initial_state,
                    "route": "wrds",
                    "translated_task": normalized_task,
                    "search_query": "",
                    "english_search_query": "",
                    "orchestration": build_direct_wrds_orchestration(),
                    "selected_skills": [skill_to_dict(skill) for skill in direct_wrds_skills],
                    "plan": [legacy_direct_wrds_plan_step()],
                }
                result = normalize_run_result({**wrds_state, **(await self._wrds_agent(wrds_state))})
            else:
                result = normalize_run_result(await self.graph.ainvoke(initial_state))
            result = preserve_runtime_metadata(result, initial_state["metadata"])
            result["agent_metrics"] = current_agent_metrics()
            run_status, degraded_reasons = summarize_run_outcome(result)
            result["run_status"] = run_status
            result["degraded_reasons"] = degraded_reasons
            try:
                append_swarm_trace(result)
            except OSError:
                pass
            try:
                append_run_audit(result)
            except OSError:
                pass
            return result
        except Exception as exc:
            failed_run: dict[str, Any] = {
                **initial_state,
                "route": "failed",
                "selected_skills": [],
                "plan": [],
                "execution_log": [],
                "research_brief": {},
                "quant_analysis": {},
                "domain_analysis": {},
                "agent_outputs": {},
                "committee_outputs": {},
                "discussion_transcript": [],
                "agent_decision": {},
                "committee_decision": {},
                "pheromone_field_snapshot": {},
                "pheromone_trace": [],
                "stop_signals": [],
                "constraint_signals": [],
                "quorum_trace": {},
                "agent_allocation_trace": [],
                "patroller_report": {},
                "swarm_metrics": {},
                "review": {
                    "status": "error",
                    "issues": [str(exc)],
                    "summary": "Agent runtime failed before producing a final answer.",
                },
                "draft_final": "",
                "final": "",
                "agent_metrics": current_agent_metrics(),
                "run_status": "failed",
                "degraded_reasons": [str(exc)],
                "error": str(exc),
            }
            try:
                append_run_audit(failed_run)
            except OSError:
                pass
            raise
        finally:
            reset_agent_metrics(metrics_token)

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("orchestrator", self._orchestrator)
        graph.add_node("patroller_gate", self._patroller_gate)
        graph.add_node("memory_agent", self._memory_agent)
        graph.add_node("executor", self._executor)
        graph.add_node("workflow_host", self._workflow_host)
        graph.add_node("data_gate", self._data_gate)
        graph.add_node("wrds_agent", self._wrds_agent)
        graph.add_node("research_agent", self._research_agent)
        graph.add_node("quant_agent", self._quant_agent)
        graph.add_node("domain_expert", self._domain_expert)
        graph.add_node("committee_opening", self._committee_opening)
        graph.add_node("committee_discussion", self._committee_discussion)
        graph.add_node("investment_committee", self._investment_committee)
        graph.add_node("critic", self._critic)
        graph.add_node("writer", self._writer)
        graph.add_node("final_judge", self._final_judge)
        graph.set_entry_point("orchestrator")
        graph.add_conditional_edges("orchestrator", next_after_orchestrator)
        graph.add_conditional_edges("patroller_gate", next_after_patroller)
        graph.add_edge("wrds_agent", END)
        graph.add_conditional_edges("memory_agent", next_after_memory)
        graph.add_conditional_edges("executor", next_after_executor)
        graph.add_conditional_edges("workflow_host", next_after_workflow_host)
        graph.add_conditional_edges("data_gate", next_after_data_gate)
        graph.add_conditional_edges("research_agent", next_after_research)
        graph.add_conditional_edges("quant_agent", next_after_quant)
        graph.add_conditional_edges("domain_expert", next_after_domain)
        graph.add_edge("committee_opening", "committee_discussion")
        graph.add_edge("committee_discussion", "investment_committee")
        graph.add_edge("investment_committee", "critic")
        graph.add_conditional_edges("critic", next_after_critic)
        graph.add_conditional_edges("writer", next_after_writer)
        graph.add_edge("final_judge", END)
        return graph.compile()

    async def _orchestrator(self, state: AgentState) -> AgentState:
        started_at = metric_started_at()
        requested = state.get("metadata", {}).get("requested_skill_names") or None
        skills = self.skill_loader.match(state["task"], explicit_names=requested)
        selected_skill_dicts = [skill_to_dict(skill) for skill in skills]
        orchestration_guidance = orchestration_guidance_for_state(state, selected_skills=selected_skill_dicts)
        fallback_query = build_search_queries(state["task"], english_only=False)[0]
        orchestration_fallback_reason: Exception | None = None
        orchestration_model_used = self.model_config.orchestrator
        try:
            content, orchestration_model_used, orchestration_fallback_reason = await self._chat_with_fallback(
                primary_model=self.model_config.orchestrator,
                fallback_model=None,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": build_orchestrator_system_prompt(orchestration_guidance["instructions"]),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "task": state["task"],
                                "source_mode": state.get("metadata", {}).get("source_mode") or "DEFAULT",
                                "suggested_search_query": fallback_query,
                                "selected_skills": selected_skill_dicts,
                                "skill_context": render_skill_context(skills),
                                "available_tools": tool_manifest_for_state(self.tool_registry.manifest(), state),
                                "orchestration_guidance": orchestration_guidance["instructions"],
                                "orchestration_guidance_trace": orchestration_guidance["trace"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            )
            payload = parse_json_object(content)
            translated_task = state["task"]
            english_search_query = normalize_search_query(
                str(payload.get("english_search_query") or payload.get("search_query") or fallback_query)
            )
            orchestration = normalize_orchestration(
                payload,
                task=state["task"],
                selected_skills=skills,
                os_plan=os_plan_from_state(state),
            )
            plan = parse_plan(json.dumps({"steps": payload.get("steps") or []}, ensure_ascii=False))
        except Exception as exc:
            orchestration_fallback_reason = exc
            payload = {}
            translated_task = state["task"]
            english_search_query = normalize_search_query(fallback_query)
            orchestration = normalize_orchestration(
                payload,
                task=state["task"],
                selected_skills=skills,
                os_plan=os_plan_from_state(state),
            )
            plan = []

        source_mode_decision = effective_source_mode_decision_for_orchestration(
            state,
            orchestration=orchestration,
        )
        effective_source_mode = source_mode_decision.get("source_mode")

        active_skills, blocked_skills = apply_source_mode_to_skills(
            skills,
            source_mode=effective_source_mode,
        )
        active_skill_dicts = [skill_to_dict(skill) for skill in active_skills]
        blocked_skill_dicts = [
            {**skill_to_dict(skill), "blocked_reason": legacy_source_policy_skill_block_reason()}
            for skill in blocked_skills
        ]

        metadata_update = dict(state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {})
        if source_mode_is_wrds_only(effective_source_mode):
            metadata_update["source_mode"] = canonical_wrds_only_source_mode()
        metadata_update["source_mode_source"] = source_mode_decision.get("source")
        metadata_update["source_mode_decision"] = source_mode_decision
        adapter_input = {
            "task": state["task"],
            "translated_task": translated_task,
            "search_query": english_search_query,
            "english_search_query": english_search_query,
            "route": orchestration.get("task_type") or ("planned" if skills else "general"),
            "metadata": metadata_update,
            "orchestration": orchestration,
            "selected_skills": active_skill_dicts,
            "blocked_skills": blocked_skill_dicts,
            "skill_context": render_skill_context(active_skills),
            "tool_manifest": tool_manifest_for_state(self.tool_registry.manifest(), {**state, "metadata": metadata_update}),
            "preferred_web_search_tool": self.preferred_web_search_tool(),
            "plan": plan,
        }
        adapter_result = apply_domain_workflow_plan_adapters({**state, "metadata": metadata_update}, adapter_input)
        plan = adapter_result.get("plan", plan)
        plan_adapter_trace = adapter_result.get("plan_adapter_trace", [])
        plan_fallback_trace: list[dict[str, Any]] = []
        if not plan:
            plan = deterministic_plan(
                task=state["task"],
                english_search_query=english_search_query,
                selected_skills=active_skill_dicts,
                preferred_web_search_tool=self.preferred_web_search_tool(),
                source_mode=effective_source_mode,
            )
            plan_fallback_trace.append(
                {
                    "source": "legacy_deterministic_plan_fallback",
                    "reason": "orchestrator and capability plan adapters produced no usable plan",
                    "step_count": len(plan),
                }
            )
        if not (
            plan_adapter_handled_tool(adapter_result, WEB_SEARCH_TOOL_NAME)
            or plan_adapter_handled_tool(adapter_result, PROVIDER_WEB_SEARCH_TOOL_NAME)
        ):
            plan = ensure_required_web_research_step(
                plan,
                task=state["task"],
                english_search_query=english_search_query,
                selected_skills=active_skill_dicts,
                preferred_web_search_tool=self.preferred_web_search_tool(),
                source_mode=effective_source_mode,
            )
        if not plan_adapter_handled_tool(adapter_result, "wrds_company_financials"):
            plan = ensure_required_wrds_company_step(
                plan,
                task=state["task"],
                orchestration=orchestration,
                selected_skills=active_skill_dicts,
                available_tools=tool_manifest_for_state(self.tool_registry.manifest(), {**state, "metadata": metadata_update}),
            )
        plan = enforce_source_mode_on_plan(
            plan,
            source_mode=effective_source_mode,
            tool_policy=tool_policy_from_state(state),
        )

        record_agent_metric(
            agent="orchestrator",
            model=orchestration_model_used,
            started_at=started_at,
            status="completed_with_fallback" if orchestration_fallback_reason else "completed",
            failure_reason=orchestration_fallback_reason,
        )
        result = {
            "translated_task": translated_task,
            "search_query": english_search_query,
            "english_search_query": english_search_query,
            "route": orchestration.get("task_type") or ("planned" if skills else "general"),
            "orchestration": orchestration,
            "metadata": metadata_update,
            "source_mode_decision": source_mode_decision,
            "selected_skills": active_skill_dicts,
            "blocked_skills": blocked_skill_dicts,
            "skill_context": render_skill_context(active_skills),
            "tool_manifest": tool_manifest_for_state(self.tool_registry.manifest(), {**state, "metadata": metadata_update}),
            "workflow_routing": workflow_routing_summary({**state, "metadata": metadata_update}),
            "orchestration_guidance_trace": orchestration_guidance["trace"],
            "plan": plan,
            "plan_adapter_trace": plan_adapter_trace,
            "plan_fallback_trace": plan_fallback_trace,
            "defer_generic_workflow_host": True,
        }
        if isinstance(adapter_result.get("plan_adapter_outputs"), dict):
            result["plan_adapter_outputs"] = adapter_result["plan_adapter_outputs"]
        result = await apply_domain_workflow_plan_async(
            {**state, "metadata": metadata_update},
            result,
            tool_registry=self.tool_registry,
        )
        result.update(update_state_with_signals({**state, **result}, initial_signals_from_state({**state, **result})))
        result = attach_swarm_execution_loop({**state, "metadata": metadata_update}, result)
        return result

    async def _patroller_gate(self, state: AgentState) -> AgentState:
        from runtime.nodes.preflight import patroller_gate_node

        return await patroller_gate_node(self, state)

    async def _memory_agent(self, state: AgentState) -> AgentState:
        from runtime.nodes.memory import memory_agent_node

        return await memory_agent_node(self, state)

    async def _wrds_agent(self, state: AgentState) -> AgentState:
        wrds_agent_node = load_capability_runtime_node(legacy_wrds_financial_data_capability_id(), "wrds_agent_node")
        return await wrds_agent_node(self, state)

    async def _executor(self, state: AgentState) -> AgentState:
        started_at = metric_started_at()
        model_used = False
        try:
            execution_log = []
            for step in state.get("plan") or []:
                tool_calls = step.get("tool_calls")
                if tool_calls is None:
                    if web_tools_disabled_for_state(state):
                        tool_calls = []
                    else:
                        model_used = True
                        tool_calls = await self._propose_tool_calls({**state, "execution_log": execution_log}, step)
                results = await self._execute_tool_calls(tool_calls, state=state, step=step)
                ok = step_tool_results_succeeded(results)
                execution_log.append(
                    {
                        "step_id": step.get("id"),
                        "title": step.get("title"),
                        "status": "completed" if ok else "failed",
                        "tool_calls": results,
                        "result": summarize_tool_results(step, results),
                    }
                )
            status, failure_reason = summarize_execution_metric_status(execution_log)
            record_agent_metric(
                agent="executor",
                model=self.model_config.executor,
                model_used=model_used,
                started_at=started_at,
                status=status,
                failure_reason=failure_reason,
            )
            wrds_result = collect_wrds_results(execution_log, state=state)
            result = {
                "execution_log": execution_log,
                "wrds_result": wrds_result,
                "data_source_results": wrds_result.get("data_source_results", []),
                "provider_results": wrds_result.get("provider_results", []),
            }
            return apply_domain_workflow_execution_results(state, result, tool_registry=self.tool_registry)
        except Exception as exc:
            record_agent_metric(
                agent="executor",
                model=self.model_config.executor,
                model_used=model_used,
                started_at=started_at,
                status="failed",
                failure_reason=exc,
            )
            raise

    async def _workflow_host(self, state: AgentState) -> AgentState:
        workflow = workflow_descriptor_from_state(state)
        from runtime.workflows.generic_swarm_workflow import execute_graph_workflow_host

        return await execute_graph_workflow_host(state, workflow=workflow, tool_registry=self.tool_registry)

    async def _data_gate(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "data_gate")
        if descriptor_result is not None:
            return descriptor_result
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        require_protocol_workflow_node_entrypoint(state, workflow, "data_gate")
        data_gate_node = load_value_investing_runtime_node("data_gate_node")
        return await data_gate_node(self, state)

    async def _propose_tool_calls(self, state: AgentState, step: dict[str, Any]) -> list[dict[str, Any]]:
        content, _model_used, _fallback_reason = await self._chat_with_fallback(
            primary_model=self.model_config.executor,
            fallback_model=None,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Executor / Tool Agent. Return strict JSON only with a top-level "
                        '"tool_calls" array. Use only available tools. Do not make analytical judgments.'
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": state["task"],
                            "step": step,
                            "available_tools": state.get("tool_manifest", []),
                            "selected_skills": state.get("selected_skills", []),
                            "previous_execution_log": model_safe_execution_log(state.get("execution_log", [])),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        try:
            payload = parse_json_object(content)
        except RuntimeError:
            repaired = extract_tool_calls_from_text(content)
            if repaired:
                return repaired
            raise
        return normalize_tool_calls(payload.get("tool_calls", []))

    async def _chat_with_fallback(
        self,
        *,
        primary_model: str,
        fallback_model: str | None,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> tuple[str, str, Exception | None]:
        model_chain = model_fallback_chain(
            primary_model=primary_model,
            explicit_fallback=fallback_model,
            model_config=self.model_config,
        )
        first_exc: Exception | None = None
        failures: list[tuple[str, Exception]] = []
        for index, candidate in enumerate(model_chain):
            try:
                content = await self.model_gateway.chat(model=candidate, messages=messages, temperature=temperature)
                if index == 0:
                    return content, candidate, None
                return content, fallback_model_label(candidate, primary_model=primary_model, failed_models=[model for model, _ in failures]), first_exc
            except Exception as exc:
                first_exc = first_exc or exc
                failures.append((candidate, exc))
                next_model = model_chain[index + 1] if index + 1 < len(model_chain) else None
                if not should_try_model_fallback(exc, primary_model=primary_model, fallback_model=next_model):
                    if index == 0:
                        raise
                    raise RuntimeError(format_model_chain_failure(failures)) from exc
        raise RuntimeError(format_model_chain_failure(failures))

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        state: AgentState,
        step: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results = []
        for call in tool_calls:
            name = str(call.get("name") or "")
            args = call.get("args") or {}
            if name in WRDS_COMPANY_TOOL_NAMES:
                args = normalize_wrds_company_tool_args(args, state=state, step=step, tool_name=name)
            policy_decision = resolve_tool_policy(
                tool_name=name,
                state=state,
                tool_manifest=tool_registry_manifest(self.tool_registry),
            )
            blocked_signal = tool_blocked_by_signal(state, name)
            if blocked_signal:
                result = ToolResult(
                    False,
                    {
                        "name": name,
                        "blocked_by_signal": blocked_signal.get("id"),
                        "target": blocked_signal.get("target"),
                        "tool_policy_decision": policy_decision,
                    },
                    str(blocked_signal.get("content") or f"{name} blocked by swarm stop-signal"),
                )
                results.append(
                    {
                        "index": len(results),
                        "event_type": tool_policy_event_type(policy_decision),
                        "name": name,
                        "args": args,
                        "result": result.to_dict(),
                    }
                )
                continue
            if source_policy_blocks_tool(state, f"tool:{name}"):
                wrds_only_source_mode = canonical_wrds_only_source_mode()
                result = ToolResult(
                    False,
                    {
                        "name": name,
                        "source_mode": wrds_only_source_mode,
                        "tool_policy_decision": policy_decision,
                    },
                    legacy_source_policy_tool_disabled_detail(action=name, source_mode=wrds_only_source_mode),
                )
                results.append(
                    {
                        "index": len(results),
                        "event_type": tool_policy_event_type(policy_decision),
                        "name": name,
                        "args": args,
                        "result": result.to_dict(),
                    }
                )
                continue
            if tool_policy_blocks_execution(policy_decision):
                results.append(blocked_tool_policy_result(name=name, args=args, decision=policy_decision, index=len(results)))
                continue
            if name in SEARCH_TOOL_NAMES:
                args = normalize_web_search_args(args, state=state)
                name, result = await self._run_resilient_search(name, args, state=state, results=results)
            else:
                result = await self.tool_registry.arun(name, args)
                result_payload = result.to_dict()
                result_payload["tool_policy_decision"] = policy_decision
                results.append(
                    {
                        "index": len(results),
                        "event_type": tool_policy_event_type(policy_decision),
                        "name": name,
                        "args": args,
                        "result": result_payload,
                    }
                )
            if (
                name in SEARCH_TOOL_NAMES
                and result.ok
                and should_auto_fetch_search_results(
                    state["task"],
                    args,
                    selected_skills=state.get("selected_skills", []),
                    english_search_query=state.get("english_search_query"),
                )
            ):
                approved_urls = select_search_result_urls(result.data)
                fetch_tool_name = preferred_source_fetch_tool(self.tool_registry.names())
                for url in approved_urls:
                    fetch_args = {"url": url, "max_bytes": 512_000, "extract_text": True}
                    if fetch_tool_name == APPROVED_SOURCE_FETCH_TOOL_NAME:
                        fetch_args["approved_urls"] = approved_urls
                    fetch_policy = resolve_tool_policy(
                        tool_name=fetch_tool_name,
                        state=state,
                        tool_manifest=tool_registry_manifest(self.tool_registry),
                    )
                    if tool_policy_blocks_execution(fetch_policy):
                        results.append(blocked_tool_policy_result(name=fetch_tool_name, args=fetch_args, decision=fetch_policy, index=len(results)))
                    else:
                        fetch_result = self.tool_registry.run(fetch_tool_name, fetch_args)
                        result_payload = fetch_result.to_dict()
                        result_payload["tool_policy_decision"] = fetch_policy
                        results.append(
                            {
                                "index": len(results),
                                "event_type": tool_policy_event_type(fetch_policy),
                                "name": fetch_tool_name,
                                "args": fetch_args,
                                "result": result_payload,
                            }
                        )
        return results

    async def _run_resilient_search(
        self,
        name: str,
        args: dict[str, Any],
        *,
        state: AgentState,
        results: list[dict[str, Any]],
    ) -> tuple[str, ToolResult]:
        if name == WEB_SEARCH_TOOL_NAME and should_upgrade_search_to_provider(state, self.tool_registry.names()):
            provider_policy = resolve_tool_policy(
                tool_name=PROVIDER_WEB_SEARCH_TOOL_NAME,
                state=state,
                tool_manifest=tool_registry_manifest(self.tool_registry),
            )
            if tool_policy_blocks_execution(provider_policy):
                results.append(
                    blocked_tool_policy_result(
                        name=PROVIDER_WEB_SEARCH_TOOL_NAME,
                        args=args,
                        decision=provider_policy,
                        index=len(results),
                    )
                )
                fallback_policy = resolve_tool_policy(
                    tool_name=WEB_SEARCH_TOOL_NAME,
                    state=state,
                    tool_manifest=tool_registry_manifest(self.tool_registry),
                )
                if tool_policy_blocks_execution(fallback_policy):
                    results.append(
                        blocked_tool_policy_result(
                            name=WEB_SEARCH_TOOL_NAME,
                            args={**args, "fallback_from": f"{PROVIDER_WEB_SEARCH_TOOL_NAME}_policy_block"},
                            decision=fallback_policy,
                            index=len(results),
                        )
                    )
                    return WEB_SEARCH_TOOL_NAME, ToolResult(
                        False,
                        {"tool_policy_decision": fallback_policy},
                        f"{WEB_SEARCH_TOOL_NAME} blocked by tool policy: {fallback_policy.get('reason')}",
                    )
                fallback_result = self.tool_registry.run(WEB_SEARCH_TOOL_NAME, args)
                results.append(
                    {
                        "index": len(results),
                        "event_type": tool_policy_event_type(fallback_policy),
                        "name": WEB_SEARCH_TOOL_NAME,
                        "args": {**args, "fallback_from": f"{PROVIDER_WEB_SEARCH_TOOL_NAME}_policy_block"},
                        "result": {**fallback_result.to_dict(), "tool_policy_decision": fallback_policy},
                    }
                )
                return WEB_SEARCH_TOOL_NAME, fallback_result
            provider_result = await self.tool_registry.arun(PROVIDER_WEB_SEARCH_TOOL_NAME, args)
            results.append(
                {
                    "index": len(results),
                    "event_type": tool_policy_event_type(provider_policy),
                    "name": PROVIDER_WEB_SEARCH_TOOL_NAME,
                    "args": {**args, "upgraded_from": WEB_SEARCH_TOOL_NAME},
                    "result": {**provider_result.to_dict(), "tool_policy_decision": provider_policy},
                }
            )
            if provider_result.ok:
                return PROVIDER_WEB_SEARCH_TOOL_NAME, provider_result
            fallback_policy = resolve_tool_policy(
                tool_name=WEB_SEARCH_TOOL_NAME,
                state=state,
                tool_manifest=tool_registry_manifest(self.tool_registry),
            )
            if tool_policy_blocks_execution(fallback_policy):
                results.append(
                    blocked_tool_policy_result(
                        name=WEB_SEARCH_TOOL_NAME,
                        args={**args, "fallback_from": PROVIDER_WEB_SEARCH_TOOL_NAME},
                        decision=fallback_policy,
                        index=len(results),
                    )
                )
                return WEB_SEARCH_TOOL_NAME, ToolResult(
                    False,
                    {"tool_policy_decision": fallback_policy},
                    f"{WEB_SEARCH_TOOL_NAME} blocked by tool policy: {fallback_policy.get('reason')}",
                )
            fallback_result = self.tool_registry.run(WEB_SEARCH_TOOL_NAME, args)
            results.append(
                {
                    "index": len(results),
                    "event_type": tool_policy_event_type(fallback_policy),
                    "name": WEB_SEARCH_TOOL_NAME,
                    "args": {**args, "fallback_from": PROVIDER_WEB_SEARCH_TOOL_NAME},
                    "result": {**fallback_result.to_dict(), "tool_policy_decision": fallback_policy},
                }
            )
            return WEB_SEARCH_TOOL_NAME, fallback_result

        policy_decision = resolve_tool_policy(
            tool_name=name,
            state=state,
            tool_manifest=tool_registry_manifest(self.tool_registry),
        )
        if tool_policy_blocks_execution(policy_decision):
            results.append(blocked_tool_policy_result(name=name, args=args, decision=policy_decision, index=len(results)))
            return name, ToolResult(False, {"tool_policy_decision": policy_decision}, f"{name} blocked by tool policy: {policy_decision.get('reason')}")
        result = await self.tool_registry.arun(name, args)
        results.append(
            {
                "index": len(results),
                "event_type": tool_policy_event_type(policy_decision),
                "name": name,
                "args": args,
                "result": {**result.to_dict(), "tool_policy_decision": policy_decision},
            }
        )
        if name == PROVIDER_WEB_SEARCH_TOOL_NAME and not result.ok:
            fallback_policy = resolve_tool_policy(
                tool_name=WEB_SEARCH_TOOL_NAME,
                state=state,
                tool_manifest=tool_registry_manifest(self.tool_registry),
            )
            if tool_policy_blocks_execution(fallback_policy):
                results.append(
                    blocked_tool_policy_result(
                        name=WEB_SEARCH_TOOL_NAME,
                        args={**args, "fallback_from": PROVIDER_WEB_SEARCH_TOOL_NAME},
                        decision=fallback_policy,
                        index=len(results),
                    )
                )
                return WEB_SEARCH_TOOL_NAME, ToolResult(
                    False,
                    {"tool_policy_decision": fallback_policy},
                    f"{WEB_SEARCH_TOOL_NAME} blocked by tool policy: {fallback_policy.get('reason')}",
                )
            fallback_result = self.tool_registry.run(WEB_SEARCH_TOOL_NAME, args)
            results.append(
                {
                    "index": len(results),
                    "event_type": tool_policy_event_type(fallback_policy),
                    "name": WEB_SEARCH_TOOL_NAME,
                    "args": {**args, "fallback_from": PROVIDER_WEB_SEARCH_TOOL_NAME},
                    "result": {**fallback_result.to_dict(), "tool_policy_decision": fallback_policy},
                }
            )
            return WEB_SEARCH_TOOL_NAME, fallback_result
        return name, result

    async def _provider_web_search(self, *, query: str, max_results: int = 5) -> dict[str, Any]:
        provider_search = getattr(self.model_gateway, PROVIDER_WEB_SEARCH_TOOL_NAME, None)
        if provider_search is None:
            raise RuntimeError("configured LLM client does not support provider-native web search")
        return await provider_search(query=query, max_results=max_results, model=self.provider_web_search_config.model)

    def preferred_web_search_tool(self) -> str:
        return (
            PROVIDER_WEB_SEARCH_TOOL_NAME
            if PROVIDER_WEB_SEARCH_TOOL_NAME in self.tool_registry.names()
            else WEB_SEARCH_TOOL_NAME
        )

    async def _research_agent(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "research_agent")
        if descriptor_result is not None:
            return descriptor_result
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        graph_mode = str(workflow.get("graph_mode") or "")
        require_protocol_workflow_node_entrypoint(state, workflow, "research_agent", fallback_id=graph_mode)
        legacy_result = await legacy_research_node_fallback(self, state, graph_mode=graph_mode)
        if legacy_result is not None:
            return legacy_result
        research_agent_node = load_value_investing_runtime_node("research_agent_node")
        return await research_agent_node(self, state)

    async def _quant_agent(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "quant_agent")
        if descriptor_result is not None:
            return descriptor_result
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        require_protocol_workflow_node_entrypoint(state, workflow, "quant_agent")
        quant_agent_node = load_value_investing_runtime_node("quant_agent_node")
        return await quant_agent_node(self, state)

    async def _domain_expert(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "domain_expert")
        if descriptor_result is not None:
            return descriptor_result
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        require_protocol_workflow_node_entrypoint(state, workflow, "domain_expert")
        started_at = metric_started_at()
        try:
            content, model_used, fallback_reason = await self._chat_with_fallback(
                primary_model=self.model_config.domain_expert,
                fallback_model=None,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Domain Expert Agent. Apply the relevant domain framework "
                            "(value investing, academic writing, coding/API architecture, or business strategy). "
                            "Use Research and Quant outputs as inputs; do not add new facts. Return strict JSON "
                            "with keys: status, domain, judgment, framework_points, risks, missing_evidence, confidence."
                        ),
                    },
                    {"role": "user", "content": domain_context(state)},
                ],
            )
            result = {"domain_analysis": parse_domain_analysis(content)}
            record_agent_metric(
                agent="domain_expert",
                model=model_used,
                started_at=started_at,
                status="completed_with_fallback" if fallback_reason else "completed",
                failure_reason=fallback_reason,
            )
            return result
        except Exception as exc:
            record_agent_metric(
                agent="domain_expert",
                model=self.model_config.domain_expert,
                started_at=started_at,
                status="failed",
                failure_reason=exc,
            )
            raise

    async def _committee_opening(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "committee_opening")
        if descriptor_result is not None:
            return descriptor_result
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        require_protocol_workflow_node_entrypoint(state, workflow, "committee_opening")
        committee_opening_node = load_value_investing_runtime_node("committee_opening_node")
        return await committee_opening_node(self, state)

    async def _committee_discussion(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "committee_discussion")
        if descriptor_result is not None:
            return descriptor_result
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        require_protocol_workflow_node_entrypoint(state, workflow, "committee_discussion")
        committee_discussion_node = load_value_investing_runtime_node("committee_discussion_node")
        return await committee_discussion_node(self, state)

    async def _investment_committee(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "investment_committee")
        if descriptor_result is not None:
            return descriptor_result
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        require_protocol_workflow_node_entrypoint(state, workflow, "investment_committee")
        investment_committee_node = load_value_investing_runtime_node("investment_committee_node")
        return await investment_committee_node(self, state)

    async def _critic(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "critic")
        if descriptor_result is not None:
            return descriptor_result
        from runtime.nodes.output_chain import critic_node

        return await critic_node(self, state)

    async def _writer(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "writer")
        if descriptor_result is not None:
            return descriptor_result
        from runtime.nodes.output_chain import writer_node

        return await writer_node(self, state)

    async def _final_judge(self, state: AgentState) -> AgentState:
        descriptor_result = await self._workflow_node_entrypoint(state, "final_judge")
        if descriptor_result is not None:
            return descriptor_result
        from runtime.nodes.output_chain import final_judge_node

        return await final_judge_node(self, state)

    async def _workflow_node_entrypoint(self, state: AgentState, node: str) -> AgentState | None:
        workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
        entrypoints = workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {}
        entrypoint = str(entrypoints.get(node) or "").strip()
        if not entrypoint:
            return None
        manifest = CapabilityRegistry().get(workflow_capability_id(workflow))
        if manifest is None:
            raise CapabilityEntrypointError(f"{node} workflow entrypoint has no capability manifest")
        if ":" not in entrypoint:
            raise CapabilityEntrypointError(f"{manifest.id}.{node} must use path.py:function syntax")
        path_text, function_name = entrypoint.split(":", 1)
        module_path = safe_entrypoint_path(manifest, path_text)
        function = load_function(module_path, function_name)
        values = {"runtime": self, "state": state, "workflow": workflow, "node": node, "result": {}}
        output = function(**accepted_node_kwargs(function, values))
        if inspect.isawaitable(output):
            output = await output
        if not isinstance(output, dict):
            raise CapabilityEntrypointError(f"{manifest.id}.{node} returned {type(output).__name__}, expected dict")
        return output


def tool_policy_blocks_execution(decision: dict[str, Any]) -> bool:
    return str(decision.get("status") or "") in {"blocked", "denied"}


def tool_registry_manifest(registry: Any) -> list[dict[str, Any]]:
    manifest = getattr(registry, "manifest", None)
    if not callable(manifest):
        return []
    value = manifest()
    return value if isinstance(value, list) else []


def blocked_tool_policy_result(*, name: str, args: dict[str, Any], decision: dict[str, Any], index: int) -> dict[str, Any]:
    result = ToolResult(
        False,
        {
            "name": name,
            "tool_policy_decision": decision,
            "canonical_tool": decision.get("canonical_tool"),
        },
        f"{name} blocked by tool policy: {decision.get('reason')}",
    )
    return {
        "index": index,
        "event_type": tool_policy_event_type(decision),
        "name": name,
        "args": args,
        "result": result.to_dict(),
    }


def normalize_wrds_action(plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return load_capability_runtime_node(legacy_wrds_financial_data_capability_id(), "normalize_wrds_action")(plan)


def render_wrds_final(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    result: dict[str, Any],
    plan: dict[str, Any],
) -> str:
    return load_capability_runtime_node(legacy_wrds_financial_data_capability_id(), "render_wrds_final")(
        tool_name=tool_name,
        tool_args=tool_args,
        result=result,
        plan=plan,
    )


def load_value_investing_runtime_node(function_name: str) -> Any:
    return load_capability_runtime_node(legacy_value_investing_capability_id(), function_name)


def protocol_workflow_requires_node_entrypoint(state: AgentState, workflow: dict[str, Any], node: str) -> bool:
    if not explicit_protocol_backed_workflow(state, workflow):
        return False
    entrypoints = workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {}
    if str(entrypoints.get(node) or "").strip():
        return False
    declared_nodes = workflow_declared_nodes(workflow)
    if node in declared_nodes:
        return True
    policy = workflow.get("node_policy") if isinstance(workflow.get("node_policy"), dict) else {}
    node_policy = policy.get(node) if isinstance(policy.get(node), dict) else {}
    return bool(node_policy) and node_policy.get("required") is not False


def require_protocol_workflow_node_entrypoint(
    state: AgentState,
    workflow: dict[str, Any],
    node: str,
    *,
    fallback_id: str = "",
) -> None:
    if not protocol_workflow_requires_node_entrypoint(state, workflow, node):
        return
    capability_id = workflow_capability_id(workflow) or fallback_id or "protocol_workflow"
    raise CapabilityEntrypointError(f"{capability_id}.{node} requires a declared node_entrypoints entry")


def explicit_protocol_backed_workflow(state: AgentState, workflow: dict[str, Any]) -> bool:
    os_plan = os_plan_from_state(state)
    if not protocol_backed_os_plan(os_plan):
        return False
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    protocols = swarm_plan.get("capability_protocols") if isinstance(swarm_plan.get("capability_protocols"), list) else []
    capability_id = workflow_capability_id(workflow) or str(os_plan.get("selected_capability_id") or "").strip()
    if not protocols:
        return True
    matching = [
        item
        for item in protocols
        if isinstance(item, dict)
        and (not capability_id or str(item.get("capability_id") or "").strip() == capability_id)
    ]
    if not matching and capability_id:
        return False
    candidates = matching or [item for item in protocols if isinstance(item, dict)]
    return any(not bool(item.get("generated_legacy_protocol")) for item in candidates)


def workflow_declared_nodes(workflow: dict[str, Any]) -> set[str]:
    nodes: set[str] = set()
    for key in ("graph_nodes", "ordered_nodes"):
        value = workflow.get(key)
        if isinstance(value, list):
            nodes.update(str(item).strip() for item in value if str(item).strip())
    return nodes


def load_value_investing_support_function(function_name: str) -> Any:
    return load_capability_runtime_node(
        legacy_value_investing_capability_id(),
        function_name,
        module_name="support.py",
    )


def load_capability_runtime_node(
    capability_id: str,
    function_name: str,
    *,
    module_name: str = "runtime_nodes.py",
) -> Any:
    cache_key = (capability_id, module_name, function_name)
    if cache_key in _CAPABILITY_NODE_CACHE:
        return _CAPABILITY_NODE_CACHE[cache_key]
    from runtime.capability_runtime import load_function

    module_path = Path(__file__).resolve().parent.parent / "capabilities" / capability_id / module_name
    function = load_function(module_path, function_name)
    _CAPABILITY_NODE_CACHE[cache_key] = function
    return function


def workflow_capability_id(workflow: dict[str, Any]) -> str:
    for key in ("capability_id", "capability"):
        value = str(workflow.get(key) or "").strip()
        if value:
            return value
    workflow_id = str(workflow.get("id") or workflow.get("workflow_id") or "").strip()
    if CapabilityRegistry().get(workflow_id) is not None:
        return workflow_id
    if "." in workflow_id:
        candidate = workflow_id.split(".", 1)[0]
        if CapabilityRegistry().get(candidate) is not None:
            return candidate
    return ""


def accepted_node_kwargs(function: Any, values: dict[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(function)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return values
    return {key: value for key, value in values.items() if key in signature.parameters}


def redact_wrds_args(args: dict[str, Any]) -> dict[str, Any]:
    return load_capability_runtime_node(legacy_wrds_financial_data_capability_id(), "redact_wrds_args")(args)


def normalize_wrds_company_tool_args(
    args: dict[str, Any],
    *,
    state: dict[str, Any],
    step: dict[str, Any] | None = None,
    tool_name: str,
) -> dict[str, Any]:
    try:
        normalizer = wrds_argument_normalizer_from_state(state, tool_name) or load_capability_runtime_node(
            legacy_wrds_financial_data_capability_id(),
            "normalize_wrds_company_tool_args",
        )
        return normalizer(
            **accepted_node_kwargs(
                normalizer,
                {
                    "args": args,
                    "state": state,
                    "step": step,
                    "tool_name": tool_name,
                },
            )
        )
    except CapabilityEntrypointError:
        return default_normalize_wrds_company_tool_args(args, state=state, step=step, tool_name=tool_name)


def wrds_argument_normalizer_from_state(state: dict[str, Any] | None, tool_name: str) -> Any | None:
    if not isinstance(state, dict):
        return None
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    runtime = metadata.get("capability_runtime") if isinstance(metadata.get("capability_runtime"), dict) else {}
    capabilities = runtime.get("capabilities") if isinstance(runtime.get("capabilities"), dict) else {}
    capability_id = legacy_wrds_financial_data_capability_id()
    descriptor = capabilities.get(capability_id) if isinstance(capabilities.get(capability_id), dict) else {}
    entrypoints = descriptor.get("entrypoints") if isinstance(descriptor.get("entrypoints"), dict) else {}
    runtime_nodes = entrypoints.get("runtime_nodes") if isinstance(entrypoints.get("runtime_nodes"), dict) else {}
    normalizers = runtime_nodes.get("argument_normalizers") if isinstance(runtime_nodes.get("argument_normalizers"), dict) else {}
    entrypoint = str(normalizers.get(tool_name) or "").strip()
    if not entrypoint or ":" not in entrypoint:
        return None
    manifest = CapabilityRegistry().get(capability_id)
    if manifest is None:
        return None
    try:
        path_text, function_name = entrypoint.split(":", 1)
        module_path = safe_entrypoint_path(manifest, path_text)
        return load_function(module_path, function_name)
    except CapabilityEntrypointError:
        return None


def skill_to_dict(skill: Skill) -> dict[str, str]:
    return {
        "name": skill.name,
        "description": skill.description,
        "path": str(skill.path),
    }


def protocol_signals_to_trace(signals: list[Any]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for signal in signals:
        if hasattr(signal, "to_dict"):
            payload = signal.to_dict()
        elif isinstance(signal, dict):
            payload = signal
        else:
            continue
        trace.append(
            {
                "type": payload.get("type"),
                "target": payload.get("target"),
                "source_module": payload.get("source_module"),
                "verification_state": payload.get("verification_state"),
                "strength": payload.get("strength"),
                "content": payload.get("content"),
            }
        )
    return trace


def render_skill_context(skills: list[Skill]) -> str:
    if not skills:
        return ""
    return "\n\n".join(skill.content for skill in skills)


def normalize_run_result(result: dict[str, Any]) -> dict[str, Any]:
    evidence_graph = result.get("evidence_graph")
    if not isinstance(evidence_graph, dict):
        evidence_graph = build_evidence_graph(result)
    public_execution_log = public_safe_execution_log(result.get("execution_log", []))
    public_wrds_result = public_safe_wrds_result(result.get("wrds_result", {}))
    public_data_source_results = public_safe_data_source_results(
        result.get("data_source_results")
        or result.get("provider_results")
        or public_wrds_result.get("data_source_results")
        or public_wrds_result.get("provider_results")
        or []
    )
    agent_outputs = runtime_agent_outputs(result)
    agent_decision = runtime_agent_decision(result)
    legacy_decision = legacy_committee_decision(result)
    if not legacy_decision:
        legacy_decision = agent_decision or skipped_analysis(
            legacy_skipped_analysis_reason("investment_committee_not_required")
        )
    return {
        **result,
        "metadata": result.get("metadata", {}),
        "selected_skills": result.get("selected_skills", []),
        "plan": result.get("plan", []),
        "execution_log": public_execution_log,
        "wrds_result": public_wrds_result,
        "data_source_results": public_data_source_results,
        "provider_results": public_safe_data_source_results(result.get("provider_results") or public_data_source_results),
        "data_contract": result.get("data_contract", {}),
        "metric_registry": result.get("metric_registry", {}),
        "data_gate": result.get("data_gate", {"status": "skipped", "blocking": False}),
        "memory_context": result.get("memory_context", {"status": "empty", "items": []}),
        "research_brief": result.get(
            "research_brief",
            skipped_analysis(legacy_skipped_analysis_reason("research_not_required")),
        ),
        "quant_analysis": result.get(
            "quant_analysis",
            skipped_analysis(legacy_skipped_analysis_reason("quant_analysis_not_required")),
        ),
        "domain_analysis": result.get(
            "domain_analysis",
            skipped_analysis(legacy_skipped_analysis_reason("domain_judgment_not_required")),
        ),
        "agent_outputs": agent_outputs,
        "committee_outputs": result.get("committee_outputs", {}),
        "discussion_transcript": result.get("discussion_transcript", []),
        "agent_decision": agent_decision
        or skipped_analysis(legacy_skipped_analysis_reason("agent_decision_not_required")),
        "committee_decision": legacy_decision,
        "pheromone_field_snapshot": result.get("pheromone_field_snapshot", {}),
        "pheromone_trace": result.get("pheromone_trace", []),
        "stop_signals": result.get("stop_signals", []),
        "constraint_signals": result.get("constraint_signals", []),
        "quorum_trace": result.get("quorum_trace", {}),
        "agent_allocation_trace": result.get("agent_allocation_trace", []),
        "agent_signal_diagnostics": result.get("agent_signal_diagnostics", []),
        "agent_signal_verification_trace": result.get("agent_signal_verification_trace", []),
        "swarm_execution_loop": result.get("swarm_execution_loop", {}),
        "swarm_protocol_trace": result.get("swarm_protocol_trace", []),
        "swarm_governance_trace": result.get("swarm_governance_trace", []),
        "governance_results": result.get("governance_results", []),
        "enforcement_bus_report": result.get("enforcement_bus_report", {}),
        "encounter_rate_report": result.get("encounter_rate_report", {}),
        "bottleneck_report": result.get("bottleneck_report", {}),
        "arousal_report": result.get("arousal_report", {}),
        "lane_assignment_report": result.get("lane_assignment_report", {}),
        "social_immunity_report": result.get("social_immunity_report", {}),
        "policing_trace": result.get("policing_trace", {}),
        "receiver_normalizer_report": result.get("receiver_normalizer_report", {}),
        "evidence_steward_report": result.get("evidence_steward_report", {}),
        "tool_health_sentinel_report": result.get("tool_health_sentinel_report", {}),
        "capability_sandbox_auditor_report": result.get("capability_sandbox_auditor_report", {}),
        "outcome_memory_steward_report": result.get("outcome_memory_steward_report", {}),
        "quorum_marshal_report": result.get("quorum_marshal_report", {}),
        "homeostasis_report": result.get("homeostasis_report", {}),
        "maturity_report": result.get("maturity_report", {}),
        "independence_report": result.get("independence_report", {}),
        "swarm_controller_report": result.get("swarm_controller_report", {}),
        "signal_resolution_report": result.get("signal_resolution_report", {}),
        "artifact_cue_report": result.get("artifact_cue_report", {}),
        "trust_badges": result.get("trust_badges", []),
        "patroller_report": result.get("patroller_report", {}),
        "workflow_routing": result.get("workflow_routing", {}),
        "domain_workflow": result.get("domain_workflow", {}),
        "swarm_metrics": result.get("swarm_metrics", {}),
        "evidence_graph": evidence_graph,
        "review": result.get("review", {"status": "skipped", "issues": [], "summary": "Critic not required."}),
        "draft_final": result.get("draft_final", result.get("final", "")),
    }


def preserve_runtime_metadata(result: dict[str, Any], initial_metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep OS control-plane metadata attached to the final run artifact."""

    current = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    merged = {**initial_metadata, **current}
    tenant_id = str(merged.get("tenant_id") or nested_metadata_tenant(merged) or result.get("tenant_id") or "")
    if tenant_id:
        merged["tenant_id"] = tenant_id
    return {**result, "tenant_id": tenant_id or result.get("tenant_id"), "metadata": merged}


def nested_metadata_tenant(metadata: dict[str, Any]) -> str | None:
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    tenant_id = os_plan.get("tenant_id")
    return str(tenant_id) if tenant_id else None


def summarize_run_outcome(result: dict[str, Any]) -> tuple[str, list[str]]:
    if result.get("error"):
        return "failed", [str(result.get("error"))]

    blocked_reasons: list[str] = []
    degraded_reasons: list[str] = []

    if data_gate_failed(result):
        blocked_reasons.append("Data Gate failed.")
    elif data_gate_publication_blocked(result):
        blocked_reasons.append("Data Gate blocked publication.")

    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    review_status = str(review.get("status") or "").strip().upper()
    if review_status in {"REJECT_CONDITIONAL", "REJECT_FATAL"}:
        blocked_reasons.append(f"Critic blocked publication with status {review_status}.")

    for metric in result.get("agent_metrics") or []:
        if not isinstance(metric, dict):
            continue
        status = str(metric.get("status") or "")
        failure_reason = metric.get("failure_reason")
        if failure_reason or status in {
            "failed",
            "failed_blocking",
            "completed_with_model_failure",
            "completed_with_tool_failure",
            "completed_with_step_failures",
            "completed_with_partial_tool_failures",
        }:
            agent = metric.get("agent") or "agent"
            reason = failure_reason or status
            degraded_reasons.append(f"{agent}: {reason}")

    for step in result.get("execution_log") or []:
        if isinstance(step, dict) and step.get("status") == "failed":
            degraded_reasons.append(f"tool step failed: {step.get('step_id') or step.get('title') or 'unknown'}")

    if blocked_reasons:
        return "blocked", unique_strings(blocked_reasons + degraded_reasons)
    if degraded_reasons:
        return "degraded", unique_strings(degraded_reasons)
    return "completed", []


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def fatal_runtime_validation_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fatal: list[dict[str, Any]] = []
    legacy_wrds_codes = legacy_wrds_validation_issue_codes()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "").strip().lower()
        code = str(issue.get("code") or "").strip()
        if severity == "blocking" or code in {
            "runtime_not_ready",
            "missing_model_provider",
            "missing_connection",
        } | legacy_wrds_codes:
            fatal.append(issue)
    return fatal


def runtime_preflight_blocked_result(
    *,
    task: str,
    skill_names: list[str] | None,
    metadata: dict[str, Any],
    tenant_id: str,
    context: RuntimeContext,
    fatal_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    agent_catalog = (context.agent_registry or {}).get("agents", [])
    enriched_metadata = {
        **metadata,
        "_runtime_materialized": True,
        "tenant_id": tenant_id,
        "capability_index": context.capability_index,
        "model_routing_policy": context.model_routing_policy,
        "os_plan": context.os_plan,
        "enabled_capabilities": context.enabled_capabilities,
        "permission_grants": context.permission_grants,
        "data_source_registry": context.data_source_registry,
        "skill_registry": context.skill_registry,
        "agent_registry": context.agent_registry,
        "capability_runtime": context.capability_runtime,
        "agent_catalog": agent_catalog,
        **legacy_committee_agent_catalog_metadata(agent_catalog),
        "runtime_validation_issues": context.validation_issues or [],
        "preflight_blocked": True,
    }
    state: AgentState = {
        "run_id": run_id,
        "task": task,
        "metadata": {
            **enriched_metadata,
            "requested_skill_names": skill_names or [],
        },
        "route": "preflight_blocked",
        "selected_skills": [],
        "plan": [],
        "execution_log": [],
        "tool_manifest": context.tool_registry.manifest(),
        "patroller_report": {},
        "workflow_routing": workflow_routing_summary({"metadata": enriched_metadata}),
        "review": {
            "status": "REJECT_FATAL",
            "issues": [str(issue.get("message") or issue.get("code") or issue) for issue in fatal_issues],
            "summary": legacy_runtime_preflight_blocked_summary(),
        },
    }
    patroller_report = build_patroller_report(state)
    signal_update = update_state_with_signals(
        {**state, "patroller_report": patroller_report},
        [
            *initial_signals_from_state({**state, "patroller_report": patroller_report}),
            *patroller_signals(state, patroller_report),
        ],
    )
    blocked_state = {
        **state,
        "patroller_report": patroller_report,
        **signal_update,
    }
    final = render_patroller_defect_memo(blocked_state)
    result = normalize_run_result(
        {
            **blocked_state,
            "research_brief": skipped_analysis(
                legacy_skipped_analysis_reason("runtime_preflight_blocked_research")
            ),
            "quant_analysis": skipped_analysis(
                legacy_skipped_analysis_reason("runtime_preflight_blocked_quant_analysis")
            ),
            "domain_analysis": skipped_analysis(
                legacy_skipped_analysis_reason("runtime_preflight_blocked_domain_analysis")
            ),
            "agent_outputs": {},
            "committee_outputs": {},
            "discussion_transcript": [],
            "agent_decision": skipped_analysis(
                legacy_skipped_analysis_reason("runtime_preflight_blocked_agent_decision")
            ),
            "committee_decision": skipped_analysis(
                legacy_skipped_analysis_reason("runtime_preflight_blocked_committee")
            ),
            "draft_final": final,
            "final": final,
            "agent_metrics": [],
            "run_status": "blocked",
            "degraded_reasons": [str(issue.get("message") or issue.get("code") or issue) for issue in fatal_issues],
        }
    )
    result["run_status"] = "blocked"
    result["degraded_reasons"] = unique_strings(
        [str(issue.get("message") or issue.get("code") or issue) for issue in fatal_issues]
    )
    try:
        append_swarm_trace(result)
    except OSError:
        pass
    try:
        append_run_audit(result)
    except OSError:
        pass
    return result


def normalize_orchestration(
    payload: dict[str, Any],
    *,
    task: str,
    selected_skills: list[Skill],
    os_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    os_plan = os_plan if isinstance(os_plan, dict) else {}
    suppress_investment_defaults = protocol_plan_suppresses_graph_investment_defaults(os_plan)
    task_type = normalize_task_type(str(payload.get("task_type") or infer_task_type(task, selected_skills)))
    return legacy_normalize_orchestration_defaults(
        payload,
        task=task,
        selected_skills=selected_skills,
        task_type=task_type,
        suppress_investment_defaults=suppress_investment_defaults,
    )


def normalize_task_type(value: str) -> str:
    return legacy_normalize_task_type(value)


def os_plan_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return os_plan


def protocol_plan_suppresses_graph_investment_defaults(os_plan: dict[str, Any]) -> bool:
    if not protocol_backed_os_plan(os_plan):
        return False
    return not os_plan_declares_committee_or_source_policy(os_plan)


def protocol_backed_os_plan(os_plan: dict[str, Any]) -> bool:
    if str(os_plan.get("intent_source") or "").strip() == "capability_protocol_intent":
        return True
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    return str(swarm_plan.get("protocol_source") or "").strip() == "capability_manifest"


def os_plan_declares_committee_or_source_policy(os_plan: dict[str, Any]) -> bool:
    committee_plan = os_plan.get("committee_plan") if isinstance(os_plan.get("committee_plan"), dict) else {}
    if bool(committee_plan.get("required")):
        return True
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    tool_policy = swarm_plan.get("tool_policy") if isinstance(swarm_plan.get("tool_policy"), dict) else {}
    return bool(str(tool_policy.get("source_mode") or "").strip())


def next_after_orchestrator(state: AgentState) -> str:
    return "patroller_gate"


def next_after_patroller(state: AgentState) -> str:
    if patroller_blocked(state):
        return "writer"
    if should_run_wrds_agent(state):
        return "wrds_agent"
    if should_run_workflow_host(state):
        return "workflow_host"
    return next_required_node(state, after="orchestrator")


def next_after_memory(state: AgentState) -> str:
    return next_required_node(state, after="memory_agent")


def next_after_executor(state: AgentState) -> str:
    if should_run_data_gate(state):
        return "data_gate"
    return next_required_node(state, after="executor")


def next_after_workflow_host(state: AgentState) -> str:
    return next_required_node(state, after="workflow_host")


def next_after_data_gate(state: AgentState) -> str:
    if data_gate_failed(state):
        return "writer"
    return next_required_node(state, after="data_gate")


def next_after_research(state: AgentState) -> str:
    return next_required_node(state, after="research_agent")


def next_after_quant(state: AgentState) -> str:
    if workflow_node_order_from_state(state):
        return next_required_node(state, after="quant_agent")
    if should_run_committee(state):
        return "committee_opening"
    return next_required_node(state, after="quant_agent")


def next_after_domain(state: AgentState) -> str:
    return next_required_node(state, after="domain_expert")


def next_after_critic(state: AgentState) -> str:
    return "writer"


def next_after_writer(state: AgentState) -> str:
    if (
        patroller_blocked(state)
        or
        data_gate_failed(state)
        or data_gate_publication_blocked(state)
        or report_publication_blocked(state)
        or review_requires_revision_or_stop(state.get("review", {}))
    ):
        return END
    if should_run_final_judge_agent(state):
        return "final_judge"
    return END


def next_required_node(state: AgentState, *, after: str) -> str:
    order = active_node_order(state)
    start_index = order.index(after) + 1 if after in order else 0
    for node in order[start_index:]:
        if node == "memory_agent" and should_run_memory_node(state):
            return node
        if node == "executor" and should_run_executor_node(state):
            return node
        if node == "data_gate" and should_run_data_gate(state):
            return node
        if node == "research_agent" and should_run_research_agent(state):
            return node
        if node == "quant_agent" and should_run_quant_agent(state):
            return node
        if node == "domain_expert" and should_run_domain_expert(state):
            return node
        if node == "committee_opening" and should_run_committee(state):
            return node
        if node == "critic" and should_run_critic_agent(state):
            return node
        if node == "writer":
            return node
    return "writer"


def should_run_memory_node(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "memory_agent")
    if workflow_decision is not None:
        return workflow_decision
    required = (state.get("orchestration") or {}).get("required_agents") or {}
    return bool(required.get("memory")) or bool(build_memory_context(state.get("metadata", {}), task=state["task"])["items"])


def should_run_wrds_agent(state: AgentState) -> bool:
    try:
        entrypoint = wrds_runtime_routing_entrypoint("should_run_node")
        if entrypoint is not None:
            return bool(entrypoint(**accepted_node_kwargs(entrypoint, {"state": state})))
    except CapabilityEntrypointError:
        pass
    return legacy_should_run_wrds_agent(state)


def should_run_workflow_host(state: AgentState) -> bool:
    workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state(state))
    graph_mode = str(workflow.get("graph_mode") or "").strip()
    if not graph_mode or legacy_builtin_graph_mode(graph_mode):
        return False
    entrypoints = workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {}
    if not entrypoints:
        return False
    current = state.get("domain_workflow") if isinstance(state.get("domain_workflow"), dict) else {}
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    if not current:
        current = metadata.get("domain_workflow") if isinstance(metadata.get("domain_workflow"), dict) else {}
    if current.get("graph_host_node") == "workflow_host":
        return False
    if current.get("deferred_to_graph_node") == "workflow_host":
        return True
    if current:
        return False
    return bool(state.get("defer_generic_workflow_host"))


def should_bypass_graph_to_wrds(*, task: str, metadata: dict[str, Any], skills: list[Skill]) -> bool:
    try:
        entrypoint = wrds_runtime_routing_entrypoint("should_bypass_graph")
        if entrypoint is not None:
            return bool(
                entrypoint(
                    **accepted_node_kwargs(
                        entrypoint,
                        {
                            "task": task,
                            "metadata": metadata,
                            "skills": skills,
                        },
                    )
                )
            )
    except CapabilityEntrypointError:
        pass
    return legacy_should_bypass_graph_to_wrds(task=task, metadata=metadata, skills=skills)


def build_direct_wrds_orchestration() -> dict[str, Any]:
    try:
        entrypoint = wrds_runtime_routing_entrypoint("direct_orchestration")
        if entrypoint is not None:
            result = entrypoint()
            if isinstance(result, dict):
                return result
    except CapabilityEntrypointError:
        pass
    return legacy_direct_wrds_orchestration()


def wrds_runtime_routing_entrypoint(name: str) -> Any | None:
    capability_id = legacy_wrds_financial_data_capability_id()
    cache_key = (capability_id, "runtime_nodes.routing", name)
    if cache_key in _CAPABILITY_NODE_CACHE:
        return _CAPABILITY_NODE_CACHE[cache_key]
    manifest = CapabilityRegistry().get(capability_id)
    if manifest is None:
        return None
    descriptor = load_capability_descriptor(manifest)
    runtime_nodes = descriptor.get("entrypoints", {}).get("runtime_nodes")
    routing = runtime_nodes.get("routing") if isinstance(runtime_nodes, dict) and isinstance(runtime_nodes.get("routing"), dict) else {}
    entrypoint = str(routing.get(name) or "").strip()
    if not entrypoint or ":" not in entrypoint:
        return None
    path_text, function_name = entrypoint.split(":", 1)
    module_path = safe_entrypoint_path(manifest, path_text)
    function = load_function(module_path, function_name)
    _CAPABILITY_NODE_CACHE[cache_key] = function
    return function


def should_run_executor_node(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "executor")
    if workflow_decision is not None:
        return workflow_decision
    for step in state.get("plan") or []:
        tool_calls = step.get("tool_calls")
        if tool_calls is None:
            return True
        if isinstance(tool_calls, list) and len(tool_calls) > 0:
            return True
    return False


def should_run_data_gate(state: AgentState) -> bool:
    if state.get("data_gate"):
        return False
    workflow_decision = workflow_node_required(state, "data_gate")
    if workflow_decision is not None:
        return workflow_decision
    requirement = data_gate_required_decision(state)
    if requirement["required"]:
        return True
    if requirement.get("source") == DATA_CONTRACT_DATA_GATE_REQUIRED_SOURCE:
        return False
    has_financial_data = bool(state.get("wrds_result")) or plan_has_any_tool_call(
        state.get("plan") or [],
        legacy_data_gate_tool_names(),
    )
    return legacy_graph_data_gate_required(state, has_financial_data=has_financial_data)


def review_requires_revision_or_stop(review: Any) -> bool:
    if not isinstance(review, dict):
        return False
    status = str(review.get("status") or "").strip().upper()
    return status in {"REJECT_CONDITIONAL", "REJECT_FATAL"}


def infer_task_type(task: str, selected_skills: list[Any] | set[str]) -> str:
    skill_names = {skill_name(skill) for skill in selected_skills}
    lowered = task.lower()
    return legacy_infer_task_type(
        task,
        skill_names=skill_names,
        direct_wrds_selected=selected_skills_request_direct_wrds_data(list(selected_skills)),
        investment_research_selected=selected_skills_request_investment_research(list(selected_skills)),
        research_selected=research_skill_selected(selected_skills),
        known_research_marker_found=any(marker in lowered for marker in known_research_company_markers()),
        company_like_task=looks_like_ticker_or_company_name(task),
    )


def normalize_translated_text(value: Any, *, fallback: str) -> str:
    text = str(value or fallback).strip() or fallback
    return text


def deterministic_plan(
    *,
    task: str,
    english_search_query: str,
    selected_skills: list[dict[str, Any]],
    preferred_web_search_tool: str = WEB_SEARCH_TOOL_NAME,
    source_mode: Any = None,
) -> list[dict[str, Any]]:
    return legacy_deterministic_plan(
        task=task,
        english_search_query=english_search_query,
        selected_skills=selected_skills,
        preferred_web_search_tool=preferred_web_search_tool,
        source_mode=source_mode,
    )


def apply_source_mode_to_skills(skills: list[Skill], *, source_mode: Any) -> tuple[list[Skill], list[Skill]]:
    return partition_skills_by_source_policy(skills, source_mode=source_mode)


def plan_has_any_tool_call(plan: list[dict[str, Any]], tool_names: set[str]) -> bool:
    for step in plan:
        tool_calls = step.get("tool_calls") or []
        if any(call.get("name") in tool_names for call in tool_calls if isinstance(call, dict)):
            return True
    return False


def parse_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def tool_manifest_for_state(manifest: list[dict[str, Any]], state: AgentState | dict[str, Any]) -> list[dict[str, Any]]:
    if not web_tools_disabled_for_state(state):
        return manifest
    blocked_tool_names = {
        target.split(":", 1)[1]
        for target in source_policy_blocked_tool_targets(state)
        if target.startswith("tool:")
    }
    return [tool for tool in manifest if str(tool.get("name") or "") not in blocked_tool_names]


def enforce_source_mode_on_plan(
    plan: list[dict[str, Any]],
    *,
    source_mode: Any,
    tool_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return filter_plan_by_source_and_tool_policy(plan, source_mode=source_mode, tool_policy=tool_policy)


def normalize_web_search_args(args: dict[str, Any], *, state: AgentState) -> dict[str, Any]:
    normalized = dict(args)
    query = str(normalized.get("query") or "").strip()
    if not query:
        query = state.get("search_query") or state.get("english_search_query") or state["task"]
    elif should_preserve_original_search_language(state["task"], query):
        query = state.get("search_query") or state["task"]
    normalized["query"] = normalize_search_query(query)
    return normalized


def normalize_search_query(query: str) -> str:
    return query.strip()


def should_preserve_original_search_language(task: str, query: str) -> bool:
    if not has_cjk(task) or has_cjk(query):
        return False
    lowered = task.lower()
    explicit_english_request = any(marker in lowered for marker in ("english", "英文", "英语", "外文", "英文资料"))
    return not explicit_english_request


def parse_plan(content: str) -> list[dict[str, Any]]:
    payload = parse_json_object(content)
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RuntimeError("orchestrator response must include a non-empty steps array")

    normalized = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise RuntimeError("each plan step must be an object")
        action, tool_calls = normalize_plan_action(step)
        normalized.append(
            {
                "id": str(step.get("id") or index),
                "title": str(step.get("title") or f"Step {index}"),
                "action": action,
                "tool_calls": tool_calls,
            }
        )
    return normalized


def normalize_plan_action(step: dict[str, Any]) -> tuple[str, list[dict[str, Any]] | None]:
    raw_action = step.get("action") or ""
    raw_tool_calls = first_present(step, "tool_calls", "tools", "tool")

    if isinstance(raw_action, dict):
        if not raw_tool_calls:
            raw_tool_calls = first_present(raw_action, "tool_calls", "tools", "tool")
        action = str(raw_action.get("description") or raw_action.get("action") or raw_action.get("name") or "")
        return action, normalize_tool_calls(raw_tool_calls) if raw_tool_calls is not None else None

    if isinstance(raw_action, str) and not raw_tool_calls:
        parsed = parse_literal_dict(raw_action)
        if parsed:
            parsed_tool_calls = first_present(parsed, "tool_calls", "tools", "tool")
            if parsed_tool_calls is not None:
                return str(parsed.get("description") or parsed.get("action") or ""), normalize_tool_calls(parsed_tool_calls)

    return str(raw_action), normalize_tool_calls(raw_tool_calls) if raw_tool_calls is not None else None


def first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def parse_literal_dict(value: str) -> dict[str, Any] | None:
    stripped = value.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        parsed = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    if tool_calls in (None, ""):
        return []
    if isinstance(tool_calls, str):
        tool_calls = [tool_calls]
    if isinstance(tool_calls, dict):
        tool_calls = [tool_calls]
    if not isinstance(tool_calls, list):
        raise RuntimeError("tool_calls must be an array")
    normalized = []
    for call in tool_calls:
        normalized_call = normalize_tool_call(call)
        if normalized_call is None:
            continue
        normalized.append(normalized_call)
    return normalized


def extract_tool_calls_from_text(content: str) -> list[dict[str, Any]]:
    """Recover tool calls from malformed model JSON such as merged objects."""
    text = str(content or "")
    recovered: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    name_matches = list(re.finditer(r'"name"\s*:\s*"([^"]+)"', text))
    for index, match in enumerate(name_matches):
        name = match.group(1)
        next_start = name_matches[index + 1].start() if index + 1 < len(name_matches) else len(text)
        chunk = text[match.end() : next_start]
        args: Any = {}
        args_match = re.search(r'"args"\s*:', chunk)
        if args_match:
            object_start = chunk.find("{", args_match.end())
            if object_start >= 0:
                try:
                    args, _ = decoder.raw_decode(chunk[object_start:])
                except json.JSONDecodeError:
                    args = {}
        normalized = normalize_tool_call({"name": name, "args": args})
        if normalized is not None:
            recovered.append(normalized)
    return recovered


def normalize_tool_call(call: Any) -> dict[str, Any] | None:
    if isinstance(call, str):
        name = call.strip()
        return {"name": name, "args": {}} if name else None
    if not isinstance(call, dict):
        raise RuntimeError("each tool call must be an object")

    function = call.get("function")
    name = call.get("name") or call.get("tool") or call.get("tool_name")
    args = first_present(call, "args", "arguments", "input", "parameters")

    if isinstance(function, dict):
        name = name or function.get("name")
        if args is None:
            args = first_present(function, "args", "arguments", "input", "parameters")
    elif isinstance(function, str) and not name:
        name = function

    if not name and len(call) == 1:
        only_key = next(iter(call))
        only_value = call[only_key]
        if only_key not in {"name", "tool", "tool_name", "function", "args", "arguments", "input", "parameters", "description"}:
            name = only_key
            args = only_value

    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    args = normalize_tool_args(args, tool_name=name)
    return {"name": name, "args": args}


def normalize_tool_args(args: Any, *, tool_name: str) -> dict[str, Any]:
    if args in (None, ""):
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        parsed = parse_literal_dict(args)
        if parsed is not None:
            return parsed
        try:
            decoded = json.loads(args)
        except json.JSONDecodeError:
            if tool_name in SEARCH_TOOL_NAMES:
                return {"query": args}
            raise RuntimeError("tool call args must be an object")
        if isinstance(decoded, dict):
            return decoded
        if tool_name in SEARCH_TOOL_NAMES and isinstance(decoded, str):
            return {"query": decoded}
        raise RuntimeError("tool call args must be an object")
    if tool_name in SEARCH_TOOL_NAMES:
        return {"query": str(args)}
    raise RuntimeError("tool call args must be an object")


def summarize_tool_results(step: dict[str, Any], results: list[dict[str, Any]]) -> str:
    if not results:
        return f"No tool call required for action: {step.get('action')}"
    ok_count = sum(1 for item in results if item["result"].get("ok"))
    return f"Executed {ok_count}/{len(results)} tool calls for action: {step.get('action')}"


def collect_wrds_results(execution_log: list[dict[str, Any]], *, state: dict[str, Any] | None = None) -> dict[str, Any]:
    collector = wrds_result_collector_from_state(state) or load_capability_runtime_node(
        legacy_wrds_financial_data_capability_id(),
        "collect_wrds_results",
    )
    return collector(
        **accepted_node_kwargs(
            collector,
            {
                "execution_log": execution_log,
                "state": state or {},
            },
        )
    )


def wrds_result_collector_from_state(state: dict[str, Any] | None) -> Any | None:
    if not isinstance(state, dict):
        return None
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    runtime = metadata.get("capability_runtime") if isinstance(metadata.get("capability_runtime"), dict) else {}
    capabilities = runtime.get("capabilities") if isinstance(runtime.get("capabilities"), dict) else {}
    capability_id = legacy_wrds_financial_data_capability_id()
    descriptor = capabilities.get(capability_id) if isinstance(capabilities.get(capability_id), dict) else {}
    entrypoints = descriptor.get("entrypoints") if isinstance(descriptor.get("entrypoints"), dict) else {}
    runtime_nodes = entrypoints.get("runtime_nodes") if isinstance(entrypoints.get("runtime_nodes"), dict) else {}
    collectors = runtime_nodes.get("result_collectors") if isinstance(runtime_nodes.get("result_collectors"), dict) else {}
    entrypoint = str(collectors.get("wrds_result") or "").strip()
    if not entrypoint or ":" not in entrypoint:
        return None
    manifest = CapabilityRegistry().get(capability_id)
    if manifest is None:
        return None
    try:
        path_text, function_name = entrypoint.split(":", 1)
        module_path = safe_entrypoint_path(manifest, path_text)
        return load_function(module_path, function_name)
    except CapabilityEntrypointError:
        return None


def should_auto_fetch_search_results(
    task: str,
    args: dict[str, Any],
    *,
    selected_skills: list[dict[str, Any]] | None = None,
    english_search_query: str | None = None,
) -> bool:
    return source_tool_helpers.should_auto_fetch_search_results(
        task,
        args,
        selected_skills=selected_skills,
        english_search_query=english_search_query,
    )


def web_research_selected(selected_skills: list[dict[str, Any]] | None) -> bool:
    return source_tool_helpers.web_research_selected(selected_skills)


def value_research_selected(selected_skills: list[dict[str, Any]] | None) -> bool:
    return source_tool_helpers.value_research_selected(selected_skills)


def looks_like_known_entity_research(
    task: str,
    *,
    args: dict[str, Any] | None = None,
    english_search_query: str | None = None,
) -> bool:
    return source_tool_helpers.looks_like_known_entity_research(
        task,
        args=args,
        english_search_query=english_search_query,
    )


def select_search_result_urls(search_data: dict[str, Any], *, limit: int = 5) -> list[str]:
    return source_tool_helpers.select_search_result_urls(search_data, limit=limit)


def preferred_source_fetch_tool(tool_names: list[str] | set[str]) -> str:
    return source_tool_helpers.preferred_source_fetch_tool(tool_names)


def step_tool_results_succeeded(results: list[dict[str, Any]]) -> bool:
    return source_tool_helpers.step_tool_results_succeeded(results)


def summarize_execution_metric_status(execution_log: list[dict[str, Any]]) -> tuple[str, str | None]:
    return source_tool_helpers.summarize_execution_metric_status(execution_log)


def should_run_research_agent(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "research_agent")
    if workflow_decision is not None:
        return workflow_decision
    required = (state.get("orchestration") or {}).get("required_agents") or {}
    if required.get("research"):
        return True
    if web_research_selected(state.get("selected_skills")) or value_research_selected(state.get("selected_skills")):
        return True
    return any_search_tool_called(state.get("execution_log", [])) or any(
        any_tool_called(state.get("execution_log", []), tool_name) for tool_name in FETCH_TOOL_NAMES
    )


def should_run_quant_agent(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "quant_agent")
    if workflow_decision is not None:
        return workflow_decision
    required = (state.get("orchestration") or {}).get("required_agents") or {}
    if required.get("quant"):
        return True
    return value_research_selected(state.get("selected_skills"))


def should_run_domain_expert(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "domain_expert")
    if workflow_decision is not None:
        return workflow_decision
    if should_run_committee(state):
        return False
    required = (state.get("orchestration") or {}).get("required_agents") or {}
    if required.get("domain"):
        return True
    if state.get("selected_skills"):
        return True
    return needs_domain_analysis(state["task"])


def should_run_critic_agent(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "critic")
    if workflow_decision is not None:
        return workflow_decision
    required = (state.get("orchestration") or {}).get("required_agents") or {}
    if required.get("critic"):
        return True
    return False


def should_run_final_judge_agent(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "final_judge")
    if workflow_decision is not None:
        return workflow_decision
    required = (state.get("orchestration") or {}).get("required_agents") or {}
    return bool(required.get("final_judge"))


def should_run_committee(state: AgentState) -> bool:
    workflow_decision = workflow_node_required(state, "committee_opening")
    if workflow_decision is not None:
        return workflow_decision
    orchestration = state.get("orchestration") or {}
    if orchestration.get("committee"):
        return True
    return value_research_selected(state.get("selected_skills"))


def needs_quant_analysis(task: str) -> bool:
    return legacy_needs_quant_analysis(task)


def needs_domain_analysis(task: str) -> bool:
    return legacy_needs_domain_analysis(task)


def build_memory_context(metadata: dict[str, Any], *, task: str) -> dict[str, Any]:
    items = []
    for key in legacy_memory_context_metadata_keys():
        value = metadata.get(key)
        if value:
            items.append({"key": key, "value": value})
    return {
        "status": "loaded" if items else "empty",
        "items": items,
        "task_hint": infer_task_type(task, set()),
    }


def skipped_analysis(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "reason": reason}


def research_context(state: AgentState) -> str:
    return json.dumps(
        {
            "task": state["task"],
            "translated_task": state.get("translated_task"),
            "english_search_query": state.get("english_search_query"),
            "selected_skills": state.get("selected_skills", []),
            "execution_log": model_safe_execution_log(state.get("execution_log", [])),
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "workflow_routing": state.get("workflow_routing", {}),
            "domain_workflow": state.get("domain_workflow") or (state.get("metadata", {}) or {}).get("domain_workflow", {}),
            "source_grounding": describe_source_grounding(state),
        },
        ensure_ascii=False,
    )


def quant_context(state: AgentState) -> str:
    return json.dumps(
        {
            "task": state["task"],
            "research_brief": state.get("research_brief", {}),
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "workflow_routing": state.get("workflow_routing", {}),
            "domain_workflow": state.get("domain_workflow") or (state.get("metadata", {}) or {}).get("domain_workflow", {}),
            "execution_log": model_safe_execution_log(state.get("execution_log", []), text_limit=1_500),
        },
        ensure_ascii=False,
    )


def domain_context(state: AgentState) -> str:
    return json.dumps(
        {
            "task": state["task"],
            "memory_context": state.get("memory_context", {}),
            "selected_skills": state.get("selected_skills", []),
            "skill_context": state.get("skill_context", ""),
            "research_brief": state.get("research_brief", {}),
            "quant_analysis": state.get("quant_analysis", {}),
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "workflow_routing": state.get("workflow_routing", {}),
            "domain_workflow": state.get("domain_workflow") or (state.get("metadata", {}) or {}).get("domain_workflow", {}),
        },
        ensure_ascii=False,
    )


def critic_context(state: AgentState) -> str:
    return json.dumps(
        {
            "task": state["task"],
            "orchestration": state.get("orchestration", {}),
            "plan": state.get("plan", []),
            "execution_log": model_safe_execution_log(state.get("execution_log", [])),
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "research_brief": state.get("research_brief", {}),
            "quant_analysis": state.get("quant_analysis", {}),
            "domain_analysis": state.get("domain_analysis", {}),
            "agent_outputs": agent_outputs_for_model(state),
            "legacy_agent_outputs": legacy_agent_outputs_for_model(state),
            "discussion_transcript": state.get("discussion_transcript", []),
            "agent_decision": runtime_agent_decision(state),
            "legacy_agent_decision": legacy_agent_decision(state),
            "workflow_routing": state.get("workflow_routing", {}),
            "domain_workflow": state.get("domain_workflow") or (state.get("metadata", {}) or {}).get("domain_workflow", {}),
            "swarm_governance": swarm_context_for_model(state),
            "evidence_graph": evidence_graph_for_model(state),
            "source_grounding": describe_source_grounding(state),
        },
        ensure_ascii=False,
    )


def evidence_graph_for_model(state: AgentState) -> dict[str, Any]:
    graph = state.get("evidence_graph") if isinstance(state.get("evidence_graph"), dict) else build_evidence_graph(state)
    return {
        "summary": graph.get("summary", {}),
        "writer_contract": graph.get("writer_contract", {}),
        "output_permissions": graph.get("output_permissions", []),
        "blockers": (graph.get("blockers") or [])[:8],
        "proposals": (graph.get("proposals") or [])[:8],
        "candidate_decisions": graph.get("candidate_decisions", []),
        "decision_claims": graph.get("decision_claims", []),
        "review_findings": graph.get("review_findings", []),
    }


def agent_outputs_for_model(state: AgentState) -> dict[str, Any]:
    return summarize_agent_outputs_for_model(runtime_agent_outputs(state))


def legacy_agent_outputs_for_model(state: AgentState) -> dict[str, Any]:
    return summarize_agent_outputs_for_model(legacy_committee_outputs(state))


def legacy_agent_decision(state: AgentState) -> dict[str, Any]:
    return legacy_committee_decision(state)


def writer_context(state: AgentState) -> str:
    return json.dumps(
        {
            "task": state["task"],
            "translated_task": state.get("translated_task"),
            "english_search_query": state.get("english_search_query"),
            "route": state.get("route"),
            "memory_context": state.get("memory_context", {}),
            "research_brief": state.get("research_brief", {}),
            "quant_analysis": state.get("quant_analysis", {}),
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "domain_analysis": state.get("domain_analysis", {}),
            "agent_outputs": agent_outputs_for_model(state),
            "legacy_agent_outputs": legacy_agent_outputs_for_model(state),
            "discussion_transcript": state.get("discussion_transcript", []),
            "agent_decision": runtime_agent_decision(state),
            "legacy_agent_decision": legacy_agent_decision(state),
            "swarm_governance": swarm_context_for_model(state),
            "evidence_graph": evidence_graph_for_model(state),
            "review": state.get("review", {}),
            "plan": state.get("plan", []),
            "execution_log": model_safe_execution_log(state.get("execution_log", [])),
            "workflow_routing": state.get("workflow_routing", {}),
            "domain_workflow": state.get("domain_workflow") or (state.get("metadata", {}) or {}).get("domain_workflow", {}),
        },
        ensure_ascii=False,
    )


def final_judge_context(state: AgentState) -> str:
    return json.dumps(
        {
            "task": state["task"],
            "translated_task": state.get("translated_task"),
            "draft_final": state.get("draft_final") or state.get("final") or "",
            "wrds_result_summary": summarize_wrds_result_for_model(state.get("wrds_result", {})),
            "data_contract": state.get("data_contract", {}),
            "data_gate": state.get("data_gate", {}),
            "metric_registry": metric_registry_for_model(state.get("metric_registry", {})),
            "research_brief": state.get("research_brief", {}),
            "quant_analysis": state.get("quant_analysis", {}),
            "domain_analysis": state.get("domain_analysis", {}),
            "agent_outputs": agent_outputs_for_model(state),
            "legacy_agent_outputs": legacy_agent_outputs_for_model(state),
            "discussion_transcript": state.get("discussion_transcript", []),
            "agent_decision": runtime_agent_decision(state),
            "legacy_agent_decision": legacy_agent_decision(state),
            "workflow_routing": state.get("workflow_routing", {}),
            "domain_workflow": state.get("domain_workflow") or (state.get("metadata", {}) or {}).get("domain_workflow", {}),
            "swarm_governance": swarm_context_for_model(state),
            "evidence_graph": evidence_graph_for_model(state),
            "review": state.get("review", {}),
            "source_grounding": describe_source_grounding(state),
        },
        ensure_ascii=False,
    )


def render_review_defect_memo(state: AgentState) -> str:
    review = state.get("review", {}) if isinstance(state.get("review"), dict) else {}
    lines = [
        "# Review Defect Report",
        "",
        "当前版本不可发布为最终投资报告。Critic / Verifier 已打回该输出，系统已停止 Writer 继续包装结论。",
        "",
        f"- Task: `{state.get('task')}`",
        f"- Review status: `{review.get('status', 'unknown')}`",
        "",
        "## Issues",
    ]
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    if issues:
        for index, issue in enumerate(issues, start=1):
            lines.append(f"{index}. {issue}")
    else:
        lines.append("No structured issues were provided.")
    for title, key in (
        ("Data Errors", "data_errors"),
        ("Citation Gaps", "citation_gaps"),
        ("Overclaims", "overclaims"),
        ("Minimal Fixes", "minimal_fixes"),
    ):
        values = review.get(key) if isinstance(review.get(key), list) else []
        if values:
            lines.append("")
            lines.append(f"## {title}")
            for index, value in enumerate(values, start=1):
                lines.append(f"{index}. {value}")
    summary = review.get("summary")
    if summary:
        lines.append("")
        lines.append("## Summary")
        lines.append(str(summary))
    return "\n".join(lines)


def model_safe_execution_log(execution_log: Any, *, text_limit: int = 4_000) -> list[dict[str, Any]]:
    if not isinstance(execution_log, list):
        return []
    safe_log = []
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        safe_calls = []
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            result = dict(call.get("result") or {})
            data = dict(result.get("data") or {})
            for key in ("text", "content", "stdout", "stderr"):
                if isinstance(result.get(key), str) and len(result[key]) > text_limit:
                    result[key] = result[key][:text_limit] + "\n...[truncated]"
                if isinstance(result.get(key), str):
                    result[key] = sanitize_artifact_text(result[key])
            for key in ("text", "content", "stdout", "stderr"):
                if isinstance(data.get(key), str) and len(data[key]) > text_limit:
                    data[key] = data[key][:text_limit] + "\n...[truncated]"
                if isinstance(data.get(key), str):
                    data[key] = sanitize_artifact_text(data[key])
            result["data"] = data
            safe_calls.append({**call, "result": result})
        safe_log.append({**step, "tool_calls": safe_calls})
    return safe_log


def metric_registry_for_model(metric_registry: Any) -> dict[str, Any]:
    if not isinstance(metric_registry, dict):
        return {}
    metrics = metric_registry.get("metrics") if isinstance(metric_registry.get("metrics"), list) else []
    warnings = metric_registry.get("warnings") if isinstance(metric_registry.get("warnings"), list) else []
    metric_series = metric_registry.get("metric_series") if isinstance(metric_registry.get("metric_series"), dict) else {}
    annual_metric_series = (
        metric_registry.get("annual_metric_series") if isinstance(metric_registry.get("annual_metric_series"), dict) else {}
    )
    quarterly_metric_series = (
        metric_registry.get("quarterly_metric_series") if isinstance(metric_registry.get("quarterly_metric_series"), dict) else {}
    )
    ttm_metric_series = (
        metric_registry.get("ttm_metric_series") if isinstance(metric_registry.get("ttm_metric_series"), dict) else {}
    )
    selected_metrics = select_metrics_for_model(metrics)
    return {
        "status": metric_registry.get("status"),
        "as_of_date": metric_registry.get("as_of_date"),
        "source_mode": metric_registry.get("source_mode"),
        "metric_count": len(metrics),
        "metrics_in_context": len(selected_metrics),
        "truncated": len(selected_metrics) < len(metrics),
        "derived_metrics": selected_metrics,
        "ttm_metrics": [
            slim_metric_for_model(metric)
            for metric in metrics
            if isinstance(metric, dict) and str(metric.get("metric") or "").startswith("ttm_")
        ],
        "metric_series": metric_series,
        "annual_metric_series": annual_metric_series,
        "quarterly_metric_series": quarterly_metric_series,
        "ttm_metric_series": ttm_metric_series,
        "warnings": warnings[:8],
        "warning_count": len(warnings),
        "source_priority": metric_registry.get("source_priority", []),
        "usage_rules": metric_registry.get("usage_rules", [])[:6],
        "raw_fields": "withheld_from_model_context",
    }


def select_metrics_for_model(metrics: list[Any], *, annual_limit: int = 3, quarterly_limit: int = 4) -> list[dict[str, Any]]:
    normalized = [metric for metric in metrics if isinstance(metric, dict)]
    annual_periods = latest_periods(
        [str(metric.get("period") or "") for metric in normalized if "Q" not in str(metric.get("period") or "").upper()],
        limit=annual_limit,
    )
    quarterly_periods = latest_periods(
        [str(metric.get("period") or "") for metric in normalized if "Q" in str(metric.get("period") or "").upper()],
        limit=quarterly_limit,
    )
    selected_periods = set(annual_periods + quarterly_periods)
    selected = [
        slim_metric_for_model(metric)
        for metric in normalized
        if str(metric.get("period") or "") in selected_periods and metric_relevant_for_model(metric)
    ]
    selected.sort(key=lambda metric: (period_sort_key(str(metric.get("period") or "")), str(metric.get("metric") or "")), reverse=True)
    return selected[:60]


def latest_periods(periods: list[str], *, limit: int) -> list[str]:
    unique = sorted({period for period in periods if period}, key=period_sort_key, reverse=True)
    return unique[:limit]


def period_sort_key(period: str) -> tuple[int, int, int]:
    text = str(period or "").upper()
    match = re.search(r"FY\s*(\d{4})(?:Q([1-4]))?", text)
    if match:
        return int(match.group(1)), int(match.group(2) or 0), 1
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return (0, 0, 0)


def metric_relevant_for_model(metric: dict[str, Any]) -> bool:
    name = str(metric.get("metric") or "")
    if metric.get("canonical") is True:
        return True
    return name in {
        "gross_margin_before_depreciation",
        "gross_margin_after_depreciation_candidate",
        "reported_gross_margin_candidate",
        "market_price",
        "inventory",
    }


def slim_metric_for_model(metric: dict[str, Any]) -> dict[str, Any]:
    source = metric.get("source") if isinstance(metric.get("source"), dict) else {}
    return {
        "metric": metric.get("metric"),
        "value": metric.get("value"),
        "period": metric.get("period"),
        "unit": metric.get("unit"),
        "formula": metric.get("formula"),
        "components": metric.get("components") or {},
        "confidence": metric.get("confidence"),
        "source": {
            "type": source.get("type"),
            "table": source.get("table"),
            "datadate": source.get("datadate"),
            "fyear": source.get("fyear"),
            "fyearq": source.get("fyearq"),
            "fqtr": source.get("fqtr"),
            "price_date": source.get("price_date"),
            "financial_period": source.get("financial_period"),
        },
    }


def deterministic_wrds_research_brief(state: AgentState) -> dict[str, Any]:
    return load_value_investing_support_function("deterministic_wrds_research_brief")(state)


def deterministic_wrds_quant_analysis(state: AgentState) -> dict[str, Any]:
    return load_value_investing_support_function("deterministic_wrds_quant_analysis")(state)


def committee_member_specs_for_state(state: AgentState) -> list[dict[str, Any]]:
    return load_value_investing_support_function("committee_member_specs_for_state")(state)


def default_committee_member_specs_from_manifests() -> list[dict[str, Any]]:
    return load_value_investing_support_function("default_committee_member_specs_from_manifests")()


def normalize_committee_agent_catalog(catalog: list[Any]) -> list[dict[str, Any]]:
    return load_value_investing_support_function("normalize_committee_agent_catalog")(catalog)


def normalize_selected_committee_members(value: Any) -> set[str]:
    return load_value_investing_support_function("normalize_selected_committee_members")(value)


def committee_member_order(spec: dict[str, Any]) -> int:
    return load_value_investing_support_function("committee_member_order")(spec)


def committee_member_context(
    state: AgentState,
    *,
    spec: dict[str, Any],
    prior_outputs: dict[str, Any] | None = None,
) -> str:
    return load_value_investing_support_function("committee_member_context")(
        state,
        spec=spec,
        prior_outputs=prior_outputs,
    )


def committee_discussion_context(state: AgentState, *, transcript: list[dict[str, Any]], round_number: int) -> str:
    return load_value_investing_support_function("committee_discussion_context")(
        state,
        transcript=transcript,
        round_number=round_number,
    )


def investment_committee_context(state: AgentState) -> str:
    return load_value_investing_support_function("investment_committee_context")(state)


def parse_committee_output(content: str, *, member: str) -> dict[str, Any]:
    return load_value_investing_support_function("parse_committee_output")(content, member=member)


def normalize_committee_payload(
    payload: dict[str, Any],
    *,
    member: str,
    status_default: str = "completed",
) -> dict[str, Any]:
    return load_value_investing_support_function("normalize_committee_payload")(
        payload,
        member=member,
        status_default=status_default,
    )


def normalize_emitted_signal_payloads(value: Any) -> list[dict[str, Any]]:
    return load_value_investing_support_function("normalize_emitted_signal_payloads")(value)


def salvage_committee_output(content: str) -> dict[str, Any]:
    return load_value_investing_support_function("salvage_committee_output")(content)


def parse_embedded_json_object(content: str) -> dict[str, Any] | None:
    return load_value_investing_support_function("parse_embedded_json_object")(content)


def regex_json_string_value(text: str, key: str) -> str | None:
    return load_value_investing_support_function("regex_json_string_value")(text, key)


def failed_committee_output(member: str, exc: Exception) -> dict[str, Any]:
    return load_value_investing_support_function("failed_committee_output")(member, exc)


def opening_transcript_entry(member: str, output: dict[str, Any]) -> dict[str, Any]:
    return load_value_investing_support_function("opening_transcript_entry")(member, output)


def parse_discussion_round(content: str, *, round_number: int) -> dict[str, Any]:
    return load_value_investing_support_function("parse_discussion_round")(content, round_number=round_number)


def fallback_discussion_turns(state: AgentState | dict[str, Any], *, round_number: int) -> list[dict[str, Any]]:
    return load_value_investing_support_function("fallback_discussion_turns")(state, round_number=round_number)


def should_continue_committee_discussion(
    state: AgentState,
    *,
    transcript: list[dict[str, Any]],
    model_requested_continue: bool,
    rounds_completed: int,
) -> bool:
    return load_value_investing_support_function("should_continue_committee_discussion")(
        state,
        transcript=transcript,
        model_requested_continue=model_requested_continue,
        rounds_completed=rounds_completed,
    )


def committee_discussion_pressure(state: AgentState) -> dict[str, Any]:
    return load_value_investing_support_function("committee_discussion_pressure")(state)


def parse_agent_decision(content: str, *, state: AgentState) -> dict[str, Any]:
    return load_value_investing_support_function("parse_agent_decision")(content, state=state)


def parse_committee_decision(content: str, *, state: AgentState) -> dict[str, Any]:
    return parse_agent_decision(content, state=state)


def fallback_agent_decision(state: AgentState, *, summary: str = "") -> dict[str, Any]:
    return load_value_investing_support_function("fallback_agent_decision")(state, summary=summary)


def fallback_committee_decision(state: AgentState, *, summary: str = "") -> dict[str, Any]:
    return fallback_agent_decision(state, summary=summary)


def normalize_scorecard(value: Any, *, state: AgentState) -> list[dict[str, Any]]:
    return load_value_investing_support_function("normalize_scorecard")(value, state=state)


def scorecard_fallback_by_agent(state: AgentState) -> dict[str, dict[str, Any]]:
    return load_value_investing_support_function("scorecard_fallback_by_agent")(state)


def best_confidence(primary: Any, fallback: Any) -> Any:
    return load_value_investing_support_function("best_confidence")(primary, fallback)


def agent_decision_to_domain_analysis(decision: dict[str, Any]) -> dict[str, Any]:
    return load_value_investing_support_function("agent_decision_to_domain_analysis")(decision)


def committee_decision_to_domain_analysis(decision: dict[str, Any]) -> dict[str, Any]:
    return agent_decision_to_domain_analysis(decision)


def apply_protocol_decision_boundary(state: AgentState, decision: dict[str, Any]) -> dict[str, Any]:
    return load_value_investing_support_function("apply_protocol_decision_boundary")(state, decision)


def summarize_agent_outputs_for_model(outputs: Any) -> dict[str, Any]:
    return load_value_investing_support_function("summarize_agent_outputs_for_model")(outputs)


def summarize_committee_outputs_for_model(outputs: Any) -> dict[str, Any]:
    return summarize_agent_outputs_for_model(outputs)


def normalize_score(value: Any) -> float | int | None:
    return load_value_investing_support_function("normalize_score")(value)


def parse_bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "required"}:
            return True
        if normalized in {"0", "false", "no", "off", "skip", "skipped"}:
            return False
    return bool(value)


def should_try_model_fallback(exc: Exception, *, primary_model: str, fallback_model: str | None) -> bool:
    if not fallback_model or fallback_model == primary_model:
        return False
    text = str(exc).lower()
    recoverable_markers = (
        "contentfilter",
        "content filter",
        "内容",
        "1301",
        "timed out",
        "timeout",
        "readtimeout",
        "temporarily unavailable",
        "insufficient balance",
        "insufficient quota",
        "quota",
        "resource pack",
        "余额不足",
        "无可用资源包",
        "rate limit",
        "429",
        "context window exceeds limit",
        "context length",
        "context window",
        "maximum context",
        "token limit",
        "too many tokens",
        "bad_request_error",
        "500",
        "connection error",
        "internalservererror",
        "502",
        "503",
        "504",
    )
    return any(marker in text for marker in recoverable_markers)


def model_fallback_chain(
    *,
    primary_model: str,
    explicit_fallback: str | None,
    model_config: ModelConfig,
) -> list[str]:
    chain: list[str] = [primary_model]
    if explicit_fallback:
        chain.append(explicit_fallback)
    primary_lower = str(primary_model or "").lower()
    if "glm" in primary_lower:
        chain.extend(split_model_list(model_config.glm_fallback_models))
    elif "minimax" in primary_lower:
        chain.extend(split_model_list(model_config.minimax_fallback_models))
    elif "kimi" in primary_lower or "moonshot" in primary_lower:
        chain.extend(split_model_list(os.getenv("KIMI_FALLBACK_MODELS", "kimi-k2.5,kimi-k2-turbo-preview,moonshot-v1-128k")))
    chain.extend(split_model_list(model_config.default_fallback_models))
    return unique_model_chain(chain)


def split_model_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def unique_model_chain(models: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model in models:
        key = model.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(model)
    return result


def fallback_model_label(candidate: str, *, primary_model: str, failed_models: list[str]) -> str:
    if len(failed_models) <= 1:
        return f"{candidate} (fallback from {primary_model})"
    attempted = ", ".join(failed_models)
    return f"{candidate} (fallback from {primary_model}; attempted {attempted})"


def format_model_chain_failure(failures: list[tuple[str, Exception]]) -> str:
    if not failures:
        return "Model fallback chain failed without captured errors."
    return "; ".join(f"model {model} failed: {exc}" for model, exc in failures)


def should_upgrade_search_to_provider(state: AgentState, tool_names: list[str]) -> bool:
    return source_tool_helpers.should_upgrade_search_to_provider(state, tool_names)


def committee_member_fallback_model(*, primary_model: str, fallback_model: str | None) -> str | None:
    if not fallback_model or fallback_model == primary_model:
        return None
    return fallback_model


def failed_research_brief(exc: Exception, *, grounding: str) -> dict[str, Any]:
    return {
        "status": "model_failed",
        "sources": [],
        "key_facts": [],
        "evidence_gaps": [f"Research model failed: {exc}"],
        "reliability": "unknown",
        "source_grounding": grounding,
    }


def failed_quant_analysis(exc: Exception) -> dict[str, Any]:
    return {
        "status": "model_failed",
        "assumptions": [],
        "formulas": [],
        "calculations": [],
        "metrics": [],
        "sensitivity": [],
        "missing_data": [f"Quant model failed: {exc}"],
        "data_quality": "unavailable",
    }


def parse_research_brief(content: str, *, grounding: str) -> dict[str, Any]:
    payload = parse_optional_json(content)
    if payload is None:
        return {
            "status": "unstructured",
            "sources": [],
            "key_facts": [content.strip()],
            "evidence_gaps": [],
            "reliability": "unknown",
            "source_grounding": grounding,
        }
    return {
        "status": str(payload.get("status") or "completed"),
        "sources": normalize_sources(payload.get("sources")),
        "key_facts": ensure_string_list(payload.get("key_facts")),
        "evidence_gaps": ensure_string_list(payload.get("evidence_gaps")),
        "reliability": str(payload.get("reliability") or "unknown"),
        "source_grounding": str(payload.get("source_grounding") or grounding),
    }


def parse_quant_analysis(content: str) -> dict[str, Any]:
    payload = parse_optional_json(content)
    if payload is None:
        return {
            "status": "unstructured",
            "assumptions": [],
            "formulas": [],
            "calculations": [content.strip()],
            "metrics": [],
            "sensitivity": [],
            "missing_data": [],
            "data_quality": "unknown",
        }
    return {
        "status": str(payload.get("status") or "completed"),
        "assumptions": ensure_string_list(payload.get("assumptions")),
        "formulas": ensure_string_list(payload.get("formulas")),
        "calculations": ensure_string_list(payload.get("calculations")),
        "metrics": normalize_dict_list(payload.get("metrics")),
        "sensitivity": normalize_dict_list(payload.get("sensitivity")),
        "missing_data": ensure_string_list(payload.get("missing_data")),
        "data_quality": str(payload.get("data_quality") or "unknown"),
    }


def parse_domain_analysis(content: str) -> dict[str, Any]:
    payload = parse_optional_json(content)
    if payload is None:
        return {
            "status": "unstructured",
            "domain": "unknown",
            "judgment": content.strip(),
            "framework_points": [],
            "risks": [],
            "missing_evidence": [],
            "confidence": "unknown",
        }
    return {
        "status": str(payload.get("status") or "completed"),
        "domain": str(payload.get("domain") or "unknown"),
        "judgment": str(payload.get("judgment") or ""),
        "framework_points": ensure_string_list(payload.get("framework_points")),
        "risks": ensure_string_list(payload.get("risks")),
        "missing_evidence": ensure_string_list(payload.get("missing_evidence")),
        "confidence": str(payload.get("confidence") or "unknown"),
    }


def parse_review(content: str) -> dict[str, Any]:
    payload = parse_optional_json(content)
    if payload is None:
        return {
            "status": "unstructured",
            "issues": [content.strip()],
            "overclaims": [],
            "data_errors": [],
            "citation_gaps": [],
            "minimal_fixes": [],
            "summary": content.strip(),
        }
    return {
        "status": str(payload.get("status") or "unknown"),
        "issues": ensure_string_list(payload.get("issues")),
        "overclaims": ensure_string_list(payload.get("overclaims")),
        "data_errors": ensure_string_list(payload.get("data_errors")),
        "citation_gaps": ensure_string_list(payload.get("citation_gaps")),
        "minimal_fixes": ensure_string_list(payload.get("minimal_fixes")),
        "summary": str(payload.get("summary") or ""),
    }


def normalize_sources(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sources = []
    for item in value:
        if not isinstance(item, dict):
            continue
        sources.append(
            {
                "title": str(item.get("title") or ""),
                "url": str(item.get("url") or ""),
                "date": str(item.get("date") or ""),
                "key_facts": ensure_string_list(item.get("key_facts")),
                "reliability": str(item.get("reliability") or "unknown"),
            }
        )
    return sources


def normalize_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def apply_review_grounding_policy(review: dict[str, Any], state: AgentState) -> dict[str, Any]:
    execution_log = state.get("execution_log", [])
    if (
        not requires_source_grounding(state)
        or has_fetched_source_text(execution_log)
        or has_provider_web_search_results(execution_log)
        or has_wrds_professional_data(execution_log)
    ):
        return review

    issues = ensure_string_list(review.get("issues"))
    citation_gaps = ensure_string_list(review.get("citation_gaps"))
    grounding_issue = (
        "No fetched source text is available; this run is only grounded in search snippets, "
        "so conclusions must be treated as preliminary."
    )
    if grounding_issue not in issues:
        issues.append(grounding_issue)
    if grounding_issue not in citation_gaps:
        citation_gaps.append(grounding_issue)
    return {
        **review,
        "status": "needs_sources",
        "issues": issues,
        "citation_gaps": citation_gaps,
        "summary": append_summary_note(review.get("summary"), "Source grounding is incomplete because no fetched page text was available."),
    }


def requires_source_grounding(state: AgentState) -> bool:
    return source_tool_helpers.requires_source_grounding(state)


def any_tool_called(execution_log: Any, tool_name: str) -> bool:
    return source_tool_helpers.any_tool_called(execution_log, tool_name)


def any_search_tool_called(execution_log: Any) -> bool:
    return source_tool_helpers.any_search_tool_called(execution_log)


def has_fetched_source_text(execution_log: Any, *, min_word_count: int = 80) -> bool:
    return source_tool_helpers.has_fetched_source_text(execution_log, min_word_count=min_word_count)


def has_provider_web_search_results(execution_log: Any) -> bool:
    return source_tool_helpers.has_provider_web_search_results(execution_log)


def has_wrds_professional_data(execution_log: Any) -> bool:
    return source_tool_helpers.has_wrds_professional_data(execution_log)


def describe_source_grounding(state: AgentState) -> str:
    return source_tool_helpers.describe_source_grounding(state)


def append_summary_note(summary: Any, note: str) -> str:
    text = str(summary or "").strip()
    if not text:
        return note
    if note in text:
        return text
    return f"{text} {note}"


def parse_optional_json(content: str) -> dict[str, Any] | None:
    try:
        return parse_json_object(content)
    except RuntimeError:
        return None


def parse_json_object(content: str) -> dict[str, Any]:
    stripped = strip_reasoning_blocks(str(content or "")).strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        payload = decode_first_json_object(stripped)
        if payload is None:
            raise RuntimeError(f"response did not contain a JSON object: {str(content or '')[:200]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("response JSON must be an object")
    return payload


def strip_reasoning_blocks(content: str) -> str:
    text = str(content or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def decode_first_json_object(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            decoded, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return None


def ensure_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(value)]


def parse_discussion_view(content: str, *, role: str) -> dict[str, Any]:
    payload = parse_json_object(content)
    return {
        "stance": str(payload.get("stance") or role),
        "key_points": ensure_string_list(payload.get("key_points")),
        "evidence": ensure_string_list(payload.get("evidence")),
        "assumptions": ensure_string_list(payload.get("assumptions")),
    }


def parse_synthesis(content: str) -> dict[str, Any]:
    payload = parse_json_object(content)
    return {
        "summary": str(payload.get("summary") or ""),
        "agreements": ensure_string_list(payload.get("agreements")),
        "disagreements": ensure_string_list(payload.get("disagreements")),
        "balanced_conclusion": str(payload.get("balanced_conclusion") or ""),
        "confidence": str(payload.get("confidence") or "unknown"),
        "open_questions": ensure_string_list(payload.get("open_questions")),
    }
