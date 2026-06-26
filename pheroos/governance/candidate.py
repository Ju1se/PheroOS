from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance.errors import GovernanceError


@dataclass(frozen=True)
class Candidate:
    id: str
    target: str
    safe_fallback: bool = False


@dataclass(frozen=True)
class CandidateSet:
    candidates: list[Candidate] = field(default_factory=list)

    def require_declared(self, candidate_id: str) -> Candidate:
        for candidate in self.candidates:
            if candidate.id == candidate_id:
                return candidate
        raise GovernanceError(f"candidate is not declared by the active protocol: {candidate_id}")

    def require_declared_for_target(self, candidate_id: str, target: str) -> Candidate:
        candidate = self.require_declared(candidate_id)
        if candidate.target != target:
            raise GovernanceError(
                f"candidate {candidate_id} targets {candidate.target}, not active target {target}"
            )
        return candidate
