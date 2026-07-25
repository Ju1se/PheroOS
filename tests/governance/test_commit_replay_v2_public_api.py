from __future__ import annotations

import inspect

import pheroos.governance as governance
from pheroos.governance import commit_state_v2


EXPECTED = {
    "COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2",
    "COMMIT_REPLAY_EMPTY_RECEIPT_ROOT_V2",
    "COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2",
    "COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2",
    "COMMIT_REPLAY_RECEIPT_SCHEMA_V2",
    "COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2",
    "COMMIT_REPLAY_STATE_SCHEMA_V2",
    "CommitReplayAdvanceRequestV2",
    "CommitReplayReceiptV2",
    "CommitReplaySnapshotV2",
    "ReplayNamespace",
    "VerifiedCommitReplaySourceV2",
    "VerifiedCommitReplayStateV2",
    "advance_commit_replay_state_v2",
    "canonical_commit_replay_receipts_v2",
    "commit_replay_receipt_set_root_v2",
    "commit_replay_state_is_current_v2",
    "commit_replay_stream_ref_v2",
    "commit_replay_transition_id_v2",
    "open_commit_replay_authority_session_v2",
    "prepare_commit_replay_advance_v2",
    "rehydrate_commit_replay_state_v2",
    "require_current_commit_replay_state_v2",
}


def test_commit_replay_v2_public_surface_is_exact_and_top_level_owned() -> None:
    assert set(commit_state_v2.__all__) == EXPECTED
    assert EXPECTED <= set(governance.__all__)
    for name in EXPECTED:
        assert getattr(governance, name) is getattr(commit_state_v2, name)


def test_commit_replay_v2_native_objects_report_public_owner() -> None:
    for name in EXPECTED:
        value = getattr(commit_state_v2, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            expected_owner = (
                "pheroos.governance.commit_state"
                if name == "ReplayNamespace"
                else "pheroos.governance.commit_state_v2"
            )
            assert value.__module__ == expected_owner


def test_commit_replay_v2_verified_wrappers_are_final_and_nonportable() -> None:
    for cls in (
        commit_state_v2.VerifiedCommitReplaySourceV2,
        commit_state_v2.VerifiedCommitReplayStateV2,
    ):
        assert cls.__final__ is True
        try:

            class Derived(cls):  # type: ignore[misc, valid-type]
                pass
        except TypeError:
            continue
        raise AssertionError("verified replay wrapper accepted subclassing")
