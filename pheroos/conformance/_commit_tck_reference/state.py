"""Private Commit TCK reference state handlers."""

from __future__ import annotations

from threading import RLock

from typing import Any

from pheroos.conformance._commit_reference import (
    ReferenceScenario,
)

from pheroos.governance.commit import (
    commit_assessment_fingerprint,
)

from pheroos.governance.commit_state import (
    advance_commit_window_state as _advance_commit_window_state,
    commit_window_state_fingerprint,
)

from pheroos.governance.risk import (
    commit_threshold_snapshot_fingerprint,
)

_REFERENCE_FIXTURE_CACHE: dict[tuple[Any, ...], ReferenceScenario] = {}

_REFERENCE_FIXTURE_CACHE_LOCK = RLock()

_EPOCH_THRESHOLD_FIXTURE_CACHE: dict[tuple[Any, ...], Any] = {}

_EPOCH_THRESHOLD_FIXTURE_CACHE_LOCK = RLock()

_LIVENESS_INPUT_FIXTURE_CACHE: dict[tuple[Any, ...], Any] = {}

_LIVENESS_INPUT_FIXTURE_CACHE_LOCK = RLock()

_WINDOW_TRANSITION_FIXTURE_CACHE: dict[tuple[Any, ...], Any] = {}

_WINDOW_TRANSITION_FIXTURE_CACHE_LOCK = RLock()


def advance_commit_window_state(
    state: Any,
    *,
    assessment: Any,
    commit_policy: Any,
    threshold_snapshot: Any,
    current_step: int,
) -> Any:
    """Replay-safe access to an immutable historical window transition."""

    fixture_key = (
        commit_window_state_fingerprint(state),
        commit_assessment_fingerprint(assessment),
        commit_threshold_snapshot_fingerprint(threshold_snapshot),
        current_step,
    )
    with _WINDOW_TRANSITION_FIXTURE_CACHE_LOCK:
        cached = _WINDOW_TRANSITION_FIXTURE_CACHE.get(fixture_key)
        if cached is not None:
            return cached
    transitioned = _advance_commit_window_state(
        state,
        assessment=assessment,
        commit_policy=commit_policy,
        threshold_snapshot=threshold_snapshot,
        current_step=current_step,
    )
    with _WINDOW_TRANSITION_FIXTURE_CACHE_LOCK:
        _WINDOW_TRANSITION_FIXTURE_CACHE[fixture_key] = transitioned
    return transitioned
