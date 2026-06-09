from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    task: str
    translated_task: str
    search_query: str
    english_search_query: str
    metadata: dict[str, Any]
    orchestration: dict[str, Any]
    route: str
    selected_skills: list[dict[str, str]]
    skill_context: str
    memory_context: dict[str, Any]
    plan: list[dict[str, Any]]
    execution_log: list[dict[str, Any]]
    wrds_result: dict[str, Any]
    data_source_results: list[dict[str, Any]]
    provider_results: list[dict[str, Any]]
    data_contract: dict[str, Any]
    metric_registry: dict[str, Any]
    data_gate: dict[str, Any]
    research_brief: dict[str, Any]
    quant_analysis: dict[str, Any]
    domain_analysis: dict[str, Any]
    agent_outputs: dict[str, Any]
    agent_decision: dict[str, Any]
    committee_outputs: dict[str, Any]
    discussion_transcript: list[dict[str, Any]]
    committee_decision: dict[str, Any]
    pheromone_field_snapshot: dict[str, Any]
    pheromone_trace: list[dict[str, Any]]
    stop_signals: list[dict[str, Any]]
    constraint_signals: list[dict[str, Any]]
    quorum_trace: dict[str, Any]
    agent_allocation_trace: list[dict[str, Any]]
    active_committee_member_specs: list[dict[str, Any]]
    agent_signal_diagnostics: list[dict[str, Any]]
    agent_signal_verification_trace: list[dict[str, Any]]
    swarm_execution_loop: dict[str, Any]
    swarm_protocol_trace: list[dict[str, Any]]
    swarm_governance_trace: list[dict[str, Any]]
    governance_results: list[dict[str, Any]]
    enforcement_bus_report: dict[str, Any]
    encounter_rate_report: dict[str, Any]
    bottleneck_report: dict[str, Any]
    arousal_report: dict[str, Any]
    lane_assignment_report: dict[str, Any]
    social_immunity_report: dict[str, Any]
    policing_trace: dict[str, Any]
    receiver_normalizer_report: dict[str, Any]
    evidence_steward_report: dict[str, Any]
    tool_health_sentinel_report: dict[str, Any]
    capability_sandbox_auditor_report: dict[str, Any]
    outcome_memory_steward_report: dict[str, Any]
    quorum_marshal_report: dict[str, Any]
    homeostasis_report: dict[str, Any]
    maturity_report: dict[str, Any]
    independence_report: dict[str, Any]
    swarm_controller_report: dict[str, Any]
    signal_resolution_report: dict[str, Any]
    artifact_cue_report: dict[str, Any]
    trust_badges: list[dict[str, Any]]
    patroller_report: dict[str, Any]
    workflow_routing: dict[str, Any]
    swarm_metrics: dict[str, Any]
    evidence_graph: dict[str, Any]
    tool_manifest: list[dict[str, Any]]
    review: dict[str, Any]
    draft_final: str
    final: str
    agent_metrics: list[dict[str, Any]]
    run_status: str
    degraded_reasons: list[str]
    error: str
