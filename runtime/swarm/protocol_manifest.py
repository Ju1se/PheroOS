from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.swarm.protocol_schema import (
    AgentSelectionPolicy,
    CandidateDeclaration,
    EvidencePolicy,
    OutputPolicy,
    QuorumPolicy,
    RecoveryProtocol,
    StopSignalPolicy,
    SwarmLoopPolicy,
    TargetDeclaration,
    ToolPolicy,
    dict_value,
    string_list,
)


PROTOCOL_SCHEMA_VERSION = "pheroos.capability_protocol.v1"


@dataclass(frozen=True)
class CapabilityPheroOSProtocol:
    capability_id: str
    version: str = "0.1.0"
    intents: list[str] = field(default_factory=list)
    intent_keywords: dict[str, list[str]] = field(default_factory=dict)
    required_capability_types: list[str] = field(default_factory=list)
    required_capability_types_by_intent: dict[str, list[str]] = field(default_factory=dict)
    targets: list[TargetDeclaration] = field(default_factory=list)
    candidates: list[CandidateDeclaration] = field(default_factory=list)
    quorum_policy: QuorumPolicy = field(default_factory=QuorumPolicy)
    stop_signal_policy: StopSignalPolicy = field(default_factory=StopSignalPolicy)
    recovery_protocols: list[RecoveryProtocol] = field(default_factory=list)
    agent_selection_policy: AgentSelectionPolicy = field(default_factory=AgentSelectionPolicy)
    evidence_policy: EvidencePolicy = field(default_factory=EvidencePolicy)
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)
    output_policy: OutputPolicy = field(default_factory=OutputPolicy)
    swarm_loop_policy: SwarmLoopPolicy = field(default_factory=SwarmLoopPolicy)
    required_governance_actors: list[str] = field(default_factory=list)
    source: str = "capability_protocol"
    generated_legacy_protocol: bool = False
    validation_diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        capability_id: str,
        source: str = "capability_protocol",
        generated_legacy_protocol: bool = False,
    ) -> "CapabilityPheroOSProtocol":
        data = dict_value(payload)
        targets = [
            target
            for target in (
                TargetDeclaration.from_dict(item, source=source)
                for item in data.get("targets", [])
            )
            if target is not None
        ]
        candidates = [
            candidate
            for candidate in (
                CandidateDeclaration.from_dict(item)
                for item in data.get("candidates", [])
            )
            if candidate is not None
        ]
        candidate_ids = [candidate.candidate for candidate in candidates]
        quorum_payload = data.get("quorum_policy")
        stop_payload = data.get("stop_signal_policy")
        loop_payload = data.get("swarm_loop_policy") or quorum_payload
        return cls(
            capability_id=str(data.get("capability_id") or capability_id),
            version=str(data.get("version") or "0.1.0"),
            intents=string_list(data.get("intents")),
            intent_keywords=string_list_map(data.get("intent_keywords") or data.get("intent_markers")),
            required_capability_types=string_list(data.get("required_capability_types")),
            required_capability_types_by_intent=string_list_map(
                data.get("required_capability_types_by_intent") or data.get("intent_required_capability_types")
            ),
            targets=targets,
            candidates=candidates,
            quorum_policy=QuorumPolicy.from_dict(quorum_payload, candidate_ids=candidate_ids),
            stop_signal_policy=StopSignalPolicy.from_dict(stop_payload),
            recovery_protocols=[
                protocol
                for protocol in (
                    RecoveryProtocol.from_dict(item)
                    for item in data.get("recovery_protocols", [])
                )
                if protocol is not None
            ],
            agent_selection_policy=AgentSelectionPolicy.from_dict(data.get("agent_selection_policy")),
            evidence_policy=EvidencePolicy.from_dict(data.get("evidence_policy")),
            tool_policy=ToolPolicy.from_dict(data.get("tool_policy")),
            output_policy=OutputPolicy.from_dict(data.get("output_policy")),
            swarm_loop_policy=SwarmLoopPolicy.from_dict(loop_payload),
            required_governance_actors=string_list(data.get("required_governance_actors")),
            source=source,
            generated_legacy_protocol=generated_legacy_protocol,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROTOCOL_SCHEMA_VERSION,
            "capability_id": self.capability_id,
            "version": self.version,
            "intents": list(self.intents),
            "intent_keywords": {
                intent: list(keywords)
                for intent, keywords in self.intent_keywords.items()
            },
            "required_capability_types": list(self.required_capability_types),
            "required_capability_types_by_intent": {
                intent: list(required)
                for intent, required in self.required_capability_types_by_intent.items()
            },
            "targets": [target.to_dict() for target in self.targets],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "quorum_policy": self.quorum_policy.to_dict(),
            "stop_signal_policy": self.stop_signal_policy.to_dict(),
            "recovery_protocols": [protocol.to_dict() for protocol in self.recovery_protocols],
            "agent_selection_policy": self.agent_selection_policy.to_dict(),
            "evidence_policy": self.evidence_policy.to_dict(),
            "tool_policy": self.tool_policy.to_dict(),
            "output_policy": self.output_policy.to_dict(),
            "swarm_loop_policy": self.swarm_loop_policy.to_dict(),
            "required_governance_actors": list(self.required_governance_actors),
            "source": self.source,
            "generated_legacy_protocol": self.generated_legacy_protocol,
            "validation_diagnostics": [dict(item) for item in self.validation_diagnostics],
        }

    def with_diagnostics(self, diagnostics: list[dict[str, Any]]) -> "CapabilityPheroOSProtocol":
        return CapabilityPheroOSProtocol(
            capability_id=self.capability_id,
            version=self.version,
            intents=list(self.intents),
            intent_keywords={
                intent: list(keywords)
                for intent, keywords in self.intent_keywords.items()
            },
            required_capability_types=list(self.required_capability_types),
            required_capability_types_by_intent={
                intent: list(required)
                for intent, required in self.required_capability_types_by_intent.items()
            },
            targets=list(self.targets),
            candidates=list(self.candidates),
            quorum_policy=self.quorum_policy,
            stop_signal_policy=self.stop_signal_policy,
            recovery_protocols=list(self.recovery_protocols),
            agent_selection_policy=self.agent_selection_policy,
            evidence_policy=self.evidence_policy,
            tool_policy=self.tool_policy,
            output_policy=self.output_policy,
            swarm_loop_policy=self.swarm_loop_policy,
            required_governance_actors=list(self.required_governance_actors),
            source=self.source,
            generated_legacy_protocol=self.generated_legacy_protocol,
            validation_diagnostics=diagnostics,
        )


def string_list_map(value: Any) -> dict[str, list[str]]:
    data = dict_value(value)
    return {
        str(key).strip(): string_list(item)
        for key, item in data.items()
        if str(key).strip()
    }
