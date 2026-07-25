"""Public durable Hybrid Replay v2 Governance ABI.

The high-level evaluator binds one exact scoped manifest, topology, input
policy, and committed parent into a non-portable source proof.  Only an exact
request, scoped authority session, and atomic StateStore commit can advance the
portable replay lineage.
"""

from __future__ import annotations

from pheroos.governance._hybrid_replay_v2.contracts import (
    HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2,
    HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2,
    HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
    HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2,
    HYBRID_REPLAY_STATE_SCHEMA_V2,
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
    hybrid_replay_diffusion_source_trail_root_v2,
    hybrid_replay_stream_ref_v2,
    hybrid_replay_transition_id_v2,
)
from pheroos.governance._hybrid_replay_v2.evaluator import (
    evaluate_hybrid_collective_step_v2,
)
from pheroos.governance._hybrid_replay_v2.numeric import (
    HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2,
)
from pheroos.governance._hybrid_replay_v2.operations import (
    VerifiedHybridReplayStateV2,
    advance_hybrid_replay_state_v2,
    hybrid_replay_state_is_current_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
    require_current_hybrid_replay_state_v2,
)
from pheroos.governance._hybrid_replay_v2.projection import (
    build_hybrid_replay_advance_request_v2,
)
from pheroos.governance._hybrid_replay_v2.source import VerifiedHybridSourceStepV2


_PUBLIC_MODULE = __name__
_NATIVE_PUBLIC_OBJECTS = (
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
    VerifiedHybridReplayStateV2,
    VerifiedHybridSourceStepV2,
    advance_hybrid_replay_state_v2,
    build_hybrid_replay_advance_request_v2,
    evaluate_hybrid_collective_step_v2,
    hybrid_replay_diffusion_source_trail_root_v2,
    hybrid_replay_state_is_current_v2,
    hybrid_replay_stream_ref_v2,
    hybrid_replay_transition_id_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
    require_current_hybrid_replay_state_v2,
)
for _public_object in _NATIVE_PUBLIC_OBJECTS:
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
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
]
