from __future__ import annotations

from collections.abc import Mapping

from dataclasses import dataclass


from pheroos.governance._distributed.invariants import (
    _coerce_assurance,
    _coerce_authority,
    _require_sequence,
    _strict_mapping,
)

from pheroos.governance._distributed._membership_contract import (
    _validate_portable_membership_snapshot,
)


from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_text,
)


from pheroos.governance.authority import AuthorityLevel


from pheroos.governance.commit_numeric import commit_payload_fingerprint

from pheroos.governance.errors import GovernanceError


from pheroos.protocol.commit_models import (
    CommitAssurance,
)

from pheroos.governance._support.records import (
    EligiblePrincipalSnapshot,
    eligible_principal_snapshot_fingerprint,
)
from pheroos.governance._support.membership import (
    eligible_principal_snapshot_is_authoritative,
)


@dataclass(frozen=True)
class PortableEligiblePrincipal:
    principal_id: str
    principal_verification_fingerprint: str
    verified_issuer_id: str
    verified_method: str
    failure_domain: str

    def __post_init__(self) -> None:
        require_commit_text(self.principal_id, "portable member principal_id")
        require_commit_fingerprint(
            self.principal_verification_fingerprint,
            "portable member principal_verification_fingerprint",
        )
        require_commit_text(
            self.verified_issuer_id,
            "portable member verified_issuer_id",
        )
        require_commit_text(self.verified_method, "portable member verified_method")
        require_commit_text(self.failure_domain, "portable member failure_domain")


@dataclass(frozen=True)
class PortableEligibleCluster:
    cluster_id: str
    principals: tuple[PortableEligiblePrincipal, ...]

    def __post_init__(self) -> None:
        require_commit_text(self.cluster_id, "portable membership cluster_id")
        values = tuple(self.principals)
        if not values or any(
            type(item) is not PortableEligiblePrincipal for item in values
        ):
            raise GovernanceError(
                "portable membership cluster requires canonical principals"
            )
        values = tuple(
            sorted(
                values,
                key=lambda item: (
                    item.principal_id,
                    item.principal_verification_fingerprint,
                ),
            )
        )
        if len({item.principal_id for item in values}) != len(values):
            raise GovernanceError("portable membership repeats a principal")
        if len({item.principal_verification_fingerprint for item in values}) != len(
            values
        ):
            raise GovernanceError("portable membership repeats a verification")
        object.__setattr__(self, "principals", values)


@dataclass(frozen=True)
class PortableMembershipSnapshot:
    snapshot_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    eligible_clusters: tuple[PortableEligibleCluster, ...]
    membership_root: str
    issuer_id: str
    membership_method: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    snapshot_fingerprint: str

    def __post_init__(self) -> None:
        values = tuple(self.eligible_clusters)
        if any(type(item) is not PortableEligibleCluster for item in values):
            raise GovernanceError(
                "portable membership requires canonical cluster records"
            )
        values = tuple(sorted(values, key=lambda item: item.cluster_id))
        if not values:
            raise GovernanceError("portable distributed membership must not be empty")
        if len({item.cluster_id for item in values}) != len(values):
            raise GovernanceError("portable membership repeats a cluster")
        principal_ids = tuple(
            principal.principal_id
            for cluster in values
            for principal in cluster.principals
        )
        if len(principal_ids) != len(set(principal_ids)):
            raise GovernanceError(
                "portable membership principal belongs to multiple clusters"
            )
        object.__setattr__(self, "eligible_clusters", values)
        _validate_portable_membership_snapshot(self)


def portable_membership_snapshot_from_eligible(
    snapshot: EligiblePrincipalSnapshot,
) -> PortableMembershipSnapshot:
    if not eligible_principal_snapshot_is_authoritative(snapshot):
        raise GovernanceError(
            "portable distributed membership requires an authoritative snapshot"
        )
    clusters = tuple(
        PortableEligibleCluster(
            cluster_id=cluster.cluster_id,
            principals=tuple(
                PortableEligiblePrincipal(
                    principal_id=principal.principal_id,
                    principal_verification_fingerprint=(
                        principal.principal_verification_fingerprint
                    ),
                    verified_issuer_id=principal.verified_issuer_id,
                    verified_method=principal.verified_method,
                    failure_domain=principal.failure_domain,
                )
                for principal in cluster.principals
            ),
        )
        for cluster in snapshot.eligible_clusters
    )
    return PortableMembershipSnapshot(
        snapshot_id=snapshot.snapshot_id,
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        protocol_id=snapshot.protocol_id,
        run_id=snapshot.run_id,
        target=snapshot.target,
        epoch=snapshot.epoch,
        eligible_clusters=clusters,
        membership_root=snapshot.membership_root,
        issuer_id=snapshot.issuer_id,
        membership_method=snapshot.membership_method,
        authority=snapshot.authority,
        issued_at_step=snapshot.issued_at_step,
        expires_at_step=snapshot.expires_at_step,
        provenance=snapshot.provenance,
        trace_event_id=snapshot.trace_event_id,
        snapshot_fingerprint=eligible_principal_snapshot_fingerprint(snapshot),
    )


def portable_membership_snapshot_payload(
    snapshot: PortableMembershipSnapshot,
    *,
    include_snapshot_fingerprint: bool = True,
) -> dict[str, object]:
    if type(snapshot) is not PortableMembershipSnapshot:
        raise GovernanceError(
            "portable membership must use the canonical distributed record"
        )
    _validate_portable_membership_snapshot(snapshot)
    payload: dict[str, object] = {
        "assurance": snapshot.assurance,
        "authority": snapshot.authority,
        "commit_policy_root": snapshot.commit_policy_root,
        "eligible_clusters": tuple(
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
        ),
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
    if include_snapshot_fingerprint:
        payload["snapshot_fingerprint"] = snapshot.snapshot_fingerprint
    return payload


def portable_membership_snapshot_fingerprint(
    snapshot: PortableMembershipSnapshot,
) -> str:
    return commit_payload_fingerprint(
        portable_membership_snapshot_payload(
            snapshot,
            include_snapshot_fingerprint=False,
        ),
        schema="pheroos-eligible-principal-snapshot-v1",
        profile=snapshot.profile,
    )


def portable_membership_root(snapshot: PortableMembershipSnapshot) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": snapshot.assurance,
            "commit_policy_root": snapshot.commit_policy_root,
            "eligible_clusters": portable_membership_snapshot_payload(
                snapshot,
                include_snapshot_fingerprint=False,
            )["eligible_clusters"],
            "epoch": snapshot.epoch,
            "manifest_root": snapshot.manifest_root,
            "protocol_id": snapshot.protocol_id,
            "run_id": snapshot.run_id,
            "target": snapshot.target,
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=snapshot.profile,
    )


def portable_membership_snapshot_from_payload(
    payload: Mapping[str, object],
) -> PortableMembershipSnapshot:
    values = _strict_mapping(
        payload,
        {
            "assurance",
            "authority",
            "commit_policy_root",
            "eligible_clusters",
            "epoch",
            "expires_at_step",
            "issued_at_step",
            "issuer_id",
            "manifest_root",
            "membership_method",
            "membership_root",
            "profile",
            "protocol_id",
            "provenance",
            "run_id",
            "snapshot_fingerprint",
            "snapshot_id",
            "target",
            "trace_event_id",
        },
        "portable membership payload",
    )
    raw_clusters = _require_sequence(
        values["eligible_clusters"],
        "portable membership eligible_clusters",
    )
    clusters: list[PortableEligibleCluster] = []
    for raw_cluster in raw_clusters:
        cluster = _strict_mapping(
            raw_cluster,
            {"cluster_id", "principals"},
            "portable membership cluster",
        )
        raw_principals = _require_sequence(
            cluster["principals"],
            "portable membership principals",
        )
        principals = tuple(
            PortableEligiblePrincipal(
                **_strict_mapping(
                    raw_principal,
                    {
                        "failure_domain",
                        "principal_id",
                        "principal_verification_fingerprint",
                        "verified_issuer_id",
                        "verified_method",
                    },
                    "portable membership principal",
                )
            )
            for raw_principal in raw_principals
        )
        clusters.append(
            PortableEligibleCluster(
                cluster_id=cluster["cluster_id"],
                principals=principals,
            )
        )
    return PortableMembershipSnapshot(
        snapshot_id=values["snapshot_id"],
        profile=values["profile"],
        assurance=_coerce_assurance(values["assurance"]),
        manifest_root=values["manifest_root"],
        commit_policy_root=values["commit_policy_root"],
        protocol_id=values["protocol_id"],
        run_id=values["run_id"],
        target=values["target"],
        epoch=values["epoch"],
        eligible_clusters=tuple(clusters),
        membership_root=values["membership_root"],
        issuer_id=values["issuer_id"],
        membership_method=values["membership_method"],
        authority=_coerce_authority(values["authority"]),
        issued_at_step=values["issued_at_step"],
        expires_at_step=values["expires_at_step"],
        provenance=values["provenance"],
        trace_event_id=values["trace_event_id"],
        snapshot_fingerprint=values["snapshot_fingerprint"],
    )


for _name in (
    "PortableEligiblePrincipal",
    "PortableEligibleCluster",
    "PortableMembershipSnapshot",
    "portable_membership_snapshot_from_eligible",
    "portable_membership_snapshot_payload",
    "portable_membership_snapshot_fingerprint",
    "portable_membership_root",
    "portable_membership_snapshot_from_payload",
):
    globals()[_name].__module__ = "pheroos.governance.distributed_commit"
del _name
