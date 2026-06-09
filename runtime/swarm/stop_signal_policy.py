from __future__ import annotations

from typing import Any

from runtime.swarm.action_policy import related_actions_for_action, source_policy_blocking_signal
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.stop_policy import action_blocked_by_stop_policy, canonical_action


def blocking_signal_for_action(state: dict[str, Any], action: Any) -> dict[str, Any] | None:
    policy_signal = action_blocked_by_stop_policy(state, str(action or ""))
    if policy_signal is not None:
        return policy_signal

    source_policy_signal = source_policy_blocking_signal(state, action)
    if source_policy_signal is not None:
        return source_policy_signal

    normalized_action = canonical_action(action)
    if not normalized_action:
        return None
    related_actions = related_actions_for_action(normalized_action)
    for signal in active_blocking_signals(state):
        signal_action = canonical_action(signal.get("target"))
        if signal_action == normalized_action:
            return signal
        if signal_action in related_actions or normalized_action in related_actions_for_action(signal_action):
            return signal
    return None


def active_blocking_signals(state: dict[str, Any]) -> list[dict[str, Any]]:
    signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    return [signal for signal in signals if isinstance(signal, dict) and is_active_blocker(signal)]
