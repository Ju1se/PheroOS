from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from pheroos.governance.errors import GovernanceError


_StateT = TypeVar("_StateT")


if TYPE_CHECKING:

    class _WitnessView(Protocol):
        @property
        def membership_root(self) -> str: ...

    class _VerificationView(Protocol):
        @property
        def witness(self) -> _WitnessView: ...

    class _DistributedStateView(Protocol):
        @property
        def membership_root(self) -> str: ...
else:

    class _WitnessView(Protocol):
        pass

    class _VerificationView(Protocol):
        pass

    class _DistributedStateView(Protocol):
        pass


def _validate_verification_state_binding(
    verification: _VerificationView,
    state: _DistributedStateView,
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
    state: _StateT,
    **changes: Any,
) -> _StateT:
    replaced: object = replace(cast(Any, state), **changes)
    if type(replaced) is not type(state):
        raise GovernanceError("distributed state replacement changed record type")
    return cast(_StateT, replaced)
