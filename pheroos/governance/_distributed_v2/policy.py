"""Exact static-epoch fault-policy and eligible-membership validation."""

from __future__ import annotations

from dataclasses import dataclass

from pheroos.protocol.commit_models import DistributedCommitPolicy

from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_PRINCIPALS_V2,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2


@dataclass(frozen=True, slots=True)
class DistributedPolicyBindingV2:
    policy_root: str
    membership_size: int
    max_byzantine_faults: int
    witness_quorum: int
    witness_ttl_steps: int
    minimum_failure_domain_diversity: int
    epoch_transition_rule: str
    binding_root: str = ""

    def __post_init__(self) -> None:
        _require_root(self.policy_root, "distributed policy root")
        n = _require_count(
            self.membership_size,
            "distributed membership size",
            minimum=1,
            maximum=MAX_DISTRIBUTED_PRINCIPALS_V2,
        )
        f = _require_count(
            self.max_byzantine_faults,
            "distributed maximum Byzantine faults",
            maximum=MAX_DISTRIBUTED_PRINCIPALS_V2,
        )
        q = _require_count(
            self.witness_quorum,
            "distributed witness quorum",
            minimum=1,
            maximum=MAX_DISTRIBUTED_PRINCIPALS_V2,
        )
        _require_count(
            self.witness_ttl_steps,
            "distributed witness TTL",
            minimum=1,
        )
        diversity = _require_count(
            self.minimum_failure_domain_diversity,
            "distributed failure-domain diversity",
            minimum=1,
            maximum=MAX_DISTRIBUTED_PRINCIPALS_V2,
        )
        _require_text(self.epoch_transition_rule, "distributed epoch transition rule")
        if n < 3 * f + 1:
            raise ValueError("distributed policy must satisfy n >= 3f + 1")
        if q > n - f:
            raise ValueError("distributed policy must satisfy q <= n - f")
        if 2 * q - n <= f:
            raise ValueError("distributed policy must satisfy 2q - n > f")
        if diversity > q:
            raise ValueError("distributed diversity exceeds quorum")
        expected = _root("policy-binding", self._body())
        if self.binding_root not in ("", expected):
            raise ValueError("distributed policy binding_root is mismatched")
        object.__setattr__(self, "binding_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "policy_root": self.policy_root,
            "membership_size": self.membership_size,
            "max_byzantine_faults": self.max_byzantine_faults,
            "witness_quorum": self.witness_quorum,
            "witness_ttl_steps": self.witness_ttl_steps,
            "minimum_failure_domain_diversity": (self.minimum_failure_domain_diversity),
            "epoch_transition_rule": self.epoch_transition_rule,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "binding_root": self.binding_root}


def distributed_policy_binding_v2(
    policy: DistributedCommitPolicy,
    *,
    policy_root: str,
) -> DistributedPolicyBindingV2:
    if type(policy) is not DistributedCommitPolicy:
        raise TypeError("distributed policy must be exact DistributedCommitPolicy")
    if policy.fault_model != "byzantine_static_v1":
        raise ValueError("distributed fault model is unsupported")
    if policy.membership_mode != "static_epoch_verified_clusters_v1":
        raise ValueError("distributed membership mode is unsupported")
    if policy.conflict_rule != "freeze_v1":
        raise ValueError("distributed conflict rule is unsupported")
    return DistributedPolicyBindingV2(
        policy_root=policy_root,
        membership_size=policy.membership_size,
        max_byzantine_faults=policy.max_byzantine_faults,
        witness_quorum=policy.witness_quorum,
        witness_ttl_steps=policy.witness_ttl_steps,
        minimum_failure_domain_diversity=policy.minimum_failure_domain_diversity,
        epoch_transition_rule=policy.epoch_transition_rule,
    )


def validate_distributed_membership_v2(
    membership: MembershipSnapshotV2,
    binding: DistributedPolicyBindingV2,
    *,
    current_step: int,
) -> None:
    if type(membership) is not MembershipSnapshotV2:
        raise TypeError("distributed membership requires exact MembershipSnapshotV2")
    if type(binding) is not DistributedPolicyBindingV2:
        raise TypeError("distributed membership requires exact policy binding")
    _require_count(current_step, "distributed membership current step")
    principals = tuple(
        principal for cluster in membership.clusters for principal in cluster.principals
    )
    if len(principals) != binding.membership_size:
        raise ValueError("distributed membership size is not the exact eligible set")
    principal_refs = tuple(item.principal_ref for item in principals)
    verification_roots = tuple(item.verification_root for item in principals)
    if len(principal_refs) != len(set(principal_refs)) or len(
        verification_roots
    ) != len(set(verification_roots)):
        raise ValueError("distributed membership repeats a principal identity")
    domains = {item.failure_domain_ref for item in principals}
    clusters = {cluster.cluster_ref for cluster in membership.clusters}
    if "" in domains:
        raise ValueError("distributed membership requires declared failure domains")
    if not clusters:
        raise ValueError("distributed membership requires declared clusters")
    if len(domains) < binding.minimum_failure_domain_diversity:
        raise ValueError("distributed membership cannot reach declared diversity")
    if not membership.issued_at_step <= current_step < membership.expires_at_step:
        raise ValueError("distributed membership is not current at the logical step")


__all__ = [
    "DistributedPolicyBindingV2",
    "distributed_policy_binding_v2",
    "validate_distributed_membership_v2",
]
