from __future__ import annotations

from typing import Any


GOVERNANCE_ACTORS = [
    {
        "key": "swarm_scheduler_agent",
        "caste": "traffic_scheduler",
        "report_key": "swarm_controller_report",
        "deterministic": True,
        "can_block": False,
    },
    {
        "key": "receiver_normalizer_agent",
        "caste": "receiver",
        "report_key": "receiver_normalizer_report",
        "deterministic": True,
        "can_block": False,
    },
    {
        "key": "evidence_steward_agent",
        "caste": "evidence_steward",
        "report_key": "evidence_steward_report",
        "deterministic": True,
        "can_block": False,
    },
    {
        "key": "quorum_marshal_agent",
        "caste": "quorum_governance",
        "report_key": "quorum_marshal_report",
        "deterministic": True,
        "can_block": True,
    },
    {
        "key": "social_immunity_agent",
        "caste": "social_immunity",
        "report_key": "social_immunity_report",
        "deterministic": True,
        "can_block": True,
    },
    {
        "key": "protocol_police_agent",
        "caste": "worker_policing",
        "report_key": "policing_trace",
        "deterministic": True,
        "can_block": True,
    },
    {
        "key": "tool_health_sentinel_agent",
        "caste": "tool_health",
        "report_key": "tool_health_sentinel_report",
        "deterministic": True,
        "can_block": True,
    },
    {
        "key": "outcome_memory_steward_agent",
        "caste": "outcome_learning",
        "report_key": "outcome_memory_steward_report",
        "deterministic": True,
        "can_block": False,
    },
    {
        "key": "capability_sandbox_auditor_agent",
        "caste": "capability_trust",
        "report_key": "capability_sandbox_auditor_report",
        "deterministic": True,
        "can_block": True,
    },
    {
        "key": "independent_scout_agent",
        "caste": "independent_scout",
        "report_key": "independence_report",
        "deterministic": True,
        "can_block": False,
    },
]


def build_governance_actor_trace(state: dict[str, Any]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for actor in GOVERNANCE_ACTORS:
        report_key = actor["report_key"]
        report = state.get(report_key) if isinstance(state.get(report_key), dict) else {}
        status = str(report.get("status") or "not_run")
        trace.append(
            {
                "agent": actor["key"],
                "caste": actor["caste"],
                "deterministic": actor["deterministic"],
                "can_block": actor["can_block"],
                "report_key": report_key,
                "status": status,
                "actions": extract_actions(report),
                "summary": summary_for(report_key, report, status),
            }
        )
    return trace


def extract_actions(report: dict[str, Any]) -> list[Any]:
    for key in ("actions", "recommendations", "findings", "violations", "blocked_candidates"):
        value = report.get(key)
        if isinstance(value, list):
            return value[:8]
    return []


def summary_for(report_key: str, report: dict[str, Any], status: str) -> str:
    if not report:
        return f"{report_key} has not run in this phase."
    if report_key == "receiver_normalizer_report":
        return f"normalized {report.get('claim_count', 0)} claims and {report.get('risk_count', 0)} risks"
    if report_key == "evidence_steward_report":
        return f"linked {report.get('linked_claim_count', 0)} claims, unsupported {report.get('unsupported_claim_count', 0)}"
    if report_key == "tool_health_sentinel_report":
        return f"{report.get('attempts', 0)} attempts, failure rate {report.get('failure_rate', 0)}"
    if report_key == "quorum_marshal_report":
        committed = report.get("committed_candidate") if isinstance(report.get("committed_candidate"), dict) else {}
        return f"committed candidate: {committed.get('label') or 'pending'}"
    return status
