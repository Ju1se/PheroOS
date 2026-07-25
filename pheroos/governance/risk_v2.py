"""Public Draft ABI for durable, policy-bound Risk v2 authority.

Portable assessments and snapshots carry deterministic meaning only.  Risk
authority exists only after an exact ``QUALIFY_EVIDENCE`` authority session
atomically commits the request and its two canonical Trace events to a
StateStore v2 lineage.
"""

from __future__ import annotations

from pheroos.governance._risk_policy import RiskBand

from pheroos.governance._risk_v2.contracts import (
    MAX_RISK_INPUT_ROOTS_V2,
    MAX_RISK_RATIONALE_CODES_V2,
    MAX_RISK_RESOURCE_DEPTH_V2,
    MAX_RISK_RESOURCE_NODES_V2,
    MAX_RISK_RESOURCE_TEXT_BYTES_V2,
    MAX_RISK_SNAPSHOT_BYTES_V2,
    MAX_RISK_SOURCE_TRACE_ROOTS_V2,
    MAX_RISK_TEXT_BYTES_V2,
    RISK_ASSESSMENT_RECORD_SCHEMA_V2,
    RISK_GENESIS_SNAPSHOT_ROOT_V2,
    RISK_GENESIS_TRANSITION_ID_V2,
    RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2,
    RISK_STATE_SCHEMA_V2,
    RISK_STATE_SNAPSHOT_SCHEMA_V2,
    RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2,
    RiskAssessmentRecordV2,
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
    RiskThresholdSnapshotV2,
    risk_state_stream_ref_v2,
    risk_state_transition_id_v2,
)
from pheroos.governance._risk_v2.operations import (
    VerifiedRiskStateV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    rehydrate_risk_state_v2,
    require_current_risk_state_v2,
    risk_state_is_current_v2,
)
from pheroos.governance._risk_v2.source import (
    VerifiedRiskSourceV2,
    prepare_risk_state_advance_v2,
    verify_risk_state_request_source_v2,
)


_PUBLIC_MODULE = __name__
_NATIVE_PUBLIC_OBJECTS = (
    RiskAssessmentRecordV2,
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
    RiskThresholdSnapshotV2,
    VerifiedRiskSourceV2,
    VerifiedRiskStateV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
    rehydrate_risk_state_v2,
    require_current_risk_state_v2,
    risk_state_is_current_v2,
    risk_state_stream_ref_v2,
    risk_state_transition_id_v2,
    verify_risk_state_request_source_v2,
)
for _public_object in _NATIVE_PUBLIC_OBJECTS:
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "MAX_RISK_INPUT_ROOTS_V2",
    "MAX_RISK_RATIONALE_CODES_V2",
    "MAX_RISK_RESOURCE_DEPTH_V2",
    "MAX_RISK_RESOURCE_NODES_V2",
    "MAX_RISK_RESOURCE_TEXT_BYTES_V2",
    "MAX_RISK_SNAPSHOT_BYTES_V2",
    "MAX_RISK_SOURCE_TRACE_ROOTS_V2",
    "MAX_RISK_TEXT_BYTES_V2",
    "RISK_ASSESSMENT_RECORD_SCHEMA_V2",
    "RISK_GENESIS_SNAPSHOT_ROOT_V2",
    "RISK_GENESIS_TRANSITION_ID_V2",
    "RISK_STATE_ADVANCE_REQUEST_SCHEMA_V2",
    "RISK_STATE_SCHEMA_V2",
    "RISK_STATE_SNAPSHOT_SCHEMA_V2",
    "RISK_THRESHOLD_SNAPSHOT_SCHEMA_V2",
    "RiskAssessmentRecordV2",
    "RiskBand",
    "RiskStateAdvanceRequestV2",
    "RiskStateSnapshotV2",
    "RiskThresholdSnapshotV2",
    "VerifiedRiskSourceV2",
    "VerifiedRiskStateV2",
    "advance_risk_state_v2",
    "open_risk_authority_session_v2",
    "prepare_risk_state_advance_v2",
    "rehydrate_risk_state_v2",
    "require_current_risk_state_v2",
    "risk_state_is_current_v2",
    "risk_state_stream_ref_v2",
    "risk_state_transition_id_v2",
    "verify_risk_state_request_source_v2",
]
