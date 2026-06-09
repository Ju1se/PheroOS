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
