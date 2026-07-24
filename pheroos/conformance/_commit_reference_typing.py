"""Typing-only projections for the Commit reference fixtures."""

from __future__ import annotations

from typing import cast

from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    DistributedCommitPolicy,
    EvidenceQualificationPolicy,
)


def collective_commit_policy(value: object) -> CollectiveCommitPolicy:
    """Project the fixture's ABI-stable opaque policy annotation."""

    return cast(CollectiveCommitPolicy, value)


def evidence_qualification_policy(value: object) -> EvidenceQualificationPolicy:
    """Project the fixture's ABI-stable opaque evidence-policy annotation."""

    return cast(EvidenceQualificationPolicy, value)


def distributed_commit_policy(value: object) -> DistributedCommitPolicy:
    """Project the declared distributed branch for a fixture that requires it."""

    return cast(DistributedCommitPolicy, collective_commit_policy(value).distributed)


__all__ = [
    "collective_commit_policy",
    "distributed_commit_policy",
    "evidence_qualification_policy",
]
