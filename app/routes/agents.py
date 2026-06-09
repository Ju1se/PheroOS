from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.routes.dependencies import get_agent_runtime
from runtime.graph import AgentRuntime


router = APIRouter(prefix="/agents", tags=["agents"])


class AgentRunRequest(BaseModel):
    task: str = Field(min_length=1)
    skill_names: list[str] | None = None
    tenant_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    run_id: str
    task: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    translated_task: str | None = None
    search_query: str | None = None
    english_search_query: str | None = None
    orchestration: dict[str, Any] | None = None
    route: str
    selected_skills: list[dict[str, str]]
    plan: list[dict[str, Any]]
    execution_log: list[dict[str, Any]]
    wrds_result: dict[str, Any] | None = None
    data_source_results: list[dict[str, Any]] = Field(default_factory=list)
    provider_results: list[dict[str, Any]] = Field(default_factory=list)
    data_contract: dict[str, Any] | None = None
    metric_registry: dict[str, Any] | None = None
    data_gate: dict[str, Any] | None = None
    memory_context: dict[str, Any] | None = None
    research_brief: dict[str, Any] | None = None
    quant_analysis: dict[str, Any] | None = None
    domain_analysis: dict[str, Any] | None = None
    agent_outputs: dict[str, Any] | None = None
    committee_outputs: dict[str, Any] | None = None
    discussion_transcript: list[dict[str, Any]] = Field(default_factory=list)
    agent_decision: dict[str, Any] | None = None
    committee_decision: dict[str, Any] | None = None
    pheromone_field_snapshot: dict[str, Any] | None = None
    pheromone_trace: list[dict[str, Any]] = Field(default_factory=list)
    stop_signals: list[dict[str, Any]] = Field(default_factory=list)
    constraint_signals: list[dict[str, Any]] = Field(default_factory=list)
    quorum_trace: dict[str, Any] | None = None
    agent_allocation_trace: list[dict[str, Any]] = Field(default_factory=list)
    agent_signal_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    agent_signal_verification_trace: list[dict[str, Any]] = Field(default_factory=list)
    swarm_execution_loop: dict[str, Any] | None = None
    swarm_protocol_trace: list[dict[str, Any]] = Field(default_factory=list)
    swarm_governance_trace: list[dict[str, Any]] = Field(default_factory=list)
    governance_results: list[dict[str, Any]] = Field(default_factory=list)
    enforcement_bus_report: dict[str, Any] | None = None
    encounter_rate_report: dict[str, Any] | None = None
    bottleneck_report: dict[str, Any] | None = None
    arousal_report: dict[str, Any] | None = None
    lane_assignment_report: dict[str, Any] | None = None
    social_immunity_report: dict[str, Any] | None = None
    policing_trace: dict[str, Any] | None = None
    receiver_normalizer_report: dict[str, Any] | None = None
    evidence_steward_report: dict[str, Any] | None = None
    tool_health_sentinel_report: dict[str, Any] | None = None
    capability_sandbox_auditor_report: dict[str, Any] | None = None
    outcome_memory_steward_report: dict[str, Any] | None = None
    quorum_marshal_report: dict[str, Any] | None = None
    homeostasis_report: dict[str, Any] | None = None
    maturity_report: dict[str, Any] | None = None
    independence_report: dict[str, Any] | None = None
    swarm_controller_report: dict[str, Any] | None = None
    signal_resolution_report: dict[str, Any] | None = None
    artifact_cue_report: dict[str, Any] | None = None
    trust_badges: list[dict[str, Any]] = Field(default_factory=list)
    patroller_report: dict[str, Any] | None = None
    workflow_routing: dict[str, Any] | None = None
    swarm_metrics: dict[str, Any] | None = None
    evidence_graph: dict[str, Any] | None = None
    review: dict[str, Any]
    draft_final: str | None = None
    final: str
    agent_metrics: list[dict[str, Any]] = Field(default_factory=list)
    run_status: str = "completed"
    degraded_reasons: list[str] = Field(default_factory=list)


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    runtime: AgentRuntime = Depends(get_agent_runtime),
) -> dict[str, Any]:
    try:
        metadata = dict(request.metadata or {})
        if request.tenant_id:
            metadata["tenant_id"] = request.tenant_id
        return await runtime.run(
            task=request.task,
            skill_names=request.skill_names,
            metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
