from __future__ import annotations

"""Stable public facade for the governed risk and threshold ABI."""

from pheroos.governance._risk.chain import (
    initialize_risk_assessment_chain,
    issue_risk_assessment,
    risk_assessment_chain_state_is_authoritative,
    risk_assessment_chain_state_is_current,
    risk_assessment_is_authoritative,
    risk_assessment_is_latest,
    risk_assessment_matches,
)
from pheroos.governance._risk.invariants import risk_policy_root
from pheroos.governance._risk.payloads import (
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_payload,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_chain_state_payload,
    risk_assessment_fingerprint,
    risk_assessment_payload,
)
from pheroos.governance._risk.records import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    RiskBand,
)
from pheroos.governance._risk.thresholds import (
    commit_threshold_snapshot_is_authoritative,
    commit_threshold_snapshot_matches,
    commit_threshold_transition_requires_reset,
    issue_commit_threshold_snapshot,
    risk_transition_is_monotonic,
)


_PUBLIC_MODULE = __name__
for _public_object in (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    RiskBand,
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_is_authoritative,
    commit_threshold_snapshot_matches,
    commit_threshold_snapshot_payload,
    commit_threshold_transition_requires_reset,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_chain_state_is_authoritative,
    risk_assessment_chain_state_is_current,
    risk_assessment_chain_state_payload,
    risk_assessment_fingerprint,
    risk_assessment_is_authoritative,
    risk_assessment_is_latest,
    risk_assessment_matches,
    risk_assessment_payload,
    risk_policy_root,
    risk_transition_is_monotonic,
):
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "CommitThresholdSnapshot",
    "RiskAssessment",
    "RiskAssessmentChainState",
    "RiskBand",
    "commit_threshold_snapshot_fingerprint",
    "commit_threshold_snapshot_is_authoritative",
    "commit_threshold_snapshot_matches",
    "commit_threshold_snapshot_payload",
    "commit_threshold_transition_requires_reset",
    "initialize_risk_assessment_chain",
    "issue_commit_threshold_snapshot",
    "issue_risk_assessment",
    "risk_assessment_chain_state_fingerprint",
    "risk_assessment_chain_state_is_authoritative",
    "risk_assessment_chain_state_is_current",
    "risk_assessment_chain_state_payload",
    "risk_assessment_fingerprint",
    "risk_assessment_is_authoritative",
    "risk_assessment_is_latest",
    "risk_assessment_matches",
    "risk_assessment_payload",
    "risk_policy_root",
    "risk_transition_is_monotonic",
]
