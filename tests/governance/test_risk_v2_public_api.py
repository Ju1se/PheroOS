from __future__ import annotations

import pickle

import pytest

from pheroos.governance import risk_v2


EXPECTED = {
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
}


def test_risk_v2_public_module_is_exact_and_canonically_owned() -> None:
    assert set(risk_v2.__all__) == EXPECTED
    for name in EXPECTED - {"RiskBand"}:
        value = getattr(risk_v2, name)
        if callable(value) and not name.startswith("MAX_"):
            assert value.__module__ == "pheroos.governance.risk_v2"
    assert risk_v2.RiskBand.__module__ == "pheroos.governance.risk"


@pytest.mark.parametrize(
    "verified_type",
    (risk_v2.VerifiedRiskSourceV2, risk_v2.VerifiedRiskStateV2),
)
def test_risk_v2_verified_handles_cannot_be_constructed_or_pickled(
    verified_type: type[object],
) -> None:
    with pytest.raises(TypeError):
        verified_type()
    handle = object.__new__(verified_type)
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(handle)
