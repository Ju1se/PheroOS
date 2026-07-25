from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_bool,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.challenge import (
    VerifiedChallenge,
    verified_challenge_fingerprint,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.evidence_binding import EvidenceBinding
from pheroos.governance.observation import (
    CounterevidenceDisposition,
    VerifiedObservation,
    counterevidence_disposition_fingerprint,
    verified_observation_fingerprint,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
)


_RecordT = TypeVar("_RecordT")


class CommitEvaluationFailureKind(StrEnum):
    INVALID = "invalid"
    SAFETY_FINDING = "safety_finding"


class CommitReasonCode(StrEnum):
    INVALID_CONTEXT = "invalid_context"
    CONTEXT_EXPIRED = "context_expired"
    CONTEXT_AUTHORITY_FORK = "context_authority_fork"
    INVALID_MANIFEST = "invalid_manifest"
    MANIFEST_ROOT_MISMATCH = "manifest_root_mismatch"
    POLICY_ROOT_MISMATCH = "policy_root_mismatch"
    RISK_HEAD_MISMATCH = "risk_head_mismatch"
    THRESHOLD_MISMATCH = "threshold_mismatch"
    MEMBERSHIP_HEAD_MISMATCH = "membership_head_mismatch"
    REPLAY_HEAD_MISMATCH = "replay_head_mismatch"
    SUPPORT_REPLAY_HEAD_MISMATCH = "support_replay_head_mismatch"
    CANDIDATE_COVERAGE_MISMATCH = "candidate_coverage_mismatch"
    CANDIDATE_CLAIM_CONFLICT = "candidate_claim_conflict"
    CANDIDATE_CLAIM_MISMATCH = "candidate_claim_mismatch"
    EVIDENCE_BINDING_INVALID = "evidence_binding_invalid"
    EVIDENCE_EVALUATION_INVALID = "evidence_evaluation_invalid"
    SUPPORT_EVALUATION_INVALID = "support_evaluation_invalid"
    REPLAY_COVERAGE_MISMATCH = "replay_coverage_mismatch"
    CROSS_RECORD_REPLAY = "cross_record_replay"
    SUPPORT_EQUIVOCATION = "support_equivocation"
    STOP_RESOLUTION_UNRESOLVED = "stop_resolution_unresolved"
    STOP_BLOCKED = "stop_blocked"
    COMMIT_PERMISSION_UNRESOLVED = "commit_permission_unresolved"
    COMMIT_PERMISSION_DENIED = "commit_permission_denied"
    POSITIVE_EVIDENCE_INSUFFICIENT = "positive_evidence_insufficient"
    COUNTEREVIDENCE_LIMIT_EXCEEDED = "counterevidence_limit_exceeded"
    COUNTEREVIDENCE_RATIO_EXCEEDED = "counterevidence_ratio_exceeded"
    CRITICAL_COUNTEREVIDENCE_UNRESOLVED = "critical_counterevidence_unresolved"
    CHALLENGE_COVERAGE_INCOMPLETE = "challenge_coverage_incomplete"
    SUPPORT_CLUSTERS_INSUFFICIENT = "support_clusters_insufficient"
    SUPPORT_RATIO_INSUFFICIENT = "support_ratio_insufficient"
    SOURCE_DIVERSITY_INSUFFICIENT = "source_diversity_insufficient"
    ASSURANCE_INSUFFICIENT = "assurance_insufficient"
    NO_UNIQUE_LEADER = "no_unique_leader"
    NOT_LEADER = "not_leader"
    MARGIN_INSUFFICIENT = "margin_insufficient"


class CommitEvaluationError(GovernanceError):
    """Typed fail-closed error for inputs that cannot produce an assessment."""

    def __init__(
        self,
        reason_code: CommitReasonCode,
        message: str,
        *,
        kind: CommitEvaluationFailureKind = CommitEvaluationFailureKind.INVALID,
        references: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.kind = kind
        self.references = tuple(references)


@dataclass(frozen=True)
class CandidateClaimBinding:
    candidate_id: str
    claim_fingerprint: str
    safe_fallback: bool

    def __post_init__(self) -> None:
        require_commit_text(self.candidate_id, "candidate claim candidate_id")
        require_commit_fingerprint(
            self.claim_fingerprint,
            "candidate claim claim_fingerprint",
        )
        require_commit_bool(self.safe_fallback, "candidate claim safe_fallback")


@dataclass(frozen=True)
class CommitEvaluationContext:
    context_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_claims: tuple[CandidateClaimBinding, ...]
    substantive_candidate_ids: tuple[str, ...]
    fallback_candidate_id: str
    risk_chain_state_fingerprint: str
    risk_assessment_fingerprint: str
    risk_policy_root: str
    threshold_fingerprint: str
    membership_snapshot_fingerprint: str
    membership_epoch_state_fingerprint: str
    membership_root: str
    replay_state_fingerprint: str
    replay_receipt_root: str
    support_replay_state_fingerprint: str
    support_replay_root: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _authority_key: str = field(
        default="",
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        claims = _canonical_candidate_claims(self.candidate_claims)
        object.__setattr__(self, "candidate_claims", claims)
        object.__setattr__(
            self,
            "substantive_candidate_ids",
            require_commit_labels(
                self.substantive_candidate_ids,
                "commit context substantive candidates",
            ),
        )
        _validate_commit_evaluation_context_shape(self)


@dataclass(frozen=True)
class CandidateCommitInput:
    candidate_id: str
    claim_fingerprint: str
    evidence_binding: EvidenceBinding
    positive_observations: tuple[VerifiedObservation, ...]
    counter_observations: tuple[VerifiedObservation, ...]
    dispositions: tuple[CounterevidenceDisposition, ...]
    challenges: tuple[VerifiedChallenge, ...]

    def __post_init__(self) -> None:
        require_commit_text(self.candidate_id, "candidate commit input candidate_id")
        require_commit_fingerprint(
            self.claim_fingerprint,
            "candidate commit input claim_fingerprint",
        )
        if type(self.evidence_binding) is not EvidenceBinding:
            raise GovernanceError(
                "candidate commit input requires a canonical evidence binding"
            )
        object.__setattr__(
            self,
            "positive_observations",
            _canonical_records(
                self.positive_observations,
                VerifiedObservation,
                verified_observation_fingerprint,
                "positive observation",
            ),
        )
        object.__setattr__(
            self,
            "counter_observations",
            _canonical_records(
                self.counter_observations,
                VerifiedObservation,
                verified_observation_fingerprint,
                "counter observation",
            ),
        )
        object.__setattr__(
            self,
            "dispositions",
            _canonical_records(
                self.dispositions,
                CounterevidenceDisposition,
                counterevidence_disposition_fingerprint,
                "counterevidence disposition",
            ),
        )
        object.__setattr__(
            self,
            "challenges",
            _canonical_records(
                self.challenges,
                VerifiedChallenge,
                verified_challenge_fingerprint,
                "challenge",
            ),
        )


def _validate_commit_evaluation_context_shape(
    context: CommitEvaluationContext,
) -> None:
    profile = require_commit_profile(context.profile, "commit context profile")
    assurance = require_commit_assurance(context.assurance, "commit context assurance")
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("commit context profile/assurance mismatch")
    for name in (
        "context_id",
        "protocol_id",
        "run_id",
        "target",
        "fallback_candidate_id",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(context, name), f"commit context {name}")
    for name in (
        "manifest_root",
        "commit_policy_root",
        "risk_chain_state_fingerprint",
        "risk_assessment_fingerprint",
        "risk_policy_root",
        "threshold_fingerprint",
        "membership_snapshot_fingerprint",
        "membership_epoch_state_fingerprint",
        "membership_root",
        "replay_state_fingerprint",
        "replay_receipt_root",
        "support_replay_state_fingerprint",
        "support_replay_root",
    ):
        require_commit_fingerprint(getattr(context, name), f"commit context {name}")
    require_commit_step(context.epoch, "commit context epoch")
    issued = require_commit_step(
        context.issued_at_step, "commit context issued_at_step"
    )
    expires = require_commit_step(
        context.expires_at_step,
        "commit context expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("commit context expiry must be after issuance")
    if type(context.authority) is not AuthorityLevel or not can_verify(
        context.authority
    ):
        raise GovernanceError("commit context authority is invalid")
    claim_ids = tuple(item.candidate_id for item in context.candidate_claims)
    if not set(context.substantive_candidate_ids).issubset(claim_ids):
        raise GovernanceError("commit context substantive candidates are undeclared")
    fallback = next(
        (
            item
            for item in context.candidate_claims
            if item.candidate_id == context.fallback_candidate_id
        ),
        None,
    )
    if fallback is None or not fallback.safe_fallback:
        raise GovernanceError("commit context fallback binding is invalid")
    expected_substantive = require_commit_labels(
        tuple(
            item.candidate_id
            for item in context.candidate_claims
            if item.candidate_id != context.fallback_candidate_id
        ),
        "commit context expected substantive candidates",
    )
    if tuple(context.substantive_candidate_ids) != expected_substantive:
        raise GovernanceError("commit context substantive candidate set is invalid")


def _canonical_candidate_claims(
    claims: Sequence[CandidateClaimBinding],
) -> tuple[CandidateClaimBinding, ...]:
    values = tuple(claims)
    if not values or any(type(item) is not CandidateClaimBinding for item in values):
        raise GovernanceError("commit context candidate claims are invalid")
    normalized = tuple(sorted(values, key=lambda item: item.candidate_id))
    ids = tuple(item.candidate_id for item in normalized)
    if len(ids) != len(set(ids)):
        raise GovernanceError("commit context candidate claims contain duplicates")
    return normalized


def _canonical_records(
    values: Sequence[_RecordT],
    expected_type: type[_RecordT],
    fingerprint: Callable[[_RecordT], str],
    label: str,
) -> tuple[_RecordT, ...]:
    records = tuple(values)
    if any(type(item) is not expected_type for item in records):
        raise GovernanceError(f"candidate commit input {label} is not canonical")
    return tuple(sorted(records, key=fingerprint))


_PUBLIC_MODULE = "pheroos.governance.commit"
for _public_object in (
    CandidateClaimBinding,
    CandidateCommitInput,
    CommitEvaluationContext,
    CommitEvaluationError,
    CommitEvaluationFailureKind,
    CommitReasonCode,
):
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object
