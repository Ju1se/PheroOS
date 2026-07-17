from __future__ import annotations

from dataclasses import replace

from pheroos.governance.errors import GovernanceError


def _validate_verification_state_binding(
    verification: object,
    state: object,
) -> None:
    witness = verification.witness
    for name in (
        "profile",
        "assurance",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if getattr(witness, name) != getattr(state, name):
            raise GovernanceError(f"witness verification state {name} mismatch")
    if witness.membership_root != state.membership_root:
        raise GovernanceError("witness verification state membership mismatch")


def _validate_proposal_state_binding(
    proposal: object,
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
        "membership_snapshot_root",
        "membership_epoch_state_root",
    ):
        if getattr(proposal, name) != getattr(state, name):
            raise GovernanceError(f"distributed proposal state {name} mismatch")


def _replace_distributed_state(
    state: object,
    **changes: object,
) -> object:
    return replace(state, **changes)
