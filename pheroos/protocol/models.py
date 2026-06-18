from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_COLLECTIVE_MODES = frozenset({"quorum", "bee_swarm", "ant_colony", "hybrid"})
SWARM_COLLECTIVE_MODES = frozenset({"bee_swarm", "ant_colony", "hybrid"})
SUPPORTED_PHEROMONE_DECAY_MODELS = frozenset({"linear", "exponential", "step"})

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


@dataclass(frozen=True)
class SignalSpec:
    type: str
    target: str
    authority_required: str = "governance"


@dataclass(frozen=True)
class EvidencePolicy:
    require_provenance: bool = True
    allow_agent_fact_creation: bool = False


@dataclass(frozen=True)
class StopSignalPolicy:
    blocked_actions: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateSpec:
    id: str
    target: str
    safe_fallback: bool = False
    label: str = ""


@dataclass(frozen=True)
class QuorumPolicy:
    target: str
    fallback_candidate: str
    commit_threshold: int = 1


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
    fallback_candidate: str = ""


@dataclass(frozen=True)
class RecoveryProtocol:
    id: str
    trigger_targets: list[str]
    allowed_roles: list[str] = field(default_factory=list)
    allowed_tags: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    failure_candidate: str = ""


@dataclass(frozen=True)
class OutputPolicy:
    writer_may_create_facts: bool = False
    requires_committed_candidate: bool = True
    requires_evidence_contract: bool = True
    requires_stop_resolution: bool = True
    requires_publication_permission: bool = True


@dataclass(frozen=True)
class TracePolicy:
    required_events: list[str] = field(default_factory=lambda: ["block", "commit", "recovery", "output"])


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


@dataclass(frozen=True)
class CapabilityManifest:
    id: str
    name: str
    version: str
    protocol: ProtocolManifest
    permissions: list[str] = field(default_factory=list)
    required_connections: list[str] = field(default_factory=list)
    drivers: list[dict[str, Any]] = field(default_factory=list)


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
    return events


def is_swarm_policy(policy: CollectiveDecisionPolicy | None) -> bool:
    return policy is not None and policy.mode in SWARM_COLLECTIVE_MODES


def collective_fallback_id(protocol: ProtocolManifest) -> str:
    policy = protocol.collective_decision_policy
    if policy is None:
        return protocol.quorum_policy.fallback_candidate
    return policy.fallback_candidate or protocol.quorum_policy.fallback_candidate
