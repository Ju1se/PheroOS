"""Exact manifest-derived context for durable verification and membership."""

from __future__ import annotations

from dataclasses import dataclass

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import validate_support_lease_policy

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import _require_bounded_text_v2


PRINCIPAL_VERIFICATION_POLICY_VERSION_V2 = "pheroos-principal-verification-policy-v2"
MEMBERSHIP_POLICY_VERSION_V2 = "pheroos-membership-policy-v2"


@dataclass(frozen=True, slots=True)
class DurableSupportContextV2:
    manifest: ScopedProtocolManifestV2
    manifest_root: str
    authority_policy_root: str
    commit_policy_root: str
    principal_verification_policy_root: str
    membership_policy_root: str
    protocol_ref: str
    target_ref: str
    profile: str
    assurance: CommitAssurance


def durable_support_context_v2(
    manifest: ScopedProtocolManifestV2,
    *,
    profile: str,
    assurance: CommitAssurance,
    target_ref: str,
) -> DurableSupportContextV2:
    """Detach one exact scoped manifest and derive every durable policy root."""

    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("durable support requires an exact scoped manifest")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    _require_bounded_text_v2(profile, "durable support profile")
    _require_bounded_text_v2(target_ref, "durable support target_ref")
    if type(assurance) is not CommitAssurance:
        raise TypeError("durable support assurance is invalid")
    if profile not in COMMIT_PROFILES_BY_ASSURANCE.get(assurance.value, frozenset()):
        raise ValueError("durable support profile and assurance are mismatched")
    if target_ref not in {item.id for item in detached.targets}:
        raise ValueError("durable support target is not declared")
    policy = detached.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("durable support manifest has no commit policy")
    if policy.target != target_ref or policy.assurance != assurance.value:
        raise ValueError("durable support commit policy is cross-bound")
    support_diagnostics = validate_support_lease_policy(
        policy.support_lease,
        path="collective_commit_policy.support_lease",
    )
    if support_diagnostics:
        codes = ", ".join(
            sorted({diagnostic.code for diagnostic in support_diagnostics})
        )
        raise ValueError(f"durable support policy is invalid: {codes}")
    manifest_root = detached.manifest_root
    authority_policy_root = detached.authority_policy.root()
    commit_policy_root = commit_policy_fingerprint(policy, profile=profile)
    for label, value in (
        ("manifest_root", manifest_root),
        ("authority_policy_root", authority_policy_root),
        ("commit_policy_root", commit_policy_root),
    ):
        _require_root(value, f"durable support {label}")
    shared = {
        "manifest_root": manifest_root,
        "authority_policy_root": authority_policy_root,
        "commit_policy_root": commit_policy_root,
        "protocol_ref": detached.id,
        "target_ref": target_ref,
        "profile": profile,
        "assurance": assurance.value,
    }
    verification_policy_root = _compute_root(
        "principal-verification-v2:policy",
        {
            **shared,
            "policy_version": PRINCIPAL_VERIFICATION_POLICY_VERSION_V2,
            "authority_operation": "qualify_evidence",
            "complete_replacement": True,
        },
    )
    membership_policy_root = _compute_root(
        "membership-v2:policy",
        {
            **shared,
            "policy_version": MEMBERSHIP_POLICY_VERSION_V2,
            "authority_operation": "evaluate_quorum",
            "sybil_unit": "cluster",
            "empty_membership_allowed": True,
            "verification_policy_root": verification_policy_root,
        },
    )
    return DurableSupportContextV2(
        manifest=detached,
        manifest_root=manifest_root,
        authority_policy_root=authority_policy_root,
        commit_policy_root=commit_policy_root,
        principal_verification_policy_root=verification_policy_root,
        membership_policy_root=membership_policy_root,
        protocol_ref=detached.id,
        target_ref=target_ref,
        profile=profile,
        assurance=assurance,
    )


__all__ = [
    "DurableSupportContextV2",
    "MEMBERSHIP_POLICY_VERSION_V2",
    "PRINCIPAL_VERIFICATION_POLICY_VERSION_V2",
    "durable_support_context_v2",
]
