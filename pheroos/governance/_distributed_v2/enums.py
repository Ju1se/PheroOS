"""Closed Distributed Commit v2 enum contracts."""

from __future__ import annotations

from enum import StrEnum


class DistributedLaneV2(StrEnum):
    EPOCH = "epoch"
    PROPOSAL = "proposal"
    WITNESS = "witness"
    CERTIFICATE = "certificate"


class DistributedMutationKindV2(StrEnum):
    EPOCH_INITIALIZED = "epoch_initialized"
    EPOCH_TRANSITIONED = "epoch_transitioned"
    PROPOSAL_RECORDED = "proposal_recorded"
    PROPOSAL_SEMANTIC_RETRY = "proposal_semantic_retry"
    WITNESS_RECORDED = "witness_recorded"
    WITNESS_RETRY = "witness_retry"
    EQUIVOCATION_FROZEN = "equivocation_frozen"
    CERTIFICATE_VERIFIED = "certificate_verified"
    CERTIFICATE_RETRY = "certificate_retry"
    CERTIFICATE_CONFLICT_FROZEN = "certificate_conflict_frozen"


class DistributedLaneStatusV2(StrEnum):
    ACTIVE = "active"
    VERIFIED = "verified"
    FROZEN = "frozen"
    SUPERSEDED = "superseded"


class DistributedCertificateStatusV2(StrEnum):
    VERIFIED = "verified"
    CONFLICT = "conflict"


class DistributedDependencyRoleV2(StrEnum):
    EPOCH = "epoch"
    PROPOSAL = "proposal"
    WITNESS = "witness"
    CERTIFICATE = "certificate"
    DECISION = "decision"
    CENTRAL_CERTIFICATE = "central_certificate"
    MEMBERSHIP = "membership"
    PRINCIPAL_VERIFICATION = "principal_verification"


__all__ = [
    "DistributedCertificateStatusV2",
    "DistributedDependencyRoleV2",
    "DistributedLaneStatusV2",
    "DistributedLaneV2",
    "DistributedMutationKindV2",
]
