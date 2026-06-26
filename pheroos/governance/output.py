from __future__ import annotations

from dataclasses import dataclass

from pheroos.governance.evidence import EvidenceGraph
from pheroos.governance.quorum import QuorumDecision
from pheroos.governance.stop_signal import StopResolution


@dataclass(frozen=True)
class OutputContract:
    committed_candidate_required: bool = True
    evidence_required: bool = True
    publication_permission_required: bool = True


def output_authorized(
    contract: OutputContract,
    decision: QuorumDecision,
    evidence: EvidenceGraph,
    stop_resolutions: list[StopResolution],
    *,
    publication_permission: bool,
) -> bool:
    if contract.committed_candidate_required and not decision.committed:
        return False
    if contract.evidence_required and (not evidence.has_evidence() or not evidence.has_provenance()):
        return False
    if any(resolution.blocked for resolution in stop_resolutions):
        return False
    if contract.publication_permission_required and not publication_permission:
        return False
    return True
