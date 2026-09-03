from __future__ import annotations

from math import isclose

from pheroos.conformance.checks._manifest import (
    active_target,
    candidate_set,
    exercise_candidate_id,
    target_candidate_ids,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    CandidateSet,
    LayerCoordinationPolicy,
    LayerCoordinationState,
    LayerPerformanceSnapshot,
    LayerProposal,
    evaluate_layer_coordination,
    layer_action_effect,
    layer_coordination_policy_from_collective,
    validate_layer_proposal,
)
from pheroos.governance.layer_coordination import materialize_layer_pheromone_proposals
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import SUPPORTED_LAYER_ACTIONS
from pheroos.protocol.models import (
    CapabilityManifest,
    CollectiveDecisionPolicy,
    collective_fallback_id,
    has_hybrid_pheromone_features,
)


BUILTIN_ACTION_EFFECTS = {
    "support": ("learned", "candidate_preference", "positive"),
    "prefer_candidate": ("learned", "candidate_preference", "positive"),
    "route_preference": ("learned", "candidate_preference", "positive"),
    "risk": ("learned", "candidate_risk_pressure", "negative"),
    "alarm": ("reactive", "reactive_emergency_pressure", "negative"),
    "cautionary": ("reactive", "reactive_emergency_pressure", "negative"),
    "request_scouting": ("learned", "scouting_required", "zero"),
    "fallback_pressure": ("reactive", "fallback_required", "zero"),
    "confirm_trace_coverage": ("metacognitive", "trace_coverage_confirmed", "zero"),
    "resolve_conflict": (
        "metacognitive",
        "metacognitive_conflict_resolution_proposed",
        "positive",
    ),
    "propose_pheromone": (
        "evolutionary",
        "bounded_pheromone_deposit_proposed",
        "zero",
    ),
}


def check(manifest: CapabilityManifest) -> CheckResult:
    collective_policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(collective_policy):
        return CheckResult("layer_coordination_policy", True)
    if collective_policy is None:
        return CheckResult("layer_coordination_policy", False, "collective_policy")
    try:
        problems = layer_coordination_problems(manifest)
    except Exception as exc:  # total-function boundary for direct check consumers
        detail = str(exc).strip()
        return CheckResult(
            "layer_coordination_policy",
            False,
            f"exercise:{type(exc).__name__}" + (f":{detail}" if detail else ""),
        )
    return CheckResult("layer_coordination_policy", not problems, ", ".join(problems))


def layer_coordination_problems(manifest: CapabilityManifest) -> list[str]:
    collective_policy = manifest.protocol.collective_decision_policy
    if collective_policy is None:
        return ["collective_policy"]
    problems = declared_policy_problems(collective_policy)
    if problems:
        return problems
    target = active_target(manifest)
    fallback_id = collective_fallback_id(manifest.protocol)
    candidates = candidate_set(manifest)
    primary = exercise_candidate_id(manifest)
    if primary is None:
        return ["active_target_candidates"]
    secondary = next(
        (
            candidate_id
            for candidate_id in target_candidate_ids(manifest)
            if candidate_id != primary and candidate_id != fallback_id
        ),
        None,
    )
    policy = layer_coordination_policy_from_collective(collective_policy)

    problems.extend(
        builtin_action_problems(
            collective_policy=collective_policy,
            policy=policy,
            candidates=candidates,
            target=target,
            primary=primary,
            fallback_id=fallback_id,
        )
    )
    problems.extend(
        coordination_interaction_problems(
            policy=policy,
            candidates=candidates,
            target=target,
            primary=primary,
            secondary=secondary,
            fallback_id=fallback_id,
        )
    )
    problems.extend(
        snapshot_weight_problems(
            policy=policy,
            candidates=candidates,
            target=target,
            primary=primary,
            fallback_id=fallback_id,
        )
    )

    try:
        validate_layer_proposal(
            LayerProposal(
                layer_id="learned",
                source_id="layer:bad",
                target=target,
                candidate_id=primary,
                action="support",
                confidence=action_confidence(policy, "learned"),
            ),
            candidate_set=candidates,
            target=target,
        )
    except GovernanceError:
        pass
    else:
        problems.append("lineage_required")
    return problems


def builtin_action_problems(
    *,
    collective_policy: CollectiveDecisionPolicy,
    policy: LayerCoordinationPolicy,
    candidates: CandidateSet,
    target: str,
    primary: str,
    fallback_id: str,
) -> list[str]:
    problems: list[str] = []
    observed: set[str] = set()
    if set(BUILTIN_ACTION_EFFECTS) != set(SUPPORTED_LAYER_ACTIONS):
        problems.append("builtin_action_contract")
    for action, (
        layer_id,
        expected_effect,
        expected_sign,
    ) in BUILTIN_ACTION_EFFECTS.items():
        item = action_proposal(
            action,
            layer_id=layer_id,
            candidate_id=primary,
            target=target,
            policy=policy,
            collective_policy=collective_policy,
        )
        validate_layer_proposal(item, candidate_set=candidates, target=target)
        effect = layer_action_effect(item, policy)
        state = evaluate_layer_coordination(
            candidate_set=candidates,
            target=target,
            policy=policy,
            fallback_candidate_id=fallback_id,
            proposals=[item],
        )
        observed.add(action)
        problems.extend(
            _action_state_problems(
                action=action,
                layer_id=layer_id,
                effect=effect,
                expected_effect=expected_effect,
                expected_sign=expected_sign,
                primary=primary,
                item=item,
                state=state,
            )
        )
        problems.extend(
            _action_interaction_problems(
                action=action,
                primary=primary,
                item=item,
                state=state,
                candidates=candidates,
                target=target,
                policy=policy,
            )
        )
    if observed != set(BUILTIN_ACTION_EFFECTS):
        problems.append("builtin_action_coverage")
    return problems


def _action_state_problems(
    *,
    action: str,
    layer_id: str,
    effect: str,
    expected_effect: str,
    expected_sign: str,
    primary: str,
    item: LayerProposal,
    state: LayerCoordinationState,
) -> list[str]:
    problems: list[str] = []
    if (
        effect != expected_effect
        or state.action_effects.get(item.trace_event_id) != expected_effect
    ):
        problems.append(f"action_effect:{action}")
    if item.trace_event_id not in state.trace_lineage:
        problems.append(f"action_lineage:{action}")
    category = f"layer_{layer_id}"
    score = float(state.score_breakdown[primary][category])
    weight = float(state.allocated_weights.get(layer_id, 0.0))
    if expected_sign == "positive" and weight > 0 and score <= 0:
        problems.append(f"action_score:{action}")
    elif expected_sign == "negative" and weight > 0 and score >= 0:
        problems.append(f"action_score:{action}")
    elif expected_sign == "zero" and not isclose(score, 0.0, abs_tol=1e-9):
        problems.append(f"action_score:{action}")
    return problems


def _action_interaction_problems(
    *,
    action: str,
    primary: str,
    item: LayerProposal,
    state: LayerCoordinationState,
    candidates: CandidateSet,
    target: str,
    policy: LayerCoordinationPolicy,
) -> list[str]:
    problems: list[str] = []
    if action == "request_scouting" and "scouting_requested" not in state.conflicts:
        problems.append("action_conflict:request_scouting")
    if action == "fallback_pressure" and "fallback_pressure" not in state.conflicts:
        problems.append("action_conflict:fallback_pressure")
    if (
        action in {"alarm", "cautionary"}
        and "reactive_emergency_pressure" not in state.conflicts
    ):
        problems.append(f"action_conflict:{action}")
    if (
        action == "confirm_trace_coverage"
        and state.trace_coverage_confirmations.get(primary) != item.confidence
    ):
        problems.append("action_confirmation:confirm_trace_coverage")
    if action == "propose_pheromone":
        problems.extend(
            _pheromone_materialization_problems(
                primary=primary,
                item=item,
                candidates=candidates,
                target=target,
                policy=policy,
            )
        )
    return problems


def _pheromone_materialization_problems(
    *,
    primary: str,
    item: LayerProposal,
    candidates: CandidateSet,
    target: str,
    policy: LayerCoordinationPolicy,
) -> list[str]:
    trails = materialize_layer_pheromone_proposals(
        proposals=[item],
        candidate_set=candidates,
        target=target,
        current_step=1,
        policy=policy,
    )
    expected_strength = item.proposed_strength * item.confidence
    if (
        len(trails) != 1
        or trails[0].trace_event_id != item.trace_event_id
        or trails[0].candidate_id != primary
        or trails[0].kind != "positive"
        or not isclose(trails[0].strength, expected_strength, abs_tol=1e-9)
    ):
        return ["action_materialization:propose_pheromone"]
    return []


def coordination_interaction_problems(
    *,
    policy: LayerCoordinationPolicy,
    candidates: CandidateSet,
    target: str,
    primary: str,
    secondary: str | None,
    fallback_id: str,
) -> list[str]:
    problems: list[str] = []
    all_layers = ("reactive", "learned", "evolutionary", "metacognitive")
    coverage = evaluate_layer_coordination(
        candidate_set=candidates,
        target=target,
        policy=policy,
        fallback_candidate_id=fallback_id,
        proposals=[
            action_proposal(
                "support",
                layer_id=layer_id,
                candidate_id=primary,
                target=target,
                policy=policy,
            )
            for layer_id in all_layers
        ],
    )
    if set(coverage.confidences) != set(all_layers):
        problems.append("layer_coverage")

    confirmation = action_proposal(
        "confirm_trace_coverage",
        layer_id="metacognitive",
        candidate_id=primary,
        target=target,
        policy=policy,
    )
    learned = action_proposal(
        "prefer_candidate",
        layer_id="learned",
        candidate_id=primary,
        target=target,
        policy=policy,
    )
    confirmed = evaluate_layer_coordination(
        candidate_set=candidates,
        target=target,
        policy=policy,
        fallback_candidate_id=fallback_id,
        proposals=[learned, confirmation],
        snapshots=[
            LayerPerformanceSnapshot(
                "learned",
                recent_success_rate=1.0,
                mean_confidence=1.0,
                evidence_coverage=1.0,
                trace_coverage=0.0,
            )
        ],
    )
    if confirmed.trace_coverage_confirmations.get(primary) != confirmation.confidence:
        problems.append("trace_coverage_interaction")

    if secondary is not None:
        left = action_proposal(
            "prefer_candidate",
            layer_id="learned",
            candidate_id=primary,
            target=target,
            policy=policy,
            suffix="conflict-left",
        )
        right = action_proposal(
            "prefer_candidate",
            layer_id="evolutionary",
            candidate_id=secondary,
            target=target,
            policy=policy,
            suffix="conflict-right",
        )
        resolver = action_proposal(
            "resolve_conflict",
            layer_id="metacognitive",
            candidate_id=primary,
            target=target,
            policy=policy,
            suffix="conflict-resolver",
        )
        proposals = [left, right, resolver]
        for index in range(max(0, int(policy.min_layer_provenance) - len(proposals))):
            proposals.append(
                action_proposal(
                    "confirm_trace_coverage",
                    layer_id="metacognitive",
                    candidate_id=primary,
                    target=target,
                    policy=policy,
                    suffix=f"provenance:{index}",
                )
            )
        resolved = evaluate_layer_coordination(
            candidate_set=candidates,
            target=target,
            policy=policy,
            fallback_candidate_id=fallback_id,
            proposals=proposals,
        )
        resolver_has_weight = (
            float(resolved.allocated_weights.get("metacognitive", 0.0)) > 0.0
        )
        resolution_matches = (
            not resolved.fallback_used
            and resolved.selected_candidate == primary
            and resolved.resolution == "metacognitive_conflict_resolution"
            if resolver_has_weight
            else resolved.fallback_used
            and resolved.selected_candidate == fallback_id
            and resolved.resolution == "safe_fallback_for_layer_conflict"
        )
        if (
            "candidate_support_conflict" not in resolved.conflicts
            or not resolution_matches
        ):
            problems.append("resolve_conflict_interaction")
    return problems


def snapshot_weight_problems(
    *,
    policy: LayerCoordinationPolicy,
    candidates: CandidateSet,
    target: str,
    primary: str,
    fallback_id: str,
) -> list[str]:
    """Prove every performance metric participates in bounded allocation."""

    problems: list[str] = []
    layers = ("reactive", "learned", "evolutionary", "metacognitive")
    worst_values = {
        "recent_success_rate": 0.0,
        "recent_conflict_rate": 1.0,
        "recent_fallback_rate": 1.0,
        "mean_confidence": 0.0,
        "evidence_coverage": 0.0,
        "trace_coverage": 0.0,
    }
    favorable_values = {
        "recent_success_rate": 1.0,
        "recent_conflict_rate": 0.0,
        "recent_fallback_rate": 0.0,
        "mean_confidence": 1.0,
        "evidence_coverage": 1.0,
        "trace_coverage": 1.0,
    }
    for layer_id in layers:
        item = action_proposal(
            "support",
            layer_id=layer_id,
            candidate_id=primary,
            target=target,
            policy=policy,
            suffix=f"snapshot:{layer_id}",
        )

        def allocated(snapshot: LayerPerformanceSnapshot | None) -> float:
            state = evaluate_layer_coordination(
                candidate_set=candidates,
                target=target,
                policy=policy,
                fallback_candidate_id=fallback_id,
                proposals=[item],
                snapshots=[] if snapshot is None else [snapshot],
            )
            return float(state.allocated_weights[layer_id])

        base = float(policy.default_layer_weights.get(layer_id, 1.0))
        lower, upper = policy.layer_weight_bounds.get(
            layer_id,
            (0.0, max(1.0, base)),
        )
        lower = float(lower)
        upper = float(upper)

        baseline = allocated(None)
        expected_baseline = min(upper, max(lower, base))
        if not isclose(baseline, expected_baseline, abs_tol=1e-9):
            problems.append(f"snapshot_baseline_weight:{layer_id}")

        worst = LayerPerformanceSnapshot(layer_id, **worst_values)
        worst_weight = allocated(worst)
        expected_worst = min(upper, max(lower, base * 0.5))
        if not isclose(worst_weight, expected_worst, abs_tol=1e-9):
            problems.append(f"snapshot_lower_clamp:{layer_id}")

        best = LayerPerformanceSnapshot(layer_id, **favorable_values)
        best_weight = allocated(best)
        expected_best = min(upper, max(lower, base * 1.5))
        if not isclose(best_weight, expected_best, abs_tol=1e-9):
            problems.append(f"snapshot_upper_clamp:{layer_id}")

        for field_name, favorable in favorable_values.items():
            values = dict(worst_values)
            values[field_name] = favorable
            snapshot = LayerPerformanceSnapshot(layer_id, **values)
            quality = (
                values["recent_success_rate"]
                + 1.0
                - values["recent_conflict_rate"]
                + 1.0
                - values["recent_fallback_rate"]
                + values["mean_confidence"]
                + values["evidence_coverage"]
                + values["trace_coverage"]
            ) / 6.0
            expected = min(upper, max(lower, base * (0.5 + quality)))
            if not isclose(allocated(snapshot), expected, abs_tol=1e-9):
                problems.append(f"snapshot_metric_weight:{layer_id}:{field_name}")
    return problems


def action_confidence(
    policy: LayerCoordinationPolicy,
    layer_id: str,
    *,
    emergency: bool = False,
) -> float:
    thresholds = [float(policy.confidence_thresholds.get(layer_id, 0.0)), 0.9]
    if emergency:
        thresholds.append(float(policy.emergency_override_threshold))
    return min(1.0, max(thresholds))


def action_proposal(
    action: str,
    *,
    layer_id: str,
    candidate_id: str,
    target: str,
    policy: LayerCoordinationPolicy,
    collective_policy: CollectiveDecisionPolicy | None = None,
    suffix: str = "exercise",
) -> LayerProposal:
    confidence = action_confidence(
        policy,
        layer_id,
        emergency=action in {"alarm", "cautionary"},
    )
    support = (
        1.0
        if action
        in {"support", "prefer_candidate", "route_preference", "resolve_conflict"}
        else 0.0
    )
    risk = 1.0 if action in {"risk", "alarm", "cautionary"} else 0.0
    proposed_kind = action if action in {"alarm", "cautionary"} else ""
    proposed_strength = 1.0 if action in {"alarm", "cautionary"} else 0.0
    if action == "propose_pheromone":
        proposed_kind = "positive"
        if collective_policy is None:
            proposed_strength = 1.0
        else:
            proposed_strength = min(
                1.0,
                float(collective_policy.pheromone_max_strength),
                float(collective_policy.pheromone_per_source_cap),
                float(collective_policy.pheromone_per_round_deposit_cap),
            )
    identity = f"{action}:{layer_id}:{suffix}"
    return LayerProposal(
        layer_id=layer_id,
        source_id=f"source:{identity}",
        target=target,
        candidate_id=candidate_id,
        action=action,
        confidence=confidence,
        support=support,
        risk=risk,
        proposed_pheromone_kind=proposed_kind,
        proposed_strength=proposed_strength,
        evidence_id=f"evidence:{identity}",
        provenance=f"conformance:{identity}",
        trace_event_id=f"trace:{identity}",
    )


def declared_policy_problems(policy: CollectiveDecisionPolicy) -> list[str]:
    problems: list[str] = []
    if policy.layer_min_provenance <= 0:
        problems.append("min_layer_provenance")
    if (
        policy.layer_conflict_threshold < 0
        or policy.layer_emergency_override_threshold < 0
    ):
        problems.append("thresholds")
    for layer_id, weight in policy.layer_default_weights.items():
        if layer_id not in {"reactive", "learned", "evolutionary", "metacognitive"}:
            problems.append("layer_id")
        if weight < 0:
            problems.append("weights")
    for layer_id, bounds in policy.layer_weight_bounds.items():
        lower, upper = bounds
        if layer_id not in {"reactive", "learned", "evolutionary", "metacognitive"}:
            problems.append("layer_id")
        if lower < 0 or upper < 0 or lower > upper:
            problems.append("bounds")
    return sorted(set(problems))
