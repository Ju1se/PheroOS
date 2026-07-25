from __future__ import annotations

from pheroos.governance._risk.records import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    _validate_risk_assessment_chain_state_shape,
    _validate_risk_assessment_shape,
    _validate_threshold_snapshot_shape,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError


def risk_assessment_chain_state_payload(
    state: RiskAssessmentChainState,
) -> dict[str, object]:
    if type(state) is not RiskAssessmentChainState:
        raise GovernanceError("risk assessment chain state must be canonical")
    _validate_risk_assessment_chain_state_shape(state)
    return {
        "assurance": state.assurance,
        "authority": state.authority,
        "chain_id": state.chain_id,
        "commit_policy_root": state.commit_policy_root,
        "epoch": state.epoch,
        "expires_at_step": state.expires_at_step,
        "initialized_at_step": state.initialized_at_step,
        "issuer_id": state.issuer_id,
        "last_issued_at_step": state.last_issued_at_step,
        "latest_assessment_fingerprint": state.latest_assessment_fingerprint,
        "latest_risk_band": state.latest_risk_band,
        "manifest_root": state.manifest_root,
        "previous_state_fingerprint": state.previous_state_fingerprint,
        "profile": state.profile,
        "protocol_id": state.protocol_id,
        "provenance": state.provenance,
        "revision": state.revision,
        "risk_policy_root": state.risk_policy_root,
        "run_id": state.run_id,
        "target": state.target,
        "trace_event_id": state.trace_event_id,
    }


def risk_assessment_chain_state_fingerprint(
    state: RiskAssessmentChainState,
) -> str:
    return _risk_assessment_chain_state_snapshot(state)


def risk_assessment_payload(assessment: RiskAssessment) -> dict[str, object]:
    if type(assessment) is not RiskAssessment:
        raise GovernanceError("risk assessment must use the canonical record")
    _validate_risk_assessment_shape(assessment)
    return {
        "assessment_id": assessment.assessment_id,
        "assessment_method": assessment.assessment_method,
        "assurance": assessment.assurance,
        "authority": assessment.authority,
        "commit_policy_root": assessment.commit_policy_root,
        "epoch": assessment.epoch,
        "expires_at_step": assessment.expires_at_step,
        "issued_at_step": assessment.issued_at_step,
        "issuer_id": assessment.issuer_id,
        "manifest_root": assessment.manifest_root,
        "previous_assessment_fingerprint": (assessment.previous_assessment_fingerprint),
        "profile": assessment.profile,
        "protocol_id": assessment.protocol_id,
        "provenance": assessment.provenance,
        "rationale_codes": assessment.rationale_codes,
        "risk_band": assessment.risk_band,
        "risk_chain_id": assessment.risk_chain_id,
        "risk_chain_revision": assessment.risk_chain_revision,
        "risk_input_fingerprints": assessment.risk_input_fingerprints,
        "risk_policy_root": assessment.risk_policy_root,
        "run_id": assessment.run_id,
        "target": assessment.target,
        "trace_event_id": assessment.trace_event_id,
        "window_reset_required": assessment.window_reset_required,
        "previous_chain_state_fingerprint": (
            assessment.previous_chain_state_fingerprint
        ),
    }


def risk_assessment_fingerprint(assessment: RiskAssessment) -> str:
    return _risk_assessment_snapshot(assessment)


def commit_threshold_snapshot_payload(
    snapshot: CommitThresholdSnapshot,
) -> dict[str, object]:
    if type(snapshot) is not CommitThresholdSnapshot:
        raise GovernanceError("commit threshold must use the canonical record")
    _validate_threshold_snapshot_shape(snapshot)
    return {
        "assurance": snapshot.assurance,
        "authority": snapshot.authority,
        "commit_policy_root": snapshot.commit_policy_root,
        "epoch": snapshot.epoch,
        "executable_outcomes": snapshot.executable_outcomes,
        "expires_at_step": snapshot.expires_at_step,
        "issued_at_step": snapshot.issued_at_step,
        "issuer_id": snapshot.issuer_id,
        "manifest_root": snapshot.manifest_root,
        "maximum_counterevidence": snapshot.maximum_counterevidence,
        "maximum_counterevidence_ratio_ppm": (
            snapshot.maximum_counterevidence_ratio_ppm
        ),
        "minimum_assurance": snapshot.minimum_assurance,
        "minimum_margin": snapshot.minimum_margin,
        "minimum_positive_evidence": snapshot.minimum_positive_evidence,
        "minimum_source_diversity": snapshot.minimum_source_diversity,
        "minimum_support_clusters": snapshot.minimum_support_clusters,
        "minimum_support_ratio_ppm": snapshot.minimum_support_ratio_ppm,
        "profile": snapshot.profile,
        "protocol_id": snapshot.protocol_id,
        "provenance": snapshot.provenance,
        "publishable_outcomes": snapshot.publishable_outcomes,
        "required_challenge_categories": snapshot.required_challenge_categories,
        "risk_assessment_fingerprint": snapshot.risk_assessment_fingerprint,
        "risk_band": snapshot.risk_band,
        "risk_chain_id": snapshot.risk_chain_id,
        "risk_chain_revision": snapshot.risk_chain_revision,
        "risk_chain_state_fingerprint": snapshot.risk_chain_state_fingerprint,
        "risk_policy_root": snapshot.risk_policy_root,
        "run_id": snapshot.run_id,
        "stability_steps": snapshot.stability_steps,
        "target": snapshot.target,
        "threshold_id": snapshot.threshold_id,
        "trace_event_id": snapshot.trace_event_id,
    }


def commit_threshold_snapshot_fingerprint(
    snapshot: CommitThresholdSnapshot,
) -> str:
    return _threshold_snapshot(snapshot)


def _risk_assessment_snapshot(assessment: RiskAssessment) -> str:
    return commit_payload_fingerprint(
        risk_assessment_payload(assessment),
        schema="pheroos-risk-assessment-v1",
        profile=assessment.profile,
    )


def _risk_assessment_chain_state_snapshot(
    state: RiskAssessmentChainState,
) -> str:
    return commit_payload_fingerprint(
        risk_assessment_chain_state_payload(state),
        schema="pheroos-risk-assessment-chain-state-v1",
        profile=state.profile,
    )


def _threshold_snapshot(snapshot: CommitThresholdSnapshot) -> str:
    return commit_payload_fingerprint(
        commit_threshold_snapshot_payload(snapshot),
        schema="pheroos-commit-threshold-snapshot-v1",
        profile=snapshot.profile,
    )
