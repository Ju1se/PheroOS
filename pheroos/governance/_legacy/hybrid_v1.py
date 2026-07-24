"""Frozen legacy blended-score decision selector.

This module exists only for the v1 swarm/Hybrid compatibility profile.  It
receives an already validated score projection and selects either a declared
candidate or the declared safe fallback.  It must not gain memory, diffusion,
feedback, layer, certificate, persistence, or output-authority behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Set

from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.runtime_policy import resolve_collective_fallback_id
from pheroos.protocol.models import CollectiveDecisionPolicy


LEGACY_HYBRID_V1_DECISION_VERSION = "pheroos-legacy-blended-decision-v1"


def select_legacy_blended_decision(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    scores: Mapping[str, float],
    independent_scouts: Mapping[str, Set[str]],
    layer_fallback_used: bool,
    fallback_candidate_id: str | None,
) -> tuple[str, str]:
    """Select the frozen v1 candidate/reason projection.

    The return value is deliberately not a ``QuorumDecision``.  Only the
    owning governance wrapper may issue an authoritative decision object.
    """

    if layer_fallback_used:
        fallback = _safe_fallback(
            candidate_set=candidate_set,
            policy=policy,
            target=target,
            fallback_candidate_id=fallback_candidate_id,
        )
        return fallback, "safe_layer_coordination_fallback"

    for candidate_id, score in sorted(
        scores.items(), key=lambda item: (-item[1], item[0])
    ):
        if (
            len(independent_scouts[candidate_id]) >= policy.min_independent_scouts
            and score >= policy.quorum_threshold
        ):
            candidate = candidate_set.require_declared_for_target(candidate_id, target)
            return candidate.id, "collective_consensus"

    return (
        _safe_fallback(
            candidate_set=candidate_set,
            policy=policy,
            target=target,
            fallback_candidate_id=fallback_candidate_id,
        ),
        "safe_collective_fallback",
    )


def _safe_fallback(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    fallback_candidate_id: str | None,
) -> str:
    fallback = candidate_set.require_declared_for_target(
        resolve_collective_fallback_id(
            candidate_set=candidate_set,
            policy=policy,
            target=target,
            fallback_candidate_id=fallback_candidate_id,
        ),
        target,
    )
    if not fallback.safe_fallback:
        raise GovernanceError(
            f"collective fallback candidate is not marked safe: {fallback.id}"
        )
    return fallback.id


__all__ = ()
