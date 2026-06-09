from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GovernanceContract:
    actor: str
    report_key: str
    input_contract: list[str]
    output_contract: list[str]
    enforcement_targets: list[str]
    can_block: bool = False
    trace_event: str = "governance.actor.completed"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "report_key": self.report_key,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "enforcement_targets": self.enforcement_targets,
            "can_block": self.can_block,
            "trace_event": self.trace_event,
            "description": self.description,
        }


GOVERNANCE_CONTRACTS: dict[str, GovernanceContract] = {
    "swarm_scheduler_agent": GovernanceContract(
        actor="swarm_scheduler_agent",
        report_key="swarm_controller_report",
        input_contract=["protocol_reports", "member_specs"],
        output_contract=["agent_overrides", "writer_policy", "quorum_policy"],
        enforcement_targets=["committee:scheduling", "writer:constraints", "quorum:policy"],
        description="Converts swarm pressure reports into runtime scheduling and writer/quorum policy.",
    ),
    "receiver_normalizer_agent": GovernanceContract(
        actor="receiver_normalizer_agent",
        report_key="receiver_normalizer_report",
        input_contract=["agent_outputs"],
        output_contract=["claims", "risks", "missing_data", "candidates"],
        enforcement_targets=["evidence_graph:claim_contract"],
        description="Normalizes agent prose into structured claim/evidence/risk objects.",
    ),
    "evidence_steward_agent": GovernanceContract(
        actor="evidence_steward_agent",
        report_key="evidence_steward_report",
        input_contract=["receiver_normalizer_report", "metric_registry", "data_gate"],
        output_contract=["linked_claims", "unsupported_claims", "blocked_claims", "writer_constraints"],
        enforcement_targets=["writer:claims", "final_judge:claims", "decision:blocked_output"],
        description="Links claims to deterministic evidence and blocks unsupported or Data-Gate-forbidden claims.",
    ),
    "quorum_marshal_agent": GovernanceContract(
        actor="quorum_marshal_agent",
        report_key="quorum_marshal_report",
        input_contract=["quorum_trace", "stop_signals", "evidence_graph"],
        output_contract=["committed_candidate", "why_committed", "blocked_candidates"],
        enforcement_targets=["quorum:committed_candidate", "writer:decision", "final_judge:decision"],
        can_block=True,
        description="Owns committed-candidate authority; CIO may propose, but Quorum Marshal commits.",
    ),
    "social_immunity_agent": GovernanceContract(
        actor="social_immunity_agent",
        report_key="social_immunity_report",
        input_contract=["execution_log", "research_brief", "wrds_result", "agent_outputs"],
        output_contract=["contaminants", "quarantine_count", "recommendation"],
        enforcement_targets=["artifact:quarantine", "evidence_graph:artifact_intake", "writer:artifact_use"],
        can_block=True,
        description="Quarantines prompt-injection, secret-like, or contaminated artifacts.",
    ),
    "protocol_police_agent": GovernanceContract(
        actor="protocol_police_agent",
        report_key="policing_trace",
        input_contract=["agent_signal_diagnostics", "final", "execution_log", "quorum_trace"],
        output_contract=["violations", "warnings", "policing_signals"],
        enforcement_targets=["decision:blocked_output", "tool:policy", "agent:reliability"],
        can_block=True,
        description="Turns protocol violations into reliability penalties and blocking stop-signals.",
    ),
    "tool_health_sentinel_agent": GovernanceContract(
        actor="tool_health_sentinel_agent",
        report_key="tool_health_sentinel_report",
        input_contract=["execution_log", "wrds_result", "agent_metrics"],
        output_contract=["failure_rate", "tools", "recommendation"],
        enforcement_targets=["tool:routes", "model:routes", "writer:confidence"],
        can_block=True,
        description="Monitors tool/model route reliability and blocks or degrades failing routes.",
    ),
    "outcome_memory_steward_agent": GovernanceContract(
        actor="outcome_memory_steward_agent",
        report_key="outcome_memory_steward_report",
        input_contract=["agent_outputs", "agent_signal_diagnostics", "policing_trace"],
        output_contract=["profile_updates", "memory_boundary"],
        enforcement_targets=["agent_profiles:process_reliability"],
        description="Stores process-only agent reliability updates, never company-specific conclusions.",
    ),
    "capability_sandbox_auditor_agent": GovernanceContract(
        actor="capability_sandbox_auditor_agent",
        report_key="capability_sandbox_auditor_report",
        input_contract=["enabled_capabilities", "capability_index"],
        output_contract=["findings", "sandbox_policy"],
        enforcement_targets=["capability:sandbox", "permission:capability", "signal:authority"],
        can_block=True,
        description="Blocks dangerous or untrusted capability permissions and signal authority.",
    ),
    "independent_scout_agent": GovernanceContract(
        actor="independent_scout_agent",
        report_key="independence_report",
        input_contract=["agent_outputs", "quorum_trace", "swarm_controller_report"],
        output_contract=["source_diversity", "independence_gate", "adjusted_quorum"],
        enforcement_targets=["quorum:independence"],
        description="Prevents correlated support from masquerading as independent quorum.",
    ),
}


def governance_contract(actor: str) -> GovernanceContract | None:
    return GOVERNANCE_CONTRACTS.get(str(actor))


def governance_contract_catalog() -> list[dict[str, Any]]:
    return [contract.to_dict() for contract in GOVERNANCE_CONTRACTS.values()]
