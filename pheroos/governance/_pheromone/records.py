from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from pheroos.protocol.models import PheromoneKindProfile
from types import MappingProxyType
from typing import Any

SUPPORTED_PHEROMONE_KINDS = frozenset({"positive", "negative", "cautionary", "alarm", "novelty", "stale"})


SUPPORTED_PHEROMONE_SUBJECT_TYPES = frozenset({"candidate", "route", "tool", "evidence", "agent"})


SUPPORTED_PHEROMONE_RESPONSE_MODELS = frozenset({"linear", "saturating", "threshold", "competitive"})


SUPPORTED_PHEROMONE_COMPETITION_MODES = frozenset({"none", "normalize"})


PHEROMONE_EXTENSION_PREFIXES = ("x-", "ext.")


PHEROMONE_KIND_PROFILE_MAP_VERSION = "pheroos-pheromone-kind-profile-map-v1"


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


for _compat_type in (PheromoneTrail, PheromoneSubject, PheromoneEdge, PheromoneNeighborhood, PheromoneDiffusionPolicy, PheromonePolicy, PheromoneLifecycleRecord, PheromoneExplorationObservation, PheromoneNormalizationRecord, PheromoneScoreResult,):
    _compat_type.__module__ = 'pheroos.governance.pheromone'
    for _compat_descriptor in _compat_type.__dict__.values():
        if isinstance(_compat_descriptor, (staticmethod, classmethod)):
            _compat_member = _compat_descriptor.__func__
        else:
            _compat_member = _compat_descriptor
        if callable(_compat_member) and hasattr(_compat_member, '__module__'):
            _compat_member.__module__ = 'pheroos.governance.pheromone'
del _compat_descriptor, _compat_member, _compat_type

PheromonePolicy.__dataclass_fields__["scored_subject_types"].default_factory.__module__ = (
    "pheroos.governance.pheromone"
)

__all__ = ('BREAKDOWN_CATEGORIES', 'PHEROMONE_EXTENSION_PREFIXES', 'PHEROMONE_KIND_PROFILE_MAP_VERSION', 'PheromoneDiffusionPolicy', 'PheromoneEdge', 'PheromoneExplorationObservation', 'PheromoneLifecycleRecord', 'PheromoneNeighborhood', 'PheromoneNormalizationRecord', 'PheromonePolicy', 'PheromoneScoreResult', 'PheromoneSubject', 'PheromoneTrail', 'SUPPORTED_PHEROMONE_COMPETITION_MODES', 'SUPPORTED_PHEROMONE_KINDS', 'SUPPORTED_PHEROMONE_RESPONSE_MODELS', 'SUPPORTED_PHEROMONE_SUBJECT_TYPES')
