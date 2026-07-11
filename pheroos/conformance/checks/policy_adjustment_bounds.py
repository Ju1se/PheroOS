from __future__ import annotations

from collections.abc import Mapping
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    PolicyAdjustmentProposal,
    apply_policy_adjustment_overlay,
    validate_policy_adjustment_proposal,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import CapabilityManifest, has_hybrid_pheromone_features


SAFETY_CRITICAL_FIELDS = frozenset(
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


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(policy):
        return CheckResult("policy_adjustment_bounds", True)
    bounds = dict(policy.policy_adjustment_bounds if policy is not None else {})
    problems = []
    unsafe = sorted(set(bounds) & SAFETY_CRITICAL_FIELDS)
    if unsafe:
        problems.append("unsafe:" + ",".join(unsafe))
    if bounds:
        try:
            validate_policy_adjustment_proposal(proposal({"unbounded_field": 0}), policy)
        except GovernanceError:
            rejects_unbounded = True
        else:
            rejects_unbounded = False
        for key in sorted(bounds):
            accepted_value = accepted_value_for(bounds[key])
            try:
                overlay = validate_policy_adjustment_proposal(proposal({key: accepted_value}), policy)
            except GovernanceError:
                problems.append(f"bounded_rejected:{key}")
            else:
                if dict(overlay) != {key: accepted_value}:
                    problems.append(f"overlay_mismatch:{key}")
                else:
                    effective = apply_policy_adjustment_overlay(policy, overlay)
                    if not effective_adjustment_applied(effective, key, accepted_value):
                        problems.append(f"effective_policy_mismatch:{key}")
            rejected_value = rejected_value_for(bounds[key])
            try:
                validate_policy_adjustment_proposal(proposal({key: rejected_value}), policy)
            except GovernanceError:
                pass
            else:
                problems.append(f"out_of_bounds_accepted:{key}")
        if not rejects_unbounded:
            problems.append("unbounded_accepted")
    else:
        try:
            validate_policy_adjustment_proposal(
                proposal({"pheromone_evaporation_rate": 0.1}),
                policy,
            )
        except GovernanceError:
            rejects_when_undeclared = True
        else:
            rejects_when_undeclared = False
        if not rejects_when_undeclared:
            problems.append("undeclared_adjustment_accepted")
    return CheckResult("policy_adjustment_bounds", not problems, ", ".join(problems))


def proposal(adjustments: dict[str, object]) -> PolicyAdjustmentProposal:
    return PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="layer:evolutionary",
        adjustments=adjustments,
        provenance="runtime:evolutionary",
        trace_event_id="trace:policy-adjustment",
    )


def accepted_value_for(bounds: object) -> object:
    if isinstance(bounds, list) and len(bounds) == 2:
        return bounds[0]
    if isinstance(bounds, tuple) and len(bounds) == 2:
        return bounds[0]
    if isinstance(bounds, Mapping) and "allowed_values" in bounds:
        return bounds["allowed_values"][0]
    if isinstance(bounds, Mapping) and "min" in bounds:
        return bounds["min"]
    return 0


def rejected_value_for(bounds: object) -> object:
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        return float(bounds[1]) + 1
    if isinstance(bounds, Mapping) and "allowed_values" in bounds:
        return "unsupported"
    if isinstance(bounds, Mapping) and "max" in bounds:
        return float(bounds["max"]) + 1
    return object()


def effective_adjustment_applied(policy: object, key: str, expected: object) -> bool:
    """Prove every declared adjustment reaches its owned effective policy field."""

    scalar_fields = {
        "pheromone_evaporation_rate": "pheromone_evaporation_rate",
        "pheromone_response_model": "pheromone_response_model",
        "pheromone_exploration_floor": "pheromone_exploration_floor",
        "pheromone_cautionary_override_threshold": "pheromone_cautionary_override_threshold",
        "layer_emergency_override_threshold": "layer_emergency_override_threshold",
    }
    if key in scalar_fields and getattr(policy, scalar_fields[key], object()) != expected:
        return False
    kind_fields = {
        "pheromone_positive_weight": ("positive", "pheromone_positive_weight"),
        "pheromone_negative_weight": ("negative", "pheromone_negative_weight"),
        "pheromone_cautionary_weight": ("cautionary", "pheromone_cautionary_weight"),
        "pheromone_alarm_weight": ("alarm", None),
        "pheromone_novelty_weight": ("novelty", "pheromone_novelty_weight"),
    }
    if key in kind_fields:
        kind, scalar = kind_fields[key]
        profile = policy.pheromone_kind_profiles.get(kind)
        if profile is None or profile.weight != float(expected):
            return False
        if scalar is not None and getattr(policy, scalar) != expected:
            return False
    layer_fields = {
        "layer_learned_weight": "learned",
        "layer_evolutionary_weight": "evolutionary",
        "layer_metacognitive_weight": "metacognitive",
    }
    if key in layer_fields and policy.layer_default_weights.get(layer_fields[key]) != float(expected):
        return False
    if key == "pheromone_evaporation_rate" and any(
        profile.evaporation_rate != float(expected)
        for profile in policy.pheromone_kind_profiles.values()
    ):
        return False
    if key == "pheromone_response_model" and any(
        profile.response_model != expected
        for profile in policy.pheromone_kind_profiles.values()
    ):
        return False
    return key in scalar_fields or key in kind_fields or key in layer_fields
