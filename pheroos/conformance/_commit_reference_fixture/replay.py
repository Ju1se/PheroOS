"""Private Commit reference fixture replay handlers."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance.commit_state import (
    CommitReplayState,
    ReplayReceipt,
    record_commit_replay_receipts,
)

from pheroos.conformance._commit_reference_fixture.models import (
    ReferenceScenario,
)


def replay_state_with_receipts(
    scenario: ReferenceScenario,
    receipts: Sequence[ReplayReceipt],
    *,
    step: int,
) -> CommitReplayState:
    return record_commit_replay_receipts(
        scenario.replay_state,
        current_step=step,
        receipts=tuple(receipts),
    )
