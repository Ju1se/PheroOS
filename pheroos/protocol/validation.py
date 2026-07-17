from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import unicodedata
from numbers import Real

from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    MAX_AUTHORITY_INTEGER,
    REQUIRED_COMMIT_RESET_RULES,
    SUPPORTED_CERTIFICATE_MODES,
    SUPPORTED_COMMIT_ASSURANCES,
    SUPPORTED_DEADLINE_OUTCOMES,
    SUPPORTED_RISK_BANDS,
    SUPPORTED_TERMINAL_OUTCOMES,
    WEIGHT_SCALE,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitWindowPolicy,
    DistributedCommitPolicy,
    EvidenceQualificationPolicy,
    RiskBandPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.extensions import is_namespaced_extension, secret_like_paths
from pheroos.protocol.models import (
    SUPPORTED_PROTOCOL_VERSIONS,
    SUPPORTED_COLLECTIVE_MODES,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    SUPPORTED_PHEROMONE_COMPETITION_MODES,
    SUPPORTED_PHEROMONE_KINDS,
    SUPPORTED_PHEROMONE_RESPONSE_MODELS,
    SUPPORTED_LAYER_IDS,
    CapabilityManifest,
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    ProtocolManifest,
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
COMMIT_ASSURANCE_ORDER = {
    "advisory": 0,
    "evidence_bound": 1,
    "certified": 2,
    "distributed": 3,
}
CERTIFICATE_MODE_BY_ASSURANCE = {
    "advisory": "none",
    "evidence_bound": "local_receipt",
    "certified": "portable",
    "distributed": "distributed",
}
NON_PUBLISHABLE_TERMINAL_OUTCOMES = frozenset(
    {"invalid", "finality_unavailable", "safety_violation"}
)
COMMIT_CRITICAL_EXTENSION_PREFIXES = (
    "x-critical",
    "ext.critical",
)


def validate_capability_manifest(manifest: CapabilityManifest) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    protocol = manifest.protocol
    target_ids = {target.id for target in protocol.targets}
    candidate_ids = {candidate.id for candidate in protocol.candidates}
    candidates_by_id = {candidate.id: candidate for candidate in protocol.candidates}
    safe_candidates = {candidate.id for candidate in protocol.candidates if candidate.safe_fallback}

    if not canonical_nonblank_text(protocol.protocol_version):
        diagnostics.append(
            error(
                "protocol_version_invalid",
                "protocol version must be canonical non-blank text",
                "protocol.protocol_version",
            )
        )
    elif protocol.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
        diagnostics.append(
            error(
                "protocol_version_unsupported",
                "protocol version is not explicitly supported",
                "protocol.protocol_version",
            )
        )

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

    if protocol.collective_commit_policy is not None:
        diagnostics.extend(validate_collective_commit_policy(protocol))

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


def validate_collective_commit_policy(
    protocol: ProtocolManifest,
) -> list[ValidationDiagnostic]:
    policy = protocol.collective_commit_policy
    path = "protocol.collective_commit_policy"
    if not isinstance(policy, CollectiveCommitPolicy):
        return [
            error(
                "commit_policy_type_invalid",
                "collective commit policy must use the canonical Protocol ABI declaration",
                path,
            )
        ]

    diagnostics: list[ValidationDiagnostic] = []
    if policy.policy_version != COMMIT_POLICY_VERSION:
        diagnostics.append(error("commit_policy_version_unsupported", "collective commit policy version is unsupported", f"{path}.policy_version"))
    if policy.model != COMMIT_MODEL:
        diagnostics.append(error("commit_model_unsupported", "collective commit model is unsupported", f"{path}.model"))
    if policy.assurance not in SUPPORTED_COMMIT_ASSURANCES:
        diagnostics.append(error("commit_assurance_unsupported", "collective commit assurance is unsupported", f"{path}.assurance"))
    if not canonical_nonblank_text(policy.target):
        diagnostics.append(error("commit_target_invalid", "collective commit target must be canonical and non-blank", f"{path}.target"))

    extension_owners = (
        (policy, path),
        (policy.evidence_qualification, f"{path}.evidence_qualification"),
        (policy.support_lease, f"{path}.support_lease"),
        (policy.commit_window, f"{path}.commit_window"),
        (policy.terminal_outcome, f"{path}.terminal_outcome"),
        (policy.certificate, f"{path}.certificate"),
        *((band, f"{path}.risk_bands.{name}") for name, band in policy.risk_bands.items()),
    )
    if policy.distributed is not None:
        extension_owners = (
            *extension_owners,
            (policy.distributed, f"{path}.distributed"),
        )
    for owner, owner_path in extension_owners:
        diagnostics.extend(
            validate_commit_extensions(
                getattr(owner, "extensions", None),
                path=f"{owner_path}.extensions",
            )
        )

    target_ids = {target.id for target in protocol.targets}
    candidates_by_id = {candidate.id: candidate for candidate in protocol.candidates}
    safe_candidates = {candidate.id for candidate in protocol.candidates if candidate.safe_fallback}
    if policy.target not in target_ids:
        diagnostics.append(error("commit_target_missing", "collective commit target must be declared", f"{path}.target"))
    if policy.target != protocol.quorum_policy.target:
        diagnostics.append(error("commit_target_mismatch", "collective commit and quorum targets must match exactly", f"{path}.target"))

    diagnostics.extend(validate_evidence_qualification_policy(policy.evidence_qualification, path=f"{path}.evidence_qualification"))
    diagnostics.extend(validate_support_lease_policy(policy.support_lease, path=f"{path}.support_lease"))
    diagnostics.extend(validate_commit_window_policy(policy.commit_window, path=f"{path}.commit_window"))
    diagnostics.extend(
        validate_terminal_outcome_policy(
            policy.terminal_outcome,
            assurance=policy.assurance,
            path=f"{path}.terminal_outcome",
        )
    )
    diagnostics.extend(
        validate_certificate_policy(
            policy.certificate,
            assurance=policy.assurance,
            path=f"{path}.certificate",
        )
    )
    diagnostics.extend(
        validate_distributed_commit_policy(
            policy.distributed,
            assurance=policy.assurance,
            path=f"{path}.distributed",
        )
    )

    terminal = policy.terminal_outcome
    if isinstance(terminal, TerminalOutcomePolicy):
        fallback_id = terminal.safe_fallback_candidate
        if fallback_id != protocol.quorum_policy.fallback_candidate:
            diagnostics.append(error("commit_fallback_quorum_mismatch", "collective commit and quorum fallbacks must match exactly", f"{path}.terminal_outcome.safe_fallback_candidate"))
        if protocol.collective_decision_policy is not None and fallback_id != collective_fallback_id(protocol):
            diagnostics.append(error("commit_fallback_collective_mismatch", "collective commit and collective decision fallbacks must match exactly", f"{path}.terminal_outcome.safe_fallback_candidate"))
        fallback = candidates_by_id.get(fallback_id)
        if fallback is None:
            diagnostics.append(error("commit_fallback_missing", "collective commit fallback candidate must be declared", f"{path}.terminal_outcome.safe_fallback_candidate"))
        elif fallback_id not in safe_candidates:
            diagnostics.append(error("commit_fallback_not_safe", "collective commit fallback candidate must be marked safe", f"{path}.terminal_outcome.safe_fallback_candidate"))
        elif fallback.target != policy.target:
            diagnostics.append(error("commit_fallback_target_mismatch", "collective commit fallback must target the active commit target", f"{path}.terminal_outcome.safe_fallback_candidate"))

    if protocol.evidence_policy.require_provenance is not True:
        diagnostics.append(error("commit_manifest_provenance_required", "collective commit requires protocol evidence provenance", "protocol.evidence_policy.require_provenance"))

    diagnostics.extend(validate_risk_bands(policy, path=f"{path}.risk_bands"))
    return diagnostics


def validate_commit_extensions(
    extensions: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    """Keep optional metadata open without accepting unknown critical semantics."""

    if not isinstance(extensions, Mapping):
        return [
            error(
                "commit_extensions_type_invalid",
                "commit extensions must be a namespaced metadata object",
                path,
            )
        ]
    diagnostics: list[ValidationDiagnostic] = []
    for key in extensions:
        if not isinstance(key, str) or not is_namespaced_extension(key):
            diagnostics.append(
                error(
                    "commit_extension_namespace_invalid",
                    "commit extension keys must use x- or ext. namespaces",
                    f"{path}.{key}",
                )
            )
            continue
        normalized = key.lower()
        if any(
            normalized == prefix
            or normalized.startswith(prefix + "-")
            or normalized.startswith(prefix + ".")
            for prefix in COMMIT_CRITICAL_EXTENSION_PREFIXES
        ):
            diagnostics.append(
                error(
                    "commit_unknown_critical_extension",
                    "unknown critical commit extensions require a new supported ABI version",
                    f"{path}.{key}",
                )
            )
    return diagnostics


def validate_evidence_qualification_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, EvidenceQualificationPolicy):
        return [error("commit_evidence_policy_type_invalid", "evidence qualification must use the canonical Protocol ABI declaration", path)]
    diagnostics: list[ValidationDiagnostic] = []
    if policy.numeric_scale != WEIGHT_SCALE:
        diagnostics.append(error("commit_numeric_scale_invalid", "commit numeric scale must use the v1 fixed-point scale", f"{path}.numeric_scale"))
    for name, value, minimum, maximum in (
        ("minimum_quality_ppm", policy.minimum_quality_ppm, 0, WEIGHT_SCALE),
        ("minimum_relevance_ppm", policy.minimum_relevance_ppm, 0, WEIGHT_SCALE),
        ("positive_group_cap", policy.positive_group_cap, 1, MAX_AUTHORITY_INTEGER),
        ("counter_group_cap", policy.counter_group_cap, 1, MAX_AUTHORITY_INTEGER),
        ("counter_weight_ppm", policy.counter_weight_ppm, 1, MAX_AUTHORITY_INTEGER),
        ("minimum_positive_evidence", policy.minimum_positive_evidence, 1, MAX_AUTHORITY_INTEGER),
        ("maximum_counterevidence", policy.maximum_counterevidence, 0, MAX_AUTHORITY_INTEGER),
        ("maximum_counterevidence_ratio_ppm", policy.maximum_counterevidence_ratio_ppm, 0, WEIGHT_SCALE),
        ("domain_contribution_floor", policy.domain_contribution_floor, 1, MAX_AUTHORITY_INTEGER),
        ("minimum_source_diversity", policy.minimum_source_diversity, 1, MAX_AUTHORITY_INTEGER),
        ("observation_ttl_steps", policy.observation_ttl_steps, 1, MAX_AUTHORITY_INTEGER),
    ):
        if not authority_integer_in_range(value, minimum, maximum):
            diagnostics.append(error("commit_evidence_numeric_invalid", f"{name} is outside the declared commit numeric bounds", f"{path}.{name}"))
    if not canonical_string_set(policy.required_challenge_categories, require_nonempty=True):
        diagnostics.append(error("commit_challenge_categories_invalid", "required challenge categories must be unique canonical strings", f"{path}.required_challenge_categories"))
    if policy.require_provenance is not True:
        diagnostics.append(error("commit_evidence_provenance_required", "commit evidence provenance cannot be disabled", f"{path}.require_provenance"))
    if policy.require_trace is not True:
        diagnostics.append(error("commit_evidence_trace_required", "commit evidence trace lineage cannot be disabled", f"{path}.require_trace"))
    return diagnostics


def validate_support_lease_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, SupportLeasePolicy):
        return [error("commit_support_policy_type_invalid", "support lease policy must use the canonical Protocol ABI declaration", path)]
    diagnostics: list[ValidationDiagnostic] = []
    for name, value, minimum, maximum in (
        ("minimum_support_clusters", policy.minimum_support_clusters, 1, MAX_AUTHORITY_INTEGER),
        ("support_ratio_ppm", policy.support_ratio_ppm, 1, WEIGHT_SCALE),
        ("lease_ttl_steps", policy.lease_ttl_steps, 1, MAX_AUTHORITY_INTEGER),
    ):
        if not authority_integer_in_range(value, minimum, maximum):
            diagnostics.append(error("commit_support_numeric_invalid", f"{name} is outside the declared commit numeric bounds", f"{path}.{name}"))
    for name, observed, required in (
        ("membership_mode", policy.membership_mode, "verified_snapshot_v1"),
        ("switch_mode", policy.switch_mode, "revoke_then_issue_v1"),
        ("equivocation_mode", policy.equivocation_mode, "exclude_conflicts_v1"),
    ):
        if observed != required:
            diagnostics.append(error("commit_support_semantics_invalid", f"{name} must use the normative v1 mode", f"{path}.{name}"))
    if policy.evidence_reference_required is not True:
        diagnostics.append(error("commit_support_evidence_reference_required", "support leases must reference qualified evidence", f"{path}.evidence_reference_required"))
    if policy.cluster_verification_required is not True:
        diagnostics.append(error("commit_support_cluster_verification_required", "support leases must use verified principal clusters", f"{path}.cluster_verification_required"))
    return diagnostics


def validate_commit_window_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, CommitWindowPolicy):
        return [error("commit_window_policy_type_invalid", "commit window policy must use the canonical Protocol ABI declaration", path)]
    diagnostics: list[ValidationDiagnostic] = []
    for name, value, minimum in (
        ("minimum_stability_steps", policy.minimum_stability_steps, 1),
        ("deliberation_deadline_steps", policy.deliberation_deadline_steps, 1),
        ("maximum_leader_resets", policy.maximum_leader_resets, 0),
        ("maximum_epoch_restarts", policy.maximum_epoch_restarts, 0),
        ("run_deadline_steps", policy.run_deadline_steps, 1),
    ):
        if not authority_integer_in_range(value, minimum, MAX_AUTHORITY_INTEGER):
            diagnostics.append(error("commit_window_numeric_invalid", f"{name} is outside the declared commit numeric bounds", f"{path}.{name}"))
    if set(policy.reset_rules) != set(REQUIRED_COMMIT_RESET_RULES) or not canonical_string_set(policy.reset_rules, require_nonempty=True):
        diagnostics.append(error("commit_window_reset_rules_invalid", "commit window reset rules must exactly cover every normative reset condition", f"{path}.reset_rules"))
    if authority_integer(policy.minimum_stability_steps) and authority_integer(policy.deliberation_deadline_steps) and policy.minimum_stability_steps > policy.deliberation_deadline_steps:
        diagnostics.append(error("commit_window_unreachable", "minimum stability cannot exceed the deliberation deadline", path))
    if authority_integer(policy.deliberation_deadline_steps) and authority_integer(policy.run_deadline_steps) and policy.deliberation_deadline_steps > policy.run_deadline_steps:
        diagnostics.append(error("commit_deadline_order_invalid", "deliberation deadline cannot exceed the absolute run deadline", path))
    return diagnostics


def validate_terminal_outcome_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, TerminalOutcomePolicy):
        return [error("commit_terminal_policy_type_invalid", "terminal outcome policy must use the canonical Protocol ABI declaration", path)]
    diagnostics: list[ValidationDiagnostic] = []
    if not canonical_nonblank_text(policy.safe_fallback_candidate):
        diagnostics.append(error("commit_fallback_invalid", "safe fallback candidate must be canonical and non-blank", f"{path}.safe_fallback_candidate"))
    if policy.deadline_outcome not in SUPPORTED_DEADLINE_OUTCOMES:
        diagnostics.append(error("commit_deadline_outcome_invalid", "deadline outcome must be safe_fallback or advisory", f"{path}.deadline_outcome"))
    if policy.policy_incomplete_outcome != "invalid":
        diagnostics.append(error("commit_policy_incomplete_outcome_invalid", "policy-incomplete runs must terminate as invalid", f"{path}.policy_incomplete_outcome"))
    if policy.finality_unavailable_outcome != "finality_unavailable":
        diagnostics.append(error("commit_finality_outcome_invalid", "missing finality must remain a typed finality_unavailable outcome", f"{path}.finality_unavailable_outcome"))
    for name, outcomes in (
        ("deliverable_outcomes", policy.deliverable_outcomes),
        ("publishable_outcomes", policy.publishable_outcomes),
        ("executable_outcomes", policy.executable_outcomes),
    ):
        if not canonical_string_set(outcomes) or not set(outcomes).issubset(SUPPORTED_TERMINAL_OUTCOMES):
            diagnostics.append(error("commit_terminal_outcomes_invalid", f"{name} must contain unique supported terminal outcomes", f"{path}.{name}"))
    if set(policy.deliverable_outcomes) != set(SUPPORTED_TERMINAL_OUTCOMES):
        diagnostics.append(error("commit_terminal_totality_incomplete", "every terminal outcome must remain deliverable", f"{path}.deliverable_outcomes"))
    if set(policy.publishable_outcomes) & NON_PUBLISHABLE_TERMINAL_OUTCOMES:
        diagnostics.append(error("commit_terminal_publication_unsafe", "invalid, finality-unavailable, and safety-violation outcomes cannot authorize publication", f"{path}.publishable_outcomes"))
    if not set(policy.executable_outcomes).issubset({"evidence_commit"}):
        diagnostics.append(error("commit_terminal_execution_unsafe", "only an evidence commit may be execution-eligible", f"{path}.executable_outcomes"))
    if assurance == "advisory" and (policy.publishable_outcomes or policy.executable_outcomes):
        diagnostics.append(error("commit_advisory_authority_invalid", "advisory assurance cannot authorize publication or execution", path))
    return diagnostics


def validate_certificate_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, CertificatePolicy):
        return [error("commit_certificate_policy_type_invalid", "certificate policy must use the canonical Protocol ABI declaration", path)]
    diagnostics: list[ValidationDiagnostic] = []
    if policy.mode not in SUPPORTED_CERTIFICATE_MODES:
        diagnostics.append(error("commit_certificate_mode_invalid", "certificate mode is unsupported", f"{path}.mode"))
    expected_mode = CERTIFICATE_MODE_BY_ASSURANCE.get(assurance)
    if expected_mode is not None and policy.mode != expected_mode:
        diagnostics.append(error("commit_certificate_assurance_mismatch", "certificate mode must exactly match the declared assurance", f"{path}.mode"))
    if policy.wire_version != COMMIT_WIRE_VERSION:
        diagnostics.append(error("commit_wire_version_unsupported", "commit wire version is unsupported", f"{path}.wire_version"))
    if policy.canonicalization != COMMIT_CANONICAL_VERSION:
        diagnostics.append(error("commit_canonical_version_unsupported", "commit canonicalization version is unsupported", f"{path}.canonicalization"))
    if policy.hash_algorithm != "sha256":
        diagnostics.append(error("commit_hash_algorithm_unsupported", "commit hash algorithm must be sha256", f"{path}.hash_algorithm"))
    requires_portable = assurance in {"certified", "distributed"}
    if policy.issuer_attestation_required is not requires_portable:
        diagnostics.append(error("commit_certificate_issuer_requirement_invalid", "issuer attestation requirement must match the assurance", f"{path}.issuer_attestation_required"))
    if policy.independent_verification_required is not requires_portable:
        diagnostics.append(error("commit_certificate_verification_requirement_invalid", "independent verification requirement must match the assurance", f"{path}.independent_verification_required"))
    return diagnostics


def validate_distributed_commit_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    if assurance != "distributed":
        if policy is not None:
            return [error("commit_distributed_policy_inactive", "distributed policy is only valid for distributed assurance", path)]
        return []
    if not isinstance(policy, DistributedCommitPolicy):
        return [error("commit_distributed_policy_required", "distributed assurance requires the complete distributed policy", path)]
    diagnostics: list[ValidationDiagnostic] = []
    if policy.fault_model != "byzantine_static_v1":
        diagnostics.append(error("commit_fault_model_invalid", "distributed commit must use the normative static Byzantine fault model", f"{path}.fault_model"))
    if policy.membership_mode != "static_epoch_verified_clusters_v1":
        diagnostics.append(error("commit_membership_mode_invalid", "distributed commit must use static epoch verified clusters", f"{path}.membership_mode"))
    if policy.conflict_rule != "freeze_v1":
        diagnostics.append(error("commit_conflict_rule_invalid", "distributed conflicts must freeze finality", f"{path}.conflict_rule"))
    if not canonical_nonblank_text(policy.epoch_transition_rule):
        diagnostics.append(error("commit_epoch_transition_rule_invalid", "epoch transition rule must be canonical and non-blank", f"{path}.epoch_transition_rule"))
    for name, value, minimum in (
        ("membership_size", policy.membership_size, 1),
        ("max_byzantine_faults", policy.max_byzantine_faults, 0),
        ("witness_quorum", policy.witness_quorum, 1),
        ("witness_ttl_steps", policy.witness_ttl_steps, 1),
        ("minimum_failure_domain_diversity", policy.minimum_failure_domain_diversity, 1),
    ):
        if not authority_integer_in_range(value, minimum, MAX_AUTHORITY_INTEGER):
            diagnostics.append(error("commit_distributed_numeric_invalid", f"{name} is outside the declared commit numeric bounds", f"{path}.{name}"))
    if all(authority_integer(value) for value in (policy.membership_size, policy.max_byzantine_faults, policy.witness_quorum)):
        n = policy.membership_size
        f = policy.max_byzantine_faults
        q = policy.witness_quorum
        if n < 3 * f + 1:
            diagnostics.append(error("commit_byzantine_membership_invalid", "membership must satisfy n >= 3f + 1", path))
        if q > n - f:
            diagnostics.append(error("commit_witness_quorum_too_large", "witness quorum must satisfy q <= n - f", path))
        if 2 * q - n <= f:
            diagnostics.append(error("commit_quorum_intersection_invalid", "witness quorum must satisfy 2q - n > f", path))
        if authority_integer(policy.minimum_failure_domain_diversity) and policy.minimum_failure_domain_diversity > q:
            diagnostics.append(error("commit_failure_domain_diversity_unreachable", "failure-domain diversity cannot exceed the witness quorum", f"{path}.minimum_failure_domain_diversity"))
    return diagnostics


def validate_risk_bands(
    policy: CollectiveCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if not isinstance(policy.risk_bands, Mapping) or set(policy.risk_bands) != set(SUPPORTED_RISK_BANDS):
        return [error("commit_risk_band_coverage_invalid", "risk policy must declare exactly LOW, MODERATE, HIGH, and CRITICAL", path)]
    evidence = policy.evidence_qualification
    support = policy.support_lease
    window = policy.commit_window
    terminal = policy.terminal_outcome
    previous: RiskBandPolicy | None = None
    for band_name in SUPPORTED_RISK_BANDS:
        band = policy.risk_bands[band_name]
        band_path = f"{path}.{band_name}"
        if not isinstance(band, RiskBandPolicy):
            diagnostics.append(error("commit_risk_band_type_invalid", "risk band must use the canonical Protocol ABI declaration", band_path))
            previous = None
            continue
        for name, value, minimum, maximum in (
            ("minimum_positive_evidence", band.minimum_positive_evidence, 1, MAX_AUTHORITY_INTEGER),
            ("maximum_counterevidence", band.maximum_counterevidence, 0, MAX_AUTHORITY_INTEGER),
            ("maximum_counterevidence_ratio_ppm", band.maximum_counterevidence_ratio_ppm, 0, WEIGHT_SCALE),
            ("minimum_support_clusters", band.minimum_support_clusters, 1, MAX_AUTHORITY_INTEGER),
            ("minimum_support_ratio_ppm", band.minimum_support_ratio_ppm, 1, WEIGHT_SCALE),
            ("minimum_source_diversity", band.minimum_source_diversity, 1, MAX_AUTHORITY_INTEGER),
            ("minimum_margin", band.minimum_margin, 1, MAX_AUTHORITY_INTEGER),
            ("stability_steps", band.stability_steps, 1, MAX_AUTHORITY_INTEGER),
        ):
            if not authority_integer_in_range(value, minimum, maximum):
                diagnostics.append(error("commit_risk_numeric_invalid", f"{name} is outside the declared commit numeric bounds", f"{band_path}.{name}"))
        if band.minimum_assurance not in SUPPORTED_COMMIT_ASSURANCES:
            diagnostics.append(error("commit_risk_assurance_invalid", "risk band minimum assurance is unsupported", f"{band_path}.minimum_assurance"))
        if not canonical_string_set(band.required_challenge_categories, require_nonempty=True):
            diagnostics.append(error("commit_risk_challenges_invalid", "risk band challenge categories must be unique canonical strings", f"{band_path}.required_challenge_categories"))
        for name, outcomes in (
            ("publishable_outcomes", band.publishable_outcomes),
            ("executable_outcomes", band.executable_outcomes),
        ):
            if not canonical_string_set(outcomes) or not set(outcomes).issubset(SUPPORTED_TERMINAL_OUTCOMES):
                diagnostics.append(error("commit_risk_outcomes_invalid", f"{name} must contain unique supported outcomes", f"{band_path}.{name}"))

        if isinstance(evidence, EvidenceQualificationPolicy):
            if band.minimum_positive_evidence < evidence.minimum_positive_evidence or band.maximum_counterevidence > evidence.maximum_counterevidence or band.maximum_counterevidence_ratio_ppm > evidence.maximum_counterevidence_ratio_ppm or band.minimum_source_diversity < evidence.minimum_source_diversity or not set(band.required_challenge_categories).issuperset(evidence.required_challenge_categories):
                diagnostics.append(error("commit_risk_evidence_weakened", "risk band cannot weaken the evidence qualification baseline", band_path))
        if isinstance(support, SupportLeasePolicy) and (band.minimum_support_clusters < support.minimum_support_clusters or band.minimum_support_ratio_ppm < support.support_ratio_ppm):
            diagnostics.append(error("commit_risk_support_weakened", "risk band cannot weaken the support lease baseline", band_path))
        if isinstance(window, CommitWindowPolicy):
            if band.stability_steps < window.minimum_stability_steps:
                diagnostics.append(error("commit_risk_window_weakened", "risk band cannot weaken the stability baseline", f"{band_path}.stability_steps"))
            if band.stability_steps > window.deliberation_deadline_steps:
                diagnostics.append(error("commit_risk_window_unreachable", "risk-band stability cannot exceed the deliberation deadline", f"{band_path}.stability_steps"))
        if isinstance(terminal, TerminalOutcomePolicy):
            if not set(band.publishable_outcomes).issubset(terminal.publishable_outcomes) or not set(band.executable_outcomes).issubset(terminal.executable_outcomes):
                diagnostics.append(error("commit_risk_action_ceiling_exceeded", "risk-band action outcomes must stay inside the terminal policy ceiling", band_path))
        if not set(band.executable_outcomes).issubset({"evidence_commit"}):
            diagnostics.append(error("commit_risk_execution_unsafe", "risk bands may execute only an evidence commit", f"{band_path}.executable_outcomes"))

        if previous is not None:
            weaker_minimum = any(
                current < prior
                for current, prior in (
                    (band.minimum_positive_evidence, previous.minimum_positive_evidence),
                    (band.minimum_support_clusters, previous.minimum_support_clusters),
                    (band.minimum_support_ratio_ppm, previous.minimum_support_ratio_ppm),
                    (band.minimum_source_diversity, previous.minimum_source_diversity),
                    (band.minimum_margin, previous.minimum_margin),
                    (band.stability_steps, previous.stability_steps),
                )
            )
            weaker_maximum = band.maximum_counterevidence > previous.maximum_counterevidence or band.maximum_counterevidence_ratio_ppm > previous.maximum_counterevidence_ratio_ppm
            weaker_challenge = not set(band.required_challenge_categories).issuperset(previous.required_challenge_categories)
            weaker_assurance = COMMIT_ASSURANCE_ORDER.get(band.minimum_assurance, -1) < COMMIT_ASSURANCE_ORDER.get(previous.minimum_assurance, -1)
            expanded_actions = not set(band.publishable_outcomes).issubset(previous.publishable_outcomes) or not set(band.executable_outcomes).issubset(previous.executable_outcomes)
            if weaker_minimum or weaker_maximum or weaker_challenge or weaker_assurance or expanded_actions:
                diagnostics.append(error("commit_risk_monotonicity_invalid", "risk thresholds, assurance, challenges, and action authority must strengthen monotonically", band_path))
        previous = band
    return diagnostics


def authority_integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_AUTHORITY_INTEGER


def authority_integer_in_range(value: object, minimum: int, maximum: int) -> bool:
    return authority_integer(value) and minimum <= value <= maximum


def canonical_nonblank_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and value == unicodedata.normalize("NFC", value)
    )


def canonical_string_set(value: object, *, require_nonempty: bool = False) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    if require_nonempty and not value:
        return False
    values = list(value)
    return all(canonical_nonblank_text(item) for item in values) and len(values) == len(set(values))


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
