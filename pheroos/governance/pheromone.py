from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    SUPPORTED_PHEROMONE_DECAY_MODELS,
    effective_pheromone_scored_subject_types,
    is_scored_pheromone_subject_type,
)
from pheroos.trace import canonical_pheromone_clip_payload


SUPPORTED_PHEROMONE_KINDS = frozenset({"positive", "negative", "cautionary", "alarm", "novelty", "stale"})
SUPPORTED_PHEROMONE_SUBJECT_TYPES = frozenset({"candidate", "route", "tool", "evidence", "agent"})
SUPPORTED_PHEROMONE_RESPONSE_MODELS = frozenset({"linear", "saturating", "threshold", "competitive"})
SUPPORTED_PHEROMONE_COMPETITION_MODES = frozenset({"none", "normalize"})
PHEROMONE_EXTENSION_PREFIXES = ("x-", "ext.")
BREAKDOWN_CATEGORIES = (
    "scout",
    "recruitment",
    "inhibition",
    "pheromone_positive",
    "pheromone_negative",
    "pheromone_cautionary",
    "pheromone_alarm",
    "pheromone_novelty",
    "pheromone_response_floor",
    "pheromone_route",
    "pheromone_tool",
    "pheromone_agent",
    "layer_reactive",
    "layer_learned",
    "layer_evolutionary",
    "layer_metacognitive",
)


@dataclass(frozen=True)
class PheromoneTrail:
    candidate_id: str
    strength: float
    subject_type: str = "candidate"
    subject_id: str = ""
    target: str = ""
    route_id: str = ""
    tool_id: str = ""
    kind: str = "positive"
    source_id: str = ""
    source_role: str = ""
    evidence_id: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    deposited_at_step: int = 0
    updated_at_step: int = 0
    ttl_steps: int | None = None
    lineage_event_ids: tuple[str, ...] = ()
    diffusion_root_trace_event_id: str = ""
    diffusion_parent_trace_event_id: str = ""
    diffusion_hop: int = 0

    def __post_init__(self) -> None:
        lineage = tuple(self.lineage_event_ids)
        if self.trace_event_id and self.trace_event_id not in lineage:
            lineage = (*lineage, self.trace_event_id)
        object.__setattr__(self, "lineage_event_ids", lineage)


@dataclass(frozen=True)
class PheromoneSubject:
    subject_type: str
    subject_id: str
    candidate_id: str = ""
    target: str = ""


@dataclass(frozen=True)
class PheromoneEdge:
    source_subject_type: str
    source_subject_id: str
    target_subject_type: str
    target_subject_id: str
    attenuation: float = 1.0


@dataclass(frozen=True)
class PheromoneNeighborhood:
    subjects: list[PheromoneSubject] = field(default_factory=list)
    edges: list[PheromoneEdge] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "subjects", tuple(self.subjects))
        object.__setattr__(self, "edges", tuple(self.edges))


@dataclass(frozen=True)
class PheromoneDiffusionPolicy:
    enabled: bool = False
    max_hops: int = 0
    attenuation: float = 0.0


@dataclass(frozen=True)
class PheromonePolicy:
    enabled: bool = False
    evaporation_rate: float = 0.0
    decay_model: str = "exponential"
    min_strength: float = 0.0
    max_strength: float = 10.0
    positive_weight: float = 1.0
    negative_weight: float = 1.0
    cautionary_weight: float = 1.0
    cautionary_override_threshold: float = 1.0
    novelty_weight: float = 0.5
    per_source_cap: float = 3.0
    per_round_deposit_cap: float = 5.0
    min_source_diversity: int = 1
    require_provenance: bool = True
    require_trace: bool = True
    scored_subject_types: list[str] = field(default_factory=lambda: ["candidate"])
    kind_profiles: dict[str, PheromoneKindProfile] = field(default_factory=dict)
    response_model: str = "linear"
    activation_threshold: float = 0.0
    saturation_threshold: float = 10.0
    competition_mode: str = "none"
    exploration_floor: float = 0.0
    exploration_enabled: bool = False
    novelty_decay_rate: float = 0.0
    stale_route_reopen_threshold: float = 0.0
    feedback_enabled: bool = False
    response_exploration_floor: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "scored_subject_types", tuple(self.scored_subject_types))
        object.__setattr__(self, "kind_profiles", MappingProxyType(dict(self.kind_profiles)))

    def __deepcopy__(self, memo: dict[int, object]) -> PheromonePolicy:
        del memo
        return self


@dataclass(frozen=True)
class PheromoneLifecycleRecord:
    action: str
    target: str
    candidate_id: str
    subject_type: str
    subject_id: str
    kind: str
    source_kind: str
    source_id: str
    provenance: str
    source_trace_event_id: str
    trace_event_id: str
    old_strength: float
    new_strength: float
    requested_strength: float = 0.0
    applied_strength: float = 0.0
    round_budget_remaining: float | None = None
    source_budget_remaining: float | None = None
    hop: int = 0
    attenuation: float = 1.0
    policy_attenuation: float = 1.0
    edge_attenuation: float = 1.0
    step: int = 0
    elapsed_steps: int = 0
    outcome: str = ""
    reward: float = 0.0
    cause_trace_event_id: str = ""
    deposited_at_step: int = 0
    ttl_steps: int | None = None
    _causal_payload_json: str = field(default="", repr=False)

    def to_lineage(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "candidate_id": self.candidate_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "kind": self.kind,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "provenance": self.provenance,
            "source_trace_event_id": self.source_trace_event_id,
            "trace_event_id": self.trace_event_id,
            "old_strength": self.old_strength,
            "new_strength": self.new_strength,
            "requested_strength": self.requested_strength,
            "applied_strength": self.applied_strength,
            "round_budget_remaining": self.round_budget_remaining,
            "source_budget_remaining": self.source_budget_remaining,
            "hop": self.hop,
            "attenuation": self.attenuation,
            "policy_attenuation": self.policy_attenuation,
            "edge_attenuation": self.edge_attenuation,
            "step": self.step,
            "elapsed_steps": self.elapsed_steps,
            "outcome": self.outcome,
            "reward": self.reward,
            "cause_trace_event_id": self.cause_trace_event_id,
            "deposited_at_step": self.deposited_at_step,
            "ttl_steps": self.ttl_steps,
        }


@dataclass(frozen=True)
class PheromoneBudgetState:
    round_cap: float
    per_source_cap: float
    round_used: float = 0.0
    source_used: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_used", MappingProxyType(dict(self.source_used)))

    def __deepcopy__(self, memo: dict[int, object]) -> PheromoneBudgetState:
        del memo
        return self

    @classmethod
    def for_policy(cls, policy: PheromonePolicy) -> PheromoneBudgetState:
        validate_pheromone_policy(policy)
        return cls(
            round_cap=float(policy.per_round_deposit_cap),
            per_source_cap=float(policy.per_source_cap),
        )

    @property
    def round_remaining(self) -> float:
        return max(0.0, self.round_cap - self.round_used)

    def source_remaining(self, source_id: str) -> float:
        return max(0.0, self.per_source_cap - self.source_used.get(source_id, 0.0))

    def consume(self, source_id: str, requested: float) -> tuple[float, PheromoneBudgetState]:
        amount = _non_negative_number(requested, "pheromone budget request")
        applied = min(amount, self.round_remaining, self.source_remaining(source_id))
        updated_sources = dict(self.source_used)
        updated_sources[source_id] = updated_sources.get(source_id, 0.0) + applied
        return applied, PheromoneBudgetState(
            round_cap=self.round_cap,
            per_source_cap=self.per_source_cap,
            round_used=self.round_used + applied,
            source_used=updated_sources,
        )


@dataclass(frozen=True)
class PheromoneBatchResult:
    trails: tuple[PheromoneTrail, ...] = ()
    records: tuple[PheromoneLifecycleRecord, ...] = ()
    processed_event_ids: frozenset[str] = frozenset()
    budget_state: PheromoneBudgetState | None = None
    replayed_event_ids: tuple[str, ...] = ()
    _processed_event_receipts: tuple[tuple[str, tuple[Any, ...]], ...] = field(
        default=(),
        repr=False,
    )


@dataclass(frozen=True)
class PheromoneExplorationObservation:
    target: str
    candidate_id: str
    subject_type: str
    subject_id: str
    novelty_pressure: float
    reopen_eligible: bool
    reason: str
    trace_event_id: str


@dataclass(frozen=True)
class PheromoneNormalizationRecord:
    response_model: str
    competition_mode: str
    candidate_ids: tuple[str, ...]
    pre_scores: dict[str, float]
    post_scores: dict[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        object.__setattr__(self, "pre_scores", MappingProxyType(dict(self.pre_scores)))
        object.__setattr__(self, "post_scores", MappingProxyType(dict(self.post_scores)))

    def __deepcopy__(self, memo: dict[int, object]) -> PheromoneNormalizationRecord:
        del memo
        return self


@dataclass(frozen=True)
class PheromoneScoreResult:
    scores: dict[str, float]
    score_breakdown: dict[str, dict[str, float]]
    kind_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    subject_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    normalization: PheromoneNormalizationRecord | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scores", MappingProxyType(dict(self.scores)))
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
        for field_name in ("kind_breakdown", "subject_breakdown"):
            object.__setattr__(
                self,
                field_name,
                MappingProxyType(
                    {
                        candidate_id: MappingProxyType(dict(categories))
                        for candidate_id, categories in getattr(self, field_name).items()
                    }
                ),
            )

    def __deepcopy__(self, memo: dict[int, object]) -> PheromoneScoreResult:
        del memo
        return self


def pheromone_policy_from_collective(policy: CollectiveDecisionPolicy) -> PheromonePolicy:
    return PheromonePolicy(
        enabled=policy.pheromone_enabled,
        evaporation_rate=policy.pheromone_evaporation_rate,
        decay_model=policy.pheromone_decay_model,
        min_strength=policy.pheromone_min_strength,
        max_strength=policy.pheromone_max_strength,
        positive_weight=policy.pheromone_positive_weight,
        negative_weight=policy.pheromone_negative_weight,
        cautionary_weight=policy.pheromone_cautionary_weight,
        cautionary_override_threshold=policy.pheromone_cautionary_override_threshold,
        novelty_weight=policy.pheromone_novelty_weight,
        per_source_cap=policy.pheromone_per_source_cap,
        per_round_deposit_cap=policy.pheromone_per_round_deposit_cap,
        min_source_diversity=policy.pheromone_min_source_diversity,
        require_provenance=policy.pheromone_require_provenance,
        require_trace=policy.pheromone_require_trace,
        scored_subject_types=list(policy.pheromone_scored_subject_types),
        kind_profiles={
            kind: PheromoneKindProfile(
                weight=profile.weight,
                evaporation_rate=profile.evaporation_rate,
                ttl_steps=profile.ttl_steps,
                response_model=profile.response_model,
                priority=profile.priority,
                can_suppress_positive=profile.can_suppress_positive,
                scored_subject_types=list(profile.scored_subject_types),
                extensions=dict(profile.extensions),
            )
            for kind, profile in policy.pheromone_kind_profiles.items()
        },
        response_model=policy.pheromone_response_model,
        activation_threshold=policy.pheromone_activation_threshold,
        saturation_threshold=policy.pheromone_saturation_threshold,
        competition_mode=policy.pheromone_competition_mode,
        exploration_floor=policy.exploration_floor,
        exploration_enabled=policy.exploration_enabled,
        novelty_decay_rate=policy.novelty_decay_rate,
        stale_route_reopen_threshold=policy.stale_route_reopen_threshold,
        feedback_enabled=policy.pheromone_feedback_enabled,
        response_exploration_floor=policy.pheromone_exploration_floor,
    )


def diffusion_policy_from_collective(policy: CollectiveDecisionPolicy) -> PheromoneDiffusionPolicy:
    return PheromoneDiffusionPolicy(
        enabled=policy.pheromone_diffusion_enabled,
        max_hops=policy.pheromone_diffusion_max_hops,
        attenuation=policy.pheromone_diffusion_attenuation,
    )


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GovernanceError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise GovernanceError(f"{field_name} must be a finite number")
    return number


def _non_negative_number(value: object, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number < 0:
        raise GovernanceError(f"{field_name} must be non-negative")
    return number


def _non_negative_step(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GovernanceError(f"{field_name} must be a non-negative integer")
    return value


def validate_pheromone_policy(policy: PheromonePolicy) -> None:
    if not isinstance(policy.enabled, bool):
        raise GovernanceError("pheromone enabled must be boolean")
    if not isinstance(policy.feedback_enabled, bool):
        raise GovernanceError("pheromone feedback_enabled must be boolean")
    if not isinstance(policy.exploration_enabled, bool):
        raise GovernanceError("pheromone exploration_enabled must be boolean")
    if not isinstance(policy.require_provenance, bool) or not isinstance(policy.require_trace, bool):
        raise GovernanceError("pheromone provenance and trace requirements must be boolean")
    evaporation_rate = _finite_number(policy.evaporation_rate, "pheromone evaporation_rate")
    if not 0 <= evaporation_rate <= 1:
        raise GovernanceError("pheromone evaporation_rate must be between 0 and 1")
    if not isinstance(policy.decay_model, str) or policy.decay_model not in SUPPORTED_PHEROMONE_DECAY_MODELS:
        raise GovernanceError(f"unsupported pheromone decay model: {policy.decay_model}")
    minimum = _non_negative_number(policy.min_strength, "pheromone min_strength")
    maximum = _non_negative_number(policy.max_strength, "pheromone max_strength")
    if minimum > maximum:
        raise GovernanceError("pheromone min_strength must not exceed max_strength")
    for name in (
        "positive_weight",
        "negative_weight",
        "cautionary_weight",
        "cautionary_override_threshold",
        "novelty_weight",
        "per_source_cap",
        "per_round_deposit_cap",
        "activation_threshold",
        "saturation_threshold",
        "exploration_floor",
        "stale_route_reopen_threshold",
        "response_exploration_floor",
    ):
        _non_negative_number(getattr(policy, name), f"pheromone {name}")
    for name in ("exploration_floor", "response_exploration_floor"):
        if getattr(policy, name) > 1:
            raise GovernanceError(f"pheromone {name} must be between 0 and 1")
    if policy.enabled and any(
        policy.min_strength > bound
        for bound in (policy.max_strength, policy.per_source_cap, policy.per_round_deposit_cap)
    ):
        raise GovernanceError(
            "pheromone minimum strength must fit max/source/round bounds"
        )
    novelty_decay_rate = _finite_number(policy.novelty_decay_rate, "pheromone novelty_decay_rate")
    if not 0 <= novelty_decay_rate <= 1:
        raise GovernanceError("pheromone novelty_decay_rate must be between 0 and 1")
    if isinstance(policy.min_source_diversity, bool) or not isinstance(policy.min_source_diversity, int):
        raise GovernanceError("pheromone min_source_diversity must be a positive integer")
    if policy.min_source_diversity <= 0:
        raise GovernanceError("pheromone min_source_diversity must be a positive integer")
    if not isinstance(policy.response_model, str) or policy.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
        raise GovernanceError(f"unsupported pheromone response model: {policy.response_model}")
    if not isinstance(policy.competition_mode, str) or policy.competition_mode not in SUPPORTED_PHEROMONE_COMPETITION_MODES:
        raise GovernanceError(f"unsupported pheromone competition mode: {policy.competition_mode}")
    if not policy.scored_subject_types:
        raise GovernanceError("pheromone scored_subject_types must not be empty")
    for subject_type in policy.scored_subject_types:
        if not isinstance(subject_type, str) or (
            not is_scored_pheromone_subject_type(subject_type)
        ):
            raise GovernanceError(
                f"unsupported or non-scoring pheromone subject type: {subject_type}"
            )
    if len(set(policy.scored_subject_types)) != len(policy.scored_subject_types):
        raise GovernanceError("pheromone scored_subject_types must not contain duplicates")
    for kind, profile in policy.kind_profiles.items():
        if not isinstance(kind, str) or (
            kind not in SUPPORTED_PHEROMONE_KINDS and not is_extension_pheromone_value(kind)
        ):
            raise GovernanceError(f"unsupported pheromone kind profile: {kind}")
        if not isinstance(profile, PheromoneKindProfile):
            raise GovernanceError(f"pheromone kind profile has invalid type: {kind}")
        _non_negative_number(profile.weight, f"pheromone kind profile {kind} weight")
        if profile.evaporation_rate is not None:
            rate = _finite_number(profile.evaporation_rate, f"pheromone kind profile {kind} evaporation_rate")
            if not 0 <= rate <= 1:
                raise GovernanceError(f"pheromone kind profile {kind} evaporation_rate must be between 0 and 1")
        if profile.ttl_steps is not None:
            _non_negative_step(profile.ttl_steps, f"pheromone kind profile {kind} ttl_steps")
        if not isinstance(profile.response_model, str) or profile.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
            raise GovernanceError(f"unsupported pheromone kind profile response model: {profile.response_model}")
        if isinstance(profile.priority, bool) or not isinstance(profile.priority, int) or profile.priority < 0:
            raise GovernanceError(f"pheromone kind profile {kind} priority must be a non-negative integer")
        if not isinstance(profile.can_suppress_positive, bool):
            raise GovernanceError(f"pheromone kind profile {kind} can_suppress_positive must be boolean")
        for subject_type in profile.scored_subject_types:
            if not isinstance(subject_type, str) or (
                not is_scored_pheromone_subject_type(subject_type)
            ):
                raise GovernanceError(
                    f"unsupported or non-scoring pheromone subject type: {subject_type}"
                )
        if len(set(profile.scored_subject_types)) != len(profile.scored_subject_types):
            raise GovernanceError(f"pheromone kind profile {kind} subject types must not contain duplicates")
        if kind == "stale" and (profile.weight != 0 or profile.scored_subject_types):
            raise GovernanceError("stale pheromone kind profile must remain no-score")
    if policy.activation_threshold > 0:
        threshold_weights = []
        for kind in set(SUPPORTED_PHEROMONE_KINDS) | set(policy.kind_profiles):
            if kind == "stale":
                continue
            profile = policy.kind_profiles.get(kind)
            if not effective_pheromone_scored_subject_types(
                kind,
                profile,
                policy.scored_subject_types,
            ):
                continue
            response_model = profile.response_model if profile is not None else policy.response_model
            if response_model != "threshold":
                continue
            weight = profile.weight if profile is not None else legacy_pheromone_weight(kind, policy)
            threshold_weights.append(float(weight))
        maximum_threshold_delta = policy.max_strength * max(threshold_weights, default=0.0)
        if threshold_weights and (
            maximum_threshold_delta <= 0
            or policy.activation_threshold > maximum_threshold_delta
        ):
            raise GovernanceError(
                "pheromone activation_threshold cannot be reached by any declared threshold response"
            )


def validate_pheromone_diffusion_policy(policy: PheromoneDiffusionPolicy) -> None:
    if not isinstance(policy.enabled, bool):
        raise GovernanceError("pheromone diffusion enabled must be boolean")
    if isinstance(policy.max_hops, bool) or not isinstance(policy.max_hops, int) or policy.max_hops < 0:
        raise GovernanceError("pheromone diffusion max_hops must be a non-negative integer")
    attenuation = _finite_number(policy.attenuation, "pheromone diffusion attenuation")
    if not 0 <= attenuation <= 1:
        raise GovernanceError("pheromone diffusion attenuation must be between 0 and 1")
    if policy.enabled and (policy.max_hops <= 0 or attenuation <= 0):
        raise GovernanceError("enabled pheromone diffusion requires positive hops and attenuation")


def validate_pheromone_budget_state(
    budget_state: PheromoneBudgetState,
    policy: PheromonePolicy,
) -> None:
    round_cap = _non_negative_number(budget_state.round_cap, "pheromone budget round_cap")
    source_cap = _non_negative_number(budget_state.per_source_cap, "pheromone budget per_source_cap")
    round_used = _non_negative_number(budget_state.round_used, "pheromone budget round_used")
    if round_cap != float(policy.per_round_deposit_cap) or source_cap != float(policy.per_source_cap):
        raise GovernanceError("pheromone budget state caps do not match active policy")
    if round_used > round_cap:
        raise GovernanceError("pheromone round budget usage exceeds declared cap")
    total_source_usage = 0.0
    for source_id, used in budget_state.source_used.items():
        if not isinstance(source_id, str):
            raise GovernanceError("pheromone budget source identity must be a string")
        amount = _non_negative_number(used, f"pheromone budget source usage {source_id}")
        if amount > source_cap:
            raise GovernanceError("pheromone source budget usage exceeds declared cap")
        total_source_usage += amount
    if not math.isfinite(total_source_usage):
        raise GovernanceError("pheromone source budget usage must remain finite")
    if abs(total_source_usage - round_used) > 1e-9:
        raise GovernanceError("pheromone budget round and source usage do not reconstruct")


def pheromone_budget_for_policy(
    policy: PheromonePolicy,
    budget_state: PheromoneBudgetState | None,
) -> PheromoneBudgetState:
    state = budget_state or PheromoneBudgetState.for_policy(policy)
    validate_pheromone_budget_state(state, policy)
    return state


def clip_pheromone_strength(strength: float, policy: PheromonePolicy) -> float:
    validate_pheromone_policy(policy)
    value = _finite_number(strength, "pheromone strength")
    clipped = min(policy.max_strength, max(policy.min_strength, value))
    if not math.isfinite(clipped):
        raise GovernanceError("clipped pheromone strength must be finite")
    return clipped


def validate_pheromone_trail(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    allow_strength_above_max: bool = False,
    allow_strength_below_min: bool = False,
) -> None:
    validate_pheromone_policy(policy)
    for field_name in (
        "candidate_id",
        "subject_type",
        "subject_id",
        "target",
        "route_id",
        "tool_id",
        "kind",
        "source_id",
        "source_role",
        "evidence_id",
        "provenance",
        "trace_event_id",
        "diffusion_root_trace_event_id",
        "diffusion_parent_trace_event_id",
    ):
        if not isinstance(getattr(trail, field_name), str):
            raise GovernanceError(f"pheromone trail {field_name} must be a string")
    if trail.subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES and not is_extension_pheromone_value(trail.subject_type):
        raise GovernanceError(f"unsupported pheromone subject type: {trail.subject_type}")
    if trail.kind not in SUPPORTED_PHEROMONE_KINDS and not is_extension_pheromone_value(trail.kind):
        raise GovernanceError(f"unsupported pheromone kind: {trail.kind}")
    strength = _non_negative_number(trail.strength, "pheromone strength")
    if not allow_strength_below_min and strength < policy.min_strength:
        raise GovernanceError("active pheromone strength is below the declared minimum")
    if not allow_strength_above_max and strength > policy.max_strength:
        raise GovernanceError("active pheromone strength exceeds the declared maximum")
    if not is_nonblank_string(pheromone_subject_id(trail)):
        raise GovernanceError("pheromone trail must declare a subject")
    for field_name in ("candidate_id", "target", "route_id", "tool_id", "source_role", "evidence_id"):
        value = getattr(trail, field_name)
        if value and not is_nonblank_string(value):
            raise GovernanceError(f"pheromone trail {field_name} must be non-blank when declared")
    candidate_id = pheromone_bound_candidate_id(trail)
    subject_type = pheromone_subject_type(trail)
    subject_id = pheromone_subject_id(trail)
    if subject_type == "candidate" and candidate_id != subject_id:
        raise GovernanceError("candidate pheromone subject_id must match candidate_id")
    if candidate_id and candidate_set is not None:
        candidate = candidate_set.require_declared(candidate_id)
        if trail.target and trail.target != candidate.target:
            raise GovernanceError(
                f"pheromone trail targets {trail.target}, not candidate target {candidate.target}"
            )
        if target is not None and candidate.target != target:
            raise GovernanceError(
                f"pheromone trail candidate targets {candidate.target}, not active target {target}"
            )
    if trail.source_id and not is_nonblank_string(trail.source_id):
        raise GovernanceError("pheromone trail source_id must be non-blank")
    if target is not None:
        if not is_nonblank_string(trail.target):
            raise GovernanceError("target-scoped pheromone trail must declare target")
        if trail.target != target:
            raise GovernanceError(f"pheromone trail targets {trail.target}, not active target {target}")
    if policy.require_provenance and not is_nonblank_string(trail.provenance):
        raise GovernanceError("pheromone trail is missing provenance")
    if policy.require_trace and not is_nonblank_string(trail.trace_event_id):
        raise GovernanceError("pheromone trail is missing trace event id")
    # Legacy non-Hybrid callers may score anonymous trails when neither
    # provenance nor trace lineage is part of their declared contract.  A
    # lineage-aware policy, including every valid Hybrid policy, must bind the
    # trail to a non-blank source identity.
    if (
        policy.enabled
        and (policy.require_provenance or policy.require_trace)
        and not is_nonblank_string(pheromone_source_id(trail))
    ):
        raise GovernanceError("active pheromone trail requires a non-blank source identity")
    _non_negative_step(trail.deposited_at_step, "pheromone deposited_at_step")
    _non_negative_step(trail.updated_at_step, "pheromone updated_at_step")
    if trail.updated_at_step < trail.deposited_at_step:
        raise GovernanceError("pheromone updated step must not precede deposit step")
    if trail.ttl_steps is not None:
        _non_negative_step(trail.ttl_steps, "pheromone ttl_steps")
    if any(not is_nonblank_string(item) for item in trail.lineage_event_ids):
        raise GovernanceError("pheromone lineage_event_ids must be non-empty strings")
    if len(set(trail.lineage_event_ids)) != len(trail.lineage_event_ids):
        raise GovernanceError("pheromone lineage_event_ids must not contain duplicates")
    _non_negative_step(trail.diffusion_hop, "pheromone diffusion_hop")
    if trail.diffusion_hop == 0:
        if trail.diffusion_root_trace_event_id or trail.diffusion_parent_trace_event_id:
            raise GovernanceError("root pheromone trail cannot declare diffusion lineage")
    elif not (
        is_nonblank_string(trail.diffusion_root_trace_event_id)
        and is_nonblank_string(trail.diffusion_parent_trace_event_id)
    ):
        raise GovernanceError("derived pheromone trail requires explicit diffusion lineage")
    elif (
        trail.diffusion_root_trace_event_id not in trail.lineage_event_ids
        or trail.diffusion_parent_trace_event_id not in trail.lineage_event_ids
        or trail.trace_event_id == trail.diffusion_root_trace_event_id
    ):
        raise GovernanceError("derived pheromone trail diffusion lineage is inconsistent")


def deposit_pheromone(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
) -> PheromoneTrail:
    result = deposit_pheromone_trails(
        [trail],
        policy,
        candidate_set=candidate_set,
        target=target,
        budget_state=budget_state,
    )
    if not result.trails:
        raise GovernanceError("pheromone deposit was rejected by the active budget")
    return result.trails[0]


def deposit_pheromone_trails(
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
    processed_event_ids: frozenset[str] = frozenset(),
) -> PheromoneBatchResult:
    """Validate and apply a deposit batch atomically.

    Budgets are allocated in canonical priority order, while the returned trails
    retain caller order.  Validation completes for the entire batch before any
    transition record is produced.
    """

    validate_pheromone_policy(policy)
    items = list(trails)
    for trail in items:
        validate_pheromone_trail(
            trail,
            policy,
            candidate_set=candidate_set,
            target=target,
            allow_strength_above_max=True,
            allow_strength_below_min=True,
        )
    _reject_duplicate_trail_events(items, lifecycle="deposit")

    budget = pheromone_budget_for_policy(policy, budget_state)
    already_processed = set(processed_event_ids)
    replayed = tuple(sorted(trail.trace_event_id for trail in items if trail.trace_event_id in already_processed))
    pending = [trail for trail in items if trail.trace_event_id not in already_processed]
    deposited_by_identity: dict[int, PheromoneTrail] = {}
    records: list[PheromoneLifecycleRecord] = []
    indexed = sorted(enumerate(pending), key=lambda item: pheromone_processing_key(item[1], item[0], policy))
    for index, trail in indexed:
        # Preserve the caller's requested strength in lifecycle lineage.  The
        # bounded value is what consumes budget, but pre-clamping the recorded
        # request would hide a real max-strength clip from trace/conformance.
        requested = float(trail.strength)
        budget_request = min(requested, float(policy.max_strength))
        source_id = pheromone_source_id(trail)
        applied, updated_budget = budget.consume(source_id, budget_request)
        if applied < policy.min_strength:
            applied = 0.0
            updated_budget = budget
        budget = updated_budget
        deposited_trail = replace(trail, strength=applied)
        if applied > 0:
            deposited_by_identity[id(trail)] = deposited_trail
        records.append(
            lifecycle_record(
                "deposit" if applied > 0 else "deposit_rejected",
                deposited_trail,
                old_strength=0.0,
                requested_strength=requested,
                applied_strength=applied,
                round_budget_remaining=budget.round_remaining,
                source_budget_remaining=budget.source_remaining(source_id),
                causal_payload=_deposit_clip_causal_payload(trail),
            )
        )
        if trail.trace_event_id:
            already_processed.add(trail.trace_event_id)
    return PheromoneBatchResult(
        trails=tuple(
            deposited_by_identity[id(trail)]
            for trail in pending
            if id(trail) in deposited_by_identity
        ),
        records=tuple(records),
        processed_event_ids=frozenset(already_processed),
        budget_state=budget,
        replayed_event_ids=replayed,
    )


def clip_pheromone_deposit_strength(strength: float, policy: PheromonePolicy) -> float:
    validate_pheromone_policy(policy)
    value = _non_negative_number(strength, "pheromone deposit strength")
    clipped = min(policy.per_round_deposit_cap, policy.per_source_cap, policy.max_strength, value)
    if clipped < policy.min_strength:
        return 0.0
    return clipped


def evaporate_trails(
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> list[PheromoneTrail]:
    return list(evaporate_trails_with_records(trails, policy, current_step=current_step).trails)


def evaporate_trails_with_records(
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> PheromoneBatchResult:
    validate_pheromone_policy(policy)
    if current_step is not None:
        _non_negative_step(current_step, "current_step")
    items = list(trails)
    # Legacy evaporation accepts trails without deposit lineage, but numeric and
    # temporal state is still validated for the entire batch up front.
    relaxed_policy = replace(policy, require_provenance=False, require_trace=False)
    for trail in items:
        validate_pheromone_trail(trail, relaxed_policy)
        if current_step is not None and current_step < trail.updated_at_step:
            raise GovernanceError("current_step must not precede pheromone updated step")
    if not policy.enabled:
        return PheromoneBatchResult(trails=tuple(items))
    active: list[PheromoneTrail] = []
    records: list[PheromoneLifecycleRecord] = []
    for trail in items:
        updated = evaporate_trail(trail, policy, current_step=current_step)
        active.append(updated)
        if updated == trail:
            continue
        action = "expire" if updated.kind == "stale" and trail.kind != "stale" else "evaporate"
        elapsed_steps = updated.updated_at_step - trail.updated_at_step
        records.append(
            lifecycle_record(
                action,
                updated,
                old_strength=float(trail.strength),
                requested_strength=float(trail.strength),
                applied_strength=float(updated.strength) - float(trail.strength),
                source_kind=trail.kind,
                elapsed_steps=elapsed_steps,
                ttl_steps=(
                    trail.ttl_steps
                    if trail.ttl_steps is not None
                    else (
                        policy.kind_profiles[trail.kind].ttl_steps
                        if trail.kind in policy.kind_profiles
                        else None
                    )
                ),
            )
        )
    return PheromoneBatchResult(
        trails=tuple(active),
        records=tuple(records),
        processed_event_ids=frozenset(trail.trace_event_id for trail in active if trail.trace_event_id),
    )


def evaporate_trail(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> PheromoneTrail:
    validate_pheromone_policy(policy)
    relaxed_policy = replace(policy, require_provenance=False, require_trace=False)
    validate_pheromone_trail(trail, relaxed_policy)
    step = trail.updated_at_step + 1 if current_step is None else current_step
    _non_negative_step(step, "current_step")
    if step < trail.updated_at_step:
        raise GovernanceError("current_step must not precede pheromone updated step")
    active_policy = pheromone_policy_for_trail(trail, policy)
    if is_expired_with_policy(trail, active_policy, step):
        return replace(trail, kind="stale", strength=policy.min_strength, updated_at_step=step)

    elapsed_steps = step - trail.updated_at_step
    if elapsed_steps == 0:
        return trail
    retained = retained_pheromone_strength(trail.strength, active_policy, elapsed_steps)
    if trail.kind == "novelty" and policy.exploration_enabled:
        retained *= (1.0 - policy.novelty_decay_rate) ** elapsed_steps
        if not math.isfinite(retained):
            raise GovernanceError("novelty pheromone decay must remain finite")
    return replace(
        trail,
        strength=clip_pheromone_strength(retained, policy),
        updated_at_step=step,
    )


def retained_pheromone_strength(strength: float, policy: PheromonePolicy, elapsed_steps: int) -> float:
    validate_pheromone_policy(policy)
    value = _non_negative_number(strength, "pheromone strength")
    _non_negative_step(elapsed_steps, "elapsed_steps")
    retention = max(0.0, min(1.0, 1.0 - policy.evaporation_rate))
    if policy.decay_model == "exponential":
        retained = value * (retention ** elapsed_steps)
    elif policy.decay_model == "step":
        retained = value * retention if elapsed_steps > 0 else value
    else:
        retained = value * max(0.0, 1.0 - policy.evaporation_rate * elapsed_steps)
    if not math.isfinite(retained):
        raise GovernanceError("retained pheromone strength must be finite")
    return retained


def is_expired(trail: PheromoneTrail, current_step: int) -> bool:
    _non_negative_step(current_step, "current_step")
    if current_step < trail.updated_at_step:
        raise GovernanceError("current_step must not precede pheromone updated step")
    return trail.ttl_steps is not None and current_step - trail.deposited_at_step >= trail.ttl_steps


def is_expired_with_policy(trail: PheromoneTrail, policy: PheromonePolicy, current_step: int) -> bool:
    _non_negative_step(current_step, "current_step")
    if current_step < trail.updated_at_step:
        raise GovernanceError("current_step must not precede pheromone updated step")
    ttl_steps = trail.ttl_steps
    profile = policy.kind_profiles.get(trail.kind)
    if ttl_steps is None and profile is not None:
        ttl_steps = profile.ttl_steps
    return ttl_steps is not None and current_step - trail.deposited_at_step >= ttl_steps


def pheromone_policy_for_trail(trail: PheromoneTrail, policy: PheromonePolicy) -> PheromonePolicy:
    profile = policy.kind_profiles.get(trail.kind)
    if profile is None or profile.evaporation_rate is None:
        return policy
    return replace(policy, evaporation_rate=profile.evaporation_rate)


def pheromone_subject_type(trail: PheromoneTrail) -> str:
    if trail.subject_id:
        return trail.subject_type
    if trail.candidate_id:
        return "candidate"
    if trail.route_id:
        return "route"
    if trail.tool_id:
        return "tool"
    return trail.subject_type


def pheromone_subject_id(trail: PheromoneTrail) -> str:
    if trail.subject_id:
        return trail.subject_id
    if trail.candidate_id:
        return trail.candidate_id
    if trail.route_id:
        return trail.route_id
    if trail.tool_id:
        return trail.tool_id
    return ""


def pheromone_candidate_id(trail: PheromoneTrail) -> str:
    subject_type = pheromone_subject_type(trail)
    if subject_type != "candidate":
        return ""
    return pheromone_subject_id(trail)


def pheromone_bound_candidate_id(trail: PheromoneTrail) -> str:
    return trail.candidate_id or pheromone_candidate_id(trail)


def pheromone_lineage(
    trail: PheromoneTrail,
    *,
    old_strength: float | None = None,
    new_strength: float | None = None,
    step: int | None = None,
    score_delta: float | None = None,
    score_breakdown: dict[str, float] | None = None,
    fallback_used: bool | None = None,
    resolution: str = "",
) -> dict[str, Any]:
    lineage: dict[str, Any] = {
        "candidate_id": pheromone_bound_candidate_id(trail),
        "subject_type": pheromone_subject_type(trail),
        "subject_id": pheromone_subject_id(trail),
        "kind": trail.kind,
        "source_id": trail.source_id,
        "evidence_id": trail.evidence_id,
        "provenance": trail.provenance,
        "trace_event_id": trail.trace_event_id,
        "lineage_event_ids": list(trail.lineage_event_ids),
        "new_strength": trail.strength if new_strength is None else new_strength,
        "step": trail.updated_at_step if step is None else step,
    }
    if trail.target:
        lineage["target"] = trail.target
    if old_strength is not None:
        lineage["old_strength"] = old_strength
    if score_delta is not None:
        lineage["score_delta"] = score_delta
    if score_breakdown is not None:
        lineage["score_breakdown"] = dict(score_breakdown)
    if fallback_used is not None:
        lineage["fallback_used"] = fallback_used
    if resolution:
        lineage["resolution"] = resolution
    return lineage


def scoreable_pheromone_candidate_id(trail: PheromoneTrail, policy: PheromonePolicy) -> str:
    if trail.kind == "stale":
        return ""
    if trail.kind == "novelty" and not policy.exploration_enabled:
        return ""
    subject_type = pheromone_subject_type(trail)
    if subject_type == "evidence":
        return ""
    profile = policy.kind_profiles.get(trail.kind)
    scored_subject_types = effective_pheromone_scored_subject_types(
        trail.kind,
        profile,
        policy.scored_subject_types,
    )
    if subject_type not in scored_subject_types:
        return ""
    if subject_type == "candidate":
        return pheromone_candidate_id(trail)
    return trail.candidate_id


def pheromone_source_id(trail: PheromoneTrail) -> str:
    return trail.source_id or trail.provenance or ""


_DEFAULT_KIND_PRIORITY = {
    "alarm": 5,
    "cautionary": 4,
    "negative": 3,
    "positive": 2,
    "novelty": 1,
    "stale": 0,
}


def pheromone_kind_priority(trail: PheromoneTrail, policy: PheromonePolicy) -> int:
    profile = policy.kind_profiles.get(trail.kind)
    if profile is not None:
        return profile.priority
    return _DEFAULT_KIND_PRIORITY.get(trail.kind, -1)


def pheromone_processing_key(
    trail: PheromoneTrail,
    original_index: int,
    policy: PheromonePolicy,
) -> tuple[object, ...]:
    return (
        -pheromone_kind_priority(trail, policy),
        trail.target,
        pheromone_bound_candidate_id(trail),
        pheromone_subject_type(trail),
        pheromone_subject_id(trail),
        pheromone_source_id(trail),
        trail.kind,
        trail.trace_event_id,
        original_index,
    )


def _reject_duplicate_trail_events(trails: list[PheromoneTrail], *, lifecycle: str) -> None:
    seen_trace_ids: set[str] = set()
    seen_records: set[tuple[object, ...]] = set()
    for trail in trails:
        if trail.trace_event_id:
            if trail.trace_event_id in seen_trace_ids:
                raise GovernanceError(f"duplicate pheromone {lifecycle} trace_event_id: {trail.trace_event_id}")
            seen_trace_ids.add(trail.trace_event_id)
        identity = (
            trail.target,
            pheromone_bound_candidate_id(trail),
            pheromone_subject_type(trail),
            pheromone_subject_id(trail),
            trail.kind,
            pheromone_source_id(trail),
            trail.deposited_at_step,
            trail.updated_at_step,
        )
        if identity in seen_records:
            raise GovernanceError(f"duplicate equivalent pheromone {lifecycle} record")
        seen_records.add(identity)


def _trail_clip_payload(trail: PheromoneTrail) -> dict[str, Any]:
    """Snapshot every public trail input field for a deterministic receipt."""

    return {
        "candidate_id": trail.candidate_id,
        "strength": float(trail.strength),
        "subject_type": trail.subject_type,
        "subject_id": trail.subject_id,
        "target": trail.target,
        "route_id": trail.route_id,
        "tool_id": trail.tool_id,
        "kind": trail.kind,
        "source_id": trail.source_id,
        "source_role": trail.source_role,
        "evidence_id": trail.evidence_id,
        "provenance": trail.provenance,
        "trace_event_id": trail.trace_event_id,
        "deposited_at_step": trail.deposited_at_step,
        "updated_at_step": trail.updated_at_step,
        "ttl_steps": trail.ttl_steps,
        "lineage_event_ids": list(trail.lineage_event_ids),
        "diffusion_root_trace_event_id": trail.diffusion_root_trace_event_id,
        "diffusion_parent_trace_event_id": trail.diffusion_parent_trace_event_id,
        "diffusion_hop": trail.diffusion_hop,
    }


def _deposit_clip_causal_payload(trail: PheromoneTrail) -> dict[str, Any]:
    return {
        "lifecycle": "deposit",
        "input": _trail_clip_payload(trail),
        "effective": {
            "target": trail.target,
            "candidate_id": pheromone_bound_candidate_id(trail),
            "subject_type": pheromone_subject_type(trail),
            "subject_id": pheromone_subject_id(trail),
            "source_id": pheromone_source_id(trail),
        },
    }


def _diffusion_clip_causal_payload(
    *,
    source_trail: PheromoneTrail,
    target_subject: PheromoneSubject,
    edge: PheromoneEdge,
    policy_attenuation: float,
    hop: int,
    parent_trace_event_id: str,
    derived_trace_event_id: str,
    effective_target: str,
    effective_candidate_id: str,
    source_strength: float,
) -> dict[str, Any]:
    return {
        "lifecycle": "diffusion",
        "input": {
            "source_trail": _trail_clip_payload(source_trail),
            "target_subject": {
                "subject_type": target_subject.subject_type,
                "subject_id": target_subject.subject_id,
                "candidate_id": target_subject.candidate_id,
                "target": target_subject.target,
            },
            "edge": {
                "source_subject_type": edge.source_subject_type,
                "source_subject_id": edge.source_subject_id,
                "target_subject_type": edge.target_subject_type,
                "target_subject_id": edge.target_subject_id,
                "attenuation": float(edge.attenuation),
            },
            "policy_attenuation": float(policy_attenuation),
            "hop": hop,
            "parent_trace_event_id": parent_trace_event_id,
            "derived_trace_event_id": derived_trace_event_id,
        },
        "effective": {
            "target": effective_target,
            "candidate_id": effective_candidate_id,
            "subject_type": target_subject.subject_type,
            "subject_id": target_subject.subject_id,
            "source_id": pheromone_source_id(source_trail),
            "source_kind": source_trail.kind,
            "source_strength": float(source_strength),
            "root_trace_event_id": (
                source_trail.diffusion_root_trace_event_id
                or source_trail.trace_event_id
            ),
        },
    }


def _diffusion_replay_fingerprint(
    causal_payload: Mapping[str, Any],
) -> tuple[Any, ...]:
    return (
        "diffusion-v1",
        canonical_pheromone_clip_payload(causal_payload),
    )


def lifecycle_record(
    action: str,
    trail: PheromoneTrail,
    *,
    old_strength: float,
    requested_strength: float,
    applied_strength: float,
    source_kind: str | None = None,
    source_trace_event_id: str | None = None,
    round_budget_remaining: float | None = None,
    source_budget_remaining: float | None = None,
    hop: int = 0,
    attenuation: float = 1.0,
    policy_attenuation: float = 1.0,
    edge_attenuation: float = 1.0,
    elapsed_steps: int = 0,
    cause_trace_event_id: str = "",
    ttl_steps: int | None = None,
    causal_payload: Mapping[str, Any] | None = None,
) -> PheromoneLifecycleRecord:
    return PheromoneLifecycleRecord(
        action=action,
        target=trail.target,
        candidate_id=pheromone_bound_candidate_id(trail),
        subject_type=pheromone_subject_type(trail),
        subject_id=pheromone_subject_id(trail),
        kind=trail.kind,
        source_kind=source_kind or trail.kind,
        source_id=pheromone_source_id(trail),
        provenance=trail.provenance,
        source_trace_event_id=source_trace_event_id or trail.trace_event_id,
        trace_event_id=trail.trace_event_id,
        old_strength=old_strength,
        new_strength=float(trail.strength),
        requested_strength=requested_strength,
        applied_strength=applied_strength,
        round_budget_remaining=round_budget_remaining,
        source_budget_remaining=source_budget_remaining,
        hop=hop,
        attenuation=attenuation,
        policy_attenuation=policy_attenuation,
        edge_attenuation=edge_attenuation,
        step=trail.updated_at_step,
        elapsed_steps=elapsed_steps,
        cause_trace_event_id=cause_trace_event_id,
        deposited_at_step=trail.deposited_at_step,
        ttl_steps=trail.ttl_steps if ttl_steps is None else ttl_steps,
        _causal_payload_json=(
            canonical_pheromone_clip_payload(causal_payload)
            if causal_payload is not None
            else ""
        ),
    )


def collect_pheromone_source_diversity(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> dict[str, int]:
    _, source_diversity = _capped_pheromone_score_contributions(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    )
    return source_diversity


def _capped_pheromone_score_contributions(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None,
) -> tuple[
    tuple[tuple[PheromoneTrail, str, str, float, str], ...],
    dict[str, int],
]:
    """Resolve deterministic score deltas before applying the diversity gate.

    The per-source cap is global across candidates, so source diversity cannot
    be computed from merely eligible trail presence.  First allocate that cap
    in canonical kind/candidate/source order, then count only sources whose
    post-cap delta is nonzero for each candidate.  The caller can subsequently
    apply the minimum-diversity gate without letting a fully consumed source
    unlock another candidate.
    """

    validate_pheromone_policy(policy)
    if current_step is not None:
        _non_negative_step(current_step, "current_step")
    sources = {candidate.id: set() for candidate in candidate_set.candidates}
    if not policy.enabled:
        return (), {candidate_id: 0 for candidate_id in sources}

    items = list(trails)
    for trail in items:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set)
        if current_step is not None and current_step < trail.updated_at_step:
            raise GovernanceError("current_step must not precede pheromone updated step")
    ordered = [
        trail
        for _, trail in sorted(
            enumerate(items),
            key=lambda item: pheromone_processing_key(item[1], item[0], policy),
        )
    ]
    source_contribution: dict[object, float] = {}
    contributions: list[tuple[PheromoneTrail, str, str, float, str]] = []
    for trail in ordered:
        if current_step is not None and is_expired_with_policy(trail, policy, current_step):
            continue
        candidate_id = scoreable_pheromone_candidate_id(trail, policy)
        if not candidate_id:
            continue
        source_id = pheromone_source_id(trail)
        raw_delta, category = raw_pheromone_delta(trail, policy)
        if trail.kind == "novelty" and policy.exploration_enabled and current_step is not None:
            elapsed = current_step - trail.updated_at_step
            raw_delta *= (1.0 - policy.novelty_decay_rate) ** elapsed
        if raw_delta == 0:
            continue
        responded_delta = apply_pheromone_response(raw_delta, trail, policy)
        if not math.isfinite(responded_delta):
            raise GovernanceError("pheromone response must remain finite")
        if responded_delta == 0:
            continue
        delta = cap_source_contribution(
            responded_delta,
            candidate_id,
            source_id,
            policy,
            source_contribution,
        )
        if not math.isfinite(delta):
            raise GovernanceError("pheromone source contribution must remain finite")
        if delta == 0:
            continue
        contributions.append((trail, candidate_id, source_id, delta, category))
        if source_id:
            sources[candidate_id].add(source_id)
    return tuple(contributions), {
        candidate_id: len(candidate_sources)
        for candidate_id, candidate_sources in sources.items()
    }


def score_pheromone_trails(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> dict[str, float]:
    return dict(score_pheromone_trails_result(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    ).scores)


def score_pheromone_trails_with_breakdown(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    result = score_pheromone_trails_result(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    )
    return dict(result.scores), {
        candidate_id: dict(categories)
        for candidate_id, categories in result.score_breakdown.items()
    }


def score_pheromone_trails_result(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int | None = None,
) -> PheromoneScoreResult:
    validate_pheromone_policy(policy)
    if current_step is not None:
        _non_negative_step(current_step, "current_step")
    scores = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    breakdown = empty_score_breakdown(candidate_set)
    kind_breakdown: dict[str, dict[str, float]] = {
        candidate.id: {} for candidate in candidate_set.candidates
    }
    subject_breakdown: dict[str, dict[str, float]] = {
        candidate.id: {} for candidate in candidate_set.candidates
    }
    positive_support = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    positive_subject_support: dict[str, dict[str, float]] = {
        candidate.id: {} for candidate in candidate_set.candidates
    }
    suppressing_support = {candidate.id: 0.0 for candidate in candidate_set.candidates}
    if not policy.enabled:
        return PheromoneScoreResult(
            scores=scores,
            score_breakdown=breakdown,
            kind_breakdown=kind_breakdown,
            subject_breakdown=subject_breakdown,
        )

    contributions, source_diversity = _capped_pheromone_score_contributions(
        candidate_set=candidate_set,
        trails=trails,
        policy=policy,
        current_step=current_step,
    )
    competitive_response = policy.response_model == "competitive" or policy.competition_mode == "normalize"
    competitive_kinds: set[str] = set()
    for trail, candidate_id, _, delta, category in contributions:
        if source_diversity[candidate_id] < policy.min_source_diversity:
            continue
        profile = policy.kind_profiles.get(trail.kind)
        if profile is not None and profile.response_model == "competitive":
            competitive_response = True
            competitive_kinds.add(trail.kind)
        scores[candidate_id] += delta
        add_breakdown(breakdown, candidate_id, category, delta)
        add_dimension_breakdown(kind_breakdown, candidate_id, trail.kind, delta)
        subject_dimension = pheromone_subject_type(trail)
        add_dimension_breakdown(subject_breakdown, candidate_id, subject_dimension, delta)
        if trail.kind == "positive":
            positive_support[candidate_id] += delta
            add_dimension_breakdown(
                positive_subject_support,
                candidate_id,
                subject_dimension,
                delta,
            )
        elif trail.kind in {"cautionary", "alarm"} and pheromone_kind_can_suppress_positive(trail.kind, policy):
            suppressing_support[candidate_id] += abs(delta)

    for candidate_id, cautionary in suppressing_support.items():
        if cautionary > 0 and cautionary >= policy.cautionary_override_threshold:
            scores[candidate_id] -= positive_support[candidate_id]
            add_breakdown(breakdown, candidate_id, "pheromone_cautionary", -positive_support[candidate_id])
            add_dimension_breakdown(
                kind_breakdown,
                candidate_id,
                "cautionary_suppression",
                -positive_support[candidate_id],
            )
            for subject_type, positive_delta in positive_subject_support[candidate_id].items():
                add_dimension_breakdown(
                    subject_breakdown,
                    candidate_id,
                    subject_type,
                    -positive_delta,
                )
    if policy.response_exploration_floor > 0:
        response_floor = min(float(policy.max_strength), float(policy.response_exploration_floor))
        for candidate in candidate_set.candidates:
            if candidate.safe_fallback:
                continue
            candidate_id = candidate.id
            current = scores[candidate_id]
            if current < 0 or current >= response_floor:
                continue
            delta = response_floor - current
            scores[candidate_id] += delta
            add_breakdown(breakdown, candidate_id, "pheromone_response_floor", delta)
            add_dimension_breakdown(
                kind_breakdown,
                candidate_id,
                "response_exploration_floor",
                delta,
            )
            add_dimension_breakdown(
                subject_breakdown,
                candidate_id,
                "candidate",
                delta,
            )
    if policy.exploration_enabled and policy.exploration_floor > 0:
        for candidate in candidate_set.candidates:
            if candidate.safe_fallback:
                continue
            candidate_id = candidate.id
            scores[candidate_id] += policy.exploration_floor
            add_breakdown(breakdown, candidate_id, "pheromone_novelty", policy.exploration_floor)
            add_dimension_breakdown(
                kind_breakdown,
                candidate_id,
                "exploration_floor",
                policy.exploration_floor,
            )
            add_dimension_breakdown(
                subject_breakdown,
                candidate_id,
                "candidate",
                policy.exploration_floor,
            )
    normalization: PheromoneNormalizationRecord | None = None
    if competitive_response:
        pre_scores = dict(scores)
        normalization_offsets = normalize_pheromone_scores(scores, breakdown)
        for candidate_id, offset in normalization_offsets.items():
            add_dimension_breakdown(kind_breakdown, candidate_id, "normalization", offset)
            add_dimension_breakdown(subject_breakdown, candidate_id, "candidate", offset)
        response_model = policy.response_model
        if response_model != "competitive" and competitive_kinds:
            response_model = "competitive:" + ",".join(sorted(competitive_kinds))
        normalization = PheromoneNormalizationRecord(
            response_model=response_model,
            competition_mode=policy.competition_mode,
            candidate_ids=tuple(sorted(scores)),
            pre_scores=pre_scores,
            post_scores=dict(scores),
        )
    for candidate_id in scores:
        reconstructed = math.fsum(breakdown[candidate_id].values())
        if not math.isfinite(reconstructed):
            raise GovernanceError("pheromone score breakdown must remain finite")
        if abs(math.fsum(kind_breakdown[candidate_id].values()) - reconstructed) > 1e-9:
            raise GovernanceError("pheromone kind breakdown does not reconstruct candidate score")
        if abs(math.fsum(subject_breakdown[candidate_id].values()) - reconstructed) > 1e-9:
            raise GovernanceError("pheromone subject breakdown does not reconstruct candidate score")
        scores[candidate_id] = reconstructed
    if normalization is not None:
        normalization = replace(normalization, post_scores=dict(scores))
    return PheromoneScoreResult(
        scores=scores,
        score_breakdown=breakdown,
        kind_breakdown=kind_breakdown,
        subject_breakdown=subject_breakdown,
        normalization=normalization,
    )


def pheromone_kind_can_suppress_positive(kind: str, policy: PheromonePolicy) -> bool:
    profile = policy.kind_profiles.get(kind)
    if profile is not None:
        return profile.can_suppress_positive
    # Preserve the pre-profile cautionary override as the legacy default.
    return kind in {"cautionary", "alarm"}


def raw_pheromone_delta(trail: PheromoneTrail, policy: PheromonePolicy) -> tuple[float, str]:
    strength = clip_pheromone_strength(trail.strength, policy)
    profile = policy.kind_profiles.get(trail.kind)
    if trail.kind not in SUPPORTED_PHEROMONE_KINDS and profile is None:
        return 0.0, "pheromone_positive"
    weight = profile.weight if profile is not None else legacy_pheromone_weight(trail.kind, policy)
    if trail.kind == "stale" or weight == 0:
        return 0.0, "pheromone_positive"
    subject_category = subject_breakdown_category(pheromone_subject_type(trail))
    category = subject_category or kind_breakdown_category(trail.kind)
    if trail.kind in {"negative", "cautionary", "alarm"}:
        return -(strength * weight), category
    return strength * weight, category


def legacy_pheromone_weight(kind: str, policy: PheromonePolicy) -> float:
    if kind == "positive":
        return policy.positive_weight
    if kind == "negative":
        return policy.negative_weight
    if kind == "cautionary":
        return policy.cautionary_weight
    if kind == "alarm":
        return policy.cautionary_weight
    if kind == "novelty":
        return policy.novelty_weight
    return 0.0


def kind_breakdown_category(kind: str) -> str:
    if kind == "negative":
        return "pheromone_negative"
    if kind == "cautionary":
        return "pheromone_cautionary"
    if kind == "alarm":
        return "pheromone_alarm"
    if kind == "novelty":
        return "pheromone_novelty"
    return "pheromone_positive"


def subject_breakdown_category(subject_type: str) -> str:
    if subject_type == "route":
        return "pheromone_route"
    if subject_type == "tool":
        return "pheromone_tool"
    if subject_type == "agent":
        return "pheromone_agent"
    return ""


def apply_pheromone_response(delta: float, trail: PheromoneTrail, policy: PheromonePolicy) -> float:
    value = _finite_number(delta, "pheromone score delta")
    profile = policy.kind_profiles.get(trail.kind)
    response_model = profile.response_model if profile is not None else policy.response_model
    if response_model == "threshold" and abs(value) < policy.activation_threshold:
        return 0.0
    if response_model == "saturating":
        threshold = policy.saturation_threshold
        if threshold <= 0:
            return 0.0
        sign = 1 if value >= 0 else -1
        magnitude = abs(value)
        response = sign * ((magnitude * threshold) / (magnitude + threshold))
        if not math.isfinite(response):
            raise GovernanceError("pheromone response must remain finite")
        return response
    return value


def normalize_pheromone_scores(
    scores: dict[str, float],
    breakdown: dict[str, dict[str, float]],
) -> dict[str, float]:
    if not scores:
        return {}
    for candidate_id, score in scores.items():
        _finite_number(score, f"pheromone score for {candidate_id}")
    mean_score = math.fsum(scores.values()) / len(scores)
    if not math.isfinite(mean_score):
        raise GovernanceError("normalized pheromone mean must remain finite")
    offsets: dict[str, float] = {}
    for candidate_id in sorted(scores):
        scores[candidate_id] -= mean_score
        add_breakdown(breakdown, candidate_id, "pheromone_positive", -mean_score)
        offsets[candidate_id] = -mean_score
    return offsets


def empty_score_breakdown(candidate_set: CandidateSet) -> dict[str, dict[str, float]]:
    return {
        candidate.id: {category: 0.0 for category in BREAKDOWN_CATEGORIES}
        for candidate in candidate_set.candidates
    }


def add_breakdown(
    breakdown: dict[str, dict[str, float]],
    candidate_id: str,
    category: str,
    delta: float,
) -> None:
    value = _finite_number(delta, f"score breakdown {category}")
    if candidate_id not in breakdown:
        breakdown[candidate_id] = {item: 0.0 for item in BREAKDOWN_CATEGORIES}
    if category not in breakdown[candidate_id]:
        breakdown[candidate_id][category] = 0.0
    updated = breakdown[candidate_id][category] + value
    if not math.isfinite(updated):
        raise GovernanceError(f"score breakdown {category} must remain finite")
    breakdown[candidate_id][category] = updated


def add_dimension_breakdown(
    breakdown: dict[str, dict[str, float]],
    candidate_id: str,
    dimension: str,
    delta: float,
) -> None:
    value = _finite_number(delta, f"pheromone dimension breakdown {dimension}")
    categories = breakdown.setdefault(candidate_id, {})
    updated = categories.get(dimension, 0.0) + value
    if not math.isfinite(updated):
        raise GovernanceError(f"pheromone dimension breakdown must remain finite: {dimension}")
    categories[dimension] = updated


def validate_pheromone_topology(
    neighborhood: PheromoneNeighborhood,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
) -> None:
    subjects: dict[tuple[str, str], PheromoneSubject] = {}
    for subject in neighborhood.subjects:
        for field_name in ("subject_type", "subject_id", "candidate_id", "target"):
            if not isinstance(getattr(subject, field_name), str):
                raise GovernanceError(f"pheromone topology subject {field_name} must be a string")
        for field_name in ("candidate_id", "target"):
            value = getattr(subject, field_name)
            if value and not is_nonblank_string(value):
                raise GovernanceError(
                    f"pheromone topology subject {field_name} must be non-blank when declared"
                )
        if not isinstance(subject.subject_type, str) or (
            subject.subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES
            and not is_extension_pheromone_value(subject.subject_type)
        ):
            raise GovernanceError(f"unsupported pheromone subject type: {subject.subject_type}")
        if not is_nonblank_string(subject.subject_id):
            raise GovernanceError("pheromone topology subject_id is required")
        key = subject_key(subject.subject_type, subject.subject_id)
        if key in subjects:
            raise GovernanceError(f"duplicate pheromone topology subject: {subject.subject_type}:{subject.subject_id}")
        subjects[key] = subject
        candidate_id = topology_subject_candidate_id(subject)
        if subject.subject_type == "candidate" and candidate_id != subject.subject_id:
            raise GovernanceError("candidate topology subject_id must match candidate_id")
        if subject.subject_type != "candidate" and not is_nonblank_string(subject.candidate_id):
            raise GovernanceError(
                "non-candidate pheromone topology subject must declare candidate_id"
            )
        if candidate_id and candidate_set is not None:
            candidate = candidate_set.require_declared(candidate_id)
            if subject.target and candidate.target != subject.target:
                raise GovernanceError(
                    f"pheromone topology subject targets {subject.target}, not candidate target {candidate.target}"
                )
            if target is not None and candidate.target != target:
                raise GovernanceError(
                    f"pheromone topology subject candidate targets {candidate.target}, not active target {target}"
                )
        resolved_target = topology_subject_target(subject, candidate_set)
        if target is not None:
            if not resolved_target:
                raise GovernanceError("target-scoped pheromone topology subject must declare target or candidate binding")
            if resolved_target != target:
                raise GovernanceError(
                    f"pheromone topology subject targets {resolved_target}, not active target {target}"
                )
    seen_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    for edge in neighborhood.edges:
        for field_name in (
            "source_subject_type",
            "source_subject_id",
            "target_subject_type",
            "target_subject_id",
        ):
            if not is_nonblank_string(getattr(edge, field_name)):
                raise GovernanceError(f"pheromone edge {field_name} must be a non-empty string")
        if not isinstance(edge.source_subject_type, str) or (
            edge.source_subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES
            and not is_extension_pheromone_value(edge.source_subject_type)
        ):
            raise GovernanceError(f"unsupported pheromone edge source type: {edge.source_subject_type}")
        if not isinstance(edge.target_subject_type, str) or (
            edge.target_subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES
            and not is_extension_pheromone_value(edge.target_subject_type)
        ):
            raise GovernanceError(f"unsupported pheromone edge target type: {edge.target_subject_type}")
        attenuation = _finite_number(edge.attenuation, "pheromone edge attenuation")
        if not 0 <= attenuation <= 1:
            raise GovernanceError("pheromone edge attenuation must be between 0 and 1")
        source = subject_key(edge.source_subject_type, edge.source_subject_id)
        destination = subject_key(edge.target_subject_type, edge.target_subject_id)
        if source not in subjects or destination not in subjects:
            raise GovernanceError("pheromone edge must reference declared topology subjects")
        edge_identity = (source, destination)
        if edge_identity in seen_edges:
            raise GovernanceError("duplicate pheromone topology edge")
        seen_edges.add(edge_identity)
        source_target = topology_subject_target(subjects[source], candidate_set)
        destination_target = topology_subject_target(subjects[destination], candidate_set)
        if source_target and destination_target and source_target != destination_target:
            raise GovernanceError(
                f"pheromone edge crosses targets: {source_target} -> {destination_target}"
            )


def topology_subject_candidate_id(subject: PheromoneSubject) -> str:
    if subject.candidate_id:
        return subject.candidate_id
    if subject.subject_type == "candidate":
        return subject.subject_id
    return ""


def topology_subject_target(
    subject: PheromoneSubject,
    candidate_set: CandidateSet | None,
) -> str:
    if subject.target:
        return subject.target
    candidate_id = topology_subject_candidate_id(subject)
    if candidate_id and candidate_set is not None:
        return candidate_set.require_declared(candidate_id).target
    return ""


def validate_pheromone_subject_binding(
    neighborhood: PheromoneNeighborhood,
    *,
    subject_type: str,
    subject_id: str,
    candidate_id: str,
    require_declared: bool,
) -> None:
    """Require one topology key to have one explicit candidate meaning.

    Subject keys are the topology identity.  Letting a route/tool/agent key
    inherit whichever candidate happens to reach it makes diffusion order an
    authority input, so connected or scored subjects must use their declared
    binding instead.
    """

    key = subject_key(subject_type, subject_id)
    subjects = {
        subject_key(subject.subject_type, subject.subject_id): subject
        for subject in neighborhood.subjects
    }
    subject = subjects.get(key)
    if subject is None:
        if require_declared:
            raise GovernanceError(
                f"pheromone subject is not declared in topology: {subject_type}:{subject_id}"
            )
        return
    declared_candidate_id = topology_subject_candidate_id(subject)
    if not declared_candidate_id:
        raise GovernanceError(
            f"pheromone topology subject has no candidate binding: {subject_type}:{subject_id}"
        )
    if candidate_id != declared_candidate_id:
        raise GovernanceError(
            "pheromone subject candidate binding does not match topology: "
            f"{subject_type}:{subject_id} binds {declared_candidate_id}, not {candidate_id}"
        )


def diffuse_pheromone_trails(
    trails: list[PheromoneTrail],
    neighborhood: PheromoneNeighborhood,
    policy: PheromonePolicy,
    diffusion_policy: PheromoneDiffusionPolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
    processed_event_ids: frozenset[str] = frozenset(),
    processed_event_receipts: Mapping[str, tuple[Any, ...]] | None = None,
) -> list[PheromoneTrail]:
    return list(
        diffuse_pheromone_trails_with_records(
            trails,
            neighborhood,
            policy,
            diffusion_policy,
            candidate_set=candidate_set,
            target=target,
            budget_state=budget_state,
            processed_event_ids=processed_event_ids,
            processed_event_receipts=processed_event_receipts,
        ).trails
    )


def diffuse_pheromone_trails_with_records(
    trails: list[PheromoneTrail],
    neighborhood: PheromoneNeighborhood,
    policy: PheromonePolicy,
    diffusion_policy: PheromoneDiffusionPolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
    processed_event_ids: frozenset[str] = frozenset(),
    processed_event_receipts: Mapping[str, tuple[Any, ...]] | None = None,
) -> PheromoneBatchResult:
    validate_pheromone_policy(policy)
    validate_pheromone_diffusion_policy(diffusion_policy)
    validate_pheromone_topology(neighborhood, candidate_set=candidate_set, target=target)
    items = list(trails)
    for trail in items:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set, target=target)
        validate_pheromone_subject_binding(
            neighborhood,
            subject_type=pheromone_subject_type(trail),
            subject_id=pheromone_subject_id(trail),
            candidate_id=pheromone_bound_candidate_id(trail),
            require_declared=bool(scoreable_pheromone_candidate_id(trail, policy)),
        )
    _reject_duplicate_trail_events(items, lifecycle="diffusion")
    budget = pheromone_budget_for_policy(policy, budget_state)
    processed = set(processed_event_ids)
    receipts = dict(processed_event_receipts or {})
    if not set(receipts).issubset(processed):
        raise GovernanceError(
            "pheromone diffusion replay receipt ids must be processed event ids"
        )
    if any(
        not is_nonblank_string(trace_event_id) or not isinstance(receipt, tuple)
        for trace_event_id, receipt in receipts.items()
    ):
        raise GovernanceError(
            "pheromone diffusion replay receipts require non-blank ids and tuple payloads"
        )
    replayed: set[str] = set()
    if not diffusion_policy.enabled:
        return PheromoneBatchResult(
            trails=tuple(items),
            processed_event_ids=frozenset(processed),
            budget_state=budget,
            _processed_event_receipts=tuple(sorted(receipts.items())),
        )

    subjects = {subject_key(subject.subject_type, subject.subject_id): subject for subject in neighborhood.subjects}
    edges = outgoing_edges(neighborhood)
    diffused = list(items)
    records: list[PheromoneLifecycleRecord] = []
    ordered = [
        trail
        for _, trail in sorted(
            enumerate(items),
            key=lambda item: pheromone_processing_key(item[1], item[0], policy),
        )
    ]
    for trail in ordered:
        # Derived trails are explicit ABI records produced by a complete
        # bounded BFS from their source root. Reusing them as roots on replay
        # would create propagation beyond the declared lifecycle record.
        if trail.diffusion_hop > 0:
            continue
        start = subject_key(pheromone_subject_type(trail), pheromone_subject_id(trail))
        if start not in subjects:
            continue
        start_target = topology_subject_target(subjects[start], candidate_set)
        trail_target = trail.target
        if not trail_target and pheromone_bound_candidate_id(trail) and candidate_set is not None:
            trail_target = candidate_set.require_declared(pheromone_bound_candidate_id(trail)).target
        if start_target and trail_target and start_target != trail_target:
            raise GovernanceError(
                f"pheromone trail target {trail_target} does not match topology subject target {start_target}"
            )
        frontier = [(start, 0, trail.strength, trail.trace_event_id)]
        visited = {start}
        while frontier:
            current, hops, strength, parent_trace_event_id = frontier.pop(0)
            if hops >= diffusion_policy.max_hops:
                continue
            for edge in edges.get(current, []):
                next_key = subject_key(edge.target_subject_type, edge.target_subject_id)
                if next_key in visited:
                    continue
                visited.add(next_key)
                next_hops = hops + 1
                requested_strength = strength * diffusion_policy.attenuation * edge.attenuation
                if not math.isfinite(requested_strength):
                    raise GovernanceError("diffused pheromone strength must remain finite")
                if requested_strength <= 0:
                    continue
                subject = subjects[next_key]
                candidate_id = topology_subject_candidate_id(subject) or trail.candidate_id
                subject_target = topology_subject_target(subject, candidate_set) or trail_target
                source_id = pheromone_source_id(trail)
                derived_trace_id = pheromone_diffusion_trace_event_id(
                    trail.trace_event_id,
                    next_hops,
                    subject.subject_type,
                    subject.subject_id,
                )
                parent_trail = next(
                    (
                        item
                        for item in reversed(diffused)
                        if item.trace_event_id == parent_trace_event_id
                    ),
                    trail,
                )
                causal_payload = _diffusion_clip_causal_payload(
                    source_trail=parent_trail,
                    target_subject=subject,
                    edge=edge,
                    policy_attenuation=diffusion_policy.attenuation,
                    hop=next_hops,
                    parent_trace_event_id=parent_trace_event_id,
                    derived_trace_event_id=derived_trace_id,
                    effective_target=subject_target,
                    effective_candidate_id=candidate_id,
                    source_strength=strength,
                )
                replay_fingerprint = _diffusion_replay_fingerprint(causal_payload)
                if derived_trace_id in processed:
                    expected = receipts.get(derived_trace_id)
                    if expected is None:
                        raise GovernanceError(
                            "processed pheromone diffusion id has no matching replay receipt: "
                            f"{derived_trace_id}"
                        )
                    if expected != replay_fingerprint:
                        raise GovernanceError(
                            "pheromone diffusion replay payload does not match its processed id: "
                            f"{derived_trace_id}"
                        )
                    replayed.add(derived_trace_id)
                    continue
                budget_request = min(requested_strength, float(policy.max_strength))
                applied_strength, updated_budget = budget.consume(source_id, budget_request)
                if applied_strength < policy.min_strength or applied_strength <= 0:
                    rejected = replace(
                        trail,
                        candidate_id=candidate_id,
                        strength=0.0,
                        subject_type=subject.subject_type,
                        subject_id=subject.subject_id,
                        target=subject_target,
                        trace_event_id=derived_trace_id,
                    )
                    records.append(
                        lifecycle_record(
                            "diffuse_rejected",
                            rejected,
                            old_strength=0.0,
                            requested_strength=requested_strength,
                            applied_strength=0.0,
                            source_trace_event_id=parent_trace_event_id,
                            round_budget_remaining=budget.round_remaining,
                            source_budget_remaining=budget.source_remaining(source_id),
                            hop=next_hops,
                            attenuation=diffusion_policy.attenuation * edge.attenuation,
                            policy_attenuation=diffusion_policy.attenuation,
                            edge_attenuation=edge.attenuation,
                            causal_payload=causal_payload,
                        )
                    )
                    processed.add(derived_trace_id)
                    receipts[derived_trace_id] = replay_fingerprint
                    continue
                budget = updated_budget
                diffused_trail = replace(
                    trail,
                    candidate_id=candidate_id,
                    strength=applied_strength,
                    subject_type=subject.subject_type,
                    subject_id=subject.subject_id,
                    target=subject_target,
                    trace_event_id=derived_trace_id,
                    diffusion_root_trace_event_id=trail.trace_event_id,
                    diffusion_parent_trace_event_id=parent_trace_event_id,
                    diffusion_hop=next_hops,
                    lineage_event_ids=tuple(
                        dict.fromkeys(
                            (*trail.lineage_event_ids, parent_trace_event_id)
                        )
                    ),
                )
                validate_pheromone_trail(
                    diffused_trail,
                    policy,
                    candidate_set=candidate_set,
                    target=target,
                )
                diffused.append(diffused_trail)
                processed.add(derived_trace_id)
                receipts[derived_trace_id] = replay_fingerprint
                attenuation = diffusion_policy.attenuation * edge.attenuation
                records.append(
                    lifecycle_record(
                        "diffuse",
                        diffused_trail,
                        old_strength=0.0,
                        requested_strength=requested_strength,
                        applied_strength=applied_strength,
                        source_trace_event_id=parent_trace_event_id,
                        round_budget_remaining=budget.round_remaining,
                        source_budget_remaining=budget.source_remaining(source_id),
                        hop=next_hops,
                        attenuation=attenuation,
                        policy_attenuation=diffusion_policy.attenuation,
                        edge_attenuation=edge.attenuation,
                        causal_payload=causal_payload,
                    )
                )
                # Propagate the actual bounded state, never the pre-budget
                # request, and bind the next hop to its immediate parent.
                frontier.append(
                    (next_key, next_hops, applied_strength, derived_trace_id)
                )
    return PheromoneBatchResult(
        trails=tuple(diffused),
        records=tuple(records),
        processed_event_ids=frozenset(processed),
        budget_state=budget,
        replayed_event_ids=tuple(sorted(replayed)),
        _processed_event_receipts=tuple(sorted(receipts.items())),
    )


def pheromone_diffusion_trace_event_id(
    root_trace_event_id: str,
    hop: int,
    subject_type: str,
    subject_id: str,
) -> str:
    """Build a collision-free deterministic identity from opaque ABI fields."""

    components = (root_trace_event_id, str(hop), subject_type, subject_id)
    return "diffuse:" + "".join(f"{len(item)}:{item}" for item in components)


def outgoing_edges(neighborhood: PheromoneNeighborhood) -> dict[tuple[str, str], list[PheromoneEdge]]:
    edges: dict[tuple[str, str], list[PheromoneEdge]] = {}
    for edge in neighborhood.edges:
        edges.setdefault(subject_key(edge.source_subject_type, edge.source_subject_id), []).append(edge)
    for items in edges.values():
        items.sort(key=lambda edge: (edge.target_subject_type, edge.target_subject_id))
    return edges


def subject_key(subject_type: str, subject_id: str) -> tuple[str, str]:
    return subject_type, subject_id


def observe_pheromone_exploration(
    *,
    candidate_set: CandidateSet,
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    current_step: int,
    target: str | None = None,
) -> tuple[PheromoneExplorationObservation, ...]:
    """Return deterministic runtime-facing exploration observations.

    Observations never create candidates, evidence, or score by themselves.
    Stale route reopening is eligibility only; the runtime must still produce a
    governed scout report before the route can affect commitment.
    """

    validate_pheromone_policy(policy)
    _non_negative_step(current_step, "current_step")
    if not policy.exploration_enabled:
        return ()
    observations: list[PheromoneExplorationObservation] = []
    items = list(trails)
    for trail in items:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set, target=target)
    for _, trail in sorted(
        enumerate(items),
        key=lambda item: pheromone_processing_key(item[1], item[0], policy),
    ):
        expired = is_expired_with_policy(trail, policy, current_step)
        is_stale_route = pheromone_subject_type(trail) == "route" and (trail.kind == "stale" or expired)
        novelty_pressure = 0.0
        if trail.kind == "novelty" and not expired:
            elapsed = current_step - trail.updated_at_step
            novelty_pressure = float(trail.strength) * ((1.0 - policy.novelty_decay_rate) ** elapsed)
            novelty_pressure = min(float(policy.max_strength), max(0.0, novelty_pressure))
        reopen_eligible = (
            is_stale_route
            and float(trail.strength) <= float(policy.stale_route_reopen_threshold)
        )
        if novelty_pressure <= 0 and not reopen_eligible:
            continue
        reason = "stale_route_reopen_eligible" if reopen_eligible else "novelty_pressure_observed"
        observations.append(
            PheromoneExplorationObservation(
                target=trail.target,
                candidate_id=pheromone_bound_candidate_id(trail),
                subject_type=pheromone_subject_type(trail),
                subject_id=pheromone_subject_id(trail),
                novelty_pressure=novelty_pressure,
                reopen_eligible=reopen_eligible,
                reason=reason,
                trace_event_id=trail.trace_event_id,
            )
        )
    return tuple(observations)


def cap_source_contribution(
    delta: float,
    candidate_id: str,
    source_id: str,
    policy: PheromonePolicy,
    source_contribution: dict[object, float],
) -> float:
    del candidate_id  # The cap follows source identity across all candidates.
    _finite_number(delta, "pheromone source contribution")
    key = source_id
    used = source_contribution.get(key, 0.0)
    remaining = max(0.0, policy.per_source_cap - used)
    allowed = min(abs(delta), remaining)
    source_contribution[key] = used + allowed
    return allowed if delta >= 0 else -allowed


def is_extension_pheromone_value(value: str) -> bool:
    return isinstance(value, str) and any(
        value.startswith(prefix) and len(value) > len(prefix)
        for prefix in PHEROMONE_EXTENSION_PREFIXES
    )
