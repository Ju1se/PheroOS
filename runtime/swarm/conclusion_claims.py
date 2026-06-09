from __future__ import annotations

from typing import Any

from runtime.swarm.data_gate_permissions import (
    blocked_conclusion_permissions,
    data_gate_conclusion_permission,
    writer_action_for_conclusion_target,
)
from runtime.swarm.legacy_data_gate_permissions import legacy_formal_valuation_conclusion_target
from runtime.swarm.legacy_output_phrases import legacy_formal_valuation_present
from runtime.swarm.stop_policy import stop_signal_policy_from_state
from runtime.swarm.target_registry import canonical_target
from runtime.writer_guardrails import declared_writer_actions, stop_policy_action_markers


def blocked_conclusion_target_for_text(
    content: str,
    state: dict[str, Any],
    data_gate: dict[str, Any] | None = None,
) -> str | None:
    match = blocked_conclusion_match_for_text(content, state, data_gate)
    return str(match.get("target")) if match else None


def blocked_conclusion_match_for_text(
    content: str,
    state: dict[str, Any],
    data_gate: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    gate = data_gate if isinstance(data_gate, dict) else state.get("data_gate")
    gate = gate if isinstance(gate, dict) else {}
    if not gate:
        return None

    policy = stop_signal_policy_from_state(state)
    actions = set(declared_writer_actions(content, policy))
    for permission in blocked_conclusion_permissions(gate):
        target = canonical_target(permission.get("canonical_target") or permission.get("target") or "")
        writer_action = writer_action_for_conclusion_target(target)
        if writer_action in actions:
            return {
                "target": target,
                "source": "declared_stop_signal_action_marker",
                "writer_action": writer_action,
            }

    if stop_policy_action_markers(policy):
        return None
    legacy_target = legacy_formal_valuation_conclusion_target()
    if data_gate_conclusion_permission(gate, legacy_target) is False and legacy_formal_valuation_present(content):
        return {
            "target": legacy_target,
            "source": "legacy_formal_valuation_phrase_fallback",
            "writer_action": writer_action_for_conclusion_target(legacy_target),
        }
    return None
