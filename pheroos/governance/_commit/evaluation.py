from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._commit.assessment import (
    CandidateCommitMetrics,
    CommitAssessment,
    CommitAssessmentStatus,
    mark_commit_assessment_authoritative,
)
from pheroos.governance._commit.context import (
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
)
from pheroos.governance._commit.invariants import (
    _canonical_permission_fingerprint,
    _canonical_stop_fingerprint,
    _collective_root,
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
    commit_replay_state_fingerprint,
)
from pheroos.governance._commit_validation import (
    require_commit_step,
    require_commit_text,
)
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
    challenge_coverage_fingerprint,
    evaluate_challenge_coverage,
)
from pheroos.governance.commit_numeric import ceil_scaled_count
from pheroos.governance.errors import GovernanceError
from pheroos.governance.evidence_binding import (
    EvidenceSummary,
    evidence_binding_fingerprint,
    evidence_binding_is_authoritative,
    evidence_summary_fingerprint,
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
from pheroos.protocol.commit_models import (
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


_ASSURANCE_RANK = {
    CommitAssurance.ADVISORY: 0,
    CommitAssurance.EVIDENCE_BOUND: 1,
    CommitAssurance.CERTIFIED: 2,
    CommitAssurance.DISTRIBUTED: 3,
}


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
    return mark_commit_assessment_authoritative(assessment)

assess_optimal_commit.__module__ = "pheroos.governance.commit"
