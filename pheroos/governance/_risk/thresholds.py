from __future__ import annotations

from pheroos.governance._commit_validation import (
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._risk.chain import (
    risk_assessment_is_authoritative,
    risk_assessment_is_latest,
    risk_assessment_matches,
)
from pheroos.governance._risk.invariants import (
    _risk_band_values,
    _same_commit_scope,
)
from pheroos.governance._risk.payloads import (
    _threshold_snapshot,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance._risk.records import (
    _RISK_ORDER,
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    _threshold_values,
    _validate_threshold_snapshot_shape,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
    RiskBandPolicy,
)


_COMMIT_THRESHOLD_ISSUANCE = object()


def issue_commit_threshold_snapshot(
    assessment: RiskAssessment,
    *,
    chain_state: RiskAssessmentChainState,
    threshold_id: str,
    commit_policy: CollectiveCommitPolicy,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> CommitThresholdSnapshot:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("commit threshold issuance requires governance authority")
    if not risk_assessment_is_latest(
        assessment,
        chain_state=chain_state,
    ):
        raise GovernanceError(
            "commit threshold issuance requires the authoritative latest risk assessment/state"
        )
    current = require_commit_step(current_step, "commit threshold current_step")
    if not risk_assessment_matches(
        assessment,
        chain_state=chain_state,
        commit_policy=commit_policy,
        profile=assessment.profile,
        assurance=assessment.assurance,
        manifest_root=assessment.manifest_root,
        commit_policy_root=assessment.commit_policy_root,
        protocol_id=assessment.protocol_id,
        run_id=assessment.run_id,
        target=assessment.target,
        epoch=assessment.epoch,
        current_step=current,
    ):
        raise GovernanceError(
            "commit threshold risk assessment is stale or policy-mismatched"
        )
    band = commit_policy.risk_bands[assessment.risk_band.value]
    if type(band) is not RiskBandPolicy:  # guarded by policy validation
        raise GovernanceError("commit threshold risk band is not canonical")

    snapshot = CommitThresholdSnapshot(
        threshold_id=require_commit_text(
            threshold_id,
            "commit threshold threshold_id",
        ),
        profile=assessment.profile,
        assurance=assessment.assurance,
        manifest_root=assessment.manifest_root,
        commit_policy_root=assessment.commit_policy_root,
        risk_policy_root=assessment.risk_policy_root,
        risk_chain_id=chain_state.chain_id,
        risk_chain_revision=chain_state.revision,
        risk_chain_state_fingerprint=(
            risk_assessment_chain_state_fingerprint(chain_state)
        ),
        protocol_id=assessment.protocol_id,
        run_id=assessment.run_id,
        target=assessment.target,
        epoch=assessment.epoch,
        risk_assessment_fingerprint=risk_assessment_fingerprint(assessment),
        risk_band=assessment.risk_band,
        minimum_positive_evidence=band.minimum_positive_evidence,
        maximum_counterevidence=band.maximum_counterevidence,
        maximum_counterevidence_ratio_ppm=(band.maximum_counterevidence_ratio_ppm),
        minimum_support_clusters=band.minimum_support_clusters,
        minimum_support_ratio_ppm=band.minimum_support_ratio_ppm,
        minimum_source_diversity=band.minimum_source_diversity,
        minimum_margin=band.minimum_margin,
        stability_steps=band.stability_steps,
        required_challenge_categories=tuple(band.required_challenge_categories),
        minimum_assurance=CommitAssurance(band.minimum_assurance),
        publishable_outcomes=tuple(band.publishable_outcomes),
        executable_outcomes=tuple(band.executable_outcomes),
        issuer_id=require_commit_text(issuer_id, "commit threshold issuer_id"),
        authority=authority,
        issued_at_step=current,
        expires_at_step=assessment.expires_at_step,
        provenance=require_commit_text(provenance, "commit threshold provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit threshold trace_event_id",
        ),
    )
    object.__setattr__(
        snapshot,
        "_issuance",
        (_COMMIT_THRESHOLD_ISSUANCE, _threshold_snapshot(snapshot)),
    )
    return snapshot


def commit_threshold_snapshot_is_authoritative(snapshot: object) -> bool:
    if type(snapshot) is not CommitThresholdSnapshot:
        return False
    try:
        _validate_threshold_snapshot_shape(snapshot)
        issuance = snapshot._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COMMIT_THRESHOLD_ISSUANCE
            and issuance[1] == _threshold_snapshot(snapshot)
        )
    except Exception:
        return False


def commit_threshold_snapshot_matches(
    snapshot: CommitThresholdSnapshot | None,
    *,
    assessment: RiskAssessment,
    chain_state: RiskAssessmentChainState,
    commit_policy: CollectiveCommitPolicy,
    current_step: int,
) -> bool:
    try:
        current = require_commit_step(current_step, "commit threshold current_step")
        if not risk_assessment_matches(
            assessment,
            chain_state=chain_state,
            commit_policy=commit_policy,
            profile=assessment.profile,
            assurance=assessment.assurance,
            manifest_root=assessment.manifest_root,
            commit_policy_root=assessment.commit_policy_root,
            protocol_id=assessment.protocol_id,
            run_id=assessment.run_id,
            target=assessment.target,
            epoch=assessment.epoch,
            current_step=current,
        ):
            return False
        if not commit_threshold_snapshot_is_authoritative(snapshot) or snapshot is None:
            return False
        if not _same_commit_scope(snapshot, assessment):
            return False
        if not _same_commit_scope(snapshot, chain_state):
            return False
        if (
            snapshot.risk_policy_root != assessment.risk_policy_root
            or snapshot.risk_policy_root != chain_state.risk_policy_root
            or snapshot.risk_chain_id != chain_state.chain_id
            or snapshot.risk_chain_revision != chain_state.revision
            or snapshot.risk_chain_state_fingerprint
            != risk_assessment_chain_state_fingerprint(chain_state)
            or snapshot.risk_assessment_fingerprint
            != risk_assessment_fingerprint(assessment)
            or snapshot.risk_band is not assessment.risk_band
            or not (snapshot.issued_at_step <= current < snapshot.expires_at_step)
        ):
            return False
        band = commit_policy.risk_bands[assessment.risk_band.value]
        return _threshold_values(snapshot) == _risk_band_values(band)
    except (GovernanceError, KeyError, ValueError):
        return False


def risk_transition_is_monotonic(
    previous: RiskAssessment,
    current: RiskAssessment,
) -> bool:
    if not (
        risk_assessment_is_authoritative(previous)
        and risk_assessment_is_authoritative(current)
    ):
        return False
    return bool(
        _same_commit_scope(previous, current)
        and previous.risk_policy_root == current.risk_policy_root
        and previous.risk_chain_id == current.risk_chain_id
        and current.risk_chain_revision == previous.risk_chain_revision + 1
        and current.previous_assessment_fingerprint
        == risk_assessment_fingerprint(previous)
        and current.issued_at_step > previous.issued_at_step
        and current.expires_at_step == previous.expires_at_step
        and _RISK_ORDER[current.risk_band] >= _RISK_ORDER[previous.risk_band]
        and current.window_reset_required
        is (current.risk_band is not previous.risk_band)
    )


def commit_threshold_transition_requires_reset(
    previous: CommitThresholdSnapshot,
    current: CommitThresholdSnapshot,
) -> bool:
    if not (
        commit_threshold_snapshot_is_authoritative(previous)
        and commit_threshold_snapshot_is_authoritative(current)
    ):
        raise GovernanceError("threshold transition requires authoritative snapshots")
    for name in ("protocol_id", "run_id", "target"):
        if getattr(previous, name) != getattr(current, name):
            raise GovernanceError("threshold transition scope mismatch")
    return bool(
        previous.epoch != current.epoch
        or previous.manifest_root != current.manifest_root
        or previous.commit_policy_root != current.commit_policy_root
        or previous.risk_policy_root != current.risk_policy_root
        or previous.risk_band is not current.risk_band
        or _threshold_values(previous) != _threshold_values(current)
    )
