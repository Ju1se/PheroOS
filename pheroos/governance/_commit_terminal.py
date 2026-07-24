"""Registry-free terminal outcome selection shared by v1 and Conformance."""

from __future__ import annotations

from pheroos.governance._commit_state.records import DecisionOutcomeKind
from pheroos.governance.errors import GovernanceError


def select_terminal_outcome_kind(
    *,
    invalid: bool,
    safety_violation: bool,
    blocked: bool,
    evidence_commit_ready: bool,
    finality_unavailable: bool,
    deadline_reached: bool,
    deadline_outcome: str,
) -> DecisionOutcomeKind | None:
    """Select the first declared terminal condition in canonical priority order."""

    for field_name, value in (
        ("invalid", invalid),
        ("safety_violation", safety_violation),
        ("blocked", blocked),
        ("evidence_commit_ready", evidence_commit_ready),
        ("finality_unavailable", finality_unavailable),
        ("deadline_reached", deadline_reached),
    ):
        if type(value) is not bool:
            raise GovernanceError(f"terminal condition {field_name} must be boolean")
    if deadline_outcome not in {
        DecisionOutcomeKind.SAFE_FALLBACK.value,
        DecisionOutcomeKind.ADVISORY.value,
    }:
        raise GovernanceError("terminal deadline outcome is unsupported")
    if invalid:
        return DecisionOutcomeKind.INVALID
    if safety_violation:
        return DecisionOutcomeKind.SAFETY_VIOLATION
    if blocked:
        return DecisionOutcomeKind.BLOCKED
    if evidence_commit_ready:
        return DecisionOutcomeKind.EVIDENCE_COMMIT
    if finality_unavailable:
        return DecisionOutcomeKind.FINALITY_UNAVAILABLE
    if deadline_reached:
        return DecisionOutcomeKind(deadline_outcome)
    return None


__all__ = ["select_terminal_outcome_kind"]
