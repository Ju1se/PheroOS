from __future__ import annotations

from pheroos.governance.errors import GovernanceError


def _validate_outcome_state_binding(
    outcome: object,
    state: object,
) -> None:
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
        "membership_root",
    ):
        if getattr(outcome, name) != getattr(state, name):
            raise GovernanceError(f"distributed outcome state {name} mismatch")
