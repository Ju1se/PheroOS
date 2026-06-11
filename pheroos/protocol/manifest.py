from __future__ import annotations

from typing import Any

from pheroos.protocol.models import (
    CandidateSpec,
    CapabilityManifest,
    EvidencePolicy,
    OutputPolicy,
    ProtocolManifest,
    QuorumPolicy,
    RecoveryProtocol,
    SignalSpec,
    StopSignalPolicy,
    TargetSpec,
    TracePolicy,
)


def capability_manifest_from_dict(payload: dict[str, Any]) -> CapabilityManifest:
    protocol_payload = object_payload(payload.get("protocol"))
    return CapabilityManifest(
        id=required_text(payload, "id"),
        name=required_text(payload, "name"),
        version=required_text(payload, "version"),
        permissions=text_list(payload.get("permissions")),
        required_connections=text_list(payload.get("required_connections")),
        drivers=[item for item in payload.get("drivers") or [] if isinstance(item, dict)],
        protocol=protocol_manifest_from_dict(protocol_payload),
    )


def protocol_manifest_from_dict(payload: dict[str, Any]) -> ProtocolManifest:
    quorum_payload = object_payload(payload.get("quorum_policy"))
    return ProtocolManifest(
        protocol_version=required_text(payload, "protocol_version"),
        id=required_text(payload, "id"),
        targets=[target_from_dict(item) for item in payload.get("targets") or [] if isinstance(item, dict)],
        candidates=[candidate_from_dict(item) for item in payload.get("candidates") or [] if isinstance(item, dict)],
        quorum_policy=QuorumPolicy(
            target=required_text(quorum_payload, "target"),
            fallback_candidate=required_text(quorum_payload, "fallback_candidate"),
            commit_threshold=positive_int(quorum_payload.get("commit_threshold"), default=1),
        ),
        recovery_protocols=[
            recovery_from_dict(item) for item in payload.get("recovery_protocols") or [] if isinstance(item, dict)
        ],
        output_policy=output_policy_from_dict(object_payload(payload.get("output_policy"), default={})),
        trace_policy=TracePolicy(required_events=text_list(object_payload(payload.get("trace_policy"), default={}).get("required_events")) or ["block", "commit", "recovery", "output"]),
        evidence_policy=evidence_policy_from_dict(object_payload(payload.get("evidence_policy"), default={})),
        signals=[signal_from_dict(item) for item in payload.get("signals") or [] if isinstance(item, dict)],
    )


def target_from_dict(payload: dict[str, Any]) -> TargetSpec:
    return TargetSpec(id=required_text(payload, "id"), description=str(payload.get("description") or ""))


def candidate_from_dict(payload: dict[str, Any]) -> CandidateSpec:
    return CandidateSpec(
        id=required_text(payload, "id"),
        target=required_text(payload, "target"),
        safe_fallback=bool(payload.get("safe_fallback", False)),
        label=str(payload.get("label") or ""),
    )


def signal_from_dict(payload: dict[str, Any]) -> SignalSpec:
    return SignalSpec(
        type=required_text(payload, "type"),
        target=required_text(payload, "target"),
        authority_required=str(payload.get("authority_required") or "governance"),
    )


def recovery_from_dict(payload: dict[str, Any]) -> RecoveryProtocol:
    return RecoveryProtocol(
        id=required_text(payload, "id"),
        trigger_targets=text_list(payload.get("trigger_targets")),
        allowed_roles=text_list(payload.get("allowed_roles")),
        allowed_tags=text_list(payload.get("allowed_tags")),
        required_tools=text_list(payload.get("required_tools")),
        failure_candidate=str(payload.get("failure_candidate") or ""),
    )


def output_policy_from_dict(payload: dict[str, Any]) -> OutputPolicy:
    return OutputPolicy(
        writer_may_create_facts=bool(payload.get("writer_may_create_facts", False)),
        requires_committed_candidate=bool(payload.get("requires_committed_candidate", True)),
        requires_evidence_contract=bool(payload.get("requires_evidence_contract", True)),
        requires_stop_resolution=bool(payload.get("requires_stop_resolution", True)),
        requires_publication_permission=bool(payload.get("requires_publication_permission", True)),
    )


def evidence_policy_from_dict(payload: dict[str, Any]) -> EvidencePolicy:
    return EvidencePolicy(
        require_provenance=bool(payload.get("require_provenance", True)),
        allow_agent_fact_creation=bool(payload.get("allow_agent_fact_creation", False)),
    )


def stop_signal_policy_from_dict(payload: dict[str, Any]) -> StopSignalPolicy:
    return StopSignalPolicy(
        blocked_actions=text_list(payload.get("blocked_actions")),
        targets=text_list(payload.get("targets")),
    )


def required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"missing required field: {key}")
    return value


def object_payload(value: Any, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if default is not None:
        return default
    raise ValueError("expected object payload")


def text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
