"""Public ABI for durable Commit Evidence v2.

Portable proposals, snapshots, projections, and evaluations are deterministic
data only.  Evidence authority requires a QUALIFY_EVIDENCE authority session,
current Principal Verification, Membership, and Commit Replay state handles,
and one successful atomic StateStore v2 commit.
"""

from __future__ import annotations

from pheroos.governance._commit_evidence_owner_v2.contracts import (
    COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2,
    COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2,
    COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2,
    COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2,
    COMMIT_EVIDENCE_STATE_SCHEMA_V2,
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceSnapshotV2,
    active_qualified_evidence_v2,
    commit_evidence_history_advance_v2,
    commit_evidence_stream_ref_v2,
    commit_evidence_transition_id_v2,
)
from pheroos.governance._commit_evidence_owner_v2.operations import (
    advance_commit_evidence_state_v2,
    open_commit_evidence_authority_session_v2,
    rehydrate_commit_evidence_state_v2,
)
from pheroos.governance._commit_evidence_owner_v2.proposals import (
    COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2,
    COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2,
    COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2,
    CommitEvidenceAttestationV2,
    CommitEvidenceRevocationV2,
    CounterevidenceDispositionProposalV2,
)
from pheroos.governance._commit_evidence_owner_v2.replay_projection import (
    commit_evidence_replay_receipts_for_proposals_v2,
)
from pheroos.governance._commit_evidence_owner_v2.source import (
    prepare_commit_evidence_advance_v2,
    verify_commit_evidence_request_source_v2,
)
from pheroos.governance._commit_evidence_owner_v2.source_proof import (
    VerifiedCommitEvidenceSourceV2,
)
from pheroos.governance._commit_evidence_owner_v2.state_handle import (
    VerifiedCommitEvidenceStateV2,
    commit_evidence_state_is_current_v2,
    project_current_commit_evidence_v2,
    require_current_commit_evidence_state_v2,
)
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


_PUBLIC_MODULE = __name__
_NATIVE_PUBLIC_OBJECTS = (
    ChallengeResultV2,
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceAttestationV2,
    CommitEvidenceDispositionV2,
    CommitEvidenceEvaluationV2,
    CommitEvidenceKindV2,
    CommitEvidencePolicySnapshotV2,
    CommitEvidenceProjectionV2,
    CommitEvidenceRevocationV2,
    CommitEvidenceSnapshotV2,
    CommitEvidenceStatusV2,
    CounterevidenceDispositionProposalV2,
    QualifiedCommitEvidenceV2,
    VerifiedCommitEvidenceSourceV2,
    VerifiedCommitEvidenceStateV2,
    active_qualified_evidence_v2,
    advance_commit_evidence_state_v2,
    commit_evidence_history_advance_v2,
    commit_evidence_replay_receipts_for_proposals_v2,
    commit_evidence_state_is_current_v2,
    commit_evidence_stream_ref_v2,
    commit_evidence_transition_id_v2,
    evaluate_commit_evidence_projection_v2,
    open_commit_evidence_authority_session_v2,
    prepare_commit_evidence_advance_v2,
    project_current_commit_evidence_v2,
    rehydrate_commit_evidence_state_v2,
    require_current_commit_evidence_state_v2,
    verify_commit_evidence_request_source_v2,
)
for _public_object in _NATIVE_PUBLIC_OBJECTS:
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2",
    "COMMIT_EVIDENCE_ATTESTATION_SCHEMA_V2",
    "COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2",
    "COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2",
    "COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2",
    "COMMIT_EVIDENCE_POLICY_SCHEMA_V2",
    "COMMIT_EVIDENCE_PROJECTION_SCHEMA_V2",
    "COMMIT_EVIDENCE_RECORD_SCHEMA_V2",
    "COMMIT_EVIDENCE_REVOCATION_SCHEMA_V2",
    "COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2",
    "COMMIT_EVIDENCE_STATE_SCHEMA_V2",
    "COUNTEREVIDENCE_DISPOSITION_PROPOSAL_SCHEMA_V2",
    "ChallengeResultV2",
    "CommitEvidenceAdvanceRequestV2",
    "CommitEvidenceAttestationV2",
    "CommitEvidenceDispositionV2",
    "CommitEvidenceEvaluationV2",
    "CommitEvidenceKindV2",
    "CommitEvidencePolicySnapshotV2",
    "CommitEvidenceProjectionV2",
    "CommitEvidenceRevocationV2",
    "CommitEvidenceSnapshotV2",
    "CommitEvidenceStatusV2",
    "CounterevidenceDispositionProposalV2",
    "QualifiedCommitEvidenceV2",
    "VerifiedCommitEvidenceSourceV2",
    "VerifiedCommitEvidenceStateV2",
    "active_qualified_evidence_v2",
    "advance_commit_evidence_state_v2",
    "commit_evidence_history_advance_v2",
    "commit_evidence_replay_receipts_for_proposals_v2",
    "commit_evidence_state_is_current_v2",
    "commit_evidence_stream_ref_v2",
    "commit_evidence_transition_id_v2",
    "evaluate_commit_evidence_projection_v2",
    "open_commit_evidence_authority_session_v2",
    "prepare_commit_evidence_advance_v2",
    "project_current_commit_evidence_v2",
    "rehydrate_commit_evidence_state_v2",
    "require_current_commit_evidence_state_v2",
    "verify_commit_evidence_request_source_v2",
]
