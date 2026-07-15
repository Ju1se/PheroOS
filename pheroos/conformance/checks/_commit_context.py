from __future__ import annotations

from dataclasses import dataclass

from pheroos.conformance.profile import profile_for_manifest
from pheroos.protocol import (
    CapabilityManifest,
    CollectiveCommitPolicy,
    CommitAssurance,
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
)


@dataclass(frozen=True)
class ActiveCommitContext:
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int


def active_commit_context(
    manifest: CapabilityManifest,
) -> ActiveCommitContext | None:
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        return None
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError(
            "collective commit policy must use the canonical Protocol ABI declaration"
        )
    profile = profile_for_manifest(manifest).version
    assurance = CommitAssurance(policy.assurance)
    return ActiveCommitContext(
        profile=profile,
        assurance=assurance,
        manifest_root=commit_manifest_fingerprint(manifest, profile=profile),
        commit_policy_root=commit_policy_fingerprint(policy, profile=profile),
        protocol_id=manifest.protocol.id,
        run_id="conformance:commit-run:v1",
        target=policy.target,
        epoch=1,
    )


__all__ = ["ActiveCommitContext", "active_commit_context"]
