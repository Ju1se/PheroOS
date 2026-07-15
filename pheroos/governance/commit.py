from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock

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
    ChallengeCoverage,
    VerifiedChallenge,
    challenge_coverage_fingerprint,
    evaluate_challenge_coverage,
    verified_challenge_fingerprint,
)
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    canonical_commit_set,
    ceil_scaled_count,
    commit_payload_fingerprint,
    require_authority_integer,
)
from pheroos.governance.commit_state import (
    CommitReplayState,
    ReplayNamespace,
    ReplayReceipt,
    commit_replay_state_fingerprint,
    commit_replay_state_matches,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.evidence_binding import (
    EvidenceBinding,
    EvidenceSummary,
    evidence_binding_fingerprint,
    evidence_binding_is_authoritative,
    evidence_summary_fingerprint,
    evaluate_evidence_binding,
)
from pheroos.governance.observation import (
    CounterevidenceDisposition,
    VerifiedObservation,
    counterevidence_disposition_fingerprint,
    verified_observation_fingerprint,
)
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
    action_permission_matches,
)
from pheroos.governance.replay import (
    challenge_replay_receipt,
    counterevidence_disposition_replay_receipt,
    observation_replay_receipt,
)
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_matches,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
    risk_assessment_matches,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
    stop_resolution_verification_matches,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseEvaluation,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_matches,
    evaluate_support_leases,
    support_lease_fingerprint,
    support_lease_is_authoritative,
    support_lease_revocation_fingerprint,
    support_lease_revocation_is_authoritative,
    support_lease_replay_state_fingerprint,
    support_lease_replay_state_is_current,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAction,
    CommitAssurance,
    CollectiveCommitPolicy,
)
from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
)
from pheroos.protocol.models import CapabilityManifest
from pheroos.protocol.validation import validate_capability_manifest


_COMMIT_CONTEXT_ISSUANCE = object()
_COMMIT_ASSESSMENT_ISSUANCE = object()
_COMMIT_CONTEXT_AUTHORITY_LOCK = RLock()
_COMMIT_CONTEXT_AUTHORITIES: dict[
    str,
    tuple[str, "CommitEvaluationContext"],
] = {}
_COMMIT_CONTEXT_CLAIM_AUTHORITIES: dict[str, str] = {}
_ASSURANCE_RANK = {
    CommitAssurance.ADVISORY: 0,
    CommitAssurance.EVIDENCE_BOUND: 1,
    CommitAssurance.CERTIFIED: 2,
    CommitAssurance.DISTRIBUTED: 3,
}
_COMMIT_INPUT_REPLAY_NAMESPACES = frozenset(
    {
        ReplayNamespace.OBSERVATION,
        ReplayNamespace.CHALLENGE,
        ReplayNamespace.COUNTEREVIDENCE_DISPOSITION,
        ReplayNamespace.SUPPORT_LEASE,
        ReplayNamespace.SUPPORT_REVOCATION,
    }
)


class CommitAssessmentStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    SAFETY_VIOLATION = "safety_violation"


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
    CRITICAL_COUNTEREVIDENCE_UNRESOLVED = (
        "critical_counterevidence_unresolved"
    )
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


@dataclass(frozen=True)
class CandidateCommitMetrics:
    candidate_id: str
    claim_fingerprint: str
    evidence_binding_fingerprint: str
    evidence_summary_fingerprint: str
    positive_root: str
    counter_root: str
    disposition_root: str
    evidence_root: str
    challenge_root: str
    challenge_coverage_fingerprint: str
    lease_root: str
    support_replay_scope_root: str
    positive_evidence: int
    counterevidence: int
    weighted_counterevidence: int
    net_evidence: int
    counterevidence_ratio_ppm: int
    active_support_clusters: int
    eligible_support_clusters: int
    support_threshold_clusters: int
    support_ratio_ppm: int
    source_diversity: int
    margin: int
    missing_challenge_categories: tuple[str, ...]
    blocker_references: tuple[str, ...]
    equivocation_finding_ids: tuple[str, ...]
    replay_conflict_references: tuple[str, ...]
    roots_valid: bool
    positive_threshold_satisfied: bool
    counter_limit_satisfied: bool
    counter_ratio_satisfied: bool
    critical_counterevidence_clear: bool
    challenge_coverage_satisfied: bool
    support_cluster_satisfied: bool
    support_ratio_satisfied: bool
    source_diversity_satisfied: bool
    minimum_assurance_satisfied: bool
    margin_satisfied: bool
    unique_leader: bool
    stop_resolution_satisfied: bool
    commit_permission_satisfied: bool
    replay_clear: bool
    equivocation_clear: bool
    ready_for_stability: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_candidate_commit_metrics(self)


@dataclass(frozen=True)
class CommitAssessment:
    assessment_id: str
    status: CommitAssessmentStatus
    profile: str
    assurance: CommitAssurance
    context_fingerprint: str
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
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
    stop_resolution_fingerprint: str
    permission_fingerprint: str
    collective_evidence_root: str
    collective_challenge_root: str
    collective_lease_root: str
    candidate_metrics: tuple[CandidateCommitMetrics, ...]
    unique_leader: bool
    leader_candidate_id: str
    tied_candidate_ids: tuple[str, ...]
    leader_margin: int
    leader_ready_for_stability: bool
    blocker_references: tuple[str, ...]
    equivocation_finding_ids: tuple[str, ...]
    replay_conflict_references: tuple[str, ...]
    reason_codes: tuple[str, ...]
    issuer_id: str
    authority: AuthorityLevel
    evaluated_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_metrics",
            _canonical_metrics(self.candidate_metrics),
        )
        for name in (
            "tied_candidate_ids",
            "reason_codes",
        ):
            object.__setattr__(
                self,
                name,
                require_commit_labels(
                    getattr(self, name),
                    f"commit assessment {name}",
                    allow_empty=True,
                ),
            )
        for name in (
            "blocker_references",
            "equivocation_finding_ids",
            "replay_conflict_references",
        ):
            object.__setattr__(
                self,
                name,
                _canonical_fingerprints(
                    getattr(self, name),
                    f"commit assessment {name}",
                    allow_empty=True,
                ),
            )
        _validate_commit_assessment_shape(self)


def issue_commit_evaluation_context(
    manifest: CapabilityManifest,
    *,
    context_id: str,
    profile: str,
    assurance: CommitAssurance,
    run_id: str,
    target: str,
    epoch: int,
    candidate_claims: Mapping[str, str],
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> CommitEvaluationContext:
    if type(manifest) is not CapabilityManifest:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context requires a canonical CapabilityManifest",
        )
    diagnostic_codes = tuple(
        item.code
        for item in validate_capability_manifest(manifest)
        if item.level == "error"
    )
    if diagnostic_codes:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context manifest is invalid: " + ", ".join(diagnostic_codes),
        )
    policy = manifest.protocol.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context requires an active collective commit policy",
        )
    normalized_profile = require_commit_profile(profile, "commit context profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        "commit context assurance",
    )
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[normalized_assurance.value]:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context profile and assurance do not match",
        )
    if policy.assurance != normalized_assurance.value:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context cannot downgrade or replace the declared assurance",
        )
    normalized_target = require_commit_text(target, "commit context target")
    if policy.target != normalized_target:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "commit context target is not the active policy target",
        )
    normalized_run = require_commit_text(run_id, "commit context run_id")
    normalized_epoch = require_commit_step(epoch, "commit context epoch")
    current = require_commit_step(current_step, "commit context current_step")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_CONTEXT,
            "commit context issuance requires governance authority",
        )

    manifest_root = commit_manifest_fingerprint(manifest, profile=normalized_profile)
    policy_root = commit_policy_fingerprint(policy, profile=normalized_profile)
    protocol_id = manifest.protocol.id
    _require_authoritative_heads(
        policy=policy,
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=normalized_run,
        target=normalized_target,
        epoch=normalized_epoch,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
        current_step=current,
    )

    declared = tuple(
        candidate
        for candidate in manifest.protocol.candidates
        if candidate.target == normalized_target
    )
    if not isinstance(candidate_claims, Mapping):
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "candidate claims must be a mapping",
        )
    expected_ids = {candidate.id for candidate in declared}
    if set(candidate_claims) != expected_ids:
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "candidate claims must cover every declared target candidate exactly",
        )
    claims = tuple(
        CandidateClaimBinding(
            candidate_id=candidate.id,
            claim_fingerprint=require_commit_fingerprint(
                candidate_claims[candidate.id],
                f"candidate claim {candidate.id}",
            ),
            safe_fallback=candidate.safe_fallback,
        )
        for candidate in declared
    )
    fallback_id = policy.terminal_outcome.safe_fallback_candidate
    fallback_claim = next(
        (item for item in claims if item.candidate_id == fallback_id),
        None,
    )
    if fallback_claim is None or not fallback_claim.safe_fallback:
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "commit context does not bind the declared safe fallback",
        )
    substantive_ids = tuple(
        item.candidate_id
        for item in claims
        if item.candidate_id != fallback_id
    )
    if not substantive_ids:
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "commit context requires a substantive candidate",
        )
    expiry = min(
        risk_chain_state.expires_at_step,
        risk_assessment.expires_at_step,
        threshold_snapshot.expires_at_step,
        membership_snapshot.expires_at_step,
        membership_epoch_state.expires_at_step,
    )
    if current >= expiry:
        raise CommitEvaluationError(
            CommitReasonCode.CONTEXT_EXPIRED,
            "commit context authority inputs are no longer fresh",
        )
    context = CommitEvaluationContext(
        context_id=require_commit_text(context_id, "commit context context_id"),
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=normalized_run,
        target=normalized_target,
        epoch=normalized_epoch,
        candidate_claims=claims,
        substantive_candidate_ids=substantive_ids,
        fallback_candidate_id=fallback_id,
        risk_chain_state_fingerprint=risk_assessment_chain_state_fingerprint(
            risk_chain_state
        ),
        risk_assessment_fingerprint=risk_assessment_fingerprint(risk_assessment),
        risk_policy_root=risk_assessment.risk_policy_root,
        threshold_fingerprint=commit_threshold_snapshot_fingerprint(
            threshold_snapshot
        ),
        membership_snapshot_fingerprint=eligible_principal_snapshot_fingerprint(
            membership_snapshot
        ),
        membership_epoch_state_fingerprint=(
            eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        ),
        membership_root=membership_snapshot.membership_root,
        replay_state_fingerprint=commit_replay_state_fingerprint(replay_state),
        replay_receipt_root=replay_state.receipt_root,
        support_replay_state_fingerprint=(
            support_lease_replay_state_fingerprint(support_replay_state)
        ),
        support_replay_root=support_replay_state.replay_root,
        issuer_id=require_commit_text(issuer_id, "commit context issuer_id"),
        authority=authority,
        issued_at_step=current,
        expires_at_step=expiry,
        provenance=require_commit_text(provenance, "commit context provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit context trace_event_id",
        ),
    )
    context_fingerprint = commit_evaluation_context_fingerprint(context)
    authority_key = _commit_context_authority_key(context)
    claim_authority_key = _commit_context_claim_authority_key(context)
    claim_authority_fingerprint = _commit_context_claims_fingerprint(context)
    with _COMMIT_CONTEXT_AUTHORITY_LOCK:
        existing_claims = _COMMIT_CONTEXT_CLAIM_AUTHORITIES.get(
            claim_authority_key
        )
        if (
            existing_claims is not None
            and existing_claims != claim_authority_fingerprint
        ):
            raise CommitEvaluationError(
                CommitReasonCode.CONTEXT_AUTHORITY_FORK,
                "commit candidate claims are immutable within one run target epoch",
                kind=CommitEvaluationFailureKind.SAFETY_FINDING,
                references=(existing_claims, claim_authority_fingerprint),
            )
        existing = _COMMIT_CONTEXT_AUTHORITIES.get(authority_key)
        if existing is not None:
            existing_fingerprint, existing_context = existing
            if (
                existing_fingerprint == context_fingerprint
                and commit_evaluation_context_is_authoritative(existing_context)
            ):
                return existing_context
            raise CommitEvaluationError(
                CommitReasonCode.CONTEXT_AUTHORITY_FORK,
                "commit context authority heads already have a conflicting context",
                kind=CommitEvaluationFailureKind.SAFETY_FINDING,
                references=(existing_fingerprint, context_fingerprint),
            )
        object.__setattr__(context, "_authority_key", authority_key)
        object.__setattr__(
            context,
            "_issuance",
            (_COMMIT_CONTEXT_ISSUANCE, context_fingerprint),
        )
        _COMMIT_CONTEXT_AUTHORITIES[authority_key] = (
            context_fingerprint,
            context,
        )
        _COMMIT_CONTEXT_CLAIM_AUTHORITIES[claim_authority_key] = (
            claim_authority_fingerprint
        )
        return context


def assess_optimal_commit(
    context: CommitEvaluationContext,
    *,
    manifest: CapabilityManifest,
    candidate_inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation],
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    stop_resolution: StopResolutionVerification,
    commit_permission: ActionPermission,
    assessment_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> CommitAssessment:
    current = require_commit_step(current_step, "optimal commit current_step")
    if not commit_evaluation_context_is_authoritative(context):
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_CONTEXT,
            "optimal commit requires an authoritative evaluation context",
        )
    if not context.issued_at_step <= current < context.expires_at_step:
        raise CommitEvaluationError(
            CommitReasonCode.CONTEXT_EXPIRED,
            "optimal commit evaluation context is not fresh",
        )
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_CONTEXT,
            "optimal commit assessment requires governance authority",
        )
    if type(manifest) is not CapabilityManifest:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "optimal commit requires a canonical manifest",
        )
    errors = tuple(
        item.code
        for item in validate_capability_manifest(manifest)
        if item.level == "error"
    )
    if errors:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "optimal commit manifest is invalid: " + ", ".join(errors),
        )
    policy = manifest.protocol.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_MANIFEST,
            "optimal commit manifest has no active commit policy",
        )
    observed_manifest_root = commit_manifest_fingerprint(
        manifest,
        profile=context.profile,
    )
    if observed_manifest_root != context.manifest_root:
        raise CommitEvaluationError(
            CommitReasonCode.MANIFEST_ROOT_MISMATCH,
            "optimal commit manifest does not match the issued context",
        )
    observed_policy_root = commit_policy_fingerprint(
        policy,
        profile=context.profile,
    )
    if observed_policy_root != context.commit_policy_root:
        raise CommitEvaluationError(
            CommitReasonCode.POLICY_ROOT_MISMATCH,
            "optimal commit policy does not match the issued context",
        )
    _require_authoritative_heads(
        policy=policy,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        epoch=context.epoch,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
        current_step=current,
    )
    _require_context_head_fingerprints(
        context,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
    )
    inputs = _validate_candidate_inputs(context, candidate_inputs)
    normalized_leases = tuple(leases)
    normalized_revocations = tuple(revocations)
    declared_claims = {
        item.candidate_id: item.claim_fingerprint for item in context.candidate_claims
    }
    for lease in normalized_leases:
        if type(lease) is not SupportLease:
            raise CommitEvaluationError(
                CommitReasonCode.SUPPORT_EVALUATION_INVALID,
                "optimal commit lease set contains a non-canonical record",
            )
        if not support_lease_is_authoritative(lease):
            raise CommitEvaluationError(
                CommitReasonCode.SUPPORT_EVALUATION_INVALID,
                "optimal commit lease set contains a forged record",
            )
        if (
            lease.profile != context.profile
            or lease.assurance is not context.assurance
            or lease.manifest_root != context.manifest_root
            or lease.commit_policy_root != context.commit_policy_root
            or lease.protocol_id != context.protocol_id
            or lease.run_id != context.run_id
            or lease.target != context.target
            or lease.epoch != context.epoch
            or lease.candidate_id not in context.substantive_candidate_ids
        ):
            raise CommitEvaluationError(
                CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
                "optimal commit lease references a hidden or unbound candidate scope",
            )
        if declared_claims[lease.candidate_id] != lease.claim_fingerprint:
            raise CommitEvaluationError(
                CommitReasonCode.CANDIDATE_CLAIM_MISMATCH,
                "optimal commit lease claim does not match the evaluation context",
            )
    for revocation in normalized_revocations:
        if type(revocation) is not SupportLeaseRevocation:
            raise CommitEvaluationError(
                CommitReasonCode.SUPPORT_EVALUATION_INVALID,
                "optimal commit revocation set contains a non-canonical record",
            )

    stop_root = _canonical_stop_fingerprint(stop_resolution)
    permission_root = _canonical_permission_fingerprint(commit_permission)
    context_ref = commit_evaluation_context_fingerprint(context)
    stop_bound = stop_resolution_verification_matches(
        stop_resolution,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        action=CommitAction.COMMIT,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref="",
        current_step=current,
        require_unblocked=False,
    )
    permission_bound = action_permission_matches(
        commit_permission,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        action=CommitAction.COMMIT,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref="",
        current_step=current,
        require_allowed=False,
    )

    try:
        receipts = build_commit_replay_receipts(
            inputs,
            normalized_leases,
            normalized_revocations,
        )
    except GovernanceError as exc:
        raise CommitEvaluationError(
            CommitReasonCode.REPLAY_COVERAGE_MISMATCH,
            f"commit replay inputs cannot be projected canonically: {exc}",
        ) from exc
    recorded_scoped_receipts = _scoped_commit_input_receipts(
        context,
        replay_state.receipts,
    )
    supplied_scoped_receipts = _scoped_commit_input_receipts(context, receipts)
    replay_conflicts = _cross_record_replay_conflicts(
        inputs,
        (*recorded_scoped_receipts, *supplied_scoped_receipts),
    )
    if replay_conflicts:
        return _issue_commit_assessment(
            context=context,
            status=CommitAssessmentStatus.SAFETY_VIOLATION,
            candidate_metrics=(),
            leader_candidate_id="",
            tied_candidate_ids=(),
            leader_margin=0,
            blocker_references=replay_conflicts,
            equivocation_finding_ids=(),
            replay_conflict_references=replay_conflicts,
            reason_codes=(CommitReasonCode.CROSS_RECORD_REPLAY.value,),
            stop_resolution_fingerprint=stop_root,
            permission_fingerprint=permission_root,
            assessment_id=assessment_id,
            issuer_id=issuer_id,
            authority=authority,
            evaluated_at_step=current,
            provenance=provenance,
            trace_event_id=trace_event_id,
        )
    recorded_set = set(recorded_scoped_receipts)
    supplied_set = set(supplied_scoped_receipts)
    if recorded_set != supplied_set:
        mismatched_receipts = recorded_set.symmetric_difference(supplied_set)
        raise CommitEvaluationError(
            CommitReasonCode.REPLAY_COVERAGE_MISMATCH,
            "authoritative replay head and supplied scoped inputs differ",
            references=tuple(
                sorted(item.payload_fingerprint for item in mismatched_receipts)
            ),
        )

    summaries: dict[str, EvidenceSummary] = {}
    support: dict[str, SupportLeaseEvaluation] = {}
    active_challenge_coverage: dict[str, ChallengeCoverage] = {}
    for item in inputs:
        if not evidence_binding_is_authoritative(item.evidence_binding):
            raise CommitEvaluationError(
                CommitReasonCode.EVIDENCE_BINDING_INVALID,
                f"candidate {item.candidate_id} evidence binding is not authoritative",
            )
        if (
            item.evidence_binding.profile != context.profile
            or item.evidence_binding.assurance is not context.assurance
            or item.evidence_binding.manifest_root != context.manifest_root
            or item.evidence_binding.commit_policy_root != context.commit_policy_root
            or item.evidence_binding.protocol_id != context.protocol_id
            or item.evidence_binding.run_id != context.run_id
            or item.evidence_binding.target != context.target
            or item.evidence_binding.epoch != context.epoch
            or item.evidence_binding.candidate_id != item.candidate_id
            or item.evidence_binding.claim_fingerprint != item.claim_fingerprint
        ):
            raise CommitEvaluationError(
                CommitReasonCode.EVIDENCE_BINDING_INVALID,
                f"candidate {item.candidate_id} evidence binding has a root or scope mismatch",
            )
        try:
            summaries[item.candidate_id] = evaluate_evidence_binding(
                item.evidence_binding,
                positive_observations=item.positive_observations,
                counter_observations=item.counter_observations,
                dispositions=item.dispositions,
                challenges=item.challenges,
                evidence_policy=policy.evidence_qualification,
                current_step=current,
            )
            active_challenge_coverage[item.candidate_id] = (
                evaluate_challenge_coverage(
                    item.challenges,
                    required_categories=(
                        threshold_snapshot.required_challenge_categories
                    ),
                    profile=context.profile,
                    assurance=context.assurance,
                    manifest_root=context.manifest_root,
                    commit_policy_root=context.commit_policy_root,
                    protocol_id=context.protocol_id,
                    run_id=context.run_id,
                    target=context.target,
                    candidate_id=item.candidate_id,
                    claim_fingerprint=item.claim_fingerprint,
                    epoch=context.epoch,
                    current_step=current,
                )
            )
        except GovernanceError as exc:
            raise CommitEvaluationError(
                CommitReasonCode.EVIDENCE_EVALUATION_INVALID,
                f"candidate {item.candidate_id} evidence cannot be reconstructed: {exc}",
            ) from exc
        try:
            support[item.candidate_id] = evaluate_support_leases(
                normalized_leases,
                revocations=normalized_revocations,
                membership_snapshot=membership_snapshot,
                membership_epoch_state=membership_epoch_state,
                replay_state=support_replay_state,
                commit_policy=policy,
                candidate_id=item.candidate_id,
                claim_fingerprint=item.claim_fingerprint,
                current_step=current,
            )
        except GovernanceError as exc:
            raise CommitEvaluationError(
                CommitReasonCode.SUPPORT_EVALUATION_INVALID,
                f"candidate {item.candidate_id} support cannot be reconstructed: {exc}",
            ) from exc

    scores = {candidate_id: summary.net_evidence for candidate_id, summary in summaries.items()}
    max_score = max(scores.values())
    tied_ids = tuple(
        sorted(candidate_id for candidate_id, score in scores.items() if score == max_score)
    )
    unique_leader_id = tied_ids[0] if len(tied_ids) == 1 else ""
    assurance_ok = (
        _ASSURANCE_RANK[context.assurance]
        >= _ASSURANCE_RANK[threshold_snapshot.minimum_assurance]
    )
    stop_ok = bool(stop_bound and not stop_resolution.blocked)
    permission_ok = bool(permission_bound and commit_permission.allowed)
    all_findings = tuple(
        sorted(
            {
                finding.finding_id
                for evaluation in support.values()
                for finding in evaluation.equivocation_findings
            }
        )
    )
    metrics: list[CandidateCommitMetrics] = []
    for item in inputs:
        summary = summaries[item.candidate_id]
        support_evaluation = support[item.candidate_id]
        coverage = active_challenge_coverage[item.candidate_id]
        other_best = max(
            (score for candidate_id, score in scores.items() if candidate_id != item.candidate_id),
            default=0,
        )
        margin = summary.net_evidence - max(other_best, 0)
        active_threshold_clusters = max(
            threshold_snapshot.minimum_support_clusters,
            ceil_scaled_count(
                support_evaluation.eligible_cluster_count,
                threshold_snapshot.minimum_support_ratio_ppm,
            ),
        )
        positive_ok = (
            summary.positive_evidence
            >= threshold_snapshot.minimum_positive_evidence
        )
        counter_ok = summary.counterevidence <= threshold_snapshot.maximum_counterevidence
        ratio_ok = (
            summary.counterevidence_ratio_ppm
            <= threshold_snapshot.maximum_counterevidence_ratio_ppm
        )
        critical_ok = not summary.blocking_critical_counter_observation_fingerprints
        challenge_ok = coverage.complete
        support_cluster_ok = (
            support_evaluation.active_support_cluster_count
            >= active_threshold_clusters
        )
        support_ratio_ok = (
            support_evaluation.support_ratio_ppm
            >= threshold_snapshot.minimum_support_ratio_ppm
        )
        diversity_ok = (
            summary.source_diversity
            >= threshold_snapshot.minimum_source_diversity
        )
        margin_ok = margin >= threshold_snapshot.minimum_margin
        is_unique_leader = item.candidate_id == unique_leader_id
        equivocation_ids = tuple(
            finding.finding_id
            for finding in support_evaluation.equivocation_findings
        )
        equivocation_clear = not equivocation_ids
        reasons: list[str] = []
        blockers: list[str] = []
        if not positive_ok:
            reasons.append(CommitReasonCode.POSITIVE_EVIDENCE_INSUFFICIENT.value)
        if not counter_ok:
            reasons.append(CommitReasonCode.COUNTEREVIDENCE_LIMIT_EXCEEDED.value)
        if not ratio_ok:
            reasons.append(CommitReasonCode.COUNTEREVIDENCE_RATIO_EXCEEDED.value)
        if not critical_ok:
            reasons.append(
                CommitReasonCode.CRITICAL_COUNTEREVIDENCE_UNRESOLVED.value
            )
            blockers.extend(summary.blocking_critical_counter_observation_fingerprints)
        if not challenge_ok:
            reasons.append(CommitReasonCode.CHALLENGE_COVERAGE_INCOMPLETE.value)
        if not support_cluster_ok:
            reasons.append(CommitReasonCode.SUPPORT_CLUSTERS_INSUFFICIENT.value)
        if not support_ratio_ok:
            reasons.append(CommitReasonCode.SUPPORT_RATIO_INSUFFICIENT.value)
        if not diversity_ok:
            reasons.append(CommitReasonCode.SOURCE_DIVERSITY_INSUFFICIENT.value)
        if not assurance_ok:
            reasons.append(CommitReasonCode.ASSURANCE_INSUFFICIENT.value)
        if not unique_leader_id:
            reasons.append(CommitReasonCode.NO_UNIQUE_LEADER.value)
        elif not is_unique_leader:
            reasons.append(CommitReasonCode.NOT_LEADER.value)
        if not margin_ok:
            reasons.append(CommitReasonCode.MARGIN_INSUFFICIENT.value)
        if not stop_bound:
            reasons.append(CommitReasonCode.STOP_RESOLUTION_UNRESOLVED.value)
        elif stop_resolution.blocked:
            reasons.append(CommitReasonCode.STOP_BLOCKED.value)
            blockers.append(stop_root)
        if not permission_bound:
            reasons.append(CommitReasonCode.COMMIT_PERMISSION_UNRESOLVED.value)
        elif not commit_permission.allowed:
            reasons.append(CommitReasonCode.COMMIT_PERMISSION_DENIED.value)
            blockers.append(permission_root)
        if not equivocation_clear:
            reasons.append(CommitReasonCode.SUPPORT_EQUIVOCATION.value)
            blockers.extend(equivocation_ids)
        ready = bool(
            positive_ok
            and counter_ok
            and ratio_ok
            and critical_ok
            and challenge_ok
            and support_cluster_ok
            and support_ratio_ok
            and diversity_ok
            and assurance_ok
            and is_unique_leader
            and margin_ok
            and stop_ok
            and permission_ok
            and equivocation_clear
        )
        metrics.append(
            CandidateCommitMetrics(
                candidate_id=item.candidate_id,
                claim_fingerprint=item.claim_fingerprint,
                evidence_binding_fingerprint=evidence_binding_fingerprint(
                    item.evidence_binding
                ),
                evidence_summary_fingerprint=evidence_summary_fingerprint(
                    summary,
                    profile=context.profile,
                ),
                positive_root=item.evidence_binding.positive_root,
                counter_root=item.evidence_binding.counter_root,
                disposition_root=item.evidence_binding.disposition_root,
                evidence_root=item.evidence_binding.evidence_root,
                challenge_root=item.evidence_binding.challenge_root,
                challenge_coverage_fingerprint=challenge_coverage_fingerprint(
                    coverage,
                    profile=context.profile,
                ),
                lease_root=support_evaluation.lease_root,
                support_replay_scope_root=(
                    support_evaluation.support_replay_scope_root
                ),
                positive_evidence=summary.positive_evidence,
                counterevidence=summary.counterevidence,
                weighted_counterevidence=summary.weighted_counterevidence,
                net_evidence=summary.net_evidence,
                counterevidence_ratio_ppm=summary.counterevidence_ratio_ppm,
                active_support_clusters=(
                    support_evaluation.active_support_cluster_count
                ),
                eligible_support_clusters=(
                    support_evaluation.eligible_cluster_count
                ),
                support_threshold_clusters=active_threshold_clusters,
                support_ratio_ppm=support_evaluation.support_ratio_ppm,
                source_diversity=summary.source_diversity,
                margin=margin,
                missing_challenge_categories=coverage.missing_categories,
                blocker_references=tuple(blockers),
                equivocation_finding_ids=equivocation_ids,
                replay_conflict_references=(),
                roots_valid=True,
                positive_threshold_satisfied=positive_ok,
                counter_limit_satisfied=counter_ok,
                counter_ratio_satisfied=ratio_ok,
                critical_counterevidence_clear=critical_ok,
                challenge_coverage_satisfied=challenge_ok,
                support_cluster_satisfied=support_cluster_ok,
                support_ratio_satisfied=support_ratio_ok,
                source_diversity_satisfied=diversity_ok,
                minimum_assurance_satisfied=assurance_ok,
                margin_satisfied=margin_ok,
                unique_leader=is_unique_leader,
                stop_resolution_satisfied=stop_ok,
                commit_permission_satisfied=permission_ok,
                replay_clear=True,
                equivocation_clear=equivocation_clear,
                ready_for_stability=ready,
                reason_codes=tuple(reasons),
            )
        )

    leader_metrics = next(
        (item for item in metrics if item.candidate_id == unique_leader_id),
        None,
    )
    safety = bool(all_findings)
    status = (
        CommitAssessmentStatus.SAFETY_VIOLATION
        if safety
        else (
            CommitAssessmentStatus.READY
            if leader_metrics is not None and leader_metrics.ready_for_stability
            else CommitAssessmentStatus.NOT_READY
        )
    )
    assessment_reasons = set(
        leader_metrics.reason_codes if leader_metrics is not None else ()
    )
    if not unique_leader_id:
        assessment_reasons.add(CommitReasonCode.NO_UNIQUE_LEADER.value)
    if safety:
        assessment_reasons.add(CommitReasonCode.SUPPORT_EQUIVOCATION.value)
    blockers = tuple(
        {
            reference
            for item in metrics
            for reference in item.blocker_references
        }
    )
    leader_margin = leader_metrics.margin if leader_metrics is not None else 0
    return _issue_commit_assessment(
        context=context,
        status=status,
        candidate_metrics=tuple(metrics),
        leader_candidate_id=unique_leader_id,
        tied_candidate_ids=tied_ids if not unique_leader_id else (),
        leader_margin=leader_margin,
        blocker_references=blockers,
        equivocation_finding_ids=all_findings,
        replay_conflict_references=(),
        reason_codes=tuple(assessment_reasons),
        stop_resolution_fingerprint=stop_root,
        permission_fingerprint=permission_root,
        assessment_id=assessment_id,
        issuer_id=issuer_id,
        authority=authority,
        evaluated_at_step=current,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )


def build_commit_replay_receipts(
    candidate_inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation] = (),
) -> tuple[ReplayReceipt, ...]:
    receipts: list[ReplayReceipt] = []
    for candidate_input in tuple(candidate_inputs):
        if type(candidate_input) is not CandidateCommitInput:
            raise GovernanceError(
                "commit replay receipt construction requires candidate inputs"
            )
        for observation in (
            *candidate_input.positive_observations,
            *candidate_input.counter_observations,
        ):
            receipts.append(observation_replay_receipt(observation))
        for challenge in candidate_input.challenges:
            receipts.append(challenge_replay_receipt(challenge))
        for disposition in candidate_input.dispositions:
            receipts.append(
                counterevidence_disposition_replay_receipt(disposition)
            )
    for lease in tuple(leases):
        if type(lease) is not SupportLease:
            raise GovernanceError(
                "commit replay receipt construction requires canonical leases"
            )
        receipts.append(_support_lease_commit_replay_receipt(lease))
    for revocation in tuple(revocations):
        receipts.append(_support_revocation_commit_replay_receipt(revocation))
    return tuple(
        sorted(
            receipts,
            key=lambda item: (
                item.namespace.value,
                item.record_id,
                item.nonce,
                item.payload_fingerprint,
            ),
        )
    )


def commit_evaluation_context_payload(
    context: CommitEvaluationContext,
) -> dict[str, object]:
    if type(context) is not CommitEvaluationContext:
        raise GovernanceError("commit evaluation context must be canonical")
    _validate_commit_evaluation_context_shape(context)
    return {
        "assurance": context.assurance,
        "authority": context.authority,
        "candidate_claims": tuple(
            {
                "candidate_id": item.candidate_id,
                "claim_fingerprint": item.claim_fingerprint,
                "safe_fallback": item.safe_fallback,
            }
            for item in context.candidate_claims
        ),
        "commit_policy_root": context.commit_policy_root,
        "context_id": context.context_id,
        "epoch": context.epoch,
        "expires_at_step": context.expires_at_step,
        "fallback_candidate_id": context.fallback_candidate_id,
        "issued_at_step": context.issued_at_step,
        "issuer_id": context.issuer_id,
        "manifest_root": context.manifest_root,
        "membership_epoch_state_fingerprint": (
            context.membership_epoch_state_fingerprint
        ),
        "membership_root": context.membership_root,
        "membership_snapshot_fingerprint": (
            context.membership_snapshot_fingerprint
        ),
        "profile": context.profile,
        "protocol_id": context.protocol_id,
        "provenance": context.provenance,
        "replay_receipt_root": context.replay_receipt_root,
        "replay_state_fingerprint": context.replay_state_fingerprint,
        "risk_assessment_fingerprint": context.risk_assessment_fingerprint,
        "risk_chain_state_fingerprint": context.risk_chain_state_fingerprint,
        "risk_policy_root": context.risk_policy_root,
        "run_id": context.run_id,
        "substantive_candidate_ids": context.substantive_candidate_ids,
        "support_replay_root": context.support_replay_root,
        "support_replay_state_fingerprint": (
            context.support_replay_state_fingerprint
        ),
        "target": context.target,
        "threshold_fingerprint": context.threshold_fingerprint,
        "trace_event_id": context.trace_event_id,
    }


def commit_evaluation_context_fingerprint(
    context: CommitEvaluationContext,
) -> str:
    return commit_payload_fingerprint(
        commit_evaluation_context_payload(context),
        schema="pheroos-commit-evaluation-context-v1",
        profile=context.profile,
    )


def commit_evaluation_context_is_authoritative(context: object) -> bool:
    if type(context) is not CommitEvaluationContext:
        return False
    try:
        _validate_commit_evaluation_context_shape(context)
        issuance = context._issuance
        authority_key = _commit_context_authority_key(context)
        claim_authority_key = _commit_context_claim_authority_key(context)
        claim_fingerprint = _commit_context_claims_fingerprint(context)
        with _COMMIT_CONTEXT_AUTHORITY_LOCK:
            registered = _COMMIT_CONTEXT_AUTHORITIES.get(authority_key)
            registered_claims = _COMMIT_CONTEXT_CLAIM_AUTHORITIES.get(
                claim_authority_key
            )
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_CONTEXT_ISSUANCE
            and issuance[1] == commit_evaluation_context_fingerprint(context)
            and context._authority_key == authority_key
            and registered is not None
            and registered[0] == issuance[1]
            and registered[1] is context
            and registered_claims == claim_fingerprint
        )
    except Exception:
        return False


def candidate_commit_metrics_payload(
    metrics: CandidateCommitMetrics,
) -> dict[str, object]:
    if type(metrics) is not CandidateCommitMetrics:
        raise GovernanceError("candidate commit metrics must be canonical")
    _validate_candidate_commit_metrics(metrics)
    return {
        name: getattr(metrics, name)
        for name in metrics.__dataclass_fields__
    }


def candidate_commit_metrics_fingerprint(
    metrics: CandidateCommitMetrics,
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        candidate_commit_metrics_payload(metrics),
        schema="pheroos-candidate-commit-metrics-v1",
        profile=require_commit_profile(profile, "candidate metrics profile"),
    )


def commit_assessment_payload(assessment: CommitAssessment) -> dict[str, object]:
    if type(assessment) is not CommitAssessment:
        raise GovernanceError("commit assessment must be canonical")
    _validate_commit_assessment_shape(assessment)
    return {
        "assessment_id": assessment.assessment_id,
        "assurance": assessment.assurance,
        "authority": assessment.authority,
        "blocker_references": assessment.blocker_references,
        "candidate_metrics": tuple(
            candidate_commit_metrics_payload(item)
            for item in assessment.candidate_metrics
        ),
        "collective_challenge_root": assessment.collective_challenge_root,
        "collective_evidence_root": assessment.collective_evidence_root,
        "collective_lease_root": assessment.collective_lease_root,
        "commit_policy_root": assessment.commit_policy_root,
        "context_fingerprint": assessment.context_fingerprint,
        "epoch": assessment.epoch,
        "equivocation_finding_ids": assessment.equivocation_finding_ids,
        "evaluated_at_step": assessment.evaluated_at_step,
        "issuer_id": assessment.issuer_id,
        "leader_candidate_id": assessment.leader_candidate_id,
        "leader_margin": assessment.leader_margin,
        "leader_ready_for_stability": assessment.leader_ready_for_stability,
        "manifest_root": assessment.manifest_root,
        "membership_epoch_state_fingerprint": (
            assessment.membership_epoch_state_fingerprint
        ),
        "membership_root": assessment.membership_root,
        "membership_snapshot_fingerprint": (
            assessment.membership_snapshot_fingerprint
        ),
        "permission_fingerprint": assessment.permission_fingerprint,
        "profile": assessment.profile,
        "protocol_id": assessment.protocol_id,
        "provenance": assessment.provenance,
        "reason_codes": assessment.reason_codes,
        "replay_conflict_references": assessment.replay_conflict_references,
        "replay_receipt_root": assessment.replay_receipt_root,
        "replay_state_fingerprint": assessment.replay_state_fingerprint,
        "risk_assessment_fingerprint": assessment.risk_assessment_fingerprint,
        "risk_chain_state_fingerprint": assessment.risk_chain_state_fingerprint,
        "risk_policy_root": assessment.risk_policy_root,
        "run_id": assessment.run_id,
        "status": assessment.status,
        "stop_resolution_fingerprint": assessment.stop_resolution_fingerprint,
        "support_replay_root": assessment.support_replay_root,
        "support_replay_state_fingerprint": (
            assessment.support_replay_state_fingerprint
        ),
        "target": assessment.target,
        "threshold_fingerprint": assessment.threshold_fingerprint,
        "tied_candidate_ids": assessment.tied_candidate_ids,
        "trace_event_id": assessment.trace_event_id,
        "unique_leader": assessment.unique_leader,
    }


def commit_assessment_fingerprint(assessment: CommitAssessment) -> str:
    return commit_payload_fingerprint(
        commit_assessment_payload(assessment),
        schema="pheroos-optimal-commit-assessment-v1",
        profile=assessment.profile,
    )


def rebuild_commit_assessment_roots(
    assessment: CommitAssessment,
) -> dict[str, str]:
    if type(assessment) is not CommitAssessment:
        raise GovernanceError("commit assessment must be canonical")
    return _rebuild_collective_assessment_roots(
        assessment.candidate_metrics,
        profile=assessment.profile,
    )


def commit_assessment_is_authoritative(assessment: object) -> bool:
    if type(assessment) is not CommitAssessment:
        return False
    try:
        _validate_commit_assessment_shape(assessment)
        issuance = assessment._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_ASSESSMENT_ISSUANCE
            and issuance[1] == commit_assessment_fingerprint(assessment)
        )
    except Exception:
        return False


def _require_authoritative_heads(
    *,
    policy: CollectiveCommitPolicy,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    current_step: int,
) -> None:
    if not risk_assessment_matches(
        risk_assessment,
        chain_state=risk_chain_state,
        commit_policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.RISK_HEAD_MISMATCH,
            "risk assessment is not the authoritative current chain head",
        )
    if not commit_threshold_snapshot_matches(
        threshold_snapshot,
        assessment=risk_assessment,
        chain_state=risk_chain_state,
        commit_policy=policy,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.THRESHOLD_MISMATCH,
            "commit threshold is not authoritative, active, and risk-bound",
        )
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.MEMBERSHIP_HEAD_MISMATCH,
            "membership snapshot is not the immutable authoritative epoch head",
        )
    if not commit_replay_state_matches(
        replay_state,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        current_step=current_step,
    ):
        raise CommitEvaluationError(
            CommitReasonCode.REPLAY_HEAD_MISMATCH,
            "commit replay state is not the authoritative current run head",
        )
    if not support_lease_replay_state_is_current(support_replay_state) or (
        support_replay_state.profile != profile
        or support_replay_state.protocol_id != protocol_id
    ):
        raise CommitEvaluationError(
            CommitReasonCode.SUPPORT_REPLAY_HEAD_MISMATCH,
            "support replay state is not the authoritative current head",
        )


def _commit_context_authority_key(context: CommitEvaluationContext) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": context.assurance,
            "commit_policy_root": context.commit_policy_root,
            "epoch": context.epoch,
            "manifest_root": context.manifest_root,
            "membership_epoch_state_fingerprint": (
                context.membership_epoch_state_fingerprint
            ),
            "membership_root": context.membership_root,
            "membership_snapshot_fingerprint": (
                context.membership_snapshot_fingerprint
            ),
            "profile": context.profile,
            "protocol_id": context.protocol_id,
            "replay_receipt_root": context.replay_receipt_root,
            "replay_state_fingerprint": context.replay_state_fingerprint,
            "risk_assessment_fingerprint": context.risk_assessment_fingerprint,
            "risk_chain_state_fingerprint": (
                context.risk_chain_state_fingerprint
            ),
            "risk_policy_root": context.risk_policy_root,
            "run_id": context.run_id,
            "support_replay_root": context.support_replay_root,
            "support_replay_state_fingerprint": (
                context.support_replay_state_fingerprint
            ),
            "target": context.target,
            "threshold_fingerprint": context.threshold_fingerprint,
        },
        schema="pheroos-commit-evaluation-context-authority-key-v1",
        profile=context.profile,
    )


def _commit_context_claim_authority_key(
    context: CommitEvaluationContext,
) -> str:
    return commit_payload_fingerprint(
        {
            "assurance": context.assurance,
            "commit_policy_root": context.commit_policy_root,
            "epoch": context.epoch,
            "manifest_root": context.manifest_root,
            "profile": context.profile,
            "protocol_id": context.protocol_id,
            "run_id": context.run_id,
            "target": context.target,
        },
        schema="pheroos-commit-candidate-claim-authority-key-v1",
        profile=context.profile,
    )


def _commit_context_claims_fingerprint(
    context: CommitEvaluationContext,
) -> str:
    return commit_payload_fingerprint(
        {
            "candidate_claims": tuple(
                {
                    "candidate_id": item.candidate_id,
                    "claim_fingerprint": item.claim_fingerprint,
                    "safe_fallback": item.safe_fallback,
                }
                for item in context.candidate_claims
            ),
            "fallback_candidate_id": context.fallback_candidate_id,
            "substantive_candidate_ids": context.substantive_candidate_ids,
        },
        schema="pheroos-commit-candidate-claims-v1",
        profile=context.profile,
    )


def _require_context_head_fingerprints(
    context: CommitEvaluationContext,
    *,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
) -> None:
    observed = {
        "risk_chain_state_fingerprint": risk_assessment_chain_state_fingerprint(
            risk_chain_state
        ),
        "risk_assessment_fingerprint": risk_assessment_fingerprint(risk_assessment),
        "threshold_fingerprint": commit_threshold_snapshot_fingerprint(
            threshold_snapshot
        ),
        "membership_snapshot_fingerprint": eligible_principal_snapshot_fingerprint(
            membership_snapshot
        ),
        "membership_epoch_state_fingerprint": (
            eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        ),
        "membership_root": membership_snapshot.membership_root,
        "replay_state_fingerprint": commit_replay_state_fingerprint(replay_state),
        "replay_receipt_root": replay_state.receipt_root,
        "support_replay_state_fingerprint": (
            support_lease_replay_state_fingerprint(support_replay_state)
        ),
        "support_replay_root": support_replay_state.replay_root,
    }
    for name, value in observed.items():
        if getattr(context, name) != value:
            code = (
                CommitReasonCode.REPLAY_HEAD_MISMATCH
                if name.startswith("replay_")
                else (
                    CommitReasonCode.SUPPORT_REPLAY_HEAD_MISMATCH
                    if name.startswith("support_replay_")
                    else (
                        CommitReasonCode.MEMBERSHIP_HEAD_MISMATCH
                        if name.startswith("membership_")
                        else (
                            CommitReasonCode.THRESHOLD_MISMATCH
                            if name.startswith("threshold_")
                            else CommitReasonCode.RISK_HEAD_MISMATCH
                        )
                    )
                )
            )
            raise CommitEvaluationError(
                code,
                f"commit context authority head changed: {name}",
            )


def _validate_candidate_inputs(
    context: CommitEvaluationContext,
    candidate_inputs: Sequence[CandidateCommitInput],
) -> tuple[CandidateCommitInput, ...]:
    inputs = tuple(candidate_inputs)
    if any(type(item) is not CandidateCommitInput for item in inputs):
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "candidate input set contains a non-canonical record",
        )
    claims_seen: dict[str, str] = {}
    for item in inputs:
        prior = claims_seen.setdefault(item.candidate_id, item.claim_fingerprint)
        if prior != item.claim_fingerprint:
            raise CommitEvaluationError(
                CommitReasonCode.CANDIDATE_CLAIM_CONFLICT,
                "one candidate is bound to multiple claims in one assessment",
            )
    observed_ids = tuple(item.candidate_id for item in inputs)
    if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(
        context.substantive_candidate_ids
    ):
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "candidate inputs must cover every substantive candidate exactly once",
        )
    expected_claims = {
        item.candidate_id: item.claim_fingerprint for item in context.candidate_claims
    }
    for item in inputs:
        if expected_claims[item.candidate_id] != item.claim_fingerprint:
            raise CommitEvaluationError(
                CommitReasonCode.CANDIDATE_CLAIM_MISMATCH,
                f"candidate {item.candidate_id} claim does not match the context",
            )
    return tuple(sorted(inputs, key=lambda item: item.candidate_id))


def _support_lease_commit_replay_receipt(
    lease: SupportLease,
) -> ReplayReceipt:
    if not support_lease_is_authoritative(lease):
        raise GovernanceError(
            "support lease replay receipt requires authoritative input"
        )
    return ReplayReceipt(
        namespace=ReplayNamespace.SUPPORT_LEASE,
        record_id=lease.lease_id,
        nonce=lease.nonce,
        payload_fingerprint=support_lease_fingerprint(lease),
        target=lease.target,
        candidate_id=lease.candidate_id,
        epoch=lease.epoch,
        principal_id=lease.principal_id,
    )


def _scoped_commit_input_receipts(
    context: CommitEvaluationContext,
    receipts: Sequence[ReplayReceipt],
) -> tuple[ReplayReceipt, ...]:
    substantive = set(context.substantive_candidate_ids)
    scoped = tuple(
        receipt
        for receipt in receipts
        if receipt.namespace in _COMMIT_INPUT_REPLAY_NAMESPACES
        and receipt.target == context.target
        and receipt.epoch == context.epoch
        and receipt.candidate_id in substantive
    )
    return tuple(
        sorted(
            set(scoped),
            key=lambda receipt: (
                receipt.namespace.value,
                receipt.record_id,
                receipt.nonce,
                receipt.payload_fingerprint,
            ),
        )
    )


def _support_revocation_commit_replay_receipt(
    revocation: SupportLeaseRevocation,
) -> ReplayReceipt:
    if not support_lease_revocation_is_authoritative(revocation):
        raise GovernanceError(
            "support revocation replay receipt requires authoritative input"
        )
    return ReplayReceipt(
        namespace=ReplayNamespace.SUPPORT_REVOCATION,
        record_id=revocation.revocation_id,
        nonce=commit_payload_fingerprint(
            {
                "namespace": ReplayNamespace.SUPPORT_REVOCATION,
                "record_id": revocation.revocation_id,
            },
            schema="pheroos-support-revocation-replay-nonce-v1",
            profile=revocation.profile,
        ),
        payload_fingerprint=support_lease_revocation_fingerprint(revocation),
        target=revocation.target,
        candidate_id=revocation.candidate_id,
        epoch=revocation.epoch,
        principal_id=revocation.principal_id,
    )


def _cross_record_replay_conflicts(
    candidate_inputs: Sequence[CandidateCommitInput],
    receipts: Sequence[ReplayReceipt],
) -> tuple[str, ...]:
    challenge_executions: list[tuple[str, str, str]] = []
    for item in candidate_inputs:
        for challenge in item.challenges:
            fingerprint = verified_challenge_fingerprint(challenge)
            challenge_executions.append(
                (
                    challenge.execution_attestation_ref,
                    challenge.execution_fingerprint,
                    fingerprint,
                )
            )
    conflicts: set[str] = set()
    by_nonce: dict[str, ReplayReceipt] = {}
    by_id: dict[tuple[ReplayNamespace, str], ReplayReceipt] = {}
    by_payload: dict[str, ReplayReceipt] = {}
    for receipt in receipts:
        collisions = tuple(
            prior
            for prior in (
                by_nonce.get(receipt.nonce),
                by_id.get((receipt.namespace, receipt.record_id)),
                by_payload.get(receipt.payload_fingerprint),
            )
            if prior is not None and prior != receipt
        )
        for prior in collisions:
            conflicts.add(
                _replay_conflict_fingerprint(
                    "record_collision",
                    prior,
                    receipt,
                )
            )
        by_nonce[receipt.nonce] = receipt
        by_id[(receipt.namespace, receipt.record_id)] = receipt
        by_payload[receipt.payload_fingerprint] = receipt
    by_execution_ref: dict[str, tuple[str, str, str]] = {}
    by_execution_fingerprint: dict[str, tuple[str, str, str]] = {}
    for execution in challenge_executions:
        ref, fingerprint, challenge_fingerprint = execution
        collisions = tuple(
            prior
            for prior in (
                by_execution_ref.get(ref),
                by_execution_fingerprint.get(fingerprint),
            )
            if prior is not None and prior != execution
        )
        for prior in collisions:
            conflicts.add(
                commit_payload_fingerprint(
                    {
                        "conflict_kind": "challenge_execution_reuse",
                        "left": prior,
                        "right": execution,
                    },
                    schema="pheroos-commit-replay-conflict-v1",
                    profile="pheroos-commit-authority-v1",
                )
            )
        by_execution_ref[ref] = execution
        by_execution_fingerprint[fingerprint] = execution
    return tuple(sorted(conflicts))


def _replay_conflict_fingerprint(
    conflict_kind: str,
    left: ReplayReceipt,
    right: ReplayReceipt,
) -> str:
    def payload(receipt: ReplayReceipt) -> tuple[str, str, str, str, str]:
        return (
            receipt.namespace.value,
            receipt.record_id,
            receipt.nonce,
            receipt.payload_fingerprint,
            receipt.candidate_id,
        )

    return commit_payload_fingerprint(
        {
            "conflict_kind": conflict_kind,
            "records": tuple(sorted((payload(left), payload(right)))),
        },
        schema="pheroos-commit-replay-conflict-v1",
        profile="pheroos-commit-authority-v1",
    )


def _issue_commit_assessment(
    *,
    context: CommitEvaluationContext,
    status: CommitAssessmentStatus,
    candidate_metrics: Sequence[CandidateCommitMetrics],
    leader_candidate_id: str,
    tied_candidate_ids: Sequence[str],
    leader_margin: int,
    blocker_references: Sequence[str],
    equivocation_finding_ids: Sequence[str],
    replay_conflict_references: Sequence[str],
    reason_codes: Sequence[str],
    stop_resolution_fingerprint: str,
    permission_fingerprint: str,
    assessment_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    evaluated_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> CommitAssessment:
    metrics = tuple(candidate_metrics)
    collective_evidence_root = _collective_root(
        ((item.candidate_id, item.evidence_root) for item in metrics),
        schema="pheroos-collective-evidence-root-v1",
        profile=context.profile,
    )
    collective_challenge_root = _collective_root(
        ((item.candidate_id, item.challenge_root) for item in metrics),
        schema="pheroos-collective-challenge-root-v1",
        profile=context.profile,
    )
    collective_lease_root = _collective_root(
        ((item.candidate_id, item.lease_root) for item in metrics),
        schema="pheroos-collective-lease-root-v1",
        profile=context.profile,
    )
    leader_metrics = next(
        (item for item in metrics if item.candidate_id == leader_candidate_id),
        None,
    )
    assessment = CommitAssessment(
        assessment_id=require_commit_text(
            assessment_id,
            "commit assessment assessment_id",
        ),
        status=status,
        profile=context.profile,
        assurance=context.assurance,
        context_fingerprint=commit_evaluation_context_fingerprint(context),
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        epoch=context.epoch,
        risk_chain_state_fingerprint=context.risk_chain_state_fingerprint,
        risk_assessment_fingerprint=context.risk_assessment_fingerprint,
        risk_policy_root=context.risk_policy_root,
        threshold_fingerprint=context.threshold_fingerprint,
        membership_snapshot_fingerprint=context.membership_snapshot_fingerprint,
        membership_epoch_state_fingerprint=(
            context.membership_epoch_state_fingerprint
        ),
        membership_root=context.membership_root,
        replay_state_fingerprint=context.replay_state_fingerprint,
        replay_receipt_root=context.replay_receipt_root,
        support_replay_state_fingerprint=(
            context.support_replay_state_fingerprint
        ),
        support_replay_root=context.support_replay_root,
        stop_resolution_fingerprint=stop_resolution_fingerprint,
        permission_fingerprint=permission_fingerprint,
        collective_evidence_root=collective_evidence_root,
        collective_challenge_root=collective_challenge_root,
        collective_lease_root=collective_lease_root,
        candidate_metrics=metrics,
        unique_leader=bool(leader_candidate_id),
        leader_candidate_id=leader_candidate_id,
        tied_candidate_ids=tuple(tied_candidate_ids),
        leader_margin=leader_margin,
        leader_ready_for_stability=bool(
            leader_metrics is not None and leader_metrics.ready_for_stability
        ),
        blocker_references=tuple(blocker_references),
        equivocation_finding_ids=tuple(equivocation_finding_ids),
        replay_conflict_references=tuple(replay_conflict_references),
        reason_codes=tuple(reason_codes),
        issuer_id=require_commit_text(issuer_id, "commit assessment issuer_id"),
        authority=authority,
        evaluated_at_step=evaluated_at_step,
        provenance=require_commit_text(provenance, "commit assessment provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit assessment trace_event_id",
        ),
    )
    object.__setattr__(
        assessment,
        "_issuance",
        (_COMMIT_ASSESSMENT_ISSUANCE, commit_assessment_fingerprint(assessment)),
    )
    return assessment


def _collective_root(
    values: object,
    *,
    schema: str,
    profile: str,
) -> str:
    normalized = tuple(sorted(tuple(values)))
    return commit_payload_fingerprint(
        {"candidate_roots": normalized},
        schema=schema,
        profile=profile,
    )


def _canonical_stop_fingerprint(value: object) -> str:
    if type(value) is not StopResolutionVerification:
        raise CommitEvaluationError(
            CommitReasonCode.STOP_RESOLUTION_UNRESOLVED,
            "commit stop resolution must use the canonical verification record",
        )
    try:
        return stop_resolution_verification_fingerprint(value)
    except GovernanceError as exc:
        raise CommitEvaluationError(
            CommitReasonCode.STOP_RESOLUTION_UNRESOLVED,
            f"commit stop resolution is malformed: {exc}",
        ) from exc


def _canonical_permission_fingerprint(value: object) -> str:
    if type(value) is not ActionPermission:
        raise CommitEvaluationError(
            CommitReasonCode.COMMIT_PERMISSION_UNRESOLVED,
            "commit permission must use the canonical permission record",
        )
    try:
        return action_permission_fingerprint(value)
    except GovernanceError as exc:
        raise CommitEvaluationError(
            CommitReasonCode.COMMIT_PERMISSION_UNRESOLVED,
            f"commit permission is malformed: {exc}",
        ) from exc


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
    issued = require_commit_step(context.issued_at_step, "commit context issued_at_step")
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


def _validate_candidate_commit_metrics(metrics: CandidateCommitMetrics) -> None:
    require_commit_text(metrics.candidate_id, "candidate metrics candidate_id")
    for name in (
        "claim_fingerprint",
        "evidence_binding_fingerprint",
        "evidence_summary_fingerprint",
        "positive_root",
        "counter_root",
        "disposition_root",
        "evidence_root",
        "challenge_root",
        "challenge_coverage_fingerprint",
        "lease_root",
        "support_replay_scope_root",
    ):
        require_commit_fingerprint(getattr(metrics, name), f"candidate metrics {name}")
    for name in (
        "positive_evidence",
        "counterevidence",
        "weighted_counterevidence",
        "net_evidence",
        "counterevidence_ratio_ppm",
        "active_support_clusters",
        "eligible_support_clusters",
        "support_threshold_clusters",
        "support_ratio_ppm",
        "source_diversity",
        "margin",
    ):
        require_authority_integer(
            getattr(metrics, name),
            f"candidate metrics {name}",
            allow_negative=name in {"net_evidence", "margin"},
        )
    if metrics.counterevidence_ratio_ppm > WEIGHT_SCALE or metrics.support_ratio_ppm > WEIGHT_SCALE:
        raise GovernanceError("candidate metrics ratio exceeds the fixed-point scale")
    object.__setattr__(
        metrics,
        "missing_challenge_categories",
        require_commit_labels(
            metrics.missing_challenge_categories,
            "candidate metrics missing challenge categories",
            allow_empty=True,
        ),
    )
    object.__setattr__(
        metrics,
        "reason_codes",
        require_commit_labels(
            metrics.reason_codes,
            "candidate metrics reason codes",
            allow_empty=True,
        ),
    )
    for name in (
        "blocker_references",
        "equivocation_finding_ids",
        "replay_conflict_references",
    ):
        object.__setattr__(
            metrics,
            name,
            _canonical_fingerprints(
                getattr(metrics, name),
                f"candidate metrics {name}",
                allow_empty=True,
            ),
        )
    gates = (
        "roots_valid",
        "positive_threshold_satisfied",
        "counter_limit_satisfied",
        "counter_ratio_satisfied",
        "critical_counterevidence_clear",
        "challenge_coverage_satisfied",
        "support_cluster_satisfied",
        "support_ratio_satisfied",
        "source_diversity_satisfied",
        "minimum_assurance_satisfied",
        "margin_satisfied",
        "unique_leader",
        "stop_resolution_satisfied",
        "commit_permission_satisfied",
        "replay_clear",
        "equivocation_clear",
    )
    for name in (*gates, "ready_for_stability"):
        require_commit_bool(getattr(metrics, name), f"candidate metrics {name}")
    expected_ready = all(getattr(metrics, name) for name in gates)
    if metrics.ready_for_stability is not expected_ready:
        raise GovernanceError("candidate metrics ready gate is inconsistent")
    expected_threshold = max(
        0,
        metrics.support_threshold_clusters,
    )
    if (
        metrics.support_cluster_satisfied and metrics.support_ratio_satisfied
    ) is not (metrics.active_support_clusters >= expected_threshold):
        # The combined threshold is max(cluster floor, ceil(ratio * eligible)).
        raise GovernanceError("candidate metrics support threshold is inconsistent")


def _validate_commit_assessment_shape(assessment: CommitAssessment) -> None:
    if type(assessment.status) is not CommitAssessmentStatus:
        raise GovernanceError("commit assessment status is invalid")
    profile = require_commit_profile(assessment.profile, "commit assessment profile")
    assurance = require_commit_assurance(
        assessment.assurance,
        "commit assessment assurance",
    )
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("commit assessment profile/assurance mismatch")
    for name in (
        "assessment_id",
        "protocol_id",
        "run_id",
        "target",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(assessment, name), f"commit assessment {name}")
    for name in (
        "context_fingerprint",
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
        "stop_resolution_fingerprint",
        "permission_fingerprint",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
    ):
        require_commit_fingerprint(
            getattr(assessment, name),
            f"commit assessment {name}",
        )
    require_commit_step(assessment.epoch, "commit assessment epoch")
    require_commit_step(
        assessment.evaluated_at_step,
        "commit assessment evaluated_at_step",
    )
    require_authority_integer(
        assessment.leader_margin,
        "commit assessment leader_margin",
        allow_negative=True,
    )
    for name in ("unique_leader", "leader_ready_for_stability"):
        require_commit_bool(getattr(assessment, name), f"commit assessment {name}")
    if type(assessment.authority) is not AuthorityLevel or not can_verify(
        assessment.authority
    ):
        raise GovernanceError("commit assessment authority is invalid")
    expected_roots = _rebuild_collective_assessment_roots(
        assessment.candidate_metrics,
        profile=assessment.profile,
    )
    if any(getattr(assessment, name) != value for name, value in expected_roots.items()):
        raise GovernanceError("commit assessment collective roots are inconsistent")
    if assessment.candidate_metrics:
        scores = {
            item.candidate_id: item.net_evidence
            for item in assessment.candidate_metrics
        }
        maximum = max(scores.values())
        maxima = tuple(
            sorted(
                candidate_id
                for candidate_id, score in scores.items()
                if score == maximum
            )
        )
        expected_leader = maxima[0] if len(maxima) == 1 else ""
        for metrics in assessment.candidate_metrics:
            other_best = max(
                (
                    score
                    for candidate_id, score in scores.items()
                    if candidate_id != metrics.candidate_id
                ),
                default=0,
            )
            expected_margin = metrics.net_evidence - max(other_best, 0)
            if metrics.margin != expected_margin:
                raise GovernanceError("commit assessment candidate margin is inconsistent")
            if metrics.unique_leader is not (
                metrics.candidate_id == expected_leader
            ):
                raise GovernanceError("commit assessment candidate leader gate is inconsistent")
        if assessment.leader_candidate_id != expected_leader:
            raise GovernanceError("commit assessment unique argmax is inconsistent")
        expected_ties = () if expected_leader else maxima
        if set(assessment.tied_candidate_ids) != set(expected_ties):
            raise GovernanceError("commit assessment tie lineage is inconsistent")
    elif assessment.leader_candidate_id or assessment.tied_candidate_ids:
        raise GovernanceError("empty commit assessment cannot identify candidates")
    leader_metrics = tuple(
        item
        for item in assessment.candidate_metrics
        if item.candidate_id == assessment.leader_candidate_id
    )
    if assessment.unique_leader:
        require_commit_text(
            assessment.leader_candidate_id,
            "commit assessment leader_candidate_id",
        )
        if len(leader_metrics) != 1 or assessment.tied_candidate_ids:
            raise GovernanceError("commit assessment leader lineage is inconsistent")
        if assessment.leader_margin != leader_metrics[0].margin:
            raise GovernanceError("commit assessment leader margin is inconsistent")
    elif assessment.leader_candidate_id:
        raise GovernanceError("non-unique assessment cannot identify a leader")
    elif assessment.leader_margin != 0:
        raise GovernanceError("assessment without a leader must have zero leader margin")
    if assessment.leader_ready_for_stability is not bool(
        leader_metrics and leader_metrics[0].ready_for_stability
    ):
        raise GovernanceError("commit assessment leader ready state is inconsistent")
    if assessment.status is CommitAssessmentStatus.READY and not (
        assessment.unique_leader and assessment.leader_ready_for_stability
    ):
        raise GovernanceError("ready assessment requires one fully gated leader")
    if assessment.status is CommitAssessmentStatus.SAFETY_VIOLATION and not (
        assessment.equivocation_finding_ids
        or assessment.replay_conflict_references
    ):
        raise GovernanceError("safety assessment requires a concrete safety finding")


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


def _rebuild_collective_assessment_roots(
    metrics: Sequence[CandidateCommitMetrics],
    *,
    profile: str,
) -> dict[str, str]:
    values = tuple(metrics)
    return {
        "collective_evidence_root": _collective_root(
            ((item.candidate_id, item.evidence_root) for item in values),
            schema="pheroos-collective-evidence-root-v1",
            profile=profile,
        ),
        "collective_challenge_root": _collective_root(
            ((item.candidate_id, item.challenge_root) for item in values),
            schema="pheroos-collective-challenge-root-v1",
            profile=profile,
        ),
        "collective_lease_root": _collective_root(
            ((item.candidate_id, item.lease_root) for item in values),
            schema="pheroos-collective-lease-root-v1",
            profile=profile,
        ),
    }


def _canonical_records(
    values: Sequence[object],
    expected_type: type,
    fingerprint,
    label: str,
) -> tuple[object, ...]:
    records = tuple(values)
    if any(type(item) is not expected_type for item in records):
        raise GovernanceError(f"candidate commit input {label} is not canonical")
    return tuple(sorted(records, key=fingerprint))


def _canonical_metrics(
    metrics: Sequence[CandidateCommitMetrics],
) -> tuple[CandidateCommitMetrics, ...]:
    values = tuple(metrics)
    if any(type(item) is not CandidateCommitMetrics for item in values):
        raise GovernanceError("commit assessment metrics are not canonical")
    normalized = tuple(sorted(values, key=lambda item: item.candidate_id))
    ids = tuple(item.candidate_id for item in normalized)
    if len(ids) != len(set(ids)):
        raise GovernanceError("commit assessment metrics contain duplicate candidates")
    return normalized


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        normalized.append(require_commit_fingerprint(value, field_name))
    if not normalized and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise GovernanceError(f"{field_name} contains duplicate fingerprints")
    return tuple(canonical_commit_set(normalized))


__all__ = [
    "CandidateClaimBinding",
    "CandidateCommitInput",
    "CandidateCommitMetrics",
    "CommitAssessment",
    "CommitAssessmentStatus",
    "CommitEvaluationContext",
    "CommitEvaluationError",
    "CommitEvaluationFailureKind",
    "CommitReasonCode",
    "assess_optimal_commit",
    "build_commit_replay_receipts",
    "candidate_commit_metrics_fingerprint",
    "candidate_commit_metrics_payload",
    "commit_assessment_fingerprint",
    "commit_assessment_is_authoritative",
    "commit_assessment_payload",
    "commit_evaluation_context_fingerprint",
    "commit_evaluation_context_is_authoritative",
    "commit_evaluation_context_payload",
    "issue_commit_evaluation_context",
    "rebuild_commit_assessment_roots",
]
