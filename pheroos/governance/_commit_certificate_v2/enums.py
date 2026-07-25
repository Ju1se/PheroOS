"""Closed semantic vocabulary for Commit Certificate v2."""

from enum import StrEnum


class CommitCertificateMutationKindV2(StrEnum):
    VERIFIED = "verified"
    SEMANTIC_RETRY = "semantic_retry"
    CONFLICT = "conflict"


class CommitCertificateStatusV2(StrEnum):
    VERIFIED = "verified"
    CONFLICT = "conflict"


class CommitCertificateAuthorityRoleV2(StrEnum):
    REPLAY = "replay"
    RISK = "risk"
    MEMBERSHIP = "membership"
    PRINCIPAL_VERIFICATION = "principal_verification"
    EVIDENCE = "evidence"
    SUPPORT = "support"
    STOP = "stop"
    PERMISSION = "permission"


REQUIRED_COMMIT_CERTIFICATE_AUTHORITY_ROLES_V2 = frozenset(
    CommitCertificateAuthorityRoleV2
)


__all__ = [
    "CommitCertificateAuthorityRoleV2",
    "CommitCertificateMutationKindV2",
    "CommitCertificateStatusV2",
    "REQUIRED_COMMIT_CERTIFICATE_AUTHORITY_ROLES_V2",
]
