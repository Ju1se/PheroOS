from __future__ import annotations

import inspect

import pheroos.governance.commit_decision_v2 as api


EXPECTED_PUBLIC = frozenset(
    """
    COMMIT_DECISION_ASSESSMENT_SCHEMA_V2
    COMMIT_DECISION_CANDIDATE_PROPOSAL_SCHEMA_V2
    COMMIT_DECISION_CANONICAL_VERSION_V2
    COMMIT_DECISION_DEPENDENCY_SCHEMA_V2
    COMMIT_DECISION_EVIDENCE_PROPOSAL_SCHEMA_V2
    COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2
    COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2
    COMMIT_DECISION_GENESIS_TRANSITION_ID_V2
    COMMIT_DECISION_OUTCOME_SCHEMA_V2
    COMMIT_DECISION_OUTPUT_PROPOSAL_SCHEMA_V2
    COMMIT_DECISION_PROGRESS_SCHEMA_V2
    COMMIT_DECISION_REQUEST_SCHEMA_V2
    COMMIT_DECISION_SEAL_INCLUSION_SCHEMA_V2
    COMMIT_DECISION_SEAL_SCHEMA_V2
    COMMIT_DECISION_SNAPSHOT_SCHEMA_V2
    COMMIT_DECISION_STATE_SCHEMA_V2
    COMMIT_DECISION_WINDOW_SCHEMA_V2
    COMMIT_FINALITY_INPUT_SCHEMA_V2
    COMMIT_FINALITY_PROJECTION_SCHEMA_V2
    MAX_COMMIT_DECISION_ITEMS_V2
    MAX_COMMIT_DECISION_RESOURCE_DEPTH_V2
    MAX_COMMIT_DECISION_RESOURCE_NODES_V2
    MAX_COMMIT_DECISION_RESOURCE_TEXT_BYTES_V2
    MAX_COMMIT_DECISION_SNAPSHOT_BYTES_V2
    MAX_COMMIT_DECISION_TEXT_BYTES_V2
    CommitAssessmentV2
    CommitCandidateMetricsV2
    CommitDecisionCandidateProposalV2
    CommitDecisionCommandV2
    CommitDecisionDependencyRoleV2
    CommitDecisionDependencyV2
    CommitDecisionEvidenceProposalV2
    CommitDecisionGateStatusV2
    CommitDecisionMutationKindV2
    CommitDecisionOutcomeKindV2
    CommitDecisionOutcomeV2
    CommitDecisionOutputProposalV2
    CommitDecisionPhaseV2
    CommitDecisionProgressV2
    CommitDecisionRequestV2
    CommitDecisionSealInclusionV2
    CommitDecisionSnapshotV2
    CommitDecisionWindowSealV2
    CommitDecisionWindowV2
    CommitFinalityOwnerV2
    CommitFinalityProjectionV2
    CommitFinalityStatusV2
    VerifiedCommitDecisionSourceV2
    VerifiedCommitDecisionStateV2
    VerifiedCommitFinalityInputV2
    advance_commit_decision_v2
    canonical_candidate_proposals_v2
    canonical_commit_decision_dependencies_v2
    commit_decision_dependency_set_root_v2
    commit_decision_frozen_dependency_root_v2
    commit_decision_history_advance_v2
    commit_decision_state_is_current_v2
    commit_decision_stream_ref_v2
    commit_decision_transition_id_v2
    commit_finality_owner_genesis_snapshot_root_v2
    commit_finality_owner_stream_ref_v2
    open_commit_decision_authority_session_v2
    prepare_commit_decision_initialize_v2
    prepare_commit_decision_missing_inputs_v2
    prepare_commit_decision_successor_v2
    reduce_commit_decision_v2
    rehydrate_commit_decision_state_v2
    require_current_commit_decision_state_v2
    verify_commit_decision_request_source_v2
    """.split()
)
NEUTRAL_FINALITY_OBJECTS = frozenset(
    {
        "CommitFinalityOwnerV2",
        "CommitFinalityProjectionV2",
        "CommitFinalityStatusV2",
        "VerifiedCommitFinalityInputV2",
        "commit_finality_owner_genesis_snapshot_root_v2",
        "commit_finality_owner_stream_ref_v2",
    }
)


def test_commit_decision_v2_public_surface_is_exact_and_native() -> None:
    assert frozenset(api.__all__) == EXPECTED_PUBLIC
    assert len(api.__all__) == len(EXPECTED_PUBLIC)
    assert all(not name.startswith("_") for name in api.__all__)
    for name in api.__all__:
        value = getattr(api, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            expected_module = (
                "pheroos.governance.commit_finality_v2"
                if name in NEUTRAL_FINALITY_OBJECTS
                else "pheroos.governance.commit_decision_v2"
            )
            assert value.__module__ == expected_module


def test_commit_decision_v2_facade_closes_all_durable_entrypoints() -> None:
    for entrypoint in (
        "prepare_commit_decision_initialize_v2",
        "prepare_commit_decision_missing_inputs_v2",
        "prepare_commit_decision_successor_v2",
        "open_commit_decision_authority_session_v2",
        "advance_commit_decision_v2",
        "rehydrate_commit_decision_state_v2",
        "require_current_commit_decision_state_v2",
        "commit_decision_state_is_current_v2",
    ):
        assert callable(getattr(api, entrypoint))


def test_commit_decision_v2_facade_names_draft_and_unconsumed_owner_boundary() -> None:
    document = api.__doc__ or ""
    assert document.startswith("Draft public Commit Decision v2 ABI.")
    assert "CAS dependency" in document
    assert "never infers owner status" in document
