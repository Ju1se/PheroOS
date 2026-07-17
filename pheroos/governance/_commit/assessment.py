from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

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
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    canonical_commit_set,
    commit_payload_fingerprint,
    require_authority_integer,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
)


_COMMIT_ASSESSMENT_ISSUANCE = object()


class CommitAssessmentStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    SAFETY_VIOLATION = "safety_violation"


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
        for name in ("tied_candidate_ids", "reason_codes"):
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


def mark_commit_assessment_authoritative(
    assessment: CommitAssessment,
) -> CommitAssessment:
    if type(assessment) is not CommitAssessment:
        raise GovernanceError("commit assessment must be canonical")
    object.__setattr__(
        assessment,
        "_issuance",
        (_COMMIT_ASSESSMENT_ISSUANCE, commit_assessment_fingerprint(assessment)),
    )
    return assessment


def project_commit_assessment_for_window(
    assessment: object,
    *,
    current_step: int | None,
) -> dict[str, object]:
    if (
        type(assessment) is not CommitAssessment
        or not commit_assessment_is_authoritative(assessment)
    ):
        raise GovernanceError(
            "commit window requires an authoritative CommitAssessment"
        )
    if current_step is not None and assessment.evaluated_at_step != current_step:
        raise GovernanceError(
            "commit assessment step does not match the window transition"
        )
    ready = bool(
        assessment.status is CommitAssessmentStatus.READY
        and assessment.unique_leader
        and assessment.leader_ready_for_stability
        and assessment.leader_candidate_id
    )
    if ready:
        require_commit_text(
            assessment.leader_candidate_id,
            "commit assessment window leader",
        )
    leader_metrics = next(
        (
            item
            for item in assessment.candidate_metrics
            if item.candidate_id == assessment.leader_candidate_id
        ),
        None,
    )
    return {
        "assessment_ref": commit_assessment_fingerprint(assessment),
        "status": assessment.status.value,
        "profile": assessment.profile,
        "assurance": assessment.assurance,
        "manifest_root": assessment.manifest_root,
        "commit_policy_root": assessment.commit_policy_root,
        "protocol_id": assessment.protocol_id,
        "run_id": assessment.run_id,
        "target": assessment.target,
        "epoch": assessment.epoch,
        "context_ref": assessment.context_fingerprint,
        "risk_assessment_root": assessment.risk_assessment_fingerprint,
        "risk_chain_state_root": assessment.risk_chain_state_fingerprint,
        "risk_policy_root": assessment.risk_policy_root,
        "membership_root": assessment.membership_root,
        "membership_snapshot_root": assessment.membership_snapshot_fingerprint,
        "membership_epoch_state_root": (
            assessment.membership_epoch_state_fingerprint
        ),
        "threshold_root": assessment.threshold_fingerprint,
        "replay_state_ref": assessment.replay_state_fingerprint,
        "replay_root": assessment.replay_receipt_root,
        "support_replay_state_root": (
            assessment.support_replay_state_fingerprint
        ),
        "support_replay_root": assessment.support_replay_root,
        "collective_evidence_root": assessment.collective_evidence_root,
        "collective_challenge_root": assessment.collective_challenge_root,
        "collective_lease_root": assessment.collective_lease_root,
        "candidate_evidence_root": (
            leader_metrics.evidence_root if leader_metrics is not None else ""
        ),
        "candidate_challenge_root": (
            leader_metrics.challenge_root if leader_metrics is not None else ""
        ),
        "candidate_lease_root": (
            leader_metrics.lease_root if leader_metrics is not None else ""
        ),
        "stop_resolution_root": assessment.stop_resolution_fingerprint,
        "permission_root": assessment.permission_fingerprint,
        "leader_candidate_id": assessment.leader_candidate_id,
        "ready": ready,
        "reason_codes": assessment.reason_codes,
        "evaluated_at_step": assessment.evaluated_at_step,
    }


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
    if (
        metrics.counterevidence_ratio_ppm > WEIGHT_SCALE
        or metrics.support_ratio_ppm > WEIGHT_SCALE
    ):
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
    if metrics.ready_for_stability is not all(
        getattr(metrics, name) for name in gates
    ):
        raise GovernanceError("candidate metrics ready gate is inconsistent")
    expected_threshold = max(0, metrics.support_threshold_clusters)
    if (
        metrics.support_cluster_satisfied and metrics.support_ratio_satisfied
    ) is not (metrics.active_support_clusters >= expected_threshold):
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
    if any(
        getattr(assessment, name) != value
        for name, value in expected_roots.items()
    ):
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
                raise GovernanceError(
                    "commit assessment candidate margin is inconsistent"
                )
            if metrics.unique_leader is not (
                metrics.candidate_id == expected_leader
            ):
                raise GovernanceError(
                    "commit assessment candidate leader gate is inconsistent"
                )
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
        raise GovernanceError(
            "assessment without a leader must have zero leader margin"
        )
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


def _collective_root(
    values: object,
    *,
    schema: str,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        {"candidate_roots": tuple(sorted(tuple(values)))},
        schema=schema,
        profile=profile,
    )


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
    normalized = [require_commit_fingerprint(value, field_name) for value in values]
    if not normalized and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise GovernanceError(f"{field_name} contains duplicate fingerprints")
    return tuple(canonical_commit_set(normalized))


_PUBLIC_MODULE = "pheroos.governance.commit"
for _public_type in (
    CandidateCommitMetrics,
    CommitAssessment,
    CommitAssessmentStatus,
):
    _public_type.__module__ = _PUBLIC_MODULE
for _public_function in (
    candidate_commit_metrics_fingerprint,
    candidate_commit_metrics_payload,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_assessment_payload,
    rebuild_commit_assessment_roots,
):
    _public_function.__module__ = _PUBLIC_MODULE


__all__ = [
    "CandidateCommitMetrics",
    "CommitAssessment",
    "CommitAssessmentStatus",
    "candidate_commit_metrics_fingerprint",
    "candidate_commit_metrics_payload",
    "commit_assessment_fingerprint",
    "commit_assessment_is_authoritative",
    "commit_assessment_payload",
    "mark_commit_assessment_authoritative",
    "project_commit_assessment_for_window",
    "rebuild_commit_assessment_roots",
]
