from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, is_dataclass
from types import MappingProxyType
from typing import Any


SUPPORTED_COLLECTIVE_MODES = frozenset({"quorum", "bee_swarm", "ant_colony", "hybrid"})
SWARM_COLLECTIVE_MODES = frozenset({"bee_swarm", "ant_colony", "hybrid"})
SUPPORTED_PHEROMONE_DECAY_MODELS = frozenset({"linear", "exponential", "step"})
SUPPORTED_PHEROMONE_RESPONSE_MODELS = frozenset({"linear", "saturating", "threshold", "competitive"})
SUPPORTED_PHEROMONE_COMPETITION_MODES = frozenset({"none", "normalize"})
SUPPORTED_PHEROMONE_SUBJECT_TYPES = frozenset({"candidate", "route", "tool", "evidence", "agent"})
SUPPORTED_PHEROMONE_KINDS = frozenset({"positive", "negative", "cautionary", "alarm", "novelty", "stale"})
SUPPORTED_LAYER_IDS = frozenset({"reactive", "learned", "evolutionary", "metacognitive"})
PHEROMONE_EXTENSION_PREFIXES = ("x-", "ext.")

BASE_SWARM_TRACE_EVENTS = frozenset(
    {
        "explore",
        "scout_report",
        "candidate_score",
        "consensus_check",
        "commit",
        "fallback",
        "output",
    }
)

HYBRID_SWARM_TRACE_EVENTS = frozenset(
    {
        "pheromone_observe",
        "pheromone_diffuse",
        "pheromone_reinforce",
        "pheromone_normalize",
        "layer_proposal",
        "coordination_assess",
        "coordination_resolve",
        "policy_adjustment",
    }
)


@dataclass(frozen=True)
class ValidationDiagnostic:
    code: str
    message: str
    level: str = "error"
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "code": self.code, "message": self.message, "path": self.path}


@dataclass(frozen=True)
class TargetSpec:
    id: str
    description: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class SignalSpec:
    type: str
    target: str
    authority_required: str = "governance"
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class EvidencePolicy:
    require_provenance: bool = True
    allow_agent_fact_creation: bool = False
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class CandidateSpec:
    id: str
    target: str
    safe_fallback: bool = False
    label: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class QuorumPolicy:
    target: str
    fallback_candidate: str
    commit_threshold: int = 1
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class PheromoneKindProfile:
    weight: float = 1.0
    evaporation_rate: float | None = None
    ttl_steps: int | None = None
    response_model: str = "linear"
    priority: int = 0
    can_suppress_positive: bool = False
    scored_subject_types: list[str] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, sequences=("scored_subject_types",), mappings=("extensions",))


@dataclass(frozen=True)
class CollectiveDecisionPolicy:
    mode: str = "quorum"
    min_independent_scouts: int = 1
    quorum_threshold: int = 1
    recruitment_enabled: bool = False
    inhibition_enabled: bool = False
    pheromone_enabled: bool = False
    pheromone_evaporation_rate: float = 0.0
    pheromone_decay_model: str = "exponential"
    pheromone_min_strength: float = 0.0
    pheromone_max_strength: float = 10.0
    pheromone_positive_weight: float = 1.0
    pheromone_negative_weight: float = 1.0
    pheromone_cautionary_weight: float = 1.0
    pheromone_cautionary_override_threshold: float = 1.0
    pheromone_novelty_weight: float = 0.5
    pheromone_per_source_cap: float = 3.0
    pheromone_per_round_deposit_cap: float = 5.0
    pheromone_min_source_diversity: int = 1
    pheromone_require_provenance: bool = True
    pheromone_require_trace: bool = True
    pheromone_scored_subject_types: list[str] = field(default_factory=lambda: ["candidate"])
    pheromone_kind_profiles: dict[str, PheromoneKindProfile] = field(default_factory=dict)
    pheromone_response_model: str = "linear"
    pheromone_activation_threshold: float = 0.0
    pheromone_saturation_threshold: float = 10.0
    pheromone_competition_mode: str = "none"
    pheromone_exploration_floor: float = 0.0
    pheromone_diffusion_enabled: bool = False
    pheromone_diffusion_max_hops: int = 0
    pheromone_diffusion_attenuation: float = 0.0
    pheromone_feedback_enabled: bool = False
    exploration_enabled: bool = False
    exploration_floor: float = 0.0
    novelty_decay_rate: float = 0.0
    stale_route_reopen_threshold: float = 0.0
    layer_coordination_enabled: bool = False
    layer_weight_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    layer_default_weights: dict[str, float] = field(default_factory=dict)
    layer_confidence_thresholds: dict[str, float] = field(default_factory=dict)
    layer_conflict_threshold: float = 0.0
    layer_emergency_override_threshold: float = 0.0
    layer_min_provenance: int = 1
    layer_fallback_on_unresolved_conflict: bool = True
    policy_adjustment_bounds: dict[str, Any] = field(default_factory=dict)
    fallback_candidate: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(
            self,
            sequences=("pheromone_scored_subject_types",),
            mappings=(
                "pheromone_kind_profiles",
                "layer_weight_bounds",
                "layer_default_weights",
                "layer_confidence_thresholds",
                "policy_adjustment_bounds",
                "extensions",
            ),
        )


@dataclass(frozen=True)
class RecoveryProtocol:
    id: str
    trigger_targets: list[str]
    allowed_roles: list[str] = field(default_factory=list)
    allowed_tags: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    failure_candidate: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(
            self,
            sequences=("trigger_targets", "allowed_roles", "allowed_tags", "required_tools"),
            mappings=("extensions",),
        )


@dataclass(frozen=True)
class OutputPolicy:
    writer_may_create_facts: bool = False
    requires_committed_candidate: bool = True
    requires_evidence_contract: bool = True
    requires_stop_resolution: bool = True
    requires_publication_permission: bool = True
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, mappings=("extensions",))


@dataclass(frozen=True)
class TracePolicy:
    required_events: list[str] = field(default_factory=lambda: ["block", "commit", "recovery", "output"])
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, sequences=("required_events",), mappings=("extensions",))


@dataclass(frozen=True)
class DriverSpec:
    id: str
    kind: str
    version: str
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    config_ref: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(self, sequences=("capabilities", "permissions"), mappings=("extensions",))


@dataclass(frozen=True)
class ProtocolManifest:
    protocol_version: str
    id: str
    targets: list[TargetSpec]
    candidates: list[CandidateSpec]
    quorum_policy: QuorumPolicy
    recovery_protocols: list[RecoveryProtocol] = field(default_factory=list)
    output_policy: OutputPolicy = field(default_factory=OutputPolicy)
    trace_policy: TracePolicy = field(default_factory=TracePolicy)
    evidence_policy: EvidencePolicy = field(default_factory=EvidencePolicy)
    signals: list[SignalSpec] = field(default_factory=list)
    collective_decision_policy: CollectiveDecisionPolicy | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(
            self,
            sequences=("targets", "candidates", "recovery_protocols", "signals"),
            mappings=("extensions",),
        )


@dataclass(frozen=True)
class CapabilityManifest:
    id: str
    name: str
    version: str
    protocol: ProtocolManifest
    permissions: list[str] = field(default_factory=list)
    required_connections: list[str] = field(default_factory=list)
    drivers: list[DriverSpec] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        snapshot_fields(
            self,
            sequences=("permissions", "required_connections", "drivers"),
            mappings=("extensions",),
        )


def required_swarm_trace_events(policy: CollectiveDecisionPolicy) -> set[str]:
    events = set(BASE_SWARM_TRACE_EVENTS)
    if policy.recruitment_enabled:
        events.add("recruit")
    if policy.inhibition_enabled:
        events.add("inhibit")
    if policy.pheromone_enabled:
        events.update(
            {
                "pheromone_deposit",
                "pheromone_evaporate",
                "pheromone_score",
                "pheromone_clip",
                "pheromone_expire",
            }
        )
    if has_hybrid_pheromone_features(policy):
        events.update(HYBRID_SWARM_TRACE_EVENTS)
    return events


def is_swarm_policy(policy: CollectiveDecisionPolicy | None) -> bool:
    return policy is not None and policy.mode in SWARM_COLLECTIVE_MODES


def has_hybrid_pheromone_features(policy: CollectiveDecisionPolicy | None) -> bool:
    if policy is None:
        return False
    return (
        policy.mode == "hybrid"
        or tuple(policy.pheromone_scored_subject_types) != ("candidate",)
        or bool(policy.pheromone_kind_profiles)
        or policy.pheromone_diffusion_enabled
        or policy.pheromone_diffusion_max_hops != 0
        or policy.pheromone_diffusion_attenuation != 0.0
        or policy.pheromone_feedback_enabled
        or policy.pheromone_response_model != "linear"
        or policy.pheromone_activation_threshold != 0.0
        or policy.pheromone_saturation_threshold != 10.0
        or policy.pheromone_competition_mode != "none"
        or policy.pheromone_exploration_floor != 0.0
        or policy.exploration_enabled
        or policy.exploration_floor != 0.0
        or policy.novelty_decay_rate != 0.0
        or policy.stale_route_reopen_threshold != 0.0
        or policy.layer_coordination_enabled
        or bool(policy.layer_weight_bounds)
        or bool(policy.layer_default_weights)
        or bool(policy.layer_confidence_thresholds)
        or policy.layer_conflict_threshold != 0.0
        or policy.layer_emergency_override_threshold != 0.0
        or policy.layer_min_provenance != 1
        or not policy.layer_fallback_on_unresolved_conflict
        or bool(policy.policy_adjustment_bounds)
    )


def is_supported_pheromone_subject_type(subject_type: str) -> bool:
    return isinstance(subject_type, str) and (
        subject_type in SUPPORTED_PHEROMONE_SUBJECT_TYPES
        or any(
            subject_type.startswith(prefix) and len(subject_type) > len(prefix)
            for prefix in PHEROMONE_EXTENSION_PREFIXES
        )
    )


def is_scored_pheromone_subject_type(subject_type: str) -> bool:
    """Return whether a subject may be named in a scoring declaration.

    Evidence remains a supported pheromone-memory subject, but collective
    memory about evidence cannot itself become score-bearing evidence.
    """

    return subject_type != "evidence" and is_supported_pheromone_subject_type(
        subject_type
    )


def is_supported_pheromone_kind(kind: str) -> bool:
    return kind in SUPPORTED_PHEROMONE_KINDS or any(
        kind.startswith(prefix) and len(kind) > len(prefix)
        for prefix in PHEROMONE_EXTENSION_PREFIXES
    )


def effective_pheromone_scored_subject_types(
    kind: str,
    profile: PheromoneKindProfile | None,
    policy_subject_types: Sequence[str],
) -> tuple[str, ...]:
    """Resolve the subjects a kind is explicitly allowed to score.

    Built-in kinds retain the compatibility behavior of inheriting the
    policy-wide declaration when their profile list is empty. Namespaced
    extension kinds are metadata-only by default and therefore never inherit
    that declaration; a non-empty per-kind list is their explicit scoring
    opt-in.
    """

    if profile is not None and profile.scored_subject_types:
        return tuple(profile.scored_subject_types)
    if kind in SUPPORTED_PHEROMONE_KINDS:
        return tuple(policy_subject_types)
    return ()


def snapshot_fields(
    value: object,
    *,
    sequences: tuple[str, ...] = (),
    mappings: tuple[str, ...] = (),
) -> None:
    for name in sequences:
        object.__setattr__(
            value,
            name,
            tuple(deep_freeze(item) for item in getattr(value, name)),
        )
    for name in mappings:
        source = getattr(value, name)
        object.__setattr__(
            value,
            name,
            MappingProxyType(
                {deepcopy(key): deep_freeze(item) for key, item in source.items()}
            ),
        )


def deep_freeze(value: Any) -> Any:
    """Recursively freeze caller-owned ABI containers at the protocol boundary."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {deepcopy(key): deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    if is_dataclass(value):
        # Protocol dataclasses are frozen and recursively snapshot themselves.
        return value
    return deepcopy(value)


def thaw_protocol_value(value: Any) -> Any:
    """Return a detached JSON-compatible copy of a frozen protocol value."""

    if isinstance(value, Mapping):
        return {
            deepcopy(key): thaw_protocol_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [thaw_protocol_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [thaw_protocol_value(item) for item in sorted(value, key=repr)]
    return deepcopy(value)


def collective_fallback_id(protocol: ProtocolManifest) -> str:
    policy = protocol.collective_decision_policy
    if policy is None:
        return protocol.quorum_policy.fallback_candidate
    return policy.fallback_candidate or protocol.quorum_policy.fallback_candidate
