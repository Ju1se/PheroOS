from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime.swarm.legacy_protocol_intents import legacy_intents_for_capability_types
from runtime.swarm.legacy_protocol_fields import legacy_candidate_safe_fallback_value
from runtime.swarm.protocol_manifest import CapabilityPheroOSProtocol
from runtime.swarm.protocol_schema import dict_value, string_list
from runtime.swarm.protocol_validation import validate_protocol
from runtime.swarm.target_registry import canonical_target


def load_protocol_from_capability(capability: dict[str, Any]) -> CapabilityPheroOSProtocol:
    capability_id = str(capability.get("id") or capability.get("capability_id") or "").strip()
    trust_level = str(capability.get("trust_level") or "first_party_reviewed").strip() or "first_party_reviewed"

    explicit = protocol_payload_from_capability(capability)
    if explicit:
        protocol = CapabilityPheroOSProtocol.from_dict(
            explicit,
            capability_id=capability_id,
            source=explicit.get("source") or "capability_protocol",
            generated_legacy_protocol=False,
        )
    else:
        protocol = CapabilityPheroOSProtocol.from_dict(
            legacy_protocol_payload(capability),
            capability_id=capability_id,
            source="generated_legacy_protocol",
            generated_legacy_protocol=True,
        )

    return protocol.with_diagnostics(validate_protocol(protocol, trust_level=trust_level))


def protocol_payload_from_capability(capability: dict[str, Any]) -> dict[str, Any]:
    for key in ("protocol", "pheroos_protocol", "pheroos"):
        value = capability.get(key)
        if isinstance(value, dict) and value:
            return dict(value)

    swarm = capability.get("swarm") if isinstance(capability.get("swarm"), dict) else {}
    declared_intents = string_list(swarm.get("intents"))
    if declared_intents:
        return {
            **legacy_protocol_payload(capability, declared_intents=declared_intents),
            "source": "capability_swarm_protocol",
        }

    path_text = str(capability.get("path") or "").strip()
    if not path_text:
        return {}
    manifest_path = Path(path_text)
    candidate_path = manifest_path.parent / "pheroos_protocol.json"
    if not candidate_path.exists():
        return {}
    try:
        payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def legacy_protocol_payload(capability: dict[str, Any], *, declared_intents: list[str] | None = None) -> dict[str, Any]:
    capability_id = str(capability.get("id") or "").strip()
    swarm = capability.get("swarm") if isinstance(capability.get("swarm"), dict) else {}
    candidate_policy = dict_value(swarm.get("candidate_policy"))
    candidates = normalize_legacy_candidates(candidate_policy.get("candidates"))
    quorum_policy = dict_value(swarm.get("quorum_policy"))
    if candidates and "candidates" not in quorum_policy:
        quorum_policy = {**quorum_policy, "candidates": [candidate["candidate"] for candidate in candidates]}
    return {
        "capability_id": capability_id,
        "version": str(capability.get("version") or "0.1.0"),
        "intents": declared_intents if declared_intents is not None else legacy_intents(capability),
        "required_capability_types": string_list(swarm.get("required_capability_types")),
        "targets": normalize_legacy_targets(
            swarm.get("targets"),
            capability_id=capability_id,
            allowed_signal_types=string_list(swarm.get("allowed_signal_types")),
        ),
        "candidates": candidates,
        "quorum_policy": quorum_policy,
        "stop_signal_policy": dict_value(swarm.get("stop_signal_policy")),
        "recovery_protocols": normalize_legacy_recovery_protocols(swarm.get("recovery_protocols")),
        "agent_selection_policy": dict_value(swarm.get("agent_selection_policy")),
        "evidence_policy": dict_value(swarm.get("evidence_policy")),
        "tool_policy": legacy_tool_policy(capability),
        "output_policy": dict_value(swarm.get("output_policy")),
        "swarm_loop_policy": {
            "max_rounds": quorum_policy.get("max_swarm_rounds") or swarm.get("max_rounds") or 2,
        },
        "required_governance_actors": string_list(swarm.get("required_governance_actors")),
    }


def normalize_legacy_targets(
    value: Any,
    *,
    capability_id: str,
    allowed_signal_types: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if isinstance(item, str):
            raw_target = item
            data: dict[str, Any] = {}
        elif isinstance(item, dict):
            data = dict(item)
            raw_target = str(data.get("target") or data.get("canonical_target") or "").strip()
        else:
            continue
        target = canonical_target(raw_target)
        if not raw_target or target == "run":
            continue
        output.append(
            {
                "target": target,
                "target_type": data.get("target_type") or data.get("target_kind"),
                "description": data.get("description") or data.get("summary") or data.get("content") or f"{capability_id} requires {target}.",
                "required": data.get("required", True),
                "default_pressure": data.get("default_pressure") or data.get("demand_strength") or 0.7,
                "aliases": data.get("aliases") or [],
                "source": "legacy_swarm",
                "lifecycle_policy": data.get("lifecycle_policy") or {},
                "allowed_signal_types": data.get("allowed_signal_types") or allowed_signal_types,
                "keywords": data.get("keywords") or [],
            }
        )
    return output


def normalize_legacy_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if isinstance(item, str):
            candidate = item
            label = item
            data: dict[str, Any] = {}
        elif isinstance(item, dict):
            data = dict(item)
            candidate = str(data.get("candidate") or data.get("id") or data.get("label") or "").strip()
            label = str(data.get("label") or data.get("candidate") or data.get("id") or candidate)
        else:
            continue
        if not candidate:
            continue
        output.append(
            {
                "candidate": candidate,
                "label": label,
                "description": data.get("description") or "",
                "target": data.get("target") or candidate,
                "compatible_intents": data.get("compatible_intents") or [],
                "blocked_by_targets": data.get("blocked_by_targets") or [],
                "required_evidence_targets": data.get("required_evidence_targets") or [],
                "required_permissions": data.get("required_permissions") or [],
                "default_priority": data.get("default_priority", 0.5),
                "safe_fallback": legacy_candidate_safe_fallback_value(data, label),
            }
        )
    return output


def normalize_legacy_recovery_protocols(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if isinstance(item, str):
            output.append({"recovery_id": item})
        elif isinstance(item, dict):
            data = dict(item)
            if "recovery_id" not in data:
                data["recovery_id"] = data.get("id") or data.get("name") or data.get("hook")
            if "trigger_targets" not in data and isinstance(data.get("targets"), list):
                data["trigger_targets"] = [
                    target.get("target") or target.get("canonical_target")
                    for target in data["targets"]
                    if isinstance(target, dict)
                ]
            if "required_tools" not in data and data.get("retry_tools"):
                data["required_tools"] = data.get("retry_tools")
            output.append(data)
    return output


def legacy_tool_policy(capability: dict[str, Any]) -> dict[str, Any]:
    tools = string_list(capability.get("tools"))
    return {
        "allowed_tool_targets": [f"tool:{tool}" for tool in tools],
        "required_permissions": string_list(capability.get("permissions")),
        "required_connections": string_list(capability.get("required_connections")),
        "risk_level": str(capability.get("risk_level") or "low"),
        "quarantine_external_outputs": True,
    }


def legacy_intents(capability: dict[str, Any]) -> list[str]:
    return legacy_intents_for_capability_types(string_list(capability.get("capability_types")))
