from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.swarm.protocol_loader import load_protocol_from_capability
from runtime.swarm.protocol_manifest import PROTOCOL_SCHEMA_VERSION
from runtime.swarm.target_registry import canonical_target, target_kind


def capability_protocol_bundle(capabilities: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Extract swarm protocol declarations from capability manifests.

    Capability manifests are the extension boundary. This helper keeps OS Kernel
    planning generic by turning manifest-declared targets, recovery protocols,
    quorum policies, stop-signal policies, and candidate policies into a single
    protocol bundle.
    """

    protocols = []
    targets: list[dict[str, Any]] = []
    recovery_protocols: list[dict[str, Any]] = []
    candidate_policies: list[dict[str, Any]] = []
    quorum_policies: list[dict[str, Any]] = []
    stop_signal_policies: list[dict[str, Any]] = []
    evidence_policies: list[dict[str, Any]] = []
    tool_policies: list[dict[str, Any]] = []
    output_policies: list[dict[str, Any]] = []
    agent_selection_policies: list[dict[str, Any]] = []
    swarm_loop_policies: list[dict[str, Any]] = []
    workflow_entrypoints: list[dict[str, Any]] = []
    target_aliases: dict[str, str] = {}
    generated_legacy_protocol_count = 0
    validation_diagnostics: list[dict[str, Any]] = []

    for capability in capabilities or []:
        if not isinstance(capability, dict):
            continue
        capability_id = str(capability.get("id") or "").strip()
        entrypoints = capability.get("entrypoints") if isinstance(capability.get("entrypoints"), dict) else {}
        loaded = load_protocol_from_capability(capability)
        loaded_payload = loaded.to_dict()
        targets_payload = loaded_payload.get("targets") if isinstance(loaded_payload.get("targets"), list) else []
        recovery_payload = loaded_payload.get("recovery_protocols") if isinstance(loaded_payload.get("recovery_protocols"), list) else []
        candidates_payload = loaded_payload.get("candidates") if isinstance(loaded_payload.get("candidates"), list) else []
        protocol = {
            "capability_id": capability_id,
            "schema_version": loaded_payload.get("schema_version"),
            "source": loaded.source,
            "generated_legacy_protocol": loaded.generated_legacy_protocol,
            "validation_diagnostics": loaded.validation_diagnostics,
            "intents": loaded_payload.get("intents", []),
            "targets": normalize_protocol_targets(targets_payload, capability_id=capability_id),
            "recovery_protocols": normalize_named_protocols(recovery_payload, capability_id=capability_id),
            "candidate_policy": candidate_policy_from_protocol(
                capability,
                candidates_payload,
                capability_id=capability_id,
            ),
            "quorum_policy": normalize_policy(loaded_payload.get("quorum_policy"), capability_id=capability_id),
            "stop_signal_policy": normalize_policy(loaded_payload.get("stop_signal_policy"), capability_id=capability_id),
            "evidence_policy": normalize_policy(loaded_payload.get("evidence_policy"), capability_id=capability_id),
            "tool_policy": normalize_policy(loaded_payload.get("tool_policy"), capability_id=capability_id),
            "output_policy": normalize_policy(loaded_payload.get("output_policy"), capability_id=capability_id),
            "agent_selection_policy": normalize_policy(loaded_payload.get("agent_selection_policy"), capability_id=capability_id),
            "swarm_loop_policy": normalize_policy(loaded_payload.get("swarm_loop_policy"), capability_id=capability_id),
            "workflow_entrypoint": str(entrypoints.get("workflow") or "").strip() or None,
        }
        if protocol_has_runtime_surface(capability, protocol):
            protocols.append(protocol)
            if loaded.generated_legacy_protocol:
                generated_legacy_protocol_count += 1
            validation_diagnostics.extend(
                {**item, "capability_id": capability_id}
                for item in loaded.validation_diagnostics
                if isinstance(item, dict)
            )
        targets.extend(protocol["targets"])
        target_aliases.update(target_aliases_from_protocol_targets(protocol["targets"]))
        recovery_protocols.extend(protocol["recovery_protocols"])
        if protocol["candidate_policy"]:
            candidate_policies.append(protocol["candidate_policy"])
        if protocol["quorum_policy"]:
            quorum_policies.append(protocol["quorum_policy"])
        if protocol["stop_signal_policy"]:
            stop_signal_policies.append(protocol["stop_signal_policy"])
        if protocol["evidence_policy"]:
            evidence_policies.append(protocol["evidence_policy"])
        if protocol["tool_policy"]:
            tool_policies.append(protocol["tool_policy"])
        if protocol["output_policy"]:
            output_policies.append(protocol["output_policy"])
        if protocol["agent_selection_policy"]:
            agent_selection_policies.append(protocol["agent_selection_policy"])
        if protocol["swarm_loop_policy"]:
            swarm_loop_policies.append(protocol["swarm_loop_policy"])
        if protocol["workflow_entrypoint"]:
            workflow_entrypoints.append(
                {
                    "capability_id": capability_id,
                    "workflow": protocol["workflow_entrypoint"],
                }
            )

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "protocol_count": len(protocols),
        "protocols": protocols,
        "targets": dedupe_targets(targets),
        "recovery_protocols": recovery_protocols,
        "candidate_policy": merge_policies(candidate_policies),
        "quorum_policy": merge_policies(quorum_policies),
        "stop_signal_policy": merge_policies(stop_signal_policies),
        "evidence_policy": merge_policies(evidence_policies),
        "tool_policy": merge_policies(tool_policies),
        "output_policy": merge_policies(output_policies),
        "agent_selection_policy": merge_policies(agent_selection_policies),
        "swarm_loop_policy": merge_policies(swarm_loop_policies),
        "workflow_entrypoints": workflow_entrypoints,
        "target_aliases": target_aliases,
        "protocol_source": "capability_manifest" if protocols else "intent_default",
        "generated_legacy_protocol_count": generated_legacy_protocol_count,
        "validation_diagnostics": validation_diagnostics,
    }


def protocol_has_runtime_surface(capability: dict[str, Any], protocol: dict[str, Any]) -> bool:
    if any(capability.get(key) for key in ("protocol", "pheroos_protocol", "pheroos")):
        return True
    if adjacent_protocol_file_exists(capability):
        return True
    swarm = capability.get("swarm") if isinstance(capability.get("swarm"), dict) else {}
    if swarm:
        return True
    return any(
        protocol.get(key)
        for key in (
            "targets",
            "recovery_protocols",
            "candidate_policy",
            "quorum_policy",
            "stop_signal_policy",
            "evidence_policy",
            "tool_policy",
            "output_policy",
            "agent_selection_policy",
            "swarm_loop_policy",
            "workflow_entrypoint",
        )
    )


def adjacent_protocol_file_exists(capability: dict[str, Any]) -> bool:
    path_text = str(capability.get("path") or "").strip()
    return bool(path_text and (Path(path_text).parent / "pheroos_protocol.json").exists())


def candidate_policy_from_protocol(
    capability: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    capability_id: str,
) -> dict[str, Any]:
    swarm = capability.get("swarm") if isinstance(capability.get("swarm"), dict) else {}
    legacy = normalize_policy(swarm.get("candidate_policy"), capability_id=capability_id)
    if not candidates:
        return legacy
    declared = dedupe_candidates(candidates)
    return {
        **legacy,
        "candidates": declared,
    }


def target_aliases_from_protocol_targets(targets: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for target in targets:
        canonical = canonical_target(target.get("canonical_target") or target.get("target"))
        if canonical == "run":
            continue
        for alias in target.get("aliases") or []:
            alias_text = str(alias).strip()
            if alias_text:
                aliases[alias_text] = canonical
                aliases[alias_text.lower()] = canonical
    return aliases


def normalize_protocol_targets(value: Any, *, capability_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if isinstance(item, str):
            raw_target = item
            payload: dict[str, Any] = {}
        elif isinstance(item, dict):
            raw_target = str(item.get("target") or item.get("canonical_target") or "").strip()
            payload = dict(item)
        else:
            continue
        canonical = canonical_target(raw_target)
        if not raw_target or canonical == "run":
            continue
        demand = safe_float(payload.get("demand_strength"), 0.7)
        keywords = payload.get("keywords") if isinstance(payload.get("keywords"), list) else []
        aliases = payload.get("aliases") if isinstance(payload.get("aliases"), list) else []
        compatible_intents = payload.get("compatible_intents") if isinstance(payload.get("compatible_intents"), list) else []
        output.append(
            {
                "target": raw_target,
                "canonical_target": canonical,
                "target_kind": target_kind(canonical),
                "demand_strength": max(0.0, min(1.0, demand)),
                "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
                "keywords": [str(keyword).strip() for keyword in keywords if str(keyword).strip()],
                "compatible_intents": [str(intent).strip() for intent in compatible_intents if str(intent).strip()],
                "summary": str(payload.get("summary") or payload.get("content") or f"{capability_id} requires {canonical}."),
                "capability_id": capability_id,
            }
        )
    return output


def normalize_named_protocols(value: Any, *, capability_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if isinstance(item, str):
            payload = {"id": item}
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            continue
        protocol_id = str(payload.get("id") or payload.get("name") or payload.get("hook") or "").strip()
        if not protocol_id:
            continue
        targets = normalize_protocol_targets(payload.get("targets") or payload.get("target"), capability_id=capability_id)
        output.append(
            {
                **payload,
                "id": protocol_id,
                "capability_id": capability_id,
                "targets": targets,
            }
        )
    return output


SOURCE_ATTRIBUTED_POLICY_LIST_KEYS = {"rules", "action_markers", "action_cues"}


def normalize_policy(value: Any, *, capability_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    policy = {
        str(key): normalize_policy_value(str(key), item, capability_id=capability_id)
        for key, item in value.items()
    }
    policy = normalize_top_level_stop_policy_rule(policy, capability_id=capability_id)
    policy.setdefault("capability_id", capability_id)
    return policy


def normalize_top_level_stop_policy_rule(policy: dict[str, Any], *, capability_id: str) -> dict[str, Any]:
    blocked_actions = policy.get("blocked_actions")
    if not isinstance(blocked_actions, list) or not blocked_actions:
        return policy
    generated_rule = {
        "id": "default",
        "trigger_targets": policy_string_list(policy.get("trigger_targets")),
        "blocked_actions": list(blocked_actions),
        "capability_id": capability_id,
        "generated_from_top_level": True,
    }
    rules = policy.get("rules") if isinstance(policy.get("rules"), list) else []
    return {
        **policy,
        "rules": [*rules, generated_rule],
        "top_level_blocking_policy_sources": [capability_id] if capability_id else [],
    }


def normalize_policy_value(key: str, value: Any, *, capability_id: str) -> Any:
    if key in SOURCE_ATTRIBUTED_POLICY_LIST_KEYS and isinstance(value, list):
        return [source_attributed_policy_item(item, capability_id=capability_id) for item in value]
    if key == "resolution_policy" and isinstance(value, dict):
        policy = dict(value)
        rules = policy.get("rules")
        if isinstance(rules, list):
            policy["rules"] = [source_attributed_policy_item(item, capability_id=capability_id) for item in rules]
        elif policy:
            policy.setdefault("capability_id", capability_id)
        return policy
    return value


def source_attributed_policy_item(value: Any, *, capability_id: str) -> Any:
    if not isinstance(value, dict):
        return value
    item = dict(value)
    item.setdefault("capability_id", capability_id)
    return item


def policy_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def merge_policies(policies: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    sources = []
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        capability_id = str(policy.get("capability_id") or "").strip()
        if capability_id:
            sources.append(capability_id)
        for key, value in policy.items():
            if key == "capability_id":
                continue
            if key == "candidates" and isinstance(value, list):
                merged[key] = dedupe_candidates(list(merged.get(key) or []) + value)
            elif key not in merged:
                merged[key] = value
            elif isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = dedupe_scalars(merged[key] + value)
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
    if sources:
        merged["policy_sources"] = dedupe_scalars(sources)
    return merged


def dedupe_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for target in targets:
        canonical = canonical_target(target.get("canonical_target") or target.get("target"))
        if canonical in seen:
            continue
        seen.add(canonical)
        output.append({**target, "canonical_target": canonical, "target_kind": target_kind(canonical)})
    return output


def dedupe_candidates(candidates: list[Any]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for item in candidates:
        if isinstance(item, str):
            candidate = {"id": item, "label": item}
        elif isinstance(item, dict):
            candidate = dict(item)
        else:
            continue
        candidate_id = str(candidate.get("id") or candidate.get("label") or "").strip()
        if not candidate_id or candidate_id in seen:
            continue
        seen.add(candidate_id)
        output.append(candidate)
    return output


def dedupe_scalars(values: list[Any]) -> list[Any]:
    output = []
    seen = set()
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
