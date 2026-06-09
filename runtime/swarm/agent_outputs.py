from __future__ import annotations

from typing import Any


def runtime_agent_outputs(state: dict[str, Any]) -> dict[str, Any]:
    outputs = state.get("agent_outputs")
    if isinstance(outputs, dict) and outputs:
        return outputs
    return legacy_committee_outputs(state)


def runtime_agent_output_artifacts(state: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    outputs = state.get("agent_outputs")
    if isinstance(outputs, dict) and outputs:
        artifacts.append({"artifact_id": "agent_outputs", "source": "agent_outputs", "value": outputs})
    legacy_outputs = legacy_committee_outputs(state)
    if legacy_outputs:
        artifacts.append(
            {
                "artifact_id": "legacy_agent_outputs",
                "source": "legacy_agent_outputs",
                "value": legacy_outputs,
            }
        )
    return artifacts


def legacy_committee_outputs(state: dict[str, Any]) -> dict[str, Any]:
    outputs = state.get("committee_outputs")
    return outputs if isinstance(outputs, dict) else {}
