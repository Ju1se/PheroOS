from __future__ import annotations

from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.protocol.models import CapabilityManifest, collective_fallback_id


def active_target(manifest: CapabilityManifest) -> str:
    return manifest.protocol.quorum_policy.target


def candidate_set(manifest: CapabilityManifest) -> CandidateSet:
    target = active_target(manifest)
    return CandidateSet(
        [
            Candidate(item.id, item.target, item.safe_fallback)
            for item in manifest.protocol.candidates
            if item.target == target
        ]
    )


def target_candidate_ids(manifest: CapabilityManifest) -> list[str]:
    target = active_target(manifest)
    return sorted(item.id for item in manifest.protocol.candidates if item.target == target)


def exercise_candidate_id(manifest: CapabilityManifest) -> str | None:
    """Choose deterministically within the active target, including fallback-only manifests."""

    target = active_target(manifest)
    active = [item for item in manifest.protocol.candidates if item.target == target]
    non_fallback = sorted(item.id for item in active if not item.safe_fallback)
    if non_fallback:
        return non_fallback[0]
    fallback_id = collective_fallback_id(manifest.protocol)
    if any(item.id == fallback_id and item.safe_fallback for item in active):
        return fallback_id
    return sorted(item.id for item in active)[0] if active else None


__all__ = ["active_target", "candidate_set", "exercise_candidate_id", "target_candidate_ids"]
