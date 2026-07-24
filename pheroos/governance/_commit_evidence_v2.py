"""Authority-neutral Commit Evidence v2 projection shared by v2 owners.

Everything exported here is portable deterministic data.  A projection is
Decision-eligible only when the private Evidence owner supplies the matching
current StateStore handle and read precondition.  Replay data independently
proves non-reuse; it never creates or qualifies evidence.
"""

from pheroos.governance._commit_evidence_projection_v2 import (
    COMMIT_EVIDENCE_POLICY_SCHEMA_V2,
    COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2,
    COMMIT_EVIDENCE_RECORD_SCHEMA_V2,
    ChallengeResultV2,
    CommitEvidenceDispositionV2,
    CommitEvidenceEvaluationV2,
    CommitEvidenceKindV2,
    CommitEvidencePolicySnapshotV2,
    CommitEvidenceProjectionV2,
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
    evaluate_commit_evidence_projection_v2,
)

__all__ = [
    "COMMIT_EVIDENCE_POLICY_SCHEMA_V2",
    "COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2",
    "COMMIT_EVIDENCE_RECORD_SCHEMA_V2",
    "ChallengeResultV2",
    "CommitEvidenceDispositionV2",
    "CommitEvidenceEvaluationV2",
    "CommitEvidenceKindV2",
    "CommitEvidencePolicySnapshotV2",
    "CommitEvidenceProjectionV2",
    "CommitEvidenceStatusV2",
    "QualifiedCommitEvidenceV2",
    "evaluate_commit_evidence_projection_v2",
]
