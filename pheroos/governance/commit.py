"""Public Draft facade for optimal-commit governance evaluation."""

from __future__ import annotations

from pheroos.governance._commit.assessment import (
    CandidateCommitMetrics,
    CommitAssessment,
    CommitAssessmentStatus,
    candidate_commit_metrics_fingerprint,
    candidate_commit_metrics_payload,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_assessment_payload,
    rebuild_commit_assessment_roots,
)
from pheroos.governance._commit.context import (
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
    commit_evaluation_context_payload,
    issue_commit_evaluation_context,
)
from pheroos.governance._commit.evaluation import assess_optimal_commit
from pheroos.governance._commit.records import (
    CandidateClaimBinding,
    CandidateCommitInput,
    CommitEvaluationContext,
    CommitEvaluationError,
    CommitEvaluationFailureKind,
    CommitReasonCode,
)
from pheroos.governance._commit.replay import build_commit_replay_receipts


_PUBLIC_MODULE = __name__
for _public_object in (
    CandidateClaimBinding,
    CandidateCommitInput,
    CandidateCommitMetrics,
    CommitAssessment,
    CommitAssessmentStatus,
    CommitEvaluationContext,
    CommitEvaluationError,
    CommitEvaluationFailureKind,
    CommitReasonCode,
    assess_optimal_commit,
    build_commit_replay_receipts,
    candidate_commit_metrics_fingerprint,
    candidate_commit_metrics_payload,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_assessment_payload,
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
    commit_evaluation_context_payload,
    issue_commit_evaluation_context,
    rebuild_commit_assessment_roots,
):
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


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
