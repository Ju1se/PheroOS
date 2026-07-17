from __future__ import annotations
from collections.abc import Sequence
from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    commit_payload_fingerprint,
    require_scaled_integer,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
    SupportLeasePolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


def _validate_eligible_principal(principal: object) -> None:
    for name in ("principal_id", "verified_issuer_id", "verified_method"):
        require_commit_text(
            getattr(principal, name),
            f"eligible principal {name}",
        )
    require_commit_fingerprint(
        principal.principal_verification_fingerprint,
        "eligible principal verification fingerprint",
    )
    if principal.failure_domain:
        require_commit_text(
            principal.failure_domain,
            "eligible principal failure_domain",
        )


def _validate_bound_record(record: object, field_name: str) -> None:
    profile = require_commit_profile(
        getattr(record, "profile"), f"{field_name} profile"
    )
    assurance = require_commit_assurance(
        getattr(record, "assurance"),
        f"{field_name} assurance",
    )
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    require_commit_fingerprint(
        getattr(record, "manifest_root"),
        f"{field_name} manifest_root",
    )
    require_commit_fingerprint(
        getattr(record, "commit_policy_root"),
        f"{field_name} commit_policy_root",
    )
    for name in ("protocol_id", "run_id", "target"):
        require_commit_text(getattr(record, name), f"{field_name} {name}")
    require_commit_step(getattr(record, "epoch"), f"{field_name} epoch")


def _normalized_bindings(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    field_name: str,
) -> dict[str, object]:
    normalized_profile = require_commit_profile(profile, f"{field_name} profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        f"{field_name} assurance",
    )
    if (
        normalized_profile
        not in COMMIT_PROFILES_BY_ASSURANCE[normalized_assurance.value]
    ):
        raise GovernanceError(f"{field_name} profile/assurance mismatch")
    return {
        "profile": normalized_profile,
        "assurance": normalized_assurance,
        "manifest_root": require_commit_fingerprint(
            manifest_root,
            f"{field_name} manifest_root",
        ),
        "commit_policy_root": require_commit_fingerprint(
            commit_policy_root,
            f"{field_name} commit_policy_root",
        ),
        "protocol_id": require_commit_text(
            protocol_id,
            f"{field_name} protocol_id",
        ),
        "run_id": require_commit_text(run_id, f"{field_name} run_id"),
        "target": require_commit_text(target, f"{field_name} target"),
        "epoch": require_commit_step(epoch, f"{field_name} epoch"),
    }


def _record_bindings_equal(record: object, expected: dict[str, object]) -> bool:
    return all(getattr(record, name) == value for name, value in expected.items())


def _same_commit_scope(left: object, right: object) -> bool:
    return all(
        getattr(left, name) == getattr(right, name)
        for name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
            "target",
            "epoch",
        )
    )


def _validate_support_policy(policy: object) -> None:
    if type(policy) is not SupportLeasePolicy:
        raise GovernanceError("support policy must use the Protocol ABI record")
    if (
        policy.membership_mode != "verified_snapshot_v1"
        or policy.switch_mode != "revoke_then_issue_v1"
        or policy.equivocation_mode != "exclude_conflicts_v1"
        or policy.evidence_reference_required is not True
        or policy.cluster_verification_required is not True
    ):
        raise GovernanceError("support policy does not use normative v1 semantics")
    if (
        require_commit_step(
            policy.minimum_support_clusters,
            "support policy minimum_support_clusters",
        )
        <= 0
    ):
        raise GovernanceError("support policy minimum clusters must be positive")
    ratio = require_scaled_integer(
        policy.support_ratio_ppm,
        "support policy ratio",
        maximum=WEIGHT_SCALE,
    )
    if ratio <= 0:
        raise GovernanceError("support policy ratio must be positive")
    if require_commit_step(policy.lease_ttl_steps, "support policy lease TTL") <= 0:
        raise GovernanceError("support policy lease TTL must be positive")


def _validate_commit_policy_binding(
    policy: object,
    bound_record: object,
) -> None:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("support evaluation requires a collective commit policy")
    if policy.target != getattr(bound_record, "target"):
        raise GovernanceError("support policy target binding mismatch")
    if policy.assurance != getattr(bound_record, "assurance").value:
        raise GovernanceError("support policy assurance binding mismatch")
    observed_root = commit_policy_fingerprint(
        policy,
        profile=getattr(bound_record, "profile"),
    )
    if observed_root != getattr(bound_record, "commit_policy_root"):
        raise GovernanceError("support policy root binding mismatch")


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    fingerprints = tuple(values)
    if not fingerprints and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    for value in fingerprints:
        require_commit_fingerprint(value, field_name)
    if len(fingerprints) != len(set(fingerprints)):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(fingerprints))


def _membership_epoch_authority_key(record: object) -> str:
    profile = require_commit_profile(
        getattr(record, "profile"),
        "membership epoch authority profile",
    )
    return commit_payload_fingerprint(
        {
            "assurance": require_commit_assurance(
                getattr(record, "assurance"),
                "membership epoch authority assurance",
            ),
            "commit_policy_root": require_commit_fingerprint(
                getattr(record, "commit_policy_root"),
                "membership epoch authority commit_policy_root",
            ),
            "epoch": require_commit_step(
                getattr(record, "epoch"),
                "membership epoch authority epoch",
            ),
            "manifest_root": require_commit_fingerprint(
                getattr(record, "manifest_root"),
                "membership epoch authority manifest_root",
            ),
            "protocol_id": require_commit_text(
                getattr(record, "protocol_id"),
                "membership epoch authority protocol_id",
            ),
            "run_id": require_commit_text(
                getattr(record, "run_id"),
                "membership epoch authority run_id",
            ),
            "target": require_commit_text(
                getattr(record, "target"),
                "membership epoch authority target",
            ),
        },
        schema="pheroos-eligible-membership-epoch-authority-key-v1",
        profile=profile,
    )


def _eligible_cluster_payload(cluster: object) -> dict[str, object]:
    return {
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


def _membership_root(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    clusters: Sequence[object],
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": assurance,
            "commit_policy_root": commit_policy_root,
            "eligible_clusters": tuple(
                _eligible_cluster_payload(cluster) for cluster in clusters
            ),
            "epoch": epoch,
            "manifest_root": manifest_root,
            "protocol_id": protocol_id,
            "run_id": run_id,
            "target": target,
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=profile,
    )


def _support_replay_authority_key(
    *,
    profile: str,
    protocol_id: str,
    issuer_id: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "issuer_id": issuer_id,
            "profile": profile,
            "protocol_id": protocol_id,
        },
        schema="pheroos-support-lease-replay-authority-key-v1",
        profile=profile,
    )


def _equivocation_finding_id(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    cluster_id: str,
    candidates: Sequence[str],
    lease_fingerprints: Sequence[str],
    first_overlap_step: int,
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": assurance,
            "commit_policy_root": commit_policy_root,
            "conflicting_candidates": tuple(candidates),
            "conflicting_lease_fingerprints": tuple(lease_fingerprints),
            "epoch": epoch,
            "first_overlap_step": first_overlap_step,
            "manifest_root": manifest_root,
            "principal_cluster_id": cluster_id,
            "protocol_id": protocol_id,
            "run_id": run_id,
            "target": target,
        },
        schema="pheroos-support-equivocation-finding-v1",
        profile=profile,
    )
