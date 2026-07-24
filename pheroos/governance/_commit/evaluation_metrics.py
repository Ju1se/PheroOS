"""Deterministic candidate metrics and assessment assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pheroos.governance._commit.assessment import (
    CandidateCommitMetrics,
    CommitAssessment,
    CommitAssessmentStatus,
    mark_commit_assessment_authoritative,
)
from pheroos.governance._commit.context import (
    commit_evaluation_context_fingerprint,
)
from pheroos.governance._commit.invariants import _collective_root
from pheroos.governance._commit.records import (
    CandidateCommitInput,
    CommitEvaluationContext,
    CommitReasonCode,
)
from pheroos.governance._commit_validation import require_commit_text
from pheroos.governance._support.records import SupportLeaseEvaluation
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.challenge import (
    ChallengeCoverage,
    challenge_coverage_fingerprint,
)
from pheroos.governance.commit_numeric import ceil_scaled_count
from pheroos.governance.evidence_binding import (
    EvidenceSummary,
    evidence_binding_fingerprint,
    evidence_summary_fingerprint,
)
from pheroos.governance.permission import ActionPermission
from pheroos.governance.stop_signal import StopResolutionVerification
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.governance._risk.records import CommitThresholdSnapshot


_ASSURANCE_RANK = {
    CommitAssurance.ADVISORY: 0,
    CommitAssurance.EVIDENCE_BOUND: 1,
    CommitAssurance.CERTIFIED: 2,
    CommitAssurance.DISTRIBUTED: 3,
}


@dataclass(frozen=True)
class ActionGateBindings:
    stop_root: str
    permission_root: str
    stop_bound: bool
    permission_bound: bool
    stop_resolution: StopResolutionVerification
    commit_permission: ActionPermission


@dataclass(frozen=True)
class SelectionState:
    scores: Mapping[str, int]
    tied_candidate_ids: tuple[str, ...]
    unique_leader_id: str
    assurance_satisfied: bool
    stop_satisfied: bool
    permission_satisfied: bool
    equivocation_finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateGateState:
    margin: int
    support_threshold_clusters: int
    positive_satisfied: bool
    counter_satisfied: bool
    ratio_satisfied: bool
    critical_satisfied: bool
    challenge_satisfied: bool
    support_cluster_satisfied: bool
    support_ratio_satisfied: bool
    diversity_satisfied: bool
    margin_satisfied: bool
    unique_leader: bool
    equivocation_finding_ids: tuple[str, ...]
    equivocation_clear: bool


@dataclass(frozen=True)
class AssessmentIssuance:
    assessment_id: str
    issuer_id: str
    authority: AuthorityLevel
    evaluated_at_step: int
    provenance: str
    trace_event_id: str


def build_selection_state(
    context: CommitEvaluationContext,
    *,
    summaries: Mapping[str, EvidenceSummary],
    support: Mapping[str, SupportLeaseEvaluation],
    threshold_snapshot: CommitThresholdSnapshot,
    gates: ActionGateBindings,
) -> SelectionState:
    scores = {
        candidate_id: summary.net_evidence
        for candidate_id, summary in summaries.items()
    }
    maximum = max(scores.values())
    tied_ids = tuple(
        sorted(
            candidate_id for candidate_id, score in scores.items() if score == maximum
        )
    )
    findings = tuple(
        sorted(
            {
                finding.finding_id
                for evaluation in support.values()
                for finding in evaluation.equivocation_findings
            }
        )
    )
    return SelectionState(
        scores=scores,
        tied_candidate_ids=tied_ids,
        unique_leader_id=tied_ids[0] if len(tied_ids) == 1 else "",
        assurance_satisfied=(
            _ASSURANCE_RANK[context.assurance]
            >= _ASSURANCE_RANK[threshold_snapshot.minimum_assurance]
        ),
        stop_satisfied=bool(gates.stop_bound and not gates.stop_resolution.blocked),
        permission_satisfied=bool(
            gates.permission_bound and gates.commit_permission.allowed
        ),
        equivocation_finding_ids=findings,
    )


def build_candidate_metrics(
    context: CommitEvaluationContext,
    *,
    inputs: Sequence[CandidateCommitInput],
    summaries: Mapping[str, EvidenceSummary],
    support: Mapping[str, SupportLeaseEvaluation],
    coverage: Mapping[str, ChallengeCoverage],
    threshold_snapshot: CommitThresholdSnapshot,
    gates: ActionGateBindings,
    selection: SelectionState,
) -> tuple[CandidateCommitMetrics, ...]:
    return tuple(
        _candidate_metrics(
            context,
            item=item,
            summary=summaries[item.candidate_id],
            support_evaluation=support[item.candidate_id],
            coverage=coverage[item.candidate_id],
            threshold_snapshot=threshold_snapshot,
            gates=gates,
            selection=selection,
        )
        for item in inputs
    )


def _candidate_metrics(
    context: CommitEvaluationContext,
    *,
    item: CandidateCommitInput,
    summary: EvidenceSummary,
    support_evaluation: SupportLeaseEvaluation,
    coverage: ChallengeCoverage,
    threshold_snapshot: CommitThresholdSnapshot,
    gates: ActionGateBindings,
    selection: SelectionState,
) -> CandidateCommitMetrics:
    state = _candidate_gate_state(
        item=item,
        summary=summary,
        support_evaluation=support_evaluation,
        coverage=coverage,
        threshold_snapshot=threshold_snapshot,
        selection=selection,
    )
    reasons = _candidate_reason_codes(state, gates, selection)
    blockers = _candidate_blockers(state, summary, gates)
    ready = _candidate_is_ready(state, selection)
    return CandidateCommitMetrics(
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
        support_replay_scope_root=support_evaluation.support_replay_scope_root,
        positive_evidence=summary.positive_evidence,
        counterevidence=summary.counterevidence,
        weighted_counterevidence=summary.weighted_counterevidence,
        net_evidence=summary.net_evidence,
        counterevidence_ratio_ppm=summary.counterevidence_ratio_ppm,
        active_support_clusters=support_evaluation.active_support_cluster_count,
        eligible_support_clusters=support_evaluation.eligible_cluster_count,
        support_threshold_clusters=state.support_threshold_clusters,
        support_ratio_ppm=support_evaluation.support_ratio_ppm,
        source_diversity=summary.source_diversity,
        margin=state.margin,
        missing_challenge_categories=coverage.missing_categories,
        blocker_references=blockers,
        equivocation_finding_ids=state.equivocation_finding_ids,
        replay_conflict_references=(),
        roots_valid=True,
        positive_threshold_satisfied=state.positive_satisfied,
        counter_limit_satisfied=state.counter_satisfied,
        counter_ratio_satisfied=state.ratio_satisfied,
        critical_counterevidence_clear=state.critical_satisfied,
        challenge_coverage_satisfied=state.challenge_satisfied,
        support_cluster_satisfied=state.support_cluster_satisfied,
        support_ratio_satisfied=state.support_ratio_satisfied,
        source_diversity_satisfied=state.diversity_satisfied,
        minimum_assurance_satisfied=selection.assurance_satisfied,
        margin_satisfied=state.margin_satisfied,
        unique_leader=state.unique_leader,
        stop_resolution_satisfied=selection.stop_satisfied,
        commit_permission_satisfied=selection.permission_satisfied,
        replay_clear=True,
        equivocation_clear=state.equivocation_clear,
        ready_for_stability=ready,
        reason_codes=reasons,
    )


def _candidate_gate_state(
    *,
    item: CandidateCommitInput,
    summary: EvidenceSummary,
    support_evaluation: SupportLeaseEvaluation,
    coverage: ChallengeCoverage,
    threshold_snapshot: CommitThresholdSnapshot,
    selection: SelectionState,
) -> CandidateGateState:
    other_best = max(
        (
            score
            for candidate_id, score in selection.scores.items()
            if candidate_id != item.candidate_id
        ),
        default=0,
    )
    margin = summary.net_evidence - max(other_best, 0)
    threshold_clusters = max(
        threshold_snapshot.minimum_support_clusters,
        ceil_scaled_count(
            support_evaluation.eligible_cluster_count,
            threshold_snapshot.minimum_support_ratio_ppm,
        ),
    )
    equivocation_ids = tuple(
        finding.finding_id for finding in support_evaluation.equivocation_findings
    )
    return CandidateGateState(
        margin=margin,
        support_threshold_clusters=threshold_clusters,
        positive_satisfied=(
            summary.positive_evidence >= threshold_snapshot.minimum_positive_evidence
        ),
        counter_satisfied=(
            summary.counterevidence <= threshold_snapshot.maximum_counterevidence
        ),
        ratio_satisfied=(
            summary.counterevidence_ratio_ppm
            <= threshold_snapshot.maximum_counterevidence_ratio_ppm
        ),
        critical_satisfied=(
            not summary.blocking_critical_counter_observation_fingerprints
        ),
        challenge_satisfied=coverage.complete,
        support_cluster_satisfied=(
            support_evaluation.active_support_cluster_count >= threshold_clusters
        ),
        support_ratio_satisfied=(
            support_evaluation.support_ratio_ppm
            >= threshold_snapshot.minimum_support_ratio_ppm
        ),
        diversity_satisfied=(
            summary.source_diversity >= threshold_snapshot.minimum_source_diversity
        ),
        margin_satisfied=margin >= threshold_snapshot.minimum_margin,
        unique_leader=item.candidate_id == selection.unique_leader_id,
        equivocation_finding_ids=equivocation_ids,
        equivocation_clear=not equivocation_ids,
    )


def _candidate_reason_codes(
    state: CandidateGateState,
    gates: ActionGateBindings,
    selection: SelectionState,
) -> tuple[str, ...]:
    reasons = tuple(
        code.value
        for failed, code in (
            (
                not state.positive_satisfied,
                CommitReasonCode.POSITIVE_EVIDENCE_INSUFFICIENT,
            ),
            (
                not state.counter_satisfied,
                CommitReasonCode.COUNTEREVIDENCE_LIMIT_EXCEEDED,
            ),
            (
                not state.ratio_satisfied,
                CommitReasonCode.COUNTEREVIDENCE_RATIO_EXCEEDED,
            ),
            (
                not state.critical_satisfied,
                CommitReasonCode.CRITICAL_COUNTEREVIDENCE_UNRESOLVED,
            ),
            (
                not state.challenge_satisfied,
                CommitReasonCode.CHALLENGE_COVERAGE_INCOMPLETE,
            ),
            (
                not state.support_cluster_satisfied,
                CommitReasonCode.SUPPORT_CLUSTERS_INSUFFICIENT,
            ),
            (
                not state.support_ratio_satisfied,
                CommitReasonCode.SUPPORT_RATIO_INSUFFICIENT,
            ),
            (
                not state.diversity_satisfied,
                CommitReasonCode.SOURCE_DIVERSITY_INSUFFICIENT,
            ),
            (
                not selection.assurance_satisfied,
                CommitReasonCode.ASSURANCE_INSUFFICIENT,
            ),
        )
        if failed
    )
    return (
        *reasons,
        *_leader_reason(state, selection),
        *(
            (CommitReasonCode.MARGIN_INSUFFICIENT.value,)
            if not state.margin_satisfied
            else ()
        ),
        *_stop_reason(gates),
        *_permission_reason(gates),
        *(
            (CommitReasonCode.SUPPORT_EQUIVOCATION.value,)
            if not state.equivocation_clear
            else ()
        ),
    )


def _leader_reason(
    state: CandidateGateState,
    selection: SelectionState,
) -> tuple[str, ...]:
    if not selection.unique_leader_id:
        return (CommitReasonCode.NO_UNIQUE_LEADER.value,)
    if not state.unique_leader:
        return (CommitReasonCode.NOT_LEADER.value,)
    return ()


def _stop_reason(gates: ActionGateBindings) -> tuple[str, ...]:
    if not gates.stop_bound:
        return (CommitReasonCode.STOP_RESOLUTION_UNRESOLVED.value,)
    if gates.stop_resolution.blocked:
        return (CommitReasonCode.STOP_BLOCKED.value,)
    return ()


def _permission_reason(gates: ActionGateBindings) -> tuple[str, ...]:
    if not gates.permission_bound:
        return (CommitReasonCode.COMMIT_PERMISSION_UNRESOLVED.value,)
    if not gates.commit_permission.allowed:
        return (CommitReasonCode.COMMIT_PERMISSION_DENIED.value,)
    return ()


def _candidate_blockers(
    state: CandidateGateState,
    summary: EvidenceSummary,
    gates: ActionGateBindings,
) -> tuple[str, ...]:
    return (
        *(
            summary.blocking_critical_counter_observation_fingerprints
            if not state.critical_satisfied
            else ()
        ),
        *(
            (gates.stop_root,)
            if gates.stop_bound and gates.stop_resolution.blocked
            else ()
        ),
        *(
            (gates.permission_root,)
            if gates.permission_bound and not gates.commit_permission.allowed
            else ()
        ),
        *state.equivocation_finding_ids,
    )


def _candidate_is_ready(
    state: CandidateGateState,
    selection: SelectionState,
) -> bool:
    return all(
        (
            state.positive_satisfied,
            state.counter_satisfied,
            state.ratio_satisfied,
            state.critical_satisfied,
            state.challenge_satisfied,
            state.support_cluster_satisfied,
            state.support_ratio_satisfied,
            state.diversity_satisfied,
            selection.assurance_satisfied,
            state.unique_leader,
            state.margin_satisfied,
            selection.stop_satisfied,
            selection.permission_satisfied,
            state.equivocation_clear,
        )
    )


def issue_conflict_assessment(
    context: CommitEvaluationContext,
    *,
    replay_conflicts: Sequence[str],
    gates: ActionGateBindings,
    issuance: AssessmentIssuance,
) -> CommitAssessment:
    return issue_commit_assessment(
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
        stop_resolution_fingerprint=gates.stop_root,
        permission_fingerprint=gates.permission_root,
        issuance=issuance,
    )


def issue_selected_assessment(
    context: CommitEvaluationContext,
    *,
    metrics: Sequence[CandidateCommitMetrics],
    selection: SelectionState,
    gates: ActionGateBindings,
    issuance: AssessmentIssuance,
) -> CommitAssessment:
    leader = next(
        (item for item in metrics if item.candidate_id == selection.unique_leader_id),
        None,
    )
    safety = bool(selection.equivocation_finding_ids)
    status = _assessment_status(safety=safety, leader=leader)
    reasons = set(leader.reason_codes if leader is not None else ())
    if not selection.unique_leader_id:
        reasons.add(CommitReasonCode.NO_UNIQUE_LEADER.value)
    if safety:
        reasons.add(CommitReasonCode.SUPPORT_EQUIVOCATION.value)
    blockers = tuple(
        {reference for item in metrics for reference in item.blocker_references}
    )
    return issue_commit_assessment(
        context=context,
        status=status,
        candidate_metrics=metrics,
        leader_candidate_id=selection.unique_leader_id,
        tied_candidate_ids=(
            selection.tied_candidate_ids if not selection.unique_leader_id else ()
        ),
        leader_margin=leader.margin if leader is not None else 0,
        blocker_references=blockers,
        equivocation_finding_ids=selection.equivocation_finding_ids,
        replay_conflict_references=(),
        reason_codes=tuple(reasons),
        stop_resolution_fingerprint=gates.stop_root,
        permission_fingerprint=gates.permission_root,
        issuance=issuance,
    )


def _assessment_status(
    *,
    safety: bool,
    leader: CandidateCommitMetrics | None,
) -> CommitAssessmentStatus:
    if safety:
        return CommitAssessmentStatus.SAFETY_VIOLATION
    if leader is not None and leader.ready_for_stability:
        return CommitAssessmentStatus.READY
    return CommitAssessmentStatus.NOT_READY


def issue_commit_assessment(
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
    issuance: AssessmentIssuance,
) -> CommitAssessment:
    metrics = tuple(candidate_metrics)
    evidence_root, challenge_root, lease_root = _collective_metric_roots(
        context,
        metrics,
    )
    leader = next(
        (item for item in metrics if item.candidate_id == leader_candidate_id),
        None,
    )
    assessment = CommitAssessment(
        assessment_id=require_commit_text(
            issuance.assessment_id,
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
        membership_epoch_state_fingerprint=(context.membership_epoch_state_fingerprint),
        membership_root=context.membership_root,
        replay_state_fingerprint=context.replay_state_fingerprint,
        replay_receipt_root=context.replay_receipt_root,
        support_replay_state_fingerprint=(context.support_replay_state_fingerprint),
        support_replay_root=context.support_replay_root,
        stop_resolution_fingerprint=stop_resolution_fingerprint,
        permission_fingerprint=permission_fingerprint,
        collective_evidence_root=evidence_root,
        collective_challenge_root=challenge_root,
        collective_lease_root=lease_root,
        candidate_metrics=metrics,
        unique_leader=bool(leader_candidate_id),
        leader_candidate_id=leader_candidate_id,
        tied_candidate_ids=tuple(tied_candidate_ids),
        leader_margin=leader_margin,
        leader_ready_for_stability=bool(
            leader is not None and leader.ready_for_stability
        ),
        blocker_references=tuple(blocker_references),
        equivocation_finding_ids=tuple(equivocation_finding_ids),
        replay_conflict_references=tuple(replay_conflict_references),
        reason_codes=tuple(reason_codes),
        issuer_id=require_commit_text(
            issuance.issuer_id,
            "commit assessment issuer_id",
        ),
        authority=issuance.authority,
        evaluated_at_step=issuance.evaluated_at_step,
        provenance=require_commit_text(
            issuance.provenance,
            "commit assessment provenance",
        ),
        trace_event_id=require_commit_text(
            issuance.trace_event_id,
            "commit assessment trace_event_id",
        ),
    )
    return mark_commit_assessment_authoritative(assessment)


def _collective_metric_roots(
    context: CommitEvaluationContext,
    metrics: Sequence[CandidateCommitMetrics],
) -> tuple[str, str, str]:
    evidence_root = _collective_root(
        ((item.candidate_id, item.evidence_root) for item in metrics),
        schema="pheroos-collective-evidence-root-v1",
        profile=context.profile,
    )
    challenge_root = _collective_root(
        ((item.candidate_id, item.challenge_root) for item in metrics),
        schema="pheroos-collective-challenge-root-v1",
        profile=context.profile,
    )
    lease_root = _collective_root(
        ((item.candidate_id, item.lease_root) for item in metrics),
        schema="pheroos-collective-lease-root-v1",
        profile=context.profile,
    )
    return evidence_root, challenge_root, lease_root


__all__: list[str] = []
