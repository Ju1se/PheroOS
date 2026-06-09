from __future__ import annotations

from typing import Any

from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.target_registry import canonical_target, target_kind

UNTRUSTED_BLOCKING_AUTHORITY_DIAGNOSTIC = "untrusted_blocking_authority"
SOURCE_ATTRIBUTED_STOP_POLICY_FIELDS = ("rules", "action_markers", "action_cues")


def action_blocked_by_stop_policy(state: dict[str, Any], action: str) -> dict[str, Any] | None:
    """Return the active stop-signal that blocks an action under capability policy.

    Direct stop-signals still work (`target=tool:web_search` blocks
    `tool:web_search`). Capability-declared policy rules make this generic:
    a capability can say that a blocker on `gate:research_evidence_gate` blocks
    `writer:confirmed_claim`, or that `decision:compliance_approval` blocks
    `tool:email_send`.
    """

    policy = stop_signal_policy_from_state(state)
    aliases = target_aliases_from_state(state, policy)
    normalized_action = canonical_action(action, aliases=aliases)
    if not normalized_action:
        return None
    signals = active_blocking_signals(state)
    if not signals:
        return None

    for signal in signals:
        if canonical_action(signal.get("target"), aliases=aliases) == normalized_action:
            return signal

    for rule in stop_policy_rules(policy):
        actions = {canonical_action(item, aliases=aliases) for item in rule.get("blocked_actions", [])}
        if normalized_action not in actions:
            continue
        trigger_targets = {canonical_action(item, aliases=aliases) for item in rule.get("trigger_targets", []) if str(item).strip()}
        for signal in signals:
            signal_target = canonical_action(signal.get("target"), aliases=aliases)
            if trigger_targets:
                if signal_target in trigger_targets:
                    return signal
            elif action_related_to_signal(normalized_action, signal_target):
                return signal
    return None


def stop_signal_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("stop_signal_policy") if isinstance(swarm_plan.get("stop_signal_policy"), dict) else {}
    return sanitize_stop_signal_policy(policy, validation_diagnostics_from_state(state, metadata, os_plan, swarm_plan))


def sanitize_stop_signal_policy(policy: dict[str, Any], diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    unsafe_sources = untrusted_blocking_policy_sources(diagnostics)
    if not unsafe_sources:
        return policy
    sanitized = dict(policy)
    changed = False

    for key in SOURCE_ATTRIBUTED_STOP_POLICY_FIELDS:
        filtered = filter_source_attributed_items(sanitized.get(key), unsafe_sources)
        if filtered is not None:
            sanitized[key] = filtered
            changed = True

    resolution_policy = sanitized.get("resolution_policy")
    if isinstance(resolution_policy, dict):
        filtered_rules = filter_source_attributed_items(resolution_policy.get("rules"), unsafe_sources)
        if filtered_rules is not None:
            sanitized["resolution_policy"] = {**resolution_policy, "rules": filtered_rules}
            changed = True

    top_level_sources = set(source_list(sanitized.get("top_level_blocking_policy_sources")))
    if top_level_sources.intersection(unsafe_sources):
        sanitized = strip_top_level_hard_blocking_fields(sanitized)
        changed = True

    policy_sources = source_list(sanitized.get("policy_sources"))
    all_sources_unsafe = bool(policy_sources) and all(source in unsafe_sources for source in policy_sources)
    if all_sources_unsafe:
        sanitized = strip_top_level_hard_blocking_fields(sanitized)
        changed = True

    if not changed:
        return policy
    return {
        **sanitized,
        "policy_sanitized": True,
        "blocked_policy_sources": sorted(unsafe_sources),
    }


def validation_diagnostics_from_state(
    state: dict[str, Any],
    metadata: dict[str, Any],
    os_plan: dict[str, Any],
    swarm_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for source in (swarm_plan, os_plan, metadata, state):
        items = source.get("validation_diagnostics") if isinstance(source, dict) else None
        if not isinstance(items, list):
            continue
        diagnostics.extend(item for item in items if isinstance(item, dict))
    return diagnostics


def untrusted_blocking_policy_sources(diagnostics: list[dict[str, Any]]) -> set[str]:
    sources: set[str] = set()
    for diagnostic in diagnostics:
        if str(diagnostic.get("code") or "").strip() != UNTRUSTED_BLOCKING_AUTHORITY_DIAGNOSTIC:
            continue
        capability_id = str(diagnostic.get("capability_id") or "").strip()
        if capability_id:
            sources.add(capability_id)
    return sources


def filter_source_attributed_items(value: Any, unsafe_sources: set[str]) -> list[Any] | None:
    if not isinstance(value, list):
        return None
    filtered = []
    changed = False
    for item in value:
        source = str(item.get("capability_id") or "").strip() if isinstance(item, dict) else ""
        if source and source in unsafe_sources:
            changed = True
            continue
        filtered.append(item)
    return filtered if changed else None


def strip_top_level_hard_blocking_fields(policy: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(policy)
    for key in ("blocked_actions", "blocked_targets", "trigger_targets"):
        if key in stripped:
            stripped[key] = []
    for key in ("action_effects", "aliases", "resolution_policy"):
        if key in stripped:
            stripped[key] = {}
    for key in ("blocking_authority_required", "authority_level_required"):
        if key in stripped:
            stripped[key] = 0
    return stripped


def source_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def target_aliases_from_state(state: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, str]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    aliases: dict[str, str] = {}
    for source in (
        swarm_plan.get("target_aliases") if isinstance(swarm_plan.get("target_aliases"), dict) else {},
        (policy or {}).get("aliases") if isinstance((policy or {}).get("aliases"), dict) else {},
    ):
        for alias, target in source.items():
            alias_text = str(alias).strip()
            target_text = str(target).strip()
            if not alias_text or not target_text:
                continue
            aliases[alias_text] = canonical_target(target_text)
            aliases[alias_text.lower()] = canonical_target(target_text)
    return aliases


def stop_policy_rules(policy: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    top_level_rule_generated = False
    for item in policy.get("rules") or []:
        if not isinstance(item, dict):
            continue
        actions = string_list(item.get("blocked_actions") or item.get("actions"))
        if not actions:
            continue
        top_level_rule_generated = top_level_rule_generated or bool(item.get("generated_from_top_level"))
        rules.append(
            {
                "id": str(item.get("id") or "").strip() or None,
                "trigger_targets": string_list(item.get("trigger_targets") or item.get("targets")),
                "blocked_actions": actions,
            }
        )
    top_level_actions = string_list(policy.get("blocked_actions"))
    if top_level_actions and not top_level_rule_generated:
        rules.append(
            {
                "id": "default",
                "trigger_targets": string_list(policy.get("trigger_targets")),
                "blocked_actions": top_level_actions,
            }
        )
    return rules


def active_blocking_signals(state: dict[str, Any]) -> list[dict[str, Any]]:
    signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    return [signal for signal in signals if isinstance(signal, dict) and is_active_blocker(signal)]


def canonical_action(value: Any, *, aliases: dict[str, str] | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    aliases = aliases or {}
    if text in aliases:
        return aliases[text]
    if text.lower() in aliases:
        return aliases[text.lower()]
    if ":" not in text:
        return canonical_target(text)
    prefix, tail = text.split(":", 1)
    prefix = prefix.strip().lower().replace("-", "_")
    tail = "_".join(tail.strip().lower().replace("-", "_").split())
    if prefix == "tool":
        return canonical_target(f"tool:{tail}")
    return f"{prefix}:{tail}"


def action_related_to_signal(action: str, signal_target: str) -> bool:
    action_tail = action.rsplit(":", 1)[-1]
    target_tail = canonical_target(signal_target).rsplit(":", 1)[-1]
    if action_tail == target_tail:
        return True
    if action_tail in target_tail or target_tail in action_tail:
        return True
    if action.startswith(("writer:", "final_judge:")) and target_kind(signal_target) in {"gate", "decision", "constraint"}:
        return shared_word(action_tail, target_tail)
    return False


def shared_word(left: str, right: str) -> bool:
    left_words = {word for word in left.replace("-", "_").split("_") if len(word) > 3}
    right_words = {word for word in right.replace("-", "_").split("_") if len(word) > 3}
    return bool(left_words.intersection(right_words))


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
