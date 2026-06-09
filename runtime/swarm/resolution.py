from __future__ import annotations

from typing import Any

from runtime.swarm.action_policy import source_policy_blocks_tool
from runtime.swarm.data_gate_permissions import (
    data_gate_conclusion_permission,
    is_publication_target,
    publication_conclusion_permission_target,
)
from runtime.swarm.lifecycle import SignalLifecycleState, is_active_blocker
from runtime.swarm.legacy_tool_policy import legacy_web_research_tool_actions
from runtime.swarm.stop_policy import stop_signal_policy_from_state, target_aliases_from_state
from runtime.swarm.target_registry import (
    TARGET_DATA_GATE,
    canonical_target,
)


def apply_stop_signal_resolution(state: dict[str, Any]) -> dict[str, Any]:
    """Resolve blocking stop-signals when deterministic gates clear them.

    This keeps lifecycle semantics centralized: old stop-signals can remain in
    the trace for audit, but resolved/rejected signals stop influencing quorum,
    writer guardrails, and tool policy.
    """

    signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    if not signals:
        return {"signal_resolution_report": _empty_report()}

    resolved_signals: list[dict[str, Any]] = []
    report = _empty_report()
    for index, signal in enumerate(signals):
        if not isinstance(signal, dict):
            continue
        updated = dict(signal)
        reason = resolution_reason(state, signal)
        if reason and is_active_blocker(signal):
            updated["blocking"] = False
            updated["lifecycle_state"] = SignalLifecycleState.RESOLVED.value
            updated["resolution_reason"] = reason
            metadata = updated.get("metadata") if isinstance(updated.get("metadata"), dict) else {}
            updated["metadata"] = {**metadata, "resolved_by": "stop_signal_resolution", "resolution_reason": reason}
            report["resolved"].append(
                {
                    "id": updated.get("id") or f"signal_{index}",
                    "target": canonical_target(updated.get("target")),
                    "reason": reason,
                }
            )
        elif is_active_blocker(signal):
            report["open_blockers"].append(
                {
                    "id": updated.get("id") or f"signal_{index}",
                    "target": canonical_target(updated.get("target")),
                    "reason": str(updated.get("content") or "blocking stop-signal remains open"),
                }
            )
        resolved_signals.append(updated)

    report["status"] = "resolved_some" if report["resolved"] else "open_blockers" if report["open_blockers"] else "clear"
    return {"stop_signals": resolved_signals, "signal_resolution_report": report}


def resolution_reason(state: dict[str, Any], signal: dict[str, Any]) -> str | None:
    target = canonical_target(signal.get("target"))
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    review = state.get("review") if isinstance(state.get("review"), dict) else {}
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}

    if publication_review_rejects_resolution(target=target, review=review):
        return None

    policy_applies, policy_reason = policy_resolution_decision(state, signal, target=target)
    if policy_applies:
        return policy_reason

    permission = data_gate_conclusion_permission(data_gate, target)
    if permission is True:
        return f"Data Gate conclusion permission now allows {target}."
    if target == TARGET_DATA_GATE:
        publication_target = publication_conclusion_permission_target(data_gate)
        publication_allowed = data_gate_conclusion_permission(data_gate, publication_target)
        if publication_allowed is True:
            return f"Data Gate and review now allow {publication_target}."
    if source_policy_resolution_target(signal, target) and (
        metadata.get("allow_web_search") is True or not source_policy_blocks_tool(state, target)
    ):
        return "Current source policy allows this tool."
    return None


def publication_review_rejects_resolution(*, target: str, review: dict[str, Any]) -> bool:
    review_status = str(review.get("status") or "").upper()
    if review_status not in {"REJECT_CONDITIONAL", "REJECT_FATAL"}:
        return False
    return is_publication_target(target) or target == TARGET_DATA_GATE


def source_policy_resolution_target(signal: dict[str, Any], target: str) -> bool:
    if not target.startswith("tool:"):
        return False
    metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    if metadata.get("source_policy_blocked_tool_targets"):
        return True
    if str(signal.get("source_module") or "") == "source_policy":
        return True
    return target in legacy_web_research_tool_actions()


def _empty_report() -> dict[str, Any]:
    return {"status": "clear", "resolved": [], "open_blockers": []}


def policy_resolution_reason(state: dict[str, Any], signal: dict[str, Any], *, target: str) -> str | None:
    applies, reason = policy_resolution_decision(state, signal, target=target)
    return reason if applies else None


def policy_resolution_decision(state: dict[str, Any], signal: dict[str, Any], *, target: str) -> tuple[bool, str | None]:
    policy = stop_signal_policy_from_state(state)
    resolution_policy = policy.get("resolution_policy") if isinstance(policy.get("resolution_policy"), dict) else {}
    aliases = target_aliases_from_state(state, policy)
    for rule in resolution_rules(resolution_policy):
        raw_targets = string_list(rule.get("targets") or rule.get("target"))
        rule_targets = {canonical_target_with_aliases(item, aliases) for item in raw_targets}
        if rule_targets and target not in rule_targets:
            continue
        if not resolution_condition_met(state, rule.get("resolution_condition") or rule.get("condition") or rule.get("resolved_when")):
            return True, None
        allowed_authorities = string_list(
            rule.get("resolution_authority")
            or rule.get("allowed_authorities")
            or rule.get("authorities")
        )
        authority = resolution_authority(state, signal)
        if not authority or authority not in allowed_authorities:
            return True, None
        return True, str(rule.get("reason") or f"{authority} satisfied declared resolution policy.")
    return False, None


def canonical_target_with_aliases(value: Any, aliases: dict[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return canonical_target(text)
    return aliases.get(text) or aliases.get(text.lower()) or canonical_target(text)


def resolution_rules(policy: dict[str, Any]) -> list[dict[str, Any]]:
    raw_rules = policy.get("rules") if isinstance(policy.get("rules"), list) else []
    if raw_rules:
        return [dict(rule) for rule in raw_rules if isinstance(rule, dict)]
    return [policy] if policy else []


def resolution_condition_met(state: dict[str, Any], condition: Any) -> bool:
    if not isinstance(condition, dict):
        return False
    if isinstance(condition.get("all_of"), list):
        return all(resolution_condition_met(state, item) for item in condition["all_of"])
    if isinstance(condition.get("any_of"), list):
        return any(resolution_condition_met(state, item) for item in condition["any_of"])
    path = str(condition.get("path") or condition.get("state_path") or "").strip()
    if not path:
        return False
    actual = value_at_path(state, path)
    expected = condition.get("equals", True)
    return actual == expected


def value_at_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def resolution_authority(state: dict[str, Any], signal: dict[str, Any]) -> str:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    signal_metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    return str(
        state.get("resolution_authority")
        or metadata.get("resolution_authority")
        or signal.get("resolution_authority")
        or signal_metadata.get("resolution_authority")
        or ""
    ).strip()


def string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
