"""Projection of frozen Commit Decision dependencies into certificate leaves."""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType

from pheroos.governance._commit_certificate_v2.authority_leaves import (
    CommitCertificateAuthorityLeafV2,
)
from pheroos.governance._commit_certificate_v2.enums import (
    CommitCertificateAuthorityRoleV2,
)
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionDependencyRoleV2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitPositionV2


_ROLE_MAP = MappingProxyType(
    {
        CommitDecisionDependencyRoleV2.REPLAY: CommitCertificateAuthorityRoleV2.REPLAY,
        CommitDecisionDependencyRoleV2.RISK: CommitCertificateAuthorityRoleV2.RISK,
        CommitDecisionDependencyRoleV2.MEMBERSHIP: CommitCertificateAuthorityRoleV2.MEMBERSHIP,
        CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION: CommitCertificateAuthorityRoleV2.PRINCIPAL_VERIFICATION,
        CommitDecisionDependencyRoleV2.EVIDENCE: CommitCertificateAuthorityRoleV2.EVIDENCE,
        CommitDecisionDependencyRoleV2.SUPPORT: CommitCertificateAuthorityRoleV2.SUPPORT,
        CommitDecisionDependencyRoleV2.STOP: CommitCertificateAuthorityRoleV2.STOP,
        CommitDecisionDependencyRoleV2.PERMISSION: CommitCertificateAuthorityRoleV2.PERMISSION,
    }
)


def _authority_leaves(
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> tuple[CommitCertificateAuthorityLeafV2, ...]:
    leaves = []
    for dependency in dependencies:
        role = _ROLE_MAP.get(dependency.role)
        if role is None:
            continue
        if dependency.observed_position is not GovernanceCommitPositionV2.CURRENT:
            raise ValueError("commit certificate dependency was not current")
        leaves.append(
            CommitCertificateAuthorityLeafV2(
                role=role,
                stream_ref=dependency.stream_ref,
                revision=dependency.revision,
                transition_id=dependency.transition_id,
                snapshot_root=dependency.snapshot_root,
                head_root=dependency.head_root,
                receipt_root=dependency.receipt_root,
            )
        )
    return tuple(leaves)


__all__: tuple[str, ...] = ()
