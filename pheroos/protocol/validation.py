from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from numbers import Real

from pheroos.protocol.extensions import secret_like_paths
from pheroos.protocol.models import (
    SUPPORTED_COLLECTIVE_MODES,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    SUPPORTED_PHEROMONE_COMPETITION_MODES,
    SUPPORTED_PHEROMONE_KINDS,
    SUPPORTED_PHEROMONE_RESPONSE_MODELS,
    SUPPORTED_LAYER_IDS,
    CapabilityManifest,
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    ValidationDiagnostic,
    collective_fallback_id,
    effective_pheromone_scored_subject_types,
    has_hybrid_pheromone_features,
    is_scored_pheromone_subject_type,
    is_swarm_policy,
    is_supported_pheromone_kind,
    required_swarm_trace_events,
)


SAFETY_CRITICAL_POLICY_ADJUSTMENT_FIELDS = frozenset(
    {
        "fallback_candidate",
        "safe_fallback",
        "declared_candidates",
        "candidate_declaration",
        "trace_policy.required_events",
        "pheromone_require_trace",
        "pheromone_require_provenance",
        "evidence_policy.require_provenance",
        "output_policy.requires_committed_candidate",
        "output_policy.requires_evidence_contract",
        "output_policy.requires_stop_resolution",
        "output_policy.requires_publication_permission",
    }
)

POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS = {
    "pheromone_evaporation_rate": (0.0, 1.0),
    "pheromone_positive_weight": (0.0, 10.0),
    "pheromone_negative_weight": (0.0, 10.0),
    "pheromone_cautionary_weight": (0.0, 10.0),
    "pheromone_alarm_weight": (0.0, 10.0),
    "pheromone_novelty_weight": (0.0, 10.0),
    "pheromone_exploration_floor": (0.0, 1.0),
    "pheromone_cautionary_override_threshold": (0.0, 10.0),
    "layer_emergency_override_threshold": (0.0, 1.0),
    "layer_learned_weight": (0.0, 10.0),
    "layer_evolutionary_weight": (0.0, 10.0),
    "layer_metacognitive_weight": (0.0, 10.0),
}
POLICY_ADJUSTMENT_ENUM_FIELDS = {
    "pheromone_response_model": SUPPORTED_PHEROMONE_RESPONSE_MODELS,
}
ALLOWED_POLICY_ADJUSTMENT_FIELDS = frozenset(
    POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS | POLICY_ADJUSTMENT_ENUM_FIELDS
)
MAX_LAYER_WEIGHT = 10.0


def validate_capability_manifest(manifest: CapabilityManifest) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    protocol = manifest.protocol
    target_ids = {target.id for target in protocol.targets}
    candidate_ids = {candidate.id for candidate in protocol.candidates}
    candidates_by_id = {candidate.id: candidate for candidate in protocol.candidates}
    safe_candidates = {candidate.id for candidate in protocol.candidates if candidate.safe_fallback}

    for secret_path in secret_like_paths(manifest):
        diagnostics.append(error("secret_like_manifest_field", "manifest must not contain secret-like fields", secret_path))

    for target_id in duplicate_values(target.id for target in protocol.targets):
        diagnostics.append(error("duplicate_target", f"target {target_id} is declared more than once", "protocol.targets"))
    for candidate_id in duplicate_values(candidate.id for candidate in protocol.candidates):
        diagnostics.append(error("duplicate_candidate", f"candidate {candidate_id} is declared more than once", "protocol.candidates"))

    if not protocol.targets:
        diagnostics.append(error("missing_targets", "protocol must declare at least one target", "protocol.targets"))
    if not protocol.candidates:
        diagnostics.append(error("missing_candidates", "protocol must declare at least one candidate", "protocol.candidates"))

    for candidate in protocol.candidates:
        if candidate.target not in target_ids:
            diagnostics.append(error("candidate_target_missing", f"candidate {candidate.id} references undeclared target", "protocol.candidates"))

    quorum_target = protocol.quorum_policy.target
    quorum_fallback = protocol.quorum_policy.fallback_candidate
    if not isinstance(quorum_target, str) or not quorum_target:
        diagnostics.append(error("quorum_target_invalid", "quorum target must be non-empty", "protocol.quorum_policy.target"))
    elif quorum_target not in target_ids:
        diagnostics.append(error("quorum_target_missing", "quorum target must be declared", "protocol.quorum_policy.target"))
    if not isinstance(quorum_fallback, str) or not quorum_fallback:
        diagnostics.append(error("quorum_fallback_invalid", "quorum fallback candidate must be non-empty", "protocol.quorum_policy.fallback_candidate"))
    elif quorum_fallback not in candidate_ids:
        diagnostics.append(error("quorum_fallback_missing", "quorum fallback candidate must be declared", "protocol.quorum_policy.fallback_candidate"))
    if not positive_integer(protocol.quorum_policy.commit_threshold):
        diagnostics.append(error("quorum_commit_threshold_invalid", "quorum commit threshold must be a positive integer", "protocol.quorum_policy.commit_threshold"))
    if isinstance(quorum_fallback, str) and quorum_fallback and quorum_fallback not in safe_candidates:
        diagnostics.append(error("quorum_fallback_not_safe", "quorum fallback candidate must be marked safe_fallback", "protocol.quorum_policy.fallback_candidate"))
    fallback = candidates_by_id.get(quorum_fallback) if isinstance(quorum_fallback, str) else None
    if fallback is not None and fallback.target != quorum_target:
        diagnostics.append(error("quorum_fallback_target_mismatch", "quorum fallback candidate must target the quorum target", "protocol.quorum_policy.fallback_candidate"))

    for signal in protocol.signals:
        if signal.target not in target_ids:
            diagnostics.append(error("signal_target_missing", f"signal {signal.type} references undeclared target", "protocol.signals"))

    collective_policy = protocol.collective_decision_policy
    if collective_policy is not None:
        if collective_policy.mode not in SUPPORTED_COLLECTIVE_MODES:
            diagnostics.append(error("collective_mode_unsupported", "collective decision mode is unsupported", "protocol.collective_decision_policy.mode"))
        if not positive_integer(collective_policy.min_independent_scouts):
            diagnostics.append(error("collective_min_scouts_invalid", "min_independent_scouts must be positive", "protocol.collective_decision_policy.min_independent_scouts"))
        if not positive_integer(collective_policy.quorum_threshold):
            diagnostics.append(error("collective_quorum_threshold_invalid", "quorum_threshold must be positive", "protocol.collective_decision_policy.quorum_threshold"))
        if not finite_in_range(collective_policy.pheromone_evaporation_rate, 0, 1):
            diagnostics.append(error("collective_pheromone_evaporation_invalid", "pheromone evaporation rate must be between 0 and 1", "protocol.collective_decision_policy.pheromone_evaporation_rate"))
        if collective_policy.pheromone_decay_model not in SUPPORTED_PHEROMONE_DECAY_MODELS:
            diagnostics.append(error("collective_pheromone_decay_model_invalid", "pheromone decay model is unsupported", "protocol.collective_decision_policy.pheromone_decay_model"))
        if not valid_non_negative_bounds(
            collective_policy.pheromone_min_strength,
            collective_policy.pheromone_max_strength,
        ):
            diagnostics.append(error("collective_pheromone_strength_bounds_invalid", "pheromone strength bounds must be finite, non-negative, and ordered", "protocol.collective_decision_policy"))
        if any(
            not finite_non_negative(value)
            for value in (
                collective_policy.pheromone_positive_weight,
                collective_policy.pheromone_negative_weight,
                collective_policy.pheromone_cautionary_weight,
                collective_policy.pheromone_novelty_weight,
            )
        ):
            diagnostics.append(error("collective_pheromone_weight_invalid", "pheromone weights must be non-negative", "protocol.collective_decision_policy"))
        if not finite_non_negative(collective_policy.pheromone_cautionary_override_threshold):
            diagnostics.append(error("collective_pheromone_cautionary_threshold_invalid", "pheromone cautionary override threshold must be non-negative", "protocol.collective_decision_policy.pheromone_cautionary_override_threshold"))
        if not finite_non_negative(collective_policy.pheromone_per_source_cap) or not finite_non_negative(collective_policy.pheromone_per_round_deposit_cap):
            diagnostics.append(error("collective_pheromone_cap_invalid", "pheromone caps must be non-negative", "protocol.collective_decision_policy"))
        if not positive_integer(collective_policy.pheromone_min_source_diversity):
            diagnostics.append(error("collective_pheromone_source_diversity_invalid", "pheromone min source diversity must be positive", "protocol.collective_decision_policy.pheromone_min_source_diversity"))
        if not collective_policy.pheromone_scored_subject_types:
            diagnostics.append(error("collective_pheromone_subject_types_empty", "pheromone scored subject types must not be empty", "protocol.collective_decision_policy.pheromone_scored_subject_types"))
        for subject_type in collective_policy.pheromone_scored_subject_types:
            if not isinstance(subject_type, str) or not is_scored_pheromone_subject_type(subject_type):
                diagnostics.append(error("collective_pheromone_subject_type_invalid", "pheromone scored subject type is unsupported or non-scoring", "protocol.collective_decision_policy.pheromone_scored_subject_types"))
        if collective_policy.pheromone_response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
            diagnostics.append(error("collective_pheromone_response_model_invalid", "pheromone response model is unsupported", "protocol.collective_decision_policy.pheromone_response_model"))
        if collective_policy.pheromone_competition_mode not in SUPPORTED_PHEROMONE_COMPETITION_MODES:
            diagnostics.append(error("collective_pheromone_competition_mode_invalid", "pheromone competition mode is unsupported", "protocol.collective_decision_policy.pheromone_competition_mode"))
        if any(
            not finite_non_negative(value)
            for value in (
                collective_policy.pheromone_activation_threshold,
                collective_policy.pheromone_saturation_threshold,
                collective_policy.stale_route_reopen_threshold,
            )
        ) or any(
            not finite_in_range(value, 0, 1)
            for value in (
                collective_policy.pheromone_exploration_floor,
                collective_policy.exploration_floor,
            )
        ):
            diagnostics.append(error("collective_pheromone_threshold_invalid", "pheromone thresholds must be non-negative and exploration floors must be between 0 and 1", "protocol.collective_decision_policy"))
        if not finite_in_range(collective_policy.pheromone_diffusion_attenuation, 0, 1):
            diagnostics.append(error("collective_pheromone_diffusion_attenuation_invalid", "pheromone diffusion attenuation must be between 0 and 1", "protocol.collective_decision_policy.pheromone_diffusion_attenuation"))
        if not non_negative_integer(collective_policy.pheromone_diffusion_max_hops):
            diagnostics.append(error("collective_pheromone_diffusion_hops_invalid", "pheromone diffusion max hops must be non-negative", "protocol.collective_decision_policy.pheromone_diffusion_max_hops"))
        if not finite_in_range(collective_policy.novelty_decay_rate, 0, 1):
            diagnostics.append(error("collective_pheromone_novelty_decay_invalid", "novelty decay rate must be between 0 and 1", "protocol.collective_decision_policy.novelty_decay_rate"))
        for kind, profile in collective_policy.pheromone_kind_profiles.items():
            if not isinstance(kind, str) or not is_supported_pheromone_kind(kind):
                diagnostics.append(error("collective_pheromone_kind_invalid", "pheromone kind must be built-in or namespaced", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            if not isinstance(profile, PheromoneKindProfile):
                diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone kind profile must use the canonical protocol declaration", "protocol.collective_decision_policy.pheromone_kind_profiles"))
                continue
            if not finite_non_negative(profile.weight):
                diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone kind profile weights must be non-negative", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            if profile.evaporation_rate is not None and not finite_in_range(profile.evaporation_rate, 0, 1):
                diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone kind profile evaporation rates must be between 0 and 1", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            if profile.ttl_steps is not None and not non_negative_integer(profile.ttl_steps):
                diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone kind profile ttl values must be non-negative", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            if profile.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
                diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone kind profile response model is unsupported", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            if not non_negative_integer(profile.priority):
                diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone kind profile priority must be a non-negative integer", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            if not isinstance(profile.can_suppress_positive, bool):
                diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone suppression flag must be boolean", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            for subject_type in profile.scored_subject_types:
                if not isinstance(subject_type, str) or not is_scored_pheromone_subject_type(subject_type):
                    diagnostics.append(error("collective_pheromone_kind_profile_invalid", "pheromone kind profile subject type is unsupported or non-scoring", "protocol.collective_decision_policy.pheromone_kind_profiles"))
            if kind == "stale" and (profile.weight != 0 or profile.scored_subject_types):
                diagnostics.append(error("collective_pheromone_stale_scores_invalid", "stale pheromone must remain no-score", "protocol.collective_decision_policy.pheromone_kind_profiles.stale"))
        if not positive_integer(collective_policy.layer_min_provenance):
            diagnostics.append(error("collective_layer_provenance_invalid", "layer_min_provenance must be positive", "protocol.collective_decision_policy.layer_min_provenance"))
        if not finite_in_range(collective_policy.layer_conflict_threshold, 0, 1) or not finite_in_range(collective_policy.layer_emergency_override_threshold, 0, 1):
            diagnostics.append(error("collective_layer_threshold_invalid", "layer coordination thresholds must be finite and between 0 and 1", "protocol.collective_decision_policy"))
        for layer_id, weight in collective_policy.layer_default_weights.items():
            if layer_id not in SUPPORTED_LAYER_IDS:
                diagnostics.append(error("collective_layer_id_invalid", "layer default weight references an unsupported layer", "protocol.collective_decision_policy.layer_default_weights"))
            if not finite_in_range(weight, 0, MAX_LAYER_WEIGHT):
                diagnostics.append(error("collective_layer_weight_invalid", "layer weights must be finite and within absolute bounds", "protocol.collective_decision_policy.layer_default_weights"))
        for layer_id, threshold in collective_policy.layer_confidence_thresholds.items():
            if layer_id not in SUPPORTED_LAYER_IDS:
                diagnostics.append(error("collective_layer_id_invalid", "layer confidence threshold references an unsupported layer", "protocol.collective_decision_policy.layer_confidence_thresholds"))
            if not finite_in_range(threshold, 0, 1):
                diagnostics.append(error("collective_layer_threshold_invalid", "layer confidence thresholds must be finite and between 0 and 1", "protocol.collective_decision_policy.layer_confidence_thresholds"))
        for layer_id, bounds in collective_policy.layer_weight_bounds.items():
            if layer_id not in SUPPORTED_LAYER_IDS:
                diagnostics.append(error("collective_layer_id_invalid", "layer weight bounds reference an unsupported layer", "protocol.collective_decision_policy.layer_weight_bounds"))
            if not valid_absolute_bounds(bounds, 0, MAX_LAYER_WEIGHT):
                diagnostics.append(error("collective_layer_bounds_invalid", "layer weight bounds must be finite, ordered, and within absolute bounds", "protocol.collective_decision_policy.layer_weight_bounds"))
                continue
            lower, upper = bounds
            default_weight = collective_policy.layer_default_weights.get(layer_id)
            if finite_number(default_weight) and not lower <= default_weight <= upper:
                diagnostics.append(error("collective_layer_default_weight_out_of_bounds", "layer default weight must stay inside declared bounds", "protocol.collective_decision_policy.layer_default_weights"))
        for field_name, bounds in collective_policy.policy_adjustment_bounds.items():
            if field_name in SAFETY_CRITICAL_POLICY_ADJUSTMENT_FIELDS:
                diagnostics.append(error("collective_policy_adjustment_unsafe", "policy adjustment bounds must not permit safety-critical invariant changes", "protocol.collective_decision_policy.policy_adjustment_bounds"))
            if field_name not in ALLOWED_POLICY_ADJUSTMENT_FIELDS:
                diagnostics.append(error("collective_policy_adjustment_unknown", "policy adjustment field is not allowlisted", "protocol.collective_decision_policy.policy_adjustment_bounds"))
            if not valid_policy_adjustment_bound(field_name, bounds, collective_policy):
                diagnostics.append(error("collective_policy_adjustment_bounds_invalid", "policy adjustment bounds must declare ordered numeric bounds or allowed values", "protocol.collective_decision_policy.policy_adjustment_bounds"))
        hybrid_features = has_hybrid_pheromone_features(collective_policy)
        if hybrid_features and collective_policy.mode != "hybrid":
            diagnostics.append(error("collective_hybrid_mode_required", "hybrid pheromone features require hybrid collective mode", "protocol.collective_decision_policy.mode"))
        if collective_policy.mode == "hybrid":
            missing_hybrid_surfaces = [
                name
                for name, enabled in (
                    ("pheromone_enabled", collective_policy.pheromone_enabled),
                    ("pheromone_diffusion_enabled", collective_policy.pheromone_diffusion_enabled),
                    ("pheromone_feedback_enabled", collective_policy.pheromone_feedback_enabled),
                    ("layer_coordination_enabled", collective_policy.layer_coordination_enabled),
                    ("pheromone_kind_profiles", bool(collective_policy.pheromone_kind_profiles)),
                    ("policy_adjustment_bounds", bool(collective_policy.policy_adjustment_bounds)),
                )
                if not enabled
            ]
            if missing_hybrid_surfaces:
                diagnostics.append(
                    error(
                        "collective_hybrid_declaration_incomplete",
                        "hybrid mode requires the complete Hybrid Pheromone declaration: "
                        + ", ".join(missing_hybrid_surfaces),
                        "protocol.collective_decision_policy",
                    )
                )
            if any(
                not finite_number(value) or float(value) <= 0
                for value in (
                    collective_policy.pheromone_max_strength,
                    collective_policy.pheromone_per_source_cap,
                    collective_policy.pheromone_per_round_deposit_cap,
                )
            ):
                diagnostics.append(
                    error(
                        "collective_hybrid_budget_inactive",
                        "hybrid mode requires positive pheromone strength and source/round budgets",
                        "protocol.collective_decision_policy",
                    )
                )
            if finite_number(collective_policy.pheromone_min_strength) and any(
                not finite_number(bound)
                or float(collective_policy.pheromone_min_strength) > float(bound)
                for bound in (
                    collective_policy.pheromone_max_strength,
                    collective_policy.pheromone_per_source_cap,
                    collective_policy.pheromone_per_round_deposit_cap,
                )
            ):
                diagnostics.append(
                    error(
                        "collective_hybrid_min_strength_unreachable",
                        "hybrid minimum pheromone strength must fit max/source/round bounds",
                        "protocol.collective_decision_policy",
                    )
                )
            threshold_weights: list[float] = []
            for kind in set(SUPPORTED_PHEROMONE_KINDS) | set(
                collective_policy.pheromone_kind_profiles
            ):
                if kind == "stale":
                    continue
                profile = collective_policy.pheromone_kind_profiles.get(kind)
                if not effective_pheromone_scored_subject_types(
                    kind,
                    profile if isinstance(profile, PheromoneKindProfile) else None,
                    collective_policy.pheromone_scored_subject_types,
                ):
                    continue
                response_model = (
                    profile.response_model
                    if isinstance(profile, PheromoneKindProfile)
                    else collective_policy.pheromone_response_model
                )
                if response_model != "threshold":
                    continue
                weight = (
                    profile.weight
                    if isinstance(profile, PheromoneKindProfile)
                    else collective_kind_weight(collective_policy, kind)
                )
                if finite_non_negative(weight):
                    threshold_weights.append(float(weight))
            if (
                threshold_weights
                and finite_number(collective_policy.pheromone_activation_threshold)
                and collective_policy.pheromone_activation_threshold > 0
            ):
                maximum_threshold_delta = (
                    collective_policy.pheromone_max_strength * max(threshold_weights, default=0.0)
                    if finite_non_negative(collective_policy.pheromone_max_strength)
                    else 0.0
                )
                if threshold_weights and (
                    not finite_number(maximum_threshold_delta)
                    or maximum_threshold_delta <= 0
                    or collective_policy.pheromone_activation_threshold > maximum_threshold_delta
                ):
                    diagnostics.append(
                        error(
                            "collective_pheromone_activation_unreachable",
                            "pheromone activation threshold cannot be reached by any declared threshold response",
                            "protocol.collective_decision_policy.pheromone_activation_threshold",
                        )
                    )
        hybrid_lineage_features = (
            collective_policy.pheromone_diffusion_enabled
            or collective_policy.pheromone_feedback_enabled
            or collective_policy.layer_coordination_enabled
            or bool(collective_policy.policy_adjustment_bounds)
        )
        if hybrid_lineage_features and (
            not collective_policy.pheromone_require_provenance
            or not protocol.evidence_policy.require_provenance
        ):
            diagnostics.append(error("collective_hybrid_provenance_required", "enabled hybrid features require manifest and pheromone provenance", "protocol.collective_decision_policy"))
        if hybrid_lineage_features and not collective_policy.pheromone_require_trace:
            diagnostics.append(error("collective_hybrid_trace_required", "enabled hybrid features require trace lineage", "protocol.collective_decision_policy.pheromone_require_trace"))
        if collective_policy.pheromone_diffusion_enabled:
            if not positive_integer(collective_policy.pheromone_diffusion_max_hops) or not finite_in_range(
                collective_policy.pheromone_diffusion_attenuation,
                0,
                1,
                lower_inclusive=False,
            ):
                diagnostics.append(error("collective_pheromone_diffusion_declaration_invalid", "enabled diffusion requires positive hops and attenuation", "protocol.collective_decision_policy"))
        elif collective_policy.pheromone_diffusion_max_hops != 0 or collective_policy.pheromone_diffusion_attenuation != 0:
            diagnostics.append(error("collective_pheromone_diffusion_declaration_invalid", "disabled diffusion must not declare active propagation semantics", "protocol.collective_decision_policy"))
        if collective_policy.layer_coordination_enabled:
            for field_name, declared_layers in (
                ("layer_weight_bounds", set(collective_policy.layer_weight_bounds)),
                ("layer_default_weights", set(collective_policy.layer_default_weights)),
                ("layer_confidence_thresholds", set(collective_policy.layer_confidence_thresholds)),
            ):
                if declared_layers != set(SUPPORTED_LAYER_IDS):
                    diagnostics.append(error("collective_layer_coverage_incomplete", f"{field_name} must cover every supported layer", f"protocol.collective_decision_policy.{field_name}"))
            if not collective_policy.layer_fallback_on_unresolved_conflict:
                diagnostics.append(error("collective_layer_fallback_required", "layer coordination must fall back on unresolved conflict", "protocol.collective_decision_policy.layer_fallback_on_unresolved_conflict"))
        fallback_candidate = collective_fallback_id(protocol)
        if fallback_candidate not in candidate_ids:
            diagnostics.append(error("collective_fallback_missing", "collective fallback candidate must be declared", "protocol.collective_decision_policy.fallback_candidate"))
        elif fallback_candidate not in safe_candidates:
            diagnostics.append(error("collective_fallback_not_safe", "collective fallback candidate must be marked safe_fallback", "protocol.collective_decision_policy.fallback_candidate"))
        else:
            collective_fallback = candidates_by_id[fallback_candidate]
            if collective_fallback.target != protocol.quorum_policy.target:
                diagnostics.append(error("collective_fallback_target_mismatch", "collective fallback candidate must target the collective target", "protocol.collective_decision_policy.fallback_candidate"))
        if is_swarm_policy(collective_policy):
            swarm_missing_trace = sorted(required_swarm_trace_events(collective_policy) - set(protocol.trace_policy.required_events))
            if swarm_missing_trace:
                diagnostics.append(error("swarm_trace_lineage_incomplete", f"trace policy missing swarm events: {', '.join(swarm_missing_trace)}", "protocol.trace_policy"))

    for recovery in protocol.recovery_protocols:
        for target in recovery.trigger_targets:
            if target not in target_ids:
                diagnostics.append(error("recovery_target_missing", f"recovery target {target} is undeclared", "protocol.recovery_protocols"))
        if recovery.failure_candidate and recovery.failure_candidate not in candidate_ids:
            diagnostics.append(error("recovery_failure_candidate_missing", "recovery failure candidate must be declared", "protocol.recovery_protocols"))
        failure_candidate = candidates_by_id.get(recovery.failure_candidate)
        if failure_candidate is not None and failure_candidate.target not in set(recovery.trigger_targets):
            diagnostics.append(error("recovery_failure_candidate_target_mismatch", "recovery failure candidate must target a recovery trigger target", "protocol.recovery_protocols"))

    if protocol.output_policy.writer_may_create_facts:
        diagnostics.append(error("writer_fact_creation", "output policy must not allow writer fact creation", "protocol.output_policy"))

    for field_name, enabled in (
        ("requires_committed_candidate", protocol.output_policy.requires_committed_candidate),
        ("requires_evidence_contract", protocol.output_policy.requires_evidence_contract),
        ("requires_stop_resolution", protocol.output_policy.requires_stop_resolution),
        ("requires_publication_permission", protocol.output_policy.requires_publication_permission),
    ):
        if enabled is not True:
            diagnostics.append(
                error(
                    "output_gate_disabled",
                    "output authorization gates are mandatory and cannot be disabled",
                    f"protocol.output_policy.{field_name}",
                )
            )

    if protocol.evidence_policy.allow_agent_fact_creation:
        diagnostics.append(error("agent_fact_creation", "evidence policy must not allow agent fact creation", "protocol.evidence_policy"))

    required_trace = {"block", "commit", "recovery", "output"}
    missing_trace = sorted(required_trace - set(protocol.trace_policy.required_events))
    if missing_trace:
        diagnostics.append(error("trace_lineage_incomplete", f"trace policy missing events: {', '.join(missing_trace)}", "protocol.trace_policy"))

    return diagnostics


def validate_ok(manifest: CapabilityManifest) -> bool:
    return not any(item.level == "error" for item in validate_capability_manifest(manifest))


def error(code: str, message: str, path: str) -> ValidationDiagnostic:
    return ValidationDiagnostic(code=code, message=message, path=path)


def duplicate_values(values: object) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        text = str(value)
        if text in seen:
            duplicates.add(text)
        seen.add(text)
    return sorted(duplicates)


def collective_kind_weight(policy: CollectiveDecisionPolicy, kind: str) -> float:
    value: object
    if kind == "positive":
        value = policy.pheromone_positive_weight
    elif kind == "negative":
        value = policy.pheromone_negative_weight
    elif kind in {"cautionary", "alarm"}:
        value = policy.pheromone_cautionary_weight
    elif kind == "novelty":
        value = policy.pheromone_novelty_weight
    else:
        return 0.0
    return float(value) if finite_non_negative(value) else 0.0


def valid_policy_adjustment_bound(
    field_name: object,
    bounds: object,
    policy: object,
) -> bool:
    if not isinstance(field_name, str):
        return False
    allowed_values = POLICY_ADJUSTMENT_ENUM_FIELDS.get(field_name)
    if allowed_values is not None:
        if not isinstance(bounds, Mapping) or set(bounds) != {"allowed_values"}:
            return False
        values = bounds["allowed_values"]
        return (
            isinstance(values, Sequence)
            and not isinstance(values, (str, bytes, bytearray))
            and bool(values)
            and all(isinstance(value, str) and value in allowed_values for value in values)
        )

    absolute_bounds = POLICY_ADJUSTMENT_NUMERIC_ABSOLUTE_BOUNDS.get(field_name)
    if absolute_bounds is None or not valid_absolute_bounds(bounds, *absolute_bounds):
        return False
    lower, upper = normalized_bounds(bounds)
    if field_name == "pheromone_cautionary_override_threshold" and finite_number(policy.pheromone_max_strength):
        if upper > policy.pheromone_max_strength:
            return False
    if field_name.startswith("layer_") and field_name.endswith("_weight"):
        layer_id = field_name.removeprefix("layer_").removesuffix("_weight")
        declared_bounds = policy.layer_weight_bounds.get(layer_id)
        if declared_bounds is None or not valid_absolute_bounds(declared_bounds, 0, MAX_LAYER_WEIGHT):
            return False
        declared_lower, declared_upper = normalized_bounds(declared_bounds)
        if lower < declared_lower or upper > declared_upper:
            return False
    return True


def normalized_bounds(bounds: object) -> tuple[float, float]:
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        return float(bounds[0]), float(bounds[1])
    if isinstance(bounds, Mapping) and set(bounds) == {"min", "max"}:
        return float(bounds["min"]), float(bounds["max"])
    raise ValueError("invalid bounds")


def valid_absolute_bounds(bounds: object, absolute_minimum: float, absolute_maximum: float) -> bool:
    try:
        lower, upper = normalized_bounds(bounds)
    except (TypeError, ValueError):
        return False
    return (
        finite_number(lower)
        and finite_number(upper)
        and absolute_minimum <= lower <= upper <= absolute_maximum
    )


def valid_non_negative_bounds(lower: object, upper: object) -> bool:
    return finite_non_negative(lower) and finite_non_negative(upper) and float(lower) <= float(upper)


def finite_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def finite_non_negative(value: object) -> bool:
    return finite_number(value) and float(value) >= 0


def finite_in_range(
    value: object,
    minimum: float,
    maximum: float,
    *,
    lower_inclusive: bool = True,
) -> bool:
    if not finite_number(value):
        return False
    if lower_inclusive:
        return minimum <= float(value) <= maximum
    return minimum < float(value) <= maximum


def positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def non_negative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
