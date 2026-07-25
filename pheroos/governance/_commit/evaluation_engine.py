"""Ordered execution engine for optimal commit assessment."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pheroos.governance._commit.assessment import CommitAssessment
from pheroos.governance._commit.context import (
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
)
from pheroos.governance._commit.evaluation_metrics import (
    ActionGateBindings,
    AssessmentIssuance,
    build_candidate_metrics,
    build_selection_state,
    issue_conflict_assessment,
    issue_selected_assessment,
)
from pheroos.governance._commit.invariants import (
    _canonical_permission_fingerprint,
    _canonical_stop_fingerprint,
    _require_authoritative_heads,
)
from pheroos.governance._commit.records import (
    CandidateCommitInput,
    CommitEvaluationContext,
    CommitEvaluationError,
    CommitReasonCode,
)
from pheroos.governance._commit.replay import (
    _cross_record_replay_conflicts,
    _scoped_commit_input_receipts,
    build_commit_replay_receipts,
)
from pheroos.governance._commit_state.records import (
    CommitReplayState,
    ReplayReceipt,
    commit_replay_state_fingerprint,
)
from pheroos.governance._commit_validation import require_commit_step
from pheroos.governance._risk.payloads import (
    commit_threshold_snapshot_fingerprint,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance._risk.records import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
)
from pheroos.governance._support.evaluation import evaluate_support_leases
from pheroos.governance._support.lease import support_lease_is_authoritative
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseEvaluation,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    support_lease_replay_state_fingerprint,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.challenge import (
    ChallengeCoverage,
    evaluate_challenge_coverage,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.evidence_binding import (
    EvidenceSummary,
    evidence_binding_is_authoritative,
    evaluate_evidence_binding,
)
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_matches,
)
from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_matches,
)
from pheroos.protocol.commit_models import CommitAction, CollectiveCommitPolicy
from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
)
from pheroos.protocol.models import CapabilityManifest
from pheroos.protocol.validation import validate_capability_manifest


@dataclass(frozen=True)
class CommitEvaluationRequest:
    context: CommitEvaluationContext
    manifest: CapabilityManifest
    candidate_inputs: Sequence[CandidateCommitInput]
    leases: Sequence[SupportLease]
    revocations: Sequence[SupportLeaseRevocation]
    risk_chain_state: RiskAssessmentChainState
    risk_assessment: RiskAssessment
    threshold_snapshot: CommitThresholdSnapshot
    membership_snapshot: EligiblePrincipalSnapshot
    membership_epoch_state: EligibleMembershipEpochState
    replay_state: CommitReplayState
    support_replay_state: SupportLeaseReplayState
    stop_resolution: StopResolutionVerification
    commit_permission: ActionPermission
    assessment_id: str
    issuer_id: str
    authority: AuthorityLevel
    current_step: int
    provenance: str
    trace_event_id: str


@dataclass(frozen=True)
class CandidateEvaluations:
    summaries: dict[str, EvidenceSummary]
    support: dict[str, SupportLeaseEvaluation]
    challenge_coverage: dict[str, ChallengeCoverage]


def assess_optimal_commit_impl(request: CommitEvaluationRequest) -> CommitAssessment:
    current = _validate_initial_request(request)
    policy = _validate_manifest_binding(request)
    _validate_authority_heads(request, policy=policy, current=current)
    inputs = _validate_candidate_inputs(request.context, request.candidate_inputs)
    leases, revocations = _validate_support_inputs(request)
    gates = _action_gate_bindings(request, current=current)
    conflicts = _validate_replay_inputs(
        request,
        inputs=inputs,
        leases=leases,
        revocations=revocations,
    )
    if conflicts:
        return _conflict_assessment(request, conflicts, gates, current=current)
    evaluations = _evaluate_candidates(
        request,
        policy=policy,
        inputs=inputs,
        leases=leases,
        revocations=revocations,
        current=current,
    )
    selection = build_selection_state(
        request.context,
        summaries=evaluations.summaries,
        support=evaluations.support,
        threshold_snapshot=request.threshold_snapshot,
        gates=gates,
    )
    metrics = build_candidate_metrics(
        request.context,
        inputs=inputs,
        summaries=evaluations.summaries,
        support=evaluations.support,
        coverage=evaluations.challenge_coverage,
        threshold_snapshot=request.threshold_snapshot,
        gates=gates,
        selection=selection,
    )
    return issue_selected_assessment(
        request.context,
        metrics=metrics,
        selection=selection,
        gates=gates,
        issuance=_assessment_issuance(request, current=current),
    )


def _validate_initial_request(request: CommitEvaluationRequest) -> int:
    current = require_commit_step(
        request.current_step,
        "optimal commit current_step",
    )
    context = request.context
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
    if type(request.authority) is not AuthorityLevel or not can_verify(
        request.authority
    ):
        raise CommitEvaluationError(
            CommitReasonCode.INVALID_CONTEXT,
            "optimal commit assessment requires governance authority",
        )
    return current


def _validate_manifest_binding(
    request: CommitEvaluationRequest,
) -> CollectiveCommitPolicy:
    manifest = request.manifest
    context = request.context
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
    _validate_manifest_roots(context, manifest=manifest, policy=policy)
    return policy


def _validate_manifest_roots(
    context: CommitEvaluationContext,
    *,
    manifest: CapabilityManifest,
    policy: CollectiveCommitPolicy,
) -> None:
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


def _validate_authority_heads(
    request: CommitEvaluationRequest,
    *,
    policy: CollectiveCommitPolicy,
    current: int,
) -> None:
    context = request.context
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
        risk_chain_state=request.risk_chain_state,
        risk_assessment=request.risk_assessment,
        threshold_snapshot=request.threshold_snapshot,
        membership_snapshot=request.membership_snapshot,
        membership_epoch_state=request.membership_epoch_state,
        replay_state=request.replay_state,
        support_replay_state=request.support_replay_state,
        current_step=current,
    )
    _require_context_head_fingerprints(request)


def _require_context_head_fingerprints(request: CommitEvaluationRequest) -> None:
    observed = _observed_context_heads(request)
    for name, value in observed.items():
        if getattr(request.context, name) != value:
            raise CommitEvaluationError(
                _context_head_reason(name),
                f"commit context authority head changed: {name}",
            )


def _observed_context_heads(request: CommitEvaluationRequest) -> dict[str, str]:
    return {
        "risk_chain_state_fingerprint": risk_assessment_chain_state_fingerprint(
            request.risk_chain_state
        ),
        "risk_assessment_fingerprint": risk_assessment_fingerprint(
            request.risk_assessment
        ),
        "threshold_fingerprint": commit_threshold_snapshot_fingerprint(
            request.threshold_snapshot
        ),
        "membership_snapshot_fingerprint": eligible_principal_snapshot_fingerprint(
            request.membership_snapshot
        ),
        "membership_epoch_state_fingerprint": (
            eligible_membership_epoch_state_fingerprint(request.membership_epoch_state)
        ),
        "membership_root": request.membership_snapshot.membership_root,
        "replay_state_fingerprint": commit_replay_state_fingerprint(
            request.replay_state
        ),
        "replay_receipt_root": request.replay_state.receipt_root,
        "support_replay_state_fingerprint": (
            support_lease_replay_state_fingerprint(request.support_replay_state)
        ),
        "support_replay_root": request.support_replay_state.replay_root,
    }


def _context_head_reason(name: str) -> CommitReasonCode:
    if name.startswith("replay_"):
        return CommitReasonCode.REPLAY_HEAD_MISMATCH
    if name.startswith("support_replay_"):
        return CommitReasonCode.SUPPORT_REPLAY_HEAD_MISMATCH
    if name.startswith("membership_"):
        return CommitReasonCode.MEMBERSHIP_HEAD_MISMATCH
    if name.startswith("threshold_"):
        return CommitReasonCode.THRESHOLD_MISMATCH
    return CommitReasonCode.RISK_HEAD_MISMATCH


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
    _validate_candidate_claim_consistency(inputs)
    observed_ids = tuple(item.candidate_id for item in inputs)
    if len(observed_ids) != len(set(observed_ids)) or set(observed_ids) != set(
        context.substantive_candidate_ids
    ):
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "candidate inputs must cover every substantive candidate exactly once",
        )
    _validate_candidate_context_claims(context, inputs)
    return tuple(sorted(inputs, key=lambda item: item.candidate_id))


def _validate_candidate_claim_consistency(
    inputs: Sequence[CandidateCommitInput],
) -> None:
    claims_seen: dict[str, str] = {}
    for item in inputs:
        prior = claims_seen.setdefault(item.candidate_id, item.claim_fingerprint)
        if prior != item.claim_fingerprint:
            raise CommitEvaluationError(
                CommitReasonCode.CANDIDATE_CLAIM_CONFLICT,
                "one candidate is bound to multiple claims in one assessment",
            )


def _validate_candidate_context_claims(
    context: CommitEvaluationContext,
    inputs: Sequence[CandidateCommitInput],
) -> None:
    expected_claims = {
        item.candidate_id: item.claim_fingerprint for item in context.candidate_claims
    }
    for item in inputs:
        if expected_claims[item.candidate_id] != item.claim_fingerprint:
            raise CommitEvaluationError(
                CommitReasonCode.CANDIDATE_CLAIM_MISMATCH,
                f"candidate {item.candidate_id} claim does not match the context",
            )


def _validate_support_inputs(
    request: CommitEvaluationRequest,
) -> tuple[tuple[SupportLease, ...], tuple[SupportLeaseRevocation, ...]]:
    leases = tuple(request.leases)
    revocations = tuple(request.revocations)
    declared_claims = {
        item.candidate_id: item.claim_fingerprint
        for item in request.context.candidate_claims
    }
    for lease in leases:
        _validate_lease(request.context, lease, declared_claims)
    for revocation in revocations:
        if type(revocation) is not SupportLeaseRevocation:
            raise CommitEvaluationError(
                CommitReasonCode.SUPPORT_EVALUATION_INVALID,
                "optimal commit revocation set contains a non-canonical record",
            )
    return leases, revocations


def _validate_lease(
    context: CommitEvaluationContext,
    lease: SupportLease,
    declared_claims: dict[str, str],
) -> None:
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
    if not _lease_scope_matches(context, lease):
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
            "optimal commit lease references a hidden or unbound candidate scope",
        )
    if declared_claims[lease.candidate_id] != lease.claim_fingerprint:
        raise CommitEvaluationError(
            CommitReasonCode.CANDIDATE_CLAIM_MISMATCH,
            "optimal commit lease claim does not match the evaluation context",
        )


def _lease_scope_matches(
    context: CommitEvaluationContext,
    lease: SupportLease,
) -> bool:
    return all(
        (
            lease.profile == context.profile,
            lease.assurance is context.assurance,
            lease.manifest_root == context.manifest_root,
            lease.commit_policy_root == context.commit_policy_root,
            lease.protocol_id == context.protocol_id,
            lease.run_id == context.run_id,
            lease.target == context.target,
            lease.epoch == context.epoch,
            lease.candidate_id in context.substantive_candidate_ids,
        )
    )


def _action_gate_bindings(
    request: CommitEvaluationRequest,
    *,
    current: int,
) -> ActionGateBindings:
    context = request.context
    stop_root = _canonical_stop_fingerprint(request.stop_resolution)
    permission_root = _canonical_permission_fingerprint(request.commit_permission)
    context_ref = commit_evaluation_context_fingerprint(context)
    stop_bound = stop_resolution_verification_matches(
        request.stop_resolution,
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
        request.commit_permission,
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
    return ActionGateBindings(
        stop_root=stop_root,
        permission_root=permission_root,
        stop_bound=stop_bound,
        permission_bound=permission_bound,
        stop_resolution=request.stop_resolution,
        commit_permission=request.commit_permission,
    )


def _validate_replay_inputs(
    request: CommitEvaluationRequest,
    *,
    inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation],
) -> tuple[str, ...]:
    try:
        receipts = build_commit_replay_receipts(inputs, leases, revocations)
    except GovernanceError as exc:
        raise CommitEvaluationError(
            CommitReasonCode.REPLAY_COVERAGE_MISMATCH,
            f"commit replay inputs cannot be projected canonically: {exc}",
        ) from exc
    recorded = _scoped_commit_input_receipts(
        request.context,
        request.replay_state.receipts,
    )
    supplied = _scoped_commit_input_receipts(request.context, receipts)
    conflicts = _cross_record_replay_conflicts(inputs, (*recorded, *supplied))
    if not conflicts:
        _require_replay_coverage(recorded, supplied)
    return conflicts


def _require_replay_coverage(
    recorded: Sequence[ReplayReceipt],
    supplied: Sequence[ReplayReceipt],
) -> None:
    recorded_set = set(recorded)
    supplied_set = set(supplied)
    if recorded_set != supplied_set:
        mismatched = recorded_set.symmetric_difference(supplied_set)
        raise CommitEvaluationError(
            CommitReasonCode.REPLAY_COVERAGE_MISMATCH,
            "authoritative replay head and supplied scoped inputs differ",
            references=tuple(sorted(item.payload_fingerprint for item in mismatched)),
        )


def _conflict_assessment(
    request: CommitEvaluationRequest,
    conflicts: Sequence[str],
    gates: ActionGateBindings,
    *,
    current: int,
) -> CommitAssessment:
    return issue_conflict_assessment(
        request.context,
        replay_conflicts=conflicts,
        gates=gates,
        issuance=_assessment_issuance(request, current=current),
    )


def _assessment_issuance(
    request: CommitEvaluationRequest,
    *,
    current: int,
) -> AssessmentIssuance:
    return AssessmentIssuance(
        assessment_id=request.assessment_id,
        issuer_id=request.issuer_id,
        authority=request.authority,
        evaluated_at_step=current,
        provenance=request.provenance,
        trace_event_id=request.trace_event_id,
    )


def _evaluate_candidates(
    request: CommitEvaluationRequest,
    *,
    policy: CollectiveCommitPolicy,
    inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation],
    current: int,
) -> CandidateEvaluations:
    summaries: dict[str, EvidenceSummary] = {}
    support: dict[str, SupportLeaseEvaluation] = {}
    coverage: dict[str, ChallengeCoverage] = {}
    for item in inputs:
        summary, candidate_coverage, support_evaluation = _evaluate_candidate(
            request,
            policy=policy,
            item=item,
            leases=leases,
            revocations=revocations,
            current=current,
        )
        summaries[item.candidate_id] = summary
        coverage[item.candidate_id] = candidate_coverage
        support[item.candidate_id] = support_evaluation
    return CandidateEvaluations(summaries, support, coverage)


def _evaluate_candidate(
    request: CommitEvaluationRequest,
    *,
    policy: CollectiveCommitPolicy,
    item: CandidateCommitInput,
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation],
    current: int,
) -> tuple[EvidenceSummary, ChallengeCoverage, SupportLeaseEvaluation]:
    if not evidence_binding_is_authoritative(item.evidence_binding):
        raise CommitEvaluationError(
            CommitReasonCode.EVIDENCE_BINDING_INVALID,
            f"candidate {item.candidate_id} evidence binding is not authoritative",
        )
    if not _evidence_binding_matches(request.context, item):
        raise CommitEvaluationError(
            CommitReasonCode.EVIDENCE_BINDING_INVALID,
            f"candidate {item.candidate_id} evidence binding has a root or scope mismatch",
        )
    summary, coverage = _evaluate_evidence(
        request,
        policy=policy,
        item=item,
        current=current,
    )
    support = _evaluate_support(
        request,
        policy=policy,
        item=item,
        leases=leases,
        revocations=revocations,
        current=current,
    )
    return summary, coverage, support


def _evidence_binding_matches(
    context: CommitEvaluationContext,
    item: CandidateCommitInput,
) -> bool:
    binding = item.evidence_binding
    return all(
        (
            binding.profile == context.profile,
            binding.assurance is context.assurance,
            binding.manifest_root == context.manifest_root,
            binding.commit_policy_root == context.commit_policy_root,
            binding.protocol_id == context.protocol_id,
            binding.run_id == context.run_id,
            binding.target == context.target,
            binding.epoch == context.epoch,
            binding.candidate_id == item.candidate_id,
            binding.claim_fingerprint == item.claim_fingerprint,
        )
    )


def _evaluate_evidence(
    request: CommitEvaluationRequest,
    *,
    policy: CollectiveCommitPolicy,
    item: CandidateCommitInput,
    current: int,
) -> tuple[EvidenceSummary, ChallengeCoverage]:
    context = request.context
    try:
        summary = evaluate_evidence_binding(
            item.evidence_binding,
            positive_observations=item.positive_observations,
            counter_observations=item.counter_observations,
            dispositions=item.dispositions,
            challenges=item.challenges,
            evidence_policy=policy.evidence_qualification,
            current_step=current,
        )
        coverage = evaluate_challenge_coverage(
            item.challenges,
            required_categories=(
                request.threshold_snapshot.required_challenge_categories
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
        return summary, coverage
    except GovernanceError as exc:
        raise CommitEvaluationError(
            CommitReasonCode.EVIDENCE_EVALUATION_INVALID,
            f"candidate {item.candidate_id} evidence cannot be reconstructed: {exc}",
        ) from exc


def _evaluate_support(
    request: CommitEvaluationRequest,
    *,
    policy: CollectiveCommitPolicy,
    item: CandidateCommitInput,
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation],
    current: int,
) -> SupportLeaseEvaluation:
    try:
        return evaluate_support_leases(
            leases,
            revocations=revocations,
            membership_snapshot=request.membership_snapshot,
            membership_epoch_state=request.membership_epoch_state,
            replay_state=request.support_replay_state,
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


__all__: list[str] = []
