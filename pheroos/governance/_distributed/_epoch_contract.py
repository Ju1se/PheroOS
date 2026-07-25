from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pheroos.governance.errors import GovernanceError
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_matches,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_matches,
)
from pheroos.protocol.commit_models import CommitAction, CommitAssurance


if TYPE_CHECKING:

    class _DistributedStateView(Protocol):
        @property
        def profile(self) -> str: ...

        @property
        def assurance(self) -> CommitAssurance: ...

        @property
        def manifest_root(self) -> str: ...

        @property
        def commit_policy_root(self) -> str: ...

        @property
        def protocol_id(self) -> str: ...

        @property
        def run_id(self) -> str: ...

        @property
        def target(self) -> str: ...

        @property
        def epoch(self) -> int: ...
else:

    class _DistributedStateView(Protocol):
        pass


def _require_action_gate(
    *,
    stop: StopResolutionVerification,
    permission: ActionPermission,
    state: _DistributedStateView,
    action: CommitAction,
    decision_ref: str,
    current_step: int,
) -> None:
    if not stop_resolution_verification_matches(
        stop,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        action=action,
        epoch=state.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        current_step=current_step,
        require_unblocked=True,
    ):
        raise GovernanceError(f"{action.value} stop gate is not resolved")
    if not action_permission_matches(
        permission,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        action=action,
        epoch=state.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        current_step=current_step,
        require_allowed=True,
    ):
        raise GovernanceError(f"{action.value} permission gate is denied")
