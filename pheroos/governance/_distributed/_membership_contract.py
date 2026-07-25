from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CommitAssurance,
    DistributedCommitPolicy,
)


if TYPE_CHECKING:

    class _PortablePrincipalView(Protocol):
        @property
        def principal_id(self) -> str: ...

        @property
        def principal_verification_fingerprint(self) -> str: ...

        @property
        def verified_issuer_id(self) -> str: ...

        @property
        def verified_method(self) -> str: ...

        @property
        def failure_domain(self) -> str: ...

    class _PortableClusterView(Protocol):
        @property
        def cluster_id(self) -> str: ...

        @property
        def principals(self) -> Sequence[_PortablePrincipalView]: ...

    class _PortableMembershipView(Protocol):
        @property
        def snapshot_id(self) -> str: ...

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

        @property
        def eligible_clusters(self) -> Sequence[_PortableClusterView]: ...

        @property
        def membership_root(self) -> str: ...

        @property
        def issuer_id(self) -> str: ...

        @property
        def membership_method(self) -> str: ...

        @property
        def authority(self) -> AuthorityLevel: ...

        @property
        def issued_at_step(self) -> int: ...

        @property
        def expires_at_step(self) -> int: ...

        @property
        def provenance(self) -> str: ...

        @property
        def trace_event_id(self) -> str: ...

        @property
        def snapshot_fingerprint(self) -> str: ...
else:

    class _PortablePrincipalView(Protocol):
        pass

    class _PortableClusterView(Protocol):
        pass

    class _PortableMembershipView(Protocol):
        pass


def _validate_portable_membership_snapshot(
    snapshot: _PortableMembershipView,
) -> None:
    if snapshot.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("portable membership profile is not distributed")
    if snapshot.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("portable membership assurance is not distributed")
    for name in (
        "snapshot_id",
        "protocol_id",
        "run_id",
        "target",
        "issuer_id",
        "membership_method",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(snapshot, name),
            f"portable membership {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "membership_root",
        "snapshot_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(snapshot, name),
            f"portable membership {name}",
        )
    require_commit_step(snapshot.epoch, "portable membership epoch")
    issued = require_commit_step(
        snapshot.issued_at_step,
        "portable membership issued_at_step",
    )
    expires = require_commit_step(
        snapshot.expires_at_step,
        "portable membership expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("portable membership expiry must follow issuance")
    if type(snapshot.authority) is not AuthorityLevel or not can_verify(
        snapshot.authority
    ):
        raise GovernanceError("portable membership issuer lacks authority")
    expected_snapshot = commit_payload_fingerprint(
        _portable_snapshot_payload_unchecked(snapshot),
        schema="pheroos-eligible-principal-snapshot-v1",
        profile=snapshot.profile,
    )
    if snapshot.snapshot_fingerprint != expected_snapshot:
        raise GovernanceError("portable membership snapshot root is invalid")
    expected_membership = commit_payload_fingerprint(
        {
            "assurance": snapshot.assurance,
            "commit_policy_root": snapshot.commit_policy_root,
            "eligible_clusters": _portable_clusters_payload(snapshot),
            "epoch": snapshot.epoch,
            "manifest_root": snapshot.manifest_root,
            "protocol_id": snapshot.protocol_id,
            "run_id": snapshot.run_id,
            "target": snapshot.target,
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=snapshot.profile,
    )
    if snapshot.membership_root != expected_membership:
        raise GovernanceError("portable membership root is invalid")


def _portable_clusters_payload(
    snapshot: _PortableMembershipView,
) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "cluster_id": cluster.cluster_id,
            "principals": tuple(
                {
                    "failure_domain": principal.failure_domain,
                    "principal_id": principal.principal_id,
                    "principal_verification_fingerprint": (
                        principal.principal_verification_fingerprint
                    ),
                    "verified_issuer_id": principal.verified_issuer_id,
                    "verified_method": principal.verified_method,
                }
                for principal in cluster.principals
            ),
        }
        for cluster in snapshot.eligible_clusters
    )


def _portable_snapshot_payload_unchecked(
    snapshot: _PortableMembershipView,
) -> dict[str, object]:
    return {
        "assurance": snapshot.assurance,
        "authority": snapshot.authority,
        "commit_policy_root": snapshot.commit_policy_root,
        "eligible_clusters": _portable_clusters_payload(snapshot),
        "epoch": snapshot.epoch,
        "expires_at_step": snapshot.expires_at_step,
        "issued_at_step": snapshot.issued_at_step,
        "issuer_id": snapshot.issuer_id,
        "manifest_root": snapshot.manifest_root,
        "membership_method": snapshot.membership_method,
        "membership_root": snapshot.membership_root,
        "profile": snapshot.profile,
        "protocol_id": snapshot.protocol_id,
        "provenance": snapshot.provenance,
        "run_id": snapshot.run_id,
        "snapshot_id": snapshot.snapshot_id,
        "target": snapshot.target,
        "trace_event_id": snapshot.trace_event_id,
    }


def _validate_membership_policy(
    membership: _PortableMembershipView,
    policy: DistributedCommitPolicy,
) -> None:
    _validate_portable_membership_snapshot(membership)
    if len(membership.eligible_clusters) != policy.membership_size:
        raise GovernanceError(
            "distributed membership size does not match the declared fault model"
        )
    failure_domains = {
        principal.failure_domain
        for cluster in membership.eligible_clusters
        for principal in cluster.principals
    }
    if len(failure_domains) < policy.minimum_failure_domain_diversity:
        raise GovernanceError(
            "distributed membership cannot satisfy failure-domain diversity"
        )


def _portable_member(
    membership: _PortableMembershipView,
    principal_id: str,
) -> tuple[str, _PortablePrincipalView] | None:
    for cluster in membership.eligible_clusters:
        for principal in cluster.principals:
            if principal.principal_id == principal_id:
                return cluster.cluster_id, principal
    return None
