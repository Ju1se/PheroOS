"""Pure assessment derived only from Store-qualified Evidence v2 data."""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.models import CandidateSpec

from pheroos.governance._commit_evidence_v2 import (
    CommitEvidenceEvaluationV2,
    CommitEvidenceProjectionV2,
)
from pheroos.governance._commit_decision_v2.assessment_records import (
    CommitAssessmentV2,
    CommitCandidateMetricsV2,
)
from pheroos.governance._commit_decision_v2.common import _root
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionCandidateProposalV2,
)
from pheroos.governance._commit_gate_v2.permission_contracts import (
    CommitPermissionSnapshotV2,
)
from pheroos.governance._commit_gate_v2.stop_contracts import CommitStopSnapshotV2
from pheroos.governance._risk_v2.contracts import RiskStateSnapshotV2
from pheroos.governance._support_v2.evaluation import evaluate_support_v2


_ASSURANCE_RANK = MappingProxyType(
    {
        CommitAssurance.ADVISORY: 0,
        CommitAssurance.EVIDENCE_BOUND: 1,
        CommitAssurance.CERTIFIED: 2,
        CommitAssurance.DISTRIBUTED: 3,
    }
)


def derive_commit_assessment_v2(
    *,
    manifest: ScopedProtocolManifestV2,
    current_step: int,
    epoch: int,
    proposals: Sequence[CommitDecisionCandidateProposalV2],
    authoritative_subjects: Sequence[tuple[str, str]],
    evidence_evaluations: Sequence[
        tuple[CommitEvidenceProjectionV2, CommitEvidenceEvaluationV2]
    ],
    risk: RiskStateSnapshotV2,
    membership_state: object,
    support_state: object,
    stop: CommitStopSnapshotV2,
    permission: CommitPermissionSnapshotV2,
    stop_dependencies_current: bool,
    permission_dependencies_current: bool,
    dependency_set_root: str,
    evaluation_context_root: str,
) -> CommitAssessmentV2:
    policy = manifest.collective_commit_policy
    if policy is None:
        raise ValueError("Commit Decision v2 manifest has no commit policy")
    declared = {
        item.id: item for item in manifest.candidates if item.target == policy.target
    }
    canonical, coverage_reasons = _closed_candidate_proposals_v2(
        manifest=manifest,
        proposals=proposals,
        authoritative_subjects=authoritative_subjects,
    )
    evidence = _evidence_by_candidate_v2(evidence_evaluations)
    results = tuple(
        _candidate_metrics(
            proposal,
            preset_reasons=preset_reasons,
            manifest=manifest,
            current_step=current_step,
            epoch=epoch,
            declared=declared,
            evidence=evidence.get((proposal.candidate_ref, proposal.claim_root)),
            risk=risk,
            membership_state=membership_state,
            support_state=support_state,
            stop=stop,
            permission=permission,
        )
        for proposal, preset_reasons in canonical
    )
    metrics = tuple(item[0] for item in results)
    leader, ties, margin = _select_leader_v2(metrics)
    unique = bool(leader)
    eligible = tuple(
        item for item in metrics if not _candidate_is_authority_invalid(item)
    )
    selected = next((item for item in eligible if item.candidate_ref == leader), None)
    threshold = risk.threshold
    stop_clear = (
        stop_dependencies_current
        and stop.issued_at_step <= current_step < stop.expires_at_step
        and not stop.blocked
    )
    permission_allowed = (
        permission_dependencies_current
        and permission.issued_at_step <= current_step < permission.expires_at_step
        and permission.allowed
    )
    authority_failure = any(
        reason.startswith(("invalid:", "safety:"))
        for item in metrics
        for reason in item.reason_codes
    ) or any(reason.startswith(("invalid:", "safety:")) for reason in coverage_reasons)
    ready = bool(
        selected is not None
        and selected.ready_for_stability
        and margin >= threshold.minimum_margin
        and stop_clear
        and permission_allowed
        and not authority_failure
    )
    normalized_candidate_reasons: tuple[str, ...] = ()
    if any(
        reason.startswith("invalid:")
        for item in metrics
        for reason in item.reason_codes
    ):
        normalized_candidate_reasons = ("invalid:candidate_authority_binding",)
    reasons = (
        coverage_reasons
        + normalized_candidate_reasons
        + _global_reasons(
            has_proposals=bool(metrics),
            has_eligible=bool(eligible),
            unique=unique,
            margin=margin,
            minimum_margin=threshold.minimum_margin,
            stop_clear=stop_clear,
            permission_allowed=permission_allowed,
            stop=stop,
            permission=permission,
            stop_dependencies_current=stop_dependencies_current,
            permission_dependencies_current=permission_dependencies_current,
            current_step=current_step,
        )
    )
    return CommitAssessmentV2(
        current_step=current_step,
        candidate_metrics=metrics,
        leader_candidate_ref=leader,
        tied_candidate_refs=ties,
        unique_leader=unique,
        leader_margin=max(0, margin),
        leader_ready_for_stability=ready,
        stop_clear=stop_clear,
        permission_allowed=permission_allowed,
        blocker_refs=(stop.reason_root,) if not stop_clear else (),
        equivocation_refs=tuple(
            sorted({root for _, roots in results for root in roots})
        ),
        replay_conflict_refs=(),
        reason_codes=reasons,
        dependency_set_root=dependency_set_root,
        evaluation_context_root=evaluation_context_root,
        collective_evidence_root=_root(
            "collective-evidence", {"roots": [item.evidence_root for item in metrics]}
        ),
        collective_challenge_root=_root(
            "collective-challenge", {"roots": [item.challenge_root for item in metrics]}
        ),
        collective_claim_root=_root(
            "collective-claims", {"roots": sorted(item.claim_root for item in metrics)}
        ),
        collective_lease_root=_root(
            "collective-leases", {"roots": [item.lease_root for item in metrics]}
        ),
    )


def _candidate_metrics(
    proposal: CommitDecisionCandidateProposalV2,
    *,
    preset_reasons: Sequence[str],
    manifest: ScopedProtocolManifestV2,
    current_step: int,
    epoch: int,
    declared: dict[str, CandidateSpec],
    evidence: tuple[CommitEvidenceProjectionV2, CommitEvidenceEvaluationV2] | None,
    risk: RiskStateSnapshotV2,
    membership_state: object,
    support_state: object,
    stop: CommitStopSnapshotV2,
    permission: CommitPermissionSnapshotV2,
) -> tuple[CommitCandidateMetricsV2, tuple[str, ...]]:
    projection, evaluated, evidence_status = _candidate_evidence_v2(
        proposal,
        evidence=evidence,
        current_step=current_step,
    )
    positive = 0 if evaluated is None else evaluated.positive_evidence
    counter = 0 if evaluated is None else evaluated.counterevidence
    ratio = 0 if evaluated is None else evaluated.counterevidence_ratio_ppm
    challenges = () if evaluated is None else evaluated.covered_challenge_categories
    diversity = 0 if evaluated is None else evaluated.source_diversity
    support = evaluate_support_v2(
        support_state=support_state,
        membership_state=membership_state,
        manifest=manifest,
        candidate_ref=proposal.candidate_ref,
        claim_root=proposal.claim_root,
        epoch=epoch,
        current_step=current_step,
    )
    threshold = risk.threshold
    reasons = list(preset_reasons)
    candidate = declared.get(proposal.candidate_ref)
    if candidate is None:
        reasons.append("invalid:undeclared_candidate")
    elif getattr(candidate, "safe_fallback", False):
        reasons.append("invalid:safe_fallback_not_substantive")
    if evidence_status == "unbound":
        reasons.append("invalid:evidence_projection_unbound")
    elif evidence_status == "unavailable":
        reasons.append("input:evidence_unavailable")
    if proposal.claim_root not in permission.claim_roots:
        reasons.append("invalid:permission_claim_unbound")
    if proposal.candidate_ref not in permission.candidate_refs:
        reasons.append("invalid:permission_candidate_unbound")
    policy = manifest.collective_commit_policy
    if policy is None:
        raise ValueError("Commit Decision v2 manifest has no commit policy")
    checks = (
        (
            evaluated is not None and evaluated.evidence_gates_satisfied,
            "evidence:owner_gates_unsatisfied",
        ),
        (
            positive >= threshold.minimum_positive_evidence,
            "evidence:positive_insufficient",
        ),
        (counter <= threshold.maximum_counterevidence, "evidence:counter_limit"),
        (
            ratio <= threshold.maximum_counterevidence_ratio_ppm,
            "evidence:counter_ratio",
        ),
        (
            support.active_support_cluster_count >= threshold.minimum_support_clusters,
            "support:clusters_insufficient",
        ),
        (
            support.support_ratio_ppm >= threshold.minimum_support_ratio_ppm,
            "support:ratio_insufficient",
        ),
        (diversity >= threshold.minimum_source_diversity, "evidence:source_diversity"),
        (
            set(threshold.required_challenge_categories).issubset(challenges),
            "challenge:coverage_incomplete",
        ),
        (
            _ASSURANCE_RANK[CommitAssurance(policy.assurance)]
            >= _ASSURANCE_RANK[threshold.minimum_assurance],
            "assurance:insufficient",
        ),
        (not support.equivocations, "safety:support_equivocation"),
        (not stop.blocked, "stop:blocked"),
        (permission.allowed, "permission:denied"),
    )
    reasons.extend(reason for passed, reason in checks if not passed)
    fatal = any(reason.startswith("invalid:") for reason in reasons)
    net_evidence = 0 if fatal or evaluated is None else evaluated.net_evidence
    score = max(0, net_evidence)
    metrics = CommitCandidateMetricsV2(
        candidate_ref=proposal.candidate_ref,
        claim_root=proposal.claim_root,
        positive_evidence_count=positive,
        counterevidence_count=counter,
        counterevidence_ratio_ppm=ratio,
        active_support_clusters=support.active_support_cluster_count,
        support_ratio_ppm=support.support_ratio_ppm,
        source_diversity=diversity,
        challenge_categories=challenges,
        evidence_root=_root(
            "candidate-qualified-evidence",
            {
                "evaluation_root": ""
                if evaluated is None
                else evaluated.evaluation_root,
                "records": []
                if evaluated is None
                else list(evaluated.replayed_record_roots),
            },
        ),
        challenge_root=_root(
            "candidate-challenges", {"categories": sorted(challenges)}
        ),
        lease_root=_root(
            "candidate-leases", {"roots": list(support.included_lease_roots)}
        ),
        net_evidence=net_evidence,
        score=score,
        ready_for_stability=not reasons,
        reason_codes=reasons,
    )
    equivocations = tuple(sorted(item.finding_root for item in support.equivocations))
    return metrics, equivocations


def _closed_candidate_proposals_v2(
    *,
    manifest: ScopedProtocolManifestV2,
    proposals: Sequence[CommitDecisionCandidateProposalV2],
    authoritative_subjects: Sequence[tuple[str, str]],
) -> tuple[
    tuple[tuple[CommitDecisionCandidateProposalV2, tuple[str, ...]], ...],
    tuple[str, ...],
]:
    """Close caller intent over every substantive manifest candidate exactly once."""

    policy = manifest.collective_commit_policy
    assert policy is not None
    expected = tuple(
        sorted(
            (
                item.id
                for item in manifest.candidates
                if item.target == policy.target and not item.safe_fallback
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    supplied = {item.candidate_ref: item for item in proposals}
    extra = tuple(
        sorted(set(supplied) - set(expected), key=lambda item: item.encode("utf-8"))
    )
    global_reasons = tuple(
        f"invalid:unexpected_candidate_proposal:{candidate}" for candidate in extra
    )
    claims = _authoritative_claims_v2(authoritative_subjects)
    closed = tuple(
        _closed_candidate_proposal_v2(
            candidate,
            proposal=supplied.get(candidate),
            claims=claims.get(candidate, ()),
        )
        for candidate in expected
    )
    if any(
        reason.startswith("invalid:") for _, reasons in closed for reason in reasons
    ):
        global_reasons += ("invalid:candidate_set_or_claim_binding",)
    if any(reason.startswith("safety:") for _, reasons in closed for reason in reasons):
        global_reasons += ("safety:subject_claim_conflict",)
    return closed, global_reasons


def _authoritative_claims_v2(
    subjects: Sequence[tuple[str, str]],
) -> dict[str, tuple[str, ...]]:
    if type(subjects) not in (list, tuple):
        raise TypeError("commit decision authoritative subjects must be exact")
    claims: dict[str, set[str]] = {}
    for subject in subjects:
        if (
            type(subject) is not tuple
            or len(subject) != 2
            or any(type(value) is not str for value in subject)
        ):
            raise TypeError("commit decision authoritative subject is malformed")
        claims.setdefault(subject[0], set()).add(subject[1])
    return {
        candidate: tuple(sorted(values, key=lambda item: item.encode("utf-8")))
        for candidate, values in claims.items()
    }


def _closed_candidate_proposal_v2(
    candidate: str,
    *,
    proposal: CommitDecisionCandidateProposalV2 | None,
    claims: Sequence[str],
) -> tuple[CommitDecisionCandidateProposalV2, tuple[str, ...]]:
    reasons: list[str] = []
    if proposal is None:
        reasons.append("invalid:missing_candidate_proposal")
    if len(claims) > 1:
        reasons.append("safety:multiple_active_claims")
    if claims:
        claim_root = claims[0]
    elif proposal is not None:
        claim_root = proposal.claim_root
        reasons.append("input:authoritative_claim_unavailable")
    else:
        claim_root = _root("missing-claim", {"candidate_ref": candidate})
        reasons.append("input:authoritative_claim_unavailable")
    if proposal is not None and claims and proposal.claim_root != claim_root:
        reasons.append("invalid:claim_substitution")
    evidence = (
        proposal.evidence
        if proposal is not None and proposal.claim_root == claim_root
        else ()
    )
    return (
        CommitDecisionCandidateProposalV2(
            candidate_ref=candidate,
            claim_root=claim_root,
            evidence=evidence,
        ),
        tuple(reasons),
    )


def _candidate_is_authority_invalid(metrics: CommitCandidateMetricsV2) -> bool:
    return any(reason.startswith("invalid:") for reason in metrics.reason_codes)


def _select_leader_v2(
    metrics: Sequence[CommitCandidateMetricsV2],
) -> tuple[str, tuple[str, ...], int]:
    """Exclude every authority-invalid candidate before comparing scores."""

    eligible = tuple(
        item for item in metrics if not _candidate_is_authority_invalid(item)
    )
    maximum = max((item.net_evidence for item in eligible), default=-1)
    ties = tuple(
        sorted(
            (item.candidate_ref for item in eligible if item.net_evidence == maximum),
            key=lambda item: item.encode("utf-8"),
        )
    )
    if len(ties) != 1:
        return "", ties, 0
    leader = ties[0]
    runner_up = max(
        (item.net_evidence for item in eligible if item.candidate_ref != leader),
        default=0,
    )
    return leader, ties, max(0, maximum - max(0, runner_up))


def _candidate_evidence_v2(
    proposal: CommitDecisionCandidateProposalV2,
    *,
    evidence: tuple[CommitEvidenceProjectionV2, CommitEvidenceEvaluationV2] | None,
    current_step: int,
) -> tuple[
    CommitEvidenceProjectionV2 | None,
    CommitEvidenceEvaluationV2 | None,
    str,
]:
    if evidence is None:
        return None, None, "unavailable"
    projection, evaluated = evidence
    records = {
        item.record_root: item
        for item in projection.records
        if item.candidate_ref == proposal.candidate_ref
        and item.claim_root == proposal.claim_root
    }
    proposed = {item.qualified_record_root for item in proposal.evidence}
    replayed = set(evaluated.replayed_record_roots)
    if (
        evaluated.projection_root != projection.projection_root
        or evaluated.candidate_ref != proposal.candidate_ref
        or evaluated.claim_root != proposal.claim_root
        or not proposed.issubset(replayed)
        or not replayed.issubset(records)
        or any(records[root].expires_at_step <= current_step for root in replayed)
    ):
        return None, None, "unbound"
    return projection, evaluated, "verified"


def _evidence_by_candidate_v2(
    values: Sequence[tuple[CommitEvidenceProjectionV2, CommitEvidenceEvaluationV2]],
) -> dict[
    tuple[str, str], tuple[CommitEvidenceProjectionV2, CommitEvidenceEvaluationV2]
]:
    if type(values) not in (list, tuple):
        raise TypeError("commit decision evidence evaluations must be exact")
    result = {}
    for item in values:
        if type(item) is not tuple or len(item) != 2:
            raise TypeError("commit decision evidence evaluation is malformed")
        projection, evaluated = item
        if (
            type(projection) is not CommitEvidenceProjectionV2
            or type(evaluated) is not CommitEvidenceEvaluationV2
            or evaluated.projection_root != projection.projection_root
        ):
            raise TypeError("commit decision evidence evaluation is invalid")
        key = (evaluated.candidate_ref, evaluated.claim_root)
        if key in result:
            raise ValueError(
                "commit decision evidence evaluation repeats a candidate claim"
            )
        result[key] = (projection, evaluated)
    return result


def _global_reasons(
    *,
    has_proposals: bool,
    has_eligible: bool,
    unique: bool,
    margin: int,
    minimum_margin: int,
    stop_clear: bool,
    permission_allowed: bool,
    stop: CommitStopSnapshotV2,
    permission: CommitPermissionSnapshotV2,
    stop_dependencies_current: bool,
    permission_dependencies_current: bool,
    current_step: int,
) -> tuple[str, ...]:
    reasons = []
    if not has_proposals:
        reasons.append("input:candidates_missing")
    if not unique:
        reasons.append("leader:not_unique")
    if unique and margin < minimum_margin:
        reasons.append("leader:margin_insufficient")
    if has_proposals and not has_eligible:
        reasons.append("invalid:no_authority_eligible_candidate")
    if not stop_clear:
        reasons.append(
            "stop:dependency_stale"
            if not stop_dependencies_current
            else "stop:blocked"
            if stop.issued_at_step <= current_step < stop.expires_at_step
            and stop.blocked
            else "stop:unresolved_or_expired"
        )
    if not permission_allowed:
        reasons.append(
            "permission:dependency_stale"
            if not permission_dependencies_current
            else "permission:denied"
            if permission.issued_at_step <= current_step < permission.expires_at_step
            and not permission.allowed
            else "permission:unresolved_or_expired"
        )
    return tuple(reasons)


__all__ = ("derive_commit_assessment_v2",)
