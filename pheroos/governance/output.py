from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.evidence import EvidenceGraph
from pheroos.governance.errors import GovernanceError
from pheroos.governance.quorum import QuorumDecision, quorum_decision_is_authoritative
from pheroos.governance.stop_signal import StopResolution
from pheroos.trace import TraceEvent


@dataclass(frozen=True)
class OutputContract:
    committed_candidate_required: bool = True
    evidence_required: bool = True
    stop_resolution_required: bool = True
    publication_permission_required: bool = True

    def __post_init__(self) -> None:
        disabled = [
            name
            for name, enabled in (
                ("committed_candidate_required", self.committed_candidate_required),
                ("evidence_required", self.evidence_required),
                ("stop_resolution_required", self.stop_resolution_required),
                ("publication_permission_required", self.publication_permission_required),
            )
            if enabled is not True
        ]
        if disabled:
            raise GovernanceError(f"output authorization gate cannot be disabled: {disabled[0]}")


@dataclass(frozen=True)
class OutputAuthorizationResult:
    authorized: bool
    gates: dict[str, bool]
    trace_event: TraceEvent

    def __post_init__(self) -> None:
        object.__setattr__(self, "gates", MappingProxyType(dict(self.gates)))


def output_authorized(
    contract: OutputContract,
    decision: QuorumDecision,
    evidence: EvidenceGraph,
    stop_resolutions: list[StopResolution],
    *,
    publication_permission: bool,
    candidate_set: CandidateSet | None = None,
) -> bool:
    gates = output_gate_lineage(
        contract,
        decision,
        evidence,
        stop_resolutions,
        publication_permission=publication_permission,
        candidate_set=candidate_set,
    )
    return all(gates.values())


def output_gate_lineage(
    contract: OutputContract,
    decision: QuorumDecision,
    evidence: EvidenceGraph,
    stop_resolutions: list[StopResolution],
    *,
    publication_permission: bool,
    candidate_set: CandidateSet | None = None,
) -> dict[str, bool]:
    mandatory_contract = bool(
        isinstance(contract, OutputContract)
        and contract.committed_candidate_required is True
        and contract.evidence_required is True
        and contract.stop_resolution_required is True
        and contract.publication_permission_required is True
    )
    target_resolutions = [
        resolution
        for resolution in stop_resolutions
        if (
            isinstance(resolution, StopResolution)
            and isinstance(resolution.target, str)
            and resolution.target == decision.target
            and isinstance(resolution.action, str)
            and bool(resolution.action.strip())
            and isinstance(resolution.blocked, bool)
        )
    ]
    declared_candidate = False
    if candidate_set is not None:
        try:
            candidate_set.require_declared_for_target(decision.candidate_id, decision.target)
        except GovernanceError:
            pass
        else:
            declared_candidate = True
    return {
        "committed_candidate": (
            mandatory_contract
            and decision.committed
            and quorum_decision_is_authoritative(decision)
            and declared_candidate
        ),
        "evidence_provenance": (
            mandatory_contract and evidence.has_evidence() and evidence.has_provenance()
        ),
        "stop_resolution": mandatory_contract
        and not any(resolution.blocked for resolution in target_resolutions)
        and bool(target_resolutions),
        "publication_permission": mandatory_contract and publication_permission is True,
    }


def evaluate_output_authorization(
    contract: OutputContract,
    decision: QuorumDecision,
    evidence: EvidenceGraph,
    stop_resolutions: list[StopResolution],
    *,
    publication_permission: bool,
    protocol_id: str,
    candidate_set: CandidateSet | None = None,
) -> OutputAuthorizationResult:
    gates = output_gate_lineage(
        contract,
        decision,
        evidence,
        stop_resolutions,
        publication_permission=publication_permission,
        candidate_set=candidate_set,
    )
    authorized = all(gates.values())
    event = TraceEvent(
        event_type="output",
        protocol_id=protocol_id,
        target=decision.target,
        reason="output authorized by all four gates" if authorized else "output denied by contract gate",
        lineage={**gates, "authorized": authorized},
    )
    event.validate()
    return OutputAuthorizationResult(authorized=authorized, gates=gates, trace_event=event)
