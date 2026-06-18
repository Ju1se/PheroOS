from __future__ import annotations

from pheroos.protocol.extensions import secret_like_paths
from pheroos.protocol.models import (
    SUPPORTED_COLLECTIVE_MODES,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    CapabilityManifest,
    ValidationDiagnostic,
    collective_fallback_id,
    is_swarm_policy,
    required_swarm_trace_events,
)


def validate_capability_manifest(manifest: CapabilityManifest) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    protocol = manifest.protocol
    target_ids = {target.id for target in protocol.targets}
    candidate_ids = {candidate.id for candidate in protocol.candidates}
    safe_candidates = {candidate.id for candidate in protocol.candidates if candidate.safe_fallback}

    for secret_path in secret_like_paths(manifest):
        diagnostics.append(error("secret_like_manifest_field", "manifest must not contain secret-like fields", secret_path))

    if not protocol.targets:
        diagnostics.append(error("missing_targets", "protocol must declare at least one target", "protocol.targets"))
    if not protocol.candidates:
        diagnostics.append(error("missing_candidates", "protocol must declare at least one candidate", "protocol.candidates"))

    for candidate in protocol.candidates:
        if candidate.target not in target_ids:
            diagnostics.append(error("candidate_target_missing", f"candidate {candidate.id} references undeclared target", "protocol.candidates"))

    if protocol.quorum_policy.target not in target_ids:
        diagnostics.append(error("quorum_target_missing", "quorum target must be declared", "protocol.quorum_policy.target"))
    if protocol.quorum_policy.fallback_candidate not in candidate_ids:
        diagnostics.append(error("quorum_fallback_missing", "quorum fallback candidate must be declared", "protocol.quorum_policy.fallback_candidate"))
    if protocol.quorum_policy.fallback_candidate and protocol.quorum_policy.fallback_candidate not in safe_candidates:
        diagnostics.append(error("quorum_fallback_not_safe", "quorum fallback candidate must be marked safe_fallback", "protocol.quorum_policy.fallback_candidate"))

    collective_policy = protocol.collective_decision_policy
    if collective_policy is not None:
        if collective_policy.mode not in SUPPORTED_COLLECTIVE_MODES:
            diagnostics.append(error("collective_mode_unsupported", "collective decision mode is unsupported", "protocol.collective_decision_policy.mode"))
        if collective_policy.min_independent_scouts <= 0:
            diagnostics.append(error("collective_min_scouts_invalid", "min_independent_scouts must be positive", "protocol.collective_decision_policy.min_independent_scouts"))
        if collective_policy.quorum_threshold <= 0:
            diagnostics.append(error("collective_quorum_threshold_invalid", "quorum_threshold must be positive", "protocol.collective_decision_policy.quorum_threshold"))
        if not 0 <= collective_policy.pheromone_evaporation_rate <= 1:
            diagnostics.append(error("collective_pheromone_evaporation_invalid", "pheromone evaporation rate must be between 0 and 1", "protocol.collective_decision_policy.pheromone_evaporation_rate"))
        if collective_policy.pheromone_decay_model not in SUPPORTED_PHEROMONE_DECAY_MODELS:
            diagnostics.append(error("collective_pheromone_decay_model_invalid", "pheromone decay model is unsupported", "protocol.collective_decision_policy.pheromone_decay_model"))
        if collective_policy.pheromone_min_strength > collective_policy.pheromone_max_strength:
            diagnostics.append(error("collective_pheromone_strength_bounds_invalid", "pheromone min strength must not exceed max strength", "protocol.collective_decision_policy"))
        if (
            collective_policy.pheromone_positive_weight < 0
            or collective_policy.pheromone_negative_weight < 0
            or collective_policy.pheromone_cautionary_weight < 0
            or collective_policy.pheromone_novelty_weight < 0
        ):
            diagnostics.append(error("collective_pheromone_weight_invalid", "pheromone weights must be non-negative", "protocol.collective_decision_policy"))
        if collective_policy.pheromone_cautionary_override_threshold < 0:
            diagnostics.append(error("collective_pheromone_cautionary_threshold_invalid", "pheromone cautionary override threshold must be non-negative", "protocol.collective_decision_policy.pheromone_cautionary_override_threshold"))
        if collective_policy.pheromone_per_source_cap < 0 or collective_policy.pheromone_per_round_deposit_cap < 0:
            diagnostics.append(error("collective_pheromone_cap_invalid", "pheromone caps must be non-negative", "protocol.collective_decision_policy"))
        if collective_policy.pheromone_min_source_diversity <= 0:
            diagnostics.append(error("collective_pheromone_source_diversity_invalid", "pheromone min source diversity must be positive", "protocol.collective_decision_policy.pheromone_min_source_diversity"))
        fallback_candidate = collective_fallback_id(protocol)
        if fallback_candidate not in candidate_ids:
            diagnostics.append(error("collective_fallback_missing", "collective fallback candidate must be declared", "protocol.collective_decision_policy.fallback_candidate"))
        elif fallback_candidate not in safe_candidates:
            diagnostics.append(error("collective_fallback_not_safe", "collective fallback candidate must be marked safe_fallback", "protocol.collective_decision_policy.fallback_candidate"))
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

    if protocol.output_policy.writer_may_create_facts:
        diagnostics.append(error("writer_fact_creation", "output policy must not allow writer fact creation", "protocol.output_policy"))

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
