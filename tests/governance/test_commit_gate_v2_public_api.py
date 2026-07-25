from __future__ import annotations

from pathlib import Path

import pheroos.governance.commit_gate_v2 as api


EXPECTED_PUBLIC = frozenset(
    {
        "COMMIT_GATE_DEPENDENCIES_SCHEMA_V2",
        "COMMIT_GATE_GENESIS_TRANSITION_ID_V2",
        "COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2",
        "COMMIT_PERMISSION_POLICY_VERSION_V2",
        "COMMIT_PERMISSION_REQUEST_SCHEMA_V2",
        "COMMIT_PERMISSION_SNAPSHOT_SCHEMA_V2",
        "COMMIT_PERMISSION_STATE_SCHEMA_V2",
        "COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2",
        "COMMIT_STOP_POLICY_VERSION_V2",
        "COMMIT_STOP_REQUEST_SCHEMA_V2",
        "COMMIT_STOP_SNAPSHOT_SCHEMA_V2",
        "COMMIT_STOP_STATE_SCHEMA_V2",
        "MAX_COMMIT_GATE_ITEMS_V2",
        "MAX_COMMIT_GATE_SNAPSHOT_BYTES_V2",
        "MAX_COMMIT_GATE_TEXT_BYTES_V2",
        "CommitGateDependenciesV2",
        "CommitPermissionRequestV2",
        "CommitPermissionSnapshotV2",
        "CommitStopRequestV2",
        "CommitStopSnapshotV2",
        "VerifiedCommitPermissionSourceV2",
        "VerifiedCommitPermissionStateV2",
        "VerifiedCommitStopSourceV2",
        "VerifiedCommitStopStateV2",
        "commit_gate_candidate_set_root_v2",
        "commit_gate_claims_root_v2",
        "commit_gate_evaluation_context_root_v2",
        "commit_permission_allows_v2",
        "commit_permission_policy_root_v2",
        "commit_permission_state_is_current_v2",
        "commit_permission_stream_ref_v2",
        "commit_permission_transition_id_v2",
        "commit_stop_blocks_v2",
        "commit_stop_policy_root_v2",
        "commit_stop_reasons_root_v2",
        "commit_stop_state_is_current_v2",
        "commit_stop_stream_ref_v2",
        "commit_stop_transition_id_v2",
        "issue_commit_permission_v2",
        "open_commit_permission_authority_session_v2",
        "open_commit_stop_authority_session_v2",
        "prepare_commit_permission_issue_v2",
        "prepare_commit_stop_resolution_v2",
        "rehydrate_commit_permission_state_v2",
        "rehydrate_commit_stop_state_v2",
        "require_current_commit_permission_state_v2",
        "require_current_commit_stop_state_v2",
        "resolve_commit_stop_v2",
        "verify_commit_permission_request_source_v2",
        "verify_commit_stop_request_source_v2",
    }
)


def test_commit_gate_v2_public_surface_is_exact_and_native() -> None:
    assert frozenset(api.__all__) == EXPECTED_PUBLIC
    assert len(api.__all__) == len(EXPECTED_PUBLIC)
    for name in api.__all__:
        value = getattr(api, name)
        if callable(value):
            assert value.__module__ == "pheroos.governance.commit_gate_v2"
    assert all(not name.startswith("_") for name in api.__all__)


def test_commit_gate_v2_document_names_fixed_streams_and_boundaries() -> None:
    document = (
        Path(__file__).resolve().parents[2] / "docs/protocol/commit-gate-v2.md"
    ).read_text()
    for required in (
        "authority:commit-stop-v2",
        "authority:commit-permission-v2",
        "RESOLVE_STOP",
        "ISSUE_ACTION_PERMISSION",
        "exactly eight streams",
        "Principal Verification v2",
        "does not select a candidate",
        "commit_stop_resolved_v2",
        "commit_permission_issued_v2",
    ):
        assert required in document
