"""Closed Commit Decision v2 semantic registries."""

from enum import StrEnum


class CommitDecisionCommandV2(StrEnum):
    INITIALIZE = "initialize"
    EVALUATE = "evaluate"
    SEAL = "seal"
    EXPLICIT_UNSEAL = "explicit_unseal"
    EPOCH_RESTART = "epoch_restart"


class CommitDecisionMutationKindV2(StrEnum):
    INITIALIZED = "initialized"
    ASSESSED = "assessed"
    WINDOW_RESET = "window_reset"
    EPOCH_RESTARTED = "epoch_restarted"
    SEALED = "sealed"
    HEARTBEAT = "heartbeat"
    FINALIZED = "finalized"
    DEADLINE_TERMINATED = "deadline_terminated"


class CommitDecisionPhaseV2(StrEnum):
    SEARCH = "search"
    DELIBERATE = "deliberate"
    QUORUM_PENDING = "quorum_pending"
    PROVISIONAL = "provisional"


class CommitDecisionOutcomeKindV2(StrEnum):
    EVIDENCE_COMMIT = "evidence_commit"
    SAFE_FALLBACK = "safe_fallback"
    ADVISORY = "advisory"
    BLOCKED = "blocked"
    INVALID = "invalid"
    FINALITY_UNAVAILABLE = "finality_unavailable"
    SAFETY_VIOLATION = "safety_violation"


class CommitDecisionFinalityStatusV2(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    VERIFIED = "verified"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"


class CommitDecisionEvidenceKindV2(StrEnum):
    POSITIVE = "positive"
    COUNTER = "counter"
    CHALLENGE = "challenge"


class CommitDecisionDependencyRoleV2(StrEnum):
    PARENT = "parent"
    EVIDENCE = "evidence"
    REPLAY = "replay"
    RISK = "risk"
    MEMBERSHIP = "membership"
    PRINCIPAL_VERIFICATION = "principal_verification"
    SUPPORT = "support"
    STOP = "stop"
    PERMISSION = "permission"
    CERTIFICATE = "certificate"
    DISTRIBUTED = "distributed"


__all__ = (
    "CommitDecisionCommandV2",
    "CommitDecisionDependencyRoleV2",
    "CommitDecisionEvidenceKindV2",
    "CommitDecisionFinalityStatusV2",
    "CommitDecisionMutationKindV2",
    "CommitDecisionOutcomeKindV2",
    "CommitDecisionPhaseV2",
)
