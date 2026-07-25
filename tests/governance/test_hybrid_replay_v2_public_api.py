from __future__ import annotations

import inspect

import pytest

import pheroos.governance as governance
import pheroos.governance.hybrid_replay_v2 as hybrid_replay_v2


_PUBLIC_NAMES = {
    "HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2",
    "HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2",
    "HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2",
    "HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2",
    "HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2",
    "HYBRID_REPLAY_STATE_SCHEMA_V2",
    "HybridReplayAdvanceRequestV2",
    "HybridReplaySnapshotV2",
    "VerifiedHybridReplayStateV2",
    "VerifiedHybridSourceStepV2",
    "advance_hybrid_replay_state_v2",
    "build_hybrid_replay_advance_request_v2",
    "evaluate_hybrid_collective_step_v2",
    "hybrid_replay_diffusion_source_trail_root_v2",
    "hybrid_replay_state_is_current_v2",
    "hybrid_replay_stream_ref_v2",
    "hybrid_replay_transition_id_v2",
    "open_hybrid_replay_authority_session_v2",
    "rehydrate_hybrid_replay_state_v2",
    "require_current_hybrid_replay_state_v2",
}


def test_hybrid_replay_v2_public_module_is_small_and_exact() -> None:
    assert set(hybrid_replay_v2.__all__) == _PUBLIC_NAMES
    assert not {
        "RestoredHybridReplayInputsV2",
        "project_collective_policy_v2",
        "restore_collective_policy_v2",
        "restore_hybrid_replay_inputs_v2",
        "verify_hybrid_replay_request_source_v2",
    }.intersection(hybrid_replay_v2.__all__)


@pytest.mark.parametrize("name", sorted(_PUBLIC_NAMES))
def test_hybrid_replay_v2_top_level_facade_owns_every_public_binding(
    name: str,
) -> None:
    selected = getattr(hybrid_replay_v2, name)
    assert getattr(governance, name) is selected
    if inspect.isclass(selected) or inspect.isfunction(selected):
        assert selected.__module__ == "pheroos.governance.hybrid_replay_v2"


def test_hybrid_replay_v2_verified_handles_have_no_public_constructor() -> None:
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        hybrid_replay_v2.VerifiedHybridSourceStepV2()
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        hybrid_replay_v2.VerifiedHybridReplayStateV2()
