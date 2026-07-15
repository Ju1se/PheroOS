from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import gc
from threading import Barrier
import weakref

import pytest
import tests.governance.test_commit_engine as commit_engine_tests

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitEvaluationError,
    CommitReasonCode,
    assess_optimal_commit,
    build_commit_replay_receipts,
    commit_assessment_fingerprint,
    commit_evaluation_context_fingerprint,
    issue_commit_evaluation_context,
)
from pheroos.governance.commit_state import (
    CommitReplayState,
    CommitWindowState,
    ReplayNamespace,
    ReplayReceipt,
    _window_reset_reason,
    advance_commit_window_state,
    commit_replay_state_fingerprint,
    commit_replay_state_is_authoritative,
    commit_window_ready,
    commit_window_state_fingerprint,
    commit_window_state_is_authoritative,
    commit_window_state_is_current,
    initialize_commit_replay_state,
    initialize_commit_window_state,
    record_commit_replay_receipts,
    restart_commit_window_epoch,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.evidence_binding import bind_evidence
from pheroos.governance.permission import issue_action_permission
from pheroos.governance.risk import (
    RiskBand,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
)
from pheroos.governance.stop_signal import StopResolution, verify_stop_resolution
from pheroos.protocol.commit_models import CommitAction, CommitAssurance
from tests.governance.test_commit_engine import (
    ASSURANCE,
    EPOCH,
    PROFILE,
    PROTOCOL_ID,
    TARGET,
    _fingerprint,
    _observation,
    _scenario,
)


def _window(scenario, *, current_step: int = 4) -> CommitWindowState:
    return initialize_commit_window_state(
        commit_policy=scenario.policy,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=scenario.run_id,
        target=TARGET,
        epoch=EPOCH,
        risk_assessment_root=scenario.context.risk_assessment_fingerprint,
        membership_root=scenario.context.membership_root,
        threshold_snapshot=scenario.threshold,
        current_step=current_step,
        issuer_id="governance:window",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:window:{scenario.run_id}",
        trace_event_id=f"trace:window:{scenario.run_id}",
    )


def _gates(scenario, *, context, step: int, blocked: bool = False):
    context_ref = commit_evaluation_context_fingerprint(context)
    stop = verify_stop_resolution(
        StopResolution(
            target=TARGET,
            action=CommitAction.COMMIT,
            blocked=blocked,
            reason="hard_stop" if blocked else "all_hard_stops_resolved",
        ),
        resolution_id=f"stop:{scenario.run_id}:{step}:{blocked}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=scenario.run_id,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref="",
        resolved_stop_root=_fingerprint(
            f"stop-root:{scenario.run_id}:{step}:{blocked}"
        ),
        verifier_id="governance:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        expires_at_step=12,
        provenance=f"urn:test:stop:{scenario.run_id}:{step}",
        trace_event_id=f"trace:stop:{scenario.run_id}:{step}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{scenario.run_id}:{step}:{blocked}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=scenario.run_id,
        target=TARGET,
        action=CommitAction.COMMIT,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref="",
        allowed=not blocked,
        reason_codes=("denied",) if blocked else ("policy_authorized",),
        issuer_id="governance:permission",
        policy_ref="policy:commit-action-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        expires_at_step=12,
        provenance=f"urn:test:permission:{scenario.run_id}:{step}",
        trace_event_id=f"trace:permission:{scenario.run_id}:{step}",
    )
    return stop, permission


def _assessment(
    scenario,
    *,
    step: int,
    context=None,
    candidate_inputs=None,
    replay_state=None,
    risk_chain_state=None,
    risk_assessment=None,
    threshold=None,
    stop_resolution=None,
    permission=None,
    suffix: str = "",
):
    context = scenario.context if context is None else context
    replay_state = scenario.replay_state if replay_state is None else replay_state
    risk_chain_state = (
        scenario.risk_chain_state
        if risk_chain_state is None
        else risk_chain_state
    )
    risk_assessment = (
        scenario.risk_assessment
        if risk_assessment is None
        else risk_assessment
    )
    threshold = scenario.threshold if threshold is None else threshold
    if stop_resolution is None or permission is None:
        if context is scenario.context and step < 10:
            stop_resolution = scenario.stop_resolution
            permission = scenario.permission
        else:
            stop_resolution, permission = _gates(
                scenario,
                context=context,
                step=max(5, step - 1),
            )
    return assess_optimal_commit(
        context,
        manifest=scenario.manifest,
        candidate_inputs=(
            scenario.candidate_inputs
            if candidate_inputs is None
            else candidate_inputs
        ),
        leases=scenario.leases,
        revocations=(),
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=replay_state,
        support_replay_state=scenario.support_replay_state,
        stop_resolution=stop_resolution,
        commit_permission=permission,
        assessment_id=f"assessment:{scenario.run_id}:{step}:{suffix}",
        issuer_id="governance:commit",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:test:assessment:{scenario.run_id}:{step}:{suffix}",
        trace_event_id=f"trace:assessment:{scenario.run_id}:{step}:{suffix}",
    )


def _advance(
    state: CommitWindowState,
    scenario,
    *,
    step: int,
    assessment=None,
    threshold=None,
) -> CommitWindowState:
    assessment = (
        _assessment(scenario, step=step)
        if assessment is None
        else assessment
    )
    return advance_commit_window_state(
        state,
        assessment=assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold if threshold is None else threshold,
        current_step=step,
    )


def _assessment_with_extra_leader_evidence(scenario, *, step: int):
    leader_input = next(
        item
        for item in scenario.candidate_inputs
        if item.candidate_id == scenario.leader_id
    )
    extra = _observation(
        scenario.leader_principal,
        candidate_id=leader_input.candidate_id,
        claim=leader_input.claim_fingerprint,
        index=71,
        manifest_root=scenario.context.manifest_root,
        policy_root=scenario.context.commit_policy_root,
        policy=scenario.policy,
        run_id=scenario.run_id,
    )
    positives = (*leader_input.positive_observations, extra)
    binding = bind_evidence(
        evidence_id=f"evidence:{scenario.run_id}:leader:expanded",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=scenario.run_id,
        target=TARGET,
        candidate_id=leader_input.candidate_id,
        claim_fingerprint=leader_input.claim_fingerprint,
        epoch=EPOCH,
        positive_observations=positives,
        counter_observations=leader_input.counter_observations,
        dispositions=leader_input.dispositions,
        challenges=leader_input.challenges,
        issuer_id="governance:evidence-binding",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:test:evidence-expanded:{scenario.run_id}",
        trace_event_id=f"trace:evidence-expanded:{scenario.run_id}",
    )
    expanded = CandidateCommitInput(
        candidate_id=leader_input.candidate_id,
        claim_fingerprint=leader_input.claim_fingerprint,
        evidence_binding=binding,
        positive_observations=positives,
        counter_observations=leader_input.counter_observations,
        dispositions=leader_input.dispositions,
        challenges=leader_input.challenges,
    )
    inputs = tuple(
        expanded if item.candidate_id == scenario.leader_id else item
        for item in scenario.candidate_inputs
    )
    replay = record_commit_replay_receipts(
        scenario.replay_state,
        current_step=step,
        receipts=build_commit_replay_receipts(inputs, scenario.leases),
    )
    context = issue_commit_evaluation_context(
        scenario.manifest,
        context_id=f"context:{scenario.run_id}:expanded",
        profile=PROFILE,
        assurance=ASSURANCE,
        run_id=scenario.run_id,
        target=TARGET,
        epoch=EPOCH,
        candidate_claims={
            item.candidate_id: item.claim_fingerprint
            for item in scenario.context.candidate_claims
        },
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=replay,
        support_replay_state=scenario.support_replay_state,
        issuer_id="governance:commit-context",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:test:context-expanded:{scenario.run_id}",
        trace_event_id=f"trace:context-expanded:{scenario.run_id}",
    )
    stop, permission = _gates(scenario, context=context, step=step)
    assessment = _assessment(
        scenario,
        step=step,
        context=context,
        candidate_inputs=inputs,
        replay_state=replay,
        stop_resolution=stop,
        permission=permission,
        suffix="expanded-evidence",
    )
    return assessment, replay, context, inputs


def test_window_uses_policy_threshold_and_consecutive_assessments() -> None:
    scenario = _scenario()
    initial = _window(scenario)
    first_assessment = _assessment(scenario, step=5)
    first = _advance(
        initial,
        scenario,
        step=5,
        assessment=first_assessment,
    )
    second_assessment = _assessment(scenario, step=6)
    second = _advance(
        first,
        scenario,
        step=6,
        assessment=second_assessment,
    )

    assert initial.minimum_stability_steps == scenario.threshold.stability_steps == 2
    assert first.window_count == 1
    assert second.window_count == 2
    assert second.ordered_assessment_refs == (
        commit_assessment_fingerprint(first_assessment),
        commit_assessment_fingerprint(second_assessment),
    )
    assert commit_window_ready(second)
    assert second.absolute_deadline_step == initial.absolute_deadline_step == 12
    assert second.absolute_run_deadline_step == initial.absolute_run_deadline_step == 16


def test_window_init_is_single_strong_idempotent_concurrent_and_gc_retained() -> None:
    scenario = _scenario()
    initial = _window(scenario)
    assert _window(scenario) is initial

    with ThreadPoolExecutor(max_workers=8) as pool:
        states = tuple(pool.map(lambda _: _window(scenario), range(32)))
    assert all(item is initial for item in states)

    retained = weakref.ref(initial)
    expected_id = id(initial)
    del states
    del initial
    gc.collect()
    reinitialized = _window(scenario)
    assert retained() is reinitialized
    assert id(reinitialized) == expected_id

    with pytest.raises(GovernanceError, match="different base"):
        initialize_commit_window_state(
            commit_policy=scenario.policy,
            profile=PROFILE,
            assurance=ASSURANCE,
            manifest_root=scenario.context.manifest_root,
            commit_policy_root=scenario.context.commit_policy_root,
            protocol_id=PROTOCOL_ID,
            run_id=scenario.run_id,
            target=TARGET,
            epoch=EPOCH,
            risk_assessment_root=scenario.context.risk_assessment_fingerprint,
            membership_root=scenario.context.membership_root,
            threshold_snapshot=scenario.threshold,
            current_step=4,
            issuer_id="governance:window",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:different-base",
            trace_event_id=f"trace:window:{scenario.run_id}",
        )


def test_window_transition_is_exactly_idempotent_atomic_and_fork_free() -> None:
    scenario = _scenario()
    initial = _window(scenario)
    first_assessment = _assessment(scenario, step=5, suffix="first")
    alternate = _assessment(scenario, step=5, suffix="alternate")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = tuple(
            pool.map(
                lambda _: _advance(
                    initial,
                    scenario,
                    step=5,
                    assessment=first_assessment,
                ),
                range(32),
            )
        )
    assert all(item is results[0] for item in results)
    assert _advance(
        initial,
        scenario,
        step=5,
        assessment=first_assessment,
    ) is results[0]
    with pytest.raises(GovernanceError, match="stale or would fork"):
        _advance(
            initial,
            scenario,
            step=5,
            assessment=alternate,
        )

    race = _scenario()
    parent = _window(race)
    left = _assessment(race, step=5, suffix="race-left")
    right = _assessment(race, step=5, suffix="race-right")
    barrier = Barrier(2)

    def competing(item):
        barrier.wait()
        try:
            return _advance(parent, race, step=5, assessment=item)
        except GovernanceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        raced = tuple(pool.map(competing, (left, right)))
    assert sum(type(item) is CommitWindowState for item in raced) == 1
    assert sum(isinstance(item, GovernanceError) for item in raced) == 1


def test_step_gap_gate_failure_and_all_authority_head_changes_reset() -> None:
    scenario = _scenario()
    first = _advance(_window(scenario), scenario, step=5)
    gap = _advance(first, scenario, step=7)
    assert gap.reset_reason == "step_gap"
    assert gap.window_count == 1
    assert gap.remaining_reset_budget == 1
    assert gap.absolute_deadline_step == first.absolute_deadline_step

    blocked_stop, denied = _gates(
        scenario,
        context=scenario.context,
        step=8,
        blocked=True,
    )
    blocked_assessment = _assessment(
        scenario,
        step=8,
        stop_resolution=blocked_stop,
        permission=denied,
        suffix="blocked",
    )
    failed = _advance(
        gap,
        scenario,
        step=8,
        assessment=blocked_assessment,
    )
    assert failed.reset_reason == "gate_failure"
    assert failed.window_count == 0
    assert failed.remaining_reset_budget == 0

    # The reset classifier is intentionally independent of evidence/assessment
    # roots: only the normative authority heads reset a continuous ready window.
    fresh = first
    common = {
        "current_step": fresh.last_evaluated_step + 1,
        "ready": True,
        "leader_candidate_id": fresh.leader_candidate_id,
        "manifest_root": fresh.manifest_root,
        "commit_policy_root": fresh.commit_policy_root,
        "risk_assessment_root": fresh.risk_assessment_root,
        "membership_root": fresh.membership_root,
        "threshold_root": fresh.threshold_root,
    }
    assert _window_reset_reason(fresh, **common) == "none"
    assert _window_reset_reason(
        fresh,
        **{**common, "leader_candidate_id": "candidate:replacement"},
    ) == "leader_change"
    assert _window_reset_reason(
        fresh,
        **{**common, "commit_policy_root": _fingerprint("new-policy")},
    ) == "policy_change"
    assert _window_reset_reason(
        fresh,
        **{**common, "membership_root": _fingerprint("new-membership")},
    ) == "membership_change"
    assert _window_reset_reason(
        fresh,
        **{**common, "risk_assessment_root": _fingerprint("new-risk")},
    ) == "risk_change"
    assert _window_reset_reason(
        fresh,
        **{**common, "threshold_root": _fingerprint("new-threshold")},
    ) == "threshold_change"


def test_assessment_root_changes_do_not_reset_same_ready_leader() -> None:
    scenario = _scenario()
    first_assessment = _assessment(scenario, step=5, suffix="first")
    initial = _window(scenario)
    first = _advance(
        initial,
        scenario,
        step=5,
        assessment=first_assessment,
    )
    # Add qualified evidence, rebuild the evidence/replay/context roots, and
    # prove those mutable epistemic roots do not reset a still-ready leader.
    second_assessment, descendant_replay, successor_context, successor_inputs = (
        _assessment_with_extra_leader_evidence(
            scenario,
            step=6,
        )
    )
    assert commit_assessment_fingerprint(second_assessment) != (
        commit_assessment_fingerprint(first_assessment)
    )
    assert second_assessment.collective_evidence_root != (
        first_assessment.collective_evidence_root
    )
    second = _advance(
        first,
        scenario,
        step=6,
        assessment=second_assessment,
    )
    assert second.reset_reason == "none"
    assert second.window_count == 2

    # A replay descendant is consumed through a newly issued immutable
    # evaluation snapshot.  Neither the old context/new head pairing nor the
    # new context/old head pairing can be used as an implicit descendant
    # authorization.
    with pytest.raises(CommitEvaluationError) as stale_context:
        _assessment(
            scenario,
            step=7,
            context=scenario.context,
            candidate_inputs=successor_inputs,
            replay_state=descendant_replay,
            suffix="stale-context",
        )
    assert stale_context.value.reason_code is CommitReasonCode.REPLAY_HEAD_MISMATCH
    with pytest.raises(CommitEvaluationError) as stale_replay:
        _assessment(
            scenario,
            step=7,
            context=successor_context,
            candidate_inputs=successor_inputs,
            replay_state=scenario.replay_state,
            suffix="stale-replay",
        )
    assert stale_replay.value.reason_code is CommitReasonCode.REPLAY_HEAD_MISMATCH

    deleted_receipt_state = replace(descendant_replay)
    object.__setattr__(
        deleted_receipt_state,
        "receipts",
        descendant_replay.receipts[:-1],
    )
    assert not commit_replay_state_is_authoritative(deleted_receipt_state)
    with pytest.raises(CommitEvaluationError) as deleted_receipt:
        _assessment(
            scenario,
            step=7,
            context=successor_context,
            candidate_inputs=successor_inputs,
            replay_state=deleted_receipt_state,
            suffix="deleted-receipt",
        )
    assert deleted_receipt.value.reason_code is CommitReasonCode.REPLAY_HEAD_MISMATCH

    substituted_receipt_state = replace(descendant_replay)
    substituted = replace(
        descendant_replay.receipts[-1],
        payload_fingerprint=_fingerprint("substituted-replay-payload"),
    )
    object.__setattr__(
        substituted_receipt_state,
        "receipts",
        (*descendant_replay.receipts[:-1], substituted),
    )
    assert not commit_replay_state_is_authoritative(substituted_receipt_state)
    with pytest.raises(CommitEvaluationError) as substituted_receipt:
        _assessment(
            scenario,
            step=7,
            context=successor_context,
            candidate_inputs=successor_inputs,
            replay_state=substituted_receipt_state,
            suffix="substituted-receipt",
        )
    assert substituted_receipt.value.reason_code is (
        CommitReasonCode.REPLAY_HEAD_MISMATCH
    )


def test_reset_budget_exhaustion_cannot_lower_or_restart_stability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_policy = commit_engine_tests._policy

    def no_reset_policy(**kwargs):
        policy = original_policy(**kwargs)
        return replace(
            policy,
            commit_window=replace(
                policy.commit_window,
                maximum_leader_resets=0,
            ),
        )

    monkeypatch.setattr(commit_engine_tests, "_policy", no_reset_policy)
    scenario = commit_engine_tests._scenario()
    state = _advance(_window(scenario), scenario, step=5)
    blocked_stop, denied = _gates(
        scenario,
        context=scenario.context,
        step=6,
        blocked=True,
    )
    blocked = _assessment(
        scenario,
        step=6,
        stop_resolution=blocked_stop,
        permission=denied,
        suffix="budget-exhausted",
    )
    state = _advance(
        state,
        scenario,
        step=6,
        assessment=blocked,
    )
    assert state.remaining_reset_budget == 0
    assert state.reset_budget_exhausted is True
    assert state.window_count == 0
    assert state.last_ready is False
    assert not commit_window_ready(state)
    assert state.minimum_stability_steps == scenario.threshold.stability_steps


def test_risk_and_threshold_change_reset_without_lowering_stability() -> None:
    scenario = _scenario()
    initial = _window(scenario)
    first = _advance(initial, scenario, step=5)
    new_risk, new_chain = issue_risk_assessment(
        scenario.risk_chain_state,
        assessment_id=f"risk:{scenario.run_id}:moderate",
        risk_band=RiskBand.MODERATE,
        risk_input_fingerprints=(_fingerprint(f"risk:moderate:{scenario.run_id}"),),
        rationale_codes=("risk_increased",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=scenario.policy,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=scenario.run_id,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="governance:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=6,
        expires_at_step=12,
        provenance=f"urn:test:risk:moderate:{scenario.run_id}",
        trace_event_id=f"trace:risk:moderate:{scenario.run_id}",
        previous_assessment=scenario.risk_assessment,
    )
    new_threshold = issue_commit_threshold_snapshot(
        new_risk,
        chain_state=new_chain,
        threshold_id=f"threshold:{scenario.run_id}:moderate",
        commit_policy=scenario.policy,
        issuer_id="governance:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=6,
        provenance=f"urn:test:threshold:moderate:{scenario.run_id}",
        trace_event_id=f"trace:threshold:moderate:{scenario.run_id}",
    )
    # Engine context regeneration is covered by the commit-engine tests. The
    # temporal classifier proves both independently bound roots force a reset,
    # and the state stores a monotone max threshold on every real
    # advance/restart.
    common = {
        "current_step": 6,
        "ready": True,
        "leader_candidate_id": first.leader_candidate_id,
        "manifest_root": first.manifest_root,
        "commit_policy_root": first.commit_policy_root,
        "risk_assessment_root": new_threshold.risk_assessment_fingerprint,
        "membership_root": first.membership_root,
        "threshold_root": _fingerprint("placeholder"),
    }
    assert _window_reset_reason(first, **common) == "risk_change"
    assert new_threshold.stability_steps >= first.minimum_stability_steps


def _epoch_threshold(scenario, *, epoch: int, step: int):
    chain = initialize_risk_assessment_chain(
        commit_policy=scenario.policy,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=scenario.run_id,
        target=TARGET,
        epoch=epoch,
        issuer_id="governance:risk-chain",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=step,
        expires_at_step=12,
        provenance=f"urn:test:risk-chain:{scenario.run_id}:{epoch}",
        trace_event_id=f"trace:risk-chain:{scenario.run_id}:{epoch}",
    )
    risk, chain = issue_risk_assessment(
        chain,
        assessment_id=f"risk:{scenario.run_id}:{epoch}",
        risk_band=RiskBand.LOW,
        risk_input_fingerprints=(_fingerprint(f"risk:{scenario.run_id}:{epoch}"),),
        rationale_codes=("epoch_restart",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=scenario.policy,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=scenario.run_id,
        target=TARGET,
        epoch=epoch,
        issuer_id="governance:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        expires_at_step=12,
        provenance=f"urn:test:risk:{scenario.run_id}:{epoch}",
        trace_event_id=f"trace:risk:{scenario.run_id}:{epoch}",
    )
    return issue_commit_threshold_snapshot(
        risk,
        chain_state=chain,
        threshold_id=f"threshold:{scenario.run_id}:{epoch}",
        commit_policy=scenario.policy,
        issuer_id="governance:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:test:threshold:{scenario.run_id}:{epoch}",
        trace_event_id=f"trace:threshold:{scenario.run_id}:{epoch}",
    )


def test_epoch_restart_stays_on_one_run_chain_and_never_extends_deadlines() -> None:
    scenario = _scenario()
    first = _advance(_window(scenario), scenario, step=5)
    threshold = _epoch_threshold(scenario, epoch=EPOCH + 1, step=6)
    restarted = restart_commit_window_epoch(
        first,
        new_epoch=EPOCH + 1,
        current_step=6,
        commit_policy=scenario.policy,
        threshold_snapshot=threshold,
        membership_root=_fingerprint(f"membership:{scenario.run_id}:{EPOCH + 1}"),
    )
    assert restarted.chain_id == first.chain_id
    assert restarted.epoch == EPOCH + 1
    assert restarted.remaining_epoch_restart_budget == 0
    assert restarted.window_count == 0
    assert restarted.absolute_deadline_step == first.absolute_deadline_step
    assert restarted.absolute_run_deadline_step == first.absolute_run_deadline_step
    assert restarted.minimum_stability_steps >= first.minimum_stability_steps
    assert restart_commit_window_epoch(
        first,
        new_epoch=EPOCH + 1,
        current_step=6,
        commit_policy=scenario.policy,
        threshold_snapshot=threshold,
        membership_root=_fingerprint(f"membership:{scenario.run_id}:{EPOCH + 1}"),
    ) is restarted

    with pytest.raises(GovernanceError, match="different base"):
        initialize_commit_window_state(
            commit_policy=scenario.policy,
            profile=PROFILE,
            assurance=ASSURANCE,
            manifest_root=scenario.context.manifest_root,
            commit_policy_root=scenario.context.commit_policy_root,
            protocol_id=PROTOCOL_ID,
            run_id=scenario.run_id,
            target=TARGET,
            epoch=EPOCH + 1,
            risk_assessment_root=threshold.risk_assessment_fingerprint,
            membership_root=restarted.membership_root,
            threshold_snapshot=threshold,
            current_step=6,
            issuer_id="governance:window",
            authority=AuthorityLevel.GOVERNANCE,
            provenance=f"urn:test:window:{scenario.run_id}:parallel",
            trace_event_id=f"trace:window:{scenario.run_id}:parallel",
        )
    with pytest.raises(GovernanceError, match="budget is exhausted"):
        restart_commit_window_epoch(
            restarted,
            new_epoch=EPOCH + 2,
            current_step=7,
            commit_policy=scenario.policy,
            threshold_snapshot=threshold,
            membership_root=_fingerprint("membership:third-epoch"),
        )

    race = _scenario()
    race_parent = _advance(_window(race), race, step=5)
    race_threshold = _epoch_threshold(race, epoch=EPOCH + 1, step=6)
    barrier = Barrier(2)

    def competing_restart(label: str):
        barrier.wait()
        try:
            return restart_commit_window_epoch(
                race_parent,
                new_epoch=EPOCH + 1,
                current_step=6,
                commit_policy=race.policy,
                threshold_snapshot=race_threshold,
                membership_root=_fingerprint(label),
            )
        except GovernanceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        raced = tuple(pool.map(competing_restart, ("member:left", "member:right")))
    assert sum(type(item) is CommitWindowState for item in raced) == 1
    assert sum(isinstance(item, GovernanceError) for item in raced) == 1


def test_window_tamper_and_raw_legacy_api_fail_closed() -> None:
    scenario = _scenario()
    issued = _window(scenario)
    forged = replace(issued)
    assert not commit_window_state_is_authoritative(forged)
    before = commit_window_state_fingerprint(issued)
    object.__setattr__(issued, "minimum_stability_steps", 1)
    assert not commit_window_state_is_authoritative(issued)
    assert commit_window_state_fingerprint(issued) != before
    assert not commit_window_state_is_current(issued)

    another = _scenario()
    with pytest.raises(TypeError, match="unexpected keyword"):
        initialize_commit_window_state(  # type: ignore[call-arg]
            commit_policy=another.policy,
            profile=PROFILE,
            assurance=ASSURANCE,
            manifest_root=another.context.manifest_root,
            commit_policy_root=another.context.commit_policy_root,
            protocol_id=PROTOCOL_ID,
            run_id=another.run_id,
            target=TARGET,
            epoch=EPOCH,
            risk_assessment_root=another.context.risk_assessment_fingerprint,
            membership_root=another.context.membership_root,
            threshold_snapshot=another.threshold,
            current_step=4,
            issuer_id="governance:window",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:legacy",
            trace_event_id="trace:legacy",
            deliberation_deadline_steps=1,
        )


def _replay(*, run_id: str) -> CommitReplayState:
    return initialize_commit_replay_state(
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=_fingerprint("manifest"),
        commit_policy_root=_fingerprint("policy"),
        protocol_id="protocol:optimal",
        run_id=run_id,
        current_step=0,
        issuer_id="governance:replay",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:commit-replay",
        trace_event_id=f"trace:{run_id}",
    )


def _receipt(
    namespace: ReplayNamespace,
    record_id: str,
    nonce: str,
    payload_fingerprint: str,
) -> ReplayReceipt:
    return ReplayReceipt(
        namespace=namespace,
        record_id=record_id,
        nonce=nonce,
        payload_fingerprint=payload_fingerprint,
        target="decision:collective",
        candidate_id="candidate:alpha",
        epoch=1,
        principal_id="principal:alpha",
    )


def test_replay_initialization_is_concurrent_idempotent_and_strongly_retained() -> None:
    run_id = "run:replay:concurrent-init"

    with ThreadPoolExecutor(max_workers=8) as pool:
        states = tuple(pool.map(lambda _: _replay(run_id=run_id), range(32)))

    assert all(state is states[0] for state in states)
    retained = weakref.ref(states[0])
    del states
    gc.collect()
    current = _replay(run_id=run_id)
    assert retained() is current
    assert commit_replay_state_is_authoritative(current)


def test_replay_state_is_canonical_idempotent_linear_and_conflict_safe() -> None:
    observation = _receipt(
        ReplayNamespace.OBSERVATION,
        "observation:1",
        "nonce:observation:1",
        _fingerprint("observation"),
    )
    lease = _receipt(
        ReplayNamespace.SUPPORT_LEASE,
        "lease:1",
        "nonce:lease:1",
        _fingerprint("lease"),
    )
    initial = _replay(run_id="run:replay:canonical")
    first = record_commit_replay_receipts(
        initial,
        current_step=1,
        receipts=(lease, observation),
    )
    assert record_commit_replay_receipts(
        initial,
        current_step=1,
        receipts=(observation, lease),
    ) is first
    assert commit_replay_state_is_authoritative(first)
    assert record_commit_replay_receipts(
        first,
        current_step=2,
        receipts=(observation,),
    ) is first

    conflicting = replace(
        observation,
        payload_fingerprint=_fingerprint("conflict"),
    )
    with pytest.raises(GovernanceError, match="safety violation"):
        record_commit_replay_receipts(
            first,
            current_step=2,
            receipts=(conflicting,),
        )
    fork = _receipt(
        ReplayNamespace.CHALLENGE,
        "challenge:fork",
        "nonce:challenge:fork",
        _fingerprint("fork"),
    )
    with pytest.raises(GovernanceError, match="stale or would fork"):
        record_commit_replay_receipts(
            initial,
            current_step=1,
            receipts=(fork,),
        )

    race_parent = _replay(run_id="run:replay:race")
    left = _receipt(
        ReplayNamespace.OBSERVATION,
        "observation:left",
        "nonce:observation:left",
        _fingerprint("observation:left"),
    )
    right = _receipt(
        ReplayNamespace.OBSERVATION,
        "observation:right",
        "nonce:observation:right",
        _fingerprint("observation:right"),
    )
    barrier = Barrier(2)

    def competing_replay(receipt):
        barrier.wait()
        try:
            return record_commit_replay_receipts(
                race_parent,
                current_step=1,
                receipts=(receipt,),
            )
        except GovernanceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        raced = tuple(pool.map(competing_replay, (left, right)))
    assert sum(type(item) is CommitReplayState for item in raced) == 1
    assert sum(isinstance(item, GovernanceError) for item in raced) == 1


def test_replay_state_forgery_and_tamper_fail_closed() -> None:
    issued = _replay(run_id="run:replay:tamper")
    forged = replace(issued)
    assert not commit_replay_state_is_authoritative(forged)
    before = commit_replay_state_fingerprint(issued)
    object.__setattr__(issued, "current_step", 2)
    assert not commit_replay_state_is_authoritative(issued)
    assert commit_replay_state_fingerprint(issued) != before
