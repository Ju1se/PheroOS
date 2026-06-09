from __future__ import annotations

from typing import Any


def runtime_agent_decision(state: dict[str, Any]) -> dict[str, Any]:
    decision = state.get("agent_decision")
    if isinstance(decision, dict) and decision:
        return decision
    return legacy_committee_decision(state)


def runtime_agent_decision_source(state: dict[str, Any]) -> str:
    decision = state.get("agent_decision")
    if isinstance(decision, dict) and decision:
        return "agent_decision"
    legacy_decision = legacy_committee_decision(state)
    return "legacy_committee_decision" if legacy_decision else "none"


def runtime_agent_decision_artifacts(state: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    decision = state.get("agent_decision")
    if isinstance(decision, dict) and decision:
        artifacts.append({"artifact_id": "agent_decision", "source": "agent_decision", "value": decision})
    legacy_decision = legacy_committee_decision(state)
    if legacy_decision:
        artifacts.append(
            {
                "artifact_id": "legacy_agent_decision",
                "source": "legacy_agent_decision",
                "value": legacy_decision,
            }
        )
    return artifacts


def state_with_agent_decision(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {"agent_decision": decision}
    if "committee_decision" in state:
        updates["committee_decision"] = decision
    return {**state, **updates}


def has_agent_decision_value(decision: dict[str, Any]) -> bool:
    return bool(decision.get("final_decision") or decision.get("decision"))


def legacy_committee_decision(state: dict[str, Any]) -> dict[str, Any]:
    decision = state.get("committee_decision")
    return decision if isinstance(decision, dict) else {}
