from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.errors import GovernanceError


@dataclass(frozen=True)
class Candidate:
    id: str
    target: str
    safe_fallback: bool = False


@dataclass(frozen=True)
class CandidateSet:
    candidates: tuple[Candidate, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        snapshot = tuple(deepcopy(self.candidates))
        identifiers: set[str] = set()
        for candidate in snapshot:
            if not isinstance(candidate, Candidate):
                raise GovernanceError("candidate set entries must be Candidate records")
            if not is_nonblank_string(candidate.id):
                raise GovernanceError("candidate id must be a non-blank string")
            if not is_nonblank_string(candidate.target):
                raise GovernanceError("candidate target must be a non-blank string")
            if not isinstance(candidate.safe_fallback, bool):
                raise GovernanceError("candidate safe_fallback must be boolean")
            if candidate.id in identifiers:
                raise GovernanceError(
                    f"duplicate candidate declaration: {candidate.id}"
                )
            identifiers.add(candidate.id)
        object.__setattr__(self, "candidates", snapshot)

    def require_declared(self, candidate_id: str) -> Candidate:
        if not is_nonblank_string(candidate_id):
            raise GovernanceError("candidate id must be a non-blank string")
        for candidate in self.candidates:
            if candidate.id == candidate_id:
                return candidate
        raise GovernanceError(
            f"candidate is not declared by the active protocol: {candidate_id}"
        )

    def require_declared_for_target(self, candidate_id: str, target: str) -> Candidate:
        if not is_nonblank_string(target):
            raise GovernanceError("candidate target must be a non-blank string")
        candidate = self.require_declared(candidate_id)
        if candidate.target != target:
            raise GovernanceError(
                f"candidate {candidate_id} targets {candidate.target}, not active target {target}"
            )
        return candidate
