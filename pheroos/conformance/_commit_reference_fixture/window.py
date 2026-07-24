"""Private Commit reference fixture window handlers."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.certificate import (
    issue_local_commit_receipt,
    output_payload_fingerprint,
)

from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitAssessment,
    CommitEvaluationContext,
    build_commit_replay_receipts,
    issue_commit_evaluation_context,
)

from pheroos.governance.commit_state import (
    CommitReplayState,
    CommitWindowState,
    advance_commit_window_state,
    initialize_commit_window_state,
    record_commit_replay_receipts,
)

from pheroos.governance.permission import (
    ActionPermission,
)

from pheroos.governance.stop_signal import (
    StopResolutionVerification,
)

from pheroos.governance.support_lease import (
    SupportLease,
    SupportLeaseReplayState,
)

from pheroos.protocol.commit_models import CommitAction

from pheroos.conformance._commit_reference_fixture.models import (
    ReferenceScenario,
    ReferenceStableCommit,
)

from pheroos.conformance._commit_reference_fixture.decision import (
    assess_reference_scenario,
    issue_reference_action_gates,
)

from pheroos.conformance._commit_reference_fixture.state import (
    _REFERENCE_STABLE_FIXTURES,
    _REFERENCE_STABLE_FIXTURES_LOCK,
    _REFERENCE_WINDOW_FIXTURES,
    _REFERENCE_WINDOW_FIXTURES_LOCK,
)


def initialize_reference_window(
    scenario: ReferenceScenario,
) -> CommitWindowState:
    """Return the immutable historical initial window for one scenario."""

    with _REFERENCE_WINDOW_FIXTURES_LOCK:
        cached = _REFERENCE_WINDOW_FIXTURES.get(scenario.namespace)
        if cached is not None:
            return cached
        window = initialize_commit_window_state(
            commit_policy=collective_commit_policy(scenario.policy),
            profile=scenario.profile,
            assurance=scenario.assurance,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            protocol_id=scenario.protocol_id,
            run_id=scenario.run_id,
            target=scenario.target,
            epoch=scenario.epoch,
            risk_assessment_root=(scenario.context.risk_assessment_fingerprint),
            membership_root=scenario.context.membership_root,
            threshold_snapshot=scenario.threshold,
            current_step=4,
            issuer_id="governance:tck:window",
            authority=AuthorityLevel.GOVERNANCE,
            provenance=f"urn:pheroos:tck:{scenario.namespace}:window",
            trace_event_id=f"trace:{scenario.namespace}:window",
        )
        _REFERENCE_WINDOW_FIXTURES[scenario.namespace] = window
        return window


def rotate_reference_context(
    scenario: ReferenceScenario,
    *,
    candidate_inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    current_step: int,
    suffix: str,
    support_replay_state: SupportLeaseReplayState | None = None,
) -> tuple[
    CommitEvaluationContext,
    CommitReplayState,
    SupportLeaseReplayState,
    StopResolutionVerification,
    ActionPermission,
]:
    """Append scoped authority inputs and issue a new immutable context head."""

    selected_support_replay = support_replay_state or scenario.support_replay_state
    replay = record_commit_replay_receipts(
        scenario.replay_state,
        current_step=current_step,
        receipts=build_commit_replay_receipts(candidate_inputs, leases),
    )
    context = issue_commit_evaluation_context(
        scenario.manifest,
        context_id=f"context:{scenario.namespace}:{suffix}",
        profile=scenario.profile,
        assurance=scenario.assurance,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        candidate_claims=scenario.claims,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=replay,
        support_replay_state=selected_support_replay,
        issuer_id="governance:tck:commit-context",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:context:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:context:{suffix}",
    )
    stop, permission = issue_reference_action_gates(
        scenario.namespace,
        context=context,
        action=CommitAction.COMMIT,
        blocked=False,
        current_step=current_step,
        expires_at_step=min(30, current_step + 10),
        suffix=f"context-{suffix}",
    )
    return context, replay, selected_support_replay, stop, permission


def build_reference_stable_commit(
    scenario: ReferenceScenario,
    *,
    variant: str = "stable",
) -> ReferenceStableCommit:
    fixture_key = (scenario.namespace, variant)
    with _REFERENCE_STABLE_FIXTURES_LOCK:
        cached = _REFERENCE_STABLE_FIXTURES.get(fixture_key)
        if cached is not None:
            return cached
    window = initialize_reference_window(scenario)
    required = scenario.threshold.stability_steps
    assessments: list[CommitAssessment] = []
    for offset in range(1, required + 1):
        step = 4 + offset
        assessment = assess_reference_scenario(
            scenario,
            step=step,
            suffix=f"{variant}:{step}",
        )
        assessments.append(assessment)
        window = advance_commit_window_state(
            window,
            assessment=assessment,
            commit_policy=collective_commit_policy(scenario.policy),
            threshold_snapshot=scenario.threshold,
            current_step=step,
        )
    output_ref = output_payload_fingerprint(
        {
            "candidate_id": scenario.leader_id,
            "result": "declared-tck-output",
            "variant": variant,
        },
        profile=scenario.profile,
    )
    receipt = issue_local_commit_receipt(
        scenario.context,
        assessments[-1],
        window,
        commit_policy=collective_commit_policy(scenario.policy),
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        output_payload_fingerprint=output_ref,
        receipt_id=f"receipt:{scenario.namespace}:{variant}",
        issuer_id="governance:tck:receipt",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=window.last_evaluated_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:receipt:{variant}",
        trace_event_id=f"trace:{scenario.namespace}:receipt:{variant}",
    )
    stable = ReferenceStableCommit(
        scenario=scenario,
        assessments=tuple(assessments),
        window=window,
        output_fingerprint=output_ref,
        receipt=receipt,
    )
    with _REFERENCE_STABLE_FIXTURES_LOCK:
        _REFERENCE_STABLE_FIXTURES[fixture_key] = stable
    return stable
