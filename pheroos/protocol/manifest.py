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
    PheromoneKindProfile,
    ProtocolManifest,
    QuorumPolicy,
    RecoveryProtocol,
    SignalSpec,
    TargetSpec,
    TracePolicy,
)
from pheroos.protocol.schema import capability_schema
from pheroos.protocol.schema_validation import validate_json_schema


def capability_manifest_from_dict(payload: dict[str, Any]) -> CapabilityManifest:
    reject_secret_like_fields(payload)
    schema_errors = validate_json_schema(payload, capability_schema())
    if schema_errors:
        raise ValueError(f"manifest schema invalid: {'; '.join(schema_errors)}")
    protocol_payload = object_payload(payload.get("protocol"))
    return CapabilityManifest(
        id=required_text(payload, "id"),
        name=required_text(payload, "name"),
        version=required_text(payload, "version"),
        permissions=text_list(payload.get("permissions", [])),
        required_connections=text_list(payload.get("required_connections", [])),
        drivers=[driver_from_dict(item) for item in payload.get("drivers", [])],
        protocol=protocol_manifest_from_dict(protocol_payload),
        extensions=collect_extensions(payload),
    )


def protocol_manifest_from_dict(payload: dict[str, Any]) -> ProtocolManifest:
    quorum_payload = object_payload(payload.get("quorum_policy"))
    return ProtocolManifest(
        protocol_version=required_text(payload, "protocol_version"),
        id=required_text(payload, "id"),
        targets=[target_from_dict(item) for item in payload.get("targets", [])],
        candidates=[candidate_from_dict(item) for item in payload.get("candidates", [])],
        quorum_policy=QuorumPolicy(
            target=required_text(quorum_payload, "target"),
            fallback_candidate=required_text(quorum_payload, "fallback_candidate"),
            commit_threshold=positive_int(quorum_payload.get("commit_threshold"), default=1),
        ),
        recovery_protocols=[
            recovery_from_dict(item) for item in payload.get("recovery_protocols", [])
        ],
        output_policy=output_policy_from_dict(object_payload(payload.get("output_policy"), default={})),
        trace_policy=trace_policy_from_dict(object_payload(payload.get("trace_policy"), default={})),
        evidence_policy=evidence_policy_from_dict(object_payload(payload.get("evidence_policy"), default={})),
        signals=[signal_from_dict(item) for item in payload.get("signals", [])],
        collective_decision_policy=collective_decision_policy_from_dict(payload.get("collective_decision_policy")),
        extensions=collect_extensions(payload),
    )


def target_from_dict(payload: dict[str, Any]) -> TargetSpec:
    return TargetSpec(
        id=required_text(payload, "id"),
        description=optional_text(payload, "description"),
        extensions=collect_extensions(payload),
    )


def candidate_from_dict(payload: dict[str, Any]) -> CandidateSpec:
    return CandidateSpec(
        id=required_text(payload, "id"),
        target=required_text(payload, "target"),
        safe_fallback=bool_field(payload, "safe_fallback", default=False),
        label=optional_text(payload, "label"),
        extensions=collect_extensions(payload),
    )


def signal_from_dict(payload: dict[str, Any]) -> SignalSpec:
    return SignalSpec(
        type=required_text(payload, "type"),
        target=required_text(payload, "target"),
        authority_required=optional_text(payload, "authority_required", default="governance"),
        extensions=collect_extensions(payload),
    )


def collective_decision_policy_from_dict(value: Any) -> CollectiveDecisionPolicy | None:
    if value is None:
        return None
    payload = object_payload(value)
    return CollectiveDecisionPolicy(
        mode=optional_text(payload, "mode", default="quorum"),
        min_independent_scouts=positive_int_field(payload, "min_independent_scouts", default=1),
        quorum_threshold=positive_int_field(payload, "quorum_threshold", default=1),
        recruitment_enabled=bool_field(payload, "recruitment_enabled", default=False),
        inhibition_enabled=bool_field(payload, "inhibition_enabled", default=False),
        pheromone_enabled=bool_field(payload, "pheromone_enabled", default=False),
        pheromone_evaporation_rate=float_field(payload, "pheromone_evaporation_rate", default=0.0),
        pheromone_decay_model=optional_text(payload, "pheromone_decay_model", default="exponential"),
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
        pheromone_require_provenance=bool_field(payload, "pheromone_require_provenance", default=True),
        pheromone_require_trace=bool_field(payload, "pheromone_require_trace", default=True),
        pheromone_scored_subject_types=(
            text_list(payload["pheromone_scored_subject_types"])
            if "pheromone_scored_subject_types" in payload
            else ["candidate"]
        ),
        pheromone_kind_profiles=pheromone_kind_profiles_from_dict(payload.get("pheromone_kind_profiles")),
        pheromone_response_model=optional_text(payload, "pheromone_response_model", default="linear"),
        pheromone_activation_threshold=float_field(payload, "pheromone_activation_threshold", default=0.0),
        pheromone_saturation_threshold=float_field(payload, "pheromone_saturation_threshold", default=10.0),
        pheromone_competition_mode=optional_text(payload, "pheromone_competition_mode", default="none"),
        pheromone_exploration_floor=float_field(payload, "pheromone_exploration_floor", default=0.0),
        pheromone_diffusion_enabled=bool_field(payload, "pheromone_diffusion_enabled", default=False),
        pheromone_diffusion_max_hops=non_negative_int_field(payload, "pheromone_diffusion_max_hops", default=0),
        pheromone_diffusion_attenuation=float_field(payload, "pheromone_diffusion_attenuation", default=0.0),
        pheromone_feedback_enabled=bool_field(payload, "pheromone_feedback_enabled", default=False),
        exploration_enabled=bool_field(payload, "exploration_enabled", default=False),
        exploration_floor=float_field(payload, "exploration_floor", default=0.0),
        novelty_decay_rate=float_field(payload, "novelty_decay_rate", default=0.0),
        stale_route_reopen_threshold=float_field(payload, "stale_route_reopen_threshold", default=0.0),
        layer_coordination_enabled=bool_field(payload, "layer_coordination_enabled", default=False),
        layer_weight_bounds=float_bounds_map(payload.get("layer_weight_bounds")),
        layer_default_weights=float_map(payload.get("layer_default_weights")),
        layer_confidence_thresholds=float_map(payload.get("layer_confidence_thresholds")),
        layer_conflict_threshold=float_field(payload, "layer_conflict_threshold", default=0.0),
        layer_emergency_override_threshold=float_field(payload, "layer_emergency_override_threshold", default=0.0),
        layer_min_provenance=positive_int_field(payload, "layer_min_provenance", default=1),
        layer_fallback_on_unresolved_conflict=bool_field(
            payload,
            "layer_fallback_on_unresolved_conflict",
            default=True,
        ),
        policy_adjustment_bounds=object_payload(payload.get("policy_adjustment_bounds"), default={}),
        fallback_candidate=optional_text(payload, "fallback_candidate"),
        extensions=collect_extensions(payload),
    )


def pheromone_kind_profiles_from_dict(value: Any) -> dict[str, PheromoneKindProfile]:
    if value is None:
        return {}
    payload = object_payload(value)
    profiles: dict[str, PheromoneKindProfile] = {}
    for kind, raw_profile in payload.items():
        profile_payload = object_payload(raw_profile)
        profiles[str(kind)] = PheromoneKindProfile(
            weight=float_field(profile_payload, "weight", default=1.0),
            evaporation_rate=optional_float_field(profile_payload, "evaporation_rate"),
            ttl_steps=optional_non_negative_int_field(profile_payload, "ttl_steps"),
            response_model=optional_text(profile_payload, "response_model", default="linear"),
            priority=non_negative_int_field(profile_payload, "priority", default=0),
            can_suppress_positive=bool_field(profile_payload, "can_suppress_positive", default=False),
            scored_subject_types=text_list(profile_payload.get("scored_subject_types", [])),
            extensions=collect_extensions(profile_payload),
        )
    return profiles


def trace_policy_from_dict(payload: dict[str, Any]) -> TracePolicy:
    return TracePolicy(
        required_events=(
            text_list(payload["required_events"])
            if "required_events" in payload
            else ["block", "commit", "recovery", "output"]
        ),
        extensions=collect_extensions(payload),
    )


def driver_from_dict(payload: dict[str, Any]) -> DriverSpec:
    return DriverSpec(
        id=required_text(payload, "id"),
        kind=required_text(payload, "kind"),
        version=required_text(payload, "version"),
        capabilities=text_list(payload.get("capabilities", [])),
        permissions=text_list(payload.get("permissions", [])),
        config_ref=optional_text(payload, "config_ref"),
        extensions=collect_extensions(payload),
    )


def recovery_from_dict(payload: dict[str, Any]) -> RecoveryProtocol:
    return RecoveryProtocol(
        id=required_text(payload, "id"),
        trigger_targets=text_list(payload.get("trigger_targets", [])),
        allowed_roles=text_list(payload.get("allowed_roles", [])),
        allowed_tags=text_list(payload.get("allowed_tags", [])),
        required_tools=text_list(payload.get("required_tools", [])),
        failure_candidate=optional_text(payload, "failure_candidate"),
        extensions=collect_extensions(payload),
    )


def output_policy_from_dict(payload: dict[str, Any]) -> OutputPolicy:
    return OutputPolicy(
        writer_may_create_facts=bool_field(payload, "writer_may_create_facts", default=False),
        requires_committed_candidate=bool_field(payload, "requires_committed_candidate", default=True),
        requires_evidence_contract=bool_field(payload, "requires_evidence_contract", default=True),
        requires_stop_resolution=bool_field(payload, "requires_stop_resolution", default=True),
        requires_publication_permission=bool_field(payload, "requires_publication_permission", default=True),
        extensions=collect_extensions(payload),
    )


def evidence_policy_from_dict(payload: dict[str, Any]) -> EvidencePolicy:
    return EvidencePolicy(
        require_provenance=bool_field(payload, "require_provenance", default=True),
        allow_agent_fact_creation=bool_field(payload, "allow_agent_fact_creation", default=False),
        extensions=collect_extensions(payload),
    )


def required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"field must be a string: {key}")
    value = value.strip()
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
        raise ValueError("expected list payload")
    if any(not isinstance(item, str) for item in value):
        raise ValueError("expected string list payload")
    return [item.strip() for item in value]


def positive_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not float(value).is_integer()
        or value <= 0
    ):
        raise ValueError("expected positive integer")
    return int(value)


def positive_int_field(payload: dict[str, Any], key: str, *, default: int) -> int:
    if key not in payload:
        return default
    return positive_int(payload[key], default=default)


def non_negative_int_field(payload: dict[str, Any], key: str, *, default: int) -> int:
    if key not in payload:
        return default
    value = payload[key]
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not float(value).is_integer()
        or value < 0
    ):
        raise ValueError(f"expected non-negative integer: {key}")
    return int(value)


def optional_non_negative_int_field(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload or payload.get(key) is None:
        return None
    return non_negative_int_field(payload, key, default=-1)


def float_field(payload: dict[str, Any], key: str, *, default: float) -> float:
    if key not in payload:
        return default
    return float_value(payload[key], key=key)


def optional_float_field(payload: dict[str, Any], key: str) -> float | None:
    if key not in payload or payload.get(key) is None:
        return None
    return float_field(payload, key, default=-1.0)


def float_map(value: Any) -> dict[str, float]:
    if value is None:
        return {}
    payload = object_payload(value)
    return {str(key): float_value(raw_value, key=str(key)) for key, raw_value in payload.items()}


def float_bounds_map(value: Any) -> dict[str, tuple[float, float]]:
    if value is None:
        return {}
    payload = object_payload(value)
    bounds: dict[str, tuple[float, float]] = {}
    for key, raw_value in payload.items():
        if isinstance(raw_value, list) and len(raw_value) == 2:
            bounds[str(key)] = (
                float_value(raw_value[0], key=f"{key}.min"),
                float_value(raw_value[1], key=f"{key}.max"),
            )
        elif isinstance(raw_value, dict):
            bounds[str(key)] = (
                float_value(raw_value.get("min"), key=f"{key}.min"),
                float_value(raw_value.get("max"), key=f"{key}.max"),
            )
        else:
            raise ValueError(f"expected numeric bounds: {key}")
    return bounds


def float_value(value: Any, *, key: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"expected number: {key}")
    return float(value)


def optional_text(payload: dict[str, Any], key: str, *, default: str = "") -> str:
    if key not in payload:
        return default
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"field must be a string: {key}")
    return value


def bool_field(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    if key not in payload:
        return default
    value = payload[key]
    if not isinstance(value, bool):
        raise ValueError(f"field must be a boolean: {key}")
    return value
