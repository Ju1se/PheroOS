"""Authority-envelope and prior-trace preflight validation."""

from __future__ import annotations

from typing import TypedDict, cast

from pheroos.governance._hybrid.request import HybridCommitEvaluationRequest
from pheroos.governance.commit import (
    CommitAssessment,
    CommitEvaluationContext,
    commit_assessment_is_authoritative,
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
)
from pheroos.governance.commit_state import (
    CommitReplayState,
    CommitWindowState,
    commit_replay_state_is_current,
    commit_window_state_is_current,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_is_authoritative,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_chain_state_is_current,
    risk_assessment_fingerprint,
    risk_assessment_is_authoritative,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
    eligible_membership_epoch_state_fingerprint,
    eligible_membership_epoch_state_is_current,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_is_authoritative,
    support_lease_replay_state_fingerprint,
    support_lease_replay_state_is_current,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.trace import TraceEvent
from pheroos.trace.commit_contracts import replay_commit_trace


class _AuthorityHeads(TypedDict):
    risk_chain_state: RiskAssessmentChainState
    risk_assessment: RiskAssessment
    threshold_snapshot: CommitThresholdSnapshot
    membership_snapshot: EligiblePrincipalSnapshot
    membership_epoch_state: EligibleMembershipEpochState
    support_replay_state: SupportLeaseReplayState


class _AuthorityEnvelope(_AuthorityHeads):
    assessment: CommitAssessment
    context: CommitEvaluationContext
    window_state: CommitWindowState
    replay_state: CommitReplayState
    commit_policy: CollectiveCommitPolicy


def _establish_authority_envelope(
    request: HybridCommitEvaluationRequest,
) -> _AuthorityEnvelope:
    assessment = request.commit_assessment
    context = request.context
    window_state = request.window_state
    replay_state = request.replay_state
    policy = request.commit_policy
    if type(assessment) is not CommitAssessment or not (
        commit_assessment_is_authoritative(assessment)
    ):
        raise GovernanceError("CommitAssessment authority is unavailable")
    if type(context) is not CommitEvaluationContext or not (
        commit_evaluation_context_is_authoritative(context)
    ):
        raise GovernanceError("CommitEvaluationContext authority is unavailable")
    if type(window_state) is not CommitWindowState or not (
        commit_window_state_is_current(window_state)
    ):
        raise GovernanceError("commit window current authority is unavailable")
    if type(replay_state) is not CommitReplayState or not (
        commit_replay_state_is_current(replay_state)
    ):
        raise GovernanceError("commit replay current authority is unavailable")
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("collective commit policy is not canonical")
    if request.current_step < window_state.last_evaluated_step:
        raise GovernanceError("evaluation step precedes the commit window")
    exact = {
        "profile": assessment.profile,
        "assurance": assessment.assurance,
        "manifest_root": assessment.manifest_root,
        "commit_policy_root": assessment.commit_policy_root,
        "protocol_id": assessment.protocol_id,
        "run_id": assessment.run_id,
        "target": assessment.target,
        "epoch": assessment.epoch,
    }
    for source_name, source in (
        ("context", context),
        ("window", window_state),
    ):
        for name, expected in exact.items():
            if getattr(source, name) != expected:
                raise GovernanceError(
                    f"{source_name} {name} does not match CommitAssessment authority"
                )
    replay_exact = {
        name: exact[name]
        for name in (
            "profile",
            "assurance",
            "manifest_root",
            "commit_policy_root",
            "protocol_id",
            "run_id",
        )
    }
    for name, expected in replay_exact.items():
        if getattr(replay_state, name) != expected:
            raise GovernanceError(
                f"replay {name} does not match CommitAssessment authority"
            )
    if context.context_id == "" or (
        commit_evaluation_context_fingerprint(context) != assessment.context_fingerprint
    ):
        raise GovernanceError("assessment does not bind the supplied context")
    if (
        policy.assurance != assessment.assurance.value
        or policy.target != assessment.target
    ):
        raise GovernanceError(
            "commit policy assurance/target does not match assessment"
        )
    if (
        commit_policy_fingerprint(policy, profile=assessment.profile)
        != assessment.commit_policy_root
    ):
        raise GovernanceError("commit policy root does not match assessment")
    heads = _validate_authority_heads(request, assessment=assessment)
    return {
        "assessment": assessment,
        "context": context,
        "window_state": window_state,
        "replay_state": replay_state,
        "commit_policy": policy,
        **heads,
    }


def _validate_authority_heads(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
) -> _AuthorityHeads:
    risk_chain_state = request.risk_chain_state
    risk_assessment = request.risk_assessment
    threshold_snapshot = request.threshold_snapshot
    membership_snapshot = request.membership_snapshot
    membership_epoch_state = request.membership_epoch_state
    support_replay_state = request.support_replay_state
    if type(risk_chain_state) is not RiskAssessmentChainState or not (
        risk_assessment_chain_state_is_current(risk_chain_state)
    ):
        raise GovernanceError("risk chain current head is unavailable")
    if type(risk_assessment) is not RiskAssessment or not (
        risk_assessment_is_authoritative(risk_assessment)
    ):
        raise GovernanceError("risk assessment authority is unavailable")
    if type(threshold_snapshot) is not CommitThresholdSnapshot or not (
        commit_threshold_snapshot_is_authoritative(threshold_snapshot)
    ):
        raise GovernanceError("threshold snapshot authority is unavailable")
    if type(membership_snapshot) is not EligiblePrincipalSnapshot or not (
        eligible_principal_snapshot_is_authoritative(membership_snapshot)
    ):
        raise GovernanceError("membership snapshot authority is unavailable")
    if type(membership_epoch_state) is not EligibleMembershipEpochState or not (
        eligible_membership_epoch_state_is_current(membership_epoch_state)
    ):
        raise GovernanceError("membership epoch current head is unavailable")
    if type(support_replay_state) is not SupportLeaseReplayState or not (
        support_lease_replay_state_is_current(support_replay_state)
    ):
        raise GovernanceError("support replay current head is unavailable")
    exact_roots = {
        "risk_chain_state_fingerprint": risk_assessment_chain_state_fingerprint(
            risk_chain_state
        ),
        "risk_assessment_fingerprint": risk_assessment_fingerprint(risk_assessment),
        "threshold_fingerprint": commit_threshold_snapshot_fingerprint(
            threshold_snapshot
        ),
        "membership_snapshot_fingerprint": (
            eligible_principal_snapshot_fingerprint(membership_snapshot)
        ),
        "membership_epoch_state_fingerprint": (
            eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        ),
        "support_replay_state_fingerprint": (
            support_lease_replay_state_fingerprint(support_replay_state)
        ),
    }
    for name, observed in exact_roots.items():
        if getattr(assessment, name) != observed:
            raise GovernanceError(f"authority head {name} does not match assessment")
    return {
        "risk_chain_state": risk_chain_state,
        "risk_assessment": risk_assessment,
        "threshold_snapshot": threshold_snapshot,
        "membership_snapshot": membership_snapshot,
        "membership_epoch_state": membership_epoch_state,
        "support_replay_state": support_replay_state,
    }


def _validated_prior_trace(
    request: HybridCommitEvaluationRequest,
    *,
    assessment: CommitAssessment,
) -> tuple[TraceEvent, ...]:
    runtime_events = tuple(request.prior_trace_events)
    if not runtime_events or any(
        type(item) is not TraceEvent for item in runtime_events
    ):
        raise GovernanceError(
            "authoritative Hybrid Commit evaluation requires prior TraceEvent lineage"
        )
    events = tuple(cast(TraceEvent, item) for item in runtime_events)
    replay = replay_commit_trace(events, require_complete=False)
    expected_identity = (
        assessment.protocol_id,
        assessment.run_id,
        assessment.target,
        assessment.profile,
        assessment.assurance.value,
        assessment.epoch,
    )
    observed_identity = (
        replay.protocol_id,
        replay.run_id,
        replay.target,
        replay.profile,
        replay.assurance,
        replay.epoch,
    )
    if observed_identity != expected_identity:
        raise GovernanceError("prior trace identity does not match CommitAssessment")
    if replay.complete or replay.outcome_ref or replay.output_ref:
        raise GovernanceError("prior trace already contains a terminal result")
    if replay.last_step > request.current_step:
        raise GovernanceError("prior trace is from a future logical step")
    by_type: dict[str, list[TraceEvent]] = {}
    for event in events:
        if event.event_type in {
            "principal_attested",
            "principal_verified",
            "risk_assessed",
            "membership_snapshot",
            "observation_recorded",
            "observation_verified",
            "counterevidence_disposed",
            "challenge_recorded",
            "evidence_bound",
            "support_lease_issued",
            "support_lease_revoked",
            "support_lease_expired",
            "support_equivocation",
            "stop_resolution_verified",
            "action_permission_issued",
            "commit_metrics",
            "commit_window_advanced",
            "commit_window_reset",
            "quorum_pending",
            "commit_certificate_issued",
            "quorum_witness",
            "commit_provisional",
            "certificate_conflict",
        }:
            by_type.setdefault(event.event_type, []).append(event)
    required_types = {
        "principal_attested",
        "principal_verified",
        "risk_assessed",
        "membership_snapshot",
        "observation_recorded",
        "observation_verified",
        "evidence_bound",
        "support_lease_issued",
        "stop_resolution_verified",
        "action_permission_issued",
    }
    missing = sorted(required_types - set(by_type))
    if missing:
        raise GovernanceError(
            "prior trace lacks required authority lineage: " + ", ".join(missing)
        )
    risk_ref = risk_assessment_fingerprint(
        cast(RiskAssessment, request.risk_assessment)
    )
    membership_ref = eligible_principal_snapshot_fingerprint(
        cast(EligiblePrincipalSnapshot, request.membership_snapshot)
    )
    stop_ref = assessment.stop_resolution_fingerprint
    permission_ref = assessment.permission_fingerprint
    exact_refs = {
        "risk_assessed": risk_ref,
        "membership_snapshot": membership_ref,
        "stop_resolution_verified": stop_ref,
        "action_permission_issued": permission_ref,
    }
    for event_type, expected_ref in exact_refs.items():
        if not any(
            event.lineage["record_ref"] == expected_ref for event in by_type[event_type]
        ):
            raise GovernanceError(
                f"prior {event_type} trace does not bind the current authority head"
            )
    evidence_refs = {
        item.evidence_binding_fingerprint for item in assessment.candidate_metrics
    }
    observed_evidence = {
        event.lineage["record_ref"] for event in by_type["evidence_bound"]
    }
    if not evidence_refs.issubset(observed_evidence):
        raise GovernanceError("prior evidence trace does not cover assessed candidates")
    return events


__all__: list[str] = []
