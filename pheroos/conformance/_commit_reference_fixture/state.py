"""Private Commit reference fixture state handlers."""

from __future__ import annotations

from threading import RLock

from pheroos.governance.commit import (
    CommitAssessment,
)

from pheroos.governance.commit_state import (
    CommitWindowState,
)

from pheroos.conformance._commit_reference_fixture.models import (
    ReferenceDistributedCommit,
    ReferenceStableCommit,
)

_REFERENCE_WINDOW_FIXTURES: dict[str, CommitWindowState] = {}

_REFERENCE_WINDOW_FIXTURES_LOCK = RLock()

_REFERENCE_STABLE_FIXTURES: dict[tuple[str, str], ReferenceStableCommit] = {}

_REFERENCE_STABLE_FIXTURES_LOCK = RLock()

_REFERENCE_ASSESSMENT_FIXTURES: dict[tuple[object, ...], CommitAssessment] = {}

_REFERENCE_ASSESSMENT_FIXTURES_LOCK = RLock()

_REFERENCE_DISTRIBUTED_FIXTURES: dict[
    tuple[str, str, int | None], ReferenceDistributedCommit
] = {}

_REFERENCE_DISTRIBUTED_FIXTURES_LOCK = RLock()
