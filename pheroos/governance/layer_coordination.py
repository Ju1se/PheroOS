from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, cast

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.pheromone import (
    SUPPORTED_PHEROMONE_KINDS,
    SUPPORTED_PHEROMONE_SUBJECT_TYPES,
    PheromoneNeighborhood,
    PheromoneTrail,
    add_breakdown,
    empty_score_breakdown,
    is_extension_pheromone_value,
    validate_pheromone_subject_binding,
    validate_pheromone_topology,
)
from pheroos.protocol.models import CollectiveDecisionPolicy, deep_freeze


SUPPORTED_LAYER_IDS = frozenset(
    {"reactive", "learned", "evolutionary", "metacognitive"}
)
SUPPORTED_LAYER_ACTIONS = frozenset(
    {
        "support",
        "prefer_candidate",
        "route_preference",
        "risk",
        "alarm",
        "cautionary",
        "request_scouting",
        "fallback_pressure",
        "confirm_trace_coverage",
        "resolve_conflict",
        "propose_pheromone",
    }
)
LAYER_ACTION_EXTENSION_PREFIXES = ("x-", "ext.")
PREFERENCE_ACTIONS = frozenset({"support", "prefer_candidate", "route_preference"})
EMERGENCY_ACTIONS = frozenset({"alarm", "cautionary"})
NON_SCORING_ACTIONS = frozenset(
    {
        "request_scouting",
        "fallback_pressure",
        "confirm_trace_coverage",
        "propose_pheromone",
    }
)
MAX_LAYER_MAGNITUDE = 10.0


@dataclass(frozen=True)
class LayerProposal:
    layer_id: str
    source_id: str
    target: str
    candidate_id: str
    action: str
    confidence: float
    support: float = 0.0
    risk: float = 0.0
    proposed_pheromone_kind: str = ""
    proposed_strength: float = 0.0
    evidence_id: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metadata",
            deep_freeze(self.metadata),
        )

    def __deepcopy__(self, memo: dict[int, object]) -> LayerProposal:
        del memo
        return self


@dataclass(frozen=True)
class StrategyBias:
    # The first five fields preserve the draft ABI positional constructor.
    layer_id: str
    candidate_id: str
    support: float = 0.0
    provenance: str = ""
    trace_event_id: str = ""
    target: str = ""
    source_id: str = ""
    confidence: float = 1.0
    evidence_id: str = ""


@dataclass(frozen=True)
class LayerPerformanceSnapshot:
    layer_id: str
    recent_success_rate: float = 0.0
    recent_conflict_rate: float = 0.0
    recent_fallback_rate: float = 0.0
    mean_confidence: float = 0.0
    evidence_coverage: float = 0.0
    trace_coverage: float = 0.0


@dataclass(frozen=True)
class LayerCoordinationPolicy:
    enabled: bool = False
    layer_weight_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    default_layer_weights: dict[str, float] = field(default_factory=dict)
    confidence_thresholds: dict[str, float] = field(default_factory=dict)
    conflict_threshold: float = 0.0
    emergency_override_threshold: float = 0.0
    min_layer_provenance: int = 1
    fallback_on_unresolved_conflict: bool = True
    policy_adjustment_bounds: dict[str, Any] = field(default_factory=dict)
    max_strategy_bias: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "layer_weight_bounds",
            deep_freeze(self.layer_weight_bounds),
        )
        object.__setattr__(
            self,
            "default_layer_weights",
            deep_freeze(self.default_layer_weights),
        )
        object.__setattr__(
            self,
            "confidence_thresholds",
            deep_freeze(self.confidence_thresholds),
        )
        object.__setattr__(
            self,
            "policy_adjustment_bounds",
            deep_freeze(self.policy_adjustment_bounds),
        )

    def __deepcopy__(self, memo: dict[int, object]) -> LayerCoordinationPolicy:
        del memo
        return self


@dataclass(frozen=True)
class LayerCoordinationState:
    confidences: dict[str, float] = field(default_factory=dict)
    allocated_weights: dict[str, float] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    resolution: str = ""
    selected_candidate: str = ""
    fallback_used: bool = False
    score_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    trace_lineage: list[str] = field(default_factory=list)
    trace_coverage_confirmations: dict[str, float] = field(default_factory=dict)
    action_effects: dict[str, str] = field(default_factory=dict)
    pheromone_proposal_trace_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "confidences", MappingProxyType(dict(self.confidences))
        )
        object.__setattr__(
            self, "allocated_weights", MappingProxyType(dict(self.allocated_weights))
        )
        object.__setattr__(self, "conflicts", tuple(self.conflicts))
        object.__setattr__(
            self,
            "score_breakdown",
            MappingProxyType(
                {
                    candidate_id: MappingProxyType(dict(categories))
                    for candidate_id, categories in self.score_breakdown.items()
                }
            ),
        )
        object.__setattr__(self, "trace_lineage", tuple(self.trace_lineage))
        object.__setattr__(
            self,
            "trace_coverage_confirmations",
            MappingProxyType(dict(self.trace_coverage_confirmations)),
        )
        object.__setattr__(
            self, "action_effects", MappingProxyType(dict(self.action_effects))
        )
        object.__setattr__(
            self,
            "pheromone_proposal_trace_ids",
            tuple(self.pheromone_proposal_trace_ids),
        )

    def __deepcopy__(self, memo: dict[int, object]) -> LayerCoordinationState:
        del memo
        return self


def layer_coordination_policy_from_collective(
    policy: object,
) -> LayerCoordinationPolicy:
    collective_policy = cast(CollectiveDecisionPolicy, policy)
    return LayerCoordinationPolicy(
        enabled=collective_policy.layer_coordination_enabled,
        layer_weight_bounds=dict(collective_policy.layer_weight_bounds),
        default_layer_weights=dict(collective_policy.layer_default_weights),
        confidence_thresholds=dict(collective_policy.layer_confidence_thresholds),
        conflict_threshold=collective_policy.layer_conflict_threshold,
        emergency_override_threshold=(
            collective_policy.layer_emergency_override_threshold
        ),
        min_layer_provenance=collective_policy.layer_min_provenance,
        fallback_on_unresolved_conflict=(
            collective_policy.layer_fallback_on_unresolved_conflict
        ),
        policy_adjustment_bounds=dict(collective_policy.policy_adjustment_bounds),
    )


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GovernanceError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise GovernanceError(f"{field_name} must be a finite number")
    return number


def _bounded_rate(value: object, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if not 0 <= number <= 1:
        raise GovernanceError(f"{field_name} must be between 0 and 1")
    return number


def validate_layer_coordination_policy(policy: LayerCoordinationPolicy) -> None:
    if not isinstance(policy.enabled, bool):
        raise GovernanceError("layer coordination enabled must be boolean")
    if not isinstance(policy.fallback_on_unresolved_conflict, bool):
        raise GovernanceError("layer fallback_on_unresolved_conflict must be boolean")
    conflict_threshold = _finite_number(
        policy.conflict_threshold, "layer conflict_threshold"
    )
    emergency_threshold = _finite_number(
        policy.emergency_override_threshold,
        "layer emergency_override_threshold",
    )
    if not 0 <= conflict_threshold <= 1 or not 0 <= emergency_threshold <= 1:
        raise GovernanceError("layer coordination thresholds must be between 0 and 1")
    if isinstance(policy.min_layer_provenance, bool) or not isinstance(
        policy.min_layer_provenance, int
    ):
        raise GovernanceError("layer min_layer_provenance must be a positive integer")
    if policy.min_layer_provenance <= 0:
        raise GovernanceError("layer min_layer_provenance must be a positive integer")
    if policy.enabled and not policy.fallback_on_unresolved_conflict:
        raise GovernanceError(
            "enabled layer coordination must fall back on unresolved conflict"
        )
    max_bias = _finite_number(policy.max_strategy_bias, "layer max_strategy_bias")
    if not 0 <= max_bias <= MAX_LAYER_MAGNITUDE:
        raise GovernanceError("layer max_strategy_bias is outside absolute bounds")
    for mapping_name, mapping in (
        ("default weight", policy.default_layer_weights),
        ("confidence threshold", policy.confidence_thresholds),
    ):
        for layer_id, value in mapping.items():
            if layer_id not in SUPPORTED_LAYER_IDS:
                raise GovernanceError(
                    f"unsupported layer id in {mapping_name}: {layer_id}"
                )
            number = _finite_number(value, f"layer {mapping_name} {layer_id}")
            if number < 0:
                raise GovernanceError(
                    f"layer {mapping_name} must be non-negative: {layer_id}"
                )
            if mapping_name == "confidence threshold" and number > 1:
                raise GovernanceError(
                    f"layer confidence threshold must not exceed 1: {layer_id}"
                )
    for layer_id, bounds in policy.layer_weight_bounds.items():
        if layer_id not in SUPPORTED_LAYER_IDS:
            raise GovernanceError(f"unsupported layer id in weight bounds: {layer_id}")
        if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
            raise GovernanceError(
                f"layer weight bounds must contain two values: {layer_id}"
            )
        lower = _finite_number(bounds[0], f"layer {layer_id} lower weight bound")
        upper = _finite_number(bounds[1], f"layer {layer_id} upper weight bound")
        if lower < 0 or upper < lower or upper > MAX_LAYER_MAGNITUDE:
            raise GovernanceError(f"layer weight bounds are invalid: {layer_id}")
        default = policy.default_layer_weights.get(layer_id)
        if default is not None and not lower <= default <= upper:
            raise GovernanceError(
                f"layer default weight is outside declared bounds: {layer_id}"
            )


def is_extension_layer_action(action: str) -> bool:
    return isinstance(action, str) and any(
        action.startswith(prefix) and len(action) > len(prefix)
        for prefix in LAYER_ACTION_EXTENSION_PREFIXES
    )


def validate_layer_proposal(
    proposal: LayerProposal,
    *,
    candidate_set: CandidateSet,
    target: str,
) -> None:
    for field_name in (
        "layer_id",
        "source_id",
        "target",
        "candidate_id",
        "action",
        "proposed_pheromone_kind",
        "evidence_id",
        "provenance",
        "trace_event_id",
    ):
        if not isinstance(getattr(proposal, field_name), str):
            raise GovernanceError(f"layer proposal {field_name} must be a string")
    if proposal.layer_id not in SUPPORTED_LAYER_IDS:
        raise GovernanceError(f"unsupported layer id: {proposal.layer_id}")
    if not is_nonblank_string(proposal.source_id):
        raise GovernanceError("layer proposal source_id is required")
    if not isinstance(proposal.target, str) or proposal.target != target:
        raise GovernanceError(
            f"layer proposal targets {proposal.target}, not active target {target}"
        )
    if proposal.action not in SUPPORTED_LAYER_ACTIONS and not is_extension_layer_action(
        proposal.action
    ):
        raise GovernanceError(f"unsupported layer action: {proposal.action}")
    if proposal.candidate_id:
        candidate_set.require_declared_for_target(proposal.candidate_id, target)
    if not is_nonblank_string(proposal.candidate_id):
        raise GovernanceError(f"layer action requires a candidate: {proposal.action}")
    confidence = _bounded_rate(proposal.confidence, "layer proposal confidence")
    del confidence
    for field_name in ("support", "risk", "proposed_strength"):
        value = _finite_number(
            getattr(proposal, field_name), f"layer proposal {field_name}"
        )
        if not 0 <= value <= MAX_LAYER_MAGNITUDE:
            raise GovernanceError(
                f"layer proposal {field_name} is outside absolute bounds"
            )
    if proposal.proposed_pheromone_kind:
        if (
            proposal.proposed_pheromone_kind not in SUPPORTED_PHEROMONE_KINDS
            and not is_extension_pheromone_value(proposal.proposed_pheromone_kind)
        ):
            raise GovernanceError(
                f"unsupported proposed pheromone kind: {proposal.proposed_pheromone_kind}"
            )
        subject_type = proposal.metadata.get("subject_type", "candidate")
        subject_id = proposal.metadata.get("subject_id", proposal.candidate_id)
        if (
            not isinstance(subject_type, str)
            or not isinstance(subject_id, str)
            or not subject_id
        ):
            raise GovernanceError("proposed pheromone subject binding is invalid")
        if (
            subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES
            and not is_extension_pheromone_value(subject_type)
        ):
            raise GovernanceError("proposed pheromone subject type is unsupported")
        if subject_type == "candidate" and subject_id != proposal.candidate_id:
            raise GovernanceError(
                "proposed candidate pheromone subject must match candidate_id"
            )
        if (
            proposal.proposed_pheromone_kind in {"alarm", "cautionary"}
            and proposal.layer_id != "reactive"
        ):
            raise GovernanceError(
                "only the reactive layer may propose emergency pheromone pressure"
            )
    if proposal.action == "propose_pheromone":
        if not proposal.proposed_pheromone_kind:
            raise GovernanceError(
                "propose_pheromone action requires proposed_pheromone_kind"
            )
        if proposal.proposed_strength <= 0:
            raise GovernanceError(
                "propose_pheromone action requires positive proposed_strength"
            )
    elif proposal.action not in EMERGENCY_ACTIONS and (
        proposal.proposed_pheromone_kind or proposal.proposed_strength > 0
    ):
        raise GovernanceError(
            "proposed pheromone fields require propose_pheromone or a reactive emergency action"
        )
    if proposal.action in EMERGENCY_ACTIONS and proposal.layer_id != "reactive":
        raise GovernanceError("only the reactive layer may raise emergency pressure")
    if proposal.action in EMERGENCY_ACTIONS and proposal.proposed_pheromone_kind:
        if proposal.proposed_pheromone_kind != proposal.action:
            raise GovernanceError(
                "reactive emergency action and proposed pheromone kind must match"
            )
    if proposal.action == "resolve_conflict" and proposal.layer_id != "metacognitive":
        raise GovernanceError(
            "only the metacognitive layer may propose conflict resolution"
        )
    if (
        proposal.action == "confirm_trace_coverage"
        and proposal.layer_id != "metacognitive"
    ):
        raise GovernanceError("only the metacognitive layer may confirm trace coverage")
    if proposal.action not in {
        "request_scouting",
        "fallback_pressure",
    } and not is_extension_layer_action(proposal.action):
        if not is_nonblank_string(proposal.evidence_id):
            raise GovernanceError("layer proposal is missing evidence")
    if not is_nonblank_string(proposal.provenance):
        raise GovernanceError("layer proposal is missing provenance")
    if not is_nonblank_string(proposal.trace_event_id):
        raise GovernanceError("layer proposal is missing trace event id")


def validate_layer_proposals(
    proposals: list[LayerProposal],
    *,
    candidate_set: CandidateSet,
    target: str,
) -> tuple[LayerProposal, ...]:
    items = list(proposals)
    for proposal in items:
        validate_layer_proposal(proposal, candidate_set=candidate_set, target=target)
    trace_ids: set[str] = set()
    identities: set[tuple[object, ...]] = set()
    for proposal in items:
        if proposal.trace_event_id in trace_ids:
            raise GovernanceError(
                f"duplicate layer proposal trace_event_id: {proposal.trace_event_id}"
            )
        trace_ids.add(proposal.trace_event_id)
        identity = (
            proposal.layer_id,
            proposal.source_id,
            proposal.target,
            proposal.candidate_id,
            proposal.action,
        )
        if identity in identities:
            raise GovernanceError("duplicate equivalent layer proposal")
        identities.add(identity)
    return tuple(sorted(items, key=layer_proposal_key))


def layer_proposal_key(proposal: LayerProposal) -> tuple[object, ...]:
    return (
        proposal.layer_id,
        proposal.source_id,
        proposal.target,
        proposal.candidate_id,
        proposal.action,
        proposal.trace_event_id,
    )


def layer_action_effect(
    proposal: LayerProposal,
    policy: LayerCoordinationPolicy,
) -> str:
    threshold = policy.confidence_thresholds.get(proposal.layer_id, 0.0)
    if is_extension_layer_action(proposal.action):
        return "metadata_only"
    if proposal.confidence < threshold:
        return f"{proposal.action}_below_confidence_threshold"
    if proposal.action in PREFERENCE_ACTIONS:
        return "candidate_preference"
    if proposal.action == "risk":
        return "candidate_risk_pressure"
    if proposal.action in EMERGENCY_ACTIONS:
        return "reactive_emergency_pressure"
    if proposal.action == "request_scouting":
        return "scouting_required"
    if proposal.action == "fallback_pressure":
        return "fallback_required"
    if proposal.action == "confirm_trace_coverage":
        return "trace_coverage_confirmed"
    if proposal.action == "resolve_conflict":
        return "metacognitive_conflict_resolution_proposed"
    if proposal.action == "propose_pheromone":
        return "bounded_pheromone_deposit_proposed"
    raise GovernanceError(
        f"layer action has no governance semantics: {proposal.action}"
    )


def trace_coverage_confirmations(
    proposals: list[LayerProposal] | tuple[LayerProposal, ...],
    policy: LayerCoordinationPolicy,
) -> dict[str, float]:
    confirmations: dict[str, float] = {}
    for proposal in sorted(proposals, key=layer_proposal_key):
        if (
            proposal.action == "confirm_trace_coverage"
            and layer_action_effect(proposal, policy) == "trace_coverage_confirmed"
        ):
            confirmations[proposal.candidate_id] = max(
                confirmations.get(proposal.candidate_id, 0.0),
                float(proposal.confidence),
            )
    return confirmations


def materialize_layer_pheromone_proposals(
    *,
    proposals: list[LayerProposal],
    candidate_set: CandidateSet,
    target: str,
    current_step: int,
    policy: LayerCoordinationPolicy,
    neighborhood: PheromoneNeighborhood | None = None,
) -> tuple[PheromoneTrail, ...]:
    """Convert validated layer proposals into non-authoritative trail inputs.

    The returned trails still pass through the normal atomic deposit batch,
    shared budgets, target checks, diffusion, scoring, and independent-scout
    gate.  No layer proposal directly mutates memory or commits a candidate.
    """

    validate_layer_coordination_policy(policy)
    if (
        isinstance(current_step, bool)
        or not isinstance(current_step, int)
        or current_step < 0
    ):
        raise GovernanceError(
            "layer pheromone proposal step must be a non-negative integer"
        )
    ordered = validate_layer_proposals(
        proposals, candidate_set=candidate_set, target=target
    )
    if neighborhood is not None:
        validate_pheromone_topology(
            neighborhood, candidate_set=candidate_set, target=target
        )
    trails: list[PheromoneTrail] = []
    for proposal in ordered:
        if proposal.action != "propose_pheromone":
            continue
        if (
            layer_action_effect(proposal, policy)
            != "bounded_pheromone_deposit_proposed"
        ):
            continue
        subject_type = proposal.metadata.get("subject_type", "candidate")
        subject_id = proposal.metadata.get("subject_id", proposal.candidate_id)
        if neighborhood is not None:
            validate_pheromone_subject_binding(
                neighborhood,
                subject_type=subject_type,
                subject_id=subject_id,
                candidate_id=proposal.candidate_id,
                require_declared=True,
            )
        strength = float(proposal.proposed_strength) * float(proposal.confidence)
        # Proposal validation establishes finite, bounded operands.
        if strength <= 0:
            raise GovernanceError(
                "materialized layer pheromone strength must be finite and positive"
            )
        trails.append(
            PheromoneTrail(
                candidate_id=proposal.candidate_id,
                strength=strength,
                subject_type=subject_type,
                subject_id=subject_id,
                target=target,
                kind=proposal.proposed_pheromone_kind,
                source_id=proposal.source_id,
                source_role=f"layer:{proposal.layer_id}",
                evidence_id=proposal.evidence_id,
                provenance=proposal.provenance,
                trace_event_id=proposal.trace_event_id,
                deposited_at_step=current_step,
                updated_at_step=current_step,
            )
        )
    return tuple(trails)


def validate_strategy_bias(
    bias: StrategyBias,
    policy: LayerCoordinationPolicy,
    *,
    candidate_set: CandidateSet,
    target: str,
) -> None:
    for field_name in (
        "layer_id",
        "candidate_id",
        "provenance",
        "trace_event_id",
        "target",
        "source_id",
        "evidence_id",
    ):
        if not isinstance(getattr(bias, field_name), str):
            raise GovernanceError(f"StrategyBias {field_name} must be a string")
    if bias.layer_id != "evolutionary":
        raise GovernanceError(
            "StrategyBias may only be proposed by the evolutionary layer"
        )
    if not is_nonblank_string(bias.source_id):
        raise GovernanceError("StrategyBias source_id is required")
    if bias.target != target:
        raise GovernanceError(
            f"StrategyBias targets {bias.target}, not active target {target}"
        )
    candidate_set.require_declared_for_target(bias.candidate_id, target)
    support = _finite_number(bias.support, "StrategyBias support")
    if not 0 <= support <= policy.max_strategy_bias:
        raise GovernanceError("StrategyBias support is outside declared bounds")
    _bounded_rate(bias.confidence, "StrategyBias confidence")
    if not is_nonblank_string(bias.provenance):
        raise GovernanceError("StrategyBias is missing provenance")
    if not is_nonblank_string(bias.evidence_id):
        raise GovernanceError("StrategyBias is missing evidence")
    if not is_nonblank_string(bias.trace_event_id):
        raise GovernanceError("StrategyBias is missing trace event id")


def validate_strategy_biases(
    biases: list[StrategyBias],
    policy: LayerCoordinationPolicy,
    *,
    candidate_set: CandidateSet,
    target: str,
) -> tuple[StrategyBias, ...]:
    items = list(biases)
    for bias in items:
        validate_strategy_bias(bias, policy, candidate_set=candidate_set, target=target)
    trace_ids: set[str] = set()
    identities: set[tuple[str, str, str]] = set()
    for bias in items:
        if bias.trace_event_id in trace_ids:
            raise GovernanceError(
                f"duplicate StrategyBias trace_event_id: {bias.trace_event_id}"
            )
        trace_ids.add(bias.trace_event_id)
        identity = (bias.source_id, bias.target, bias.candidate_id)
        if identity in identities:
            raise GovernanceError("duplicate equivalent StrategyBias")
        identities.add(identity)
    return tuple(
        sorted(
            items,
            key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
        )
    )


def validate_layer_performance_snapshot(snapshot: LayerPerformanceSnapshot) -> None:
    if (
        not isinstance(snapshot.layer_id, str)
        or snapshot.layer_id not in SUPPORTED_LAYER_IDS
    ):
        raise GovernanceError(f"unsupported layer snapshot id: {snapshot.layer_id}")
    for field_name in (
        "recent_success_rate",
        "recent_conflict_rate",
        "recent_fallback_rate",
        "mean_confidence",
        "evidence_coverage",
        "trace_coverage",
    ):
        _bounded_rate(getattr(snapshot, field_name), f"layer snapshot {field_name}")


def validate_layer_performance_snapshots(
    snapshots: list[LayerPerformanceSnapshot] | None,
) -> tuple[LayerPerformanceSnapshot, ...]:
    items = list(snapshots or [])
    seen: set[str] = set()
    for snapshot in items:
        validate_layer_performance_snapshot(snapshot)
        if snapshot.layer_id in seen:
            raise GovernanceError(
                f"duplicate layer performance snapshot: {snapshot.layer_id}"
            )
        seen.add(snapshot.layer_id)
    return tuple(sorted(items, key=lambda item: item.layer_id))


def assess_layer_confidences(proposals: list[LayerProposal]) -> dict[str, float]:
    values: dict[str, list[float]] = {layer_id: [] for layer_id in SUPPORTED_LAYER_IDS}
    for proposal in sorted(proposals, key=layer_proposal_key):
        if (
            not isinstance(proposal.layer_id, str)
            or proposal.layer_id not in SUPPORTED_LAYER_IDS
        ):
            raise GovernanceError(f"unsupported layer id: {proposal.layer_id}")
        values[proposal.layer_id].append(
            _bounded_rate(proposal.confidence, "layer proposal confidence")
        )
    return {
        layer_id: (math.fsum(layer_values) / len(layer_values) if layer_values else 0.0)
        for layer_id, layer_values in sorted(values.items())
    }


def allocate_layer_weights(
    policy: LayerCoordinationPolicy,
    snapshots: list[LayerPerformanceSnapshot] | None = None,
    *,
    active_emergency: bool = False,
) -> dict[str, float]:
    validate_layer_coordination_policy(policy)
    validated = validate_layer_performance_snapshots(snapshots)
    performance = {snapshot.layer_id: snapshot for snapshot in validated}
    weights: dict[str, float] = {}
    for layer_id in sorted(SUPPORTED_LAYER_IDS):
        base = float(policy.default_layer_weights.get(layer_id, 1.0))
        adjusted = base
        snapshot = performance.get(layer_id)
        if snapshot is not None:
            quality = (
                math.fsum(
                    (
                        snapshot.recent_success_rate,
                        1.0 - snapshot.recent_conflict_rate,
                        1.0 - snapshot.recent_fallback_rate,
                        snapshot.mean_confidence,
                        snapshot.evidence_coverage,
                        snapshot.trace_coverage,
                    )
                )
                / 6.0
            )
            adjusted = base * (0.5 + quality)
        if active_emergency and layer_id == "reactive":
            adjusted = max(base, adjusted)
        lower, upper = policy.layer_weight_bounds.get(layer_id, (0.0, max(1.0, base)))
        weight = min(float(upper), max(float(lower), adjusted))
        weights[layer_id] = weight
    return weights


def _strong_preference(
    proposal: LayerProposal, policy: LayerCoordinationPolicy
) -> bool:
    threshold = policy.confidence_thresholds.get(proposal.layer_id, 0.0)
    return (
        proposal.action in PREFERENCE_ACTIONS
        and proposal.proposed_pheromone_kind not in {"alarm", "cautionary"}
        and bool(proposal.candidate_id)
        and proposal.confidence >= threshold
        and proposal.support > proposal.risk
    )


def _active_emergency(proposal: LayerProposal, policy: LayerCoordinationPolicy) -> bool:
    return (
        proposal.layer_id == "reactive"
        and (
            proposal.action in EMERGENCY_ACTIONS
            or proposal.proposed_pheromone_kind in {"alarm", "cautionary"}
        )
        and proposal.confidence >= policy.emergency_override_threshold
    )


def detect_layer_conflicts(
    proposals: list[LayerProposal],
    policy: LayerCoordinationPolicy,
    snapshots: list[LayerPerformanceSnapshot] | None = None,
) -> list[str]:
    validate_layer_coordination_policy(policy)
    validated_snapshots = validate_layer_performance_snapshots(snapshots)
    ordered = sorted(proposals, key=layer_proposal_key)
    conflicts: set[str] = set()
    strong = [proposal for proposal in ordered if _strong_preference(proposal, policy)]
    for index, proposal in enumerate(strong):
        for other in strong[index + 1 :]:
            if (
                proposal.layer_id == other.layer_id
                or proposal.candidate_id == other.candidate_id
            ):
                continue
            if abs(proposal.confidence - other.confidence) <= policy.conflict_threshold:
                conflicts.add("candidate_support_conflict")
    emergencies = [
        proposal for proposal in ordered if _active_emergency(proposal, policy)
    ]
    if emergencies:
        conflicts.add("reactive_emergency_pressure")
    for emergency in emergencies:
        for proposal in strong:
            if proposal.layer_id in {"learned", "evolutionary"}:
                conflicts.add("reactive_emergency_exploitation_conflict")
            if proposal.candidate_id == emergency.candidate_id:
                conflicts.add("positive_alarm_conflict")
    for proposal in ordered:
        if proposal.action == "request_scouting":
            conflicts.add("scouting_requested")
        if proposal.action == "fallback_pressure":
            conflicts.add("fallback_pressure")
    snapshot_by_layer = {
        snapshot.layer_id: snapshot for snapshot in validated_snapshots
    }
    confirmed_trace_coverage = trace_coverage_confirmations(ordered, policy)
    for proposal in strong:
        if proposal.layer_id not in {"learned", "evolutionary"}:
            continue
        snapshot = snapshot_by_layer.get(proposal.layer_id)
        threshold = policy.confidence_thresholds.get(proposal.layer_id, 0.0)
        if snapshot is not None and snapshot.evidence_coverage < threshold:
            conflicts.add("insufficient_evidence_coverage")
        if (
            snapshot is not None
            and snapshot.trace_coverage < threshold
            and confirmed_trace_coverage.get(proposal.candidate_id, 0.0) < threshold
        ):
            conflicts.add("insufficient_trace_coverage")
    provenance = {proposal.provenance for proposal in ordered if proposal.provenance}
    if ordered and len(provenance) < policy.min_layer_provenance:
        conflicts.add("insufficient_layer_provenance")
    return sorted(conflicts)


def resolve_layer_conflicts(
    conflicts: list[str],
    policy: LayerCoordinationPolicy,
    *,
    fallback_candidate_id: str,
    candidate_scores: dict[str, float],
    proposals: list[LayerProposal] | None = None,
) -> tuple[str, bool, str]:
    validate_layer_coordination_policy(policy)
    for candidate_id, score in candidate_scores.items():
        _finite_number(score, f"layer candidate score {candidate_id}")
    hard_conflicts = {
        "reactive_emergency_pressure",
        "reactive_emergency_exploitation_conflict",
        "fallback_pressure",
        "scouting_requested",
        "insufficient_evidence_coverage",
        "insufficient_trace_coverage",
        "insufficient_layer_provenance",
    }
    if conflicts:
        resolvers = [
            proposal
            for proposal in proposals or []
            if proposal.layer_id == "metacognitive"
            and proposal.action == "resolve_conflict"
            and proposal.candidate_id in candidate_scores
            and proposal.confidence
            >= policy.confidence_thresholds.get("metacognitive", 0.0)
            and proposal.support > proposal.risk
        ]
        if not (set(conflicts) & hard_conflicts) and resolvers:
            resolver = sorted(
                resolvers,
                key=lambda item: (
                    -item.confidence,
                    -item.support,
                    item.candidate_id,
                    item.trace_event_id,
                ),
            )[0]
            return resolver.candidate_id, False, "metacognitive_conflict_resolution"
        # An unresolved coordination conflict is always fail-closed.  The policy
        # flag is retained as ABI declaration but cannot authorize unsafe choice.
        return fallback_candidate_id, True, "safe_fallback_for_layer_conflict"
    positive_scores = {
        candidate_id: score
        for candidate_id, score in candidate_scores.items()
        if score > 0
    }
    if positive_scores:
        candidate_id = sorted(
            positive_scores.items(), key=lambda item: (-item[1], item[0])
        )[0][0]
        return candidate_id, False, "layer_candidate_preference"
    return fallback_candidate_id, True, "safe_fallback_no_layer_candidate"


def proposal_score_delta(
    proposal: LayerProposal,
    policy: LayerCoordinationPolicy,
    weight: float,
) -> float:
    weight = _finite_number(weight, "layer proposal weight")
    if weight < 0:
        raise GovernanceError("layer proposal weight must be non-negative")
    threshold = policy.confidence_thresholds.get(proposal.layer_id, 0.0)
    if proposal.confidence < threshold or is_extension_layer_action(proposal.action):
        return 0.0
    if proposal.action in EMERGENCY_ACTIONS or proposal.proposed_pheromone_kind in {
        "alarm",
        "cautionary",
    }:
        pressure = max(proposal.risk, proposal.proposed_strength, proposal.support)
        delta = -(pressure * proposal.confidence * weight)
    elif proposal.action in PREFERENCE_ACTIONS:
        delta = (proposal.support * proposal.confidence - proposal.risk) * weight
    elif proposal.action == "risk":
        delta = -(max(proposal.risk, proposal.support) * proposal.confidence * weight)
    elif proposal.action == "resolve_conflict":
        delta = (
            max(0.0, proposal.support - proposal.risk) * proposal.confidence * weight
        )
    else:
        delta = 0.0
    if not math.isfinite(delta):
        raise GovernanceError("layer proposal score must remain finite")
    return delta


def strategy_bias_score_delta(
    bias: StrategyBias,
    policy: LayerCoordinationPolicy,
    weight: float,
) -> float:
    """Return the governance-owned bounded score effect for StrategyBias."""

    del policy  # Validation against this policy occurs at the coordination boundary.
    weight = _finite_number(weight, "StrategyBias weight")
    if weight < 0:
        raise GovernanceError("StrategyBias weight must be non-negative")
    delta = bias.support * bias.confidence * weight
    if not math.isfinite(delta):
        raise GovernanceError("StrategyBias score must remain finite")
    return delta


def evaluate_layer_coordination(
    *,
    candidate_set: CandidateSet,
    target: str,
    policy: LayerCoordinationPolicy,
    proposals: list[LayerProposal],
    fallback_candidate_id: str,
    snapshots: list[LayerPerformanceSnapshot] | None = None,
    strategy_biases: list[StrategyBias] | None = None,
) -> LayerCoordinationState:
    fallback = candidate_set.require_declared_for_target(fallback_candidate_id, target)
    if not fallback.safe_fallback:
        raise GovernanceError(
            f"layer fallback candidate is not marked safe: {fallback.id}"
        )
    validate_layer_coordination_policy(policy)
    if not policy.enabled:
        return LayerCoordinationState(resolution="disabled")

    ordered_proposals = validate_layer_proposals(
        proposals, candidate_set=candidate_set, target=target
    )
    ordered_biases = validate_strategy_biases(
        strategy_biases or [],
        policy,
        candidate_set=candidate_set,
        target=target,
    )
    validated_snapshots = validate_layer_performance_snapshots(snapshots)
    proposal_trace_ids = {proposal.trace_event_id for proposal in ordered_proposals}
    bias_trace_ids = {bias.trace_event_id for bias in ordered_biases}
    duplicate_lineage = proposal_trace_ids & bias_trace_ids
    if duplicate_lineage:
        raise GovernanceError(
            f"duplicate layer lineage across proposal and StrategyBias: {sorted(duplicate_lineage)[0]}"
        )

    confidences = assess_layer_confidences(list(ordered_proposals))
    emergency_active = any(
        _active_emergency(proposal, policy) for proposal in ordered_proposals
    )
    weights = allocate_layer_weights(
        policy,
        list(validated_snapshots),
        active_emergency=emergency_active,
    )
    active_candidate_set = CandidateSet(
        tuple(
            candidate
            for candidate in candidate_set.candidates
            if candidate.target == target
        )
    )
    breakdown = empty_score_breakdown(active_candidate_set)
    candidate_scores = {
        candidate.id: 0.0 for candidate in active_candidate_set.candidates
    }
    touched_candidates: set[str] = set()
    for proposal in ordered_proposals:
        delta = proposal_score_delta(
            proposal, policy, weights.get(proposal.layer_id, 0.0)
        )
        if delta == 0:
            continue
        touched_candidates.add(proposal.candidate_id)
        add_breakdown(
            breakdown, proposal.candidate_id, f"layer_{proposal.layer_id}", delta
        )
    for bias in ordered_biases:
        delta = strategy_bias_score_delta(
            bias,
            policy,
            weights.get(bias.layer_id, 0.0),
        )
        if delta == 0:
            continue
        touched_candidates.add(bias.candidate_id)
        add_breakdown(breakdown, bias.candidate_id, "layer_evolutionary", delta)
    for candidate_id in candidate_scores:
        candidate_scores[candidate_id] = math.fsum(breakdown[candidate_id].values())

    conflicts = detect_layer_conflicts(
        list(ordered_proposals), policy, list(validated_snapshots)
    )
    coverage_confirmations = trace_coverage_confirmations(ordered_proposals, policy)
    action_effects = {
        proposal.trace_event_id: layer_action_effect(proposal, policy)
        for proposal in ordered_proposals
    }
    selected, fallback_used, resolution = resolve_layer_conflicts(
        conflicts,
        policy,
        fallback_candidate_id=fallback_candidate_id,
        candidate_scores={
            candidate_id: candidate_scores[candidate_id]
            for candidate_id in touched_candidates
        },
        proposals=list(ordered_proposals),
    )
    return LayerCoordinationState(
        confidences=confidences,
        allocated_weights=weights,
        conflicts=conflicts,
        resolution=resolution,
        selected_candidate=selected,
        fallback_used=fallback_used,
        score_breakdown=breakdown,
        trace_lineage=[
            *(proposal.trace_event_id for proposal in ordered_proposals),
            *(bias.trace_event_id for bias in ordered_biases),
        ],
        trace_coverage_confirmations=coverage_confirmations,
        action_effects=action_effects,
        pheromone_proposal_trace_ids=tuple(
            proposal.trace_event_id
            for proposal in ordered_proposals
            if proposal.action == "propose_pheromone"
            and action_effects[proposal.trace_event_id]
            == "bounded_pheromone_deposit_proposed"
        ),
    )
