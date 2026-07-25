"""Public scoped baseline-output v2 Governance ABI.

The request carries proposals and one exact Protocol-owned manifest.  The
permission and terminal result are computed by Governance and only derive
external-action authority from current StateStore inclusion.
"""

from __future__ import annotations

from pheroos.governance._baseline_output_v2.contracts import (
    ACTION_PERMISSION_SCHEMA_V2,
    BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2,
    BASELINE_DECISION_STATE_SCHEMA_V2,
    BASELINE_EVIDENCE_STATE_SCHEMA_V2,
    BASELINE_MANIFEST_STATE_SCHEMA_V2,
    BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
    BASELINE_OUTPUT_RESULT_SCHEMA_V2,
    BASELINE_OUTPUT_STATE_SCHEMA_V2,
    BASELINE_STOP_STATE_SCHEMA_V2,
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    BaselineOutputTerminalStatusV2,
    baseline_action_permission_stream_ref_v2,
    baseline_decision_stream_ref_v2,
    baseline_evidence_stream_ref_v2,
    baseline_manifest_stream_ref_v2,
    baseline_output_result_root_v2,
    baseline_output_stream_ref_v2,
    baseline_stop_stream_ref_v2,
    baseline_verified_signal_proposal_root_v2,
)
from pheroos.governance._baseline_output_v2.operations import (
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
    recover_baseline_output_result_v2,
)
from pheroos.governance._baseline_output_v2.journey import (
    evaluate_and_commit_governed_baseline_output_v2,
)


_PUBLIC_MODULE = __name__
_NATIVE_PUBLIC_OBJECTS = (
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    BaselineOutputTerminalStatusV2,
    baseline_action_permission_stream_ref_v2,
    baseline_decision_stream_ref_v2,
    baseline_evidence_stream_ref_v2,
    baseline_manifest_stream_ref_v2,
    baseline_output_result_root_v2,
    baseline_output_stream_ref_v2,
    baseline_stop_stream_ref_v2,
    baseline_verified_signal_proposal_root_v2,
    evaluate_and_commit_baseline_output_v2,
    evaluate_and_commit_governed_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
    recover_baseline_output_result_v2,
)
for _public_object in _NATIVE_PUBLIC_OBJECTS:
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "ACTION_PERMISSION_SCHEMA_V2",
    "BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2",
    "BASELINE_DECISION_STATE_SCHEMA_V2",
    "BASELINE_EVIDENCE_STATE_SCHEMA_V2",
    "BASELINE_MANIFEST_STATE_SCHEMA_V2",
    "BASELINE_OUTPUT_REQUEST_SCHEMA_V2",
    "BASELINE_OUTPUT_RESULT_SCHEMA_V2",
    "BASELINE_OUTPUT_STATE_SCHEMA_V2",
    "BASELINE_STOP_STATE_SCHEMA_V2",
    "ActionPermissionDispositionV2",
    "ActionPermissionV2",
    "BaselineOutputActionDispositionV2",
    "BaselineOutputDeliveryDispositionV2",
    "BaselineOutputRequestV2",
    "BaselineOutputResultV2",
    "BaselineOutputTerminalStatusV2",
    "baseline_action_permission_stream_ref_v2",
    "baseline_decision_stream_ref_v2",
    "baseline_evidence_stream_ref_v2",
    "baseline_manifest_stream_ref_v2",
    "baseline_output_result_root_v2",
    "baseline_output_stream_ref_v2",
    "baseline_stop_stream_ref_v2",
    "baseline_verified_signal_proposal_root_v2",
    "evaluate_and_commit_baseline_output_v2",
    "evaluate_and_commit_governed_baseline_output_v2",
    "issue_action_permission_v2",
    "open_baseline_output_authority_session_v2",
    "recover_baseline_output_result_v2",
]
