from __future__ import annotations

from typing import Any

from runtime.swarm.data_gate_permissions import is_publication_target
from runtime.swarm.legacy_output_phrases import (
    legacy_formal_valuation_stop_signal_fallback_reason,
    legacy_formal_valuation_stop_signal_report,
    legacy_formal_recommendation_present,
    legacy_formal_valuation_writer_action,
)
from runtime.swarm.legacy_target_aliases import legacy_formal_valuation_target
from runtime.swarm.target_registry import (
    TARGET_DATA_GATE,
    canonical_target,
)
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.stop_policy import stop_signal_policy_from_state
from runtime.swarm.stop_signal_policy import blocking_signal_for_action


def blocking_signals(state: dict[str, Any], *targets: str) -> list[dict[str, Any]]:
    target_set = {canonical_target(target) for target in targets if target}
    signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    return [
        signal
        for signal in signals
        if isinstance(signal, dict)
        and is_active_blocker(signal)
        and (not target_set or canonical_target(str(signal.get("target") or "")) in target_set)
    ]


def has_blocking_signal(state: dict[str, Any], *targets: str) -> bool:
    return bool(blocking_signals(state, *targets))


def report_publication_blocked(state: dict[str, Any]) -> bool:
    for signal in blocking_signals(state):
        target = canonical_target(signal.get("target"))
        if target == TARGET_DATA_GATE or is_publication_target(target):
            return True
    return False


def formal_valuation_blocked(state: dict[str, Any]) -> bool:
    return has_blocking_signal(state, legacy_formal_valuation_target())


def tool_blocked_by_signal(state: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    return blocking_signal_for_action(state, f"tool:{tool_name}")


def swarm_context_for_model(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "hard_constraints": state.get("constraint_signals", []),
        "stop_signals": state.get("stop_signals", []),
        "quorum_trace": state.get("quorum_trace", {}),
        "swarm_metrics": state.get("swarm_metrics", {}),
    }


def apply_swarm_report_policy(text: str, state: dict[str, Any]) -> str:
    declared_block = declared_writer_action_block(text, state)
    if declared_block:
        action, signal = declared_block
        return "\n".join(
            [
                "# Swarm Stop-Signal Guardrail Report",
                "",
                f"当前版本触发 `{action}`，但 Swarm Governance Layer 检测到该 writer action 已被 active stop-signal 阻止。",
                "",
                "## Blocking Signal",
                f"- {signal.get('content') or signal.get('target') or 'active stop-signal'}",
                "",
                "## Required Action",
                "请先解决对应 stop-signal 或 recovery protocol，再重新生成输出。Writer 只能表达未被 policy 阻断的内容。",
                "",
                "## Blocked Draft Preview",
                str(text or "")[:1200],
            ]
        )
    if not formal_valuation_blocked(state):
        return text
    if not formal_recommendation_present(text, state):
        return text
    signals = blocking_signals(state, legacy_formal_valuation_target())
    reasons = "\n".join(
        f"- {signal.get('content') or signal.get('target')}" for signal in signals
    ) or legacy_formal_valuation_stop_signal_fallback_reason()
    return legacy_formal_valuation_stop_signal_report(text, reasons=reasons)


def declared_writer_action_block(text: str, state: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    policy = stop_signal_policy_from_state(state)
    for marker in stop_policy_action_markers(policy):
        action = normalize_action(marker.get("action"))
        if not action.startswith("writer:"):
            continue
        if not action_marker_matches(text, {"action_markers": [marker]}, action):
            continue
        signal = blocking_signal_for_action(state, action)
        if signal:
            return action, signal
    return None


def formal_recommendation_present(text: str, state: dict[str, Any]) -> bool:
    policy = stop_signal_policy_from_state(state)
    if action_marker_matches(text, policy, legacy_formal_valuation_writer_action()):
        return True
    if stop_policy_action_markers(policy):
        return False
    return legacy_formal_recommendation_present(text)


def action_marker_matches(text: str, policy: dict[str, Any], action: str) -> bool:
    haystack = normalize_marker_text(text)
    if not haystack:
        return False
    action_key = normalize_action(action)
    for marker in stop_policy_action_markers(policy):
        if normalize_action(marker.get("action")) != action_key:
            continue
        phrases = marker.get("phrases") or marker.get("keywords") or marker.get("markers")
        for phrase in phrases if isinstance(phrases, list) else []:
            needle = normalize_marker_text(phrase)
            if needle and needle in haystack:
                return True
    return False


def stop_policy_action_markers(policy: dict[str, Any]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    sources = [policy]
    sources.extend(rule for rule in policy.get("rules") or [] if isinstance(rule, dict))
    for source in sources:
        for marker in source.get("action_markers") or source.get("action_cues") or []:
            if isinstance(marker, dict):
                markers.append(dict(marker))
    return markers


def normalize_action(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ":" not in text:
        return "_".join(text.lower().replace("-", "_").split())
    prefix, tail = text.split(":", 1)
    return f"{prefix.strip().lower().replace('-', '_')}:{'_'.join(tail.strip().lower().replace('-', '_').split())}"


def normalize_marker_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
