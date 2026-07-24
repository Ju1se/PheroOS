from __future__ import annotations

from collections.abc import Mapping

from pheroos.protocol._validation_primitives import (
    collective_kind_weight,
    finite_in_range,
    finite_non_negative,
    finite_number,
    positive_integer,
    validation_error,
)
from pheroos.protocol.models import (
    SUPPORTED_LAYER_IDS,
    SUPPORTED_PHEROMONE_KINDS,
    CandidateSpec,
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    ProtocolManifest,
    ValidationDiagnostic,
    collective_fallback_id,
    effective_pheromone_scored_subject_types,
    has_hybrid_pheromone_features,
    is_swarm_policy,
    required_swarm_trace_events,
)


def validate_hybrid_rules(
    protocol: ProtocolManifest,
    policy: CollectiveDecisionPolicy,
    *,
    candidate_ids: frozenset[str],
    candidates_by_id: Mapping[str, CandidateSpec],
    safe_candidates: frozenset[str],
) -> list[ValidationDiagnostic]:
    diagnostics = _validate_hybrid_declaration(policy)
    diagnostics.extend(
        _validate_hybrid_lineage(
            protocol,
            policy,
            candidate_ids=candidate_ids,
            candidates_by_id=candidates_by_id,
            safe_candidates=safe_candidates,
        )
    )
    return diagnostics


def _validate_hybrid_declaration(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if has_hybrid_pheromone_features(policy) and policy.mode != "hybrid":
        diagnostics.append(
            validation_error(
                "collective_hybrid_mode_required",
                "hybrid pheromone features require hybrid collective mode",
                "protocol.collective_decision_policy.mode",
            )
        )
    if policy.mode != "hybrid":
        return diagnostics
    diagnostics.extend(_validate_hybrid_surfaces(policy))
    diagnostics.extend(_validate_hybrid_budget(policy))
    diagnostics.extend(_validate_threshold_activation(policy))
    return diagnostics


def _validate_hybrid_surfaces(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    missing_surfaces = [
        name
        for name, enabled in (
            ("pheromone_enabled", policy.pheromone_enabled),
            ("pheromone_diffusion_enabled", policy.pheromone_diffusion_enabled),
            ("pheromone_feedback_enabled", policy.pheromone_feedback_enabled),
            ("layer_coordination_enabled", policy.layer_coordination_enabled),
            ("pheromone_kind_profiles", bool(policy.pheromone_kind_profiles)),
            ("policy_adjustment_bounds", bool(policy.policy_adjustment_bounds)),
        )
        if not enabled
    ]
    if not missing_surfaces:
        return []
    return [
        validation_error(
            "collective_hybrid_declaration_incomplete",
            "hybrid mode requires the complete Hybrid Pheromone declaration: "
            + ", ".join(missing_surfaces),
            "protocol.collective_decision_policy",
        )
    ]


def _validate_hybrid_budget(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if any(
        not finite_number(value) or float(value) <= 0
        for value in (
            policy.pheromone_max_strength,
            policy.pheromone_per_source_cap,
            policy.pheromone_per_round_deposit_cap,
        )
    ):
        diagnostics.append(
            validation_error(
                "collective_hybrid_budget_inactive",
                "hybrid mode requires positive pheromone strength and source/round budgets",
                "protocol.collective_decision_policy",
            )
        )
    if finite_number(policy.pheromone_min_strength) and any(
        not finite_number(bound) or float(policy.pheromone_min_strength) > float(bound)
        for bound in (
            policy.pheromone_max_strength,
            policy.pheromone_per_source_cap,
            policy.pheromone_per_round_deposit_cap,
        )
    ):
        diagnostics.append(
            validation_error(
                "collective_hybrid_min_strength_unreachable",
                "hybrid minimum pheromone strength must fit max/source/round bounds",
                "protocol.collective_decision_policy",
            )
        )
    return diagnostics


def _validate_threshold_activation(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    threshold_weights = _threshold_weights(policy)
    if not (
        threshold_weights
        and finite_number(policy.pheromone_activation_threshold)
        and policy.pheromone_activation_threshold > 0
    ):
        return []
    maximum_delta = (
        policy.pheromone_max_strength * max(threshold_weights, default=0.0)
        if finite_non_negative(policy.pheromone_max_strength)
        else 0.0
    )
    if (
        finite_number(maximum_delta)
        and maximum_delta > 0
        and policy.pheromone_activation_threshold <= maximum_delta
    ):
        return []
    return [
        validation_error(
            "collective_pheromone_activation_unreachable",
            "pheromone activation threshold cannot be reached by any declared threshold response",
            "protocol.collective_decision_policy.pheromone_activation_threshold",
        )
    ]


def _threshold_weights(policy: CollectiveDecisionPolicy) -> list[float]:
    weights: list[float] = []
    for kind in set(SUPPORTED_PHEROMONE_KINDS) | set(policy.pheromone_kind_profiles):
        if kind == "stale":
            continue
        profile = policy.pheromone_kind_profiles.get(kind)
        canonical_profile = (
            profile if isinstance(profile, PheromoneKindProfile) else None
        )
        if not effective_pheromone_scored_subject_types(
            kind,
            canonical_profile,
            policy.pheromone_scored_subject_types,
        ):
            continue
        response_model = (
            canonical_profile.response_model
            if canonical_profile is not None
            else policy.pheromone_response_model
        )
        if response_model != "threshold":
            continue
        weight = (
            canonical_profile.weight
            if canonical_profile is not None
            else collective_kind_weight(policy, kind)
        )
        if finite_non_negative(weight):
            weights.append(float(weight))
    return weights


def _validate_hybrid_lineage(
    protocol: ProtocolManifest,
    policy: CollectiveDecisionPolicy,
    *,
    candidate_ids: frozenset[str],
    candidates_by_id: Mapping[str, CandidateSpec],
    safe_candidates: frozenset[str],
) -> list[ValidationDiagnostic]:
    lineage_enabled = (
        policy.pheromone_diffusion_enabled
        or policy.pheromone_feedback_enabled
        or policy.layer_coordination_enabled
        or bool(policy.policy_adjustment_bounds)
    )
    diagnostics: list[ValidationDiagnostic] = []
    if lineage_enabled and (
        not policy.pheromone_require_provenance
        or not protocol.evidence_policy.require_provenance
    ):
        diagnostics.append(
            validation_error(
                "collective_hybrid_provenance_required",
                "enabled hybrid features require manifest and pheromone provenance",
                "protocol.collective_decision_policy",
            )
        )
    if lineage_enabled and not policy.pheromone_require_trace:
        diagnostics.append(
            validation_error(
                "collective_hybrid_trace_required",
                "enabled hybrid features require trace lineage",
                "protocol.collective_decision_policy.pheromone_require_trace",
            )
        )
    diagnostics.extend(_validate_diffusion_declaration(policy))
    diagnostics.extend(_validate_layer_coverage(policy))
    diagnostics.extend(
        _validate_collective_fallback(
            protocol,
            candidate_ids=candidate_ids,
            candidates_by_id=candidates_by_id,
            safe_candidates=safe_candidates,
        )
    )
    diagnostics.extend(_validate_swarm_trace(protocol, policy))
    return diagnostics


def _validate_diffusion_declaration(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    invalid = False
    message = "disabled diffusion must not declare active propagation semantics"
    if policy.pheromone_diffusion_enabled:
        invalid = not positive_integer(
            policy.pheromone_diffusion_max_hops
        ) or not finite_in_range(
            policy.pheromone_diffusion_attenuation,
            0,
            1,
            lower_inclusive=False,
        )
        message = "enabled diffusion requires positive hops and attenuation"
    elif (
        policy.pheromone_diffusion_max_hops != 0
        or policy.pheromone_diffusion_attenuation != 0
    ):
        invalid = True
    if not invalid:
        return []
    return [
        validation_error(
            "collective_pheromone_diffusion_declaration_invalid",
            message,
            "protocol.collective_decision_policy",
        )
    ]


def _validate_layer_coverage(
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    if not policy.layer_coordination_enabled:
        return []
    diagnostics = [
        validation_error(
            "collective_layer_coverage_incomplete",
            f"{field_name} must cover every supported layer",
            f"protocol.collective_decision_policy.{field_name}",
        )
        for field_name, declared_layers in (
            ("layer_weight_bounds", set(policy.layer_weight_bounds)),
            ("layer_default_weights", set(policy.layer_default_weights)),
            (
                "layer_confidence_thresholds",
                set(policy.layer_confidence_thresholds),
            ),
        )
        if declared_layers != set(SUPPORTED_LAYER_IDS)
    ]
    if not policy.layer_fallback_on_unresolved_conflict:
        diagnostics.append(
            validation_error(
                "collective_layer_fallback_required",
                "layer coordination must fall back on unresolved conflict",
                "protocol.collective_decision_policy.layer_fallback_on_unresolved_conflict",
            )
        )
    return diagnostics


def _validate_collective_fallback(
    protocol: ProtocolManifest,
    *,
    candidate_ids: frozenset[str],
    candidates_by_id: Mapping[str, CandidateSpec],
    safe_candidates: frozenset[str],
) -> list[ValidationDiagnostic]:
    fallback_id = collective_fallback_id(protocol)
    path = "protocol.collective_decision_policy.fallback_candidate"
    if fallback_id not in candidate_ids:
        return [
            validation_error(
                "collective_fallback_missing",
                "collective fallback candidate must be declared",
                path,
            )
        ]
    if fallback_id not in safe_candidates:
        return [
            validation_error(
                "collective_fallback_not_safe",
                "collective fallback candidate must be marked safe_fallback",
                path,
            )
        ]
    fallback = candidates_by_id[fallback_id]
    if fallback.target != protocol.quorum_policy.target:
        return [
            validation_error(
                "collective_fallback_target_mismatch",
                "collective fallback candidate must target the collective target",
                path,
            )
        ]
    return []


def _validate_swarm_trace(
    protocol: ProtocolManifest,
    policy: CollectiveDecisionPolicy,
) -> list[ValidationDiagnostic]:
    if not is_swarm_policy(policy):
        return []
    missing = sorted(
        required_swarm_trace_events(policy) - set(protocol.trace_policy.required_events)
    )
    if not missing:
        return []
    return [
        validation_error(
            "swarm_trace_lineage_incomplete",
            f"trace policy missing swarm events: {', '.join(missing)}",
            "protocol.trace_policy",
        )
    ]
