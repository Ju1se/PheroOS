from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(frozen=True)
class CapabilityManifest:
    id: str
    name: str
    version: str
    protocol: ProtocolManifest
    permissions: list[str] = field(default_factory=list)
    required_connections: list[str] = field(default_factory=list)
    drivers: list[dict[str, Any]] = field(default_factory=list)
