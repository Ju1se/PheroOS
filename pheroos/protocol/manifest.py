from __future__ import annotations

from typing import Any

from pheroos.protocol.extensions import collect_extensions, reject_secret_like_fields
from pheroos.protocol.models import (
    CandidateSpec,
    CapabilityManifest,
    CollectiveDecisionPolicy,
    DriverSpec,
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
    reject_secret_like_fields(payload)
    protocol_payload = object_payload(payload.get("protocol"))
    return CapabilityManifest(
        id=required_text(payload, "id"),
        name=required_text(payload, "name"),
        version=required_text(payload, "version"),
        permissions=text_list(payload.get("permissions")),
        required_connections=text_list(payload.get("required_connections")),
        drivers=[driver_from_dict(item) for item in payload.get("drivers") or [] if isinstance(item, dict)],
        protocol=protocol_manifest_from_dict(protocol_payload),
        extensions=collect_extensions(payload),
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
        trace_policy=trace_policy_from_dict(object_payload(payload.get("trace_policy"), default={})),
        evidence_policy=evidence_policy_from_dict(object_payload(payload.get("evidence_policy"), default={})),
        signals=[signal_from_dict(item) for item in payload.get("signals") or [] if isinstance(item, dict)],
        collective_decision_policy=collective_decision_policy_from_dict(payload.get("collective_decision_policy")),
        extensions=collect_extensions(payload),
    )


def target_from_dict(payload: dict[str, Any]) -> TargetSpec:
    return TargetSpec(
        id=required_text(payload, "id"),
        description=str(payload.get("description") or ""),
        extensions=collect_extensions(payload),
    )


def candidate_from_dict(payload: dict[str, Any]) -> CandidateSpec:
    return CandidateSpec(
        id=required_text(payload, "id"),
        target=required_text(payload, "target"),
        safe_fallback=bool(payload.get("safe_fallback", False)),
        label=str(payload.get("label") or ""),
        extensions=collect_extensions(payload),
    )


def signal_from_dict(payload: dict[str, Any]) -> SignalSpec:
    return SignalSpec(
        type=required_text(payload, "type"),
        target=required_text(payload, "target"),
        authority_required=str(payload.get("authority_required") or "governance"),
        extensions=collect_extensions(payload),
    )


def collective_decision_policy_from_dict(value: Any) -> CollectiveDecisionPolicy | None:
    if value is None:
        return None
    payload = object_payload(value)
    return CollectiveDecisionPolicy(
        mode=str(payload.get("mode") or "quorum"),
        min_independent_scouts=positive_int_field(payload, "min_independent_scouts", default=1),
        quorum_threshold=positive_int_field(payload, "quorum_threshold", default=1),
        recruitment_enabled=bool(payload.get("recruitment_enabled", False)),
        inhibition_enabled=bool(payload.get("inhibition_enabled", False)),
        pheromone_enabled=bool(payload.get("pheromone_enabled", False)),
        pheromone_evaporation_rate=float_field(payload, "pheromone_evaporation_rate", default=0.0),
        pheromone_decay_model=str(payload.get("pheromone_decay_model") or "exponential"),
        pheromone_min_strength=float_field(payload, "pheromone_min_strength", default=0.0),
        pheromone_max_strength=float_field(payload, "pheromone_max_strength", default=10.0),
        pheromone_positive_weight=float_field(payload, "pheromone_positive_weight", default=1.0),
        pheromone_negative_weight=float_field(payload, "pheromone_negative_weight", default=1.0),
        pheromone_cautionary_weight=float_field(payload, "pheromone_cautionary_weight", default=1.0),
        pheromone_cautionary_override_threshold=float_field(payload, "pheromone_cautionary_override_threshold", default=1.0),
        pheromone_novelty_weight=float_field(payload, "pheromone_novelty_weight", default=0.5),
        pheromone_per_source_cap=float_field(payload, "pheromone_per_source_cap", default=3.0),
        pheromone_per_round_deposit_cap=float_field(payload, "pheromone_per_round_deposit_cap", default=5.0),
        pheromone_min_source_diversity=positive_int_field(payload, "pheromone_min_source_diversity", default=1),
        pheromone_require_provenance=bool(payload.get("pheromone_require_provenance", True)),
        pheromone_require_trace=bool(payload.get("pheromone_require_trace", True)),
        fallback_candidate=str(payload.get("fallback_candidate") or ""),
        extensions=collect_extensions(payload),
    )


def trace_policy_from_dict(payload: dict[str, Any]) -> TracePolicy:
    return TracePolicy(
        required_events=text_list(payload.get("required_events")) or ["block", "commit", "recovery", "output"],
        extensions=collect_extensions(payload),
    )


def driver_from_dict(payload: dict[str, Any]) -> DriverSpec:
    return DriverSpec(
        id=required_text(payload, "id"),
        kind=required_text(payload, "kind"),
        version=required_text(payload, "version"),
        capabilities=text_list(payload.get("capabilities")),
        permissions=text_list(payload.get("permissions")),
        config_ref=str(payload.get("config_ref") or ""),
        extensions=collect_extensions(payload),
    )


def recovery_from_dict(payload: dict[str, Any]) -> RecoveryProtocol:
    return RecoveryProtocol(
        id=required_text(payload, "id"),
        trigger_targets=text_list(payload.get("trigger_targets")),
        allowed_roles=text_list(payload.get("allowed_roles")),
        allowed_tags=text_list(payload.get("allowed_tags")),
        required_tools=text_list(payload.get("required_tools")),
        failure_candidate=str(payload.get("failure_candidate") or ""),
        extensions=collect_extensions(payload),
    )


def output_policy_from_dict(payload: dict[str, Any]) -> OutputPolicy:
    return OutputPolicy(
        writer_may_create_facts=bool(payload.get("writer_may_create_facts", False)),
        requires_committed_candidate=bool(payload.get("requires_committed_candidate", True)),
        requires_evidence_contract=bool(payload.get("requires_evidence_contract", True)),
        requires_stop_resolution=bool(payload.get("requires_stop_resolution", True)),
        requires_publication_permission=bool(payload.get("requires_publication_permission", True)),
        extensions=collect_extensions(payload),
    )


def evidence_policy_from_dict(payload: dict[str, Any]) -> EvidencePolicy:
    return EvidencePolicy(
        require_provenance=bool(payload.get("require_provenance", True)),
        allow_agent_fact_creation=bool(payload.get("allow_agent_fact_creation", False)),
        extensions=collect_extensions(payload),
    )


def stop_signal_policy_from_dict(payload: dict[str, Any]) -> StopSignalPolicy:
    return StopSignalPolicy(
        blocked_actions=text_list(payload.get("blocked_actions")),
        targets=text_list(payload.get("targets")),
        extensions=collect_extensions(payload),
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


def positive_int_field(payload: dict[str, Any], key: str, *, default: int) -> int:
    if key not in payload:
        return default
    try:
        return int(payload.get(key))
    except (TypeError, ValueError):
        return 0


def float_field(payload: dict[str, Any], key: str, *, default: float) -> float:
    if key not in payload:
        return default
    try:
        return float(payload.get(key))
    except (TypeError, ValueError):
        return -1.0
